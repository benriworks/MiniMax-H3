export type StudioStatus =
  | 'pending'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'blocked'
  | 'approved'
  | 'rejected'
  | 'cancelled'
  | 'unknown';

export interface ProductionSummary {
  id: string;
  title: string;
  status: StudioStatus;
  updatedAt?: string;
  createdAt?: string;
  durationSeconds?: number;
  thumbnailUrl?: string;
  description?: string;
  activeRunId?: string;
  technicalStatus?: StudioStatus;
  creativeStatus?: StudioStatus;
  publicReleaseStatus?: StudioStatus;
  archived: boolean;
  archivedAt?: string;
  libraryReadOnly: boolean;
  tags: string[];
  raw: Record<string, unknown>;
}

export type ProductionLibraryAction = 'rename' | 'archive' | 'duplicate';

/** Verified response projection for one idempotent library mutation. */
export interface ProductionLibraryMutationResponse {
  schemaVersion: 1;
  operationId: string;
  action: ProductionLibraryAction;
  production: ProductionSummary;
  sourceProductionId?: string;
  includeImports?: boolean;
  importedArtifactCount?: number;
  deduplicated: boolean;
}

/** Exact request body for creating a production from the Studio UI. */
export interface ProductionCreatePayload {
  schema_version: 1;
  production_id: string;
  title: string;
}

export interface RunStage {
  id: string;
  name: string;
  status: StudioStatus;
  startedAt?: string;
  finishedAt?: string;
  message?: string;
  progress?: number;
}

export type PipelineContinuationState =
  | 'active'
  | 'waiting_provider'
  | 'ready'
  | 'continuing'
  | 'succeeded'
  | 'recovery_blocked'
  | 'unavailable'
  | 'cancel_requested'
  | 'cancelled';

export interface PipelineContinuationError {
  code?: string;
  message?: string;
}

/** Safe public projection for automatic local-pipeline continuation. */
export interface PipelineContinuation {
  state: PipelineContinuationState;
  automatic: boolean;
  resumeCount?: number;
  jobId?: string;
  sourceJobId?: string;
  sourceAttemptId?: string;
  updatedAt?: string;
  error: PipelineContinuationError | null;
  raw: Record<string, unknown>;
}

export interface ProductionRun {
  id: string;
  status: StudioStatus;
  label: string;
  revision?: number;
  createdAt?: string;
  startedAt?: string;
  finishedAt?: string;
  stages: RunStage[];
  requestedStages: string[];
  executionProfile?: 'local_sapi' | 'local_comfyui' | 'local_playwright' | 'local_pipeline' | string;
  stageAttempts: StageAttempt[];
  providerTasks?: ProviderTask[];
  pipelineContinuation?: PipelineContinuation;
  estimatedCost?: number;
  currency?: string;
  latestApproval?: Approval;
  raw: Record<string, unknown>;
}

export type ArtifactKind = 'video' | 'audio' | 'image' | 'text' | 'document' | 'archive' | 'other';

export interface Artifact {
  id: string;
  name: string;
  kind: ArtifactKind;
  mimeType?: string;
  url?: string;
  path?: string;
  stage?: string;
  runId?: string;
  createdAt?: string;
  sizeBytes?: number;
  sha256?: string;
  durationSeconds?: number;
  description?: string;
  metadata: Record<string, unknown>;
  raw: Record<string, unknown>;
}

export interface StageAttempt {
  id: string;
  stage: string;
  status: StudioStatus;
  attempt?: number;
  jobId?: string;
  createdAt?: string;
  startedAt?: string;
  finishedAt?: string;
  durationSeconds?: number;
  durationMs?: number;
  cacheHit?: boolean;
  provider?: string;
  providerTaskId?: string;
  promptSha256?: string;
  seed?: number | string;
  workflowPreset?: string;
  /** Provider-reported billable character count (external TTS only). */
  characterCost?: number;
  /** Provider-reported USD cost. null means the provider has not finalized it. */
  actualCostUsd?: number | null;
  actualCost?: number;
  timingSource?: string;
  analysisStatus?: string;
  technicalVerdict?: LocalQcVerdict;
  assemblyAttemptId?: string;
  variant?: LocalQcVariant;
  checks?: QcCheck[];
  mediaFacts?: Record<string, unknown>;
  artifacts: Artifact[];
  message?: string;
  errorCode?: string;
  raw: Record<string, unknown>;
}

export type ProviderTaskStatus =
  | 'prepared'
  | 'submitted'
  | 'recovering'
  | 'succeeded'
  | 'failed'
  | 'ambiguous'
  | 'recovery_blocked'
  | 'cancel_requested'
  | 'unknown';

