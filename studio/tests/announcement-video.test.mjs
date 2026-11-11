import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const appSource = await readFile(join(studioRoot, 'src', 'App.tsx'), 'utf8');
const quickCreateSource = await readFile(join(studioRoot, 'src', 'QuickCreateForm.tsx'), 'utf8');
const announcementSource = appSource.slice(
  appSource.indexOf('function AnnouncementVideoPanel'),
  appSource.indexOf('function DetailedTestVideoPanel'),
);
const stylesSource = await readFile(join(studioRoot, 'src', 'styles.css'), 'utf8');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);
const recoverySource = await readFile(join(testDist, 'announcementRecovery.js'), 'utf8');
const recovery = await import(`data:text/javascript;base64,${Buffer.from(recoverySource).toString('base64')}`);

const artifact = (value) => `art_${value.repeat(32)}`;
const recipeId = `announcement_${'a'.repeat(32)}`;
const memoryStorage = (initial = {}) => {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
};

const recipe = (overrides = {}) => ({
  schemaVersion: 1,
  name: '新サービス告知',
  templatePreset: 'shorts_ja_15s_v1',
  scenes: [
    { role: 'hook', videoArtifactId: artifact('1'), startMs: 0, endMs: 5000, volumePercent: 0, headline: 'その情報、\n届いていますか？', narration: '十五秒で、しっかり伝える。' },
    { role: 'message', videoArtifactId: artifact('2'), startMs: 0, endMs: 5000, volumePercent: 0, headline: '大切なことを\nひと目で', narration: '大切な情報を、ひと目で。' },
    { role: 'cta', videoArtifactId: artifact('3'), startMs: 0, endMs: 5000, volumePercent: 0, headline: '詳しくは\nプロフィールへ', narration: '続きはプロフィールから。' },
  ],
  voice: '',
  rate: 0,
  pronunciations: [],
  includeCaptioned: true,
  captionStylePreset: 'shorts_ja_large_v1',
  audioMixPreset: 'narration_only_v1',
  variant: 'captioned',
  ...overrides,
});

test('screen explainer uses hard cuts, preserves layout and accepts 15 through 30 seconds', () => {
  for (const seconds of [5, 7, 10]) {
    const source = recipe({ templatePreset: 'screen_explainer_ja_v1' });
    source.scenes.forEach((scene) => { scene.endMs = seconds * 1000; });
    const result = api.normalizeAnnouncementVideoInput(source);
    assert.deepEqual(result.errors, []);
    assert.equal(result.outputDurationMs, seconds * 3000);
    assert.equal(result.payload.template_preset, 'screen_explainer_ja_v1');
    assert.deepEqual(result.detailedRequest.clips.map((clip) => clip.transitionToNext), [null, null, null]);
    assert.deepEqual(result.detailedRequest.clips.map((clip) => clip.layoutPreset), Array(3).fill('screen_explainer_v1'));
    assert.deepEqual(result.detailedRequest.clips.map((clip) => clip.overlay.position), Array(3).fill('top'));
    assert.deepEqual(api.normalizeAnnouncementVideoInput(result.payload).errors, []);
  }
});

test('creator preset survives save/read normalization and compiles to instant kinetic headings', () => {
  const source=recipe({templatePreset:'shorts_creator_ja_v1'});
  const result=api.normalizeAnnouncementVideoInput(source);
  assert.deepEqual(result.errors,[]);
  assert.equal(result.outputDurationMs,15000);
  assert.deepEqual(result.detailedRequest.clips.map(c=>c.transitionToNext),[null,null,null]);
  assert.ok(result.detailedRequest.clips.every(c=>c.overlay.startMs===0&&c.overlay.stylePreset==='shorts_creator_v1'));
  assert.deepEqual(api.normalizeAnnouncementVideoInput(result.payload).recipe,result.recipe);
  source.scenes.forEach(scene=>{scene.endMs=10000;});
  assert.equal(api.normalizeAnnouncementVideoInput(source).outputDurationMs,30000);
  assert.deepEqual(api.normalizeAnnouncementVideoInput(source).errors,[]);
});

test('creator timeline rejects text which would have to shrink below the font floor', () => {
  const result=api.normalizeAnnouncementVideoInput(recipe({templatePreset:'shorts_creator_ja_v1'}));
  const clips=result.detailedRequest.clips;
  clips[0].overlay.text='大きな文字'.repeat(10);
  assert.ok(api.normalizeRemotionTimelineInput({clips}).errors.some(e=>e.includes('14文字')));
});

test('desktop capture passes only the named viewport preset', () => {
  const source = { url: 'http://127.0.0.1:8765/', durationMs: 5000, settleMs: 1000, actions: [], viewportPreset: 'desktop_16_9' };
  const result = api.normalizeLocalScreenCaptureInput(source);
  assert.deepEqual(result.errors, []);
  assert.equal(result.payload.viewport_preset, 'desktop_16_9');
  assert.ok(api.normalizeLocalScreenCaptureInput({ ...source, viewportPreset: 'arbitrary' }).errors.length);
  const { viewportPreset, ...legacy } = source;
  assert.equal(Object.hasOwn(api.normalizeLocalScreenCaptureInput(legacy).payload, 'viewport_preset'), false);
});

