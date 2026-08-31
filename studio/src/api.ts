import type {
  Approval,
  AnnouncementExecutionRecord,
  AnnouncementRecipeRecord,
  AnnouncementSceneRole,
  AnnouncementVideoRecipe,
  AnnouncementVideoScene,
  Artifact,
  ArtifactImportResponse,
  ArtifactKind,
  CostEntry,
  DetailedTestVideoRequest,
  ExternalNarrationPayload,
  ExternalNarrationRequest,
  ExternalVoiceSettings,
  HealthStatus,
  Job,
  JobCancellationResponse,
  JobResult,
  LocalAssemblyAudioMixPreset,
  LocalAssemblyCaptionStylePreset,
  LocalAssemblyRequest,
  LocalComfyUiRequest,
  LocalPipelineRequest,
  LocalPipelineStageResult,
  LocalScreenCaptureAction,
  LocalScreenCaptureRequest,
  LocalRemotionTimelineClip,
  LocalRemotionTimelineOverlay,
  LocalRemotionTimelineOverlayPosition,
  LocalRemotionTimelineRequest,
  LocalRemotionTimelineTransition,
  LocalRemotionTimelineVisualPreset,
  LocalTimelineClip,
  LocalTimelineRequest,
  LocalQcRequest,
  LocalQcVariant,
  LocalQcVerdict,
  LocalNarrationRequest,
  ProductionDetail,
  ProductionCreatePayload,
  ProductionRun,
  ProductionLibraryMutationResponse,
  PipelineContinuation,
  PipelineContinuationState,
  ProductionSummary,
  ProviderTask,
  ProviderTaskStatus,
  ProviderStatus,
  ReviewAction,
  ReviewCategory,
  ReviewDecision,
  ReviewGate,
  ReviewGates,
  ReviewIdentity,
  ReviewMutationResponse,
  ReviewRevisionPlan,
  ReviewThread,
  RerunChanges,
  RerunPlan,
  QcCheck,
  RunStage,
  StageAttempt,
  StudioEvent,
  WindowsCaptureCapability,
  WindowsCaptureCancelResponse,
  WindowsCaptureConsentIntent,
  WindowsCaptureExecutionPayload,
  WindowsCapturePayload,
  WindowsCaptureRequest,
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

const pickIncludingNull = (record: UnknownRecord, keys: string[]): unknown => {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(record, key)) return record[key];
  }
  return undefined;
};

const numberOrNull = (value: unknown): number | null | undefined => value === null ? null : number(value);

const durationSeconds = (record: UnknownRecord): number | undefined => {
  const seconds = number(pick(record, ['duration_seconds', 'duration', 'elapsed_seconds']));
  if (seconds !== undefined) return seconds;
  const milliseconds = number(pick(record, ['duration_ms', 'elapsed_ms']));
  return milliseconds === undefined ? undefined : milliseconds / 1000;
};

