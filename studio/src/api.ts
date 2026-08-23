import type {
  Approval,
  Artifact,
  ArtifactKind,
  CostEntry,
  HealthStatus,
  Job,
  JobResult,
  LocalNarrationRequest,
  ProductionDetail,
  ProductionRun,
  ProductionSummary,
  ProviderStatus,
  RerunChanges,
  RerunPlan,
  RunStage,
  StageAttempt,
  StudioEvent,
} from './types';
import { normalizeStatus } from './status';

type UnknownRecord = Record<string, unknown>;

const asRecord = (value: unknown): UnknownRecord =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as UnknownRecord) : {};

const pick = (record: UnknownRecord, keys: string[]): unknown => {
  for (const key of keys) {
    if (record[key] !== undefined && record[key] !== null) return record[key];
  }
  return undefined;
};

const text = (value: unknown, fallback = ''): string =>
  typeof value === 'string' || typeof value === 'number' ? String(value) : fallback;

const number = (value: unknown): number | undefined => {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
};

const durationSeconds = (record: UnknownRecord): number | undefined => {
  const seconds = number(pick(record, ['duration_seconds', 'duration', 'elapsed_seconds']));
  if (seconds !== undefined) return seconds;
  const milliseconds = number(pick(record, ['duration_ms', 'elapsed_ms']));
  return milliseconds === undefined ? undefined : milliseconds / 1000;
};

const boolean = (value: unknown, fallback = false): boolean => {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;
  if (typeof value === 'string') return ['true', '1', 'yes', 'ok', 'configured', 'healthy'].includes(value.toLowerCase());
  return fallback;
};

export const LOCAL_NARRATION_LIMITS = {
  maxSegments: 100,
  maxSegmentLength: 2_000,
  maxTotalLength: 50_000,
  minRate: -10,
  maxRate: 10,
} as const;

export interface NormalizedNarrationInput {
  segments: string[];
  errors: string[];
}

export const normalizeNarrationInput = (script: string, rate: number): NormalizedNarrationInput => {
  const segments = script.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const errors: string[] = [];
  if (segments.length === 0) errors.push('セグメントを1行以上入力してください。');
  if (segments.length > LOCAL_NARRATION_LIMITS.maxSegments) errors.push(`セグメントは${LOCAL_NARRATION_LIMITS.maxSegments}行以内にしてください。`);
  if (segments.some((segment) => segment.length > LOCAL_NARRATION_LIMITS.maxSegmentLength)) errors.push(`1行あたり${LOCAL_NARRATION_LIMITS.maxSegmentLength.toLocaleString()}文字以内にしてください。`);
  if (segments.join('').length > LOCAL_NARRATION_LIMITS.maxTotalLength) errors.push(`合計${LOCAL_NARRATION_LIMITS.maxTotalLength.toLocaleString()}文字以内にしてください。`);
  if (!Number.isInteger(rate) || rate < LOCAL_NARRATION_LIMITS.minRate || rate > LOCAL_NARRATION_LIMITS.maxRate) errors.push(`読み上げ速度は整数 ${LOCAL_NARRATION_LIMITS.minRate}〜${LOCAL_NARRATION_LIMITS.maxRate} の範囲で指定してください。`);
  return { segments, errors };
};

const list = (value: unknown): unknown[] => (Array.isArray(value) ? value : []);

const stringList = (value: unknown): string[] => list(value).map((item) => text(item)).filter(Boolean);

const items = (value: unknown, keys: string[]): unknown[] => {
  if (Array.isArray(value)) return value;
  const record = asRecord(value);
  for (const key of keys) {
    if (Array.isArray(record[key])) return record[key] as unknown[];
  }
  return [];
};

interface NormalizedError {
  message?: string;
  code?: string;
}

const normalizeError = (record: UnknownRecord, fallback = ''): NormalizedError => {
  const nested = asRecord(pick(record, ['error']));
  const rawErrorMessage = text(pick(record, ['error']), '');
  const message = text(pick(record, ['message', 'detail']), text(pick(nested, ['message', 'detail']), rawErrorMessage || fallback)) || undefined;
  const code = text(pick(record, ['error_code', 'errorCode']), text(pick(nested, ['code']), '')) || undefined;
  return { message, code };
};

