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

test('local pipeline builder emits the exact allowlisted body with defaults', () => {
  const payload = api.buildLocalPipelinePayload({
    workflowPreset: 'ignored',
    workflow_path: 'C:/secret/workflow.json',
    prompt: '  a calm portrait  ',
    seed: '42',
    script: 'first line\nsecond line',
    voice: '  ja-female  ',
    rate: 0,
    pronunciations: [{ source: 'AI', target: 'エーアイ' }],
    includeCaptioned: true,
    captionStylePreset: 'shorts_ja_large_v1',
    variant: 'captioned',
    endpoint: 'https://example.invalid',
  });
  assert.deepEqual(payload, {
    workflow_preset: 'minimax_h3_t2v_official_q4_v1',
    prompt: 'a calm portrait',
    seed: 42,
    segments: [{ text: 'first line' }, { text: 'second line' }],
    voice: 'ja-female',
    rate: 0,
    pronunciations: [{ source: 'AI', target: 'エーアイ' }],
    include_captioned: true,
    caption_style_preset: 'shorts_ja_large_v1',
    variant: 'captioned',
  });
  assert.deepEqual(Object.keys(payload), [
    'workflow_preset',
    'prompt',
    'seed',
    'segments',
    'voice',
    'rate',
    'pronunciations',
    'include_captioned',
    'caption_style_preset',
    'variant',
  ]);
});

test('local pipeline seed serialization keeps max int64 as an unquoted JSON integer', () => {
  const normalized = api.normalizeLocalPipelineInput({
    prompt: 'portrait',
    seed: '9223372036854775807',
    script: 'hello',
    rate: 0,
    includeCaptioned: true,
    captionStylePreset: 'shorts_ja_large_v1',
    variant: 'captioned',
  });
  assert.deepEqual(normalized.errors, []);
  assert.equal(normalized.request.seed, '9223372036854775807');
  assert.equal(normalized.payload.seed, '9223372036854775807');
  const serialized = api.serializeLocalPipelinePayload(normalized.payload);
  assert.match(serialized, /"seed":9223372036854775807,"segments"/);
  assert.doesNotMatch(serialized, /"seed":"9223372036854775807"/);
});

test('local pipeline validation fails closed for invalid prompt, script, seed, and variant', () => {
  const invalid = api.normalizeLocalPipelineInput({
    prompt: 'line\u0001next',
    seed: '9223372036854775808',
    script: '',
    rate: 11,
    includeCaptioned: false,
    captionStylePreset: 'shorts_ja_large_v1',
    variant: 'captioned',
  });
  assert.ok(invalid.errors.some((error) => error.includes('制御文字')));
  assert.ok(invalid.errors.some((error) => error.includes('9223372036854775807')));
  assert.ok(invalid.errors.some((error) => error.includes('セグメント')));
  assert.ok(invalid.errors.some((error) => error.includes('読み上げ速度')));
  assert.ok(invalid.errors.some((error) => error.includes('字幕なし')));
  assert.throws(() => api.buildLocalPipelinePayload({ prompt: 'ok', seed: '0', script: '' }), /セグメント/);
});

test('pipeline result normalization retains run, revision, child jobs, artifacts, and QC verdict', () => {
  const job = api.normalizeJob({
    id: 'pipeline-job',
    production_id: 'production-1',
    run_id: 'run-pipeline',
    type: 'local_pipeline',
    status: 'running',
    result: {
      run_id: 'run-pipeline',
      revision_id: 'rev-7',
      technical_verdict: 'pass',
      artifacts: [{ id: 'master-captioned', name: 'master-captioned.mp4', kind: 'video' }],
      jobs: {
        video_generation: { id: 'child-video', stage: 'video_generation', status: 'succeeded' },
        qc: { id: 'child-qc', stage: 'qc', status: 'running', progress: 42 },
      },
    },
  });
  assert.equal(job.runId, 'run-pipeline');
  assert.equal(job.result?.runId, 'run-pipeline');
  assert.equal(job.result?.revisionId, 'rev-7');
  assert.equal(job.result?.technicalVerdict, 'pass');
  assert.equal(job.result?.artifacts[0].id, 'master-captioned');
  assert.equal(job.result?.jobs?.video_generation.status, 'succeeded');
  assert.equal(job.result?.jobs?.qc.progress, 42);
});

test('pipeline selection and active-state helpers recover after reload without duplicate submission', () => {
  const selection = { productionId: 'production-1', runId: 'run-pipeline' };
  assert.equal(api.isLocalPipelineJobForSelection({
    id: 'pipeline-job',
    production_id: 'production-1',
    run_id: 'run-pipeline',
    type: 'local_pipeline',
    status: 'failed',
  }, selection), true);
  assert.equal(api.isLocalPipelineJobForSelection({
    id: 'other-job',
    production_id: 'production-1',
    run_id: 'other-run',
    type: 'local_pipeline',
    status: 'running',
  }, selection), false);
  assert.equal(api.isLocalPipelineExecutionActive({
    status: 'succeeded',
    result: { jobs: { qc: { status: 'running' } } },
  }), true);
  assert.equal(api.isLocalPipelineExecutionActiveAcross([
    { status: 'failed' },
    { status: 'succeeded' },
    { status: 'pending' },
  ]), true);
  assert.equal(api.isLocalPipelineExecutionActiveAcross([
    { status: 'failed' },
    { status: 'succeeded' },
  ]), false);
});
