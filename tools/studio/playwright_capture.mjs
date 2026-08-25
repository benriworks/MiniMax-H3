import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';
import { createRequire } from 'node:module';


const requireFromStudio = createRequire(
  new URL('../../studio/package.json', import.meta.url),
);
const { chromium } = requireFromStudio('playwright');
const playwrightPackage = requireFromStudio('playwright/package.json');

const MAX_RESULT_MESSAGES = 32;

const fail = (message) => {
  throw new Error(message);
};

const sha256 = (value) => crypto.createHash('sha256').update(String(value)).digest('hex').toUpperCase();

const readRequest = async (fileName) => {
  const value = JSON.parse(await fs.readFile(fileName, 'utf8'));
  const expected = ['actions', 'duration_ms', 'output_dir', 'settle_ms', 'url'];
  if (!value || typeof value !== 'object' || Array.isArray(value) || Object.keys(value).sort().join(',') !== expected.join(',')) {
    fail('invalid capture request');
  }
  if (typeof value.url !== 'string' || typeof value.output_dir !== 'string') fail('invalid capture request');
  if (!Number.isInteger(value.duration_ms) || !Number.isInteger(value.settle_ms) || !Array.isArray(value.actions)) fail('invalid capture request');
  return value;
};

const writeResult = async (fileName, value) => {
  const temporary = `${fileName}.partial`;
  await fs.writeFile(temporary, `${JSON.stringify(value)}\n`, { encoding: 'utf8', flag: 'wx' });
  await fs.rename(temporary, fileName);
};

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, Math.max(0, milliseconds)));

const loopbackTarget = (raw, allowedPort) => {
  try {
    const target = new URL(raw);
    return target.protocol === 'http:'
      && target.hostname === '127.0.0.1'
      && target.port === allowedPort
      && target.username === ''
      && target.password === ''
      && target.hash === '';
  } catch {
    return false;
  }
};

const main = async () => {
  if (process.argv.length !== 4) fail('usage: playwright_capture.mjs request.json result.json');
  const requestPath = path.resolve(process.argv[2]);
  const resultPath = path.resolve(process.argv[3]);
  const request = await readRequest(requestPath);
  const outputDirectory = path.resolve(request.output_dir);
  const target = new URL(request.url);
  await fs.mkdir(outputDirectory, { recursive: false });

  let browser;
  let context;
  let closing = false;
  const messageHashes = [];
  const recordMessage = (value) => {
    if (messageHashes.length < MAX_RESULT_MESSAGES) messageHashes.push(sha256(value));
  };
  const close = async () => {
    if (closing) return;
    closing = true;
    try { await context?.close(); } catch {}
    try { await browser?.close(); } catch {}
  };
  process.once('SIGINT', () => { void close().finally(() => process.exit(130)); });
  process.once('SIGTERM', () => { void close().finally(() => process.exit(143)); });

  try {
    browser = await chromium.launch({
      headless: true,
      args: [
        '--disable-background-networking',
        '--disable-component-update',
        '--disable-default-apps',
        '--disable-extensions',
        '--disable-sync',
        '--no-first-run',
        '--no-proxy-server',
      ],
    });
    const browserVersion = browser.version();
    context = await browser.newContext({
      acceptDownloads: false,
      bypassCSP: false,
      colorScheme: 'light',
      locale: 'ja-JP',
      recordVideo: {
        dir: outputDirectory,
        size: { width: 1080, height: 1920 },
      },
      reducedMotion: 'no-preference',
      serviceWorkers: 'block',
      viewport: { width: 1080, height: 1920 },
    });
    await context.route('**/*', async (route) => {
      if (loopbackTarget(route.request().url(), target.port)) {
        await route.continue();
      } else {
        recordMessage(`blocked:${route.request().resourceType()}:${route.request().url()}`);
        await route.abort('blockedbyclient');
      }
    });
    if (typeof context.routeWebSocket === 'function') {
      await context.routeWebSocket('**/*', (webSocketRoute) => {
        recordMessage(`blocked-websocket:${webSocketRoute.url()}`);
        webSocketRoute.close();
      });
    }
    const contextStarted = performance.now();
    const page = await context.newPage();
    context.on('page', (popup) => {
      if (popup !== page) void popup.close().catch(() => {});
    });
    page.on('console', (message) => {
      if (message.type() === 'error' || message.type() === 'warning') recordMessage(`console:${message.type()}:${message.text()}`);
    });
    page.on('pageerror', (error) => recordMessage(`pageerror:${error.message}`));
    page.setDefaultTimeout(2_000);
    page.setDefaultNavigationTimeout(10_000);
    await page.goto(request.url, { waitUntil: 'domcontentloaded', timeout: 10_000 });
    if (!loopbackTarget(page.url(), target.port)) fail('navigation left the allowed loopback origin');
    if (request.settle_ms > 0) await delay(request.settle_ms);
    await page.screenshot({ path: path.join(outputDirectory, 'first-frame.png'), type: 'png' });
    const captureStarted = performance.now();
    const trimStartMs = Math.max(0, Math.round(captureStarted - contextStarted));
    for (const action of request.actions) {
      await delay(captureStarted + action.at_ms - performance.now());
      if (action.type === 'scroll') {
        await page.mouse.wheel(0, action.delta_y);
      } else if (action.type === 'click') {
        await page.locator(action.selector).click({ timeout: 2_000 });
      } else if (action.type === 'press') {
        await page.locator(action.selector).press(action.key, { timeout: 2_000 });
      } else {
        fail('unsupported action');
      }
    }
    await delay(captureStarted + request.duration_ms - performance.now());
    await page.screenshot({ path: path.join(outputDirectory, 'last-frame.png'), type: 'png' });
    // Keep a short tail in the raw recording so the exact requested window
    // remains available to FFmpeg even when Chromium flushes its final frame
    // on a coarse timer.
    await delay(500);
    const video = page.video();
    await context.close();
    context = undefined;
    if (!video) fail('Playwright did not create a video');
    const generatedVideo = await video.path();
    const rawVideo = path.join(outputDirectory, 'playwright-raw.webm');
    await fs.rename(generatedVideo, rawVideo);
    const stat = await fs.stat(rawVideo);
    if (!stat.isFile() || stat.size < 1 || stat.size > 512 * 1024 * 1024) fail('recorded video size is invalid');
    await writeResult(resultPath, {
      schema_version: 1,
      playwright_version: String(playwrightPackage.version),
      browser_version: browserVersion,
      trim_start_ms: trimStartMs,
      requested_duration_ms: request.duration_ms,
      diagnostic_hashes: [...new Set(messageHashes)].slice(0, MAX_RESULT_MESSAGES),
      diagnostic_count: messageHashes.length,
      raw_video_bytes: stat.size,
    });
  } finally {
    await close();
  }
};

main().catch(async (error) => {
  const resultPath = process.argv[3] ? path.resolve(process.argv[3]) : undefined;
  if (resultPath) {
    try {
      await writeResult(resultPath, {
        schema_version: 1,
        error_code: 'playwright_capture_failed',
        error_sha256: sha256(error instanceof Error ? error.message : String(error)),
      });
    } catch {}
  }
  process.stderr.write('Playwright capture failed.\n');
  process.exitCode = 1;
});
