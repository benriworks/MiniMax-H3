import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const helperSource = await readFile(join(testDist, 'simpleCreate.js'), 'utf8');
const helperUrl = `data:text/javascript;base64,${Buffer.from(helperSource).toString('base64')}`;
const helper = await import(helperUrl);
const workflowSource = await readFile(join(testDist, 'simpleCreateWorkflow.js'), 'utf8');
const workflow = await import(`data:text/javascript;base64,${Buffer.from(
  workflowSource.replace("from './simpleCreate'", `from '${helperUrl}'`),
).toString('base64')}`);

const intent = {
  schemaVersion: 1,
  productionId: `production_${'1'.repeat(32)}`,
  recipeId: `announcement_${'2'.repeat(32)}`,
  title: '秋のイベント告知',
  templateId: 'event_v1',
  message: '9月15日\nオンライン開催',
};

const artifact = (value, durationSeconds = 5.5) => ({
  id: `art_${value.repeat(32)}`,
  name: `${value}.mp4`,
  kind: 'video',
  durationSeconds,
  metadata: {},
  raw: {},
});

test('storyboard shows exactly the compiled headlines and narration for every template', () => {
  for (const template of helper.SIMPLE_CREATE_TEMPLATES) {
    const current = { ...intent, templateId: template.id };
    const expected = helper.buildSimpleCreateRecipe(current, [artifact('a')]).scenes.map(({ role, headline, narration }) => ({ role, headline, narration }));
    assert.deepEqual(helper.simpleCreateStoryboard(current.templateId, current.message), expected);
  }
  assert.equal(helper.simpleCreateStoryboard('event_v1', '  ')[1].narration, '');
  assert.equal(helper.simpleCreateStoryboard('event_v1', '  参加しませんか？  ')[1].narration, '参加しませんか？');
});

test('simple create exposes exactly three fixed version-1 templates', () => {
  assert.deepEqual(helper.SIMPLE_CREATE_TEMPLATES.map((item) => [item.id, item.version]), [
    ['announcement_v1', 1],
    ['event_v1', 1],
    ['recruitment_v1', 1],
  ]);
  assert.deepEqual(helper.validateSimpleCreateFields(intent.title, intent.templateId, intent.message), []);
  assert.match(helper.validateSimpleCreateFields('x', 'event_v1', '12345678901234567890123456789012345678901')[0], /20文字/);
});

test('simple create intent parser is closed and never accepts file paths', () => {
  assert.deepEqual(helper.parseSimpleCreateIntent(intent), intent);
  assert.throws(() => helper.parseSimpleCreateIntent({ ...intent, sourcePath: 'C:/secret/source.mp4' }), /保留情報/);
  assert.throws(() => helper.parseSimpleCreateIntent({ ...intent, productionId: 'production_bad' }), /保留情報/);
});

test('simple create validates the actual 20 half-width headline limit before any import or job', () => {
  for (const message of ['あ'.repeat(10), 'A'.repeat(20), 'ｶ'.repeat(20), 'あ'.repeat(10) + '\n' + 'い'.repeat(10)]) {
    assert.deepEqual(helper.validateSimpleCreateFields('test', 'announcement_v1', message), []);
  }
  for (const message of ['あ'.repeat(11), 'A'.repeat(21), 'ｶ'.repeat(21)]) {
    assert.match(helper.validateSimpleCreateFields('test', 'announcement_v1', message)[0], /全角10/);
    assert.throws(() => helper.createSimpleCreateIntent({ title: 'test', templateId: 'announcement_v1', message }, () => { throw new Error('ID must not be issued'); }), /全角10/);
  }
});

