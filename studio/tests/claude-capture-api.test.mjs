import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const statusUrl = pathToFileURL(join(root, '.test-dist/status.js')).href;
const source = (await readFile(join(root, '.test-dist/api.js'), 'utf8')).replaceAll("from './status'", `from '${statusUrl}'`);
const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const requestId = 'claude_capture_' + 'a'.repeat(32);
const selectionToken = 't'.repeat(43); // Explicit fixture: never an actual window token.
const request = { requestId, selectionToken, durationMs: 15000, confirmCapture: true };
const inspection = { schema_version: 1, available: true, actual_capture_performed: false, selections: [{ selection_token: selectionToken, label: 'Claude 1', width: 1280, height: 720, expires_in_seconds: 60 }] };
const rawJob = () => ({ id: 'job_fixture', type: 'claude_window_capture', production_id: 'production_fixture', status: 'running', payload: { production_id: 'production_fixture', capture_request_id: requestId } });
const withFetch = async (fn, run) => {
  const previous = globalThis.fetch; globalThis.fetch = fn;
  try { return await run(); } finally { globalThis.fetch = previous; }
};

test('Claude inspect normalizes safe target labels and expiring memory-only tokens', () => {
  assert.deepEqual(module.normalizeClaudeCaptureInspection(inspection), { available: true, reason: undefined, targets: [{ selectionToken, label: 'Claude 1', width: 1280, height: 720 }], expiresInSeconds: 60 });
  for (const changed of [
    { ...inspection, actual_capture_performed: true },
    { ...inspection, available: false },
    { ...inspection, selections: [{ ...inspection.selections[0], label: 'Private conversation title' }] },
    { ...inspection, selections: [{ ...inspection.selections[0], selection_token: 'invalid' }] },
    { ...inspection, selections: [{ ...inspection.selections[0], expires_in_seconds: 301 }] },
  ]) assert.throws(() => module.normalizeClaudeCaptureInspection(changed));
});

test('Claude capture request is a closed snake_case contract with strict consent and receipt', () => {
  assert.deepEqual(module.buildClaudeCapturePayload({ ...request, extra: 'ignored', systemAudio: true }), { request_id: requestId, selection_token: selectionToken, duration_ms: 15000, confirm_capture: true });
  for (const patch of [{ confirmCapture: false }, { confirmCapture: 'true' }, { durationMs: 14999 }, { durationMs: 30001 }, { requestId: 'invalid' }, { selectionToken: 'bad' }]) assert.throws(() => module.buildClaudeCapturePayload({ ...request, ...patch }));
});

test('Terminal inspect uses its own endpoint, identity and label validation', async () => {
  const terminal = { ...inspection, provider: 'local_windows_terminal_still', cli_content_verified: false, selections: [{ ...inspection.selections[0], label: 'Windows Terminal 1' }] };
  assert.throws(() => module.normalizeClaudeCaptureInspection(terminal));
  assert.throws(() => module.normalizeClaudeCaptureInspection(inspection, 'terminal'));
  for (const patch of [{ provider: 'other' }, { cli_content_verified: true }, { selections: [{ ...terminal.selections[0], label: 'private tab' }] }]) {
    assert.throws(() => module.normalizeClaudeCaptureInspection({ ...terminal, ...patch }, 'terminal'));
  }
  await withFetch(async (url, init) => {
    assert.equal(url, '/api/stills/terminal/inspect'); assert.equal(init.body, '{}');
    return new Response(JSON.stringify(terminal), { status: 200 });
  }, async () => { assert.equal((await module.api.inspectTerminalStill()).targets[0].label, 'Windows Terminal 1'); });
});

test('inspect sends only its explicit empty request without invoking capture', async () => {
  const seen = [];
  await withFetch(async (url, init) => { seen.push([url, init]); return new Response(JSON.stringify(inspection), { status: 200 }); }, async () => {
    const result = await module.api.inspectClaudeCapture(); assert.equal(result.targets[0].selectionToken, selectionToken);
  });
  assert.equal(seen.length, 1); assert.equal(seen[0][0], '/api/capabilities/claude-capture/inspect');
  assert.equal(seen[0][1].method, 'POST'); assert.equal(seen[0][1].body, '{}');
});

test('capture POST and GET normalize exact production, Job kind and receipt lineage', async () => {
  const seen = [];
  await withFetch(async (url, init) => { seen.push([url, init]); return new Response(JSON.stringify(rawJob()), { status: 202 }); }, async () => {
    const accepted = await module.api.executeClaudeCapture('production_fixture', request);
    assert.equal(accepted.id, 'job_fixture'); assert.equal(accepted.type, 'claude_window_capture');
    assert.equal(accepted.productionId, 'production_fixture'); assert.equal(accepted.runId, undefined);
    const restored = await module.api.claudeCaptureJob('production_fixture', requestId); assert.equal(restored.id, accepted.id);
  });
  assert.equal(seen[0][0], '/api/productions/production_fixture/claude-captures');
  assert.deepEqual(JSON.parse(seen[0][1].body), module.buildClaudeCapturePayload(request));
  assert.equal(seen[1][0], `/api/productions/production_fixture/claude-captures/${requestId}`);
  assert.equal(seen[1][1].method, undefined);
});

test('wrong capture response production, kind or receipt rejects instead of accepting a foreign Job', async () => {
  for (const mutate of [
    (job) => { job.production_id = 'production_foreign'; job.payload.production_id = 'production_foreign'; },
    (job) => { job.type = 'local_screen_capture'; },
    (job) => { job.payload.capture_request_id = 'claude_capture_' + 'f'.repeat(32); },
  ]) {
    const value = rawJob(); mutate(value);
    await withFetch(async () => new Response(JSON.stringify(value), { status: 200 }), async () => {
      await assert.rejects(module.api.executeClaudeCapture('production_fixture', request), /対応を確認/);
      await assert.rejects(module.api.claudeCaptureJob('production_fixture', requestId), /照合/);
    });
  }
});

test('receipt 404 is unresolved, and API never automatically retries a lost POST', async () => {
  let calls = 0;
  await withFetch(async () => { calls += 1; return new Response('{}', { status: 404 }); }, async () => {
    assert.equal(await module.api.claudeCaptureJob('production_fixture', requestId), undefined);
  });
  assert.equal(calls, 1); calls = 0;
  await withFetch(async () => { calls += 1; throw new TypeError('fixture transport loss'); }, async () => {
    await assert.rejects(module.api.executeClaudeCapture('production_fixture', request), /応答を受信できません/);
  });
  assert.equal(calls, 1);
});

test('focus API accepts four decimal normalized coordinates and rejects extra precision or null', () => {
  assert.equal(module.isValidScreenFocusRegion({ x: 0.1234, y: 0.2, width: 0.5, height: 0.6 }), true);
  for (const value of [null, { x: 0.12345, y: 0.2, width: 0.5, height: 0.6 }, { x: 0.1, y: 0.1, width: 0.1999, height: 0.6 }]) assert.equal(module.isValidScreenFocusRegion(value), false);
});
