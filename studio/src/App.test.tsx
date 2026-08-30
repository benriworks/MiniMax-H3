// This file is executed by the Node contract-test runner, while the app
// tsconfig intentionally contains only browser DOM types.
// @ts-ignore node-only test dependency
import { readFileSync } from 'node:fs';
// @ts-ignore node-only test dependency
import { resolve } from 'node:path';
// @ts-ignore node-only test dependency
import { pathToFileURL } from 'node:url';
// @ts-ignore node-only test dependency
import assert from 'node:assert/strict';
// @ts-ignore node-only test dependency
import test from 'node:test';
import type { WindowsCaptureCapability } from './types';

declare const process: { cwd(): string };
declare const Buffer: { from(value: string): { toString(encoding: string): string } };

const appSource = readFileSync(resolve(process.cwd(), 'src', 'App.tsx'), 'utf8');
const nativePanelSource = appSource.slice(
  appSource.indexOf('function WindowsCapturePanel'),
  appSource.indexOf('function ScreenCapturePanel'),
);
const testDist = resolve(process.cwd(), '.test-dist');
const apiSource = readFileSync(resolve(testDist, 'api.js'), 'utf8');
const statusUrl = pathToFileURL(resolve(testDist, 'status.js')).href;
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);

const readyCapability: WindowsCaptureCapability = {
  schemaVersion: 1,
  implementationVersion: 'windows-capture-capability-v2',
  status: 'ready',
  captureExecutionEnabled: true,
  screenCaptureReady: true,
  systemAudioLoopbackReady: true,
  explicitConfirmationRequired: true,
  actualCapturePerformed: false,
  reasons: [],
  helper: {
    available: true,
    doctorOk: true,
    endpointActive: true,
    loopbackInitialized: true,
    recordingStarted: false,
    captureCommandAvailable: true,
  },
  ffmpeg: {
    available: true,
    gdigrabAvailable: true,
    ffprobeAvailable: true,
  },
  display: {
    target: 'primary_display',
    width: 2560,
    height: 1440,
  },
};

test('Windows native capture payload is exactly the seven-field wire contract', () => {
  const payload = api.buildWindowsCapturePayload({
    durationMs: 5_000,
    confirmCapture: true,
    confirmSystemAudio: true,
    ignored: 'must not cross the API boundary',
  });
  assert.deepEqual(payload, {
    schema_version: 1,
    target: 'primary_display',
    audio_mode: 'default_render_loopback',
    cursor_mode: 'hidden',
    duration_ms: 5_000,
    confirm_capture: true,
    confirm_system_audio: true,
  });
  assert.deepEqual(Object.keys(payload).sort(), [
    'audio_mode',
    'confirm_capture',
    'confirm_system_audio',
    'cursor_mode',
    'duration_ms',
    'schema_version',
    'target',
  ]);
});

const nativeRequest = {
  durationMs: 5_000,
  confirmCapture: true,
  confirmSystemAudio: true,
};

const consentResponse = {
  schema_version: 1,
  consent_intent_id: `capture_consent_${'a'.repeat(32)}`,
  consent_token: 'A'.repeat(43),
  run_id: 'run/native',
  request_settings_digest: 'B'.repeat(64),
  issued_at: '2026-08-30T00:00:00.000Z',
  expires_at: '2026-08-30T00:01:00.000Z',
  expires_in_seconds: 60,
};

