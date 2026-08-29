import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const appSource = await readFile(join(studioRoot, 'src', 'App.tsx'), 'utf8');
const stylesSource = await readFile(join(studioRoot, 'src', 'styles.css'), 'utf8');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);

const ARTIFACT_A = `art_${'a'.repeat(32)}`;
const ARTIFACT_B = `art_${'b'.repeat(32)}`;

const clip = (overrides = {}) => ({
  videoArtifactId: ARTIFACT_A,
  startMs: 100,
  endMs: 2_100,
  volumePercent: 80,
  transitionToNext: null,
  overlay: null,
  ...overrides,
});

const completeRequest = (overrides = {}) => ({
  schemaVersion: 1,
  clips: [clip()],
  segments: [{ text: '一つ目のナレーションです。' }, { text: '二つ目のナレーションです。' }],
  voice: '  Microsoft Haruka Desktop  ',
  rate: 1,
  pronunciations: [{ source: 'AI', target: 'エーアイ' }],
  includeCaptioned: true,
  captionStylePreset: 'shorts_ja_large_v1',
  audioMixPreset: 'source_under_narration_v1',
  variant: 'captioned',
  ...overrides,
});

test('detailed test video payload is exact snake_case schema v1 and strips renderer escape hatches', () => {
  const payload = api.buildDetailedTestVideoPayload(completeRequest({
    clips: [
      clip({
        transitionToNext: { type: 'fade', durationMs: 300, easing: 'unsafe' },
        overlay: {
          text: '  詳細一括\r\nテスト  ',
          startMs: 100,
          endMs: 1_900,
          position: 'bottom',
          stylePreset: 'shorts_ja_large_v1',
          css: 'unsafe',
        },
        ffmpegFilter: 'unsafe',
      }),
      clip({
        videoArtifactId: ARTIFACT_B,
        startMs: 0,
        endMs: 1_000,
        volumePercent: 40,
      }),
    ],
    outputPath: 'C:/unsafe/master.mp4',
    sourceGain: 9,
    narrationGain: 9,
  }));
  assert.deepEqual(payload, {
    schema_version: 1,
    clips: [
      {
        video_artifact_id: ARTIFACT_A,
        start_ms: 100,
        end_ms: 2_100,
        volume_percent: 80,
        visual_preset: 'preserve_v1',
        transition_to_next: { type: 'fade', duration_ms: 300 },
        overlay: {
          text: '詳細一括\nテスト',
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
        volume_percent: 40,
        visual_preset: 'preserve_v1',
        transition_to_next: null,
        overlay: null,
      },
    ],
    segments: [{ text: '一つ目のナレーションです。' }, { text: '二つ目のナレーションです。' }],
    voice: 'Microsoft Haruka Desktop',
    rate: 1,
    pronunciations: [{ source: 'AI', target: 'エーアイ' }],
    include_captioned: true,
    caption_style_preset: 'shorts_ja_large_v1',
    audio_mix_preset: 'source_under_narration_v1',
    variant: 'captioned',
  });
  assert.deepEqual(Object.keys(payload), [
    'schema_version',
    'clips',
    'segments',
    'voice',
    'rate',
    'pronunciations',
    'include_captioned',
    'caption_style_preset',
    'audio_mix_preset',
    'variant',
  ]);
});

test('detailed test video defaults remain captioned Shorts plus narration-only mix', () => {
  const payload = api.buildDetailedTestVideoPayload({
    clips: [clip()],
    segments: [{ text: '既定値を確認します。' }],
  });
  assert.equal(payload.schema_version, 1);
  assert.equal(payload.rate, 0);
  assert.equal(payload.include_captioned, true);
  assert.equal(payload.caption_style_preset, 'shorts_ja_large_v1');
  assert.equal(payload.audio_mix_preset, 'narration_only_v1');
  assert.equal(payload.variant, 'captioned');
  assert.equal('voice' in payload, false);
  assert.equal('pronunciations' in payload, false);
});

test('detailed test video rejects open enums, invalid narration, and unsafe mix drafts', () => {
  const invalid = api.normalizeDetailedTestVideoInput(completeRequest({
    schemaVersion: 2,
    segments: [],
    rate: 11,
    captionStylePreset: 'custom_css',
    audioMixPreset: 'custom_gain',
    variant: 'review',
  }));
  assert.ok(invalid.errors.some((error) => error.includes('schema_version')));
  assert.ok(invalid.errors.some((error) => error.includes('セグメント')));
  assert.ok(invalid.errors.some((error) => error.includes('読み上げ速度')));
  assert.ok(invalid.errors.some((error) => error.includes('字幕プリセット')));
  assert.ok(invalid.errors.some((error) => error.includes('音声mixプリセット')));
  assert.ok(invalid.errors.some((error) => error.includes('variant')));
  assert.throws(() => api.buildDetailedTestVideoPayload(completeRequest({ schemaVersion: 2 })), /schema_version/);
});

test('source-under-narration mix fails closed when every clip requests silence', () => {
  const normalized = api.normalizeDetailedTestVideoInput(completeRequest({
    clips: [clip({ volumePercent: 0 })],
    audioMixPreset: 'source_under_narration_v1',
  }));
  assert.ok(normalized.errors.some((error) => error.includes('少なくとも1カット')));
});

test('Shorts caption preflight mirrors the backend display-width and Unicode boundaries', () => {
  assert.deepEqual(api.detailedTestVideoShortsCaptionErrors(['あ'.repeat(19), 'A'.repeat(20)]), []);
  assert.ok(api.detailedTestVideoShortsCaptionErrors(['あ'.repeat(20)]).some((error) => error.includes('表示幅38')));
  assert.ok(api.detailedTestVideoShortsCaptionErrors(['A'.repeat(21)]).some((error) => error.includes('20文字')));
  assert.ok(api.detailedTestVideoShortsCaptionErrors(['不可視\u200b文字']).some((error) => error.includes('不可視文字')));
  assert.ok(api.detailedTestVideoShortsCaptionErrors(Array.from({ length: 7 }, (_, index) => `字幕${index}`)).some((error) => error.includes('6セグメント')));

  const normalized = api.normalizeDetailedTestVideoInput(completeRequest({
    segments: [{ text: 'あ'.repeat(20) }],
  }));
  assert.ok(normalized.errors.some((error) => error.includes('表示幅38')));
  assert.throws(
    () => api.buildDetailedTestVideoPayload(completeRequest({ segments: [{ text: 'あ'.repeat(20) }] })),
    /表示幅38/,
  );
});

test('detailed top-job matching is kind-bound and statusless result.children retain stage linkage', () => {
  const selection = { productionId: 'production-1' };
  assert.equal(api.isDetailedTestVideoJobForSelection({
    id: 'top-1',
    production_id: 'production-1',
    kind: 'detailed_test_video',
  }, selection), true);
  assert.equal(api.isDetailedTestVideoJobForSelection({
    id: 'child-1',
    production_id: 'production-1',
    kind: 'worker',
    stage: 'narration',
  }, selection), false);
  assert.equal(api.isDetailedTestVideoJobForSelection({
    id: 'top-2',
    production_id: 'production-2',
    kind: 'detailed_test_video',
  }, selection), false);

  const job = api.normalizeJob({
    id: 'top-1',
    production_id: 'production-1',
    kind: 'detailed_test_video',
    status: 'running',
    result: {
      run_id: 'run-1',
      children: {
        narration: { job_id: 'narration-job', stage_attempt_id: 'narration-attempt', cache_hit: true },
        qc: { job_id: 'qc-job', stage_attempt_id: 'qc-attempt', cache_hit: false },
      },
    },
  });
  assert.equal(job.type, 'detailed_test_video');
  assert.equal(job.result?.jobs?.narration.status, 'unknown');
  assert.equal(job.result?.jobs?.narration.stageAttemptId, 'narration-attempt');
  assert.equal(job.result?.jobs?.narration.cacheHit, true);
  assert.equal(job.result?.jobs?.qc.jobId, 'qc-job');
  assert.equal(api.isDetailedTestVideoJobForSelection(job, selection), true);
  assert.equal(api.isDetailedTestVideoExecutionActive(job), true);
});

test('ambiguous direct Detailed recovery requires a fresh exact payload digest and rejects announcement timing', async () => {
  const request = completeRequest();
  const digest = await api.detailedTestVideoRequestPayloadSha256(request);
  assert.match(digest, /^[0-9A-F]{64}$/);
  assert.equal(
    await api.detailedTestVideoRequestPayloadSha256(completeRequest({
      segments: [{ text: 'one' }, { text: 'two' }],
      voice: 'Voice',
      pronunciations: [{ source: 'AI', target: 'A I' }],
    })),
    '728040BC2E6ABD4B5BE6576467120A6830AC7F600E590A114B96C16E082464B3',
  );
  const omittedOptionalsRequest = completeRequest({
    segments: [{ text: 'one' }, { text: 'two' }],
  });
  delete omittedOptionalsRequest.voice;
  delete omittedOptionalsRequest.pronunciations;
  assert.equal(
    await api.detailedTestVideoRequestPayloadSha256(omittedOptionalsRequest),
    '14204AF12EE99E320788268F716CF3D2990AB4BC5F64000E9CB45A78C5EA9A6A',
  );
  const jobRecord = (id, overrides = {}) => ({
    id,
    production_id: 'production-1',
    kind: 'detailed_test_video',
    status: 'queued',
    payload: {
      production_id: 'production-1',
      run_id: `run_${'1'.repeat(32)}`,
      revision_id: `rev_${'2'.repeat(32)}`,
      stage: 'detailed_test_video',
      execution_profile: 'local_sapi',
      request_key: 'A'.repeat(64),
      request_payload_sha256: digest,
      ...overrides,
    },
  });
  const known = api.normalizeJob(jobRecord('known-job'));
  const guard = await api.createDetailedTestVideoSubmissionGuard('production-1', request, [known]);
  const exact = api.normalizeJob(jobRecord('fresh-exact'));
  assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(exact, guard), true);
  assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(known, guard), false);

  const differentPronunciationDigest = await api.detailedTestVideoRequestPayloadSha256(completeRequest({
    pronunciations: [{ source: 'AI', target: '人工知能' }],
  }));
  const wrongDigest = api.normalizeJob(jobRecord('fresh-wrong', {
    request_payload_sha256: differentPronunciationDigest,
  }));
  assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(wrongDigest, guard), false);

  for (const [key, value] of [
    ['narration_alignment_policy', 'announcement_scene_starts_v1'],
    ['narration_timing_policy', 'explicit_segment_starts_v1'],
    ['narration_segment_start_ms', [0, 1_000]],
  ]) {
    const announcement = api.normalizeJob(jobRecord(`fresh-announcement-${key}`, { [key]: value }));
    assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(announcement, guard), false);
  }
  for (const [id, overrides] of [
    ['wrong-profile', { execution_profile: 'local_pipeline' }],
    ['wrong-stage', { stage: 'timeline' }],
    ['wrong-payload-production', { production_id: 'production-2' }],
    ['bad-request-key', { request_key: 'not-a-sha' }],
    ['bad-digest', { request_payload_sha256: 'not-a-sha' }],
  ]) {
    assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(
      api.normalizeJob(jobRecord(`fresh-${id}`, overrides)),
      guard,
    ), false);
  }
  assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(api.normalizeJob({
    ...jobRecord('fresh-wrong-top-production'),
    production_id: 'production-2',
  }), guard), false);
  assert.equal(api.detailedTestVideoJobMatchesSubmissionGuard(api.normalizeJob({
    ...jobRecord('fresh-missing'),
    payload: { production_id: 'production-1', stage: 'detailed_test_video' },
  }), guard), false);
});

