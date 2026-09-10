import type {
  LocalRemotionTimelineOverlay,
  LocalRemotionTimelineRequest,
  LocalRemotionTimelineTransition,
  ScreenFocusRegion,
  ScreenThemeId,
} from '../types';
import {
  REMOTION_TIMELINE_FPS,
  REMOTION_TIMELINE_HEIGHT,
  REMOTION_TIMELINE_LIMITS,
  REMOTION_TIMELINE_SCHEMA_VERSION,
  REMOTION_TIMELINE_WIDTH,
  millisecondsToFramesHalfUp,
  normalizeRemotionTimelineInput,
  isValidScreenFocusRegion,
} from '../api';

export {
  REMOTION_TIMELINE_COMPOSITION_ID,
  REMOTION_TIMELINE_FPS,
  REMOTION_TIMELINE_HEIGHT,
  REMOTION_TIMELINE_LIMITS,
  REMOTION_TIMELINE_SCHEMA_VERSION,
  REMOTION_TIMELINE_WIDTH,
  buildLocalRemotionTimelinePayload,
  buildRemotionTimelinePayload,
  framesToMillisecondsHalfUp,
  millisecondsToFramesHalfUp,
  normalizeLocalRemotionTimelineInput,
  normalizeRemotionTimelineInput,
  remotionTimelineDurationInFrames,
  remotionTimelineOutputDurationMs,
} from '../api';
export type {
  NormalizedRemotionTimelineInput,
  RemotionTimelinePayload,
} from '../api';

export interface RemotionTimelineCompositionTransition extends LocalRemotionTimelineTransition {
  durationInFrames: number;
}

export interface RemotionTimelineCompositionOverlay extends LocalRemotionTimelineOverlay {
  startFrame: number;
  endFrame: number;
}

export interface RemotionTimelineCompositionClip {
  src: string;
  startMs: number;
  endMs: number;
  trimBeforeFrame: number;
  trimAfterFrame: number;
  durationInFrames: number;
  volumePercent: number;
  layoutPreset?: 'full_bleed_v1' | 'screen_explainer_v1';
  screenTheme?: ScreenThemeId;
  focusRegion?: ScreenFocusRegion;
  transitionToNext: RemotionTimelineCompositionTransition | null;
  overlay: RemotionTimelineCompositionOverlay | null;
}

export interface RemotionTimelineCompositionProps {
  [key: string]: unknown;
  schemaVersion: typeof REMOTION_TIMELINE_SCHEMA_VERSION;
  width: typeof REMOTION_TIMELINE_WIDTH;
  height: typeof REMOTION_TIMELINE_HEIGHT;
  fps: typeof REMOTION_TIMELINE_FPS;
  durationInFrames: number;
  clips: RemotionTimelineCompositionClip[];
}

/** Fixed geometry keeps the complete screen separate from headlines and subtitles. */
export const SCREEN_EXPLAINER_LAYOUT = {
  sourceLeft: 60,
  sourceTop: 620,
  sourceWidth: 960,
  sourceHeight: 540,
  headlineLeft: 80,
  headlineTop: 300,
  headlineWidth: 880,
  headlineHeight: 220,
  captionSafeTop: 1450,
} as const;

export const assertScreenFocusRegion = (value: unknown): ScreenFocusRegion => {
  if (!isValidScreenFocusRegion(value)) throw new TypeError('Screen focus region must be bounded, at least 0.2 wide and high, and use at most four decimal places');
  return value;
};

/** Place a selected source rectangle inside the fixed viewport without stretching it. */
export const screenFocusGeometry = (focus: ScreenFocusRegion, sourceWidth: number, sourceHeight: number) => {
  const region = assertScreenFocusRegion(focus);
  if (!Number.isSafeInteger(sourceWidth) || !Number.isSafeInteger(sourceHeight) || sourceWidth <= 0 || sourceHeight <= 0) {
    throw new TypeError('Screen focus requires valid source video metadata');
  }
  const selectedWidth = sourceWidth * region.width;
  const selectedHeight = sourceHeight * region.height;
  const scale = Math.min(SCREEN_EXPLAINER_LAYOUT.sourceWidth / selectedWidth, SCREEN_EXPLAINER_LAYOUT.sourceHeight / selectedHeight);
  const width = selectedWidth * scale;
  const height = selectedHeight * scale;
  return {
    left: (SCREEN_EXPLAINER_LAYOUT.sourceWidth - width) / 2,
    top: (SCREEN_EXPLAINER_LAYOUT.sourceHeight - height) / 2,
    width,
    height,
    videoLeft: -sourceWidth * region.x * scale,
    videoTop: -sourceHeight * region.y * scale,
    videoWidth: sourceWidth * scale,
    videoHeight: sourceHeight * scale,
  };
};

const overlayFrames = (overlay: LocalRemotionTimelineOverlay, clipDurationInFrames: number) => {
  const startFrame = millisecondsToFramesHalfUp(overlay.startMs);
  const endFrame = Math.min(
    clipDurationInFrames,
    Math.max(startFrame + 1, millisecondsToFramesHalfUp(overlay.endMs)),
  );
  return { startFrame, endFrame };
};

const STAGED_SOURCE_RE = /^clip-\d{2}\.mp4$/;
const REGISTERED_PREVIEW_SOURCE_RE = /^\/api\/artifacts\/art_[0-9a-f]{32}\/file$/;