test('Windows native consent issuance posts exact seven fields and validates the closed 201 response', async () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl = '';
  let capturedInit: RequestInit | undefined;
  globalThis.fetch = async (url, init) => {
    capturedUrl = String(url);
    capturedInit = init;
    return new Response(JSON.stringify(consentResponse), { status: 201, headers: { 'content-type': 'application/json' } });
  };
  try {
    const intent = await api.api.issueWindowsCaptureConsent('run/native', nativeRequest);
    assert.equal(capturedUrl, '/api/runs/run%2Fnative/windows-capture-consent-intents');
    assert.equal(capturedInit?.method, 'POST');
    assert.deepEqual(JSON.parse(String(capturedInit?.body)), {
      schema_version: 1,
      target: 'primary_display',
      audio_mode: 'default_render_loopback',
      cursor_mode: 'hidden',
      duration_ms: 5_000,
      confirm_capture: true,
      confirm_system_audio: true,
    });
    assert.deepEqual(intent, consentResponse);
    assert.equal('raw' in intent, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Windows native consent issuance rejects non-201 or expanded responses', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify(consentResponse), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
  try {
    await assert.rejects(
      () => api.api.issueWindowsCaptureConsent('run/native', nativeRequest),
      /status.*201/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.throws(
    () => api.parseWindowsCaptureConsentIntent({ ...consentResponse, unexpected: true }, 'run/native'),
    /consent intent応答を検証/,
  );
});

test('Windows native API marks a fetch without an HTTP response as response loss', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError('offline'); };
  try {
    await assert.rejects(
      () => api.api.executeWindowsCapture('run/native', nativeRequest, consentResponse.consent_token),
      (error: unknown) => api.isStudioApiResponseLoss(error),
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Windows native execute posts exactly the fixed seven fields plus the raw consent token', async () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl = '';
  let capturedInit: RequestInit | undefined;
  globalThis.fetch = async (url, init) => {
    capturedUrl = String(url);
    capturedInit = init;
    return new Response(JSON.stringify({
      id: 'job-native',
      run_id: 'run/native',
      stage: 'screen_capture',
      kind: 'local_windows_capture',
      status: 'pending',
    }), { status: 202, headers: { 'content-type': 'application/json' } });
  };
  try {
    const job = await api.api.executeWindowsCapture('run/native', nativeRequest, consentResponse.consent_token);
    const body = JSON.parse(String(capturedInit?.body));
    assert.equal(capturedUrl, '/api/runs/run%2Fnative/execute-windows-capture');
    assert.equal(capturedInit?.method, 'POST');
    assert.deepEqual(body, {
      schema_version: 1,
      target: 'primary_display',
      audio_mode: 'default_render_loopback',
      cursor_mode: 'hidden',
      duration_ms: 5_000,
      confirm_capture: true,
      confirm_system_audio: true,
      consent_token: consentResponse.consent_token,
    });
    assert.equal(job.id, 'job-native');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('Windows native capture requires both independent confirmations', () => {
  assert.equal(api.canStartWindowsCapture('local_windows_capture', readyCapability, false, false), false);
  assert.equal(api.canStartWindowsCapture('local_windows_capture', readyCapability, true, false), false);
  assert.equal(api.canStartWindowsCapture('local_windows_capture', readyCapability, false, true), false);
  assert.equal(api.canStartWindowsCapture('local_windows_capture', readyCapability, true, true), true);
  assert.equal(api.canStartWindowsCapture('local_windows_capture', readyCapability, true, true, true), false);
});

test('Windows native capture never auto-starts from mount or polling effects', () => {
  assert.match(nativePanelSource, /useState\(false\)/);
  assert.match(nativePanelSource, /onInspect=\{\(\) => void inspect\(\)\}/);
  assert.equal((nativePanelSource.match(/api\.executeWindowsCapture\(/g) ?? []).length, 2);
  for (const effect of nativePanelSource.matchAll(/useEffect\(\(\) => \{([\s\S]*?)\n  \},/g)) {
    assert.doesNotMatch(effect[1], /executeWindowsCapture|void execute\(\)/);
  }
});

test('Windows native result separates structural timing from live content sync', () => {
  const job = api.normalizeJob({
    id: 'job-native-complete',
    kind: 'local_windows_capture',
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
  assert.equal(job.result?.structuralTimingVerified, true);
  assert.equal(job.result?.contentSyncVerified, false);
  assert.equal(job.result?.liveValidationRequired, true);
  assert.equal(job.result?.publicReleaseReady, false);
  assert.equal(job.result?.publicReleaseGate, 'blocked_pending_live_av_sync_validation');
  assert.match(nativePanelSource, /実内容A\/V同期/);
  assert.match(nativePanelSource, /実機での目視・試聴が完了するまで公開利用gateは保留/);
  assert.doesNotMatch(nativePanelSource, />VERIFIED OUTPUT</);
});

test('Windows native capture start gate rejects a Playwright Run', () => {
  assert.equal(api.canStartWindowsCapture('local_playwright', readyCapability, true, true), false);
  assert.match(nativePanelSource, /canStartWindowsCapture\(/);
});

test('Windows native capture issues one fresh consent per click and never stores the bearer token', () => {
  assert.equal((nativePanelSource.match(/api\.issueWindowsCaptureConsent\(/g) ?? []).length, 1);
  assert.match(nativePanelSource, /if \(!isStudioApiResponseLoss\(error\)\) throw error/);
  assert.match(nativePanelSource, /consentToken = undefined/);
  assert.doesNotMatch(nativePanelSource, /useState[^\n]*consentToken/);
  assert.doesNotMatch(nativePanelSource, /setConsentToken|localStorage|sessionStorage|console\.log/);
});

test('Windows native capture cancellation posts an exact empty object', async () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl = '';
  let capturedInit: RequestInit | undefined;
  globalThis.fetch = async (url, init) => {
    capturedUrl = String(url);
    capturedInit = init;
    return new Response(JSON.stringify({
      job: {
        id: 'job-native',
        kind: 'local_windows_capture',
        status: 'cancelled',
        payload: { run_id: 'run-native', stage: 'screen_capture' },
      },
      cancel_requested: true,
      worker_retired: true,
    }), { status: 202, headers: { 'content-type': 'application/json' } });
  };
  try {
    const response = await api.api.cancelWindowsCapture('job/native');
    assert.equal(capturedUrl, '/api/jobs/job%2Fnative/cancel-windows-capture');
    assert.equal(capturedInit?.method, 'POST');
    assert.equal(capturedInit?.body, '{}');
    assert.equal(response.cancelRequested, true);
    assert.equal(response.workerRetired, true);
    assert.equal(response.job?.id, 'job-native');
  } finally {
    globalThis.fetch = originalFetch;
  }
});
