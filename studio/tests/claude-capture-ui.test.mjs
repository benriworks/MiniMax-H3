// MOCK-ONLY acceptance: actual Studio React/API code, synthetic video, intercepted
// HTTP requests. This test never enumerates, captures or operates a real window.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir, readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test, { after, before } from 'node:test';
import { chromium } from 'playwright';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const baseUrl = process.env.STUDIO_MOCK_UI_URL || 'http://127.0.0.1:4179';
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(baseUrl)) throw new Error('Mock UI test requires an explicit loopback Vite URL.');
const output = join(root, 'output/playwright');
const token = 'm'.repeat(43); // Fixed fixture token, not an OS window capability.
let browser;
let server;
let video;

before(async () => {
  await mkdir(output, { recursive: true });
  // A caller may supply its dedicated Vite server; otherwise this test owns one.
  if (!process.env.STUDIO_MOCK_UI_URL) {
    const { createServer } = await import('vite');
    const { default: react } = await import('@vitejs/plugin-react');
    // Do not load the production proxy config or its optional development token.
    server = await createServer({ configFile: false, root, plugins: [react()], server: { host: '127.0.0.1', port: 4179, strictPort: true, proxy: {} } });
    await server.listen();
  }
  const fixturePath = join(output, 'claude-mock-synthetic.mp4');
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=0x173034:s=320x180:r=12', '-t', '15', '-an', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', fixturePath], { windowsHide: true });
  video = await readFile(fixturePath);
  browser = await chromium.launch({ headless: true });
});
after(async () => { await browser?.close(); await server?.close(); });

