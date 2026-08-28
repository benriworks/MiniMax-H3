import type { AnnouncementExecutionRecord, AnnouncementRecipeRecord, Job } from './types';

export const ANNOUNCEMENT_REQUEST_TIMEOUT_MS = 15_000;
export const ANNOUNCEMENT_DUPLICATE_INTENT_STORAGE_KEY = 'minimax-h3-studio:announcement-duplicate-intent:v2:';

export interface AnnouncementDuplicateIntent {
  schemaVersion: 1;
  productionId: string;
  sourceRecipeId: string;
  sourceRecipeVersionId: string;
  sourceRevision: number;
  newRecipeId: string;
  name: string;
  createdAt: string;
}

export type AnnouncementDuplicateIntentMatch = Pick<
  AnnouncementDuplicateIntent,
  'productionId' | 'sourceRecipeId' | 'sourceRecipeVersionId' | 'sourceRevision' | 'name'
>;

export interface AnnouncementDuplicateIntentStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const ANNOUNCEMENT_RECIPE_ID = /^announcement_[0-9a-f]{32}$/;
const ANNOUNCEMENT_RECIPE_VERSION_ID = /^annv_[0-9a-f]{32}$/;

const browserLocalStorage = (): Storage | undefined => {
  try {
    return typeof window === 'undefined' ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
};

/**
 * localStorage keeps a pre-issued clone identity across panel unmounts and page
 * reloads. Access failures are surfaced so the caller can stop before POST.
 */
export const browserAnnouncementDuplicateIntentStorage: AnnouncementDuplicateIntentStorage = {
  getItem(key) {
    const storage = browserLocalStorage();
    if (!storage) throw new Error('localStorage is unavailable');
    return storage.getItem(key);
  },
  setItem(key, value) {
    const storage = browserLocalStorage();
    if (!storage) throw new Error('localStorage is unavailable');
    storage.setItem(key, value);
  },
  removeItem(key) {
    const storage = browserLocalStorage();
    if (!storage) throw new Error('localStorage is unavailable');
    storage.removeItem(key);
  },
};

const duplicateIntentMatches = (
  intent: AnnouncementDuplicateIntent,
  match: AnnouncementDuplicateIntentMatch,
): boolean => (
  intent.productionId === match.productionId
  && intent.sourceRecipeId === match.sourceRecipeId
  && intent.sourceRecipeVersionId === match.sourceRecipeVersionId
  && intent.sourceRevision === match.sourceRevision
  && intent.name === match.name
);

const isAnnouncementDuplicateIntentMatch = (match: AnnouncementDuplicateIntentMatch): boolean => (
  typeof match.productionId === 'string'
  && match.productionId.length > 0
  && match.productionId.length <= 512
  && !/[\u0000-\u001f\u007f]/.test(match.productionId)
  && ANNOUNCEMENT_RECIPE_ID.test(match.sourceRecipeId)
  && ANNOUNCEMENT_RECIPE_VERSION_ID.test(match.sourceRecipeVersionId)
  && Number.isInteger(match.sourceRevision)
  && match.sourceRevision >= 1
  && match.sourceRevision <= 1_000_000
  && typeof match.name === 'string'
  && match.name.trim().length > 0
  && match.name.length <= 120
  && !/[\r\n]/.test(match.name)
);

/** One exact source/name intent gets one independent atomic localStorage key. */
export const announcementDuplicateIntentStorageKey = (
  match: AnnouncementDuplicateIntentMatch,
): string => {
  if (!isAnnouncementDuplicateIntentMatch(match)) {
    throw new TypeError('announcement duplicate intent match is invalid');
  }
  return `${ANNOUNCEMENT_DUPLICATE_INTENT_STORAGE_KEY}${encodeURIComponent(match.productionId)}:${match.sourceRecipeId}:${match.sourceRecipeVersionId}:${match.sourceRevision}:${encodeURIComponent(match.name)}`;
};

/**
 * The backend recipe ID is 128-bit. Deriving those 128 bits from the complete
 * immutable source identity makes concurrent browser tabs converge on one ID.
 */
export const deterministicAnnouncementCloneRecipeId = async (
  match: AnnouncementDuplicateIntentMatch,
): Promise<string> => {
  const key = announcementDuplicateIntentStorageKey(match);
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error('Web Crypto is unavailable');
  const digest = new Uint8Array(await subtle.digest('SHA-256', new TextEncoder().encode(key)));
  return `announcement_${[...digest.slice(0, 16)].map((value) => value.toString(16).padStart(2, '0')).join('')}`;
};

const isAnnouncementDuplicateIntent = (value: unknown): value is AnnouncementDuplicateIntent => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  return candidate.schemaVersion === 1
    && typeof candidate.productionId === 'string'
    && candidate.productionId.length > 0
    && candidate.productionId.length <= 512
    && !/[\u0000-\u001f\u007f]/.test(candidate.productionId)
    && typeof candidate.sourceRecipeId === 'string'
    && ANNOUNCEMENT_RECIPE_ID.test(candidate.sourceRecipeId)
    && typeof candidate.sourceRecipeVersionId === 'string'
    && ANNOUNCEMENT_RECIPE_VERSION_ID.test(candidate.sourceRecipeVersionId)
    && Number.isInteger(candidate.sourceRevision)
    && Number(candidate.sourceRevision) >= 1
    && Number(candidate.sourceRevision) <= 1_000_000
    && typeof candidate.newRecipeId === 'string'
    && ANNOUNCEMENT_RECIPE_ID.test(candidate.newRecipeId)
    && typeof candidate.name === 'string'
    && candidate.name.trim().length > 0
    && candidate.name.length <= 120
    && !/[\r\n]/.test(candidate.name)
    && typeof candidate.createdAt === 'string'
    && Number.isFinite(Date.parse(candidate.createdAt));
};

