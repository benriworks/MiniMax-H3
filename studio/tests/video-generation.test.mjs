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

test('local pipeline continuation normalizes the safe public projection and locks active states', () => {
  const run = api.normalizeRun({
    id: 'run-pipeline',
    requested_stages: ['video_generation', 'narration', 'timeline', 'assembly', 'qc'],
    pipeline_continuation: {
      state: 'continuing',
      automatic: true,
      resume_count: 2,
      job_id: 'job-continuation',
      source_job_id: 'job-top-failed',
      source_attempt_id: 'attempt-video',
      updated_at: '2026-08-25T00:10:00Z',
      error: null,
      prompt: 'must not become a typed continuation field',
    },
  });
  assert.deepEqual(run.pipelineContinuation, {
    state: 'continuing',
    automatic: true,
    resumeCount: 2,
    jobId: 'job-continuation',
    sourceJobId: 'job-top-failed',
    sourceAttemptId: 'attempt-video',
    updatedAt: '2026-08-25T00:10:00Z',
    error: null,
    raw: {
      state: 'continuing',
      automatic: true,
      error: null,
      resume_count: 2,
      job_id: 'job-continuation',
      source_job_id: 'job-top-failed',
      source_attempt_id: 'attempt-video',
      updated_at: '2026-08-25T00:10:00Z',
    },
  });
  assert.equal(api.isPipelineContinuationActive(run.pipelineContinuation), true);
  assert.equal(api.isPipelineContinuationActive({ state: 'active' }), true);
  assert.equal(api.isPipelineContinuationActive({ state: 'waiting_provider' }), true);
  assert.equal(api.isPipelineContinuationActive({ state: 'ready' }), true);
  assert.equal(api.isPipelineContinuationActive({ state: 'cancel_requested' }), true);
  assert.equal(api.isPipelineContinuationActive({ state: 'succeeded' }), false);
  assert.equal(api.isPipelineContinuationActive({ state: 'recovery_blocked' }), false);
  assert.equal(api.isPipelineContinuationActive({ state: 'unavailable' }), false);
  assert.equal(run.pipelineContinuation.raw.prompt, undefined);

  assert.equal(api.normalizePipelineContinuation({ state: 'active', automatic: true }).state, 'active');
  assert.equal(api.normalizePipelineContinuation({ state: 'unavailable', automatic: false }).state, 'unavailable');

  const invalid = api.normalizePipelineContinuation({
    state: 'unexpected-state',
    error: { code: 'continuation_failed', message: 'manual review', prompt: 'private' },
  });
  assert.equal(invalid.state, 'recovery_blocked');
  assert.deepEqual(invalid.error, { code: 'continuation_failed', message: 'manual review' });
  assert.equal(invalid.raw.prompt, undefined);
});

