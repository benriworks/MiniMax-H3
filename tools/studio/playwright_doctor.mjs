import fs from 'node:fs/promises';
import { createRequire } from 'node:module';


const requireFromStudio = createRequire(
  new URL('../../studio/package.json', import.meta.url),
);
const { chromium } = requireFromStudio('playwright');
const playwrightPackage = requireFromStudio('playwright/package.json');

const executablePath = chromium.executablePath();
const stat = await fs.stat(executablePath);
if (!stat.isFile() || stat.size < 1) throw new Error('Pinned Playwright Chromium is unavailable.');

let browser;
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
  process.stdout.write(`${JSON.stringify({
    playwright_version: String(playwrightPackage.version),
    chromium_executable_path: executablePath,
    chromium_version: browser.version(),
  })}\n`);
} finally {
  await browser?.close();
}
