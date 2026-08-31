import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);
const panelSource = await readFile(join(studioRoot, 'src', 'ReviewPanel.tsx'), 'utf8');

const productionId = `production_${'a'.repeat(32)}`;
const artifactId = `art_${'b'.repeat(32)}`;
const revisionId = `rev_${'c'.repeat(32)}`;
const runId = `run_${'d'.repeat(32)}`;
const cutId = `cut_${'b'.repeat(32)}`;
const reviewId = `review_${'e'.repeat(32)}`;
const actionId = `review_action_${'f'.repeat(32)}`;
const eventHash = '1'.repeat(64);

const identity = {
  artifact_id: artifactId,
  revision_id: revisionId,
  run_id: runId,
  cut_id: cutId,
  timecode_ms: 1250,
};

const reviewResponse = (overrides = {}) => ({
  schema_version: 1,
  production_id: productionId,
  review: {
    id: reviewId,
    status: 'open',
    category: 'creative',
    decision: 'pending',
    body: '後半の動きを増やす',
    actor: 'operator',
    created_at: '2026-09-01T00:00:00.000Z',
    updated_at: '2026-09-01T00:00:00.000Z',
    identity,
    actions: [],
    revision_plans: [],
  },
  action: {
    id: actionId,
    type: 'created',
    actor: 'operator',
    decision: 'pending',
    note: '',
    created_at: '2026-09-01T00:00:00.000Z',
    event_id: 1,
    event_hash: eventHash,
    revision_plan: null,
  },
  gates: {
    creative: { decision: 'pending', review_count: 1, open_count: 1, resolved_count: 0 },
    rights: { decision: 'pending', review_count: 0, open_count: 0, resolved_count: 0 },
    public_release: { decision: 'pending', review_count: 0, open_count: 0, resolved_count: 0 },
  },
  deduplicated: false,
  ...overrides,
});

test('review create payload is closed and binds exact artifact/revision/run/cut/timecode identity', () => {
  const payload = api.buildReviewCreatePayload({
    idempotencyKey: 'review-create-1',
    artifactId,
    revisionId,
    runId,
    cutId,
    timecodeMs: 1250,
    category: 'creative',
    body: '後半の動きを増やす',
    actor: 'operator',
    path: 'C:/private/clip.mp4',
    token: 'secret',
  });
  assert.deepEqual(payload, {
    schema_version: 1,
    idempotency_key: 'review-create-1',
    artifact_id: artifactId,
    revision_id: revisionId,
    run_id: runId,
    cut_id: cutId,
    timecode_ms: 1250,
    category: 'creative',
    body: '後半の動きを増やす',
    actor: 'operator',
  });
  assert.deepEqual(Object.keys(payload), [
    'schema_version', 'idempotency_key', 'artifact_id', 'revision_id', 'run_id',
    'cut_id', 'timecode_ms', 'category', 'body', 'actor',
  ]);
  assert.throws(() => api.buildReviewCreatePayload({ ...payload, artifactId: 'art_invalid' }), /artifact/);
});

test('review APIs use exact encoded routes and validate the returned identity', async () => {
  let capturedUrl;
  let capturedBody;
  globalThis.fetch = async (url, init) => {
    capturedUrl = url;
    capturedBody = JSON.parse(init.body);
    return new Response(JSON.stringify(reviewResponse()), {
      status: 201,
      headers: { 'Content-Type': 'application/json' },
    });
  };
  const result = await api.api.createReview(productionId, {
    idempotencyKey: 'review-create-1',
    artifactId,
    revisionId,
    runId,
    cutId,
    timecodeMs: 1250,
    category: 'creative',
    body: '後半の動きを増やす',
    actor: 'operator',
  });
  assert.equal(capturedUrl, `/api/productions/${productionId}/reviews`);
  assert.equal(capturedBody.cut_id, cutId);
  assert.equal(result.productionId, productionId);
  assert.equal(result.review.identity.cutId, cutId);
  assert.equal(result.gates.creative.openCount, 1);

  globalThis.fetch = async () => new Response(JSON.stringify(reviewResponse({ production_id: `production_${'9'.repeat(32)}` })), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
  await assert.rejects(
    () => api.api.createReview(productionId, {
      idempotencyKey: 'review-create-2', artifactId, revisionId, runId, cutId,
      timecodeMs: 1250, category: 'creative', body: '指摘', actor: 'operator',
    }),
    /identity/,
  );
});

test('revision plan response cannot claim a connected or successful render', async () => {
  const plan = {
    schema_version: 1,
    id: `review_plan_${'7'.repeat(32)}`,
    status: 'planned_not_executed',
    render_status: 'not_started',
    exact_cut_identity: identity,
    identity_digest: 'A'.repeat(64),
    affected_stages: ['video_generation', 'timeline', 'assembly', 'qc'],
    reuse_policy: 'reuse_all_other_exact_cut_artifacts',
    execution: {
      adapter: 'm4_cut_revision_job_v1',
      connected: true,
      status: 'succeeded',
      job_id: 'job_untrusted',
      endpoint_template: '/api/productions/{production_id}/cuts/{cut_id}/reruns',
      request: {},
    },
  };
  const response = reviewResponse({
    action: { ...reviewResponse().action, type: 'revision_plan_created', revision_plan: plan },
  });
  globalThis.fetch = async () => new Response(JSON.stringify(response), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
  await assert.rejects(
    () => api.api.createReviewRevisionPlan(productionId, reviewId, 'plan-1', 'operator'),
    /identity/,
  );
  assert.match(panelSource, /plan作成済み・render未実行/);
  assert.match(panelSource, /latestPlan\.execution\.status/);
  assert.doesNotMatch(panelSource, /executeReviewRevisionPlan|executeCutRevision/);
});
