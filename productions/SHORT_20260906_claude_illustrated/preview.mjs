// Render the real common screen template with this production's sealed panels.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';

const production = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(production, '../..');
const studio = path.join(root, 'studio');
const requireStudio = createRequire(path.join(studio, 'package.json'));
const { bundle } = requireStudio('@remotion/bundler');
const { selectComposition, renderStill } = requireStudio('@remotion/renderer');
const { chromium } = requireStudio('playwright');
const manifest = JSON.parse(await fs.readFile(process.argv[2], 'utf8'));
const hash = bytes => createHash('sha256').update(bytes).digest('hex').toUpperCase();
const source = { path: 'outputs/studio/claude-captures/production_18812c9ff18e4955858700ee7815f678/claude_capture_52dede446256444c9e9ed7a5a0965628/claude-capture.mp4', sha256: 'B8B9E07B8987D824D8DD1BE0EE7DACDF9613C82406E2B53763841CA6AF01A362' };
const sources = [manifest.panels.find(p => p.role === 'hook'), source, manifest.panels.find(p => p.role === 'cta')];
const output = path.join(path.dirname(path.resolve(process.argv[2])), 'template-preview');
const publicDir = path.join(output, 'public');
await fs.mkdir(path.join(publicDir, 'template-assets'), { recursive: true });
for (const item of manifest.files.concat(manifest.panels, [source])) {
  const bytes = await fs.readFile(path.join(root, item.path));
  if (hash(bytes) !== item.sha256) throw new Error('Sealed preview input changed');
}
await fs.copyFile(path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf'), path.join(publicDir, 'template-assets/NotoSansJP-Variable.ttf'));
for (const [index, item] of sources.entries()) await fs.copyFile(path.join(root, item.path), path.join(publicDir, `clip-0${index}.mp4`));
const props = { schemaVersion: 1, width: 1080, height: 1920, fps: 24, durationInFrames: 504,
  clips: manifest.recipe.scenes.map((scene, index) => ({ src: `clip-0${index}.mp4`, startMs: scene.start_ms, endMs: scene.end_ms,
    trimBeforeFrame: Math.round(scene.start_ms * 24 / 1000), trimAfterFrame: Math.round(scene.end_ms * 24 / 1000), durationInFrames: 168,
    volumePercent: 0, layoutPreset: 'screen_explainer_v1', screenTheme: manifest.recipe.screen_theme, transitionToNext: null,
    overlay: { text: scene.headline, startMs: 0, endMs: 7000, startFrame: 0, endFrame: 168, position: 'top', stylePreset: 'shorts_ja_large_v1' } })) };
const serveUrl = await bundle({ entryPoint: path.join(studio, 'src/remotion/entry.tsx'), rootDir: studio, publicDir, outDir: path.join(output, 'bundle'), enableCaching: true });
const browserExecutable = chromium.executablePath();
const composition = await selectComposition({ serveUrl, id: 'MiniMaxH3DetailedTimelineV1', browserExecutable, inputProps: props });
const figures = [];
for (const frame of [72, 240, 432]) {
  const destination = path.join(output, `f${frame}.png`);
  await renderStill({ composition, serveUrl, inputProps: props, browserExecutable, frame, output: destination, imageFormat: 'png', overwrite: false });
  figures.push({ frame, path: path.relative(root, destination).replaceAll('\\', '/'), sha256: hash(await fs.readFile(destination)) });
}
await fs.writeFile(path.join(output, 'preview.json'), `${JSON.stringify({ figures, captioned: false, source: 'common template; source illustration panels are prerendered' }, null, 2)}\n`, { flag: 'wx' });
console.log(JSON.stringify({ output, figures }));
