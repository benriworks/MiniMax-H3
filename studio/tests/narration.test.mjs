import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);

test('normalizeJob reads payload run/stage and converts duration_ms', () => {
  const job = api.normalizeJob({
    id: 'job_local_1',
    status: 'queued',
    payload: { run_id: 'run_local_1', stage: 'narration' },
    result: {
      duration_ms: 1_250,
      provider: 'windows_sapi',
      provider_task_id: null,
      actual_cost: 0,
      timing_source: 'wav_frames',
      error: { code: 'worker_failed', message: 'SAPI failed' },
    },
  });

  assert.equal(job.status, 'pending');
  assert.equal(job.runId, 'run_local_1');
  assert.equal(job.stage, 'narration');
  assert.equal(job.durationSeconds, 1.25);
  assert.equal(job.message, 'SAPI failed');
  assert.equal(job.errorCode, 'worker_failed');
  assert.equal(job.result?.durationSeconds, 1.25);
  assert.equal(job.result?.provider, 'windows_sapi');
  assert.equal(job.result?.providerTaskId, undefined);
  assert.equal(job.result?.actualCost, 0);
  assert.equal(job.result?.timingSource, 'wav_frames');
  assert.equal(job.result?.errorCode, 'worker_failed');
});

test('normalizeRun converts stage attempt duration_ms and retains attempt metadata', () => {
  const run = api.normalizeRun({
    id: 'run_local_1',
    requested_stages: ['narration'],
    stage_attempts: [{
      id: 'attempt_1',
      job_id: 'job_local_1',
      stage: 'narration',
      status: 'succeeded',
      attempt: 1,
      duration_ms: 2_500,
      cache_hit: true,
      result: {
        provider: 'windows_sapi',
        provider_task_id: null,
        actual_cost: 0,
        timing_source: 'wav_frames',
        artifacts: [{ id: 'audio_1', name: 'narration.wav', kind: 'audio' }],
      },
    }],
  });

  assert.deepEqual(run.requestedStages, ['narration']);
  assert.equal(run.stageAttempts[0].durationSeconds, 2.5);
  assert.equal(run.stageAttempts[0].cacheHit, true);
  assert.equal(run.stageAttempts[0].jobId, 'job_local_1');
  assert.equal(run.stageAttempts[0].provider, 'windows_sapi');
  assert.equal(run.stageAttempts[0].actualCost, 0);
  assert.equal(run.stageAttempts[0].timingSource, 'wav_frames');
  assert.equal(run.stageAttempts[0].artifacts[0].name, 'narration.wav');
});

test('normalizeNarrationInput removes empty lines and enforces segment and text limits', () => {
  const limits = api.LOCAL_NARRATION_LIMITS;
  const valid = api.normalizeNarrationInput(` first line\n\nsecond line `, 0);
  assert.deepEqual(valid.segments, ['first line', 'second line']);
  assert.deepEqual(valid.errors, []);

  const tooMany = api.normalizeNarrationInput(Array.from({ length: limits.maxSegments + 1 }, () => 'x').join('\n'), 0);
  assert.ok(tooMany.errors.some((error) => error.includes(`${limits.maxSegments}行以内`)));

  const tooLong = api.normalizeNarrationInput('x'.repeat(limits.maxSegmentLength + 1), 0);
  assert.ok(tooLong.errors.some((error) => error.includes(`${limits.maxSegmentLength.toLocaleString()}文字以内`)));

  const tooMuch = api.normalizeNarrationInput(Array.from({ length: 26 }, () => 'x'.repeat(2_000)).join('\n'), 0);
  assert.ok(tooMuch.errors.some((error) => error.includes(`${limits.maxTotalLength.toLocaleString()}文字以内`)));
});

