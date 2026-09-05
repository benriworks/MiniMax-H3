import type { AnnouncementVideoRecipe, Artifact } from './types';

export const SIMPLE_CREATE_SCHEMA_VERSION = 1 as const;
export const SIMPLE_CREATE_STORAGE_KEY = 'minimax-h3-studio.simple-create.intent.v1' as const;
export const SIMPLE_CREATE_MAX_VIDEOS = 3 as const;
export const SIMPLE_CREATE_DEADLINE_MS = 20 * 60 * 1_000;

export type SimpleCreateTemplateId = 'announcement_v1' | 'event_v1' | 'recruitment_v1';

export interface SimpleCreateTemplate {
  id: SimpleCreateTemplateId;
  version: 1;
  label: string;
  description: string;
  hookHeadline: string;
  hookNarration: string;
  ctaHeadline: string;
  ctaNarration: string;
  messagePlaceholder: string;
}

export interface SimpleCreateIntent {
  schemaVersion: 1;
  productionId: string;
  recipeId: string;
  title: string;
  templateId: SimpleCreateTemplateId;
  message: string;
}

export const SIMPLE_CREATE_TEMPLATES: readonly SimpleCreateTemplate[] = [
  {
    id: 'announcement_v1',
    version: 1,
    label: '告知',
    description: '新商品や更新情報を短く伝える',
    hookHeadline: '新しいお知らせ',
    hookNarration: '新しいお知らせです。',
    ctaHeadline: '詳しくは\nプロフィールへ',
    ctaNarration: '詳しくはプロフィールをご覧ください。',
    messagePlaceholder: '例：生成AI入門講座を\n公開しました',
  },
  {
    id: 'event_v1',
    version: 1,
    label: 'イベント案内',
    description: '開催日や参加方法をわかりやすく案内する',
    hookHeadline: 'イベント開催',
    hookNarration: 'イベント開催のお知らせです。',
    ctaHeadline: '参加方法は\n詳細ページへ',
    ctaNarration: '参加方法は詳細ページをご確認ください。',
    messagePlaceholder: '例：9月15日\nオンライン開催',
  },
  {
    id: 'recruitment_v1',
    version: 1,
    label: '採用・募集',
    description: '募集内容と応募先を端的に伝える',
    hookHeadline: '新しい仲間を\n募集します',
    hookNarration: '新しい仲間を募集します。',
    ctaHeadline: 'ご応募は\nプロフィールへ',
    ctaNarration: 'ご応募はプロフィールからお願いします。',
    messagePlaceholder: '例：広報メンバー募集中',
  },
] as const;

const PRODUCTION_ID = /^production_[0-9a-f]{32}$/;
const RECIPE_ID = /^announcement_[0-9a-f]{32}$/;
const DEFAULT_SCENE_END_MS = [5_167, 5_167, 5_166] as const;
const ROLE_ORDER = ['hook', 'message', 'cta'] as const;

export const getSimpleCreateTemplate = (templateId: SimpleCreateTemplateId): SimpleCreateTemplate => {
  const template = SIMPLE_CREATE_TEMPLATES.find((item) => item.id === templateId);
  if (!template) throw new TypeError('かんたん制作テンプレートが不正です。');
  return template;
};

const displayUnits = (value: string): number => [...value].reduce(
  (total, character) => total + (/^[\x20-\x7e\uff61-\uff9f]$/.test(character) ? 0.5 : 1),
  0,
);

export const validateSimpleCreateFields = (
  title: string,
  templateId: SimpleCreateTemplateId,
  message: string,
): string[] => {
  const errors: string[] = [];
  const normalizedTitle = title.trim();
  const normalizedMessage = message.trim();
  if (!normalizedTitle) errors.push('制作タイトルを入力してください。');
  if (normalizedTitle.length > 120) errors.push('制作タイトルは120文字以内にしてください。');
  try {
    getSimpleCreateTemplate(templateId);
  } catch {
    errors.push('テンプレートを選択してください。');
  }
  if (!normalizedMessage) errors.push('いちばん伝えたい文言を入力してください。');
  if (normalizedMessage.length > 80) errors.push('文言は80文字以内にしてください。');
  const lines = normalizedMessage.split(/\r?\n/);
  if (lines.length > 2) errors.push('文言は2行以内にしてください。');
  if (lines.some((line) => displayUnits(line) > 10)) {
    errors.push('文言は1行あたり全角10文字相当（半角20文字）以内にしてください。');
  }
  if (normalizedMessage && lines.some((line) => !line.trim())) errors.push('文言に空行を入れないでください。');
  return errors;
};

export const createSimpleCreateId = (
  prefix: 'production' | 'announcement',
  randomBytes: (length: number) => Uint8Array,
): string => {
  const bytes = randomBytes(16);
  if (!(bytes instanceof Uint8Array) || bytes.length !== 16) {
    throw new TypeError('安全な制作IDを生成できません。');
  }
  return `${prefix}_${[...bytes].map((value) => value.toString(16).padStart(2, '0')).join('')}`;
};

