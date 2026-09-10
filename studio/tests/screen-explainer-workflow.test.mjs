import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = await readFile(join(root, '.test-dist/screenExplainerWorkflow.js'), 'utf8');
const w = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const makeDraft = () => w.newScreenExplainerDraft(undefined, () => 'a'.repeat(32));
test('structure review is non-mutating advice about duplicate sources, titles and narrow crops', () => {
  const draft = makeDraft();
  draft.shots.forEach(shot => { shot.artifactId = 'art_same'; shot.headline = '同じ見出し'; });
  const before = JSON.stringify(draft);
  assert.equal(w.reviewScreenStructure(draft).filter(item => item.key.startsWith('source-')).length, 2);
  assert.equal(w.reviewScreenStructure(draft).filter(item => item.key.startsWith('headline-')).length, 2);
  assert.equal(JSON.stringify(draft), before);
  draft.shots[1].focusRegion = { x: .1, y: .1, width: .7, height: .2 };
  assert.equal(w.reviewScreenStructure(draft).filter(item => item.key.startsWith('crop-')).length, 1);
  assert.equal(w.reviewScreenStructure(draft).filter(item => item.key.startsWith('source-')).length, 0);
  draft.shots.forEach((shot,index) => { shot.artifactId = `art_${index}`; shot.headline = `場面${index}`; delete shot.focusRegion; });
  assert.deepEqual(w.reviewScreenStructure(draft), []);
});
const video = (id, name = 'screen-capture.mp4') => ({ id, name, kind: 'video', url: `/artifacts/${id}`, durationSeconds: 10, metadata: {}, raw: {} });
const job = (id, artifacts = []) => ({ id, type: 'local_screen_capture', status: 'succeeded', result: { artifacts, raw: {} }, raw: {} });
const renderJob = (productionId, recipe, revision) => {
  const runId = `run_render${revision}`;
  const artifact = { ...video(`art_master${revision}`, 'master-captioned.mp4'), sha256: 'B'.repeat(64), path: `outputs/studio/runs/${runId}/assembly/${'A'.repeat(64)}/master-captioned.mp4` };
  return {
    ...job(`job_render${revision}`, [artifact]), type: 'detailed_test_video', productionId, runId,
    raw: { payload: { production_id: productionId, run_id: runId, stage: 'detailed_test_video', execution_profile: 'local_sapi', clips: recipe.scenes.map((shot) => ({
      video_artifact_id: shot.videoArtifactId, start_ms: shot.startMs, end_ms: shot.endMs, layout_preset: 'screen_explainer_v1', transition_to_next: null, ...(shot.focusRegion ? { focus_region: shot.focusRegion } : {}),
      ...(recipe.screenTheme === undefined ? {} : { screen_theme: recipe.screenTheme }),
    })) } },
    result: { artifacts: [artifact], runId, technicalVerdict: 'pass', jobs: Object.fromEntries(['narration', 'timeline', 'assembly', 'qc'].map((stage) => [stage, { jobId: `job_${stage}${revision}`, status: 'succeeded' }])),
      raw: { run_id: runId, technical_verdict: 'pass', include_captioned: true, variant: 'captioned', qc: { verdict: 'pass' }, narration_alignment_policy: 'announcement_scene_starts_v1',
        narration_segment_start_ms: recipe.scenes.map((_shot, index) => recipe.scenes.slice(0, index).reduce((sum, shot) => sum + shot.endMs - shot.startMs, 0)),
        master: { id: artifact.id, name: artifact.name, rel_path: artifact.path, sha256: artifact.sha256 },
      },
    },
  };
};
const setup = (draft = makeDraft()) => {
  const calls = [];
  const detail = { id: draft.productionId, title: draft.title, artifacts: [], runs: [], announcementRecipes: [], announcementRecipeVersions: [], announcementExecutions: [] };
  const jobs = new Map();
  let captured = 0;
  const api = {
    createProduction: async (...args) => { calls.push(['create', ...args]); return { id: args[0], title: args[1] }; },
    production: async () => detail,
    importVideo: async (_id, file) => { calls.push(['import', file.name]); const artifact = video(`art_import${detail.artifacts.length}`, file.name); detail.artifacts.push(artifact); return { artifact, deduplicated: false }; },
    rerunPlan: async (_id, changes) => { calls.push(['plan', changes]); return { stages: ['screen_capture'], raw: {} }; },
    createRun: async () => { const run = { id: `run_${detail.runs.length}`, stageAttempts: [] }; detail.runs.push(run); calls.push(['run', run.id]); return { revision: {}, run }; },
    executeLocalScreenCapture: async (runId, request) => {
      calls.push(['capture', runId, request]);
      captured += 1;
      const artifact = video(`art_capture${captured}`);
      const raw = video(`art_raw${captured}`, 'playwright-raw.webm');
      detail.artifacts.push(artifact, raw);
      const result = { ...job(`job_capture${captured}`, [raw, artifact]), productionId: detail.id, runId }; jobs.set(result.id, result);
      detail.runs.find((run) => run.id === runId).stageAttempts.push({ stage: 'screen_capture', jobId: result.id });
      return result;
    },
    job: async (id) => { calls.push(['job', id]); if (!jobs.has(id)) throw new Error('job not found'); return jobs.get(id); },
    saveAnnouncementRecipe: async (_id, recipeId, expectedRevision, recipe) => {
      calls.push(['save', recipeId, expectedRevision]);
      const current = detail.announcementRecipes.find((item) => item.id === recipeId);
      if ((current?.revision ?? 0) !== expectedRevision) throw Object.assign(new Error('conflict'), { status: 409 });
      const saved = { id: recipeId, versionId: `version_${expectedRevision + 1}`, productionId: detail.id, revision: expectedRevision + 1, recipe, digest: 'digest' };
      detail.announcementRecipes = [saved]; detail.announcementRecipeVersions.push(saved); return saved;
    },
    executeAnnouncementRecipe: async (_id, recipeId, revision) => {
      calls.push(['execute', recipeId, revision]);
      const saved = detail.announcementRecipeVersions.find((item) => item.id === recipeId && item.revision === revision);
      const result = renderJob(detail.id, saved.recipe, revision); jobs.set(result.id, result);
      detail.announcementExecutions.push({ recipeId, recipeRevision: revision, recipeVersionId: `version_${revision}`, jobId: result.id });
      return result;
    },
  };
  let latest;
  const options = { onDraft: (value) => { latest = structuredClone(value); }, sleep: async () => {}, onProgress: () => {} };
  return { api, detail, calls, jobs, options, latest: () => latest };
};
const captureDraft = () => { const draft = makeDraft(); draft.shots.forEach((shot) => { shot.source = 'capture'; shot.url = 'http://127.0.0.1:5173/demo'; }); return draft; };
const readyDraft = () => { const draft = makeDraft(); draft.productionCreated = true; draft.shots.forEach((shot, index) => { shot.artifactId = `art_${index}`; shot.previewApproved = true; }); return draft; };
const addReadyAssets = (state, draft) => { state.detail.artifacts = draft.shots.map((shot) => video(shot.artifactId)); };
const claudeConsent = { selectionToken: 'transient_test_selection', confirmCapture: true };
const sharedDraft = () => ({ ...makeDraft(), sourceMode: 'claude_shared' });
const setupShared = (draft = sharedDraft()) => {
  const state = setup(draft);
  state.api.executeClaudeCapture = async (productionId, request) => {
    assert.equal(state.latest().sharedCaptureRequestId, request.requestId, 'request ID must be persisted before POST');
    assert.equal(state.latest().pending.operation, 'claude_capture');
    assert.equal(JSON.stringify(state.latest()).includes(request.selectionToken), false, 'selection token must remain transient');
    state.calls.push(['claude', productionId, request]);
    const artifact = { ...video('art_claude', 'claude-capture.mp4'), durationSeconds: request.durationMs / 1000 };
    state.detail.artifacts.push(artifact);
    const result = { ...job('job_claude', [artifact]), productionId, type: 'claude_window_capture', raw: { payload: { capture_request_id: request.requestId } } };
    state.jobs.set(result.id, result);
    return result;
  };
  state.api.claudeCaptureJob = async (productionId, requestId) => {
    state.calls.push(['claude-read', productionId, requestId]);
    return [...state.jobs.values()].find((item) => item.productionId === productionId && item.raw.payload.capture_request_id === requestId);
  };
  return state;
};

