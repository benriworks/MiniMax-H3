import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent, type SyntheticEvent } from 'react';
import { Player } from '@remotion/player';
import {
  api,
  ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
  ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET,
  DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET,
  DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
  DETAILED_TEST_VIDEO_SCHEMA_VERSION,
  LOCAL_NARRATION_LIMITS,
  RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET,
  StudioApiError,
  getLocalQcAvailableVariants,
  getLocalQcAssemblyAttempts,
  getLocalQcResultStatus,
  hasRequestedLocalQcStages,
  isLocalTimelineJobForSelection,
  isRemotionTimelineJobForSelection,
  isLocalScreenCaptureJobForSelection,
  selectLocalScreenCaptureJob,
  isWindowsCaptureJobForSelection,
  selectWindowsCaptureJob,
  isEligibleLocalQcRun,
  isLocalQcJobForSelection,
  isSucceededLocalFfmpegAssemblyAttempt,
  EXTERNAL_NARRATION_LIMITS,
  EXTERNAL_NARRATION_MODEL,
  EXTERNAL_NARRATION_PROVIDER,
  DEFAULT_EXTERNAL_VOICE_SETTINGS,
  LOCAL_COMFYUI_WORKFLOW_PRESET,
  MAX_VIDEO_IMPORT_FILES,
  PRODUCTION_ID_PATTERN,
  PRODUCTION_TITLE_MAX_LENGTH,
  isLocalComfyUiJobForSelection,
  isLocalComfyUiExecutionActive,
  isLocalComfyUiExecutionActiveAcross,
  isProviderTaskActive,
  isProviderTaskBlocking,
  isProviderTaskResumeAvailable,
  newestProviderTasks,
  isLocalPipelineJobForSelection,
  isLocalPipelineTopJob,
  isLocalPipelineExecutionActive,
  isLocalPipelineExecutionActiveAcross,
  isDetailedTestVideoExecutionActive,
  isDetailedTestVideoJobForSelection,
  createDetailedTestVideoSubmissionGuard,
  detailedTestVideoJobMatchesSubmissionGuard,
  isPipelineContinuationActive,
  duplicateTimelineClip,
  elapsedSecondsBetween,
  moveTimelineClip,
  normalizeLocalTimelineInput,
  normalizeLocalRemotionTimelineInput,
  normalizeLocalScreenCaptureInput,
  buildWindowsCapturePayload,
  createWindowsCaptureSubmissionGuard,
  isStudioApiResponseLoss,
  reconcileWindowsCaptureSubmission,
  WINDOWS_CAPTURE_LIMITS,
  WINDOWS_CAPTURE_RECONCILIATION_POLL_MS,
  canStartWindowsCapture,
  normalizeLocalAssemblyInput,
  normalizeLocalQcInput,
  normalizeLocalComfyUiInput,
  normalizeLocalPipelineInput,
  normalizeDetailedTestVideoInput,
  normalizeAnnouncementVideoInput,
  normalizeNarrationInput,
  normalizeExternalNarrationInput,
  getExternalNarrationGate,
  validateVideoImportFiles,
} from './api';
import type { DetailedTestVideoSubmissionGuard, WindowsCaptureSubmissionGuard } from './api';
import {
  ANNOUNCEMENT_DUPLICATE_INTENT_STORAGE_KEY,
  ANNOUNCEMENT_REQUEST_TIMEOUT_MS,
  announcementCloneMatchesIntent,
  announcementExecutionKey,
  announcementJobMatchesExecution,
  announcementRetryRequest,
  browserAnnouncementDuplicateIntentStorage,
  claimAnnouncementAutomaticRetry,
  clearAnnouncementDuplicateIntent,
  clearAnnouncementDuplicateIntentStore,
  createAnnouncementSubmissionGuard,
  deterministicAnnouncementCloneRecipeId,
  inspectAnnouncementDuplicateIntentStore,
  persistAnnouncementDuplicateIntent,
  runAnnouncementRequestWithTimeout,
  selectAnnouncementRecoveryCandidates,
} from './announcementRecovery';
import type { AnnouncementDuplicateIntent, AnnouncementSubmissionGuard } from './announcementRecovery';
import { TimelineComposition } from './remotion/TimelineComposition';
import { buildRemotionTimelineCompositionProps } from './remotion/model';
import { QuickCreateForm } from './QuickCreateForm';
import type {
  Approval,
  AnnouncementRecipeRecord,
  AnnouncementSceneRole,
  AnnouncementVideoRecipe,
  Artifact,
  CostEntry,
  DetailedTestVideoRequest,
  ExternalNarrationRequest,
  ExternalVoiceSettings,
  HealthStatus,
  Job,
  LocalAssemblyAudioMixPreset,
  LocalAssemblyCaptionStylePreset,
  LocalAssemblyRequest,
  LocalComfyUiRequest,
  LocalPipelineRequest,
  LocalPipelineStageResult,
  LocalScreenCaptureRequest,
  LocalTimelineClip,
  LocalTimelineRequest,
  LocalRemotionTimelineOverlayPosition,
  LocalRemotionTimelineRequest,
  LocalRemotionTimelineVisualPreset,
  LocalQcRequest,
  LocalQcVariant,
  LocalNarrationRequest,
  ProductionDetail,
  ProductionRun,
  PipelineContinuationState,
  ProductionSummary,
  ProviderTask,
  ProviderTaskStatus,
  ProviderStatus,
  RerunChanges,
  RerunPlan,
  StageAttempt,
  StudioEvent,
  StudioStatus,
  WindowsCaptureCapability,
  WindowsCaptureRequest,
} from './types';

type DetailTab = 'overview' | 'pipeline' | 'announcement' | 'detailed-test' | 'video' | 'capture' | 'narration' | 'timeline' | 'assembly' | 'qc' | 'artifacts' | 'compare' | 'logs' | 'audit';

const STATUS_LABEL: Record<StudioStatus, string> = {
  pending: '待機',
  running: '実行中',
  succeeded: '完了',
  failed: '失敗',
  blocked: '確認待ち',
  approved: '承認済み',
  rejected: '却下',
  cancelled: '中止',
  unknown: '未判定',
};

const STAGE_LABELS: Record<string, string> = {
  planning: '企画・台本',
  script: '台本',
  narration: 'ナレーション',
  captions: '字幕・テロップ',
  capture: '画面収録',
  captures: '画面収録',
  screen_capture: '画面収録',
  keyframe: 'キーフレーム画像',
  keyframes: 'キーフレーム画像',
  generated_visuals: '生成映像',
  visuals: '生成映像',
  video: '生成映像',
  video_generation: '生成映像',
  composition: '編集・合成',
  compose: '編集・合成',
  assembly: '編集・合成',
  timeline: 'カット編集',
  qc: '品質検査',
  release: '公開判定',
};

const formatDate = (value?: string): string => {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const formatDuration = (seconds?: number): string => {
  if (seconds === undefined) return '—';
  if (seconds < 60) return `${Math.round(seconds)}秒`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
};

const formatBytes = (bytes?: number): string => {
  if (bytes === undefined) return '—';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
};

const formatMoney = (amount: number, currency = 'JPY'): string => {
  try {
    return new Intl.NumberFormat('ja-JP', { style: 'currency', currency }).format(amount);
  } catch {
    return `${amount.toLocaleString('ja-JP')} ${currency}`;
  }
};

const stageLabel = (value?: string): string => {
  if (!value) return '未分類';
  return STAGE_LABELS[value.toLowerCase()] ?? value;
};

const StatusBadge = ({ status, label }: { status: StudioStatus; label?: string }) => (
  <span className={`status-badge status-${status}`}>
    <span className="status-dot" aria-hidden="true" />
    {label ?? STATUS_LABEL[status]}
  </span>
);

const costApprovalLabel = (status: StudioStatus): string | undefined => {
  if (status === 'approved') return '費用承認済み';
  if (status === 'rejected') return '費用却下';
  return undefined;
};

const runCostApprovalLabel = (run: ProductionRun): string => {
  if ((run.estimatedCost ?? 0) <= 0) return '費用承認不要';
  return costApprovalLabel(run.status) ?? '費用承認待ち';
};

const jobStatusLabel = (status: StudioStatus): string => {
  if (status === 'pending') return 'キュー待ち';
  if (status === 'running') return '実行中';
  if (status === 'succeeded') return '完了';
  if (status === 'failed') return '失敗';
  return STATUS_LABEL[status];
};

const PROVIDER_TASK_STATUS_LABEL: Record<ProviderTaskStatus, string> = {
  prepared: '照合準備中',
  submitted: 'provider実行中',
  recovering: '復旧中',
  succeeded: 'provider完了',
  failed: '失敗',
  ambiguous: '状態不明',
  recovery_blocked: '復旧停止',
  cancel_requested: 'キャンセル待ち',
  unknown: '状態不明',
};

const providerTaskStatusLabel = (status: ProviderTaskStatus): string => PROVIDER_TASK_STATUS_LABEL[status];

const PIPELINE_CONTINUATION_STATE_LABEL: Record<PipelineContinuationState, string> = {
  active: '初回生成を実行中',
  waiting_provider: 'provider復旧待ち',
  ready: '継続準備完了',
  continuing: '後続工程を継続中',
  succeeded: '自動継続完了',
  recovery_blocked: '復旧停止',
  unavailable: '自動継続不可',
  cancel_requested: 'キャンセル処理中',
  cancelled: 'キャンセル済み',
};

const pipelineContinuationStateLabel = (state: PipelineContinuationState): string =>
  PIPELINE_CONTINUATION_STATE_LABEL[state];

const PIPELINE_CONTINUATION_DESCRIPTION: Record<PipelineContinuationState, string> = {
  active: '初回の一括生成を実行しています。Studio終了時はprovider taskを保持し、次回起動後に同じRunを復旧します。',
  waiting_provider: '同じprovider taskの完了を待っています。生成promptは再送信しません。',
  ready: '復旧済み動画のcheckpointを確定しました。後続工程を同じRunへ自動投入します。',
  continuing: '指定checkpointを含む検証済みcacheだけを使い、同じRunの後続工程を実行しています。',
  succeeded: '同じRunの後続工程と技術QCまで完了しました。',
  recovery_blocked: '安全確認に失敗したため自動継続を停止しました。エラーを確認して明示的に再実行してください。',
  unavailable: '保護済みrequestを保存できなかったため自動継続できません。必要なら同じ入力を明示的に再実行してください。',
  cancel_requested: 'provider側のキャンセル確定を待っています。後続工程は自動継続しません。',
  cancelled: 'キャンセルが確定しました。後続工程は自動継続しません。',
};

const pipelineContinuationDescription = (state: PipelineContinuationState): string =>
  PIPELINE_CONTINUATION_DESCRIPTION[state];

const providerTaskNextActionLabel = (action?: string): string | undefined => {
  if (!action) return undefined;
  const labels: Record<string, string> = {
    submit: '永続化済みtaskを安全に送信できます',
    wait: '復旧処理の完了を待っています',
    none: '追加操作は不要です',
    poll: '状態を監視中',
    inspect: '状態を再照合してください',
    resume: '同じtaskを再開できます',
    recover: '成果物を回収できます',
    retry: '再試行できます',
    reconcile: '手動でprovider状態を確認してください',
    retry_with_matching_request: '同じ暗号化済み入力で再開できます',
    confirm_cancellation: 'provider側の停止状態を確認してください',
    manual_review: '手動確認が必要です',
  };
  return labels[action] ?? action;
};

const localNarrationError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはローカルナレーション実行に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('unsupported') || normalized.includes('not implemented') || normalized.includes('not found')) {
    return 'ローカルナレーションworkerは現在利用できません。対応するbackendが起動しているか確認してください。';
  }
  if (normalized.includes('profile') && normalized.includes('local')) {
    return 'このRunはlocal_sapi実行用ではありません。ローカル音声プロファイルでRunを作成してください。';
  }
  return `ローカルナレーション実行に失敗しました：${message}`;
};

const externalNarrationError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはElevenLabs外部ナレーションに対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('approval') || normalized.includes('approved') || normalized.includes('billable')) {
    return `外部TTSの課金承認ゲートで停止しました：${message}`;
  }
  if (normalized.includes('provider') || normalized.includes('eleven')) {
    return `ElevenLabs外部ナレーションに失敗しました：${message}`;
  }
  return `外部ナレーション実行に失敗しました：${message}`;
};

const normalizeRequestedStage = (value: string): string => value.toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');

const hasNarrationStage = (run: ProductionRun): boolean =>
  run.requestedStages.some((stage) => ['narration', 'script', 'copy', 'voice', 'pronunciation'].includes(normalizeRequestedStage(stage)))
  || run.stages.some((stage) => ['narration', 'script', 'copy', 'voice', 'pronunciation'].includes(normalizeRequestedStage(stage.name)));

const hasAssemblyStage = (run: ProductionRun): boolean =>
  run.requestedStages.some((stage) => normalizeRequestedStage(stage) === 'assembly')
  || run.stages.some((stage) => normalizeRequestedStage(stage.name) === 'assembly');

const hasScreenCaptureStage = (run: ProductionRun): boolean =>
  run.requestedStages.some((stage) => normalizeRequestedStage(stage) === 'screen_capture')
  || run.stages.some((stage) => normalizeRequestedStage(stage.name) === 'screen_capture');

const isWindowsCaptureRun = (run?: ProductionRun): boolean =>
  Boolean(run && hasScreenCaptureStage(run) && run.executionProfile === 'local_windows_capture');

const hasLocalSapiProfile = (run?: ProductionRun): boolean => run?.executionProfile === 'local_sapi';

const hasElevenLabsProfile = (run?: ProductionRun): boolean => run?.executionProfile === 'elevenlabs_tts';

const hasHardCutTimelineProfile = (run?: ProductionRun): boolean =>
  hasLocalSapiProfile(run) || run?.executionProfile === 'local_playwright';

const hasRemotionTimelineProfile = (run?: ProductionRun): boolean =>
  hasHardCutTimelineProfile(run) || run?.executionProfile === 'local_comfyui';

const localScreenCaptureError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはPlaywright画面収録に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('playwright') || normalized.includes('chromium')) {
    return `Playwright画面収録を開始できませんでした：${message}`;
  }
  if (normalized.includes('profile')) {
    return 'このRunはlocal_playwright実行用ではありません。画面収録プロファイルでRunを作成してください。';
  }
  return `ローカル画面収録に失敗しました：${message}`;
};

const localWindowsCaptureError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはWindowsネイティブ収録に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('profile')) {
    return 'このRunはlocal_windows_capture実行用ではありません。Windows収録プロファイルでRunを作成してください。';
  }
  if (normalized.includes('capability') || normalized.includes('workstation') || normalized.includes('ready')) {
    return `Windows収録環境を利用できません：${message}`;
  }
  return `Windowsネイティブ画面収録に失敗しました：${message}`;
};

const screenCaptureProgressPhaseLabel = (phase?: string): string => ({
  queued: '待機中',
  preflight: '実行環境を確認中',
  recording: 'Chromiumで収録中',
  transcoding: 'MP4へ変換中',
  verification: '映像を検証中',
  publishing: '成果物を公開中',
  registration: '監査記録へ登録中',
  completed: '完了',
}[phase ?? ''] ?? (phase || '—'));

/** Assembly and technical QC remain local for both local SAPI and ElevenLabs runs. */
const hasLocalMediaProfile = (run?: ProductionRun): boolean => hasLocalSapiProfile(run) || hasElevenLabsProfile(run);

const localAssemblyError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはローカル編集・合成に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('profile') && normalized.includes('local')) {
    return 'このRunはlocal_sapi実行用ではありません。ローカル音声プロファイルでRunを作成してください。';
  }
  return `ローカル編集・合成に失敗しました：${message}`;
};

const localPipelineError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendは一括生成に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('duplicate') || normalized.includes('already') || normalized.includes('active')) {
    return `同じ一括生成がすでに実行中です。既存Runの監視を継続してください：${message}`;
  }
  return `ローカル一括生成に失敗しました：${message}`;
};

const detailedTestVideoError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendは詳細一括に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('duplicate') || normalized.includes('already') || normalized.includes('active')) {
    return `同じ詳細一括がすでに実行中です。既存Jobの監視を継続してください：${message}`;
  }
  return `詳細一括に失敗しました：${message}`;
};

const announcementVideoError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendは告知動画に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  if (error instanceof StudioApiError && error.code === 'announcement_recipe_conflict') {
    return `別の画面または操作でrecipeが更新されています。再読込してから編集してください：${message}`;
  }
  return `告知動画の処理に失敗しました：${message}`;
};

const isReceivedAnnouncementClientError = (error: unknown): error is StudioApiError =>
  error instanceof StudioApiError && error.status >= 400 && error.status < 500;

const runIdempotentAnnouncementMutation = async <T,>(
  operation: (signal: AbortSignal) => Promise<T>,
  onAmbiguousResponse: () => void,
): Promise<T> => {
  try {
    return await runAnnouncementRequestWithTimeout(operation);
  } catch (error) {
    if (isReceivedAnnouncementClientError(error)) throw error;
    onAmbiguousResponse();
    // Recipe save is content/CAS idempotent and duplicate is idempotent only
    // when its pre-generated newRecipeId is reused. Never rebuild the request.
    return await runAnnouncementRequestWithTimeout(operation);
  }
};

const localQcError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはローカル技術QCに対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('profile') && normalized.includes('local')) {
    return 'このRunはlocal_sapi実行用ではありません。assembly＋qcを含むlocal_sapi Runを選択してください。';
  }
  if (normalized.includes('caption')) {
    return '選択したassembly attemptにcaptioned masterがありません。実在するmasterだけを選択してください。';
  }
  return `ローカル技術QCに失敗しました：${message}`;
};

const localTimelineError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはローカルカット編集に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('profile') && normalized.includes('local')) {
    return 'このRunはlocal_sapi実行用ではありません。timeline工程を含むlocal_sapi Runを選択してください。';
  }
  return `ローカルカット編集に失敗しました：${message}`;
};

const localComfyUiError = (error: unknown): string => {
  if (error instanceof StudioApiError && error.unsupported) {
    return 'このStudio backendはローカルComfyUI動画生成に対応していません。backendを更新してから再試行してください。';
  }
  const message = error instanceof Error ? error.message : String(error);
  const normalized = message.toLowerCase();
  if (normalized.includes('profile') && normalized.includes('comfy')) {
    return 'このRunはlocal_comfyui実行用ではありません。動画生成用のRunを作成してください。';
  }
  if (normalized.includes('stage') && normalized.includes('video')) {
    return 'このRunにはvideo_generation工程がありません。動画生成を選択してRunを作成してください。';
  }
  return `ローカルComfyUI動画生成に失敗しました：${message}`;
};

const displayQcValue = (value: unknown): string => {
  if (value === undefined || value === null || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return '（表示できない値）';
  }
};

const EmptyState = ({ title, description }: { title: string; description?: string }) => (
  <div className="empty-state">
    <div className="empty-mark" aria-hidden="true">◇</div>
    <strong>{title}</strong>
    {description && <p>{description}</p>}
  </div>
);

const LoadingState = ({ label = '読み込み中' }: { label?: string }) => (
  <div className="loading-state" role="status">
    <span className="spinner" aria-hidden="true" />
    <span>{label}</span>
  </div>
);

const ErrorNotice = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div className="notice notice-error" role="alert">
    <div>
      <strong>読み込みに失敗しました</strong>
      <p>{message}</p>
    </div>
    {onRetry && <button className="button button-secondary" onClick={onRetry}>再試行</button>}
  </div>
);

const PENDING_PRODUCTION_CREATE_STORAGE_KEY = 'minimax-h3-studio:pending-production-create:v1';
const PENDING_PRODUCTION_CREATE_SCHEMA_VERSION = 1;

interface PendingProductionCreateIntent {
  productionId: string;
  title: string;
}

interface PendingProductionCreateRead {
  intent?: PendingProductionCreateIntent;
  error?: string;
}

const readPendingProductionCreateIntent = (): PendingProductionCreateRead => {
  try {
    const raw = window.localStorage.getItem(PENDING_PRODUCTION_CREATE_STORAGE_KEY);
    if (!raw) return {};
    const value: unknown = JSON.parse(raw);
    if (value === null || typeof value !== 'object') {
      return { error: '制作作成の保留情報を読み取れません。誤って別IDを発行しないよう作成を停止しました。' };
    }
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort();
    if (keys.length === 3
      && keys[0] === 'production_id'
      && keys[1] === 'schema_version'
      && keys[2] === 'title'
      && record.schema_version === PENDING_PRODUCTION_CREATE_SCHEMA_VERSION
      && typeof record.production_id === 'string'
      && PRODUCTION_ID_PATTERN.test(record.production_id)
      && typeof record.title === 'string'
      && record.title.trim().length > 0
      && record.title === record.title.trim()
      && record.title.length <= PRODUCTION_TITLE_MAX_LENGTH
      && !/[\u0000-\u001f\u007f]/.test(record.title)
    ) return { intent: { productionId: record.production_id, title: record.title } };
    return { error: '制作作成の保留情報が不完全です。誤って別IDを発行しないよう作成を停止しました。' };
  } catch {
    return { error: '制作作成の保留情報を読み取れません。ブラウザの保存領域を確認してください。' };
  }
};

const persistPendingProductionCreateIntent = (intent: PendingProductionCreateIntent): void => {
  if (!PRODUCTION_ID_PATTERN.test(intent.productionId)
    || !intent.title
    || intent.title !== intent.title.trim()
    || intent.title.length > PRODUCTION_TITLE_MAX_LENGTH
    || /[\u0000-\u001f\u007f]/.test(intent.title)) {
    throw new Error('制作作成の保留情報が不正です。');
  }
  try {
    window.localStorage.setItem(PENDING_PRODUCTION_CREATE_STORAGE_KEY, JSON.stringify({
      schema_version: PENDING_PRODUCTION_CREATE_SCHEMA_VERSION,
      production_id: intent.productionId,
      title: intent.title,
    }));
  } catch {
    throw new Error('ブラウザの保留情報を保存できません。localStorageを有効にして再試行してください。');
  }
};

const clearPendingProductionCreateIntent = (): boolean => {
  try {
    window.localStorage.removeItem(PENDING_PRODUCTION_CREATE_STORAGE_KEY);
    return true;
  } catch {
    // A successful server response must not be shown as a failed creation when
    // storage cleanup is unavailable. The next open will still use the same ID.
    return false;
  }
};

const newClientStableProductionId = (): string => {
  const uuid = globalThis.crypto?.randomUUID?.();
  if (!uuid) throw new Error('このブラウザでは安全な制作IDを生成できません。');
  return `production_${uuid.replaceAll('-', '')}`;
};

type ImportFileState = 'pending' | 'uploading' | 'succeeded' | 'failed';

interface ImportFileItem {
  file: File;
  state: ImportFileState;
  error?: string;
  deduplicated?: boolean;
}

const importFileStateLabel: Record<ImportFileState, string> = {
  pending: '待機中',
  uploading: 'アップロード中',
  succeeded: '取込済み',
  failed: '失敗',
};

function ImportFileList({ items }: { items: ImportFileItem[] }) {
  if (items.length === 0) return null;
  return (
    <ol className="video-import-file-list" aria-label="動画ファイルの取込状況">
      {items.map((item, index) => (
        <li key={`${item.file.name}-${item.file.size}-${item.file.lastModified}-${index}`}>
          <div className="video-import-file-heading">
            <strong title={item.file.name}>{item.file.name}</strong>
            <span>{formatBytes(item.file.size)}</span>
          </div>
          <span className={`video-import-file-state is-${item.state}`}>{importFileStateLabel[item.state]}</span>
          {item.deduplicated && <small>既存artifactを再利用</small>}
          {item.error && <small className="video-import-file-error">{item.error}</small>}
        </li>
      ))}
    </ol>
  );
}

function VideoAssetImportPanel({
  productionId,
  currentVideoCount,
  onReload,
}: {
  productionId: string;
  currentVideoCount: number;
  onReload: (signal?: AbortSignal) => Promise<boolean>;
}) {
  const [items, setItems] = useState<ImportFileItem[]>([]);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    const validation = validateVideoImportFiles(files);
    setValidationErrors(validation.errors);
    setMessage(undefined);
    if (!validation.valid) {
      setItems([]);
      event.currentTarget.value = '';
      return;
    }
    setItems(files.map((file) => ({ file, state: 'pending' })));
  }, []);

  const clearSelection = useCallback(() => {
    if (uploading) return;
    setItems([]);
    setValidationErrors([]);
    setMessage(undefined);
    if (inputRef.current) inputRef.current.value = '';
  }, [uploading]);

  const uploadFiles = useCallback(async () => {
    if (uploading || items.length === 0 || validationErrors.length > 0) return;
    setUploading(true);
    setMessage({ type: 'info', text: '動画を1件ずつ取込中です。' });
    let successCount = 0;
    const failures: string[] = [];
    for (const [index, item] of items.entries()) {
      if (item.state === 'succeeded') {
        successCount += 1;
        continue;
      }
      setItems((current) => current.map((entry, itemIndex) => itemIndex === index
        ? { ...entry, state: 'uploading', error: undefined }
        : entry));
      try {
        const result = await api.importVideo(productionId, item.file);
        successCount += 1;
        setItems((current) => current.map((entry, itemIndex) => itemIndex === index
          ? { ...entry, state: 'succeeded', deduplicated: result.deduplicated, error: undefined }
          : entry));
      } catch (error) {
        const detail = error instanceof Error ? error.message : '取込に失敗しました';
        failures.push(`${item.file.name}: ${detail}`);
        setItems((current) => current.map((entry, itemIndex) => itemIndex === index
          ? { ...entry, state: 'failed', error: detail }
          : entry));
      }
    }
    const reloaded = await onReload().catch(() => false);
    setUploading(false);
    if (!reloaded) {
      setMessage({ type: 'error', text: '取込済み・再読込失敗です。制作画面を手動で再読込してください。' });
    } else if (failures.length > 0) {
      setMessage({ type: 'error', text: `${successCount}件を取込済み。${failures.length}件は失敗しました。失敗したファイルを再試行できます。` });
    } else {
      setMessage({ type: 'success', text: `${successCount}件の動画を制作へ追加しました。` });
    }
  }, [items, onReload, productionId, uploading, validationErrors.length]);

  return (
    <section className="panel compact-panel video-import-panel" aria-labelledby={`video-import-title-${productionId}`}>
      <div className="panel-header">
        <div><span className="section-kicker">SOURCE VIDEOS</span><h3 id={`video-import-title-${productionId}`}>動画素材を追加</h3></div>
        <span className="tag">現在 {currentVideoCount}本</span>
      </div>
      <p className="panel-lead">Quick Createで使う素材が少ないときに追加できます。サーバーへは選択した動画のraw bodyだけを順番に送ります。</p>
      <label className="field">
        <span>動画ファイル（最大{MAX_VIDEO_IMPORT_FILES}個）</span>
        <input ref={inputRef} type="file" accept=".mp4,.m4v,.mov,.mkv,.webm,.avi" multiple disabled={uploading} onChange={handleFileChange} />
        <small className="field-help">1ファイル0より大きく2 GiB以下。取込結果はartifactとして再読込します。</small>
      </label>
      {validationErrors.length > 0 && <div className="validation-list" role="alert">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
      <ImportFileList items={items} />
      <div className="button-row">
        <button className="button button-primary" type="button" disabled={uploading || items.length === 0 || validationErrors.length > 0} onClick={() => void uploadFiles()}>{uploading ? '順番に取込中…' : '動画を追加'}</button>
        <button className="button button-ghost" type="button" disabled={uploading || items.length === 0} onClick={clearSelection}>選択をクリア</button>
      </div>
      {message && <div className={`inline-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'} aria-live="polite">{message.text}</div>}
    </section>
  );
}

function NewProductionDialog({
  open,
  onClose,
  onProductionReady,
  canCreateProduction,
}: {
  open: boolean;
  onClose: () => void;
  onProductionReady: (productionId: string) => Promise<boolean>;
  canCreateProduction: () => boolean;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleRef = useRef<HTMLInputElement>(null);
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);
  const [productionId, setProductionId] = useState('');
  const [title, setTitle] = useState('');
  const [items, setItems] = useState<ImportFileItem[]>([]);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [created, setCreated] = useState(false);
  const [canDiscardIntent, setCanDiscardIntent] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) {
      if (dialogRef.current?.open) dialogRef.current.close();
      return;
    }
    previouslyFocusedRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const pendingResult = readPendingProductionCreateIntent();
    try {
      if (pendingResult.error) {
        setProductionId('');
        setTitle('');
        setMessage({ type: 'error', text: pendingResult.error });
        setCanDiscardIntent(true);
      } else {
        setProductionId(pendingResult.intent?.productionId ?? newClientStableProductionId());
        setTitle(pendingResult.intent?.title ?? '');
        setMessage(pendingResult.intent ? { type: 'info', text: '前回の作成応答が未確定です。同じ制作IDで再試行します。' } : undefined);
        setCanDiscardIntent(Boolean(pendingResult.intent));
      }
    } catch (error) {
      setProductionId('');
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '制作IDを生成できません。' });
      setCanDiscardIntent(false);
    }
    setItems([]);
    setValidationErrors([]);
    setCreated(false);
    setSubmitting(false);
    if (inputRef.current) inputRef.current.value = '';
    if (dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal();
    window.setTimeout(() => titleRef.current?.focus(), 0);
  }, [open]);

  const closeDialog = useCallback(() => {
    if (submitting) return;
    if (dialogRef.current?.open) dialogRef.current.close();
    onClose();
    previouslyFocusedRef.current?.focus();
  }, [onClose, submitting]);

  const handleCancel = useCallback((event: SyntheticEvent<HTMLDialogElement>) => {
    event.preventDefault();
    closeDialog();
  }, [closeDialog]);

  const handleFileChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    const validation = validateVideoImportFiles(files);
    setValidationErrors(validation.errors);
    setMessage(undefined);
    if (!validation.valid) {
      setItems([]);
      event.currentTarget.value = '';
      return;
    }
    setItems(files.map((file) => ({ file, state: 'pending' })));
  }, []);

  const discardPendingIntent = useCallback(() => {
    if (submitting || !canDiscardIntent) return;
    if (!window.confirm('保留情報を破棄すると、同じ制作を再試行できず別の制作IDになる可能性があります。破棄しますか？')) return;
    if (!clearPendingProductionCreateIntent()) {
      setMessage({ type: 'error', text: '保留情報を破棄できません。localStorageを確認してください。' });
      return;
    }
    try {
      setProductionId(newClientStableProductionId());
      setTitle('');
      setItems([]);
      setValidationErrors([]);
      setCanDiscardIntent(false);
      setCreated(false);
      setMessage({ type: 'info', text: '保留情報を破棄しました。新しい制作IDを発行しました。' });
    } catch (error) {
      setProductionId('');
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '新しい制作IDを生成できません。' });
    }
  }, [canDiscardIntent, submitting]);

  const handleSubmit = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting || validationErrors.length > 0) return;
    const currentId = productionId.trim();
    const currentTitle = title.trim();
    if (!currentId || !currentTitle) {
      setMessage({ type: 'error', text: 'タイトルを入力してください。' });
      return;
    }
    setSubmitting(true);
    setMessage({ type: 'info', text: created ? '選択した動画を順番に取込中です。' : '制作を作成しています。' });
    try {
      if (!created) {
        if (!canCreateProduction()) {
          setMessage({ type: 'info', text: '未保存の変更があるため、制作作成をキャンセルしました。' });
          return;
        }
        // Persist before the POST so a lost response can be retried with the
        // same backend id; never silently mint a second production.
        persistPendingProductionCreateIntent({ productionId: currentId, title: currentTitle });
        let creationConfirmed = false;
        try {
          await api.createProduction(currentId, currentTitle);
          creationConfirmed = true;
        } catch (error) {
          if (isStudioApiResponseLoss(error)) {
            try {
              const reconciled = await api.production(currentId);
              if (reconciled.id === currentId && reconciled.title === currentTitle) creationConfirmed = true;
            } catch {
              // Keep the intent until the exact GET succeeds or the user
              // explicitly chooses the duplicate-risk discard action.
            }
          }
          if (!creationConfirmed) {
            setCanDiscardIntent(true);
            const prefix = isStudioApiResponseLoss(error)
              ? '作成応答が不明で、同じIDの制作もまだ確認できません。'
              : error instanceof Error ? error.message : '制作を作成できませんでした。';
            setMessage({ type: 'error', text: `${prefix}同じIDで再試行するか、保留情報を明示的に破棄してください。` });
            return;
          }
        }
        clearPendingProductionCreateIntent();
        setCanDiscardIntent(false);
        setCreated(true);
      }

      const ready = await onProductionReady(currentId);
      if (!ready) {
        setMessage({ type: 'error', text: items.length > 0 ? '制作は作成済みですが、動画取込前の再読込に失敗しました。再試行してください。' : '制作は作成済み・再読込失敗です。再試行してください。' });
        return;
      }

      if (items.length === 0) {
        setMessage({ type: 'success', text: '制作を作成しました。' });
        closeDialog();
        return;
      }

      let successCount = 0;
      const failures: string[] = [];
      for (const [index, item] of items.entries()) {
        if (item.state === 'succeeded') {
          successCount += 1;
          continue;
        }
        setItems((current) => current.map((entry, itemIndex) => itemIndex === index
          ? { ...entry, state: 'uploading', error: undefined }
          : entry));
        try {
          const result = await api.importVideo(currentId, item.file);
          successCount += 1;
          setItems((current) => current.map((entry, itemIndex) => itemIndex === index
            ? { ...entry, state: 'succeeded', deduplicated: result.deduplicated, error: undefined }
            : entry));
        } catch (error) {
          const detail = error instanceof Error ? error.message : '取込に失敗しました';
          failures.push(`${item.file.name}: ${detail}`);
          setItems((current) => current.map((entry, itemIndex) => itemIndex === index
            ? { ...entry, state: 'failed', error: detail }
            : entry));
        }
      }
      const reloaded = await onProductionReady(currentId);
      if (!reloaded) {
        setMessage({ type: 'error', text: '取込済み・再読込失敗です。制作画面の再読込を実行してください。' });
        return;
      }
      if (failures.length > 0) {
        setMessage({ type: 'error', text: `${successCount}件を取込済み。${failures.length}件は失敗しました。失敗した動画だけ再試行できます。` });
        return;
      }
      setMessage({ type: 'success', text: items.length > 0 ? `${successCount}件の動画を追加しました。` : '制作を作成しました。' });
      closeDialog();
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '制作処理に失敗しました。' });
    } finally {
      setSubmitting(false);
    }
  }, [canCreateProduction, closeDialog, created, items, onProductionReady, productionId, submitting, title, validationErrors.length]);

  return (
    <dialog ref={dialogRef} className="new-production-dialog" aria-labelledby="new-production-title" onCancel={handleCancel}>
      <form className="new-production-form" onSubmit={(event) => void handleSubmit(event)}>
        <div className="panel-header">
          <div><span className="section-kicker">NEW PRODUCTION</span><h2 id="new-production-title">新しい制作</h2></div>
          <button className="button button-ghost" type="button" onClick={closeDialog} disabled={submitting} aria-label="新しい制作ダイアログを閉じる">閉じる</button>
        </div>
        <p className="panel-lead">制作を作成して、必要なら動画素材を順番に取り込みます。作成IDは応答が不明な場合も保持されます。</p>
        <label className="field" htmlFor="new-production-title-input"><span>タイトル</span><input id="new-production-title-input" ref={titleRef} maxLength={120} value={title} disabled={submitting || created || canDiscardIntent} onChange={(event) => setTitle(event.target.value)} placeholder="例：Claude Code解説ショート" required /></label>
        <label className="field" htmlFor="new-production-id-input"><span>作成ID（再試行時も同じ）</span><input id="new-production-id-input" value={productionId} readOnly disabled={submitting || created} aria-describedby="new-production-id-help" /><small id="new-production-id-help" className="field-help">production_＋UUIDの固定ID。手動変更はできません。</small></label>
        <label className="field" htmlFor="new-production-files-input"><span>動画素材（任意、最大{MAX_VIDEO_IMPORT_FILES}個）</span><input id="new-production-files-input" ref={inputRef} type="file" accept=".mp4,.m4v,.mov,.mkv,.webm,.avi" multiple disabled={submitting} onChange={handleFileChange} /><small className="field-help">対応形式: mp4 / m4v / mov / mkv / webm / avi。1ファイル0より大きく2 GiB以下。選択順に1件ずつ取込みます。</small></label>
        {validationErrors.length > 0 && <div className="validation-list" role="alert">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
        <ImportFileList items={items} />
        {message && <div className={`inline-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'} aria-live="polite">{message.text}</div>}
        <div className="button-row new-production-actions">
          <button className="button button-primary" type="submit" disabled={submitting || !productionId || !title.trim() || validationErrors.length > 0}>{submitting ? '処理中…' : created && items.some((item) => item.state === 'failed') ? '失敗した動画を再試行' : '制作を作成'}</button>
          <button className="button button-secondary" type="button" onClick={closeDialog} disabled={submitting}>キャンセル</button>
        </div>
        {canDiscardIntent && <button className="button button-ghost new-production-discard" type="button" disabled={submitting} onClick={discardPendingIntent}>保留情報を破棄（別IDになる可能性あり）</button>}
      </form>
    </dialog>
  );
}

function App() {
  const [health, setHealth] = useState<HealthStatus>({ healthy: false, message: '確認中' });
  const [productions, setProductions] = useState<ProductionSummary[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [detail, setDetail] = useState<ProductionDetail>();
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [detailError, setDetailError] = useState<string>();
  const [refreshing, setRefreshing] = useState(false);
  const [query, setQuery] = useState('');
  const [unsavedAnnouncementProductionId, setUnsavedAnnouncementProductionId] = useState<string>();
  const [newProductionOpen, setNewProductionOpen] = useState(false);
  const [cancellingJobIds, setCancellingJobIds] = useState<Set<string>>(() => new Set());
  const [jobActionMessage, setJobActionMessage] = useState<string>();
  const selectedIdRef = useRef<string | undefined>(selectedId);
  const detailRequestRef = useRef<{ id: string; generation: number; controller: AbortController } | undefined>(undefined);
  const detailRequestGenerationRef = useRef(0);
  selectedIdRef.current = selectedId;

  const loadDashboard = useCallback(async (): Promise<boolean> => {
    setLoading(true);
    setError(undefined);
    const results = await Promise.allSettled([api.health(), api.productions(), api.jobs(), api.providers()]);
    const [healthResult, productionResult, jobsResult, providersResult] = results;
    if (healthResult.status === 'fulfilled') setHealth(healthResult.value);
    if (productionResult.status === 'fulfilled') {
      setProductions(productionResult.value);
      setSelectedId((current) => {
        const next = current ?? productionResult.value[0]?.id;
        selectedIdRef.current = next;
        return next;
      });
    }
    if (jobsResult.status === 'fulfilled') setJobs(jobsResult.value);
    if (providersResult.status === 'fulfilled') setProviders(providersResult.value);
    const failures = results.filter((result) => result.status === 'rejected') as PromiseRejectedResult[];
    if (failures.length) {
      setError(failures.map((failure) => failure.reason instanceof Error ? failure.reason.message : String(failure.reason)).join(' / '));
    }
    setLoading(false);
    return failures.length === 0;
  }, []);

  const loadDetail = useCallback(async (id: string, signal?: AbortSignal): Promise<boolean> => {
    if (selectedIdRef.current !== id) return false;
    detailRequestRef.current?.controller.abort();
    const controller = new AbortController();
    const generation = detailRequestGenerationRef.current + 1;
    detailRequestGenerationRef.current = generation;
    detailRequestRef.current = { id, generation, controller };
    const relayAbort = () => controller.abort();
    if (signal?.aborted) controller.abort();
    else signal?.addEventListener('abort', relayAbort, { once: true });
    setDetailLoading(true);
    setDetailError(undefined);
    try {
      const loaded = await api.production(id, controller.signal);
      if (
        controller.signal.aborted
        || selectedIdRef.current !== id
        || detailRequestRef.current?.generation !== generation
      ) return false;
      setDetail(loaded);
      return true;
    } catch (loadError) {
      if (signal?.aborted) throw loadError;
      if (controller.signal.aborted || detailRequestRef.current?.generation !== generation) return false;
      // Keep the last known detail mounted during a polling failure so an
      // active provider task does not reset the form or recovery controls.
      setDetail((current) => current?.id === id ? current : undefined);
      setDetailError(loadError instanceof Error ? loadError.message : '制作情報を取得できませんでした');
      return false;
    } finally {
      signal?.removeEventListener('abort', relayAbort);
      if (detailRequestRef.current?.generation === generation) {
        detailRequestRef.current = undefined;
        setDetailLoading(false);
      }
    }
  }, []);

  const abortDetailRequest = useCallback(() => {
    detailRequestRef.current?.controller.abort();
    detailRequestRef.current = undefined;
  }, []);

  useEffect(() => { void loadDashboard(); }, [loadDashboard]);
  useEffect(() => {
    if (selectedId) void loadDetail(selectedId);
    else {
      abortDetailRequest();
      setDetail(undefined);
    }
    return abortDetailRequest;
  }, [abortDetailRequest, selectedId, loadDetail]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void Promise.all([api.health(), api.jobs()]).then(([nextHealth, nextJobs]) => {
        setHealth(nextHealth);
        setJobs(nextJobs);
      }).catch(() => undefined);
    }, 15000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!unsavedAnnouncementProductionId) return;
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warnBeforeUnload);
    return () => window.removeEventListener('beforeunload', warnBeforeUnload);
  }, [unsavedAnnouncementProductionId]);

  const refreshIndex = async () => {
    setRefreshing(true);
    try {
      await api.refreshIndex();
      await loadDashboard();
      if (selectedIdRef.current) await loadDetail(selectedIdRef.current);
    } catch (refreshError) {
      setError(refreshError instanceof Error ? refreshError.message : 'インデックスを更新できませんでした');
    } finally {
      setRefreshing(false);
    }
  };

  const filteredProductions = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return productions;
    return productions.filter((production) =>
      [production.title, production.description, ...production.tags].filter(Boolean).join(' ').toLowerCase().includes(normalized),
    );
  }, [productions, query]);

  const selectedDetailId = selectedId;
  const reloadSelectedDetail = useCallback(async (signal?: AbortSignal) => {
    if (selectedDetailId) await loadDetail(selectedDetailId, signal);
  }, [loadDetail, selectedDetailId]);
  const reloadSelectedDetailWithStatus = useCallback(async (signal?: AbortSignal): Promise<boolean> => {
    if (!selectedDetailId) return false;
    return loadDetail(selectedDetailId, signal);
  }, [loadDetail, selectedDetailId]);

  const refreshProductionAfterMutation = useCallback(async (productionId: string): Promise<boolean> => {
    selectedIdRef.current = productionId;
    setSelectedId(productionId);
    const dashboardLoaded = await loadDashboard();
    // loadDashboard may have received a stale list while the create/import
    // response is settling. Keep the requested id selected for the detail GET.
    selectedIdRef.current = productionId;
    setSelectedId(productionId);
    const detailLoaded = await loadDetail(productionId);
    return dashboardLoaded && detailLoaded;
  }, [loadDashboard, loadDetail]);

  const openNewProductionDialog = useCallback(() => {
    setNewProductionOpen(true);
  }, []);

  const canCreateProduction = useCallback(() => {
    if (unsavedAnnouncementProductionId !== selectedId) return true;
    if (!window.confirm('告知動画の未保存変更を破棄して、新しい制作を作成しますか？')) return false;
    setUnsavedAnnouncementProductionId(undefined);
    return true;
  }, [selectedId, unsavedAnnouncementProductionId]);

  const cancelJob = useCallback(async (job: Job) => {
    if (cancellingJobIds.has(job.id)) return;
    if (!window.confirm(`Job ${job.id} の停止を要求しますか？実行中のworkerが終了するまで状態は確定しません。`)) return;
    setCancellingJobIds((current) => new Set(current).add(job.id));
    setJobActionMessage(`Job ${job.id} の停止要求を送信中です。`);
    try {
      const response = await api.cancelJob(job.id);
      const serverStatus = response.job?.status ?? response.status;
      setJobActionMessage(response.workerRetired === true
        ? `Job ${job.id} は停止要求済み・worker終了を確認しました（${serverStatus ?? '状態を再確認中'}）。`
        : serverStatus === 'cancelled'
          ? `Job ${job.id} の中止状態をサーバーで確認しました。`
        : `Job ${job.id} は停止要求済み・worker終了待ちです（${serverStatus ?? '状態を再確認中'}）。`);
      await loadDashboard();
      if (selectedIdRef.current) await loadDetail(selectedIdRef.current);
    } catch (error) {
      setJobActionMessage(`Job ${job.id} の停止要求に失敗しました：${error instanceof Error ? error.message : '不明なエラー'}`);
    } finally {
      setCancellingJobIds((current) => {
        const next = new Set(current);
        next.delete(job.id);
        return next;
      });
    }
  }, [cancellingJobIds, loadDashboard, loadDetail]);
  const updateSelectedAnnouncementDirty = useCallback((dirty: boolean) => {
    if (!selectedDetailId) return;
    setUnsavedAnnouncementProductionId((current) => (
      dirty ? selectedDetailId : current === selectedDetailId ? undefined : current
    ));
  }, [selectedDetailId]);

  const selectProduction = (productionId: string) => {
    if (productionId === selectedId) return;
    if (unsavedAnnouncementProductionId === selectedId
      && !window.confirm('告知動画の未保存変更を破棄して、別の制作へ移動しますか？')) return;
    abortDetailRequest();
    selectedIdRef.current = productionId;
    setUnsavedAnnouncementProductionId(undefined);
    setSelectedId(productionId);
  };

  const activeJobs = jobs.filter((job) => job.status === 'running' || job.status === 'pending');
  const configuredProviders = providers.filter((provider) => provider.configured).length;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark" aria-hidden="true"><span /></div>
          <div>
            <div className="eyebrow">LOCAL PRODUCTION CONTROL</div>
            <h1>MiniMax H3 Studio</h1>
          </div>
        </div>
        <div className="topbar-actions">
          <div className={`connection-state ${health.degraded ? 'is-degraded' : health.healthy ? 'is-online' : 'is-offline'}`} title={health.message}>
            <span aria-hidden="true" />
            <span>{health.degraded ? '監査ログ 要確認' : health.healthy ? 'API 接続中' : 'API 未接続'}</span>
            {health.version && <small>v{health.version}</small>}
          </div>
          <button className="button button-primary" type="button" onClick={openNewProductionDialog} aria-haspopup="dialog">
            <span aria-hidden="true">＋</span>
            新しい制作
          </button>
          <button className="button button-secondary" onClick={() => void refreshIndex()} disabled={refreshing}>
            <span aria-hidden="true">↻</span>
            {refreshing ? '更新中…' : 'インデックス更新'}
          </button>
        </div>
      </header>

      {(activeJobs.length > 0 || jobActionMessage) && <JobsStrip jobs={activeJobs} productions={productions} cancellingJobIds={cancellingJobIds} onCancelJob={cancelJob} actionMessage={jobActionMessage} />}

      <div className="studio-layout">
        <aside className="production-sidebar" aria-label="制作一覧">
          <div className="sidebar-header">
            <div>
              <span className="section-kicker">PRODUCTIONS</span>
              <h2>制作一覧</h2>
            </div>
            <span className="count-chip">{productions.length}</span>
          </div>
          <label className="search-box">
            <span className="sr-only">制作を検索</span>
            <span aria-hidden="true">⌕</span>
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="タイトル・タグで検索" />
          </label>

          {loading && <LoadingState />}
          {!loading && error && productions.length === 0 && <ErrorNotice message={error} onRetry={() => void loadDashboard()} />}
          {!loading && filteredProductions.length === 0 && !error && (
            <EmptyState title="制作がありません" description="productions を追加し、インデックスを更新してください。" />
          )}
          <div className="production-list">
            {filteredProductions.map((production) => (
              <button
                key={production.id}
                className={`production-card ${selectedId === production.id ? 'is-selected' : ''}`}
                onClick={() => selectProduction(production.id)}
                aria-current={selectedId === production.id ? 'page' : undefined}
              >
                <div className="production-thumb">
                  {production.thumbnailUrl
                    ? <img src={production.thumbnailUrl} alt="" />
                    : <span aria-hidden="true">{production.title.slice(0, 1)}</span>}
                </div>
                <div className="production-card-body">
                  <div className="production-card-top">
                    <strong>{production.title}</strong>
                    <StatusBadge status={production.status} />
                  </div>
                  <div className="production-meta">
                    <span>{formatDuration(production.durationSeconds)}</span>
                    <span>{formatDate(production.updatedAt)}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div className="provider-summary">
            <div className="provider-summary-title">
              <span>プロバイダー</span>
              <span>{configuredProviders}/{providers.length} 認証情報設定済み</span>
            </div>
            {providers.length === 0
              ? <p>設定情報がありません</p>
              : providers.map((provider) => (
                <div className="provider-row" key={provider.id} title={provider.message}>
                  <span className={`provider-indicator ${provider.healthy === true ? 'is-ready' : provider.configured ? 'is-configured' : ''}`} aria-hidden="true" />
                  <span>{provider.name}</span>
                  <small>{provider.configured ? (provider.healthy === true ? '接続確認済み' : provider.healthy === false ? '接続エラー' : '接続未確認') : '未設定'}</small>
                </div>
              ))}
          </div>
        </aside>

        <main className="workspace">
          {error && productions.length > 0 && <ErrorNotice message={error} onRetry={() => void loadDashboard()} />}
          {!selectedId && !loading && <EmptyState title="制作を選択してください" description="左の一覧から確認する制作を選択します。" />}
          {selectedId && detailLoading && (!detail || detail.id !== selectedId) && <LoadingState label="制作記録を読み込み中" />}
          {selectedId && detailError && !detailLoading && (!detail || detail.id !== selectedId) && <ErrorNotice message={detailError} onRetry={() => void loadDetail(selectedId)} />}
          {detail && detail.id === selectedId && (
            <ProductionWorkspace
              detail={detail}
              jobs={jobs.filter((job) => job.productionId === detail.id)}
              providers={providers}
              onReload={reloadSelectedDetail}
              onReloadStatus={reloadSelectedDetailWithStatus}
              onAnnouncementDirtyChange={updateSelectedAnnouncementDirty}
            />
          )}
        </main>
      </div>
      <NewProductionDialog open={newProductionOpen} onClose={() => setNewProductionOpen(false)} onProductionReady={refreshProductionAfterMutation} canCreateProduction={canCreateProduction} />
    </div>
  );
}

function JobsStrip({
  jobs,
  productions,
  cancellingJobIds,
  onCancelJob,
  actionMessage,
}: {
  jobs: Job[];
  productions: ProductionSummary[];
  cancellingJobIds: Set<string>;
  onCancelJob: (job: Job) => Promise<void>;
  actionMessage?: string;
}) {
  return (
    <section className="jobs-strip" aria-label="実行中のジョブ">
      <span className="jobs-strip-label"><span className="pulse" aria-hidden="true" />{jobs.length > 0 ? '実行中' : 'ジョブ操作'}</span>
      <div className="jobs-list">
        {jobs.slice(0, 4).map((job) => {
          const production = productions.find((item) => item.id === job.productionId);
          const cancelling = cancellingJobIds.has(job.id);
          return (
            <div className="job-item" key={job.id}>
              <span>{production?.title ?? job.productionId ?? job.type}</span>
              <strong>{stageLabel(job.stage ?? job.type)}</strong>
              {job.progress !== undefined && (
                <div className="progress-track" aria-label={`${job.progress}%`}>
                  <span style={{ width: `${Math.max(0, Math.min(100, job.progress))}%` }} />
                </div>
              )}
              <small>{job.progress !== undefined ? `${Math.round(job.progress)}%` : STATUS_LABEL[job.status]}</small>
              <button className="button button-danger job-cancel-button" type="button" disabled={cancelling} onClick={() => void onCancelJob(job)} aria-label={`Job ${job.id} の停止を要求`}>
                {cancelling ? '停止要求中…' : '停止'}
              </button>
            </div>
          );
        })}
      </div>
      {actionMessage && <p className="jobs-action-message" role="status" aria-live="polite">{actionMessage}</p>}
    </section>
  );
}

function ProductionWorkspace({ detail, jobs, providers, onReload, onReloadStatus, onAnnouncementDirtyChange }: { detail: ProductionDetail; jobs: Job[]; providers: ProviderStatus[]; onReload: (signal?: AbortSignal) => Promise<void>; onReloadStatus: (signal?: AbortSignal) => Promise<boolean>; onAnnouncementDirtyChange: (dirty: boolean) => void }) {
  const [tab, setTab] = useState<DetailTab>('announcement');
  const [announcementDirty, setAnnouncementDirty] = useState(false);
  const latestRun = [...detail.runs].sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))[0];
  const completedArtifacts = detail.artifacts.length;
  const costSummary = [...detail.costs.reduce((totals, cost) => {
    totals.set(cost.currency, (totals.get(cost.currency) ?? 0) + cost.amount);
    return totals;
  }, new Map<string, number>()).entries()]
    .map(([currency, amount]) => formatMoney(amount, currency))
    .join(' / ') || '—';
  const activeJob = jobs.find((job) => job.status === 'running' || job.status === 'pending');

  const tabs: { id: DetailTab; label: string; count?: number }[] = [
    { id: 'announcement', label: 'かんたん作成', count: detail.announcementRecipes.length || undefined },
    { id: 'overview', label: '概要' },
    { id: 'pipeline', label: '一括生成' },
    { id: 'detailed-test', label: '詳細一括' },
    { id: 'video', label: '生成映像' },
    { id: 'capture', label: '画面収録' },
    { id: 'narration', label: 'ナレーション' },
    { id: 'timeline', label: 'カット編集' },
    { id: 'assembly', label: '編集・合成' },
    { id: 'qc', label: '品質検査' },
    { id: 'artifacts', label: '成果物', count: detail.artifacts.length },
    { id: 'compare', label: 'A/B比較' },
    { id: 'logs', label: 'ログ', count: detail.events.length },
    { id: 'audit', label: '監査・費用' },
  ];
  const changeTab = (nextTab: DetailTab) => {
    if (tab === 'announcement' && nextTab !== 'announcement' && announcementDirty) {
      if (!window.confirm('告知動画の未保存変更を破棄して、別の画面へ移動しますか？')) return;
      setAnnouncementDirty(false);
      onAnnouncementDirtyChange(false);
    }
    setTab(nextTab);
  };
  const updateAnnouncementDirty = useCallback((dirty: boolean) => {
    setAnnouncementDirty(dirty);
    onAnnouncementDirtyChange(dirty);
  }, [onAnnouncementDirtyChange]);

  return (
    <>
      <section className="workspace-header">
        <div>
          <div className="breadcrumb"><span>制作</span><span>/</span><span>{detail.id}</span></div>
          <div className="title-row">
            <h2>{detail.title}</h2>
            <StatusBadge status={activeJob?.status ?? detail.status} />
          </div>
          {detail.description && <p className="production-description">{detail.description}</p>}
          <div className="tag-row">
            {detail.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}
          </div>
          {(detail.technicalStatus || detail.creativeStatus || detail.publicReleaseStatus) && (
            <div className="gate-row" aria-label="判定ゲート">
              {detail.technicalStatus && <span><small>技術</small><StatusBadge status={detail.technicalStatus} /></span>}
              {detail.creativeStatus && <span><small>表現</small><StatusBadge status={detail.creativeStatus} /></span>}
              {detail.publicReleaseStatus && <span><small>公開</small><StatusBadge status={detail.publicReleaseStatus} /></span>}
            </div>
          )}
        </div>
        <div className="header-stats" aria-label="制作サマリー">
          <div><span>尺</span><strong>{formatDuration(detail.durationSeconds)}</strong></div>
          <div><span>Run</span><strong>{detail.runs.length}</strong></div>
          <div><span>成果物</span><strong>{completedArtifacts}</strong></div>
          <div><span>費用見積・記録</span><strong>{costSummary}</strong></div>
        </div>
      </section>

      <nav className="tabs" aria-label="制作情報" role="tablist">
        {tabs.map((item) => (
          <button key={item.id} id={`production-tab-${item.id}`} role="tab" aria-selected={tab === item.id} aria-controls="production-tabpanel" className={tab === item.id ? 'is-active' : ''} onClick={() => changeTab(item.id)}>
            {item.label}{item.count !== undefined && <span>{item.count}</span>}
          </button>
        ))}
      </nav>

      <div className="tab-content" id="production-tabpanel" role="tabpanel" aria-labelledby={`production-tab-${tab}`}>
        {tab === 'overview' && <Overview detail={detail} latestRun={latestRun} onReload={onReload} />}
        {tab === 'pipeline' && <LocalPipelinePanel detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'announcement' && <AnnouncementVideoPanel key={detail.id} detail={detail} jobs={jobs} onReload={onReload} onReloadStatus={onReloadStatus} onDirtyChange={updateAnnouncementDirty} />}
        {tab === 'detailed-test' && <DetailedTestVideoPanel key={detail.id} detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'video' && <VideoGenerationPanel detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'capture' && <CaptureTab detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'narration' && <NarrationPanel detail={detail} jobs={jobs} providers={providers} onReload={onReload} />}
        {tab === 'timeline' && <TimelinePanel detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'assembly' && <AssemblyPanel detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'qc' && <QcPanel detail={detail} jobs={jobs} onReload={onReload} />}
        {tab === 'artifacts' && <ArtifactsPanel artifacts={detail.artifacts} />}
        {tab === 'compare' && <ComparisonPanel artifacts={detail.artifacts} />}
        {tab === 'logs' && <LogPanel events={detail.events} />}
        {tab === 'audit' && <AuditPanel detail={detail} onReload={onReload} />}
      </div>
    </>
  );
}

function Overview({ detail, latestRun, onReload }: { detail: ProductionDetail; latestRun?: ProductionRun; onReload: () => Promise<void> }) {
  return (
    <div className="overview-grid">
      <div className="overview-main">
        <section className="panel">
          <div className="panel-header">
            <div><span className="section-kicker">PIPELINE PLAN</span><h3>要求工程</h3></div>
            {latestRun && <span className="muted">{latestRun.label} · {formatDate(latestRun.createdAt)}</span>}
          </div>
          {!latestRun && <EmptyState title="Runがありません" description="再実行計画を作成すると、工程がここに表示されます。" />}
          {latestRun && latestRun.stages.length === 0 && (
            <div className="run-summary-line"><StatusBadge status={latestRun.status} /><span>工程の詳細記録はありません。</span></div>
          )}
          {latestRun && latestRun.stages.length > 0 && (
            <ol className="pipeline-list">
              {latestRun.stages.map((stage, index) => (
                <li key={stage.id} className={`pipeline-step step-${stage.status}`}>
                  <div className="step-rail"><span>{index + 1}</span></div>
                  <div className="step-body">
                    <div><strong>{stageLabel(stage.name)}</strong><StatusBadge status={stage.status} /></div>
                    {stage.message && <p>{stage.message}</p>}
                    <small>{formatDate(stage.startedAt)}{stage.finishedAt ? ` → ${formatDate(stage.finishedAt)}` : ''}</small>
                    {stage.progress !== undefined && <div className="progress-track"><span style={{ width: `${stage.progress}%` }} /></div>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">RUN PLANS</span><h3>Run計画履歴</h3></div></div>
          {detail.runs.length === 0 && <EmptyState title="Run計画履歴がありません" />}
          <div className="run-table-wrap">
            {detail.runs.length > 0 && (
              <table className="data-table">
                <thead><tr><th>Run</th><th>費用承認状態</th><th>作成日時</th><th>Revision</th></tr></thead>
                <tbody>{detail.runs.map((run) => (
                  <tr key={run.id}>
                    <td><strong>{run.label}</strong><small>{run.id}</small></td>
                    <td><StatusBadge status={run.status} label={runCostApprovalLabel(run)} /></td>
                    <td>{formatDate(run.createdAt)}</td>
                    <td>{run.revision ?? '—'}</td>
                  </tr>
                ))}</tbody>
              </table>
            )}
          </div>
        </section>
      </div>
      <aside className="overview-side">
        <RerunPanel productionId={detail.id} onReload={onReload} />
        <section className="panel compact-panel">
          <div className="panel-header"><div><span className="section-kicker">LATEST ARTIFACTS</span><h3>最近の成果物</h3></div></div>
          {detail.artifacts.length === 0 && <p className="muted">成果物はまだありません。</p>}
          <div className="latest-artifacts">
            {detail.artifacts.slice(0, 5).map((artifact) => (
              <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer" className="latest-artifact">
                <span className={`artifact-kind kind-${artifact.kind}`} aria-hidden="true">{artifact.kind.slice(0, 1).toUpperCase()}</span>
                <span><strong>{artifact.name}</strong><small>{stageLabel(artifact.stage)} · {formatBytes(artifact.sizeBytes)}</small></span>
                <span aria-hidden="true">↗</span>
              </a>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

const LOCAL_PIPELINE_STEPS = [
  { key: 'video_generation', label: '生成映像' },
  { key: 'narration', label: 'ナレーション' },
  { key: 'timeline', label: 'カット編集' },
  { key: 'assembly', label: '編集・合成' },
  { key: 'qc', label: '品質検査' },
] as const;

type LocalPipelineStepKey = typeof LOCAL_PIPELINE_STEPS[number]['key'];

const isTerminalStatus = (status?: StudioStatus): boolean =>
  status === 'succeeded' || status === 'failed' || status === 'cancelled';

const pipelineJobTimestamp = (job: Job): string =>
  job.updatedAt
  ?? job.startedAt
  ?? (typeof job.raw.updated_at === 'string' ? job.raw.updated_at : undefined)
  ?? (typeof job.raw.created_at === 'string' ? job.raw.created_at : undefined)
  ?? '';

const newestPipelineJob = (jobs: Job[]): Job | undefined => [...jobs]
  .sort((left, right) => pipelineJobTimestamp(right).localeCompare(pipelineJobTimestamp(left)))[0];

const jobBelongsToPipelineRun = (job: Job, runId?: string): boolean => {
  if (!runId) return true;
  const rawRunId = typeof job.raw.run_id === 'string' ? job.raw.run_id : typeof job.raw.runId === 'string' ? job.raw.runId : undefined;
  return job.runId === runId || job.result?.runId === runId || rawRunId === runId;
};

/** Keep the pipeline summary on its true top job; child jobs only drive stage progress. */
const selectLocalPipelineDisplayJob = (localJob: Job | undefined, matchingJobs: Job[], runId?: string): Job | undefined => {
  const candidates = [localJob, ...matchingJobs]
    .filter((candidate): candidate is Job => candidate !== undefined)
    .filter((candidate) => jobBelongsToPipelineRun(candidate, runId))
    .filter((candidate, index, all) => all.findIndex((item) => item.id === candidate.id) === index);
  const topJobs = candidates.filter(isLocalPipelineTopJob);
  const active = topJobs.filter((candidate) => isLocalPipelineExecutionActive(candidate));
  return newestPipelineJob(active) ?? newestPipelineJob(topJobs);
};

const localPipelineRunIsEligible = (run: ProductionRun): boolean => run.executionProfile === 'local_pipeline';

const localPipelineStageResult = (
  key: LocalPipelineStepKey,
  run: ProductionRun | undefined,
  job: Job | undefined,
  jobs: Job[],
): LocalPipelineStageResult | undefined => {
  const result = job?.result?.jobs;
  const nested = result ? Object.values(result).find((item) => normalizeRequestedStage(item.stage) === key) : undefined;
  // The backend's compact result.jobs lineage intentionally contains IDs only;
  // prefer the richer child-job/stage-attempt status after reload in that case.
  if (nested && nested.status !== 'unknown') return nested;
  const child = jobs.find((item) => {
    const stage = normalizeRequestedStage(item.stage ?? item.type);
    return jobBelongsToPipelineRun(item, run?.id) && (stage === key || stage.endsWith(`_${key}`));
  });
  if (child) {
    return {
      stage: key,
      status: child.status,
      jobId: child.id,
      stageAttemptId: child.stageAttemptId,
      attempt: child.attempt,
      progress: child.progress,
      message: child.message,
      artifacts: child.result?.artifacts ?? [],
      raw: child.raw,
    };
  }
  const attempt = [...(run?.stageAttempts ?? [])]
    .filter((item) => normalizeRequestedStage(item.stage) === key)
    .sort((left, right) => (right.createdAt ?? '').localeCompare(left.createdAt ?? ''))[0];
  if (!attempt) return undefined;
  return {
    stage: key,
    status: attempt.status,
    jobId: attempt.jobId,
    stageAttemptId: attempt.id,
    attempt: attempt.attempt,
    progress: undefined,
    message: attempt.message,
    artifacts: attempt.artifacts,
    raw: attempt.raw,
  };
};

function LocalPipelinePanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const pipelineRuns = useMemo(
    () => [...detail.runs]
      .filter(localPipelineRunIsEligible)
      .sort((left, right) => (right.createdAt ?? '').localeCompare(left.createdAt ?? '')),
    [detail.runs],
  );
  const [prompt, setPrompt] = useState('');
  const [seed, setSeed] = useState('0');
  const [script, setScript] = useState('');
  const [voice, setVoice] = useState('');
  const [rate, setRate] = useState('0');
  const [pronunciations, setPronunciations] = useState([{ source: '', target: '' }]);
  const [includeCaptioned, setIncludeCaptioned] = useState(true);
  const [captionStylePreset, setCaptionStylePreset] = useState<LocalAssemblyCaptionStylePreset>(RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET);
  const [variant, setVariant] = useState<LocalQcVariant>('captioned');
  const [pipelineRunId, setPipelineRunId] = useState('');
  const [job, setJob] = useState<Job>();
  const [observedJobs, setObservedJobs] = useState<Job[]>([]);
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [resumingTaskId, setResumingTaskId] = useState<string>();
  const submittingRef = useRef(false);
  const resumingRef = useRef(false);
  const pollingRef = useRef(false);
  const jobRef = useRef<Job | undefined>(undefined);
  const onReloadRef = useRef(onReload);
  const reloadedTerminalRun = useRef<string | undefined>(undefined);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();

  useEffect(() => { jobRef.current = job; }, [job]);
  useEffect(() => { onReloadRef.current = onReload; }, [onReload]);
  const activePipelineRun = useMemo(() => {
    const allJobs = [...jobs, ...observedJobs];
    return pipelineRuns.find((run) => isPipelineContinuationActive(run.pipelineContinuation)
      || isLocalPipelineExecutionActiveAcross([
        ...(run.stageAttempts ?? []),
        ...allJobs.filter((item) => jobBelongsToPipelineRun(item, run.id)),
      ]));
  }, [jobs, observedJobs, pipelineRuns]);
  useEffect(() => {
    if (!pipelineRunId && (activePipelineRun || pipelineRuns[0])) setPipelineRunId((activePipelineRun ?? pipelineRuns[0]).id);
    if (pipelineRunId && !pipelineRuns.some((run) => run.id === pipelineRunId) && !job?.result?.runId && !job?.runId) {
      setPipelineRunId(activePipelineRun?.id ?? pipelineRuns[0]?.id ?? '');
    }
  }, [activePipelineRun, job, pipelineRunId, pipelineRuns]);

  const selectedRun = pipelineRuns.find((run) => run.id === pipelineRunId) ?? activePipelineRun ?? pipelineRuns[0];
  const effectiveRunId = pipelineRunId || selectedRun?.id;
  const providerTasks = useMemo(() => {
    if (!selectedRun) return [];
    const candidates = [...(selectedRun.providerTasks ?? []), ...(detail.providerTasks ?? [])]
      .filter((task) => providerTaskBelongsToVideoRun(task, detail.id, selectedRun.id));
    const unique = candidates.filter((task, index, all) => all.findIndex((item) => item.id === task.id) === index);
    return newestProviderTasks(unique);
  }, [detail.id, detail.providerTasks, selectedRun]);
  const providerTaskActive = providerTasks.some((task) => isProviderTaskActive(task));
  const providerTaskBlocking = providerTasks.some((task) => isProviderTaskBlocking(task));
  const pipelineContinuation = selectedRun?.pipelineContinuation;
  const pipelineContinuationActive = isPipelineContinuationActive(pipelineContinuation);
  const matchingJobs = useMemo(() => {
    const all = [...jobs, ...observedJobs];
    return all
      .filter((item, index, values) => values.findIndex((candidate) => candidate.id === item.id) === index)
      .filter((item) => isLocalPipelineJobForSelection(item.raw, { productionId: detail.id, runId: effectiveRunId }) || jobBelongsToPipelineRun(item, effectiveRunId));
  }, [detail.id, effectiveRunId, jobs, observedJobs]);
  const visibleJob = selectLocalPipelineDisplayJob(job, matchingJobs, effectiveRunId);
  const stageAttempts = selectedRun?.stageAttempts ?? [];
  const executionActive = isLocalPipelineExecutionActiveAcross([
    job,
    visibleJob,
    ...stageAttempts,
    ...matchingJobs,
  ]) || providerTaskActive || pipelineContinuationActive;
  const pipelineStatus = visibleJob?.status ?? selectedRun?.status;
  const formInput = useMemo(() => ({
    prompt,
    seed,
    script,
    voice,
    rate,
    pronunciations: pronunciations.some((item) => item.source.trim() || item.target.trim()) ? pronunciations : undefined,
    includeCaptioned,
    captionStylePreset,
    variant,
  }), [captionStylePreset, includeCaptioned, prompt, pronunciations, rate, script, seed, variant, voice]);
  const normalizedInput = useMemo(() => normalizeLocalPipelineInput(formInput), [formInput]);
  const validationErrors = normalizedInput.errors;
  const stageResults = useMemo(
    () => Object.fromEntries(LOCAL_PIPELINE_STEPS.map((step) => [step.key, localPipelineStageResult(step.key, selectedRun, visibleJob, matchingJobs)])) as Record<LocalPipelineStepKey, LocalPipelineStageResult | undefined>,
    [matchingJobs, selectedRun, visibleJob],
  );
  const finalArtifacts = useMemo(() => {
    const fromResult = visibleJob?.result?.artifacts ?? [];
    const fromAttempts = selectedRun?.stageAttempts.flatMap((attempt) => attempt.artifacts) ?? [];
    const all = [...fromResult, ...fromAttempts];
    return all.filter((artifact, index) => all.findIndex((candidate) => candidate.id === artifact.id) === index);
  }, [selectedRun, visibleJob]);
  const qcAttempt = [...stageAttempts]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'qc')
    .sort((left, right) => (right.createdAt ?? '').localeCompare(left.createdAt ?? ''))[0];
  const technicalVerdict = visibleJob?.result?.technicalVerdict ?? qcAttempt?.technicalVerdict;

  useEffect(() => {
    if (!effectiveRunId || (!executionActive && !providerTaskActive)) return undefined;
    let cancelled = false;
    const poll = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const nextJobs = await api.jobs();
        if (cancelled) return;
        const nextMatching = nextJobs.filter((item) => isLocalPipelineJobForSelection(item.raw, { productionId: detail.id, runId: effectiveRunId }) || jobBelongsToPipelineRun(item, effectiveRunId));
        setObservedJobs(nextMatching);
        const next = selectLocalPipelineDisplayJob(jobRef.current, nextMatching, effectiveRunId);
        if (next) {
          setJob(next);
          const nextRunId = next.result?.runId ?? next.runId;
          if (nextRunId && nextRunId !== pipelineRunId) setPipelineRunId(nextRunId);
        }
        await onReloadRef.current().catch(() => undefined);
      } catch {
        // The next two-second poll retries; the last known attempt remains visible.
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [detail.id, effectiveRunId, executionActive, pipelineRunId, providerTaskActive]);

  useEffect(() => {
    const terminal = !executionActive && isTerminalStatus(pipelineStatus);
    const key = visibleJob?.id ?? effectiveRunId;
    if (!terminal || !key || reloadedTerminalRun.current === key) return;
    reloadedTerminalRun.current = key;
    void onReloadRef.current().catch(() => undefined);
  }, [effectiveRunId, executionActive, pipelineStatus, visibleJob?.id]);

  useEffect(() => {
    if (!executionActive && isTerminalStatus(pipelineStatus) && !submitting) {
      setBusy(false);
    }
  }, [executionActive, pipelineStatus, submitting]);

  const execute = async () => {
    if (submittingRef.current || resumingRef.current || executionActive || providerTaskBlocking) return;
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    reloadedTerminalRun.current = undefined;
    setMessage({ type: 'info', text: 'local_pipelineを登録しています。既存の同一リクエストはbackendのdedupe結果を監視します。' });
    try {
      const request: LocalPipelineRequest = normalizedInput.request;
      const submitted = await api.executeLocalPipeline(detail.id, request);
      setJob(submitted);
      setObservedJobs((current) => [submitted, ...current.filter((item) => item.id !== submitted.id)]);
      const submittedRunId = submitted.result?.runId ?? submitted.runId;
      if (submittedRunId) setPipelineRunId(submittedRunId);
      const submittedVerdict = submitted.result?.technicalVerdict;
      setMessage({
        type: submitted.status === 'failed' || submittedVerdict === 'fail' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? localPipelineError(submitted.message ?? 'pipeline workerが失敗しました')
          : submittedVerdict === 'fail'
            ? 'パイプラインは完了しましたが、技術QCは不合格です。'
            : `一括生成を登録しました${submittedRunId ? `（Run ${submittedRunId}）` : ''}。5段階の進捗を監視しています。`,
      });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: '一括生成は登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (isTerminalStatus(submitted.status)) setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localPipelineError(error) });
      try {
        await onReload();
      } catch {
        // Keep the original API error visible when recovery reload also fails.
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const resumeProviderTask = async (task: ProviderTask) => {
    if (resumingRef.current || submittingRef.current || !isProviderTaskResumeAvailable(task)) return;
    resumingRef.current = true;
    setResumingTaskId(task.id);
    setBusy(true);
    setMessage({
      type: 'info',
      text: task.status === 'cancel_requested'
        ? 'キャンセル要求済みtaskの状態を再照合しています。生成promptの再送信は行いません。'
        : '一括生成内の同じprovider taskを照合・再開しています。重複送信は行いません。',
    });
    try {
      const resumed = await api.resumeProviderTask(task.id);
      setObservedJobs((current) => [resumed, ...current.filter((item) => item.id !== resumed.id)]);
      await onReload().catch(() => undefined);
      const resumeFailed = resumed.status === 'failed' || resumed.status === 'cancelled';
      setMessage({
        type: resumeFailed ? 'error' : 'success',
        text: resumeFailed
          ? localComfyUiError(resumed.message ?? (resumed.status === 'cancelled' ? 'provider taskの再照合は中断されました' : 'provider taskの再開に失敗しました'))
          : task.status === 'cancel_requested'
            ? 'キャンセル状態の再照合を登録しました。providerが終了するまで同じtask IDだけを確認します。'
            : '動画生成taskの再開を登録しました。provider完了後は、同じRunの一括生成がキャッシュを検証して後続工程を自動継続します。',
      });
      if (isTerminalStatus(resumed.status)) setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localComfyUiError(error) });
      await onReload().catch(() => undefined);
    } finally {
      resumingRef.current = false;
      setResumingTaskId(undefined);
    }
  };

  const updatePronunciation = (index: number, key: 'source' | 'target', value: string) => {
    setPronunciations((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };
  const addPronunciation = () => setPronunciations((current) => [...current, { source: '', target: '' }]);
  const removePronunciation = (index: number) => setPronunciations((current) => current.length === 1 ? current : current.filter((_, itemIndex) => itemIndex !== index));
  const formDisabled = submitting || busy || executionActive || providerTaskBlocking || resumingTaskId !== undefined;

  return (
    <div className="local-pipeline-grid">
      <div>
        <section className="panel local-pipeline-panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL PIPELINE</span><h3>一括生成</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">生成映像・ナレーション・カット編集・合成・技術QCを、1つのlocal_pipeline Runで順番に実行します。</p>
          <div className="local-pipeline-policy" role="note"><strong>ローカル専用の固定構成</strong><p>動画ソースはMiniMax H3の約5.17秒です。workflow presetは固定で、モデルパスやendpointは入力できません。外部有料APIは使用しません。</p></div>
          <label className="field"><span>生成プロンプト</span><textarea rows={7} value={prompt} disabled={formDisabled} onChange={(event) => setPrompt(event.target.value)} placeholder="例：正面を向いた日本人女性が、柔らかな自然光のスタジオで静かに微笑む。フォトリアル、縦長構図。" aria-label="一括生成プロンプト" /></label>
          <label className="field"><span>seed（0〜2^63−1の整数）</span><input type="text" inputMode="numeric" pattern="[0-9]*" value={seed} disabled={formDisabled} onChange={(event) => setSeed(event.target.value)} aria-label="一括生成seed" /></label>
          <label className="field"><span>ナレーション台本（1行＝1セグメント）</span><textarea rows={6} value={script} disabled={formDisabled} onChange={(event) => setScript(event.target.value)} placeholder="例：この動画では、生成AIの使い方を紹介します。" aria-label="一括生成ナレーション台本" /></label>
          <div className="local-pipeline-form-row">
            <label className="field"><span>音声（任意）</span><input value={voice} disabled={formDisabled} onChange={(event) => setVoice(event.target.value)} placeholder="既定音声" aria-label="一括生成音声" /></label>
            <label className="field"><span>読み上げ速度</span><input type="number" min={-10} max={10} step={1} value={rate} disabled={formDisabled} onChange={(event) => setRate(event.target.value)} aria-label="一括生成読み上げ速度" /></label>
          </div>
          <fieldset className="pronunciation-fieldset"><legend>発音置換（任意）</legend>{pronunciations.map((item, index) => <div className="pronunciation-row" key={index}><input value={item.source} disabled={formDisabled} onChange={(event) => updatePronunciation(index, 'source', event.target.value)} placeholder="表記" aria-label={`一括生成発音置換 ${index + 1} 表記`} /><span aria-hidden="true">→</span><input value={item.target} disabled={formDisabled} onChange={(event) => updatePronunciation(index, 'target', event.target.value)} placeholder="読み" aria-label={`一括生成発音置換 ${index + 1} 読み`} /><button className="button button-ghost" type="button" onClick={() => removePronunciation(index)} disabled={formDisabled || pronunciations.length === 1}>削除</button></div>)}<button className="button button-secondary" type="button" onClick={addPronunciation} disabled={formDisabled}>＋置換を追加</button></fieldset>
          <label className="toggle-field"><input type="checkbox" checked={includeCaptioned} disabled={formDisabled} onChange={(event) => { const next = event.target.checked; setIncludeCaptioned(next); setVariant(next ? 'captioned' : 'clean'); setCaptionStylePreset(next ? RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET : 'studio_default_v1'); }} /><span><strong>字幕付きmasterを生成</strong><small>オンの場合、字幕付き版をQC対象にします。</small></span></label>
          <label className="field"><span>字幕プリセット</span><select value={captionStylePreset} disabled={formDisabled || !includeCaptioned} onChange={(event) => { const next = event.target.value; if (next === 'studio_default_v1' || next === 'shorts_ja_large_v1') setCaptionStylePreset(next); }} aria-label="一括生成字幕プリセット"><option value="shorts_ja_large_v1">Shorts向け大字幕（推奨）</option><option value="studio_default_v1">標準字幕</option></select></label>
          <label className="field"><span>QC対象variant</span><select value={variant} disabled={formDisabled || !includeCaptioned} onChange={(event) => { const next = event.target.value; if (next === 'clean' || next === 'captioned') setVariant(next); }} aria-label="一括生成QC対象variant"><option value="captioned">captioned（字幕付き）</option><option value="clean">clean（字幕なし）</option></select></label>
          <div className="local-pipeline-summary"><span>Workflow</span><strong className="mono">{LOCAL_COMFYUI_WORKFLOW_PRESET}</strong><span>既存Run</span><strong className="mono">{effectiveRunId ?? '新規作成（dedupe対応）'}</strong></div>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={formDisabled || validationErrors.length > 0}>{submitting ? '登録中…' : providerTaskBlocking ? 'provider task確認中…' : executionActive || busy ? '一括生成を監視中…' : '一括生成を実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <ProviderTaskRecoveryCard tasks={providerTasks} resumingTaskId={resumingTaskId} onResume={(task) => void resumeProviderTask(task)} continuesPipeline />
        <section className="panel compact-panel local-pipeline-progress-panel" aria-live="polite" aria-busy={executionActive}>
          <div className="panel-header"><div><span className="section-kicker">PIPELINE PROGRESS</span><h3>5段階の進捗</h3></div>{pipelineStatus ? <StatusBadge status={pipelineStatus} label={executionActive ? '監視中' : jobStatusLabel(pipelineStatus)} /> : <span className="muted">未実行</span>}</div>
          {pipelineContinuation && <div className="local-pipeline-policy" role="status" aria-live="polite">
            <strong>Pipeline継続：{pipelineContinuationStateLabel(pipelineContinuation.state)}</strong>
            <p>{pipelineContinuationDescription(pipelineContinuation.state)}</p>
            <dl className="narration-metrics">
              <div><dt>継続Job</dt><dd className="mono">{pipelineContinuation.jobId ?? '—'}</dd></div>
              <div><dt>復旧元Job</dt><dd className="mono">{pipelineContinuation.sourceJobId ?? '—'}</dd></div>
              <div><dt>再開回数</dt><dd>{pipelineContinuation.resumeCount ?? 0}</dd></div>
              <div><dt>更新</dt><dd>{formatDate(pipelineContinuation.updatedAt)}</dd></div>
            </dl>
            {pipelineContinuation.error && <p className="provider-task-error">{pipelineContinuation.error.message ?? pipelineContinuation.error.code ?? 'pipeline継続に失敗しました'}{pipelineContinuation.error.code ? ` · ${pipelineContinuation.error.code}` : ''}</p>}
          </div>}
          <ol className="local-pipeline-progress">{LOCAL_PIPELINE_STEPS.map((step, index) => {
            const item = stageResults[step.key];
            const status = item?.status ?? (pipelineStatus ? 'pending' : 'unknown');
            return <li className={`local-pipeline-step step-${status}`} key={step.key}><div className="local-pipeline-step-rail"><span>{index + 1}</span></div><div className="local-pipeline-step-body"><div><strong>{step.label}</strong><StatusBadge status={status} label={item ? jobStatusLabel(status) : '未開始'} /></div>{item?.progress !== undefined && <div className="progress-track" aria-label={`${item.progress}%`}><span style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }} /></div>}<small>{item?.jobId ? `Job ${item.jobId}` : item?.stageAttemptId ? `Attempt ${item.stageAttemptId}` : 'backendのstage記録を待機中'}</small>{item?.message && <p>{item.message}</p>}</div></li>;
          })}</ol>
          <dl className="narration-metrics"><div><dt>Run</dt><dd className="mono">{visibleJob?.result?.runId ?? visibleJob?.runId ?? effectiveRunId ?? '—'}</dd></div><div><dt>Revision</dt><dd className="mono">{visibleJob?.result?.revisionId ?? '—'}</dd></div><div><dt>更新</dt><dd>{formatDate(visibleJob?.updatedAt ?? selectedRun?.finishedAt ?? selectedRun?.startedAt)}</dd></div></dl>
          {executionActive && <p className="gate-separation-note">監視中です。再読込後も同じRunとchild jobを照合して重複送信を防ぎます。</p>}
          {!executionActive && providerTasks.some((task) => task.status === 'succeeded') && !pipelineContinuation && <p className="gate-separation-note">動画生成taskの復旧後は、同じRunのpipelineがcacheを検証して後続工程を自動継続します。</p>}
        </section>
        <section className="panel compact-panel local-pipeline-result-panel"><div className="panel-header"><div><span className="section-kicker">FINAL RESULT</span><h3>最終成果物・QC</h3></div>{technicalVerdict ? <StatusBadge status={technicalVerdict === 'pass' ? 'succeeded' : 'failed'} label={`technical verdict: ${technicalVerdict}`} /> : <span className="muted">判定待ち</span>}</div>{technicalVerdict === 'fail' && <div className="notice notice-warning"><div><strong>技術QCは不合格です</strong><p>ジョブ完了と技術検査合格は別判定です。成果物を確認してから再試行してください。</p></div></div>}{finalArtifacts.length === 0 ? <p className="muted">master artifactはまだありません。</p> : <div className="narration-artifact-list">{finalArtifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer"><strong>{artifact.name}</strong><span>{artifact.kind} · {formatBytes(artifact.sizeBytes)} ↗</span></a>)}</div>}<p className="gate-separation-note">ここで表示するのは実行・技術結果です。表現、権利、公開可否は別途確認してください。</p></section>
      </aside>
    </div>
  );
}

const hasVideoGenerationStage = (run: ProductionRun): boolean =>
  run.requestedStages.some((stage) => ['video', 'video_generation'].includes(normalizeRequestedStage(stage)))
  || run.stages.some((stage) => ['video', 'video_generation'].includes(normalizeRequestedStage(stage.name)));

const localComfyUiJobMatchesAttempt = (job: Job, attempt?: StageAttempt): boolean => Boolean(
  attempt
  && (job.id === attempt.jobId || job.stageAttemptId === attempt.id),
);

const localComfyUiJobTimestamp = (job: Job): string =>
  job.updatedAt
  ?? job.startedAt
  ?? (typeof job.raw.updated_at === 'string' ? job.raw.updated_at : undefined)
  ?? (typeof job.raw.created_at === 'string' ? job.raw.created_at : undefined)
  ?? '';

const newestLocalComfyUiJob = (jobs: Job[]): Job | undefined => [...jobs]
  .sort((left, right) => localComfyUiJobTimestamp(right).localeCompare(localComfyUiJobTimestamp(left)))[0];

/**
 * Select a job only after considering the latest stage attempt. A locally
 * submitted terminal job is intentionally ignored while that same Run has a
 * newer active attempt or matching active job.
 */
const selectLocalComfyUiDisplayJob = (
  localJob: Job | undefined,
  currentAttempt: StageAttempt | undefined,
  matchingJobs: Job[],
  runId?: string,
): Job | undefined => {
  const localJobMatchesRun = Boolean(
    localJob
    && ((runId && localJob.runId === runId) || localComfyUiJobMatchesAttempt(localJob, currentAttempt)),
  );
  const candidates = [
    ...(localJobMatchesRun && localJob ? [localJob] : []),
    ...matchingJobs,
  ].filter((candidate, index, all) => all.findIndex((item) => item.id === candidate.id) === index);
  const linkedJobs = candidates.filter((candidate) => localComfyUiJobMatchesAttempt(candidate, currentAttempt));
  const activeJobs = candidates.filter((candidate) => isLocalComfyUiExecutionActive(candidate));
  if (currentAttempt && isLocalComfyUiExecutionActive(currentAttempt)) {
    return newestLocalComfyUiJob(linkedJobs.filter((candidate) => isLocalComfyUiExecutionActive(candidate)))
      ?? newestLocalComfyUiJob(activeJobs);
  }
  return newestLocalComfyUiJob(linkedJobs)
    ?? newestLocalComfyUiJob(activeJobs)
    ?? newestLocalComfyUiJob(candidates);
};

const providerTaskBelongsToVideoRun = (task: ProviderTask, productionId: string, runId: string): boolean => {
  const stage = task.stage ? normalizeRequestedStage(task.stage) : '';
  return task.provider.toLowerCase() === 'comfyui'
    && (!task.productionId || task.productionId === productionId)
    && (!task.runId || task.runId === runId)
    && (!stage || stage === 'video_generation' || stage === 'video');
};

function ProviderTaskRecoveryCard({
  tasks,
  resumingTaskId,
  onResume,
  continuesPipeline = false,
}: {
  tasks: ProviderTask[];
  resumingTaskId?: string;
  onResume: (task: ProviderTask) => void;
  continuesPipeline?: boolean;
}) {
  if (tasks.length === 0) return null;
  return (
    <section className="panel compact-panel provider-task-recovery-card">
      <p className="sr-only" aria-live="polite">
        {tasks.map((task) => `${task.id}:${providerTaskStatusLabel(task.status)}`).join('、')}
      </p>
      <div className="panel-header">
        <div><span className="section-kicker">PROVIDER RECOVERY</span><h3>Provider task復旧</h3></div>
        <span className="count-chip">{tasks.length}</span>
      </div>
      <p className="panel-lead">再起動後もprovider taskの重複送信を防ぎ、永続化済みのtaskを同じRunで安全に照合・再開します。{continuesPipeline ? 'provider完了後はpipelineの後続工程を自動継続します。' : ''}prompt本文は表示しません。</p>
      <div className="provider-task-recovery-list">
        {tasks.map((task) => {
          const resumeAvailable = isProviderTaskResumeAvailable(task);
          const blocking = isProviderTaskBlocking(task);
          return (
            <article className={`provider-task-recovery-row is-${task.status}`} key={task.id}>
              <div className="provider-task-recovery-heading">
                <div>
                  <strong>{providerTaskStatusLabel(task.status)}</strong>
                  <small className="mono">{task.id}</small>
                </div>
                <span className={`provider-task-badge is-${task.status}`}>
                  <span className="status-dot" aria-hidden="true" />
                  {providerTaskStatusLabel(task.status)}
                </span>
              </div>
              <dl className="provider-task-recovery-metrics">
                <div><dt>Provider task ID</dt><dd className="mono">{task.providerTaskId ?? '未確定'}</dd></div>
                <div><dt>試行</dt><dd>{task.attemptSequence ?? '—'}</dd></div>
                <div><dt>復旧回数</dt><dd>{task.recoveryCount ?? 0}</dd></div>
                <div><dt>作成</dt><dd>{task.createdAt ? formatDate(task.createdAt) : '—'}</dd></div>
                <div><dt>状態更新</dt><dd>{task.updatedAt ? formatDate(task.updatedAt) : '—'}</dd></div>
                <div><dt>Provider最終照合</dt><dd>{task.checkedAt ? formatDate(task.checkedAt) : '未照合'}</dd></div>
              </dl>
              {task.error && <p className="provider-task-error">{task.error.message ?? task.error.code ?? 'provider taskの確認に失敗しました'}{task.error.code ? ` · ${task.error.code}` : ''}</p>}
              {providerTaskNextActionLabel(task.nextAction) && <p className="provider-task-next-action">{providerTaskNextActionLabel(task.nextAction)}</p>}
              <div className="provider-task-recovery-footer">
                <span>{task.duplicateSubmissionBlocked ? '重複送信をブロック中' : blocking ? '実行状態を保持中' : '通常操作可能'}</span>
                {resumeAvailable && <button className="button button-secondary" type="button" onClick={() => onResume(task)} disabled={resumingTaskId !== undefined}>
                  {resumingTaskId === task.id
                    ? task.status === 'cancel_requested' ? '再照合中…' : '再開中…'
                    : task.status === 'cancel_requested' ? 'キャンセル状態を再照合' : '同じtaskを再開'}
                </button>}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

const WINDOWS_CAPTURE_REASON_LABELS: Record<string, string> = {
  unsupported_platform: 'Windows環境ではありません',
  native_helper_not_built: 'ネイティブhelperが未ビルドです',
  dotnet_unavailable: '.NETランタイムが見つかりません',
  helper_doctor_failed: 'WASAPI doctorが完了しませんでした',
  helper_contract_invalid: 'helperの診断結果を検証できませんでした',
  ffmpeg_unavailable: 'FFmpegが見つかりません',
  gdigrab_unavailable: 'FFmpegのWindows画面入力が利用できません',
  wasapi_loopback_unavailable: '既定再生音声のloopbackが利用できません',
};

const WINDOWS_CAPTURE_ARTIFACT_NAMES = [
  'screen-capture.mp4',
  'screen-video.mp4',
  'system-audio.wav',
  'first-frame.png',
  'last-frame.png',
  'capture-report.json',
  'ffprobe.json',
  'manifest.json',
] as const;

function WindowsCaptureCapabilityCard({
  capability,
  checking,
  error,
  onInspect,
}: {
  capability?: WindowsCaptureCapability;
  checking: boolean;
  error?: string;
  onInspect: () => void;
}) {
  const ready = capability?.status === 'ready';
  return (
    <section className="panel compact-panel" aria-live="polite" aria-busy={checking}>
      <div className="panel-header">
        <div><span className="section-kicker">WINDOWS NATIVE CAPABILITY</span><h3>Windows画面・システム音声</h3></div>
        {capability
          ? <StatusBadge status={ready ? 'approved' : 'blocked'} label={ready ? '収録可能' : '利用不可'} />
          : <span className="muted">未確認</span>}
      </div>
      <p className="panel-lead">診断は収録せず、固定helper・FFmpeg・既定再生音声・プライマリ画面の事前条件だけを確認します。</p>
      <button className="button button-secondary" type="button" disabled={checking} onClick={onInspect}>{checking ? '環境確認中…' : '収録せずに環境を確認'}</button>
      {capability && <>
        <dl className="narration-metrics">
          <div><dt>Capability</dt><dd>{capability.status}</dd></div>
          <div><dt>プライマリ画面</dt><dd>{capability.display.width !== null && capability.display.height !== null ? `${capability.display.width}×${capability.display.height}` : '利用不可'}</dd></div>
          <div><dt>画面入力</dt><dd>{capability.screenCaptureReady ? '利用可能' : '利用不可'}</dd></div>
          <div><dt>既定再生音声</dt><dd>{capability.systemAudioLoopbackReady ? 'loopback利用可能' : '利用不可'}</dd></div>
          <div><dt>capture command</dt><dd>{capability.helper.captureCommandAvailable ? '利用可能' : '利用不可'}</dd></div>
          <div><dt>FFprobe</dt><dd>{capability.ffmpeg.ffprobeAvailable ? '利用可能' : '利用不可'}</dd></div>
          <div><dt>実収録</dt><dd>{capability.captureExecutionEnabled ? '有効' : '無効'}</dd></div>
          <div><dt>今回の取得</dt><dd>{capability.actualCapturePerformed ? 'あり' : 'なし'}</dd></div>
        </dl>
        {capability.reasons.length > 0 && <div className="validation-list" role="status">{capability.reasons.map((reason) => <div key={reason}>・{WINDOWS_CAPTURE_REASON_LABELS[reason] ?? reason}</div>)}</div>}
        <p className="gate-separation-note">実収録はこの診断と分離した明示操作です。対象はプライマリ画面、音声は既定render loopback、カーソルは非表示に固定し、マイク・任意device・任意path・任意FFmpeg引数は受け付けません。</p>
      </>}
      {error && <div className="inline-message is-error" role="status">{error}</div>}
    </section>
  );
}

function CaptureTab({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  return (
    <div className="narration-stack">
      <WindowsCapturePanel detail={detail} jobs={jobs} onReload={onReload} />
      <ScreenCapturePanel detail={detail} jobs={jobs} onReload={onReload} />
    </div>
  );
}

function WindowsCapturePanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => isWindowsCaptureRun(run))
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [durationSeconds, setDurationSeconds] = useState(5);
  const [confirmCapture, setConfirmCapture] = useState(false);
  const [confirmSystemAudio, setConfirmSystemAudio] = useState(false);
  const [capability, setCapability] = useState<WindowsCaptureCapability>();
  const [checkingCapability, setCheckingCapability] = useState(false);
  const [capabilityError, setCapabilityError] = useState<string>();
  const [job, setJob] = useState<Job>();
  const [submitting, setSubmitting] = useState(false);
  const [submissionUncertain, setSubmissionUncertain] = useState(false);
  const [submissionReviewRequired, setSubmissionReviewRequired] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const submittingRef = useRef(false);
  const pollingRef = useRef(false);
  const submissionGuardRef = useRef<WindowsCaptureSubmissionGuard | undefined>(undefined);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setJob(undefined);
      setSubmissionUncertain(false);
      setSubmissionReviewRequired(false);
      submissionGuardRef.current = undefined;
    }
  }, [eligibleRuns, selectedRunId]);

  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const attempts = [...(selectedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'screen_capture')
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''));
  const currentAttempt = attempts[0];
  const matchingJobs = selectedRun
    ? jobs.filter((candidate) => isWindowsCaptureJobForSelection(candidate, { runId: selectedRun.id }))
    : [];
  const visibleJob = submitting || submissionUncertain || submissionReviewRequired
    ? (submissionUncertain ? job : undefined)
    : selectWindowsCaptureJob(job, currentAttempt, matchingJobs, selectedRun?.id);
  const status = visibleJob?.status ?? (submitting || submissionUncertain || submissionReviewRequired ? undefined : currentAttempt?.status);
  const active = status === 'pending' || status === 'running';
  const nativeRequest = useMemo<WindowsCaptureRequest>(() => ({
    durationMs: durationSeconds * 1_000,
    confirmCapture,
    confirmSystemAudio,
  }), [confirmCapture, confirmSystemAudio, durationSeconds]);
  const requestError = useMemo(() => {
    try {
      buildWindowsCapturePayload(nativeRequest);
      return undefined;
    } catch (error) {
      return error instanceof Error ? error.message : '収録条件を確認してください。';
    }
  }, [nativeRequest]);
  const locked = submitting || active || submissionUncertain || cancelling;
  const canExecute = canStartWindowsCapture(
    selectedRun?.executionProfile,
    capability,
    confirmCapture,
    confirmSystemAudio,
    locked || Boolean(requestError),
  );

  const inspect = async () => {
    if (checkingCapability) return;
    setCheckingCapability(true);
    setCapabilityError(undefined);
    try {
      setCapability(await api.inspectWindowsCaptureCapability());
    } catch (inspectionError) {
      setCapability(undefined);
      setCapabilityError(inspectionError instanceof Error ? inspectionError.message : 'Windows収録環境を確認できませんでした。');
    } finally {
      setCheckingCapability(false);
    }
  };

  useEffect(() => {
    if (!selectedRun || submitting || (!active && !submissionUncertain)) return;
    let cancelled = false;
    const requireManualReview = () => {
      submissionGuardRef.current = undefined;
      setSubmissionUncertain(false);
      setSubmissionReviewRequired(true);
      setJob(undefined);
      // A future recording requires a new, explicit pair of confirmations.
      setConfirmCapture(false);
      setConfirmSystemAudio(false);
      setMessage({
        type: 'error',
        text: '受理状態は未確定です。自動照合と自動再送を停止しました。収録履歴を手動確認し、必要なら確認項目を再選択して開始してください。',
      });
    };
    const guardedIntentId = submissionUncertain ? submissionGuardRef.current?.consentIntentId : undefined;
    const deadlineTimer = guardedIntentId && submissionGuardRef.current
      ? window.setTimeout(() => {
        const guard = submissionGuardRef.current;
        if (!cancelled && guard?.consentIntentId === guardedIntentId) requireManualReview();
      }, Math.max(0, submissionGuardRef.current.reconcileDeadlineMs - Date.now()))
      : undefined;
    const poll = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const nextJobs = await api.jobs();
        if (cancelled) return;
        const scopedJobs = nextJobs.filter((candidate) => isWindowsCaptureJobForSelection(candidate, { runId: selectedRun.id }));
        const guard = submissionGuardRef.current;
        const reconciliation = submissionUncertain && guard?.runId === selectedRun.id
          ? reconcileWindowsCaptureSubmission(guard, scopedJobs)
          : undefined;
        const reconciled = reconciliation?.state === 'matched' ? reconciliation.job : undefined;
        if (reconciliation?.state === 'pending') submissionGuardRef.current = reconciliation.guard;
        if (reconciliation?.state === 'manual_review') {
          requireManualReview();
          return;
        }
        const next = reconciled
          ?? (submissionUncertain ? undefined : visibleJob?.id
            ? nextJobs.find((candidate) => candidate.id === visibleJob.id)
            : selectWindowsCaptureJob(undefined, currentAttempt, scopedJobs, selectedRun.id));
        if (next) setJob(next);
        if (reconciled) {
          submissionGuardRef.current = undefined;
          setSubmissionUncertain(false);
          setMessage({ type: 'info', text: '応答を受信できませんでしたが、受理済みJobを照合しました。再送は行いません。' });
        }
        if (next && ['succeeded', 'failed', 'cancelled'].includes(next.status)) {
          await onReload().catch(() => undefined);
        }
      } catch {
        const guard = submissionGuardRef.current;
        if (
          submissionUncertain
          && guard?.runId === selectedRun.id
          && (Date.now() >= guard.reconcileDeadlineMs)
        ) {
          requireManualReview();
        }
        // Otherwise the next bounded poll retries; the last known job remains visible.
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, WINDOWS_CAPTURE_RECONCILIATION_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      if (deadlineTimer !== undefined) window.clearTimeout(deadlineTimer);
    };
  }, [active, currentAttempt, onReload, selectedRun, submissionUncertain, submitting, visibleJob?.id]);

  const execute = async () => {
    if (submittingRef.current || active || !selectedRun) return;
    if (!canExecute) {
      setMessage({ type: 'error', text: requestError ?? '環境確認と2つの明示確認を完了してから収録を開始してください。' });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setSubmissionUncertain(false);
    setSubmissionReviewRequired(false);
    submissionGuardRef.current = undefined;
    setJob(undefined);
    setMessage({ type: 'info', text: 'Windowsネイティブ収録をcapture laneへ登録しています。' });
    let consentToken: string | undefined;
    let consentIssued = false;
    try {
      const consentIntent = await api.issueWindowsCaptureConsent(selectedRun.id, nativeRequest);
      consentToken = consentIntent.consent_token;
      submissionGuardRef.current = createWindowsCaptureSubmissionGuard(consentIntent);
      consentIssued = true;
      let submitted: Job;
      try {
        submitted = await api.executeWindowsCapture(selectedRun.id, nativeRequest, consentToken!);
      } catch (error) {
        if (!isStudioApiResponseLoss(error)) throw error;
        // The backend returns the original Job for this exact token. Retry it
        // once, without issuing a second intent or generating a new token.
        submitted = await api.executeWindowsCapture(selectedRun.id, nativeRequest, consentToken!);
      }
      const guard = submissionGuardRef.current;
      if (!guard || !isWindowsCaptureJobForSelection(submitted, {
        runId: guard.runId,
        consentIntentId: guard.consentIntentId,
      })) {
        throw new Error('Windows収録Jobのconsent intent lineageを検証できませんでした。');
      }
      submissionGuardRef.current = undefined;
      setSubmissionUncertain(false);
      setJob(submitted);
      setMessage({
        type: submitted.status === 'failed' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? localWindowsCaptureError(submitted.message ?? 'workerが失敗しました')
          : 'Windowsネイティブ画面・システム音声収録をキューに登録しました。',
      });
      void onReload().catch(() => undefined);
    } catch (error) {
      if (!consentIssued) {
        submissionGuardRef.current = undefined;
        setSubmissionUncertain(false);
        setMessage({ type: 'error', text: `${localWindowsCaptureError(error)} 収録は開始していません。もう一度明示クリックしてください。` });
        return;
      }
      if (error instanceof StudioApiError && error.status >= 400 && error.status < 500) {
        submissionGuardRef.current = undefined;
        setSubmissionUncertain(false);
        setMessage({ type: 'error', text: localWindowsCaptureError(error) });
        return;
      }
      setSubmissionUncertain(true);
      setMessage({ type: 'error', text: `${localWindowsCaptureError(error)} 受理状態を確認中のため、二重実行防止で再送を停止しています。` });
    } finally {
      // The bearer token is intentionally never put in React state, refs,
      // storage, DOM, logs, or Job/raw data. Drop this local reference after
      // the execute attempt and any single response-loss retry settle.
      consentToken = undefined;
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const cancel = async () => {
    if (!visibleJob?.id || !active || cancelling) return;
    setCancelling(true);
    setMessage({ type: 'info', text: 'Windows収録の停止を要求しています。' });
    try {
      const response = await api.cancelWindowsCapture(visibleJob.id);
      if (response.job) setJob(response.job);
      await onReload().catch(() => undefined);
      setMessage({ type: 'info', text: response.cancelRequested ? '停止要求を受理しました。workerの終了を確認しています。' : '収録はすでに終了しています。状態を更新しました。' });
    } catch (error) {
      setMessage({ type: 'error', text: localWindowsCaptureError(error) });
    } finally {
      setCancelling(false);
    }
  };

  const artifacts = visibleJob?.result?.artifacts ?? (submitting || submissionUncertain || submissionReviewRequired ? [] : currentAttempt?.artifacts ?? []);
  const preview = artifacts.find((artifact) => artifact.name === 'screen-capture.mp4');
  const progressPercent = visibleJob?.progress === undefined
    ? undefined
    : Math.max(0, Math.min(100, visibleJob.progress));
  const display = capability?.display;
  const showExpectedArtifacts = status === 'succeeded';
  const captureResult = visibleJob?.result;
  const structuralTimingLabel = captureResult?.structuralTimingVerified === true
    ? '検証済み（container timestamp / duration / WASAPI packet clock）'
    : '未確認';
  const contentSyncLabel = captureResult?.contentSyncVerified === true
    ? '実内容で検証済み'
    : captureResult?.liveValidationRequired === true
      ? '実機では未検証（目視・試聴が必要）'
      : '未確認';
  const publicReleaseLabel = captureResult?.publicReleaseReady === true
    ? '利用可'
    : captureResult?.publicReleaseGate === 'blocked_pending_live_av_sync_validation'
      ? '保留（実機A/V同期確認待ち）'
      : '未判定';
  const renderedArtifacts = showExpectedArtifacts
    ? WINDOWS_CAPTURE_ARTIFACT_NAMES.map((name) => artifacts.find((artifact) => artifact.name === name || artifactFileName(artifact) === name))
    : artifacts;
  const availableArtifacts = renderedArtifacts.filter((artifact): artifact is Artifact => Boolean(artifact));

  return (
    <div className="narration-stack">
      <WindowsCaptureCapabilityCard capability={capability} checking={checkingCapability} error={capabilityError} onInspect={() => void inspect()} />
      <div className="timeline-grid">
        <div>
          <section className="panel">
            <div className="panel-header"><div><span className="section-kicker">LOCAL WINDOWS CAPTURE</span><h3>Windows実画面収録</h3></div><span className="tag">費用 0円</span></div>
            <p className="panel-lead">プライマリ画面を固定形式で収録し、既定render loopbackのsystem audioを同時に保存します。対象画面・音声経路・カーソル設定は変更できません。</p>
            <label className="field"><span>対象Run</span><select value={selectedRunId} disabled={locked} onChange={(event) => { setSelectedRunId(event.target.value); setJob(undefined); setSubmissionUncertain(false); setSubmissionReviewRequired(false); submissionGuardRef.current = undefined; setMessage(undefined); }} aria-label="Windows収録対象Run">
              {eligibleRuns.length === 0 ? <option value="">local_windows_capture Runなし</option> : eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id} · {run.executionProfile}</option>)}
            </select></label>
            <dl className="narration-metrics">
              <div><dt>画面</dt><dd>primary display{display?.width && display?.height ? ` · ${display.width}×${display.height}` : ''}</dd></div>
              <div><dt>音声</dt><dd>default render loopback</dd></div>
              <div><dt>カーソル</dt><dd>hidden</dd></div>
            </dl>
            <label className="field"><span>録画時間（秒）</span><input type="number" min={WINDOWS_CAPTURE_LIMITS.minDurationMs / 1_000} max={WINDOWS_CAPTURE_LIMITS.maxDurationMs / 1_000} step={1} value={durationSeconds} disabled={locked} onChange={(event) => setDurationSeconds(Number(event.target.value))} aria-label="Windows収録時間" /><small>1〜30秒</small></label>
            <fieldset className="stage-checks">
              <legend>収録前の明示確認</legend>
              <label><input type="checkbox" checked={confirmCapture} disabled={locked} onChange={(event) => setConfirmCapture(event.target.checked)} aria-label="画面収録を確認" /><span>プライマリ画面を取得・保存することを確認します</span></label>
              <label><input type="checkbox" checked={confirmSystemAudio} disabled={locked} onChange={(event) => setConfirmSystemAudio(event.target.checked)} aria-label="システム音声収録を確認" /><span>既定再生音声（system audio）を取得・保存することを確認します</span></label>
            </fieldset>
            {requestError && <div className="validation-list" role="status">・{requestError}</div>}
            <div className="button-row">
              <button className="button button-primary" type="button" disabled={!canExecute} onClick={() => void execute()}>{submitting ? '登録中…' : submissionUncertain ? '受理状態を照合中…' : active ? '収録を監視中…' : submissionReviewRequired ? '手動確認後にWindows収録を開始' : 'Windows収録を開始'}</button>
              {active && <button className="button button-secondary" type="button" disabled={cancelling} onClick={() => void cancel()}>{cancelling ? '停止要求中…' : '収録をキャンセル'}</button>}
            </div>
            {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
          </section>
          {preview && <section className="panel"><div className="panel-header"><div><span className="section-kicker">STRUCTURALLY VERIFIED OUTPUT</span><h3>収録プレビュー（実内容A/V同期は未検証）</h3></div></div><ArtifactPreview artifact={preview} /></section>}
        </div>
        <aside>
          <section className="panel compact-panel timeline-status-panel" aria-live="polite" aria-busy={active || submissionUncertain}>
            <div className="panel-header"><div><span className="section-kicker">NATIVE CAPTURE STATUS</span><h3>Windows収録実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>
            <dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{visibleJob?.id ?? (submitting || submissionUncertain || submissionReviewRequired ? '—' : currentAttempt?.jobId ?? '—')}</dd></div><div><dt>Stage attempt</dt><dd className="mono">{visibleJob?.stageAttemptId ?? (submitting || submissionUncertain || submissionReviewRequired ? '—' : currentAttempt?.id ?? '—')}</dd></div><div><dt>進捗</dt><dd>{progressPercent === undefined ? (active || submissionUncertain ? '計測中' : '—') : `${Math.round(progressPercent)}%`}</dd></div><div><dt>工程</dt><dd>{screenCaptureProgressPhaseLabel(visibleJob?.progressPhase)}</dd></div><div><dt>出力</dt><dd>1920×1080 / 24fps</dd></div><div><dt>音声</dt><dd>48kHz stereo loopback</dd></div><div><dt>構造タイミング</dt><dd>{structuralTimingLabel}</dd></div><div><dt>実内容A/V同期</dt><dd>{contentSyncLabel}</dd></div><div><dt>公開利用</dt><dd>{publicReleaseLabel}</dd></div><div><dt>artifact</dt><dd>{showExpectedArtifacts ? WINDOWS_CAPTURE_ARTIFACT_NAMES.length : artifacts.length}</dd></div></dl>
            {progressPercent === undefined
              ? (active || submissionUncertain) && <p className="muted">進捗: worker報告待ち。状態と成果物を2秒ごとに更新しています。</p>
              : <div className="progress-track" role="progressbar" aria-label="Windows収録の進捗" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent}><span style={{ width: `${progressPercent}%` }} /></div>}
            {visibleJob?.message && <p className={visibleJob.status === 'failed' ? 'narration-error-text' : 'muted'}>{visibleJob.message}{visibleJob.errorCode ? ` · ${visibleJob.errorCode}` : ''}</p>}
            <div className="narration-artifact-list"><strong>native captureの8成果物</strong>{renderedArtifacts.length === 0 ? <span className="muted">まだありません</span> : showExpectedArtifacts ? WINDOWS_CAPTURE_ARTIFACT_NAMES.map((name, index) => { const artifact = renderedArtifacts[index]; return <div className="external-artifact-row" key={name}>{artifact?.url ? <a href={artifact.url} target="_blank" rel="noreferrer">{name} ↗</a> : <span>{name}</span>}<small>{artifact ? `${formatBytes(artifact.sizeBytes)} · SHA-256 ${artifact.sha256 ?? '未取得'}` : '未取得'}</small></div>; }) : availableArtifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} · {formatBytes(artifact.sizeBytes)} ↗</a>)}</div>
            <p className="gate-separation-note">Job成功は8成果物の構造・timestamp・duration検証成功を表します。映像内の出来事と音声内の出来事が同期していることは証明しないため、実機での目視・試聴が完了するまで公開利用gateは保留です。</p>
          </section>
          <section className="panel compact-panel"><div className="panel-header"><div><span className="section-kicker">STAGE ATTEMPTS</span><h3>Windows収録試行履歴</h3></div><span className="count-chip">{attempts.length}</span></div>{attempts.length === 0 ? <p className="muted">stage attempt記録はまだありません。</p> : <div className="attempt-list">{attempts.map((attempt) => <article className="attempt-row" key={attempt.id}><div><strong>#{attempt.attempt ?? '—'} · {attempt.id}</strong><small>{formatDate(attempt.createdAt)}</small></div><StatusBadge status={attempt.status} label={jobStatusLabel(attempt.status)} /><div><span>{formatDuration(attempt.durationSeconds)}</span><span>{attempt.artifacts.length} artifact</span></div></article>)}</div>}</section>
        </aside>
      </div>
    </div>
  );
}

function ScreenCapturePanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => hasScreenCaptureStage(run) && run.executionProfile === 'local_playwright')
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [url, setUrl] = useState(() => `${window.location.origin}/`);
  const [durationMs, setDurationMs] = useState(5_000);
  const [settleMs, setSettleMs] = useState(500);
  const [actionsText, setActionsText] = useState('[\n  {"type":"scroll","at_ms":1500,"delta_y":720}\n]');
  const [job, setJob] = useState<Job>();
  const [submitting, setSubmitting] = useState(false);
  const [submissionUncertain, setSubmissionUncertain] = useState(false);
  const submittingRef = useRef(false);
  const pollingRef = useRef(false);
  const submissionGuardRef = useRef<{ runId: string; knownJobIds: Set<string> } | undefined>(undefined);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setJob(undefined);
      setSubmissionUncertain(false);
      submissionGuardRef.current = undefined;
      setMessage(undefined);
    }
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const attempts = [...(selectedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'screen_capture')
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''));
  const currentAttempt = attempts[0];
  const matchingJobs = selectedRun
    ? jobs.filter((candidate) => isLocalScreenCaptureJobForSelection(candidate, { runId: selectedRun.id }))
    : [];
  const visibleJob = submitting || submissionUncertain
    ? (submissionUncertain ? job : undefined)
    : selectLocalScreenCaptureJob(job, currentAttempt, matchingJobs, selectedRun?.id);
  const status = visibleJob?.status ?? (submitting || submissionUncertain ? undefined : currentAttempt?.status);
  const active = status === 'pending' || status === 'running';
  const parsedActions = useMemo(() => {
    try {
      const value: unknown = JSON.parse(actionsText);
      return Array.isArray(value)
        ? { value, error: undefined }
        : { value: [], error: '操作一覧はJSON配列で指定してください。' };
    } catch {
      return { value: [], error: '操作一覧のJSONが正しくありません。' };
    }
  }, [actionsText]);
  const normalizedInput = useMemo(
    () => normalizeLocalScreenCaptureInput({ url, durationMs, settleMs, actions: parsedActions.value }),
    [durationMs, parsedActions.value, settleMs, url],
  );
  const validationErrors = parsedActions.error
    ? [parsedActions.error, ...normalizedInput.errors]
    : normalizedInput.errors;

  useEffect(() => {
    if (!selectedRun || submitting || (!active && !submissionUncertain)) return;
    let cancelled = false;
    const poll = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const nextJobs = await api.jobs();
        if (cancelled) return;
        const scopedJobs = nextJobs.filter((candidate) => isLocalScreenCaptureJobForSelection(candidate, { runId: selectedRun.id }));
        const guard = submissionGuardRef.current;
        const reconciled = submissionUncertain && guard?.runId === selectedRun.id
          ? selectLocalScreenCaptureJob(
            undefined,
            undefined,
            scopedJobs.filter((candidate) => !guard.knownJobIds.has(candidate.id)),
            selectedRun.id,
          )
          : undefined;
        const next = reconciled
          ?? (submissionUncertain ? undefined : visibleJob?.id
            ? nextJobs.find((candidate) => candidate.id === visibleJob.id)
            : selectLocalScreenCaptureJob(undefined, currentAttempt, scopedJobs, selectedRun.id));
        if (next) setJob(next);
        if (reconciled) {
          submissionGuardRef.current = undefined;
          setSubmissionUncertain(false);
          setMessage({ type: 'info', text: '応答を受信できませんでしたが、受理済みJobを照合しました。再送は行いません。' });
        }
        if (next && ['succeeded', 'failed', 'cancelled'].includes(next.status)) {
          await onReload().catch(() => undefined);
        }
      } catch {
        // Preserve the last known state; the next bounded poll retries.
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [active, currentAttempt, onReload, selectedRun, submissionUncertain, submitting, visibleJob?.id]);

  const execute = async () => {
    if (submittingRef.current || active || !selectedRun) return;
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setSubmissionUncertain(false);
    submissionGuardRef.current = {
      runId: selectedRun.id,
      knownJobIds: new Set([
        ...matchingJobs.map((candidate) => candidate.id),
        ...(currentAttempt?.jobId ? [currentAttempt.jobId] : []),
      ]),
    };
    setJob(undefined);
    setMessage({ type: 'info', text: 'isolated Chromiumの画面収録をbrowser laneへ登録しています。' });
    try {
      const request: LocalScreenCaptureRequest = normalizedInput.request;
      const submitted = await api.executeLocalScreenCapture(selectedRun.id, request);
      submissionGuardRef.current = undefined;
      setSubmissionUncertain(false);
      setJob(submitted);
      setMessage({
        type: submitted.status === 'failed' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? localScreenCaptureError(submitted.message ?? 'workerが失敗しました')
          : 'Playwright画面収録をキューに登録しました。',
      });
      await onReload().catch(() => undefined);
    } catch (error) {
      // A server-side 4xx is a definitive rejection; it cannot represent an
      // accepted capture, so do not leave the form in the ambiguity lock.
      if (error instanceof StudioApiError && error.status >= 400 && error.status < 500) {
        submissionGuardRef.current = undefined;
        setSubmissionUncertain(false);
        setMessage({ type: 'error', text: localScreenCaptureError(error) });
        return;
      }
      // The backend persists the attempt/job before the HTTP response is
      // written. Re-read both sources before allowing another submission so
      // a timeout or disconnected response cannot create a duplicate capture.
      setSubmissionUncertain(true);
      await onReload().catch(() => undefined);
      try {
        const nextJobs = await api.jobs();
        const guard = submissionGuardRef.current;
        const freshJobs = guard?.runId === selectedRun.id
          ? nextJobs
            .filter((candidate) => isLocalScreenCaptureJobForSelection(candidate, { runId: selectedRun.id }))
            .filter((candidate) => !guard.knownJobIds.has(candidate.id))
          : [];
        const reconciled = selectLocalScreenCaptureJob(undefined, undefined, freshJobs, selectedRun.id);
        if (reconciled) {
          submissionGuardRef.current = undefined;
          setSubmissionUncertain(false);
          setJob(reconciled);
          setMessage({ type: 'info', text: '応答を受信できませんでしたが、受理済みJobを照合しました。再送は行いません。' });
          if (['succeeded', 'failed', 'cancelled'].includes(reconciled.status)) {
            await onReload().catch(() => undefined);
          }
          return;
        }
      } catch {
        // Keep the uncertainty lock; the polling effect retries the jobs
        // lookup without permitting a second POST.
      }
      setMessage({ type: 'error', text: `${localScreenCaptureError(error)} 受理状態を確認中のため、二重実行防止で再送を停止しています。` });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (eligibleRuns.length === 0) {
    return <div className="narration-stack"><section className="panel"><div className="panel-header"><div><span className="section-kicker">LOCAL PLAYWRIGHT</span><h3>Web画面収録</h3></div></div><EmptyState title="local_playwrightの画面収録Runがありません" description="概要の再調整で画面収録を選び、local_playwrightプロファイルのRunを作成してください。" /></section></div>;
  }

  const artifacts = visibleJob?.result?.artifacts ?? (submitting || submissionUncertain ? [] : currentAttempt?.artifacts ?? []);
  const preview = artifacts.find((artifact) => artifact.name === 'screen-capture.mp4');
  const recordedDurationMs = visibleJob?.result?.durationMs ?? (submitting || submissionUncertain ? durationMs : currentAttempt?.durationMs ?? durationMs);
  const progressPercent = visibleJob?.progress === undefined
    ? undefined
    : Math.max(0, Math.min(100, visibleJob.progress));
  const locked = submitting || active || submissionUncertain;
  return (
    <div className="narration-stack">
      <div className="timeline-grid">
      <div>
        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL PLAYWRIGHT</span><h3>Web実画面収録</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">新しいChromium contextでloopback Web画面だけを縦1080×1920・24fps・音声なしMP4に収録します。Cookieや既存ブラウザprofileは共有せず、外部通信も遮断します。</p>
          <label className="field"><span>対象Run</span><select value={selectedRunId} disabled={locked} onChange={(event) => { setSelectedRunId(event.target.value); setJob(undefined); setSubmissionUncertain(false); submissionGuardRef.current = undefined; setMessage(undefined); }} aria-label="画面収録対象Run">{eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id} · {run.executionProfile}</option>)}</select></label>
          <label className="field"><span>loopback URL</span><input type="url" value={url} disabled={locked} onChange={(event) => setUrl(event.target.value)} placeholder="http://127.0.0.1:3000/" aria-label="画面収録URL" /></label>
          <div className="field-grid two-columns">
            <label className="field"><span>録画時間（ms）</span><input type="number" min="1000" max="30000" step="100" value={durationMs} disabled={locked} onChange={(event) => setDurationMs(Number(event.target.value))} /></label>
            <label className="field"><span>描画待ち（ms）</span><input type="number" min="0" max="10000" step="100" value={settleMs} disabled={locked} onChange={(event) => setSettleMs(Number(event.target.value))} /></label>
          </div>
          <label className="field"><span>操作（最大16件のJSON配列）</span><textarea rows={7} value={actionsText} disabled={locked} onChange={(event) => setActionsText(event.target.value)} spellCheck={false} aria-label="画面収録操作JSON" /><small>scroll、click、pressのみ。任意JavaScript、文字入力、認証情報は受け付けません。</small></label>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{[...new Set(validationErrors)].map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button" type="button" disabled={locked || validationErrors.length > 0} onClick={() => void execute()}>{submitting ? '登録中…' : submissionUncertain ? '受理状態を照合中…' : active ? '収録を監視中…' : '画面収録を実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
        {preview && <section className="panel"><div className="panel-header"><div><span className="section-kicker">VERIFIED OUTPUT</span><h3>収録プレビュー</h3></div></div><ArtifactPreview artifact={preview} /></section>}
      </div>
      <aside>
        <section className="panel compact-panel timeline-status-panel" aria-live="polite" aria-busy={active || submissionUncertain}>
          <div className="panel-header"><div><span className="section-kicker">CAPTURE STATUS</span><h3>画面収録実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>
          <dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{visibleJob?.id ?? (submitting || submissionUncertain ? '—' : currentAttempt?.jobId ?? '—')}</dd></div><div><dt>Stage attempt</dt><dd className="mono">{visibleJob?.stageAttemptId ?? (submitting || submissionUncertain ? '—' : currentAttempt?.id ?? '—')}</dd></div><div><dt>進捗</dt><dd>{progressPercent === undefined ? (active || submissionUncertain ? '計測中' : '—') : `${Math.round(progressPercent)}%`}</dd></div><div><dt>工程</dt><dd>{screenCaptureProgressPhaseLabel(visibleJob?.progressPhase)}</dd></div><div><dt>指定尺</dt><dd>{(recordedDurationMs / 1000).toFixed(1)}秒</dd></div><div><dt>出力</dt><dd>1080×1920 / 24fps</dd></div><div><dt>音声</dt><dd>なし</dd></div><div><dt>artifact</dt><dd>{artifacts.length}</dd></div></dl>
          {progressPercent === undefined
            ? (active || submissionUncertain) && <p className="muted">進捗: worker報告待ち。状態と成果物を2秒ごとに更新しています。</p>
            : <div className="progress-track" role="progressbar" aria-label="画面収録の進捗" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progressPercent}><span style={{ width: `${progressPercent}%` }} /></div>}
          {visibleJob?.message && <p className={visibleJob.status === 'failed' ? 'narration-error-text' : 'muted'}>{visibleJob.message}{visibleJob.errorCode ? ` · ${visibleJob.errorCode}` : ''}</p>}
          <div className="narration-artifact-list"><strong>中間・最終成果物</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} · {formatBytes(artifact.sizeBytes)} ↗</a>)}</div>
          <p className="gate-separation-note">URL全文とselector本文はjob・eventへ保存せず、originとSHA-256だけを監査記録に残します。</p>
        </section>
        <section className="panel compact-panel"><div className="panel-header"><div><span className="section-kicker">STAGE ATTEMPTS</span><h3>画面収録試行履歴</h3></div><span className="count-chip">{attempts.length}</span></div>{attempts.length === 0 ? <p className="muted">stage attempt記録はまだありません。</p> : <div className="attempt-list">{attempts.map((attempt) => <article className="attempt-row" key={attempt.id}><div><strong>#{attempt.attempt ?? '—'} · {attempt.id}</strong><small>{formatDate(attempt.createdAt)}</small></div><StatusBadge status={attempt.status} label={jobStatusLabel(attempt.status)} /><div><span>{formatDuration(attempt.durationSeconds)}</span><span>{attempt.artifacts.length} artifact</span></div></article>)}</div>}</section>
      </aside>
      </div>
    </div>
  );
}

function VideoGenerationPanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => hasVideoGenerationStage(run) && run.executionProfile === 'local_comfyui')
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [prompt, setPrompt] = useState('');
  const [seed, setSeed] = useState('0');
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [resumingTaskId, setResumingTaskId] = useState<string>();
  const resumingRef = useRef(false);
  const pollingRef = useRef(false);
  const onReloadRef = useRef(onReload);
  onReloadRef.current = onReload;
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadedTerminalJob = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setJob(undefined);
      setMessage(undefined);
    }
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const currentAttempt = [...(selectedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'video_generation')
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))[0];
  const selectedRunRef = useRef<ProductionRun | undefined>(selectedRun);
  const currentAttemptRef = useRef<StageAttempt | undefined>(currentAttempt);
  const jobRef = useRef<Job | undefined>(job);
  selectedRunRef.current = selectedRun;
  currentAttemptRef.current = currentAttempt;
  jobRef.current = job;
  const providerTasks = useMemo(() => {
    if (!selectedRun) return [];
    const candidates = [...(selectedRun.providerTasks ?? []), ...(detail.providerTasks ?? [])]
      .filter((task) => providerTaskBelongsToVideoRun(task, detail.id, selectedRun.id));
    const unique = candidates.filter((task, index, all) => all.findIndex((item) => item.id === task.id) === index);
    return newestProviderTasks(unique);
  }, [detail.id, detail.providerTasks, selectedRun]);
  const providerTaskActive = providerTasks.some((task) => isProviderTaskActive(task));
  const providerTaskBlocking = providerTasks.some((task) => isProviderTaskBlocking(task));
  const matchingJobs = selectedRun
    ? jobs.filter((item) => isLocalComfyUiJobForSelection(item, { runId: selectedRun.id }))
    : [];
  const visibleJob = selectLocalComfyUiDisplayJob(job, currentAttempt, matchingJobs, selectedRun?.id);
  const executionStatus = visibleJob?.status ?? currentAttempt?.status;
  const localJobForRun = job && (
    (selectedRun?.id !== undefined && job.runId === selectedRun.id)
    || localComfyUiJobMatchesAttempt(job, currentAttempt)
  ) ? job : undefined;
  const executionActive = isLocalComfyUiExecutionActiveAcross([
    localJobForRun,
    currentAttempt,
    ...matchingJobs,
  ]) || providerTaskActive;
  const isTerminal = executionStatus === 'succeeded' || executionStatus === 'failed' || executionStatus === 'cancelled';
  const normalizedInput = useMemo(() => normalizeLocalComfyUiInput(prompt, seed), [prompt, seed]);
  const validationErrors = normalizedInput.errors;

  useEffect(() => {
    const runId = selectedRun?.id;
    if (!runId || (!executionActive && !providerTaskActive)) {
      if (isTerminal && !submitting && !providerTaskActive) setBusy(false);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const nextJobs = await api.jobs();
        if (cancelled) return;
        const latestRun = selectedRunRef.current;
        if (!latestRun || latestRun.id !== runId) return;
        const nextMatchingJobs = nextJobs.filter((item) => isLocalComfyUiJobForSelection(item, { runId }));
        const next = selectLocalComfyUiDisplayJob(jobRef.current, currentAttemptRef.current, nextMatchingJobs, runId);
        if (next) {
          jobRef.current = next;
          setJob(next);
        }
        // Provider-task state is returned by production detail, not /api/jobs.
        await onReloadRef.current().catch(() => undefined);
      } catch {
        // The next two-second poll retries; the last known attempt remains visible.
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2_000);
    return () => window.clearInterval(timer);
  }, [executionActive, isTerminal, providerTaskActive, selectedRun?.id, submitting]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const execute = async () => {
    if (submittingRef.current || resumingRef.current || executionActive || providerTaskBlocking) return;
    if (!selectedRun) {
      setMessage({ type: 'error', text: 'video_generation工程を含むlocal_comfyui Runを選択してください。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setJob(undefined);
    reloadedTerminalJob.current = undefined;
    setMessage({ type: 'info', text: 'ComfyUI動画生成workerをキューに登録しています。成功とはまだ判定していません。' });
    try {
      const request: LocalComfyUiRequest = normalizedInput.request;
      const submitted = await api.executeLocalVideoGeneration(selectedRun.id, request);
      setJob(submitted);
      setMessage({
        type: submitted.status === 'failed' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? localComfyUiError(submitted.message ?? 'workerが失敗しました')
          : 'ComfyUI動画生成workerをキューに登録しました。',
      });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: 'workerは登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (submitted.status === 'succeeded' || submitted.status === 'failed' || submitted.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localComfyUiError(error) });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const resumeProviderTask = async (task: ProviderTask) => {
    if (resumingRef.current || submittingRef.current || !isProviderTaskResumeAvailable(task)) return;
    resumingRef.current = true;
    setResumingTaskId(task.id);
    setBusy(true);
    setMessage({
      type: 'info',
      text: task.status === 'cancel_requested'
        ? 'キャンセル要求済みtaskの状態を再照合しています。生成promptの再送信は行いません。'
        : '同じprovider taskを安全に照合・再開しています。重複送信は行いません。',
    });
    try {
      const resumed = await api.resumeProviderTask(task.id);
      setJob(resumed);
      await onReload().catch(() => undefined);
      const resumeFailed = resumed.status === 'failed' || resumed.status === 'cancelled';
      setMessage({
        type: resumeFailed ? 'error' : 'success',
        text: resumeFailed
          ? localComfyUiError(resumed.message ?? (resumed.status === 'cancelled' ? 'provider taskの再照合は中断されました' : 'provider taskの再開に失敗しました'))
          : task.status === 'cancel_requested'
            ? 'キャンセル状態の再照合を登録しました。同じtask IDを監視します。'
            : 'provider taskの再開を登録しました。状態を監視しています。',
      });
      if (resumed.status === 'succeeded' || resumed.status === 'failed' || resumed.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localComfyUiError(error) });
    } finally {
      resumingRef.current = false;
      setResumingTaskId(undefined);
    }
  };

  if (eligibleRuns.length === 0) {
    return <section className="panel video-generation-panel"><div className="panel-header"><div><span className="section-kicker">LOCAL COMFYUI</span><h3>生成映像</h3></div></div><EmptyState title="local_comfyuiの動画生成Runがありません" description="概要の再調整で生成映像（video）を選択し、local_comfyuiプロファイルのRunを作成してください。" /></section>;
  }

  const resultArtifacts = visibleJob?.result?.artifacts ?? currentAttempt?.artifacts ?? [];
  const formLocked = busy || submitting || executionActive || providerTaskBlocking || resumingTaskId !== undefined;
  return (
    <div className="timeline-grid">
      <div>
        <section className="panel video-generation-panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL COMFYUI</span><h3>生成映像</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">固定済みのMiniMax H3 workflow presetで、プロンプトとseedだけを指定してローカル生成します。workflow JSON、モデルパス、endpointは画面から入力できません。</p>
          <label className="field"><span>対象Run（video_generation工程を要求したRun）</span><select value={selectedRunId} disabled={formLocked} onChange={(event) => { setSelectedRunId(event.target.value); setJob(undefined); setMessage(undefined); }} aria-label="生成映像対象Run">
            {eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id} · {run.executionProfile}</option>)}
          </select></label>
          <div className="timeline-run-summary"><span>Run ID</span><strong className="mono">{selectedRun?.id}</strong><span>Workflow</span><strong className="mono">{LOCAL_COMFYUI_WORKFLOW_PRESET}</strong></div>
          <label className="field"><span>生成プロンプト</span><textarea rows={8} value={prompt} disabled={formLocked} onChange={(event) => setPrompt(event.target.value)} placeholder="例：正面を向いた日本人女性が、柔らかい自然光のスタジオで静かに微笑む。フォトリアル、縦長構図。" aria-label="生成プロンプト" /></label>
          <label className="field"><span>seed（0〜2^63−1の整数）</span><input type="text" inputMode="numeric" pattern="[0-9]*" value={seed} disabled={formLocked} onChange={(event) => setSeed(event.target.value)} aria-label="生成seed" /></label>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={submitting || busy || executionActive || providerTaskBlocking || validationErrors.length > 0}>{submitting ? '登録中…' : providerTaskBlocking ? 'provider task確認中…' : busy || executionActive ? 'worker監視中…' : '動画生成を実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <ProviderTaskRecoveryCard tasks={providerTasks} resumingTaskId={resumingTaskId} onResume={(task) => void resumeProviderTask(task)} />
        <VideoGenerationJobStatus job={visibleJob} attempt={currentAttempt} artifacts={resultArtifacts} />
        <VideoGenerationAttemptHistory attempts={selectedRun?.stageAttempts.filter((attempt) => normalizeRequestedStage(attempt.stage) === 'video_generation') ?? []} />
      </aside>
    </div>
  );
}

function VideoGenerationJobStatus({ job, attempt, artifacts }: { job?: Job; attempt?: StageAttempt; artifacts: Artifact[] }) {
  const status = job?.status ?? attempt?.status;
  const active = status === 'pending' || status === 'running';
  const result = job?.result;
  const cacheHit = job?.cacheHit ?? attempt?.cacheHit;
  const provider = result?.provider ?? attempt?.provider ?? 'comfyui';
  const providerTaskId = result?.providerTaskId ?? attempt?.providerTaskId;
  const durationSeconds = result?.durationSeconds ?? job?.durationSeconds ?? attempt?.durationSeconds;
  const promptHash = result?.promptSha256 ?? attempt?.promptSha256;
  const seed = result?.seed ?? attempt?.seed;
  const workflowPreset = result?.workflowPreset ?? attempt?.workflowPreset;
  return <section className="panel compact-panel timeline-status-panel" aria-live="polite" aria-busy={active}><div className="panel-header"><div><span className="section-kicker">VIDEO GENERATION STATUS</span><h3>動画生成実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>{!job && !attempt && <p className="muted">実行すると、キュー投入後の状態をここで監視します。</p>}<dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{job?.id ?? attempt?.jobId ?? '—'}</dd></div><div><dt>Stage attempt</dt><dd className="mono">{job?.stageAttemptId ?? attempt?.id ?? '—'}</dd></div><div><dt>Cache hit</dt><dd>{cacheHit === undefined ? '—' : cacheHit ? 'はい' : 'いいえ'}</dd></div><div><dt>所要時間</dt><dd>{formatDuration(durationSeconds)}</dd></div><div><dt>Provider</dt><dd>{provider}</dd></div><div><dt>Provider task ID</dt><dd className="mono">{providerTaskId ?? '—'}</dd></div><div><dt>Workflow preset</dt><dd className="mono">{workflowPreset ?? '—'}</dd></div><div><dt>seed</dt><dd className="mono">{seed === undefined ? '—' : String(seed)}</dd></div><div><dt>prompt SHA-256</dt><dd className="mono">{promptHash ?? '—'}</dd></div><div><dt>更新</dt><dd>{formatDate(job?.updatedAt ?? attempt?.finishedAt ?? attempt?.startedAt)}</dd></div></dl>{job?.message && <p className={job.status === 'failed' ? 'narration-error-text' : 'muted'}>{job.message}{job.errorCode ? ` · ${job.errorCode}` : ''}</p>}<div className="narration-artifact-list"><strong>生成artifact</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} · {formatBytes(artifact.sizeBytes)} ↗</a>)}</div><p className="gate-separation-note">prompt本文はイベントログやjob表示へ複製せず、監査にはSHA-256だけを記録します。</p></section>;
}

function VideoGenerationAttemptHistory({ attempts }: { attempts: StageAttempt[] }) {
  const ordered = [...attempts].sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''));
  return <section className="panel compact-panel"><div className="panel-header"><div><span className="section-kicker">STAGE ATTEMPTS</span><h3>動画生成試行履歴</h3></div><span className="count-chip">{ordered.length}</span></div>{ordered.length === 0 ? <p className="muted">stage attempt記録はまだありません。</p> : <div className="attempt-list">{ordered.map((attempt) => <article className="attempt-row" key={attempt.id}><div><strong>#{attempt.attempt ?? '—'} · {attempt.id}</strong><small>{formatDate(attempt.startedAt ?? attempt.createdAt)}{attempt.finishedAt ? ` → ${formatDate(attempt.finishedAt)}` : ''}</small></div><StatusBadge status={attempt.status} label={jobStatusLabel(attempt.status)} /><div><span>{attempt.cacheHit === undefined ? 'cache —' : attempt.cacheHit ? 'cache hit' : 'cache miss'}</span><span>{formatDuration(attempt.durationSeconds)}</span><span>{attempt.artifacts.length} artifact</span></div>{attempt.message && <p>{attempt.message}</p>}</article>)}</div>}</section>;
}

const RERUN_STAGES = [
  ['script', '台本'],
  ['narration', 'ナレーション'],
  ['captions', '字幕・テロップ'],
  ['screen_capture', '画面収録'],
  ['keyframe', 'キーフレーム画像'],
  ['video', '生成映像'],
  ['timeline', 'カット編集'],
  ['assembly', '編集・合成'],
  ['qc', '品質検査'],
] as const;

const LOCAL_SAPI_STAGES = new Set(['narration', 'captions', 'timeline', 'assembly', 'qc']);
const ELEVENLABS_TTS_STAGES = new Set(['narration', 'captions', 'assembly', 'qc']);
const LOCAL_COMFYUI_STAGES = new Set(['video', 'video_generation', 'timeline', 'assembly', 'qc']);
const LOCAL_WINDOWS_CAPTURE_STAGES = new Set(['screen_capture']);
// A Playwright Run starts from a new capture. The planner expands that change
// to timeline/assembly/QC impact, while only capture and timeline have an
// executable local_playwright worker in this profile.
const LOCAL_PLAYWRIGHT_STAGES = new Set(['screen_capture']);

const artifactFileName = (artifact: Artifact): string =>
  (artifact.name || artifact.path || '').split(/[\\/]/).pop()?.toLowerCase() ?? '';

const hasArtifactFile = (attempt: StageAttempt, fileName: string): boolean =>
  attempt.artifacts.some((artifact) => artifactFileName(artifact) === fileName);

const isSucceededNarrationAttempt = (attempt: StageAttempt): boolean =>
  normalizeRequestedStage(attempt.stage) === 'narration'
  && attempt.status === 'succeeded'
  && hasArtifactFile(attempt, 'narration.wav')
  && hasArtifactFile(attempt, 'captions.srt');

const hasTimelineStage = (run: ProductionRun): boolean =>
  run.requestedStages.some((stage) => normalizeRequestedStage(stage) === 'timeline')
  || run.stages.some((stage) => normalizeRequestedStage(stage.name) === 'timeline');

const isAvailableVideoArtifact = (artifact: Artifact): boolean =>
  artifact.kind === 'video'
  && artifact.raw.available !== false
  && artifact.metadata.available !== false;

type TimelineDraftClip = {
  videoArtifactId: string;
  startMs: string;
  endMs: string;
  volumePercent: string;
  visualPreset: LocalRemotionTimelineVisualPreset;
  transitionEnabled: boolean;
  transitionDurationMs: string;
  overlayEnabled: boolean;
  overlayText: string;
  overlayStartMs: string;
  overlayEndMs: string;
  overlayPosition: LocalRemotionTimelineOverlayPosition;
};

const timelineDraftForArtifact = (artifact?: Artifact): TimelineDraftClip => {
  const durationMs = artifact?.durationSeconds === undefined
    ? undefined
    : Math.max(50, Math.round(artifact.durationSeconds * 1_000));
  return {
    videoArtifactId: artifact?.id ?? '',
    startMs: '0',
    endMs: durationMs === undefined ? '' : String(durationMs),
    volumePercent: '100',
    visualPreset: DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
    transitionEnabled: false,
    transitionDurationMs: '300',
    overlayEnabled: false,
    overlayText: '',
    overlayStartMs: '0',
    overlayEndMs: durationMs === undefined ? '' : String(Math.min(durationMs, 2_000)),
    overlayPosition: 'bottom',
  };
};

const timelineArtifactHash = (artifact?: Artifact): string => artifact?.sha256 ? `${artifact.sha256.slice(0, 16)}…` : 'hash未記録';

const formatMilliseconds = (milliseconds?: number): string =>
  milliseconds === undefined ? '—' : formatDuration(milliseconds / 1_000);

const timelineAttemptUsesRemotion = (attempt: StageAttempt): boolean => {
  const payload = attempt.raw.payload;
  const renderEngine = payload && typeof payload === 'object' && !Array.isArray(payload)
    ? (payload as Record<string, unknown>).render_engine
    : undefined;
  return attempt.provider === 'local_remotion_timeline' || renderEngine === 'remotion_v1';
};

function TimelinePanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const timelineRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => hasTimelineStage(run) && hasRemotionTimelineProfile(run))
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const hardCutAvailable = timelineRuns.some((run) => hasHardCutTimelineProfile(run));
  const remotionAvailable = timelineRuns.some((run) => hasRemotionTimelineProfile(run));
  const [editorMode, setEditorMode] = useState<'hard_cut' | 'remotion'>(() =>
    hardCutAvailable ? 'hard_cut' : 'remotion');
  const eligibleRuns = useMemo(
    () => timelineRuns.filter((run) => editorMode === 'remotion'
      ? hasRemotionTimelineProfile(run)
      : hasHardCutTimelineProfile(run)),
    [editorMode, timelineRuns],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [clips, setClips] = useState<TimelineDraftClip[]>([]);
  const [selectedClipIndex, setSelectedClipIndex] = useState(0);
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadedTerminalJob = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (eligibleRuns.length > 0 || timelineRuns.length === 0) return;
    if (editorMode === 'hard_cut' && remotionAvailable) setEditorMode('remotion');
    else if (editorMode === 'remotion' && hardCutAvailable) setEditorMode('hard_cut');
  }, [editorMode, eligibleRuns.length, hardCutAvailable, remotionAvailable, timelineRuns.length]);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setClips([]);
      setSelectedClipIndex(0);
      setJob(undefined);
      setMessage(undefined);
    }
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const videoArtifacts = useMemo(
    () => detail.artifacts.filter(isAvailableVideoArtifact),
    [detail.artifacts],
  );

  useEffect(() => {
    if (!selectedRunId) return;
    const first = videoArtifacts[0];
    setClips(first ? [timelineDraftForArtifact(first)] : []);
    setSelectedClipIndex(0);
    setJob(undefined);
    setMessage(undefined);
    reloadedTerminalJob.current = undefined;
  }, [selectedRunId]);

  useEffect(() => {
    if (clips.length === 0) setSelectedClipIndex(0);
    else if (selectedClipIndex >= clips.length) setSelectedClipIndex(clips.length - 1);
  }, [clips.length, selectedClipIndex]);

  const remotionMode = editorMode === 'remotion';
  const currentAttempt = [...(selectedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'timeline'
      && timelineAttemptUsesRemotion(attempt) === remotionMode)
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))[0];
  const matchesEditorModeJob = (candidate: Job): boolean =>
    (remotionMode ? isRemotionTimelineJobForSelection : isLocalTimelineJobForSelection)(candidate, {
      runId: selectedRun?.id,
    });
  const submittedJob = job && matchesEditorModeJob(job) ? job : undefined;
  const visibleJob = submittedJob ?? jobs.find((item) =>
    item.id === currentAttempt?.jobId
    || (remotionMode ? isRemotionTimelineJobForSelection : isLocalTimelineJobForSelection)(item, {
      runId: selectedRun?.id,
      stageAttemptId: currentAttempt?.id,
    }),
  );
  const isTerminal = visibleJob?.status === 'succeeded' || visibleJob?.status === 'failed' || visibleJob?.status === 'cancelled';
  const executionActive = visibleJob?.status === 'pending' || visibleJob?.status === 'running'
    || currentAttempt?.status === 'pending' || currentAttempt?.status === 'running';
  useEffect(() => {
    if (executionActive) setBusy(true);
  }, [executionActive]);
  const normalizedHardCutInput = useMemo(() => normalizeLocalTimelineInput(clips), [clips]);
  const remotionDraftInput = useMemo(() => ({
    clips: clips.map((clip, index) => ({
      videoArtifactId: clip.videoArtifactId,
      startMs: clip.startMs,
      endMs: clip.endMs,
      volumePercent: clip.volumePercent,
      visualPreset: clip.visualPreset,
      transitionToNext: index === clips.length - 1 || !clip.transitionEnabled ? null : {
        type: 'fade',
        durationMs: clip.transitionDurationMs,
      },
      overlay: !clip.overlayEnabled ? null : {
        text: clip.overlayText,
        startMs: clip.overlayStartMs,
        endMs: clip.overlayEndMs,
        position: clip.overlayPosition,
        stylePreset: 'shorts_ja_large_v1',
      },
    })),
  }), [clips]);
  const normalizedRemotionInput = useMemo(
    () => normalizeLocalRemotionTimelineInput(remotionDraftInput),
    [remotionDraftInput],
  );
  const missingArtifactErrors = clips.flatMap((clip, index) => clip.videoArtifactId && !videoArtifacts.some((artifact) => artifact.id === clip.videoArtifactId)
    ? [`カット${index + 1}の動画artifactはこの制作で利用できません。`]
    : []);
  const validationErrors = [
    ...(remotionMode ? normalizedRemotionInput.errors : normalizedHardCutInput.errors),
    ...missingArtifactErrors,
  ];
  const totalDurationMs = remotionMode
    ? normalizedRemotionInput.outputDurationMs
    : normalizedHardCutInput.totalDurationMs;
  const selectedArtifact = videoArtifacts.find((artifact) => artifact.id === clips[selectedClipIndex]?.videoArtifactId);
  const playerProps = useMemo(() => {
    if (!remotionMode || normalizedRemotionInput.errors.length > 0 || missingArtifactErrors.length > 0) return undefined;
    try {
      return buildRemotionTimelineCompositionProps(
        normalizedRemotionInput.request,
        (artifactId) => videoArtifacts.find((artifact) => artifact.id === artifactId)?.url ?? '',
      );
    } catch {
      return undefined;
    }
  }, [missingArtifactErrors.length, normalizedRemotionInput, remotionMode, videoArtifacts]);

  useEffect(() => {
    if (!visibleJob || isTerminal) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    const timer = window.setInterval(() => {
      void api.jobs().then((nextJobs) => {
        const next = nextJobs.find((item) => item.id === visibleJob.id);
        if (next) setJob(next);
      }).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [isTerminal, submitting, visibleJob]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const updateClip = <Key extends keyof TimelineDraftClip>(
    index: number,
    key: Key,
    value: TimelineDraftClip[Key],
  ) => {
    setClips((current) => current.map((clip, clipIndex) => clipIndex === index ? { ...clip, [key]: value } : clip));
  };

  const addClip = () => {
    const maximum = remotionMode ? 16 : 32;
    if (clips.length >= maximum) {
      setMessage({ type: 'error', text: `カットは${maximum}件以内にしてください。` });
      return;
    }
    const next = timelineDraftForArtifact(videoArtifacts[0]);
    setClips((current) => [...current, next]);
    setSelectedClipIndex(clips.length);
    setMessage(undefined);
  };

  const removeClip = (index: number) => {
    setClips((current) => current.filter((_, clipIndex) => clipIndex !== index));
    setSelectedClipIndex((current) => Math.max(0, Math.min(current, clips.length - 2)));
    setMessage(undefined);
  };

  const duplicateClip = (index: number) => {
    setClips((current) => duplicateTimelineClip(current, index));
    setSelectedClipIndex(index + 1);
    setMessage(undefined);
  };

  const moveClip = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= clips.length) return;
    setClips((current) => moveTimelineClip(current, index, target));
    setSelectedClipIndex(target);
    setMessage(undefined);
  };

  const execute = async () => {
    if (submittingRef.current || executionActive) return;
    if (!selectedRun) {
      setMessage({ type: 'error', text: 'カット編集工程を含むRunを選択してください。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setJob(undefined);
    reloadedTerminalJob.current = undefined;
    setMessage({
      type: 'info',
      text: remotionMode
        ? 'Remotion詳細preview workerをキューに登録しています。成功とはまだ判定していません。'
        : 'ハードカットworkerをキューに登録しています。成功とはまだ判定していません。',
    });
    try {
      const submitted = remotionMode
        ? await api.executeRemotionTimeline(
          selectedRun.id,
          normalizedRemotionInput.request as LocalRemotionTimelineRequest,
        )
        : await api.executeLocalTimeline(
          selectedRun.id,
          normalizedHardCutInput.request as LocalTimelineRequest,
        );
      setJob(submitted);
      setMessage({
        type: submitted.status === 'failed' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? localTimelineError(submitted.message ?? 'workerが失敗しました')
          : remotionMode
            ? 'Remotion詳細preview workerをキューに登録しました。'
            : 'ハードカットpreview workerをキューに登録しました。',
      });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: 'workerは登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (submitted.status === 'succeeded' || submitted.status === 'failed' || submitted.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localTimelineError(error) });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (timelineRuns.length === 0) {
    return <section className="panel timeline-panel"><div className="panel-header"><div><span className="section-kicker">LOCAL TIMELINE</span><h3>カット編集</h3></div></div><EmptyState title="カット編集工程を含むRunがありません" description="概要の再調整で timeline を選択し、カット編集用のRunを作成してください。" /></section>;
  }

  const resultArtifacts = visibleJob?.result?.artifacts ?? currentAttempt?.artifacts ?? [];
  const maximumClips = remotionMode ? 16 : 32;
  const formLocked = busy || submitting || executionActive;
  const visibleAttempts = (selectedRun?.stageAttempts ?? []).filter(
    (attempt) => normalizeRequestedStage(attempt.stage) === 'timeline'
      && timelineAttemptUsesRemotion(attempt) === remotionMode,
  );
  return (
    <div className="timeline-grid">
      <div>
        <section className="panel timeline-panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL TIMELINE</span><h3>カット編集</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">同じ制作に登録された動画artifactだけを使います。高速ハードカットと、fade・素材音量・固定テロップを確認できるRemotion詳細previewを切り替えられます。</p>
          <fieldset className="timeline-mode-picker" disabled={formLocked}>
            <legend>編集エンジン</legend>
            <label className={editorMode === 'hard_cut' ? 'is-selected' : ''}><input type="radio" name="timeline-engine" value="hard_cut" checked={editorMode === 'hard_cut'} disabled={!hardCutAvailable} onChange={() => { setEditorMode('hard_cut'); setJob(undefined); setMessage(undefined); }} /><span><strong>高速ハードカット</strong><small>最大32カット。トリムと並び順だけを素早く確認</small></span></label>
            <label className={editorMode === 'remotion' ? 'is-selected' : ''}><input type="radio" name="timeline-engine" value="remotion" checked={editorMode === 'remotion'} disabled={!remotionAvailable} onChange={() => { setEditorMode('remotion'); setJob(undefined); setMessage(undefined); }} /><span><strong>Remotion詳細preview</strong><small>最大16カット／60秒。fade・音量・固定テロップを反映</small></span></label>
          </fieldset>
          <label className="field"><span>対象Run（timeline工程を要求したRun）</span><select value={selectedRunId} disabled={formLocked} onChange={(event) => { setSelectedRunId(event.target.value); setClips([]); setSelectedClipIndex(0); setJob(undefined); setMessage(undefined); }} aria-label="カット編集対象Run">
            {eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id} · {run.executionProfile ?? 'profile未指定'}</option>)}
          </select></label>
          <div className="timeline-run-summary"><span>Run ID</span><strong className="mono">{selectedRun?.id}</strong><span>工程</span><strong>{selectedRun?.requestedStages.map(stageLabel).join('、') || '—'}</strong></div>
          {videoArtifacts.length === 0 && <div className="notice notice-warning"><div><strong>動画artifactがありません</strong><p>先に生成映像を登録し、インデックスを更新してください。</p></div></div>}
          <div className="timeline-toolbar"><div><strong>カット一覧</strong><small>{clips.length} / {maximumClips}件 · 出力 {formatMilliseconds(totalDurationMs)}</small></div><button className="button button-secondary" type="button" onClick={addClip} disabled={formLocked || clips.length >= maximumClips}>＋カットを追加</button></div>
          <div className="timeline-clip-list">
            {clips.map((clip, index) => {
              const artifact = videoArtifacts.find((item) => item.id === clip.videoArtifactId);
              return (
                <article className={`timeline-clip-row ${selectedClipIndex === index ? 'is-selected' : ''}`} key={`${index}-${clip.videoArtifactId}`} onClick={() => setSelectedClipIndex(index)}>
                  <div className="timeline-clip-heading"><button className="timeline-clip-select" type="button" onClick={() => setSelectedClipIndex(index)} aria-label={`カット${index + 1}を選択`}><strong>{String(index + 1).padStart(2, '0')}</strong><span>{artifact?.name ?? '動画artifact未選択'}</span></button><span className="timeline-clip-duration">{formatMilliseconds((Number(clip.endMs) || 0) - (Number(clip.startMs) || 0))}</span></div>
                  <label className="field"><span>動画artifact</span><select value={clip.videoArtifactId} disabled={busy || submitting || videoArtifacts.length === 0} onChange={(event) => updateClip(index, 'videoArtifactId', event.target.value)} aria-label={`カット${index + 1}の動画artifact`}>
                    <option value="">動画artifactを選択</option>
                    {videoArtifacts.map((item) => <option key={item.id} value={item.id}>{item.name} · {formatBytes(item.sizeBytes)}</option>)}
                  </select></label>
                  <div className="timeline-time-grid"><label className="field"><span>開始（ms）</span><input type="number" min="0" step="1" value={clip.startMs} disabled={busy || submitting} onChange={(event) => updateClip(index, 'startMs', event.target.value)} aria-label={`カット${index + 1}の開始ミリ秒`} /></label><label className="field"><span>終了（ms）</span><input type="number" min="0" step="1" value={clip.endMs} disabled={busy || submitting} onChange={(event) => updateClip(index, 'endMs', event.target.value)} aria-label={`カット${index + 1}の終了ミリ秒`} /></label></div>
                  {remotionMode && <div className="remotion-clip-controls">
                    <label className="field"><span>素材音量（0〜100%）</span><input type="number" min="0" max="100" step="1" value={clip.volumePercent} disabled={busy || submitting} onChange={(event) => updateClip(index, 'volumePercent', event.target.value)} aria-label={`カット${index + 1}の素材音量`} /></label>
                    <label className="field"><span>映像補正preset</span><select value={clip.visualPreset} disabled={busy || submitting} onChange={(event) => updateClip(index, 'visualPreset', event.target.value as LocalRemotionTimelineVisualPreset)} aria-label={`カット${index + 1}の映像補正preset`}><option value="preserve_v1">補正なし（preserve_v1）</option><option value="h3_low_res_sharp_v1">H3低解像度を鮮明化</option></select><small className="field-help">固定強度です。任意filterは指定できません。</small></label>
                    <label className={`remotion-toggle ${index === clips.length - 1 ? 'is-disabled' : ''}`}><input type="checkbox" checked={index < clips.length - 1 && clip.transitionEnabled} disabled={busy || submitting || index === clips.length - 1} onChange={(event) => updateClip(index, 'transitionEnabled', event.target.checked)} /><span><strong>次カットへfade</strong><small>{index === clips.length - 1 ? '最終カットには設定できません' : '50〜2000ms'}</small></span></label>
                    {index < clips.length - 1 && clip.transitionEnabled && <label className="field"><span>fade時間（ms）</span><input type="number" min="50" max="2000" step="1" value={clip.transitionDurationMs} disabled={busy || submitting} onChange={(event) => updateClip(index, 'transitionDurationMs', event.target.value)} aria-label={`カット${index + 1}のfade時間`} /></label>}
                    <label className="remotion-toggle"><input type="checkbox" checked={clip.overlayEnabled} disabled={busy || submitting} onChange={(event) => updateClip(index, 'overlayEnabled', event.target.checked)} /><span><strong>固定テロップ</strong><small>shorts_ja_large_v1／最大4行</small></span></label>
                    {clip.overlayEnabled && <div className="remotion-overlay-editor">
                      <label className="field remotion-overlay-text"><span>テロップ本文</span><textarea rows={3} maxLength={200} value={clip.overlayText} disabled={busy || submitting} onChange={(event) => updateClip(index, 'overlayText', event.target.value)} aria-label={`カット${index + 1}のテロップ本文`} /></label>
                      <label className="field"><span>表示開始（ms）</span><input type="number" min="0" step="1" value={clip.overlayStartMs} disabled={busy || submitting} onChange={(event) => updateClip(index, 'overlayStartMs', event.target.value)} aria-label={`カット${index + 1}のテロップ表示開始ミリ秒`} /></label>
                      <label className="field"><span>表示終了（ms）</span><input type="number" min="0" step="1" value={clip.overlayEndMs} disabled={busy || submitting} onChange={(event) => updateClip(index, 'overlayEndMs', event.target.value)} aria-label={`カット${index + 1}のテロップ表示終了ミリ秒`} /></label>
                      <label className="field"><span>表示位置</span><select value={clip.overlayPosition} disabled={busy || submitting} onChange={(event) => updateClip(index, 'overlayPosition', event.target.value as LocalRemotionTimelineOverlayPosition)} aria-label={`カット${index + 1}のテロップ表示位置`}><option value="top">上</option><option value="center">中央</option><option value="bottom">下</option></select></label>
                    </div>}
                  </div>}
                  <div className="timeline-artifact-meta"><span>bytes {formatBytes(artifact?.sizeBytes)}</span><span className="mono">SHA {timelineArtifactHash(artifact)}</span><span>source尺 {formatDuration(artifact?.durationSeconds)}</span></div>
                  <div className="timeline-row-actions"><button className="button button-ghost" type="button" onClick={(event) => { event.stopPropagation(); moveClip(index, -1); }} disabled={busy || submitting || index === 0} aria-label={`カット${index + 1}を上へ移動`}>↑</button><button className="button button-ghost" type="button" onClick={(event) => { event.stopPropagation(); moveClip(index, 1); }} disabled={busy || submitting || index === clips.length - 1} aria-label={`カット${index + 1}を下へ移動`}>↓</button><button className="button button-ghost" type="button" onClick={(event) => { event.stopPropagation(); duplicateClip(index); }} disabled={busy || submitting || clips.length >= maximumClips}>複製</button><button className="button button-ghost" type="button" onClick={(event) => { event.stopPropagation(); removeClip(index); }} disabled={busy || submitting}>削除</button></div>
                </article>
              );
            })}
            {clips.length === 0 && <EmptyState title="カットがありません" description="動画artifactを選び、カットを追加してください。" />}
          </div>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={formLocked || validationErrors.length > 0}>{submitting ? '登録中…' : formLocked ? 'worker監視中…' : remotionMode ? 'Remotion詳細previewをレンダー' : 'ハードカットpreviewを実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        {remotionMode && <section className="panel compact-panel remotion-player-panel">
          <div className="panel-header"><div><span className="section-kicker">INTERACTIVE PLAYER</span><h3>詳細preview</h3></div><span className="tag">1080×1920 · 24fps</span></div>
          {playerProps ? <div className="remotion-player-shell"><Player component={TimelineComposition} inputProps={playerProps} durationInFrames={playerProps.durationInFrames} compositionWidth={1080} compositionHeight={1920} fps={24} controls loop style={{ width: '100%', aspectRatio: '9 / 16' }} /></div> : <p className="muted">入力を整えると、同じcompositionをここで再生できます。</p>}
          <p className="gate-separation-note">Playerは映像補正presetの前処理を再現しません。鮮明化は完成artifactを正として確認してください。素材音量はpreviewに反映し、後続assemblyで「素材音を小さく残す」を選ぶとさらに素材25%を適用します。</p>
        </section>}
        <TimelineJobStatus job={visibleJob} attempt={currentAttempt} artifacts={resultArtifacts} />
        <section className="panel compact-panel">
          <div className="panel-header"><div><span className="section-kicker">SELECTED SOURCE</span><h3>選択中artifact</h3></div></div>
          {selectedArtifact ? <dl className="timeline-selected-source"><div><dt>名前</dt><dd>{selectedArtifact.name}</dd></div><div><dt>bytes</dt><dd>{formatBytes(selectedArtifact.sizeBytes)}</dd></div><div><dt>SHA-256</dt><dd className="mono">{selectedArtifact.sha256 ?? '未記録'}</dd></div><div><dt>URL</dt><dd><a href={selectedArtifact.url} target="_blank" rel="noreferrer">artifactを開く ↗</a></dd></div></dl> : <p className="muted">カットを選択すると入力artifactのhashとbytesを表示します。</p>}
        </section>
        <TimelineAttemptHistory attempts={visibleAttempts} />
      </aside>
    </div>
  );
}

function TimelineJobStatus({ job, attempt, artifacts }: { job?: Job; attempt?: StageAttempt; artifacts: Artifact[] }) {
  const status = job?.status ?? attempt?.status;
  const active = status === 'pending' || status === 'running';
  const cacheHit = job?.cacheHit ?? attempt?.cacheHit;
  const provider = job?.result?.provider ?? attempt?.provider;
  const executionSeconds = elapsedSecondsBetween(
    job?.startedAt ?? attempt?.startedAt,
    job && !active ? job.updatedAt : attempt?.finishedAt,
  );
  const outputDurationSeconds = job?.result?.durationSeconds ?? attempt?.durationSeconds;
  const cacheKey = typeof job?.raw.cache_key === 'string' ? job.raw.cache_key : typeof attempt?.raw.cache_key === 'string' ? attempt.raw.cache_key : undefined;
  return <section className="panel compact-panel timeline-status-panel" aria-live="polite" aria-busy={active}><div className="panel-header"><div><span className="section-kicker">TIMELINE STATUS</span><h3>カット編集実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>{!job && !attempt && <p className="muted">実行すると、キュー投入後の状態をここで監視します。</p>}<dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{job?.id ?? attempt?.jobId ?? '—'}</dd></div><div><dt>Stage attempt</dt><dd className="mono">{job?.stageAttemptId ?? attempt?.id ?? '—'}</dd></div><div><dt>Cache hit</dt><dd>{cacheHit === undefined ? '—' : cacheHit ? 'はい' : 'いいえ'}</dd></div><div><dt>Cache key</dt><dd className="mono">{cacheKey ? `${cacheKey.slice(0, 16)}…` : '—'}</dd></div><div><dt>実行時間</dt><dd>{active ? '実行中' : formatDuration(executionSeconds)}</dd></div><div><dt>出力尺</dt><dd>{formatDuration(outputDurationSeconds)}</dd></div><div><dt>Provider</dt><dd>{provider ?? '—'}</dd></div><div><dt>実費</dt><dd>{(job?.result?.actualCost ?? attempt?.actualCost) === undefined ? '—' : `${job?.result?.actualCost ?? attempt?.actualCost}（local）`}</dd></div><div><dt>更新</dt><dd>{formatDate(job?.updatedAt ?? attempt?.finishedAt ?? attempt?.startedAt)}</dd></div></dl>{job?.message && <p className={job.status === 'failed' ? 'narration-error-text' : 'muted'}>{job.message}</p>}<div className="narration-artifact-list"><strong>出力artifact</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} · {formatBytes(artifact.sizeBytes)} ↗</a>)}</div><p className="gate-separation-note">カット編集のworker記録です。音声／字幕assembly、technical QC、公開判定とは別の工程です。</p></section>;
}

function TimelineAttemptHistory({ attempts }: { attempts: StageAttempt[] }) {
  const ordered = [...attempts].sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''));
  return <section className="panel compact-panel"><div className="panel-header"><div><span className="section-kicker">STAGE ATTEMPTS</span><h3>カット編集試行履歴</h3></div><span className="count-chip">{ordered.length}</span></div>{ordered.length === 0 ? <p className="muted">stage attempt記録はまだありません。</p> : <div className="attempt-list">{ordered.map((attempt) => <article className="attempt-row" key={attempt.id}><div><strong>#{attempt.attempt ?? '—'} · {attempt.id}</strong><small>{formatDate(attempt.startedAt ?? attempt.createdAt)}{attempt.finishedAt ? ` → ${formatDate(attempt.finishedAt)}` : ''}</small></div><StatusBadge status={attempt.status} label={jobStatusLabel(attempt.status)} /><div><span>{attempt.cacheHit === undefined ? 'cache —' : attempt.cacheHit ? 'cache hit' : 'cache miss'}</span><span>実行 {formatDuration(elapsedSecondsBetween(attempt.startedAt, attempt.finishedAt))}</span><span>出力 {formatDuration(attempt.durationSeconds)}</span><span>{attempt.artifacts.length} artifact</span></div>{attempt.message && <p>{attempt.message}</p>}</article>)}</div>}</section>;
}

const DETAILED_TEST_VIDEO_STEPS = [
  { key: 'narration', label: 'ナレーション', aliases: ['narration'] },
  { key: 'timeline', label: 'Remotion詳細編集', aliases: ['timeline', 'remotion_timeline'] },
  { key: 'assembly', label: '音声・字幕合成', aliases: ['assembly'] },
  { key: 'qc', label: '技術QC', aliases: ['qc'] },
] as const;

const detailedTestVideoStageResult = (
  step: typeof DETAILED_TEST_VIDEO_STEPS[number],
  job?: Job,
  run?: ProductionRun,
): LocalPipelineStageResult | undefined => {
  const childEntry = Object.entries(job?.result?.jobs ?? {}).find(([key, child]) => {
    const normalizedKey = normalizeRequestedStage(key);
    const normalizedStage = normalizeRequestedStage(child.stage);
    return (step.aliases as readonly string[]).some((alias) => alias === normalizedKey || alias === normalizedStage);
  });
  const child = childEntry?.[1];
  const attempt = [...(run?.stageAttempts ?? [])]
    .filter((item) => (step.aliases as readonly string[]).includes(normalizeRequestedStage(item.stage))
      || Boolean(child?.stageAttemptId && item.id === child.stageAttemptId)
      || Boolean(child?.jobId && item.jobId === child.jobId))
    .sort((left, right) => (right.createdAt ?? '').localeCompare(left.createdAt ?? ''))[0];
  if (!attempt) return child;
  const attemptResult: LocalPipelineStageResult = {
    stage: step.key,
    status: attempt.status,
    jobId: attempt.jobId,
    stageAttemptId: attempt.id,
    attempt: attempt.attempt,
    cacheHit: attempt.cacheHit,
    message: attempt.message,
    artifacts: attempt.artifacts,
    raw: attempt.raw,
  };
  if (!child) return attemptResult;
  return {
    ...attemptResult,
    ...child,
    stage: step.key,
    status: child.status === 'unknown' ? attempt.status : child.status,
    jobId: child.jobId ?? attempt.jobId,
    stageAttemptId: child.stageAttemptId ?? attempt.id,
    artifacts: child.artifacts.length > 0 ? child.artifacts : attempt.artifacts,
    raw: { ...attempt.raw, ...child.raw },
  };
};

type AnnouncementSceneDraft = {
  role: AnnouncementSceneRole;
  videoArtifactId: string;
  startMs: string;
  endMs: string;
  volumePercent: string;
  visualPreset: LocalRemotionTimelineVisualPreset;
  headline: string;
  narration: string;
};

type AnnouncementRecipeDraft = {
  schemaVersion: 1;
  name: string;
  templatePreset: 'shorts_ja_15s_v1';
  scenes: AnnouncementSceneDraft[];
  voice: string;
  rate: string;
  pronunciations: Array<{ source: string; target: string }>;
  includeCaptioned: boolean;
  captionStylePreset: LocalAssemblyCaptionStylePreset;
  audioMixPreset: LocalAssemblyAudioMixPreset;
  variant: LocalQcVariant;
};

type AnnouncementEditorMode = 'quick' | 'advanced';

const ANNOUNCEMENT_ROLE_META: Record<AnnouncementSceneRole, { index: string; label: string; guide: string }> = {
  hook: { index: '01', label: 'HOOK', guide: '最初の数秒で目を止める一言' },
  message: { index: '02', label: 'MESSAGE', guide: '伝えたい価値・要点をひとつ' },
  cta: { index: '03', label: 'CTA', guide: '次の行動を短く案内' },
};

const newAnnouncementRecipeId = (): string => {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return `announcement_${[...bytes].map((value) => value.toString(16).padStart(2, '0')).join('')}`;
};

const ANNOUNCEMENT_DEFAULT_SCENE_END_MS = [5_167, 5_167, 5_166] as const;

const announcementEndMs = (artifact: Artifact | undefined, sceneIndex: number): string => {
  const target = ANNOUNCEMENT_DEFAULT_SCENE_END_MS[sceneIndex] ?? 5_000;
  if (artifact?.durationSeconds === undefined) return String(target);
  return String(Math.min(target, Math.max(0, Math.floor(artifact.durationSeconds * 1_000))));
};

const newAnnouncementDraft = (artifacts: Artifact[]): AnnouncementRecipeDraft => {
  const source = (index: number) => artifacts[index] ?? artifacts[0];
  return {
    schemaVersion: ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
    name: '15秒告知動画',
    templatePreset: ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET,
    scenes: [
      { role: 'hook', videoArtifactId: source(0)?.id ?? '', startMs: '0', endMs: announcementEndMs(source(0), 0), volumePercent: '0', visualPreset: DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET, headline: 'その情報、\n届いていますか？', narration: '十五秒で、しっかり伝える。' },
      { role: 'message', videoArtifactId: source(1)?.id ?? '', startMs: '0', endMs: announcementEndMs(source(1), 1), volumePercent: '0', visualPreset: DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET, headline: '大切なことを\nひと目で', narration: '大切な情報を、ひと目で。' },
      { role: 'cta', videoArtifactId: source(2)?.id ?? '', startMs: '0', endMs: announcementEndMs(source(2), 2), volumePercent: '0', visualPreset: DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET, headline: '詳しくは\nプロフィールへ', narration: '続きはプロフィールから。' },
    ],
    voice: '',
    rate: '0',
    pronunciations: [{ source: '', target: '' }],
    includeCaptioned: true,
    captionStylePreset: 'shorts_ja_large_v1',
    audioMixPreset: DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET,
    variant: 'captioned',
  };
};

const announcementDraftUsesQuickDefaults = (draft: AnnouncementRecipeDraft, artifacts: Artifact[]): boolean => {
  const expectedRoles: AnnouncementSceneRole[] = ['hook', 'message', 'cta'];
  return draft.schemaVersion === ANNOUNCEMENT_VIDEO_SCHEMA_VERSION
    && draft.templatePreset === ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET
    && draft.voice.trim() === ''
    && draft.rate.trim() !== ''
    && Number(draft.rate) === 0
    && draft.pronunciations.every((item) => item.source.trim() === '' && item.target.trim() === '')
    && draft.includeCaptioned
    && draft.captionStylePreset === 'shorts_ja_large_v1'
    && draft.audioMixPreset === 'narration_only_v1'
    && draft.variant === 'captioned'
    && draft.scenes.length === expectedRoles.length
    && draft.scenes.every((scene, index) => (
      scene.role === expectedRoles[index]
      && scene.startMs.trim() !== ''
      && Number(scene.startMs) === 0
      && scene.endMs === announcementEndMs(artifacts.find((artifact) => artifact.id === scene.videoArtifactId), index)
      && scene.volumePercent.trim() !== ''
      && Number(scene.volumePercent) === 0
      && scene.visualPreset === DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET
    ));
};

const announcementDraftFromRecord = (record: AnnouncementRecipeRecord): AnnouncementRecipeDraft => ({
  schemaVersion: ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
  name: record.recipe.name,
  templatePreset: ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET,
  scenes: record.recipe.scenes.map((scene) => ({
    ...scene,
    visualPreset: scene.visualPreset ?? DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
    startMs: String(scene.startMs),
    endMs: String(scene.endMs),
    volumePercent: String(scene.volumePercent),
  })),
  voice: record.recipe.voice ?? '',
  rate: String(record.recipe.rate),
  pronunciations: record.recipe.pronunciations.length > 0
    ? record.recipe.pronunciations.map((item) => ({ ...item }))
    : [{ source: '', target: '' }],
  includeCaptioned: record.recipe.includeCaptioned,
  captionStylePreset: record.recipe.captionStylePreset,
  audioMixPreset: record.recipe.audioMixPreset,
  variant: record.recipe.variant,
});

const announcementDraftSignature = (draft: AnnouncementRecipeDraft): string => JSON.stringify(draft);

const announcementDuplicateName = (name: string): string => {
  const suffix = '（コピー）';
  return `${name.slice(0, 120 - suffix.length)}${suffix}`;
};

const announcementExactJobFetchKey = (recipeVersionId: string, jobId: string): string =>
  `${recipeVersionId}\u0000${jobId}`;

const announcementRecipeHasAdvanced = (
  latest: AnnouncementRecipeRecord | undefined,
  localRevision: number,
  localVersionId: string,
): latest is AnnouncementRecipeRecord => Boolean(
  latest
  && (
    latest.revision > localRevision
    || (latest.revision === localRevision && latest.versionId !== localVersionId)
  )
);

type AnnouncementJobBinding = {
  recipeVersionId: string;
  job: Job;
};

function AnnouncementVideoPanel({ detail, jobs, onReload, onReloadStatus, onDirtyChange }: { detail: ProductionDetail; jobs: Job[]; onReload: (signal?: AbortSignal) => Promise<void>; onReloadStatus: (signal?: AbortSignal) => Promise<boolean>; onDirtyChange: (dirty: boolean) => void }) {
  const videoArtifacts = useMemo(() => detail.artifacts.filter(isAvailableVideoArtifact), [detail.artifacts]);
  const firstSaved = detail.announcementRecipes[0];
  const initialDraft = firstSaved ? announcementDraftFromRecord(firstSaved) : newAnnouncementDraft(videoArtifacts);
  const [editorMode, setEditorMode] = useState<AnnouncementEditorMode>(() => (
    announcementDraftUsesQuickDefaults(initialDraft, videoArtifacts) ? 'quick' : 'advanced'
  ));
  const [recipeId, setRecipeId] = useState(() => firstSaved?.id ?? newAnnouncementRecipeId());
  const [recipeRevision, setRecipeRevision] = useState(firstSaved?.revision ?? 0);
  const [recipeVersionId, setRecipeVersionId] = useState(firstSaved?.versionId ?? '');
  const [draft, setDraft] = useState<AnnouncementRecipeDraft>(() => initialDraft);
  const [savedSignature, setSavedSignature] = useState(() => announcementDraftSignature(initialDraft));
  const [savedRecord, setSavedRecord] = useState<AnnouncementRecipeRecord | undefined>(firstSaved);
  const [jobBinding, setJobBinding] = useState<AnnouncementJobBinding>();
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submissionUncertain, setSubmissionUncertain] = useState(false);
  const [automaticRetryReady, setAutomaticRetryReady] = useState(false);
  const [manualReconciliationAvailable, setManualReconciliationAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const submittingRef = useRef(false);
  const pollingRef = useRef(false);
  const detailPollTickRef = useRef(0);
  const exactJobFetchRef = useRef<string | undefined>(undefined);
  const executionGuardRef = useRef<AnnouncementSubmissionGuard | undefined>(undefined);
  const recoveryJobFetchRef = useRef<string | undefined>(undefined);
  const recoveryJobBlockedRef = useRef<string | undefined>(undefined);
  const [duplicateIntentRevision, setDuplicateIntentRevision] = useState(0);
  const reloadedTerminalJob = useRef<string | undefined>(undefined);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadAnnouncementDetail = useCallback(
    () => runAnnouncementRequestWithTimeout((signal) => onReload(signal)),
    [onReload],
  );

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key?.startsWith(ANNOUNCEMENT_DUPLICATE_INTENT_STORAGE_KEY)) {
        setDuplicateIntentRevision((current) => current + 1);
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const normalized = useMemo(() => normalizeAnnouncementVideoInput(draft), [draft]);
  const missingArtifactErrors = draft.scenes.flatMap((scene) => {
    if (!scene.videoArtifactId) return [];
    const artifact = videoArtifacts.find((item) => item.id === scene.videoArtifactId);
    if (!artifact) return [`${ANNOUNCEMENT_ROLE_META[scene.role].label}の動画artifactは現在利用できません。置き換えてください。`];
    const endMs = Number(scene.endMs);
    const sourceDurationMs = artifact.durationSeconds === undefined
      ? undefined
      : Math.floor(artifact.durationSeconds * 1_000);
    return sourceDurationMs !== undefined && Number.isFinite(endMs) && endMs > sourceDurationMs
      ? [`${ANNOUNCEMENT_ROLE_META[scene.role].label}の終了は素材尺 ${sourceDurationMs}ms 以内にしてください。`]
      : [];
  });
  const validationErrors = [...normalized.errors, ...missingArtifactErrors];
  const dirty = announcementDraftSignature(draft) !== savedSignature;
  const quickModeAvailable = announcementDraftUsesQuickDefaults(draft, videoArtifacts);
  const activeEditorMode: AnnouncementEditorMode = quickModeAvailable ? editorMode : 'advanced';
  const job = jobBinding?.recipeVersionId === recipeVersionId ? jobBinding.job : undefined;
  const currentExecutions = detail.announcementExecutions.filter((item) => item.recipeVersionId === recipeVersionId);
  const linkedJobIds = new Set(currentExecutions.map((item) => item.jobId));
  const linkedJobs = jobs.filter((candidate) => linkedJobIds.has(candidate.id));
  const reconciledJobs = useMemo(() => {
    const byId = new Map(linkedJobs.map((candidate) => [candidate.id, candidate]));
    if (job) byId.set(job.id, job);
    return [...byId.values()];
  }, [job, linkedJobs]);
  const visibleJob = newestPipelineJob(reconciledJobs.filter(isDetailedTestVideoExecutionActive)) ?? newestPipelineJob(reconciledJobs);
  const executionActive = reconciledJobs.some(isDetailedTestVideoExecutionActive);
  const runId = visibleJob?.result?.runId ?? visibleJob?.runId ?? currentExecutions[0]?.runId;
  const linkedRun = detail.runs.find((run) => run.id === runId);
  const isTerminal = visibleJob ? isTerminalStatus(visibleJob.status) && !executionActive : false;
  const displayedRecipeDurationMs = visibleJob?.result?.durationMs ?? normalized.outputDurationMs;
  const stageResults = Object.fromEntries(DETAILED_TEST_VIDEO_STEPS.map((step) => [step.key, detailedTestVideoStageResult(step, visibleJob, linkedRun)]));
  const qcAttempt = [...(linkedRun?.stageAttempts ?? [])].filter((attempt) => normalizeRequestedStage(attempt.stage) === 'qc').sort((left, right) => (right.createdAt ?? '').localeCompare(left.createdAt ?? ''))[0];
  const technicalVerdict = visibleJob?.result?.technicalVerdict ?? qcAttempt?.technicalVerdict;
  const finalArtifacts = [...(visibleJob?.result?.artifacts ?? []), ...detail.artifacts.filter((artifact) => runId && artifact.runId === runId)]
    .filter((artifact, index, all) => all.findIndex((candidate) => candidate.id === artifact.id) === index)
    .filter((artifact) => ['master-clean.mp4', 'master-captioned.mp4', 'technical-qc.json', 'ffprobe.json', 'manifest.json'].includes(artifact.name));
  const playerProps = useMemo(() => {
    if (validationErrors.some((error) => error.includes('artifact') || error.includes('素材尺') || error.includes('開始') || error.includes('終了'))) return undefined;
    try {
      return buildRemotionTimelineCompositionProps(
        { clips: normalized.detailedRequest.clips.map((clip) => ({ ...clip, volumePercent: 0 })) },
        (artifactId) => videoArtifacts.find((artifact) => artifact.id === artifactId)?.url ?? '',
      );
    } catch {
      return undefined;
    }
  }, [normalized.detailedRequest.clips, validationErrors, videoArtifacts]);

  const latestSelectedRecord = useMemo(
    () => detail.announcementRecipes.find((record) => record.id === recipeId),
    [detail.announcementRecipes, recipeId],
  );
  const staleRecipeVersion = announcementRecipeHasAdvanced(latestSelectedRecord, recipeRevision, recipeVersionId);
  const recipeSyncIdle = !saving && !submitting && !submissionUncertain && !busy && !executionActive;
  const exactExecutionJobId = currentExecutions[0]?.jobId;
  const exactExecutionJobLoaded = exactExecutionJobId
    ? reconciledJobs.some((candidate) => candidate.id === exactExecutionJobId)
    : false;
  const requestedDuplicateName = announcementDuplicateName(draft.name);
  const duplicateIntentMatch = recipeRevision > 0 && recipeVersionId
    ? {
        productionId: detail.id,
        sourceRecipeId: recipeId,
        sourceRecipeVersionId: recipeVersionId,
        sourceRevision: recipeRevision,
        name: requestedDuplicateName,
      }
    : undefined;
  const duplicateIntentStore = useMemo(
    () => duplicateIntentMatch
      ? inspectAnnouncementDuplicateIntentStore(browserAnnouncementDuplicateIntentStorage, duplicateIntentMatch)
      : { status: 'ready' as const },
    [detail.id, duplicateIntentRevision, recipeId, recipeRevision, recipeVersionId, requestedDuplicateName],
  );
  const pendingDuplicateIntent = duplicateIntentStore.status === 'ready'
    ? duplicateIntentStore.intent
    : undefined;

  useEffect(() => {
    if (!quickModeAvailable && editorMode !== 'advanced') setEditorMode('advanced');
  }, [editorMode, quickModeAvailable]);

  const loadRecord = useCallback((record: AnnouncementRecipeRecord) => {
    const nextDraft = announcementDraftFromRecord(record);
    setEditorMode(announcementDraftUsesQuickDefaults(nextDraft, videoArtifacts) ? 'quick' : 'advanced');
    setRecipeId(record.id);
    setRecipeRevision(record.revision);
    setRecipeVersionId(record.versionId);
    setDraft(nextDraft);
    setSavedSignature(announcementDraftSignature(nextDraft));
    setSavedRecord(record);
    setJobBinding(undefined);
    setMessage(undefined);
    setSubmissionUncertain(false);
    setAutomaticRetryReady(false);
    setManualReconciliationAvailable(false);
    exactJobFetchRef.current = undefined;
    executionGuardRef.current = undefined;
    recoveryJobFetchRef.current = undefined;
    recoveryJobBlockedRef.current = undefined;
    reloadedTerminalJob.current = undefined;
    detailPollTickRef.current = 0;
    setBusy(false);
  }, [videoArtifacts]);

  const retryGuardedExecution = useCallback(async (mode: 'automatic' | 'manual') => {
    const guard = executionGuardRef.current;
    if (!guard || guard.productionId !== detail.id || submittingRef.current) return;
    const request = mode === 'automatic'
      ? claimAnnouncementAutomaticRetry(guard)
      : announcementRetryRequest(guard);
    if (!request) return;

    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setAutomaticRetryReady(false);
    setManualReconciliationAvailable(false);
    recoveryJobBlockedRef.current = undefined;
    setMessage({
      type: 'info',
      text: mode === 'automatic'
        ? '初回照合で新しい受理記録を確認できなかったため、同じ保存済みrevisionを1回だけ自動再照合しています。'
        : '同じ保存済みrevisionだけを再照合しています。',
    });
    try {
      const submitted = await runAnnouncementRequestWithTimeout((signal) => api.executeAnnouncementRecipe(
        request.productionId,
        request.recipeId,
        request.recipeRevision,
        signal,
      ));
      if (executionGuardRef.current !== guard) return;
      executionGuardRef.current = undefined;
      recoveryJobFetchRef.current = undefined;
      recoveryJobBlockedRef.current = undefined;
      setSubmissionUncertain(false);
      setJobBinding({ recipeVersionId: guard.recipeVersionId, job: submitted });
      setMessage({
        type: submitted.status === 'failed' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? announcementVideoError(submitted.message ?? '同一revisionの告知動画Jobが失敗しました')
          : '同一revisionの応答を受信し、受理済みJobを確定しました。既存結果なら安全に再利用されます。',
      });
      await reloadAnnouncementDetail().catch(() => undefined);
      if (isTerminalStatus(submitted.status)) setBusy(false);
    } catch (error) {
      if (executionGuardRef.current !== guard) return;
      if (isReceivedAnnouncementClientError(error)) {
        executionGuardRef.current = undefined;
        recoveryJobFetchRef.current = undefined;
        recoveryJobBlockedRef.current = undefined;
        setSubmissionUncertain(false);
        setBusy(false);
        setMessage({ type: 'error', text: announcementVideoError(error) });
      } else {
        setSubmissionUncertain(true);
        setManualReconciliationAvailable(true);
        setMessage({
          type: 'error',
          text: `${announcementVideoError(error)} 同一revisionの応答も不明です。履歴では確定せず、必要なときだけ手動で再照合できます。`,
        });
        await reloadAnnouncementDetail().catch(() => undefined);
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  }, [detail.id, reloadAnnouncementDetail]);

  useEffect(() => {
    onDirtyChange(dirty);
  }, [dirty, onDirtyChange]);

  useEffect(() => {
    if (!pendingDuplicateIntent) return;
    const provenClone = detail.announcementRecipeVersions.find((record) => (
      announcementCloneMatchesIntent(record, pendingDuplicateIntent)
    ));
    if (!provenClone) return;
    try {
      clearAnnouncementDuplicateIntent(browserAnnouncementDuplicateIntentStorage, pendingDuplicateIntent);
      setDuplicateIntentRevision((current) => current + 1);
      setMessage({
        type: 'success',
        text: `前回応答が不明だった複製 ${pendingDuplicateIntent.newRecipeId} の保存を監査履歴で確認しました。`,
      });
    } catch (error) {
      setMessage({ type: 'error', text: `複製は監査履歴で確認できましたが、ブラウザの保留情報を消去できません：${error instanceof Error ? error.message : String(error)}` });
    }
  }, [detail.announcementRecipeVersions, pendingDuplicateIntent]);

  useEffect(() => {
    if (submissionUncertain || !exactExecutionJobId || exactExecutionJobLoaded || !recipeVersionId) return;
    const fetchKey = announcementExactJobFetchKey(recipeVersionId, exactExecutionJobId);
    if (exactJobFetchRef.current === fetchKey) return;
    let cancelled = false;
    exactJobFetchRef.current = fetchKey;
    void runAnnouncementRequestWithTimeout((signal) => api.job(exactExecutionJobId, signal)).then((loaded) => {
      if (cancelled || exactJobFetchRef.current !== fetchKey) return;
      setJobBinding({ recipeVersionId, job: loaded });
    }).catch(() => {
      if (!cancelled && exactJobFetchRef.current === fetchKey) exactJobFetchRef.current = undefined;
    });
    return () => {
      cancelled = true;
      if (exactJobFetchRef.current === fetchKey) exactJobFetchRef.current = undefined;
    };
  }, [exactExecutionJobId, exactExecutionJobLoaded, recipeVersionId, submissionUncertain]);

  useEffect(() => {
    if (!staleRecipeVersion || !latestSelectedRecord || dirty || !recipeSyncIdle) return;
    loadRecord(latestSelectedRecord);
    setMessage({ type: 'info', text: `外部更新された最新版 rev ${latestSelectedRecord.revision} を読み込みました。` });
  }, [dirty, latestSelectedRecord, loadRecord, recipeSyncIdle, staleRecipeVersion]);

  useEffect(() => {
    if (!submissionUncertain && !executionActive) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    let cancelled = false;
    setBusy(true);
    const poll = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const nextJobs = await runAnnouncementRequestWithTimeout((signal) => api.jobs(signal));
        if (cancelled) return;
        const next = visibleJob?.id ? nextJobs.find((candidate) => candidate.id === visibleJob.id) : undefined;
        if (next) setJobBinding({ recipeVersionId, job: next });
        detailPollTickRef.current += 1;
        if (submissionUncertain || detailPollTickRef.current === 1 || detailPollTickRef.current % 3 === 0) {
          await reloadAnnouncementDetail().catch(() => undefined);
        }
      } catch {
        // Keep the immutable version and last known job; the next bounded poll retries.
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [executionActive, isTerminal, recipeVersionId, reloadAnnouncementDetail, submissionUncertain, submitting, visibleJob?.id]);

  useEffect(() => {
    if (!submissionUncertain) return;
    const guard = executionGuardRef.current;
    if (!guard || guard.productionId !== detail.id) return;
    const candidates = selectAnnouncementRecoveryCandidates(detail.announcementExecutions, guard);
    // Only a new immutable link can prove that the ambiguous POST was admitted.
    // A known succeeded Job is intentionally audit-only and never clears this lock.
    const fresh = candidates.fresh;
    const canAccept = (candidateJob: Job, execution: typeof fresh[number]): boolean => (
      announcementJobMatchesExecution(candidateJob, execution, guard.productionId)
    );
    const inline = fresh
      .map((execution) => ({ execution, candidateJob: reconciledJobs.find((candidate) => candidate.id === execution.jobId) }))
      .find((candidate): candidate is { execution: typeof fresh[number]; candidateJob: Job } => (
        candidate.candidateJob !== undefined && canAccept(candidate.candidateJob, candidate.execution)
      ));
    const finish = (recoveredJob: Job) => {
      executionGuardRef.current = undefined;
      recoveryJobFetchRef.current = undefined;
      recoveryJobBlockedRef.current = undefined;
      setJobBinding({ recipeVersionId: guard.recipeVersionId, job: recoveredJob });
      setSubmissionUncertain(false);
      setAutomaticRetryReady(false);
      setManualReconciliationAvailable(false);
      setMessage({
        type: 'info',
        text: '応答は受信できませんでしたが、今回新しく記録された受理済みJobを厳密に照合しました。再送は行いません。',
      });
    };
    if (inline) {
      finish(inline.candidateJob);
      return;
    }
    const fetchToken = fresh.map(announcementExecutionKey).join('|');
    if (!fetchToken) {
      if (automaticRetryReady && !guard.automaticRetryAttempted) {
        void retryGuardedExecution('automatic');
      }
      return;
    }
    if (recoveryJobFetchRef.current === fetchToken || recoveryJobBlockedRef.current === fetchToken) return;
    recoveryJobFetchRef.current = fetchToken;
    void (async () => {
      let recovered = false;
      try {
        for (const execution of fresh) {
          try {
            const loaded = await runAnnouncementRequestWithTimeout((signal) => api.job(execution.jobId, signal));
            if (executionGuardRef.current !== guard) return;
            if (canAccept(loaded, execution)) {
              recovered = true;
              finish(loaded);
              return;
            }
          } catch {
            // Another exact candidate may still be available; never broaden scope.
          }
        }
      } finally {
        if (recoveryJobFetchRef.current === fetchToken) recoveryJobFetchRef.current = undefined;
        if (!recovered && executionGuardRef.current === guard) {
          recoveryJobBlockedRef.current = fetchToken;
          setAutomaticRetryReady(false);
          setManualReconciliationAvailable(true);
          setMessage({
            type: 'error',
            text: '新しい受理記録はありますが、対応するexact Jobを確認できませんでした。自動再送と同じ候補への追加GETを停止しました。監査状態の確認は継続し、必要なときだけ同一revisionを手動再照合できます。',
          });
        }
      }
    })();
  }, [automaticRetryReady, detail.announcementExecutions, detail.id, reconciledJobs, retryGuardedExecution, submissionUncertain, submitting]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void reloadAnnouncementDetail().catch(() => undefined);
  }, [isTerminal, reloadAnnouncementDetail, visibleJob]);

  const confirmDiscard = (): boolean => !dirty || window.confirm('未保存の変更を破棄しますか？');
  const startNew = () => {
    if (!confirmDiscard()) return;
    const next = newAnnouncementDraft(videoArtifacts);
    setEditorMode('quick');
    setRecipeId(newAnnouncementRecipeId());
    setRecipeRevision(0);
    setRecipeVersionId('');
    setDraft(next);
    setSavedSignature(announcementDraftSignature(next));
    setSavedRecord(undefined);
    setJobBinding(undefined);
    setMessage(undefined);
    setSubmissionUncertain(false);
    setAutomaticRetryReady(false);
    setManualReconciliationAvailable(false);
    exactJobFetchRef.current = undefined;
    executionGuardRef.current = undefined;
    recoveryJobFetchRef.current = undefined;
    recoveryJobBlockedRef.current = undefined;
    reloadedTerminalJob.current = undefined;
    detailPollTickRef.current = 0;
    setBusy(false);
  };
  const selectSaved = (id: string) => {
    const record = detail.announcementRecipes.find((item) => item.id === id);
    if (record && confirmDiscard()) loadRecord(record);
  };
  const updateScene = <Key extends keyof AnnouncementSceneDraft>(index: number, key: Key, value: AnnouncementSceneDraft[Key]) => {
    setDraft((current) => ({ ...current, scenes: current.scenes.map((scene, sceneIndex) => sceneIndex === index ? { ...scene, [key]: value } : scene) }));
  };
  const selectSceneArtifact = (index: number, artifactId: string) => {
    const artifact = videoArtifacts.find((item) => item.id === artifactId);
    setDraft((current) => ({
      ...current,
      scenes: current.scenes.map((scene, sceneIndex) => sceneIndex === index ? {
        ...scene,
        videoArtifactId: artifactId,
        startMs: '0',
        endMs: announcementEndMs(artifact, index),
      } : scene),
    }));
  };
  const updatePronunciation = (index: number, key: 'source' | 'target', value: string) => {
    setDraft((current) => ({ ...current, pronunciations: current.pronunciations.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) }));
  };

  const save = async (): Promise<AnnouncementRecipeRecord | undefined> => {
    if (staleRecipeVersion) {
      setMessage({ type: 'error', text: 'このrecipeには新しいrevisionがあります。最新版を読み込んでから保存してください。' });
      return undefined;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return undefined;
    }
    setSaving(true);
    setMessage({ type: 'info', text: '告知recipeを監査履歴へ保存しています。' });
    try {
      const saved = await runIdempotentAnnouncementMutation(
        (signal) => api.saveAnnouncementRecipe(
          detail.id,
          recipeId,
          recipeRevision,
          normalized.recipe,
          signal,
        ),
        () => setMessage({ type: 'info', text: '保存応答が不明なため、同じrecipe ID・expected revision・内容を1回だけ再照合しています。' }),
      );
      const nextDraft = announcementDraftFromRecord(saved);
      setRecipeId(saved.id);
      setRecipeRevision(saved.revision);
      setRecipeVersionId(saved.versionId);
      setDraft(nextDraft);
      setSavedSignature(announcementDraftSignature(nextDraft));
      setSavedRecord(saved);
      setJobBinding(undefined);
      setAutomaticRetryReady(false);
      setManualReconciliationAvailable(false);
      exactJobFetchRef.current = undefined;
      executionGuardRef.current = undefined;
      recoveryJobFetchRef.current = undefined;
      recoveryJobBlockedRef.current = undefined;
      reloadedTerminalJob.current = undefined;
      detailPollTickRef.current = 0;
      setMessage({ type: 'success', text: `recipe rev ${saved.revision} を保存しました。` });
      await reloadAnnouncementDetail().catch(() => undefined);
      return saved;
    } catch (error) {
      setMessage({ type: 'error', text: announcementVideoError(error) });
      await reloadAnnouncementDetail().catch(() => undefined);
      return undefined;
    } finally {
      setSaving(false);
    }
  };

  const duplicate = async () => {
    if (dirty) {
      setMessage({ type: 'error', text: '未保存の変更があります。先に保存してから複製してください。' });
      return;
    }
    if (recipeRevision < 1 || !recipeVersionId) {
      setMessage({ type: 'error', text: '先にrecipeを保存してください。' });
      return;
    }
    setSaving(true);
    let intent = pendingDuplicateIntent;
    let intentPersisted = false;
    try {
      if (!duplicateIntentMatch) throw new Error('複製元のimmutable identityを確定できません。');
      if (!intent) {
        intent = {
          schemaVersion: 1,
          ...duplicateIntentMatch,
          newRecipeId: await deterministicAnnouncementCloneRecipeId(duplicateIntentMatch),
          createdAt: new Date().toISOString(),
        } satisfies AnnouncementDuplicateIntent;
      }
      const persistedIntent = await persistAnnouncementDuplicateIntent(browserAnnouncementDuplicateIntentStorage, intent);
      intent = persistedIntent;
      intentPersisted = true;
      setDuplicateIntentRevision((current) => current + 1);
      const cloned = await runIdempotentAnnouncementMutation(
        (signal) => api.duplicateAnnouncementRecipe(
          persistedIntent.productionId,
          persistedIntent.sourceRecipeId,
          persistedIntent.sourceRevision,
          persistedIntent.newRecipeId,
          persistedIntent.name,
          signal,
        ),
        () => setMessage({ type: 'info', text: '複製応答が不明なため、新しいIDを作らず同じ複製IDを1回だけ再照合しています。' }),
      );
      if (!announcementCloneMatchesIntent(cloned, persistedIntent)) {
        throw new Error('複製応答が事前発行したID・source version・名前と一致しません。');
      }
      clearAnnouncementDuplicateIntent(browserAnnouncementDuplicateIntentStorage, persistedIntent);
      setDuplicateIntentRevision((current) => current + 1);
      loadRecord(cloned);
      setMessage({ type: 'success', text: '元recipeを変更せず、編集用コピーを作成しました。' });
      await reloadAnnouncementDetail().catch(() => undefined);
    } catch (error) {
      setMessage({
        type: 'error',
        text: intentPersisted
          ? `${announcementVideoError(error)} 複製ID ${intent?.newRecipeId ?? '（不明）'} は保持しました。同じIDで再照合するか、明示的に保留を破棄してください。`
          : `${announcementVideoError(error)} 安全な複製IDをブラウザへ保存できなかったため、複製POSTは送信していません。`,
      });
      await reloadAnnouncementDetail().catch(() => undefined);
    } finally {
      setSaving(false);
    }
  };

  const discardPendingDuplicate = () => {
    if (!pendingDuplicateIntent) return;
    if (!window.confirm('この複製がserverで受理済みの場合、保存済みrecipe自体は削除されません。ブラウザに保持した複製IDだけを破棄しますか？')) return;
    try {
      clearAnnouncementDuplicateIntent(browserAnnouncementDuplicateIntentStorage, pendingDuplicateIntent);
      setDuplicateIntentRevision((current) => current + 1);
      setMessage({ type: 'info', text: `保留中の複製ID ${pendingDuplicateIntent.newRecipeId} を明示的に破棄しました。` });
    } catch (error) {
      setMessage({ type: 'error', text: `保留中の複製IDを破棄できません：${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const discardCorruptDuplicateStore = () => {
    if (!duplicateIntentMatch) return;
    if (!window.confirm('壊れた保留情報にserver受理済みの複製が含まれていても、保存済みrecipe自体は削除されません。ブラウザの保留情報をすべて破棄しますか？')) return;
    try {
      clearAnnouncementDuplicateIntentStore(browserAnnouncementDuplicateIntentStorage, duplicateIntentMatch);
      setDuplicateIntentRevision((current) => current + 1);
      setMessage({ type: 'info', text: '壊れた複製保留情報を明示的に破棄しました。' });
    } catch (error) {
      setMessage({ type: 'error', text: `複製保留情報を破棄できません：${error instanceof Error ? error.message : String(error)}` });
    }
  };

  const saveAndExecute = async () => {
    if (submittingRef.current || executionActive || submissionUncertain) return;
    if (staleRecipeVersion) {
      setMessage({ type: 'error', text: 'このrecipeには新しいrevisionがあります。最新版を読み込んでから実行してください。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setJobBinding(undefined);
    try {
      const saved = dirty || recipeRevision < 1 ? await save() : savedRecord;
      if (!saved) {
        setBusy(false);
        return;
      }
      executionGuardRef.current = createAnnouncementSubmissionGuard(detail.id, saved, detail.announcementExecutions);
      recoveryJobFetchRef.current = undefined;
      recoveryJobBlockedRef.current = undefined;
      setAutomaticRetryReady(false);
      setManualReconciliationAvailable(false);
      setMessage({ type: 'info', text: 'SAPI → Remotion → 合成 → 技術QCをキューへ登録しています。' });
      const submitted = await runAnnouncementRequestWithTimeout((signal) => api.executeAnnouncementRecipe(
        detail.id,
        saved.id,
        saved.revision,
        signal,
      ));
      executionGuardRef.current = undefined;
      setAutomaticRetryReady(false);
      setManualReconciliationAvailable(false);
      setJobBinding({ recipeVersionId: saved.versionId, job: submitted });
      setMessage({ type: submitted.status === 'failed' ? 'error' : 'success', text: submitted.status === 'failed' ? announcementVideoError(submitted.message ?? '告知動画Jobが失敗しました') : '告知動画Jobを受理しました。既存結果が同一なら再レンダーせず再利用します。' });
      await reloadAnnouncementDetail().catch(() => undefined);
      if (isTerminalStatus(submitted.status)) setBusy(false);
    } catch (error) {
      if (isReceivedAnnouncementClientError(error)) {
        executionGuardRef.current = undefined;
        recoveryJobFetchRef.current = undefined;
        recoveryJobBlockedRef.current = undefined;
        setSubmissionUncertain(false);
        setAutomaticRetryReady(false);
        setManualReconciliationAvailable(false);
        setBusy(false);
        setMessage({ type: 'error', text: announcementVideoError(error) });
      } else {
        const guard = executionGuardRef.current;
        setSubmissionUncertain(true);
        setAutomaticRetryReady(false);
        setManualReconciliationAvailable(false);
        await reloadAnnouncementDetail().catch(() => undefined);
        if (executionGuardRef.current === guard) {
          setAutomaticRetryReady(true);
          setMessage({ type: 'error', text: `${announcementVideoError(error)} 新しい受理記録を1回照合し、なければ同じ保存済みrevisionだけを自動再照合します。各API照合は${ANNOUNCEMENT_REQUEST_TIMEOUT_MS / 1_000}秒で打ち切ります。` });
        }
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const operationLocked = saving || submitting || submissionUncertain || busy || executionActive;
  const formLocked = operationLocked || Boolean(pendingDuplicateIntent) || duplicateIntentStore.status !== 'ready';
  return (
    <div className="announcement-grid">
      <div>
        <VideoAssetImportPanel productionId={detail.id} currentVideoCount={videoArtifacts.length} onReload={onReloadStatus} />
        <section className={`panel announcement-panel editor-${activeEditorMode}`}>
          {activeEditorMode === 'quick' ? (
            <><div className="panel-header"><div><span className="section-kicker">QUICK CREATE</span><h3>かんたん作成</h3></div><span className="tag">{formatMilliseconds(normalized.outputDurationMs)} · 縦型 · 費用0円</span></div><p className="panel-lead">動画を3つ選び、伝える言葉を入れるだけ。保存、ローカル音声、字幕、編集、技術QCまでまとめて進めます。</p></>
          ) : (
            <><div className="panel-header"><div><span className="section-kicker">ANNOUNCEMENT VIDEO V1</span><h3>15秒告知動画・詳細設定</h3></div><span className="tag">既存素材 · 費用0円</span></div><p className="panel-lead">HOOK → MESSAGE → CTAの3シーンを調整し、大見出し、ナレーション、字幕、fade、音声mix、技術QCまで一括生成します。</p><div className="local-pipeline-policy" role="note"><strong>使える範囲を閉じた実用テンプレート</strong><p>10〜20秒（推奨15秒）、縦1080×1920、固定250ms fadeです。大見出しは安全域内の上・中央だけを使い、字幕との下端衝突を避けます。ナレーション必須、BGM・ロゴ画像はv1対象外です。</p></div></>
          )}

          <fieldset className="announcement-mode-picker" disabled={formLocked}>
            <legend>作り方</legend>
            <label className={activeEditorMode === 'quick' ? 'is-selected' : ''}>
              <input type="radio" name="announcement-editor-mode" value="quick" checked={activeEditorMode === 'quick'} disabled={formLocked || !quickModeAvailable} onChange={() => setEditorMode('quick')} />
              <span><strong>かんたん作成</strong><small>素材と言葉だけを入力</small></span>
            </label>
            <label className={activeEditorMode === 'advanced' ? 'is-selected' : ''}>
              <input type="radio" name="announcement-editor-mode" value="advanced" checked={activeEditorMode === 'advanced'} disabled={formLocked} onChange={() => setEditorMode('advanced')} />
              <span><strong>詳細設定</strong><small>時間・音・補正も調整</small></span>
            </label>
          </fieldset>
          {!quickModeAvailable && <div className="quick-create-advanced-note" role="note"><strong>この内容には詳細設定が含まれています</strong><p>trim、素材音、映像補正、音声、字幕のいずれかが、かんたん作成の安全な既定値と異なります。設定を隠したまま上書きしないよう、詳細設定で表示しています。「新規」でかんたん設定へ戻せます。</p></div>}

          {duplicateIntentStore.status !== 'ready' && <div className="inline-message is-error" role="alert"><p>{duplicateIntentStore.status === 'corrupt' ? 'ブラウザの複製保留情報が壊れています。誤って新しいIDを発行しないようrecipe操作を停止しました。' : 'ブラウザのlocalStorageを利用できないため、安全な複製IDを保持できません。ブラウザ設定を確認してください。'}</p>{duplicateIntentStore.status === 'corrupt' && <button className="button button-ghost" type="button" disabled={operationLocked} onClick={discardCorruptDuplicateStore}>壊れた保留情報を破棄</button>}</div>}
          {pendingDuplicateIntent && <div className="inline-message is-error" role="alert"><p>複製ID <code>{pendingDuplicateIntent.newRecipeId}</code> の応答が未確定です。画面移動や再読込後も同じIDを使い、二重作成を防ぎます。</p><div className="button-row"><button className="button button-secondary" type="button" disabled={operationLocked || dirty} onClick={() => void duplicate()}>同じ複製IDで再照合</button><button className="button button-ghost" type="button" disabled={operationLocked} onClick={discardPendingDuplicate}>保留中の複製を破棄</button></div></div>}
          {staleRecipeVersion && latestSelectedRecord && <div className="inline-message is-error" role="alert"><p>この画面は rev {recipeRevision} を編集中ですが、保存先には最新版 rev {latestSelectedRecord.revision} があります。内容を自動で上書きせず、保存・実行を停止しました。</p><button className="button button-secondary" type="button" disabled={!recipeSyncIdle} onClick={() => { if (!confirmDiscard()) return; loadRecord(latestSelectedRecord); setMessage({ type: 'info', text: `最新版 rev ${latestSelectedRecord.revision} を読み込みました。` }); }}>最新版を読み込む</button></div>}

          <div className="announcement-recipe-browser">
            <label className="field">
              <span>{activeEditorMode === 'quick' ? '保存した内容から続ける' : '保存済みrecipe'}</span>
              <select value={detail.announcementRecipes.some((item) => item.id === recipeId) ? recipeId : ''} disabled={formLocked} onChange={(event) => event.target.value ? selectSaved(event.target.value) : startNew()}>
                <option value="">新しい動画</option>
                {detail.announcementRecipes.map((item) => <option key={item.id} value={item.id}>{item.id === recipeId && staleRecipeVersion ? `${draft.name} · 編集中 rev ${recipeRevision} / 最新 rev ${item.revision}` : `${item.recipe.name} · rev ${item.revision}`}</option>)}
              </select>
            </label>
            <button className="button button-secondary" type="button" onClick={startNew} disabled={formLocked}>{activeEditorMode === 'quick' ? '新しく作る' : '新規'}</button>
            <span className={dirty ? 'is-dirty' : 'is-saved'}>{dirty ? '入力内容は未保存' : recipeRevision > 0 ? `保存済み rev ${recipeRevision}` : '新しい動画'}</span>
            {activeEditorMode === 'advanced' && <code>{recipeId}</code>}
          </div>
          <p className="sr-only" aria-live="polite">{activeEditorMode === 'advanced' && !quickModeAvailable ? '選択した内容には詳細設定が含まれるため、詳細設定を表示しました。' : ''}</p>

          {activeEditorMode === 'quick' ? (
            <QuickCreateForm
              recipeName={draft.name}
              scenes={draft.scenes}
              videoArtifacts={videoArtifacts}
              outputDurationMs={normalized.outputDurationMs}
              validationErrors={validationErrors}
              disabled={formLocked}
              onRecipeNameChange={(value) => setDraft((current) => ({ ...current, name: value }))}
              onSceneArtifactChange={selectSceneArtifact}
              onSceneHeadlineChange={(index, value) => updateScene(index, 'headline', value)}
              onSceneNarrationChange={(index, value) => updateScene(index, 'narration', value)}
            />
          ) : (
            <>
              <div className="announcement-recipe-actions button-row">
                <button className="button button-secondary" type="button" onClick={() => void save()} disabled={formLocked || Boolean(pendingDuplicateIntent) || staleRecipeVersion || validationErrors.length > 0}>{saving ? '保存中…' : '保存'}</button>
                <button className="button button-secondary" type="button" onClick={() => void duplicate()} disabled={formLocked || recipeRevision < 1 || dirty} title={dirty ? '先に未保存の変更を保存してください' : undefined}>複製して編集</button>
              </div>
              <label className="field"><span>recipe名</span><input maxLength={120} value={draft.name} disabled={formLocked} onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))} /></label>
              <div className="announcement-scene-list">{draft.scenes.map((scene, index) => {
                const meta = ANNOUNCEMENT_ROLE_META[scene.role];
                const artifact = videoArtifacts.find((item) => item.id === scene.videoArtifactId);
                return <article className={`announcement-scene role-${scene.role}`} key={scene.role}>
                  <div className="announcement-scene-heading"><span>{meta.index}</span><div><strong>{meta.label}</strong><small>{meta.guide}</small></div><em>{index < 2 ? 'fade 250ms' : 'END'}</em></div>
                  <label className="field"><span>動画artifact</span><select value={scene.videoArtifactId} disabled={formLocked || videoArtifacts.length === 0} onChange={(event) => selectSceneArtifact(index, event.target.value)}><option value="">動画artifactを選択</option>{scene.videoArtifactId && !videoArtifacts.some((item) => item.id === scene.videoArtifactId) && <option value={scene.videoArtifactId}>[利用不可] {scene.videoArtifactId}</option>}{videoArtifacts.map((item) => <option key={item.id} value={item.id}>{item.name} · {formatBytes(item.sizeBytes)}</option>)}</select></label>
                  <div className="announcement-time-grid"><label className="field"><span>開始（ms）</span><input type="number" min="0" max="60000" step="1" value={scene.startMs} disabled={formLocked} onChange={(event) => updateScene(index, 'startMs', event.target.value)} /></label><label className="field"><span>終了（ms）</span><input type="number" min="0" max="60000" step="1" value={scene.endMs} disabled={formLocked} onChange={(event) => updateScene(index, 'endMs', event.target.value)} /></label><label className="field"><span>素材音量（%）</span><input type="number" min="0" max="100" step="1" value={scene.volumePercent} disabled={formLocked} onChange={(event) => updateScene(index, 'volumePercent', event.target.value)} /></label></div>
                  <label className="field"><span>映像補正preset</span><select value={scene.visualPreset} disabled={formLocked} onChange={(event) => updateScene(index, 'visualPreset', event.target.value as LocalRemotionTimelineVisualPreset)}><option value="preserve_v1">補正なし（preserve_v1）</option><option value="h3_low_res_sharp_v1">H3低解像度を鮮明化</option></select><small className="field-help">固定強度です。完成artifactで効果を確認します。</small></label>
                  <label className="field"><span>大見出し（2行まで）</span><textarea rows={2} maxLength={80} value={scene.headline} disabled={formLocked} onChange={(event) => updateScene(index, 'headline', event.target.value)} /></label>
                  <label className="field"><span>ナレーション（1文）</span><textarea rows={2} maxLength={200} value={scene.narration} disabled={formLocked} onChange={(event) => updateScene(index, 'narration', event.target.value)} /></label>
                  <div className="timeline-artifact-meta"><span>source尺 {formatDuration(artifact?.durationSeconds)}</span><span>大見出し {scene.role === 'message' ? '上' : '中央'}</span></div>
                </article>;
              })}</div>
              <details className="announcement-advanced"><summary>音声・字幕の詳細設定</summary><div className="announcement-advanced-body">
                <div className="local-pipeline-form-row"><label className="field"><span>音声（任意）</span><input value={draft.voice} disabled={formLocked} onChange={(event) => setDraft((current) => ({ ...current, voice: event.target.value }))} placeholder="既定音声" /></label><label className="field"><span>読み上げ速度</span><input type="number" min="-10" max="10" step="1" value={draft.rate} disabled={formLocked} onChange={(event) => setDraft((current) => ({ ...current, rate: event.target.value }))} /></label></div>
                <fieldset className="pronunciation-fieldset"><legend>発音置換（任意）</legend>{draft.pronunciations.map((item, index) => <div className="pronunciation-row" key={index}><input value={item.source} disabled={formLocked} onChange={(event) => updatePronunciation(index, 'source', event.target.value)} placeholder="表記" /><span aria-hidden="true">→</span><input value={item.target} disabled={formLocked} onChange={(event) => updatePronunciation(index, 'target', event.target.value)} placeholder="読み" /><button className="button button-ghost" type="button" onClick={() => setDraft((current) => ({ ...current, pronunciations: current.pronunciations.length === 1 ? current.pronunciations : current.pronunciations.filter((_, itemIndex) => itemIndex !== index) }))} disabled={formLocked || draft.pronunciations.length === 1}>削除</button></div>)}<button className="button button-secondary" type="button" onClick={() => setDraft((current) => ({ ...current, pronunciations: [...current.pronunciations, { source: '', target: '' }] }))} disabled={formLocked}>＋置換を追加</button></fieldset>
                <label className="toggle-field"><input type="checkbox" checked={draft.includeCaptioned} disabled={formLocked} onChange={(event) => { const enabled = event.target.checked; setDraft((current) => ({ ...current, includeCaptioned: enabled, captionStylePreset: enabled ? 'shorts_ja_large_v1' : 'studio_default_v1', variant: enabled ? 'captioned' : 'clean' })); }} /><span><strong>ナレーション字幕を焼き込む</strong><small>大見出しとは別に、読み上げ文を下部へ表示します。</small></span></label>
                <div className="detailed-test-output-grid"><label className="field"><span>字幕preset</span><select value={draft.captionStylePreset} disabled={formLocked || !draft.includeCaptioned} onChange={(event) => setDraft((current) => ({ ...current, captionStylePreset: event.target.value as LocalAssemblyCaptionStylePreset }))}><option value="shorts_ja_large_v1">Shorts向け大字幕</option><option value="studio_default_v1">標準字幕</option></select></label><label className="field"><span>音声mix</span><select value={draft.audioMixPreset} disabled={formLocked} onChange={(event) => setDraft((current) => ({ ...current, audioMixPreset: event.target.value as LocalAssemblyAudioMixPreset }))}><option value="narration_only_v1">ナレーションのみ</option><option value="source_under_narration_v1">素材25%＋ナレーション100%</option></select></label><label className="field"><span>QC対象</span><select value={draft.variant} disabled={formLocked || !draft.includeCaptioned} onChange={(event) => setDraft((current) => ({ ...current, variant: event.target.value as LocalQcVariant }))}><option value="captioned">captioned</option><option value="clean">clean</option></select></label></div>
              </div></details>
            </>
          )}
          {validationErrors.length > 0 && <div className="validation-list" role="status" aria-live="polite">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button announcement-execute" type="button" onClick={() => void saveAndExecute()} disabled={formLocked || Boolean(pendingDuplicateIntent) || staleRecipeVersion || validationErrors.length > 0}>{saving ? 'recipe保存中…' : submitting ? 'Job登録中…' : executionActive || busy ? activeEditorMode === 'quick' ? '作成状況を確認中…' : '告知動画を監視中…' : activeEditorMode === 'quick' ? `この内容で動画を作る（${formatMilliseconds(normalized.outputDurationMs)}）` : '保存して告知動画を作る'}</button>
          {submissionUncertain && manualReconciliationAvailable && <button className="button button-secondary full-button" type="button" disabled={submitting} onClick={() => void retryGuardedExecution('manual')}>{submitting ? '同一revisionを再照合中…' : '同一revisionを再照合'}</button>}
          {message && <div className={`inline-message is-${message.type}`} role={message.type === 'error' ? 'alert' : 'status'}>{message.text}</div>}
        </section>
      </div>
      <aside>
        <section className="panel compact-panel remotion-player-panel"><div className="panel-header"><div><span className="section-kicker">TEMPLATE PLAYER</span><h3>3シーンpreview</h3></div><span className="tag">1080×1920</span></div>{playerProps ? <div className="remotion-player-shell"><Player component={TimelineComposition} inputProps={playerProps} durationInFrames={playerProps.durationInFrames} compositionWidth={1080} compositionHeight={1920} fps={24} controls loop style={{ width: '100%', aspectRatio: '9 / 16' }} /></div> : <p className="muted">3シーンの入力を整えるとpreviewできます。</p>}<p className="gate-separation-note">previewは映像補正presetを再現せず、素材と大見出しのみ・消音です。鮮明化、ナレーション、焼き込み字幕、最終mixは完成masterを正として確認します。</p></section>
        <section className="panel compact-panel local-pipeline-progress-panel" aria-live="polite" aria-busy={executionActive}><div className="panel-header"><div><span className="section-kicker">ANNOUNCEMENT JOB</span><h3>4段階の進捗</h3></div>{visibleJob ? <StatusBadge status={visibleJob.status} label={executionActive ? '監視中' : jobStatusLabel(visibleJob.status)} /> : <span className="muted">未実行</span>}</div><ol className="local-pipeline-progress">{DETAILED_TEST_VIDEO_STEPS.map((step, index) => { const item = stageResults[step.key] as LocalPipelineStageResult | undefined; const status = item?.status ?? (visibleJob ? 'pending' : 'unknown'); return <li className={`local-pipeline-step step-${status}`} key={step.key}><div className="local-pipeline-step-rail"><span>{index + 1}</span></div><div className="local-pipeline-step-body"><div><strong>{step.label}</strong><StatusBadge status={status} label={item ? jobStatusLabel(status) : '未開始'} /></div>{item?.progress !== undefined && <div className="progress-track"><span style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }} /></div>}<small>{item?.jobId ? `Job ${item.jobId}` : item?.stageAttemptId ? `Attempt ${item.stageAttemptId}` : 'stage記録を待機中'}{item?.cacheHit === undefined ? '' : item.cacheHit ? ' · cache hit' : ' · cache miss'}</small>{item?.message && <p>{item.message}</p>}</div></li>; })}</ol><dl className="narration-metrics"><div><dt>Top Job</dt><dd className="mono">{visibleJob?.id ?? '—'}</dd></div><div><dt>Run</dt><dd className="mono">{runId ?? '—'}</dd></div><div><dt>recipe</dt><dd>rev {recipeRevision || '—'}</dd></div><div><dt>完成尺</dt><dd>{formatMilliseconds(displayedRecipeDurationMs)}</dd></div></dl></section>
        <section className="panel compact-panel local-pipeline-result-panel"><div className="panel-header"><div><span className="section-kicker">FINAL RESULT</span><h3>master・QC</h3></div>{technicalVerdict ? <StatusBadge status={technicalVerdict === 'pass' ? 'succeeded' : 'failed'} label={`technical verdict: ${technicalVerdict}`} /> : <span className="muted">判定待ち</span>}</div>{finalArtifacts.length === 0 ? <p className="muted">最終artifactはまだありません。</p> : <div className="narration-artifact-list">{finalArtifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer"><strong>{artifact.name}</strong><span>{artifact.kind} · {formatBytes(artifact.sizeBytes)} ↗</span></a>)}</div>}<p className="gate-separation-note">safe-areaは固定presetの技術条件です。文字の読みやすさ、表現、権利、公開可否は完成masterを目視確認してください。</p></section>
      </aside>
    </div>
  );
}

function DetailedTestVideoPanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const videoArtifacts = useMemo(
    () => detail.artifacts.filter(isAvailableVideoArtifact),
    [detail.artifacts],
  );
  const [clips, setClips] = useState<TimelineDraftClip[]>([]);
  const initializedClips = useRef(false);
  const [script, setScript] = useState('');
  const [voice, setVoice] = useState('');
  const [rate, setRate] = useState('0');
  const [pronunciations, setPronunciations] = useState([{ source: '', target: '' }]);
  const [includeCaptioned, setIncludeCaptioned] = useState(true);
  const [captionStylePreset, setCaptionStylePreset] = useState<LocalAssemblyCaptionStylePreset>(RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET);
  const [audioMixPreset, setAudioMixPreset] = useState<LocalAssemblyAudioMixPreset>(DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET);
  const [variant, setVariant] = useState<LocalQcVariant>('captioned');
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submissionUncertain, setSubmissionUncertain] = useState(false);
  const submittingRef = useRef(false);
  const pollingRef = useRef(false);
  const submissionGuardRef = useRef<DetailedTestVideoSubmissionGuard | undefined>(undefined);
  const reloadedTerminalJob = useRef<string | undefined>(undefined);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();

  useEffect(() => {
    if (initializedClips.current || videoArtifacts.length === 0) return;
    initializedClips.current = true;
    setClips([timelineDraftForArtifact(videoArtifacts[0])]);
  }, [videoArtifacts]);

  const matchingJobs = useMemo(
    () => {
      const announcementJobIds = new Set(detail.announcementExecutions.map((item) => item.jobId));
      return jobs.filter((candidate) => isDetailedTestVideoJobForSelection(candidate, { productionId: detail.id }) && !announcementJobIds.has(candidate.id));
    },
    [detail.announcementExecutions, detail.id, jobs],
  );
  const reconciledJobs = useMemo(() => {
    const byId = new Map(matchingJobs.map((candidate) => [candidate.id, candidate]));
    // The 2-second local poll is newer than the parent dashboard snapshot.
    // Replace the same ID so a stale pending copy cannot outlive terminal truth.
    if (job) byId.set(job.id, job);
    return [...byId.values()];
  }, [job, matchingJobs]);
  const visibleJob = newestPipelineJob(reconciledJobs.filter((candidate) => isDetailedTestVideoExecutionActive(candidate)))
    ?? newestPipelineJob(reconciledJobs);
  const visibleJobId = visibleJob?.id;
  const executionActive = reconciledJobs.some((candidate) => isDetailedTestVideoExecutionActive(candidate));
  const runId = visibleJob?.result?.runId ?? visibleJob?.runId;
  const linkedRun = detail.runs.find((run) => run.id === runId);
  const isTerminal = visibleJob ? isTerminalStatus(visibleJob.status) && !executionActive : false;

  const remotionDraft = useMemo(() => clips.map((clip, index) => ({
    videoArtifactId: clip.videoArtifactId,
    startMs: clip.startMs,
    endMs: clip.endMs,
    volumePercent: clip.volumePercent,
    visualPreset: clip.visualPreset,
    transitionToNext: index === clips.length - 1 || !clip.transitionEnabled ? null : {
      type: 'fade',
      durationMs: clip.transitionDurationMs,
    },
    overlay: !clip.overlayEnabled ? null : {
      text: clip.overlayText,
      startMs: clip.overlayStartMs,
      endMs: clip.overlayEndMs,
      position: clip.overlayPosition,
      stylePreset: 'shorts_ja_large_v1',
    },
  })), [clips]);
  const formInput = useMemo(() => ({
    schemaVersion: DETAILED_TEST_VIDEO_SCHEMA_VERSION,
    clips: remotionDraft,
    script,
    voice,
    rate,
    pronunciations: pronunciations.some((item) => item.source.trim() || item.target.trim()) ? pronunciations : undefined,
    includeCaptioned,
    captionStylePreset,
    audioMixPreset,
    variant,
  }), [audioMixPreset, captionStylePreset, includeCaptioned, pronunciations, rate, remotionDraft, script, variant, voice]);
  const normalizedInput = useMemo(() => normalizeDetailedTestVideoInput(formInput), [formInput]);
  const displayedRecipeDurationMs = visibleJob?.result?.durationMs ?? normalizedInput.outputDurationMs;
  const missingArtifactErrors = clips.flatMap((clip, index) => clip.videoArtifactId && !videoArtifacts.some((artifact) => artifact.id === clip.videoArtifactId)
    ? [`カット${index + 1}の動画artifactはこの制作で利用できません。`]
    : []);
  const validationErrors = [...normalizedInput.errors, ...missingArtifactErrors];
  const hasClipValidationError = validationErrors.some((error) => error.includes('カット'));
  const playerProps = useMemo(() => {
    if (hasClipValidationError) return undefined;
    try {
      return buildRemotionTimelineCompositionProps(
        { clips: normalizedInput.request.clips },
        (artifactId) => videoArtifacts.find((artifact) => artifact.id === artifactId)?.url ?? '',
      );
    } catch {
      return undefined;
    }
  }, [hasClipValidationError, normalizedInput.request.clips, videoArtifacts]);

  useEffect(() => {
    if (!submissionUncertain && (!visibleJobId || !executionActive)) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    let cancelled = false;
    setBusy(true);
    const poll = async () => {
      if (pollingRef.current) return;
      pollingRef.current = true;
      try {
        const nextJobs = await api.jobs();
        if (cancelled) return;
        const announcementJobIds = new Set(detail.announcementExecutions.map((item) => item.jobId));
        const scoped = nextJobs.filter((candidate) => (
          isDetailedTestVideoJobForSelection(candidate, { productionId: detail.id })
          && !announcementJobIds.has(candidate.id)
        ));
        const guard = submissionGuardRef.current;
        const reconciled = submissionUncertain && guard?.productionId === detail.id
          ? newestPipelineJob(scoped.filter((candidate) => detailedTestVideoJobMatchesSubmissionGuard(candidate, guard)))
          : undefined;
        const next = reconciled
          ?? (visibleJobId ? nextJobs.find((candidate) => candidate.id === visibleJobId) : undefined)
          ?? newestPipelineJob(scoped.filter((candidate) => isDetailedTestVideoExecutionActive(candidate)))
          ?? newestPipelineJob(scoped);
        if (next) setJob(next);
        if (reconciled) {
          submissionGuardRef.current = undefined;
          setSubmissionUncertain(false);
          setMessage({ type: 'info', text: '応答を受信できませんでしたが、受理済みの詳細一括Jobを照合しました。再送は行いません。' });
        }
        await onReload().catch(() => undefined);
      } catch {
        // Preserve the last known state. The next bounded poll retries without
        // permitting a second POST while acceptance is uncertain.
      } finally {
        pollingRef.current = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => { void poll(); }, 2_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [detail.id, executionActive, isTerminal, onReload, submissionUncertain, submitting, visibleJobId]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const updateClip = <Key extends keyof TimelineDraftClip>(index: number, key: Key, value: TimelineDraftClip[Key]) => {
    setClips((current) => current.map((clip, clipIndex) => clipIndex === index ? { ...clip, [key]: value } : clip));
  };
  const selectArtifact = (index: number, artifactId: string) => {
    const artifact = videoArtifacts.find((item) => item.id === artifactId);
    setClips((current) => current.map((clip, clipIndex) => clipIndex !== index ? clip : {
      ...clip,
      videoArtifactId: artifactId,
      ...(artifact?.durationSeconds === undefined ? {} : {
        startMs: '0',
        endMs: String(Math.max(50, Math.round(artifact.durationSeconds * 1_000))),
        overlayStartMs: '0',
        overlayEndMs: String(Math.min(Math.max(50, Math.round(artifact.durationSeconds * 1_000)), 2_000)),
      }),
    }));
  };
  const addClip = () => {
    if (clips.length >= 16) return;
    setClips((current) => [...current, timelineDraftForArtifact(videoArtifacts[0])]);
  };
  const removeClip = (index: number) => setClips((current) => current.filter((_, clipIndex) => clipIndex !== index));
  const duplicateClip = (index: number) => {
    if (clips.length >= 16) return;
    setClips((current) => duplicateTimelineClip(current, index));
  };
  const moveClip = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= clips.length) return;
    setClips((current) => moveTimelineClip(current, index, target));
  };
  const updatePronunciation = (index: number, key: 'source' | 'target', value: string) => {
    setPronunciations((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };

  const execute = async () => {
    if (submittingRef.current || submissionUncertain || busy || executionActive) return;
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setSubmissionUncertain(false);
    reloadedTerminalJob.current = undefined;
    setMessage({ type: 'info', text: '詳細一括Jobを登録しています。各workerの成功とはまだ判定していません。' });
    try {
      submissionGuardRef.current = await createDetailedTestVideoSubmissionGuard(
        detail.id,
        normalizedInput.request,
        reconciledJobs,
      );
    } catch {
      submissionGuardRef.current = undefined;
      setBusy(false);
      setMessage({ type: 'error', text: '詳細一括requestの照合用SHA-256を作成できないため、Jobを送信しませんでした。' });
      submittingRef.current = false;
      setSubmitting(false);
      return;
    }
    try {
      const submitted = await api.executeDetailedTestVideo(detail.id, normalizedInput.request as DetailedTestVideoRequest);
      submissionGuardRef.current = undefined;
      setSubmissionUncertain(false);
      setJob(submitted);
      setMessage({
        type: submitted.status === 'failed' ? 'error' : 'success',
        text: submitted.status === 'failed'
          ? detailedTestVideoError(submitted.message ?? '詳細一括Jobが失敗しました')
          : `詳細一括Job ${submitted.id} を登録しました。4段階を2秒間隔で監視します。`,
      });
      await onReload().catch(() => setMessage({ type: 'info', text: 'Jobは登録済みです。制作詳細の再読込だけ失敗したため、Job監視を継続します。' }));
      if (isTerminalStatus(submitted.status)) setBusy(false);
    } catch (error) {
      if (error instanceof StudioApiError && error.status >= 400 && error.status < 500) {
        submissionGuardRef.current = undefined;
        setSubmissionUncertain(false);
        setBusy(false);
        setMessage({ type: 'error', text: detailedTestVideoError(error) });
      } else {
        setSubmissionUncertain(true);
        await onReload().catch(() => undefined);
        try {
          const nextJobs = await api.jobs();
          const guard = submissionGuardRef.current;
          const reconciled = guard?.productionId === detail.id
            ? newestPipelineJob(nextJobs
              .filter((candidate) => isDetailedTestVideoJobForSelection(candidate, { productionId: detail.id }))
              .filter((candidate) => detailedTestVideoJobMatchesSubmissionGuard(candidate, guard)))
            : undefined;
          if (reconciled) {
            submissionGuardRef.current = undefined;
            setSubmissionUncertain(false);
            setJob(reconciled);
            setMessage({ type: 'info', text: '応答を受信できませんでしたが、受理済みの詳細一括Jobを照合しました。再送は行いません。' });
          } else {
            setMessage({ type: 'error', text: `${detailedTestVideoError(error)} 受理状態を確認中のため、二重実行防止で再送を停止しています。` });
          }
        } catch {
          setMessage({ type: 'error', text: `${detailedTestVideoError(error)} 受理状態を確認中のため、二重実行防止で再送を停止しています。` });
        }
      }
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const formLocked = submitting || submissionUncertain || busy || executionActive;
  const stageResults = Object.fromEntries(DETAILED_TEST_VIDEO_STEPS.map((step) => [step.key, detailedTestVideoStageResult(step, visibleJob, linkedRun)]));
  const qcAttempt = [...(linkedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'qc')
    .sort((left, right) => (right.createdAt ?? '').localeCompare(left.createdAt ?? ''))[0];
  const technicalVerdict = visibleJob?.result?.technicalVerdict ?? qcAttempt?.technicalVerdict;
  const finalArtifacts = [...(visibleJob?.result?.artifacts ?? []), ...detail.artifacts.filter((artifact) => runId && artifact.runId === runId)]
    .filter((artifact, index, all) => all.findIndex((candidate) => candidate.id === artifact.id) === index)
    .filter((artifact) => ['master-clean.mp4', 'master-captioned.mp4', 'technical-qc.json', 'ffprobe.json', 'manifest.json'].includes(artifact.name));

  return (
    <div className="detailed-test-grid">
      <div>
        <section className="panel detailed-test-panel">
          <div className="panel-header"><div><span className="section-kicker">DETAILED TEST VIDEO V1</span><h3>詳細一括</h3></div><span className="tag">既存素材 · 費用0円</span></div>
          <p className="panel-lead">登録済み動画からRemotion詳細編集、Windows SAPI、音声・字幕合成、技術QCまでを1つのtop Jobで実行します。</p>
          <div className="local-pipeline-policy" role="note"><strong>schema v1の閉じたrecipe</strong><p>最大16カット／60秒です。任意path、CSS、FFmpeg filter、gainは送信しません。Playerは素材・固定テロップのpreviewで、ナレーションと焼き込み字幕は完成masterで確認します。</p></div>
          {videoArtifacts.length === 0 && <div className="notice notice-warning"><div><strong>利用できる動画artifactがありません</strong><p>先に生成映像または画面収録を登録してください。</p></div></div>}
          <div className="timeline-toolbar"><div><strong>カットrecipe</strong><small>{clips.length} / 16件 · 出力 {formatMilliseconds(normalizedInput.outputDurationMs)}</small></div><button className="button button-secondary" type="button" onClick={addClip} disabled={formLocked || clips.length >= 16 || videoArtifacts.length === 0}>＋カットを追加</button></div>
          <div className="timeline-clip-list detailed-test-clips">{clips.map((clip, index) => {
            const artifact = videoArtifacts.find((item) => item.id === clip.videoArtifactId);
            return <article className="timeline-clip-row" key={`${index}-${clip.videoArtifactId}`}>
              <div className="timeline-clip-heading"><strong>{String(index + 1).padStart(2, '0')} · {artifact?.name ?? '動画artifact未選択'}</strong><span className="timeline-clip-duration">{formatMilliseconds((Number(clip.endMs) || 0) - (Number(clip.startMs) || 0))}</span></div>
              <label className="field"><span>動画artifact</span><select value={clip.videoArtifactId} disabled={formLocked || videoArtifacts.length === 0} onChange={(event) => selectArtifact(index, event.target.value)} aria-label={`詳細一括カット${index + 1}の動画artifact`}><option value="">動画artifactを選択</option>{videoArtifacts.map((item) => <option key={item.id} value={item.id}>{item.name} · {formatBytes(item.sizeBytes)}</option>)}</select></label>
              <div className="timeline-time-grid"><label className="field"><span>開始（ms）</span><input type="number" min="0" step="1" value={clip.startMs} disabled={formLocked} onChange={(event) => updateClip(index, 'startMs', event.target.value)} /></label><label className="field"><span>終了（ms）</span><input type="number" min="0" step="1" value={clip.endMs} disabled={formLocked} onChange={(event) => updateClip(index, 'endMs', event.target.value)} /></label></div>
              <div className="remotion-clip-controls">
                <label className="field"><span>素材音量（0〜100%）</span><input type="number" min="0" max="100" step="1" value={clip.volumePercent} disabled={formLocked} onChange={(event) => updateClip(index, 'volumePercent', event.target.value)} /></label>
                <label className="field"><span>映像補正preset</span><select value={clip.visualPreset} disabled={formLocked} onChange={(event) => updateClip(index, 'visualPreset', event.target.value as LocalRemotionTimelineVisualPreset)}><option value="preserve_v1">補正なし（preserve_v1）</option><option value="h3_low_res_sharp_v1">H3低解像度を鮮明化</option></select><small className="field-help">固定強度です。任意filterは指定できません。</small></label>
                <label className={`remotion-toggle ${index === clips.length - 1 ? 'is-disabled' : ''}`}><input type="checkbox" checked={index < clips.length - 1 && clip.transitionEnabled} disabled={formLocked || index === clips.length - 1} onChange={(event) => updateClip(index, 'transitionEnabled', event.target.checked)} /><span><strong>次カットへfade</strong><small>50〜2000ms</small></span></label>
                {index < clips.length - 1 && clip.transitionEnabled && <label className="field"><span>fade時間（ms）</span><input type="number" min="50" max="2000" step="1" value={clip.transitionDurationMs} disabled={formLocked} onChange={(event) => updateClip(index, 'transitionDurationMs', event.target.value)} /></label>}
                <label className="remotion-toggle"><input type="checkbox" checked={clip.overlayEnabled} disabled={formLocked} onChange={(event) => updateClip(index, 'overlayEnabled', event.target.checked)} /><span><strong>固定テロップ</strong><small>shorts_ja_large_v1</small></span></label>
                {clip.overlayEnabled && <div className="remotion-overlay-editor"><label className="field remotion-overlay-text"><span>テロップ本文</span><textarea rows={3} maxLength={200} value={clip.overlayText} disabled={formLocked} onChange={(event) => updateClip(index, 'overlayText', event.target.value)} /></label><label className="field"><span>表示開始（ms）</span><input type="number" min="0" step="1" value={clip.overlayStartMs} disabled={formLocked} onChange={(event) => updateClip(index, 'overlayStartMs', event.target.value)} /></label><label className="field"><span>表示終了（ms）</span><input type="number" min="0" step="1" value={clip.overlayEndMs} disabled={formLocked} onChange={(event) => updateClip(index, 'overlayEndMs', event.target.value)} /></label><label className="field"><span>表示位置</span><select value={clip.overlayPosition} disabled={formLocked} onChange={(event) => updateClip(index, 'overlayPosition', event.target.value as LocalRemotionTimelineOverlayPosition)}><option value="top">上</option><option value="center">中央</option><option value="bottom">下</option></select></label></div>}
              </div>
              <div className="timeline-artifact-meta"><span>bytes {formatBytes(artifact?.sizeBytes)}</span><span>source尺 {formatDuration(artifact?.durationSeconds)}</span></div>
              <div className="timeline-row-actions"><button className="button button-ghost" type="button" onClick={() => moveClip(index, -1)} disabled={formLocked || index === 0}>↑</button><button className="button button-ghost" type="button" onClick={() => moveClip(index, 1)} disabled={formLocked || index === clips.length - 1}>↓</button><button className="button button-ghost" type="button" onClick={() => duplicateClip(index)} disabled={formLocked || clips.length >= 16}>複製</button><button className="button button-ghost" type="button" onClick={() => removeClip(index)} disabled={formLocked}>削除</button></div>
            </article>;
          })}{clips.length === 0 && <EmptyState title="カットがありません" description="登録済み動画をカットrecipeへ追加してください。" />}</div>

          <div className="detailed-test-section"><div className="panel-header"><div><span className="section-kicker">NARRATION & OUTPUT</span><h3>音声・字幕・QC</h3></div></div>
            <label className="field"><span>ナレーション台本（1行＝1セグメント）</span><textarea rows={6} value={script} disabled={formLocked} onChange={(event) => setScript(event.target.value)} placeholder="例：詳細編集した映像を、一本の動画に仕上げます。" /></label>
            <div className="local-pipeline-form-row"><label className="field"><span>音声（任意）</span><input value={voice} disabled={formLocked} onChange={(event) => setVoice(event.target.value)} placeholder="既定音声" /></label><label className="field"><span>読み上げ速度</span><input type="number" min="-10" max="10" step="1" value={rate} disabled={formLocked} onChange={(event) => setRate(event.target.value)} /></label></div>
            <fieldset className="pronunciation-fieldset"><legend>発音置換（任意）</legend>{pronunciations.map((item, index) => <div className="pronunciation-row" key={index}><input value={item.source} disabled={formLocked} onChange={(event) => updatePronunciation(index, 'source', event.target.value)} placeholder="表記" /><span aria-hidden="true">→</span><input value={item.target} disabled={formLocked} onChange={(event) => updatePronunciation(index, 'target', event.target.value)} placeholder="読み" /><button className="button button-ghost" type="button" onClick={() => setPronunciations((current) => current.length === 1 ? current : current.filter((_, itemIndex) => itemIndex !== index))} disabled={formLocked || pronunciations.length === 1}>削除</button></div>)}<button className="button button-secondary" type="button" onClick={() => setPronunciations((current) => [...current, { source: '', target: '' }])} disabled={formLocked}>＋置換を追加</button></fieldset>
            <label className="toggle-field"><input type="checkbox" checked={includeCaptioned} disabled={formLocked} onChange={(event) => { const next = event.target.checked; setIncludeCaptioned(next); setVariant(next ? 'captioned' : 'clean'); setCaptionStylePreset(next ? RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET : 'studio_default_v1'); }} /><span><strong>字幕付きmasterを生成</strong><small>オフの場合はclean masterをQCします。</small></span></label>
            <div className="detailed-test-output-grid"><label className="field"><span>字幕プリセット</span><select value={captionStylePreset} disabled={formLocked || !includeCaptioned} onChange={(event) => { const next = event.target.value; if (next === 'studio_default_v1' || next === 'shorts_ja_large_v1') setCaptionStylePreset(next); }}><option value="shorts_ja_large_v1">Shorts向け大字幕</option><option value="studio_default_v1">標準字幕</option></select></label><label className="field"><span>音声mix</span><select value={audioMixPreset} disabled={formLocked} onChange={(event) => { const next = event.target.value; if (next === 'narration_only_v1' || next === 'source_under_narration_v1') setAudioMixPreset(next); }}><option value="narration_only_v1">ナレーションのみ</option><option value="source_under_narration_v1">素材25%＋ナレーション100%</option></select></label><label className="field"><span>QC対象</span><select value={variant} disabled={formLocked || !includeCaptioned} onChange={(event) => { const next = event.target.value; if (next === 'clean' || next === 'captioned') setVariant(next); }}><option value="captioned">captioned</option><option value="clean">clean</option></select></label></div>
            <p className="gate-separation-note">素材音を残すpresetは、Remotionの素材音量適用後にさらに25%へ下げます。素材音声なし／無音は自動代替せずfail closedです。</p>
          </div>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={formLocked || validationErrors.length > 0}>{submitting ? '登録中…' : executionActive || busy ? '詳細一括を監視中…' : '詳細一括を実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <section className="panel compact-panel remotion-player-panel"><div className="panel-header"><div><span className="section-kicker">RECIPE PLAYER</span><h3>素材・固定テロップpreview</h3></div><span className="tag">1080×1920</span></div>{playerProps ? <div className="remotion-player-shell"><Player component={TimelineComposition} inputProps={playerProps} durationInFrames={playerProps.durationInFrames} compositionWidth={1080} compositionHeight={1920} fps={24} controls loop style={{ width: '100%', aspectRatio: '9 / 16' }} /></div> : <p className="muted">カット入力を整えるとpreviewできます。</p>}<p className="gate-separation-note">Playerは映像補正presetを再現しません。鮮明化は完成artifactを正とし、ナレーション、SRT字幕、最終mixもrender後のmasterで確認します。</p></section>
        <section className="panel compact-panel local-pipeline-progress-panel" aria-live="polite" aria-busy={executionActive}><div className="panel-header"><div><span className="section-kicker">DETAILED JOB</span><h3>4段階の進捗</h3></div>{visibleJob ? <StatusBadge status={visibleJob.status} label={executionActive ? '監視中' : jobStatusLabel(visibleJob.status)} /> : <span className="muted">未実行</span>}</div><ol className="local-pipeline-progress">{DETAILED_TEST_VIDEO_STEPS.map((step, index) => { const item = stageResults[step.key] as LocalPipelineStageResult | undefined; const status = item?.status ?? (visibleJob ? 'pending' : 'unknown'); return <li className={`local-pipeline-step step-${status}`} key={step.key}><div className="local-pipeline-step-rail"><span>{index + 1}</span></div><div className="local-pipeline-step-body"><div><strong>{step.label}</strong><StatusBadge status={status} label={item ? jobStatusLabel(status) : '未開始'} /></div>{item?.progress !== undefined && <div className="progress-track"><span style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }} /></div>}<small>{item?.jobId ? `Job ${item.jobId}` : item?.stageAttemptId ? `Attempt ${item.stageAttemptId}` : 'stage記録を待機中'}{item?.cacheHit === undefined ? '' : item.cacheHit ? ' · cache hit' : ' · cache miss'}</small>{item?.message && <p>{item.message}</p>}</div></li>; })}</ol><dl className="narration-metrics"><div><dt>Top Job</dt><dd className="mono">{visibleJob?.id ?? '—'}</dd></div><div><dt>Run</dt><dd className="mono">{runId ?? '—'}</dd></div><div><dt>recipe尺</dt><dd>{formatMilliseconds(displayedRecipeDurationMs)}</dd></div><div><dt>更新</dt><dd>{formatDate(visibleJob?.updatedAt)}</dd></div></dl></section>
        <section className="panel compact-panel local-pipeline-result-panel"><div className="panel-header"><div><span className="section-kicker">FINAL RESULT</span><h3>master・QC</h3></div>{technicalVerdict ? <StatusBadge status={technicalVerdict === 'pass' ? 'succeeded' : 'failed'} label={`technical verdict: ${technicalVerdict}`} /> : <span className="muted">判定待ち</span>}</div>{technicalVerdict === 'fail' && <div className="notice notice-warning"><div><strong>技術QCは不合格です</strong><p>Job完了とtechnical passは別判定です。</p></div></div>}{finalArtifacts.length === 0 ? <p className="muted">最終artifactはまだありません。</p> : <div className="narration-artifact-list">{finalArtifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer"><strong>{artifact.name}</strong><span>{artifact.kind} · {formatBytes(artifact.sizeBytes)} ↗</span></a>)}</div>}<p className="gate-separation-note">表現、権利、公開可否はtechnical QCとは別に確認してください。</p></section>
      </aside>
    </div>
  );
}

function AssemblyPanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => hasNarrationStage(run) && hasAssemblyStage(run) && hasLocalMediaProfile(run))
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [videoArtifactId, setVideoArtifactId] = useState('');
  const [narrationAttemptId, setNarrationAttemptId] = useState('');
  const [includeCaptioned, setIncludeCaptioned] = useState(true);
  const [captionStylePreset, setCaptionStylePreset] = useState<LocalAssemblyCaptionStylePreset>(RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET);
  const [audioMixPreset, setAudioMixPreset] = useState<LocalAssemblyAudioMixPreset>(DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET);
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadedTerminalJob = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setVideoArtifactId('');
      setNarrationAttemptId('');
      setJob(undefined);
    }
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const videoArtifacts = useMemo(
    () => detail.artifacts.filter((artifact) => artifact.kind === 'video'),
    [detail.artifacts],
  );
  const narrationAttempts = useMemo(
    () => (selectedRun?.stageAttempts ?? []).filter(isSucceededNarrationAttempt),
    [selectedRun],
  );

  useEffect(() => {
    if (!videoArtifacts.some((artifact) => artifact.id === videoArtifactId)) {
      setVideoArtifactId(videoArtifacts[0]?.id ?? '');
    }
  }, [videoArtifactId, videoArtifacts]);

  useEffect(() => {
    if (!narrationAttempts.some((attempt) => attempt.id === narrationAttemptId)) {
      setNarrationAttemptId(narrationAttempts[narrationAttempts.length - 1]?.id ?? '');
    }
  }, [narrationAttemptId, narrationAttempts]);

  const currentAttempt = [...(selectedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'assembly')
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))[0];
  const visibleJob = job ?? jobs.find((item) =>
    item.id === currentAttempt?.jobId
    || (item.runId === selectedRun?.id && (item.stage === 'assembly' || item.type === 'local_assembly')),
  );
  const isTerminal = visibleJob?.status === 'succeeded' || visibleJob?.status === 'failed' || visibleJob?.status === 'cancelled';
  const selectedNarrationAttempt = narrationAttempts.find((attempt) => attempt.id === narrationAttemptId);
  const normalizedInput = useMemo(
    () => normalizeLocalAssemblyInput(videoArtifactId, narrationAttemptId, includeCaptioned, captionStylePreset, audioMixPreset),
    [audioMixPreset, captionStylePreset, includeCaptioned, narrationAttemptId, videoArtifactId],
  );
  const validationErrors = [
    ...normalizedInput.errors,
    ...(selectedRun && !hasLocalMediaProfile(selectedRun) ? ['このRunはlocal_sapiまたはelevenlabs_ttsではありません。'] : []),
  ];

  useEffect(() => {
    if (!job || isTerminal) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    const timer = window.setInterval(() => {
      void api.jobs().then((nextJobs) => {
        const next = nextJobs.find((item) => item.id === job.id);
        if (next) setJob(next);
      }).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [isTerminal, job, submitting]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const execute = async () => {
    if (submittingRef.current) return;
    if (!selectedRun) {
      setMessage({ type: 'error', text: 'assembly工程を含むlocal_sapiまたはelevenlabs_tts Runを選択してください。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setJob(undefined);
    setMessage({ type: 'info', text: '編集・合成workerをキューに登録しています。成功とはまだ判定していません。' });
    try {
      const request: LocalAssemblyRequest = normalizedInput.request;
      const submitted = await api.executeLocalAssembly(selectedRun.id, request);
      setJob(submitted);
      setMessage({ type: submitted.status === 'failed' ? 'error' : 'success', text: submitted.status === 'failed' ? localAssemblyError(submitted.message ?? 'workerが失敗しました') : '編集・合成workerをキューに登録しました。' });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: 'workerは登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (submitted.status === 'succeeded' || submitted.status === 'failed' || submitted.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localAssemblyError(error) });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (eligibleRuns.length === 0) {
    return <section className="panel assembly-panel"><div className="panel-header"><div><span className="section-kicker">LOCAL ASSEMBLY</span><h3>ローカル編集・合成worker</h3></div></div><EmptyState title="narration＋assembly工程を含むRunがありません" description="概要の再調整で narration と assembly を選択し、local_sapi または elevenlabs_tts プロファイルのRunを作成してください。外部profileでも合成はローカルで実行します。" /></section>;
  }

  const resultArtifacts = visibleJob?.result?.artifacts ?? currentAttempt?.artifacts ?? [];
  return (
    <div className="assembly-grid">
      <div>
        <section className="panel assembly-panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL ASSEMBLY</span><h3>ローカル編集・合成worker</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">登録済みの動画artifactと、成功済みの音声・字幕をこのPC上で合成します。elevenlabs_tts Runでも外部送信は音声工程だけで、合成はローカルworkerです。</p>
          <label className="field"><span>対象Run（narration＋assemblyを要求したlocal_sapi / elevenlabs_tts）</span><select value={selectedRunId} disabled={busy || submitting} onChange={(event) => { setSelectedRunId(event.target.value); setVideoArtifactId(''); setNarrationAttemptId(''); setJob(undefined); setMessage(undefined); }} aria-label="編集・合成対象Run">
            {eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id} · {run.executionProfile}</option>)}
          </select></label>
          <div className="assembly-run-summary"><span>Run ID</span><strong className="mono">{selectedRun?.id}</strong><span>実行profile</span><strong>{selectedRun?.executionProfile}</strong></div>
          <label className="field"><span>動画artifact</span><select value={videoArtifactId} disabled={busy || submitting || videoArtifacts.length === 0} onChange={(event) => setVideoArtifactId(event.target.value)} aria-describedby="assembly-video-help" aria-label="合成する動画artifact">
            <option value="">動画artifactを選択</option>
            {videoArtifacts.map((artifact) => <option key={artifact.id} value={artifact.id}>{artifact.name} · {formatBytes(artifact.sizeBytes)}{artifact.runId ? ` · ${artifact.runId}` : ''}</option>)}
          </select><small id="assembly-video-help" className="field-help">同じ制作に登録されたvideo kindのみ表示しています。</small></label>
          {videoArtifacts.length === 0 && <div className="notice notice-warning"><div><strong>動画artifactがありません</strong><p>先に生成映像を登録し、インデックスを更新してください。</p></div></div>}
          <label className="field"><span>ナレーション試行（成功済み・音声＋字幕あり）</span><select value={narrationAttemptId} disabled={busy || submitting || narrationAttempts.length === 0} onChange={(event) => setNarrationAttemptId(event.target.value)} aria-describedby="assembly-narration-help" aria-label="合成に使うナレーション試行">
            <option value="">成功済み試行を選択</option>
            {narrationAttempts.map((attempt) => <option key={attempt.id} value={attempt.id}>#{attempt.attempt ?? '—'} · {attempt.id} · {attempt.artifacts.length} artifacts</option>)}
          </select><small id="assembly-narration-help" className="field-help">narration.wav と captions.srt の両方を含む成功済みstage attemptのみ表示しています。</small></label>
          {narrationAttempts.length === 0 && <div className="notice notice-warning"><div><strong>利用できるナレーション試行がありません</strong><p>ローカルナレーションを先に成功させ、音声とcaptions.srtを生成してください。</p></div></div>}
          {selectedNarrationAttempt && <div className="assembly-source-summary"><span>音声・字幕</span><strong>{selectedNarrationAttempt.artifacts.map((artifact) => artifact.name).join('、')}</strong></div>}
          <label className="field"><span>音声mixプリセット</span><select value={audioMixPreset} disabled={busy || submitting} onChange={(event) => { const next = event.target.value; if (next === 'narration_only_v1' || next === 'source_under_narration_v1') setAudioMixPreset(next); }} aria-describedby="assembly-audio-mix-help" aria-label="音声mixプリセット">
            <option value="narration_only_v1">ナレーションのみ（従来互換）</option>
            <option value="source_under_narration_v1">素材音を小さく残す（素材25%・ナレーション100%）</option>
          </select><small id="assembly-audio-mix-help" className="field-help">任意gainは指定できません。素材音を残すpresetは、素材に音声がない場合や無音の場合はfail closedで停止します。Remotionで素材音量を調整済みの場合も、その結果にさらに25%を適用します。</small></label>
          <label className="assembly-check"><input type="checkbox" checked={includeCaptioned} disabled={busy || submitting} onChange={(event) => { const next = event.target.checked; setIncludeCaptioned(next); if (!next) setCaptionStylePreset('studio_default_v1'); }} /><span><strong>字幕付き版も生成</strong><small>オンの場合、通常版に加えてcaptions.srtを焼き込んだcaptioned版を生成します。</small></span></label>
          <label className="field"><span>字幕プリセット</span><select value={captionStylePreset} disabled={busy || submitting || !includeCaptioned} onChange={(event) => { const next = event.target.value; if (next === 'studio_default_v1' || next === 'shorts_ja_large_v1') setCaptionStylePreset(next); }} aria-describedby="assembly-caption-style-help" aria-label="字幕プリセット">
            <option value="shorts_ja_large_v1">Shorts向け大字幕（推奨）</option>
            <option value="studio_default_v1">標準字幕（従来互換）</option>
          </select><small id="assembly-caption-style-help" className="field-help">閉じた検証済みpresetのみ選択できます。Shorts向けは大きな太字・強い縁取り・safe marginを使用します。</small></label>
          <div className="assembly-confirm" role="note"><strong>実行前確認</strong><span>Run <b className="mono">{selectedRun?.id}</b> に選択した動画・音声・字幕を合成</span><span>音声mix: <b className="mono">{audioMixPreset}</b></span><span>字幕preset: <b className="mono">{captionStylePreset}</b></span><span>{hasElevenLabsProfile(selectedRun) ? '音声のみ外部送信 · 合成はローカルworker' : '外部送信なし · ローカルworker'} · 費用0円</span></div>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={submitting || busy || validationErrors.length > 0}>{submitting ? '登録中…' : busy ? 'worker監視中…' : 'ローカル編集・合成を実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <AssemblyJobStatus job={visibleJob} attempt={currentAttempt} artifacts={resultArtifacts} />
      </aside>
    </div>
  );
}

function AssemblyJobStatus({ job, attempt, artifacts }: { job?: Job; attempt?: StageAttempt; artifacts: Artifact[] }) {
  const status = job?.status ?? attempt?.status;
  const cacheHit = job?.cacheHit ?? attempt?.cacheHit;
  const result = job?.result;
  const provider = result?.provider ?? attempt?.provider;
  const providerTaskId = result?.providerTaskId ?? attempt?.providerTaskId;
  const actualCost = result?.actualCost ?? attempt?.actualCost;
  const timingSource = result?.timingSource ?? attempt?.timingSource;
  const active = status === 'pending' || status === 'running';
  return <section className="panel compact-panel narration-status-panel" aria-live="polite" aria-busy={active}><div className="panel-header"><div><span className="section-kicker">ASSEMBLY STATUS</span><h3>合成実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>{!job && !attempt && <p className="muted">実行すると、キュー投入後の状態をここで監視します。</p>}<dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{job?.id ?? attempt?.jobId ?? '—'}</dd></div><div><dt>Attempt</dt><dd>{job?.attempt ?? attempt?.attempt ?? '—'}</dd></div><div><dt>Cache hit</dt><dd>{cacheHit === undefined ? '—' : cacheHit ? 'はい' : 'いいえ'}</dd></div><div><dt>所要時間</dt><dd>{formatDuration(job?.durationSeconds ?? attempt?.durationSeconds)}</dd></div><div><dt>Provider</dt><dd>{provider ?? '—'}</dd></div><div><dt>Provider task</dt><dd className="mono">{provider ? providerTaskId ?? 'なし' : '—'}</dd></div><div><dt>実費</dt><dd>{actualCost === undefined ? '—' : `${actualCost}（local）`}</dd></div><div><dt>Timing</dt><dd>{timingSource ?? '—'}</dd></div><div><dt>更新</dt><dd>{formatDate(job?.updatedAt ?? attempt?.finishedAt ?? attempt?.startedAt)}</dd></div></dl>{job?.message && <p className={job.status === 'failed' ? 'narration-error-text' : 'muted'}>{job.message}</p>}<div className="narration-artifact-list"><strong>生成artifact</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} ↗</a>)}</div><p className="gate-separation-note">これはworkerの実行履歴です。費用承認・技術/表現/公開ゲートとは別の記録です。</p></section>;
}

const qcVariantLabel = (variant: LocalQcVariant): string => variant === 'captioned' ? 'captioned（字幕焼き込み）' : 'clean（字幕なし）';

const qcVariantArtifactNames = (attempt: StageAttempt | undefined, variant: LocalQcVariant): string[] => {
  const videoArtifacts = attempt?.artifacts.filter((artifact) => artifact.kind === 'video') ?? [];
  const names = videoArtifacts
    .filter((artifact) => {
      const name = artifact.name.toLowerCase();
      if (variant === 'captioned') return /caption/.test(name);
      return /clean|master(?![-_]?caption)/.test(name);
    })
    .map((artifact) => artifact.name);
  if (names.length > 0) return names;
  return variant === 'clean' && videoArtifacts.length === 1 ? [videoArtifacts[0].name] : [];
};

function QcPanel({ detail, jobs, onReload }: { detail: ProductionDetail; jobs: Job[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter(isEligibleLocalQcRun)
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [selectedAttemptId, setSelectedAttemptId] = useState('');
  const [variant, setVariant] = useState<LocalQcVariant>('clean');
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadedTerminalJob = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setSelectedAttemptId('');
      setVariant('clean');
      setJob(undefined);
      setMessage(undefined);
    }
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const assemblyAttempts = useMemo(
    () => selectedRun ? getLocalQcAssemblyAttempts(selectedRun) : [],
    [selectedRun],
  );

  useEffect(() => {
    if (!assemblyAttempts.some((attempt) => attempt.id === selectedAttemptId)) {
      setSelectedAttemptId(assemblyAttempts[0]?.id ?? '');
      setVariant('clean');
      setJob(undefined);
    }
  }, [assemblyAttempts, selectedAttemptId]);

  const selectedAttempt = assemblyAttempts.find((attempt) => attempt.id === selectedAttemptId);
  const availableVariants = useMemo(
    () => selectedAttempt ? getLocalQcAvailableVariants(selectedAttempt) : [],
    [selectedAttempt],
  );

  useEffect(() => {
    if (!availableVariants.includes(variant)) setVariant(availableVariants[0] ?? 'clean');
  }, [availableVariants, variant]);

  const qcAttempts = useMemo(
    () => [...(selectedRun?.stageAttempts ?? [])]
      .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'qc')
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [selectedRun],
  );
  const currentQcAttempt = qcAttempts.find((attempt) =>
    attempt.assemblyAttemptId === selectedAttemptId && attempt.variant === variant,
  );
  const matchesQcSelection = (item: Job): boolean => isLocalQcJobForSelection(item, {
    runId: selectedRun?.id,
    assemblyAttemptId: selectedAttemptId,
    variant,
  });
  const visibleJob = job && matchesQcSelection(job)
    ? job
    : jobs.find((item) => item.id === currentQcAttempt?.jobId || matchesQcSelection(item));
  const isTerminal = visibleJob?.status === 'succeeded' || visibleJob?.status === 'failed' || visibleJob?.status === 'cancelled';
  const normalizedInput = useMemo(
    () => normalizeLocalQcInput(selectedAttemptId, variant),
    [selectedAttemptId, variant],
  );
  const validationErrors = [
    ...normalizedInput.errors,
    ...(selectedRun && !hasLocalMediaProfile(selectedRun) ? ['このRunはlocal_sapiまたはelevenlabs_ttsではありません。'] : []),
    ...(selectedRun && !hasRequestedLocalQcStages(selectedRun) ? ['このRunはassembly＋qcを要求していません。'] : []),
    ...(selectedAttemptId && !selectedAttempt ? ['選択したassembly試行を確認できません。再読込してください。'] : []),
    ...(selectedAttempt && !isSucceededLocalFfmpegAssemblyAttempt(selectedAttempt) ? ['成功済みlocal_ffmpeg assembly attemptだけを検査できます。'] : []),
    ...(selectedAttempt && !availableVariants.includes(variant) ? [`${qcVariantLabel(variant)}のmaster artifactがありません。実在するvariantを選択してください。`] : []),
  ];

  useEffect(() => {
    if (!job || isTerminal) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    const timer = window.setInterval(() => {
      void api.jobs().then((nextJobs) => {
        const next = nextJobs.find((item) => item.id === job.id);
        if (next) setJob(next);
      }).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [isTerminal, job, submitting]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const execute = async () => {
    if (submittingRef.current) return;
    if (!selectedRun) {
      setMessage({ type: 'error', text: 'assembly＋qcを要求したlocal_sapiまたはelevenlabs_tts Runを選択してください。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setJob(undefined);
    setMessage({ type: 'info', text: '技術QC jobをキューに登録しています。job成功と技術検査合格は別判定です。' });
    try {
      const request: LocalQcRequest = normalizedInput.request;
      const submitted = await api.executeLocalQc(selectedRun.id, request);
      setJob(submitted);
      const resultStatus = getLocalQcResultStatus(submitted);
      const text = submitted.status === 'failed'
        ? localQcError(submitted.message ?? 'QC workerが失敗しました')
        : resultStatus.technicalFailed
          ? 'QC jobは完了しましたが、技術検査は不合格です。'
          : '技術QC jobをキューに登録しました。解析結果を監視しています。';
      setMessage({ type: submitted.status === 'failed' ? 'error' : 'success', text });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: 'QC jobは登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (submitted.status === 'succeeded' || submitted.status === 'failed' || submitted.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localQcError(error) });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (eligibleRuns.length === 0) {
    const requestedRuns = detail.runs.filter(hasRequestedLocalQcStages);
    const localRuns = requestedRuns.filter((run) => hasLocalMediaProfile(run));
    const description = requestedRuns.length === 0
      ? '品質検査には、requested stagesに assembly と qc の両方を含むRunが必要です。概要の再調整で工程を選択してください。'
      : localRuns.length === 0
        ? 'assembly＋qcを要求したRunがlocal_sapi / elevenlabs_ttsではありません。対応するプロファイルでRunを作成してください。'
        : '成功済みlocal_ffmpeg assembly attemptと、cleanまたはcaptionedの実在master artifactがありません。先にローカル編集・合成を成功させてください。';
    return <section className="panel qc-panel"><div className="panel-header"><div><span className="section-kicker">LOCAL TECHNICAL QC</span><h3>ローカル技術QC</h3></div><span className="tag">費用 0円</span></div><p className="panel-lead">合成済みmasterのcodec、duration、decode、音量、黒画面、無音などをローカルで検査します。</p><div className="qc-policy-note" role="note"><strong>判定範囲の注意（technical-qc-mp4-v2）</strong><p>ジョブ成功は解析完了を示しますが、技術検査の合格を意味しません。Integrated loudness -24.0〜-10.0 LUFS、true peak -1.0 dBFS以下、0.5秒以上の黒画面はhard checkです。1.0秒以上の長い静止区間はwarningだけで、technical verdictには影響しません。creative QC、権利確認、公開可否は自動判定しません。</p></div><EmptyState title="品質検査の対象masterがありません" description={description} /></section>;
  }

  const resultArtifacts = visibleJob?.result?.artifacts ?? currentQcAttempt?.artifacts ?? [];
  return (
    <div className="qc-grid">
      <div>
        <section className="panel qc-panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL TECHNICAL QC</span><h3>ローカル技術QC</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">成功済みlocal_ffmpeg assemblyが生成した実在masterだけを選び、loopback内で技術的な再生可能性を検査します。elevenlabs_tts Runでも合成とQCはローカルです。</p>
          <div className="qc-policy-note" role="note"><strong>判定範囲の注意（technical-qc-mp4-v2）</strong><p>ジョブ成功 = 解析完了です。ただしtechnical verdictは別の判定で、fail = 技術検査不合格です。Integrated loudness -24.0〜-10.0 LUFS、true peak -1.0 dBFS以下、0.5秒以上の黒画面はhard checkです。1.0秒以上の長い静止区間はwarningだけで、technical verdictには影響しません。creative QC、権利確認、公開可否をこの画面やjob結果から自動決定することはありません。</p></div>
          <label className="field"><span>対象Run（assembly＋qcを要求したlocal_sapi / elevenlabs_tts）</span><select value={selectedRunId} disabled={busy || submitting} onChange={(event) => { setSelectedRunId(event.target.value); setSelectedAttemptId(''); setVariant('clean'); setJob(undefined); setMessage(undefined); }} aria-label="品質検査対象Run">
            {eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id} · {run.executionProfile}</option>)}
          </select></label>
          <div className="qc-run-summary"><span>Run ID</span><strong className="mono">{selectedRun?.id}</strong><span>要求工程</span><strong>{selectedRun?.requestedStages.map(stageLabel).join('、')}</strong><span>実行profile</span><strong>{selectedRun?.executionProfile}</strong></div>
          <label className="field"><span>検査対象assembly attempt（成功済みlocal_ffmpeg）</span><select value={selectedAttemptId} disabled={busy || submitting || assemblyAttempts.length === 0} onChange={(event) => { setSelectedAttemptId(event.target.value); setVariant('clean'); setJob(undefined); setMessage(undefined); }} aria-label="品質検査対象assembly attempt">
            <option value="">assembly attemptを選択</option>
            {assemblyAttempts.map((attempt) => <option key={attempt.id} value={attempt.id}>#{attempt.attempt ?? '—'} · {attempt.id} · {attempt.artifacts.filter((artifact) => artifact.kind === 'video').map((artifact) => artifact.name).join('、') || 'video artifactなし'}</option>)}
          </select><small className="field-help">合成jobの成功ではなく、stage attemptのprovider/statusと実在artifactを検証して候補にしています。</small></label>
          {selectedAttempt && <div className="qc-source-summary"><span>Provider</span><strong>{selectedAttempt.provider ?? '—'}</strong><span>Master</span><strong>{selectedAttempt.artifacts.filter((artifact) => artifact.kind === 'video').map((artifact) => artifact.name).join('、') || '—'}</strong><span>Attempt</span><strong className="mono">{selectedAttempt.id}</strong></div>}
          {selectedAttempt && <label className="field"><span>master variant（実在artifactに応じて選択）</span><select value={variant} disabled={busy || submitting || availableVariants.length === 0} onChange={(event) => { const next = event.target.value; if (next === 'clean' || next === 'captioned') setVariant(next); }} aria-label="技術QCのmaster variant">
            {availableVariants.map((item) => <option key={item} value={item}>{qcVariantLabel(item)} · {qcVariantArtifactNames(selectedAttempt, item).join('、') || 'artifactあり'}</option>)}
          </select><small className="field-help">captioned artifactが存在しない場合、captionedは選択肢に表示しません。</small></label>}
          {selectedAttempt && availableVariants.includes('clean') && !availableVariants.includes('captioned') && <div className="notice notice-warning"><div><strong>captioned masterはありません</strong><p>このassembly attemptにはclean masterだけが登録されています。captioned版の検査は実行できません。</p></div></div>}
          {!selectedAttempt && <div className="notice notice-warning"><div><strong>assembly attemptを選択してください</strong><p>成功済みlocal_ffmpeg attemptに記録されたmasterだけを検査できます。</p></div></div>}
          {selectedAttempt && availableVariants.length === 0 && <div className="notice notice-warning"><div><strong>検査可能なmasterがありません</strong><p>cleanまたはcaptionedのvideo artifactがattemptに存在しません。再読込して実在artifactを確認してください。</p></div></div>}
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <div className="qc-confirm" role="note"><strong>実行前確認</strong><span>Run <b className="mono">{selectedRun?.id}</b> のassembly attempt <b className="mono">{selectedAttempt?.id ?? '—'}</b></span><span>variant: <b>{qcVariantLabel(variant)}</b> · {hasElevenLabsProfile(selectedRun) ? '音声のみ外部送信 · 合成/QCはローカル' : '外部送信なし'} · 費用0円</span></div>
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={submitting || busy || validationErrors.length > 0}>{submitting ? '登録中…' : busy ? 'QC監視中…' : 'ローカル技術QCを実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <QcJobStatus job={visibleJob} attempt={currentQcAttempt} artifacts={resultArtifacts} />
      </aside>
    </div>
  );
}

function QcJobStatus({ job, attempt, artifacts }: { job?: Job; attempt?: StageAttempt; artifacts: Artifact[] }) {
  const result = job?.result;
  const status = job?.status ?? attempt?.status;
  const statusSummary = getLocalQcResultStatus(job ?? attempt ?? {});
  const analysisStatus = result?.analysisStatus ?? attempt?.analysisStatus;
  const technicalVerdict = result?.technicalVerdict ?? attempt?.technicalVerdict;
  const provider = result?.provider ?? attempt?.provider;
  const actualCost = result?.actualCost ?? attempt?.actualCost;
  const durationMs = result?.durationMs ?? attempt?.durationMs;
  const checks = result?.checks?.length ? result.checks : attempt?.checks ?? [];
  const mediaFacts = result?.mediaFacts && Object.keys(result.mediaFacts).length > 0 ? result.mediaFacts : attempt?.mediaFacts ?? {};
  const longStaticFact = mediaFacts.long_static;
  const longStaticRecord = longStaticFact !== null && typeof longStaticFact === 'object' && !Array.isArray(longStaticFact)
    ? longStaticFact as Record<string, unknown>
    : undefined;
  const longStaticWarning = longStaticRecord?.warning === true;
  const longStaticDuration = longStaticRecord?.max_duration_seconds;
  const longStaticAdvisory = longStaticWarning
    ? <div className="qc-result-callout is-warning" role="status"><strong>長い静止区間の注意</strong><span>{typeof longStaticDuration === 'number' ? `最大${longStaticDuration.toFixed(2)}秒の静止区間を検出しました。` : '1.0秒以上の静止区間を検出しました。'}これは警告のみで、technical verdictの合否には影響しません。公開前にテンポと意図した演出を目視確認してください。</span></div>
    : undefined;
  const active = status === 'pending' || status === 'running';
  const jobError = statusSummary.phase === 'job_failed' || status === 'failed';
  const callout = statusSummary.phase === 'job_succeeded_analysis_complete_fail'
    ? <div className="qc-result-callout is-fail"><strong>技術検査：不合格</strong><span>Job成功（解析完了）とは別に、technical verdict=failとなりました。</span></div>
    : statusSummary.phase === 'job_succeeded_analysis_complete_pass'
      ? <div className="qc-result-callout is-pass"><strong>技術検査：合格</strong><span>Job成功により解析完了し、technical verdict=passでした。</span></div>
      : jobError
        ? <div className="qc-result-callout is-error"><strong>Job失敗：解析エラー</strong><span>技術検査の判定結果はありません。</span></div>
        : statusSummary.phase === 'job_succeeded_analysis_incomplete'
          ? <div className="qc-result-callout is-warning"><strong>Job成功だが解析結果が不完全</strong><span>analysis_statusがsucceededになるまで、合否を表示しません。</span></div>
          : statusSummary.phase === 'analysis_failed'
            ? <div className="qc-result-callout is-error"><strong>解析失敗</strong><span>Job状態と技術検査の判定を分けて記録しています。</span></div>
            : undefined;
  return <section className="panel compact-panel qc-status-panel" aria-live="polite" aria-busy={active}>
    <div className="panel-header"><div><span className="section-kicker">QC RESULT</span><h3>技術QC結果</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>
    {!job && !attempt && <p className="muted">実行すると、2秒間隔でjobを監視し、解析完了後に結果を表示します。</p>}
    {callout}
    {longStaticAdvisory}
    <dl className="narration-metrics qc-metrics"><div><dt>Job</dt><dd className="mono">{job?.id ?? attempt?.jobId ?? '—'}</dd></div><div><dt>Provider</dt><dd>{provider ?? '—'}</dd></div><div><dt>実費</dt><dd>{actualCost === undefined ? '—' : `${actualCost}（local）`}</dd></div><div><dt>analysis_status</dt><dd>{analysisStatus ?? '—'}</dd></div><div><dt>technical_verdict</dt><dd>{technicalVerdict ? <span className={`qc-verdict is-${technicalVerdict}`}>{technicalVerdict === 'pass' ? 'pass（合格）' : 'fail（不合格）'}</span> : '—'}</dd></div><div><dt>duration_ms</dt><dd>{durationMs === undefined ? '—' : `${durationMs.toLocaleString()} ms`}</dd></div></dl>
    {job?.message && <p className={jobError ? 'narration-error-text' : 'muted'}>{job.message}{job.errorCode ? ` · ${job.errorCode}` : ''}</p>}
    <div className="qc-detail-block"><strong>checks</strong>{checks.length === 0 ? <span className="muted">まだありません</span> : <div className="qc-check-list">{checks.map((check, index) => { const name = displayQcValue(check.name ?? check.id ?? check.key ?? `check-${index + 1}`); const checkStatus = displayQcValue(check.status ?? check.verdict ?? check.result); const checkMessage = check.message ?? check.detail ?? check.reason; return <div className="qc-check-row" key={`${name}-${index}`}><span>{name}</span><b className={String(checkStatus).toLowerCase() === 'fail' ? 'is-fail' : String(checkStatus).toLowerCase() === 'pass' ? 'is-pass' : ''}>{checkStatus}</b>{checkMessage !== undefined && <small>{displayQcValue(checkMessage)}</small>}</div>; })}</div>}</div>
    <div className="qc-detail-block"><strong>media_facts</strong>{Object.keys(mediaFacts).length === 0 ? <span className="muted">まだありません</span> : <dl className="qc-facts">{Object.entries(mediaFacts).map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{displayQcValue(value)}</dd></div>)}</dl>}</div>
    <div className="narration-artifact-list"><strong>QC artifact</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} ↗</a>)}</div>
    <p className="gate-separation-note">技術QCは固定policy（schema v2 / local-ffmpeg-qc-v2）でcodec・尺・decode・音量・黒画面等を検査します。長い静止区間はwarningのみでtechnical verdictを変えません。creative QC、権利確認、公開可否を自動判定・承認する機能ではありません。</p>
  </section>;
}

function NarrationPanel({ detail, jobs, providers, onReload }: { detail: ProductionDetail; jobs: Job[]; providers: ProviderStatus[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => hasNarrationStage(run) && hasLocalSapiProfile(run))
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [script, setScript] = useState('');
  const [voice, setVoice] = useState('');
  const [rate, setRate] = useState(0);
  const [pronunciations, setPronunciations] = useState([{ source: '', target: '' }]);
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadedTerminalJob = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) setSelectedRunId(eligibleRuns[0]?.id ?? '');
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const normalizedInput = useMemo(() => normalizeNarrationInput(script, rate), [rate, script]);
  const { segments, errors: validationErrors } = normalizedInput;

  const currentAttempt = selectedRun?.stageAttempts[selectedRun.stageAttempts.length - 1];
  const visibleJob = job ?? jobs.find((item) => item.id === currentAttempt?.jobId || (item.runId === selectedRun?.id && (item.stage === 'narration' || item.type === 'local_narration')));
  const isTerminal = visibleJob?.status === 'succeeded' || visibleJob?.status === 'failed' || visibleJob?.status === 'cancelled';

  useEffect(() => {
    if (!job || isTerminal) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    const timer = window.setInterval(() => {
      void api.jobs().then((nextJobs) => {
        const next = nextJobs.find((item) => item.id === job.id);
        if (next) {
          setJob(next);
        }
      }).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [isTerminal, job, submitting]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const execute = async () => {
    if (submittingRef.current) return;
    if (!selectedRun) {
      setMessage({ type: 'error', text: 'ナレーション工程を含むRunを選択してください。' });
      return;
    }
    if (!hasLocalSapiProfile(selectedRun)) {
      setMessage({ type: 'error', text: 'このRunはlocal_sapi実行用ではありません。概要の再調整からローカル音声プロファイルでRunを作成してください。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    const pronunciationList = pronunciations
      .map(({ source, target }) => ({ source: source.trim(), target: target.trim() }))
      .filter(({ source, target }) => source && target);
    const request: LocalNarrationRequest = {
      segments: segments.map((text) => ({ text })),
      voice: voice.trim() || undefined,
      rate,
      pronunciations: pronunciationList.length > 0 ? pronunciationList : undefined,
    };
    setBusy(true);
    setJob(undefined);
    setMessage({ type: 'info', text: '実行をキューに登録しています。成功とはまだ判定していません。' });
    try {
      const submitted = await api.executeLocalNarration(selectedRun.id, request);
      setJob(submitted);
      setMessage({ type: submitted.status === 'failed' ? 'error' : 'success', text: submitted.status === 'failed' ? localNarrationError(submitted.message ?? 'workerが失敗しました') : 'ナレーションworkerをキューに登録しました。' });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: 'workerは登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (submitted.status === 'succeeded' || submitted.status === 'failed' || submitted.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: localNarrationError(error) });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  const addPronunciation = () => setPronunciations((current) => [...current, { source: '', target: '' }]);
  const updatePronunciation = (index: number, key: 'source' | 'target', value: string) => {
    setPronunciations((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item));
  };
  const removePronunciation = (index: number) => setPronunciations((current) => current.length === 1 ? current : current.filter((_, itemIndex) => itemIndex !== index));

  if (eligibleRuns.length === 0) {
    return <div className="narration-stack"><section className="panel narration-panel"><div className="panel-header"><div><span className="section-kicker">LOCAL NARRATION</span><h3>ローカル音声＋字幕worker</h3></div></div><EmptyState title="local_sapiのナレーションRunがありません" description="概要の再調整で narration を選択し、local_sapi プロファイルのRunを作成してください。" /></section><ExternalNarrationPanel detail={detail} jobs={jobs} providers={providers} onReload={onReload} /></div>;
  }

  const resultArtifacts = visibleJob?.result?.artifacts ?? currentAttempt?.artifacts ?? [];
  return (
    <div className="narration-stack">
      <div className="narration-grid">
      <div>
        <section className="panel narration-panel">
          <div className="panel-header"><div><span className="section-kicker">LOCAL NARRATION</span><h3>ローカル音声＋字幕worker</h3></div><span className="tag">費用 0円</span></div>
          <p className="panel-lead">SAPIをこのPC上で実行します。音声・字幕テキストは外部APIへ送信しません。backendの検証を正本とし、ここでは入力ミスを早期表示します。</p>
          <label className="field"><span>対象Run（narration工程を要求したものだけ）</span><select value={selectedRunId} disabled={busy || submitting} onChange={(event) => { setSelectedRunId(event.target.value); setJob(undefined); setMessage(undefined); }} aria-label="ナレーション対象Run">
            {eligibleRuns.map((run) => <option key={run.id} value={run.id}>{run.label} · {run.id}{run.executionProfile === 'local_sapi' ? ' · local_sapi' : ' · 別profile'}</option>)}
          </select></label>
          <div className="narration-run-summary"><span>Run ID</span><strong className="mono">{selectedRun?.id}</strong><span>要求工程</span><strong>{selectedRun?.requestedStages.map(stageLabel).join('、') || 'narration'}</strong><span>実行profile</span><strong>{selectedRun?.executionProfile ?? '未指定'}</strong></div>
          {!hasLocalSapiProfile(selectedRun) && <div className="notice notice-warning"><div><strong>local_sapiではありません</strong><p>このRunは履歴の閲覧対象ですが、ローカルworkerの実行対象にはできません。local_sapi Runを作成してください。</p></div></div>}
          <label className="field"><span>論理セグメント（1行=1セグメント、空行は除去）</span><textarea rows={9} value={script} onChange={(event) => setScript(event.target.value)} placeholder={'例：\nClaude Codeで、開発をもっと速く。\nまずはCLAUDE.mdを用意しましょう。'} aria-describedby="narration-segment-help" />
            <small id="narration-segment-help" className="field-help">{segments.length} / {LOCAL_NARRATION_LIMITS.maxSegments} セグメント · {segments.join('').length.toLocaleString()} / {LOCAL_NARRATION_LIMITS.maxTotalLength.toLocaleString()} 文字</small>
          </label>
          {validationErrors.length > 0 && <div className="validation-list" role="status">{validationErrors.map((error) => <div key={error}>・{error}</div>)}</div>}
          <div className="narration-form-grid">
            <label className="field"><span>Voice（任意）</span><input value={voice} onChange={(event) => setVoice(event.target.value)} placeholder="既定：ローカルSAPI" /></label>
            <label className="field"><span>Rate（-10〜10）</span><input type="number" min={-10} max={10} step={1} value={rate} onChange={(event) => setRate(Number(event.target.value))} /></label>
          </div>
          <fieldset className="pronunciation-fieldset"><legend>発音置換（任意）</legend>{pronunciations.map((item, index) => <div className="pronunciation-row" key={index}><input value={item.source} onChange={(event) => updatePronunciation(index, 'source', event.target.value)} placeholder="表記" aria-label={`発音置換 ${index + 1} 表記`} /><span aria-hidden="true">→</span><input value={item.target} onChange={(event) => updatePronunciation(index, 'target', event.target.value)} placeholder="読み" aria-label={`発音置換 ${index + 1} 読み`} /><button className="button button-ghost" type="button" onClick={() => removePronunciation(index)} disabled={pronunciations.length === 1}>削除</button></div>)}<button className="button button-secondary" type="button" onClick={addPronunciation}>＋置換を追加</button></fieldset>
          <div className="narration-confirm"><strong>実行前確認</strong><span>Run <b className="mono">{selectedRun?.id}</b> に {segments.length} セグメントを送信</span><span>外部送信なし · ローカルSAPI · 費用0円</span></div>
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={submitting || busy || validationErrors.length > 0 || !hasLocalSapiProfile(selectedRun)}>{submitting ? '登録中…' : busy ? 'worker監視中…' : 'ローカルナレーションを実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <NarrationJobStatus job={visibleJob} attempt={currentAttempt} artifacts={resultArtifacts} />
        <NarrationAttemptHistory attempts={selectedRun?.stageAttempts ?? []} />
      </aside>
      </div>
      <ExternalNarrationPanel detail={detail} jobs={jobs} providers={providers} onReload={onReload} />
    </div>
  );
}

function ExternalNarrationPanel({ detail, jobs, providers, onReload }: { detail: ProductionDetail; jobs: Job[]; providers: ProviderStatus[]; onReload: () => Promise<void> }) {
  const eligibleRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => hasNarrationStage(run) && hasElevenLabsProfile(run))
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );
  const elevenLabs = providers.find((provider) => ['elevenlabs', 'elevenlabs_tts'].includes(provider.id.toLowerCase()));
  const providerConfigured = elevenLabs?.configured === true;
  const [selectedRunId, setSelectedRunId] = useState(eligibleRuns[0]?.id ?? '');
  const [script, setScript] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [voiceSettings, setVoiceSettings] = useState<ExternalVoiceSettings>(DEFAULT_EXTERNAL_VOICE_SETTINGS);
  const [seed, setSeed] = useState<number | null>(0);
  const [payloadConfirmed, setPayloadConfirmed] = useState(false);
  const [job, setJob] = useState<Job>();
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const submittingRef = useRef(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success' | 'info'; text: string }>();
  const reloadedTerminalJob = useRef<string | undefined>(undefined);

  useEffect(() => {
    if (!eligibleRuns.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(eligibleRuns[0]?.id ?? '');
      setJob(undefined);
      setMessage(undefined);
      setPayloadConfirmed(false);
    }
  }, [eligibleRuns, selectedRunId]);

  const selectedRun = eligibleRuns.find((run) => run.id === selectedRunId);
  const gate = useMemo(
    () => getExternalNarrationGate(selectedRun, providerConfigured),
    [providerConfigured, selectedRun],
  );
  const normalizedInput = useMemo(
    () => normalizeExternalNarrationInput({
      provider: EXTERNAL_NARRATION_PROVIDER,
      model_id: EXTERNAL_NARRATION_MODEL,
      voiceId,
      script,
      voiceSettings,
      seed,
      confirmBillable: payloadConfirmed,
    }),
    [payloadConfirmed, script, seed, voiceId, voiceSettings],
  );
  const validationErrors = [
    ...normalizedInput.errors.filter((error) => !error.includes('課金対象のpayload')),
    ...gate.reasons,
  ];

  const currentAttempt = [...(selectedRun?.stageAttempts ?? [])]
    .filter((attempt) => normalizeRequestedStage(attempt.stage) === 'narration')
    .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? ''))[0];
  const visibleJob = job ?? jobs.find((item) =>
    item.id === currentAttempt?.jobId
    || (item.runId === selectedRun?.id && normalizeRequestedStage(item.stage ?? '') === 'narration'
      && ['external_narration', 'elevenlabs_narration', 'elevenlabs_tts'].includes(normalizeRequestedStage(item.type))),
  );
  const isTerminal = visibleJob?.status === 'succeeded' || visibleJob?.status === 'failed' || visibleJob?.status === 'cancelled';

  useEffect(() => {
    if (!job || isTerminal) {
      if (isTerminal && !submitting) setBusy(false);
      return;
    }
    const timer = window.setInterval(() => {
      void api.jobs().then((nextJobs) => {
        const next = nextJobs.find((item) => item.id === job.id);
        if (next) setJob(next);
      }).catch(() => undefined);
    }, 2_000);
    return () => window.clearInterval(timer);
  }, [isTerminal, job, submitting]);

  useEffect(() => {
    if (!visibleJob || !isTerminal || reloadedTerminalJob.current === visibleJob.id) return;
    reloadedTerminalJob.current = visibleJob.id;
    void onReload().catch(() => undefined);
  }, [isTerminal, onReload, visibleJob]);

  const updateVoiceSetting = <K extends keyof ExternalVoiceSettings>(key: K, value: ExternalVoiceSettings[K]) => {
    setVoiceSettings((current) => ({ ...current, [key]: value }));
    setPayloadConfirmed(false);
  };

  const execute = async () => {
    if (submittingRef.current) return;
    if (!selectedRun) {
      setMessage({ type: 'error', text: 'elevenlabs_ttsのナレーションRunを選択してください。' });
      return;
    }
    if (!gate.eligible) {
      setMessage({ type: 'error', text: gate.reasons[0] ?? '外部TTSの実行条件を満たしていません。' });
      return;
    }
    if (validationErrors.length > 0) {
      setMessage({ type: 'error', text: validationErrors[0] });
      return;
    }
    if (!payloadConfirmed) {
      setMessage({ type: 'error', text: '実行するpayloadと課金条件を確認するチェックが必要です。' });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setBusy(true);
    setJob(undefined);
    setMessage({ type: 'info', text: 'ElevenLabs外部TTSをキューに登録しています。provider応答を監視します。' });
    try {
      const request: ExternalNarrationRequest = normalizedInput.request;
      const submitted = await api.executeExternalNarration(selectedRun.id, request);
      setJob(submitted);
      setMessage({ type: submitted.status === 'failed' ? 'error' : 'success', text: submitted.status === 'failed' ? externalNarrationError(submitted.message ?? 'workerが失敗しました') : 'ElevenLabs外部TTSをキューに登録しました。' });
      try {
        await onReload();
      } catch {
        setMessage({ type: 'info', text: 'workerは登録済みです。制作詳細の再読込だけ失敗したため、job監視を継続します。' });
      }
      if (submitted.status === 'succeeded' || submitted.status === 'failed' || submitted.status === 'cancelled') setBusy(false);
    } catch (error) {
      setBusy(false);
      setMessage({ type: 'error', text: externalNarrationError(error) });
    } finally {
      submittingRef.current = false;
      setSubmitting(false);
    }
  };

  if (eligibleRuns.length === 0) {
    return <section className="panel external-narration-panel"><div className="panel-header"><div><span className="section-kicker">EXTERNAL ELEVENLABS</span><h3>外部音声＋字幕worker</h3></div><span className="tag">課金対象</span></div><p className="panel-lead">ElevenLabsは音声テキストを外部へ送信します。外部TTS専用の <b>elevenlabs_tts</b> profile、narration工程、正の見積、費用承認済みRunだけを実行できます。合成とQCはローカルで続けます。</p><EmptyState title="外部TTSの対象Runがありません" description="概要の再調整で narration を選択し、elevenlabs_tts プロファイルのRunを作成してください。Run作成後、正の見積額を承認すると実行できます。" /></section>;
  }

  const resultArtifacts = visibleJob?.result?.artifacts ?? currentAttempt?.artifacts ?? [];
  const approvedMaxLabel = gate.approvedMax === undefined ? '未承認' : formatMoney(gate.approvedMax, gate.approvedCurrency ?? gate.estimateCurrency);
  return (
    <div className="narration-grid external-narration-grid">
      <div>
        <section className="panel external-narration-panel">
          <div className="panel-header"><div><span className="section-kicker">EXTERNAL ELEVENLABS</span><h3>ElevenLabs外部音声＋字幕worker</h3></div><span className="tag tag-billable">課金対象</span></div>
          <p className="panel-lead">音声テキストをElevenLabsへ送信し、文字単位alignmentからsegment字幕を生成します。実行前にRunの見積・承認と、このpayloadの内容を二重に確認します。</p>
          <label className="field"><span>対象Run（elevenlabs_tts＋narration、費用承認済みのみ実行可能）</span><select value={selectedRunId} disabled={busy || submitting} onChange={(event) => { setSelectedRunId(event.target.value); setJob(undefined); setMessage(undefined); setPayloadConfirmed(false); }} aria-label="ElevenLabs外部ナレーション対象Run">
            {eligibleRuns.map((run) => { const runGate = getExternalNarrationGate(run, providerConfigured); return <option key={run.id} value={run.id}>{run.label} · {run.id} · {runGate.estimate === undefined ? '見積未設定' : formatMoney(runGate.estimate, runGate.estimateCurrency)} · {runGate.costApproved ? '承認済み' : '承認待ち'}</option>; })}
          </select></label>
          <div className="narration-run-summary external-run-summary"><span>Run ID</span><strong className="mono">{selectedRun?.id}</strong><span>実行profile</span><strong>{selectedRun?.executionProfile}</strong><span>Provider</span><strong>{EXTERNAL_NARRATION_PROVIDER}</strong><span>見積</span><strong>{gate.estimate === undefined ? '—' : formatMoney(gate.estimate, gate.estimateCurrency)}</strong><span>承認上限</span><strong>{approvedMaxLabel}</strong></div>
          {!providerConfigured && <div className="notice notice-warning"><div><strong>ElevenLabs providerが未設定です</strong><p>{elevenLabs?.message ?? 'Provider statusで認証情報を設定してから実行してください。'}</p></div></div>}
          {gate.reasons.length > 0 && <div className="validation-list" role="status">{gate.reasons.map((error) => <div key={error}>・{error}</div>)}</div>}
          <label className="field"><span>論理セグメント（1行=1segment、空行は除去）</span><textarea rows={9} value={script} onChange={(event) => { setScript(event.target.value); setPayloadConfirmed(false); }} placeholder={'例：\nClaude Codeで、開発をもっと速く。\nまずは字幕タイミングも保存します。'} aria-describedby="external-narration-segment-help" />
            <small id="external-narration-segment-help" className="field-help">{normalizedInput.request.segments.length} / {EXTERNAL_NARRATION_LIMITS.maxSegments} segment · {normalizedInput.totalCharacters.toLocaleString()} / {EXTERNAL_NARRATION_LIMITS.maxTotalLength.toLocaleString()} 文字</small>
          </label>
          <label className="field"><span>voice_id（ElevenLabs）</span><input value={voiceId} onChange={(event) => { setVoiceId(event.target.value); setPayloadConfirmed(false); }} placeholder="例：21m00Tcm4TlvDq8ikWAM" aria-label="ElevenLabs voice_id" /></label>
          <div className="narration-form-grid external-settings-grid">
            <label className="field"><span>stability（0〜1）</span><input type="number" min={0} max={1} step={0.01} value={voiceSettings.stability} onChange={(event) => updateVoiceSetting('stability', Number(event.target.value))} /></label>
            <label className="field"><span>similarity（0〜1）</span><input type="number" min={0} max={1} step={0.01} value={voiceSettings.similarityBoost} onChange={(event) => updateVoiceSetting('similarityBoost', Number(event.target.value))} /></label>
            <label className="field"><span>style（0〜1）</span><input type="number" min={0} max={1} step={0.01} value={voiceSettings.style} onChange={(event) => updateVoiceSetting('style', Number(event.target.value))} /></label>
            <label className="field"><span>speed（0.7〜1.2）</span><input type="number" min={0.7} max={1.2} step={0.01} value={voiceSettings.speed} onChange={(event) => updateVoiceSetting('speed', Number(event.target.value))} /></label>
          </div>
          <label className="toggle-field external-speaker-boost"><input type="checkbox" checked={voiceSettings.useSpeakerBoost} onChange={(event) => updateVoiceSetting('useSpeakerBoost', event.target.checked)} /><span><strong>speaker boost</strong><small>ElevenLabsのuse_speaker_boostとして送信</small></span></label>
          <label className="field inline-field"><span>seed</span><div><input type="number" min={0} max={EXTERNAL_NARRATION_LIMITS.maxSeed} step={1} value={seed ?? ''} onChange={(event) => { const value = event.target.value.trim(); setSeed(value === '' ? null : Number(value)); setPayloadConfirmed(false); }} /><span>0〜{EXTERNAL_NARRATION_LIMITS.maxSeed.toLocaleString()}</span></div></label>
          {normalizedInput.errors.filter((error) => !error.includes('課金対象のpayload')).length > 0 && <div className="validation-list" role="status">{normalizedInput.errors.filter((error) => !error.includes('課金対象のpayload')).map((error) => <div key={error}>・{error}</div>)}</div>}
          <div className="external-preflight" role="note"><strong>課金・payload最終確認</strong><dl><div><dt>Provider</dt><dd>{EXTERNAL_NARRATION_PROVIDER}</dd></div><div><dt>model_id</dt><dd className="mono">{EXTERNAL_NARRATION_MODEL}</dd></div><div><dt>voice_id</dt><dd className="mono">{voiceId.trim() || '未設定'}</dd></div><div><dt>総文字数</dt><dd>{normalizedInput.totalCharacters.toLocaleString()} 文字</dd></div><div><dt>Run estimate</dt><dd>{gate.estimate === undefined ? '未設定' : formatMoney(gate.estimate, gate.estimateCurrency)}</dd></div><div><dt>approved max</dt><dd>{approvedMaxLabel}</dd></div></dl><p>USD実費はprovider応答で未確定です。完了後にcharacter-costとprovider task IDを記録します。</p></div>
          <label className="external-second-confirm"><input type="checkbox" checked={payloadConfirmed} disabled={!gate.eligible || busy || submitting} onChange={(event) => setPayloadConfirmed(event.target.checked)} /><span><strong>このpayloadで課金対象のElevenLabs実行を明示確認する</strong><small>provider、model_id、voice_id、segment、voice settings、seed、見積上限を確認しました。送信payloadにはconfirm_billable: trueを付与します。</small></span></label>
          <button className="button button-primary full-button" type="button" onClick={() => void execute()} disabled={submitting || busy || !gate.eligible || validationErrors.length > 0 || !payloadConfirmed}>{submitting ? '登録中…' : busy ? 'provider監視中…' : '確認済みpayloadで外部TTSを実行'}</button>
          {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
        </section>
      </div>
      <aside>
        <ExternalNarrationJobStatus job={visibleJob} attempt={currentAttempt} artifacts={resultArtifacts} />
        <NarrationAttemptHistory attempts={selectedRun?.stageAttempts ?? []} />
      </aside>
    </div>
  );
}

function ExternalNarrationJobStatus({ job, attempt, artifacts }: { job?: Job; attempt?: StageAttempt; artifacts: Artifact[] }) {
  const status = job?.status ?? attempt?.status;
  const cacheHit = job?.cacheHit ?? attempt?.cacheHit;
  const result = job?.result;
  const provider = result?.provider ?? attempt?.provider;
  const providerTaskId = result?.providerTaskId ?? attempt?.providerTaskId;
  const characterCost = result?.characterCost ?? attempt?.characterCost;
  const actualUsd = result?.actualCostUsd !== undefined ? result.actualCostUsd : attempt?.actualCostUsd;
  const timingSource = result?.timingSource ?? attempt?.timingSource;
  const active = status === 'pending' || status === 'running';
  const actualUsdLabel = actualUsd === undefined || actualUsd === null ? '未確定' : formatMoney(actualUsd, 'USD');
  return <section className="panel compact-panel narration-status-panel external-status-panel" aria-live="polite" aria-busy={active}><div className="panel-header"><div><span className="section-kicker">EXTERNAL TTS STATUS</span><h3>ElevenLabs実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>{!job && !attempt && <p className="muted">実行すると、2秒間隔でjobを監視し、provider taskと成果物を表示します。</p>}<dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{job?.id ?? attempt?.jobId ?? '—'}</dd></div><div><dt>Attempt</dt><dd>{job?.attempt ?? attempt?.attempt ?? '—'}</dd></div><div><dt>Provider</dt><dd>{provider ?? EXTERNAL_NARRATION_PROVIDER}</dd></div><div><dt>Provider task ID</dt><dd className="mono">{providerTaskId ?? '—'}</dd></div><div><dt>Character cost</dt><dd>{characterCost === undefined ? '—' : characterCost.toLocaleString()}</dd></div><div><dt>USD実費</dt><dd>{actualUsdLabel}</dd></div><div><dt>Cache hit</dt><dd>{cacheHit === undefined ? '—' : cacheHit ? 'はい' : 'いいえ'}</dd></div><div><dt>Timing</dt><dd>{timingSource ?? '—'}</dd></div><div><dt>更新</dt><dd>{formatDate(job?.updatedAt ?? attempt?.finishedAt ?? attempt?.startedAt)}</dd></div></dl>{job?.message && <p className={job.status === 'failed' ? 'narration-error-text' : 'muted'}>{job.message}{job.errorCode ? ` · ${job.errorCode}` : ''}</p>}<div className="narration-artifact-list"><strong>生成artifact / hash</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <div className="external-artifact-row" key={artifact.id}>{artifact.url ? <a href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} ↗</a> : <span>{artifact.name}</span>}<small>{formatBytes(artifact.sizeBytes)} · SHA-256 <b className="mono">{artifact.sha256 ?? '未取得'}</b></small></div>)}</div><p className="gate-separation-note">外部送信は音声工程だけです。合成・technical QC・creative/rights/public gateとは別に記録します。</p></section>;
}

function NarrationJobStatus({ job, attempt, artifacts }: { job?: Job; attempt?: StageAttempt; artifacts: Artifact[] }) {
  const status = job?.status ?? attempt?.status;
  const cacheHit = job?.cacheHit ?? attempt?.cacheHit;
  const result = job?.result;
  const provider = result?.provider ?? attempt?.provider;
  const providerTaskId = result?.providerTaskId ?? attempt?.providerTaskId;
  const actualCost = result?.actualCost ?? attempt?.actualCost;
  const timingSource = result?.timingSource ?? attempt?.timingSource;
  const active = status === 'pending' || status === 'running';
  return <section className="panel compact-panel narration-status-panel" aria-live="polite" aria-busy={active}><div className="panel-header"><div><span className="section-kicker">WORKER STATUS</span><h3>実行状況</h3></div>{status ? <StatusBadge status={status} label={jobStatusLabel(status)} /> : <span className="muted">未実行</span>}</div>{!job && !attempt && <p className="muted">実行すると、キュー投入後の状態をここで監視します。</p>}<dl className="narration-metrics"><div><dt>Job</dt><dd className="mono">{job?.id ?? attempt?.jobId ?? '—'}</dd></div><div><dt>Attempt</dt><dd>{job?.attempt ?? attempt?.attempt ?? '—'}</dd></div><div><dt>Cache hit</dt><dd>{cacheHit === undefined ? '—' : cacheHit ? 'はい' : 'いいえ'}</dd></div><div><dt>所要時間</dt><dd>{formatDuration(job?.durationSeconds ?? attempt?.durationSeconds)}</dd></div><div><dt>Provider</dt><dd>{provider ?? '—'}</dd></div><div><dt>Provider task</dt><dd className="mono">{provider ? providerTaskId ?? 'なし' : '—'}</dd></div><div><dt>実費</dt><dd>{actualCost === undefined ? '—' : `${actualCost}（local）`}</dd></div><div><dt>Timing</dt><dd>{timingSource ?? '—'}</dd></div><div><dt>更新</dt><dd>{formatDate(job?.updatedAt ?? attempt?.finishedAt ?? attempt?.startedAt)}</dd></div></dl>{job?.message && <p className={job.status === 'failed' ? 'narration-error-text' : 'muted'}>{job.message}</p>}<div className="narration-artifact-list"><strong>生成artifact</strong>{artifacts.length === 0 ? <span className="muted">まだありません</span> : artifacts.map((artifact) => <a key={artifact.id} href={artifact.url} target="_blank" rel="noreferrer">{artifact.name} ↗</a>)}</div><p className="gate-separation-note">これはworkerの実行履歴です。費用承認・技術/表現/公開ゲートとは別の記録です。</p></section>;
}

function NarrationAttemptHistory({ attempts }: { attempts: StageAttempt[] }) {
  return <section className="panel compact-panel"><div className="panel-header"><div><span className="section-kicker">STAGE ATTEMPTS</span><h3>ナレーション試行履歴</h3></div><span className="count-chip">{attempts.length}</span></div>{attempts.length === 0 ? <p className="muted">stage attempt記録はまだありません。</p> : <div className="attempt-list">{attempts.map((attempt) => <article className="attempt-row" key={attempt.id}><div><strong>#{attempt.attempt ?? '—'} · {attempt.id}</strong><small>{formatDate(attempt.startedAt ?? attempt.createdAt)}{attempt.finishedAt ? ` → ${formatDate(attempt.finishedAt)}` : ''}</small></div><StatusBadge status={attempt.status} label={jobStatusLabel(attempt.status)} /><div><span>{attempt.cacheHit === undefined ? 'cache —' : attempt.cacheHit ? 'cache hit' : 'cache miss'}</span><span>{formatDuration(attempt.durationSeconds)}</span><span>{attempt.artifacts.length} artifact</span></div>{attempt.message && <p>{attempt.message}</p>}</article>)}</div>}</section>;
}

function RerunPanel({ productionId, onReload }: { productionId: string; onReload: () => Promise<void> }) {
  const [changes, setChanges] = useState<RerunChanges>({ stages: [], note: '', allowPaidApi: false, executionProfile: 'default' });
  const [plan, setPlan] = useState<RerunPlan>();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string }>();

  const toggleStage = (stage: string) => {
    if (changes.executionProfile === 'local_sapi' && !LOCAL_SAPI_STAGES.has(normalizeRequestedStage(stage))) return;
    if (changes.executionProfile === 'elevenlabs_tts' && !ELEVENLABS_TTS_STAGES.has(normalizeRequestedStage(stage))) return;
    if (changes.executionProfile === 'local_comfyui' && !LOCAL_COMFYUI_STAGES.has(normalizeRequestedStage(stage))) return;
    if (changes.executionProfile === 'local_windows_capture' && !LOCAL_WINDOWS_CAPTURE_STAGES.has(normalizeRequestedStage(stage))) return;
    if (changes.executionProfile === 'local_playwright' && !LOCAL_PLAYWRIGHT_STAGES.has(normalizeRequestedStage(stage))) return;
    setPlan(undefined);
    setChanges((current) => ({
      ...current,
      stages: current.stages.includes(stage) ? current.stages.filter((item) => item !== stage) : [...current.stages, stage],
    }));
  };

  const createPlan = async () => {
    if (changes.stages.length === 0) {
      setMessage({ type: 'error', text: '再実行する工程を1つ以上選択してください。' });
      return;
    }
    setBusy(true);
    setMessage(undefined);
    try {
      setPlan(await api.rerunPlan(productionId, changes));
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : '計画を作成できませんでした' });
    } finally {
      setBusy(false);
    }
  };

  const startRun = async () => {
    if (!plan) return;
    if (changes.executionProfile === 'local_sapi' && !changes.stages.some((stage) => LOCAL_SAPI_STAGES.has(normalizeRequestedStage(stage)))) {
      setMessage({ type: 'error', text: 'local_sapiはナレーション、字幕、カット編集、編集・合成、品質検査のいずれかを含むRunに指定してください。' });
      return;
    }
    if (changes.executionProfile === 'elevenlabs_tts' && !changes.stages.some((stage) => normalizeRequestedStage(stage) === 'narration')) {
      setMessage({ type: 'error', text: 'elevenlabs_ttsはnarration工程を必須にしてください。' });
      return;
    }
    if (changes.executionProfile === 'local_comfyui' && !changes.stages.some((stage) => ['video', 'video_generation'].includes(normalizeRequestedStage(stage)))) {
      setMessage({ type: 'error', text: 'local_comfyuiは生成映像（video_generation）工程を必須にしてください。' });
      return;
    }
    if (changes.executionProfile === 'local_windows_capture' && !changes.stages.some((stage) => normalizeRequestedStage(stage) === 'screen_capture')) {
      setMessage({ type: 'error', text: 'local_windows_captureは画面収録（screen_capture）工程を必須にしてください。' });
      return;
    }
    if (changes.executionProfile === 'local_playwright' && !changes.stages.some((stage) => normalizeRequestedStage(stage) === 'screen_capture')) {
      setMessage({ type: 'error', text: 'local_playwrightは画面収録（screen_capture）工程を必須にしてください。' });
      return;
    }
    if (changes.executionProfile === 'elevenlabs_tts' && (!Number.isFinite(changes.maxCostJpy) || (changes.maxCostJpy ?? 0) <= 0)) {
      setMessage({ type: 'error', text: 'elevenlabs_ttsは正の見積額（maxCostJpy）を必須にしてください。' });
      return;
    }
    if (plan.requiresCostEstimate && changes.executionProfile !== 'local_sapi' && changes.executionProfile !== 'local_comfyui' && changes.executionProfile !== 'local_windows_capture' && changes.executionProfile !== 'local_playwright' && (!changes.allowPaidApi || !changes.maxCostJpy || changes.maxCostJpy <= 0)) {
      setMessage({ type: 'error', text: '課金工程を含むため、有料APIの計画を有効にして見積額を入力してください。' });
      return;
    }
    setBusy(true);
    setMessage(undefined);
    try {
      await api.createRun(productionId, plan, changes);
      setMessage({ type: 'success', text: '新しいRunを登録しました。' });
      await onReload();
    } catch (error) {
      setMessage({ type: 'error', text: error instanceof Error ? error.message : 'Run計画を保存できませんでした' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel rerun-panel">
      <div className="panel-header"><div><span className="section-kicker">PARTIAL RERUN</span><h3>再調整</h3></div></div>
      <p className="panel-lead">変更箇所から再実行範囲と再利用候補を計算し、監査可能なRun計画として保存します。ローカル音声・ComfyUI動画・Playwright画面収録、またはElevenLabs外部音声をRun作成後に各タブから明示実行できます。</p>
      <fieldset className="stage-checks">
        <legend>変更する工程</legend>
        {RERUN_STAGES.map(([id, label]) => (
          <label key={id}>
            <input type="checkbox" checked={changes.stages.includes(id)} onChange={() => toggleStage(id)} disabled={(changes.executionProfile === 'local_sapi' && !LOCAL_SAPI_STAGES.has(id)) || (changes.executionProfile === 'elevenlabs_tts' && !ELEVENLABS_TTS_STAGES.has(id)) || (changes.executionProfile === 'local_comfyui' && !LOCAL_COMFYUI_STAGES.has(id)) || (changes.executionProfile === 'local_windows_capture' && !LOCAL_WINDOWS_CAPTURE_STAGES.has(id)) || (changes.executionProfile === 'local_playwright' && !LOCAL_PLAYWRIGHT_STAGES.has(id))} />
            <span>{label}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="execution-profile-fieldset"><legend>実行プロファイル</legend>
        <label className="profile-option"><input type="radio" name={`execution-profile-${productionId}`} value="default" checked={changes.executionProfile !== 'local_sapi' && changes.executionProfile !== 'elevenlabs_tts' && changes.executionProfile !== 'local_comfyui' && changes.executionProfile !== 'local_playwright'} onChange={() => { setPlan(undefined); setChanges((current) => ({ ...current, executionProfile: 'default' })); }} /><span><strong>通常</strong><small>既存のRun計画・費用ルールを使用</small></span></label>
        <label className="profile-option"><input type="radio" name={`execution-profile-${productionId}`} value="local_sapi" checked={changes.executionProfile === 'local_sapi'} onChange={() => { setPlan(undefined); setChanges((current) => ({ ...current, executionProfile: 'local_sapi', stages: ['narration'], allowPaidApi: false, maxCostJpy: undefined })); }} /><span><strong>local_sapi（ローカルworker）</strong><small>narration・字幕・カット編集・編集/合成・QC、見積0円・外部送信なし</small></span></label>
        <label className="profile-option"><input type="radio" name={`execution-profile-${productionId}`} value="local_comfyui" checked={changes.executionProfile === 'local_comfyui'} onChange={() => { setPlan(undefined); setChanges((current) => ({ ...current, executionProfile: 'local_comfyui', stages: ['video'], allowPaidApi: false, maxCostJpy: undefined })); }} /><span><strong>local_comfyui（ローカル動画worker）</strong><small>生成映像を実行。後続工程は影響計画として記録し、このprofileではまだ実行しません</small></span></label>
        <label className="profile-option"><input type="radio" name={`execution-profile-${productionId}`} value="local_windows_capture" checked={changes.executionProfile === 'local_windows_capture'} onChange={() => { setPlan(undefined); setChanges((current) => ({ ...current, executionProfile: 'local_windows_capture', stages: ['screen_capture'], allowPaidApi: false, maxCostJpy: undefined })); }} /><span><strong>local_windows_capture（Windows実画面・system audio）</strong><small>プライマリ画面と既定render loopbackを実行。後続工程は影響計画として記録します</small></span></label>
        <label className="profile-option"><input type="radio" name={`execution-profile-${productionId}`} value="local_playwright" checked={changes.executionProfile === 'local_playwright'} onChange={() => { setPlan(undefined); setChanges((current) => ({ ...current, executionProfile: 'local_playwright', stages: ['screen_capture'], allowPaidApi: false, maxCostJpy: undefined })); }} /><span><strong>local_playwright（Web画面収録）</strong><small>収録から開始し、timelineは後で明示実行。assembly／QCは影響記録のみ</small></span></label>
        <label className="profile-option"><input type="radio" name={`execution-profile-${productionId}`} value="elevenlabs_tts" checked={changes.executionProfile === 'elevenlabs_tts'} onChange={() => { setPlan(undefined); setChanges((current) => ({ ...current, executionProfile: 'elevenlabs_tts', stages: ['narration'], allowPaidApi: true, maxCostJpy: undefined })); }} /><span><strong>elevenlabs_tts（外部音声）</strong><small>音声だけ外部送信・課金、合成/QCはローカル。正の見積と承認が必要</small></span></label>
      </fieldset>
      <label className="field">
        <span>変更内容・理由</span>
        <textarea
          rows={3}
          value={changes.note}
          onChange={(event) => { setPlan(undefined); setChanges((current) => ({ ...current, note: event.target.value })); }}
          placeholder="例：CUT03後半の動きを増やす"
        />
      </label>
      <label className="toggle-field">
        <input
          type="checkbox"
          checked={changes.allowPaidApi}
          disabled={changes.executionProfile === 'local_sapi' || changes.executionProfile === 'local_comfyui' || changes.executionProfile === 'local_windows_capture' || changes.executionProfile === 'local_playwright' || changes.executionProfile === 'elevenlabs_tts'}
          onChange={(event) => { setPlan(undefined); setChanges((current) => ({ ...current, allowPaidApi: event.target.checked, executionProfile: event.target.checked ? 'default' : current.executionProfile })); }}
        />
          <span><strong>有料APIを使う計画</strong><small>{changes.executionProfile === 'local_sapi' ? 'local_sapiと相互排他的です' : changes.executionProfile === 'local_comfyui' ? 'local_comfyuiはローカルGPUで実行するため課金なしです' : changes.executionProfile === 'local_windows_capture' ? 'local_windows_captureはWindowsローカル収録のため課金なしです' : changes.executionProfile === 'local_playwright' ? 'local_playwrightはローカルChromiumで実行するため課金なしです' : changes.executionProfile === 'elevenlabs_tts' ? 'elevenlabs_ttsでは必須です。Run作成後に上限を承認します' : 'Run作成後、監査タブで上限を承認します'}</small></span>
      </label>
      {changes.allowPaidApi && (
        <label className="field inline-field">
          <span>見積額</span>
          <div><input type="number" min="0" step="100" value={changes.maxCostJpy ?? ''} onChange={(event) => setChanges((current) => ({ ...current, maxCostJpy: event.target.value ? Number(event.target.value) : undefined }))} /><span>円</span></div>
        </label>
      )}
      {!plan && <button className="button button-primary full-button" onClick={() => void createPlan()} disabled={busy}>{busy ? '計算中…' : '再実行計画を確認'}</button>}
      {plan && (
        <div className="plan-result">
          <div className="plan-result-title"><strong>実行前の影響範囲</strong><span>{plan.id ?? 'draft'}</span></div>
          {plan.summary && <p>{plan.summary}</p>}
          <dl>
            <div><dt>再実行</dt><dd>{(plan.stages.length ? plan.stages : changes.stages).map(stageLabel).join('、')}</dd></div>
            <div><dt>再利用</dt><dd>{plan.reusedStages.length ? plan.reusedStages.map(stageLabel).join('、') : 'APIから情報なし'}</dd></div>
            <div><dt>課金工程</dt><dd>{changes.executionProfile === 'local_sapi' || changes.executionProfile === 'local_comfyui' || changes.executionProfile === 'local_windows_capture' || changes.executionProfile === 'local_playwright' ? 'なし（ローカル）' : plan.billableStages.length ? plan.billableStages.map(stageLabel).join('、') : 'なし'}</dd></div>
            <div><dt>見積費用</dt><dd>{changes.executionProfile === 'local_sapi' || changes.executionProfile === 'local_comfyui' || changes.executionProfile === 'local_windows_capture' || changes.executionProfile === 'local_playwright' ? '0円（外部送信なし）' : plan.estimatedCost === undefined ? (plan.requiresCostEstimate ? (changes.maxCostJpy && changes.maxCostJpy > 0 ? formatMoney(changes.maxCostJpy, 'JPY') : '見積入力が必要') : '課金なし') : formatMoney(plan.estimatedCost, plan.currency)}</dd></div>
          </dl>
          <div className="button-row">
            <button className="button button-ghost" onClick={() => setPlan(undefined)} disabled={busy}>戻る</button>
            <button className="button button-primary" onClick={() => void startRun()} disabled={busy}>{busy ? '登録中…' : 'この内容でRunを作成'}</button>
          </div>
        </div>
      )}
      {message && <div className={`inline-message is-${message.type}`} role="status">{message.text}</div>}
    </section>
  );
}

function ArtifactsPanel({ artifacts }: { artifacts: Artifact[] }) {
  const [kind, setKind] = useState('all');
  const [selected, setSelected] = useState<Artifact>();
  const filtered = kind === 'all' ? artifacts : artifacts.filter((artifact) => artifact.kind === kind);
  const kinds = [...new Set(artifacts.map((artifact) => artifact.kind))];

  return (
    <section className="panel artifacts-panel">
      <div className="panel-header artifact-toolbar">
        <div><span className="section-kicker">ARTIFACT LIBRARY</span><h3>中間成果物・完成素材</h3></div>
        <div className="filter-chips" role="group" aria-label="成果物の種類">
          <button className={kind === 'all' ? 'is-active' : ''} onClick={() => setKind('all')}>すべて <span>{artifacts.length}</span></button>
          {kinds.map((item) => <button key={item} className={kind === item ? 'is-active' : ''} onClick={() => setKind(item)}>{item} <span>{artifacts.filter((artifact) => artifact.kind === item).length}</span></button>)}
        </div>
      </div>
      {filtered.length === 0 && <EmptyState title="表示できる成果物がありません" description="Run完了後、素材やログがここに並びます。" />}
      <div className="artifact-grid">
        {filtered.map((artifact) => (
          <article className="artifact-card" key={artifact.id}>
            <button className="artifact-preview-button" onClick={() => setSelected(artifact)} aria-label={`${artifact.name}をプレビュー`}>
              <ArtifactPreview artifact={artifact} compact />
            </button>
            <div className="artifact-info">
              <div><span className={`kind-label kind-${artifact.kind}`}>{artifact.kind}</span><span>{stageLabel(artifact.stage)}</span></div>
              <strong title={artifact.name}>{artifact.name}</strong>
              <small>{formatDate(artifact.createdAt)} · {formatBytes(artifact.sizeBytes)}</small>
              <div className="artifact-actions">
                <button onClick={() => setSelected(artifact)}>詳細</button>
                <a href={artifact.url} target="_blank" rel="noreferrer">開く ↗</a>
              </div>
            </div>
          </article>
        ))}
      </div>
      {selected && <ArtifactDialog artifact={selected} onClose={() => setSelected(undefined)} />}
    </section>
  );
}

function ArtifactDialog({ artifact, onClose }: { artifact: Artifact; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (!dialog.open) dialog.showModal();
    return () => { if (dialog.open) dialog.close(); };
  }, []);

  return (
    <dialog
      ref={dialogRef}
      className="artifact-dialog"
      aria-labelledby="artifact-dialog-title"
      onCancel={(event) => { event.preventDefault(); onClose(); }}
      onClick={(event) => { if (event.target === dialogRef.current) onClose(); }}
    >
      <div className="dialog-card">
        <header><div><span className={`kind-label kind-${artifact.kind}`}>{artifact.kind}</span><h3 id="artifact-dialog-title">{artifact.name}</h3></div><button className="icon-button" onClick={onClose} aria-label="閉じる" autoFocus>×</button></header>
        <div className="dialog-preview"><ArtifactPreview artifact={artifact} /></div>
        <dl className="artifact-details">
          <div><dt>工程</dt><dd>{stageLabel(artifact.stage)}</dd></div>
          <div><dt>作成日時</dt><dd>{formatDate(artifact.createdAt)}</dd></div>
          <div><dt>サイズ</dt><dd>{formatBytes(artifact.sizeBytes)}</dd></div>
          <div><dt>SHA-256</dt><dd className="mono">{artifact.sha256 ?? '—'}</dd></div>
          <div className="wide"><dt>保存先</dt><dd className="mono">{artifact.path ?? artifact.url ?? '—'}</dd></div>
        </dl>
        <footer><a className="button button-primary" href={artifact.url} target="_blank" rel="noreferrer">別画面で開く</a></footer>
      </div>
    </dialog>
  );
}

function ArtifactPreview({ artifact, compact = false }: { artifact: Artifact; compact?: boolean }) {
  if (!artifact.url) return <PreviewFallback artifact={artifact} />;
  if (artifact.kind === 'image') return <img className="media-preview" src={artifact.url} alt={artifact.name} loading="lazy" />;
  if (artifact.kind === 'video') return compact
    ? <video className="media-preview" src={`${artifact.url}#t=0.1`} muted preload="metadata" />
    : <video className="media-preview" src={artifact.url} controls preload="metadata" />;
  if (artifact.kind === 'audio') return compact
    ? <div className="audio-placeholder"><span aria-hidden="true">≋</span><small>AUDIO</small></div>
    : <div className="audio-full"><div className="audio-placeholder"><span aria-hidden="true">≋</span></div><audio src={artifact.url} controls preload="metadata" /></div>;
  if (artifact.kind === 'text') return compact ? <PreviewFallback artifact={artifact} /> : <TextPreview artifact={artifact} />;
  return <PreviewFallback artifact={artifact} />;
}

function TextPreview({ artifact }: { artifact: Artifact }) {
  const [content, setContent] = useState('読み込み中…');
  useEffect(() => {
    if (!artifact.url) return;
    const controller = new AbortController();
    fetch(artifact.url, { signal: controller.signal }).then(async (response) => {
      if (!response.ok) throw new Error(`${response.status}`);
      setContent((await response.text()).slice(0, 200_000));
    }).catch((error) => {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      setContent('テキストのプレビューを取得できませんでした。');
    });
    return () => controller.abort();
  }, [artifact.url]);
  return <pre className="text-preview">{content}</pre>;
}

function PreviewFallback({ artifact }: { artifact: Artifact }) {
  const marks: Record<string, string> = { text: 'TXT', document: 'DOC', archive: 'ZIP', other: 'FILE' };
  return <div className="preview-fallback"><span>{marks[artifact.kind] ?? artifact.kind.toUpperCase()}</span><small>{artifact.name}</small></div>;
}

function ComparisonPanel({ artifacts }: { artifacts: Artifact[] }) {
  const candidates = artifacts.filter((artifact) => ['video', 'audio', 'image'].includes(artifact.kind));
  const [leftId, setLeftId] = useState(candidates[0]?.id ?? '');
  const [rightId, setRightId] = useState(candidates[1]?.id ?? candidates[0]?.id ?? '');
  const left = candidates.find((artifact) => artifact.id === leftId);
  const right = candidates.find((artifact) => artifact.id === rightId);
  const leftMedia = useRef<HTMLMediaElement>(null);
  const rightMedia = useRef<HTMLMediaElement>(null);

  const mediaControl = (action: 'play' | 'pause' | 'sync') => {
    const a = leftMedia.current;
    const b = rightMedia.current;
    if (!a || !b) return;
    if (action === 'sync') b.currentTime = a.currentTime;
    if (action === 'pause') { a.pause(); b.pause(); }
    if (action === 'play') { void a.play(); void b.play(); }
  };

  if (candidates.length === 0) return <section className="panel"><EmptyState title="比較できる素材がありません" description="動画・音声・画像が2つ以上あるとA/B比較できます。" /></section>;
  const bothMedia = left && right && ['video', 'audio'].includes(left.kind) && left.kind === right.kind;

  return (
    <section className="panel comparison-panel">
      <div className="panel-header">
        <div><span className="section-kicker">VERSION REVIEW</span><h3>A/B比較</h3></div>
        {bothMedia && <div className="comparison-controls"><button onClick={() => mediaControl('play')}>両方再生</button><button onClick={() => mediaControl('pause')}>停止</button><button onClick={() => mediaControl('sync')}>BをAに同期</button></div>}
      </div>
      <p className="panel-lead">旧版と新版、生成候補やナレーションを並べて確認できます。</p>
      <div className="comparison-grid">
        <CompareSide label="A" artifact={left} candidates={candidates} value={leftId} onChange={setLeftId} mediaRef={leftMedia} />
        <CompareSide label="B" artifact={right} candidates={candidates} value={rightId} onChange={setRightId} mediaRef={rightMedia} />
      </div>
      {left && right && (
        <div className="comparison-metadata">
          <div><span>種類</span><strong>{left.kind}</strong><strong>{right.kind}</strong></div>
          <div><span>工程</span><strong>{stageLabel(left.stage)}</strong><strong>{stageLabel(right.stage)}</strong></div>
          <div><span>サイズ</span><strong>{formatBytes(left.sizeBytes)}</strong><strong>{formatBytes(right.sizeBytes)}</strong></div>
          <div><span>作成日時</span><strong>{formatDate(left.createdAt)}</strong><strong>{formatDate(right.createdAt)}</strong></div>
        </div>
      )}
    </section>
  );
}

function CompareSide({ label, artifact, candidates, value, onChange, mediaRef }: {
  label: string;
  artifact?: Artifact;
  candidates: Artifact[];
  value: string;
  onChange: (value: string) => void;
  mediaRef: React.RefObject<HTMLMediaElement | null>;
}) {
  return (
    <div className="compare-side">
      <div className="compare-select"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} aria-label={`比較素材 ${label}`}>
        {candidates.map((candidate) => <option key={candidate.id} value={candidate.id}>{candidate.name}</option>)}
      </select></div>
      <div className="compare-canvas">
        {!artifact && <PreviewFallback artifact={{ id: '', name: '未選択', kind: 'other', metadata: {}, raw: {} }} />}
        {artifact?.kind === 'video' && <video ref={mediaRef as React.RefObject<HTMLVideoElement>} src={artifact.url} controls preload="metadata" />}
        {artifact?.kind === 'audio' && <div className="audio-full"><div className="audio-placeholder"><span aria-hidden="true">≋</span></div><audio ref={mediaRef as React.RefObject<HTMLAudioElement>} src={artifact.url} controls preload="metadata" /></div>}
        {artifact?.kind === 'image' && <img src={artifact.url} alt={artifact.name} />}
      </div>
      {artifact && <div className="compare-name"><strong>{artifact.name}</strong><small>{artifact.sha256 ? `SHA ${artifact.sha256.slice(0, 12)}…` : artifact.path}</small></div>}
    </div>
  );
}

function LogPanel({ events }: { events: StudioEvent[] }) {
  const [level, setLevel] = useState('all');
  const [query, setQuery] = useState('');
  const filtered = events.filter((event) => {
    const levelMatches = level === 'all' || event.level === level;
    const textMatches = !query || `${event.message} ${event.stage ?? ''}`.toLowerCase().includes(query.toLowerCase());
    return levelMatches && textMatches;
  });
  return (
    <section className="panel log-panel">
      <div className="panel-header log-toolbar">
        <div><span className="section-kicker">EVENT STREAM</span><h3>Studioイベント</h3></div>
        <div className="log-filters">
          <select value={level} onChange={(event) => setLevel(event.target.value)} aria-label="ログレベル">
            <option value="all">すべてのレベル</option><option value="info">Info</option><option value="warning">Warning</option><option value="error">Error</option><option value="debug">Debug</option>
          </select>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="メッセージを検索" aria-label="ログを検索" />
        </div>
      </div>
      {filtered.length === 0 && <EmptyState title="一致するログがありません" />}
      <div className="event-list">
        {filtered.map((event) => (
          <article className={`event-row event-${event.level}`} key={event.id}>
            <time>{formatDate(event.timestamp)}</time>
            <span className="event-level">{event.level}</span>
            <span className="event-stage">{stageLabel(event.stage)}</span>
            <div><p>{event.message}</p>{event.details !== undefined && <details><summary>詳細データ</summary><pre>{JSON.stringify(event.details, null, 2)}</pre></details>}</div>
          </article>
        ))}
      </div>
    </section>
  );
}

function AuditPanel({ detail, onReload }: { detail: ProductionDetail; onReload: () => Promise<void> }) {
  const [exporting, setExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{ jobId?: string; error?: string }>();
  const groupedCosts = useMemo(() => {
    const result = new Map<string, number>();
    detail.costs.forEach((cost) => result.set(cost.currency, (result.get(cost.currency) ?? 0) + cost.amount));
    return [...result.entries()];
  }, [detail.costs]);
  const costApprovalRuns = useMemo(
    () => [...detail.runs]
      .filter((run) => (run.estimatedCost ?? 0) > 0)
      .sort((a, b) => (b.createdAt ?? '').localeCompare(a.createdAt ?? '')),
    [detail.runs],
  );

  const exportAudit = async () => {
    setExporting(true);
    setExportResult(undefined);
    try {
      const result = await api.exportAudit(detail.id);
      const record = result !== null && typeof result === 'object' ? result as Record<string, unknown> : {};
      setExportResult({ jobId: String(record.id ?? record.job_id ?? '登録済み') });
    } catch (error) {
      setExportResult({ error: error instanceof Error ? error.message : '監査パッケージを作成できませんでした' });
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="audit-grid">
      <div>
        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">COST LEDGER</span><h3>API費用</h3></div><div className="cost-total">{groupedCosts.map(([currency, amount]) => <strong key={currency}>{formatMoney(amount, currency)}</strong>)}</div></div>
          {detail.costs.length === 0 && <EmptyState title="費用記録がありません" />}
          {detail.costs.length > 0 && <table className="data-table cost-table"><thead><tr><th>日時</th><th>Provider</th><th>サービス</th><th>区分</th><th>金額</th></tr></thead><tbody>{detail.costs.map((cost) => <CostRow cost={cost} key={cost.id} />)}</tbody></table>}
        </section>
        <section className="panel">
          <div className="panel-header"><div><span className="section-kicker">COST APPROVAL TRAIL</span><h3>費用承認履歴</h3></div></div>
          {detail.approvals.length === 0 && <EmptyState title="費用承認記録がありません" />}
          <div className="approval-list">{detail.approvals.map((approval) => <ApprovalRow approval={approval} key={approval.id} />)}</div>
        </section>
      </div>
      <aside>
        <section className="panel compact-panel">
          <div className="panel-header"><div><span className="section-kicker">COST APPROVAL</span><h3>有料工程の費用上限</h3></div></div>
          <p className="panel-lead">正の見積を持つRun計画について、課金上限だけを承認または却下します。技術・表現・公開可否の判定とは別です。</p>
          {costApprovalRuns.length > 0
            ? <div className="approval-list">{costApprovalRuns.map((run) => <ApprovalControl key={run.id} run={run} onReload={onReload} />)}</div>
            : <p className="muted">費用承認が必要なRun計画はありません。</p>}
        </section>
        <section className="panel compact-panel audit-export">
          <div className="panel-header"><div><span className="section-kicker">AUDIT PACKAGE</span><h3>監査用書き出し</h3></div></div>
          <p>閲覧時点のStudio snapshot、イベント、格納entry hashと、台帳に存在する副生成物をまとめます。</p>
          <ul><li>audit/production-snapshot.json</li><li>audit/events.jsonl</li><li>audit/package-manifest.json</li><li>存在する台帳・ログ・QC sidecar</li></ul>
          <button className="button button-primary full-button" onClick={() => void exportAudit()} disabled={exporting}>{exporting ? '作成中…' : '監査パッケージを作成'}</button>
          {exportResult?.error && <div className="inline-message is-error">{exportResult.error}</div>}
          {exportResult?.jobId && <div className="inline-message is-success">書き出しジョブを登録しました：{exportResult.jobId}</div>}
        </section>
      </aside>
    </div>
  );
}

function CostRow({ cost }: { cost: CostEntry }) {
  return <tr><td>{formatDate(cost.createdAt)}</td><td><strong>{cost.provider}</strong></td><td>{cost.service ?? '—'}</td><td>{cost.estimated ? <span className="tag">見積</span> : '確定'}</td><td className="money-cell">{formatMoney(cost.amount, cost.currency)}</td></tr>;
}

function ApprovalRow({ approval }: { approval: Approval }) {
  return <article className="approval-row"><StatusBadge status={approval.status} label={costApprovalLabel(approval.status)} /><div><strong>{approval.target ?? 'Run費用上限'}</strong><p>{approval.note ?? 'コメントなし'}</p><small>{approval.approvedMax !== undefined ? `${formatMoney(approval.approvedMax, approval.currency ?? 'USD')} · ` : ''}{approval.reviewer ?? 'system'} · {formatDate(approval.createdAt)}</small></div></article>;
}

function ApprovalControl({ run, onReload }: { run: ProductionRun; onReload: () => Promise<void> }) {
  const [note, setNote] = useState('');
  const [maxCost, setMaxCost] = useState(run.estimatedCost ?? 0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string>();
  useEffect(() => setMaxCost(run.estimatedCost ?? 0), [run.id, run.estimatedCost]);
  const decide = async (approved: boolean) => {
    setBusy(true);
    setMessage(undefined);
    try {
      await api.approveRun(run.id, approved, note, maxCost, run.currency ?? 'USD');
      setMessage(approved ? '費用上限の承認を記録しました。' : '費用上限の却下を記録しました。');
      setNote('');
      await onReload();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '判断を記録できませんでした');
    } finally {
      setBusy(false);
    }
  };
  return <div className="approval-control"><div className="target-run"><span>対象Run計画</span><strong>{run.label}</strong><StatusBadge status={run.status} label={runCostApprovalLabel(run)} /></div><label className="field"><span>費用判断コメント</span><textarea rows={4} value={note} onChange={(event) => setNote(event.target.value)} placeholder="上限の承認・却下理由を記録" /></label><label className="field inline-field"><span>費用承認上限</span><div><input type="number" min="0" step="0.01" value={maxCost} onChange={(event) => setMaxCost(Number(event.target.value))} /><span>{run.currency ?? 'USD'}</span></div></label><div className="decision-buttons"><button className="button button-danger" onClick={() => void decide(false)} disabled={busy}>費用上限を却下</button><button className="button button-primary" onClick={() => void decide(true)} disabled={busy}>費用上限を承認</button></div>{message && <div className="inline-message">{message}</div>}</div>;
}

export default App;