const inferArtifactKind = (record: UnknownRecord): ArtifactKind => {
  const explicit = text(pick(record, ['kind', 'type', 'artifact_type']), '').toLowerCase();
  if (['subtitle', 'log'].includes(explicit)) return 'text';
  if (explicit === 'audit') return 'archive';
  if (explicit === 'document') {
    const name = text(pick(record, ['rel_path', 'path', 'name']), '').toLowerCase();
    const media = text(pick(record, ['media_type', 'mime_type', 'content_type']), '').toLowerCase();
    if (media.startsWith('text/') || /\.(md|txt|json|jsonl|ya?ml|csv|srt|ass|vtt|log)$/.test(name)) return 'text';
  }
  if (['video', 'audio', 'image', 'text', 'document', 'archive'].includes(explicit)) return explicit as ArtifactKind;
  const mime = text(pick(record, ['mime_type', 'mimeType', 'content_type', 'media_type']), '').toLowerCase();
  if (mime.startsWith('video/')) return 'video';
  if (mime.startsWith('audio/')) return 'audio';
  if (mime.startsWith('image/')) return 'image';
  if (mime.startsWith('text/') || mime.includes('json') || mime.includes('subtitle')) return 'text';
  if (mime.includes('pdf') || mime.includes('document')) return 'document';
  if (mime.includes('zip') || mime.includes('archive')) return 'archive';
  const path = text(pick(record, ['path', 'rel_path', 'filename', 'name', 'url', 'file_url']), '').toLowerCase().split('?')[0];
  if (/\.(mp4|mov|webm|mkv)$/.test(path)) return 'video';
  if (/\.(wav|mp3|m4a|flac|ogg)$/.test(path)) return 'audio';
  if (/\.(png|jpe?g|webp|gif|avif)$/.test(path)) return 'image';
  if (/\.(txt|md|json|jsonl|ya?ml|srt|ass|vtt|log)$/.test(path)) return 'text';
  if (/\.(pdf|docx?)$/.test(path)) return 'document';
  if (/\.(zip|tar|gz)$/.test(path)) return 'archive';
  return 'other';
};

const normalizeStage = (value: unknown, index: number): RunStage => {
  const record = asRecord(value);
  const primitiveName = text(value, '');
  return {
    id: text(pick(record, ['id', 'stage_id', 'key']), `stage-${index}`),
    name: text(pick(record, ['name', 'label', 'stage', 'key']), primitiveName || `工程 ${index + 1}`),
    status: Object.keys(record).length === 0 ? 'pending' : normalizeStatus(pick(record, ['status', 'state'])),
    startedAt: text(pick(record, ['started_at', 'startedAt']), '') || undefined,
    finishedAt: text(pick(record, ['finished_at', 'finishedAt', 'completed_at']), '') || undefined,
    message: text(pick(record, ['message', 'detail', 'error']), '') || undefined,
    progress: number(pick(record, ['progress', 'percent', 'percentage'])),
  };
};

