import assert from 'node:assert/strict';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const studioRoot = join(dirname(fileURLToPath(import.meta.url)), '..');
const testDist = join(studioRoot, '.test-dist');
const statusUrl = pathToFileURL(join(testDist, 'status.js')).href;
const apiSource = await readFile(join(testDist, 'api.js'), 'utf8');
const apiModule = apiSource.replaceAll("from './status'", `from '${statusUrl}'`);
const api = await import(`data:text/javascript;base64,${Buffer.from(apiModule).toString('base64')}`);

test('timeline payload is exact and accepts normalized camelCase drafts', () => {
  const payload = api.buildLocalTimelinePayload({
    clips: [
      { videoArtifactId: ' video-a ', startMs: 0, endMs: 5000, label: 'ignored' },
      { video_artifact_id: 'video-b', start_ms: 125, end_ms: 2125, unexpected: true },
    ],
    fps: 60,
    transition: 'fade',
  });
  assert.deepEqual(payload, {
    clips: [
      { video_artifact_id: 'video-a', start_ms: 0, end_ms: 5000 },
      { video_artifact_id: 'video-b', start_ms: 125, end_ms: 2125 },
    ],
  });
  assert.deepEqual(Object.keys(payload), ['clips']);
});

test('timeline normalization enforces clip count, integer ranges, minimum clip length, and total duration', () => {
  const tooShort = api.normalizeLocalTimelineInput([{ videoArtifactId: 'a', startMs: 0, endMs: 49 }]);
  assert.ok(tooShort.errors.some((error) => error.includes('50ms以上')));

  const fractional = api.normalizeLocalTimelineInput([{ videoArtifactId: 'a', startMs: 0.5, endMs: 100 }]);
  assert.ok(fractional.errors.some((error) => error.includes('整数ミリ秒')));

  const invalidText = api.normalizeLocalTimelineInput([{ videoArtifactId: 'a', startMs: 'abc', endMs: 100 }]);
  assert.ok(invalidText.errors.some((error) => error.includes('開始時刻')));
  assert.throws(() => api.buildLocalTimelinePayload([{ videoArtifactId: 'a', startMs: '', endMs: 100 }]), /開始時刻/);

  const reversed = api.normalizeLocalTimelineInput([{ videoArtifactId: 'a', startMs: 500, endMs: 100 }]);
  assert.ok(reversed.errors.some((error) => error.includes('50ms以上')));

  const tooLong = api.normalizeLocalTimelineInput([{ videoArtifactId: 'a', startMs: 0, endMs: 1_800_001 }]);
  assert.ok(tooLong.errors.some((error) => error.includes('30分以内')));

  const absoluteEndTooLarge = api.normalizeLocalTimelineInput([{ videoArtifactId: 'a', startMs: 1_800_000, endMs: 1_800_050 }]);
  assert.ok(absoluteEndTooLarge.errors.some((error) => error.includes('終了時刻')));

  const tooMany = api.normalizeLocalTimelineInput(Array.from({ length: 33 }, (_, index) => ({
    videoArtifactId: `video-${index}`,
    startMs: 0,
    endMs: 50,
  })));
  assert.ok(tooMany.errors.some((error) => error.includes('32件以内')));
});

test('timeline normalization reports total duration and rejects an empty list', () => {
  const normalized = api.normalizeLocalTimelineInput([
    { videoArtifactId: 'a', startMs: 0, endMs: 500 },
    { videoArtifactId: 'b', startMs: 1000, endMs: 2500 },
  ]);
  assert.equal(normalized.totalDurationMs, 2000);
  assert.deepEqual(normalized.errors, []);

  const empty = api.normalizeLocalTimelineInput([]);
  assert.ok(empty.errors.some((error) => error.includes('1件以上')));
  assert.throws(() => api.buildLocalTimelinePayload([]), /1件以上/);
});

test('timeline reorder and duplicate helpers are immutable and bounded', () => {
  const clips = ['a', 'b', 'c'];
  assert.deepEqual(api.reorderTimelineClips(clips, 2, 0), ['c', 'a', 'b']);
  assert.deepEqual(api.moveTimelineClip(clips, 0, 1), ['b', 'a', 'c']);
  assert.deepEqual(api.reorderTimelineClips(clips, -1, 1), clips);
  assert.deepEqual(api.duplicateTimelineClip(clips, 1), ['a', 'b', 'b', 'c']);
  assert.deepEqual(api.duplicateTimelineClip(clips, 99), clips);
  assert.deepEqual(clips, ['a', 'b', 'c']);
});

test('timeline job selection requires the selected run and timeline stage', () => {
  const selection = { runId: 'run-1', stageAttemptId: 'attempt-1' };
  assert.equal(api.isLocalTimelineJobForSelection({
    id: 'job-1',
    stage: 'timeline',
    run_id: 'run-1',
    stage_attempt_id: 'attempt-1',
  }, selection), true);
  assert.equal(api.isLocalTimelineJobForSelection({
    id: 'job-2',
    type: 'local_timeline',
    payload: { run_id: 'run-1', stage_attempt_id: 'attempt-1' },
  }, selection), true);
  assert.equal(api.isLocalTimelineJobForSelection({
    stage: 'timeline',
    run_id: 'run-2',
    stage_attempt_id: 'attempt-1',
  }, selection), false);
  assert.equal(api.isLocalTimelineJobForSelection({
    stage: 'assembly',
    run_id: 'run-1',
    stage_attempt_id: 'attempt-1',
  }, selection), false);
  assert.equal(api.isLocalTimelineJobForSelection({
    stage: 'composition',
    run_id: 'run-1',
    stage_attempt_id: 'attempt-1',
  }, selection), false);
});

test('timeline normalization accepts backend snake_case fields but only emits snake_case payload', () => {
  const normalized = api.normalizeLocalTimelineInput({
    clips: [{ video_artifact_id: 'source', start_ms: '0', end_ms: '50' }],
  });
  assert.deepEqual(normalized.request.clips[0], { videoArtifactId: 'source', startMs: 0, endMs: 50 });
  assert.deepEqual(normalized.payload, {
    clips: [{ video_artifact_id: 'source', start_ms: 0, end_ms: 50 }],
  });
});