test('executeDetailedTestVideo posts the canonical body to the production endpoint', async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url, init, body: JSON.parse(String(init.body)) };
    return new Response(JSON.stringify({
      id: 'top-job', production_id: 'production/a', kind: 'detailed_test_video', status: 'pending',
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    const request = completeRequest();
    const job = await api.api.executeDetailedTestVideo('production/a', request);
    assert.equal(job.id, 'top-job');
    assert.equal(job.type, 'detailed_test_video');
    assert.equal(captured.url, '/api/productions/production%2Fa/execute-detailed-test-video');
    assert.equal(captured.init.method, 'POST');
    assert.deepEqual(captured.body, api.buildDetailedTestVideoPayload(request));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Studio exposes a distinct responsive detailed batch surface with 2-second top-job polling', () => {
  assert.match(appSource, /id: 'detailed-test', label: '詳細一括'/);
  assert.match(appSource, /function DetailedTestVideoPanel/);
  assert.match(appSource, /setInterval\([\s\S]{0,500}2_000/);
  assert.match(appSource, /onReload\(\)/);
  assert.match(appSource, /pollingRef\.current/);
  assert.match(appSource, /submissionUncertain/);
  assert.match(appSource, /knownJobIds/);
  assert.match(appSource, /detailedTestVideoJobMatchesSubmissionGuard/);
  assert.match(appSource, /byId\.set\(job\.id, job\)/);
  assert.match(appSource, /素材音を残すpresetは、Remotionの素材音量適用後にさらに25%/);
  assert.match(appSource, /result\?\.jobs/);
  assert.match(appSource, /child\.status === 'unknown' \? attempt\.status : child\.status/);
  assert.match(appSource, /visibleJob\?\.result\?\.durationMs \?\? normalizedInput\.outputDurationMs/);
  assert.match(appSource, /formatMilliseconds\(displayedRecipeDurationMs\)/);
  assert.match(appSource, /H3低解像度を鮮明化/);
  assert.match(appSource, /Playerは映像補正presetを再現しません/);
  assert.match(stylesSource, /\.detailed-test-grid/);
  assert.match(stylesSource, /\.detailed-test-output-grid/);
});
