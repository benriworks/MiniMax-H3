import type { AnnouncementRecipeRecord, AnnouncementVideoRecipe, Artifact, ArtifactImportResponse, Job, LocalScreenCaptureRequest, ProductionDetail, ProductionSummary, RerunChanges, RerunPlan, ScreenThemeId } from './types';

export const SCREEN_EXPLAINER_STORAGE_KEY = 'minimax-h3-studio.screen-explainer.v1';
export const SCREEN_EXPLAINER_ROLES = ['hook', 'message', 'cta'] as const;
export const SCREEN_EXPLAINER_LABELS = ['目的', '操作', '結果'] as const;
export const SCREEN_EXPLAINER_THEME_OPTIONS = [
  { id: 'neutral_v1', group: '標準', label: '標準・ニュートラル', description: '製品を限定しない、落ち着いた画面解説。' },
  { id: 'claude_desktop_v1', group: '製品別', label: 'Claude Desktop', description: '会話・文章作成の紹介。橙色と明るい背景。' },
  { id: 'claude_code_v1', group: '製品別', label: 'Claude Code', description: '開発支援の紹介。温かい白と橙色のアクセント。' },
  { id: 'claude_editorial_v1', group: '製品別', label: 'Claude Desktop・編集スタイル', description: '導入は暖色、ポイントは白、まとめは墨色。章表示と短い見出しの動きで切替を明確に。' },
  { id: 'technical_v1', group: '技術テーマ別', label: '技術解説', description: '仕組み・手順・比較を伝える、製品に依存しないテーマ。' },
] as const satisfies readonly { id: ScreenThemeId; group: string; label: string; description: string }[];
export const isScreenExplainerTheme = (value: unknown): value is ScreenThemeId => SCREEN_EXPLAINER_THEME_OPTIONS.some((theme) => theme.id === value);
export type ScreenExplainerSource = 'existing' | 'file' | 'capture';
export interface ScreenExplainerFocusRegion { x: number; y: number; width: number; height: number }
export interface ClaudeCaptureInspection {
  available: boolean;
  reason?: string;
  targets: Array<{ selectionToken: string; label: string; width: number; height: number }>;
  expiresInSeconds: number;
}
export interface ClaudeCaptureSubmission { selectionToken: string; durationMs: number; confirmCapture: true; requestId: string }
export interface ScreenExplainerShot {
  role: typeof SCREEN_EXPLAINER_ROLES[number];
  headline: string;
  narration: string;
  durationMs: number;
  startMs: number;
  source: ScreenExplainerSource;
  url: string;
  scroll: boolean;
  artifactId: string;
  previewApproved: boolean;
  captureRunId?: string;
  captureJobId?: string;
  focusRegion?: ScreenExplainerFocusRegion;
}
export interface ScreenExplainerDraft {
  schemaVersion: 1;
  productionId: string;
  productionCreated: boolean;
  title: string;
  screenTheme?: ScreenThemeId;
  // Kept on recipe reload so visual edits do not silently choose another voice.
  voice?: string;
  rate?: number;
  pronunciations?: AnnouncementVideoRecipe['pronunciations'];
  recipeId: string;
  recipeRevision: number;
  recipeVersionId?: string;
  savedFingerprint?: string;
  jobId?: string;
  jobRevision?: number;
  sourceMode?: 'individual' | 'claude_shared';
  sharedCaptureRequestId?: string;
  sharedCaptureJobId?: string;
  sharedCaptureArtifactId?: string;
  pending?: { operation: 'production' | 'import' | 'run' | 'capture' | 'claude_capture' | 'save' | 'execute'; shotIndex?: number };
  shots: ScreenExplainerShot[];
}
export interface ScreenExplainerApi {
  createProduction(id: string, title: string): Promise<ProductionSummary>;
  production(id: string): Promise<ProductionDetail>;
  importVideo(id: string, file: File): Promise<ArtifactImportResponse>;
  rerunPlan(id: string, changes: RerunChanges): Promise<RerunPlan>;
  createRun(id: string, plan: RerunPlan, changes: RerunChanges): Promise<unknown>;
  executeLocalScreenCapture(runId: string, body: LocalScreenCaptureRequest): Promise<Job>;
  job(id: string): Promise<Job>;
  saveAnnouncementRecipe(id: string, recipeId: string, revision: number, recipe: AnnouncementVideoRecipe): Promise<AnnouncementRecipeRecord>;
  executeAnnouncementRecipe(id: string, recipeId: string, revision: number): Promise<Job>;
  executeClaudeCapture?(productionId: string, body: ClaudeCaptureSubmission): Promise<Job>;
  claudeCaptureJob?(productionId: string, requestId: string): Promise<Job | undefined>;
}
export interface ScreenExplainerOptions {
  onDraft(draft: ScreenExplainerDraft): void;
  onProgress?(message: string, job?: Job): void;
  signal?: AbortSignal;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
  timeoutMs?: number;
}