export type AnnouncementDuplicateIntentStoreSnapshot =
  | { status: 'ready'; intent?: AnnouncementDuplicateIntent }
  | { status: 'corrupt' | 'unavailable'; intent?: undefined };

export const inspectAnnouncementDuplicateIntentStore = (
  storage: AnnouncementDuplicateIntentStorage,
  match: AnnouncementDuplicateIntentMatch,
): AnnouncementDuplicateIntentStoreSnapshot => {
  let raw: string | null;
  try {
    raw = storage.getItem(announcementDuplicateIntentStorageKey(match));
  } catch {
    return { status: 'unavailable' };
  }
  if (!raw) return { status: 'ready' };
  try {
    const parsed = JSON.parse(raw) as unknown;
    return isAnnouncementDuplicateIntent(parsed) && duplicateIntentMatches(parsed, match)
      ? { status: 'ready', intent: parsed }
      : { status: 'corrupt' };
  } catch {
    return { status: 'corrupt' };
  }
};

export const findAnnouncementDuplicateIntent = (
  storage: AnnouncementDuplicateIntentStorage,
  match: AnnouncementDuplicateIntentMatch,
): AnnouncementDuplicateIntent | undefined => (
  (() => {
    const snapshot = inspectAnnouncementDuplicateIntentStore(storage, match);
    if (snapshot.status !== 'ready') throw new Error(`announcement duplicate intent store is ${snapshot.status}`);
    return snapshot.intent;
  })()
);