const fixturePage = async () => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const state = { production: undefined, job: undefined, posts: 0, inspections: 0, cancels: 0, receipts: 0, loseResponse: false, receiptMissing: false, forbidden: [], pageErrors: [], consoleErrors: [] };
  page.on('pageerror', (error) => state.pageErrors.push(error.message));
  page.on('console', (message) => { if (message.type() === 'error') state.consoleErrors.push(message.text()); });
  const artifact = { id: 'art_mock_claude', kind: 'video', name: 'claude-capture.mp4', url: '/mock/synthetic.mp4', duration_seconds: 15, metadata: { duration_seconds: 15 } };
  const completed = () => state.job?.status === 'succeeded';
  const jobValue = () => ({ ...state.job, result: completed() ? { artifacts: [artifact] } : {} });
  const detail = () => ({ ...state.production, artifacts: completed() ? [artifact] : [], runs: [], announcement_recipes: [], announcement_recipe_versions: [], announcement_executions: [] });
  await page.route('**/*', async (route) => {
    const request = route.request(); const url = new URL(request.url()); const path = url.pathname;
    if (url.origin !== baseUrl) { state.forbidden.push(request.url()); await route.abort(); return; }
    const json = (value, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(value) });
    if (path === '/mock/synthetic.mp4') {
      const range = /^bytes=(\d+)-(\d*)$/.exec(request.headers().range ?? '');
      const start = range ? Number(range[1]) : 0; const end = range?.[2] ? Math.min(Number(range[2]), video.length - 1) : video.length - 1;
      await route.fulfill({ status: range ? 206 : 200, contentType: 'video/mp4', headers: { 'Accept-Ranges': 'bytes', 'Content-Length': String(end - start + 1), ...(range ? { 'Content-Range': `bytes ${start}-${end}/${video.length}` } : {}) }, body: video.subarray(start, end + 1) }); return;
    }
    if (!path.startsWith('/api/')) { await route.continue(); return; }
    if (path === '/api/health') return json({ status: 'ok', healthy: true });
    if (path === '/api/providers/status') return json({ items: [] });
    if (path === '/api/jobs') return json({ items: state.job ? [jobValue()] : [] });
    if (path === '/api/productions' && request.method() === 'GET') return json({ items: state.production ? [state.production] : [] });
    if (path === '/api/productions' && request.method() === 'POST') {
      const body = request.postDataJSON(); state.production = { id: body.production_id, title: body.title, status: 'draft' };
      return json({ schema_version: 1, production: state.production }, 201);
    }
    if (path === '/api/capabilities/claude-capture/inspect') {
      state.inspections += 1;
      return json({ schema_version: 1, available: true, actual_capture_performed: false, selections: [{ selection_token: token, label: 'Claude 1', width: 1280, height: 720, expires_in_seconds: 60 }] });
    }
    if (path === `/api/productions/${state.production?.id}`) return json(detail());
    if (path === `/api/productions/${state.production?.id}/claude-captures` && request.method() === 'POST') {
      state.posts += 1;
      const body = request.postDataJSON();
      assert.equal(body.selection_token, token); assert.equal(body.confirm_capture, true);
      const persisted = await page.evaluate(() => JSON.stringify({ ...localStorage }));
      assert.ok(persisted.includes(body.request_id)); assert.ok(!persisted.includes(token));
      state.job = { id: 'job_mock_claude', type: 'claude_window_capture', status: 'running', production_id: state.production.id, payload: { production_id: state.production.id, capture_request_id: body.request_id } };
      if (state.loseResponse) { await route.abort('connectionfailed'); return; }
      return json(jobValue(), 202);
    }
    if (path.startsWith(`/api/productions/${state.production?.id}/claude-captures/`)) {
      state.receipts += 1;
      return state.receiptMissing ? json({ message: 'MOCK: receipt not found' }, 404) : json(jobValue());
    }
    if (path === '/api/jobs/job_mock_claude') return json(jobValue());
    if (path === '/api/jobs/job_mock_claude/cancel' && request.method() === 'POST') {
      state.cancels += 1; state.job.status = 'cancelled';
      return json({ schema_version: 1, cancel_requested: true, worker_retired: true, job: jobValue() }, 202);
    }
    state.forbidden.push(`${request.method()} ${path}`);
    return json({ message: `MOCK: unconfigured route ${path}` }, 501);
  });
  await page.goto(baseUrl);
  await page.getByRole('button', { name: '画面解説を作る', exact: true }).waitFor();
  assert.equal(await page.locator('vite-error-overlay').count(), 0);
  assert.ok((await page.locator('body').innerText()).trim().length > 0);
  return { page, state, close: () => context.close() };
};
const openPanel = async (page) => {
  await page.getByRole('button', { name: '画面解説を作る', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '画面で伝える、ひとつの操作' }); await dialog.waitFor(); return dialog;
};
const inspectAndConsent = async (dialog) => {
  await dialog.getByRole('button', { name: 'Claudeを確認', exact: true }).click();
  const start = dialog.getByRole('button', { name: 'このウィンドウを15秒収録する', exact: true }); await start.waitFor();
  assert.equal(await start.isDisabled(), true);
  await dialog.getByRole('checkbox', { name: /選択したウィンドウ内の会話/ }).check();
  assert.equal(await start.isEnabled(), true); return start;
};
const storedDraft = (page) => page.evaluate(() => {
  const entries = Object.entries(localStorage).filter(([key]) => key.startsWith('minimax-h3-studio.screen-explainer.v1:'));
  if (!entries.length) return undefined;
  const first = JSON.parse(entries[0][1]);
  return JSON.parse(localStorage.getItem(`minimax-h3-studio.screen-explainer.v1:${first.productionId}`) || entries[0][1]);
});
const evidence = async (page, name) => {
  await page.evaluate(() => {
    document.querySelector('[data-mock-evidence-badge]')?.remove();
    const badge = document.createElement('div'); badge.textContent = 'MOCK UI TEST — synthetic video / no real Claude capture';
    badge.dataset.mockEvidenceBadge = 'true';
    badge.style.cssText = 'position:fixed;bottom:8px;left:8px;z-index:9999999;color:white;background:#793b18;padding:8px;font:12px sans-serif;max-width:calc(100vw - 32px);box-sizing:border-box';
    document.querySelector('dialog[open]')?.append(badge);
  });
  await page.screenshot({ path: join(output, name) });
};