export interface ScreenStructureIssue { key: string; message: string }
/** Advisory only: settings can expose risks, but cannot prove image/motion quality. */
export const reviewScreenStructure = (draft: ScreenExplainerDraft): ScreenStructureIssue[] => {
  const issues: ScreenStructureIssue[] = [];
  for (const [index, shot] of draft.shots.entries()) {
    const previous = draft.shots[index - 1];
    const focus = shot.focusRegion;
    if (focus && focus.height <= .25 && focus.width >= .6) issues.push({ key: `crop-${index}`, message: `${index + 1}場面目：横長の切り抜きです。文字の帯だけにならず、アプリの文脈が残るか確認してください。` });
    if (!previous) continue;
    const sameFocus = (!focus && !previous.focusRegion) || (focus && previous.focusRegion &&
      (['x', 'y', 'width', 'height'] as const).every(key => focus[key] === previous.focusRegion?.[key]));
    if (shot.artifactId && shot.artifactId === previous.artifactId && sameFocus) issues.push({ key: `source-${index}`, message: `${index}→${index + 1}場面目：同じ素材・同じ注目範囲です。区間が違っても絵が似る可能性があります。内容の変化を確認するか、別素材・図解を検討してください。` });
    const title = shot.headline.replace(/\s/g, '');
    if (title && title === previous.headline.replace(/\s/g, '')) issues.push({ key: `headline-${index}`, message: `${index}→${index + 1}場面目：見出しが同じです。次に何を伝える場面か、役割を分けてみてください。` });
  }
  return issues;
};

/** A closed dialog must keep recovery IDs without publishing into a new UI. */
export const createScreenExplainerSessionGuard = <T>(
  isCurrent: () => boolean,
  persist: (value: T) => void,
  publish: (value: T) => void,
) => ({
  checkpoint(value: T): void {
    persist(value);
    if (isCurrent()) publish(value);
  },
  update(action: () => void): void {
    if (isCurrent()) action();
  },
});

const ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const units = (value: string): number => Array.from(value).reduce((sum, char) => sum + (/^[\x20-\x7e\uff61-\uff9f]$/.test(char) ? 0.5 : 1), 0);
const safeText = (value: unknown, max: number): value is string => typeof value === 'string' && value.length <= max && !/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(value);
const id = (value: unknown): value is string => typeof value === 'string' && ID.test(value);
const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const clone = (draft: ScreenExplainerDraft): ScreenExplainerDraft => ({ ...draft, ...(draft.pronunciations === undefined ? {} : { pronunciations: draft.pronunciations.map((item) => ({ ...item })) }), pending: draft.pending ? { ...draft.pending } : undefined, shots: draft.shots.map((shot) => ({ ...shot, ...(shot.focusRegion ? { focusRegion: { ...shot.focusRegion } } : {}) })) });
const fingerprint = (value: unknown): string => JSON.stringify(value, (_key, item: unknown) => {
  if (!item || typeof item !== 'object' || Array.isArray(item)) return item;
  return Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b)));
});

export const validScreenExplainerFocus = (value: unknown): value is ScreenExplainerFocusRegion => {
  const focus = record(value);
  return Object.keys(focus).sort().join(',') === 'height,width,x,y'
    && ['x', 'y', 'width', 'height'].every((field) => typeof focus[field] === 'number' && Number.isFinite(focus[field]) && Number(Number(focus[field]).toFixed(4)) === focus[field])
    && Number(focus.x) >= 0 && Number(focus.y) >= 0 && Number(focus.width) >= 0.2 && Number(focus.height) >= 0.2
    && Number(focus.x) + Number(focus.width) <= 1.00000001 && Number(focus.y) + Number(focus.height) <= 1.00000001;
};

export const screenExplainerCaptureUrl = (value: string): string => {
  if (!safeText(value, 2048) || /[\\\s]/.test(value)) throw new Error('収録URLは http://127.0.0.1:ポート/ の形式で入力してください。');
  let target: URL;
  try { target = new URL(value); } catch { throw new Error('収録URLの形式が正しくありません。'); }
  if (target.protocol !== 'http:' || target.hostname !== '127.0.0.1' || !target.port || target.username || target.password || target.search || target.hash) {
    throw new Error('自動収録は http://127.0.0.1:ポート/ のみです。認証情報・クエリ・外部サイトには対応していません。');
  }
  return target.href;
};

export const newScreenExplainerDraft = (production?: Pick<ProductionDetail, 'id' | 'title'>, randomId = () => globalThis.crypto.randomUUID().replaceAll('-', '')): ScreenExplainerDraft => ({
  schemaVersion: 1,
  productionId: production?.id ?? `production_${randomId()}`,
  productionCreated: Boolean(production),
  title: production?.title ?? '画面でわかる、ひとつの操作',
  recipeId: `announcement_${randomId()}`,
  recipeRevision: 0,
  shots: SCREEN_EXPLAINER_ROLES.map((role, index) => ({ role, headline: ['何ができる？', '操作をひとつ', '結果を確認'][index], narration: ['ひとつの操作を紹介します。', '画面の変化を見てみましょう。', 'このように結果を確認できます。'][index], durationMs: 5000, startMs: 0, source: 'existing', url: '', scroll: false, artifactId: '', previewApproved: false })),
});

