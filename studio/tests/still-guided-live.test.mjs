// Real browser -> Studio HTTP -> SQLite -> local Chromium capture. Synthetic content only.
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
const id = (prefix) => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
test('guided capture: durable receipt, side-by-side review, adoption retry, stale rejection and original preservation', { timeout: 90000 }, async () => {
  const server = spawn('python', ['-m', 'tests.still_library_live_server'], { cwd: join(studio, '..'), windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let browser, page, stderr = '';
  server.stderr.on('data', (chunk) => { stderr += chunk; });
  const output = join(studio, 'output/playwright'); await mkdir(output, { recursive: true });
  try {
    const reader = createInterface({ input: server.stdout });
    const info = await Promise.race([once(reader, 'line').then(([line]) => JSON.parse(line)), once(server, 'exit').then(() => { throw new Error(stderr); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('startup timeout')), 15000); timer.unref(); })]);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 } });
    page = await context.newPage(); page.setDefaultTimeout(12000);
    const errors = []; page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(info.studio_url);
    const get = async (path) => { const r = await context.request.get(info.studio_url + path); assert.equal(r.status(), 200, await r.text()); return r.json(); };
    const post = async (path, data, status = 200) => { const r = await context.request.post(info.studio_url + path, { headers: { Origin: info.studio_url }, data }); assert.equal(r.status(), status, await r.text()); return r.json(); };
    const artifact = (await get('/api/stills/sources')).items[0];
    const original = await post('/api/stills', { id: id('still'), title: '既存の全体像', memo: '比較元のPNG原本', source: { kind: 'artifact', artifact_id: artifact.id }, parent_id: null, confirm_capture: true }, 202);
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('button', { name: '既存の全体像を確認', exact: true }).click();
    const before = await get('/api/stills/' + original.id);
    const plan = await post('/api/still-plans/' + id('plan'), { operation_id: id('planedit'), expected_revision: 0, title: '撮影から採用まで・検証用', steps: [
      { id: id('step'), title: '全体像を撮り直す', memo: '画面全体が見える構図を確認', source: { kind: 'web', url: info.fixture_url, viewport: 'desktop', area: 'viewport', selector: '' }, image: { id: before.id, revision: before.revision } },
      { id: id('step'), title: '結果・確認', memo: '', source: { kind: 'artifact', artifact_id: artifact.id }, image: null },
    ] });
    await page.getByRole('button', { name: '撮影手順を開く', exact: true }).click();
    await page.getByRole('combobox', { name: '保存した撮影手順', exact: true }).selectOption(plan.id);
    await page.getByText(/手順を保存済み · 版1/).waitFor();
    await page.getByRole('button', { name: '場面1の撮影を準備', exact: true }).click();
    assert.equal(await page.getByLabel('ローカルURL', { exact: true }).isDisabled(), true);
    assert.equal(await page.getByLabel('画像名', { exact: true }).inputValue(), plan.steps[0].title);
    assert.equal(await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).isDisabled(), true);
    let captures = 0;
    const capturePath = `**/api/still-plans/${plan.id}/steps/${plan.steps[0].id}/capture`;
    await page.route(capturePath, async (route) => { captures++; await route.fetch(); await route.abort('connectionfailed'); });
    await page.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。', { exact: true }).check();
    await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: '重複撮影は自動では行いません' }).waitFor();
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    await page.reload();
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('button', { name: '全体像を撮り直すを確認', exact: true }).click();
    await page.getByRole('button', { name: '比較・採用状況を確認', exact: true }).waitFor();
    assert.equal(captures, 1);
    await page.unroute(capturePath);
    const captured = (await get('/api/stills')).items.find((item) => item.plan_capture);
    assert.deepEqual(captured.plan_capture, { plan_id: plan.id, plan_revision: 1, step_id: plan.steps[0].id });
    assert.equal(captured.parent_id, before.id);
    assert.notEqual(captured.media.sha256, before.media.sha256);
    assert.equal((await get('/api/still-plans/' + plan.id)).revision, 1, 'capture cannot adopt');
    assert.equal(await page.evaluate(() => localStorage.getItem('studio.still-library.pending.v1')), null);

    const compare = page.getByRole('button', { name: '比較・採用状況を確認', exact: true });
    await compare.click();
    const approval = page.getByLabel('元画像と新画像を確認し、この場面への採用を許可します。', { exact: true });
    await approval.check(); // Auto-waits for both PNG load events.
    await page.locator('.still-capture-review').scrollIntoViewIfNeeded();
    await page.screenshot({ path: join(output, 'still-guided-comparison-desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.locator('.still-library').evaluate((element) => element.scrollWidth <= element.clientWidth + 2), true);
    await page.locator('.still-capture-review').evaluate((element) => element.scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: join(output, 'still-guided-comparison-mobile.png') });
    await page.getByAltText('今回撮影した画像', { exact: true }).evaluate((element) => element.closest('figure').scrollIntoView({ block: 'start' }));
    await page.screenshot({ path: join(output, 'still-guided-comparison-mobile-after.png') });
    await page.setViewportSize({ width: 1440, height: 1050 });
    // Unsaved image notes clear approval and block adoption until resolved.
    await page.getByLabel('保存画像のメモ', { exact: true }).fill('未保存');
    assert.equal(await approval.isDisabled(), true); assert.equal(await approval.isChecked(), false);
    await page.getByLabel('保存画像のメモ', { exact: true }).fill(captured.memo);
    await approval.check();
    const adoptionPath = `**/api/still-plans/${plan.id}/captures/${captured.id}/adopt`;
    const adoptionRequests = [];
    await page.route(adoptionPath, async (route) => {
      adoptionRequests.push(route.request().postDataJSON());
      if (adoptionRequests.length > 1) return route.continue();
      await route.fetch(); await route.abort('connectionfailed');
    });
    await page.getByRole('button', { name: 'この画像を場面に採用', exact: true }).click();
    await page.getByRole('button', { name: '同じ採用操作を再確認', exact: true }).waitFor();
    assert.equal(adoptionRequests.length, 1, 'no automatic adoption retry');
    await page.getByRole('button', { name: '同じ採用操作を再確認', exact: true }).click();
    await page.getByText(/手順を保存済み · 版2/).waitFor();
    assert.equal(adoptionRequests.length, 2); assert.deepEqual(adoptionRequests[0], adoptionRequests[1]);
    await page.unroute(adoptionPath);
    const adopted = await get('/api/still-plans/' + plan.id);
    assert.equal(adopted.steps[0].image.id, captured.id); assert.deepEqual(adopted.steps[1], plan.steps[1]);
    assert.equal(adopted.history.length, 2);
    assert.equal((await get('/api/stills/' + before.id)).media.sha256, before.media.sha256);
    // Capture a second candidate, then change the plan in another client.
    await page.getByRole('button', { name: '場面1の撮影を準備', exact: true }).click();
    await page.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。', { exact: true }).check();
    const receipt = page.waitForResponse((response) => response.url().endsWith(`/steps/${plan.steps[0].id}/capture`) && response.request().method() === 'POST');
    await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).click();
    const next = await (await receipt).json();
    await page.locator('.still-card').filter({ has: page.locator(`img[src="/api/stills/${next.id}/file"]`) }).getByRole('button').click();
    await post('/api/still-plans/' + plan.id, { operation_id: id('planedit'), expected_revision: 2, title: '別画面で変更済み', steps: adopted.steps });
    await compare.click();
    await page.getByText(/撮影後に手順が更新されました/).waitFor();
    assert.equal(await page.getByRole('button', { name: 'この画像を場面に採用', exact: true }).isDisabled(), true);
    assert.equal((await get('/api/still-plans/' + plan.id)).revision, 3);
    assert.deepEqual(errors, []);
  } catch (error) { if (page) await page.screenshot({ path: join(output, 'still-guided-failure.png') }).catch(() => {}); throw error; }
  finally { if (browser) await browser.close(); server.stdin.end('\n'); await Promise.race([once(server, 'exit'), new Promise((resolve) => { const timer = setTimeout(() => { server.kill(); resolve(); }, 5000); timer.unref(); })]); }
});