test('MOCK UI: explicit inspect/consent, close discards token, close never cancels, cancel is explicit', async () => {
  const { page, state, close } = await fixturePage();
  try {
    let dialog = await openPanel(page);
    await dialog.getByLabel('画面素材の取得方法').selectOption('claude_shared');
    assert.equal(state.inspections, 0); assert.equal(state.posts, 0);
    await inspectAndConsent(dialog);
    const beforeTheme = await storedDraft(page);
    await dialog.getByRole('combobox', { name: 'デザインテーマ', exact: true }).selectOption('claude_code_v1');
    assert.equal(await dialog.getByRole('checkbox', { name: /選択したウィンドウ内の会話/ }).isChecked(), true);
    assert.equal(await dialog.getByRole('button', { name: 'このウィンドウを15秒収録する', exact: true }).isEnabled(), true);
    assert.deepEqual((await storedDraft(page)).shots, beforeTheme.shots);
    assert.equal((await storedDraft(page)).screenTheme, 'claude_code_v1');
    assert.equal(state.inspections, 1); assert.equal(state.posts, 0);
    assert.equal(await dialog.getByText('独立した非公式の紹介用です。', { exact: true }).isVisible(), true);
    assert.ok(!(await page.evaluate(() => JSON.stringify({ ...localStorage }))).includes(token));
    await evidence(page, 'claude-mock-consent.png');
    await dialog.getByRole('button', { name: '画面解説を閉じる' }).click();
    dialog = await openPanel(page);
    assert.equal(await dialog.getByRole('combobox', { name: 'デザインテーマ', exact: true }).inputValue(), 'claude_code_v1');
    assert.equal(await dialog.getByRole('checkbox', { name: /選択したウィンドウ内の会話/ }).count(), 0);
    const start = await inspectAndConsent(dialog); await start.click();
    await page.waitForFunction(() => Object.values(localStorage).some((value) => value.includes('job_mock_claude')));
    assert.equal(state.posts, 1);
    await dialog.getByRole('button', { name: '画面解説を閉じる' }).click();
    assert.equal(state.cancels, 0);
    dialog = await openPanel(page);
    await dialog.getByRole('button', { name: '収録を停止する', exact: true }).click();
    await dialog.getByRole('button', { name: '停止要求済み', exact: true }).waitFor();
    assert.equal(state.cancels, 1); assert.equal(state.posts, 1);
    assert.ok(!(await page.evaluate(() => JSON.stringify({ ...localStorage }))).includes(token));
    assert.deepEqual(state.forbidden, []); assert.deepEqual(state.pageErrors, []);
  } finally { await close(); }
});

test('MOCK UI: grouped themes remain readable at desktop and 390px with no requests on selection', async (t) => {
  const { page, state, close } = await fixturePage();
  try {
    const dialog = await openPanel(page);
    const selector = dialog.getByRole('combobox', { name: 'デザインテーマ', exact: true });
    assert.deepEqual(await selector.locator('optgroup').evaluateAll((groups) => groups.map((group) => group.label)), ['標準', '製品別', '技術テーマ別']);
    assert.equal(await selector.inputValue(), 'neutral_v1');
    await selector.selectOption('claude_code_v1');
    await selector.scrollIntoViewIfNeeded();
    await evidence(page, 'screen-theme-selector-desktop.png');
    await page.setViewportSize({ width: 390, height: 960 });
    await selector.scrollIntoViewIfNeeded();
    const fits = await dialog.locator('.screen-explainer-theme').evaluate((element) => {
      const box = element.getBoundingClientRect();
      const control = element.querySelector('select').getBoundingClientRect();
      return { left: box.left >= 0, right: box.right <= window.innerWidth, text: element.scrollWidth <= element.clientWidth + 1, control: control.left >= box.left && control.right <= box.right };
    });
    assert.deepEqual(fits, { left: true, right: true, text: true, control: true });
    assert.equal(await dialog.getByText('独立した非公式の紹介用です。', { exact: true }).isVisible(), true);
    await evidence(page, 'screen-theme-selector-390.png');
    await selector.selectOption('technical_v1');
    assert.equal(await dialog.getByText('独立した非公式の紹介用です。', { exact: true }).count(), 0);
    assert.equal((await storedDraft(page)).screenTheme, 'technical_v1');
    assert.equal(state.posts, 0); assert.equal(state.inspections, 0); assert.equal(state.cancels, 0); assert.equal(state.receipts, 0);
    assert.deepEqual(state.forbidden, []); assert.deepEqual(state.pageErrors, []); assert.deepEqual(state.consoleErrors, []);
    assert.equal(await page.locator('vite-error-overlay').count(), 0);
    t.diagnostic(JSON.stringify({ mocked: 'all API endpoints; no capture or synthesis', viewport: [390, 960], pageErrors: state.pageErrors, consoleErrors: state.consoleErrors, remoteRequests: state.forbidden, capturePosts: state.posts }));
  } finally { await close(); }
});