/** Closed persisted schema: no File, local path, API key, or arbitrary request body. */
export const parseScreenExplainerDraft = (value: unknown): ScreenExplainerDraft => {
  const v = record(value);
  const allowed = ['schemaVersion', 'productionId', 'productionCreated', 'title', 'screenTheme', 'voice', 'rate', 'pronunciations', 'recipeId', 'recipeRevision', 'recipeVersionId', 'savedFingerprint', 'jobId', 'jobRevision', 'pending', 'shots', 'sourceMode', 'sharedCaptureRequestId', 'sharedCaptureJobId', 'sharedCaptureArtifactId'];
  if (Object.keys(v).some((key) => !allowed.includes(key)) || v.schemaVersion !== 1 || !id(v.productionId) || !id(v.recipeId) || !safeText(v.title, 120)
    || typeof v.productionCreated !== 'boolean' || !Number.isInteger(v.recipeRevision) || Number(v.recipeRevision) < 0 || !Array.isArray(v.shots) || v.shots.length !== 3) throw new Error('画面解説の保存情報が不正です。');
  for (const field of ['recipeVersionId', 'jobId', 'sharedCaptureJobId', 'sharedCaptureArtifactId']) if (v[field] !== undefined && !id(v[field])) throw new Error('保存されたIDが不正です。');
  if (v.screenTheme !== undefined && !isScreenExplainerTheme(v.screenTheme)) throw new Error('保存されたテーマが不正です。');
  if (v.voice !== undefined && (!safeText(v.voice, 128) || !v.voice.trim() || /[\r\n]/.test(v.voice))) throw new Error('保存された音声名が不正です。');
  if (v.rate !== undefined && (!Number.isInteger(v.rate) || Number(v.rate) < -10 || Number(v.rate) > 10)) throw new Error('保存された音声速度が不正です。');
  if (v.pronunciations !== undefined) {
    if (!Array.isArray(v.pronunciations) || v.pronunciations.length > 100) throw new Error('保存された発音置換が不正です。');
    const seen = new Set<string>();
    for (const item of v.pronunciations) {
      const entry = record(item);
      if (Object.keys(entry).sort().join(',') !== 'source,target' || !safeText(entry.source, 512) || !safeText(entry.target, 512)
        || !entry.source.trim() || !entry.target.trim() || /[\r\n]/.test(entry.source + entry.target) || seen.has(entry.source)) throw new Error('保存された発音置換が不正です。');
      seen.add(entry.source);
    }
  }
  if (v.sourceMode !== undefined && !['individual', 'claude_shared'].includes(String(v.sourceMode))) throw new Error('素材取得モードが不正です。');
  if (v.sharedCaptureRequestId !== undefined && (typeof v.sharedCaptureRequestId !== 'string' || !/^claude_capture_[0-9a-f]{32}$/.test(v.sharedCaptureRequestId))) throw new Error('共通収録のリクエストIDが不正です。');
  if (v.savedFingerprint !== undefined && !safeText(v.savedFingerprint, 128000)) throw new Error('保存された版情報が不正です。');
  if (v.jobRevision !== undefined && (!Number.isInteger(v.jobRevision) || Number(v.jobRevision) < 1)) throw new Error('保存されたJob版が不正です。');
  if (v.pending !== undefined) {
    const pending = record(v.pending);
    if (Object.keys(pending).some((key) => !['operation', 'shotIndex'].includes(key)) || !['production', 'import', 'run', 'capture', 'claude_capture', 'save', 'execute'].includes(String(pending.operation))
      || (pending.shotIndex !== undefined && (!Number.isInteger(pending.shotIndex) || Number(pending.shotIndex) < 0 || Number(pending.shotIndex) > 2))) throw new Error('保留処理の情報が不正です。');
  }
  for (const [index, item] of v.shots.entries()) {
    const shot = record(item);
    const fields = ['role', 'headline', 'narration', 'durationMs', 'startMs', 'source', 'url', 'scroll', 'artifactId', 'previewApproved', 'captureRunId', 'captureJobId', 'focusRegion'];
    if (Object.keys(shot).some((key) => !fields.includes(key)) || shot.role !== SCREEN_EXPLAINER_ROLES[index] || !safeText(shot.headline, 80) || !safeText(shot.narration, 300)
      || !Number.isInteger(shot.durationMs) || Number(shot.durationMs) < 5000 || Number(shot.durationMs) > 10000 || !Number.isInteger(shot.startMs) || Number(shot.startMs) < 0
      || !['existing', 'file', 'capture'].includes(String(shot.source)) || !safeText(shot.url, 2048) || typeof shot.scroll !== 'boolean' || typeof shot.previewApproved !== 'boolean'
      || !(shot.artifactId === '' || id(shot.artifactId))) throw new Error('保存された場面情報が不正です。');
    for (const field of ['captureRunId', 'captureJobId']) if (shot[field] !== undefined && !id(shot[field])) throw new Error('保存された収録IDが不正です。');
    if (shot.focusRegion !== undefined && !validScreenExplainerFocus(shot.focusRegion)) throw new Error('注目範囲は画面内の0〜1の座標、幅・高さ0.2以上で指定してください。');
    if (shot.url) screenExplainerCaptureUrl(String(shot.url));
  }
  return clone(value as ScreenExplainerDraft);
};

type DraftStorage = Pick<Storage, 'getItem' | 'setItem'>;

/** The production key is canonical; the new-entry alias never wins over it. */
export const persistScreenExplainerDraft = (storage: DraftStorage, draft: ScreenExplainerDraft, entryKey: string): void => {
  const stored = parseScreenExplainerDraft(draft);
  const serialized = JSON.stringify(stored);
  for (const key of new Set([`${SCREEN_EXPLAINER_STORAGE_KEY}:${stored.productionId}`, entryKey])) {
    storage.setItem(key, serialized);
    if (storage.getItem(key) !== serialized) throw new Error('再開情報をブラウザへ保存できません。送信を停止しました。');
  }
};

