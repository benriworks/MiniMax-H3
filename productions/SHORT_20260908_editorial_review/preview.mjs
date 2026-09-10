// Six-second silent design verification using the actual common composition.
// This is not a new narrated production, Studio Run, or publication approval.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const folder = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(folder, '../..');
const studio = path.join(root, 'studio');
const require = createRequire(path.join(studio, 'package.json'));
const { bundle } = require('@remotion/bundler');
const { selectComposition, renderStill, renderMedia } = require('@remotion/renderer');
const { chromium } = require('playwright');
const hash = bytes => createHash('sha256').update(bytes).digest('hex').toUpperCase();
const manifestPath = path.join(root, 'outputs/studio/verification/claude-illustrated-20260906/panels/20260906T065122124Z/manifest.json');
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
const capture = { path: 'outputs/studio/claude-captures/production_18812c9ff18e4955858700ee7815f678/claude_capture_52dede446256444c9e9ed7a5a0965628/claude-capture.mp4', sha256: 'B8B9E07B8987D824D8DD1BE0EE7DACDF9613C82406E2B53763841CA6AF01A362' };
const inputs = [manifest.panels.find(item => item.role === 'hook'), capture, manifest.panels.find(item => item.role === 'cta')];
const output = path.join(root, 'outputs/studio/verification/editorial-20260908', new Date().toISOString().replaceAll(/[^0-9TZ]/g, ''));
const publicDir = path.join(output, 'public');
await fs.mkdir(path.join(publicDir, 'template-assets'), { recursive: true });
for (const [index, item] of inputs.entries()) {
  const bytes = await fs.readFile(path.join(root, item.path));
  if (hash(bytes) !== item.sha256) throw new Error('Existing source changed');
  await fs.writeFile(path.join(publicDir, `clip-0${index}.mp4`), bytes, { flag: 'wx' });
}
const fontPath = 'studio/public/template-assets/NotoSansJP-Variable.ttf';
const font = await fs.readFile(path.join(root, fontPath));
if (hash(font) !== 'C2F3B4D463500A2DDCD3849CDED1FCEEB9FD6D1C32E6CBECD568453BA50FC68F') throw new Error('Font changed');
await fs.writeFile(path.join(publicDir, 'template-assets/NotoSansJP-Variable.ttf'), font, { flag: 'wx' });
const sourceNames = ['studio/src/remotion/entry.tsx', 'studio/src/remotion/TimelineComposition.tsx', 'studio/src/remotion/model.ts', 'studio/src/remotion/ScreenTypography.tsx', 'studio/src/remotion/screenThemes.ts', 'studio/src/api.ts', 'studio/src/types.ts', 'studio/src/status.ts', 'studio/package.json', 'studio/package-lock.json', fontPath, path.relative(root, fileURLToPath(import.meta.url))];
const sourceHashes = Object.fromEntries(await Promise.all(sourceNames.map(async name => [name, hash(await fs.readFile(path.join(root, name)))])));
const props = { schemaVersion: 1, width: 1080, height: 1920, fps: 24, durationInFrames: 144,
  clips: manifest.recipe.scenes.map((scene, index) => {
    const start = index === 1 ? 17000 : 2000;
    return { src: `clip-0${index}.mp4`, startMs: start, endMs: start + 2000,
      trimBeforeFrame: start * 24 / 1000, trimAfterFrame: (start + 2000) * 24 / 1000, durationInFrames: 48,
      volumePercent: 0, layoutPreset: 'screen_explainer_v1', screenTheme: 'claude_editorial_v1', transitionToNext: null,
      overlay: { text: scene.headline, startMs: 0, endMs: 2000, startFrame: 0, endFrame: 48, position: 'top', stylePreset: 'shorts_ja_large_v1' } };
  }) };
const serveUrl = await bundle({ entryPoint: path.join(studio, 'src/remotion/entry.tsx'), rootDir: studio, publicDir, outDir: path.join(output, 'bundle'), enableCaching: true });
const browserExecutable = chromium.executablePath();
const composition = await selectComposition({ serveUrl, id: 'MiniMaxH3DetailedTimelineV1', browserExecutable, inputProps: props });
const figures = [];
for (const frame of [0, 24, 72, 120]) {
  const file = path.join(output, `frame-${frame}.png`);
  await renderStill({ composition, serveUrl, inputProps: props, browserExecutable, frame, output: file, imageFormat: 'png', overwrite: false });
  figures.push({ frame, path: path.relative(root, file), sha256: hash(await fs.readFile(file)) });
}
const video = path.join(output, 'editorial-design-preview-6s.mp4');
await renderMedia({ composition, serveUrl, inputProps: props, browserExecutable, outputLocation: video, codec: 'h264', pixelFormat: 'yuv420p', imageFormat: 'png', colorSpace: 'bt709', crf: 16, muted: true, concurrency: 2, overwrite: false });
const probe = JSON.parse(execFileSync('ffprobe', ['-v','error','-show_streams','-show_format','-of','json',video], { encoding: 'utf8', windowsHide: true }));
if (probe.streams.length !== 1 || probe.streams[0].nb_frames !== '144' || Number(probe.format.duration) !== 6) throw new Error('Preview format mismatch');
execFileSync('ffmpeg', ['-v','error','-xerror','-i',video,'-f','null','-'], { windowsHide: true });
for (const [name, digest] of Object.entries(sourceHashes)) if (hash(await fs.readFile(path.join(root, name))) !== digest) throw new Error('Renderer source changed during verification');
const report = { schema_version: 1, purpose: 'silent design review, not a narrated production or Studio Run', sourceHashes, inputs, props, figures, video: { path: path.relative(root, video), sha256: hash(await fs.readFile(video)), bytes: (await fs.stat(video)).size }, probe, full_decode_verified: true, new_capture: false, new_image_generation: false, narration_changed: false, public_quality_verified: false };
await fs.writeFile(path.join(output,'verification.json'), JSON.stringify(report,null,2)+'\n', { flag: 'wx' });
console.log(JSON.stringify({ output, video: report.video, figures }));
