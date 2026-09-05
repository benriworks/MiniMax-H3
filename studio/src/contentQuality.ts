import type { Artifact } from './types';

export interface ContentMediaFacts {
  width?: number;
  height?: number;
  durationSeconds?: number;
  fps?: number;
  hasAudio?: boolean;
  videoCodec?: string;
}

export interface ContentAdvice {
  id: string;
  message: string;
}

const positiveNumber = (value: unknown): number | undefined => (
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined
);

const dimension = (value: unknown): number | undefined => {
  const number = positiveNumber(value);
  return number !== undefined && Number.isInteger(number) ? number : undefined;
};

/** Unknown or malformed metadata stays unknown; a filename is never media evidence. */
export const contentMediaFacts = (artifact?: Artifact): ContentMediaFacts => ({
  width: dimension(artifact?.metadata.width),
  height: dimension(artifact?.metadata.height),
  durationSeconds: positiveNumber(artifact?.metadata.duration_seconds) ?? positiveNumber(artifact?.durationSeconds),
  fps: positiveNumber(artifact?.metadata.fps),
  hasAudio: typeof artifact?.metadata.has_audio === 'boolean' ? artifact.metadata.has_audio : undefined,
  videoCodec: typeof artifact?.metadata.video_codec === 'string' && /^[a-zA-Z0-9._-]{1,32}$/.test(artifact.metadata.video_codec)
    ? artifact.metadata.video_codec : undefined,
});

/** Mirrors the fixed preset's dimensions for UI guidance; the worker revalidates the actual media. */
export const canSharpenLowResolutionPortrait = (facts: ContentMediaFacts): boolean => {
  const { width, height } = facts;
  if (width === undefined || height === undefined || !Number.isInteger(width) || !Number.isInteger(height)) return false;
  if (width < 64 || height < 64 || width >= 1080 || height >= 1920) return false;
  const ratio = width / height;
  if (ratio < 0.5 || ratio > 0.625) return false;
  const scale = Math.max(1080 / width, 1920 / height);
  return Math.ceil(width * scale) * Math.ceil(height * scale) <= 3_000_000;
};

export const headlineDisplayUnits = (text: string): number => Array.from(text).reduce(
  (total, character) => total + (/^[\x20-\x7e\uff61-\uff9f]$/.test(character) ? 0.5 : 1), 0,
);

export const contentCopyMetrics = (headline: string, narration: string, durationSeconds: number) => {
  const lines = headline.replace(/\r\n?/g, '\n').split('\n');
  const spokenCharacterCount = Array.from(narration.replace(/[\s。、，,.！？!?「」『』（）()：:；;…・]/g, '')).length;
  const usableSeconds = Number.isFinite(durationSeconds) && durationSeconds > 0 ? durationSeconds : 0;
  return {
    headlineCharacters: Array.from(headline.replace(/\s/g, '')).length,
    headlineLines: lines.length,
    longestHeadlineUnits: Math.max(0, ...lines.map(headlineDisplayUnits)),
    spokenCharacterCount,
    hasAmbiguousReading: /[A-Za-z0-9０-９]/.test(narration),
    // A deliberately broad Japanese text-length guide, not timing or voice analysis.
    speechMinSeconds: spokenCharacterCount / 7,
    speechMaxSeconds: spokenCharacterCount / 4,
    usableSeconds,
  };
};

