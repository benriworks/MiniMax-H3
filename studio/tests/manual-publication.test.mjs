import assert from 'node:assert/strict';
import test from 'node:test';
import {
  buildManualPublicationText,
  compareZipMetadata,
  manualPublicationFileName,
  manualPublicationVideos,
  normalizeManualPublicationMetadata,
  zipMetadataSnapshot,
  ZIP_METADATA_MESSAGES,
} from '../.test-dist/manualPublication.js';

const productionId = `production_${'1'.repeat(32)}`;
const source = {
  runId: `run_${'2'.repeat(32)}`,
  sourceJobId: `job_${'3'.repeat(32)}`,
  artifacts: {
    clean_master: `art_${'4'.repeat(32)}`,
    captioned_master: `art_${'5'.repeat(32)}`,
  },
};
const artifacts = [
  { id: source.artifacts.clean_master, name: 'master-clean.mp4', kind: 'video', mimeType: 'video/mp4',
    sha256: 'a'.repeat(64), sizeBytes: 123456, durationSeconds: 15, metadata: { width: 1080, height: 1920 }, raw: {} },
  { id: source.artifacts.captioned_master, name: 'master-captioned.mp4', kind: 'video', mimeType: 'video/mp4',
    sha256: 'b'.repeat(64), sizeBytes: 234567, durationSeconds: 15, metadata: {}, raw: {} },
];
const metadata = normalizeManualPublicationMetadata('新しい学びを、今日から。', '生成AIの使い方を紹介します。\n詳しくはプロフィールへ。', '生成AI、日本語\n学び');
const videos = manualPublicationVideos(source, artifacts);
const createdAt = '2026-09-05T03:04:05.000Z';
const textRequest = { productionId, source, metadata, videos, createdAt, zipComparison: 'not_created' };

test('日本語の現在入力と実在する動画情報をUTF-8で往復できる', () => {
  const text = buildManualPublicationText(textRequest);
  assert.equal(Buffer.from(text, 'utf8').toString('utf8'), text);
  assert.ok(text.includes(`【タイトル】\n${metadata.title}`));
  assert.ok(text.includes(`【説明文】\n${metadata.description}`));
  assert.ok(text.includes('生成AI, 日本語, 学び'));
  assert.ok(text.includes(`制作ID: ${productionId}`));
  assert.ok(text.includes(source.runId));
  assert.ok(text.includes(source.sourceJobId));
  assert.ok(text.includes(`SHA-256: ${'A'.repeat(64)}`));
  assert.ok(text.includes('長さ: 15秒'));
  assert.ok(text.includes('解像度: 1080 × 1920'));
  assert.ok(text.includes(`${createdAt} (UTC)`));
  assert.ok(text.includes('作成時点のフォーム入力'));
  assert.ok(text.endsWith('\n'));
});

test('任意タグは未入力のまま出力し架空のキーワードを足さない', () => {
  const blankTags = normalizeManualPublicationMetadata(metadata.title, metadata.description, '');
  assert.deepEqual(blankTags.tags, []);
  const text = buildManualPublicationText({ ...textRequest, metadata: blankTags });
  assert.ok(text.includes('【タグ】\n未入力'));
  assert.ok(text.includes('タグは納品ZIP内のpublication.jsonには含まれません。'));
});

test('説明文の改行を保ち、タグの区切りと重複だけを整理する', () => {
  assert.deepEqual(normalizeManualPublicationMetadata('  告知  ', '  一行目\r\n二行目  ', 'AI, AI、日本語\r\n動画'), {
    title: '告知', description: '一行目\n二行目', tags: ['AI', '日本語', '動画'],
  });
});

test('無効な型・制御文字・過大入力を投稿用テキストに入れない', () => {
  for (const bad of ['', undefined, 12, '改行\nタイトル', '改行\rタイトル', '不可\u202E文字', 'x'.repeat(101)]) {
    assert.throws(() => normalizeManualPublicationMetadata(bad, '説明', ''), TypeError);
  }
  for (const bad of ['', '不可\u0000文字', 'x'.repeat(5001)]) {
    assert.throws(() => normalizeManualPublicationMetadata('題', bad, ''), TypeError);
  }
  for (const bad of [null, 'x'.repeat(501), 'x'.repeat(101), '不可\u0000', Array.from({ length: 31 }, (_, index) => `タグ${index}`).join(',')]) {
    assert.throws(() => normalizeManualPublicationMetadata('題', '説明', bad), TypeError);
  }
});

test('動画リンクは任意URLを使わず登録IDから同一originのURLを作る', () => {
  const selected = manualPublicationVideos(source, artifacts.map((artifact) => ({ ...artifact, url: 'https://attacker.invalid/video', raw: { href: 'javascript:alert(1)' } })));
  assert.equal(selected.length, 2);
  assert.equal(selected[0].url, `/api/artifacts/${source.artifacts.clean_master}/file`);
  assert.equal(selected[1].url, `/api/artifacts/${source.artifacts.captioned_master}/file`);
});

