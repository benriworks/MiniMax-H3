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
  tags: string[];
  raw: Record<string, unknown>;
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
  transitionToNext: LocalRemotionTimelineTransition | null;
  overlay: LocalRemotionTimelineOverlay | null;
}

export interface LocalRemotionTimelineRequest {
  clips: LocalRemotionTimelineClip[];
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
  executionProfile?: 'local_sapi' | 'local_comfyui' | 'local_playwright' | 'local_pipeline' | 'elevenlabs_tts' | 'default';
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