/** Calculate worker wall time without confusing it with the rendered media duration. */
export const elapsedSecondsBetween = (startedAt?: string, finishedAt?: string): number | undefined => {
  if (!startedAt || !finishedAt) return undefined;
  const started = Date.parse(startedAt);
  const finished = Date.parse(finishedAt);
  if (!Number.isFinite(started) || !Number.isFinite(finished) || finished < started) return undefined;
  return (finished - started) / 1_000;
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

export const EXTERNAL_NARRATION_PROVIDER = 'elevenlabs' as const;
export const EXTERNAL_NARRATION_MODEL = 'eleven_multilingual_v2' as const;
export const EXTERNAL_TTS_PROVIDER = EXTERNAL_NARRATION_PROVIDER;
export const EXTERNAL_TTS_MODEL = EXTERNAL_NARRATION_MODEL;

/** Public limits mirror the external narration adapter contract. */
export const EXTERNAL_NARRATION_LIMITS = {
  maxSegments: 100,
  maxSegmentLength: 4_000,
  maxTotalLength: 100_000,
  maxVoiceIdLength: 128,
  minStability: 0,
  maxStability: 1,
  minSimilarity: 0,
  maxSimilarity: 1,
  minStyle: 0,
  maxStyle: 1,
  minSpeed: 0.7,
  maxSpeed: 1.2,
  minSeed: 0,
  maxSeed: 4_294_967_295,
} as const;

export const DEFAULT_EXTERNAL_VOICE_SETTINGS: ExternalVoiceSettings = {
  stability: 0.5,
  similarityBoost: 0.75,
  style: 0,
  useSpeakerBoost: true,
  speed: 1,
};

export interface NormalizedExternalNarrationInput {
  request: ExternalNarrationRequest;
  payload: ExternalNarrationPayload;
  totalCharacters: number;
  errors: string[];
}

const externalSettingNumber = (
  record: UnknownRecord,
  keys: string[],
  fallback: number,
  min: number,
  max: number,
  label: string,
  errors: string[],
): number => {
  const raw = pickIncludingNull(record, keys);
  if (raw === undefined || raw === '') return fallback;
  const value = number(raw);
  if (value === undefined || !Number.isFinite(value)) {
    errors.push(`${label}は数値で指定してください。`);
    return fallback;
  }
  if (value < min || value > max) {
    errors.push(`${label}は${min}〜${max}の範囲で指定してください。`);
    return Math.min(max, Math.max(min, value));
  }
  return value;
};

const externalSettingBoolean = (
  record: UnknownRecord,
  keys: string[],
  fallback: boolean,
  label: string,
  errors: string[],
): boolean => {
  const raw = pickIncludingNull(record, keys);
  if (raw === undefined || raw === '') return fallback;
  if (typeof raw !== 'boolean') {
    errors.push(`${label}はbooleanで指定してください。`);
    return fallback;
  }
  return raw;
};

const externalTextSegments = (source: UnknownRecord): string[] => {
  const rawSegments = pick(source, ['segments']);
  if (Array.isArray(rawSegments)) {
    return rawSegments.map((segment) => {
      if (typeof segment === 'string') return segment;
      const record = asRecord(segment);
      return text(pick(record, ['text']), '');
    });
  }
  const script = text(pick(source, ['script', 'text', 'narration']), '');
  return script.split(/\r?\n/);
};

/**
 * Normalize the external ElevenLabs draft and build the complete audit-safe
 * request. Unknown fields are intentionally ignored; the wire payload is
 * built from this allowlist only.
 *
 * The overload-like positional form is retained for small contract tests and
 * callers that already have a script string:
 * normalizeExternalNarrationInput(script, voiceId, settings, seed, confirm).
 */
export const normalizeExternalNarrationInput = (
  value: unknown,
  voiceIdValue?: unknown,
  settingsValue?: unknown,
  seedValue?: unknown,
  confirmBillableValue?: unknown,
): NormalizedExternalNarrationInput => {
  const source = typeof value === 'string'
    ? {
        script: value,
        voiceId: voiceIdValue,
        voiceSettings: settingsValue,
        seed: seedValue,
        confirmBillable: confirmBillableValue,
      }
    : asRecord(value);
  const errors: string[] = [];

  const providedProvider = text(pick(source, ['provider']), '').trim().toLowerCase();
  if (providedProvider && providedProvider !== EXTERNAL_NARRATION_PROVIDER) {
    errors.push(`providerは${EXTERNAL_NARRATION_PROVIDER}に固定されています。`);
  }
  const providedModel = text(pick(source, ['model_id', 'model']), '').trim();
  if (providedModel && providedModel !== EXTERNAL_NARRATION_MODEL) {
    errors.push(`modelは${EXTERNAL_NARRATION_MODEL}に固定されています。`);
  }

  const rawVoiceIdValue = pick(source, ['voiceId', 'voice_id']);
  if (rawVoiceIdValue !== undefined && typeof rawVoiceIdValue !== 'string') {
    errors.push('voice_idは文字列で指定してください。');
  }
  const rawVoiceId = typeof rawVoiceIdValue === 'string' ? rawVoiceIdValue.trim() : '';
  if (!rawVoiceId) errors.push('voice_idを指定してください。');
  if (rawVoiceId.length > EXTERNAL_NARRATION_LIMITS.maxVoiceIdLength) {
    errors.push(`voice_idは${EXTERNAL_NARRATION_LIMITS.maxVoiceIdLength}文字以内にしてください。`);
  }
  if (rawVoiceId && !/^[A-Za-z0-9_-]+$/.test(rawVoiceId)) {
    errors.push('voice_idは英数字、ハイフン、アンダースコアで指定してください。');
  }

  const rawSegments = externalTextSegments(source);
  const segments = rawSegments.map((segment) => segment.trim()).filter(Boolean);
  if (segments.length === 0) errors.push('セグメントを1行以上入力してください。');
  if (segments.length > EXTERNAL_NARRATION_LIMITS.maxSegments) {
    errors.push(`セグメントは${EXTERNAL_NARRATION_LIMITS.maxSegments}行以内にしてください。`);
  }
  if (segments.some((segment) => segment.length > EXTERNAL_NARRATION_LIMITS.maxSegmentLength)) {
    errors.push(`1行あたり${EXTERNAL_NARRATION_LIMITS.maxSegmentLength.toLocaleString()}文字以内にしてください。`);
  }
  if (segments.some((segment) => /[\u0000-\u001f\u007f]/.test(segment))) {
    errors.push('セグメントに制御文字は使用できません。');
  }
  const totalCharacters = segments.join('').length;
  if (totalCharacters > EXTERNAL_NARRATION_LIMITS.maxTotalLength) {
    errors.push(`合計${EXTERNAL_NARRATION_LIMITS.maxTotalLength.toLocaleString()}文字以内にしてください。`);
  }

  const voiceSettings = asRecord(pick(source, ['voiceSettings', 'voice_settings']));
  const stability = externalSettingNumber(
    voiceSettings,
    ['stability'],
    DEFAULT_EXTERNAL_VOICE_SETTINGS.stability,
    EXTERNAL_NARRATION_LIMITS.minStability,
    EXTERNAL_NARRATION_LIMITS.maxStability,
    'stability',
    errors,
  );
  const similarityBoost = externalSettingNumber(
    voiceSettings,
    ['similarityBoost', 'similarity_boost', 'similarity'],
    DEFAULT_EXTERNAL_VOICE_SETTINGS.similarityBoost,
    EXTERNAL_NARRATION_LIMITS.minSimilarity,
    EXTERNAL_NARRATION_LIMITS.maxSimilarity,
    'similarity',
    errors,
  );
  const style = externalSettingNumber(
    voiceSettings,
    ['style'],
    DEFAULT_EXTERNAL_VOICE_SETTINGS.style,
    EXTERNAL_NARRATION_LIMITS.minStyle,
    EXTERNAL_NARRATION_LIMITS.maxStyle,
    'style',
    errors,
  );
  const useSpeakerBoost = externalSettingBoolean(
    voiceSettings,
    ['useSpeakerBoost', 'use_speaker_boost', 'speakerBoost', 'speaker_boost'],
    DEFAULT_EXTERNAL_VOICE_SETTINGS.useSpeakerBoost,
    'speaker boost',
    errors,
  );
  const speed = externalSettingNumber(
    voiceSettings,
    ['speed'],
    DEFAULT_EXTERNAL_VOICE_SETTINGS.speed,
    EXTERNAL_NARRATION_LIMITS.minSpeed,
    EXTERNAL_NARRATION_LIMITS.maxSpeed,
    'speed',
    errors,
  );

  const rawSeed = pick(source, ['seed']);
  let seed: number | null = 0;
  if (rawSeed === null || rawSeed === '') {
    seed = null;
  } else if (rawSeed !== undefined) {
    const parsedSeed = number(rawSeed);
    if (parsedSeed === undefined || !Number.isInteger(parsedSeed)) {
      errors.push('seedは整数で指定してください。');
    } else if (parsedSeed < EXTERNAL_NARRATION_LIMITS.minSeed || parsedSeed > EXTERNAL_NARRATION_LIMITS.maxSeed) {
      errors.push(`seedは${EXTERNAL_NARRATION_LIMITS.minSeed}〜${EXTERNAL_NARRATION_LIMITS.maxSeed.toLocaleString()}の範囲で指定してください。`);
    } else {
      seed = parsedSeed;
    }
  }

  const confirmBillable = pick(source, ['confirmBillable', 'confirm_billable']) === true;
  if (!confirmBillable) errors.push('課金対象のpayloadを確認してから実行を確定してください。');

  const request: ExternalNarrationRequest = {
    provider: EXTERNAL_NARRATION_PROVIDER,
    model_id: EXTERNAL_NARRATION_MODEL,
    voiceId: rawVoiceId,
    segments: segments.map((textValue) => ({ text: textValue })),
    voiceSettings: { stability, similarityBoost, style, useSpeakerBoost, speed },
    seed,
    confirmBillable,
  };
  const payload: ExternalNarrationPayload = {
    provider: EXTERNAL_NARRATION_PROVIDER,
    model_id: EXTERNAL_NARRATION_MODEL,
    voice_id: rawVoiceId,
    segments: request.segments,
    voice_settings: {
      stability,
      similarity_boost: similarityBoost,
      style,
      use_speaker_boost: useSpeakerBoost,
      speed,
    },
    seed,
    confirm_billable: confirmBillable,
  };
  return { request, payload, totalCharacters, errors };
};

/** Return the exact external TTS wire body, rejecting every non-runnable draft. */
export const buildExternalNarrationPayload = (value: unknown): ExternalNarrationPayload => {
  const normalized = normalizeExternalNarrationInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

export const toExternalNarrationPayload = buildExternalNarrationPayload;
export const normalizeExternalTtsInput = normalizeExternalNarrationInput;
export const buildExternalTtsPayload = buildExternalNarrationPayload;

export interface NormalizedAssemblyInput {
  request: LocalAssemblyRequest;
  errors: string[];
}

export const LOCAL_ASSEMBLY_CAPTION_STYLE_PRESETS = [
  'studio_default_v1',
  'shorts_ja_large_v1',
] as const satisfies readonly LocalAssemblyCaptionStylePreset[];

export const LOCAL_ASSEMBLY_AUDIO_MIX_PRESETS = [
  'narration_only_v1',
  'source_under_narration_v1',
] as const satisfies readonly LocalAssemblyAudioMixPreset[];

export const DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET: LocalAssemblyCaptionStylePreset = 'studio_default_v1';
export const RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET: LocalAssemblyCaptionStylePreset = 'shorts_ja_large_v1';
export const DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET: LocalAssemblyAudioMixPreset = 'narration_only_v1';

export const isLocalAssemblyCaptionStylePreset = (
  value: unknown,
): value is LocalAssemblyCaptionStylePreset => (
  typeof value === 'string'
  && LOCAL_ASSEMBLY_CAPTION_STYLE_PRESETS.some((preset) => preset === value)
);

export const isLocalAssemblyAudioMixPreset = (
  value: unknown,
): value is LocalAssemblyAudioMixPreset => (
  typeof value === 'string'
  && LOCAL_ASSEMBLY_AUDIO_MIX_PRESETS.some((preset) => preset === value)
);

export const normalizeLocalAssemblyInput = (
  videoArtifactId: string,
  narrationAttemptId: string,
  includeCaptioned: boolean,
  captionStylePreset: unknown = DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET,
  audioMixPreset: unknown = DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET,
): NormalizedAssemblyInput => {
  const normalizedPreset = isLocalAssemblyCaptionStylePreset(captionStylePreset)
    ? captionStylePreset
    : DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET;
  const normalizedAudioMixPreset = isLocalAssemblyAudioMixPreset(audioMixPreset)
    ? audioMixPreset
    : DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET;
  const request: LocalAssemblyRequest = {
    videoArtifactId: videoArtifactId.trim(),
    narrationAttemptId: narrationAttemptId.trim(),
    includeCaptioned: Boolean(includeCaptioned),
    captionStylePreset: normalizedPreset,
    audioMixPreset: normalizedAudioMixPreset,
  };
  const errors: string[] = [];
  if (!request.videoArtifactId) errors.push('動画artifactを選択してください。');
  if (!request.narrationAttemptId) errors.push('成功済みナレーション試行を選択してください。');
  if (!isLocalAssemblyCaptionStylePreset(captionStylePreset)) {
    errors.push('字幕プリセットはstudio_default_v1またはshorts_ja_large_v1を指定してください。');
  }
  if (!request.includeCaptioned && request.captionStylePreset !== 'studio_default_v1') {
    errors.push('shorts_ja_large_v1は字幕付き版を生成する場合のみ選択できます。');
  }
  if (!isLocalAssemblyAudioMixPreset(audioMixPreset)) {
    errors.push('音声mixプリセットはnarration_only_v1またはsource_under_narration_v1を指定してください。');
  }
  return { request, errors };
};

export interface LocalAssemblyPayload {
  video_artifact_id: string;
  narration_attempt_id: string;
  include_captioned: boolean;
  caption_style_preset: LocalAssemblyCaptionStylePreset;
  audio_mix_preset: LocalAssemblyAudioMixPreset;
}

/** Return the exact local assembly wire body after applying the same form validation. */
export const buildLocalAssemblyPayload = (value: unknown): LocalAssemblyPayload => {
  const record = asRecord(value);
  const normalized = normalizeLocalAssemblyInput(
    text(pick(record, ['videoArtifactId', 'video_artifact_id'])),
    text(pick(record, ['narrationAttemptId', 'narration_attempt_id'])),
    boolean(pick(record, ['includeCaptioned', 'include_captioned']), true),
    pick(record, ['captionStylePreset', 'caption_style_preset']),
    pick(record, ['audioMixPreset', 'audio_mix_preset']),
  );
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return {
    video_artifact_id: normalized.request.videoArtifactId,
    narration_attempt_id: normalized.request.narrationAttemptId,
    include_captioned: normalized.request.includeCaptioned,
    caption_style_preset: normalized.request.captionStylePreset,
    audio_mix_preset: normalized.request.audioMixPreset,
  };
};

export const LOCAL_TIMELINE_LIMITS = {
  minClips: 1,
  maxClips: 32,
  minClipDurationMs: 50,
  maxTotalDurationMs: 30 * 60 * 1000,
} as const;

export interface LocalTimelinePayload {
  clips: Array<{
    video_artifact_id: string;
    start_ms: number;
    end_ms: number;
  }>;
}

export interface NormalizedLocalTimelineInput {
  request: LocalTimelineRequest;
  payload: LocalTimelinePayload;
  totalDurationMs: number;
  errors: string[];
}

const timelineClipValue = (value: unknown): UnknownRecord => asRecord(value);

const timelineClipNumber = (record: UnknownRecord, keys: string[]): number | undefined =>
  number(pick(record, keys));

/** Normalize a cut draft while keeping the wire contract limited to clip ids and integer ranges. */
export const normalizeLocalTimelineInput = (value: unknown): NormalizedLocalTimelineInput => {
  const recordValue = asRecord(value);
  const values = Array.isArray(value)
    ? value
    : items(pick(recordValue, ['clips']), ['items', 'clips']);
  const requestClips: LocalTimelineClip[] = values.map((value) => {
    const record = timelineClipValue(value);
    return {
      videoArtifactId: text(pick(record, ['videoArtifactId', 'video_artifact_id']), '').trim(),
      startMs: timelineClipNumber(record, ['startMs', 'start_ms']) ?? Number.NaN,
      endMs: timelineClipNumber(record, ['endMs', 'end_ms']) ?? Number.NaN,
    };
  });
  const errors: string[] = [];
  if (!Array.isArray(value) && !Array.isArray(recordValue.clips)) errors.push('カット一覧を指定してください。');
  if (requestClips.length < LOCAL_TIMELINE_LIMITS.minClips) errors.push('カットを1件以上追加してください。');
  if (requestClips.length > LOCAL_TIMELINE_LIMITS.maxClips) errors.push(`カットは${LOCAL_TIMELINE_LIMITS.maxClips}件以内にしてください。`);

  let totalDurationMs = 0;
  requestClips.forEach((clip, index) => {
    const label = `カット${index + 1}`;
    if (!clip.videoArtifactId) errors.push(`${label}の動画artifactを選択してください。`);
    if (!Number.isInteger(clip.startMs) || clip.startMs < 0) errors.push(`${label}の開始時刻は0以上の整数ミリ秒で指定してください。`);
    if (!Number.isInteger(clip.endMs) || clip.endMs < 0) errors.push(`${label}の終了時刻は0以上の整数ミリ秒で指定してください。`);
    if (Number.isInteger(clip.endMs) && clip.endMs > LOCAL_TIMELINE_LIMITS.maxTotalDurationMs) {
      errors.push(`${label}の終了時刻は${(LOCAL_TIMELINE_LIMITS.maxTotalDurationMs / 60_000).toLocaleString('ja-JP')}分以内にしてください。`);
    }
    const duration = clip.endMs - clip.startMs;
    if (Number.isInteger(clip.startMs) && Number.isInteger(clip.endMs) && duration < LOCAL_TIMELINE_LIMITS.minClipDurationMs) {
      errors.push(`${label}の尺は${LOCAL_TIMELINE_LIMITS.minClipDurationMs}ms以上にしてください。`);
    }
    if (Number.isInteger(clip.startMs) && Number.isInteger(clip.endMs) && duration > 0) totalDurationMs += duration;
  });
  if (totalDurationMs > LOCAL_TIMELINE_LIMITS.maxTotalDurationMs) {
    errors.push(`合計尺は${(LOCAL_TIMELINE_LIMITS.maxTotalDurationMs / 60_000).toLocaleString('ja-JP')}分以内にしてください。`);
  }

  const payload: LocalTimelinePayload = {
    clips: requestClips.map((clip) => ({
      video_artifact_id: clip.videoArtifactId,
      start_ms: clip.startMs,
      end_ms: clip.endMs,
    })),
  };
  return { request: { clips: requestClips }, payload, totalDurationMs, errors };
};

/** Build the exact timeline wire body; invalid drafts never cross the API boundary. */
export const buildLocalTimelinePayload = (value: unknown): LocalTimelinePayload => {
  const normalized = normalizeLocalTimelineInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

export const toLocalTimelinePayload = buildLocalTimelinePayload;

export const REMOTION_TIMELINE_SCHEMA_VERSION = 1 as const;
export const REMOTION_TIMELINE_COMPOSITION_ID = 'MiniMaxH3DetailedTimelineV1' as const;
export const REMOTION_TIMELINE_WIDTH = 1080 as const;
export const REMOTION_TIMELINE_HEIGHT = 1920 as const;
export const REMOTION_TIMELINE_FPS = 24 as const;
export const DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET: LocalRemotionTimelineVisualPreset = 'preserve_v1';

export const REMOTION_TIMELINE_LIMITS = {
  minClips: 1,
  maxClips: 16,
  minClipDurationMs: 50,
  maxOutputDurationMs: 60_000,
  minTransitionDurationMs: 50,
  maxTransitionDurationMs: 2_000,
  minOverlayDurationMs: 50,
  maxOverlayCharacters: 200,
  maxOverlayLines: 4,
} as const;

const REMOTION_ARTIFACT_ID_RE = /^art_[0-9a-f]{32}$/;

export interface RemotionTimelinePayload {
  schema_version: typeof REMOTION_TIMELINE_SCHEMA_VERSION;
  clips: Array<{
    video_artifact_id: string;
    start_ms: number;
    end_ms: number;
    volume_percent: number;
    visual_preset: LocalRemotionTimelineVisualPreset;
    transition_to_next: null | { type: 'fade'; duration_ms: number };
    overlay: null | {
      text: string;
      start_ms: number;
      end_ms: number;
      position: LocalRemotionTimelineOverlayPosition;
      style_preset: 'shorts_ja_large_v1';
    };
  }>;
}

export interface NormalizedRemotionTimelineInput {
  request: LocalRemotionTimelineRequest;
  payload: RemotionTimelinePayload;
  outputDurationMs: number;
  durationInFrames: number;
  errors: string[];
}

const remotionInteger = (value: unknown): number => {
  const parsed = number(value);
  return parsed !== undefined && Number.isSafeInteger(parsed) ? parsed : Number.NaN;
};

const isRemotionTimelineVisualPreset = (value: unknown): value is LocalRemotionTimelineVisualPreset =>
  value === 'preserve_v1' || value === 'h3_low_res_sharp_v1';

const normalizeRemotionTransition = (value: unknown): LocalRemotionTimelineTransition | null => {
  if (value === null || value === undefined) return null;
  const record = asRecord(value);
  return {
    type: text(pick(record, ['type']), '') as 'fade',
    durationMs: remotionInteger(pick(record, ['durationMs', 'duration_ms'])),
  };
};

const normalizeRemotionOverlay = (value: unknown): LocalRemotionTimelineOverlay | null => {
  if (value === null || value === undefined) return null;
  const record = asRecord(value);
  return {
    text: text(pick(record, ['text']), '').replace(/\r\n?/g, '\n').trim(),
    startMs: remotionInteger(pick(record, ['startMs', 'start_ms'])),
    endMs: remotionInteger(pick(record, ['endMs', 'end_ms'])),
    position: text(pick(record, ['position']), '') as LocalRemotionTimelineOverlayPosition,
    stylePreset: text(pick(record, ['stylePreset', 'style_preset']), '') as 'shorts_ja_large_v1',
  };
};

const remotionPayloadForRequest = (request: LocalRemotionTimelineRequest): RemotionTimelinePayload => ({
  schema_version: REMOTION_TIMELINE_SCHEMA_VERSION,
  clips: request.clips.map((clip) => ({
    video_artifact_id: clip.videoArtifactId,
    start_ms: clip.startMs,
    end_ms: clip.endMs,
    volume_percent: clip.volumePercent,
    visual_preset: clip.visualPreset ?? DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
    transition_to_next: clip.transitionToNext === null ? null : {
      type: clip.transitionToNext.type,
      duration_ms: clip.transitionToNext.durationMs,
    },
    overlay: clip.overlay === null ? null : {
      text: clip.overlay.text,
      start_ms: clip.overlay.startMs,
      end_ms: clip.overlay.endMs,
      position: clip.overlay.position,
      style_preset: clip.overlay.stylePreset,
    },
  })),
});

/** Match Python's non-negative integer half-up frame conversion exactly. */
export const millisecondsToFramesHalfUp = (milliseconds: number, fps = REMOTION_TIMELINE_FPS): number => {
  if (!Number.isSafeInteger(milliseconds) || milliseconds < 0) {
    throw new TypeError('milliseconds must be a non-negative safe integer');
  }
  if (!Number.isSafeInteger(fps) || fps <= 0) throw new TypeError('fps must be a positive safe integer');
  const wholeSeconds = Math.floor(milliseconds / 1_000);
  const remainderMs = milliseconds % 1_000;
  const frames = wholeSeconds * fps + Math.floor((remainderMs * fps + 500) / 1_000);
  if (!Number.isSafeInteger(frames)) throw new TypeError('frame count exceeds the safe integer range');
  return frames;
};

export const framesToMillisecondsHalfUp = (frames: number, fps = REMOTION_TIMELINE_FPS): number => {
  if (!Number.isSafeInteger(frames) || frames < 1) throw new TypeError('frames must be a positive safe integer');
  if (!Number.isSafeInteger(fps) || fps <= 0) throw new TypeError('fps must be a positive safe integer');
  const milliseconds = Math.floor((frames * 1_000 + Math.floor(fps / 2)) / fps);
  if (!Number.isSafeInteger(milliseconds)) throw new TypeError('duration exceeds the safe integer range');
  return milliseconds;
};

export const remotionTimelineOutputDurationMs = (clips: readonly LocalRemotionTimelineClip[]): number =>
  clips.reduce((total, clip) => total + (clip.endMs - clip.startMs) - (clip.transitionToNext?.durationMs ?? 0), 0);

export const remotionTimelineDurationInFrames = (
  clips: readonly LocalRemotionTimelineClip[],
  fps = REMOTION_TIMELINE_FPS,
): number => clips.reduce((total, clip) => total
  + millisecondsToFramesHalfUp(clip.endMs - clip.startMs, fps)
  - (clip.transitionToNext === null ? 0 : millisecondsToFramesHalfUp(clip.transitionToNext.durationMs, fps)), 0);

export const normalizeRemotionTimelineInput = (value: unknown): NormalizedRemotionTimelineInput => {
  const recordValue = asRecord(value);
  const rawSchemaVersion = pick(recordValue, ['schemaVersion', 'schema_version']);
  const values = Array.isArray(value) ? value : Array.isArray(recordValue.clips) ? recordValue.clips : [];
  const clips: LocalRemotionTimelineClip[] = values.map((item) => {
    const record = asRecord(item);
    return {
      videoArtifactId: text(pick(record, ['videoArtifactId', 'video_artifact_id']), '').trim(),
      startMs: remotionInteger(pick(record, ['startMs', 'start_ms'])),
      endMs: remotionInteger(pick(record, ['endMs', 'end_ms'])),
      volumePercent: remotionInteger(pick(record, ['volumePercent', 'volume_percent'])),
      visualPreset: isRemotionTimelineVisualPreset(pick(record, ['visualPreset', 'visual_preset']))
        ? pick(record, ['visualPreset', 'visual_preset']) as LocalRemotionTimelineVisualPreset
        : DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
      transitionToNext: normalizeRemotionTransition(pick(record, ['transitionToNext', 'transition_to_next'])),
      overlay: normalizeRemotionOverlay(pick(record, ['overlay'])),
    };
  });
  const request: LocalRemotionTimelineRequest = { clips };
  const errors: string[] = [];
  if (!Array.isArray(value) && !Array.isArray(recordValue.clips)) errors.push('カット一覧を指定してください。');
  if (rawSchemaVersion !== undefined && remotionInteger(rawSchemaVersion) !== REMOTION_TIMELINE_SCHEMA_VERSION) {
    errors.push(`schema_versionは${REMOTION_TIMELINE_SCHEMA_VERSION}を指定してください。`);
  }
  if (clips.length < REMOTION_TIMELINE_LIMITS.minClips) errors.push('カットを1件以上追加してください。');
  if (clips.length > REMOTION_TIMELINE_LIMITS.maxClips) {
    errors.push(`カットは${REMOTION_TIMELINE_LIMITS.maxClips}件以内にしてください。`);
  }

  const durations = clips.map((clip) => clip.endMs - clip.startMs);
  clips.forEach((clip, index) => {
    const label = `カット${index + 1}`;
    const durationMs = durations[index];
    if (!REMOTION_ARTIFACT_ID_RE.test(clip.videoArtifactId)) {
      errors.push(`${label}の動画artifact IDが不正です。`);
    }
    if (!Number.isSafeInteger(clip.startMs) || clip.startMs < 0) {
      errors.push(`${label}の開始時刻は0以上の整数ミリ秒で指定してください。`);
    }
    if (!Number.isSafeInteger(clip.endMs) || clip.endMs < 0) {
      errors.push(`${label}の終了時刻は0以上の整数ミリ秒で指定してください。`);
    } else if (clip.endMs > REMOTION_TIMELINE_LIMITS.maxOutputDurationMs) {
      errors.push(`${label}の終了時刻は${REMOTION_TIMELINE_LIMITS.maxOutputDurationMs / 1_000}秒以内にしてください。`);
    }
    const visualPresetValue = pick(asRecord(values[index]), ['visualPreset', 'visual_preset']);
    if (visualPresetValue !== undefined && !isRemotionTimelineVisualPreset(visualPresetValue)) {
      errors.push(`${label}の映像補正presetはpreserve_v1またはh3_low_res_sharp_v1を指定してください。`);
    }
    if (Number.isSafeInteger(durationMs) && durationMs < REMOTION_TIMELINE_LIMITS.minClipDurationMs) {
      errors.push(`${label}の尺は${REMOTION_TIMELINE_LIMITS.minClipDurationMs}ms以上にしてください。`);
    }
    if (!Number.isSafeInteger(clip.volumePercent) || clip.volumePercent < 0 || clip.volumePercent > 100) {
      errors.push(`${label}の素材音量は0〜100の整数パーセントで指定してください。`);
    }

    const transition = clip.transitionToNext;
    if (index === clips.length - 1 && transition !== null) {
      errors.push('最終カットのtransition_to_nextはnullにしてください。');
    } else if (transition !== null) {
      if (transition.type !== 'fade') errors.push(`${label}のtransitionはfadeだけ指定できます。`);
      if (!Number.isSafeInteger(transition.durationMs)
        || transition.durationMs < REMOTION_TIMELINE_LIMITS.minTransitionDurationMs
        || transition.durationMs > REMOTION_TIMELINE_LIMITS.maxTransitionDurationMs) {
        errors.push(`${label}のfade時間は${REMOTION_TIMELINE_LIMITS.minTransitionDurationMs}〜${REMOTION_TIMELINE_LIMITS.maxTransitionDurationMs}msで指定してください。`);
      } else {
        const nextDurationMs = durations[index + 1];
        const transitionFrames = millisecondsToFramesHalfUp(transition.durationMs);
        if (Number.isSafeInteger(durationMs) && durationMs >= REMOTION_TIMELINE_LIMITS.minClipDurationMs
          && transitionFrames >= millisecondsToFramesHalfUp(durationMs)) {
          errors.push(`${label}のfade時間は現在のカット尺より短くしてください。`);
        }
        if (Number.isSafeInteger(nextDurationMs) && nextDurationMs >= REMOTION_TIMELINE_LIMITS.minClipDurationMs
          && transitionFrames >= millisecondsToFramesHalfUp(nextDurationMs)) {
          errors.push(`${label}のfade時間は次のカット尺より短くしてください。`);
        }
      }
    }

    const overlay = clip.overlay;
    if (overlay !== null) {
      const characterCount = [...overlay.text].length;
      const lineCount = overlay.text === '' ? 0 : overlay.text.split('\n').length;
      if (characterCount < 1 || characterCount > REMOTION_TIMELINE_LIMITS.maxOverlayCharacters) {
        errors.push(`${label}のテロップは1〜${REMOTION_TIMELINE_LIMITS.maxOverlayCharacters}文字で指定してください。`);
      }
      if (lineCount > REMOTION_TIMELINE_LIMITS.maxOverlayLines) {
        errors.push(`${label}のテロップは${REMOTION_TIMELINE_LIMITS.maxOverlayLines}行以内にしてください。`);
      }
      if (/[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u.test(overlay.text)) {
        errors.push(`${label}のテロップに制御文字は使用できません。`);
      }
      if (!Number.isSafeInteger(overlay.startMs) || overlay.startMs < 0) {
        errors.push(`${label}のテロップ開始時刻は0以上の整数ミリ秒で指定してください。`);
      }
      if (!Number.isSafeInteger(overlay.endMs) || overlay.endMs < 0) {
        errors.push(`${label}のテロップ終了時刻は0以上の整数ミリ秒で指定してください。`);
      }
      if (Number.isSafeInteger(overlay.startMs) && Number.isSafeInteger(overlay.endMs)
        && overlay.endMs - overlay.startMs < REMOTION_TIMELINE_LIMITS.minOverlayDurationMs) {
        errors.push(`${label}のテロップ表示時間は${REMOTION_TIMELINE_LIMITS.minOverlayDurationMs}ms以上にしてください。`);
      }
      if (Number.isSafeInteger(durationMs) && Number.isSafeInteger(overlay.endMs) && overlay.endMs > durationMs) {
        errors.push(`${label}のテロップ終了時刻はトリム後のカット尺以内にしてください。`);
      }
      if (!['top', 'center', 'bottom'].includes(overlay.position)) {
        errors.push(`${label}のテロップ位置はtop、center、bottomから選択してください。`);
      }
      if (overlay.stylePreset !== 'shorts_ja_large_v1') {
        errors.push(`${label}のテロップstyle presetはshorts_ja_large_v1を指定してください。`);
      }
    }
  });

  const canCompileDuration = clips.length > 0 && clips.every((clip, index) => {
    const durationMs = clip.endMs - clip.startMs;
    const transition = clip.transitionToNext;
    return Number.isSafeInteger(durationMs)
      && durationMs >= REMOTION_TIMELINE_LIMITS.minClipDurationMs
      && (transition === null || (
        index < clips.length - 1
        && Number.isSafeInteger(transition.durationMs)
        && transition.durationMs >= REMOTION_TIMELINE_LIMITS.minTransitionDurationMs
        && transition.durationMs <= REMOTION_TIMELINE_LIMITS.maxTransitionDurationMs
      ));
  });
  const durationInFrames = canCompileDuration ? remotionTimelineDurationInFrames(clips) : 0;
  const outputDurationMs = durationInFrames > 0 ? framesToMillisecondsHalfUp(durationInFrames) : 0;
  if (outputDurationMs > REMOTION_TIMELINE_LIMITS.maxOutputDurationMs) {
    errors.push(`出力尺は${REMOTION_TIMELINE_LIMITS.maxOutputDurationMs / 1_000}秒以内にしてください。`);
  }
  if (canCompileDuration && durationInFrames < 1) errors.push('出力は1frame以上にしてください。');

  return {
    request,
    payload: remotionPayloadForRequest(request),
    outputDurationMs,
    durationInFrames,
    errors,
  };
};

export const normalizeLocalRemotionTimelineInput = normalizeRemotionTimelineInput;

export const buildRemotionTimelinePayload = (value: unknown): RemotionTimelinePayload => {
  const normalized = normalizeRemotionTimelineInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

export const buildLocalRemotionTimelinePayload = buildRemotionTimelinePayload;

export const LOCAL_SCREEN_CAPTURE_LIMITS = {
  minDurationMs: 1_000,
  maxDurationMs: 30_000,
  maxSettleMs: 10_000,
  maxActions: 16,
  maxSelectorChars: 256,
} as const;

const LOCAL_SCREEN_CAPTURE_KEYS = new Set([
  'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'End', 'Enter',
  'Escape', 'Home', 'PageDown', 'PageUp', 'Space', 'Tab',
]);

export type LocalScreenCapturePayloadAction =
  | { type: 'scroll'; at_ms: number; delta_y: number }
  | { type: 'click'; at_ms: number; selector: string }
  | { type: 'press'; at_ms: number; selector: string; key: string };

export interface LocalScreenCapturePayload {
  url: string;
  duration_ms: number;
  settle_ms: number;
  actions: LocalScreenCapturePayloadAction[];
}

export interface NormalizedLocalScreenCaptureInput {
  request: LocalScreenCaptureRequest;
  payload: LocalScreenCapturePayload;
  errors: string[];
}

const captureInteger = (value: unknown): number => {
  const parsed = number(value);
  return parsed === undefined ? Number.NaN : parsed;
};

const normalizeCaptureUrl = (value: unknown): { url: string; error?: string } => {
  const raw = typeof value === 'string' ? value.trim() : '';
  if (!raw || raw.length > 2_048 || /[\\\u0000-\u001f]/.test(raw)) {
    return { url: raw, error: 'URLを入力してください。' };
  }
  try {
    const target = new URL(raw);
    if (
      target.protocol !== 'http:'
      || target.hostname !== '127.0.0.1'
      || !target.port
      || target.username
      || target.password
      || target.hash
    ) {
      return { url: raw, error: 'http://127.0.0.1:<port>/ のloopback URLだけを指定できます。' };
    }
    return { url: target.href };
  } catch {
    return { url: raw, error: 'URLの形式が正しくありません。' };
  }
};

/** Normalize the closed Playwright request; no credentials or arbitrary JS can enter the wire body. */
export const normalizeLocalScreenCaptureInput = (value: unknown): NormalizedLocalScreenCaptureInput => {
  const record = asRecord(value);
  const target = normalizeCaptureUrl(pick(record, ['url']));
  const durationMs = captureInteger(pick(record, ['durationMs', 'duration_ms']));
  const settleMs = captureInteger(pick(record, ['settleMs', 'settle_ms']));
  const rawActions = pick(record, ['actions']);
  const actionsValue = Array.isArray(rawActions) ? rawActions : [];
  const errors: string[] = [];
  if (target.error) errors.push(target.error);
  if (!Number.isInteger(durationMs) || durationMs < LOCAL_SCREEN_CAPTURE_LIMITS.minDurationMs || durationMs > LOCAL_SCREEN_CAPTURE_LIMITS.maxDurationMs) {
    errors.push('録画時間は1,000〜30,000msの整数で指定してください。');
  }
  if (!Number.isInteger(settleMs) || settleMs < 0 || settleMs > LOCAL_SCREEN_CAPTURE_LIMITS.maxSettleMs) {
    errors.push('描画待ちは0〜10,000msの整数で指定してください。');
  }
  if (!Array.isArray(rawActions)) errors.push('操作一覧を配列で指定してください。');
  if (actionsValue.length > LOCAL_SCREEN_CAPTURE_LIMITS.maxActions) errors.push(`操作は${LOCAL_SCREEN_CAPTURE_LIMITS.maxActions}件以内にしてください。`);

  const actions: LocalScreenCaptureAction[] = [];
  const payloadActions: LocalScreenCapturePayloadAction[] = [];
  let lastAtMs = -1;
  actionsValue.slice(0, LOCAL_SCREEN_CAPTURE_LIMITS.maxActions).forEach((value, index) => {
    const action = asRecord(value);
    const type = text(pick(action, ['type']));
    const atMs = captureInteger(pick(action, ['atMs', 'at_ms']));
    const label = `操作${index + 1}`;
    if (!['scroll', 'click', 'press'].includes(type)) {
      errors.push(`${label}のtypeはscroll、click、pressのいずれかです。`);
      return;
    }
    if (!Number.isInteger(atMs) || atMs < 0 || !Number.isInteger(durationMs) || atMs >= durationMs) {
      errors.push(`${label}のat_msは録画時間内の整数で指定してください。`);
      return;
    }
    if (atMs < lastAtMs) {
      errors.push('操作はat_msの昇順で指定してください。');
      return;
    }
    if (type === 'scroll') {
      const deltaY = captureInteger(pick(action, ['deltaY', 'delta_y']));
      if (!Number.isInteger(deltaY) || deltaY === 0 || deltaY < -4_000 || deltaY > 4_000) {
        errors.push(`${label}のdelta_yは-4,000〜4,000の0以外の整数で指定してください。`);
        return;
      }
      actions.push({ type, atMs, deltaY });
      payloadActions.push({ type, at_ms: atMs, delta_y: deltaY });
      lastAtMs = atMs;
      return;
    }
    const selector = text(pick(action, ['selector'])).trim();
    if (!selector || selector.length > LOCAL_SCREEN_CAPTURE_LIMITS.maxSelectorChars || /[\u0000-\u001f]/.test(selector)) {
      errors.push(`${label}のselectorが正しくありません。`);
      return;
    }
    if (type === 'click') {
      actions.push({ type, atMs, selector });
      payloadActions.push({ type, at_ms: atMs, selector });
      lastAtMs = atMs;
      return;
    }
    const key = text(pick(action, ['key']));
    if (!LOCAL_SCREEN_CAPTURE_KEYS.has(key)) {
      errors.push(`${label}のkeyは許可されたナビゲーションキーではありません。`);
      return;
    }
    actions.push({ type: 'press', atMs, selector, key });
    payloadActions.push({ type: 'press', at_ms: atMs, selector, key });
    lastAtMs = atMs;
  });

  return {
    request: { url: target.url, durationMs, settleMs, actions },
    payload: {
      url: target.url,
      duration_ms: durationMs,
      settle_ms: settleMs,
      actions: payloadActions,
    },
    errors,
  };
};

export const buildLocalScreenCapturePayload = (value: unknown): LocalScreenCapturePayload => {
  const normalized = normalizeLocalScreenCaptureInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

const optionalLiteralBoolean = (value: unknown): boolean | undefined => (
  typeof value === 'boolean' ? value : undefined
);

export const WINDOWS_CAPTURE_LIMITS = {
  minDurationMs: 1_000,
  maxDurationMs: 30_000,
} as const;

export const WINDOWS_CAPTURE_CONSENT_TTL_SECONDS = 60 as const;

export const WINDOWS_CAPTURE_RECONCILIATION_POLL_MS = 2_000 as const;

/** One immediate lookup plus one lookup every two seconds through the TTL. */
export const WINDOWS_CAPTURE_RECONCILIATION_MAX_POLLS = 31 as const;

export const WINDOWS_CAPTURE_REQUEST_TIMEOUT_MS = 10_000 as const;

const WINDOWS_CAPTURE_CONSENT_TOKEN_PATTERN = /^[A-Za-z0-9_-]{43}$/;
const WINDOWS_CAPTURE_CONSENT_INTENT_ID_PATTERN = /^capture_consent_[0-9a-f]{32}$/;
const WINDOWS_CAPTURE_DIGEST_PATTERN = /^[0-9A-F]{64}$/;
const WINDOWS_CAPTURE_CONSENT_RESPONSE_KEYS = [
  'schema_version',
  'consent_intent_id',
  'consent_token',
  'run_id',
  'request_settings_digest',
  'issued_at',
  'expires_at',
  'expires_in_seconds',
] as const;

const hasExactKeys = (record: UnknownRecord, keys: readonly string[]): boolean => {
  const actual = Object.keys(record);
  return actual.length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(record, key));
};

/**
 * Build the closed native request.  The UI only supplies duration and the two
 * independent confirmations; all target/audio/cursor values are fixed here
 * so no caller can expand the native capture surface.
 */
export const buildWindowsCapturePayload = (value: unknown): WindowsCapturePayload => {
  const record = asRecord(value);
  const durationMs = number(pick(record, ['durationMs', 'duration_ms']));
  if (
    durationMs === undefined
    || !Number.isInteger(durationMs)
    || durationMs < WINDOWS_CAPTURE_LIMITS.minDurationMs
    || durationMs > WINDOWS_CAPTURE_LIMITS.maxDurationMs
  ) {
    throw new TypeError('録画時間は1,000〜30,000msの整数で指定してください。');
  }
  if (pick(record, ['confirmCapture', 'confirm_capture']) !== true) {
    throw new TypeError('画面収録の明示確認が必要です。');
  }
  if (pick(record, ['confirmSystemAudio', 'confirm_system_audio']) !== true) {
    throw new TypeError('システム音声収録の明示確認が必要です。');
  }
  return {
    schema_version: 1,
    target: 'primary_display',
    audio_mode: 'default_render_loopback',
    cursor_mode: 'hidden',
    duration_ms: durationMs,
    confirm_capture: true,
    confirm_system_audio: true,
  };
};

/** Add only the raw, short-lived token to the fixed seven-field request. */
export const buildWindowsCaptureExecutionPayload = (
  value: unknown,
  consentToken: unknown,
): WindowsCaptureExecutionPayload => {
  if (typeof consentToken !== 'string' || !WINDOWS_CAPTURE_CONSENT_TOKEN_PATTERN.test(consentToken)) {
    throw new TypeError('Windows収録のconsent tokenを検証できませんでした。');
  }
  return { ...buildWindowsCapturePayload(value), consent_token: consentToken };
};

/** Parse the closed 201 response without retaining its bearer token or raw object. */
export const parseWindowsCaptureConsentIntent = (
  value: unknown,
  expectedRunId: string,
): WindowsCaptureConsentIntent => {
  const record = asRecord(value);
  if (!hasExactKeys(record, WINDOWS_CAPTURE_CONSENT_RESPONSE_KEYS)) {
    throw new TypeError('Windows収録のconsent intent応答を検証できませんでした。');
  }
  const issuedAt = record.issued_at;
  const expiresAt = record.expires_at;
  const consentIntentId = record.consent_intent_id;
  const consentToken = record.consent_token;
  const runId = record.run_id;
  const requestSettingsDigest = record.request_settings_digest;
  if (
    record.schema_version !== 1
    || typeof consentIntentId !== 'string'
    || !WINDOWS_CAPTURE_CONSENT_INTENT_ID_PATTERN.test(consentIntentId)
    || typeof consentToken !== 'string'
    || !WINDOWS_CAPTURE_CONSENT_TOKEN_PATTERN.test(consentToken)
    || typeof runId !== 'string'
    || runId !== expectedRunId
    || typeof requestSettingsDigest !== 'string'
    || !WINDOWS_CAPTURE_DIGEST_PATTERN.test(requestSettingsDigest)
    || typeof issuedAt !== 'string'
    || !Number.isFinite(Date.parse(issuedAt))
    || typeof expiresAt !== 'string'
    || !Number.isFinite(Date.parse(expiresAt))
    || Date.parse(expiresAt) - Date.parse(issuedAt) !== WINDOWS_CAPTURE_CONSENT_TTL_SECONDS * 1_000
    || record.expires_in_seconds !== WINDOWS_CAPTURE_CONSENT_TTL_SECONDS
  ) {
    throw new TypeError('Windows収録のconsent intent応答を検証できませんでした。');
  }
  return {
    schema_version: 1,
    consent_intent_id: consentIntentId,
    consent_token: consentToken,
    run_id: runId,
    request_settings_digest: requestSettingsDigest,
    issued_at: issuedAt,
    expires_at: expiresAt,
    expires_in_seconds: WINDOWS_CAPTURE_CONSENT_TTL_SECONDS,
  };
};

export const isWindowsCaptureCapabilityReady = (capability?: WindowsCaptureCapability): boolean => Boolean(
  capability
  && capability.status === 'ready'
  && capability.captureExecutionEnabled === true,
);

export const canStartWindowsCapture = (
  executionProfile: string | undefined,
  capability: WindowsCaptureCapability | undefined,
  confirmCapture: boolean,
  confirmSystemAudio: boolean,
  locked = false,
): boolean => Boolean(
  executionProfile === 'local_windows_capture'
  && isWindowsCaptureCapabilityReady(capability)
  && confirmCapture
  && confirmSystemAudio
  && !locked,
);

export const LOCAL_COMFYUI_WORKFLOW_PRESET = 'minimax_h3_t2v_official_q4_v1' as const;
export const LOCAL_COMFYUI_MAX_PROMPT_CHARS = 50_000;
export const LOCAL_COMFYUI_MAX_SEED = '9223372036854775807' as const;
const LOCAL_COMFYUI_MAX_SEED_BIGINT = BigInt(LOCAL_COMFYUI_MAX_SEED);
const LOCAL_COMFYUI_SAFE_INTEGER_BIGINT = BigInt(Number.MAX_SAFE_INTEGER);

export interface LocalComfyUiPayload {
  workflow_preset: typeof LOCAL_COMFYUI_WORKFLOW_PRESET;
  prompt: string;
  /** A decimal string is retained above Number.MAX_SAFE_INTEGER for JSON serialization. */
  seed: number | string;
}

export interface NormalizedLocalComfyUiInput {
  request: LocalComfyUiRequest;
  payload: LocalComfyUiPayload;
  errors: string[];
}

const localComfyUiPromptErrors = (prompt: string): string[] => {
  const errors: string[] = [];
  if (!prompt) errors.push('生成プロンプトを入力してください。');
  if (prompt.length > LOCAL_COMFYUI_MAX_PROMPT_CHARS) {
    errors.push(`生成プロンプトは${LOCAL_COMFYUI_MAX_PROMPT_CHARS.toLocaleString('ja-JP')}文字以内にしてください。`);
  }
  if ([...prompt].some((character) => {
    const code = character.charCodeAt(0);
    return (code <= 0x1f && code !== 0x09 && code !== 0x0a && code !== 0x0d) || code === 0x7f;
  })) {
    errors.push('生成プロンプトに制御文字は使用できません。');
  }
  for (let index = 0; index < prompt.length; index += 1) {
    const code = prompt.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdfff && (code < 0xdc00 || index === 0 || prompt.charCodeAt(index - 1) < 0xd800 || prompt.charCodeAt(index - 1) > 0xdbff)) {
      const next = prompt.charCodeAt(index + 1);
      if (code < 0xdc00 && next >= 0xdc00 && next <= 0xdfff) {
        index += 1;
        continue;
      }
      errors.push('生成プロンプトに不正なUnicode文字は使用できません。');
      break;
    }
  }
  return errors;
};

const normalizeLocalComfyUiSeed = (value: unknown): { text: string; wire: number | string; error?: string } => {
  const raw = typeof value === 'number' ? String(value) : typeof value === 'string' ? value.trim() : '';
  if (!raw) return { text: '', wire: 0, error: 'seedは0以上の整数で指定してください。' };
  if (!/^\d+$/.test(raw)) return { text: raw, wire: 0, error: 'seedは0以上の整数で指定してください。' };
  try {
    const parsed = BigInt(raw);
    if (parsed < 0n || parsed > LOCAL_COMFYUI_MAX_SEED_BIGINT) {
      return { text: raw, wire: 0, error: `seedは0〜${LOCAL_COMFYUI_MAX_SEED}の範囲で指定してください。` };
    }
    const textValue = parsed.toString();
    return {
      text: textValue,
      wire: parsed <= LOCAL_COMFYUI_SAFE_INTEGER_BIGINT ? Number(parsed) : textValue,
    };
  } catch {
    return { text: raw, wire: 0, error: 'seedは0以上の整数で指定してください。' };
  }
};

/** Normalize the only user-controlled fields accepted by the local ComfyUI worker. */
export const normalizeLocalComfyUiInput = (
  promptValue: unknown,
  seedValue: unknown,
): NormalizedLocalComfyUiInput => {
  const prompt = typeof promptValue === 'string' ? promptValue.trim() : '';
  const seed = normalizeLocalComfyUiSeed(seedValue);
  const errors = [...localComfyUiPromptErrors(prompt)];
  if (seed.error) errors.push(seed.error);
  return {
    request: {
      workflowPreset: LOCAL_COMFYUI_WORKFLOW_PRESET,
      prompt,
      seed: seed.text,
    },
    payload: {
      workflow_preset: LOCAL_COMFYUI_WORKFLOW_PRESET,
      prompt,
      seed: seed.wire,
    },
    errors,
  };
};

export const normalizeLocalComfyUIInput = normalizeLocalComfyUiInput;

/** Build the exact snake_case body; arbitrary workflow/model/path fields are discarded. */
export const buildLocalComfyUiPayload = (value: unknown): LocalComfyUiPayload => {
  const record = asRecord(value);
  const normalized = normalizeLocalComfyUiInput(
    pick(record, ['prompt']),
    pick(record, ['seed']),
  );
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

export const buildLocalComfyUIPayload = buildLocalComfyUiPayload;
export const toLocalComfyUiPayload = buildLocalComfyUiPayload;

export interface LocalPipelinePayload {
  workflow_preset: typeof LOCAL_COMFYUI_WORKFLOW_PRESET;
  prompt: string;
  /** A decimal string is retained above Number.MAX_SAFE_INTEGER for JSON serialization. */
  seed: number | string;
  segments: Array<{ text: string }>;
  voice?: string;
  rate: number;
  pronunciations?: Array<{ source: string; target: string }>;
  include_captioned: boolean;
  caption_style_preset: LocalAssemblyCaptionStylePreset;
  variant: LocalQcVariant;
}

export interface NormalizedLocalPipelineInput {
  request: LocalPipelineRequest;
  payload: LocalPipelinePayload;
  errors: string[];
}

const LOCAL_PIPELINE_DEFAULT_CAPTION_STYLE: LocalAssemblyCaptionStylePreset = 'shorts_ja_large_v1';
const LOCAL_PIPELINE_DEFAULT_VARIANT: LocalQcVariant = 'captioned';
const LOCAL_PIPELINE_MAX_PRONUNCIATIONS = 100;
const LOCAL_PIPELINE_MAX_PRONUNCIATION_CHARS = 512;

const localPipelineScript = (source: UnknownRecord): string => {
  const rawSegments = pick(source, ['segments']);
  if (Array.isArray(rawSegments)) {
    return rawSegments.map((segment) => typeof segment === 'string'
      ? segment
      : text(pick(asRecord(segment), ['text']), '')).join('\n');
  }
  return text(pick(source, ['script', 'narration', 'text']), '');
};

const localPipelinePronunciations = (
  source: UnknownRecord,
): { pronunciations?: Array<{ source: string; target: string }>; errors: string[] } => {
  const raw = pickIncludingNull(source, ['pronunciations']);
  if (raw === undefined || raw === null || raw === '') return { errors: [] };
  if (!Array.isArray(raw)) return { errors: ['発音置換は配列で指定してください。'] };
  const errors: string[] = [];
  const pronunciations: Array<{ source: string; target: string }> = [];
  const seenSources = new Set<string>();
  if (raw.length > LOCAL_PIPELINE_MAX_PRONUNCIATIONS) {
    errors.push(`発音置換は${LOCAL_PIPELINE_MAX_PRONUNCIATIONS}件以内にしてください。`);
  }
  raw.slice(0, LOCAL_PIPELINE_MAX_PRONUNCIATIONS).forEach((item, index) => {
    const record = asRecord(item);
    const sourceText = text(pick(record, ['source']), '').trim();
    const targetText = text(pick(record, ['target']), '').trim();
    if (!sourceText || !targetText) {
      errors.push(`発音置換${index + 1}の表記と読みを入力してください。`);
      return;
    }
    if (sourceText.length > LOCAL_PIPELINE_MAX_PRONUNCIATION_CHARS || targetText.length > LOCAL_PIPELINE_MAX_PRONUNCIATION_CHARS) {
      errors.push(`発音置換${index + 1}はそれぞれ${LOCAL_PIPELINE_MAX_PRONUNCIATION_CHARS}文字以内にしてください。`);
    }
    if (seenSources.has(sourceText)) errors.push(`発音置換の表記「${sourceText}」は重複しています。`);
    seenSources.add(sourceText);
    pronunciations.push({ source: sourceText, target: targetText });
  });
  return { pronunciations: pronunciations.length > 0 ? pronunciations : undefined, errors };
};

/** Normalize the complete local-only pipeline form while keeping the wire allowlist closed. */
export const normalizeLocalPipelineInput = (value: unknown): NormalizedLocalPipelineInput => {
  const source = asRecord(value);
  const comfy = normalizeLocalComfyUiInput(pick(source, ['prompt']), pick(source, ['seed']));
  const rateValue = pickIncludingNull(source, ['rate']);
  const rate = rateValue === undefined || rateValue === '' ? 0 : number(rateValue);
  const narration = normalizeNarrationInput(localPipelineScript(source), rate ?? 0);
  const pronunciationResult = localPipelinePronunciations(source);
  const includeCaptionedValue = pickIncludingNull(source, ['includeCaptioned', 'include_captioned']);
  const includeCaptioned = includeCaptionedValue === undefined ? true : includeCaptionedValue === true;
  const captionStyleValue = pick(source, ['captionStylePreset', 'caption_style_preset']);
  const captionStylePreset = isLocalAssemblyCaptionStylePreset(captionStyleValue)
    ? captionStyleValue
    : captionStyleValue === undefined
      ? LOCAL_PIPELINE_DEFAULT_CAPTION_STYLE
      : LOCAL_PIPELINE_DEFAULT_CAPTION_STYLE;
  const variantValue = pick(source, ['variant']);
  const variant = localQcVariant(variantValue) ?? LOCAL_PIPELINE_DEFAULT_VARIANT;
  const errors = [
    ...comfy.errors,
    ...narration.errors,
    ...pronunciationResult.errors,
  ];
  if (rateValue !== undefined && rateValue !== '' && rate === undefined) errors.push('読み上げ速度は整数で指定してください。');
  if (rate !== undefined && (!Number.isInteger(rate) || rate < LOCAL_NARRATION_LIMITS.minRate || rate > LOCAL_NARRATION_LIMITS.maxRate)) {
    errors.push(`読み上げ速度は整数 ${LOCAL_NARRATION_LIMITS.minRate}〜${LOCAL_NARRATION_LIMITS.maxRate} の範囲で指定してください。`);
  }
  if (includeCaptionedValue !== undefined && typeof includeCaptionedValue !== 'boolean') errors.push('字幕付き版の指定はbooleanで指定してください。');
  if (captionStyleValue !== undefined && !isLocalAssemblyCaptionStylePreset(captionStyleValue)) {
    errors.push('字幕プリセットはstudio_default_v1またはshorts_ja_large_v1を指定してください。');
  }
  if (variantValue !== undefined && !isLocalQcVariant(variantValue)) errors.push('variantはcleanまたはcaptionedを指定してください。');
  if (!includeCaptioned && variant === 'captioned') errors.push('字幕なし設定ではvariant=cleanを指定してください。');
  const normalizedRate = rate ?? 0;
  const segments = narration.segments.map((segment) => ({ text: segment }));
  const request: LocalPipelineRequest = {
    workflowPreset: LOCAL_COMFYUI_WORKFLOW_PRESET,
    prompt: comfy.request.prompt,
    seed: comfy.request.seed,
    segments,
    ...(pronunciationResult.pronunciations ? { pronunciations: pronunciationResult.pronunciations } : {}),
    rate: normalizedRate,
    includeCaptioned,
    captionStylePreset,
    variant,
  };
  const voiceValue = pickIncludingNull(source, ['voice']);
  if (voiceValue !== undefined && voiceValue !== null && voiceValue !== '') {
    if (typeof voiceValue !== 'string') errors.push('音声名は文字列で指定してください。');
    else if (voiceValue.trim().length > 128) errors.push('音声名は128文字以内にしてください。');
    else request.voice = voiceValue.trim();
  }
  const payload: LocalPipelinePayload = {
    workflow_preset: LOCAL_COMFYUI_WORKFLOW_PRESET,
    prompt: comfy.payload.prompt,
    seed: comfy.payload.seed,
    segments,
    ...(request.voice ? { voice: request.voice } : {}),
    rate: normalizedRate,
    ...(request.pronunciations ? { pronunciations: request.pronunciations } : {}),
    include_captioned: includeCaptioned,
    caption_style_preset: captionStylePreset,
    variant,
  };
  return { request, payload, errors };
};

/** Build the exact local pipeline wire body; invalid drafts never cross the API boundary. */
export const buildLocalPipelinePayload = (value: unknown): LocalPipelinePayload => {
  const normalized = normalizeLocalPipelineInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

export const toLocalPipelinePayload = buildLocalPipelinePayload;

/** Serialize a validated pipeline body without rounding an int64 seed in JavaScript. */
export const serializeLocalPipelinePayload = (payload: LocalPipelinePayload): string => {
  const fields = [
    `"workflow_preset":${JSON.stringify(payload.workflow_preset)}`,
    `"prompt":${JSON.stringify(payload.prompt)}`,
    `"seed":${typeof payload.seed === 'string' ? payload.seed : String(payload.seed)}`,
    `"segments":${JSON.stringify(payload.segments)}`,
    ...(payload.voice ? [`"voice":${JSON.stringify(payload.voice)}`] : []),
    `"rate":${String(payload.rate)}`,
    ...(payload.pronunciations ? [`"pronunciations":${JSON.stringify(payload.pronunciations)}`] : []),
    `"include_captioned":${payload.include_captioned ? 'true' : 'false'}`,
    `"caption_style_preset":${JSON.stringify(payload.caption_style_preset)}`,
    `"variant":${JSON.stringify(payload.variant)}`,
  ];
  return `{${fields.join(',')}}`;
};

export const DETAILED_TEST_VIDEO_SCHEMA_VERSION = 1 as const;
export const DETAILED_TEST_VIDEO_SHORTS_PREFLIGHT_POLICY = 'shorts_ja_large_preflight_v1' as const;

const DETAILED_TEST_VIDEO_FORBIDDEN_CAPTION_CHARACTERS = new Set([
  '\u00a0', '\u200b', '\u200c', '\u200d', '\u200e', '\u200f',
  '\u202a', '\u202b', '\u202c', '\u202d', '\u202e', '\u2060',
  '\u2066', '\u2067', '\u2068', '\u2069', '\ufeff',
]);
const DETAILED_TEST_VIDEO_ASCII_TOKEN = /[!-~]+/g;

/** Mirror the backend's deterministic, font-independent Shorts caption gate. */
export const detailedTestVideoShortsCaptionErrors = (segments: readonly string[]): string[] => {
  const errors: string[] = [];
  if (segments.length > 6) errors.push('Shorts向け大字幕は6セグメント以内にしてください。');
  segments.forEach((segment, index) => {
    const label = `字幕${index + 1}`;
    if ([...segment].some((character) => DETAILED_TEST_VIDEO_FORBIDDEN_CAPTION_CHARACTERS.has(character))) {
      errors.push(`${label}に表示できない不可視文字が含まれています。`);
    }
    const displayUnits = [...segment].reduce((total, character) => {
      const point = character.codePointAt(0) ?? 0;
      return total + ((point >= 0x20 && point <= 0x7e) || (point >= 0xff61 && point <= 0xff9f) ? 1 : 2);
    }, 0);
    if (displayUnits > 38) errors.push(`${label}が長すぎます。短いセグメントに分けてください（表示幅38以内）。`);
    const tokens = segment.match(DETAILED_TEST_VIDEO_ASCII_TOKEN) ?? [];
    if (tokens.some((token) => token.length > 20)) errors.push(`${label}の半角英数字は20文字以内で区切ってください。`);
  });
  return errors;
};

export interface DetailedTestVideoPayload {
  schema_version: typeof DETAILED_TEST_VIDEO_SCHEMA_VERSION;
  clips: RemotionTimelinePayload['clips'];
  segments: Array<{ text: string }>;
  voice?: string;
  rate: number;
  pronunciations?: Array<{ source: string; target: string }>;
  include_captioned: boolean;
  caption_style_preset: LocalAssemblyCaptionStylePreset;
  audio_mix_preset: LocalAssemblyAudioMixPreset;
  variant: LocalQcVariant;
}

export interface NormalizedDetailedTestVideoInput {
  request: DetailedTestVideoRequest;
  payload: DetailedTestVideoPayload;
  outputDurationMs: number;
  errors: string[];
}

/** Normalize the complete existing-artifact detailed test-video recipe. */
export const normalizeDetailedTestVideoInput = (value: unknown): NormalizedDetailedTestVideoInput => {
  const source = asRecord(value);
  const rawSchemaVersion = pickIncludingNull(source, ['schemaVersion', 'schema_version']);
  const remotion = normalizeRemotionTimelineInput({
    schemaVersion: DETAILED_TEST_VIDEO_SCHEMA_VERSION,
    clips: pick(source, ['clips']),
  });
  const rateValue = pickIncludingNull(source, ['rate']);
  const rate = rateValue === undefined || rateValue === '' ? 0 : number(rateValue);
  const narration = normalizeNarrationInput(localPipelineScript(source), rate ?? 0);
  const pronunciationResult = localPipelinePronunciations(source);
  const includeCaptionedValue = pickIncludingNull(source, ['includeCaptioned', 'include_captioned']);
  const includeCaptioned = includeCaptionedValue === undefined ? true : includeCaptionedValue === true;
  const captionStyleValue = pick(source, ['captionStylePreset', 'caption_style_preset']);
  const captionStylePreset = isLocalAssemblyCaptionStylePreset(captionStyleValue)
    ? captionStyleValue
    : captionStyleValue === undefined
      ? includeCaptioned ? RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET : DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET
      : DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET;
  const audioMixValue = pick(source, ['audioMixPreset', 'audio_mix_preset']);
  const audioMixPreset = isLocalAssemblyAudioMixPreset(audioMixValue)
    ? audioMixValue
    : DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET;
  const variantValue = pick(source, ['variant']);
  const variant: LocalQcVariant = variantValue === 'clean' || variantValue === 'captioned'
    ? variantValue
    : includeCaptioned ? 'captioned' : 'clean';
  const errors = [
    ...remotion.errors,
    ...narration.errors,
    ...pronunciationResult.errors,
  ];
  if (includeCaptioned && captionStylePreset === 'shorts_ja_large_v1') {
    errors.push(...detailedTestVideoShortsCaptionErrors(narration.segments));
  }
  if (rawSchemaVersion !== undefined && rawSchemaVersion !== DETAILED_TEST_VIDEO_SCHEMA_VERSION) {
    errors.push(`schema_versionは${DETAILED_TEST_VIDEO_SCHEMA_VERSION}を指定してください。`);
  }
  if (rateValue !== undefined && rateValue !== '' && rate === undefined) errors.push('読み上げ速度は整数で指定してください。');
  if (rate !== undefined && (!Number.isInteger(rate) || rate < LOCAL_NARRATION_LIMITS.minRate || rate > LOCAL_NARRATION_LIMITS.maxRate)) {
    errors.push(`読み上げ速度は整数 ${LOCAL_NARRATION_LIMITS.minRate}〜${LOCAL_NARRATION_LIMITS.maxRate} の範囲で指定してください。`);
  }
  if (includeCaptionedValue !== undefined && typeof includeCaptionedValue !== 'boolean') errors.push('字幕付き版の指定はbooleanで指定してください。');
  if (captionStyleValue !== undefined && !isLocalAssemblyCaptionStylePreset(captionStyleValue)) {
    errors.push('字幕プリセットはstudio_default_v1またはshorts_ja_large_v1を指定してください。');
  }
  if (!includeCaptioned && captionStylePreset !== DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET) {
    errors.push('字幕なし設定ではcaption_style_preset=studio_default_v1を指定してください。');
  }
  if (audioMixValue !== undefined && !isLocalAssemblyAudioMixPreset(audioMixValue)) {
    errors.push('音声mixプリセットはnarration_only_v1またはsource_under_narration_v1を指定してください。');
  }
  if (variantValue !== undefined && variantValue !== 'clean' && variantValue !== 'captioned') {
    errors.push('variantはcleanまたはcaptionedを指定してください。');
  }
  if (!includeCaptioned && variant === 'captioned') errors.push('字幕なし設定ではvariant=cleanを指定してください。');
  if (audioMixPreset === 'source_under_narration_v1'
    && remotion.request.clips.length > 0
    && !remotion.request.clips.some((clip) => clip.volumePercent > 0)) {
    errors.push('素材音を残す場合は、少なくとも1カットの素材音量を1%以上にしてください。');
  }

  const segments = narration.segments.map((textValue) => ({ text: textValue }));
  const request: DetailedTestVideoRequest = {
    schemaVersion: DETAILED_TEST_VIDEO_SCHEMA_VERSION,
    clips: remotion.request.clips,
    segments,
    rate: rate ?? 0,
    ...(pronunciationResult.pronunciations ? { pronunciations: pronunciationResult.pronunciations } : {}),
    includeCaptioned,
    captionStylePreset,
    audioMixPreset,
    variant,
  };
  const voiceValue = pickIncludingNull(source, ['voice']);
  if (voiceValue !== undefined && voiceValue !== null && voiceValue !== '') {
    if (typeof voiceValue !== 'string') errors.push('音声名は文字列で指定してください。');
    else if (voiceValue.trim().length > 128) errors.push('音声名は128文字以内にしてください。');
    else request.voice = voiceValue.trim();
  }
  const payload: DetailedTestVideoPayload = {
    schema_version: DETAILED_TEST_VIDEO_SCHEMA_VERSION,
    clips: remotion.payload.clips,
    segments,
    ...(request.voice ? { voice: request.voice } : {}),
    rate: request.rate,
    ...(request.pronunciations ? { pronunciations: request.pronunciations } : {}),
    include_captioned: includeCaptioned,
    caption_style_preset: captionStylePreset,
    audio_mix_preset: audioMixPreset,
    variant,
  };
  return { request, payload, outputDurationMs: remotion.outputDurationMs, errors };
};

/** Return the exact schema-v1 wire body; arbitrary renderer fields are discarded. */
export const buildDetailedTestVideoPayload = (value: unknown): DetailedTestVideoPayload => {
  const normalized = normalizeDetailedTestVideoInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

const canonicalJson = (value: unknown): string => {
  if (value === null || typeof value === 'string' || typeof value === 'boolean' || typeof value === 'number') {
    const encoded = JSON.stringify(value);
    if (encoded === undefined) throw new TypeError('detailed test video payload is not JSON serializable');
    return encoded;
  }
  if (Array.isArray(value)) return `[${value.map((item) => canonicalJson(item)).join(',')}]`;
  if (typeof value !== 'object') throw new TypeError('detailed test video payload is not JSON serializable');
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`).join(',')}}`;
};

/** Mirror the backend canonical payload digest without exposing narration text in Job audit records. */
export const detailedTestVideoRequestPayloadSha256 = async (value: unknown): Promise<string> => {
  const subtle = globalThis.crypto?.subtle;
  if (!subtle) throw new Error('Web Crypto is unavailable');
  const payload = buildDetailedTestVideoPayload(value);
  const backendNormalizedPayload = {
    ...payload,
    voice: payload.voice ?? null,
    pronunciations: payload.pronunciations ?? [],
  };
  const digest = new Uint8Array(await subtle.digest(
    'SHA-256',
    new TextEncoder().encode(canonicalJson(backendNormalizedPayload)),
  ));
  return [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join('').toUpperCase();
};

export interface DetailedTestVideoSubmissionGuard {
  productionId: string;
  requestPayloadSha256: string;
  knownJobIds: ReadonlySet<string>;
}

export const createDetailedTestVideoSubmissionGuard = async (
  productionId: string,
  request: unknown,
  knownJobs: readonly Job[],
): Promise<DetailedTestVideoSubmissionGuard> => {
  if (!productionId || /[\u0000-\u001f\u007f]/.test(productionId)) {
    throw new TypeError('production ID is invalid');
  }
  return {
    productionId,
    requestPayloadSha256: await detailedTestVideoRequestPayloadSha256(request),
    knownJobIds: new Set(knownJobs.map((job) => job.id)),
  };
};

export const ANNOUNCEMENT_VIDEO_SCHEMA_VERSION = 1 as const;
export const ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET = 'shorts_ja_15s_v1' as const;
export const ANNOUNCEMENT_VIDEO_ROLES = ['hook', 'message', 'cta'] as const;
export const ANNOUNCEMENT_VIDEO_TRANSITION_MS = 250 as const;

const ANNOUNCEMENT_RECIPE_ID = /^announcement_[0-9a-f]{32}$/;
const ANNOUNCEMENT_ARTIFACT_ID = /^art_[0-9a-f]{32}$/;

export interface AnnouncementVideoRecipePayload {
  schema_version: typeof ANNOUNCEMENT_VIDEO_SCHEMA_VERSION;
  name: string;
  template_preset: typeof ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET;
  scenes: Array<{
    role: AnnouncementSceneRole;
    video_artifact_id: string;
    start_ms: number;
    end_ms: number;
    volume_percent: number;
    visual_preset: LocalRemotionTimelineVisualPreset;
    headline: string;
    narration: string;
  }>;
  voice: string | null;
  rate: number;
  pronunciations: Array<{ source: string; target: string }>;
  include_captioned: boolean;
  caption_style_preset: LocalAssemblyCaptionStylePreset;
  audio_mix_preset: LocalAssemblyAudioMixPreset;
  variant: LocalQcVariant;
}

export interface NormalizedAnnouncementVideoInput {
  recipe: AnnouncementVideoRecipe;
  payload: AnnouncementVideoRecipePayload;
  detailedRequest: DetailedTestVideoRequest;
  outputDurationMs: number;
  errors: string[];
}

const announcementDisplayUnits = (value: string): number => [...value].reduce((total, character) => {
  const point = character.codePointAt(0) ?? 0;
  return total + ((point >= 0x20 && point <= 0x7e) || (point >= 0xff61 && point <= 0xff9f) ? 1 : 2);
}, 0);

export const announcementHeadlineErrors = (headline: string, label: string): string[] => {
  const errors: string[] = [];
  const normalized = headline.replaceAll('\r\n', '\n').replaceAll('\r', '\n').trim();
  const lines = normalized.split('\n');
  if (!normalized) errors.push(`${label}の大見出しを入力してください。`);
  if (normalized.length > 80) errors.push(`${label}の大見出しは80文字以内にしてください。`);
  if (lines.length > 2 || lines.some((line) => !line.trim())) errors.push(`${label}の大見出しは空行なしの2行以内にしてください。`);
  if ([...normalized].some((character) => DETAILED_TEST_VIDEO_FORBIDDEN_CAPTION_CHARACTERS.has(character))) {
    errors.push(`${label}の大見出しに表示できない不可視文字が含まれています。`);
  }
  if (lines.some((line) => announcementDisplayUnits(line) > 20)) {
    errors.push(`${label}の大見出しは1行あたり表示幅20以内にしてください。`);
  }
  if (lines.some((line) => (line.match(DETAILED_TEST_VIDEO_ASCII_TOKEN) ?? []).some((token) => token.length > 20))) {
    errors.push(`${label}の半角英数字は20文字以内で区切ってください。`);
  }
  return errors;
};

const announcementRoleLabel = (role: AnnouncementSceneRole): string => ({
  hook: 'HOOK',
  message: 'MESSAGE',
  cta: 'CTA',
})[role];

/** Normalize and compile the product template without exposing renderer knobs. */
export const normalizeAnnouncementVideoInput = (value: unknown): NormalizedAnnouncementVideoInput => {
  const source = asRecord(value);
  const rawScenes = list(pick(source, ['scenes']));
  const errors: string[] = [];
  const scenes: AnnouncementVideoScene[] = ANNOUNCEMENT_VIDEO_ROLES.map((expectedRole, index) => {
    const raw = asRecord(rawScenes[index]);
    const roleValue = text(pick(raw, ['role']), '');
    const label = announcementRoleLabel(expectedRole);
    if (roleValue !== expectedRole) errors.push(`${label}のroleが不正です。HOOK → MESSAGE → CTAの順序は固定です。`);
    const artifactId = text(pick(raw, ['videoArtifactId', 'video_artifact_id']), '').trim();
    const startMs = number(pickIncludingNull(raw, ['startMs', 'start_ms']));
    const endMs = number(pickIncludingNull(raw, ['endMs', 'end_ms']));
    const volumePercent = number(pickIncludingNull(raw, ['volumePercent', 'volume_percent']));
    const visualPresetValue = pick(raw, ['visualPreset', 'visual_preset']);
    const visualPreset = isRemotionTimelineVisualPreset(visualPresetValue)
      ? visualPresetValue
      : DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET;
    const headline = text(pick(raw, ['headline']), '').replaceAll('\r\n', '\n').replaceAll('\r', '\n').trim();
    const narration = text(pick(raw, ['narration']), '').trim();
    if (!ANNOUNCEMENT_ARTIFACT_ID.test(artifactId)) errors.push(`${label}の動画artifactを選択してください。`);
    if (startMs === undefined || !Number.isInteger(startMs) || startMs < 0 || startMs > 60_000) errors.push(`${label}の開始は0〜60000msの整数で指定してください。`);
    if (endMs === undefined || !Number.isInteger(endMs) || endMs < 0 || endMs > 60_000) errors.push(`${label}の終了は0〜60000msの整数で指定してください。`);
    const duration = (endMs ?? 0) - (startMs ?? 0);
    if (duration < 1_000 || duration > 10_000) errors.push(`${label}の素材尺は1〜10秒にしてください。`);
    if (volumePercent === undefined || !Number.isInteger(volumePercent) || volumePercent < 0 || volumePercent > 100) errors.push(`${label}の素材音量は0〜100%の整数で指定してください。`);
    if (visualPresetValue !== undefined && !isRemotionTimelineVisualPreset(visualPresetValue)) {
      errors.push(`${label}の映像補正presetはpreserve_v1またはh3_low_res_sharp_v1を指定してください。`);
    }
    errors.push(...announcementHeadlineErrors(headline, label));
    if (!narration) errors.push(`${label}のナレーションを入力してください。`);
    if (narration.length > 200 || /[\r\n]/.test(narration)) errors.push(`${label}のナレーションは改行なしの200文字以内にしてください。`);
    return {
      role: expectedRole,
      videoArtifactId: artifactId,
      startMs: startMs ?? 0,
      endMs: endMs ?? 0,
      volumePercent: volumePercent ?? 0,
      visualPreset,
      headline,
      narration,
    };
  });
  if (rawScenes.length !== 3) errors.push('告知動画はHOOK・MESSAGE・CTAの3シーン固定です。');

  const schemaValue = pickIncludingNull(source, ['schemaVersion', 'schema_version']);
  if (schemaValue !== ANNOUNCEMENT_VIDEO_SCHEMA_VERSION) errors.push('schema_versionは1を指定してください。');
  const templateValue = pick(source, ['templatePreset', 'template_preset']);
  if (templateValue !== ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET) errors.push('template_presetはshorts_ja_15s_v1を指定してください。');
  const name = text(pick(source, ['name']), '').trim();
  if (!name || name.length > 120 || /[\r\n]/.test(name)) errors.push('recipe名は改行なしの1〜120文字で入力してください。');
  const rateValue = pickIncludingNull(source, ['rate']);
  const rate = rateValue === undefined || rateValue === '' ? 0 : number(rateValue);
  if (rate === undefined || !Number.isInteger(rate) || rate < -10 || rate > 10) errors.push('読み上げ速度は整数 -10〜10 の範囲で指定してください。');
  const voiceValue = pickIncludingNull(source, ['voice']);
  const voice = voiceValue === undefined || voiceValue === null || voiceValue === '' ? undefined : text(voiceValue).trim();
  if (voiceValue !== undefined && voiceValue !== null && typeof voiceValue !== 'string') errors.push('音声名は文字列で指定してください。');
  if (voice && voice.length > 128) errors.push('音声名は128文字以内にしてください。');
  const pronunciationValue = pickIncludingNull(source, ['pronunciations']);
  if (!Array.isArray(pronunciationValue)) errors.push('発音置換は配列で指定してください。');
  const rawPronunciations = list(pronunciationValue);
  const pronunciationResult = localPipelinePronunciations({
    ...source,
    pronunciations: rawPronunciations.filter((item) => {
      const record = asRecord(item);
      return Boolean(text(pick(record, ['source']), '').trim() || text(pick(record, ['target']), '').trim());
    }),
  });
  errors.push(...pronunciationResult.errors);
  const pronunciations = pronunciationResult.pronunciations ?? [];
  const includeCaptionedValue = pickIncludingNull(source, ['includeCaptioned', 'include_captioned']);
  const includeCaptioned = includeCaptionedValue === true;
  if (typeof includeCaptionedValue !== 'boolean') errors.push('字幕付き版の指定はbooleanで指定してください。');
  const captionStyleValue = pick(source, ['captionStylePreset', 'caption_style_preset']);
  const captionStylePreset = isLocalAssemblyCaptionStylePreset(captionStyleValue)
    ? captionStyleValue
    : includeCaptioned ? RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET : DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET;
  if (captionStyleValue !== undefined && !isLocalAssemblyCaptionStylePreset(captionStyleValue)) errors.push('字幕プリセットが不正です。');
  const audioMixValue = pick(source, ['audioMixPreset', 'audio_mix_preset']);
  const audioMixPreset = isLocalAssemblyAudioMixPreset(audioMixValue) ? audioMixValue : DEFAULT_LOCAL_ASSEMBLY_AUDIO_MIX_PRESET;
  if (audioMixValue !== undefined && !isLocalAssemblyAudioMixPreset(audioMixValue)) errors.push('音声mixプリセットが不正です。');
  const variantValue = pick(source, ['variant']);
  const variant: LocalQcVariant = variantValue === 'clean' || variantValue === 'captioned' ? variantValue : includeCaptioned ? 'captioned' : 'clean';
  if (variantValue !== 'clean' && variantValue !== 'captioned') errors.push('QC対象が不正です。');
  if (!includeCaptioned && captionStylePreset !== 'studio_default_v1') errors.push('字幕なしでは標準字幕presetを指定してください。');
  if (!includeCaptioned && variant === 'captioned') errors.push('字幕なしではQC対象をcleanにしてください。');

  const clips = scenes.map((scene, index): LocalRemotionTimelineClip => ({
    videoArtifactId: scene.videoArtifactId,
    startMs: scene.startMs,
    endMs: scene.endMs,
    volumePercent: scene.volumePercent,
    visualPreset: scene.visualPreset ?? DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
    transitionToNext: index === 2 ? null : { type: 'fade', durationMs: ANNOUNCEMENT_VIDEO_TRANSITION_MS },
    overlay: {
      text: scene.headline,
      startMs: 125,
      endMs: Math.max(126, scene.endMs - scene.startMs - 125),
      position: scene.role === 'message' ? 'top' : 'center',
      stylePreset: 'shorts_ja_large_v1',
    },
  }));
  const detailed = normalizeDetailedTestVideoInput({
    schemaVersion: 1,
    clips,
    segments: scenes.map((scene) => ({ text: scene.narration })),
    voice,
    rate: rate ?? 0,
    pronunciations,
    includeCaptioned,
    captionStylePreset,
    audioMixPreset,
    variant,
  });
  errors.push(...detailed.errors);
  if (detailed.outputDurationMs < 10_000 || detailed.outputDurationMs > 20_000) errors.push('完成尺は10〜20秒にしてください（推奨15秒）。');

  const recipe: AnnouncementVideoRecipe = {
    schemaVersion: ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
    name,
    templatePreset: ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET,
    scenes,
    ...(voice ? { voice } : {}),
    rate: rate ?? 0,
    pronunciations,
    includeCaptioned,
    captionStylePreset,
    audioMixPreset,
    variant,
  };
  const payload: AnnouncementVideoRecipePayload = {
    schema_version: ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
    name,
    template_preset: ANNOUNCEMENT_VIDEO_TEMPLATE_PRESET,
    scenes: scenes.map((scene) => ({
      role: scene.role,
      video_artifact_id: scene.videoArtifactId,
      start_ms: scene.startMs,
      end_ms: scene.endMs,
      volume_percent: scene.volumePercent,
      visual_preset: scene.visualPreset ?? DEFAULT_REMOTION_TIMELINE_VISUAL_PRESET,
      headline: scene.headline,
      narration: scene.narration,
    })),
    voice: voice ?? null,
    rate: rate ?? 0,
    pronunciations,
    include_captioned: includeCaptioned,
    caption_style_preset: captionStylePreset,
    audio_mix_preset: audioMixPreset,
    variant,
  };
  return { recipe, payload, detailedRequest: detailed.request, outputDurationMs: detailed.outputDurationMs, errors: [...new Set(errors)] };
};

export const buildAnnouncementVideoRecipePayload = (value: unknown): AnnouncementVideoRecipePayload => {
  const normalized = normalizeAnnouncementVideoInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return normalized.payload;
};

export const buildAnnouncementSavePayload = (expectedRevision: number, recipe: unknown) => ({
  schema_version: ANNOUNCEMENT_VIDEO_SCHEMA_VERSION,
  expected_revision: expectedRevision,
  recipe: buildAnnouncementVideoRecipePayload(recipe),
});

export const buildAnnouncementDuplicatePayload = (sourceRevision: number, newRecipeId: string, name: string) => {
  if (!Number.isInteger(sourceRevision) || sourceRevision < 1) throw new TypeError('source_revisionが不正です。');
  if (!ANNOUNCEMENT_RECIPE_ID.test(newRecipeId)) throw new TypeError('new_recipe_idが不正です。');
  const normalizedName = name.trim();
  if (!normalizedName || normalizedName.length > 120 || /[\r\n]/.test(normalizedName)) throw new TypeError('recipe名が不正です。');
  return { schema_version: 1 as const, source_revision: sourceRevision, new_recipe_id: newRecipeId, name: normalizedName };
};

export const buildAnnouncementExecutePayload = (revision: number) => {
  if (!Number.isInteger(revision) || revision < 1) throw new TypeError('revisionが不正です。');
  return { schema_version: 1 as const, revision };
};

export const normalizeAnnouncementRecipeRecord = (value: unknown): AnnouncementRecipeRecord => {
  const record = asRecord(value);
  const recipeValue = asRecord(pick(record, ['recipe']));
  const normalized = normalizeAnnouncementVideoInput(recipeValue);
  return {
    id: text(pick(record, ['id', 'recipe_id'])),
    versionId: text(pick(record, ['version_id', 'recipe_version_id'])),
    productionId: text(pick(record, ['production_id', 'productionId'])),
    revision: number(pick(record, ['revision'])) ?? 0,
    parentVersionId: text(pick(record, ['parent_version_id', 'parentVersionId']), '') || undefined,
    cloneSourceVersionId: text(pick(record, ['clone_source_version_id', 'cloneSourceVersionId']), '') || undefined,
    digest: text(pick(record, ['digest', 'recipe_digest'])),
    createdAt: text(pick(record, ['created_at', 'createdAt']), '') || undefined,
    versionCount: number(pick(record, ['version_count', 'versionCount'])) ?? 1,
    recipe: normalized.recipe,
    raw: record,
  };
};

export const normalizeAnnouncementExecutionRecord = (value: unknown): AnnouncementExecutionRecord => {
  const record = asRecord(value);
  return {
    recipeId: text(pick(record, ['recipe_id', 'recipeId'])),
    recipeVersionId: text(pick(record, ['recipe_version_id', 'recipeVersionId'])),
    recipeRevision: number(pick(record, ['recipe_revision', 'recipeRevision'])) ?? 0,
    recipeDigest: text(pick(record, ['recipe_digest', 'recipeDigest'])),
    jobId: text(pick(record, ['job_id', 'jobId'])),
    runId: text(pick(record, ['run_id', 'runId'])),
    revisionId: text(pick(record, ['revision_id', 'revisionId'])),
    requestKey: text(pick(record, ['request_key', 'requestKey'])),
    deduplicated: boolean(pick(record, ['deduplicated']), false),
    createdAt: text(pick(record, ['created_at', 'createdAt']), '') || undefined,
    raw: record,
  };
};

export const reorderTimelineClips = <T>(clips: readonly T[], fromIndex: number, toIndex: number): T[] => {
  const output = [...clips];
  if (!Number.isInteger(fromIndex) || !Number.isInteger(toIndex) || fromIndex < 0 || fromIndex >= output.length || toIndex < 0 || toIndex >= output.length || fromIndex === toIndex) return output;
  const [moved] = output.splice(fromIndex, 1);
  output.splice(toIndex, 0, moved);
  return output;
};

export const moveTimelineClip = reorderTimelineClips;

export const duplicateTimelineClip = <T>(clips: readonly T[], index: number): T[] => {
  const output = [...clips];
  if (!Number.isInteger(index) || index < 0 || index >= output.length) return output;
  output.splice(index + 1, 0, output[index]);
  return output;
};

export const LOCAL_QC_VARIANTS = ['clean', 'captioned'] as const;

export interface LocalQcPayload {
  assembly_attempt_id: string;
  variant: LocalQcVariant;
}

export interface NormalizedLocalQcInput {
  request: LocalQcRequest;
  payload: LocalQcPayload;
  errors: string[];
}

export const isLocalQcVariant = (value: unknown): value is LocalQcVariant =>
  value === 'clean' || value === 'captioned';

const localQcVariant = (value: unknown): LocalQcVariant | undefined => {
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim().toLowerCase();
  return isLocalQcVariant(normalized) ? normalized : undefined;
};

/** Build the wire body and intentionally drop every field except the API contract. */
export const buildLocalQcPayload = (value: unknown): LocalQcPayload => {
  const record = asRecord(value);
  const assemblyAttemptId = text(
    pick(record, ['assemblyAttemptId', 'assembly_attempt_id']),
    '',
  ).trim();
  const variant = localQcVariant(pick(record, ['variant']));
  if (!assemblyAttemptId) throw new TypeError('assembly_attempt_id is required');
  if (!variant) throw new TypeError("variant must be 'clean' or 'captioned'");
  return { assembly_attempt_id: assemblyAttemptId, variant };
};

export const toLocalQcPayload = buildLocalQcPayload;

export const normalizeLocalQcInput = (
  assemblyAttemptId: unknown,
  variant: unknown,
): NormalizedLocalQcInput => {
  const normalizedAttemptId = typeof assemblyAttemptId === 'string' ? assemblyAttemptId.trim() : '';
  const normalizedVariant = localQcVariant(variant) ?? 'clean';
  const errors: string[] = [];
  if (!normalizedAttemptId) errors.push('品質検査対象のassembly試行を選択してください。');
  if (!isLocalQcVariant(variant)) errors.push('variantはcleanまたはcaptionedを指定してください。');
  const request: LocalQcRequest = {
    assemblyAttemptId: normalizedAttemptId,
    variant: normalizedVariant,
  };
  return {
    request,
    payload: { assembly_attempt_id: normalizedAttemptId, variant: normalizedVariant },
    errors,
  };
};

export const normalizeStudioStageName = (value: unknown): string =>
  text(value, '').toLowerCase().trim().replaceAll('-', '_').replaceAll(' ', '_');

const externalRunStages = (value: unknown): string[] => {
  const record = asRecord(value);
  const raw = pick(record, ['requestedStages', 'requested_stages', 'stages', 'steps', 'pipeline']);
  return items(raw, ['items', 'requestedStages', 'requested_stages', 'stages', 'steps'])
    .map((stage) => normalizeStudioStageName(typeof stage === 'string' ? stage : pick(asRecord(stage), ['name', 'stage', 'key'])))
    .filter(Boolean);
};

const externalRunApproval = (value: unknown): UnknownRecord => {
  const record = asRecord(value);
  const rawApproval = pick(record, ['latestApproval', 'latest_approval', 'approval']);
  return asRecord(rawApproval);
};

const externalRunEstimate = (value: unknown): { amount?: number; currency: string } => {
  const record = asRecord(value);
  const rawEstimate = pick(record, ['estimatedCost', 'estimated_cost', 'cost']);
  const estimate = asRecord(rawEstimate);
  return {
    amount: number(rawEstimate)
      ?? number(pick(estimate, ['amount', 'value']))
      ?? number(pick(record, ['estimated_cost_amount'])),
    currency: text(pick(estimate, ['currency']) ?? pick(record, ['currency']), 'USD').toUpperCase(),
  };
};

export interface ExternalNarrationGate {
  eligible: boolean;
  profileOk: boolean;
  narrationStageOk: boolean;
  positiveEstimate: boolean;
  costApproved: boolean;
  providerConfigured: boolean;
  estimate?: number;
  estimateCurrency: string;
  approvedMax?: number;
  approvedCurrency?: string;
  reasons: string[];
}

/**
 * External execution is fail-closed at the browser boundary as well as in
 * the service: only the dedicated profile, narration stage, positive
 * estimate, matching approval cap, and configured provider may pass.
 */
export const getExternalNarrationGate = (
  value: unknown,
  providerConfigured = true,
): ExternalNarrationGate => {
  const record = asRecord(value);
  const profile = text(pick(record, ['executionProfile', 'execution_profile', 'profile']), '').toLowerCase();
  const estimate = externalRunEstimate(record);
  const approval = externalRunApproval(record);
  const approvalStatus = text(pick(approval, ['status', 'decision', 'state']), '').toLowerCase();
  const rawApprovedMax = pick(approval, ['approvedMax', 'approved_max', 'max_cost', 'maxCost']);
  const approvedMaxRecord = asRecord(rawApprovedMax);
  const approvedMax = number(rawApprovedMax)
    ?? number(pick(approvedMaxRecord, ['amount', 'value']))
    ?? number(pick(approval, ['approved_max_amount', 'max_cost_amount']));
  const approvedCurrency = text(pick(approvedMaxRecord, ['currency']) ?? pick(approval, ['currency']), '').toUpperCase() || undefined;
  const profileOk = profile === 'elevenlabs_tts';
  const narrationStageOk = externalRunStages(record).includes('narration');
  const positiveEstimate = estimate.amount !== undefined && estimate.amount > 0;
  const costApproved = approvalStatus === 'approved'
    && approvedMax !== undefined
    && approvedCurrency !== undefined
    && positiveEstimate
    && approvedMax >= (estimate.amount ?? Number.POSITIVE_INFINITY)
    && approvedCurrency === estimate.currency;
  const reasons: string[] = [];
  if (!profileOk) reasons.push('execution_profile=elevenlabs_tts のRunを選択してください。');
  if (!narrationStageOk) reasons.push('narration工程を要求したRunだけ実行できます。');
  if (!positiveEstimate) reasons.push('正の見積額があるRunだけ実行できます。');
  if (!costApproved) reasons.push('見積額以上の費用承認が必要です。');
  if (!providerConfigured) reasons.push('ElevenLabs providerが未設定です。');
  return {
    eligible: profileOk && narrationStageOk && positiveEstimate && costApproved && providerConfigured,
    profileOk,
    narrationStageOk,
    positiveEstimate,
    costApproved,
    providerConfigured,
    estimate: estimate.amount,
    estimateCurrency: estimate.currency,
    approvedMax,
    approvedCurrency,
    reasons,
  };
};

export const externalNarrationGate = getExternalNarrationGate;
export const isExternalNarrationRun = (value: unknown): boolean => getExternalNarrationGate(value).profileOk;
export const isEligibleExternalNarrationRun = (value: unknown, providerConfigured = true): boolean =>
  getExternalNarrationGate(value, providerConfigured).eligible;
export const isEligibleExternalTtsRun = isEligibleExternalNarrationRun;

export const isLocalTimelineJobForSelection = (
  value: unknown,
  selection: { runId?: string; stageAttemptId?: string },
): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(payload, keys);
  const runId = text(field(['run_id', 'runId']) ?? pick(result, ['run_id', 'runId']), '');
  const stage = normalizeStudioStageName(field(['stage', 'step', 'type', 'kind']));
  const jobType = normalizeStudioStageName(text(field(['type', 'kind']), ''));
  const provider = normalizeStudioStageName(text(
    field(['provider']) ?? pick(result, ['provider']),
    '',
  ));
  const stageAttemptId = text(
    field(['stage_attempt_id', 'stageAttemptId'])
      ?? pick(result, ['stage_attempt_id', 'stageAttemptId']),
    '',
  );
  const remotionJob = jobType === 'remotion_timeline'
    || jobType === 'local_remotion_timeline'
    || provider === 'local_remotion_timeline';
  const stageMatches = !remotionJob && (stage === 'timeline' || jobType === 'local_timeline');
  return Boolean(
    stageMatches
      && (!selection.runId || runId === selection.runId)
      && (!selection.stageAttemptId || stageAttemptId === selection.stageAttemptId),
  );
};

/** Match only Remotion timeline jobs, keeping legacy timeline polling isolated. */
export const isRemotionTimelineJobForSelection = (
  value: unknown,
  selection: { runId?: string; stageAttemptId?: string },
): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(payload, keys);
  const runId = text(field(['run_id', 'runId']) ?? pick(result, ['run_id', 'runId']), '');
  const stageAttemptId = text(
    field(['stage_attempt_id', 'stageAttemptId'])
      ?? pick(result, ['stage_attempt_id', 'stageAttemptId']),
    '',
  );
  const stage = normalizeStudioStageName(field(['stage', 'step']));
  const jobType = normalizeStudioStageName(text(field(['type', 'kind']), ''));
  const provider = normalizeStudioStageName(text(
    field(['provider']) ?? pick(result, ['provider']),
    '',
  ));
  const kindMatches = jobType === 'remotion_timeline'
    || jobType === 'local_remotion_timeline'
    || provider === 'local_remotion_timeline';
  return Boolean(
    kindMatches
      && (!stage || stage === 'timeline')
      && (!selection.runId || runId === selection.runId)
      && (!selection.stageAttemptId || stageAttemptId === selection.stageAttemptId),
  );
};

const isActiveJobStatus = (status: Job['status']): boolean =>
  status === 'pending' || status === 'running';

const jobTimestamp = (job: Job): string => job.updatedAt ?? job.startedAt ?? '';

/** Match only screen-capture jobs for the selected run. */
export const isLocalScreenCaptureJobForSelection = (
  job: Job,
  selection: { runId?: string },
): boolean => {
  const stage = normalizeStudioStageName(job.stage);
  const type = normalizeStudioStageName(job.type);
  return (stage === 'screen_capture' || type === 'local_screen_capture')
    && (!selection.runId || job.runId === selection.runId);
};

/** Match only native Windows primary-display capture jobs. */
export const isWindowsCaptureJobForSelection = (
  job: Job,
  selection: { runId?: string; consentIntentId?: string },
): boolean => {
  const stage = normalizeStudioStageName(job.stage);
  const type = normalizeStudioStageName(job.type);
  return type === 'local_windows_capture'
    && (!stage || stage === 'screen_capture')
    && (!selection.runId || job.runId === selection.runId)
    && (!selection.consentIntentId || job.consentIntentId === selection.consentIntentId);
};

/**
 * Non-secret state kept while an ambiguous execute response is reconciled.
 * The bearer token is deliberately not part of this guard.
 */
export interface WindowsCaptureSubmissionGuard {
  runId: string;
  consentIntentId: string;
  reconcileDeadlineMs: number;
  pollAttempts: number;
}

export type WindowsCaptureReconciliation =
  | { state: 'matched'; job: Job }
  | { state: 'pending'; guard: WindowsCaptureSubmissionGuard }
  | { state: 'manual_review' };

export const createWindowsCaptureSubmissionGuard = (
  intent: WindowsCaptureConsentIntent,
  receivedAtMs = Date.now(),
): WindowsCaptureSubmissionGuard => ({
  runId: intent.run_id,
  consentIntentId: intent.consent_intent_id,
  // Use a local monotonic-enough window instead of trusting clock alignment
  // with the server. The server independently enforces the same 60-second TTL.
  reconcileDeadlineMs: receivedAtMs + WINDOWS_CAPTURE_CONSENT_TTL_SECONDS * 1_000,
  pollAttempts: 0,
});

/**
 * Reconcile only the Job admitted by this exact non-secret intent lineage.
 * A same-Run Job from another tab or a later click is never accepted.
 */
export const reconcileWindowsCaptureSubmission = (
  guard: WindowsCaptureSubmissionGuard,
  jobs: Job[],
  nowMs = Date.now(),
): WindowsCaptureReconciliation => {
  const matched = jobs.find((candidate) => isWindowsCaptureJobForSelection(candidate, {
    runId: guard.runId,
    consentIntentId: guard.consentIntentId,
  }));
  if (matched) return { state: 'matched', job: matched };

  const pollAttempts = guard.pollAttempts + 1;
  if (
    nowMs >= guard.reconcileDeadlineMs
    || pollAttempts >= WINDOWS_CAPTURE_RECONCILIATION_MAX_POLLS
  ) {
    return { state: 'manual_review' };
  }
  return { state: 'pending', guard: { ...guard, pollAttempts } };
};

/**
 * Select the screen-capture job that represents the current attempt.
 *
 * A just-submitted job and the attempt's explicit links outrank the jobs
 * listing.  Only after those links are absent do we consider an in-flight
 * job, which prevents an older successful capture from masking new work.
 */
export const selectLocalScreenCaptureJob = (
  submittedJob: Job | undefined,
  currentAttempt: StageAttempt | undefined,
  jobs: Job[],
  runId?: string,
): Job | undefined => {
  if (submittedJob && (!runId || submittedJob.runId === runId)) {
    return submittedJob;
  }

  const scoped = jobs.filter((job) => isLocalScreenCaptureJobForSelection(job, { runId }));
  if (currentAttempt?.jobId) {
    const linked = scoped.find((job) => job.id === currentAttempt.jobId);
    if (linked) return linked;
  }
  if (currentAttempt?.id) {
    const linked = scoped.find((job) => job.stageAttemptId === currentAttempt.id);
    if (linked) return linked;
  }

  // A detail reload has already identified the newest attempt.  Do not let
  // an unrelated older job fill this gap while that attempt is still active;
  // the next poll will pick up its explicit job/stage link.
  if (currentAttempt) {
    return undefined;
  }

  const ordered = [...scoped].sort((left, right) => {
    const activeDelta = Number(isActiveJobStatus(right.status)) - Number(isActiveJobStatus(left.status));
    if (activeDelta !== 0) return activeDelta;
    return jobTimestamp(right).localeCompare(jobTimestamp(left));
  });
  return ordered[0];
};

/** Select the current native capture attempt without falling back to stale work. */
export const selectWindowsCaptureJob = (
  submittedJob: Job | undefined,
  currentAttempt: StageAttempt | undefined,
  jobs: Job[],
  runId?: string,
): Job | undefined => {
  if (submittedJob && (!runId || submittedJob.runId === runId)) {
    return submittedJob;
  }

  const scoped = jobs.filter((job) => isWindowsCaptureJobForSelection(job, { runId }));
  if (currentAttempt?.jobId) {
    const linked = scoped.find((job) => job.id === currentAttempt.jobId);
    if (linked) return linked;
  }
  if (currentAttempt?.id) {
    const linked = scoped.find((job) => job.stageAttemptId === currentAttempt.id);
    if (linked) return linked;
  }
  if (currentAttempt) return undefined;

  const ordered = [...scoped].sort((left, right) => {
    const activeDelta = Number(isActiveJobStatus(right.status)) - Number(isActiveJobStatus(left.status));
    if (activeDelta !== 0) return activeDelta;
    return jobTimestamp(right).localeCompare(jobTimestamp(left));
  });
  return ordered[0];
};

export const isLocalComfyUiJobForSelection = (
  value: unknown,
  selection: { runId?: string; stageAttemptId?: string },
): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(payload, keys);
  const runId = text(field(['run_id', 'runId']) ?? pick(result, ['run_id', 'runId']), '');
  const stage = normalizeStudioStageName(field(['stage', 'step', 'type', 'kind']));
  const jobType = normalizeStudioStageName(text(field(['type', 'kind']), ''));
  const stageAttemptId = text(
    field(['stage_attempt_id', 'stageAttemptId'])
      ?? pick(result, ['stage_attempt_id', 'stageAttemptId']),
    '',
  );
  const stageMatches = stage === 'video_generation' || stage === 'video' || jobType === 'local_video_generation';
  return Boolean(
    stageMatches
      && (!selection.runId || runId === selection.runId)
      && (!selection.stageAttemptId || stageAttemptId === selection.stageAttemptId),
  );
};

/** True for an in-flight ComfyUI job or stage attempt after a detail reload. */
export const isLocalComfyUiExecutionActive = (value: unknown): boolean => {
  const record = asRecord(value);
  const status = text(pick(record, ['status', 'state']), '').toLowerCase();
  return status === 'pending' || status === 'running' || status === 'queued' || status === 'processing';
};

/** Check every selected-run candidate so a stale terminal local job cannot hide active work. */
export const isLocalComfyUiExecutionActiveAcross = (values: readonly unknown[]): boolean =>
  values.some((value) => isLocalComfyUiExecutionActive(value));

export const isLocalPipelineJobForSelection = (
  value: unknown,
  selection: { productionId?: string; runId?: string },
): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(payload, keys);
  const productionId = text(field(['production_id', 'productionId']) ?? pick(result, ['production_id', 'productionId']), '');
  const runId = text(field(['run_id', 'runId']) ?? pick(result, ['run_id', 'runId']), '');
  const profile = normalizeStudioStageName(field(['execution_profile', 'executionProfile', 'profile']) ?? pick(result, ['execution_profile', 'executionProfile', 'profile']));
  const type = normalizeStudioStageName(field(['type', 'kind', 'name', 'stage', 'step']));
  const pipelineMarked = profile === 'local_pipeline' || type === 'local_pipeline' || type === 'pipeline' || type.startsWith('local_pipeline_');
  return Boolean(
    pipelineMarked
      && (!selection.productionId || productionId === selection.productionId)
      && (!selection.runId || runId === selection.runId),
  );
};

/** True for an in-flight local pipeline job, stage attempt, or nested child result. */
export const isLocalPipelineExecutionActive = (value: unknown): boolean => {
  if (isLocalComfyUiExecutionActive(value)) return true;
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const jobs = pick(record, ['jobs', 'children', 'stage_jobs', 'child_jobs'])
    ?? pick(result, ['jobs', 'children', 'stage_jobs', 'child_jobs']);
  return Object.values(asRecord(jobs)).some((item) => isLocalComfyUiExecutionActive(item));
};

export const isLocalPipelineExecutionActiveAcross = (values: readonly unknown[]): boolean =>
  values.some((value) => isLocalPipelineExecutionActive(value));

/** Match only the top-level Detailed Test Video v1 job for one production. */
export const isDetailedTestVideoJobForSelection = (
  value: unknown,
  selection: { productionId?: string; jobId?: string },
): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(payload, keys);
  const jobId = text(field(['id', 'job_id', 'jobId']), '');
  const productionId = text(field(['production_id', 'productionId']) ?? pick(result, ['production_id', 'productionId']), '');
  const type = normalizeStudioStageName(field(['type', 'kind', 'name']));
  return Boolean(
    type === 'detailed_test_video'
      && (!selection.jobId || jobId === selection.jobId)
      && (!selection.productionId || productionId === selection.productionId),
  );
};

const DETAILED_TEST_VIDEO_SHA256 = /^[0-9A-F]{64}$/;
const DETAILED_TEST_VIDEO_ANNOUNCEMENT_ALIGNMENT_FIELDS = [
  'narration_alignment_policy',
  'narration_timing_policy',
  'narration_segment_start_ms',
] as const;

/**
 * A fresh Job can resolve an ambiguous direct Detailed POST only when its
 * canonical payload digest matches and no announcement-only timing capability
 * is present. Production plus a newly observed Job ID is not sufficient.
 */
export const detailedTestVideoJobMatchesSubmissionGuard = (
  job: Job,
  guard: DetailedTestVideoSubmissionGuard,
): boolean => {
  const payload = asRecord(job.raw.payload);
  const requestPayloadSha256 = text(pick(payload, ['request_payload_sha256', 'requestPayloadSha256']), '');
  const requestKey = text(pick(payload, ['request_key', 'requestKey']), '');
  const productionId = text(pick(payload, ['production_id', 'productionId']), '');
  const profile = normalizeStudioStageName(pick(payload, ['execution_profile', 'executionProfile']));
  const stage = normalizeStudioStageName(pick(payload, ['stage']));
  const hasAnnouncementAlignment = DETAILED_TEST_VIDEO_ANNOUNCEMENT_ALIGNMENT_FIELDS.some((key) => (
    Object.prototype.hasOwnProperty.call(payload, key)
  ));
  return !guard.knownJobIds.has(job.id)
    && job.type === 'detailed_test_video'
    && job.productionId === guard.productionId
    && productionId === guard.productionId
    && profile === 'local_sapi'
    && stage === 'detailed_test_video'
    && DETAILED_TEST_VIDEO_SHA256.test(requestKey)
    && DETAILED_TEST_VIDEO_SHA256.test(requestPayloadSha256)
    && requestPayloadSha256 === guard.requestPayloadSha256
    && !hasAnnouncementAlignment;
};

export const isDetailedTestVideoExecutionActive = (value: unknown): boolean =>
  isLocalPipelineExecutionActive(value);

const rawAttemptArtifacts = (value: unknown): unknown[] => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'output']));
  const direct = items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  return direct.length > 0
    ? direct
    : items(pick(result, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
};

const rawRunRequestedStages = (value: unknown): string[] => {
  const record = asRecord(value);
  return items(
    pick(record, ['requestedStages', 'requested_stages']),
    ['items', 'requestedStages', 'requested_stages', 'stages'],
  ).map((stage) => text(stage, '')).filter(Boolean);
};

export const hasRequestedLocalQcStages = (value: unknown): boolean => {
  const stages = rawRunRequestedStages(value).map(normalizeStudioStageName);
  return stages.includes('assembly') && stages.includes('qc');
};

const isSucceededStatus = (value: unknown): boolean =>
  ['succeeded', 'success', 'completed', 'complete', 'done'].includes(text(value, '').toLowerCase());

export const isSucceededLocalFfmpegAssemblyAttempt = (value: unknown): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'output']));
  const stage = normalizeStudioStageName(pick(record, ['stage', 'stage_name', 'name', 'type']));
  const provider = text(pick(record, ['provider']) ?? pick(result, ['provider']), '').toLowerCase();
  const status = pick(record, ['status', 'state']) ?? pick(result, ['status', 'state']);
  return stage === 'assembly' && provider === 'local_ffmpeg' && isSucceededStatus(status);
};

