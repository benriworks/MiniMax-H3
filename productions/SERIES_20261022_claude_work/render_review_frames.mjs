// Still-frame review only: no speech generation and no completed-video claim.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {validateCaptureForRender} from '../../studio/capture-render-validation.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const studio = path.join(root, 'studio');
const require = createRequire(path.join(studio, 'package.json'));
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderStill} = require('@remotion/renderer');
const {chromium} = require('playwright');
const [draftArg, outArg, selection = '01,02,03,04', indicesArg = '0,1,2,3,4,5,6'] = process.argv.slice(2);
if (!draftArg || !outArg) throw Error('Supply draft folder and new output folder');
const draft = path.resolve(root, draftArg), out = path.resolve(root, outArg);
if (!out.startsWith(here + path.sep)) throw Error('Review output must remain in the Claude series');
await fs.mkdir(out, {recursive: false});
const pub = path.join(out, 'public');
await fs.mkdir(path.join(pub, 'template-assets'), {recursive: true});
await fs.copyFile(path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf'), path.join(pub, 'template-assets/NotoSansJP-Variable.ttf'));
const record = async p => ({path: path.relative(root, p).replaceAll('\\', '/'), bytes: (await fs.stat(p)).size,
  sha256: createHash('sha256').update(await fs.readFile(p)).digest('hex').toUpperCase()});
const indices = indicesArg.split(',').map(Number), examples = [], captures = [], inputs = [];
for (const number of selection.split(',')) {
  const storyFile = path.join(draft, number, 'creator-story.draft.json');
  const story = JSON.parse(await fs.readFile(storyFile, 'utf8'));
  inputs.push(await record(storyFile));
  const props = {title: story.title, durationInFrames: 720, showGuides: false, scenes: [], captions: []};
  let from = 0;
  for (const [index, scene] of story.scenes.entries()) {
    const duration = index === 6 ? 102 : 103;
    const item = {...scene, id: `${number}-${index}`, from, duration};
    delete item.narration; delete item.captions; delete item.source_ids;
    if (scene.kind === 'source' && !scene.capture) throw Error(`Missing capture ${number}/${index}`);
    if (scene.capture) {
      const proof = JSON.parse(await fs.readFile(path.join(root, scene.capture.proof), 'utf8'));
      const name = `capture-${String(Number(number) * 10 + index).padStart(2, '0')}.png`;
      await fs.copyFile(path.join(root, scene.capture.path), path.join(pub, name));
      const display = validateCaptureForRender(scene.capture, {codec_name: 'png', width: proof.clip.width, height: proof.clip.height},
        await record(path.join(pub, name)), [proof.artifact, proof.context], [proof]);
      captures.push({episode: number, scene: index + 1, ...display});
      item.capture = {origin: scene.capture.origin, image: name, title: scene.capture.title};
      if (scene.capture.origin === 'official') item.capture.source_url = scene.capture.source_url;
      else Object.assign(item.capture, {product: scene.capture.product, phase: scene.capture.phase});
    }
    if (scene.media) {
      const name = `media-${String(Number(number) * 10 + index).padStart(2, '0')}.mp4`;
      await fs.copyFile(path.join(root, scene.media.path), path.join(pub, name));
      inputs.push(await record(path.join(root, scene.media.proof)));
      item.media = name;
    }
    props.scenes.push(item);
    for (const [i, text] of scene.captions.entries()) props.captions.push({start: from + Math.floor(i * duration / scene.captions.length),
      end: from + Math.floor((i + 1) * duration / scene.captions.length) - 1, text});
    from += duration;
  }
  await fs.writeFile(path.join(out, `props-${number}.json`), JSON.stringify(props, null, 2) + '\n', {flag: 'wx'});
  examples.push({number, props});
}
const serveUrl = await bundle({entryPoint: path.join(studio, 'src/remotion/creatorEntry.tsx'), rootDir: studio, publicDir: pub, outDir: path.join(out, 'bundle')});
const browserExecutable = chromium.executablePath(), images = [];
for (const {number, props} of examples) {
  const composition = await selectComposition({serveUrl, id: 'CreatorShort', browserExecutable, inputProps: props});
  for (const index of indices) {
    const output = path.join(out, `episode-${number}-scene-${index + 1}.png`);
    await renderStill({composition, serveUrl, browserExecutable, inputProps: props, frame: props.scenes[index].from + 44,
      imageFormat: 'png', output, overwrite: false});
    images.push(await record(output));
    console.log(JSON.stringify({episode: number, scene: index + 1, path: output}));
  }
}
await fs.writeFile(path.join(out, 'review.json'), JSON.stringify({status: 'requires_visual_inspection',
  actual_narration_timing: false, fixture_timing_for_layout_only: true, tts_requests: 0,
  inputs, captureDisplay: captures, images, user_approved: false, root_visual_review_status: 'pending'}, null, 2) + '\n', {flag: 'wx'});
