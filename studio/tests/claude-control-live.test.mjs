// Browser -> real Studio HTTP/SQLite -> synthetic native boundary, never actual Claude.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { mkdir, readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { chromium } from 'playwright';

const studio = join(dirname(fileURLToPath(import.meta.url)), '..');
test('Claude preparation: explicit launch, inspect, input, tab, lost reply recovery, unsupported UI and mobile', { timeout: 90000 }, async () => {
  const server = spawn('python', ['-m', 'tests.claude_control_live_server'], { cwd: join(studio, '..'), windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let browser, stderr = ''; server.stderr.on('data', (chunk) => { stderr += chunk; });
  try {
    const reader = createInterface({ input: server.stdout });
    const info = await Promise.race([once(reader, 'line').then(([line]) => JSON.parse(line)), once(server, 'exit').then(() => { throw new Error(stderr); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('startup timeout')), 15000); timer.unref(); })]);
    assert.equal(info.native_boundary, 'synthetic_only');
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
    const page = await context.newPage(); page.setDefaultTimeout(12000);
    const errors = []; page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(info.studio_url);
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('combobox', { name: /^撮影元/ }).selectOption('claude');
    const panel = page.getByRole('region', { name: 'Claudeの画面を準備', exact: true });
    await panel.getByRole('button', { name: 'Claudeの画面準備を開く', exact: true }).click();
    assert.equal(await panel.getByRole('button', { name: 'Claudeを起動する', exact: true }).isDisabled(), true);
    const get = async (path) => { const response = await context.request.get(info.studio_url + path); assert.equal(response.status(), 200, await response.text()); return response.json(); };
    assert.equal((await get('/api/claude-control')).items.length, 0);
    await panel.getByLabel('今回、公式Claudeの起動を許可します。', { exact: true }).check();
    await panel.getByRole('button', { name: 'Claudeを起動する', exact: true }).click();
    await panel.getByRole('status').filter({ hasText: 'Claudeの起動要求：実画面で結果確認が必要' }).waitFor();
    assert.equal((await get('/api/claude-control')).items.length, 1);
    const inspect = async () => {
      await panel.getByRole('button', { name: 'Claudeウィンドウを確認', exact: true }).click();
      await panel.getByRole('radio').check();
      await panel.getByLabel('選択したClaudeの操作対象確認を許可します。', { exact: true }).check();
      await panel.getByRole('button', { name: 'タブ・入力欄を確認', exact: true }).click();
    };
    await inspect();
    await panel.getByRole('combobox', { name: /^操作するタブ・入力欄/ }).selectOption('B'.repeat(64));
    await panel.getByText('入力方式：互換入力（Legacy SetValue）', { exact: false }).waitFor();
    const diagnostics = panel.getByRole('region', { name: 'Claude操作の確認結果', exact: true });
    await diagnostics.getByText('取得方式と診断（会話・入力文なし）', { exact: true }).click();
    const downloadEvent = page.waitForEvent('download');
    await diagnostics.getByRole('button', { name: '診断JSONを保存', exact: true }).click();
    const download = await downloadEvent;
    assert.equal(download.suggestedFilename(), 'claude-control-diagnostics.json');
    const report = JSON.parse(await readFile(await download.path(), 'utf8'));
    assert.deepEqual(report, { report_version: 1, engine: 'uia3', view: 'raw', inspected_nodes: 180, documents: 2,
      hidden_nodes: 20, unsupported_editors: 0, supported_inputs: 1, supported_tabs: 1, evidence: 'inspection_only_not_action_acceptance' });
    await diagnostics.getByText('取得方式と診断（会話・入力文なし）', { exact: true }).click();
    await panel.getByLabel('Claudeに入力する文章（未送信）', { exact: true }).fill('テスト専用の入力文。3案をお願いします。');
    const input = panel.getByRole('button', { name: '未送信の文章を入力する', exact: true });
    assert.equal(await input.isDisabled(), true);
    await panel.getByLabel('対象と内容を確認し、今回の1回の操作を許可します。', { exact: true }).check();
    const output = join(studio, 'output/playwright'); await mkdir(output, { recursive: true });
    await panel.scrollIntoViewIfNeeded(); await page.screenshot({ path: join(output, 'claude-control-desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('.still-library').evaluate((element) => element.scrollWidth <= element.clientWidth + 2), true);
    await panel.getByRole('combobox', { name: /^操作するタブ・入力欄/ }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(output, 'claude-control-mobile.png') });
    await page.setViewportSize({ width: 1440, height: 1080 });
    let actions = 0;
    await page.route('**/api/claude-control/actions', async (route) => { actions++; await route.fetch(); await route.abort('connectionfailed'); });
    await input.click();
    await panel.getByRole('alert').filter({ hasText: '操作は自動再送しません' }).waitFor();
    // Opaque ID only persists. Draft and window selection never enter localStorage.
    const storage = await page.evaluate(() => JSON.stringify(localStorage));
    assert.ok(!storage.includes('テスト専用')); assert.ok(!storage.includes('inspection_token'));
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('combobox', { name: /^撮影元/ }).selectOption('claude');
    await panel.getByRole('status').filter({ hasText: '未送信の入力：操作結果を照合済み' }).waitFor();
    assert.equal(actions, 1);
    assert.equal(await page.evaluate(() => localStorage.getItem('studio.claude-control.pending.v1')), null);
    await page.unroute('**/api/claude-control/actions');
    assert.equal((await get('/api/claude-control')).items.length, 2);
    const capture = page.locator('.still-capture');
    assert.equal(await capture.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。', { exact: true }).isChecked(), false);
    assert.equal(await capture.getByRole('button', { name: '1枚撮影して保存', exact: true }).isDisabled(), true);
    await inspect();
    await panel.getByRole('combobox', { name: /^操作するタブ・入力欄/ }).selectOption('A'.repeat(64));
    await panel.getByLabel('対象と内容を確認し、今回の1回の操作を許可します。', { exact: true }).check();
    await panel.getByRole('button', { name: '選択したタブへ切り替える', exact: true }).click();
    await panel.getByRole('status').filter({ hasText: 'タブ切替：操作結果を照合済み' }).waitFor();
    assert.equal((await get('/api/claude-control')).items.length, 3);
    await panel.getByLabel('Claudeに入力する文章（未送信）', { exact: true }).fill('破棄確認の試験用');
    page.once('dialog', (dialog) => dialog.dismiss());
    await page.getByRole('combobox', { name: /^撮影元/ }).selectOption('terminal');
    assert.equal(await page.getByRole('combobox', { name: /^撮影元/ }).inputValue(), 'claude');
    assert.equal(await panel.getByLabel('Claudeに入力する文章（未送信）', { exact: true }).inputValue(), '破棄確認の試験用');
    await panel.getByLabel('Claudeに入力する文章（未送信）', { exact: true }).fill('');
    // UI-only unsupported response: proves no fallback button is exposed, not native compatibility.
    await page.route('**/api/claude-control/inspect', async (route) => {
      const response = await route.fetch(); const body = await response.json();
      await route.fulfill({ response, json: { ...body, controls: [], available: false, reason: 'controls_not_exposed', diagnostics: { ...body.diagnostics, supported_inputs: 0, supported_tabs: 0 } } });
    });
    await inspect();
    await panel.getByText('自動入力・切替は利用できません。操作対象を確認できていません。', { exact: true }).waitFor();
    assert.equal(await panel.getByRole('combobox', { name: /^操作するタブ・入力欄/ }).count(), 0);
    assert.equal((await get('/api/claude-control')).items.length, 3);
    await page.unroute('**/api/claude-control/inspect');
    await panel.getByRole('button', { name: '操作対象を選び直す', exact: true }).click();
    // Partial support must not be presented as a working input capability.
    await page.route('**/api/claude-control/inspect', async (route) => {
      const response = await route.fetch(); const body = await response.json();
      await route.fulfill({ response, json: { ...body, controls: body.controls.filter((item) => item.kind === 'tab'), diagnostics: { ...body.diagnostics, supported_inputs: 0, unsupported_editors: 2 } } });
    });
    await inspect();
    await diagnostics.getByText('タブ候補のみ取得しました。入力欄は確認できていません。', { exact: true }).waitFor();
    assert.equal(await panel.getByRole('combobox', { name: /^操作するタブ・入力欄/ }).locator('option').count(), 2);
    assert.equal(await panel.getByRole('button', { name: '未送信の文章を入力する', exact: true }).count(), 0);
    await diagnostics.scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(output, 'claude-control-diagnostics.png') });
    await page.getByRole('combobox', { name: /^撮影元/ }).selectOption('terminal');
    assert.equal(await panel.count(), 0);
    assert.deepEqual(errors, []);
  } finally {
    await browser?.close();
    if (server.exitCode === null) { server.stdin.end('stop\n'); await once(server, 'exit'); }
  }
});