test('screen template compiles 3 hard-cut scenes and closed local SAPI trial settings', () => {
  const draft = readyDraft();
  const recipe = w.buildScreenExplainerRecipe(draft);
  assert.equal(recipe.templatePreset, 'screen_explainer_ja_v1');
  assert.deepEqual(recipe.scenes.map((shot) => [shot.role, shot.startMs, shot.endMs]), [['hook', 0, 5000], ['message', 0, 5000], ['cta', 0, 5000]]);
  assert.equal(recipe.scenes.every((shot) => shot.volumePercent === 0 && shot.visualPreset === 'preserve_v1'), true);
  assert.equal(recipe.captionStylePreset, 'shorts_ja_large_v1');
  assert.equal(recipe.audioMixPreset, 'narration_only_v1');
});

test('closed theme drafts preserve omitted legacy data and restore explicit themes', () => {
  const draft = readyDraft();
  const restored = w.parseScreenExplainerDraft(JSON.parse(JSON.stringify(draft)));
  assert.equal(Object.hasOwn(restored, 'screenTheme'), false);
  assert.equal(Object.hasOwn(w.buildScreenExplainerRecipe(restored), 'screenTheme'), false);
  for (const screenTheme of ['neutral_v1', 'claude_desktop_v1', 'claude_code_v1', 'technical_v1', 'claude_editorial_v1']) {
    const themed = w.parseScreenExplainerDraft({ ...draft, screenTheme });
    const state = setup(themed);
    const saved = { id: draft.recipeId, versionId: 'version_theme', productionId: draft.productionId, revision: 1, recipe: w.buildScreenExplainerRecipe(themed) };
    assert.equal(w.screenExplainerDraftFromRecipe(state.detail, saved).screenTheme, screenTheme);
    assert.deepEqual(themed.shots, draft.shots);
  }
  for (const screenTheme of ['unknown', null, {}, 0]) assert.throws(() => w.parseScreenExplainerDraft({ ...draft, screenTheme }), /テーマ/);
});

