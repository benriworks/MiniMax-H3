import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');

const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await (await import('node:fs/promises')).readFile(join(testDist, 'api.js'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);

const assemblyAttempt = (id, artifacts, overrides = {}) => ({
  id,
  stage: 'assembly',
  status: 'succeeded',
  provider: 'local_ffmpeg',
  artifacts,
  ...overrides,
});

test('buildLocalQcPayload emits exactly the two wire fields', () => {
  const payload = api.buildLocalQcPayload({
    assemblyAttemptId: '  attempt-1 ',
    variant: 'captioned',
    unexpected: 'must not cross the API boundary',
  });
  assert.deepEqual(payload, { assembly_attempt_id: 'attempt-1', variant: 'captioned' });
  assert.deepEqual(Object.keys(payload).sort(), ['assembly_attempt_id', 'variant']);
  assert.throws(() => api.buildLocalQcPayload({ assemblyAttemptId: 'attempt-1', variant: 'burned-in' }), /variant/);
  assert.throws(() => api.buildLocalQcPayload({ assemblyAttemptId: '', variant: 'clean' }), /assembly_attempt_id/);
});

test('eligible selection requires local_sapi, requested assembly+qc, and a succeeded local_ffmpeg attempt', () => {
  const eligible = {
    executionProfile: 'local_sapi',
    requestedStages: ['narration', 'assembly', 'qc'],
    stageAttempts: [assemblyAttempt('attempt-1', [
      { id: 'clean-1', name: 'master-clean.mp4', kind: 'video' },
      { id: 'captioned-1', name: 'master-captioned.mp4', kind: 'video' },
    ])],
  };
  assert.equal(api.hasRequestedLocalQcStages(eligible), true);
  assert.equal(api.isEligibleLocalQcRun(eligible), true);
  assert.deepEqual(api.getLocalQcAvailableVariants(eligible.stageAttempts[0]), ['clean', 'captioned']);
  assert.deepEqual(api.getLocalQcVariantAvailability(eligible.stageAttempts[0]), { clean: true, captioned: true });
  assert.equal(api.isEligibleLocalQcRun({ ...eligible, executionProfile: 'default' }), false);
  assert.equal(api.isEligibleLocalQcRun({ ...eligible, requestedStages: ['narration', 'assembly'] }), false);
  assert.equal(api.isEligibleLocalQcRun({ ...eligible, stageAttempts: [assemblyAttempt('failed', [{ name: 'master-clean.mp4', kind: 'video' }], { status: 'failed' })] }), false);
  assert.equal(api.isEligibleLocalQcRun({ ...eligible, stageAttempts: [assemblyAttempt('other', [{ name: 'master-clean.mp4', kind: 'video' }], { provider: 'other_ffmpeg' })] }), false);
});

test('captioned is not offered when the assembly attempt has only a clean master', () => {
  const attempt = assemblyAttempt('clean-only', [{ id: 'clean', name: 'master-clean.mp4', kind: 'video' }]);
  assert.deepEqual(api.getLocalQcAvailableVariants(attempt), ['clean']);
  assert.equal(api.isEligibleLocalQcRun({ executionProfile: 'local_sapi', requestedStages: ['assembly', 'qc'], stageAttempts: [attempt] }), true);
  assert.equal(api.normalizeLocalQcInput(' attempt ', 'captioned').errors.length, 0);
  assert.deepEqual(api.normalizeLocalQcInput(' attempt ', 'bogus').errors, ['variantはcleanまたはcaptionedを指定してください。']);
});

test('result status keeps job success/analysis completion separate from technical verdict fail', () => {
  const failedTechnical = api.getLocalQcResultStatus({
    status: 'succeeded',
    result: { analysis_status: 'succeeded', technical_verdict: 'fail' },
  });
  assert.equal(failedTechnical.jobSucceeded, true);
  assert.equal(failedTechnical.analysisComplete, true);
  assert.equal(failedTechnical.technicalFailed, true);
  assert.equal(failedTechnical.phase, 'job_succeeded_analysis_complete_fail');

  const passedTechnical = api.getLocalQcResultStatus({
    status: 'succeeded',
    result: { analysis_status: 'succeeded', technical_verdict: 'pass' },
  });
  assert.equal(passedTechnical.phase, 'job_succeeded_analysis_complete_pass');

  const jobError = api.getLocalQcResultStatus({ status: 'failed', error: { message: 'ffprobe failed' } });
  assert.equal(jobError.jobSucceeded, false);
  assert.equal(jobError.analysisComplete, false);
  assert.equal(jobError.phase, 'job_failed');

  const interrupted = api.getLocalQcResultStatus({ status: 'interrupted' });
  assert.equal(interrupted.phase, 'job_cancelled');
});

test('normalizeJob preserves the QC result fields needed by the result panel', () => {
  const job = api.normalizeJob({
    id: 'job-qc-1',
    status: 'succeeded',
    payload: { run_id: 'run-1', stage: 'qc', assembly_attempt_id: 'attempt-1', variant: 'captioned' },
    result: {
      assembly_attempt_id: 'attempt-1',
      variant: 'captioned',
      provider: 'local_ffmpeg_qc',
      actual_cost: 0,
      analysis_status: 'succeeded',
      technical_verdict: 'fail',
      duration_ms: 321,
      checks: { codec: { passed: false, reason: 'codec' } },
      media_facts: { duration_ms: 321, video_codec: 'h264' },
      artifacts: [{ name: 'technical-qc.json', kind: 'document' }],
    },
  });
  assert.equal(job.result?.provider, 'local_ffmpeg_qc');
  assert.equal(job.result?.actualCost, 0);
  assert.equal(job.result?.analysisStatus, 'succeeded');
  assert.equal(job.result?.technicalVerdict, 'fail');
  assert.equal(job.result?.durationMs, 321);
  assert.equal(job.result?.checks?.[0]?.name, 'codec');
  assert.equal(job.result?.mediaFacts.video_codec, 'h264');
  assert.equal(job.assemblyAttemptId, 'attempt-1');
  assert.equal(job.variant, 'captioned');
  assert.equal(job.result?.assemblyAttemptId, 'attempt-1');
  assert.equal(job.result?.variant, 'captioned');
});

test('normalizeRun retains QC selection lineage and does not collapse variants', () => {
  const run = api.normalizeRun({
    id: 'run-1',
    requested_stages: ['assembly', 'qc'],
    stage_attempts: [
      {
        id: 'qc-clean',
        stage: 'qc',
        status: 'succeeded',
        payload: { assembly_attempt_id: 'assembly-1', variant: 'clean' },
        result: { assembly_attempt_id: 'assembly-1', variant: 'clean' },
      },
      {
        id: 'qc-captioned',
        stage: 'qc',
        status: 'succeeded',
        payload: { assembly_attempt_id: 'assembly-2', variant: 'captioned' },
        result: { assembly_attempt_id: 'assembly-2', variant: 'captioned' },
      },
    ],
  });
  assert.equal(run.stageAttempts[0].assemblyAttemptId, 'assembly-1');
  assert.equal(run.stageAttempts[0].variant, 'clean');
  assert.equal(run.stageAttempts[1].assemblyAttemptId, 'assembly-2');
  assert.equal(run.stageAttempts[1].variant, 'captioned');
});

test('QC job selection ignores a newer attempt or different variant', () => {
  const selection = { runId: 'run-1', assemblyAttemptId: 'assembly-1', variant: 'clean' };
  assert.equal(api.isLocalQcJobForSelection({
    type: 'local_qc',
    payload: { run_id: 'run-1', assembly_attempt_id: 'assembly-1', variant: 'clean' },
  }, selection), true);
  assert.equal(api.isLocalQcJobForSelection({
    run_id: 'run-1', type: 'local_qc',
    payload: { assembly_attempt_id: 'assembly-2', variant: 'clean' },
  }, selection), false);
  assert.equal(api.isLocalQcJobForSelection({
    run_id: 'run-1', type: 'local_qc',
    result: { assembly_attempt_id: 'assembly-1', variant: 'captioned' },
  }, selection), false);
});
