// Review real prepared timings without creating or altering a full-video output.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..'), studio = path.join(root, 'studio');
const require = createRequire(path.join(studio, 'package.json'));
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderStill} = require('@remotion/renderer');
const {chromium} = require('playwright');
const [outArg, selection = '01,02,03,04,05'] = process.argv.slice(2);
if (!outArg) throw Error('Supply a new review output folder');
const out = path.resolve(root, outArg);
if (!out.startsWith(here + path.sep)) throw Error('Review output must remain in this series');
await fs.mkdir(out, {recursive: false});
const record = async file => ({path: path.relative(root, file).replaceAll('\\', '/'),
  bytes: (await fs.stat(file)).size, sha256: createHash('sha256').update(await fs.readFile(file)).digest('hex').toUpperCase()});
const check = async item => {
  const file = path.resolve(root, item.path);
  if (!file.startsWith(root + path.sep)) throw Error('Input outside workspace');
  const current = await record(file);
  if (current.bytes !== item.bytes || current.sha256 !== item.sha256) throw Error('Changed prepared input: ' + item.path);
};
const inputs = [], images = [];
for (const number of selection.split(',')) {
  if (!/^0[1-5]$/.test(number)) throw Error('Expected episode 01 through 05');
  const statePath = path.join(here, number, 'state.json');
  const state = JSON.parse(await fs.readFile(statePath, 'utf8'));
  const source = path.resolve(root, state.output);
  if (!source.startsWith(path.join(root, 'outputs/productions', `SHORT_20261022_claude_${number}_work`) + path.sep)) throw Error('Unexpected prepared folder');
  const prep = JSON.parse(await fs.readFile(path.join(source, 'preparation.json'), 'utf8'));
  for (const item of prep.sources) await check(item);
  inputs.push(await record(path.join(source, 'props.json')), ...prep.sources);
  const props = JSON.parse(await fs.readFile(path.join(source, 'props.json'), 'utf8'));
  const local = path.join(out, number); await fs.mkdir(local);
  const pub = path.join(local, 'public');
  await fs.cp(path.join(source, 'public'), pub, {recursive: true, errorOnExist: true});
  await fs.mkdir(path.join(pub, 'template-assets'), {recursive: true});
  await fs.copyFile(path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf'), path.join(pub, 'template-assets/NotoSansJP-Variable.ttf'));
  const serveUrl = await bundle({entryPoint: path.join(studio, 'src/remotion/creatorEntry.tsx'), rootDir: studio,
    publicDir: pub, outDir: path.join(local, 'bundle')});
  const browserExecutable = chromium.executablePath();
  const composition = await selectComposition({serveUrl, id: 'CreatorShort', browserExecutable, inputProps: props});
  for (const index of [0, 6]) {
    const scene = props.scenes[index];
    const samples = [{name: 'middle', offset: Math.min(scene.duration - 1, 44)}];
    if (scene.mediaPlayFrames < scene.duration) samples.push({name: 'after-media', offset: scene.duration - 1});
    for (const sample of samples) {
      const file = path.join(local, `scene-${index}-${sample.name}.png`);
      await renderStill({composition, serveUrl, browserExecutable, inputProps: props,
        frame: scene.from + sample.offset, imageFormat: 'png', output: file, overwrite: false});
      images.push({episode: Number(number), scene: index, frame: scene.from + sample.offset, artifact: await record(file)});
      console.log(JSON.stringify({episode: number, scene: index, sample: sample.name, file}));
    }
  }
}
for (const item of inputs) await check(item);
await fs.writeFile(path.join(out, 'review.json'), JSON.stringify({status: 'requires_visual_inspection',
  actual_narration_timing: true, tts_requests: 0, full_video_rendered: false, inputs, images,
  user_approved: false, root_visual_review_status: 'pending'}, null, 2) + '\n', {flag: 'wx'});
