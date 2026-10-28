import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const folder = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(folder, '../..');
const studio = path.join(root, 'studio');
const require = createRequire(path.join(studio, 'package.json'));
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderMedia, renderStill} = require('@remotion/renderer');
const {chromium} = require('playwright');
const output = path.resolve(process.argv[2]);
if (!output.startsWith(path.join(root, 'outputs') + path.sep)) throw new Error('Expected workspace output');
const read = async file => JSON.parse(await fs.readFile(file, 'utf8'));
const record = async file => ({path: path.relative(root, file).replaceAll('\\', '/'), bytes: (await fs.stat(file)).size, sha256: createHash('sha256').update(await fs.readFile(file)).digest('hex').toUpperCase()});
const check = async r => {
  const file = path.resolve(root, r.path ?? r.rel_path);
  if (!file.startsWith(root + path.sep)) throw new Error('Source outside workspace');
  const actual = await record(file);
  if (actual.bytes !== r.bytes || actual.sha256 !== r.sha256) throw new Error('Changed input: ' + r.path);
  return file;
};
const prep = await read(path.join(output, 'preparation.json'));
for (const r of prep.sources) await check(r);
const proofFile = path.resolve(root, prep.story.source_generation_record);
const proof = await read(proofFile);
if (proof.execution.success !== true || proof.paid_api_calls !== 0 || proof.review_status !== 'visual_review_passed') throw new Error('Source requires verified completion and visual review');
const sourceFile = await check(proof.artifact);
for (const r of proof.inputs) await check(r);
const probe = file => JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file], {encoding: 'utf8', windowsHide: true}));
const decode = file => execFileSync('ffmpeg', ['-v', 'error', '-xerror', '-i', file, '-f', 'null', '-'], {windowsHide: true});
const sourceProbe = probe(sourceFile);
const v = sourceProbe.streams.find(s => s.codec_type === 'video');
if (!v || v.width !== 768 || v.height !== 1376 || v.avg_frame_rate !== '24/1' || Number(v.nb_frames) < 120) throw new Error('Unexpected H3 source format');
decode(sourceFile);
const sources = [...prep.sources, ...proof.inputs, proof.artifact, await record(proofFile), ...await Promise.all([
  'Catch.tsx', 'render.mjs', 'produce.py', 'story.json',
].map(name => record(path.join(folder, name)))), ...await Promise.all([
  'src/remotion/ScreenTypography.tsx', 'public/template-assets/NotoSansJP-Variable.ttf', 'package.json', 'package-lock.json',
].map(name => record(path.join(studio, name))))];
const text = await fs.readFile(path.join(folder, 'Catch.tsx'), 'utf8');
const sizes = [...text.matchAll(/fontSize:\s*(\d+)/g)].map(m => Number(m[1]));
if (Math.min(...sizes) !== prep.story.minimum_font_px || Math.min(...sizes) < 54) throw new Error('Font size floor violated');
const publicDir = path.join(output, 'public');
await fs.mkdir(path.join(publicDir, 'template-assets'), {recursive: true});
await fs.copyFile(sourceFile, path.join(publicDir, 'source.mp4'));
await fs.copyFile(path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf'), path.join(publicDir, 'template-assets/NotoSansJP-Variable.ttf'));
const browserExecutable = chromium.executablePath();
const serveUrl = await bundle({entryPoint: path.join(folder, 'Catch.tsx'), rootDir: studio, publicDir, outDir: path.join(output, 'bundle'), webpackOverride: c => ({...c, resolve: {...c.resolve, modules: [path.join(studio, 'node_modules'), ...(c.resolve?.modules ?? [])]}})});
const composition = await selectComposition({serveUrl, id: 'ClaudeAcquired5', browserExecutable});
for (const frame of [0, 24, 48, 72, 108]) await renderStill({composition, serveUrl, browserExecutable, frame, imageFormat: 'png', output: path.join(output, `design-${frame}.png`), overwrite: false});
console.log(JSON.stringify({event: 'stills_ready', output}));
const file = path.join(output, 'timeline-silent.mp4');
let last = -1;
await renderMedia({composition, serveUrl, browserExecutable, outputLocation: file, codec: 'h264', pixelFormat: 'yuv420p', colorSpace: 'bt709', imageFormat: 'png', crf: 12, muted: true, concurrency: 2, overwrite: false, onProgress: ({progress}) => {const n = Math.floor(progress * 10); if (n > last) {last = n; console.log(JSON.stringify({event: 'render_progress', percent: n * 10}));}}});
const result = probe(file);
const video = result.streams[0];
if (result.streams.length !== 1 || video.width !== 1080 || video.height !== 1920 || video.avg_frame_rate !== '24/1' || Number(video.nb_frames) !== 120 || Number(result.format.duration) !== 5) throw new Error('Timeline format mismatch');
decode(file);
for (const r of sources) await check(r);
await fs.writeFile(path.join(output, 'render.json'), JSON.stringify({sources, timeline: await record(file), probe: result, source_probe: sourceProbe, full_decode_verified: true, crf: 12, typography: {minimum_font_px: Math.min(...sizes), at_360px_width: Math.min(...sizes) / 3, font_sizes: [...new Set(sizes)]}}, null, 2) + '\n', {flag: 'wx'});
console.log(JSON.stringify({event: 'render_complete', output}));