test('screen themes round-trip to every compiled clip and remain optional for legacy recipes', () => {
  const legacy = recipe({ templatePreset: 'screen_explainer_ja_v1' });
  const old = api.normalizeAnnouncementVideoInput(legacy);
  assert.equal(Object.hasOwn(old.recipe, 'screenTheme'), false);
  assert.equal(Object.hasOwn(old.payload, 'screen_theme'), false);
  assert.equal(old.detailedRequest.clips.some((clip) => Object.hasOwn(clip, 'screenTheme')), false);
  for (const screenTheme of ['neutral_v1', 'claude_desktop_v1', 'claude_code_v1', 'technical_v1', 'claude_editorial_v1']) {
    const result = api.normalizeAnnouncementVideoInput({ ...legacy, screenTheme });
    assert.deepEqual(result.errors, []);
    assert.equal(result.payload.screen_theme, screenTheme);
    assert.deepEqual(result.detailedRequest.clips.map((clip) => clip.screenTheme), Array(3).fill(screenTheme));
    assert.deepEqual(api.normalizeAnnouncementVideoInput(result.payload).recipe, result.recipe);
    assert.deepEqual(result.detailedRequest.segments, old.detailedRequest.segments);
    assert.equal(result.detailedRequest.voice, old.detailedRequest.voice);
    assert.deepEqual(result.recipe.scenes, old.recipe.scenes);
  }
});

test('unknown, null, object, and non-screen recipe themes fail closed', () => {
  for (const screenTheme of ['unknown', null, 0, {}, '']) {
    assert.throws(() => api.buildAnnouncementVideoRecipePayload(recipe({ templatePreset: 'screen_explainer_ja_v1', screenTheme })), /テーマ/);
    assert.throws(() => api.buildAnnouncementVideoRecipePayload({ ...recipe({ templatePreset: 'screen_explainer_ja_v1' }), screen_theme: screenTheme }), /テーマ/);
  }
  assert.throws(() => api.buildAnnouncementVideoRecipePayload(recipe({ screenTheme: 'claude_code_v1' })), /テーマ/);
});

test('announcement recipe compiles exact fixed HOOK -> MESSAGE -> CTA payload', () => {
  const normalized = api.normalizeAnnouncementVideoInput(recipe({ unsafePath: 'C:/nope.mp4' }));
  assert.deepEqual(normalized.errors, []);
  assert.equal(normalized.outputDurationMs, 14_500);
  assert.deepEqual(normalized.detailedRequest.clips.map((clip) => clip.transitionToNext), [
    { type: 'fade', durationMs: 250 },
    { type: 'fade', durationMs: 250 },
    null,
  ]);
  assert.deepEqual(normalized.detailedRequest.clips.map((clip) => clip.overlay.position), ['center', 'top', 'center']);
  const payload = api.buildAnnouncementVideoRecipePayload(recipe({ unsafePath: 'C:/nope.mp4' }));
  assert.deepEqual(Object.keys(payload), [
    'schema_version', 'name', 'template_preset', 'scenes', 'voice', 'rate',
    'pronunciations', 'include_captioned', 'caption_style_preset',
    'audio_mix_preset', 'variant',
  ]);
  assert.equal(payload.voice, null);
  assert.equal(payload.scenes[0].video_artifact_id, artifact('1'));
  assert.deepEqual(payload.scenes.map((scene) => scene.visual_preset), ['preserve_v1', 'preserve_v1', 'preserve_v1']);
  const sharpRecipe = recipe();
  sharpRecipe.scenes[1].visualPreset = 'h3_low_res_sharp_v1';
  assert.equal(api.buildAnnouncementVideoRecipePayload(sharpRecipe).scenes[1].visual_preset, 'h3_low_res_sharp_v1');
  assert.equal('unsafePath' in payload, false);
});

test('announcement preflight rejects role drift, unsafe headline, invalid trim, and non-15s duration', () => {
  const badRole = recipe();
  badRole.scenes[1].role = 'hook';
  assert.ok(api.normalizeAnnouncementVideoInput(badRole).errors.some((error) => error.includes('role')));

  for (const headline of ['あ'.repeat(11), 'one\ntwo\nthree', '不可視\u200b文字', 'A'.repeat(21)]) {
    const invalid = recipe();
    invalid.scenes[0].headline = headline;
    assert.ok(api.normalizeAnnouncementVideoInput(invalid).errors.some((error) => error.includes('HOOK')));
  }

  const short = recipe();
  short.scenes.forEach((scene) => { scene.endMs = 3_000; });
  assert.ok(api.normalizeAnnouncementVideoInput(short).errors.some((error) => error.includes('10〜20秒')));
  assert.throws(() => api.buildAnnouncementVideoRecipePayload(short), /10〜20秒/);

  const missingRole = recipe();
  delete missingRole.scenes[0].role;
  assert.ok(api.normalizeAnnouncementVideoInput(missingRole).errors.some((error) => error.includes('role')));
  assert.ok(api.normalizeAnnouncementVideoInput(recipe({ variant: 'typo' })).errors.some((error) => error.includes('QC対象')));
  assert.ok(api.normalizeAnnouncementVideoInput(recipe({ pronunciations: {} })).errors.some((error) => error.includes('配列')));
  const invalidVisualPreset = recipe();
  invalidVisualPreset.scenes[0].visualPreset = 'custom_strength';
  assert.ok(api.normalizeAnnouncementVideoInput(invalidVisualPreset).errors.some((error) => error.includes('映像補正preset')));
});