test('theme edits create a new recipe fingerprint without collecting footage or changing script/audio', async () => {
  const draft = readyDraft();
  draft.sharedCaptureRequestId = 'claude_capture_' + 'a'.repeat(32);
  draft.sharedCaptureJobId = 'job_kept';
  draft.shots[0].captureRunId = 'run_kept';
  const state = setup(draft); addReadyAssets(state, draft);
  const first = await w.executeScreenExplainer(state.api, draft, state.options);
  const edited = w.parseScreenExplainerDraft({ ...first.draft, screenTheme: 'claude_code_v1' });
  assert.deepEqual(edited.shots, first.draft.shots);
  assert.equal(edited.sharedCaptureRequestId, first.draft.sharedCaptureRequestId);
  assert.equal(edited.sharedCaptureJobId, first.draft.sharedCaptureJobId);
  const second = await w.executeScreenExplainer(state.api, edited, state.options);
  assert.equal(second.draft.recipeRevision, 2);
  assert.notEqual(first.draft.savedFingerprint, second.draft.savedFingerprint);
  const [oldRecipe, newRecipe] = state.detail.announcementRecipeVersions.map((saved) => saved.recipe);
  assert.deepEqual(newRecipe, { ...oldRecipe, screenTheme: 'claude_code_v1' });
  assert.equal(state.calls.some(([type]) => ['import', 'capture', 'claude'].includes(type)), false);
  const wrongTheme = structuredClone(second.job); wrongTheme.raw.payload.clips[1].screen_theme = 'neutral_v1';
  assert.throws(() => w.verifyScreenExplainerRender(wrongTheme, second.draft), /照合できない/);
});

