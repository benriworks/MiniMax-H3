import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const appSource = await readFile(join(studioRoot, 'src', 'App.tsx'), 'utf8');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const apiModuleSource = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const apiUrl = `data:text/javascript;base64,${Buffer.from(apiModuleSource).toString('base64')}`;
const api = await import(apiUrl);
const modelSource = await readFile(join(testDist, 'remotion', 'model.js'), 'utf8');
const modelModuleSource = modelSource.replaceAll("from '../api'", `from '${apiUrl}'`);
const model = await import(`data:text/javascript;base64,${Buffer.from(modelModuleSource).toString('base64')}`);

const ARTIFACT_A = `art_${'a'.repeat(32)}`;
const ARTIFACT_B = `art_${'b'.repeat(32)}`;

const overlay = (overrides = {}) => ({
  text: '生成AIを\nマスターしよう',
  startMs: 100,
  endMs: 1_900,
  position: 'bottom',
  stylePreset: 'shorts_ja_large_v1',
  ...overrides,
});

const clip = (overrides = {}) => ({
  videoArtifactId: ARTIFACT_A,
  startMs: 125,
  endMs: 2_125,
  volumePercent: 50,
  transitionToNext: null,
  overlay: null,
  ...overrides,
});

test('Remotion timeline payload is closed, canonical, and schema_version=1', () => {
  const value = {
    schemaVersion: 1,
    clips: [
      clip({
        transitionToNext: { type: 'fade', durationMs: 500, easing: 'unsafe' },
        overlay: overlay({ text: '  生成AIを\r\nマスターしよう  ', css: 'unsafe' }),
        arbitraryFilter: 'unsafe',
      }),
      clip({
        videoArtifactId: ARTIFACT_B,
        startMs: 0,
        endMs: 1_000,
        volumePercent: 100,
      }),
    ],
    outputPath: 'unsafe.mp4',
  };
  const normalized = api.normalizeLocalRemotionTimelineInput(value);
  assert.deepEqual(normalized.errors, []);
  assert.equal(normalized.outputDurationMs, 2_500);
  assert.equal(normalized.durationInFrames, 60);
  assert.deepEqual(api.buildLocalRemotionTimelinePayload(value), {
    schema_version: 1,
    clips: [
      {
        video_artifact_id: ARTIFACT_A,
        start_ms: 125,
        end_ms: 2_125,
        volume_percent: 50,
        transition_to_next: { type: 'fade', duration_ms: 500 },
        overlay: {
          text: '生成AIを\nマスターしよう',
          start_ms: 100,
          end_ms: 1_900,
          position: 'bottom',
          style_preset: 'shorts_ja_large_v1',
        },
      },
      {
        video_artifact_id: ARTIFACT_B,
        start_ms: 0,
        end_ms: 1_000,
        volume_percent: 100,
        transition_to_next: null,
        overlay: null,
      },
    ],
  });
  assert.deepEqual(Object.keys(normalized.payload), ['schema_version', 'clips']);
  assert.deepEqual(Object.keys(normalized.payload.clips[0]), [
    'video_artifact_id', 'start_ms', 'end_ms', 'volume_percent', 'transition_to_next', 'overlay',
  ]);
});

test('Remotion timeline enforces clip count, output duration, volume, and final transition', () => {
  const tooMany = api.normalizeRemotionTimelineInput({
    clips: Array.from({ length: 17 }, (_, index) => clip({
      videoArtifactId: `art_${index.toString(16).padStart(32, '0')}`,
      startMs: 0,
      endMs: 50,
      volumePercent: 100,
    })),
  });
  assert.ok(tooMany.errors.some((error) => error.includes('16件以内')));

  const tooLong = api.normalizeRemotionTimelineInput({
    clips: [clip({ startMs: 0, endMs: 60_001, volumePercent: 100 })],
  });
  assert.ok(tooLong.errors.some((error) => error.includes('60秒以内')));

  for (const volumePercent of [-1, 10.5, 101]) {
    const result = api.normalizeRemotionTimelineInput({ clips: [clip({ volumePercent })] });
    assert.ok(result.errors.some((error) => error.includes('0〜100')));
  }
  const finalFade = api.normalizeRemotionTimelineInput({
    clips: [clip({ transitionToNext: { type: 'fade', durationMs: 100 } })],
  });
  assert.ok(finalFade.errors.some((error) => error.includes('最終カット')));
  assert.throws(() => api.buildRemotionTimelinePayload({ schema_version: 2, clips: [clip()] }), /schema_version/);
});

