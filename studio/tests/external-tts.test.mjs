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

const validDraft = {
  provider: 'elevenlabs',
  model_id: 'eleven_multilingual_v2',
  voice_id: ' voice-jp-1 ',
  script: ' first line\n\nsecond line ',
  voice_settings: {
    stability: 0.42,
    similarity: 0.81,
    style: 0.12,
    speaker_boost: false,
    speed: 1.05,
  },
  seed: 42,
  confirm_billable: true,
  ignored: 'must not cross the API boundary',
};

test('external narration payload is exact, normalized, and model_id is fixed', () => {
  const payload = api.buildExternalNarrationPayload(validDraft);
  assert.deepEqual(payload, {
    provider: 'elevenlabs',
    model_id: 'eleven_multilingual_v2',
    voice_id: 'voice-jp-1',
    segments: [{ text: 'first line' }, { text: 'second line' }],
    voice_settings: {
      stability: 0.42,
      similarity_boost: 0.81,
      style: 0.12,
      use_speaker_boost: false,
      speed: 1.05,
    },
    seed: 42,
    confirm_billable: true,
  });
  assert.deepEqual(Object.keys(payload), [
    'provider',
    'model_id',
    'voice_id',
    'segments',
    'voice_settings',
    'seed',
    'confirm_billable',
  ]);
});

test('external payload refuses a missing billable confirmation', () => {
  const normalized = api.normalizeExternalNarrationInput({ ...validDraft, confirm_billable: false });
  assert.ok(normalized.errors.some((error) => error.includes('課金対象')));
  assert.throws(() => api.buildExternalNarrationPayload({ ...validDraft, confirm_billable: false }), /課金対象/);
});

test('external normalization applies fixed model and voice-setting/seed limits', () => {
  const invalid = api.normalizeExternalNarrationInput({
    ...validDraft,
    model_id: 'other-model',
    voice_settings: { stability: 2, similarity: -1, style: 0, speed: 9 },
    seed: 4_294_967_296,
  });
  assert.ok(invalid.errors.some((error) => error.includes('model')));
  assert.ok(invalid.errors.some((error) => error.includes('stability')));
  assert.ok(invalid.errors.some((error) => error.includes('similarity')));
  assert.ok(invalid.errors.some((error) => error.includes('speed')));
  assert.ok(invalid.errors.some((error) => error.includes('seed')));
});

const eligibleRun = {
  execution_profile: 'elevenlabs_tts',
  requested_stages: ['narration', 'assembly', 'qc'],
  estimated_cost: { amount: 1.25, currency: 'USD' },
  latest_approval: { decision: 'approved', approved_max: { amount: 2, currency: 'USD' } },
};

test('external gate requires dedicated profile, narration, positive estimate, matching approval, and provider', () => {
  assert.equal(api.getExternalNarrationGate(eligibleRun, true).eligible, true);
  assert.equal(api.getExternalNarrationGate({ ...eligibleRun, execution_profile: 'external' }, true).profileOk, false);
  assert.equal(api.getExternalNarrationGate({ ...eligibleRun, estimated_cost: { amount: 0, currency: 'USD' } }, true).positiveEstimate, false);
  assert.equal(api.getExternalNarrationGate({ ...eligibleRun, latest_approval: undefined }, true).costApproved, false);
  assert.equal(api.getExternalNarrationGate(eligibleRun, false).providerConfigured, false);
});

test('external job normalization preserves provider task, character cost, and null USD actual cost', () => {
  const job = api.normalizeJob({
    id: 'job_external_1',
    status: 'running',
    stage: 'narration',
    result: {
      provider: 'elevenlabs',
      provider_task_id: 'provider-task-1',
      character_cost: 1234,
      actual_cost: null,
      artifacts: [{ id: 'audio-1', name: 'narration.wav', kind: 'audio', sha256: 'A'.repeat(64) }],
    },
  });
  assert.equal(job.result.providerTaskId, 'provider-task-1');
  assert.equal(job.result.characterCost, 1234);
  assert.equal(job.result.actualCostUsd, null);
  assert.equal(job.result.artifacts[0].sha256, 'A'.repeat(64));
});