test('theme selector is grouped, factual, local-only, and preserves capture consent', async () => {
  const panel = await readFile(join(root, 'src/ScreenExplainerPanel.tsx'), 'utf8');
  const selector = panel.slice(panel.indexOf('<section className="screen-explainer-theme"'), panel.indexOf('{step === 0 ?'));
  assert.match(selector, /製品別/); assert.match(selector, /技術テーマ別/);
  assert.match(selector, /独立した非公式/); assert.match(selector, /公式ロゴは含みません/);
  assert.match(selector, /Claude Codeの紹介にはCode画面/);
  assert.match(selector, /edit\(\{ screenTheme: event.target.value \}\)/);
  assert.doesNotMatch(selector, /clearCaptureConsent|perform\(|setFiles|setSelectedToken|api\./);
});

test('saved voice, rate, and pronunciation survive theme-only edits without mutating the saved recipe', () => {
  const draft = readyDraft(); const state = setup(draft);
  const saved = { id: draft.recipeId, versionId: 'version_voice', productionId: draft.productionId, revision: 3, recipe: {
    ...w.buildScreenExplainerRecipe(draft), voice: 'Microsoft Sayaka', rate: -1, pronunciations: [{ source: 'Claude Code', target: 'クロードコード' }],
  } };
  const original = structuredClone(saved.recipe);
  const restored = w.screenExplainerDraftFromRecipe(state.detail, saved);
  restored.shots.forEach((shot) => { shot.previewApproved = true; });
  const themed = w.parseScreenExplainerDraft({ ...restored, screenTheme: 'claude_code_v1' });
  const result = w.buildScreenExplainerRecipe(themed);
  assert.deepEqual(result, { ...original, screenTheme: 'claude_code_v1' });
  themed.pronunciations[0].target = 'changed';
  assert.deepEqual(saved.recipe, original);
  assert.equal(restored.pronunciations[0].target, 'クロードコード');
  for (const patch of [{ voice: '' }, { voice: 5 }, { rate: 11 }, { rate: null }, { pronunciations: [{ source: 'x', target: 'y', secret: true }] }, { pronunciations: null }]) {
    assert.throws(() => w.parseScreenExplainerDraft({ ...draft, ...patch }), /保存された/);
  }
});

test('copy and manual source approval gates reject overflow before any POST', () => {
  const draft = readyDraft();
  draft.shots[0].previewApproved = false;
  assert.throws(() => w.buildScreenExplainerRecipe(draft), /確認/);
  draft.shots[0].previewApproved = true; draft.shots[0].headline = 'あ'.repeat(11);
  assert.throws(() => w.buildScreenExplainerRecipe(draft), /見出し/);
  draft.shots[0].headline = 'A'.repeat(20); draft.shots[0].narration = 'あ'.repeat(20);
  assert.throws(() => w.buildScreenExplainerRecipe(draft), /19文字/);
  draft.shots[0].narration = 'あ'.repeat(19);
  assert.deepEqual(w.validateScreenExplainer(draft), []);
});

test('draft roundtrip is versioned, rejects paths and credentials, preserves recovery IDs', () => {
  const draft = captureDraft(); draft.shots[0].captureRunId = 'run_test'; draft.pending = { operation: 'capture', shotIndex: 0 };
  assert.deepEqual(JSON.parse(JSON.stringify(w.parseScreenExplainerDraft(draft))), draft);
  assert.throws(() => w.parseScreenExplainerDraft({ ...draft, apiKey: 'secret' }), /保存情報/);
  const bad = structuredClone(draft); bad.shots[0].sourcePath = 'C:/secret.mp4';
  assert.throws(() => w.parseScreenExplainerDraft(bad), /場面情報/);
  for (const url of ['https://example.com', 'http://localhost:5173', 'http://127.0.0.1:5173/?token=secret', 'http://user:pass@127.0.0.1:5173', 'http://127.0.0.1:5173/#secret', 'file:///C:/secret']) assert.throws(() => w.screenExplainerCaptureUrl(url));
  assert.equal(w.screenExplainerCaptureUrl('http://127.0.0.1:5173/demo'), 'http://127.0.0.1:5173/demo');
});

test('new-entry draft survives automatic production selection and canonical edits override old alias', () => {
  const values = new Map();
  const storage = { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
  const draft = makeDraft(); draft.productionCreated = true; draft.shots[0].captureRunId = 'run_recover';
  const newKey = `${w.SCREEN_EXPLAINER_STORAGE_KEY}:new`;
  w.persistScreenExplainerDraft(storage, draft, newKey);
  assert.equal(w.restoreScreenExplainerDraft(storage, draft.productionId).shots[0].captureRunId, 'run_recover');
  const edited = structuredClone(draft); edited.title = '新しいタイトル';
  w.persistScreenExplainerDraft(storage, edited, `${w.SCREEN_EXPLAINER_STORAGE_KEY}:${draft.productionId}`);
  assert.equal(w.restoreScreenExplainerDraft(storage).title, edited.title);
  assert.equal(w.restoreScreenExplainerDraft(storage, 'another_production'), undefined);
  values.delete(`${w.SCREEN_EXPLAINER_STORAGE_KEY}:${draft.productionId}`);
  assert.equal(w.restoreScreenExplainerDraft(storage, draft.productionId).title, draft.title);
});

test('storage verification failure blocks before the caller can send a POST', () => {
  assert.throws(() => w.persistScreenExplainerDraft({ getItem: () => null, setItem() {} }, makeDraft(), `${w.SCREEN_EXPLAINER_STORAGE_KEY}:new`), /送信を停止/);
});

test('late checkpoint after close persists the old production Job but cannot replace new UI state', () => {
  let generation = 1;
  const stored = new Map();
  let shown = { productionId: 'production_old', jobId: undefined };
  let busy = true;
  const old = w.createScreenExplainerSessionGuard(() => generation === 1, (value) => stored.set(value.productionId, value), (value) => { shown = value; });
  old.checkpoint({ productionId: 'production_old', pending: { operation: 'capture' } });
  // Close old dialog, open a different production, and start its own work.
  generation = 2;
  shown = { productionId: 'production_new', jobId: 'job_new' };
  old.checkpoint({ productionId: 'production_old', jobId: 'job_old_late_response' });
  old.update(() => { shown = { productionId: 'production_old' }; busy = false; });
  assert.deepEqual(stored.get('production_old'), { productionId: 'production_old', jobId: 'job_old_late_response' });
  assert.deepEqual(shown, { productionId: 'production_new', jobId: 'job_new' });
  assert.equal(busy, true);
  const current = w.createScreenExplainerSessionGuard(() => generation === 2, (value) => stored.set(value.productionId, value), (value) => { shown = value; });
  current.checkpoint({ productionId: 'production_new', jobId: 'job_new_complete' });
  current.update(() => { busy = false; });
  assert.equal(shown.jobId, 'job_new_complete');
  assert.equal(busy, false);
});

test('an aborted in-flight capture records its accepted Job then stops without a second capture POST', async () => {
  const draft = captureDraft(); const state = setup(draft);
  const controller = new AbortController();
  const original = state.api.executeLocalScreenCapture;
  state.api.executeLocalScreenCapture = async (...args) => { const accepted = await original(...args); controller.abort(); return accepted; };
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), { ...state.options, signal: controller.signal }), /監視を停止/);
  assert.equal(state.latest().shots[0].captureJobId, 'job_capture1');
  assert.equal(state.latest().pending, undefined);
  assert.equal(state.calls.filter(([type]) => type === 'capture').length, 1);
});

test('collect uses desktop viewport, only optional scroll, canonical MP4 and no recapture', async () => {
  const draft = captureDraft(); draft.shots[1].scroll = true;
  const state = setup(draft);
  const result = await w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options);
  assert.equal(state.calls.filter(([type]) => type === 'capture').length, 3);
  assert.equal(result.draft.shots.every((shot) => shot.artifactId.startsWith('art_capture') && !shot.previewApproved), true);
  const requests = state.calls.filter(([type]) => type === 'capture').map((row) => row[2]);
  assert.equal(requests.every((request) => request.viewportPreset === 'desktop_16_9' && request.durationMs === 5000), true);
  assert.deepEqual(requests[1].actions, [{ type: 'scroll', atMs: 2000, deltaY: 600 }]);
  await w.collectScreenExplainerAssets(state.api, result.draft, new Map(), state.options);
  assert.equal(state.calls.filter(([type]) => type === 'capture').length, 3);
});

