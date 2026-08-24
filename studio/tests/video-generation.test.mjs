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

test('local ComfyUI payload uses the fixed preset and exact snake_case allowlist', () => {
  const payload = api.buildLocalComfyUiPayload({
    workflowPreset: 'custom',
    workflow_path: 'C:/secret/workflow.json',
    prompt: '  a calm portrait  ',
    seed: '42',
    endpoint: 'http://example.invalid',
  });
  assert.deepEqual(payload, {
    workflow_preset: 'minimax_h3_t2v_official_q4_v1',
    prompt: 'a calm portrait',
    seed: 42,
  });
  assert.deepEqual(Object.keys(payload), ['workflow_preset', 'prompt', 'seed']);
});

test('local ComfyUI seed validation preserves the complete signed 64-bit range', () => {
  const max = api.normalizeLocalComfyUiInput('prompt', '9223372036854775807');
  assert.deepEqual(max.errors, []);
  assert.equal(max.request.seed, '9223372036854775807');
  assert.equal(max.payload.seed, '9223372036854775807');

  const negative = api.normalizeLocalComfyUiInput('prompt', '-1');
  assert.ok(negative.errors.some((error) => error.includes('0以上の整数')));
  const tooLarge = api.normalizeLocalComfyUiInput('prompt', '9223372036854775808');
  assert.ok(tooLarge.errors.some((error) => error.includes('9223372036854775807')));
  const fractional = api.normalizeLocalComfyUiInput('prompt', '1.5');
  assert.ok(fractional.errors.some((error) => error.includes('整数')));

  const serialized = api.serializeLocalComfyUiPayload(max.payload);
  assert.match(serialized, /"seed":9223372036854775807}/);
  assert.doesNotMatch(serialized, /"seed":"9223372036854775807"/);
});

test('local ComfyUI prompt validation is fail-closed', () => {
  assert.ok(api.normalizeLocalComfyUiInput('', '0').errors.some((error) => error.includes('プロンプト')));
  assert.deepEqual(api.normalizeLocalComfyUiInput('line\r\nnext\twith allowed whitespace', '0').errors, []);
  assert.ok(api.normalizeLocalComfyUiInput('line\u0001next', '0').errors.some((error) => error.includes('制御文字')));
  assert.throws(() => api.buildLocalComfyUiPayload({ prompt: 'ok', seed: '' }), /seed/);
});

test('local ComfyUI job selection is constrained to the selected run and video stage', () => {
  const selection = { runId: 'run-video', stageAttemptId: 'attempt-video' };
  assert.equal(api.isLocalComfyUiJobForSelection({
    id: 'job-1',
    type: 'local_video_generation',
    payload: { run_id: 'run-video', stage: 'video_generation', stage_attempt_id: 'attempt-video' },
  }, selection), true);
  assert.equal(api.isLocalComfyUiJobForSelection({
    id: 'job-2',
    stage: 'video_generation',
    run_id: 'other-run',
    stage_attempt_id: 'attempt-video',
  }, selection), false);
  assert.equal(api.isLocalComfyUiJobForSelection({
    id: 'job-3',
    stage: 'timeline',
    run_id: 'run-video',
    stage_attempt_id: 'attempt-video',
  }, selection), false);
});

test('reload normalization retains nested ComfyUI stage metadata in typed fields', () => {
  const run = api.normalizeRun({
    id: 'run-video',
    requested_stages: ['video_generation'],
    stage_attempts: [{
      id: 'attempt-video',
      stage: 'video_generation',
      status: 'running',
      result: {
        provider: 'comfyui',
        provider_task_id: 'prompt-123',
        prompt_sha256: 'A'.repeat(64),
        seed: 9223372036854776000,
        seed_decimal: '9223372036854775807',
        workflow_preset: 'minimax_h3_t2v_official_q4_v1',
      },
    }],
  });
  const attempt = run.stageAttempts[0];
  assert.equal(attempt.providerTaskId, 'prompt-123');
  assert.equal(attempt.promptSha256, 'A'.repeat(64));
  assert.equal(attempt.seed, '9223372036854775807');
  assert.equal(attempt.workflowPreset, 'minimax_h3_t2v_official_q4_v1');

  // JSON.parse rounds the numeric seed, but the nested decimal string is exact.
  const job = api.normalizeJob(JSON.parse(`{
    "id":"job-video",
    "status":"running",
    "stage":"video_generation",
    "seed":9223372036854775807,
    "result":{
      "provider_task_id":"prompt-456",
      "prompt_sha256":"${'B'.repeat(64)}",
      "seed":9223372036854775807,
      "seed_decimal":"9223372036854775807",
      "workflow_preset":"minimax_h3_t2v_official_q4_v1"
    }
  }`));
  assert.notEqual(String(job.raw.seed), '9223372036854775807');
  assert.equal(job.result?.providerTaskId, 'prompt-456');
  assert.equal(job.result?.promptSha256, 'B'.repeat(64));
  assert.equal(job.result?.seed, '9223372036854775807');
  assert.equal(job.result?.workflowPreset, 'minimax_h3_t2v_official_q4_v1');

  const directSeedDecimalJob = api.normalizeJob({
    id: 'job-video',
    status: 'running',
    stage: 'video_generation',
    prompt_sha256: 'B'.repeat(64),
    seed: '9223372036854775807',
    workflow_preset: 'minimax_h3_t2v_official_q4_v1',
    result: { provider_task_id: 'prompt-456' },
  });
  assert.equal(directSeedDecimalJob.result?.seed, '9223372036854775807');
});

test('reloaded pending and running ComfyUI records remain execution-active', () => {
  assert.equal(api.isLocalComfyUiExecutionActive({ status: 'pending' }), true);
  assert.equal(api.isLocalComfyUiExecutionActive({ state: 'running' }), true);
  assert.equal(api.isLocalComfyUiExecutionActive({ status: 'succeeded' }), false);
  assert.equal(api.isLocalComfyUiExecutionActive(undefined), false);
  assert.equal(api.isLocalComfyUiExecutionActiveAcross([
    { id: 'stale-terminal-local-job', status: 'failed' },
    { id: 'newer-running-attempt', status: 'running' },
    { id: 'newer-running-reloaded-job', status: 'pending' },
  ]), true);
  assert.equal(api.isLocalComfyUiExecutionActiveAcross([
    { id: 'terminal-job', status: 'failed' },
    { id: 'terminal-attempt', status: 'succeeded' },
  ]), false);
});