export const restoreScreenExplainerDraft = (storage: Pick<Storage, 'getItem'>, productionId?: string): ScreenExplainerDraft | undefined => {
  let raw = storage.getItem(`${SCREEN_EXPLAINER_STORAGE_KEY}:${productionId ?? 'new'}`);
  if (!raw && productionId) {
    const legacy = storage.getItem(`${SCREEN_EXPLAINER_STORAGE_KEY}:new`);
    if (legacy && parseScreenExplainerDraft(JSON.parse(legacy)).productionId === productionId) raw = legacy;
  }
  if (!raw) return undefined;
  let draft = parseScreenExplainerDraft(JSON.parse(raw));
  const canonical = storage.getItem(`${SCREEN_EXPLAINER_STORAGE_KEY}:${draft.productionId}`);
  if (canonical) draft = parseScreenExplainerDraft(JSON.parse(canonical));
  if (productionId && draft.productionId !== productionId) throw new Error('別の制作の保存情報です。');
  return draft;
};

export const validateScreenExplainer = (draft: ScreenExplainerDraft, requireAssets = true): string[] => {
  const errors: string[] = [];
  if (draft.screenTheme !== undefined && !isScreenExplainerTheme(draft.screenTheme)) errors.push('登録済みの画面解説テーマを選択してください。');
  if (!draft.title.trim() || draft.title.length > 120) errors.push('制作タイトルは1〜120文字で入力してください。');
  draft.shots.forEach((shot, index) => {
    const label = `${index + 1}. ${SCREEN_EXPLAINER_LABELS[index]}`;
    const lines = shot.headline.trim().split(/\r?\n/);
    if (!shot.headline.trim() || lines.length > 2 || lines.some((line) => !line.trim() || units(line) > 10)) errors.push(`${label}：見出しは2行、1行全角10文字相当以内です。`);
    if (!shot.narration.trim() || /[\r\n]/.test(shot.narration) || units(shot.narration.trim()) > 19) errors.push(`${label}：読み上げ文は1文・全角19文字相当以内にしてください。`);
    if (!Number.isInteger(shot.durationMs) || shot.durationMs < 5000 || shot.durationMs > 10000) errors.push(`${label}：長さは5〜10秒です。`);
    if (shot.focusRegion !== undefined && !validScreenExplainerFocus(shot.focusRegion)) errors.push(`${label}：注目範囲の座標・幅・高さを確認してください。`);
    if (requireAssets && !shot.artifactId) errors.push(`${label}：動画素材を取得してください。`);
    if (requireAssets && !shot.previewApproved) errors.push(`${label}：素材を再生し、内容を確認してください。`);
    if (requireAssets && draft.sourceMode === 'claude_shared' && (shot.artifactId !== draft.sharedCaptureArtifactId || shot.startMs !== draft.shots.slice(0, index).reduce((sum, previous) => sum + previous.durationMs, 0))) errors.push(`${label}：共通収録の素材・連続区間を再確認してください。`);
  });
  return errors;
};

/** Keep a single recording's scene offsets contiguous after duration edits. */
export const alignSharedScreenExplainerShots = (shots: ScreenExplainerShot[]): ScreenExplainerShot[] => {
  let startMs = 0;
  return shots.map((shot) => {
    const result = { ...shot, startMs, previewApproved: shot.startMs === startMs ? shot.previewApproved : false };
    startMs += shot.durationMs;
    return result;
  });
};

export const buildScreenExplainerRecipe = (draft: ScreenExplainerDraft): AnnouncementVideoRecipe => {
  const errors = validateScreenExplainer(draft);
  if (errors.length) throw new Error(errors[0]);
  return {
    schemaVersion: 1, name: draft.title.trim(), templatePreset: 'screen_explainer_ja_v1',
    ...(draft.screenTheme === undefined ? {} : { screenTheme: draft.screenTheme }),
    scenes: draft.shots.map((shot) => ({ role: shot.role, videoArtifactId: shot.artifactId, startMs: shot.startMs, endMs: shot.startMs + shot.durationMs,
      volumePercent: 0, visualPreset: 'preserve_v1', headline: shot.headline.trim(), narration: shot.narration.trim(), ...(shot.focusRegion ? { focusRegion: { ...shot.focusRegion } } : {}) })),
    ...(draft.voice === undefined ? {} : { voice: draft.voice }),
    rate: draft.rate ?? 0, pronunciations: draft.pronunciations?.map((item) => ({ ...item })) ?? [], includeCaptioned: true, captionStylePreset: 'shorts_ja_large_v1', audioMixPreset: 'narration_only_v1', variant: 'captioned',
  };
};

