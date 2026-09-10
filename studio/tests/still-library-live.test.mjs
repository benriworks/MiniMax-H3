// REAL local integration: built Studio, Python API/SQLite, Chromium PNG worker.
// Deterministic test page only; not a Claude/Codex desktop capture claim.
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';
import test from 'node:test';
import { chromium } from 'playwright';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const repo = join(studioRoot, '..');
const output = join(studioRoot, 'output/playwright');
const id = () => 'still_' + crypto.randomUUID().replaceAll('-', '');

test('real still library: screenshot, edit, ZIP, retake, import, failures, responsive UI', { timeout: 150000 }, async () => {
  await mkdir(output, { recursive: true });
  const server = spawn('python', ['-m', 'tests.still_library_live_server'], { cwd: repo, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
  let stderr = ''; server.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
  let browser, inspectionPage;
  try {
    const reader = createInterface({ input: server.stdout });
    const info = await Promise.race([once(reader, 'line').then(([line]) => JSON.parse(line)), once(server, 'exit').then(() => { throw new Error('Server exited: ' + stderr); }), new Promise((_, reject) => { const timer = setTimeout(() => reject(new Error('Server startup timed out')), 15000); timer.unref(); })]);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1050 }, acceptDownloads: true });
    const page = await context.newPage(); inspectionPage = page; page.setDefaultTimeout(12000);
    const errors = []; page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(info.studio_url);
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('heading', { name: '静止画ライブラリ', exact: true }).waitFor();
    await page.getByLabel('ローカルURL', { exact: true }).fill(info.fixture_url + '/');
    await page.getByLabel('画像名', { exact: true }).fill('記事用・PC画面');
    await page.getByLabel('メモ', { exact: true }).fill('見出しと全体構図の確認');
    await page.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。').check();
    await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).click();
    await page.getByRole('button', { name: '記事用・PC画面を確認', exact: true }).waitFor();
    await page.waitForFunction(() => !document.querySelector('.still-card-select')?.disabled, null, { timeout: 30000 });
    await page.getByRole('button', { name: '記事用・PC画面を確認', exact: true }).click();
    await page.getByLabel('保存画像の名前', { exact: true }).fill('記事用・見出し画面');
    await page.getByLabel('保存画像のメモ', { exact: true }).fill('原図を維持。説明は記事本文で補足する。');
    await page.getByRole('button', { name: '名前・メモを保存', exact: true }).click();
    await page.getByRole('heading', { name: /記事用・見出し画面.*メモ版 2/ }).waitFor();
    await page.getByLabel('画像と現在のメモに機密情報がなく、書き出してよいことを確認しました。').check();
    const downloadWait = page.waitForEvent('download');
    await page.getByRole('button', { name: 'PNG＋MarkdownをZIPで保存', exact: true }).click();
    await (await downloadWait).saveAs(join(output, 'still-library-article.zip'));
    await page.locator('dialog.still-library').evaluate((element) => { element.scrollTop = 0; });
    await page.locator('dialog.still-library').screenshot({ path: join(output, 'still-library-desktop.png') });
    await page.getByRole('button', { name: 'この条件で撮り直す', exact: true }).click();
    await page.getByRole('combobox', { name: '撮影範囲', exact: true }).selectOption('element');
    await page.getByLabel('CSSセレクター', { exact: true }).fill('#article-example');
    await page.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。').check();
    await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).click();
    await page.getByRole('button', { name: '記事用・見出し画面・撮り直しを確認', exact: true }).waitFor();
    await page.waitForFunction(() => document.querySelectorAll('.still-card-select:not(:disabled)').length === 2, null, { timeout: 30000 });

    const apiGet = async (path) => { const response = await context.request.get(info.studio_url + path); assert.equal(response.status(), 200); return response.json(); };
    const waitDone = async (imageId) => {
      for (let i = 0; i < 45; i++) {
        const value = await apiGet('/api/stills/' + imageId);
        if (!['queued', 'running'].includes(value.status)) return value;
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      throw new Error('Capture did not terminate');
    };
    const capture = async (source) => {
      const imageId = id();
      const response = await context.request.post(info.studio_url + '/api/stills', { headers: { Origin: info.studio_url }, data: { id: imageId, title: '実撮影API検証', memo: '', parent_id: null, source, confirm_capture: true } });
      assert.equal(response.status(), 202, await response.text());
      return waitDone(imageId);
    };
    const web = { kind: 'web', url: info.fixture_url + '/', viewport: 'mobile', area: 'fullpage', selector: '' };
    const mobile = await capture(web); assert.equal(mobile.ready, true); assert.equal(mobile.media.width, 390); assert.ok(mobile.media.height > 844);
    const sources = await apiGet('/api/stills/sources');
    const imported = await capture({ kind: 'artifact', artifact_id: sources.items[0].id }); assert.equal(imported.ready, true); assert.equal(imported.media.width, 480);
    for (const scenario of ['failure', 'remote', 'large']) {
      const rejected = await capture({ ...web, url: info.fixture_url + '/' + scenario });
      assert.equal(rejected.ready, false, scenario); assert.equal(rejected.status, 'failed', scenario);
      const file = await context.request.get(info.studio_url + '/api/stills/' + rejected.id + '/file'); assert.equal(file.status(), 409);
    }
    const library = await apiGet('/api/stills');
    assert.equal(library.total, 7); assert.equal(library.items.filter((item) => item.ready).length, 4);
    const retake = library.items.find((item) => item.parent_id); assert.ok(retake); assert.ok(retake.media.width < 1440);
    // Fault injection: real POST reaches the real backend, only its response is lost.
    let posts = 0;
    await page.route('**/api/stills', async (route) => {
      if (route.request().method() !== 'POST') { await route.continue(); return; }
      posts++; await route.fetch(); await route.abort('connectionfailed');
    });
    await page.getByLabel('画像名', { exact: true }).fill('応答喪失から復旧');
    await page.getByLabel('対象・機密情報を確認しました。撮影／コピーを許可します。').check();
    await page.getByRole('button', { name: '1枚撮影して保存', exact: true }).click();
    await page.getByRole('button', { name: '応答喪失から復旧を確認', exact: true }).waitFor({ timeout: 30000 });
    await page.waitForFunction(() => !localStorage.getItem('studio.still-library.pending.v1'), null, { timeout: 30000 });
    assert.equal(posts, 1, 'a lost response must not cause automatic resubmission');
    await page.unroute('**/api/stills');
    // Real queued/running Job cancellation; interrupted media stays inaccessible.
    const cancelId = id();
    const queued = await context.request.post(info.studio_url + '/api/stills', { headers: { Origin: info.studio_url }, data: { id: cancelId, title: '停止試験', memo: '', parent_id: null, source: web, confirm_capture: true } });
    assert.equal(queued.status(), 202); const cancelRecord = await queued.json();
    const stopped = await context.request.post(info.studio_url + '/api/jobs/' + cancelRecord.job_id + '/cancel', { headers: { Origin: info.studio_url }, data: { schema_version: 1 } });
    assert.equal(stopped.status(), 202);
    assert.equal((await waitDone(cancelId)).ready, false);
    await page.reload();
    await page.getByRole('button', { name: '静止画ライブラリ', exact: true }).click();
    await page.getByRole('button', { name: '記事用・見出し画面を確認', exact: true }).click();
    await page.getByLabel('保存画像のメモ', { exact: true }).waitFor();
    assert.equal(await page.getByLabel('保存画像のメモ', { exact: true }).inputValue(), '原図を維持。説明は記事本文で補足する。');
    await page.getByLabel('保存画像のメモ', { exact: true }).fill('未保存の編集');
    page.once('dialog', (dialog) => dialog.dismiss());
    await page.getByRole('button', { name: '閉じる', exact: true }).click();
    assert.equal(await page.locator('dialog.still-library').isVisible(), true);
    assert.equal(await page.getByLabel('保存画像のメモ', { exact: true }).inputValue(), '未保存の編集');
    page.once('dialog', (dialog) => dialog.accept());
    await page.getByRole('button', { name: '記事用・見出し画面を確認', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('textarea[aria-label="保存画像のメモ"]')?.value === '原図を維持。説明は記事本文で補足する。');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('dialog.still-library').evaluate((element) => { element.scrollTop = 0; });
    await page.locator('dialog.still-library').screenshot({ path: join(output, 'still-library-mobile.png') });
    await page.getByRole('button', { name: '保存画像へ ↓', exact: true }).click();
    await page.locator('dialog.still-library').screenshot({ path: join(output, 'still-library-mobile-gallery.png') });
    assert.equal(await page.locator('dialog.still-library').evaluate((element) => element.scrollWidth <= element.clientWidth + 1), true);
    assert.deepEqual(errors, []);
    await writeFile(join(output, 'still-library-live-report.json'), JSON.stringify({ ...info, ready: (await apiGet('/api/stills')).items.filter((item) => item.ready), failed: 3, cancellation_verified: true, response_loss_recovered: true, response_loss_posts: posts, dirty_edit_preserved: true, page_errors: errors, real_api: true, real_browser_capture: true, external_product_capture: false }, null, 2));
    await context.close();
  } catch (error) {
    if (inspectionPage && !inspectionPage.isClosed()) {
      await inspectionPage.screenshot({ path: join(output, 'still-library-failure.png'), fullPage: true });
      await writeFile(join(output, 'still-library-failure.txt'), await inspectionPage.locator('body').innerText());
      await writeFile(join(output, 'still-library-failure-aria.txt'), await inspectionPage.locator('dialog.still-library').ariaSnapshot());
    }
    throw error;
  } finally {
    await browser?.close();
    if (server.exitCode === null) { server.stdin.end('\n'); await Promise.race([once(server, 'exit'), new Promise((resolve) => { const timer = setTimeout(() => { server.kill(); resolve(); }, 12000); timer.unref(); })]); }
  }
});