export const getLocalQcAssemblyAttempts = (value: unknown): StageAttempt[] => {
  const record = asRecord(value);
  const values = items(
    pick(record, ['stageAttempts', 'stage_attempts', 'attempts']),
    ['items', 'stageAttempts', 'stage_attempts', 'attempts'],
  );
  return values
    .filter(isSucceededLocalFfmpegAssemblyAttempt)
    .sort((left, right) => {
      const leftDate = text(pick(asRecord(left), ['createdAt', 'created_at', 'finishedAt', 'finished_at']), '');
      const rightDate = text(pick(asRecord(right), ['createdAt', 'created_at', 'finishedAt', 'finished_at']), '');
      return rightDate.localeCompare(leftDate);
    }) as StageAttempt[];
};

export const eligibleLocalQcAssemblyAttempts = getLocalQcAssemblyAttempts;

const artifactVariant = (value: unknown): LocalQcVariant | undefined => {
  const record = asRecord(value);
  const metadata = asRecord(pick(record, ['metadata', 'meta']));
  const name = text(pick(record, ['name', 'filename', 'path', 'rel_path', 'url']), '').toLowerCase().split('?')[0];
  const kind = text(pick(record, ['kind', 'artifact_type', 'type']), '').toLowerCase();
  if (kind && kind !== 'video') return undefined;
  if (!kind && !/\.(mp4|mov|mkv|webm)$/.test(name)) return undefined;
  const hint = [
    text(pick(record, ['variant', 'version', 'label', 'role']), ''),
    text(pick(metadata, ['variant', 'version', 'label', 'role']), ''),
    name,
  ].join(' ').toLowerCase();
  if (/caption(?:ed|s)?|burn[ _-]?in|with[ _-]?caption/.test(hint)) return 'captioned';
  if (/clean|master/.test(hint) || /(?:^|[\\/])master\.(?:mp4|mov|mkv|webm)$/.test(name)) return 'clean';
  return undefined;
};