test('normalizeLocalAssemblyInput trims source IDs and accepts only closed caption/audio presets', () => {
  assert.equal(api.DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET, 'studio_default_v1');
  assert.equal(api.RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET, 'shorts_ja_large_v1');
  assert.deepEqual(api.LOCAL_ASSEMBLY_CAPTION_STYLE_PRESETS, ['studio_default_v1', 'shorts_ja_large_v1']);
  assert.equal(api.DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET, 'narration_only_v1');
  assert.deepEqual(api.LOCAL_ASSEMBLY_AUDIO_MIX_PRESETS, ['narration_only_v1', 'source_under_narration_v1']);

  const valid = api.normalizeLocalAssemblyInput(' video-1 ', ' attempt-1 ', true, 'shorts_ja_large_v1', 'source_under_narration_v1');
  assert.deepEqual(valid.errors, []);
  assert.deepEqual(valid.request, {
    videoArtifactId: 'video-1',
    narrationAttemptId: 'attempt-1',
    includeCaptioned: true,
    captionStylePreset: 'shorts_ja_large_v1',
    audioMixPreset: 'source_under_narration_v1',
  });

  const invalid = api.normalizeLocalAssemblyInput('  ', '', false, 'studio_default_v1');
  assert.deepEqual(invalid.request, {
    videoArtifactId: '',
    narrationAttemptId: '',
    includeCaptioned: false,
    captionStylePreset: 'studio_default_v1',
    audioMixPreset: 'narration_only_v1',
  });
  assert.equal(invalid.errors.length, 2);
  assert.ok(invalid.errors[0].includes('動画artifact'));
  assert.ok(invalid.errors[1].includes('ナレーション'));

  assert.ok(api.normalizeLocalAssemblyInput('video-1', 'attempt-1', true, 'raw-ass').errors.some((error) => error.includes('字幕プリセット')));
  assert.ok(api.normalizeLocalAssemblyInput('video-1', 'attempt-1', false, 'shorts_ja_large_v1').errors.some((error) => error.includes('字幕付き版')));
  assert.ok(api.normalizeLocalAssemblyInput('video-1', 'attempt-1', true, 'studio_default_v1', 'custom_gain').errors.some((error) => error.includes('音声mixプリセット')));
});

test('buildLocalAssemblyPayload emits the exact closed preset wire body', () => {
  const payload = api.buildLocalAssemblyPayload({
    videoArtifactId: ' video-1 ',
    narrationAttemptId: ' attempt-1 ',
    includeCaptioned: true,
    captionStylePreset: 'shorts_ja_large_v1',
    audioMixPreset: 'source_under_narration_v1',
    sourceGain: 0.8,
    narrationGain: 0.4,
    captionStyle: { font: 'untrusted' },
    filter: 'subtitles=unsafe.ass',
  });
  assert.deepEqual(payload, {
    video_artifact_id: 'video-1',
    narration_attempt_id: 'attempt-1',
    include_captioned: true,
    caption_style_preset: 'shorts_ja_large_v1',
    audio_mix_preset: 'source_under_narration_v1',
  });
  assert.deepEqual(Object.keys(payload).sort(), [
    'audio_mix_preset',
    'caption_style_preset',
    'include_captioned',
    'narration_attempt_id',
    'video_artifact_id',
  ]);
  assert.throws(() => api.buildLocalAssemblyPayload({
    videoArtifactId: 'video-1',
    narrationAttemptId: 'attempt-1',
    includeCaptioned: true,
    captionStylePreset: 'custom',
  }), /字幕プリセット/);
  assert.throws(() => api.buildLocalAssemblyPayload({
    videoArtifactId: 'video-1',
    narrationAttemptId: 'attempt-1',
    includeCaptioned: true,
    captionStylePreset: 'studio_default_v1',
    audioMixPreset: 'custom_gain',
  }), /音声mixプリセット/);

  assert.deepEqual(api.buildLocalAssemblyPayload({
    videoArtifactId: 'video-1',
    narrationAttemptId: 'attempt-1',
    includeCaptioned: false,
  }), {
    video_artifact_id: 'video-1',
    narration_attempt_id: 'attempt-1',
    include_captioned: false,
    caption_style_preset: 'studio_default_v1',
    audio_mix_preset: 'narration_only_v1',
  });
});
