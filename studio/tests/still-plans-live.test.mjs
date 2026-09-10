// Real UI + Python API + SQLite + registered synthetic PNG. No user app capture.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { chromium } from 'playwright';

const studio = join(dirname(fileURLToPath(import.meta.url)), '..');
test('real capture plans: save, reorder, prepare without capture, reload and duplicate', { timeout: 90000 }, async () => {
  const server = spawn('python', ['-m', 'tests.still_library_live_server'], { cwd: join(studio, '..'), windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let browser, page, stderr = '';
  server.stderr.on('data', (chunk) => { stderr += chunk; });
  const output = join(studio, 'output/playwright'); await mkdir(output, { recursive: true });
  try {
    const reader = createInterface({ input: server.stdout });
    const info = await Promise.race([once(reader, 'line').then(([line]) => JSON.parse(line)), once(server, 'exit').then(() => { throw new Error(stderr); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('startup timeout')), 15000); timer.unref(); })]);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
    page = await context.newPage(); page.setDefaultTimeout(10000);
    const errors = []; page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(info.studio_url);
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('combobox', { name: '撮影元', exact: true }).selectOption('terminal');
    await page.getByRole('button', { name: '撮影手順を開く', exact: true }).click();
    await page.getByRole('button', { name: '撮影手順を新規作成', exact: true }).click();
    await page.getByLabel('手順の名前', { exact: true }).fill('CLI記事の素材');
    await page.getByLabel('場面1の説明', { exact: true }).fill('アプリ全体が見える構図');
    await page.getByRole('button', { name: '撮影手順を保存', exact: true }).click();
    await page.getByText(/手順を保存済み · 版1/).waitFor();
    await page.getByRole('button', { name: '場面1を下へ', exact: true }).click();
    await page.getByRole('button', { name: '撮影手順を保存', exact: true }).click();
    await page.getByText(/手順を保存済み · 版2/).waitFor();
    await page.getByRole('button', { name: '場面1の撮影を準備', exact: true }).click();
    assert.equal(await page.getByLabel('画像名', { exact: true }).inputValue(), '操作・入力');
    assert.equal(await page.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。', { exact: true }).isChecked(), false);
    assert.equal(await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).isDisabled(), true);
    const get = async (path) => { const r = await context.request.get(info.studio_url + path); assert.equal(r.status(), 200, await r.text()); return r.json(); };
    assert.equal((await get('/api/stills')).total, 0, 'prepare must not capture');
    const plans = await get('/api/still-plans'); assert.equal(plans.items.length, 1);
    const saved = await get('/api/still-plans/' + plans.items[0].id);
    assert.equal(saved.steps[0].title, '操作・入力'); assert.deepEqual(saved.steps[0].source, { kind: 'terminal' });
    assert.equal(saved.history.length, 2);
    await page.getByLabel('画像名', { exact: true }).fill('');
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('button', { name: '撮影手順を開く', exact: true }).click();
    await page.getByRole('combobox', { name: '保存した撮影手順', exact: true }).selectOption(saved.id);
    await page.getByText(/手順を保存済み · 版2/).waitFor();
    await page.getByRole('button', { name: '画像を外して手順を複製', exact: true }).click();
    await page.getByRole('button', { name: '撮影手順を保存', exact: true }).click();
    await page.getByText(/手順を保存済み · 版1/).waitFor();
    assert.equal((await get('/api/still-plans')).items.length, 2);
    await page.screenshot({ path: join(output, 'still-plans-desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('.still-library').evaluate((element) => element.scrollWidth <= element.clientWidth + 2), true);
    await page.screenshot({ path: join(output, 'still-plans-mobile.png') });
    assert.deepEqual(errors, []);
  } catch (error) { if (page) await page.screenshot({ path: join(output, 'still-plans-failure.png') }).catch(() => {}); throw error; }
  finally { if (browser) await browser.close(); server.stdin.end('\n'); await Promise.race([once(server, 'exit'), new Promise((resolve) => { const timer = setTimeout(() => { server.kill(); resolve(); }, 5000); timer.unref(); })]); }
});