test('Remotion timeline accepts only bounded fade transitions fitting both adjacent clips', () => {
  const request = (transitionToNext, nextDuration = 1_000) => ({
    clips: [
      clip({ startMs: 0, endMs: 1_000, volumePercent: 100, transitionToNext }),
      clip({ videoArtifactId: ARTIFACT_B, startMs: 0, endMs: nextDuration, volumePercent: 100 }),
    ],
  });
  assert.ok(api.normalizeRemotionTimelineInput(request({ type: 'wipe', durationMs: 100 })).errors.some((error) => error.includes('fadeだけ')));
  assert.ok(api.normalizeRemotionTimelineInput(request({ type: 'fade', durationMs: 49 })).errors.some((error) => error.includes('50〜2000')));
  assert.ok(api.normalizeRemotionTimelineInput(request({ type: 'fade', durationMs: 2_001 })).errors.some((error) => error.includes('50〜2000')));
  assert.ok(api.normalizeRemotionTimelineInput(request({ type: 'fade', durationMs: 800 }, 500)).errors.some((error) => error.includes('次のカット尺')));
  assert.ok(api.normalizeRemotionTimelineInput(request({ type: 'fade', durationMs: 500 }, 500)).errors.some((error) => error.includes('次のカット尺')));
  assert.deepEqual(api.normalizeRemotionTimelineInput(request({ type: 'fade', durationMs: 450 }, 500)).errors, []);
});

test('Remotion text overlays are bounded, relative to a clip, and use a closed preset', () => {
  const errorsFor = (value) => api.normalizeRemotionTimelineInput({ clips: [clip({ overlay: value })] }).errors;
  assert.ok(errorsFor(overlay({ text: '' })).some((error) => error.includes('1〜200文字')));
  assert.ok(errorsFor(overlay({ text: '文'.repeat(201) })).some((error) => error.includes('1〜200文字')));
  assert.ok(errorsFor(overlay({ text: '1\n2\n3\n4\n5' })).some((error) => error.includes('4行以内')));
  assert.ok(errorsFor(overlay({ text: 'bad\u0001text' })).some((error) => error.includes('制御文字')));
  assert.ok(errorsFor(overlay({ startMs: 100, endMs: 149 })).some((error) => error.includes('50ms以上')));
  assert.ok(errorsFor(overlay({ endMs: 2_001 })).some((error) => error.includes('カット尺以内')));
  assert.ok(errorsFor(overlay({ position: 'left' })).some((error) => error.includes('top、center、bottom')));
  assert.ok(errorsFor(overlay({ stylePreset: 'custom' })).some((error) => error.includes('shorts_ja_large_v1')));
});

test('frame compilation uses integer half-up and mirrors independent trim and overlay boundaries', () => {
  assert.equal(api.millisecondsToFramesHalfUp(20), 0);
  assert.equal(api.millisecondsToFramesHalfUp(21), 1);
  assert.equal(api.millisecondsToFramesHalfUp(62), 1);
  assert.equal(api.millisecondsToFramesHalfUp(63), 2);
  assert.equal(api.millisecondsToFramesHalfUp(500), 12);
  assert.throws(() => api.millisecondsToFramesHalfUp(-1), /non-negative/);

  const request = {
    clips: [clip({
      startMs: 20,
      endMs: 1_020,
      volumePercent: 75,
      overlay: overlay({ startMs: 20, endMs: 70 }),
    })],
  };
  const props = model.buildRemotionTimelineCompositionProps(request, () => `/api/artifacts/${ARTIFACT_A}/file`);
  assert.equal(props.durationInFrames, 24);
  assert.equal(props.clips[0].trimBeforeFrame, 0);
  assert.equal(props.clips[0].trimAfterFrame, 24);
  assert.equal(props.clips[0].overlay.startFrame, 0);
  assert.equal(props.clips[0].overlay.endFrame, 2);
  assert.equal(model.assertRemotionTimelineCompositionProps(props), props);
  assert.throws(
    () => model.assertRemotionTimelineCompositionProps({ ...props, durationInFrames: 25 }),
    /duration/,
  );
});