export const buildRemotionTimelineCompositionProps = (
  value: unknown,
  sourceForArtifact: (artifactId: string, index: number) => string,
): RemotionTimelineCompositionProps => {
  const normalized = normalizeRemotionTimelineInput(value);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);
  const clips = normalized.request.clips.map((clip, index): RemotionTimelineCompositionClip => {
    const src = sourceForArtifact(clip.videoArtifactId, index);
    if (typeof src !== 'string' || src.trim() === '') throw new TypeError(`カット${index + 1}のsourceを解決できません。`);
    const durationInFrames = millisecondsToFramesHalfUp(clip.endMs - clip.startMs);
    return {
      src: src.trim(),
      startMs: clip.startMs,
      endMs: clip.endMs,
      trimBeforeFrame: millisecondsToFramesHalfUp(clip.startMs),
      trimAfterFrame: millisecondsToFramesHalfUp(clip.endMs),
      durationInFrames,
      volumePercent: clip.volumePercent,
      ...(clip.layoutPreset === undefined ? {} : { layoutPreset: clip.layoutPreset }),
      ...(clip.screenTheme === undefined ? {} : { screenTheme: clip.screenTheme }),
      ...(clip.focusRegion === undefined ? {} : { focusRegion: assertScreenFocusRegion(clip.focusRegion) }),
      transitionToNext: clip.transitionToNext === null ? null : {
        ...clip.transitionToNext,
        durationInFrames: millisecondsToFramesHalfUp(clip.transitionToNext.durationMs),
      },
      overlay: clip.overlay === null ? null : {
        ...clip.overlay,
        ...overlayFrames(clip.overlay, durationInFrames),
      },
    };
  });
  return {
    schemaVersion: REMOTION_TIMELINE_SCHEMA_VERSION,
    width: REMOTION_TIMELINE_WIDTH,
    height: REMOTION_TIMELINE_HEIGHT,
    fps: REMOTION_TIMELINE_FPS,
    durationInFrames: normalized.durationInFrames,
    clips,
  };
};

export const assertRemotionTimelineCompositionProps = (
  value: RemotionTimelineCompositionProps,
): RemotionTimelineCompositionProps => {
  if (value.schemaVersion !== REMOTION_TIMELINE_SCHEMA_VERSION
    || value.width !== REMOTION_TIMELINE_WIDTH
    || value.height !== REMOTION_TIMELINE_HEIGHT
    || value.fps !== REMOTION_TIMELINE_FPS) {
    throw new TypeError('Remotion composition output policy is invalid');
  }
  if (!Array.isArray(value.clips)
    || value.clips.length < REMOTION_TIMELINE_LIMITS.minClips
    || value.clips.length > REMOTION_TIMELINE_LIMITS.maxClips) {
    throw new TypeError('Remotion composition clip count is invalid');
  }
  const request: LocalRemotionTimelineRequest = {
    clips: value.clips.map((clip) => ({
      videoArtifactId: 'art_00000000000000000000000000000000',
      startMs: clip.startMs,
      endMs: clip.endMs,
      volumePercent: clip.volumePercent,
      ...(clip.layoutPreset === undefined ? {} : { layoutPreset: clip.layoutPreset }),
      ...(clip.screenTheme === undefined ? {} : { screenTheme: clip.screenTheme }),
      ...(clip.focusRegion === undefined ? {} : { focusRegion: assertScreenFocusRegion(clip.focusRegion) }),
      transitionToNext: clip.transitionToNext === null ? null : {
        type: clip.transitionToNext.type,
        durationMs: clip.transitionToNext.durationMs,
      },
      overlay: clip.overlay === null ? null : {
        text: clip.overlay.text,
        startMs: clip.overlay.startMs,
        endMs: clip.overlay.endMs,
        position: clip.overlay.position,
        stylePreset: clip.overlay.stylePreset,
      },
    })),
  };
  const normalized = normalizeRemotionTimelineInput(request);
  if (normalized.errors.length > 0) throw new TypeError(normalized.errors[0]);

  value.clips.forEach((clip, index) => {
    if (clip.focusRegion !== undefined) {
      assertScreenFocusRegion(clip.focusRegion);
      if (clip.layoutPreset !== 'screen_explainer_v1') throw new TypeError(`Remotion clip ${index + 1} focus region requires screen layout`);
    }
    if (clip.layoutPreset !== undefined
      && clip.layoutPreset !== 'full_bleed_v1'
      && clip.layoutPreset !== 'screen_explainer_v1') {
      throw new TypeError(`Remotion clip ${index + 1} layout preset is invalid`);
    }
    if (typeof clip.src !== 'string'
      || (!STAGED_SOURCE_RE.test(clip.src) && !REGISTERED_PREVIEW_SOURCE_RE.test(clip.src))) {
      throw new TypeError(`Remotion clip ${index + 1} source is invalid`);
    }
    if (clip.trimBeforeFrame !== millisecondsToFramesHalfUp(clip.startMs)
      || clip.trimAfterFrame !== millisecondsToFramesHalfUp(clip.endMs)
      || clip.durationInFrames !== millisecondsToFramesHalfUp(clip.endMs - clip.startMs)) {
      throw new TypeError(`Remotion clip ${index + 1} trim is invalid`);
    }
    if (clip.transitionToNext !== null
      && clip.transitionToNext.durationInFrames !== millisecondsToFramesHalfUp(clip.transitionToNext.durationMs)) {
      throw new TypeError(`Remotion clip ${index + 1} transition is invalid`);
    }
    if (clip.overlay !== null) {
      const expected = overlayFrames(clip.overlay, clip.durationInFrames);
      if (clip.overlay.startFrame !== expected.startFrame
        || clip.overlay.endFrame !== expected.endFrame
        || clip.overlay.endFrame <= clip.overlay.startFrame) {
        throw new TypeError(`Remotion clip ${index + 1} overlay is invalid`);
      }
    }
  });
  if (!Number.isSafeInteger(value.durationInFrames)
    || value.durationInFrames !== normalized.durationInFrames
    || value.durationInFrames < 1) {
    throw new TypeError('Remotion composition duration is invalid');
  }
  return value;
};