test('unsafe URLs and missing File handles fail before production creation', async () => {
  const draft = captureDraft(); draft.shots[2].url = 'https://external.example';
  const state = setup(draft);
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options), /自動収録/);
  assert.equal(state.calls.length, 0);
  draft.shots[2].source = 'file'; draft.shots[2].url = '';
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options), /ファイル/);
  assert.equal(state.calls.length, 0);
});

test('interrupted multi-import retains completed material IDs without retrying unknown POST', async () => {
  const draft = makeDraft(); draft.shots.forEach((shot) => { shot.source = 'file'; });
  const state = setup(draft);
  const original = state.api.importVideo;
  state.api.importVideo = async (...args) => { if (args[1].name === 'second.mp4') throw new Error('transport lost'); return original(...args); };
  const files = new Map([[0, { name: 'first.mp4' }], [1, { name: 'second.mp4' }], [2, { name: 'third.mp4' }]]);
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, files, state.options), /transport/);
  const restored = state.latest();
  assert.equal(restored.shots[0].artifactId, 'art_import0');
  assert.deepEqual(restored.pending, { operation: 'import', shotIndex: 1 });
  await assert.rejects(w.collectScreenExplainerAssets(state.api, restored, files, state.options), /再送/);
  assert.equal(state.calls.filter(([type]) => type === 'import').length, 1);
});

test('unknown capture response is reconciled by its persisted Run without another POST', async () => {
  const draft = captureDraft();
  const state = setup(draft); const original = state.api.executeLocalScreenCapture; let once = true;
  state.api.executeLocalScreenCapture = async (...args) => { const result = await original(...args); if (once) { once = false; throw new Error('response lost'); } return result; };
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options), /response lost/);
  assert.equal(state.latest().pending.operation, 'capture');
  const result = await w.collectScreenExplainerAssets(state.api, state.latest(), new Map(), state.options);
  assert.equal(result.draft.shots[0].captureJobId, 'job_capture1');
  assert.equal(state.calls.filter(([type]) => type === 'capture').length, 3);
});

test('capture failure keeps its Job ID; replay only polls and does not POST', async () => {
  const draft = captureDraft(); const state = setup(draft); const original = state.api.executeLocalScreenCapture;
  state.api.executeLocalScreenCapture = async (...args) => { const result = await original(...args); result.status = 'failed'; result.message = 'page failed'; return result; };
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options), /page failed/);
  assert.equal(state.latest().shots[0].captureJobId, 'job_capture1');
  await assert.rejects(w.collectScreenExplainerAssets(state.api, state.latest(), new Map(), state.options), /page failed/);
  assert.equal(state.calls.filter(([type]) => type === 'capture').length, 1);
});

test('wrong-production capture response cannot bind a source or silently clear the pending marker', async () => {
  const draft = captureDraft(); const state = setup(draft); const original = state.api.executeLocalScreenCapture;
  state.api.executeLocalScreenCapture = async (...args) => ({ ...await original(...args), productionId: 'another_production' });
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options), /制作・Run/);
  assert.equal(state.latest().shots[0].artifactId, '');
  assert.equal(state.latest().pending.operation, 'capture');
});

test('execute saves a version and uses standard Job, then reuses unchanged execution', async () => {
  const draft = readyDraft(); const state = setup(draft); addReadyAssets(state, draft);
  const result = await w.executeScreenExplainer(state.api, draft, state.options);
  assert.equal(result.job.id, 'job_render1');
  assert.equal(result.draft.recipeRevision, 1);
  await w.executeScreenExplainer(state.api, result.draft, state.options);
  assert.equal(state.calls.filter(([type]) => type === 'save').length, 1);
  assert.equal(state.calls.filter(([type]) => type === 'execute').length, 1);
});

test('editing narration CAS-updates same recipe and renders new revision without collecting assets', async () => {
  const draft = readyDraft(); const state = setup(draft); addReadyAssets(state, draft);
  const first = await w.executeScreenExplainer(state.api, draft, state.options);
  const edited = structuredClone(first.draft); edited.shots[1].narration = '設定を確認しましょう。';
  const second = await w.executeScreenExplainer(state.api, edited, state.options);
  assert.equal(second.draft.recipeId, first.draft.recipeId);
  assert.equal(second.draft.recipeRevision, 2);
  assert.deepEqual(state.calls.filter(([type]) => type === 'save').map((row) => row[2]), [0, 1]);
  assert.equal(state.calls.some(([type]) => ['import', 'capture'].includes(type)), false);
});

test('only matching detailed render + four succeeded stages + technical QC pass + canonical master can complete', async () => {
  const draft = readyDraft(); const state = setup(draft); addReadyAssets(state, draft);
  const result = await w.executeScreenExplainer(state.api, draft, state.options);
  assert.equal(w.verifyScreenExplainerRender(result.job, result.draft).name, 'master-captioned.mp4');
  const mutations = [
    (value) => { value.type = 'local_screen_capture'; },
    (value) => { value.status = 'running'; },
    (value) => { value.result.technicalVerdict = 'fail'; },
    (value) => { value.result.jobs.qc.status = 'failed'; },
    (value) => { value.result.raw.run_id = 'wrong_run'; },
    (value) => { value.result.raw.qc.verdict = 'fail'; },
    (value) => { value.result.raw.narration_segment_start_ms = [0, 4000, 8000]; },
    (value) => { value.result.artifacts[0].name = 'screen-capture.mp4'; },
    (value) => { value.result.artifacts[0].path = 'outputs/foreign/master-captioned.mp4'; },
    (value) => { value.raw.payload.clips[0].video_artifact_id = 'art_wrong'; },
  ];
  for (const mutate of mutations) { const broken = structuredClone(result.job); mutate(broken); assert.throws(() => w.verifyScreenExplainerRender(broken, result.draft)); }
  assert.throws(() => w.verifyScreenExplainerRender(result.job, { ...result.draft, recipeRevision: 2 }));
});

