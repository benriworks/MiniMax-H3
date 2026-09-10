import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {lstat, readFile, readdir, realpath, rename, stat, writeFile} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

const SCHEMA_VERSION = 1;
const PINNED_REMOTION_VERSION = '4.0.517';
const COMPOSITION_ID = 'MiniMaxH3DetailedTimelineV1';
const MAX_REQUEST_BYTES = 4 * 1024 * 1024;
const MAX_CLIPS = 16;
const MAX_SOURCE_BYTES = 2 * 1024 * 1024 * 1024;
const packageNames = [
  'remotion',
  '@remotion/player',
  '@remotion/renderer',
  '@remotion/bundler',
  '@remotion/transitions',
];

const fail = (message) => {
  throw new Error(message);
};

const isInteger = (value, minimum, maximum) =>
  Number.isInteger(value) && value >= minimum && value <= maximum;

const halfUpFrames = (milliseconds, allowZero = false) => {
  const frames = Math.floor((milliseconds * 24 + 500) / 1000);
  return allowZero ? frames : Math.max(1, frames);
};

const assertExactKeys = (value, expected, label) => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    fail(`${label} must be an object`);
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  if (actual.length !== wanted.length || actual.some((key, index) => key !== wanted[index])) {
    fail(`${label} contains unsupported fields`);
  }
};

