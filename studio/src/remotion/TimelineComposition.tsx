import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, ReactNode } from 'react';
import {
  AbsoluteFill,
  Composition,
  Html5Video,
  Sequence,
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import type { CalculateMetadataFunction } from 'remotion';
import { linearTiming, TransitionSeries } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';
import { screenSceneTheme, editorialChapter } from './screenThemes';
import { SCREEN_FONT_FAMILY, ScreenTypography } from './ScreenTypography';
import {
  REMOTION_TIMELINE_COMPOSITION_ID,
  REMOTION_TIMELINE_FPS,
  REMOTION_TIMELINE_HEIGHT,
  REMOTION_TIMELINE_SCHEMA_VERSION,
  REMOTION_TIMELINE_WIDTH,
  SCREEN_EXPLAINER_LAYOUT,
  assertRemotionTimelineCompositionProps,
  screenFocusGeometry,
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

const ScreenFocusVideo = ({ clip, index }: {
  clip: RemotionTimelineCompositionClip & { focusRegion: NonNullable<RemotionTimelineCompositionClip['focusRegion']> };
  index: number;
}) => {
  const [metadata, setMetadata] = useState<{ width: number; height: number } | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [handle] = useState(() => delayRender(`Screen ${index + 1} source dimensions`, { timeoutInMilliseconds: 30_000 }));
  const geometry = metadata === null ? null : screenFocusGeometry(clip.focusRegion, metadata.width, metadata.height);

  // Release only after React has committed the correctly sized source rectangle.
  useEffect(() => {
    if (metadata !== null) continueRender(handle);
  }, [handle, metadata]);
  useEffect(() => () => continueRender(handle), [handle]);
  useEffect(() => {
    const video = videoRef.current;
    if (video === null) return;
    // The pinned rendering component suppresses its own exception when onError
    // is provided, but does not always forward the native event to that callback.
    const failSource = () => cancelRender(new Error(`Screen ${index + 1} source video could not be loaded`));
    video.addEventListener('error', failSource);
    if (video.error !== null) failSource();
    return () => video.removeEventListener('error', failSource);
  }, [index]);

  return (
    <div style={{ position: 'absolute', left: geometry?.left ?? 0, top: geometry?.top ?? 0, width: geometry?.width ?? '100%', height: geometry?.height ?? '100%', overflow: 'hidden' }}>
      <Html5Video
        ref={videoRef}
        src={clipSource(clip.src)}
        trimBefore={clip.trimBeforeFrame}
        trimAfter={clip.trimAfterFrame}
        volume={() => clip.volumePercent / 100}
        pauseWhenBuffering
        name={`Screen ${String(index + 1).padStart(2, '0')} focus`}
        onLoadedMetadata={(event) => {
          const width = event.currentTarget.videoWidth;
          const height = event.currentTarget.videoHeight;
          try {
            screenFocusGeometry(clip.focusRegion, width, height);
            setMetadata({ width, height });
          } catch (error) {
            cancelRender(error instanceof Error ? error : new Error('Screen source dimensions are invalid'));
          }
        }}
        onError={(error) => cancelRender(error)}
        style={{ position: 'absolute', left: geometry?.videoLeft ?? 0, top: geometry?.videoTop ?? 0, width: geometry?.videoWidth ?? '100%', height: geometry?.videoHeight ?? '100%', objectFit: 'fill', visibility: geometry === null ? 'hidden' : 'visible' }}
      />
    </div>
  );
};

const ScreenExplainerScene = ({ clip, index, count }: {
  clip: RemotionTimelineCompositionClip;
  index: number;
  count: number;
}) => {
  const theme = screenSceneTheme(clip.screenTheme, index);
  const frame = useCurrentFrame();
  const editorial = clip.screenTheme === 'claude_editorial_v1';
  const enter = editorial ? 1 - (1 - Math.min(1, Math.max(0, frame / 12))) ** 3 : 1;
  return <ScreenTypography>
  <AbsoluteFill data-screen-theme={clip.screenTheme ?? 'neutral_v1'} style={{ backgroundColor: theme.background, color: theme.text, fontFamily: `"${SCREEN_FONT_FAMILY}"`, fontSynthesis: 'none' }}>
    {editorial ? <div aria-hidden style={{ position: 'absolute', top: 278, right: 64, fontSize: 190, lineHeight: 1, fontWeight: 800, opacity: .065, color: theme.text }}>{String(index + 1).padStart(2, '0')}</div> : null}
    <div style={{ position: 'absolute', top: 208, left: 80, right: 80, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 28, fontWeight: 600, letterSpacing: '.02em', color: theme.text }}>
        <span style={{ width: 10, height: 28, backgroundColor: theme.accent }} />{theme.header}
      </div>
      <span style={{ fontSize: 26, color: theme.muted, fontVariantNumeric: 'tabular-nums' }}>STEP {String(index + 1).padStart(2, '0')} / {String(count).padStart(2, '0')}</span>
    </div>
    {clip.overlay !== null && (
      <Sequence from={clip.overlay.startFrame} durationInFrames={clip.overlay.endFrame - clip.overlay.startFrame} name="Screen headline">
        <div data-screen-headline style={{ position: 'absolute', left: SCREEN_EXPLAINER_LAYOUT.headlineLeft, top: SCREEN_EXPLAINER_LAYOUT.headlineTop, width: SCREEN_EXPLAINER_LAYOUT.headlineWidth, height: SCREEN_EXPLAINER_LAYOUT.headlineHeight, fontSize: 76, fontWeight: 700, lineHeight: 1.36, letterSpacing: '.01em', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineBreak: 'strict', transform: `translateY(${(1 - enter) * 18}px)`, opacity: editorial ? .65 + .35 * enter : 1 }}>
          {clip.overlay.text}
        </div>
      </Sequence>
    )}
    <div style={{ position: 'absolute', left: SCREEN_EXPLAINER_LAYOUT.sourceLeft, top: SCREEN_EXPLAINER_LAYOUT.sourceTop - 48, width: SCREEN_EXPLAINER_LAYOUT.sourceWidth, height: 40, display: 'flex', alignItems: 'center', gap: 10 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', backgroundColor: theme.accent }} />
      <span style={{ fontSize: 26, fontWeight: 600, color: theme.muted, letterSpacing: '.06em' }}>{editorial ? `${String(index + 1).padStart(2, '0')} / ${editorialChapter(index)}` : `SCREEN ${String(index + 1).padStart(2, '0')}`}</span>
      {clip.focusRegion !== undefined && <span style={{ marginLeft: 'auto', fontSize: 26, fontWeight: 600, color: theme.muted }}>拡大表示</span>}
    </div>
    <div style={{ position: 'absolute', left: SCREEN_EXPLAINER_LAYOUT.sourceLeft, top: SCREEN_EXPLAINER_LAYOUT.sourceTop, width: SCREEN_EXPLAINER_LAYOUT.sourceWidth, height: SCREEN_EXPLAINER_LAYOUT.sourceHeight, backgroundColor: theme.sourceBackground, outline: `2px solid ${theme.sourceBorder}`, boxShadow: '0 16px 48px rgba(0, 0, 0, .12)' }}>
      {clip.focusRegion === undefined ? <Html5Video
        src={clipSource(clip.src)}
        trimBefore={clip.trimBeforeFrame}
        trimAfter={clip.trimAfterFrame}
        volume={() => clip.volumePercent / 100}
        pauseWhenBuffering
        name={`Screen ${String(index + 1).padStart(2, '0')}`}
        style={{ ...VIDEO_STYLE, objectFit: 'contain', backgroundColor: theme.sourceBackground }}
      /> : <ScreenFocusVideo key={clip.src} clip={{ ...clip, focusRegion: clip.focusRegion }} index={index} />}
    </div>
    <div style={{ position: 'absolute', left: 80, right: 80, top: 1260, display: 'flex', gap: 12 }}>
      {Array.from({ length: count }, (_, step) => <span key={step} style={{ flex: 1, height: 5, backgroundColor: step === index ? theme.accent : theme.inactiveStep }} />)}
    </div>
    {theme.footer !== '' && <div style={{ position: 'absolute', top: 1330, left: 80, right: 80, fontSize: 23, fontWeight: 400, color: theme.muted, lineHeight: 1.5 }}>{theme.footer}</div>}
    {/* The lower area is intentionally empty for the assembly's narration captions. */}
  </AbsoluteFill>
  </ScreenTypography>;
};

const ClipScene = ({ clip, index, count }: { clip: RemotionTimelineCompositionClip; index: number; count: number }) => clip.layoutPreset === 'screen_explainer_v1' ? (
  <ScreenExplainerScene clip={clip} index={index} count={count} />
) : (
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
        <ClipScene clip={clip} index={index} count={value.clips.length} />
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
