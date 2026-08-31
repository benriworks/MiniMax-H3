import { buildSimpleCreateRecipe, simpleCreateRecipesMatch, type SimpleCreateIntent } from './simpleCreate';
import type {
  AnnouncementExecutionRecord,
  AnnouncementRecipeRecord,
  ArtifactImportResponse,
  Job,
  ProductionDetail,
  ProductionSummary,
} from './types';

export type SimpleCreatePhase = 'production' | 'imports' | 'recipe' | 'execution' | 'completed';

export interface SimpleCreateWorkflowApi {
  createProduction(productionId: string, title: string, signal?: AbortSignal): Promise<ProductionSummary>;
  production(productionId: string, signal?: AbortSignal): Promise<ProductionDetail>;
  importVideo(productionId: string, file: File, signal?: AbortSignal): Promise<ArtifactImportResponse>;
  announcementRecipes(productionId: string, signal?: AbortSignal): Promise<{
    recipes: AnnouncementRecipeRecord[];
    recipeVersions: AnnouncementRecipeRecord[];
    executions: AnnouncementExecutionRecord[];
  }>;
  saveAnnouncementRecipe(
    productionId: string,
    recipeId: string,
    expectedRevision: number,
    recipe: AnnouncementRecipeRecord['recipe'],
    signal?: AbortSignal,
  ): Promise<AnnouncementRecipeRecord>;
  executeAnnouncementRecipe(productionId: string, recipeId: string, revision: number, signal?: AbortSignal): Promise<Job>;
  job(jobId: string, signal?: AbortSignal): Promise<Job>;
  isResponseLoss(error: unknown): boolean;
}

export interface SimpleCreateProgress {
  phase: SimpleCreatePhase;
  fileIndex?: number;
  fileCount?: number;
  deduplicated?: boolean;
}

export interface SimpleCreateWorkflowResult {
  productionId: string;
  recipeId: string;
  recipeVersionId: string;
  job: Job;
  deduplicatedImports: number;
  resumedRecipe: boolean;
  resumedExecution: boolean;
}

export class SimpleCreateDeadlineError extends Error {
  constructor() {
    super('かんたん制作の処理期限を超えました。同じ保留IDで再試行してください。');
    this.name = 'SimpleCreateDeadlineError';
  }
}

type DeadlineCall = <T>(operation: (signal: AbortSignal) => Promise<T>) => Promise<T>;

const deadlineCaller = (deadlineAt: number, now: () => number): DeadlineCall => async <T>(
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> => {
  const remaining = Math.floor(deadlineAt - now());
  if (remaining <= 0) throw new SimpleCreateDeadlineError();
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), remaining);
  try {
    return await operation(controller.signal);
  } catch (error) {
    if (controller.signal.aborted && now() >= deadlineAt) throw new SimpleCreateDeadlineError();
    throw error;
  } finally {
    globalThis.clearTimeout(timer);
  }
};

const matchingRecipe = (
  records: readonly AnnouncementRecipeRecord[],
  intent: SimpleCreateIntent,
  expected: AnnouncementRecipeRecord['recipe'],
): AnnouncementRecipeRecord | undefined => records.find((record) => (
  record.id === intent.recipeId
  && record.productionId === intent.productionId
  && record.revision === 1
  && simpleCreateRecipesMatch(expected, record.recipe)
));

const matchingExecution = (
  records: readonly AnnouncementExecutionRecord[],
  saved: AnnouncementRecipeRecord,
): AnnouncementExecutionRecord | undefined => records.find((record) => (
  record.recipeId === saved.id
  && record.recipeVersionId === saved.versionId
  && record.recipeRevision === saved.revision
  && record.recipeDigest === saved.digest
));

/**
 * Run the existing create/import/versioned-recipe/execute contracts under one
 * deadline. Stable IDs and read-before-write reconciliation make a browser
 * reload retry safe without adding a second backend orchestration surface.
 */