export const normalizeRun = (value: unknown, index: number): ProductionRun => {
  const record = asRecord(value);
  const requestedStageValue = pick(record, ['requested_stages', 'requestedStages', 'stages', 'steps', 'pipeline']);
  const stageValues = items(requestedStageValue, ['items', 'stages', 'steps', 'requested_stages']);
  const requestedStages = stringList(stageValues.length > 0 ? stageValues : requestedStageValue);
  const estimatedCost = asRecord(pick(record, ['estimated_cost', 'cost']));
  const latestApprovalValue = pick(record, ['latest_approval', 'approval']);
  return {
    id: text(pick(record, ['id', 'run_id']), `run-${index}`),
    status: normalizeStatus(pick(record, ['status', 'state'])),
    label: text(pick(record, ['label', 'name', 'title', 'revision_id']), `Run ${index + 1}`),
    revision: number(pick(record, ['revision', 'version', 'revision_number'])),
    createdAt: text(pick(record, ['created_at', 'createdAt']), '') || undefined,
    startedAt: text(pick(record, ['started_at', 'startedAt']), '') || undefined,
    finishedAt: text(pick(record, ['finished_at', 'finishedAt', 'completed_at']), '') || undefined,
    stages: stageValues.map(normalizeStage),
    requestedStages,
    executionProfile: text(pick(record, ['execution_profile', 'executionProfile', 'profile']), '') || undefined,
    stageAttempts: items(pick(record, ['stage_attempts', 'stageAttempts', 'attempts']), ['items', 'stage_attempts', 'stageAttempts', 'attempts']).map(normalizeStageAttempt),
    estimatedCost: number(pick(estimatedCost, ['amount', 'value'])),
    currency: text(pick(estimatedCost, ['currency']), '') || undefined,
    latestApproval: latestApprovalValue ? normalizeApproval(latestApprovalValue, index) : undefined,
    raw: record,
  };
};

const normalizeArtifact = (value: unknown, index: number): Artifact => {
  const record = asRecord(value);
  const id = text(pick(record, ['id', 'artifact_id']), `artifact-${index}`);
  const path = text(pick(record, ['path', 'file_path', 'local_path', 'rel_path']), '') || undefined;
  const directUrl = text(pick(record, ['preview_url', 'download_url', 'content_url', 'file_url', 'url', 'href']), '') || undefined;
  const metadata = asRecord(pick(record, ['metadata', 'meta']));
  return {
    id,
    name: text(pick(record, ['name', 'label', 'filename', 'title']), path?.split(/[\\/]/).pop() || `成果物 ${index + 1}`),
    kind: inferArtifactKind(record),
    mimeType: text(pick(record, ['mime_type', 'mimeType', 'content_type', 'media_type']), '') || undefined,
    url: directUrl || `/api/artifacts/${encodeURIComponent(id)}/file`,
    path,
    stage: text(pick(record, ['stage', 'stage_name', 'category']), '') || undefined,
    runId: text(pick(record, ['run_id', 'runId']), '') || undefined,
    createdAt: text(pick(record, ['created_at', 'createdAt', 'modified_at']), '') || undefined,
    sizeBytes: number(pick(record, ['size_bytes', 'size', 'file_size', 'bytes'])),
    sha256: text(pick(record, ['sha256', 'hash', 'checksum']), '') || undefined,
    description: text(pick(record, ['description', 'summary']), '') || undefined,
    metadata,
    raw: record,
  };
};

