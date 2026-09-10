import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';

const productionDir = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(productionDir, '../..');
const studioRoot = path.join(projectRoot, 'studio');
const requireStudio = createRequire(path.join(studioRoot, 'package.json'));
const { bundle } = requireStudio('@remotion/bundler');
const { selectComposition, renderStill, renderMedia } = requireStudio('@remotion/renderer');
const { chromium } = requireStudio('playwright');
const browserExecutable = chromium.executablePath();
const outputBase = path.join(projectRoot, 'outputs/productions/SHORT_20260905_claude_desktop_15s');
const outputDir = path.join(outputBase, 'sources');
const assetsDir = path.join(outputBase, 'assets');
const photoPath = path.join(assetsDir, 'desktop-hero.png');
const mode = process.argv[2] ?? '--stills';
if (!['--stills', '--videos'].includes(mode)) throw new Error('Usage: node render.mjs --stills | --videos');
// The generated photograph is a required source, never silently replaced by a placeholder.
const photo = await fs.readFile(photoPath).catch(() => { throw new Error(`Required generated hero image is missing: ${photoPath}`); });
if (photo.length < 1000 || !photo.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))) throw new Error('desktop-hero.png must be a nonempty PNG photograph');
const sha256 = (value) => createHash('sha256').update(value).digest('hex').toUpperCase();
const photoSha256 = sha256(photo);
await fs.access(browserExecutable);
await fs.mkdir(outputDir, { recursive: true });
const serveUrl = await bundle({
  entryPoint: path.join(productionDir, 'ClaudeDesktopShort.tsx'), outDir: path.join(outputDir, '_bundle'), rootDir: studioRoot,
  publicDir: assetsDir, enableCaching: true,
  webpackOverride: (configuration) => ({ ...configuration, resolve: { ...configuration.resolve,
    modules: [path.join(studioRoot, 'node_modules'), ...(configuration.resolve?.modules ?? [])],
    alias: { ...configuration.resolve?.alias, 'react$': requireStudio.resolve('react'), 'react/jsx-runtime$': requireStudio.resolve('react/jsx-runtime'), 'react-dom$': requireStudio.resolve('react-dom'), 'remotion$': requireStudio.resolve('remotion') },
  } }),
});
const sourceSha256 = sha256(await fs.readFile(path.join(productionDir, 'ClaudeDesktopShort.tsx')));
const scenes = [
  { id: 'ClaudeDesktop', name: 'cut_01_desktop', frame: 105, frames: 126 },
  { id: 'ClaudeFolder', name: 'cut_02_folder', frame: 112, frames: 126 },
  { id: 'ClaudeReview', name: 'cut_03_review', frame: 109, frames: 120 },
];
const report = { production_id: 'SHORT_20260905_claude_desktop_15s', created_at: new Date().toISOString(), width: 1080, height: 1920, fps: 24, mode,
  browser_executable: browserExecutable, remotion_version: requireStudio('@remotion/renderer/package.json').version,
  composition_sha256: sourceSha256, generated_photo: { path: photoPath, bytes: photo.length, sha256: photoSha256 }, sources: [] };
for (const scene of scenes) {
  const composition = await selectComposition({ serveUrl, id: scene.id, browserExecutable });
  if (composition.width !== 1080 || composition.height !== 1920 || composition.fps !== 24 || composition.durationInFrames !== scene.frames) throw new Error('Unexpected composition contract');
  const output = path.join(outputDir, `${scene.name}${mode === '--stills' ? `.f${scene.frame}.png` : '.mp4'}`);
  const began = Date.now();
  console.log(`Rendering ${scene.id} ${mode}`);
  if (mode === '--stills') {
    await renderStill({ composition, serveUrl, output, frame: scene.frame, imageFormat: 'png', browserExecutable, overwrite: true });
  } else {
    let lastMilestone = -1;
    await renderMedia({ composition, serveUrl, outputLocation: output, codec: 'h264', crf: 16, x264Preset: 'medium', pixelFormat: 'yuv420p', imageFormat: 'png', browserExecutable, concurrency: 2, muted: true, enforceAudioTrack: false, overwrite: true,
      onProgress: ({ progress }) => { const milestone = Math.floor(progress * 4); if (milestone > lastMilestone) { lastMilestone = milestone; console.log(`${scene.id}: ${Math.min(100, milestone * 25)}%`); } },
    });
  }
  const content = await fs.readFile(output);
  report.sources.push({ composition_id: scene.id, output, frames: scene.frames, duration_seconds: scene.frames / 24, bytes: content.length, sha256: sha256(content), elapsed_seconds: (Date.now() - began) / 1000 });
  console.log(`Saved ${output}`);
}
if (sha256(await fs.readFile(photoPath)) !== photoSha256) throw new Error('Generated image changed while rendering');
await fs.writeFile(path.join(outputDir, mode === '--stills' ? 'stills-report.json' : 'sources-report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