test('simple create compiles 1-3 artifacts to the existing exact Announcement v1 recipe', () => {
  const one = helper.buildSimpleCreateRecipe(intent, [artifact('a')]);
  assert.deepEqual(one.scenes.map((scene) => scene.role), ['hook', 'message', 'cta']);
  assert.deepEqual(one.scenes.map((scene) => scene.videoArtifactId), [
    `art_${'a'.repeat(32)}`,
    `art_${'a'.repeat(32)}`,
    `art_${'a'.repeat(32)}`,
  ]);
  assert.deepEqual(one.scenes.map((scene) => scene.endMs), [5167, 5167, 5166]);
  assert.equal(one.scenes[1].headline, intent.message);
  assert.equal(one.scenes[1].narration, '9月15日 オンライン開催。');
  assert.equal(one.templatePreset, 'shorts_ja_15s_v1');
  assert.equal(one.captionStylePreset, 'shorts_ja_large_v1');
  assert.equal(one.audioMixPreset, 'narration_only_v1');
  assert.equal(one.variant, 'captioned');
  assert.equal(JSON.stringify(one).includes('C:/'), false);

  const two = helper.buildSimpleCreateRecipe(intent, [artifact('a'), artifact('b')]);
  assert.deepEqual(two.scenes.map((scene) => scene.videoArtifactId), [
    `art_${'a'.repeat(32)}`,
    `art_${'b'.repeat(32)}`,
    `art_${'b'.repeat(32)}`,
  ]);
});

const production = (artifacts = []) => ({
  id: intent.productionId,
  title: intent.title,
  status: 'pending',
  tags: [],
  raw: {},
  runs: [],
  artifacts,
  events: [],
  approvals: [],
  costs: [],
  announcementRecipes: [],
  announcementRecipeVersions: [],
  announcementExecutions: [],
});

test('simple create workflow uses one deadline and read-before-write resume identities', async () => {
  const imported = [artifact('a'), artifact('b')];
  let saved;
  let execution;
  let saveCalls = 0;
  let executeCalls = 0;
  let importCalls = 0;
  const job = { id: `job_${'3'.repeat(32)}`, productionId: intent.productionId, status: 'pending', type: 'detailed_test_video', raw: {} };
  const fake = {
    createProduction: async () => production(),
    production: async () => production(imported),
    importVideo: async (_productionId, _file) => {
      const result = imported[importCalls % imported.length];
      importCalls += 1;
      return { artifact: result, deduplicated: importCalls > imported.length, raw: {} };
    },
    announcementRecipes: async () => ({
      recipes: saved ? [saved] : [],
      recipeVersions: saved ? [saved] : [],
      executions: execution ? [execution] : [],
    }),
    saveAnnouncementRecipe: async (_productionId, recipeId, _revision, recipe) => {
      saveCalls += 1;
      saved = {
        id: recipeId,
        versionId: `announcement_version_${'4'.repeat(32)}`,
        productionId: intent.productionId,
        revision: 1,
        digest: 'A'.repeat(64),
        versionCount: 1,
        recipe,
        raw: {},
      };
      return saved;
    },
    executeAnnouncementRecipe: async () => {
      executeCalls += 1;
      execution = {
        recipeId: saved.id,
        recipeVersionId: saved.versionId,
        recipeRevision: saved.revision,
        recipeDigest: saved.digest,
        jobId: job.id,
        runId: `run_${'5'.repeat(32)}`,
        revisionId: `revision_${'6'.repeat(32)}`,
        requestKey: 'B'.repeat(64),
        deduplicated: false,
        raw: {},
      };
      return job;
    },
    job: async () => job,
    isResponseLoss: () => false,
  };
  const files = [
    new File(['a'], 'first.mp4', { type: 'video/mp4' }),
    new File(['b'], 'second.mp4', { type: 'video/mp4' }),
  ];
  const first = await workflow.runSimpleCreateWorkflow(fake, intent, files, { deadlineAt: Date.now() + 5_000 });
  assert.equal(first.resumedRecipe, false);
  assert.equal(first.resumedExecution, false);
  assert.equal(saveCalls, 1);
  assert.equal(executeCalls, 1);

  const second = await workflow.runSimpleCreateWorkflow(fake, intent, files, { deadlineAt: Date.now() + 5_000 });
  assert.equal(second.resumedRecipe, true);
  assert.equal(second.resumedExecution, true);
  assert.equal(second.deduplicatedImports, 2);
  assert.equal(saveCalls, 1, 'the saved revision must be reused');
  assert.equal(executeCalls, 1, 'the exact execution must be reused');
});

