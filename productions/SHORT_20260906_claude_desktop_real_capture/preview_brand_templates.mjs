// Design verification of the actual reusable composition, not a second renderer.
// The Code theme is exercised by contract tests; this real Desktop footage is
// deliberately never relabeled as a Claude Code demonstration.
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
const source = path.join(root, 'outputs/studio/claude-captures/production_18812c9ff18e4955858700ee7815f678/claude_capture_52dede446256444c9e9ed7a5a0965628/claude-capture.mp4');
const font = path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf');
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex').toUpperCase();
const sourceBytes = await fs.readFile(source);
if (hash(sourceBytes) !== 'B8B9E07B8987D824D8DD1BE0EE7DACDF9613C82406E2B53763841CA6AF01A362') throw new Error('The approved Desktop source changed');
const fontBytes = await fs.readFile(font);
if (hash(fontBytes) !== 'C2F3B4D463500A2DDCD3849CDED1FCEEB9FD6D1C32E6CBECD568453BA50FC68F') throw new Error('Pinned Japanese font changed');
const output = path.join(root, 'outputs/studio/verification/claude-desktop-real-20260906/brand-review', new Date().toISOString().replaceAll(/[^0-9TZ]/g, ''));
await fs.mkdir(output, { recursive: true });
const publicDir = path.join(output, 'public');
await fs.mkdir(path.join(publicDir, 'template-assets'), { recursive: true });
await fs.writeFile(path.join(publicDir, 'template-assets/NotoSansJP-Variable.ttf'), fontBytes, { flag: 'wx' });
for (let index = 0; index < 3; index += 1) await fs.writeFile(path.join(publicDir, `clip-0${index}.mp4`), sourceBytes, { flag: 'wx' });
const boundSources = ['entry.tsx', 'TimelineComposition.tsx', 'model.ts', 'screenThemes.ts', 'ScreenTypography.tsx'].map((name) => path.join(studio, 'src/remotion', name));
boundSources.push(...['api.ts', 'types.ts', 'status.ts'].map((name) => path.join(studio, 'src', name)));
const sourceHashes = Object.fromEntries(await Promise.all(boundSources.map(async (name) => [path.relative(root, name), hash(await fs.readFile(name))])));
const serveUrl = await bundle({ entryPoint: path.join(studio, 'src/remotion/entry.tsx'), rootDir: studio, publicDir,
  outDir: path.join(output, 'bundle'), enableCaching: true });
const browserExecutable = chromium.executablePath();
const report = { status: 'in_progress', source: { path: path.relative(root, source), sha256: hash(sourceBytes) }, fontSha256: hash(fontBytes),
  sourceHashes, narrationChanged: false, newCapture: false, officialLogoIncluded: false, outputs: [] };
const request = JSON.parse(await fs.readFile(path.join(production, 'request-brand.json'), 'utf8'));
for (const theme of ['neutral_v1', 'claude_desktop_v1', 'technical_v1']) {
  const props = { schemaVersion: 1, width: 1080, height: 1920, fps: 24, durationInFrames: 504,
    clips: request.recipe.scenes.map((scene, index) => ({ src: `clip-0${index}.mp4`, startMs: scene.start_ms, endMs: scene.end_ms,
      trimBeforeFrame: Math.round(scene.start_ms * 24 / 1000), trimAfterFrame: Math.round(scene.end_ms * 24 / 1000), durationInFrames: 168,
      volumePercent: 0, layoutPreset: 'screen_explainer_v1', screenTheme: theme,
      ...(scene.focus_region ? { focusRegion: scene.focus_region } : {}), transitionToNext: null,
      overlay: { text: scene.headline, startMs: 0, endMs: 7000, startFrame: 0, endFrame: 168, position: 'top', stylePreset: 'shorts_ja_large_v1' } })) };
  const composition = await selectComposition({ serveUrl, id: 'MiniMaxH3DetailedTimelineV1', browserExecutable, inputProps: props });
  const frames = theme === 'claude_desktop_v1' ? [48, 216, 384] : [48];
  for (const frame of frames) {
    const destination = path.join(output, `${theme}-f${frame}.png`);
    await renderStill({ composition, serveUrl, inputProps: props, browserExecutable, frame, output: destination, imageFormat: 'png', overwrite: false });
    const bytes = await fs.readFile(destination);
    report.outputs.push({ theme, frame, path: path.relative(root, destination), bytes: bytes.length, sha256: hash(bytes) });
  }
}
for (const [relative, expected] of Object.entries(sourceHashes)) if (hash(await fs.readFile(path.join(root, relative))) !== expected) throw new Error('Composition source changed during preview');
if (hash(await fs.readFile(source)) !== report.source.sha256 || hash(await fs.readFile(font)) !== report.fontSha256) throw new Error('Input changed during preview');
report.status = 'succeeded';
await fs.writeFile(path.join(output, 'manifest.json'), `${JSON.stringify(report, null, 2)}\n`, { flag: 'wx' });
console.log(JSON.stringify({ output, status: report.status, figures: report.outputs }, null, 2));