export const screenExplainerDraftFromRecipe = (production: ProductionDetail, saved: AnnouncementRecipeRecord): ScreenExplainerDraft => {
  if (saved.productionId !== production.id || saved.recipe.templatePreset !== 'screen_explainer_ja_v1') throw new Error('この制作の画面解説レシピを選択してください。');
  const draft = newScreenExplainerDraft(production);
  draft.title = saved.recipe.name;
  if (saved.recipe.screenTheme !== undefined) draft.screenTheme = saved.recipe.screenTheme;
  if (saved.recipe.voice !== undefined) draft.voice = saved.recipe.voice;
  draft.rate = saved.recipe.rate;
  draft.pronunciations = saved.recipe.pronunciations.map((item) => ({ ...item }));
  draft.recipeId = saved.id;
  draft.recipeRevision = saved.revision;
  draft.recipeVersionId = saved.versionId;
  draft.shots = saved.recipe.scenes.map((scene) => ({ role: scene.role, headline: scene.headline, narration: scene.narration, durationMs: scene.endMs - scene.startMs, startMs: scene.startMs,
    source: 'existing', url: '', scroll: false, artifactId: scene.videoArtifactId, previewApproved: false, ...(scene.focusRegion ? { focusRegion: { ...scene.focusRegion } } : {}) }));
  draft.savedFingerprint = fingerprint(saved.recipe);
  const execution = production.announcementExecutions.find((item) => item.recipeVersionId === saved.versionId);
  if (execution) { draft.jobId = execution.jobId; draft.jobRevision = saved.revision; }
  return parseScreenExplainerDraft(draft);
};

const pause = (ms: number, signal?: AbortSignal): Promise<void> => new Promise((resolve, reject) => {
  if (signal?.aborted) { reject(new Error('監視を停止しました。Jobは継続し、再開時に状態確認できます。')); return; }
  const abort = () => { globalThis.clearTimeout(timer); reject(new Error('監視を停止しました。Jobは継続しています。')); };
  const timer = globalThis.setTimeout(() => { signal?.removeEventListener('abort', abort); resolve(); }, ms);
  signal?.addEventListener('abort', abort, { once: true });
});

export const waitScreenExplainerJob = async (api: Pick<ScreenExplainerApi, 'job'>, jobId: string, options: ScreenExplainerOptions): Promise<Job> => {
  const now = options.now ?? Date.now;
  const deadline = now() + (options.timeoutMs ?? 20 * 60 * 1000);
  while (now() < deadline) {
    if (options.signal?.aborted) throw new Error('監視を停止しました。保存したJob IDから再開できます。');
    const job = await api.job(jobId);
    if (job.id !== jobId) throw new Error('Jobの応答IDが一致しません。処理の再送は停止しています。');
    options.onProgress?.(job.message ?? `処理中：${job.status}`, job);
    if (job.status === 'succeeded') return job;
    if (['failed', 'cancelled', 'blocked'].includes(job.status)) throw new Error(`Job ${job.id}：${job.message ?? job.status}。IDを保持しました。`);
    await (options.sleep ? options.sleep(2000) : pause(2000, options.signal));
  }
  throw new Error(`Job ${jobId} の監視期限に達しました。生成は取り消していません。「状態を再確認」で再開できます。`);
};

/** Persist before every POST. Unknown responses never automatically submit again. */
const caller = (draft: ScreenExplainerDraft, options: ScreenExplainerOptions) => {
  const save = () => options.onDraft(clone(draft));
  const post = async <T>(operation: NonNullable<ScreenExplainerDraft['pending']>, action: () => Promise<T>): Promise<T> => {
    if (draft.pending) throw new Error('前回送信の結果が不明です。状態の再確認が終わるまで再送しません。');
    if (options.signal?.aborted) throw new Error('処理を停止しました。');
    draft.pending = operation; save();
    try { return await action(); } catch (error) {
      const status = record(error).status;
      if (typeof status === 'number' && status >= 400 && status < 500) { draft.pending = undefined; save(); }
      throw error;
    }
  };
  const accepted = () => { draft.pending = undefined; save(); };
  return { save, post, accepted };
};

const verifyJobLineage = (job: Job, productionId: string, runId?: string): void => {
  if (!id(job.id) || job.productionId !== productionId || (runId !== undefined && job.runId !== runId)) throw new Error('Jobの制作・Runの対応を確認できません。再送せず、制作のログを確認してください。');
};