/** Persist before the first POST so every retry reuses one closed clone ID. */
export const persistAnnouncementDuplicateIntent = async (
  storage: AnnouncementDuplicateIntentStorage,
  intent: AnnouncementDuplicateIntent,
): Promise<AnnouncementDuplicateIntent> => {
  if (!isAnnouncementDuplicateIntent(intent)) {
    throw new TypeError('announcement duplicate intent is invalid');
  }
  const deterministicId = await deterministicAnnouncementCloneRecipeId(intent);
  if (intent.newRecipeId !== deterministicId) {
    throw new TypeError('announcement duplicate intent ID is not deterministic');
  }
  const snapshot = inspectAnnouncementDuplicateIntentStore(storage, intent);
  if (snapshot.status !== 'ready') throw new Error(`announcement duplicate intent store is ${snapshot.status}`);
  // First writer wins. A stale render must never replace a persisted ID.
  if (snapshot.intent) return snapshot.intent;
  storage.setItem(announcementDuplicateIntentStorageKey(intent), JSON.stringify(intent));
  const verified = findAnnouncementDuplicateIntent(storage, intent);
  if (!verified) {
    throw new Error('announcement duplicate intent could not be persisted');
  }
  return verified;
};

/** Clear only the exact pre-issued clone identity after proof or explicit discard. */
export const clearAnnouncementDuplicateIntent = (
  storage: AnnouncementDuplicateIntentStorage,
  intent: AnnouncementDuplicateIntent,
): void => {
  const snapshot = inspectAnnouncementDuplicateIntentStore(storage, intent);
  if (snapshot.status !== 'ready') throw new Error(`announcement duplicate intent store is ${snapshot.status}`);
  if (snapshot.intent && snapshot.intent.newRecipeId !== intent.newRecipeId) {
    throw new Error('announcement duplicate intent identity changed');
  }
  storage.removeItem(announcementDuplicateIntentStorageKey(intent));
  const verified = inspectAnnouncementDuplicateIntentStore(storage, intent);
  if (
    verified.status !== 'ready'
    || verified.intent
  ) {
    throw new Error('announcement duplicate intent could not be cleared');
  }
};

export const clearAnnouncementDuplicateIntentStore = (
  storage: AnnouncementDuplicateIntentStorage,
  match: AnnouncementDuplicateIntentMatch,
): void => {
  storage.removeItem(announcementDuplicateIntentStorageKey(match));
  const verified = inspectAnnouncementDuplicateIntentStore(storage, match);
  if (verified.status !== 'ready' || verified.intent) {
    throw new Error('announcement duplicate intent store could not be cleared');
  }
};

export const announcementCloneMatchesIntent = (
  record: AnnouncementRecipeRecord,
  intent: AnnouncementDuplicateIntent,
): boolean => (
  record.id === intent.newRecipeId
  && record.productionId === intent.productionId
  && record.revision === 1
  && record.cloneSourceVersionId === intent.sourceRecipeVersionId
  && record.recipe.name === intent.name
);

export class AnnouncementRequestTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`告知動画APIが${Math.ceil(timeoutMs / 1_000)}秒以内に応答しませんでした。`);
    this.name = 'AnnouncementRequestTimeoutError';
    this.timeoutMs = timeoutMs;
  }
}

/**
 * Bound every announcement admission/reconciliation request. The callback must
 * forward the private AbortSignal to fetch so a timed-out request does not keep
 * consuming a browser connection after the recovery UI becomes available.
 */
export const runAnnouncementRequestWithTimeout = async <T>(
  operation: (signal: AbortSignal) => Promise<T>,
  timeoutMs = ANNOUNCEMENT_REQUEST_TIMEOUT_MS,
): Promise<T> => {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new RangeError('timeoutMs must be a positive finite number');
  }
  const controller = new AbortController();
  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timeoutHandle = setTimeout(() => {
      controller.abort();
      reject(new AnnouncementRequestTimeoutError(timeoutMs));
    }, timeoutMs);
  });
  try {
    return await Promise.race([operation(controller.signal), timeout]);
  } catch (error) {
    if (controller.signal.aborted && !(error instanceof AnnouncementRequestTimeoutError)) {
      throw new AnnouncementRequestTimeoutError(timeoutMs);
    }
    throw error;
  } finally {
    if (timeoutHandle !== undefined) clearTimeout(timeoutHandle);
  }
};

export interface AnnouncementSubmissionGuard {
  productionId: string;
  recipeId: string;
  recipeVersionId: string;
  recipeRevision: number;
  recipeDigest: string;
  knownExecutionKeys: ReadonlySet<string>;
  automaticRetryAttempted: boolean;
}