test('simple create reconciles response loss without minting new production, recipe, or execution IDs', async () => {
  const responseLoss = Object.assign(new Error('lost'), { responseLost: true });
  const imported = artifact('c');
  let importCalls = 0;
  let saved;
  let execution;
  const job = { id: `job_${'7'.repeat(32)}`, productionId: intent.productionId, status: 'pending', type: 'detailed_test_video', raw: {} };
  const fake = {
    createProduction: async () => { throw responseLoss; },
    production: async () => production([imported]),
    importVideo: async () => {
      importCalls += 1;
      if (importCalls === 1) throw responseLoss;
      return { artifact: imported, deduplicated: true, raw: {} };
    },
    announcementRecipes: async () => ({
      recipes: saved ? [saved] : [],
      recipeVersions: saved ? [saved] : [],
      executions: execution ? [execution] : [],
    }),
    saveAnnouncementRecipe: async (_productionId, recipeId, _revision, recipe) => {
      saved = {
        id: recipeId,
        versionId: `announcement_version_${'8'.repeat(32)}`,
        productionId: intent.productionId,
        revision: 1,
        digest: 'C'.repeat(64),
        versionCount: 1,
        recipe,
        raw: {},
      };
      throw responseLoss;
    },
    executeAnnouncementRecipe: async () => {
      execution = {
        recipeId: saved.id,
        recipeVersionId: saved.versionId,
        recipeRevision: saved.revision,
        recipeDigest: saved.digest,
        jobId: job.id,
        runId: `run_${'9'.repeat(32)}`,
        revisionId: `revision_${'a'.repeat(32)}`,
        requestKey: 'D'.repeat(64),
        deduplicated: false,
        raw: {},
      };
      throw responseLoss;
    },
    job: async (jobId) => {
      assert.equal(jobId, job.id);
      return job;
    },
    isResponseLoss: (error) => error?.responseLost === true,
  };
  const result = await workflow.runSimpleCreateWorkflow(
    fake,
    intent,
    [new File(['c'], 'one.mp4')],
    { deadlineAt: Date.now() + 5_000 },
  );
  assert.equal(importCalls, 2);
  assert.equal(result.recipeId, intent.recipeId);
  assert.equal(result.resumedRecipe, true);
  assert.equal(result.resumedExecution, true);
  assert.equal(result.job.id, job.id);
});

test('simple create rejects an expired shared deadline before a network call', async () => {
  let calls = 0;
  const never = async () => { calls += 1; throw new Error('must not run'); };
  const fake = {
    createProduction: never,
    production: never,
    importVideo: never,
    announcementRecipes: never,
    saveAnnouncementRecipe: never,
    executeAnnouncementRecipe: never,
    job: never,
    isResponseLoss: () => false,
  };
  await assert.rejects(
    () => workflow.runSimpleCreateWorkflow(fake, intent, [new File(['a'], 'one.mp4')], { deadlineAt: 99, now: () => 100 }),
    /処理期限/,
  );
  assert.equal(calls, 0);
});

test('Studio presents simple create as the primary path and preserves the advanced escape hatch', async () => {
  const appSource = await readFile(join(studioRoot, 'src', 'App.tsx'), 'utf8');
  const wizardSource = await readFile(join(studioRoot, 'src', 'SimpleCreateWizard.tsx'), 'utf8');
  const stylesSource = await readFile(join(studioRoot, 'src', 'styles.css'), 'utf8');
  assert.match(appSource, /<SimpleCreateWizard/);
  assert.match(appSource, />\s*かんたん制作\s*</);
  assert.match(wizardSource, /詳細設定から始める/);
  assert.match(wizardSource, /API tokenや秘密情報/);
  assert.match(stylesSource, /\.simple-create-dialog/);
});