/** A succeeded capture (or an old render) is never a finished explainer. */
export const verifyScreenExplainerRender = (job: Job, draft: ScreenExplainerDraft): Artifact => {
  verifyJobLineage(job, draft.productionId);
  const payload = record(job.raw.payload);
  const raw = record(job.result?.raw);
  const master = record(raw.master);
  const clips = Array.isArray(payload.clips) ? payload.clips.map(record) : [];
  const starts = draft.shots.map((_shot, index) => draft.shots.slice(0, index).reduce((sum, shot) => sum + shot.durationMs, 0));
  const correctRoute = job.type === 'detailed_test_video' && job.status === 'succeeded'
    && job.id === draft.jobId && draft.jobRevision === draft.recipeRevision
    && id(job.runId) && payload.production_id === draft.productionId && payload.run_id === job.runId
    && payload.stage === 'detailed_test_video' && payload.execution_profile === 'local_sapi'
    && job.result?.runId === job.runId && raw.run_id === job.runId
    && job.result?.technicalVerdict === 'pass' && raw.technical_verdict === 'pass'
    && raw.include_captioned === true && raw.variant === 'captioned' && record(raw.qc).verdict === 'pass'
    && raw.narration_alignment_policy === 'announcement_scene_starts_v1'
    && fingerprint(raw.narration_segment_start_ms) === fingerprint(starts)
    && clips.length === 3 && clips.every((clip, index) => clip.layout_preset === 'screen_explainer_v1'
      && clip.video_artifact_id === draft.shots[index].artifactId && clip.start_ms === draft.shots[index].startMs
      && clip.end_ms === draft.shots[index].startMs + draft.shots[index].durationMs && clip.transition_to_next === null
      && clip.screen_theme === draft.screenTheme
      && fingerprint(clip.focus_region) === fingerprint(draft.shots[index].focusRegion));
  if (!correctRoute) throw new Error('生成Jobの経路・版・画面素材・技術QCを照合できないため、完成として表示しません。');
  const children = job.result?.jobs;
  if (!children || ['narration', 'timeline', 'assembly', 'qc'].some((stage) => children[stage]?.status !== 'succeeded' || !id(children[stage]?.jobId))) {
    throw new Error('音声・編集・合成・QCの4工程の完了を確認できません。');
  }
  const candidates = job.result?.artifacts.filter((artifact) => artifact.kind === 'video' && artifact.name === 'master-captioned.mp4') ?? [];
  const artifact = candidates[0];
  const path = artifact?.path;
  const expectedPrefix = `outputs/studio/runs/${job.runId}/assembly/`;
  if (candidates.length !== 1 || !artifact || !id(artifact.id) || !artifact.sha256 || !/^[0-9a-f]{64}$/i.test(artifact.sha256)
    || typeof path !== 'string' || !path.startsWith(expectedPrefix) || !/^[0-9a-f]{64}\/master-captioned\.mp4$/i.test(path.slice(expectedPrefix.length))
    || master.id !== artifact.id || master.name !== artifact.name || master.rel_path !== path || String(master.sha256).toUpperCase() !== artifact.sha256.toUpperCase()) {
    throw new Error('技術QC済みの字幕入りmasterのID・保存先・ハッシュが一致しません。');
  }
  return artifact;
};

export const collectScreenExplainerAssets = async (api: ScreenExplainerApi, input: ScreenExplainerDraft, files: ReadonlyMap<number, File>, options: ScreenExplainerOptions): Promise<{ draft: ScreenExplainerDraft; production: ProductionDetail }> => {
  if (input.sourceMode === 'claude_shared') return collectClaudeScreenExplainer(api, input, undefined, options);
  const draft = clone(input);
  const { post, accepted, save } = caller(draft, options);
  if (!draft.title.trim()) throw new Error('制作タイトルを入力してください。');
  // Validate all sources before creating a production or sending a capture request.
  draft.shots.forEach((shot, index) => {
    if (shot.artifactId || shot.captureJobId || shot.captureRunId) return;
    if (shot.source === 'capture') screenExplainerCaptureUrl(shot.url);
    else if (shot.source === 'file' && !files.has(index)) throw new Error(`${SCREEN_EXPLAINER_LABELS[index]}の動画ファイルを選び直してください。`);
    else if (shot.source === 'existing') throw new Error(`${SCREEN_EXPLAINER_LABELS[index]}の既存素材を選択してください。`);
  });
  if (draft.pending?.operation === 'production') {
    const existing = await api.production(draft.productionId);
    if (existing.id !== draft.productionId || existing.title !== draft.title.trim()) throw new Error('制作の作成結果を照合できません。再送は停止しています。');
    draft.productionCreated = true; accepted();
  }
  if (!draft.productionCreated) {
    options.onProgress?.('制作を準備しています');
    await post({ operation: 'production' }, () => api.createProduction(draft.productionId, draft.title.trim()));
    draft.productionCreated = true; accepted();
  }
  for (const [index, shot] of draft.shots.entries()) {
    if (shot.artifactId) continue;
    options.onProgress?.(`${index + 1}/3 ${SCREEN_EXPLAINER_LABELS[index]}の素材を取得しています`);
    if (shot.source === 'file') {
      const file = files.get(index);
      if (!file) throw new Error('動画ファイルを選び直してください。');
      const imported = await post({ operation: 'import', shotIndex: index }, () => api.importVideo(draft.productionId, file));
      if (!imported.artifact?.id) throw new Error('素材取込の結果を確認できません。制作の素材一覧を確認してください。');
      shot.artifactId = imported.artifact.id; shot.previewApproved = false; accepted();
      continue;
    }
    if (shot.source !== 'capture') throw new Error('素材を選択してください。');
    if (draft.pending?.operation === 'capture' && draft.pending.shotIndex === index && shot.captureRunId) {
      const detail = await api.production(draft.productionId);
      const attempts = detail.runs.find((run) => run.id === shot.captureRunId)?.stageAttempts.filter((attempt) => attempt.stage === 'screen_capture' && attempt.jobId) ?? [];
      if (attempts.length !== 1) throw new Error(`収録Run ${shot.captureRunId} の送信結果を確定できません。再送はせず、制作のログを確認してください。`);
      shot.captureJobId = attempts[0].jobId; accepted();
    }
    if (!shot.captureRunId) {
      const changes: RerunChanges = { stages: ['screen_capture'], note: `画面解説 ${draft.recipeId} ${shot.role}`, allowPaidApi: false, executionProfile: 'local_playwright' };
      const plan = await api.rerunPlan(draft.productionId, changes);
      const created = await post({ operation: 'run', shotIndex: index }, () => api.createRun(draft.productionId, plan, changes));
      const runId = record(record(created).run).id;
      if (!id(runId)) throw new Error('収録Runの作成結果を確認できません。再送は停止しています。');
      shot.captureRunId = runId; accepted();
    }
    if (!shot.captureJobId) {
      const submitted = await post({ operation: 'capture', shotIndex: index }, () => api.executeLocalScreenCapture(shot.captureRunId!, {
        url: screenExplainerCaptureUrl(shot.url), durationMs: shot.durationMs, settleMs: 1000, viewportPreset: 'desktop_16_9',
        actions: shot.scroll ? [{ type: 'scroll', atMs: Math.min(2000, shot.durationMs - 1000), deltaY: 600 }] : [],
      }));
      verifyJobLineage(submitted, draft.productionId, shot.captureRunId);
      shot.captureJobId = submitted.id; accepted();
    }
    const completed = await waitScreenExplainerJob(api, shot.captureJobId, options);
    verifyJobLineage(completed, draft.productionId, shot.captureRunId);
    // The capture worker publishes both the raw WebM and the canonical MP4.
    // Only the registered, trimmed MP4 has the requested scene duration.
    const videos = completed.result?.artifacts.filter((artifact) => artifact.kind === 'video' && artifact.name === 'screen-capture.mp4') ?? [];
    if (videos.length !== 1) throw new Error(`Job ${completed.id}の動画素材を一意に特定できません。素材一覧を確認してください。`);
    shot.artifactId = videos[0].id; shot.previewApproved = false; save();
  }
  const detail = await api.production(draft.productionId);
  draft.shots.forEach((shot, index) => {
    const artifact = detail.artifacts.find((item) => item.id === shot.artifactId && item.kind === 'video');
    if (!artifact) throw new Error(`${SCREEN_EXPLAINER_LABELS[index]}の素材が現在の制作にありません。`);
    const duration = artifactDuration(artifact);
    if (duration !== undefined && duration * 1000 + 1 < shot.startMs + shot.durationMs) throw new Error(`${SCREEN_EXPLAINER_LABELS[index]}の素材が指定秒数より短いため、長い素材を選ぶか場面を短くしてください。`);
  });
  save();
  return { draft, production: detail };
};