export const getLocalQcAvailableVariants = (value: unknown): LocalQcVariant[] => {
  const variants = new Set<LocalQcVariant>();
  rawAttemptArtifacts(value).forEach((artifact) => {
    const variant = artifactVariant(artifact);
    if (variant) variants.add(variant);
  });
  return LOCAL_QC_VARIANTS.filter((variant) => variants.has(variant));
};

export const availableLocalQcVariants = getLocalQcAvailableVariants;

export const getLocalQcVariantAvailability = (value: unknown): Record<LocalQcVariant, boolean> => {
  const variants = new Set(getLocalQcAvailableVariants(value));
  return { clean: variants.has('clean'), captioned: variants.has('captioned') };
};

export const isEligibleLocalQcRun = (value: unknown): boolean => {
  const record = asRecord(value);
  const profile = text(pick(record, ['executionProfile', 'execution_profile', 'profile']), '').toLowerCase();
  return ['local_sapi', 'elevenlabs_tts'].includes(profile)
    && hasRequestedLocalQcStages(record)
    && getLocalQcAssemblyAttempts(record).some((attempt) => getLocalQcAvailableVariants(attempt).length > 0);
};

export const eligibleLocalQcRuns = (values: unknown): ProductionRun[] =>
  (Array.isArray(values) ? values : []).filter(isEligibleLocalQcRun) as ProductionRun[];

