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
  executionProfile?: 'local_sapi' | string;
  stageAttempts: StageAttempt[];
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
  cacheHit?: boolean;
  provider?: string;
  providerTaskId?: string;
  actualCost?: number;
  timingSource?: string;
  artifacts: Artifact[];
  message?: string;
  errorCode?: string;
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
  specification?: Record<string, unknown>;
}

export interface JobResult {
  attempt?: number;
  artifacts: Artifact[];
  cacheHit?: boolean;
  durationSeconds?: number;
  provider?: string;
  providerTaskId?: string;
  actualCost?: number;
  timingSource?: string;
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

export interface Job {
  id: string;
  productionId?: string;
  runId?: string;
  type: string;
  stage?: string;
  status: StudioStatus;
  progress?: number;
  message?: string;
  startedAt?: string;
  updatedAt?: string;
  attempt?: number;
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
  executionProfile?: 'local_sapi' | 'default';
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