export const collectClaudeScreenExplainer = async (
  api: ScreenExplainerApi,
  input: ScreenExplainerDraft,
  consent: { selectionToken: string; confirmCapture: true } | undefined,
  options: ScreenExplainerOptions,
): Promise<{ draft: ScreenExplainerDraft; production: ProductionDetail }> => {
  const draft = clone(input);
  if (draft.sourceMode !== 'claude_shared') throw new Error('Claude Desktopの共通収録モードを選択してください。');
  const durationMs = draft.shots.reduce((sum, shot) => sum + shot.durationMs, 0);
  if (!draft.title.trim() || !Number.isInteger(durationMs) || durationMs < 15000 || durationMs > 30000
    || draft.shots.some((shot) => !Number.isInteger(shot.durationMs) || shot.durationMs < 5000 || shot.durationMs > 10000)) throw new Error('タイトルと3場面の長さ（合計15〜30秒）を確認してください。');
  if (!draft.sharedCaptureJobId && !draft.sharedCaptureArtifactId && !draft.pending
    && (!consent || consent.confirmCapture !== true || !safeText(consent.selectionToken, 2048) || !consent.selectionToken)) throw new Error('先にClaudeを確認し、プライバシー確認後に収録開始を押してください。');
  const { post, accepted, save } = caller(draft, options);
  const verifySharedJob = (job: Job) => {
    verifyJobLineage(job, draft.productionId);
    if (job.type !== 'claude_window_capture' || record(job.raw.payload).capture_request_id !== draft.sharedCaptureRequestId) throw new Error('共通収録Jobの種類・受付IDが一致しません。自動再送はしません。');
  };
  if (draft.pending?.operation === 'production') {
    const existing = await api.production(draft.productionId);
    if (existing.id !== draft.productionId || existing.title !== draft.title.trim()) throw new Error('制作の作成結果を確認できません。自動再送はしません。');
    draft.productionCreated = true; accepted();
  }
  if (!draft.productionCreated) {
    await post({ operation: 'production' }, () => api.createProduction(draft.productionId, draft.title.trim()));
    draft.productionCreated = true; accepted();
  }
  if (draft.pending?.operation === 'claude_capture') {
    if (!draft.sharedCaptureRequestId || !api.claudeCaptureJob) throw new Error('収録の送信結果が不明です。制作のログを確認してください。自動再送はしません。');
    const known = await api.claudeCaptureJob(draft.productionId, draft.sharedCaptureRequestId);
    if (!known) throw new Error(`収録 ${draft.sharedCaptureRequestId} の受付を確認できません。しばらく後に状態を再確認してください。自動再送はしません。`);
    verifySharedJob(known);
    draft.sharedCaptureJobId = known.id; accepted();
  }
  if (draft.pending) throw new Error('前回の処理が保留中です。状態を確認するまで新しく収録しません。');
  if (!draft.sharedCaptureArtifactId) {
    if (!draft.sharedCaptureJobId) {
      if (!consent || consent.confirmCapture !== true || !safeText(consent.selectionToken, 2048) || !consent.selectionToken || !api.executeClaudeCapture) throw new Error('Claudeの確認と収録への明示同意が必要です。');
      draft.sharedCaptureRequestId ??= `claude_capture_${globalThis.crypto.randomUUID().replaceAll('-', '')}`;
      save();
      options.onProgress?.(`Claude Desktopを${durationMs / 1000}秒収録しています。画面内の操作・会話送信は行いません。`);
      const submitted = await post({ operation: 'claude_capture' }, () => api.executeClaudeCapture!(draft.productionId, {
        selectionToken: consent.selectionToken, durationMs, confirmCapture: true, requestId: draft.sharedCaptureRequestId!,
      }));
      verifySharedJob(submitted);
      draft.sharedCaptureJobId = submitted.id; accepted();
    }
    const completed = await waitScreenExplainerJob(api, draft.sharedCaptureJobId, options);
    verifySharedJob(completed);
    const candidates = completed.result?.artifacts.filter((artifact) => artifact.kind === 'video' && artifact.name === 'claude-capture.mp4') ?? [];
    if (completed.type !== 'claude_window_capture' || candidates.length !== 1) throw new Error('Claude収録Jobの正規動画を一意に確認できません。');
    draft.sharedCaptureArtifactId = candidates[0].id; save();
  }
  const detail = await api.production(draft.productionId);
  const artifact = detail.artifacts.find((item) => item.id === draft.sharedCaptureArtifactId && item.kind === 'video');
  const duration = artifactDuration(artifact);
  if (detail.id !== draft.productionId || !artifact || duration === undefined || duration * 1000 + 1 < durationMs) throw new Error('共通素材が指定秒数より短いか長さを確認できません。場面を短くするか、別の素材を選択してください。');
  let startMs = 0;
  draft.shots = draft.shots.map((shot) => {
    const unchanged = shot.artifactId === artifact.id && shot.startMs === startMs;
    const result = { ...shot, artifactId: artifact.id, source: 'existing' as const, startMs, previewApproved: unchanged ? shot.previewApproved : false };
    startMs += shot.durationMs;
    return result;
  });
  save();
  return { draft, production: detail };
};

