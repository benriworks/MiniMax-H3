// Small real render to exercise effects and report the safety gate verbatim.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..'), studio = path.join(root, 'studio');
const require = createRequire(path.join(studio, 'package.json'));
const {selectComposition, renderMedia} = require('@remotion/renderer');
const {chromium} = require('playwright');
const [bundleArg, outputArg, firstArg = '44', lastArg = '45'] = process.argv.slice(2);
const output = path.resolve(root, outputArg);
if (!output.startsWith(here + path.sep)) throw Error('Diagnostic output must stay in this series');
const state = JSON.parse(await fs.readFile(path.join(here, '01/state.json'), 'utf8'));
const inputProps = JSON.parse(await fs.readFile(path.join(root, state.output, 'props.json'), 'utf8'));
const serveUrl = path.resolve(root, bundleArg), browserExecutable = chromium.executablePath();
const composition = await selectComposition({serveUrl, id: 'CreatorShort', browserExecutable, inputProps});
try {
  await renderMedia({composition, serveUrl, browserExecutable, inputProps, outputLocation: output,
    codec: 'h264', pixelFormat: 'yuv420p', muted: true, concurrency: 1, overwrite: false,
    frameRange: [Number(firstArg), Number(lastArg)]});
  console.log(JSON.stringify({status: 'passed', output, frames: [firstArg, lastArg]}));
} catch (error) {
  const result = {status: 'failed', message: String(error), stack: error.stack};
  await fs.writeFile(output + '.error.json', JSON.stringify(result, null, 2) + '\n', {flag: 'wx'});
  console.error(JSON.stringify(result));
  process.exitCode = 1;
}