test('local pipeline top-job helper excludes video and reconciliation children', () => {
  assert.equal(api.isLocalPipelineTopJob({ kind: 'local_pipeline', stage: 'pipeline' }), true);
  assert.equal(api.isLocalPipelineTopJob({ type: 'local_pipeline', payload: { stage: 'pipeline' } }), true);
  assert.equal(api.isLocalPipelineTopJob({ type: 'pipeline', raw: { kind: 'local_pipeline' } }), true);
  assert.equal(api.isLocalPipelineTopJob({ kind: 'local_video_generation', stage: 'video_generation' }), false);
  assert.equal(api.isLocalPipelineTopJob({ kind: 'provider_cancellation_reconciliation' }), false);
  assert.equal(api.isLocalPipelineTopJob({ stage: 'pipeline', execution_profile: 'local_pipeline' }), false);
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

test('provider task normalization exposes recovery metadata without prompt text', () => {
  const run = api.normalizeRun({
    id: 'run-video',
    requested_stages: ['video_generation'],
    provider_tasks: [{
      id: 'provider-task-1',
      provider: 'comfyui',
      production_id: 'production-1',
      run_id: 'run-video',
      stage: 'video_generation',
      status: 'recovering',
      provider_task_id: 'comfy-prompt-1',
      attempt_sequence: 2,
      active_stage_attempt_id: 'attempt-video-2',
      active_job_id: 'job-video-2',
      recovery_count: 1,
      automatic_recovery_available: true,
      duplicate_submission_blocked: true,
      resumable: true,
      next_action: 'resume',
      created_at: '2026-08-24T23:58:00Z',
      updated_at: '2026-08-24T23:59:00Z',
      last_observed_at: '2026-08-25T00:00:00Z',
      error: { code: 'process_interrupted', message: 'ComfyUIの状態を確認しています' },
    }],
  }, 0);
  const task = run.providerTasks[0];
  assert.equal(task.id, 'provider-task-1');
  assert.equal(task.productionId, 'production-1');
  assert.equal(task.runId, 'run-video');
  assert.equal(task.status, 'recovering');
  assert.equal(task.providerTaskId, 'comfy-prompt-1');
  assert.equal(task.attemptSequence, 2);
  assert.equal(task.activeStageAttemptId, 'attempt-video-2');
  assert.equal(task.activeJobId, 'job-video-2');
  assert.equal(task.recoveryCount, 1);
  assert.equal(task.automaticRecoveryAvailable, true);
  assert.equal(task.duplicateSubmissionBlocked, true);
  assert.equal(task.resumable, true);
  assert.equal(task.createdAt, '2026-08-24T23:58:00Z');
  assert.equal(task.updatedAt, '2026-08-24T23:59:00Z');
  assert.equal(task.checkedAt, '2026-08-25T00:00:00Z');
  assert.deepEqual(task.error, { code: 'process_interrupted', message: 'ComfyUIの状態を確認しています' });
  assert.equal(task.raw.prompt, undefined);
  assert.equal(api.isProviderTaskActive(task), true);
  assert.equal(api.isProviderTaskBlocking(task), true);
  assert.equal(api.isProviderTaskResumeAvailable(task), false);
});

test('provider task timestamps normalize backend fields and order by last observation first', () => {
  const task = api.normalizeProviderTask({
    id: 'provider-task-timestamps',
    attempt_sequence: 3,
    created_at: '2026-08-25T00:00:00Z',
    updated_at: '2026-08-25T00:01:00Z',
    last_observed_at: '2026-08-25T00:02:00Z',
    checked_at: '2026-08-24T23:59:00Z',
  });
  assert.equal(task.createdAt, '2026-08-25T00:00:00Z');
  assert.equal(task.updatedAt, '2026-08-25T00:01:00Z');
  assert.equal(task.checkedAt, '2026-08-25T00:02:00Z');
  assert.equal(api.providerTaskTimestamp(task), '2026-08-25T00:02:00Z');

  const observed = { id: 'observed', attemptSequence: 1, checkedAt: '2026-08-25T00:03:00Z', updatedAt: '2026-08-25T00:01:00Z', createdAt: '2026-08-25T00:00:00Z' };
  const updated = { id: 'updated', attemptSequence: 1, updatedAt: '2026-08-25T00:02:00Z', createdAt: '2026-08-25T00:00:00Z' };
  const created = { id: 'created', attemptSequence: 1, createdAt: '2026-08-25T00:01:00Z' };
  assert.deepEqual(api.newestProviderTasks([created, updated, observed]).map((item) => item.id), ['observed', 'updated', 'created']);

  const newerAttempt = { id: 'newer-attempt', attemptSequence: 2, checkedAt: '2026-08-24T00:00:00Z' };
  assert.equal(api.newestProviderTasks([observed, newerAttempt])[0].id, 'observed');
});

test('provider task timestamp helper falls back from observed to updated to created time', () => {
  assert.equal(api.providerTaskTimestamp({ id: 'checked', checkedAt: '2026-08-25T00:03:00Z', updatedAt: '2026-08-25T00:02:00Z', createdAt: '2026-08-25T00:01:00Z' }), '2026-08-25T00:03:00Z');
  assert.equal(api.providerTaskTimestamp({ id: 'updated', updatedAt: '2026-08-25T00:02:00Z', createdAt: '2026-08-25T00:01:00Z' }), '2026-08-25T00:02:00Z');
  assert.equal(api.providerTaskTimestamp({ id: 'created', createdAt: '2026-08-25T00:01:00Z' }), '2026-08-25T00:01:00Z');
  assert.equal(api.providerTaskTimestamp({ id: 'empty' }), '');
});

test('provider task safety helpers fail closed for ambiguous and unknown states', () => {
  const ambiguous = api.normalizeProviderTask({
    id: 'provider-task-ambiguous',
    status: 'ambiguous',
    duplicate_submission_blocked: true,
    automatic_recovery_available: true,
    next_action: 'inspect',
  });
  assert.equal(api.isProviderTaskActive(ambiguous), false);
  assert.equal(api.isProviderTaskBlocking(ambiguous), true);
  assert.equal(api.isProviderTaskResumeAvailable(ambiguous), true);

  const invalid = api.normalizeProviderTask({ id: 'provider-task-invalid', status: 'unexpected-provider-state' });
  assert.equal(invalid.status, 'recovery_blocked');
  assert.equal(api.isProviderTaskActive(invalid), false);
  assert.equal(api.isProviderTaskBlocking(invalid), true);
  assert.equal(api.isProviderTaskResumeAvailable(invalid), false);

  const recoveryBlocked = api.normalizeProviderTask({ id: 'provider-task-blocked', status: 'recovery_blocked', resumable: true });
  assert.equal(api.isProviderTaskBlocking(recoveryBlocked), true);
  assert.equal(api.isProviderTaskResumeAvailable(recoveryBlocked), true);

  const submittedWithoutOwner = api.normalizeProviderTask({ id: 'provider-task-submitted', status: 'submitted', resumable: true });
  assert.equal(api.isProviderTaskResumeAvailable(submittedWithoutOwner), true);

  const cancelRequested = api.normalizeProviderTask({
    id: 'provider-task-cancel-requested',
    status: 'cancel_requested',
    resumable: true,
    duplicate_submission_blocked: true,
  });
  assert.equal(api.isProviderTaskActive(cancelRequested), true);
  assert.equal(api.isProviderTaskBlocking(cancelRequested), true);
  assert.equal(api.isProviderTaskResumeAvailable(cancelRequested), true);

  const interruptedReconciliation = api.normalizeJob({
    id: 'job-cancel-reconciliation',
    kind: 'provider_cancellation_reconciliation',
    status: 'cancel_requested',
  });
  assert.equal(interruptedReconciliation.status, 'cancelled');

  const succeeded = api.normalizeProviderTask({ id: 'provider-task-succeeded', status: 'succeeded', resumable: true });
  assert.equal(api.isProviderTaskActive(succeeded), false);
  assert.equal(api.isProviderTaskResumeAvailable(succeeded), false);
});

test('provider task resume sends an exact empty JSON object to the backend', async () => {
  const originalFetch = globalThis.fetch;
  let seen;
  globalThis.fetch = async (input, init = {}) => {
    seen = { input: String(input), method: init.method, body: init.body, contentType: init.headers?.['Content-Type'] };
    return {
      ok: true,
      status: 202,
      json: async () => ({ id: 'job-resumed', status: 'running', stage: 'video_generation' }),
    };
  };
  try {
    const resumed = await api.api.resumeProviderTask('provider-task/1');
    assert.deepEqual(seen, {
      input: '/api/provider-tasks/provider-task%2F1/resume',
      method: 'POST',
      body: '{}',
      contentType: 'application/json',
    });
    assert.equal(resumed.id, 'job-resumed');
    assert.equal(resumed.status, 'running');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
