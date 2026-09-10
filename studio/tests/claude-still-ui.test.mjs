// MOCK native boundary only. No real Claude pixels; tests ephemeral selection UX.
import assert from 'node:assert/strict';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { chromium } from 'playwright';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
for (const kind of ['claude', 'terminal']) {
const label = kind === 'terminal' ? 'Windows Terminal' : 'Claude';
test(`MOCK ${label} still UI: explicit selection, expiry, no stored token, response-loss recovery and retake`, { timeout: 45000 }, async () => {
  const server = await createServer({ configFile: false, root, plugins: [react()], server: { host: '127.0.0.1', port: 0, proxy: {} } });
  await server.listen();
  const base = `http://127.0.0.1:${server.httpServer.address().port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage(); page.setDefaultTimeout(10000);
    let inspections = 0, posts = 0, lifetime = 1, record;
    const token = 'x'.repeat(43);
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      if (path === '/api/health') return json({ healthy: true });
      if (path === '/api/productions' || path === '/api/jobs' || path === '/api/providers/status') return json({ items: [] });
      if (path === '/api/stills/sources') return json({ items: [] });
      if (path === (kind === 'terminal' ? '/api/stills/terminal/inspect' : '/api/capabilities/claude-capture/inspect')) {
        inspections++;
        return json({ schema_version: 1, provider: 'local_windows_terminal_still', cli_content_verified: false, available: true, actual_capture_performed: false, selections: [{ label: `${label} 1`, selection_token: token, width: 1440, height: 900, expires_in_seconds: lifetime }] });
      }
      if (path === '/api/stills' && route.request().method() === 'POST') {
        posts++; const body = route.request().postDataJSON();
        assert.deepEqual(body.source, { kind, selection_token: token });
        const storage = await page.evaluate(() => JSON.stringify({ ...localStorage }));
        assert.ok(storage.includes(body.id)); assert.ok(!storage.includes(token));
        record = { id: body.id, title: body.title, memo: '', source: { kind }, parent_id: null, revision: 1, job_id: 'job_fixture', status: 'succeeded', ready: true, media: { width: 1440, height: 900, bytes: 100, sha256: 'a'.repeat(64) }, history: [] };
        return route.abort('connectionfailed');
      }
      if (path === '/api/stills') return json({ items: record ? [record] : [], total: record ? 1 : 0 });
      if (record && path === '/api/stills/' + record.id) return json(record);
      return json({ error: { message: 'fixture not found' } }, 404);
    });
    await page.goto(base);
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('combobox', { name: '撮影元', exact: true }).selectOption(kind);
    assert.equal(inspections, 0);
    await page.getByRole('button', { name: `${label}ウィンドウを確認`, exact: true }).click();
    await page.getByRole('radio', { name: new RegExp(`${label} 1`) }).check();
    await page.getByLabel('画像名', { exact: true }).fill('MOCK Claude still');
    await page.getByRole('checkbox', { name: '対象・機密情報を確認しました。撮影／コピーを許可します。', exact: true }).check();
    await page.getByText('選択の有効期限が切れました。ウィンドウを再確認してください。', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).isDisabled(), true);
    assert.equal(posts, 0);
    lifetime = 60;
    await page.getByRole('button', { name: `${label}ウィンドウを確認`, exact: true }).click();
    await page.getByRole('radio', { name: new RegExp(`${label} 1`) }).check();
    await page.getByRole('checkbox', { name: '対象・機密情報を確認しました。撮影／コピーを許可します。', exact: true }).check();
    await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).click();
    await page.getByRole('button', { name: 'MOCK Claude stillを確認', exact: true }).waitFor();
    await page.waitForFunction(() => !localStorage.getItem('studio.still-library.pending.v1'));
    assert.equal(posts, 1);
    assert.equal(await page.getByRole('radio').count(), 0, 'tokens must be discarded after dispatch');
    page.once('dialog', (dialog) => dialog.accept()); // Discard the retained request draft after response loss.
    await page.getByRole('button', { name: 'この条件で撮り直す', exact: true }).click();
    assert.equal(await page.getByRole('radio').count(), 0, 'retake must require a new selection');
    assert.equal(await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).isDisabled(), true);
    assert.ok(!(await page.evaluate(() => JSON.stringify({ ...localStorage }))).includes(token));
    await page.getByRole('button', { name: `${label}ウィンドウを確認`, exact: true }).click();
    await page.getByRole('radio', { name: new RegExp(`${label} 1`) }).waitFor();
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('combobox', { name: '撮影元', exact: true }).selectOption(kind);
    assert.equal(await page.getByRole('radio').count(), 0);
    assert.equal(posts, 1);
  } finally { await browser.close(); await server.close(); }
});
}