const normalizeStageAttempt = (value: unknown, index: number): StageAttempt => {
  const record = asRecord(value);
  const stage = text(pick(record, ['stage', 'stage_name', 'name', 'type']), 'narration');
  const result = asRecord(pick(record, ['result', 'output']));
  const error = normalizeError(record, normalizeError(result).message ?? '');
  const artifactValues = items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  const resultArtifactValues = items(pick(result, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  const artifacts = (artifactValues.length > 0 ? artifactValues : resultArtifactValues).map(normalizeArtifact);
  return {
    id: text(pick(record, ['id', 'attempt_id', 'stage_attempt_id']), `stage-attempt-${index}`),
    stage,
    status: normalizeStatus(pick(record, ['status', 'state']) ?? pick(result, ['status', 'state'])),
    attempt: number(pick(record, ['attempt', 'attempt_number', 'try'])) ?? number(pick(result, ['attempt', 'attempt_number'])),
    jobId: text(pick(record, ['job_id', 'jobId']), '') || undefined,
    createdAt: text(pick(record, ['created_at', 'createdAt']), '') || undefined,
    startedAt: text(pick(record, ['started_at', 'startedAt']), '') || undefined,
    finishedAt: text(pick(record, ['finished_at', 'finishedAt', 'completed_at']), '') || undefined,
    durationSeconds: durationSeconds(record) ?? durationSeconds(result),
    cacheHit: pick(record, ['cache_hit', 'cacheHit', 'cached']) === undefined
      ? (pick(result, ['cache_hit', 'cacheHit', 'cached']) === undefined ? undefined : boolean(pick(result, ['cache_hit', 'cacheHit', 'cached'])))
      : boolean(pick(record, ['cache_hit', 'cacheHit', 'cached'])),
    provider: text(pick(record, ['provider']) ?? pick(result, ['provider']), '') || undefined,
    providerTaskId: text(pick(record, ['provider_task_id', 'providerTaskId']) ?? pick(result, ['provider_task_id', 'providerTaskId']), '') || undefined,
    actualCost: number(pick(record, ['actual_cost', 'actualCost']) ?? pick(result, ['actual_cost', 'actualCost'])),
    timingSource: text(pick(record, ['timing_source', 'timingSource']) ?? pick(result, ['timing_source', 'timingSource']), '') || undefined,
    artifacts,
    message: error.message,
    errorCode: error.code,
    raw: record,
  };
};

const normalizeJobResult = (value: unknown): JobResult | undefined => {
  if (!value || typeof value !== 'object') return undefined;
  const record = asRecord(value);
  const error = normalizeError(record);
  return {
    attempt: number(pick(record, ['attempt', 'attempt_number', 'try'])),
    artifacts: items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']).map(normalizeArtifact),
    cacheHit: pick(record, ['cache_hit', 'cacheHit', 'cached']) === undefined ? undefined : boolean(pick(record, ['cache_hit', 'cacheHit', 'cached'])),
    durationSeconds: durationSeconds(record),
    provider: text(pick(record, ['provider']), '') || undefined,
    providerTaskId: text(pick(record, ['provider_task_id', 'providerTaskId']), '') || undefined,
    actualCost: number(pick(record, ['actual_cost', 'actualCost'])),
    timingSource: text(pick(record, ['timing_source', 'timingSource']), '') || undefined,
    message: error.message,
    errorCode: error.code,
    raw: record,
  };
};

export const normalizeJob = (value: unknown, index = 0): Job => {
  const root = asRecord(value);
  const nested = asRecord(pick(root, ['job', 'data', 'item']));
  const record = Object.keys(nested).length > 0 ? nested : root;
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(payload, keys);
  const result = normalizeJobResult(pick(record, ['result', 'job_result', 'output'])) ?? normalizeJobResult(pick(root, ['result', 'job_result', 'output']));
  const error = normalizeError(record, result?.message ?? '');
  return {
    id: text(field(['id', 'job_id']), `job-${index}`),
    productionId: text(field(['production_id', 'productionId']), '') || undefined,
    runId: text(field(['run_id', 'runId']), '') || undefined,
    type: text(field(['type', 'kind', 'name']), 'ジョブ'),
    stage: text(field(['stage', 'step']), '') || undefined,
    status: normalizeStatus(field(['status', 'state'])),
    progress: number(field(['progress', 'percent', 'percentage'])),
    message: error.message,
    startedAt: text(field(['started_at', 'startedAt']), '') || undefined,
    updatedAt: text(field(['updated_at', 'updatedAt', 'finished_at', 'finishedAt', 'completed_at']), '') || undefined,
    attempt: number(field(['attempt', 'attempt_number', 'try'])) ?? result?.attempt,
    cacheHit: field(['cache_hit', 'cacheHit', 'cached']) === undefined ? result?.cacheHit : boolean(field(['cache_hit', 'cacheHit', 'cached'])),
    durationSeconds: durationSeconds(record) ?? durationSeconds(payload) ?? result?.durationSeconds,
    result,
    errorCode: error.code ?? result?.errorCode,
    raw: record,
  };
};

const normalizeEvent = (value: unknown, index: number): StudioEvent => {
  const record = asRecord(value);
  const eventType = text(pick(record, ['event_type', 'type']), '');
  const payload = asRecord(pick(record, ['payload', 'details', 'data']));
  const inferredLevel = /fail|error|reject/.test(eventType) ? 'error' : /warn|blocked/.test(eventType) ? 'warning' : 'info';
  const rawLevel = text(pick(record, ['level', 'severity']), inferredLevel).toLowerCase();
  const level = rawLevel === 'warn' ? 'warning' : rawLevel === 'fatal' ? 'error' : rawLevel;
  return {
    id: text(pick(record, ['id', 'event_id']), `event-${index}`),
    timestamp: text(pick(record, ['timestamp', 'created_at', 'time', 'at']), '') || undefined,
    level: ['debug', 'info', 'warning', 'error'].includes(level) ? (level as StudioEvent['level']) : 'info',
    stage: text(pick(record, ['stage', 'source', 'component']), text(pick(payload, ['stage', 'component']), '')) || undefined,
    message: text(pick(record, ['message', 'event', 'title', 'detail', 'event_type']), '記録'),
    details: pick(record, ['details', 'data', 'payload', 'metadata']) ?? (Object.keys(payload).length ? payload : undefined),
  };
};

const normalizeApproval = (value: unknown, index: number): Approval => {
  const record = asRecord(value);
  const approvedMax = asRecord(pick(record, ['approved_max', 'max_cost', 'approvedMax']));
  return {
    id: text(pick(record, ['id', 'approval_id']), `approval-${index}`),
    target: text(pick(record, ['target', 'gate', 'scope', 'run_id']), '') || undefined,
    status: normalizeStatus(pick(record, ['status', 'decision', 'state'])),
    reviewer: text(pick(record, ['reviewer', 'actor', 'approved_by']), '') || undefined,
    note: text(pick(record, ['note', 'comment', 'reason']), '') || undefined,
    createdAt: text(pick(record, ['created_at', 'createdAt', 'timestamp']), '') || undefined,
    approvedMax: number(pick(approvedMax, ['amount', 'value'])),
    currency: text(pick(approvedMax, ['currency']), '') || undefined,
  };
};

const normalizeCost = (value: unknown, index: number): CostEntry => {
  const record = asRecord(value);
  return {
    id: text(pick(record, ['id', 'cost_id']), `cost-${index}`),
    provider: text(pick(record, ['provider', 'vendor']), '不明'),
    service: text(pick(record, ['service', 'model', 'operation']), '') || undefined,
    amount: number(pick(record, ['amount', 'cost', 'total'])) ?? 0,
    currency: text(pick(record, ['currency']), 'JPY').toUpperCase(),
    estimated: boolean(pick(record, ['estimated', 'is_estimate']), false),
    createdAt: text(pick(record, ['created_at', 'createdAt', 'timestamp']), '') || undefined,
    raw: record,
  };
};

const normalizeProduction = (value: unknown, index: number): ProductionSummary => {
  const record = asRecord(value);
  const tags = list(pick(record, ['tags', 'labels'])).map((tag) => text(tag)).filter(Boolean);
  return {
    id: text(pick(record, ['id', 'production_id', 'slug']), `production-${index}`),
    title: text(pick(record, ['title', 'name', 'display_name']), `制作 ${index + 1}`),
    status: normalizeStatus(pick(record, ['status', 'state'])),
    updatedAt: text(pick(record, ['updated_at', 'updatedAt', 'modified_at', 'refreshed_at', 'latest_job_at']), '') || undefined,
    createdAt: text(pick(record, ['created_at', 'createdAt', 'discovered_at']), '') || undefined,
    durationSeconds: number(pick(record, ['duration_seconds', 'duration', 'duration_sec'])),
    thumbnailUrl: text(pick(record, ['thumbnail_url', 'thumbnail', 'poster_url']), '') || undefined,
    description: text(pick(record, ['description', 'summary']), '') || undefined,
    activeRunId: text(pick(record, ['active_run_id', 'latest_run_id', 'run_id']), '') || undefined,
    technicalStatus: pick(record, ['technical_status']) === undefined ? undefined : normalizeStatus(record.technical_status),
    creativeStatus: pick(record, ['creative_status']) === undefined ? undefined : normalizeStatus(record.creative_status),
    publicReleaseStatus: pick(record, ['public_release_status']) === undefined ? undefined : normalizeStatus(record.public_release_status),
    tags,
    raw: record,
  };
};

interface ParsedApiError {
  message: string;
  code?: string;
}

export class StudioApiError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly unsupported: boolean;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = 'StudioApiError';
    this.status = status;
    this.code = code;
    this.unsupported = status === 404 || status === 405 || code === 'unsupported' || code === 'unsupported_media_type' || code === 'not_implemented';
  }
}