test('Panel completion display is separate from capture progress and cleared for edits and reopening', async () => {
  const panel = await readFile(join(root, 'src/ScreenExplainerPanel.tsx'), 'utf8');
  assert.match(panel, /const \[completedRender, setCompletedRender\]/);
  assert.match(panel, /const finalVideos = completedRender\?\.result\?\.artifacts/);
  assert.match(panel, /setJob\(result\.job\); setCompletedRender\(result\.job\)/);
  assert.doesNotMatch(panel, /\{job\?\.status === 'succeeded' \? <button/);
  const editBody = panel.slice(panel.indexOf('const edit ='), panel.indexOf('const editShot ='));
  assert.match(editBody, /setCompletedRender\(undefined\)/);
  const performBody = panel.slice(panel.indexOf('const perform ='), panel.indexOf('const artifacts ='));
  assert.match(performBody, /setCompletedRender\(undefined\)/);
  assert.match(panel, /setBusy\(running\.current\)/);
  assert.match(performBody, /if \(controller\.current === abort\) \{ running\.current = false; setBusy\(false\); \}/);
});

test('save and execution response loss are read-reconciled, never reposted', async () => {
  const draft = readyDraft(); const state = setup(draft); addReadyAssets(state, draft);
  const save = state.api.saveAnnouncementRecipe; const execute = state.api.executeAnnouncementRecipe;
  state.api.saveAnnouncementRecipe = async (...args) => { await save(...args); throw new Error('save response lost'); };
  await assert.rejects(w.executeScreenExplainer(state.api, draft, state.options), /save response lost/);
  const savedPending = state.latest();
  state.api.executeAnnouncementRecipe = async (...args) => { await execute(...args); throw new Error('execute response lost'); };
  await assert.rejects(w.executeScreenExplainer(state.api, savedPending, state.options), /execute response lost/);
  const result = await w.executeScreenExplainer(state.api, state.latest(), state.options);
  assert.equal(result.job.status, 'succeeded');
  assert.equal(state.calls.filter(([type]) => type === 'save').length, 1);
  assert.equal(state.calls.filter(([type]) => type === 'execute').length, 1);
});

test('known CAS conflict remains visible, does not silently overwrite newer revision', async () => {
  const draft = readyDraft(); const state = setup(draft); addReadyAssets(state, draft);
  await w.executeScreenExplainer(state.api, draft, state.options);
  draft.shots[1].narration = '別の編集をしました。';
  await assert.rejects(w.executeScreenExplainer(state.api, draft, state.options), /conflict/);
  assert.equal(state.latest().pending, undefined);
  assert.equal(state.calls.filter(([type]) => type === 'execute').length, 1);
});

test('polling waits 2 seconds and abort never starts another job', async () => {
  const seen = [];
  let calls = 0;
  await w.waitScreenExplainerJob({ job: async () => ({ ...job('job_one'), status: ++calls === 1 ? 'running' : 'succeeded' }) }, 'job_one', { onDraft() {}, sleep: async (ms) => { seen.push(ms); } });
  assert.deepEqual(seen, [2000]);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(w.waitScreenExplainerJob({ job: async () => { throw new Error('must not request'); } }, 'job_one', { onDraft() {}, signal: controller.signal }), /監視を停止/);
});

test('loading a saved screen recipe preserves CAS identity, source trims and requests new preview approval', () => {
  const draft = readyDraft(); draft.shots[0].startMs = 1500;
  const recipe = w.buildScreenExplainerRecipe(draft);
  const state = setup(draft);
  const saved = { id: draft.recipeId, versionId: 'version_3', productionId: draft.productionId, revision: 3, recipe };
  const restored = w.screenExplainerDraftFromRecipe(state.detail, saved);
  assert.equal(restored.recipeRevision, 3); assert.equal(restored.recipeId, draft.recipeId);
  assert.equal(restored.shots[0].startMs, 1500);
  assert.equal(restored.shots.every((shot) => !shot.previewApproved), true);
  assert.throws(() => w.screenExplainerDraftFromRecipe(state.detail, { ...saved, recipe: { ...recipe, templatePreset: 'shorts_ja_15s_v1' } }), /画面解説/);
});

test('shared Claude capture requires fresh explicit consent before any create or capture POST', async () => {
  const draft = sharedDraft(); const state = setupShared(draft);
  for (const consent of [undefined, { selectionToken: 'test', confirmCapture: false }, { selectionToken: '', confirmCapture: true }]) {
    await assert.rejects(w.collectClaudeScreenExplainer(state.api, draft, consent, state.options), /先にClaude/);
  }
  assert.equal(state.calls.length, 0);
  await assert.rejects(w.collectScreenExplainerAssets(state.api, draft, new Map(), state.options), /先にClaude/);
  assert.equal(state.calls.length, 0);
});

test('one Claude recording binds three consecutive silent intervals and reload reuses it without POST', async () => {
  const draft = sharedDraft(); const state = setupShared(draft);
  const result = await w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, state.options);
  assert.match(result.draft.sharedCaptureRequestId, /^claude_capture_[0-9a-f]{32}$/);
  assert.equal(result.draft.sharedCaptureJobId, 'job_claude');
  assert.deepEqual(result.draft.shots.map((shot) => [shot.artifactId, shot.startMs, shot.previewApproved]), [['art_claude', 0, false], ['art_claude', 5000, false], ['art_claude', 10000, false]]);
  const request = state.calls.find(([type]) => type === 'claude')[2];
  assert.equal(request.durationMs, 15000); assert.equal(request.confirmCapture, true);
  result.draft.shots.forEach((shot) => { shot.previewApproved = true; });
  const reloaded = w.parseScreenExplainerDraft(JSON.parse(JSON.stringify(result.draft)));
  const again = await w.collectScreenExplainerAssets(state.api, reloaded, new Map(), state.options);
  assert.equal(again.draft.shots.every((shot) => shot.previewApproved), true);
  const recipe = w.buildScreenExplainerRecipe(again.draft);
  assert.deepEqual(recipe.scenes.map((shot) => [shot.startMs, shot.endMs, shot.volumePercent]), [[0, 5000, 0], [5000, 10000, 0], [10000, 15000, 0]]);
  assert.equal(state.calls.filter(([type]) => type === 'claude').length, 1);
  assert.equal(state.calls.some(([type]) => ['run', 'capture', 'import'].includes(type)), false);
});

