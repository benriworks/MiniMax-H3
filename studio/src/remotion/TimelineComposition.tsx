import type { CSSProperties, ReactNode } from 'react';
import {
  AbsoluteFill,
  Composition,
  Html5Video,
  Sequence,
  staticFile,
} from 'remotion';
import type { CalculateMetadataFunction } from 'remotion';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import {
  REMOTION_TIMELINE_COMPOSITION_ID,
  REMOTION_TIMELINE_FPS,
  REMOTION_TIMELINE_HEIGHT,
  REMOTION_TIMELINE_SCHEMA_VERSION,
  REMOTION_TIMELINE_WIDTH,
  assertRemotionTimelineCompositionProps,
} from './model';
import type {
  RemotionTimelineCompositionClip,
  RemotionTimelineCompositionOverlay,
  RemotionTimelineCompositionProps,
} from './model';

const VIDEO_STYLE: CSSProperties = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
  backgroundColor: '#000000',
};

const clipSource = (src: string): string => src.startsWith('/api/artifacts/') ? src : staticFile(src);

const OVERLAY_POSITION_STYLE: Record<RemotionTimelineCompositionOverlay['position'], CSSProperties> = {
  top: { justifyContent: 'flex-start', paddingTop: 180 },
  center: { justifyContent: 'center' },
  bottom: { justifyContent: 'flex-end', paddingBottom: 300 },
};

const TextOverlay = ({ overlay }: { overlay: RemotionTimelineCompositionOverlay }) => (
  <Sequence
    from={overlay.startFrame}
    durationInFrames={overlay.endFrame - overlay.startFrame}
    name="Text overlay"
  >
    <AbsoluteFill
      style={{
        alignItems: 'center',
        boxSizing: 'border-box',
        paddingLeft: 96,
        paddingRight: 96,
        ...OVERLAY_POSITION_STYLE[overlay.position],
      }}
    >
      <div
        style={{
          maxWidth: 888,
          padding: '20px 30px 24px',
          borderRadius: 20,
          color: '#ffffff',
          backgroundColor: 'rgba(0, 0, 0, 0.45)',
          fontFamily: '"Yu Gothic UI", "Yu Gothic", sans-serif',
          fontSize: 80,
          fontWeight: 700,
          lineHeight: 1.24,
          letterSpacing: '0.01em',
          textAlign: 'center',
          textShadow: [
            '-5px -5px 0 #000000',
            '5px -5px 0 #000000',
            '-5px 5px 0 #000000',
            '5px 5px 0 #000000',
            '0 6px 18px rgba(0, 0, 0, 0.9)',
          ].join(', '),
          whiteSpace: 'pre-wrap',
          overflowWrap: 'anywhere',
        }}
      >
        {overlay.text}
      </div>
    </AbsoluteFill>
  </Sequence>
);

const ClipScene = ({ clip, index }: { clip: RemotionTimelineCompositionClip; index: number }) => (
  <AbsoluteFill style={{ backgroundColor: '#000000', overflow: 'hidden' }}>
    <Html5Video
      src={clipSource(clip.src)}
      trimBefore={clip.trimBeforeFrame}
      trimAfter={clip.trimAfterFrame}
      volume={() => clip.volumePercent / 100}
      pauseWhenBuffering
      name={`Clip ${String(index + 1).padStart(2, '0')}`}
      style={VIDEO_STYLE}
    />
    {clip.overlay === null ? null : <TextOverlay overlay={clip.overlay} />}
  </AbsoluteFill>
);

export const TimelineComposition = (props: RemotionTimelineCompositionProps) => {
  const value = assertRemotionTimelineCompositionProps(props);
  const children: ReactNode[] = [];
  value.clips.forEach((clip, index) => {
    children.push(
      <TransitionSeries.Sequence
        key={`clip-${index}`}
        durationInFrames={clip.durationInFrames}
        name={`Clip ${String(index + 1).padStart(2, '0')}`}
      >
        <ClipScene clip={clip} index={index} />
      </TransitionSeries.Sequence>,
    );
    if (clip.transitionToNext !== null) {
      children.push(
        <TransitionSeries.Transition
          key={`transition-${index}`}
          presentation={fade()}
          timing={linearTiming({ durationInFrames: clip.transitionToNext.durationInFrames })}
        />,
      );
    }
  });
  return (
    <AbsoluteFill style={{ backgroundColor: '#000000' }}>
      <TransitionSeries>{children}</TransitionSeries>
    </AbsoluteFill>
  );
};

const DEFAULT_PROPS: RemotionTimelineCompositionProps = {
  schemaVersion: REMOTION_TIMELINE_SCHEMA_VERSION,
  width: REMOTION_TIMELINE_WIDTH,
  height: REMOTION_TIMELINE_HEIGHT,
  fps: REMOTION_TIMELINE_FPS,
  durationInFrames: REMOTION_TIMELINE_FPS,
  clips: [{
    src: 'clip-00.mp4',
    startMs: 0,
    endMs: 1_000,
    trimBeforeFrame: 0,
    trimAfterFrame: REMOTION_TIMELINE_FPS,
    durationInFrames: REMOTION_TIMELINE_FPS,
    volumePercent: 100,
    transitionToNext: null,
    overlay: null,
  }],
};

const calculateMetadata: CalculateMetadataFunction<RemotionTimelineCompositionProps> = ({ props }) => {
  const value = assertRemotionTimelineCompositionProps(props);
  return {
    durationInFrames: value.durationInFrames,
    width: REMOTION_TIMELINE_WIDTH,
    height: REMOTION_TIMELINE_HEIGHT,
    fps: REMOTION_TIMELINE_FPS,
    props: value,
  };
};

export const RemotionTimelineRoot = () => (
  <Composition
    id={REMOTION_TIMELINE_COMPOSITION_ID}
    component={TimelineComposition}
    durationInFrames={REMOTION_TIMELINE_FPS}
    width={REMOTION_TIMELINE_WIDTH}
    height={REMOTION_TIMELINE_HEIGHT}
    fps={REMOTION_TIMELINE_FPS}
    defaultProps={DEFAULT_PROPS}
    calculateMetadata={calculateMetadata}
  />
);