export const createSimpleCreateIntent = (
  input: Pick<SimpleCreateIntent, 'title' | 'templateId' | 'message'>,
  randomBytes: (length: number) => Uint8Array,
): SimpleCreateIntent => {
  const title = input.title.trim();
  const message = input.message.trim();
  const errors = validateSimpleCreateFields(title, input.templateId, message);
  if (errors.length > 0) throw new TypeError(errors[0]);
  return {
    schemaVersion: SIMPLE_CREATE_SCHEMA_VERSION,
    productionId: createSimpleCreateId('production', randomBytes),
    recipeId: createSimpleCreateId('announcement', randomBytes),
    title,
    templateId: input.templateId,
    message,
  };
};

export const parseSimpleCreateIntent = (value: unknown): SimpleCreateIntent => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new TypeError('かんたん制作の保留情報が壊れています。');
  }
  const record = value as Record<string, unknown>;
  if (
    Object.keys(record).sort().join('|') !== 'message|productionId|recipeId|schemaVersion|templateId|title'
    || record.schemaVersion !== SIMPLE_CREATE_SCHEMA_VERSION
    || typeof record.productionId !== 'string'
    || !PRODUCTION_ID.test(record.productionId)
    || typeof record.recipeId !== 'string'
    || !RECIPE_ID.test(record.recipeId)
    || typeof record.title !== 'string'
    || typeof record.message !== 'string'
    || typeof record.templateId !== 'string'
    || !SIMPLE_CREATE_TEMPLATES.some((item) => item.id === record.templateId)
  ) {
    throw new TypeError('かんたん制作の保留情報が壊れています。');
  }
  const intent = {
    schemaVersion: SIMPLE_CREATE_SCHEMA_VERSION,
    productionId: record.productionId,
    recipeId: record.recipeId,
    title: record.title,
    templateId: record.templateId as SimpleCreateTemplateId,
    message: record.message,
  };
  if (validateSimpleCreateFields(intent.title, intent.templateId, intent.message).length > 0) {
    throw new TypeError('かんたん制作の保留情報が壊れています。');
  }
  return intent;
};

const sceneEndMs = (artifact: Artifact, sceneIndex: number): number => {
  const target = DEFAULT_SCENE_END_MS[sceneIndex] ?? 5_000;
  if (artifact.durationSeconds === undefined) return target;
  return Math.min(target, Math.max(0, Math.floor(artifact.durationSeconds * 1_000)));
};

const narrationForMessage = (message: string): string => {
  const normalized = message.replace(/\r?\n/g, ' ').replace(/\s+/g, ' ').trim();
  return /[。！？!?]$/.test(normalized) ? normalized : `${normalized}。`;
};

/** Display and compilation share the exact words; this is not an audio timing prediction. */
export const simpleCreateStoryboard = (templateId: SimpleCreateTemplateId, message: string) => {
  const template = getSimpleCreateTemplate(templateId);
  const headlines = [template.hookHeadline, message.trim(), template.ctaHeadline];
  const narrations = [template.hookNarration, message.trim() ? narrationForMessage(message) : '', template.ctaNarration];
  return ROLE_ORDER.map((role, index) => ({ role, headline: headlines[index], narration: narrations[index] }));
};

/** Compile the five-decision form to the existing, versioned Announcement v1 contract. */
export const buildSimpleCreateRecipe = (
  intent: SimpleCreateIntent,
  artifacts: readonly Artifact[],
): AnnouncementVideoRecipe => {
  const normalized = parseSimpleCreateIntent(intent);
  if (artifacts.length < 1 || artifacts.length > SIMPLE_CREATE_MAX_VIDEOS) {
    throw new TypeError('動画素材は1〜3件選択してください。');
  }
  if (artifacts.some((artifact) => artifact.kind !== 'video' || !/^art_[0-9a-f]{32}$/.test(artifact.id))) {
    throw new TypeError('動画artifactのidentityが不正です。');
  }
  const indexes = artifacts.length === 1 ? [0, 0, 0] : artifacts.length === 2 ? [0, 1, 1] : [0, 1, 2];
  const storyboard = simpleCreateStoryboard(normalized.templateId, normalized.message);
  return {
    schemaVersion: 1,
    name: normalized.title,
    templatePreset: 'shorts_ja_15s_v1',
    scenes: storyboard.map((scene, index) => {
      const artifact = artifacts[indexes[index]];
      return {
        role: scene.role,
        videoArtifactId: artifact.id,
        startMs: 0,
        endMs: sceneEndMs(artifact, index),
        volumePercent: 0,
        visualPreset: 'preserve_v1',
        headline: scene.headline,
        narration: scene.narration,
      };
    }),
    rate: 0,
    pronunciations: [],
    includeCaptioned: true,
    captionStylePreset: 'shorts_ja_large_v1',
    audioMixPreset: 'narration_only_v1',
    variant: 'captioned',
  };
};

export const simpleCreateRecipesMatch = (
  expected: AnnouncementVideoRecipe,
  actual: AnnouncementVideoRecipe,
): boolean => JSON.stringify(expected) === JSON.stringify(actual);