export const contentCopyAdvice = (headline: string, narration: string, durationSeconds: number): ContentAdvice[] => {
  const metrics = contentCopyMetrics(headline, narration, durationSeconds);
  const advice: ContentAdvice[] = [];
  if (headline.trim() && (metrics.headlineLines > 2 || metrics.longestHeadlineUnits > 10)) {
    advice.push({ id: 'headline-layout', message: '見出しは2行まで、1行は全角10文字相当（半角20文字）まで。要点を1つに絞り、区切りのよい位置で改行してください。' });
  } else if (metrics.longestHeadlineUnits > 8) {
    advice.push({ id: 'headline-density', message: '見出しが長めです。2行に分けるか、説明を読み上げ側へ移すと、スマートフォンで追いやすくなります。' });
  }
  if (metrics.hasAmbiguousReading) {
    advice.push({ id: 'speech-reading', message: '英数字や略語は読み方で長さが大きく変わります。音声を生成して、発音と秒数を確認してください。必要なら読み上げ文を読み仮名にしてください。' });
  } else if (metrics.usableSeconds > 0 && metrics.speechMinSeconds > metrics.usableSeconds) {
    advice.push({ id: 'speech-overrun', message: '読み上げは、この場面の秒数に収まりにくい文字量です。1文を短くするか、詳細設定で使う秒数を増やしてください。' });
  } else if (metrics.usableSeconds > 0 && metrics.speechMaxSeconds > metrics.usableSeconds) {
    advice.push({ id: 'speech-density', message: 'ゆっくり話すと場面をまたぐ可能性があります。言葉を少し減らし、生成後に字幕と音声のテンポを確認してください。' });
  }
  if (!metrics.hasAmbiguousReading && metrics.spokenCharacterCount > 0 && metrics.longestHeadlineUnits > 8 && metrics.usableSeconds > 0
    && metrics.spokenCharacterCount / metrics.usableSeconds > 4) {
    advice.push({ id: 'caption-density', message: '見出しと読み上げ字幕の両方が多めです。見出しは短い結論にして、同時に読む量を減らすと伝わりやすくなります。' });
  }
  return advice;
};

export const contentMediaAdvice = (facts: ContentMediaFacts): ContentAdvice[] => {
  const advice: ContentAdvice[] = [];
  if (facts.width !== undefined && facts.height !== undefined) {
    const ratio = facts.width / facts.height;
    if (ratio > 0.625) {
      const retainedWidthPercent = Math.round(Math.min(1, (9 / 16) / ratio) * 100);
      advice.push({ id: 'cover-horizontal-crop', message: `縦画面いっぱいに中央で切り取るため、横幅の約${retainedWidthPercent}%が残ります。顔や画面の文字が左右で切れていないか確認してください。` });
    } else if (ratio < 0.5) {
      advice.push({ id: 'cover-vertical-crop', message: '縦に細い素材のため、上下が切り取られます。頭や画面の案内が枠内に収まるか確認してください。' });
    }
    if (facts.width < 1080 || facts.height < 1920) {
      advice.push({ id: 'source-resolution', message: '完成時は1080×1920へ拡大します。細部の解像感は元素材に左右されます。読ませたい文字は見出し・字幕で追加してください。' });
    }
  }
  if (facts.hasAudio === true) {
    advice.push({ id: 'source-audio-replaced', message: 'この素材には音声があります。かんたん作成では素材音を使わず、入力した文章の読み上げに置き換えます。口の動きとの一致は完成動画で確認してください。' });
  }
  return advice;
};

/** Keep preview seeking finite, including legacy drafts with missing or invalid trim values. */
export const contentPreviewRange = (startMs: string, endMs: string, sourceDurationSeconds?: number) => {
  const start = startMs.trim() ? Number(startMs) / 1000 : 0;
  const end = endMs.trim() ? Number(endMs) / 1000 : 0;
  const duration = positiveNumber(sourceDurationSeconds);
  const startSeconds = Math.min(Math.max(0, Number.isFinite(start) ? start : 0), duration ?? Infinity);
  const endSeconds = Math.min(Number.isFinite(end) ? Math.max(0, end) : 0, duration ?? Infinity);
  return { startSeconds, endSeconds, valid: endSeconds > startSeconds };
};

/** Native play/seek controls must not allow continuing beyond the selected interval. */
export const contentPreviewPlaybackAction = (
  currentSeconds: number,
  range: ReturnType<typeof contentPreviewRange>,
): { pause: boolean; seekSeconds?: number } => {
  if (!range.valid || !Number.isFinite(currentSeconds)) return { pause: true };
  if (currentSeconds >= range.endSeconds) {
    return { pause: true, ...(currentSeconds > range.endSeconds ? { seekSeconds: range.endSeconds } : {}) };
  }
  if (currentSeconds < range.startSeconds) return { pause: false, seekSeconds: range.startSeconds };
  return { pause: false };
};
