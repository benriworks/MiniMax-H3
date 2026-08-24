import type {
  Approval,
  Artifact,
  ArtifactKind,
  CostEntry,
  ExternalNarrationPayload,
  ExternalNarrationRequest,
  ExternalVoiceSettings,
  HealthStatus,
  Job,
  JobResult,
  LocalAssemblyCaptionStylePreset,
  LocalAssemblyRequest,
  LocalComfyUiRequest,
  LocalTimelineClip,
  LocalTimelineRequest,
  LocalQcRequest,
  LocalQcVariant,
  LocalQcVerdict,
  LocalNarrationRequest,
  ProductionDetail,
  ProductionRun,
  ProductionSummary,
  ProviderStatus,
  RerunChanges,
  RerunPlan,
  QcCheck,
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

export const DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET: LocalAssemblyCaptionStylePreset = 'studio_default_v1';
export const RECOMMENDED_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET: LocalAssemblyCaptionStylePreset = 'shorts_ja_large_v1';

export const isLocalAssemblyCaptionStylePreset = (
  value: unknown,
): value is LocalAssemblyCaptionStylePreset => (
  typeof value === 'string'
  && LOCAL_ASSEMBLY_CAPTION_STYLE_PRESETS.some((preset) => preset === value)
);

export const normalizeLocalAssemblyInput = (
  videoArtifactId: string,
  narrationAttemptId: string,
  includeCaptioned: boolean,
  captionStylePreset: unknown = DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET,
): NormalizedAssemblyInput => {
  const normalizedPreset = isLocalAssemblyCaptionStylePreset(captionStylePreset)
    ? captionStylePreset
    : DEFAULT_LOCAL_ASSEMBLY_CAPTION_STYLE_PRESET;
  const request: LocalAssemblyRequest = {
    videoArtifactId: videoArtifactId.trim(),
    narrationAttemptId: narrationAttemptId.trim(),
    includeCaptioned: Boolean(includeCaptioned),
    captionStylePreset: normalizedPreset,
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
  return { request, errors };
};

export interface LocalAssemblyPayload {
  video_artifact_id: string;
  narration_attempt_id: string;
  include_captioned: boolean;
  caption_style_preset: LocalAssemblyCaptionStylePreset;
}

/** Return the exact local assembly wire body after applying the same form validation. */
export const buildLocalAssemblyPayload = (value: unknown): LocalAssemblyPayload => {
  const record = asRecord(value);
  const normalized = normalizeLocalAssemblyInput(
    text(pick(record, ['videoArtifactId', 'video_artifact_id'])),
    text(pick(record, ['narrationAttemptId', 'narration_attempt_id'])),
    boolean(pick(record, ['includeCaptioned', 'include_captioned']), true),
    pick(record, ['captionStylePreset', 'caption_style_preset']),
  );
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  return {
    video_artifact_id: normalized.request.videoArtifactId,
    narration_attempt_id: normalized.request.narrationAttemptId,
    include_captioned: normalized.request.includeCaptioned,
    caption_style_preset: normalized.request.captionStylePreset,
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
  const stageAttemptId = text(
    field(['stage_attempt_id', 'stageAttemptId'])
      ?? pick(result, ['stage_attempt_id', 'stageAttemptId']),
    '',
  );
  const stageMatches = stage === 'timeline' || jobType === 'local_timeline';
  return Boolean(
    stageMatches
      && (!selection.runId || runId === selection.runId)
      && (!selection.stageAttemptId || stageAttemptId === selection.stageAttemptId),
  );
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
  return {
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
    provider: text(pick(directRecord, ['provider']) ?? pick(result, ['provider']), '') || undefined,
    providerTaskId: text(pick(directRecord, ['provider_task_id', 'providerTaskId']) ?? pick(result, ['provider_task_id', 'providerTaskId']), '') || undefined,
    ...comfyMetadata,
    characterCost: number(pick(record, ['character_cost', 'characterCost', 'billable_characters']) ?? pick(result, ['character_cost', 'characterCost', 'billable_characters'])),
    actualCostUsd: numberOrNull(externalActualCostValue(directRecord, result)),
    actualCost: number(pick(directRecord, ['actual_cost', 'actualCost']) ?? pick(result, ['actual_cost', 'actualCost'])),
    timingSource: text(pick(directRecord, ['timing_source', 'timingSource']) ?? pick(result, ['timing_source', 'timingSource']), '') || undefined,
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
  const resultValue = pick(record, ['result', 'job_result', 'output']) ?? pick(root, ['result', 'job_result', 'output']);
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

export const serializeLocalComfyUiPayload = (payload: LocalComfyUiPayload): string => {
  // JSON.stringify rounds numbers above Number.MAX_SAFE_INTEGER. The backend
  // accepts a Python integer, so preserve a validated 64-bit seed as a JSON
  // number literal when the browser form contains the upper half of the range.
  if (typeof payload.seed !== 'string') return JSON.stringify(payload);
  const rest = JSON.stringify({ workflow_preset: payload.workflow_preset, prompt: payload.prompt });
  return `${rest.slice(0, -1)},"seed":${payload.seed}}`;
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
    } else if (changes.executionProfile === 'local_comfyui') {
      body.execution_profile = 'local_comfyui';
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