export const runSimpleCreateWorkflow = async (
  api: SimpleCreateWorkflowApi,
  intent: SimpleCreateIntent,
  files: readonly File[],
  options: {
    deadlineAt: number;
    now?: () => number;
    onProgress?: (progress: SimpleCreateProgress) => void;
  },
): Promise<SimpleCreateWorkflowResult> => {
  if (files.length < 1 || files.length > 3) throw new TypeError('動画素材は1〜3件選択してください。');
  const call = deadlineCaller(options.deadlineAt, options.now ?? Date.now);
  const progress = options.onProgress ?? (() => undefined);

  progress({ phase: 'production' });
  try {
    await call((signal) => api.createProduction(intent.productionId, intent.title, signal));
  } catch (error) {
    if (!api.isResponseLoss(error)) throw error;
    const existing = await call((signal) => api.production(intent.productionId, signal));
    if (existing.id !== intent.productionId || existing.title !== intent.title) throw error;
  }

  progress({ phase: 'imports', fileIndex: 0, fileCount: files.length });
  const imports: ArtifactImportResponse[] = [];
  for (const [index, file] of files.entries()) {
    let imported: ArtifactImportResponse;
    try {
      imported = await call((signal) => api.importVideo(intent.productionId, file, signal));
    } catch (error) {
      if (!api.isResponseLoss(error)) throw error;
      // import-video is content-addressed. Retry the exact browser File once;
      // a completed first request returns the existing artifact as deduped.
      imported = await call((signal) => api.importVideo(intent.productionId, file, signal));
    }
    imports.push(imported);
    progress({
      phase: 'imports',
      fileIndex: index + 1,
      fileCount: files.length,
      deduplicated: imported.deduplicated,
    });
  }

  const detail = await call((signal) => api.production(intent.productionId, signal));
  const artifacts = imports.map((result) => {
    if (!result.artifact) throw new Error('動画取込のartifact identityを確認できません。');
    return detail.artifacts.find((artifact) => artifact.id === result.artifact!.id) ?? result.artifact;
  });
  const recipe = buildSimpleCreateRecipe(intent, artifacts);

  progress({ phase: 'recipe' });
  let snapshot = await call((signal) => api.announcementRecipes(intent.productionId, signal));
  let saved = matchingRecipe(snapshot.recipeVersions, intent, recipe);
  let resumedRecipe = Boolean(saved);
  if (!saved) {
    try {
      saved = await call((signal) => api.saveAnnouncementRecipe(
        intent.productionId,
        intent.recipeId,
        0,
        recipe,
        signal,
      ));
    } catch (error) {
      if (!api.isResponseLoss(error)) throw error;
      snapshot = await call((signal) => api.announcementRecipes(intent.productionId, signal));
      saved = matchingRecipe(snapshot.recipeVersions, intent, recipe);
      if (!saved) throw error;
      resumedRecipe = true;
    }
  }
  if (!saved) throw new Error('保存済みrecipeのidentityを確認できません。');
  const savedRecord = saved;

  progress({ phase: 'execution' });
  snapshot = await call((signal) => api.announcementRecipes(intent.productionId, signal));
  let execution = matchingExecution(snapshot.executions, savedRecord);
  let resumedExecution = Boolean(execution);
  let job: Job;
  if (execution) {
    const existingExecution = execution;
    job = await call((signal) => api.job(existingExecution.jobId, signal));
  } else {
    try {
      job = await call((signal) => api.executeAnnouncementRecipe(
        intent.productionId,
        intent.recipeId,
        savedRecord.revision,
        signal,
      ));
    } catch (error) {
      if (!api.isResponseLoss(error)) throw error;
      snapshot = await call((signal) => api.announcementRecipes(intent.productionId, signal));
      const reconciledExecution = matchingExecution(snapshot.executions, savedRecord);
      if (!reconciledExecution) throw error;
      execution = reconciledExecution;
      resumedExecution = true;
      job = await call((signal) => api.job(reconciledExecution.jobId, signal));
    }
  }

  progress({ phase: 'completed' });
  return {
    productionId: intent.productionId,
    recipeId: intent.recipeId,
    recipeVersionId: savedRecord.versionId,
    job,
    deduplicatedImports: imports.filter((item) => item.deduplicated).length,
    resumedRecipe,
    resumedExecution,
  };
};