test('unknown Claude POST response is recovered by persisted receipt GET and never reposted', async () => {
  const draft = sharedDraft(); const state = setupShared(draft); const original = state.api.executeClaudeCapture;
  state.api.executeClaudeCapture = async (...args) => { await original(...args); throw new Error('lost Claude response'); };
  await assert.rejects(w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, state.options), /lost Claude/);
  const pending = w.parseScreenExplainerDraft(JSON.parse(JSON.stringify(state.latest())));
  assert.equal(pending.pending.operation, 'claude_capture');
  const result = await w.collectScreenExplainerAssets(state.api, pending, new Map(), state.options);
  assert.equal(result.draft.sharedCaptureRequestId, pending.sharedCaptureRequestId);
  assert.equal(result.draft.sharedCaptureJobId, 'job_claude');
  assert.equal(result.draft.pending, undefined);
  assert.equal(state.calls.filter(([type]) => type === 'claude').length, 1);
  assert.equal(state.calls.filter(([type]) => type === 'claude-read').length, 1);
});

test('unresolved Claude receipt stays blocked even if fresh consent is provided', async () => {
  const draft = sharedDraft(); const state = setupShared(draft);
  state.api.executeClaudeCapture = async () => { state.calls.push(['claude']); throw new Error('network lost'); };
  await assert.rejects(w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, state.options), /network/);
  const pending = state.latest();
  await assert.rejects(w.collectClaudeScreenExplainer(state.api, pending, claudeConsent, state.options), /受付を確認できません/);
  assert.equal(state.latest().pending.operation, 'claude_capture');
  assert.equal(state.calls.filter(([type]) => type === 'claude').length, 1);
});

test('failed or cancelled shared capture retains one Job ID and never creates another recording', async () => {
  for (const status of ['failed', 'cancelled']) {
    const draft = sharedDraft(); const state = setupShared(draft); const original = state.api.executeClaudeCapture;
    state.api.executeClaudeCapture = async (...args) => { const result = await original(...args); result.status = status; return result; };
    await assert.rejects(w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, state.options), new RegExp(status));
    assert.equal(state.latest().sharedCaptureJobId, 'job_claude');
    await assert.rejects(w.collectScreenExplainerAssets(state.api, state.latest(), new Map(), state.options), new RegExp(status));
    assert.equal(state.calls.filter(([type]) => type === 'claude').length, 1);
  }
});

test('closing during accepted Claude POST persists the Job before aborting monitoring', async () => {
  const draft = sharedDraft(); const state = setupShared(draft); const original = state.api.executeClaudeCapture;
  const controller = new AbortController();
  state.api.executeClaudeCapture = async (...args) => { const result = await original(...args); controller.abort(); return result; };
  await assert.rejects(w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, { ...state.options, signal: controller.signal }), /監視を停止/);
  assert.equal(state.latest().sharedCaptureJobId, 'job_claude');
  assert.equal(state.latest().pending, undefined);
  assert.equal(state.calls.filter(([type]) => type === 'claude').length, 1);
});

