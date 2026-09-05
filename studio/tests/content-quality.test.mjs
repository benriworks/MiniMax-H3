import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = await readFile(join(studioRoot, '.test-dist', 'contentQuality.js'), 'utf8');
const quality = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const artifact = (metadata = {}, extras = {}) => ({ id: 'art_a', name: 'portrait_4k_h3.mp4', kind: 'video', metadata, raw: {}, ...extras });

test('content facts preserve unknown media properties and never infer them from filenames', () => {
  const facts = quality.contentMediaFacts(artifact());
  assert.equal(facts.width, undefined);
  assert.equal(facts.hasAudio, undefined);
  assert.equal(quality.canSharpenLowResolutionPortrait(facts), false);
  assert.deepEqual(quality.contentMediaAdvice(facts), []);
});

test('content facts reject malformed metadata and retain meaningful false audio flags', () => {
  const facts = quality.contentMediaFacts(artifact({
    width: '480', height: -864, fps: Infinity, duration_seconds: NaN, has_audio: false, video_codec: '<script>',
  }, { durationSeconds: 5.167 }));
  assert.equal(facts.width, undefined);
  assert.equal(facts.height, undefined);
  assert.equal(facts.fps, undefined);
  assert.equal(facts.videoCodec, undefined);
  assert.equal(facts.hasAudio, false);
  assert.equal(facts.durationSeconds, 5.167);
  assert.equal(quality.contentMediaFacts(artifact({ width: 480, height: 864, fps: 24, video_codec: 'h264', duration_seconds: 6 })).durationSeconds, 6);
});

test('portrait sharp option accepts low resolution dimensions but not landscape, HD or unknown media', () => {
  assert.equal(quality.canSharpenLowResolutionPortrait({ width: 480, height: 864 }), true);
  assert.equal(quality.canSharpenLowResolutionPortrait({ width: 64, height: 128 }), true);
  assert.equal(quality.canSharpenLowResolutionPortrait({ width: 400, height: 640 }), true);
  for (const facts of [
    {}, { width: 480 }, { width: 63, height: 126 }, { width: 1080, height: 1920 },
    { width: 1920, height: 1080 }, { width: 720, height: 720 }, { width: 480, height: 961 },
    { width: 401, height: 640 }, { width: NaN, height: 864 }, { width: 480.5, height: 864 },
  ]) assert.equal(quality.canSharpenLowResolutionPortrait(facts), false, JSON.stringify(facts));
});

test('landscape cover advice explains the remaining width instead of promising uncropped output', () => {
  const advice = quality.contentMediaAdvice({ width: 1920, height: 1080, hasAudio: true });
  assert.match(advice.find((item) => item.id === 'cover-horizontal-crop').message, /約32%/);
  assert.match(advice.find((item) => item.id === 'source-audio-replaced').message, /読み上げに置き換え/);
  assert.equal(quality.contentMediaAdvice({ width: 1080, height: 1920, hasAudio: false }).length, 0);
});

test('headline metrics account for ASCII half width and Unicode without changing input', () => {
  assert.equal(quality.headlineDisplayUnits('AI入門'), 3);
  assert.equal(quality.headlineDisplayUnits('ｶﾀｶﾅ'), 2);
  const metrics = quality.contentCopyMetrics('AI入門\nはじめよう', '短く、伝える。', 5);
  assert.equal(metrics.headlineLines, 2);
  assert.equal(metrics.spokenCharacterCount, 5);
  assert.equal(metrics.speechMinSeconds, 5 / 7);
  assert.equal(metrics.speechMaxSeconds, 5 / 4);
  assert.deepEqual(quality.contentCopyAdvice('AI入門\nはじめよう', '短く、伝える。', 5), []);
});

test('copy advice distinguishes line overflow, dense captions and likely speech overrun', () => {
  assert.equal(quality.contentCopyAdvice('一\n二\n三', '説明です。', 5)[0].id, 'headline-layout');
  assert.equal(quality.contentCopyAdvice('あ'.repeat(11), '説明です。', 5)[0].id, 'headline-layout');
  assert.equal(quality.contentCopyAdvice('あ'.repeat(10), '説明です。', 5)[0].id, 'headline-density');
  const dense = quality.contentCopyAdvice('あ'.repeat(16), 'あ'.repeat(30), 5);
  assert.equal(dense.some((item) => item.id === 'speech-density'), true);
  assert.equal(dense.some((item) => item.id === 'caption-density'), true);
  const long = quality.contentCopyAdvice('要点', 'あ'.repeat(60), 5);
  assert.equal(long.some((item) => item.id === 'speech-overrun'), true);
  assert.equal(long.some((item) => item.id === 'speech-density'), false);
});

test('missing duration does not invent a speech warning or a quality guarantee', () => {
  const metrics = quality.contentCopyMetrics('', '', NaN);
  assert.equal(metrics.usableSeconds, 0);
  assert.equal(metrics.speechMaxSeconds, 0);
  assert.deepEqual(quality.contentCopyAdvice('要点', 'あ'.repeat(60), NaN), []);
});

test('ASCII abbreviations and numbers trigger pronunciation review instead of invented speech timing', () => {
  for (const narration of ['Claude Codeの使い方を紹介します。', '1日で学ぶ', '９月に公開', 'A'.repeat(100)]) {
    const metrics = quality.contentCopyMetrics('要点', narration, 5);
    assert.equal(metrics.hasAmbiguousReading, true);
    assert.deepEqual(quality.contentCopyAdvice('要点', narration, 5).map((item) => item.id), ['speech-reading']);
  }
});

test('preview trim clamps to actual duration and rejects empty, inverted or non-finite ranges', () => {
  assert.deepEqual(quality.contentPreviewRange('1000', '5000', 4), { startSeconds: 1, endSeconds: 4, valid: true });
  assert.deepEqual(quality.contentPreviewRange('1000', '5000'), { startSeconds: 1, endSeconds: 5, valid: true });
  assert.deepEqual(quality.contentPreviewRange('-1000', '2000', 4), { startSeconds: 0, endSeconds: 2, valid: true });
  for (const [start, end, duration] of [['', '', 5], ['Infinity', 'NaN', 5], ['5000', '1000', 10], ['5000', '6000', 4]]) {
    assert.equal(quality.contentPreviewRange(start, end, duration).valid, false);
  }
});

test('native preview seeking stops at or beyond the trim end and returns early seeks to its start', () => {
  const range = quality.contentPreviewRange('1000', '3000', 10);
  assert.deepEqual(quality.contentPreviewPlaybackAction(1.5, range), { pause: false });
  assert.deepEqual(quality.contentPreviewPlaybackAction(0, range), { pause: false, seekSeconds: 1 });
  assert.deepEqual(quality.contentPreviewPlaybackAction(3, range), { pause: true });
  assert.deepEqual(quality.contentPreviewPlaybackAction(9, range), { pause: true, seekSeconds: 3 });
  assert.deepEqual(quality.contentPreviewPlaybackAction(NaN, range), { pause: true });
  assert.deepEqual(quality.contentPreviewPlaybackAction(0, quality.contentPreviewRange('', '')), { pause: true });
});