export type LocalQcResultPhase =
  | 'pending'
  | 'running'
  | 'job_succeeded_analysis_complete_pass'
  | 'job_succeeded_analysis_complete_fail'
  | 'job_succeeded_analysis_incomplete'
  | 'analysis_failed'
  | 'job_failed'
  | 'job_cancelled'
  | 'unknown';

export interface LocalQcResultStatus {
  phase: LocalQcResultPhase;
  jobStatus: string;
  jobSucceeded: boolean;
  analysisStatus?: string;
  analysisComplete: boolean;
  technicalVerdict?: LocalQcVerdict;
  technicalPassed: boolean;
  technicalFailed: boolean;
}

export const getLocalQcResultStatus = (value: unknown): LocalQcResultStatus => {
  const root = asRecord(value);
  const result = asRecord(pick(root, ['result', 'job_result', 'output']));
  const source = Object.keys(result).length > 0 ? result : root;
  const jobStatus = text(pick(root, ['status', 'state']), '').toLowerCase();
  const jobSucceeded = ['succeeded', 'success', 'completed', 'complete', 'done'].includes(jobStatus);
  const analysisStatus = text(pick(source, ['analysisStatus', 'analysis_status']), '').toLowerCase() || undefined;
  const verdictValue = text(pick(source, ['technicalVerdict', 'technical_verdict']), '').toLowerCase();
  const technicalVerdict = verdictValue === 'pass' || verdictValue === 'fail' ? verdictValue : undefined;
  const analysisComplete = jobSucceeded && analysisStatus === 'succeeded';
  let phase: LocalQcResultPhase = 'unknown';
  if (['queued', 'pending', 'created'].includes(jobStatus)) phase = 'pending';
  else if (['running', 'processing'].includes(jobStatus)) phase = 'running';
  else if (['failed', 'error', 'errored'].includes(jobStatus)) phase = 'job_failed';
  else if (['cancelled', 'canceled', 'interrupted', 'aborted', 'stopped'].includes(jobStatus)) phase = 'job_cancelled';
  else if (jobSucceeded && analysisStatus === 'failed') phase = 'analysis_failed';
  else if (jobSucceeded && analysisComplete && technicalVerdict === 'pass') phase = 'job_succeeded_analysis_complete_pass';
  else if (jobSucceeded && analysisComplete && technicalVerdict === 'fail') phase = 'job_succeeded_analysis_complete_fail';
  else if (jobSucceeded) phase = 'job_succeeded_analysis_incomplete';
  return {
    phase,
    jobStatus,
    jobSucceeded,
    analysisStatus,
    analysisComplete,
    technicalVerdict,
    technicalPassed: technicalVerdict === 'pass',
    technicalFailed: technicalVerdict === 'fail',
  };
};

export const localQcResultStatus = getLocalQcResultStatus;

export const isLocalQcJobForSelection = (
  value: unknown,
  selection: { runId?: string; assemblyAttemptId: string; variant: LocalQcVariant },
): boolean => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'job_result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const runId = text(pick(record, ['run_id', 'runId']) ?? pick(payload, ['run_id', 'runId']), '');
  const stage = normalizeStudioStageName(pick(record, ['stage', 'step', 'type', 'kind']));
  const jobType = text(pick(record, ['type', 'kind']), '');
  const assemblyAttemptId = text(
    pick(record, ['assembly_attempt_id', 'assemblyAttemptId'])
      ?? pick(result, ['assembly_attempt_id', 'assemblyAttemptId'])
      ?? pick(payload, ['assembly_attempt_id', 'assemblyAttemptId']),
    '',
  );
  const variant = localQcVariant(pick(record, ['variant']) ?? pick(result, ['variant']) ?? pick(payload, ['variant']));
  return Boolean(
    selection.assemblyAttemptId
      && assemblyAttemptId === selection.assemblyAttemptId
      && variant === selection.variant
      && (!selection.runId || runId === selection.runId)
      && (stage === 'qc' || jobType === 'local_qc'),
  );
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

const normalizeQcVerdict = (value: unknown): LocalQcVerdict | undefined => {
  const normalized = text(value, '').toLowerCase();
  return normalized === 'pass' || normalized === 'fail' ? normalized : undefined;
};