export interface ProviderTaskError {
  code?: string;
  message?: string;
}

/** Public recovery projection for one provider task; never contains prompt text. */
export interface ProviderTask {
  id: string;
  provider: string;
  productionId?: string;
  runId?: string;
  stage?: string;
  status: ProviderTaskStatus;
  providerTaskId?: string;
  attemptSequence?: number;
  activeStageAttemptId?: string;
  activeJobId?: string;
  recoveryCount?: number;
  automaticRecoveryAvailable: boolean;
  duplicateSubmissionBlocked: boolean;
  resumable: boolean;
  nextAction?: string;
  createdAt?: string;
  updatedAt?: string;
  checkedAt?: string;
  error?: ProviderTaskError;
  raw: Record<string, unknown>;
}

export interface StudioEvent {
  id: string;
  timestamp?: string;
  level: 'debug' | 'info' | 'warning' | 'error';
  stage?: string;
  message: string;
  details?: unknown;
}

export interface Approval {
  id: string;
  target?: string;
  status: StudioStatus;
  reviewer?: string;
  note?: string;
  createdAt?: string;
  approvedMax?: number;
  currency?: string;
}

export interface CostEntry {
  id: string;
  provider: string;
  service?: string;
  amount: number;
  currency: string;
  estimated: boolean;
  createdAt?: string;
  raw: Record<string, unknown>;
}

export interface ProductionDetail extends ProductionSummary {
  runs: ProductionRun[];
  artifacts: Artifact[];
  events: StudioEvent[];
  approvals: Approval[];
  costs: CostEntry[];
  providerTasks?: ProviderTask[];
  announcementRecipes: AnnouncementRecipeRecord[];
  announcementRecipeVersions: AnnouncementRecipeRecord[];
  announcementExecutions: AnnouncementExecutionRecord[];
  specification?: Record<string, unknown>;
}

export interface JobResult {
  runId?: string;
  revisionId?: string;
  attempt?: number;
  stageAttemptId?: string;
  artifacts: Artifact[];
  cacheHit?: boolean;
  durationSeconds?: number;
  durationMs?: number;
  provider?: string;
  providerTaskId?: string;
  promptSha256?: string;
  seed?: number | string;
  workflowPreset?: string;
  /** Provider-reported billable character count (external TTS only). */
  characterCost?: number;
  /** Provider-reported USD cost. null means the provider has not finalized it. */
  actualCostUsd?: number | null;
  actualCost?: number;
  timingSource?: string;
  structuralTimingVerified?: boolean;
  contentSyncVerified?: boolean;
  liveValidationRequired?: boolean;
  validationScope?: string;
  publicReleaseReady?: boolean;
  publicReleaseGate?: string;
  analysisStatus?: string;
  technicalVerdict?: LocalQcVerdict;
  jobs?: Record<string, LocalPipelineStageResult>;
  assemblyAttemptId?: string;
  variant?: LocalQcVariant;
  checks?: QcCheck[];
  mediaFacts?: Record<string, unknown>;
  message?: string;
  errorCode?: string;
  raw: Record<string, unknown>;
}

export interface LocalNarrationSegment {
  text: string;
}

export interface PronunciationOverride {
  source: string;
  target: string;
}

export interface LocalNarrationRequest {
  segments: LocalNarrationSegment[];
  voice?: string;
  rate?: number;
  pronunciations?: PronunciationOverride[];
}

export interface ExternalVoiceSettings {
  stability: number;
  similarityBoost: number;
  style: number;
  useSpeakerBoost: boolean;
  speed: number;
}

/** Browser-facing request. api.ts converts this to the strict snake_case wire payload. */
export interface ExternalNarrationRequest {
  provider: 'elevenlabs';
  model_id: 'eleven_multilingual_v2';
  voiceId: string;
  segments: Array<{ text: string }>;
  voiceSettings: ExternalVoiceSettings;
  seed: number | null;
  confirmBillable: boolean;
}

export interface ExternalNarrationPayload {
  provider: 'elevenlabs';
  model_id: 'eleven_multilingual_v2';
  voice_id: string;
  segments: Array<{ text: string }>;
  voice_settings: {
    stability: number;
    similarity_boost: number;
    style: number;
    use_speaker_boost: boolean;
    speed: number;
  };
  seed: number | null;
  confirm_billable: boolean;
}

export type LocalAssemblyCaptionStylePreset = 'studio_default_v1' | 'shorts_ja_large_v1';
export type LocalAssemblyAudioMixPreset = 'narration_only_v1' | 'source_under_narration_v1';