test('Remotion job matcher excludes legacy timeline jobs and scopes run and attempt', () => {
  const selection = { runId: 'run-1', stageAttemptId: 'attempt-1' };
  assert.equal(api.isRemotionTimelineJobForSelection({
    type: 'remotion_timeline',
    stage: 'timeline',
    run_id: 'run-1',
    stage_attempt_id: 'attempt-1',
  }, selection), true);
  assert.equal(api.isRemotionTimelineJobForSelection({
    type: 'worker',
    stage: 'timeline',
    provider: 'local_remotion_timeline',
    run_id: 'run-1',
    stage_attempt_id: 'attempt-1',
  }, selection), true);
  assert.equal(api.isRemotionTimelineJobForSelection({
    type: 'local_timeline', stage: 'timeline', run_id: 'run-1', stage_attempt_id: 'attempt-1',
  }, selection), false);
  assert.equal(api.isRemotionTimelineJobForSelection({
    type: 'remotion_timeline', stage: 'timeline', run_id: 'run-2', stage_attempt_id: 'attempt-1',
  }, selection), false);
});

test('legacy timeline matcher excludes Remotion jobs even when their stage is timeline', () => {
  const selection = { runId: 'run_123', stageAttemptId: 'attempt_123' };
  assert.equal(api.isLocalTimelineJobForSelection({
    run_id: 'run_123',
    stage: 'timeline',
    stage_attempt_id: 'attempt_123',
    type: 'local_remotion_timeline',
    provider: 'local_remotion_timeline',
  }, selection), false);
  assert.equal(api.isLocalTimelineJobForSelection({
    run_id: 'run_123',
    stage: 'timeline',
    stage_attempt_id: 'attempt_123',
    type: 'local_timeline',
    provider: 'local_ffmpeg_timeline',
  }, selection), true);
});

test('executeRemotionTimeline posts only the canonical body to the sibling endpoint', async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url, init, body: JSON.parse(String(init.body)) };
    return new Response(JSON.stringify({
      id: 'job-remotion', type: 'remotion_timeline', stage: 'timeline', status: 'pending',
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    const request = { clips: [clip()] };
    const job = await api.api.executeRemotionTimeline('run/a', request);
    assert.equal(job.id, 'job-remotion');
    assert.equal(captured.url, '/api/runs/run%2Fa/execute-remotion-timeline');
    assert.equal(captured.init.method, 'POST');
    assert.deepEqual(captured.body, api.buildRemotionTimelinePayload(request));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('legacy hard-cut payload remains clips-only and ignores detailed fields', () => {
  const payload = api.buildLocalTimelinePayload({
    clips: [clip({ transitionToNext: { type: 'fade', durationMs: 500 }, overlay: overlay() })],
  });
  assert.deepEqual(payload, {
    clips: [{ video_artifact_id: ARTIFACT_A, start_ms: 125, end_ms: 2_125 }],
  });
  assert.deepEqual(Object.keys(payload), ['clips']);
});

test('Remotion run eligibility includes local_comfyui without widening legacy hard-cut', () => {
  const hardCutStart = appSource.indexOf('const hasHardCutTimelineProfile');
  const remotionStart = appSource.indexOf('const hasRemotionTimelineProfile');
  assert.notEqual(hardCutStart, -1);
  assert.notEqual(remotionStart, -1);
  const hardCutDefinition = appSource.slice(hardCutStart, remotionStart);
  const remotionDefinition = appSource.slice(remotionStart, remotionStart + 220);
  assert.match(hardCutDefinition, /local_playwright/);
  assert.doesNotMatch(hardCutDefinition, /local_comfyui/);
  assert.match(remotionDefinition, /local_comfyui/);
  assert.match(appSource, /editorMode === 'remotion'[\s\S]{0,160}hasRemotionTimelineProfile/);
});

test('timeline UI separates worker wall time from rendered media duration', () => {
  assert.equal(
    api.elapsedSecondsBetween('2026-08-25T18:26:03.883Z', '2026-08-25T18:27:01.201Z'),
    57.318,
  );
  assert.equal(api.elapsedSecondsBetween(undefined, '2026-08-25T18:27:01.201Z'), undefined);
  assert.equal(api.elapsedSecondsBetween('invalid', '2026-08-25T18:27:01.201Z'), undefined);
  assert.equal(
    api.elapsedSecondsBetween('2026-08-25T18:27:01.201Z', '2026-08-25T18:26:03.883Z'),
    undefined,
  );
  assert.match(appSource, /<dt>実行時間<\/dt>/);
  assert.match(appSource, /<dt>出力尺<\/dt>/);
});

test('shared composition uses callback volume for accurate Player timeline display', async () => {
  const compositionSource = await readFile(
    join(studioRoot, 'src', 'remotion', 'TimelineComposition.tsx'),
    'utf8',
  );
  assert.match(compositionSource, /volume=\{\(\) => clip\.volumePercent \/ 100\}/);
  assert.doesNotMatch(compositionSource, /volume=\{clip\.volumePercent \/ 100\}/);
});