const normalizeQcChecks = (value: unknown): QcCheck[] => {
  const values = items(value, ['items', 'checks']);
  if (values.length > 0) {
    return values.map((item) => {
      if (typeof item === 'string' || typeof item === 'number') return { name: String(item) };
      return asRecord(item) as QcCheck;
    });
  }
  const record = asRecord(value);
  return Object.entries(record).map(([name, item]) => {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const check = asRecord(item) as QcCheck;
      return { name: check.name === undefined ? name : String(check.name), ...check };
    }
    return { name, status: typeof item === 'boolean' ? (item ? 'pass' : 'fail') : text(item, '') || undefined };
  });
};

const normalizeQcFields = (record: UnknownRecord, result: UnknownRecord, payload: UnknownRecord = {}): Pick<StageAttempt, 'durationMs' | 'analysisStatus' | 'technicalVerdict' | 'assemblyAttemptId' | 'variant' | 'checks' | 'mediaFacts'> => {
  const field = (keys: string[]): unknown => pick(record, keys) ?? pick(result, keys) ?? pick(payload, keys);
  const checkValue = field(['checks', 'qc_checks']);
  const factsValue = field(['media_facts', 'mediaFacts', 'facts']);
  return {
    durationMs: number(field(['duration_ms', 'elapsed_ms'])),
    analysisStatus: text(field(['analysis_status', 'analysisStatus']), '').toLowerCase() || undefined,
    technicalVerdict: normalizeQcVerdict(field(['technical_verdict', 'technicalVerdict'])),
    assemblyAttemptId: text(field(['assembly_attempt_id', 'assemblyAttemptId']), '') || undefined,
    variant: localQcVariant(field(['variant'])),
    checks: normalizeQcChecks(checkValue),
    mediaFacts: asRecord(factsValue),
  };
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

const PROVIDER_TASK_STATUSES = new Set<ProviderTaskStatus>([
  'prepared',
  'submitted',
  'recovering',
  'succeeded',
  'failed',
  'ambiguous',
  'recovery_blocked',
  'cancel_requested',
]);

const PIPELINE_CONTINUATION_STATES = new Set<PipelineContinuationState>([
  'active',
  'waiting_provider',
  'ready',
  'continuing',
  'succeeded',
  'recovery_blocked',
  'unavailable',
  'cancel_requested',
  'cancelled',
]);
const PIPELINE_CONTINUATION_ACTIVE_STATES = new Set<PipelineContinuationState>([
  'active',
  'waiting_provider',
  'ready',
  'continuing',
  'cancel_requested',
]);

const normalizePipelineContinuationState = (value: unknown): PipelineContinuationState => {
  const normalized = text(value, '').toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');
  return PIPELINE_CONTINUATION_STATES.has(normalized as PipelineContinuationState)
    ? normalized as PipelineContinuationState
    : 'recovery_blocked';
};

const normalizePipelineContinuationError = (
  value: unknown,
): PipelineContinuation['error'] => {
  if (value === null) return null;
  const record = asRecord(value);
  const code = text(pick(record, ['code', 'error_code', 'errorCode']), '') || undefined;
  const message = text(pick(record, ['message', 'detail', 'error_message', 'errorMessage']), '') || undefined;
  return code || message ? { code, message } : null;
};

export const normalizePipelineContinuation = (value: unknown): PipelineContinuation | undefined => {
  const record = asRecord(value);
  if (Object.keys(record).length === 0) return undefined;
  const errorValue = pickIncludingNull(record, ['error']);
  const state = normalizePipelineContinuationState(pick(record, ['state', 'status']));
  const automatic = boolean(pick(record, ['automatic']), false);
  const resumeCount = number(pick(record, ['resume_count', 'resumeCount']));
  const jobId = text(pick(record, ['job_id', 'jobId']), '') || undefined;
  const sourceJobId = text(pick(record, ['source_job_id', 'sourceJobId']), '') || undefined;
  const sourceAttemptId = text(pick(record, ['source_attempt_id', 'sourceAttemptId']), '') || undefined;
  const updatedAt = text(pick(record, ['updated_at', 'updatedAt']), '') || undefined;
  const error = normalizePipelineContinuationError(errorValue);
  const safeRaw: Record<string, unknown> = { state, automatic, error };
  if (resumeCount !== undefined) safeRaw.resume_count = resumeCount;
  if (jobId !== undefined) safeRaw.job_id = jobId;
  if (sourceJobId !== undefined) safeRaw.source_job_id = sourceJobId;
  if (sourceAttemptId !== undefined) safeRaw.source_attempt_id = sourceAttemptId;
  if (updatedAt !== undefined) safeRaw.updated_at = updatedAt;
  return {
    state,
    automatic,
    resumeCount,
    jobId,
    sourceJobId,
    sourceAttemptId,
    updatedAt,
    error,
    raw: safeRaw,
  };
};

/** States in which the backend may still advance the same immutable Run. */
export const isPipelineContinuationActive = (value: unknown): boolean => {
  const record = asRecord(value);
  const state = normalizePipelineContinuationState(pick(record, ['state', 'status']));
  return PIPELINE_CONTINUATION_ACTIVE_STATES.has(state);
};

/** Only a true local_pipeline top job may represent the pipeline summary. */
export const isLocalPipelineTopJob = (value: unknown): boolean => {
  const record = asRecord(value);
  const raw = asRecord(pick(record, ['raw']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']) ?? pick(raw, ['payload', 'request', 'meta']));
  return [record, raw, payload].some((source) => ['kind', 'type']
    .some((key) => normalizeStudioStageName(source[key]) === 'local_pipeline'));
};

const EMPTY_JOB_ID_SET: ReadonlySet<string> = new Set<string>();

/**
 * Keep the global stop surface at orchestration boundaries.
 *
 * A pipeline child is implementation detail: cancelling it alone can leave
 * the top-level claim running until that orchestrator observes the failure.
 * When an active/cancelling top Job for the same Run is visible, show only
 * that top Job. Orphaned active children remain visible so operators are not
 * denied a stop control when no parent can be reconciled.
 */
export const selectGlobalJobControlTargets = (
  values: readonly Job[],
  cancellingJobIds: ReadonlySet<string> = EMPTY_JOB_ID_SET,
): Job[] => {
  const candidates = values.filter((job) => (
    job.status === 'running'
    || job.status === 'pending'
    || cancellingJobIds.has(job.id)
  ));
  const topRuns = new Set<string>();
  const topJobIds = new Set<string>();
  candidates.forEach((job) => {
    if (!job.runId) return;
    if (isLocalPipelineTopJob(job) || isDetailedTestVideoJobForSelection(job, {})) {
      topRuns.add(job.runId);
      topJobIds.add(job.id);
    }
  });
  return candidates.filter((job) => (
    !job.runId || !topRuns.has(job.runId) || topJobIds.has(job.id)
  ));
};

const normalizeProviderTaskStatus = (value: unknown): ProviderTaskStatus => {
  const normalized = text(value, '').toLowerCase().replaceAll('-', '_').replaceAll(' ', '_');
  return PROVIDER_TASK_STATUSES.has(normalized as ProviderTaskStatus)
    ? normalized as ProviderTaskStatus
    : 'recovery_blocked';
};

const normalizeProviderTaskError = (value: unknown, record: UnknownRecord): ProviderTask['error'] => {
  const nested = asRecord(value);
  const code = text(
    pick(record, ['error_code', 'errorCode']) ?? pick(nested, ['code', 'error_code', 'errorCode']),
    '',
  ) || undefined;
  const message = text(
    pick(record, ['error_message', 'errorMessage']) ?? pick(nested, ['message', 'detail']),
    '',
  ) || (typeof value === 'string' ? value : undefined);
  return code || message ? { code, message } : undefined;
};

export const normalizeProviderTask = (value: unknown, index = 0): ProviderTask => {
  const record = asRecord(value);
  return {
    id: text(pick(record, ['id', 'provider_task_record_id', 'providerTaskRecordId']), `provider-task-${index}`),
    provider: text(pick(record, ['provider']), 'comfyui'),
    productionId: text(pick(record, ['production_id', 'productionId']), '') || undefined,
    runId: text(pick(record, ['run_id', 'runId']), '') || undefined,
    stage: text(pick(record, ['stage']), '') || undefined,
    status: normalizeProviderTaskStatus(pick(record, ['status', 'state'])),
    providerTaskId: text(pick(record, ['provider_task_id', 'providerTaskId']), '') || undefined,
    attemptSequence: number(pick(record, ['attempt_sequence', 'attemptSequence'])),
    activeStageAttemptId: text(pick(record, ['active_stage_attempt_id', 'activeStageAttemptId', 'current_stage_attempt_id', 'currentStageAttemptId']), '') || undefined,
    activeJobId: text(pick(record, ['active_job_id', 'activeJobId', 'current_job_id', 'currentJobId']), '') || undefined,
    recoveryCount: number(pick(record, ['recovery_count', 'recoveryCount'])),
    automaticRecoveryAvailable: boolean(pick(record, ['automatic_recovery_available', 'automaticRecoveryAvailable']), false),
    duplicateSubmissionBlocked: boolean(pick(record, ['duplicate_submission_blocked', 'duplicateSubmissionBlocked']), false),
    resumable: boolean(pick(record, ['resumable']), false),
    nextAction: text(pick(record, ['next_action', 'nextAction']), '') || undefined,
    createdAt: text(pick(record, ['created_at', 'createdAt']), '') || undefined,
    updatedAt: text(pick(record, ['updated_at', 'updatedAt']), '') || undefined,
    checkedAt: text(pick(record, ['last_observed_at', 'lastObservedAt', 'checked_at', 'checkedAt']), '') || undefined,
    error: normalizeProviderTaskError(pick(record, ['error']), record),
    raw: record,
  };
};

const normalizeProviderTasks = (value: unknown): ProviderTask[] =>
  items(value, ['items', 'provider_tasks', 'providerTasks']).map(normalizeProviderTask);

const rawProviderTaskStatus = (value: unknown): ProviderTaskStatus =>
  normalizeProviderTaskStatus(pick(asRecord(value), ['status', 'state']));

/** Provider states where another provider operation may still be in flight. */
export const isProviderTaskActive = (value: unknown): boolean =>
  new Set<ProviderTaskStatus>(['prepared', 'submitted', 'recovering', 'cancel_requested']).has(rawProviderTaskStatus(value));

/** Fail closed when recovery or duplicate-submission protection is reported. */
export const isProviderTaskBlocking = (value: unknown): boolean => {
  const record = asRecord(value);
  const status = rawProviderTaskStatus(value);
  return isProviderTaskActive(value)
    || status === 'ambiguous'
    || status === 'recovery_blocked'
    || boolean(pick(record, ['duplicate_submission_blocked', 'duplicateSubmissionBlocked']), false)
    || boolean(pick(record, ['automatic_recovery_available', 'automaticRecoveryAvailable']), false)
    || boolean(pick(record, ['resumable']), false);
};

/** Only backend-authorized recovery actions can expose the resume button. */
export const isProviderTaskResumeAvailable = (value: unknown): boolean => {
  const record = asRecord(value);
  const status = rawProviderTaskStatus(value);
  const activeJobId = text(
    pick(record, ['active_job_id', 'activeJobId', 'current_job_id', 'currentJobId']),
    '',
  );
  if (activeJobId || !new Set<ProviderTaskStatus>(['prepared', 'submitted', 'ambiguous', 'recovery_blocked', 'cancel_requested']).has(status)) {
    return false;
  }
  return boolean(pick(record, ['resumable']), false)
    || boolean(pick(record, ['automatic_recovery_available', 'automaticRecoveryAvailable']), false);
};

/**
 * Return the newest timestamp available for provider-task observation.
 *
 * A provider GET updates last_observed_at without necessarily changing the
 * task state, so observation time must take precedence over state/update time
 * when the UI orders recovery records.
 */
export const providerTaskTimestamp = (task: ProviderTask): string =>
  task.checkedAt ?? task.updatedAt ?? task.createdAt ?? '';

/** Keep the newest observable timestamp first, then use attempt order as a tie-breaker. */
export const newestProviderTasks = (tasks: ProviderTask[]): ProviderTask[] => [...tasks]
  .sort((left, right) => {
    const timestampDelta = providerTaskTimestamp(right).localeCompare(providerTaskTimestamp(left));
    const sequenceDelta = (right.attemptSequence ?? 0) - (left.attemptSequence ?? 0);
    return timestampDelta || sequenceDelta;
  });

export const normalizeRun = (value: unknown, index: number): ProductionRun => {
  const record = asRecord(value);
  const requestedStageValue = pick(record, ['requested_stages', 'requestedStages', 'stages', 'steps', 'pipeline']);
  const stageValues = items(requestedStageValue, ['items', 'stages', 'steps', 'requested_stages']);
  const requestedStages = stringList(stageValues.length > 0 ? stageValues : requestedStageValue);
  const estimatedCost = asRecord(pick(record, ['estimated_cost', 'cost']));
  const latestApprovalValue = pick(record, ['latest_approval', 'approval']);
  return {
    id: text(pick(record, ['id', 'run_id']), `run-${index}`),
    revisionId: text(pick(record, ['revision_id', 'revisionId']), '') || undefined,
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
    providerTasks: normalizeProviderTasks(pick(record, ['provider_tasks', 'providerTasks'])),
    pipelineContinuation: normalizePipelineContinuation(
      pick(record, ['pipeline_continuation', 'pipelineContinuation']),
    ),
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
    durationSeconds: number(pick(record, ['duration_seconds', 'duration', 'duration_sec']))
      ?? number(pick(metadata, ['duration_seconds', 'duration', 'duration_sec'])),
    description: text(pick(record, ['description', 'summary']), '') || undefined,
    metadata,
    raw: record,
  };
};

const externalActualCostValue = (record: UnknownRecord, result: UnknownRecord): unknown => {
  const directUsd = pickIncludingNull(record, ['actual_cost_usd', 'actualCostUsd', 'usd_cost']);
  if (directUsd !== undefined) return directUsd;
  const resultUsd = pickIncludingNull(result, ['actual_cost_usd', 'actualCostUsd', 'usd_cost']);
  if (resultUsd !== undefined) return resultUsd;
  const provider = text(pick(record, ['provider']) ?? pick(result, ['provider']), '').toLowerCase();
  if (provider !== EXTERNAL_NARRATION_PROVIDER) return undefined;
  const directActual = pickIncludingNull(record, ['actual_cost', 'actualCost']);
  if (directActual !== undefined) return directActual;
  return pickIncludingNull(result, ['actual_cost', 'actualCost']);
};

const integerOrDecimalText = (value: unknown): number | string | undefined => {
  if (typeof value === 'number' && Number.isInteger(value) && Number.isFinite(value)) return value;
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return undefined;
  return normalized.length <= 15 ? Number(normalized) : normalized;
};

const seedDecimalText = (value: unknown): string | undefined => {
  if (typeof value !== 'string' || !/^\d+$/.test(value.trim())) return undefined;
  const normalized = value.trim();
  return normalized.replace(/^0+(?=\d)/, '');
};

const normalizeLocalComfyUiMetadata = (
  record: UnknownRecord,
  result: UnknownRecord,
): Pick<StageAttempt, 'promptSha256' | 'seed' | 'workflowPreset'> => ({
  promptSha256: text(
    pick(record, ['prompt_sha256', 'promptSha256'])
      ?? pick(result, ['prompt_sha256', 'promptSha256']),
    '',
  ) || undefined,
  seed: seedDecimalText(
    pick(record, ['seed_decimal', 'seedDecimal'])
      ?? pick(result, ['seed_decimal', 'seedDecimal']),
  ) ?? integerOrDecimalText(
    pick(record, ['seed']) ?? pick(result, ['seed']),
  ),
  workflowPreset: text(
    pick(record, ['workflow_preset', 'workflowPreset'])
      ?? pick(result, ['workflow_preset', 'workflowPreset']),
    '',
  ) || undefined,
});

const normalizeLocalPipelineStageResult = (value: unknown, fallbackStage: string): LocalPipelineStageResult => {
  const record = asRecord(value);
  const result = asRecord(pick(record, ['result', 'output']));
  const source = Object.keys(result).length > 0 ? result : record;
  const artifactValues = items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  const resultArtifactValues = items(pick(result, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  return {
    stage: normalizeStudioStageName(text(pick(record, ['stage', 'stage_name', 'name', 'type']) ?? pick(result, ['stage', 'stage_name', 'name', 'type']), fallbackStage)),
    status: normalizeStatus(pick(record, ['status', 'state']) ?? pick(result, ['status', 'state'])),
    jobId: text(pick(record, ['job_id', 'jobId']) ?? pick(result, ['job_id', 'jobId']), '') || undefined,
    stageAttemptId: text(pick(record, ['stage_attempt_id', 'stageAttemptId']) ?? pick(result, ['stage_attempt_id', 'stageAttemptId']), '') || undefined,
    attempt: number(pick(record, ['attempt', 'attempt_number', 'try']) ?? pick(result, ['attempt', 'attempt_number', 'try'])),
    cacheHit: pick(record, ['cache_hit', 'cacheHit', 'cached']) === undefined
      ? (pick(result, ['cache_hit', 'cacheHit', 'cached']) === undefined ? undefined : boolean(pick(result, ['cache_hit', 'cacheHit', 'cached'])))
      : boolean(pick(record, ['cache_hit', 'cacheHit', 'cached'])),
    progress: number(pick(record, ['progress', 'percent', 'percentage']) ?? pick(result, ['progress', 'percent', 'percentage'])),
    message: text(pick(record, ['message', 'detail', 'error']) ?? pick(result, ['message', 'detail', 'error']), '') || undefined,
    artifacts: (artifactValues.length > 0 ? artifactValues : resultArtifactValues).map(normalizeArtifact),
    raw: source,
  };
};

const normalizeLocalPipelineJobs = (value: unknown): Record<string, LocalPipelineStageResult> => {
  const entries: Array<[string, unknown]> = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : Object.entries(asRecord(value));
  return Object.fromEntries(entries.map(([key, item]) => {
    const fallbackStage = normalizeStudioStageName(key) || `stage_${key}`;
    const normalized = normalizeLocalPipelineStageResult(item, fallbackStage);
    return [normalized.stage || fallbackStage, normalized];
  }));
};

const normalizeStageAttempt = (value: unknown, index: number): StageAttempt => {
  const record = asRecord(value);
  const stage = text(pick(record, ['stage', 'stage_name', 'name', 'type']), 'narration');
  const result = asRecord(pick(record, ['result', 'output']));
  const payload = asRecord(pick(record, ['payload', 'request', 'meta']));
  const error = normalizeError(record, normalizeError(result).message ?? '');
  const artifactValues = items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  const resultArtifactValues = items(pick(result, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']);
  const artifacts = (artifactValues.length > 0 ? artifactValues : resultArtifactValues).map(normalizeArtifact);
  const comfyMetadata = normalizeLocalComfyUiMetadata(record, result);
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
    ...normalizeQcFields(record, result, payload),
    cacheHit: pick(record, ['cache_hit', 'cacheHit', 'cached']) === undefined
      ? (pick(result, ['cache_hit', 'cacheHit', 'cached']) === undefined ? undefined : boolean(pick(result, ['cache_hit', 'cacheHit', 'cached'])))
      : boolean(pick(record, ['cache_hit', 'cacheHit', 'cached'])),
    provider: text(pick(record, ['provider']) ?? pick(result, ['provider']), '') || undefined,
    providerTaskId: text(pick(record, ['provider_task_id', 'providerTaskId']) ?? pick(result, ['provider_task_id', 'providerTaskId']), '') || undefined,
    ...comfyMetadata,
    characterCost: number(pick(record, ['character_cost', 'characterCost', 'billable_characters']) ?? pick(result, ['character_cost', 'characterCost', 'billable_characters'])),
    actualCostUsd: numberOrNull(externalActualCostValue(record, result)),
    actualCost: number(pick(record, ['actual_cost', 'actualCost']) ?? pick(result, ['actual_cost', 'actualCost'])),
    timingSource: text(pick(record, ['timing_source', 'timingSource']) ?? pick(result, ['timing_source', 'timingSource']), '') || undefined,
    artifacts,
    message: error.message,
    errorCode: error.code,
    raw: record,
  };
};

const normalizeJobResult = (value: unknown, outerRecord: UnknownRecord = {}): JobResult | undefined => {
  if (!value || typeof value !== 'object') return undefined;
  const record = asRecord(value);
  const nestedResult = asRecord(pick(record, ['result', 'output']));
  const result = Object.keys(nestedResult).length > 0 ? nestedResult : {};
  const error = normalizeError(record, normalizeError(result).message ?? '');
  const directRecord = { ...outerRecord, ...record };
  const comfyMetadata = normalizeLocalComfyUiMetadata(directRecord, result);
  const pipelineJobsValue = pick(record, ['jobs', 'children', 'stage_jobs', 'child_jobs'])
    ?? pick(result, ['jobs', 'children', 'stage_jobs', 'child_jobs']);
  const pipelineJobs = pipelineJobsValue === undefined ? undefined : normalizeLocalPipelineJobs(pipelineJobsValue);
  return {
    runId: text(pick(directRecord, ['run_id', 'runId']) ?? pick(result, ['run_id', 'runId']), '') || undefined,
    revisionId: text(pick(directRecord, ['revision_id', 'revisionId']) ?? pick(result, ['revision_id', 'revisionId']), '') || undefined,
    attempt: number(pick(record, ['attempt', 'attempt_number', 'try']) ?? pick(result, ['attempt', 'attempt_number', 'try'])),
    stageAttemptId: text(pick(record, ['stage_attempt_id', 'stageAttemptId']) ?? pick(result, ['stage_attempt_id', 'stageAttemptId']), '') || undefined,
    artifacts: (items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs']).length > 0
      ? items(pick(record, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs'])
      : items(pick(result, ['artifacts', 'outputs']), ['items', 'artifacts', 'outputs'])).map(normalizeArtifact),
    cacheHit: pick(record, ['cache_hit', 'cacheHit', 'cached']) === undefined
      ? (pick(result, ['cache_hit', 'cacheHit', 'cached']) === undefined ? undefined : boolean(pick(result, ['cache_hit', 'cacheHit', 'cached'])))
      : boolean(pick(record, ['cache_hit', 'cacheHit', 'cached'])),
    durationSeconds: durationSeconds(record) ?? durationSeconds(result),
    ...normalizeQcFields(record, result),
    jobs: pipelineJobs,
    provider: text(pick(directRecord, ['provider']) ?? pick(result, ['provider']), '') || undefined,
    providerTaskId: text(pick(directRecord, ['provider_task_id', 'providerTaskId']) ?? pick(result, ['provider_task_id', 'providerTaskId']), '') || undefined,
    ...comfyMetadata,
    characterCost: number(pick(record, ['character_cost', 'characterCost', 'billable_characters']) ?? pick(result, ['character_cost', 'characterCost', 'billable_characters'])),
    actualCostUsd: numberOrNull(externalActualCostValue(directRecord, result)),
    actualCost: number(pick(directRecord, ['actual_cost', 'actualCost']) ?? pick(result, ['actual_cost', 'actualCost'])),
    timingSource: text(pick(directRecord, ['timing_source', 'timingSource']) ?? pick(result, ['timing_source', 'timingSource']), '') || undefined,
    structuralTimingVerified: optionalLiteralBoolean(
      pick(directRecord, ['structural_timing_verified', 'structuralTimingVerified'])
        ?? pick(result, ['structural_timing_verified', 'structuralTimingVerified']),
    ),
    contentSyncVerified: optionalLiteralBoolean(
      pick(directRecord, ['content_sync_verified', 'contentSyncVerified'])
        ?? pick(result, ['content_sync_verified', 'contentSyncVerified']),
    ),
    liveValidationRequired: optionalLiteralBoolean(
      pick(directRecord, ['live_validation_required', 'liveValidationRequired'])
        ?? pick(result, ['live_validation_required', 'liveValidationRequired']),
    ),
    validationScope: text(
      pick(directRecord, ['validation_scope', 'validationScope'])
        ?? pick(result, ['validation_scope', 'validationScope']),
      '',
    ) || undefined,
    publicReleaseReady: optionalLiteralBoolean(
      pick(directRecord, ['public_release_ready', 'publicReleaseReady'])
        ?? pick(result, ['public_release_ready', 'publicReleaseReady']),
    ),
    publicReleaseGate: text(
      pick(directRecord, ['public_release_gate', 'publicReleaseGate'])
        ?? pick(result, ['public_release_gate', 'publicReleaseGate']),
      '',
    ) || undefined,
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
  const directResult = pick(record, ['result', 'job_result', 'output']) ?? pick(root, ['result', 'job_result', 'output']);
  const hasInlinePipelineResult = ['artifacts', 'jobs', 'children', 'technical_verdict', 'technicalVerdict', 'revision_id', 'revisionId']
    .some((key) => record[key] !== undefined);
  const resultValue = directResult ?? (hasInlinePipelineResult ? record : undefined);
  const result = normalizeJobResult(resultValue, record);
  const error = normalizeError(record, result?.message ?? '');
  const assemblyAttemptId = text(
    field(['assembly_attempt_id', 'assemblyAttemptId'])
      ?? pick(asRecord(resultValue), ['assembly_attempt_id', 'assemblyAttemptId']),
    '',
  ) || undefined;
  const variantValue = field(['variant']) ?? pick(asRecord(resultValue), ['variant']);
  const variant = localQcVariant(variantValue);
  const stageAttemptId = text(
    field(['stage_attempt_id', 'stageAttemptId'])
      ?? pick(asRecord(resultValue), ['stage_attempt_id', 'stageAttemptId']),
    '',
  ) || undefined;
  const consentIntentId = text(
    field(['consent_intent_id', 'consentIntentId'])
      ?? pick(asRecord(resultValue), ['consent_intent_id', 'consentIntentId']),
    '',
  ) || undefined;
  return {
    id: text(field(['id', 'job_id']), `job-${index}`),
    productionId: text(field(['production_id', 'productionId']), '') || undefined,
    runId: text(field(['run_id', 'runId']), '') || undefined,
    consentIntentId,
    type: text(field(['type', 'kind', 'name']), 'ジョブ'),
    stage: text(field(['stage', 'step']), '') || undefined,
    status: normalizeStatus(field(['status', 'state'])),
    progress: number(field(['progress', 'percent', 'percentage'])),
    progressPhase: text(field(['progress_phase', 'progressPhase']), '') || undefined,
    message: error.message,
    startedAt: text(field(['started_at', 'startedAt']), '') || undefined,
    // The jobs endpoint exposes created_at for pending jobs and often omits
    // updated_at.  Keep that timestamp so a new queued job cannot sort behind
    // an older terminal capture in the Studio UI.
    updatedAt: text(field(['updated_at', 'updatedAt', 'finished_at', 'finishedAt', 'completed_at', 'created_at', 'createdAt']), '') || undefined,
    attempt: number(field(['attempt', 'attempt_number', 'try'])) ?? result?.attempt,
    stageAttemptId,
    assemblyAttemptId,
    variant,
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
    archived: boolean(pick(record, ['archived']), false),
    archivedAt: text(pick(record, ['archived_at', 'archivedAt']), '') || undefined,
    libraryReadOnly: boolean(pick(record, ['library_read_only', 'libraryReadOnly']), false),
    tags,
    raw: record,
  };
};

export const REVIEW_SCHEMA_VERSION = 1 as const;
export const REVIEW_ID_PATTERN = /^review_[0-9a-f]{32}$/;
export const REVIEW_ARTIFACT_PATTERN = /^art_[0-9a-f]{32}$/;
export const REVIEW_REVISION_PATTERN = /^rev_[0-9a-f]{32}$/;
export const REVIEW_RUN_PATTERN = /^run_[0-9a-f]{32}$/;
export const REVIEW_CUT_PATTERN = /^cut_[0-9a-f]{32}$/;
const REVIEW_ACTION_PATTERN = /^review_action_[0-9a-f]{32}$/;
const REVIEW_PLAN_PATTERN = /^review_plan_[0-9a-f]{32}$/;
const REVIEW_DIGEST_PATTERN = /^[0-9A-F]{64}$/;
const REVIEW_EVENT_HASH_PATTERN = /^[0-9a-f]{64}$/;
const REVIEW_IDEMPOTENCY_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/;
const REVIEW_CATEGORIES = new Set<ReviewCategory>(['creative', 'rights', 'public_release']);
const REVIEW_DECISIONS = new Set<ReviewDecision>(['pending', 'approved', 'changes_required', 'not_applicable']);
const REVIEW_ACTION_TYPES = new Set<ReviewAction['type']>(['created', 'resolved', 'decision_set', 'revision_plan_created']);

export interface ReviewCreateInput extends ReviewIdentity {
  idempotencyKey: string;
  category: ReviewCategory;
  body: string;
  actor: string;
}

const canonicalReviewText = (value: string, label: string, minimum: number, maximum: number): string => {
  if (typeof value !== 'string' || value !== value.trim() || value.length < minimum || value.length > maximum) {
    throw new TypeError(`${label}が不正です。`);
  }
  return value;
};

const validateReviewIdempotencyKey = (value: string): string => {
  if (!REVIEW_IDEMPOTENCY_PATTERN.test(value)) throw new TypeError('idempotency keyが不正です。');
  return value;
};

export const buildReviewCreatePayload = (input: ReviewCreateInput) => {
  if (!REVIEW_ARTIFACT_PATTERN.test(input.artifactId)) throw new TypeError('artifact IDが不正です。');
  if (!REVIEW_REVISION_PATTERN.test(input.revisionId)) throw new TypeError('revision IDが不正です。');
  if (!REVIEW_RUN_PATTERN.test(input.runId)) throw new TypeError('Run IDが不正です。');
  if (!REVIEW_CUT_PATTERN.test(input.cutId)) throw new TypeError('cut IDが不正です。');
  if (!Number.isInteger(input.timecodeMs) || input.timecodeMs < 0 || input.timecodeMs > 86_400_000) throw new TypeError('timecodeが不正です。');
  if (!REVIEW_CATEGORIES.has(input.category)) throw new TypeError('レビュー区分が不正です。');
  return {
    schema_version: REVIEW_SCHEMA_VERSION,
    idempotency_key: validateReviewIdempotencyKey(input.idempotencyKey),
    artifact_id: input.artifactId,
    revision_id: input.revisionId,
    run_id: input.runId,
    cut_id: input.cutId,
    timecode_ms: input.timecodeMs,
    category: input.category,
    body: canonicalReviewText(input.body, '指摘内容', 1, 2_000),
    actor: canonicalReviewText(input.actor, '担当者', 1, 80),
  };
};

export const buildReviewResolvePayload = (idempotencyKey: string, actor: string, note: string) => ({
  schema_version: REVIEW_SCHEMA_VERSION,
  idempotency_key: validateReviewIdempotencyKey(idempotencyKey),
  actor: canonicalReviewText(actor, '担当者', 1, 80),
  note: canonicalReviewText(note, '解決メモ', 0, 1_000),
});

export const buildReviewDecisionPayload = (
  idempotencyKey: string,
  actor: string,
  decision: Exclude<ReviewDecision, 'pending'>,
  note: string,
) => {
  if (!REVIEW_DECISIONS.has(decision)) throw new TypeError('判定が不正です。');
  return {
    schema_version: REVIEW_SCHEMA_VERSION,
    idempotency_key: validateReviewIdempotencyKey(idempotencyKey),
    actor: canonicalReviewText(actor, '担当者', 1, 80),
    decision,
    note: canonicalReviewText(note, '判定メモ', 0, 1_000),
  };
};

export const buildReviewPlanPayload = (idempotencyKey: string, actor: string) => ({
  schema_version: REVIEW_SCHEMA_VERSION,
  idempotency_key: validateReviewIdempotencyKey(idempotencyKey),
  actor: canonicalReviewText(actor, '担当者', 1, 80),
});

const normalizeReviewIdentity = (value: unknown): ReviewIdentity => {
  const record = asRecord(value);
  return {
    artifactId: text(pick(record, ['artifact_id', 'artifactId'])),
    revisionId: text(pick(record, ['revision_id', 'revisionId'])),
    runId: text(pick(record, ['run_id', 'runId'])),
    cutId: text(pick(record, ['cut_id', 'cutId'])),
    timecodeMs: number(pick(record, ['timecode_ms', 'timecodeMs'])) ?? -1,
  };
};

const normalizeReviewPlan = (value: unknown): ReviewRevisionPlan | null => {
  if (value === null || value === undefined) return null;
  const record = asRecord(value);
  const execution = asRecord(pick(record, ['execution']));
  const request = asRecord(pick(execution, ['request']));
  return {
    id: text(pick(record, ['id'])),
    status: text(pick(record, ['status'])) as ReviewRevisionPlan['status'],
    renderStatus: text(pick(record, ['render_status', 'renderStatus'])) as ReviewRevisionPlan['renderStatus'],
    exactCutIdentity: normalizeReviewIdentity(pick(record, ['exact_cut_identity', 'exactCutIdentity'])),
    identityDigest: text(pick(record, ['identity_digest', 'identityDigest'])),
    affectedStages: stringList(pick(record, ['affected_stages', 'affectedStages'])),
    reusePolicy: text(pick(record, ['reuse_policy', 'reusePolicy'])) as ReviewRevisionPlan['reusePolicy'],
    execution: {
      adapter: text(pick(execution, ['adapter'])) as ReviewRevisionPlan['execution']['adapter'],
      connected: pick(execution, ['connected']) as false,
      status: text(pick(execution, ['status'])) as ReviewRevisionPlan['execution']['status'],
      jobId: pickIncludingNull(execution, ['job_id', 'jobId']) as null,
      endpointTemplate: text(pick(execution, ['endpoint_template', 'endpointTemplate'])),
      request: {
        schema_version: pick(request, ['schema_version']),
        revision_plan_id: pick(request, ['revision_plan_id']),
        production_id: pick(request, ['production_id']),
        review_id: pick(request, ['review_id']),
        revision_id: pick(request, ['revision_id']),
        source_run_id: pick(request, ['source_run_id']),
        source_artifact_id: pick(request, ['source_artifact_id']),
        cut_id: pick(request, ['cut_id']),
        timecode_ms: pick(request, ['timecode_ms']),
        identity_digest: pick(request, ['identity_digest']),
      },
    },
  };
};

const normalizeReviewAction = (value: unknown): ReviewAction => {
  const record = asRecord(value);
  return {
    id: text(pick(record, ['id'])),
    type: text(pick(record, ['type'])) as ReviewAction['type'],
    actor: text(pick(record, ['actor'])),
    decision: text(pick(record, ['decision'])) as ReviewDecision,
    note: text(pick(record, ['note'])),
    createdAt: text(pick(record, ['created_at', 'createdAt'])),
    eventId: number(pick(record, ['event_id', 'eventId'])) ?? 0,
    eventHash: text(pick(record, ['event_hash', 'eventHash'])),
    revisionPlan: normalizeReviewPlan(pickIncludingNull(record, ['revision_plan', 'revisionPlan'])),
  };
};

const normalizeReviewThread = (value: unknown): ReviewThread => {
  const record = asRecord(value);
  return {
    id: text(pick(record, ['id'])),
    status: text(pick(record, ['status'])) as ReviewThread['status'],
    category: text(pick(record, ['category'])) as ReviewCategory,
    decision: text(pick(record, ['decision'])) as ReviewDecision,
    body: text(pick(record, ['body'])),
    actor: text(pick(record, ['actor'])),
    createdAt: text(pick(record, ['created_at', 'createdAt'])),
    updatedAt: text(pick(record, ['updated_at', 'updatedAt'])),
    identity: normalizeReviewIdentity(pick(record, ['identity'])),
    actions: items(pick(record, ['actions']), ['items', 'actions']).map(normalizeReviewAction),
    revisionPlans: items(pick(record, ['revision_plans', 'revisionPlans']), ['items', 'plans']).map((item) => normalizeReviewPlan(item)).filter((item): item is ReviewRevisionPlan => item !== null),
  };
};

const emptyReviewGate = (): ReviewGate => ({ decision: 'pending', reviewCount: 0, openCount: 0, resolvedCount: 0 });

const normalizeReviewGate = (value: unknown): ReviewGate => {
  const record = asRecord(value);
  const rawDecision = text(pick(record, ['decision']));
  return {
    decision: ['approved', 'changes_required', 'not_applicable'].includes(rawDecision) ? rawDecision as ReviewGate['decision'] : 'pending',
    reviewCount: number(pick(record, ['review_count', 'reviewCount'])) ?? 0,
    openCount: number(pick(record, ['open_count', 'openCount'])) ?? 0,
    resolvedCount: number(pick(record, ['resolved_count', 'resolvedCount'])) ?? 0,
  };
};

const normalizeReviewGates = (value: unknown): ReviewGates => {
  const record = asRecord(value);
  return {
    creative: record.creative === undefined ? emptyReviewGate() : normalizeReviewGate(record.creative),
    rights: record.rights === undefined ? emptyReviewGate() : normalizeReviewGate(record.rights),
    public_release: record.public_release === undefined ? emptyReviewGate() : normalizeReviewGate(record.public_release),
  };
};

const validReviewIdentity = (identity: ReviewIdentity): boolean => (
  REVIEW_ARTIFACT_PATTERN.test(identity.artifactId)
  && REVIEW_REVISION_PATTERN.test(identity.revisionId)
  && REVIEW_RUN_PATTERN.test(identity.runId)
  && REVIEW_CUT_PATTERN.test(identity.cutId)
  && Number.isInteger(identity.timecodeMs)
  && identity.timecodeMs >= 0
  && identity.timecodeMs <= 86_400_000
);

const normalizeReviewMutation = (
  value: unknown,
  expectedProductionId: string,
  expectedReviewId?: string,
): ReviewMutationResponse => {
  const record = asRecord(value);
  const review = normalizeReviewThread(pick(record, ['review']));
  const action = normalizeReviewAction(pick(record, ['action']));
  const productionId = text(pick(record, ['production_id', 'productionId']));
  const deduplicated = pick(record, ['deduplicated']);
  const plan = action.revisionPlan;
  const planRequest = plan?.execution.request ?? {};
  if (
    record.schema_version !== REVIEW_SCHEMA_VERSION
    || productionId !== expectedProductionId
    || !REVIEW_ID_PATTERN.test(review.id)
    || (expectedReviewId !== undefined && review.id !== expectedReviewId)
    || !REVIEW_ACTION_PATTERN.test(action.id)
    || !REVIEW_ACTION_TYPES.has(action.type)
    || action.eventId < 1
    || !REVIEW_EVENT_HASH_PATTERN.test(action.eventHash)
    || !validReviewIdentity(review.identity)
    || !REVIEW_CATEGORIES.has(review.category)
    || !REVIEW_DECISIONS.has(review.decision)
    || !['open', 'resolved'].includes(review.status)
    || !review.body
    || !review.actor
    || (action.type === 'revision_plan_created') !== (plan !== null)
    || typeof deduplicated !== 'boolean'
    || (plan !== null && (
      !REVIEW_PLAN_PATTERN.test(plan.id)
      || plan.status !== 'planned_not_executed'
      || plan.renderStatus !== 'not_started'
      || plan.execution.connected !== false
      || plan.execution.status !== 'not_connected'
      || plan.execution.jobId !== null
      || plan.execution.adapter !== 'm4_cut_revision_job_v1'
      || plan.execution.endpointTemplate !== '/api/productions/{production_id}/cuts/{cut_id}/reruns'
      || !REVIEW_DIGEST_PATTERN.test(plan.identityDigest)
      || plan.reusePolicy !== 'reuse_all_other_exact_cut_artifacts'
      || plan.affectedStages.join('\0') !== ['video_generation', 'timeline', 'assembly', 'qc'].join('\0')
      || plan.exactCutIdentity.cutId !== review.identity.cutId
      || plan.exactCutIdentity.artifactId !== review.identity.artifactId
      || planRequest.production_id !== expectedProductionId
      || planRequest.review_id !== review.id
      || planRequest.cut_id !== review.identity.cutId
      || planRequest.identity_digest !== plan.identityDigest
    ))
  ) {
    throw new StudioApiError('レビュー応答のidentityが要求と一致しません。', 502, 'invalid_review_response');
  }
  return {
    productionId,
    review,
    action,
    gates: normalizeReviewGates(pick(record, ['gates'])),
    deduplicated,
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

/** Fetch failed before an HTTP response was received; safe for one idempotent retry. */
export class StudioApiResponseLossError extends Error {
  readonly responseLost = true;

  constructor() {
    super('Studio APIの応答を受信できませんでした。');
    this.name = 'StudioApiResponseLossError';
  }
}

export const isStudioApiResponseLoss = (error: unknown): error is StudioApiResponseLossError =>
  error instanceof StudioApiResponseLossError;

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

const request = async <T>(path: string, init?: RequestInit, expectedStatus?: number): Promise<T> => {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new StudioApiResponseLossError();
  }
  if (!response.ok) {
    const parsed = await parseError(response);
    throw new StudioApiError(parsed.message, response.status, parsed.code);
  }
  if (expectedStatus !== undefined && response.status !== expectedStatus) {
    throw new StudioApiError(`Studio APIの応答status ${response.status}は期待値${expectedStatus}と異なります。`, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
};

const post = <T>(path: string, body?: unknown, signal?: AbortSignal, expectedStatus?: number): Promise<T> =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body), signal }, expectedStatus);

const postWindowsCapture = async <T>(
  path: string,
  body: unknown,
  expectedStatus: number | undefined,
  timeoutMs: number,
): Promise<T> => {
  const boundedTimeoutMs = Number.isInteger(timeoutMs) && timeoutMs > 0
    ? Math.min(timeoutMs, WINDOWS_CAPTURE_REQUEST_TIMEOUT_MS)
    : WINDOWS_CAPTURE_REQUEST_TIMEOUT_MS;
  const controller = new AbortController();
  const timer = globalThis.setTimeout(() => controller.abort(), boundedTimeoutMs);
  try {
    return await post<T>(path, body, controller.signal, expectedStatus);
  } finally {
    globalThis.clearTimeout(timer);
  }
};

export const serializeLocalComfyUiPayload = (payload: LocalComfyUiPayload): string => {
  // JSON.stringify rounds numbers above Number.MAX_SAFE_INTEGER. The backend
  // accepts a Python integer, so preserve a validated 64-bit seed as a JSON
  // number literal when the browser form contains the upper half of the range.
  if (typeof payload.seed !== 'string') return JSON.stringify(payload);
  const rest = JSON.stringify({ workflow_preset: payload.workflow_preset, prompt: payload.prompt });
  return `${rest.slice(0, -1)},"seed":${payload.seed}}`;
};

export const MAX_VIDEO_IMPORT_FILES = 16;
export const MAX_VIDEO_IMPORT_BYTES = 2 * 1024 * 1024 * 1024;
export const PRODUCTION_ID_PATTERN = /^production_[0-9a-f]{32}$/;
export const PRODUCTION_LIBRARY_OPERATION_ID_PATTERN = /^production_library_op_[0-9a-f]{32}$/;
export const PRODUCTION_TITLE_MAX_LENGTH = 120;
const VIDEO_IMPORT_EXTENSIONS = new Set([
  '.avi', '.m4v', '.mkv', '.mov', '.mp4', '.webm',
]);

/** Build the closed production-creation request body. */
export const buildProductionCreatePayload = (productionId: unknown, title: unknown): ProductionCreatePayload => {
  const normalizedId = typeof productionId === 'string' ? productionId.trim() : '';
  const normalizedTitle = typeof title === 'string' ? title.trim() : '';
  if (!PRODUCTION_ID_PATTERN.test(normalizedId)) throw new TypeError('production_idの形式が正しくありません。');
  if (!normalizedTitle) throw new TypeError('タイトルを入力してください。');
  if (normalizedTitle.length > PRODUCTION_TITLE_MAX_LENGTH) throw new TypeError(`タイトルは${PRODUCTION_TITLE_MAX_LENGTH}文字以内にしてください。`);
  return {
    schema_version: 1,
    production_id: normalizedId,
    title: normalizedTitle,
  };
};

const productionLibraryOperationId = (value: unknown): string => {
  if (typeof value !== 'string' || !PRODUCTION_LIBRARY_OPERATION_ID_PATTERN.test(value)) {
    throw new TypeError('制作ライブラリ操作IDの形式が正しくありません。');
  }
  return value;
};

const productionLibraryTitle = (value: unknown, label: string): string => {
  const title = typeof value === 'string' ? value.trim() : '';
  if (!title || title.length > PRODUCTION_TITLE_MAX_LENGTH || /[\u0000-\u001f\u007f]/.test(title)) {
    throw new TypeError(`${label}は1〜${PRODUCTION_TITLE_MAX_LENGTH}文字で入力してください。`);
  }
  return title;
};

export const buildProductionRenamePayload = (
  operationId: unknown,
  expectedTitle: unknown,
  title: unknown,
) => {
  const expected = productionLibraryTitle(expectedTitle, '現在のタイトル');
  const next = productionLibraryTitle(title, '新しいタイトル');
  if (expected === next) throw new TypeError('新しいタイトルを入力してください。');
  return {
    schema_version: 1 as const,
    operation_id: productionLibraryOperationId(operationId),
    expected_title: expected,
    title: next,
  };
};

export const buildProductionArchivePayload = (
  operationId: unknown,
  expectedArchived: unknown,
  archived: unknown,
) => {
  if (typeof expectedArchived !== 'boolean' || typeof archived !== 'boolean' || expectedArchived === archived) {
    throw new TypeError('アーカイブ状態の変更指定が正しくありません。');
  }
  return {
    schema_version: 1 as const,
    operation_id: productionLibraryOperationId(operationId),
    expected_archived: expectedArchived,
    archived,
  };
};

export const buildProductionDuplicatePayload = (
  operationId: unknown,
  productionId: unknown,
  title: unknown,
  includeImports: unknown,
) => {
  const id = typeof productionId === 'string' ? productionId : '';
  if (!PRODUCTION_ID_PATTERN.test(id)) throw new TypeError('複製先production_idの形式が正しくありません。');
  if (typeof includeImports !== 'boolean') throw new TypeError('素材複製指定が正しくありません。');
  return {
    schema_version: 1 as const,
    operation_id: productionLibraryOperationId(operationId),
    production_id: id,
    title: productionLibraryTitle(title, '複製タイトル'),
    include_imports: includeImports,
  };
};

const normalizeProductionLibraryMutation = (
  value: unknown,
  expected: { operationId: string; action: 'rename' | 'archive' | 'duplicate'; productionId: string },
): ProductionLibraryMutationResponse => {
  const root = asRecord(value);
  const production = normalizeProduction(pick(root, ['production', 'item', 'data']), 0);
  const operationId = text(pick(root, ['operation_id', 'operationId']), '');
  const action = text(pick(root, ['action']), '') as ProductionLibraryMutationResponse['action'];
  const deduplicated = pick(root, ['deduplicated']);
  if (
    root.schema_version !== 1
    || operationId !== expected.operationId
    || action !== expected.action
    || production.id !== expected.productionId
    || typeof deduplicated !== 'boolean'
  ) {
    throw new StudioApiError(
      '制作ライブラリ応答identityが要求と一致しません。',
      502,
      'invalid_production_library_response',
    );
  }
  return {
    schemaVersion: 1,
    operationId,
    action,
    production,
    sourceProductionId: text(pick(root, ['source_production_id', 'sourceProductionId']), '') || undefined,
    includeImports: typeof root.include_imports === 'boolean' ? root.include_imports : undefined,
    importedArtifactCount: number(pick(root, ['imported_artifact_count', 'importedArtifactCount'])),
    deduplicated,
  };
};

/** The cancellation endpoint intentionally accepts no client-selected state. */
export const buildJobCancelPayload = (): { schema_version: 1 } => ({ schema_version: 1 });

export const JOB_CANCEL_RETIREMENT_POLL_MS = 2_000 as const;
export const JOB_CANCEL_RETIREMENT_MAX_RECHECKS = 15 as const;

type JobCancellationRecheck = () => Promise<JobCancellationResponse>;
type JobCancellationWait = (milliseconds: number) => Promise<void>;

const waitForMilliseconds: JobCancellationWait = (milliseconds) => new Promise((resolve) => {
  globalThis.setTimeout(resolve, milliseconds);
});

/**
 * Reconcile an accepted cancellation until the exact worker slot retires.
 *
 * A Job can already be durably interrupted while a non-cooperative callback
 * is still leaving its worker lane. Keep the low-frequency follow-up bounded;
 * each recheck uses the same idempotent exact-ID cancellation endpoint.
 */
export const reconcileJobWorkerRetirement = async (
  initial: JobCancellationResponse,
  recheck: JobCancellationRecheck,
  wait: JobCancellationWait = waitForMilliseconds,
): Promise<JobCancellationResponse> => {
  let current = initial;
  for (
    let attempt = 0;
    current.workerRetired !== true && attempt < JOB_CANCEL_RETIREMENT_MAX_RECHECKS;
    attempt += 1
  ) {
    await wait(JOB_CANCEL_RETIREMENT_POLL_MS);
    current = await recheck();
  }
  return current;
};

export interface VideoImportValidation {
  valid: boolean;
  errors: string[];
}

/** Client-side guard for the bounded raw-file import lane. */
export const validateVideoImportFiles = (
  files: readonly { name?: unknown; size?: unknown }[],
): VideoImportValidation => {
  const errors: string[] = [];
  if (files.length > MAX_VIDEO_IMPORT_FILES) {
    errors.push(`動画は一度に${MAX_VIDEO_IMPORT_FILES}個まで選択できます（選択数: ${files.length}）。`);
  }
  files.forEach((file, index) => {
    const size = typeof file.size === 'number' ? file.size : Number(file.size);
    if (!Number.isFinite(size) || size <= 0 || size > MAX_VIDEO_IMPORT_BYTES) {
      const name = typeof file.name === 'string' && file.name ? file.name : `ファイル${index + 1}`;
      errors.push(`${name} は0より大きく、1ファイルあたり2 GiB以下にしてください。`);
      return;
    }
    const name = typeof file.name === 'string' ? file.name.trim() : '';
    const extensionIndex = name.lastIndexOf('.');
    const extension = extensionIndex >= 0 ? name.slice(extensionIndex).toLowerCase() : '';
    if (!extension || !VIDEO_IMPORT_EXTENSIONS.has(extension)) {
      errors.push(`${name || `ファイル${index + 1}`} は対応する動画拡張子（mp4/webm/mov等）を指定してください。`);
    }
  });
  return { valid: errors.length === 0, errors };
};

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

  async productions(options: { includeArchived?: boolean; query?: string } = {}): Promise<ProductionSummary[]> {
    const parameters = new URLSearchParams();
    if (options.includeArchived) parameters.set('include_archived', 'true');
    const query = options.query?.trim();
    if (query) parameters.set('q', query);
    const suffix = parameters.size > 0 ? `?${parameters.toString()}` : '';
    const value = await request<unknown>(`/api/productions${suffix}`);
    return items(value, ['items', 'productions', 'data']).map(normalizeProduction);
  },

  async createProduction(productionId: string, title: string, signal?: AbortSignal): Promise<ProductionSummary> {
    const payload = buildProductionCreatePayload(productionId, title);
    const value = await post<unknown>('/api/productions', payload, signal, 201);
    const root = asRecord(value);
    const candidate = pick(root, ['production', 'item', 'data']) ?? value;
    const production = normalizeProduction(candidate, 0);
    if (
      root.schema_version !== 1
      || production.id !== payload.production_id
      || production.title !== payload.title
    ) {
      throw new StudioApiError(
        '制作作成の応答identityが要求と一致しません。',
        502,
        'invalid_production_create_response',
      );
    }
    return production;
  },

  async renameProduction(
    productionId: string,
    operationId: string,
    expectedTitle: string,
    title: string,
  ): Promise<ProductionLibraryMutationResponse> {
    const payload = buildProductionRenamePayload(operationId, expectedTitle, title);
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/library/rename`,
      payload,
      undefined,
      200,
    );
    const result = normalizeProductionLibraryMutation(value, { operationId, action: 'rename', productionId });
    if (result.production.title !== payload.title) {
      throw new StudioApiError('表示名変更の応答が要求と一致しません。', 502, 'invalid_production_library_response');
    }
    return result;
  },

  async archiveProduction(
    productionId: string,
    operationId: string,
    expectedArchived: boolean,
    archived: boolean,
  ): Promise<ProductionLibraryMutationResponse> {
    const payload = buildProductionArchivePayload(operationId, expectedArchived, archived);
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/library/archive`,
      payload,
      undefined,
      200,
    );
    const result = normalizeProductionLibraryMutation(value, { operationId, action: 'archive', productionId });
    if (result.production.archived !== payload.archived) {
      throw new StudioApiError('アーカイブ応答が要求と一致しません。', 502, 'invalid_production_library_response');
    }
    return result;
  },

  async duplicateProduction(
    sourceProductionId: string,
    operationId: string,
    productionId: string,
    title: string,
    includeImports: boolean,
  ): Promise<ProductionLibraryMutationResponse> {
    const payload = buildProductionDuplicatePayload(operationId, productionId, title, includeImports);
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(sourceProductionId)}/library/duplicate`,
      payload,
      undefined,
      201,
    );
    const result = normalizeProductionLibraryMutation(value, { operationId, action: 'duplicate', productionId });
    if (
      result.production.title !== payload.title
      || result.sourceProductionId !== sourceProductionId
      || result.includeImports !== payload.include_imports
    ) {
      throw new StudioApiError('制作複製の応答が要求と一致しません。', 502, 'invalid_production_library_response');
    }
    return result;
  },

  async importVideo(productionId: string, file: File, signal?: AbortSignal): Promise<ArtifactImportResponse> {
    const value = await request<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/artifacts/import-video`,
      {
        method: 'POST',
        body: file,
        headers: {
          'Content-Type': file.type || 'application/octet-stream',
          'X-Studio-Filename-Encoded': encodeURIComponent(file.name),
        },
        signal,
      },
      201,
    );
    const record = asRecord(value);
    const candidate = pick(record, ['artifact', 'item', 'data']);
    const artifactRecord = asRecord(candidate ?? value);
    const artifact = normalizeArtifact(artifactRecord, 0);
    const deduplicatedValue = pick(record, ['deduplicated', 'dedupe', 'is_deduplicated']);
    const rawArtifactId = text(pick(artifactRecord, ['id', 'artifact_id']), '');
    const rawProductionId = text(pick(artifactRecord, ['production_id', 'productionId']), '');
    const rawOrigin = text(pick(artifactRecord, ['origin']), '');
    const rawKind = text(pick(artifactRecord, ['kind', 'type']), '');
    const rawPath = text(pick(artifactRecord, ['rel_path', 'path']), '');
    const rawSha256 = text(pick(artifactRecord, ['sha256']), '');
    const rawBytes = pick(artifactRecord, ['bytes', 'size_bytes', 'size']);
    if (
      record.schema_version !== 1
      || candidate === undefined
      || !/^art_[0-9a-f]{32}$/.test(rawArtifactId)
      || rawProductionId !== productionId
      || rawOrigin !== 'output'
      || rawKind !== 'video'
      || !rawPath.startsWith(`outputs/productions/${productionId}/imports/`)
      || !/^[0-9A-F]{64}$/.test(rawSha256)
      || typeof rawBytes !== 'number'
      || !Number.isSafeInteger(rawBytes)
      || rawBytes <= 0
      || typeof deduplicatedValue !== 'boolean'
    ) {
      throw new StudioApiError(
        '動画取込の応答identityが要求と一致しません。',
        502,
        'invalid_video_import_response',
      );
    }
    return {
      artifact,
      deduplicated: deduplicatedValue,
      raw: record,
    };
  },

  async production(id: string, signal?: AbortSignal): Promise<ProductionDetail> {
    const value = await request<unknown>(`/api/productions/${encodeURIComponent(id)}`, { signal });
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
      providerTasks: normalizeProviderTasks(section('provider_tasks') ?? section('providerTasks')),
      announcementRecipes: items(section('announcement_recipes') ?? section('announcementRecipes'), ['items', 'recipes']).map(normalizeAnnouncementRecipeRecord),
      announcementRecipeVersions: items(section('announcement_recipe_versions') ?? section('announcementRecipeVersions'), ['items', 'recipes']).map(normalizeAnnouncementRecipeRecord),
      announcementExecutions: items(section('announcement_executions') ?? section('announcementExecutions'), ['items', 'executions']).map(normalizeAnnouncementExecutionRecord),
      reviews: items(section('reviews'), ['items', 'reviews']).map(normalizeReviewThread),
      reviewGates: normalizeReviewGates(section('review_gates') ?? section('reviewGates')),
      specification: asRecord(pick(root, ['specification', 'spec', 'production_spec'])),
    };
  },

  async reviews(productionId: string): Promise<{ reviews: ReviewThread[]; gates: ReviewGates }> {
    const value = await request<unknown>(`/api/productions/${encodeURIComponent(productionId)}/reviews`);
    const record = asRecord(value);
    if (record.schema_version !== REVIEW_SCHEMA_VERSION || text(pick(record, ['production_id', 'productionId'])) !== productionId) {
      throw new StudioApiError('レビュー一覧のidentityが要求と一致しません。', 502, 'invalid_review_response');
    }
    return {
      reviews: items(pick(record, ['reviews']), ['items', 'reviews']).map(normalizeReviewThread),
      gates: normalizeReviewGates(pick(record, ['gates'])),
    };
  },

  async createReview(productionId: string, input: ReviewCreateInput): Promise<ReviewMutationResponse> {
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/reviews`,
      buildReviewCreatePayload(input),
      undefined,
      201,
    );
    return normalizeReviewMutation(value, productionId);
  },

  async resolveReview(
    productionId: string,
    reviewId: string,
    idempotencyKey: string,
    actor: string,
    note: string,
  ): Promise<ReviewMutationResponse> {
    if (!REVIEW_ID_PATTERN.test(reviewId)) throw new TypeError('review IDが不正です。');
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/reviews/${encodeURIComponent(reviewId)}/resolve`,
      buildReviewResolvePayload(idempotencyKey, actor, note),
      undefined,
      201,
    );
    return normalizeReviewMutation(value, productionId, reviewId);
  },

  async setReviewDecision(
    productionId: string,
    reviewId: string,
    idempotencyKey: string,
    actor: string,
    decision: Exclude<ReviewDecision, 'pending'>,
    note: string,
  ): Promise<ReviewMutationResponse> {
    if (!REVIEW_ID_PATTERN.test(reviewId)) throw new TypeError('review IDが不正です。');
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/reviews/${encodeURIComponent(reviewId)}/decision`,
      buildReviewDecisionPayload(idempotencyKey, actor, decision, note),
      undefined,
      201,
    );
    return normalizeReviewMutation(value, productionId, reviewId);
  },

  async createReviewRevisionPlan(
    productionId: string,
    reviewId: string,
    idempotencyKey: string,
    actor: string,
  ): Promise<ReviewMutationResponse> {
    if (!REVIEW_ID_PATTERN.test(reviewId)) throw new TypeError('review IDが不正です。');
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/reviews/${encodeURIComponent(reviewId)}/revision-plan`,
      buildReviewPlanPayload(idempotencyKey, actor),
      undefined,
      201,
    );
    return normalizeReviewMutation(value, productionId, reviewId);
  },

  async jobs(signal?: AbortSignal): Promise<Job[]> {
    const value = await request<unknown>('/api/jobs', { signal });
    return items(value, ['items', 'jobs', 'data']).map(normalizeJob);
  },

  async job(jobId: string, signal?: AbortSignal): Promise<Job> {
    const value = await request<unknown>(`/api/jobs/${encodeURIComponent(jobId)}`, { signal });
    return normalizeJob(value);
  },

  async cancelJob(jobId: string): Promise<JobCancellationResponse> {
    const value = await post<unknown>(
      `/api/jobs/${encodeURIComponent(jobId)}/cancel`,
      buildJobCancelPayload(),
      undefined,
      202,
    );
    const record = asRecord(value);
    const cancellation = asRecord(pick(record, ['cancellation', 'cancel']));
    const candidate = pick(record, ['job', 'item', 'data']);
    const candidateRecord = asRecord(candidate);
    const jobRecord = Object.keys(candidateRecord).length > 0
      ? candidateRecord
      : (record.id !== undefined || record.job_id !== undefined ? record : undefined);
    const statusValue = pick(record, ['status', 'cancellation_status', 'cancellationStatus'])
      ?? pick(cancellation, ['status', 'state']);
    const cancelRequestedValue = pick(record, ['cancel_requested', 'cancelRequested'])
      ?? pick(cancellation, ['cancel_requested', 'cancelRequested']);
    const normalizedJob = jobRecord ? normalizeJob(jobRecord) : undefined;
    const workerRetiredValue = pick(record, ['worker_retired', 'workerRetired']);
    if (
      record.schema_version !== 1
      || normalizedJob?.id !== jobId
      || typeof cancelRequestedValue !== 'boolean'
      || typeof workerRetiredValue !== 'boolean'
    ) {
      throw new StudioApiError(
        'Job停止の応答identityが要求と一致しません。',
        502,
        'invalid_job_cancel_response',
      );
    }
    return {
      job: normalizedJob,
      status: text(statusValue ?? normalizedJob?.status, '') || undefined,
      cancelRequested: cancelRequestedValue,
      workerRetired: workerRetiredValue,
      raw: record,
    };
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

  async inspectWindowsCaptureCapability(): Promise<WindowsCaptureCapability> {
    const value = await post<unknown>('/api/capabilities/windows-capture/inspect', {});
    const record = asRecord(value);
    const helper = asRecord(pick(record, ['helper']));
    const ffmpeg = asRecord(pick(record, ['ffmpeg']));
    const display = asRecord(pick(record, ['display']));
    const rawStatus = text(pick(record, ['status']), 'blocked').toLowerCase();
    const capability: WindowsCaptureCapability = {
      schemaVersion: number(pick(record, ['schema_version'])) ?? 0,
      implementationVersion: text(pick(record, ['implementation_version'])),
      status: rawStatus === 'ready' ? 'ready' : 'blocked',
      captureExecutionEnabled: boolean(pick(record, ['capture_execution_enabled']), false),
      screenCaptureReady: boolean(pick(record, ['screen_capture_ready']), false),
      systemAudioLoopbackReady: boolean(pick(record, ['system_audio_loopback_ready']), false),
      explicitConfirmationRequired: boolean(pick(record, ['explicit_confirmation_required']), false),
      actualCapturePerformed: boolean(pick(record, ['actual_capture_performed']), false),
      reasons: list(pick(record, ['reasons'])).map((reason) => text(reason)).filter(Boolean),
      helper: {
        available: boolean(pick(helper, ['available']), false),
        doctorOk: boolean(pick(helper, ['doctor_ok']), false),
          endpointActive: boolean(pick(helper, ['endpoint_active']), false),
          loopbackInitialized: boolean(pick(helper, ['loopback_initialized']), false),
          recordingStarted: boolean(pick(helper, ['recording_started']), false),
          captureCommandAvailable: boolean(pick(helper, ['capture_command_available']), false),
          sha256: text(pick(helper, ['sha256'])) || undefined,
        },
        ffmpeg: {
          available: boolean(pick(ffmpeg, ['available']), false),
          gdigrabAvailable: boolean(pick(ffmpeg, ['gdigrab_available']), false),
          ffprobeAvailable: boolean(pick(ffmpeg, ['ffprobe_available']), false),
        },
        display: {
          target: text(pick(display, ['target']), 'primary_display') as 'primary_display',
          width: number(pick(display, ['width'] )) ?? null,
          height: number(pick(display, ['height'])) ?? null,
        },
        toolIdentityDigest: text(pick(record, ['tool_identity_digest'])) || undefined,
    };
    if (
      capability.schemaVersion !== 1
      || capability.implementationVersion !== 'windows-capture-capability-v2'
      || !['ready', 'blocked'].includes(rawStatus)
      || !capability.explicitConfirmationRequired
      || capability.actualCapturePerformed
      || capability.helper.recordingStarted
      || capability.captureExecutionEnabled !== (capability.status === 'ready')
      || (capability.status === 'ready' && !capability.screenCaptureReady)
      || (capability.status === 'ready' && !capability.systemAudioLoopbackReady)
      || (capability.status === 'ready' && !capability.helper.captureCommandAvailable)
      || (capability.status === 'ready' && !capability.ffmpeg.ffprobeAvailable)
      || capability.display.target !== 'primary_display'
      || (capability.status === 'ready'
        && (capability.display.width === null || capability.display.height === null))
    ) {
      throw new Error('Windows収録環境の安全契約を検証できませんでした。');
    }
    return capability;
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
    } else if (changes.executionProfile === 'local_comfyui') {
      body.execution_profile = 'local_comfyui';
      body.estimated_cost = { amount: 0, currency: 'JPY' };
    } else if (changes.executionProfile === 'local_playwright') {
      body.execution_profile = 'local_playwright';
      body.estimated_cost = { amount: 0, currency: 'JPY' };
    } else if (changes.executionProfile === 'local_windows_capture') {
      body.execution_profile = 'local_windows_capture';
      body.estimated_cost = { amount: 0, currency: 'JPY' };
    } else if (changes.executionProfile === 'elevenlabs_tts') {
      body.execution_profile = 'elevenlabs_tts';
    }
    return post(`/api/productions/${encodeURIComponent(productionId)}/runs`, body);
  },

  async executeLocalNarration(runId: string, body: LocalNarrationRequest): Promise<Job> {
    const value = await post<unknown>(`/api/runs/${encodeURIComponent(runId)}/execute-local-narration`, body);
    return normalizeJob(value);
  },

  async executeExternalNarration(runId: string, body: ExternalNarrationRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-external-narration`,
      buildExternalNarrationPayload(body),
    );
    return normalizeJob(value);
  },

  async executeLocalAssembly(runId: string, body: LocalAssemblyRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-local-assembly`,
      buildLocalAssemblyPayload(body),
    );
    return normalizeJob(value);
  },

  async executeLocalTimeline(runId: string, body: LocalTimelineRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-local-timeline`,
      buildLocalTimelinePayload(body.clips),
    );
    return normalizeJob(value);
  },

  async executeRemotionTimeline(runId: string, body: LocalRemotionTimelineRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-remotion-timeline`,
      buildRemotionTimelinePayload(body),
    );
    return normalizeJob(value);
  },

  async executeLocalVideoGeneration(runId: string, body: LocalComfyUiRequest): Promise<Job> {
    const payload = buildLocalComfyUiPayload(body);
    const value = await request<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-local-video-generation`,
      {
        method: 'POST',
        body: serializeLocalComfyUiPayload(payload),
      },
    );
    return normalizeJob(value);
  },

  async executeLocalScreenCapture(runId: string, body: LocalScreenCaptureRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-local-screen-capture`,
      buildLocalScreenCapturePayload(body),
    );
    return normalizeJob(value);
  },

  async issueWindowsCaptureConsent(
    runId: string,
    body: WindowsCaptureRequest,
    timeoutMs = WINDOWS_CAPTURE_REQUEST_TIMEOUT_MS,
  ): Promise<WindowsCaptureConsentIntent> {
    const value = await postWindowsCapture<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/windows-capture-consent-intents`,
      buildWindowsCapturePayload(body),
      201,
      timeoutMs,
    );
    return parseWindowsCaptureConsentIntent(value, runId);
  },

  async executeWindowsCapture(
    runId: string,
    body: WindowsCaptureRequest,
    consentToken: string,
    timeoutMs = WINDOWS_CAPTURE_REQUEST_TIMEOUT_MS,
  ): Promise<Job> {
    const value = await postWindowsCapture<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-windows-capture`,
      buildWindowsCaptureExecutionPayload(body, consentToken),
      undefined,
      timeoutMs,
    );
    return normalizeJob(value);
  },

  async cancelWindowsCapture(jobId: string): Promise<WindowsCaptureCancelResponse> {
    const value = await post<unknown>(
      `/api/jobs/${encodeURIComponent(jobId)}/cancel-windows-capture`,
      {},
    );
    const record = asRecord(value);
    const rawJob = pick(record, ['job']);
    return {
      job: rawJob === undefined ? undefined : normalizeJob(rawJob),
      cancelRequested: boolean(pick(record, ['cancel_requested', 'cancelRequested']), false),
      workerRetired: boolean(pick(record, ['worker_retired', 'workerRetired']), false),
      raw: record,
    };
  },

  async resumeProviderTask(providerTaskId: string): Promise<Job> {
    const value = await post<unknown>(
      `/api/provider-tasks/${encodeURIComponent(providerTaskId)}/resume`,
      {},
    );
    return normalizeJob(value);
  },

  async executeLocalPipeline(productionId: string, body: LocalPipelineRequest): Promise<Job> {
    const payload = buildLocalPipelinePayload(body);
    const value = await request<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/execute-local-pipeline`,
      {
        method: 'POST',
        body: serializeLocalPipelinePayload(payload),
      },
    );
    return normalizeJob(value);
  },

  async executeDetailedTestVideo(productionId: string, body: DetailedTestVideoRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/execute-detailed-test-video`,
      buildDetailedTestVideoPayload(body),
    );
    return normalizeJob(value);
  },

  async announcementRecipes(productionId: string, signal?: AbortSignal): Promise<{
    recipes: AnnouncementRecipeRecord[];
    recipeVersions: AnnouncementRecipeRecord[];
    executions: AnnouncementExecutionRecord[];
  }> {
    const value = await request<unknown>(`/api/productions/${encodeURIComponent(productionId)}/announcement-recipes`, { signal });
    const record = asRecord(value);
    return {
      recipes: items(pick(record, ['recipes']), ['items', 'recipes']).map(normalizeAnnouncementRecipeRecord),
      recipeVersions: items(pick(record, ['recipe_versions', 'recipeVersions']), ['items', 'recipes']).map(normalizeAnnouncementRecipeRecord),
      executions: items(pick(record, ['executions']), ['items', 'executions']).map(normalizeAnnouncementExecutionRecord),
    };
  },

  async saveAnnouncementRecipe(
    productionId: string,
    recipeId: string,
    expectedRevision: number,
    recipe: AnnouncementVideoRecipe,
    signal?: AbortSignal,
  ): Promise<AnnouncementRecipeRecord> {
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/announcement-recipes/${encodeURIComponent(recipeId)}/save`,
      buildAnnouncementSavePayload(expectedRevision, recipe),
      signal,
    );
    return normalizeAnnouncementRecipeRecord(value);
  },

  async duplicateAnnouncementRecipe(
    productionId: string,
    recipeId: string,
    sourceRevision: number,
    newRecipeId: string,
    name: string,
    signal?: AbortSignal,
  ): Promise<AnnouncementRecipeRecord> {
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/announcement-recipes/${encodeURIComponent(recipeId)}/duplicate`,
      buildAnnouncementDuplicatePayload(sourceRevision, newRecipeId, name),
      signal,
    );
    return normalizeAnnouncementRecipeRecord(value);
  },

  async executeAnnouncementRecipe(productionId: string, recipeId: string, revision: number, signal?: AbortSignal): Promise<Job> {
    const value = await post<unknown>(
      `/api/productions/${encodeURIComponent(productionId)}/announcement-recipes/${encodeURIComponent(recipeId)}/execute`,
      buildAnnouncementExecutePayload(revision),
      signal,
    );
    return normalizeJob(value);
  },

  async executeLocalQc(runId: string, body: LocalQcRequest): Promise<Job> {
    const value = await post<unknown>(
      `/api/runs/${encodeURIComponent(runId)}/execute-local-qc`,
      buildLocalQcPayload(body),
    );
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
