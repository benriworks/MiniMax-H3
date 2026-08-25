import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const appSource = await readFile(join(studioRoot, 'src', 'App.tsx'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);

test('screen capture payload is closed, canonical, and snake_case', () => {
  const payload = api.buildLocalScreenCapturePayload({
    url: 'http://127.0.0.1:8765',
    durationMs: 5_000,
    settleMs: 500,
    actions: [
      { type: 'scroll', atMs: 1_000, deltaY: 720, script: 'ignored' },
      { type: 'click', at_ms: 2_000, selector: '#next', cookies: 'ignored' },
      { type: 'press', atMs: 3_000, selector: '#dialog', key: 'Escape' },
    ],
    headers: { Authorization: 'secret' },
    output_path: 'elsewhere.mp4',
    browser_args: ['--remote-debugging-port=1'],
  });
  assert.deepEqual(payload, {
    url: 'http://127.0.0.1:8765/',
    duration_ms: 5_000,
    settle_ms: 500,
    actions: [
      { type: 'scroll', at_ms: 1_000, delta_y: 720 },
      { type: 'click', at_ms: 2_000, selector: '#next' },
      { type: 'press', at_ms: 3_000, selector: '#dialog', key: 'Escape' },
    ],
  });
  assert.deepEqual(Object.keys(payload), ['url', 'duration_ms', 'settle_ms', 'actions']);
});

test('screen capture accepts only an explicit loopback origin', () => {
  const request = (url) => ({ url, durationMs: 1_000, settleMs: 0, actions: [] });
  for (const url of [
    'https://127.0.0.1:8765/',
    'http://localhost:8765/',
    'http://127.0.0.1/',
    'http://user:password@127.0.0.1:8765/',
    'http://127.0.0.1:8765/#secret',
    'file:///C:/secret',
    'javascript:alert(1)',
  ]) {
    assert.throws(() => api.buildLocalScreenCapturePayload(request(url)), /loopback|URL/);
  }
});

test('screen capture bounds timing and safe actions', () => {
  const base = { url: 'http://127.0.0.1:8765/', durationMs: 5_000, settleMs: 0 };
  assert.throws(() => api.buildLocalScreenCapturePayload({ ...base, durationMs: 999, actions: [] }), /1,000/);
  assert.throws(() => api.buildLocalScreenCapturePayload({ ...base, durationMs: 30_001, actions: [] }), /30,000/);
  assert.throws(() => api.buildLocalScreenCapturePayload({ ...base, settleMs: 10_001, actions: [] }), /10,000/);
  assert.throws(() => api.buildLocalScreenCapturePayload({ ...base, actions: [{ type: 'scroll', atMs: 5_000, deltaY: 1 }] }), /録画時間内/);
  assert.throws(() => api.buildLocalScreenCapturePayload({ ...base, actions: [{ type: 'press', atMs: 0, selector: 'body', key: 'A' }] }), /ナビゲーションキー/);
  assert.throws(() => api.buildLocalScreenCapturePayload({ ...base, actions: [{ type: 'script', atMs: 0, code: 'alert(1)' }] }), /scroll、click、press/);
});

test('normalizeJob preserves created_at for a newly queued capture', () => {
  const job = api.normalizeJob({
    id: 'job-new',
    run_id: 'run-a',
    stage: 'screen_capture',
    type: 'local_screen_capture',
    status: 'pending',
    created_at: '2026-08-25T01:00:00Z',
  });
  assert.equal(job.updatedAt, '2026-08-25T01:00:00Z');
});

test('normalizeJob preserves worker progress and phase for capture polling', () => {
  const job = api.normalizeJob({
    id: 'job-running',
    run_id: 'run-a',
    stage: 'screen_capture',
    type: 'local_screen_capture',
    status: 'running',
    progress: 60,
    progress_phase: 'transcoding',
  });
  assert.equal(job.progress, 60);
  assert.equal(job.progressPhase, 'transcoding');
});

test('screen capture selection prioritizes submitted and attempt-linked jobs over old terminal jobs', () => {
  const oldTerminal = api.normalizeJob({
    id: 'job-old',
    run_id: 'run-a',
    stage: 'screen_capture',
    type: 'local_screen_capture',
    status: 'succeeded',
    completed_at: '2026-08-25T02:00:00Z',
  });
  const newPending = api.normalizeJob({
    id: 'job-new',
    run_id: 'run-a',
    stage: 'screen_capture',
    type: 'local_screen_capture',
    status: 'pending',
    stage_attempt_id: 'attempt-new',
    created_at: '2026-08-25T01:00:00Z',
  });
  const attempt = { id: 'attempt-new', stage: 'screen_capture', status: 'pending', jobId: 'job-new', artifacts: [], raw: {} };
  const submitted = { ...newPending, id: 'job-submitted' };
  assert.equal(api.selectLocalScreenCaptureJob(submitted, attempt, [oldTerminal, newPending], 'run-a').id, 'job-submitted');
  assert.equal(api.selectLocalScreenCaptureJob(undefined, attempt, [oldTerminal, newPending], 'run-a').id, 'job-new');
  const knownJobIds = new Set([oldTerminal.id]);
  const freshJobs = [oldTerminal, newPending].filter((job) => !knownJobIds.has(job.id));
  assert.equal(api.selectLocalScreenCaptureJob(undefined, undefined, freshJobs, 'run-a').id, 'job-new');
  assert.equal(api.selectLocalScreenCaptureJob(undefined, { id: 'attempt-missing', stage: 'screen_capture', status: 'pending', artifacts: [], raw: {} }, [oldTerminal], 'run-a'), undefined);
  assert.equal(api.selectLocalScreenCaptureJob(undefined, undefined, [], 'run-a'), undefined);
});

test('screen capture UI exposes progress and keeps uncertain POST submissions locked', () => {
  assert.match(appSource, /role="progressbar" aria-label="画面収録の進捗"/);
  assert.match(appSource, /submissionUncertain/);
  assert.match(appSource, /受理済みJobを照合しました。再送は行いません。/);
  assert.match(appSource, /LOCAL_PLAYWRIGHT_STAGES = new Set\(\['screen_capture'\]\)/);
});

test('local_playwright run creation remains zero-cost and explicit', async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (_url, init) => {
    captured = JSON.parse(String(init.body));
    return new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    await api.api.createRun('production-a', {
      stages: ['screen_capture'],
      reusedStages: [],
      billableStages: [],
      requiresCostEstimate: false,
      currency: 'JPY',
      raw: {},
    }, {
      stages: ['screen_capture'],
      note: 'capture',
      allowPaidApi: false,
      executionProfile: 'local_playwright',
    });
    assert.equal(captured.execution_profile, 'local_playwright');
    assert.deepEqual(captured.estimated_cost, { amount: 0, currency: 'JPY' });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