export const artifactDuration = (artifact?: Artifact): number | undefined => {
  const value = artifact?.durationSeconds ?? artifact?.metadata.duration_seconds;
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined;
};

export const executeScreenExplainer = async (api: ScreenExplainerApi, input: ScreenExplainerDraft, options: ScreenExplainerOptions): Promise<{ draft: ScreenExplainerDraft; job: Job }> => {
  const draft = clone(input);
  const recipe = buildScreenExplainerRecipe(draft);
  const wantedFingerprint = fingerprint(recipe);
  const { post, accepted, save } = caller(draft, options);
  let detail = await api.production(draft.productionId);
  if (detail.id !== draft.productionId) throw new Error('制作の対応を確認できません。');
  draft.shots.forEach((shot) => {
    const artifact = detail.artifacts.find((item) => item.id === shot.artifactId && item.kind === 'video');
    if (!artifact) throw new Error('現在の制作に素材がありません。再取得してください。');
    const duration = artifactDuration(artifact);
    if ((draft.sourceMode === 'claude_shared' && duration === undefined) || (duration !== undefined && duration * 1000 + 1 < shot.startMs + shot.durationMs)) throw new Error('動画素材が指定した区間より短いため、場面の長さを確認してください。');
  });
  if (draft.pending?.operation === 'save') {
    const saved = detail.announcementRecipeVersions.find((item) => item.id === draft.recipeId && item.revision === draft.recipeRevision + 1 && fingerprint(item.recipe) === wantedFingerprint);
    if (!saved) throw new Error('レシピ保存の応答が不明です。制作の保存済みレシピを確認してください。自動再送はしません。');
    draft.recipeRevision = saved.revision; draft.recipeVersionId = saved.versionId; draft.savedFingerprint = wantedFingerprint; accepted();
  }
  if (draft.savedFingerprint !== wantedFingerprint || draft.recipeRevision === 0) {
    options.onProgress?.('レシピを新しい版として保存しています');
    const saved = await post({ operation: 'save' }, () => api.saveAnnouncementRecipe(draft.productionId, draft.recipeId, draft.recipeRevision, recipe));
    draft.recipeRevision = saved.revision; draft.recipeVersionId = saved.versionId; draft.savedFingerprint = wantedFingerprint;
    draft.jobId = undefined; draft.jobRevision = undefined; accepted();
    detail = await api.production(draft.productionId);
  }
  const execution = detail.announcementExecutions.find((item) => item.recipeId === draft.recipeId && item.recipeRevision === draft.recipeRevision && item.recipeVersionId === draft.recipeVersionId);
  if (execution) { draft.jobId = execution.jobId; draft.jobRevision = execution.recipeRevision; if (draft.pending?.operation === 'execute') accepted(); else save(); }
  if (draft.pending) throw new Error('前回の送信結果を確定できません。保存したIDで制作のログを確認してください。自動再送はしません。');
  if (!draft.jobId || draft.jobRevision !== draft.recipeRevision) {
    options.onProgress?.('標準の動画制作Jobを登録しています');
    const submitted = await post({ operation: 'execute' }, () => api.executeAnnouncementRecipe(draft.productionId, draft.recipeId, draft.recipeRevision));
    verifyJobLineage(submitted, draft.productionId);
    draft.jobId = submitted.id; draft.jobRevision = draft.recipeRevision; accepted();
  }
  const job = await waitScreenExplainerJob(api, draft.jobId, options);
  verifyScreenExplainerRender(job, draft);
  return { draft, job };
};
