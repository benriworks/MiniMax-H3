import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
const dist = join(dirname(fileURLToPath(import.meta.url)), '../.test-dist');
const apiSource = (await readFile(join(dist, 'api.js'), 'utf8')).replaceAll("from './status'", `from '${pathToFileURL(join(dist, 'status.js')).href}'`);
const apiUrl = `data:text/javascript;base64,${Buffer.from(apiSource).toString('base64')}`;
const contentSource = (await readFile(join(dist, 'contentWorkspaceApi.js'), 'utf8')).replaceAll("from './api'", `from '${apiUrl}'`);
const { contentApi, contentDiff, contentImageUrl } = await import(`data:text/javascript;base64,${Buffer.from(contentSource).toString('base64')}`);

test('editorial feedback keeps the proposal identity, operation id and optimistic revision', async () => {
  const old = globalThis.fetch;
  try {
    let request;
    globalThis.fetch = async (path, options) => {
      request = { path, options };
      return new Response(JSON.stringify({ project: { content_project_id: 'CONTENT_test', revision: 5 }, checks: {} }), { status: 200 });
    };
    const project = { content_project_id: 'CONTENT_test', revision: 4 };
    await contentApi.apply(project, 'feedback', { proposal_id: 'proposal_one', text: '2と3をまとめたい' }, 'op_same');
    assert.equal(request.path, '/api/content-projects/CONTENT_test/feedback');
    assert.deepEqual(JSON.parse(request.options.body), { operation_id: 'op_same', expected_revision: 4, data: { proposal_id: 'proposal_one', text: '2と3をまとめたい' } });
  } finally { globalThis.fetch = old; }
});

test('version comparison reports dependent production changes without revision-only noise', () => {
  const before = { revision: 1, research: [], assets: [{ asset_id: 'screen', version: 1 }], episodes: [] };
  assert.deepEqual(contentDiff(before, { ...before, revision: 2 }), []);
  assert.deepEqual(contentDiff(before, { ...before, assets: [{ asset_id: 'screen', version: 2 }], episodes: [{ episode_id: 'one' }] }), ['撮影・絵コンテ', '素材']);
  assert.equal(contentImageUrl('CONTENT_demo', { asset_id: 'screen', version: 3 }), '/api/content-projects/CONTENT_demo/assets/screen?version=3');
});