test('save, duplicate, and execute use exact encoded production/recipe routes and bodies', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    const body = JSON.parse(String(init.body));
    requests.push({ url, method: init.method, body, signal: init.signal });
    if (String(url).endsWith('/execute')) {
      return new Response(JSON.stringify({ id: 'job-1', kind: 'detailed_test_video', status: 'queued' }), { status: 200 });
    }
    const recipePayload = body.recipe ?? api.buildAnnouncementVideoRecipePayload(recipe({ name: body.name ?? '新サービス告知' }));
    return new Response(JSON.stringify({
      id: body.new_recipe_id ?? recipeId,
      version_id: `annv_${'b'.repeat(32)}`,
      production_id: 'production/a',
      revision: 1,
      digest: 'C'.repeat(64),
      recipe: recipePayload,
    }), { status: 200 });
  };
  try {
    await api.api.saveAnnouncementRecipe('production/a', recipeId, 0, recipe());
    await api.api.duplicateAnnouncementRecipe('production/a', recipeId, 1, `announcement_${'d'.repeat(32)}`, 'コピー');
    const controller = new AbortController();
    const job = await api.api.executeAnnouncementRecipe('production/a', recipeId, 1, controller.signal);
    assert.equal(job.id, 'job-1');
    assert.equal(requests[2].signal, controller.signal);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(requests[0].url, `/api/productions/production%2Fa/announcement-recipes/${recipeId}/save`);
  assert.deepEqual(requests[0].body, api.buildAnnouncementSavePayload(0, recipe()));
  assert.equal(requests[1].url, `/api/productions/production%2Fa/announcement-recipes/${recipeId}/duplicate`);
  assert.deepEqual(requests[1].body, { schema_version: 1, source_revision: 1, new_recipe_id: `announcement_${'d'.repeat(32)}`, name: 'コピー' });
  assert.equal(requests[2].url, `/api/productions/production%2Fa/announcement-recipes/${recipeId}/execute`);
  assert.deepEqual(requests[2].body, { schema_version: 1, revision: 1 });
});

test('Studio exposes Quick Create as the default announcement surface and keeps Detailed separate', () => {
  assert.match(appSource, /useState<DetailTab>\('announcement'\)/);
  assert.match(appSource, /id: 'announcement', label: '1\. 作る'/);
  assert.match(announcementSource, /HOOK → MESSAGE → CTA/);
  assert.match(announcementSource, /保存して告知動画を作る/);
  assert.match(announcementSource, /複製して編集/);
  assert.match(announcementSource, /H3低解像度を鮮明化/);
  assert.match(announcementSource, /完成masterを正として確認/);
  assert.match(announcementSource, /setInterval\([\s\S]{0,500}2_000/);
  assert.match(announcementSource, /detailPollTickRef\.current % 3/);
  assert.match(announcementSource, /selectAnnouncementRecoveryCandidates\(detail\.announcementExecutions, guard\)/);
  assert.match(announcementSource, /api\.job\(execution\.jobId, signal\)/);
  assert.match(announcementSource, /recipeRevision < 1 \|\| dirty/);
  assert.match(announcementSource, /currentExecutions\[0\]\?\.runId/);
  assert.match(announcementSource, /savedRecord/);
  assert.match(appSource, /announcementJobIds/);
  assert.match(appSource, /onReload=\{reloadSelectedDetail\}/);
  assert.match(appSource, /告知動画の未保存変更を破棄して、別の画面へ移動しますか/);
  assert.match(appSource, /ANNOUNCEMENT_DEFAULT_SCENE_END_MS = \[5_167, 5_167, 5_166\]/);
  assert.match(announcementSource, /visibleJob\?\.result\?\.durationMs \?\? normalized\.outputDurationMs/);
  assert.match(stylesSource, /\.announcement-grid/);
  assert.match(stylesSource, /\.announcement-scene\.role-hook/);
  assert.match(stylesSource, /\.announcement-grid > aside \.local-pipeline-progress-panel \{ order: 1; \}/);
});

test('a confirmed session rejection refreshes the same-origin cookie before one identical retry', async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, init) => {
    requests.push({ url, ...init });
    if (requests.length === 1) return new Response(JSON.stringify({ error: { code: 'forbidden', message: 'A valid Studio session is required.' } }), { status: 403 });
    if (url === '/') return new Response('<!doctype html><title>Studio</title>');
    return new Response(JSON.stringify({ id: 'job-refreshed', kind: 'detailed_test_video', status: 'queued' }));
  };
  try {
    const job = await api.api.executeAnnouncementRecipe('production', recipeId, 1);
    assert.equal(job.id, 'job-refreshed');
    assert.equal(requests.length, 3);
    assert.equal(requests[1].url, '/');
    assert.equal(requests[1].credentials, 'same-origin');
    assert.equal(requests[0].url, requests[2].url);
    assert.equal(requests[0].body, requests[2].body);
  } finally { globalThis.fetch = originalFetch; }
});

test('session recovery is bounded and never retries uncertain or unrelated failures', async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const scenario of ['session', 'denied', 'server', 'network']) {
      let calls = 0;
      globalThis.fetch = async (url) => {
        calls += 1;
        if (url === '/') return new Response('<title>Studio</title>');
        if (scenario === 'network') throw new TypeError('network lost');
        return new Response(JSON.stringify({ error: { code: 'forbidden', message: scenario === 'session' ? 'A valid Studio session is required.' : 'Unrelated failure' } }), { status: scenario === 'server' ? 500 : 403 });
      };
      await assert.rejects(api.api.executeAnnouncementRecipe('production', recipeId, 1));
      assert.equal(calls, scenario === 'session' ? 3 : 1);
    }
  } finally { globalThis.fetch = originalFetch; }
});

