import { AbsoluteFill, Composition, Img, interpolate, staticFile, useCurrentFrame } from 'remotion';
import { ScreenTypography, SCREEN_FONT_FAMILY } from '../../studio/src/remotion/ScreenTypography';

const cream = '#faf9f5';
const ink = '#141413';
const orange = '#d97757';
const ease = (frame: number, start: number, end: number) => {
  const t = interpolate(frame, [start, end], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' });
  return 1 - (1 - t) ** 3;
};

// These are editorial source clips, never generated/reconstructed product UI.
// All movement is frame-derived: no timers, randomness, network or wall clock.
const Hook = () => {
  const frame = useCurrentFrame();
  const entrance = ease(frame, 0, 16);
  return <AbsoluteFill style={{ background: cream, overflow: 'hidden' }}>
    <div style={{ position: 'absolute', inset: 0, transform: `scale(${1 + frame / 167 * 0.035})` }}>
      <Img src={staticFile('writing-ideas-v1.png')} style={{ height: 1080, width: 1620, objectFit: 'contain', position: 'absolute', left: 0, bottom: 0 }} />
    </div>
    <div style={{ position: 'absolute', top: 60, right: 50, color: '#585650', fontSize: 30, fontWeight: 500 }}>コンセプトイラスト</div>
    <div style={{ position: 'absolute', right: 60, top: 214, display: 'flex', flexDirection: 'column', gap: 24,
      transform: `translateX(${(1 - entrance) * 50}px)`, opacity: entrance }}>
      {['目的', '日付', '文字数'].map((text, index) => {
        const visible = ease(frame, index * 17 + 14, index * 17 + 30);
        return <div key={text} style={{ background: cream, border: `3px solid ${orange}`, width: 290, padding: '26px 36px',
          boxShadow: '0 8px 20px rgba(20,20,19,.06)', borderRadius: 18, fontSize: 62, fontWeight: 700,
          opacity: visible, transform: `translateY(${(1 - visible) * 24}px)` }}>{text}</div>;
      })}
    </div>
    <div style={{ position: 'absolute', bottom: 56, right: 56, color: ink, background: cream, borderRadius: 12,
      padding: '14px 26px', fontSize: 38, fontWeight: 600 }}>条件を、ひと言添える。</div>
  </AbsoluteFill>;
};

const Checklist = () => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ background: orange, color: ink, padding: '60px 86px' }}>
    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 34, fontWeight: 600 }}>
      <span>公開前に、もう一度。</span><span>編集図解</span>
    </div>
    <div style={{ display: 'flex', gap: 46, marginTop: 66 }}>
      {[{ label: '日付', value: '9月20日', note: '実際の予定と照合', number: '01' },
        { label: '文字数', value: '40字以内', note: '数えて、必要なら調整', number: '02' }].map((card, index) => {
        const visible = ease(frame, index * 28, index * 28 + 20);
        return <div key={card.label} style={{ flex: 1, height: 620, background: cream, padding: '45px 58px', borderRadius: 24,
          opacity: visible, transform: `translateY(${(1 - visible) * 70}px) rotate(${index ? 1 : -1}deg)`, boxShadow: '0 14px 28px rgba(20,20,19,.10)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: '#7a4937', fontSize: 38, fontWeight: 600 }}>
            <span>{card.number}</span><span>確認ポイント</span>
          </div>
          <div style={{ marginTop: 34, fontWeight: 700, fontSize: 62 }}>{card.label}</div>
          <div style={{ marginTop: 22, fontWeight: 700, fontSize: 112, letterSpacing: '-.02em' }}>{card.value}</div>
          <div style={{ width: `${ease(frame, index * 28 + 35, index * 28 + 60) * 100}%`, height: 7, background: orange, marginTop: 14 }} />
          <div style={{ marginTop: 40, fontSize: 42, fontWeight: 500 }}>{card.note}</div>
        </div>;
      })}
    </div>
    <div style={{ marginTop: 72, fontSize: 37, fontWeight: 500 }}>依頼した条件の例です。回答が条件を満たすとは限りません。</div>
  </AbsoluteFill>;
};

const Panel = ({ kind }: { kind: 'hook' | 'cta' }) => <ScreenTypography>
  <AbsoluteFill style={{ fontFamily: SCREEN_FONT_FAMILY, fontSynthesis: 'none' }}>
    {kind === 'hook' ? <Hook /> : <Checklist />}
  </AbsoluteFill>
</ScreenTypography>;

export const PanelRoot = () => <>
  <Composition id="IllustratedHook" component={Panel} width={1920} height={1080} fps={24} durationInFrames={168} defaultProps={{ kind: 'hook' as const }} />
  <Composition id="EditorialChecklist" component={Panel} width={1920} height={1080} fps={24} durationInFrames={168} defaultProps={{ kind: 'cta' as const }} />
</>;