const validateInputProps = (inputProps) => {
  assertExactKeys(
    inputProps,
    ['schemaVersion', 'width', 'height', 'fps', 'durationInFrames', 'clips'],
    'inputProps',
  );
  if (
    inputProps.schemaVersion !== 1 ||
    inputProps.width !== 1080 ||
    inputProps.height !== 1920 ||
    inputProps.fps !== 24 ||
    !isInteger(inputProps.durationInFrames, 1, 1440) ||
    !Array.isArray(inputProps.clips) ||
    inputProps.clips.length < 1 ||
    inputProps.clips.length > MAX_CLIPS
  ) {
    fail('inputProps does not match the fixed timeline contract');
  }
  for (const [index, clip] of inputProps.clips.entries()) {
    assertExactKeys(
      clip,
      [
        'src',
        'startMs',
        'endMs',
        'trimBeforeFrame',
        'trimAfterFrame',
        'durationInFrames',
        'volumePercent',
        'transitionToNext',
        'overlay',
        ...(Object.hasOwn(clip, 'layoutPreset') ? ['layoutPreset'] : []),
        ...(Object.hasOwn(clip, 'screenTheme') ? ['screenTheme'] : []),
        ...(Object.hasOwn(clip, 'focusRegion') ? ['focusRegion'] : []),
      ],
      `clips[${index}]`,
    );
    if (Object.hasOwn(clip, 'layoutPreset') && !['full_bleed_v1', 'screen_explainer_v1'].includes(clip.layoutPreset)) {
      fail(`clips[${index}].layoutPreset is invalid`);
    }
    if (Object.hasOwn(clip, 'screenTheme') && (clip.layoutPreset !== 'screen_explainer_v1'
      || !['neutral_v1', 'claude_desktop_v1', 'claude_code_v1', 'technical_v1', 'claude_editorial_v1'].includes(clip.screenTheme))) {
      fail(`clips[${index}].screenTheme is invalid`);
    }
    if (Object.hasOwn(clip, 'focusRegion')) {
      assertExactKeys(clip.focusRegion, ['x', 'y', 'width', 'height'], `clips[${index}].focusRegion`);
      const focus = clip.focusRegion;
      if (clip.layoutPreset !== 'screen_explainer_v1'
        || Object.values(focus).some((value) => typeof value !== 'number' || !Number.isFinite(value) || value < 0 || value > 1 || Math.round(value * 10_000) / 10_000 !== value)
        || focus.width < 0.2 || focus.height < 0.2 || focus.x + focus.width > 1 || focus.y + focus.height > 1) {
        fail(`clips[${index}].focusRegion is invalid`);
      }
    }
    if (
      clip.src !== `clip-${String(index).padStart(2, '0')}.mp4` ||
      !isInteger(clip.startMs, 0, 60000) ||
      !isInteger(clip.endMs, 1, 60000) ||
      clip.endMs <= clip.startMs ||
      clip.endMs - clip.startMs < 50 ||
      !isInteger(clip.trimBeforeFrame, 0, 1440) ||
      !isInteger(clip.trimAfterFrame, 1, 1440) ||
      !isInteger(clip.durationInFrames, 1, 1440) ||
      !isInteger(clip.volumePercent, 0, 100)
    ) {
      fail(`clips[${index}] is invalid`);
    }
    const expectedDuration = halfUpFrames(clip.endMs - clip.startMs);
    if (
      clip.durationInFrames !== expectedDuration ||
      clip.trimBeforeFrame !== halfUpFrames(clip.startMs, true) ||
      clip.trimAfterFrame !== halfUpFrames(clip.endMs, true)
    ) {
      fail(`clips[${index}] timing is inconsistent`);
    }
    if (index === inputProps.clips.length - 1 && clip.transitionToNext !== null) {
      fail('the final clip must not define a transition');
    }
    if (clip.transitionToNext !== null) {
      assertExactKeys(
        clip.transitionToNext,
        ['type', 'durationMs', 'durationInFrames'],
        `clips[${index}].transitionToNext`,
      );
      if (
        clip.transitionToNext.type !== 'fade' ||
        !isInteger(clip.transitionToNext.durationMs, 50, 2000) ||
        !isInteger(clip.transitionToNext.durationInFrames, 1, 48) ||
        clip.transitionToNext.durationInFrames !== halfUpFrames(clip.transitionToNext.durationMs)
      ) {
        fail(`clips[${index}].transitionToNext is invalid`);
      }
    }
    if (clip.overlay !== null) {
      assertExactKeys(
        clip.overlay,
        [
          'text',
          'startMs',
          'endMs',
          'startFrame',
          'endFrame',
          'position',
          'stylePreset',
        ],
        `clips[${index}].overlay`,
      );
      if (
        typeof clip.overlay.text !== 'string' ||
        !clip.overlay.text.trim() ||
        Array.from(clip.overlay.text).length > 200 ||
        /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u.test(clip.overlay.text) ||
        clip.overlay.text.split(/\r\n|[\n\r\u0085\u2028\u2029]/u).length > 4 ||
        !isInteger(clip.overlay.startMs, 0, 60000) ||
        !isInteger(clip.overlay.endMs, 1, 60000) ||
        clip.overlay.endMs - clip.overlay.startMs < 50 ||
        clip.overlay.endMs > clip.endMs - clip.startMs ||
        !isInteger(clip.overlay.startFrame, 0, 1439) ||
        !isInteger(clip.overlay.endFrame, 1, 1440) ||
        clip.overlay.endFrame <= clip.overlay.startFrame ||
        !['top', 'center', 'bottom'].includes(clip.overlay.position) ||
        clip.overlay.stylePreset !== 'shorts_ja_large_v1'
      ) {
        fail(`clips[${index}].overlay is invalid`);
      }
      const expectedStartFrame = Math.min(
        clip.durationInFrames - 1,
        halfUpFrames(clip.overlay.startMs, true),
      );
      const expectedEndFrame = Math.min(
        clip.durationInFrames,
        Math.max(expectedStartFrame + 1, halfUpFrames(clip.overlay.endMs, true)),
      );
      if (
        clip.overlay.startFrame !== expectedStartFrame ||
        clip.overlay.endFrame !== expectedEndFrame
      ) {
        fail(`clips[${index}].overlay timing is inconsistent`);
      }
    }
  }
  let expectedTotal = 0;
  for (const [index, clip] of inputProps.clips.entries()) {
    expectedTotal += clip.durationInFrames;
    if (clip.transitionToNext !== null) {
      const next = inputProps.clips[index + 1];
      if (
        clip.transitionToNext.durationInFrames >= clip.durationInFrames ||
        clip.transitionToNext.durationInFrames >= next.durationInFrames
      ) {
        fail(`clips[${index}].transitionToNext is too long`);
      }
      expectedTotal -= clip.transitionToNext.durationInFrames;
    }
  }
  if (inputProps.durationInFrames !== expectedTotal) {
    fail('inputProps duration is inconsistent');
  }
};

if (process.argv.length !== 4) {
  fail('usage: remotion_render.mjs <request.json> <result.json>');
}
const requestPath = path.resolve(process.argv[2]);
const resultPath = path.resolve(process.argv[3]);
const workingDirectory = await realpath(process.cwd());
if (
  requestPath !== path.join(workingDirectory, 'render-request.json') ||
  resultPath !== path.join(workingDirectory, 'render-result.json')
) {
  fail('request and result paths must use the fixed work directory');
}
const requestLstat = await lstat(requestPath);
if (requestLstat.isSymbolicLink()) fail('request file must not be a symlink');
const requestStat = await stat(requestPath);
if (!requestStat.isFile() || requestStat.size < 1 || requestStat.size > MAX_REQUEST_BYTES) {
  fail('request file is invalid');
}
const request = JSON.parse(await readFile(requestPath, 'utf8'));
assertExactKeys(
  request,
  [
    'schema_version',
    'composition_id',
    'entry_point',
    'public_dir',
    'browser_executable',
    'output_path',
    'scratch_directory',
    'input_props',
  ],
  'request',
);
if (request.schema_version !== SCHEMA_VERSION || request.composition_id !== COMPOSITION_ID) {
  fail('request contract is unsupported');
}
for (const key of ['entry_point', 'public_dir', 'browser_executable', 'output_path', 'scratch_directory']) {
  if (typeof request[key] !== 'string' || request[key].length < 1 || request[key].length > 2048) {
    fail(`${key} is invalid`);
  }
}
validateInputProps(request.input_props);

