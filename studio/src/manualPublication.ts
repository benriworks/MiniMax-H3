import type { Artifact, DeliveryPackageSource } from './types';

const FORBIDDEN_TEXT = /[\u0000-\u0009\u000B-\u001F\u007F\u00A0\u200B-\u200F\u202A-\u202E\u2060\u2066-\u2069\uFEFF]/u;
const ARTIFACT_ID = /^art_[0-9a-f]{32}$/;
const RUN_ID = /^run_[0-9a-f]{32}$/;
const JOB_ID = /^job_[0-9a-f]{32}$/;
const SHA256 = /^[0-9a-f]{64}$/i;

export const MANUAL_PUBLICATION_TAGS_MAX_LENGTH = 500;

export interface ManualPublicationMetadata {
  title: string;
  description: string;
  tags: string[];
}

export interface ZipMetadataSnapshot {
  productionId: string;
  runId: string;
  sourceJobId: string;
  cleanMasterId: string;
  captionedMasterId: string;
  title: string;
  description: string;
}

export type ZipMetadataComparison = 'not_created' | 'unknown' | 'matching' | 'changed';

export const ZIP_METADATA_MESSAGES: Record<ZipMetadataComparison, string> = {
  not_created: '投稿情報は現在の入力内容です。納品ZIPはまだ作成されていません。',
  unknown: '投稿情報は現在の入力内容です。ZIP作成時の入力をこの画面では確認できません。同じ内容をZIPにも保存する場合は、納品ZIPを再作成してください。',
  matching: 'タイトル・説明文・選択動画は、この画面からZIP作成を依頼した時点と同じです。タグは投稿情報テキストだけに含まれます。',
  changed: '現在の入力または選択動画が、ZIP作成を依頼した時点と異なります。ZIPは自動更新されません。同じ内容を保存する場合は、納品ZIPを再作成してください。',
};

const normalizedText = (value: unknown, label: string, maximum: number, multiline: boolean): string => {
  if (typeof value !== 'string') throw new TypeError(`${label}を入力してください。`);
  const normalized = value.replace(/\r\n/g, '\n').trim();
  if (!normalized || normalized.length > maximum) throw new TypeError(`${label}は1〜${maximum}文字で入力してください。`);
  if (FORBIDDEN_TEXT.test(normalized) || (!multiline && normalized.includes('\n'))) {
    throw new TypeError(`${label}に使用できない文字が含まれています。`);
  }
  return normalized;
};

export const normalizeManualPublicationMetadata = (
  title: unknown,
  description: unknown,
  tagsInput: unknown,
): ManualPublicationMetadata => {
  const normalizedTitle = normalizedText(title, 'タイトル', 100, false);
  const normalizedDescription = normalizedText(description, '説明文', 5_000, true);
  if (typeof tagsInput !== 'string' || tagsInput.length > MANUAL_PUBLICATION_TAGS_MAX_LENGTH) {
    throw new TypeError(`タグは${MANUAL_PUBLICATION_TAGS_MAX_LENGTH}文字以内で入力してください。`);
  }
  const rawTags = tagsInput.replace(/\r\n/g, '\n');
  if (FORBIDDEN_TEXT.test(rawTags)) throw new TypeError('タグに使用できない文字が含まれています。');
  const tags = [...new Set(rawTags.split(/[,、\n]/u).map((tag) => tag.trim()).filter(Boolean))];
  if (tags.length > 30 || tags.some((tag) => tag.length > 100) || tags.join(', ').length > MANUAL_PUBLICATION_TAGS_MAX_LENGTH) {
    throw new TypeError('タグは30個以内、各100文字以内、区切りを含めて合計500文字以内で入力してください。');
  }
  return { title: normalizedTitle, description: normalizedDescription, tags };
};

export const zipMetadataSnapshot = (
  productionId: string,
  source: DeliveryPackageSource,
  metadata: Pick<ManualPublicationMetadata, 'title' | 'description'>,
): ZipMetadataSnapshot => ({
  productionId,
  runId: source.runId,
  sourceJobId: source.sourceJobId,
  cleanMasterId: source.artifacts.clean_master,
  captionedMasterId: source.artifacts.captioned_master,
  title: metadata.title.trim(),
  description: metadata.description.replace(/\r\n/g, '\n').trim(),
});

export const compareZipMetadata = (
  current: ZipMetadataSnapshot,
  completedJobId: string | undefined,
  snapshots: Readonly<Record<string, ZipMetadataSnapshot>>,
): ZipMetadataComparison => {
  if (!completedJobId) return 'not_created';
  const recorded = snapshots[completedJobId];
  if (!recorded) return 'unknown';
  const keys: Array<keyof ZipMetadataSnapshot> = [
    'productionId', 'runId', 'sourceJobId', 'cleanMasterId', 'captionedMasterId', 'title', 'description',
  ];
  return keys.every((key) => current[key] === recorded[key]) ? 'matching' : 'changed';
};

export interface ManualPublicationVideo {
  id: string;
  label: string;
  fileName: string;
  url: string;
  sha256: string;
  sizeBytes: number;
  durationSeconds?: number;
  width?: number;
  height?: number;
}

const positiveNumber = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined;

const positiveInteger = (value: unknown): number | undefined =>
  typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : undefined;

