// Fresh, unauthenticated Chromium context. This is request routing, not an OS sandbox.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../../studio/package.json', import.meta.url));
const { chromium } = require('playwright');

let browser;
try {
  const requestPath = process.argv[2];
  const request = JSON.parse(await fs.readFile(requestPath, 'utf8'));
  const target = new URL(request.url);
  if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' || !target.port || Number(target.port) < 1024 || target.username || target.password || target.search || target.hash) throw new Error('target');
  const viewport = request.viewport === 'desktop' ? { width: 1440, height: 900 } : request.viewport === 'mobile' ? { width: 390, height: 844 } : null;
  if (!viewport || !['viewport', 'fullpage', 'element'].includes(request.area)) throw new Error('settings');
  browser = await chromium.launch({ headless: true, args: ['--disable-background-networking', '--disable-component-update', '--disable-default-apps', '--disable-extensions', '--disable-sync', '--no-first-run', '--no-proxy-server'] });
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, locale: 'ja-JP', acceptDownloads: false, serviceWorkers: 'block' });
  let blocked = 0, errors = 0;
  await context.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== target.origin || url.username || url.password) { blocked++; await route.abort(); }
    else await route.continue();
  });
  await context.routeWebSocket('**/*', (socket) => { socket.close(); });
  const page = await context.newPage();
  page.on('popup', (popup) => { void popup.close(); });
  page.on('pageerror', () => { errors++; });
  page.on('response', (response) => { if (response.status() >= 400) errors++; });
  page.on('requestfailed', () => { errors++; });
  page.setDefaultTimeout(8000);
  const response = await page.goto(target.href, { waitUntil: 'networkidle', timeout: 15000 });
  if (!response?.ok() || new URL(page.url()).origin !== target.origin) throw new Error('navigation');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  const options = { path: path.join(path.dirname(requestPath), 'image.png'), type: 'png', animations: 'disabled', caret: 'hide', timeout: 8000 };
  if (request.area === 'element') {
    if (typeof request.selector !== 'string' || !request.selector || request.selector.length > 200 || request.selector.includes('>>')) throw new Error('selector');
    const element = page.locator(`css=${request.selector}`);
    if (await element.count() !== 1) throw new Error('selector matches');
    const bounds = await element.boundingBox();
    if (!bounds || bounds.width * bounds.height > 16000000 || Math.max(bounds.width, bounds.height) > 12000) throw new Error('size');
    await element.screenshot(options);
  } else {
    const bounds = await page.evaluate(() => ({ width: Math.max(document.documentElement.scrollWidth, document.body?.scrollWidth ?? 0, innerWidth), height: Math.max(document.documentElement.scrollHeight, document.body?.scrollHeight ?? 0, innerHeight) }));
    if (request.area === 'fullpage' && (bounds.width * bounds.height > 16000000 || Math.max(bounds.width, bounds.height) > 12000)) throw new Error('size');
    await page.screenshot({ ...options, fullPage: request.area === 'fullpage' });
  }
  if (blocked || errors) throw new Error('incomplete page');
  await fs.writeFile(path.join(path.dirname(requestPath), 'capture-report.json'), JSON.stringify({ schema_version: 1, viewport, area: request.area, blocked_requests: blocked, page_errors: errors, playwright_version: require('playwright/package.json').version }));
} catch {
  // Never echo page text, request URL, network secrets or browser error detail.
  process.stderr.write('Still capture failed; check local page, resources and bounds.\n');
  process.exitCode = 1;
} finally { await browser?.close(); }