test('Quick Create is a compact view over the exact existing announcement controller', () => {
  assert.match(announcementSource, /useState<AnnouncementEditorMode>[\s\S]{0,160}'quick'[\s\S]{0,80}'advanced'/);
  assert.match(announcementSource, /useState\(\(\) => announcementDraftSignature\(initialDraft\)\)/);
  assert.match(announcementSource, /const startNew = \(\) => \{[\s\S]{0,500}setSavedSignature\(announcementDraftSignature\(next\)\)/);
  assert.match(announcementSource, /<QuickCreateForm[\s\S]{0,1500}onSceneNarrationChange=/);
  assert.match(announcementSource, /onClick=\{\(\) => void saveAndExecute\(\)\}/);
  assert.match(announcementSource, /この内容で動画を作る（\$\{formatMilliseconds\(normalized\.outputDurationMs\)\}）/);
  assert.equal((announcementSource.match(/const saveAndExecute = async/g) ?? []).length, 1);
  assert.equal((announcementSource.match(/api\.executeAnnouncementRecipe\(/g) ?? []).length, 2);
  assert.doesNotMatch(quickCreateSource, /\bapi\.|executeDetailedTestVideo|fetch\(/);
  assert.match(quickCreateSource, /3つの場面を選ぶ/);
  assert.match(quickCreateSource, /伝える言葉を入れる/);
  assert.match(quickCreateSource, /内容を確認して作成する/);
  assert.match(quickCreateSource, /ローカルのみ・API費用0円/);
  assert.match(quickCreateSource, /秘密情報、API token、公開したくない個人情報は入力しないでください/);
});

test('Quick Create keeps hidden settings fixed and reveals any advanced saved recipe', () => {
  assert.match(appSource, /const announcementDraftUsesQuickDefaults = \([\s\S]{0,1500}draft\.audioMixPreset === 'narration_only_v1'[\s\S]{0,500}scene\.visualPreset === DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET/);
  assert.match(announcementSource, /setEditorMode\(announcementDraftUsesQuickDefaults\(nextDraft, videoArtifacts\) \? 'quick' : 'advanced'\)/);
  assert.match(announcementSource, /const activeEditorMode: AnnouncementEditorMode = quickModeAvailable \? editorMode : 'advanced'/);
  assert.match(announcementSource, /if \(!quickModeAvailable && editorMode !== 'advanced'\) setEditorMode\('advanced'\)/);
  assert.match(announcementSource, /disabled=\{formLocked \|\| !quickModeAvailable\}/);
  assert.match(announcementSource, /設定を隠したまま上書きしないよう、詳細設定で表示しています/);
  assert.match(appSource, /draft\.rate\.trim\(\) !== ''[\s\S]{0,500}scene\.startMs\.trim\(\) !== ''[\s\S]{0,500}scene\.volumePercent\.trim\(\) !== ''/);
  assert.match(announcementSource, /setEditorMode\('quick'\);[\s\S]{0,100}setRecipeId\(newAnnouncementRecipeId\(\)\)/);
  assert.match(announcementSource, /type="radio" name="announcement-editor-mode"/);
  assert.ok(announcementSource.indexOf("duplicateIntentStore.status !== 'ready'") < announcementSource.indexOf('<QuickCreateForm'));
  assert.equal((announcementSource.match(/className="announcement-recipe-browser"/g) ?? []).length, 1);
  assert.match(announcementSource, /className="announcement-recipe-browser"[\s\S]*\{activeEditorMode === 'quick' \? \(\r?\n            <QuickCreateForm/);
  assert.match(announcementSource, /選択した内容には詳細設定が含まれるため、詳細設定を表示しました。/);
  assert.match(announcementSource, /validationErrors=\{validationErrors\}/);
  assert.match(announcementSource, /outputDurationMs=\{normalized\.outputDurationMs\}/);
  assert.match(announcementSource, /role="status" aria-live="polite"/);
  assert.match(quickCreateSource, /aria-describedby=\{helpId\}/);
  assert.match(quickCreateSource, /aria-invalid=\{Boolean\(recipeNameError\)\}/);
  assert.match(quickCreateSource, /<span>読み上げる文章<\/span>/);
  assert.doesNotMatch(quickCreateSource, /<details className="quick-create-narration"/);
});

test('saving a new recipe revision cannot display the previous revision job or result', () => {
  assert.match(appSource, /type AnnouncementJobBinding = \{[\s\S]*recipeVersionId: string;[\s\S]*job: Job;[\s\S]*\};/);
  assert.match(announcementSource, /const job = jobBinding\?\.recipeVersionId === recipeVersionId \? jobBinding\.job : undefined;/);
  assert.match(announcementSource, /setRecipeVersionId\(saved\.versionId\);[\s\S]{0,500}setJobBinding\(undefined\);[\s\S]{0,300}exactJobFetchRef\.current = undefined;[\s\S]{0,200}executionGuardRef\.current = undefined;/);
  assert.match(announcementSource, /setJobBinding\(\{ recipeVersionId: saved\.versionId, job: submitted \}\);/);
});

test('announcement execute treats every received 4xx as deterministic non-admission', () => {
  assert.match(appSource, /const isReceivedAnnouncementClientError = \(error: unknown\): error is StudioApiError =>\s*error instanceof StudioApiError && error\.status >= 400 && error\.status < 500;/);
  assert.match(
    announcementSource,
    /isReceivedAnnouncementClientError\(error\)\) \{[\s\S]{0,260}executionGuardRef\.current = undefined;[\s\S]{0,160}recoveryJobFetchRef\.current = undefined;[\s\S]{0,200}setSubmissionUncertain\(false\);[\s\S]{0,100}setBusy\(false\);/,
  );
});

test('exact announcement job lookup is version-keyed and ignores a late stale promise', () => {
  assert.match(appSource, /const announcementExactJobFetchKey = \(recipeVersionId: string, jobId: string\): string =>/);
  assert.match(announcementSource, /const fetchKey = announcementExactJobFetchKey\(recipeVersionId, exactExecutionJobId\);/);
  assert.match(announcementSource, /if \(cancelled \|\| exactJobFetchRef\.current !== fetchKey\) return;[\s\S]{0,100}setJobBinding\(\{ recipeVersionId, job: loaded \}\);/);
  assert.match(announcementSource, /\}, \[exactExecutionJobId, exactExecutionJobLoaded, recipeVersionId, submissionUncertain\]\);/);
  assert.match(announcementSource, /const loadRecord = useCallback[\s\S]{0,650}exactJobFetchRef\.current = undefined;/);
  assert.match(announcementSource, /const startNew = \(\) => \{[\s\S]{0,650}exactJobFetchRef\.current = undefined;/);
});

test('external latest recipe advances are reconciled without overwriting dirty or busy edits', () => {
  assert.match(appSource, /const announcementRecipeHasAdvanced = \(/);
  assert.match(announcementSource, /const staleRecipeVersion = announcementRecipeHasAdvanced\(latestSelectedRecord, recipeRevision, recipeVersionId\);/);
  assert.match(announcementSource, /if \(!staleRecipeVersion \|\| !latestSelectedRecord \|\| dirty \|\| !recipeSyncIdle\) return;[\s\S]{0,120}loadRecord\(latestSelectedRecord\);/);
  assert.match(announcementSource, /編集中 rev \$\{recipeRevision\} \/ 最新 rev \$\{item\.revision\}/);
  assert.match(announcementSource, /保存・実行を停止しました。/);
  assert.match(announcementSource, /disabled=\{formLocked \|\| Boolean\(pendingDuplicateIntent\) \|\| staleRecipeVersion \|\| validationErrors\.length > 0\}/);
  assert.match(announcementSource, /最新版を読み込む/);
});

test('mobile announcement layout lets long production and recipe content shrink inside the viewport', () => {
  assert.match(stylesSource, /\.overview-main, \.overview-side, \.audit-grid > aside \{ min-width: 0; \}/);
  assert.match(stylesSource, /\.announcement-panel \.field, \.announcement-scene-heading > div \{ min-width: 0; \}/);
  assert.match(stylesSource, /\.announcement-panel \.field input, \.announcement-panel \.field textarea, \.announcement-panel \.field select \{ width: 100%; min-width: 0; \}/);
  assert.match(stylesSource, /@media \(max-width: 760px\)[\s\S]*\.workspace-header > div:first-child, \.title-row, \.title-row h2, \.panel-header > div:first-child, \.local-pipeline-step-body \{ min-width: 0; \}/);
  assert.match(stylesSource, /@media \(max-width: 760px\)[\s\S]*\.title-row h2 \{ overflow-wrap: anywhere; \}/);
  assert.match(stylesSource, /@media \(max-width: 760px\)[\s\S]*\.quick-create-scene-grid, \.quick-create-copy-list \{ grid-template-columns: 1fr; \}/);
});

test('exact job lookup supports fresh-link ambiguous-response reconciliation', async () => {
  const originalFetch = globalThis.fetch;
  let requested;
  globalThis.fetch = async (url, init) => {
    requested = { url, init };
    return new Response(JSON.stringify({
      id: `job_${'f'.repeat(32)}`,
      kind: 'detailed_test_video',
      status: 'running',
      production_id: 'production/a',
    }), { status: 200 });
  };
  try {
    const controller = new AbortController();
    const job = await api.api.job(`job_${'f'.repeat(32)}`, controller.signal);
    assert.equal(job.status, 'running');
    assert.equal(requested.init?.signal, controller.signal);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(requested.url, `/api/jobs/job_${'f'.repeat(32)}`);
  assert.equal(requested.init?.method, undefined);
});

test('known succeeded history stays audit-only and the automatic retry is claimed exactly once', () => {
  const versionId = `annv_${'b'.repeat(32)}`;
  const jobId = `job_${'f'.repeat(32)}`;
  const requestKey = 'A'.repeat(64);
  const execution = {
    recipeId,
    recipeVersionId: versionId,
    recipeRevision: 3,
    recipeDigest: 'B'.repeat(64),
    jobId,
    runId: `run_${'c'.repeat(32)}`,
    revisionId: `rev_${'d'.repeat(32)}`,
    requestKey,
    deduplicated: false,
    raw: {},
  };
  const saved = {
    id: recipeId,
    versionId,
    productionId: 'production/a',
    revision: 3,
    digest: 'B'.repeat(64),
  };
  const guard = recovery.createAnnouncementSubmissionGuard('production/a', saved, [execution]);
  const candidates = recovery.selectAnnouncementRecoveryCandidates([
    { ...execution, recipeVersionId: `annv_${'e'.repeat(32)}`, jobId: `job_${'0'.repeat(32)}` },
    execution,
  ], guard);
  assert.deepEqual(candidates.fresh, []);

  const exactJob = {
    id: jobId,
    productionId: 'production/a',
    type: 'detailed_test_video',
    status: 'succeeded',
    raw: { payload: {
      production_id: 'production/a',
      run_id: execution.runId,
      revision_id: execution.revisionId,
      request_key: requestKey,
    } },
  };
  assert.equal(recovery.announcementJobMatchesExecution(exactJob, execution, 'production/a'), true);
  assert.equal(recovery.announcementJobMatchesExecution({
    ...exactJob,
    raw: { payload: { ...exactJob.raw.payload, request_key: 'C'.repeat(64) } },
  }, execution, 'production/a'), false);

  assert.deepEqual(recovery.claimAnnouncementAutomaticRetry(guard), {
    productionId: 'production/a',
    recipeId,
    recipeRevision: 3,
  });
  assert.equal(recovery.claimAnnouncementAutomaticRetry(guard), undefined);
  assert.deepEqual(recovery.announcementRetryRequest(guard), {
    productionId: 'production/a',
    recipeId,
    recipeRevision: 3,
  });
});

test('ambiguous recovery accepts only a fresh exact-version link with an exact Job cross-check', () => {
  const existing = {
    recipeId,
    recipeVersionId: `annv_${'b'.repeat(32)}`,
    recipeRevision: 1,
    recipeDigest: 'D'.repeat(64),
    jobId: `job_${'1'.repeat(32)}`,
    runId: `run_${'2'.repeat(32)}`,
    revisionId: `rev_${'3'.repeat(32)}`,
    requestKey: 'E'.repeat(64),
    deduplicated: false,
    raw: {},
  };
  const saved = { id: recipeId, versionId: existing.recipeVersionId, revision: 1, digest: existing.recipeDigest };
  const guard = recovery.createAnnouncementSubmissionGuard('production/a', saved, [existing]);
  const fresh = { ...existing, jobId: `job_${'4'.repeat(32)}`, requestKey: 'F'.repeat(64) };
  const candidates = recovery.selectAnnouncementRecoveryCandidates([
    { ...existing, recipeId: `announcement_${'9'.repeat(32)}` },
    fresh,
    existing,
  ], guard);
  assert.deepEqual(candidates.fresh, [fresh]);
  assert.equal('reusable' in candidates, false);
  assert.doesNotMatch(recoverySource, /isReusableAnnouncementJob|reusable/);
  assert.match(announcementSource, /const fresh = candidates\.fresh;/);
  assert.match(announcementSource, /announcementJobMatchesExecution\(candidateJob, execution, guard\.productionId\)/);
  assert.doesNotMatch(announcementSource, /candidates\.reusable|isReusableAnnouncementJob/);
});

test('ambiguous execute performs one bounded automatic POST with the immutable guarded identity', () => {
  assert.match(announcementSource, /if \(!fetchToken\) \{[\s\S]{0,220}automaticRetryReady && !guard\.automaticRetryAttempted[\s\S]{0,120}retryGuardedExecution\('automatic'\)/);
  assert.match(announcementSource, /const request = mode === 'automatic'[\s\S]{0,140}claimAnnouncementAutomaticRetry\(guard\)[\s\S]{0,80}announcementRetryRequest\(guard\)/);
  assert.match(
    announcementSource,
    /runAnnouncementRequestWithTimeout\(\(signal\) => api\.executeAnnouncementRecipe\(\s*request\.productionId,\s*request\.recipeId,\s*request\.recipeRevision,\s*signal,\s*\)\)/,
  );
  assert.match(announcementSource, /await reloadAnnouncementDetail\(\)\.catch\(\(\) => undefined\);[\s\S]{0,120}executionGuardRef\.current === guard\) \{[\s\S]{0,80}setAutomaticRetryReady\(true\)/);
});

test('announcement network timeout aborts the in-flight request and returns a stable error', async () => {
  let observedSignal;
  await assert.rejects(
    recovery.runAnnouncementRequestWithTimeout((signal) => {
      observedSignal = signal;
      return new Promise(() => undefined);
    }, 5),
    (error) => {
      assert.equal(error.name, 'AnnouncementRequestTimeoutError');
      assert.match(error.message, /1秒以内/);
      assert.equal(error.timeoutMs, 5);
      return true;
    },
  );
  assert.equal(observedSignal.aborted, true);
});

test('all announcement admission and reconciliation fetches use the bounded abort wrapper', () => {
  assert.match(appSource, /const runIdempotentAnnouncementMutation = async <T,>[\s\S]{0,500}runAnnouncementRequestWithTimeout\(operation\)[\s\S]{0,500}return await runAnnouncementRequestWithTimeout\(operation\)/);
  assert.match(announcementSource, /runIdempotentAnnouncementMutation\(\s*\(signal\) => api\.saveAnnouncementRecipe\(/);
  assert.match(announcementSource, /runIdempotentAnnouncementMutation\(\s*\(signal\) => api\.duplicateAnnouncementRecipe\(/);
  assert.equal((announcementSource.match(/runAnnouncementRequestWithTimeout\(\(signal\) => api\.executeAnnouncementRecipe\(/g) ?? []).length, 2);
  assert.match(announcementSource, /runAnnouncementRequestWithTimeout\(\(signal\) => api\.jobs\(signal\)\)/);
  assert.match(announcementSource, /runAnnouncementRequestWithTimeout\(\(signal\) => api\.job\(exactExecutionJobId, signal\)\)/);
  assert.match(announcementSource, /runAnnouncementRequestWithTimeout\(\(signal\) => api\.job\(execution\.jobId, signal\)\)/);
  assert.match(announcementSource, /runAnnouncementRequestWithTimeout\(\(signal\) => onReload\(signal\)\)/);
  assert.match(announcementSource, /\[automaticRetryReady, detail\.announcementExecutions, detail\.id, reconciledJobs, retryGuardedExecution, submissionUncertain, submitting\]\);/);
  assert.match(announcementSource, /submissionUncertain && manualReconciliationAvailable[\s\S]{0,220}同一revisionを再照合/);
});

test('retry response binds its exact version; a second ambiguity stays locked behind manual exact reconciliation', () => {
  assert.match(announcementSource, /executionGuardRef\.current = undefined;[\s\S]{0,180}setSubmissionUncertain\(false\);[\s\S]{0,140}setJobBinding\(\{ recipeVersionId: guard\.recipeVersionId, job: submitted \}\)/);
  assert.match(announcementSource, /setManualReconciliationAvailable\(true\);/);
  assert.match(announcementSource, /submissionUncertain && manualReconciliationAvailable[\s\S]{0,220}retryGuardedExecution\('manual'\)[\s\S]{0,140}同一revisionを再照合/);
  assert.match(announcementSource, /isReceivedAnnouncementClientError\(error\)[\s\S]{0,260}executionGuardRef\.current = undefined;[\s\S]{0,260}setSubmissionUncertain\(false\);/);
});

test('ambiguous save and duplicate repeat the exact idempotent mutation identity once', () => {
  assert.match(announcementSource, /保存応答が不明なため、同じrecipe ID・expected revision・内容を1回だけ再照合/);
  assert.match(announcementSource, /let intent = pendingDuplicateIntent;[\s\S]{0,520}newRecipeId: await deterministicAnnouncementCloneRecipeId\(duplicateIntentMatch\)/);
  assert.match(announcementSource, /const persistedIntent = await persistAnnouncementDuplicateIntent\(browserAnnouncementDuplicateIntentStorage, intent\);[\s\S]{0,220}runIdempotentAnnouncementMutation/);
  assert.match(announcementSource, /api\.duplicateAnnouncementRecipe\(\s*persistedIntent\.productionId,\s*persistedIntent\.sourceRecipeId,\s*persistedIntent\.sourceRevision,\s*persistedIntent\.newRecipeId,\s*persistedIntent\.name,\s*signal/);
  assert.match(announcementSource, /複製応答が不明なため、新しいIDを作らず同じ複製IDを1回だけ再照合/);
  assert.doesNotMatch(announcementSource, /api\.duplicateAnnouncementRecipe\([\s\S]{0,200}newAnnouncementRecipeId\(\)/);
  assert.doesNotMatch(announcementSource, /duplicateIntentRef/);
});

test('duplicate intent survives remount storage and clears only its exact identity', async () => {
  const storage = memoryStorage();
  const first = {
    schemaVersion: 1,
    productionId: 'production-a',
    sourceRecipeId: recipeId,
    sourceRecipeVersionId: `annv_${'b'.repeat(32)}`,
    sourceRevision: 3,
    newRecipeId: '',
    name: '新サービス告知（コピー）',
    createdAt: '2026-08-28T00:00:00.000Z',
  };
  const second = {
    ...first,
    sourceRecipeId: `announcement_${'d'.repeat(32)}`,
    sourceRecipeVersionId: `annv_${'e'.repeat(32)}`,
    newRecipeId: '',
  };
  first.newRecipeId = await recovery.deterministicAnnouncementCloneRecipeId(first);
  second.newRecipeId = await recovery.deterministicAnnouncementCloneRecipeId(second);
  assert.deepEqual(await recovery.persistAnnouncementDuplicateIntent(storage, first), first);
  await recovery.persistAnnouncementDuplicateIntent(storage, second);

  const remounted = recovery.findAnnouncementDuplicateIntent(storage, {
    productionId: first.productionId,
    sourceRecipeId: first.sourceRecipeId,
    sourceRecipeVersionId: first.sourceRecipeVersionId,
    sourceRevision: first.sourceRevision,
    name: first.name,
  });
  assert.deepEqual(remounted, first);

  recovery.clearAnnouncementDuplicateIntent(storage, first);
  assert.equal(recovery.findAnnouncementDuplicateIntent(storage, {
    productionId: first.productionId,
    sourceRecipeId: first.sourceRecipeId,
    sourceRecipeVersionId: first.sourceRecipeVersionId,
    sourceRevision: first.sourceRevision,
    name: first.name,
  }), undefined);
  assert.deepEqual(recovery.inspectAnnouncementDuplicateIntentStore(storage, second), { status: 'ready', intent: second });
});

test('duplicate intent uses a deterministic ID and first-writer-wins across tabs', async () => {
  const storage = memoryStorage();
  const match = {
    productionId: 'production-a',
    sourceRecipeId: recipeId,
    sourceRecipeVersionId: `annv_${'b'.repeat(32)}`,
    sourceRevision: 1,
    name: '告知（コピー）',
  };
  const derived = await recovery.deterministicAnnouncementCloneRecipeId(match);
  assert.match(derived, /^announcement_[0-9a-f]{32}$/);
  assert.equal(await recovery.deterministicAnnouncementCloneRecipeId({ ...match }), derived);
  assert.notEqual(await recovery.deterministicAnnouncementCloneRecipeId({ ...match, name: '別コピー' }), derived);

  const firstWriter = { schemaVersion: 1, ...match, newRecipeId: derived, createdAt: '2026-08-28T00:00:00.000Z' };
  const staleTab = { ...firstWriter, createdAt: '2026-08-28T00:00:01.000Z' };
  assert.deepEqual(await recovery.persistAnnouncementDuplicateIntent(storage, firstWriter), firstWriter);
  assert.deepEqual(await recovery.persistAnnouncementDuplicateIntent(storage, staleTab), firstWriter);
  assert.deepEqual(recovery.findAnnouncementDuplicateIntent(storage, match), firstWriter);
  await assert.rejects(
    recovery.persistAnnouncementDuplicateIntent(storage, { ...staleTab, newRecipeId: `announcement_${'f'.repeat(32)}` }),
    /not deterministic/,
  );
  assert.match(recoverySource, /One exact source\/name intent gets one independent atomic localStorage key/);
  assert.match(recoverySource, /First writer wins/);
});

test('duplicate intent storage fails closed when unavailable or corrupt', async () => {
  const intent = {
    schemaVersion: 1,
    productionId: 'production-a',
    sourceRecipeId: recipeId,
    sourceRecipeVersionId: `annv_${'b'.repeat(32)}`,
    sourceRevision: 1,
    newRecipeId: '',
    name: '告知（コピー）',
    createdAt: '2026-08-28T00:00:00.000Z',
  };
  const unavailable = {
    getItem: () => { throw new Error('blocked'); },
    setItem: () => { throw new Error('blocked'); },
    removeItem: () => { throw new Error('blocked'); },
  };
  intent.newRecipeId = await recovery.deterministicAnnouncementCloneRecipeId(intent);
  assert.deepEqual(recovery.inspectAnnouncementDuplicateIntentStore(unavailable, intent), { status: 'unavailable' });
  await assert.rejects(recovery.persistAnnouncementDuplicateIntent(unavailable, intent), /unavailable/);

  const intentKey = recovery.announcementDuplicateIntentStorageKey(intent);
  const corrupt = memoryStorage({
    [intentKey]: JSON.stringify({ ...intent, newRecipeId: 'bad' }),
  });
  assert.deepEqual(recovery.inspectAnnouncementDuplicateIntentStore(corrupt, intent), { status: 'corrupt' });
  await assert.rejects(recovery.persistAnnouncementDuplicateIntent(corrupt, intent), /corrupt/);
  recovery.clearAnnouncementDuplicateIntentStore(corrupt, intent);
  assert.deepEqual(recovery.inspectAnnouncementDuplicateIntentStore(corrupt, intent), { status: 'ready' });
});

test('duplicate response and audit reconciliation require the exact pre-issued clone lineage', () => {
  const intent = {
    schemaVersion: 1,
    productionId: 'production-a',
    sourceRecipeId: recipeId,
    sourceRecipeVersionId: `annv_${'b'.repeat(32)}`,
    sourceRevision: 1,
    newRecipeId: `announcement_${'c'.repeat(32)}`,
    name: '告知（コピー）',
    createdAt: '2026-08-28T00:00:00.000Z',
  };
  const clone = {
    id: intent.newRecipeId,
    versionId: `annv_${'d'.repeat(32)}`,
    productionId: intent.productionId,
    revision: 1,
    cloneSourceVersionId: intent.sourceRecipeVersionId,
    digest: 'E'.repeat(64),
    versionCount: 1,
    recipe: recipe({ name: intent.name }),
    raw: {},
  };
  assert.equal(recovery.announcementCloneMatchesIntent(clone, intent), true);
  assert.equal(recovery.announcementCloneMatchesIntent({ ...clone, revision: 2 }, intent), false);
  assert.equal(recovery.announcementCloneMatchesIntent({ ...clone, cloneSourceVersionId: `annv_${'f'.repeat(32)}` }, intent), false);
  assert.match(announcementSource, /announcementCloneMatchesIntent\(cloned, persistedIntent\)[\s\S]{0,220}clearAnnouncementDuplicateIntent\(browserAnnouncementDuplicateIntentStorage, persistedIntent\)/);
  assert.match(announcementSource, /detail\.announcementRecipeVersions\.find\([\s\S]{0,160}announcementCloneMatchesIntent\(record, pendingDuplicateIntent\)/);
});

test('timeout and received 4xx retain the durable clone intent until explicit discard', () => {
  const duplicateBlock = announcementSource.slice(
    announcementSource.indexOf('const duplicate = async'),
    announcementSource.indexOf('const saveAndExecute = async'),
  );
  const catchBlock = duplicateBlock.slice(duplicateBlock.indexOf('} catch (error) {'));
  assert.doesNotMatch(catchBlock.slice(0, catchBlock.indexOf('} finally')), /clearAnnouncementDuplicateIntent/);
  assert.match(duplicateBlock, /intentPersisted[\s\S]{0,260}同じIDで再照合するか、明示的に保留を破棄/);
  assert.match(announcementSource, /保留中の複製を破棄/);
  assert.match(announcementSource, /serverで受理済みの場合、保存済みrecipe自体は削除されません/);
  assert.match(appSource, /const announcementDuplicateName[\s\S]{0,120}120 - suffix\.length/);
});

test('fresh-link exact Job failures stop automatic fetches and expose manual exact reconciliation', () => {
  assert.match(announcementSource, /recoveryJobFetchRef\.current === fetchToken \|\| recoveryJobBlockedRef\.current === fetchToken/);
  assert.match(announcementSource, /if \(!recovered && executionGuardRef\.current === guard\) \{[\s\S]{0,160}recoveryJobBlockedRef\.current = fetchToken;[\s\S]{0,180}setManualReconciliationAvailable\(true\)/);
  assert.match(announcementSource, /新しい受理記録はありますが、対応するexact Jobを確認できませんでした。自動再送と同じ候補への追加GETを停止しました。/);
});

test('production detail requests abort stale generations and never render another selected production', () => {
  assert.match(appSource, /detailRequestRef\.current\?\.controller\.abort\(\);[\s\S]{0,240}detailRequestRef\.current = \{ id, generation, controller \};/);
  assert.match(appSource, /controller\.signal\.aborted[\s\S]{0,120}selectedIdRef\.current !== id[\s\S]{0,140}detailRequestRef\.current\?\.generation !== generation/);
  assert.match(appSource, /const abortDetailRequest = useCallback\(\(\) => \{[\s\S]{0,100}controller\.abort\(\);[\s\S]{0,100}detailRequestRef\.current = undefined;/);
  assert.match(appSource, /selectedIdRef\.current = productionId;[\s\S]{0,100}setSelectedId\(productionId\);/);
  assert.match(appSource, /\{detail && detail\.id === selectedId && \(/);
});