/** The source must first pass resolveDeliveryPackageSource. Never reuse an artifact-supplied URL. */
export const manualPublicationVideos = (
  source: DeliveryPackageSource,
  artifacts: readonly Artifact[],
): ManualPublicationVideo[] => {
  if (!RUN_ID.test(source.runId) || !JOB_ID.test(source.sourceJobId)) return [];
  const roles = [
    ['clean_master', '字幕なし', 'master-clean.mp4'],
    ['captioned_master', '字幕あり', 'master-captioned.mp4'],
  ] as const;
  const selectedIds = roles.map(([role]) => source.artifacts[role]);
  if (new Set(selectedIds).size !== roles.length) return [];
  return roles.flatMap(([role, label, fileName]) => {
    const id = source.artifacts[role];
    const matches = artifacts.filter((artifact) => artifact.id === id);
    if (!ARTIFACT_ID.test(id) || matches.length !== 1) return [];
    const artifact = matches[0];
    if (artifact.kind !== 'video' || artifact.name !== fileName
      || artifact.mimeType !== 'video/mp4' || !SHA256.test(artifact.sha256 ?? '')
      || positiveInteger(artifact.sizeBytes) === undefined) return [];
    const width = positiveInteger(artifact.metadata.width ?? artifact.raw.width);
    const height = positiveInteger(artifact.metadata.height ?? artifact.raw.height);
    return [{
      id, label, fileName, url: `/api/artifacts/${id}/file`,
      sha256: artifact.sha256!.toUpperCase(), sizeBytes: artifact.sizeBytes!,
      durationSeconds: positiveNumber(artifact.durationSeconds),
      ...(width && height ? { width, height } : {}),
    }];
  });
};

export const manualPublicationFileName = (title: string, createdAt: string): string => {
  const date = new Date(createdAt);
  if (!Number.isFinite(date.getTime())) throw new TypeError('作成日時が不正です。');
  const stem = Array.from(title.normalize('NFC')
    .replace(/[<>:"/\\|?*\u0000-\u001F\u007F]/gu, '_')
    .replace(/[\u200B-\u200F\u202A-\u202E\u2060\u2066-\u2069\uFEFF]/gu, '')
    .trim().replace(/[. ]+$/u, '')).slice(0, 60).join('') || '動画';
  return `投稿情報_${stem}_${date.toISOString().slice(0, 10)}.txt`;
};

export const buildManualPublicationText = ({
  productionId, source, metadata, videos, createdAt, zipComparison,
}: {
  productionId: string;
  source: DeliveryPackageSource;
  metadata: ManualPublicationMetadata;
  videos: readonly ManualPublicationVideo[];
  createdAt: string;
  zipComparison: ZipMetadataComparison;
}): string => {
  if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$/.test(productionId)
    || !RUN_ID.test(source.runId) || !JOB_ID.test(source.sourceJobId)) {
    throw new TypeError('制作元の情報を確認できません。');
  }
  const validated = normalizeManualPublicationMetadata(metadata.title, metadata.description, metadata.tags.join(', '));
  const date = new Date(createdAt);
  if (!Number.isFinite(date.getTime())) throw new TypeError('作成日時が不正です。');
  if (!(zipComparison in ZIP_METADATA_MESSAGES) || videos.length !== 2
    || videos.some((video, index) => !ARTIFACT_ID.test(video.id) || !SHA256.test(video.sha256)
      || video.url !== `/api/artifacts/${video.id}/file`
      || video.fileName !== (index === 0 ? 'master-clean.mp4' : 'master-captioned.mp4')
      || video.label !== (index === 0 ? '字幕なし' : '字幕あり')
      || positiveInteger(video.sizeBytes) === undefined
      || (video.durationSeconds !== undefined && positiveNumber(video.durationSeconds) === undefined)
      || (video.width !== undefined && positiveInteger(video.width) === undefined)
      || (video.height !== undefined && positiveInteger(video.height) === undefined))
    || videos[0].id !== source.artifacts.clean_master || videos[1].id !== source.artifacts.captioned_master) {
    throw new TypeError('投稿用動画を確認できません。');
  }
  const lines = [
    'YouTube 手動投稿用情報',
    'このテキストは作成時点のフォーム入力です。動画はYouTube Studioから手動でアップロードしてください。',
    `情報作成日時: ${date.toISOString()} (UTC)`, '',
    '【タイトル】', validated.title, '',
    '【説明文】', validated.description, '',
    '【タグ】', validated.tags.length ? validated.tags.join(', ') : '未入力', '',
    '【納品ZIPとの関係】', ZIP_METADATA_MESSAGES[zipComparison],
    'タグは納品ZIP内のpublication.jsonには含まれません。', '',
    '【制作記録】', `制作ID: ${productionId}`, `生成Run ID: ${source.runId}`,
    `元Job ID: ${source.sourceJobId}`, '', '【投稿する動画】',
  ];
  for (const video of videos) {
    lines.push(`${video.label}: ${video.fileName}`, `成果物ID: ${video.id}`, `SHA-256: ${video.sha256}`,
      `ファイルサイズ: ${video.sizeBytes} bytes`);
    if (video.durationSeconds !== undefined) lines.push(`長さ: ${video.durationSeconds}秒`);
    if (video.width !== undefined && video.height !== undefined) lines.push(`解像度: ${video.width} × ${video.height}`);
    lines.push('');
  }
  return `${lines.join('\n').trimEnd()}\n`;
};
