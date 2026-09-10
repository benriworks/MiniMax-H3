// Render only original editorial source clips. Ordinary Studio owns final
// assembly, narration reuse, saved recipe, Run/Job lineage, QC and delivery.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const production = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(production, '../..');
const studio = path.join(root, 'studio');
const requireStudio = createRequire(path.join(studio, 'package.json'));
const { bundle } = requireStudio('@remotion/bundler');
const { selectComposition, renderStill, renderMedia } = requireStudio('@remotion/renderer');
const { chromium } = requireStudio('playwright');
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex').toUpperCase();
const record = async (role, file) => {
  const bytes = await fs.readFile(file);
  return { role, path: path.relative(root, file).replaceAll('\\', '/'), bytes: bytes.length, sha256: hash(bytes) };
};
const image = path.join(production, 'assets/writing-ideas-v1.png');
const font = path.join(studio, 'public/template-assets/NotoSansJP-Variable.ttf');
const files = await Promise.all([
  record('illustration', image), record('renderer', fileURLToPath(import.meta.url)),
  ...[path.join(production, 'entry.tsx'), path.join(production, 'PanelComposition.tsx'),
    path.join(studio, 'src/remotion/ScreenTypography.tsx'), path.join(studio, 'package.json'), path.join(studio, 'package-lock.json'), font]
    .map(file => record('renderer_dependency', file)),
]);
if (files[0].sha256 !== '5B656618A509E7B0060D88E2B6A17BD7753D381F159BCC973F38990075F30BD4') throw new Error('Illustration changed');
if (files.at(-1).sha256 !== 'C2F3B4D463500A2DDCD3849CDED1FCEEB9FD6D1C32E6CBECD568453BA50FC68F') throw new Error('Font changed');
const output = path.join(root, 'outputs/studio/verification/claude-illustrated-20260906/panels', new Date().toISOString().replaceAll(/[^0-9TZ]/g, ''));
const publicDir = path.join(output, 'public');
await fs.mkdir(path.join(publicDir, 'template-assets'), { recursive: true });
await fs.copyFile(image, path.join(publicDir, 'writing-ideas-v1.png'));
await fs.copyFile(font, path.join(publicDir, 'template-assets/NotoSansJP-Variable.ttf'));
const serveUrl = await bundle({ entryPoint: path.join(production, 'entry.tsx'), rootDir: studio, publicDir, outDir: path.join(output, 'bundle'), enableCaching: true,
  webpackOverride: config => ({ ...config, resolve: { ...config.resolve, modules: [path.join(studio, 'node_modules'), ...(config.resolve?.modules ?? [])] } }) });
const browserExecutable = chromium.executablePath();
const panels = [];
for (const [role, id] of [['hook', 'IllustratedHook'], ['cta', 'EditorialChecklist']]) {
  const composition = await selectComposition({ serveUrl, id, browserExecutable });
  await renderStill({ composition, serveUrl, browserExecutable, frame: 96, output: path.join(output, `${role}-f96.png`), imageFormat: 'png', overwrite: false });
  const destination = path.join(output, `${role}.mp4`);
  await renderMedia({ composition, serveUrl, browserExecutable, codec: 'h264', crf: 16, pixelFormat: 'yuv420p', imageFormat: 'png', colorSpace: 'bt709',
    muted: true, outputLocation: destination, concurrency: 2, overwrite: false });
  const probe = JSON.parse(execFileSync('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', destination], { encoding: 'utf8', windowsHide: true }));
  const videos = probe.streams.filter(stream => stream.codec_type === 'video');
  if (probe.streams.length !== 1 || videos.length !== 1 || videos[0].width !== 1920 || videos[0].height !== 1080 || videos[0].avg_frame_rate !== '24/1' || videos[0].nb_frames !== '168' || Number(probe.format.duration) !== 7) throw new Error('Panel format mismatch');
  execFileSync('ffmpeg', ['-v', 'error', '-xerror', '-i', destination, '-f', 'null', '-'], { windowsHide: true });
  await fs.writeFile(path.join(output, `${role}-ffprobe.json`), `${JSON.stringify(probe, null, 2)}\n`, { flag: 'wx' });
  panels.push(await record(role, destination));
  console.log(JSON.stringify({ event: 'panel_complete', role, path: destination }));
}
for (const expected of files) {
  const actual = await record(expected.role, path.join(root, expected.path));
  if (actual.sha256 !== expected.sha256 || actual.bytes !== expected.bytes) throw new Error('Bound input changed while rendering');
}
const original = JSON.parse(await fs.readFile(path.join(production, '../SHORT_20260906_claude_desktop_real_capture/request-brand.json'), 'utf8'));
const recipe = original.recipe;
recipe.name = 'Claude Desktop：イラストと実画面で、告知文を３案';
for (const index of [0, 2]) {
  recipe.scenes[index].video_artifact_id = 'art_00000000000000000000000000000000';
  recipe.scenes[index].start_ms = 0;
  recipe.scenes[index].end_ms = 7000;
  delete recipe.scenes[index].focus_region;
}
// Use the actual whole application window, not the unreadable narrow text band.
delete recipe.scenes[1].focus_region;
recipe.scenes[0].headline = 'Claude Desktop\n条件を添えて、３案';
recipe.scenes[1].headline = '３つの候補から\n使う表現を選ぶ';
recipe.scenes[2].headline = '仕上げるのは\nあなたの判断';
const metadata = {
  title: 'Claude Desktopで文章づくり｜条件を添える・選ぶ・確認する',
  description: 'Claude Desktopの通常チャットを題材にした、21秒の非公式解説です。\n\n0:00 条件を添えて、告知文を3案（AI生成の独自コンセプトイラスト）\n0:07 候補から表現を選ぶ（既存のClaude Desktop実画面。回答3の表示区間）\n0:14 日付と文字数を確認（編集で作った確認ポイント図解）\n\n架空カフェ「こもれび珈琲」を例にしています。9月20日・40字以内は依頼した条件であり、回答の正しさ・条件遵守を保証する表示ではありません。実際の出店告知ではありません。\n\n通常チャットの実画面であり、Claude Codeの実演ではありません。回答取得後に収録した素材を再利用しています。思考中の画面や3案の一覧表示は追加収録していません。UI文字の差し替えやAIによる画面生成は行っていません。イラストは実際の製品UIではありません。\n\n画：Codex内蔵画像生成で制作した独自イラスト。編集：Studio／Remotion／FFmpeg。日本語見出し：Noto Sans JP（OFL 1.1）。ナレーション：前版のWindows SAPI Microsoft Sayakaを再利用。音質改善は保留中で、公開品質は未受入。BGMなし。ロゴ・マスコット・公式ブランド素材は使っていません。Anthropicの提供・協賛ではない非公式解説です。\n\n#Claude #ClaudeDesktop #生成AI',
};
const manifest = { schema_version: 1, policy: 'claude-illustrated-inputs-v1', files, panels, recipe, metadata };
await fs.writeFile(path.join(output, 'manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`, { flag: 'wx' });
console.log(JSON.stringify({ event: 'panels_complete', manifest: path.join(output, 'manifest.json') }));