const studioPackage = new URL('../../studio/package.json', import.meta.url);
const requireFromStudio = createRequire(studioPackage);
const expectedEntryPoint = path.resolve(
  fileURLToPath(new URL('../../studio/src/remotion/entry.tsx', import.meta.url)),
);
const expectedPublicDirectory = path.join(workingDirectory, 'public');
const expectedOutputPath = path.join(workingDirectory, 'remotion-raw.mp4');
const expectedScratchDirectory = path.join(workingDirectory, 'scratch');
const {chromium} = requireFromStudio('playwright');
const expectedBrowser = path.resolve(chromium.executablePath());
if (
  path.resolve(request.entry_point) !== expectedEntryPoint ||
  path.resolve(request.public_dir) !== expectedPublicDirectory ||
  path.resolve(request.output_path) !== expectedOutputPath ||
  path.resolve(request.scratch_directory) !== expectedScratchDirectory ||
  path.resolve(request.browser_executable) !== expectedBrowser
) {
  fail('request paths do not match the fixed renderer contract');
}
const scratchInfo = await lstat(expectedScratchDirectory);
if (scratchInfo.isSymbolicLink() || !scratchInfo.isDirectory()) {
  fail('scratch directory is invalid');
}
const resolvedScratchDirectory = await realpath(expectedScratchDirectory);
if (
  resolvedScratchDirectory !== expectedScratchDirectory ||
  (await readdir(expectedScratchDirectory)).length !== 0
) {
  fail('scratch directory is invalid');
}
for (const name of ['TEMP', 'TMP', 'TMPDIR']) {
  if (
    typeof process.env[name] !== 'string' ||
    path.resolve(process.env[name]) !== expectedScratchDirectory
  ) {
    fail('scratch environment is invalid');
  }
}
if (path.resolve(os.tmpdir()) !== expectedScratchDirectory) {
  fail('effective scratch directory is invalid');
}
for (const [label, filename] of [
  ['entry point', expectedEntryPoint],
  ['public directory', expectedPublicDirectory],
  ['browser executable', expectedBrowser],
]) {
  const info = await lstat(filename);
  if (info.isSymbolicLink() || (label === 'public directory' ? !info.isDirectory() : !info.isFile())) {
    fail(`${label} is invalid`);
  }
}
for (const [index] of request.input_props.clips.entries()) {
  const source = path.join(expectedPublicDirectory, `clip-${String(index).padStart(2, '0')}.mp4`);
  const info = await lstat(source);
  if (info.isSymbolicLink() || !info.isFile() || info.size < 1 || info.size > MAX_SOURCE_BYTES) {
    fail(`clips[${index}] source file is invalid`);
  }
  const resolvedSource = await realpath(source);
  if (!resolvedSource.startsWith(`${expectedPublicDirectory}${path.sep}`)) {
    fail(`clips[${index}] source escapes the public directory`);
  }
}
const needsScreenFont = request.input_props.clips.some((clip) => clip.layoutPreset === 'screen_explainer_v1');
const publicNames = await readdir(expectedPublicDirectory);
const expectedPublicNames = request.input_props.clips.map((_, index) => `clip-${String(index).padStart(2, '0')}.mp4`);
if (needsScreenFont) expectedPublicNames.push('template-assets');
if (publicNames.sort().join('\n') !== expectedPublicNames.sort().join('\n')) fail('public asset set is invalid');
if (needsScreenFont) {
  const assetDirectory = path.join(expectedPublicDirectory, 'template-assets');
  const fontName = 'NotoSansJP-Variable.ttf';
  const stagedFont = path.join(assetDirectory, fontName);
  const sourceFont = fileURLToPath(new URL(`../../studio/public/template-assets/${fontName}`, import.meta.url));
  const directoryInfo = await lstat(assetDirectory);
  if (directoryInfo.isSymbolicLink() || !directoryInfo.isDirectory()
    || (await readdir(assetDirectory)).join('\n') !== fontName) fail('template assets are invalid');
  for (const filename of [stagedFont, sourceFont]) {
    const info = await lstat(filename);
    if (info.isSymbolicLink() || !info.isFile() || info.size < 1 || info.size > 32 * 1024 * 1024
      || await realpath(filename) !== filename) fail('template font is invalid');
  }
  const digest = (bytes) => createHash('sha256').update(bytes).digest('hex');
  if (digest(await readFile(stagedFont)) !== digest(await readFile(sourceFont))) fail('template font identity differs');
}
const versions = {};
for (const name of packageNames) {
  const packageJson = requireFromStudio(`${name}/package.json`);
  if (packageJson.version !== PINNED_REMOTION_VERSION) {
    fail(`${name} must be pinned to ${PINNED_REMOTION_VERSION}`);
  }
  versions[name] = packageJson.version;
}
const {bundle} = requireFromStudio('@remotion/bundler');
const {makeCancelSignal, renderMedia, selectComposition} = requireFromStudio('@remotion/renderer');