test('MOCK UI: response loss survives reload, receipt GET resumes one artifact and focus uses percent precision', async () => {
  const { page, state, close } = await fixturePage();
  try {
    state.loseResponse = true;
    let dialog = await openPanel(page);
    await dialog.getByLabel('画面素材の取得方法').selectOption('claude_shared');
    const start = await inspectAndConsent(dialog); await start.click();
    await dialog.getByRole('alert').filter({ hasText: '応答を受信できません' }).waitFor();
    const first = await storedDraft(page); assert.equal(first.pending.operation, 'claude_capture');
    assert.match(first.sharedCaptureRequestId, /^claude_capture_[0-9a-f]{32}$/); assert.equal(state.posts, 1);
    await page.reload(); dialog = await openPanel(page);
    assert.equal(await dialog.getByLabel('画面素材の取得方法').inputValue(), 'claude_shared');
    state.receiptMissing = true;
    await dialog.getByRole('button', { name: '送信結果を再確認', exact: true }).click();
    await dialog.getByRole('alert').filter({ hasText: '受付を確認できません' }).waitFor();
    assert.equal(state.posts, 1);
    state.receiptMissing = false; state.job.status = 'succeeded';
    await dialog.getByRole('button', { name: '送信結果を再確認', exact: true }).click();
    await dialog.getByText('3場面の素材を取得しました。', { exact: false }).waitFor();
    await page.waitForFunction(() => [...document.querySelectorAll('.screen-explainer-dialog video')].length === 3 && [...document.querySelectorAll('.screen-explainer-dialog video')].every((video) => video.readyState >= 2 && !video.seeking));
    assert.deepEqual(await dialog.locator('video').evaluateAll((videos) => videos.map((video) => Math.round(video.currentTime))), [0, 5, 10]);
    await dialog.locator('video').evaluateAll((videos) => Promise.all(videos.map((video) => video.play())));
    await page.waitForFunction(() => [...document.querySelectorAll('.screen-explainer-dialog video')].every((video, index) => video.currentTime > index * 5 + 0.1));
    await dialog.locator('video').evaluateAll((videos) => videos.forEach((video) => video.pause()));
    const restored = await storedDraft(page);
    assert.equal(restored.sharedCaptureRequestId, first.sharedCaptureRequestId);
    assert.deepEqual(restored.shots.map((shot) => [shot.artifactId, shot.startMs]), [['art_mock_claude', 0], ['art_mock_claude', 5000], ['art_mock_claude', 10000]]);
    assert.equal(state.posts, 1); assert.equal(state.receipts, 2);
    await dialog.getByRole('combobox', { name: 'デザインテーマ', exact: true }).selectOption('technical_v1');
    const themed = await storedDraft(page);
    assert.deepEqual(themed.shots, restored.shots);
    assert.equal(themed.sharedCaptureRequestId, restored.sharedCaptureRequestId);
    assert.equal(themed.sharedCaptureJobId, restored.sharedCaptureJobId);
    assert.equal(themed.sharedCaptureArtifactId, restored.sharedCaptureArtifactId);
    assert.equal(state.posts, 1); assert.equal(state.receipts, 2);
    const card = dialog.locator('.screen-explainer-card').first();
    await card.getByText('詳細：画面の注目範囲', { exact: true }).click();
    await card.getByRole('checkbox', { name: '注目範囲を指定する', exact: true }).check();
    await card.getByLabel('左位置（%）').fill('12.34');
    const changed = await storedDraft(page); assert.equal(changed.shots[0].focusRegion.x, 0.1234);
    assert.equal(await card.getByLabel('左位置（%）').inputValue(), '12.34');
    await evidence(page, 'claude-mock-restored-focus.png');
    await dialog.getByRole('combobox', { name: 'デザインテーマ', exact: true }).selectOption('claude_editorial_v1');
    for (const checkbox of await dialog.getByRole('checkbox', { name: '再生して内容・秘密情報・文字の見やすさを確認した', exact: true }).all()) await checkbox.check();
    await dialog.getByRole('button', { name: /台本を整える/ }).click();
    const review = dialog.getByRole('region', { name: '構成チェック', exact: true });
    await review.waitFor();
    assert.equal(await review.locator('.screen-structure-beats > li').count(), 3);
    assert.equal(await review.getByText(/同じ素材・同じ注目範囲/).count(), 1);
    assert.equal((await storedDraft(page)).screenTheme, 'claude_editorial_v1');
    assert.deepEqual((await storedDraft(page)).shots.map(shot => [shot.artifactId, shot.startMs]), changed.shots.map(shot => [shot.artifactId, shot.startMs]));
    await review.scrollIntoViewIfNeeded();
    await evidence(page, 'screen-structure-review-desktop.png');
    await page.setViewportSize({ width: 390, height: 960 });
    await review.scrollIntoViewIfNeeded();
    assert.equal(await review.evaluate(element => element.scrollWidth <= element.clientWidth + 1), true);
    await evidence(page, 'screen-structure-review-390.png');
    assert.equal(state.posts, 1); assert.equal(state.receipts, 2);
    assert.ok(!(await page.evaluate(() => JSON.stringify({ ...localStorage }))).includes(token));
    assert.deepEqual(state.forbidden, []); assert.deepEqual(state.pageErrors, []);
  } finally { await close(); }
});