export interface AnnouncementRecoveryCandidates {
  fresh: AnnouncementExecutionRecord[];
}

export interface AnnouncementRetryRequest {
  productionId: string;
  recipeId: string;
  recipeRevision: number;
}

const recordValue = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};

const textValue = (value: unknown): string | undefined =>
  typeof value === 'string' && value.length > 0 ? value : undefined;

/** The backend stores at most one immutable execution link per recipe-version/job pair. */
export const announcementExecutionKey = (execution: AnnouncementExecutionRecord): string =>
  `${execution.recipeVersionId}\u0000${execution.jobId}`;

export const createAnnouncementSubmissionGuard = (
  productionId: string,
  recipe: AnnouncementRecipeRecord,
  executions: readonly AnnouncementExecutionRecord[],
): AnnouncementSubmissionGuard => ({
  productionId,
  recipeId: recipe.id,
  recipeVersionId: recipe.versionId,
  recipeRevision: recipe.revision,
  recipeDigest: recipe.digest,
  automaticRetryAttempted: false,
  knownExecutionKeys: new Set(
    executions
      .filter((execution) => (
        execution.recipeId === recipe.id
        && execution.recipeVersionId === recipe.versionId
        && execution.recipeRevision === recipe.revision
        && execution.recipeDigest === recipe.digest
      ))
      .map(announcementExecutionKey),
  ),
});

export const announcementExecutionMatchesGuard = (
  execution: AnnouncementExecutionRecord,
  guard: AnnouncementSubmissionGuard,
): boolean => (
  execution.recipeId === guard.recipeId
  && execution.recipeVersionId === guard.recipeVersionId
  && execution.recipeRevision === guard.recipeRevision
  && execution.recipeDigest === guard.recipeDigest
);

/**
 * Only links that did not exist before the ambiguous POST can prove admission.
 * Known history remains audit-only: even a succeeded known Job cannot clear the
 * ambiguity because it does not prove that the current POST reached the server.
 */
export const selectAnnouncementRecoveryCandidates = (
  executions: readonly AnnouncementExecutionRecord[],
  guard: AnnouncementSubmissionGuard,
): AnnouncementRecoveryCandidates => {
  const scoped = executions.filter((execution) => announcementExecutionMatchesGuard(execution, guard));
  return {
    fresh: scoped.filter((execution) => !guard.knownExecutionKeys.has(announcementExecutionKey(execution))),
  };
};

/** Rebuild the one closed execute request from the immutable submission guard. */
export const announcementRetryRequest = (
  guard: AnnouncementSubmissionGuard,
): AnnouncementRetryRequest => ({
  productionId: guard.productionId,
  recipeId: guard.recipeId,
  recipeRevision: guard.recipeRevision,
});

/** Claim the single automatic retry. Manual retries deliberately do not use this claim. */
export const claimAnnouncementAutomaticRetry = (
  guard: AnnouncementSubmissionGuard,
): AnnouncementRetryRequest | undefined => {
  if (guard.automaticRetryAttempted) return undefined;
  guard.automaticRetryAttempted = true;
  return announcementRetryRequest(guard);
};

/**
 * Cross-check the immutable execution link against the exact Detailed Job payload.
 * This prevents an old/unrelated dashboard Job from clearing an ambiguous submit.
 */
export const announcementJobMatchesExecution = (
  job: Job,
  execution: AnnouncementExecutionRecord,
  productionId: string,
): boolean => {
  const payload = recordValue(job.raw.payload);
  return job.id === execution.jobId
    && job.type === 'detailed_test_video'
    && job.productionId === productionId
    && textValue(payload.production_id ?? payload.productionId) === productionId
    && textValue(payload.run_id ?? payload.runId) === execution.runId
    && textValue(payload.revision_id ?? payload.revisionId) === execution.revisionId
    && textValue(payload.request_key ?? payload.requestKey) === execution.requestKey;
};