export interface LocalAssemblyRequest {
  videoArtifactId: string;
  narrationAttemptId: string;
  includeCaptioned: boolean;
  captionStylePreset: LocalAssemblyCaptionStylePreset;
  audioMixPreset: LocalAssemblyAudioMixPreset;
}

export interface LocalTimelineClip {
  videoArtifactId: string;
  startMs: number;
  endMs: number;
}

export interface LocalTimelineRequest {
  clips: LocalTimelineClip[];
}

export type LocalRemotionTimelineOverlayPosition = 'top' | 'center' | 'bottom';

export type LocalRemotionTimelineVisualPreset = 'preserve_v1' | 'h3_low_res_sharp_v1';

export interface LocalRemotionTimelineTransition {
  type: 'fade';
  durationMs: number;
}

export interface LocalRemotionTimelineOverlay {
  text: string;
  startMs: number;
  endMs: number;
  position: LocalRemotionTimelineOverlayPosition;
  stylePreset: 'shorts_ja_large_v1';
}

export interface LocalRemotionTimelineClip extends LocalTimelineClip {
  volumePercent: number;
  /** Omitted legacy/browser preview values normalize to preserve_v1 before submission. */
  visualPreset?: LocalRemotionTimelineVisualPreset;
  transitionToNext: LocalRemotionTimelineTransition | null;
  overlay: LocalRemotionTimelineOverlay | null;
}

export interface LocalRemotionTimelineRequest {
  clips: LocalRemotionTimelineClip[];
}

/** Browser-facing recipe for one audited narration -> Remotion -> assembly -> QC job. */
export interface DetailedTestVideoRequest {
  schemaVersion: 1;
  clips: LocalRemotionTimelineClip[];
  segments: LocalNarrationSegment[];
  voice?: string;
  rate: number;
  pronunciations?: PronunciationOverride[];
  includeCaptioned: boolean;
  captionStylePreset: LocalAssemblyCaptionStylePreset;
  audioMixPreset: LocalAssemblyAudioMixPreset;
  variant: LocalQcVariant;
}

export type AnnouncementSceneRole = 'hook' | 'message' | 'cta';

export interface AnnouncementVideoScene {
  role: AnnouncementSceneRole;
  videoArtifactId: string;
  startMs: number;
  endMs: number;
  volumePercent: number;
  /** Missing only in legacy stored revisions; normalization resolves it to preserve_v1. */
  visualPreset?: LocalRemotionTimelineVisualPreset;
  headline: string;
  narration: string;
}

/** Editable browser form for the closed HOOK -> MESSAGE -> CTA template. */
export interface AnnouncementVideoRecipe {
  schemaVersion: 1;
  name: string;
  templatePreset: 'shorts_ja_15s_v1';
  scenes: AnnouncementVideoScene[];
  voice?: string;
  rate: number;
  pronunciations: PronunciationOverride[];
  includeCaptioned: boolean;
  captionStylePreset: LocalAssemblyCaptionStylePreset;
  audioMixPreset: LocalAssemblyAudioMixPreset;
  variant: LocalQcVariant;
}

export interface AnnouncementRecipeRecord {
  id: string;
  versionId: string;
  productionId: string;
  revision: number;
  parentVersionId?: string;
  cloneSourceVersionId?: string;
  digest: string;
  createdAt?: string;
  versionCount: number;
  recipe: AnnouncementVideoRecipe;
  raw: Record<string, unknown>;
}

export interface AnnouncementExecutionRecord {
  recipeId: string;
  recipeVersionId: string;
  recipeRevision: number;
  recipeDigest: string;
  jobId: string;
  runId: string;
  revisionId: string;
  requestKey: string;
  deduplicated: boolean;
  createdAt?: string;
  raw: Record<string, unknown>;
}

export type LocalScreenCaptureAction =
  | { type: 'scroll'; atMs: number; deltaY: number }
  | { type: 'click'; atMs: number; selector: string }
  | { type: 'press'; atMs: number; selector: string; key: string };

export interface LocalScreenCaptureRequest {
  url: string;
  durationMs: number;
  settleMs: number;
  actions: LocalScreenCaptureAction[];
}

/** Browser-facing request for the closed Windows primary-display capture contract. */
export interface WindowsCaptureRequest {
  durationMs: number;
  confirmCapture: boolean;
  confirmSystemAudio: boolean;
}

/** Fixed settings payload shared by the consent-intent and execute requests. */
export interface WindowsCapturePayload {
  schema_version: 1;
  target: 'primary_display';
  audio_mode: 'default_render_loopback';
  cursor_mode: 'hidden';
  duration_ms: number;
  confirm_capture: true;
  confirm_system_audio: true;
}

