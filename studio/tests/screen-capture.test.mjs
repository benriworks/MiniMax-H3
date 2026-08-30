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

test('Windows native result keeps structural success separate from content sync', () => {
  const job = api.normalizeJob({
    id: 'job-native-complete',
    type: 'local_windows_capture',
    status: 'succeeded',
    result: {
      artifacts: [],
      structural_timing_verified: true,
      content_sync_verified: false,
      live_validation_required: true,
      validation_scope: 'container_timestamps_durations_and_wasapi_packet_clock_v1',
      public_release_ready: false,
      public_release_gate: 'blocked_pending_live_av_sync_validation',
    },
  });
  assert.equal(job.result.structuralTimingVerified, true);
  assert.equal(job.result.contentSyncVerified, false);
  assert.equal(job.result.liveValidationRequired, true);
  assert.equal(job.result.publicReleaseReady, false);
  assert.equal(job.result.publicReleaseGate, 'blocked_pending_live_av_sync_validation');

  const nativePanel = appSource.slice(
    appSource.indexOf('function WindowsCapturePanel'),
    appSource.indexOf('function ScreenCapturePanel'),
  );
  assert.match(nativePanel, /実内容A\/V同期/);
  assert.match(nativePanel, /実機での目視・試聴が完了するまで公開利用gateは保留/);
  assert.doesNotMatch(nativePanel, />VERIFIED OUTPUT</);
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

test('Windows native capability inspection posts an empty body and validates the ready v2 contract', async () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl;
  let capturedInit;
  globalThis.fetch = async (url, init) => {
    capturedUrl = String(url);
    capturedInit = init;
    return new Response(JSON.stringify({
      schema_version: 1,
      implementation_version: 'windows-capture-capability-v2',
      status: 'ready',
      foundation_ready: true,
      capture_execution_enabled: true,
      screen_capture_ready: true,
      system_audio_loopback_ready: true,
      explicit_confirmation_required: true,
      actual_capture_performed: false,
      reasons: [],
      helper: {
        available: true,
        doctor_ok: true,
        endpoint_active: true,
        loopback_initialized: true,
        recording_started: false,
        capture_command_available: true,
      },
      ffmpeg: { available: true, gdigrab_available: true, ffprobe_available: true },
      display: { target: 'primary_display', width: 2560, height: 1440 },
      tool_identity_digest: 'A'.repeat(64),
    }), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  try {
    const capability = await api.api.inspectWindowsCaptureCapability();
    assert.equal(capturedUrl, '/api/capabilities/windows-capture/inspect');
    assert.equal(capturedInit.method, 'POST');
    assert.equal(capturedInit.body, '{}');
    assert.equal(capability.status, 'ready');
    assert.equal(capability.captureExecutionEnabled, true);
    assert.equal(capability.actualCapturePerformed, false);
    assert.equal(capability.helper.recordingStarted, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Windows native capability inspection preserves safe partial diagnostics while blocked', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    schema_version: 1,
    implementation_version: 'windows-capture-capability-v2',
    status: 'blocked',
    foundation_ready: false,
    capture_execution_enabled: false,
    screen_capture_ready: true,
    system_audio_loopback_ready: false,
    explicit_confirmation_required: true,
    actual_capture_performed: false,
    reasons: ['system_audio_loopback_unavailable'],
    helper: {
      available: true,
      doctor_ok: false,
      endpoint_active: false,
      loopback_initialized: false,
      recording_started: false,
      capture_command_available: true,
    },
    ffmpeg: { available: true, gdigrab_available: true, ffprobe_available: true },
    display: { target: 'primary_display', width: 2560, height: 1440 },
    tool_identity_digest: 'A'.repeat(64),
  }), { status: 200, headers: { 'content-type': 'application/json' } });
  try {
    const capability = await api.api.inspectWindowsCaptureCapability();
    assert.equal(capability.status, 'blocked');
    assert.equal(capability.captureExecutionEnabled, false);
    assert.equal(capability.screenCaptureReady, true);
    assert.equal(capability.systemAudioLoopbackReady, false);
    assert.equal(capability.helper.captureCommandAvailable, true);
    assert.equal(capability.ffmpeg.ffprobeAvailable, true);
    assert.deepEqual(capability.reasons, ['system_audio_loopback_unavailable']);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Windows native capability UI states that inspection does not capture data', () => {
  assert.match(appSource, /診断は収録せず、固定helper・FFmpeg・既定再生音声・プライマリ画面の事前条件だけを確認します。/);
  assert.match(appSource, /実収録はこの診断と分離した明示操作です。/);
  assert.match(appSource, /収録せずに環境を確認/);
  assert.match(appSource, /画面収録を確認/);
  assert.match(appSource, /システム音声収録を確認/);
});

const nativeConsentIntent = (suffix) => ({
  schema_version: 1,
  consent_intent_id: `capture_consent_${suffix.repeat(32)}`,
  consent_token: 'A'.repeat(43),
  run_id: 'run-native',
  request_settings_digest: 'B'.repeat(64),
  issued_at: '2026-08-30T00:00:00.000Z',
  expires_at: '2026-08-30T00:01:00.000Z',
  expires_in_seconds: 60,
});

const nativeJob = (id, runId, consentIntentId) => api.normalizeJob({
  id,
  kind: 'local_windows_capture',
  status: 'queued',
  created_at: '2026-08-30T00:00:01.000Z',
  payload: {
    run_id: runId,
    stage: 'screen_capture',
    consent_intent_id: consentIntentId,
  },
});

test('Windows capture aborts a hung execute request before entering bounded reconciliation', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, init) => new Promise((_resolve, reject) => {
    init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
  });
  try {
    await assert.rejects(
      () => api.api.executeWindowsCapture(
        'run-native',
        { durationMs: 5_000, confirmCapture: true, confirmSystemAudio: true },
        'A'.repeat(43),
        5,
      ),
      (error) => api.isStudioApiResponseLoss(error),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Windows capture reconciliation accepts only the exact non-secret consent lineage', () => {
  const expectedIntent = nativeConsentIntent('a');
  const guard = api.createWindowsCaptureSubmissionGuard(expectedIntent, 1_000);
  const sameRunOtherTab = nativeJob('job-other-tab', 'run-native', nativeConsentIntent('b').consent_intent_id);
  const otherRunSameIntent = nativeJob('job-other-run', 'run-other', expectedIntent.consent_intent_id);
  const exact = nativeJob('job-exact', 'run-native', expectedIntent.consent_intent_id);

  assert.equal(exact.consentIntentId, expectedIntent.consent_intent_id);
  assert.equal(api.isWindowsCaptureJobForSelection(sameRunOtherTab, {
    runId: guard.runId,
    consentIntentId: guard.consentIntentId,
  }), false);
  assert.equal(api.isWindowsCaptureJobForSelection(otherRunSameIntent, {
    runId: guard.runId,
    consentIntentId: guard.consentIntentId,
  }), false);
  assert.deepEqual(api.reconcileWindowsCaptureSubmission(
    guard,
    [sameRunOtherTab, otherRunSameIntent],
    1_000,
  ).state, 'pending');
  const reconciled = api.reconcileWindowsCaptureSubmission(
    guard,
    [sameRunOtherTab, exact, otherRunSameIntent],
    1_000,
  );
  assert.equal(reconciled.state, 'matched');
  assert.equal(reconciled.job.id, 'job-exact');
});

test('Windows capture uncertain reconciliation is token-free, TTL-bound, and poll-bounded', () => {
  const guard = api.createWindowsCaptureSubmissionGuard(nativeConsentIntent('c'), 1_000);
  assert.deepEqual(Object.keys(guard).sort(), [
    'consentIntentId',
    'pollAttempts',
    'reconcileDeadlineMs',
    'runId',
  ]);
  assert.equal(JSON.stringify(guard).includes('A'.repeat(43)), false);
  assert.equal(guard.reconcileDeadlineMs, 61_000);

  let state = { state: 'pending', guard };
  for (let index = 0; index < api.WINDOWS_CAPTURE_RECONCILIATION_MAX_POLLS - 1; index += 1) {
    state = api.reconcileWindowsCaptureSubmission(state.guard, [], 1_000 + index);
    assert.equal(state.state, 'pending');
  }
  const bounded = api.reconcileWindowsCaptureSubmission(state.guard, [], 30_000);
  assert.equal(bounded.state, 'manual_review');
  assert.equal(api.reconcileWindowsCaptureSubmission(guard, [], 61_000).state, 'manual_review');
});

test('Windows capture UI leaves uncertain mode for manual review without selecting or cancelling another Job', () => {
  const nativePanel = appSource.slice(
    appSource.indexOf('function WindowsCapturePanel'),
    appSource.indexOf('function ScreenCapturePanel'),
  );
  assert.match(nativePanel, /reconcileWindowsCaptureSubmission\(guard, scopedJobs\)/);
  assert.match(nativePanel, /setSubmissionReviewRequired\(true\)/);
  assert.match(nativePanel, /setConfirmCapture\(false\)/);
  assert.match(nativePanel, /setConfirmSystemAudio\(false\)/);
  assert.match(nativePanel, /window\.setTimeout\(\(\) =>/);
  assert.match(nativePanel, /reconcileDeadlineMs - Date\.now\(\)/);
  assert.match(nativePanel, /window\.clearTimeout\(deadlineTimer\)/);
  assert.match(nativePanel, /受理状態は未確定です。自動照合と自動再送を停止しました。/);
  assert.doesNotMatch(nativePanel, /knownJobIds/);
});

test('Windows native capability response fails closed if capture was enabled or performed', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    schema_version: 1,
    implementation_version: 'windows-capture-capability-v2',
    status: 'ready',
    foundation_ready: true,
    capture_execution_enabled: true,
    screen_capture_ready: true,
    system_audio_loopback_ready: true,
    explicit_confirmation_required: true,
    actual_capture_performed: false,
    reasons: [],
    helper: { recording_started: false, capture_command_available: false },
    ffmpeg: { ffprobe_available: false },
    display: { target: 'primary_display', width: 2560, height: 1440 },
  }), { status: 200, headers: { 'content-type': 'application/json' } });
  try {
    await assert.rejects(() => api.api.inspectWindowsCaptureCapability(), /安全契約/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