test('別ファイル・重複登録・不正ID・hash不足は動画として提供しない', () => {
  assert.equal(manualPublicationVideos({ ...source, runId: '../../run' }, artifacts).length, 0);
  assert.equal(manualPublicationVideos(source, [...artifacts, artifacts[0]]).length, 1);
  for (const bad of [{ name: 'other.mp4' }, { kind: 'document' }, { sha256: '' }, { sizeBytes: 0 }, { mimeType: 'text/html' }]) {
    assert.equal(manualPublicationVideos(source, [{ ...artifacts[0], ...bad }, artifacts[1]]).length, 1);
  }
  assert.equal(manualPublicationVideos({ ...source, artifacts: { ...source.artifacts, captioned_master: source.artifacts.clean_master } }, artifacts).length, 0);
});

test('未記録の解像度や尺を推測してテキストへ追加しない', () => {
  const unknown = manualPublicationVideos(source, artifacts.map((artifact) => ({ ...artifact, durationSeconds: undefined, metadata: {} })));
  const text = buildManualPublicationText({ ...textRequest, videos: unknown });
  assert.equal(text.includes('解像度:'), false);
  assert.equal(text.includes('長さ:'), false);
});

test('安全なファイル名で日本語を残しパス・制御文字・Windows予約名を回避する', () => {
  const fileName = manualPublicationFileName('../CON:新作/動画\\テスト?*\u0000. ', createdAt);
  assert.ok(fileName.startsWith('投稿情報_'));
  assert.ok(fileName.includes('新作'));
  assert.ok(fileName.endsWith('_2026-09-05.txt'));
  assert.equal(/[<>:"/\\|?*\u0000-\u001F]/u.test(fileName), false);
  assert.ok(manualPublicationFileName('😀'.repeat(200), createdAt).length < 180);
  assert.throws(() => manualPublicationFileName('タイトル', 'not-a-date'), TypeError);
});

test('ZIP作成時のタイトル・説明文・動画元を変更すると差分扱いにする', () => {
  const jobId = `job_${'9'.repeat(32)}`;
  const snapshot = zipMetadataSnapshot(productionId, source, metadata);
  const snapshots = { [jobId]: snapshot };
  assert.equal(compareZipMetadata(snapshot, jobId, snapshots), 'matching');
  for (const patch of [{ title: '新タイトル' }, { description: '新しい説明' }, { sourceJobId: `job_${'a'.repeat(32)}` }, { cleanMasterId: `art_${'b'.repeat(32)}` }, { runId: `run_${'c'.repeat(32)}` }, { productionId: 'another-production' }]) {
    assert.equal(compareZipMetadata({ ...snapshot, ...patch }, jobId, snapshots), 'changed');
  }
  const tagOnlyChange = zipMetadataSnapshot(productionId, source, { ...metadata, tags: ['別のタグ'] });
  assert.equal(compareZipMetadata(tagOnlyChange, jobId, snapshots), 'matching');
  assert.ok(ZIP_METADATA_MESSAGES.matching.includes('タグは投稿情報テキストだけ'));
  assert.ok(ZIP_METADATA_MESSAGES.changed.includes('ZIPは自動更新されません'));
});

test('画面再訪でZIP作成時入力を失った場合に一致したと表示しない', () => {
  const snapshot = zipMetadataSnapshot(productionId, source, metadata);
  assert.equal(compareZipMetadata(snapshot, undefined, {}), 'not_created');
  assert.equal(compareZipMetadata(snapshot, `job_${'9'.repeat(32)}`, {}), 'unknown');
  const text = buildManualPublicationText({ ...textRequest, zipComparison: 'unknown' });
  assert.ok(text.includes('ZIP作成時の入力をこの画面では確認できません'));
  assert.ok(text.includes('再作成してください'));
});

test('出力直前にも動画ID・URL・日時を検証する', () => {
  assert.throws(() => buildManualPublicationText({ ...textRequest, videos: [videos[0]] }), TypeError);
  assert.throws(() => buildManualPublicationText({ ...textRequest, videos: [{ ...videos[0], url: 'https://attacker.invalid' }, videos[1]] }), TypeError);
  assert.throws(() => buildManualPublicationText({ ...textRequest, videos: [{ ...videos[0], label: '偽\nタイトル' }, videos[1]] }), TypeError);
  assert.throws(() => buildManualPublicationText({ ...textRequest, productionId: 'production\ninjected' }), TypeError);
  assert.throws(() => buildManualPublicationText({ ...textRequest, createdAt: 'invalid' }), TypeError);
});