/** Short-lived response returned by the explicit consent-intent endpoint. */
export interface WindowsCaptureConsentIntent {
  schema_version: 1;
  consent_intent_id: string;
  consent_token: string;
  run_id: string;
  request_settings_digest: string;
  issued_at: string;
  expires_at: string;
  expires_in_seconds: 60;
}

/** Exact wire payload accepted by the consent-bound execute endpoint. */
export interface WindowsCaptureExecutionPayload extends WindowsCapturePayload {
  consent_token: string;
}

export type LocalQcVariant = 'clean' | 'captioned';

export type LocalQcVerdict = 'pass' | 'fail';

export interface LocalQcRequest {
  assemblyAttemptId: string;
  variant: LocalQcVariant;
}

export interface QcCheck {
  name?: string;
  status?: string;
  message?: string;
  [key: string]: unknown;
}

export interface Job {
  id: string;
  productionId?: string;
  runId?: string;
  /** Non-secret lineage key for one explicit Windows capture consent. */
  consentIntentId?: string;
  type: string;
  stage?: string;
  status: StudioStatus;
  progress?: number;
  progressPhase?: string;
  message?: string;
  startedAt?: string;
  updatedAt?: string;
  attempt?: number;
  stageAttemptId?: string;
  assemblyAttemptId?: string;
  variant?: LocalQcVariant;
  cacheHit?: boolean;
  durationSeconds?: number;
  result?: JobResult;
  errorCode?: string;
  raw: Record<string, unknown>;
}

export interface ProviderStatus {
  id: string;
  name: string;
  configured: boolean;
  healthy?: boolean;
  message?: string;
  lastChecked?: string;
}

export interface WindowsCaptureCapability {
  schemaVersion: number;
  implementationVersion: string;
  status: 'ready' | 'blocked';
  captureExecutionEnabled: boolean;
  screenCaptureReady: boolean;
  systemAudioLoopbackReady: boolean;
  explicitConfirmationRequired: boolean;
  actualCapturePerformed: boolean;
  reasons: string[];
  helper: {
    available: boolean;
    doctorOk: boolean;
    endpointActive: boolean;
    loopbackInitialized: boolean;
    recordingStarted: boolean;
    captureCommandAvailable: boolean;
    sha256?: string;
  };
  ffmpeg: {
    available: boolean;
    gdigrabAvailable: boolean;
    ffprobeAvailable: boolean;
  };
  display: {
    target: 'primary_display';
    width: number | null;
    height: number | null;
  };
  toolIdentityDigest?: string;
}

export interface WindowsCaptureCancelResponse {
  job?: Job;
  cancelRequested: boolean;
  workerRetired: boolean;
  raw: Record<string, unknown>;
}

export interface ArtifactImportResponse {
  artifact?: Artifact;
  deduplicated: boolean;
  raw: Record<string, unknown>;
}

export interface JobCancellationResponse {
  job?: Job;
  status?: string;
  cancelRequested?: boolean;
  workerRetired?: boolean;
  raw: Record<string, unknown>;
}

export interface HealthStatus {
  healthy: boolean;
  degraded?: boolean;
  message: string;
  version?: string;
}

export interface RerunChanges {
  stages: string[];
  note: string;
  allowPaidApi: boolean;
  maxCostJpy?: number;
  executionProfile?: 'local_sapi' | 'local_comfyui' | 'local_playwright' | 'local_windows_capture' | 'local_pipeline' | 'elevenlabs_tts' | 'default';
}

/** Browser-facing request for the pinned local ComfyUI video worker. */
export interface LocalComfyUiRequest {
  workflowPreset: string;
  prompt: string;
  /** Decimal text keeps the complete 0..2^63-1 range lossless in the form. */
  seed: string;
}

export interface LocalPipelineRequest {
  workflowPreset: string;
  prompt: string;
  /** Decimal text keeps the complete 0..2^63-1 range lossless in the form. */
  seed: string;
  segments: LocalNarrationSegment[];
  voice?: string;
  rate: number;
  pronunciations?: PronunciationOverride[];
  includeCaptioned: boolean;
  captionStylePreset: LocalAssemblyCaptionStylePreset;
  variant: LocalQcVariant;
}

export interface LocalPipelineStageResult {
  stage: string;
  status: StudioStatus;
  jobId?: string;
  stageAttemptId?: string;
  attempt?: number;
  cacheHit?: boolean;
  progress?: number;
  message?: string;
  artifacts: Artifact[];
  raw: Record<string, unknown>;
}

export interface RerunPlan {
  id?: string;
  stages: string[];
  reusedStages: string[];
  billableStages: string[];
  requiresCostEstimate: boolean;
  estimatedCost?: number;
  currency?: string;
  summary?: string;
  raw: Record<string, unknown>;
}