const {cancel, cancelSignal} = makeCancelSignal();
let stopping = false;
const stop = () => {
  if (!stopping) {
    stopping = true;
    cancel();
  }
};
process.once('SIGINT', stop);
process.once('SIGTERM', stop);

let maxProgress = 0;
const bundleDirectory = path.join(workingDirectory, 'bundle');
try {
  await lstat(bundleDirectory);
  fail('bundle directory must not already exist');
} catch (error) {
  if (error?.code !== 'ENOENT') throw error;
}
const serveUrl = await bundle({
  entryPoint: path.resolve(request.entry_point),
  publicDir: path.resolve(request.public_dir),
  outDir: bundleDirectory,
  enableCaching: false,
  onProgress: (progress) => {
    if (Number.isFinite(progress)) maxProgress = Math.max(maxProgress, Math.min(1, progress));
  },
});
if (path.resolve(serveUrl) !== bundleDirectory) {
  fail('bundler returned an unexpected directory');
}
const composition = await selectComposition({
  serveUrl,
  id: COMPOSITION_ID,
  inputProps: request.input_props,
  browserExecutable: path.resolve(request.browser_executable),
  chromeMode: 'chrome-for-testing',
  timeoutInMilliseconds: 30_000,
});
if (
  composition.width !== 1080 ||
  composition.height !== 1920 ||
  composition.fps !== 24 ||
  composition.durationInFrames !== request.input_props.durationInFrames
) {
  fail('composition metadata does not match the request');
}

await renderMedia({
  serveUrl,
  composition,
  inputProps: request.input_props,
  outputLocation: path.resolve(request.output_path),
  browserExecutable: path.resolve(request.browser_executable),
  chromeMode: 'chrome-for-testing',
  codec: 'h264',
  audioCodec: 'aac',
  imageFormat: 'png',
  crf: 16,
  pixelFormat: 'yuv420p',
  sampleRate: 48000,
  enforceAudioTrack: true,
  concurrency: 1,
  disallowParallelEncoding: true,
  hardwareAcceleration: 'disable',
  overwrite: false,
  x264Preset: 'medium',
  envVariables: {},
  cancelSignal,
  mediaCacheSizeInBytes: 128 * 1024 * 1024,
  offthreadVideoCacheSizeInBytes: 512 * 1024 * 1024,
  offthreadVideoThreads: 1,
  onBrowserDownload: () => fail('browser download is disabled'),
  onProgress: ({progress}) => {
    if (Number.isFinite(progress)) maxProgress = Math.max(maxProgress, Math.min(1, progress));
  },
});

const result = {
  schema_version: SCHEMA_VERSION,
  composition_id: COMPOSITION_ID,
  duration_in_frames: composition.durationInFrames,
  clip_count: request.input_props.clips.length,
  transition_count: request.input_props.clips.filter((clip) => clip.transitionToNext !== null).length,
  overlay_count: request.input_props.clips.filter((clip) => clip.overlay !== null).length,
  remotion_packages: versions,
  concurrency: 1,
  disallow_parallel_encoding: true,
  silent_audio_fallback: true,
  image_format: 'png',
  video_crf: 16,
  x264_preset: 'medium',
  scratch_directory_attested: true,
  max_progress_percent: Math.round(maxProgress * 100),
};
const temporaryResultPath = `${resultPath}.partial`;
await writeFile(temporaryResultPath, `${JSON.stringify(result)}\n`, {encoding: 'utf8', flag: 'wx'});
await rename(temporaryResultPath, resultPath);