test('wrong Claude lineage, receipt or ambiguous canonical artifact cannot bind a source', async () => {
  for (const mutate of [
    (value) => { value.productionId = 'production_foreign'; },
    (value) => { value.type = 'local_screen_capture'; },
    (value) => { value.raw.payload.capture_request_id = 'claude_capture_' + 'f'.repeat(32); },
    (value) => { value.result.artifacts[0].name = 'other.mp4'; },
    (value) => { value.result.artifacts.push({ ...value.result.artifacts[0], id: 'art_duplicate' }); },
  ]) {
    const draft = sharedDraft(); const state = setupShared(draft); const original = state.api.executeClaudeCapture;
    state.api.executeClaudeCapture = async (...args) => { const value = await original(...args); mutate(value); return value; };
    await assert.rejects(w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, state.options));
    assert.equal(state.latest().shots.every((shot) => !shot.artifactId), true);
    assert.equal(state.calls.filter(([type]) => type === 'claude').length, 1);
  }
});

test('shared duration edits realign intervals and reject overshoot before recipe save or render', async () => {
  const draft = sharedDraft(); const state = setupShared(draft);
  const result = await w.collectClaudeScreenExplainer(state.api, draft, claudeConsent, state.options);
  result.draft.shots.forEach((shot) => { shot.previewApproved = true; });
  result.draft.shots[0].durationMs = 6000;
  assert.throws(() => w.buildScreenExplainerRecipe(result.draft), /連続区間/);
  result.draft.shots = w.alignSharedScreenExplainerShots(result.draft.shots);
  assert.deepEqual(result.draft.shots.map((shot) => shot.startMs), [0, 6000, 11000]);
  assert.equal(result.draft.shots[1].previewApproved, false);
  result.draft.shots.forEach((shot) => { shot.previewApproved = true; });
  await assert.rejects(w.executeScreenExplainer(state.api, result.draft, state.options), /指定した区間より短い/);
  assert.equal(state.calls.some(([type]) => ['save', 'execute'].includes(type)), false);
});

test('closed shared draft only stores receipt and IDs, never selection tokens or consent', () => {
  const draft = sharedDraft(); draft.sharedCaptureRequestId = 'claude_capture_' + 'a'.repeat(32); draft.sharedCaptureJobId = 'job_shared';
  assert.equal(w.parseScreenExplainerDraft(draft).sharedCaptureJobId, 'job_shared');
  for (const field of ['selectionToken', 'inspection', 'confirmCapture', 'captureConfirmed']) assert.throws(() => w.parseScreenExplainerDraft({ ...draft, [field]: 'secret' }), /保存情報/);
  assert.throws(() => w.parseScreenExplainerDraft({ ...draft, sharedCaptureRequestId: 'bad' }), /リクエストID/);
  const shotToken = structuredClone(draft); shotToken.shots[0].selectionToken = 'secret';
  assert.throws(() => w.parseScreenExplainerDraft(shotToken), /場面情報/);
});

test('focus region is bounded, closed, round-trips through recipe and matches render lineage', async () => {
  const focus = { x: 0.25, y: 0.2, width: 0.5, height: 0.6 };
  assert.equal(w.validScreenExplainerFocus(focus), true);
  for (const bad of [null, {}, { ...focus, width: 0.19 }, { ...focus, x: 0.8 }, { ...focus, y: -0.1 }, { ...focus, token: 'secret' }, { ...focus, x: NaN }, { ...focus, x: 0.12345 }]) assert.equal(w.validScreenExplainerFocus(bad), false);
  const draft = readyDraft(); draft.shots[1].focusRegion = focus;
  const roundtrip = w.parseScreenExplainerDraft(JSON.parse(JSON.stringify(draft)));
  assert.deepEqual(roundtrip.shots[1].focusRegion, focus);
  const state = setup(draft); addReadyAssets(state, draft);
  const result = await w.executeScreenExplainer(state.api, draft, state.options);
  assert.deepEqual(result.job.raw.payload.clips[1].focus_region, focus);
  const restored = w.screenExplainerDraftFromRecipe(state.detail, state.detail.announcementRecipes[0]);
  assert.deepEqual(restored.shots[1].focusRegion, focus);
  const changed = structuredClone(result.job); changed.raw.payload.clips[1].focus_region.x = 0.3;
  assert.throws(() => w.verifyScreenExplainerRender(changed, result.draft), /照合できない/);
  draft.shots[0].focusRegion = null;
  assert.throws(() => w.parseScreenExplainerDraft(draft), /注目範囲/);
});

test('Panel Claude consent is transient, start and cancellation are separate explicit actions', async () => {
  const panel = await readFile(join(root, 'src/ScreenExplainerPanel.tsx'), 'utf8');
  assert.match(panel, /useState<ClaudeCaptureInspection>/);
  assert.match(panel, /Date\.now\(\) >= inspectionExpiresAt/);
  assert.match(panel, /onClick=\{\(\) => void inspectClaude\(\)\}/);
  assert.match(panel, /onClick=\{\(\) => void perform\('claude'\)\}/);
  assert.match(panel, /onClick=\{\(\) => void cancelCapture\(\)\}/);
  assert.match(panel, /閉じても収録は止まりません/);
  const closeBody = panel.slice(panel.indexOf('const close ='), panel.indexOf('const reset ='));
  assert.match(closeBody, /clearCaptureConsent\(\)/);
  assert.doesNotMatch(closeBody, /cancelJob/);
  assert.doesNotMatch(panel, /edit\(\{[^}]*selectionToken/);
});
