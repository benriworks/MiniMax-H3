// Scoped 30s production: existing common theme, timed source panels, real capture.
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
const { selectComposition, renderMedia, renderStill } = require('@remotion/renderer');
const { chromium } = require('playwright');
const hash = data => createHash('sha256').update(data).digest('hex').toUpperCase();
const record = async file => ({ path: path.relative(root, file).replaceAll('\\', '/'), sha256: hash(await fs.readFile(file)), bytes: (await fs.stat(file)).size });
const story = JSON.parse(await fs.readFile(path.join(folder, 'story.json'), 'utf8'));
if (story.theme !== 'claude_editorial_v1' || story.duration_ms !== 30000 || story.headlines.length !== 3) throw new Error('Story contract changed');
const output = path.join(root, 'outputs/studio/verification/editorial-30s-20260909', new Date().toISOString().replaceAll(/[^0-9TZ]/g, ''));
const publicDir = path.join(output, 'public');
await fs.mkdir(path.join(publicDir, 'template-assets'), { recursive: true });
const image = path.join(root, 'productions/SHORT_20260906_claude_illustrated/assets/writing-ideas-v1.png');
const font = path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf');
const capture = path.join(root, 'outputs/studio/claude-captures/production_18812c9ff18e4955858700ee7815f678/claude_capture_52dede446256444c9e9ed7a5a0965628/claude-capture.mp4');
const pinned = [[image, '5B656618A509E7B0060D88E2B6A17BD7753D381F159BCC973F38990075F30BD4'], [font, 'C2F3B4D463500A2DDCD3849CDED1FCEEB9FD6D1C32E6CBECD568453BA50FC68F'], [capture, 'B8B9E07B8987D824D8DD1BE0EE7DACDF9613C82406E2B53763841CA6AF01A362']];
for (const [file, sha] of pinned) if ((await record(file)).sha256 !== sha) throw new Error('Pinned input changed');
const sources = await Promise.all([fileURLToPath(import.meta.url), path.join(folder, 'Panels.tsx'), path.join(folder, 'story.json'), path.join(folder, 'finish.py'), image, font, capture,
  ...['entry.tsx', 'TimelineComposition.tsx', 'model.ts', 'screenThemes.ts', 'ScreenTypography.tsx'].map(p => path.join(studio, 'src/remotion', p)),
  ...['src/api.ts', 'src/types.ts', 'src/status.ts', 'package.json', 'package-lock.json'].map(p => path.join(studio, p))].map(record));
await fs.copyFile(image, path.join(publicDir, 'illustration.png'));
await fs.copyFile(font, path.join(publicDir, 'template-assets/NotoSansJP-Variable.ttf'));
await fs.copyFile(capture, path.join(publicDir, 'clip-01.mp4'));
const browserExecutable = chromium.executablePath();
const mediaOptions = { browserExecutable, codec: 'h264', pixelFormat: 'yuv420p', imageFormat: 'png', colorSpace: 'bt709', crf: 16, muted: true, concurrency: 2, overwrite: false };
const probe = file => JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', file], { encoding: 'utf8', windowsHide: true }));
const verify = (file, frames, width, height) => {
  const p = probe(file), v = p.streams[0];
  if (p.streams.length !== 1 || v.codec_name !== 'h264' || v.width !== width || v.height !== height || v.avg_frame_rate !== '24/1' || Number(v.nb_frames) !== frames || Number(p.format.duration) !== frames / 24) throw new Error('Media contract mismatch');
  execFileSync('ffmpeg', ['-v', 'error', '-xerror', '-i', file, '-f', 'null', '-'], { windowsHide: true });
  return p;
};
const reuseVerifiedPanels = process.argv.includes('--reuse-verified-panels');
const panelUrl = reuseVerifiedPanels ? null : await bundle({ entryPoint: path.join(folder, 'Panels.tsx'), rootDir: studio, publicDir, outDir: path.join(output, 'panel-bundle'), enableCaching: true,
  webpackOverride: config => ({ ...config, resolve: { ...config.resolve, modules: [path.join(studio, 'node_modules'), ...(config.resolve?.modules ?? [])] } }) });
const panels = [];
for (const [role, id] of [['hook', 'EditorialHook30'], ['cta', 'EditorialCta30']]) {
  const file = path.join(publicDir, role === 'hook' ? 'clip-00.mp4' : 'clip-02.mp4');
  if (reuseVerifiedPanels) {
    // Recover only the two verified panels from the first attempt; never accept arbitrary unbound media.
    const prior = path.join(root, `outputs/studio/verification/editorial-30s-20260909/20260908T191950790Z/public/${role}.mp4`);
    const expected = role === 'hook' ? '130FE982EF3DA4D96CCF0BF881402A790FCAEC4A15D85CAD81DB9AAE13841E79' : '892C28A7CD321F2AC71802D771064BFAC9C87B788A92DBB77B347395CC1C150F';
    const original = await record(prior);
    if (original.sha256 !== expected) throw new Error('Verified recovery panel changed');
    sources.push(original);
    await fs.copyFile(prior, file);
  } else {
    const composition = await selectComposition({ serveUrl: panelUrl, id, browserExecutable });
    await renderMedia({ ...mediaOptions, composition, serveUrl: panelUrl, outputLocation: file });
  }
  const facts = verify(file, 240, 1920, 1080);
  panels.push({ role, ...await record(file), probe: facts });
  console.log(JSON.stringify({ event: 'panel_complete', role }));
}
const props = { schemaVersion: 1, width: 1080, height: 1920, fps: 24, durationInFrames: 720,
  clips: ['clip-00.mp4', 'clip-01.mp4', 'clip-02.mp4'].map((src, index) => {
    const start = index === 1 ? 15000 : 0;
    return { src, startMs: start, endMs: start + 10000, trimBeforeFrame: start * 24 / 1000, trimAfterFrame: (start + 10000) * 24 / 1000,
      durationInFrames: 240, volumePercent: 0, layoutPreset: 'screen_explainer_v1', screenTheme: story.theme, transitionToNext: null,
      overlay: { text: story.headlines[index], startMs: 0, endMs: 10000, startFrame: 0, endFrame: 240, position: 'top', stylePreset: 'shorts_ja_large_v1' } };
  }) };
const serveUrl = await bundle({ entryPoint: path.join(studio, 'src/remotion/entry.tsx'), rootDir: studio, publicDir, outDir: path.join(output, 'timeline-bundle'), enableCaching: true });
const composition = await selectComposition({ serveUrl, id: 'MiniMaxH3DetailedTimelineV1', browserExecutable, inputProps: props });
for (const frame of [36, 180, 276, 420, 516, 684]) {
  await renderStill({ composition, serveUrl, browserExecutable, inputProps: props, frame, imageFormat: 'png', output: path.join(output, `design-${frame}.png`), overwrite: false });
}
console.log(JSON.stringify({ event: 'timeline_started', frames: 720 }));
const file = path.join(output, 'timeline-silent.mp4');
await renderMedia({ ...mediaOptions, composition, serveUrl, inputProps: props, outputLocation: file });
const facts = verify(file, 720, 1080, 1920);
for (const expected of sources) if ((await record(path.join(root, expected.path))).sha256 !== expected.sha256) throw new Error('Source changed during rendering');
const report = { schema_version: 1, workflow: 'production script using shared Studio components; not a saved Studio UI Run', story, sources, panels, props, timeline: await record(file), probe: facts, full_decode_verified: true, new_capture: false, new_image_generation: false };
await fs.writeFile(path.join(output, 'render.json'), JSON.stringify(report, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ event: 'render_complete', manifest: path.join(output, 'render.json') }));