const parseError = async (response: Response): Promise<ParsedApiError> => {
  const body = await response.text();
  if (!body) return { message: `${response.status} ${response.statusText}` };
  try {
    const parsed = asRecord(JSON.parse(body));
    const nested = asRecord(parsed.error);
    return {
      message: text(pick(parsed, ['message', 'detail']), text(pick(nested, ['message', 'detail']), body)),
      code: text(pick(parsed, ['code']), text(pick(nested, ['code']), '')) || undefined,
    };
  } catch {
    return { message: body };
  }
};

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const parsed = await parseError(response);
    throw new StudioApiError(parsed.message, response.status, parsed.code);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
};

const post = <T>(path: string, body?: unknown): Promise<T> =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  async health(): Promise<HealthStatus> {
    try {
      const value = await request<unknown>('/api/health');
      const record = asRecord(value);
      const rawStatus = text(pick(record, ['status', 'state']), 'ok').toLowerCase();
      return {
        healthy: boolean(pick(record, ['healthy', 'ok']), ['ok', 'healthy', 'ready'].includes(rawStatus)),
        degraded: boolean(pick(record, ['degraded']), false),
        message: text(pick(record, ['message', 'detail']), rawStatus === 'ok' ? 'API接続中' : rawStatus),
        version: text(pick(record, ['version', 'api_version', 'schema_version']), '') || undefined,
      };
    } catch (error) {
      return { healthy: false, message: error instanceof Error ? error.message : 'APIに接続できません' };
    }
  },

  async productions(): Promise<ProductionSummary[]> {
    const value = await request<unknown>('/api/productions');
    return items(value, ['items', 'productions', 'data']).map(normalizeProduction);
  },

  async production(id: string): Promise<ProductionDetail> {
    const value = await request<unknown>(`/api/productions/${encodeURIComponent(id)}`);
    const root = asRecord(value);
    const productionRecord = asRecord(pick(root, ['production', 'item', 'data']));
    const source = Object.keys(productionRecord).length > 0 ? productionRecord : root;
    const base = normalizeProduction(source, 0);
    const section = (key: string): unknown => root[key] ?? source[key];
    const runs = items(section('runs'), ['items', 'runs']).map(normalizeRun);
    const directApprovals = items(section('approvals'), ['items', 'approvals']).map(normalizeApproval);
    const approvals = directApprovals.length > 0
      ? directApprovals
      : runs.flatMap((run) => run.latestApproval ? [{ ...run.latestApproval, target: run.label || run.id }] : []);
    const directCosts = items(section('costs'), ['items', 'costs']).map(normalizeCost);
    const costs = directCosts.length > 0
      ? directCosts
      : runs.flatMap((run, index) => run.estimatedCost === undefined ? [] : [{
          id: `run-cost-${run.id}`,
          provider: 'Run見積',
          service: run.label,
          amount: run.estimatedCost,
          currency: run.currency ?? 'USD',
          estimated: true,
          createdAt: run.createdAt,
          raw: run.raw,
        } satisfies CostEntry]);
    return {
      ...base,
      runs,
      artifacts: items(section('artifacts'), ['items', 'artifacts']).map(normalizeArtifact),
      events: items(section('events'), ['items', 'events', 'logs']).map(normalizeEvent),
      approvals,
      costs,
      specification: asRecord(pick(root, ['specification', 'spec', 'production_spec'])),
    };
  },

  async jobs(): Promise<Job[]> {
    const value = await request<unknown>('/api/jobs');
    return items(value, ['items', 'jobs', 'data']).map(normalizeJob);
  },

  async providers(): Promise<ProviderStatus[]> {
    const value = await request<unknown>('/api/providers/status');
    return items(value, ['items', 'providers', 'data']).map((item, index) => {
      const record = asRecord(item);
      const id = text(pick(record, ['id', 'provider_id', 'key']), `provider-${index}`);
      return {
        id,
        name: text(pick(record, ['name', 'label', 'provider']), id),
        configured: boolean(pick(record, ['configured', 'enabled', 'available']), false),
        healthy: pick(record, ['healthy', 'ok', 'reachable']) === undefined
          ? undefined
          : boolean(pick(record, ['healthy', 'ok', 'reachable'])),
        message: text(pick(record, ['message', 'detail', 'status']), '') || undefined,
        lastChecked: text(pick(record, ['last_checked', 'checked_at', 'updated_at']), '') || undefined,
      };
    });
  },

  refreshIndex: (): Promise<unknown> => post('/api/index/refresh'),

  async rerunPlan(productionId: string, changes: RerunChanges): Promise<RerunPlan> {
    const changeList = changes.stages.map((stage) => ({
      type: stage,
      note: changes.note,
    }));
    const value = await post<unknown>(`/api/productions/${encodeURIComponent(productionId)}/rerun-plan`, {
      changes: changeList,
    });
    const record = asRecord(value);
    return {
      id: text(pick(record, ['id', 'plan_id']), '') || undefined,
      stages: list(pick(record, ['affected_stages', 'stages', 'rerun_stages', 'invalidated_stages'])).map((item) => text(item)).filter(Boolean),
      reusedStages: list(pick(record, ['reused_stages', 'cached_stages', 'reuse'])).map((item) => text(item)).filter(Boolean),
      billableStages: list(pick(record, ['billable_stages'])).map((item) => text(item)).filter(Boolean),
      requiresCostEstimate: boolean(pick(record, ['requires_cost_estimate']), false),
      estimatedCost: number(pick(record, ['estimated_cost', 'cost', 'estimated_cost_jpy'])),
      currency: text(pick(record, ['currency']), 'JPY'),
      summary: text(pick(record, ['summary', 'message', 'description']), '') || undefined,
      raw: record,
    };
  },

  createRun: (productionId: string, plan: RerunPlan, changes: RerunChanges): Promise<unknown> => {
    const changeList = changes.stages.map((stage) => ({ type: stage, note: changes.note }));
    const estimatedAmount = plan.estimatedCost ?? (changes.allowPaidApi ? changes.maxCostJpy ?? 0 : 0);
    const body: Record<string, unknown> = {
      changes: changeList,
      estimated_cost: {
        amount: estimatedAmount,
        currency: plan.currency ?? (changes.allowPaidApi ? 'JPY' : 'USD'),
      },
    };
    if (changes.executionProfile === 'local_sapi') {
      body.execution_profile = 'local_sapi';
      body.estimated_cost = { amount: 0, currency: 'JPY' };
    }
    return post(`/api/productions/${encodeURIComponent(productionId)}/runs`, body);
  },

  async executeLocalNarration(runId: string, body: LocalNarrationRequest): Promise<Job> {
    const value = await post<unknown>(`/api/runs/${encodeURIComponent(runId)}/execute-local-narration`, body);
    return normalizeJob(value);
  },

  approveRun: (runId: string, approved: boolean, note: string, maxCost: number, currency: string): Promise<unknown> =>
    post(`/api/runs/${encodeURIComponent(runId)}/approve`, {
      approved,
      max_cost: { amount: approved ? maxCost : 0, currency },
      actor: 'local_user',
      note,
    }),

  exportAudit: (productionId: string): Promise<unknown> =>
    post(`/api/productions/${encodeURIComponent(productionId)}/audit-export`, { include_media: false }),
};
