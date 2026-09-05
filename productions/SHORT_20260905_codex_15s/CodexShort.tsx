import React from 'react';
import { AbsoluteFill, Composition, Easing, interpolate, registerRoot, useCurrentFrame, useVideoConfig } from 'remotion';

const C = { paper: '#F5F3EC', ink: '#17221C', muted: '#677168', mint: '#BDEFCF', line: '#D7DDD3', white: '#FFFEFA' };
const FONT = '"Yu Gothic", "Yu Gothic UI", sans-serif';
const MONO = '"Cascadia Code", Consolas, monospace';
const ease = Easing.bezier(0.2, 0.75, 0.25, 1);
const ramp = (frame: number, from: number, duration = 16) => interpolate(frame, [from, from + duration], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease });

function Reveal({ children, delay = 0, distance = 24, style = {} }: { children: React.ReactNode; delay?: number; distance?: number; style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const p = ramp(frame, delay);
  return <div style={{ opacity: p, transform: `translateY(${(1 - p) * distance}px)`, ...style }}>{children}</div>;
}

function Arrow({ size = 36, color = C.ink }: { size?: number; color?: string }) {
  return <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true"><path d="M6 16h19m-8-8 8 8-8 8" fill="none" stroke={color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function Check({ progress, size = 28 }: { progress: number; size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true"><path d="m7 16 6 6L26 9" fill="none" stroke={C.ink} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="36" strokeDashoffset={36 * (1 - progress)} /></svg>;
}

function Shell({ number, children }: { number: string; children: React.ReactNode }) {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const drift = frame / durationInFrames;
  return <AbsoluteFill style={{ background: C.paper, color: C.ink, fontFamily: FONT, overflow: 'hidden' }}>
    <div style={{ position: 'absolute', left: 756, top: 660, width: 520, height: 520, borderRadius: '50%', border: `1px solid ${C.line}`, transform: `translate(${drift * -22}px,${drift * 14}px)` }} />
    <div style={{ position: 'absolute', left: -270, top: 1160, width: 540, height: 540, borderRadius: '50%', background: '#E8EEE3', opacity: .65, transform: `scale(${1 + drift * .03})` }} />
    <div style={{ position: 'absolute', left: 96, right: 184, top: 158, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 37, fontWeight: 800, letterSpacing: '-.05em' }}>Codex<span style={{ color: '#87BA9B', paddingLeft: 5 }}>.</span></span>
      <span style={{ fontFamily: MONO, fontSize: 26, letterSpacing: '.09em', color: C.muted }}>A SMALL BEGINNING / {number}</span>
    </div>
    <div style={{ position: 'absolute', inset: 0, transform: `translateY(${-drift * 7}px) scale(${1 + drift * .012})`, transformOrigin: '50% 50%' }}>{children}</div>
    <div style={{ position: 'absolute', left: 96, right: 184, top: 1815, display: 'flex', justifyContent: 'space-between', color: '#7C857A', fontFamily: MONO, fontSize: 26, letterSpacing: '.04em' }}><span>IDEA → BUILD → REVIEW</span><span>{number} / 03</span></div>
    <div style={{ position: 'absolute', left: 96, bottom: 57, height: 3, width: 800, background: C.line }}><div style={{ height: '100%', width: `${(frame + 1) / durationInFrames * 100}%`, background: '#8DB89B' }} /></div>
  </AbsoluteFill>;
}

function Headline({ lines, accentLine = 1 }: { lines: [string, string]; accentLine?: number }) {
  return <div style={{ position: 'absolute', top: 297, left: 96, width: 800 }}>
    {lines.map((line, i) => <Reveal key={line} delay={i * 5} distance={18}><div style={{ fontSize: 101, fontWeight: 800, lineHeight: 1.34, letterSpacing: '-.045em', whiteSpace: 'nowrap' }}><span style={{ boxShadow: i === accentLine ? `inset 0 -.14em ${C.mint}` : undefined }}>{line}</span></div></Reveal>)}
  </div>;
}

function PromptCut() {
  const frame = useCurrentFrame();
  const prompt = 'タスク管理アプリを作って';
  const letters = Math.floor(interpolate(frame, [22, 64], [0, Array.from(prompt).length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }));
  const tasks = [ ['画面を考える', 'DESIGN', 66], ['動く形にする', 'BUILD', 83], ['使って確かめる', 'REVIEW', 100] ] as const;
  return <Shell number="01">
    <Headline lines={['作りたい。', 'を、言葉に。']} />
    <Reveal delay={16} style={{ position: 'absolute', left: 96, top: 697, width: 800 }}>
      <div style={{ padding: '30px 34px 32px', border: `1px solid ${C.line}`, borderRadius: 24, background: C.white, boxShadow: '0 20px 45px rgba(39,54,41,.065)' }}>
        <div style={{ fontSize: 27, color: C.muted, marginBottom: 23, letterSpacing: '.08em' }}>あなたの言葉から</div>
        <div style={{ display: 'flex', alignItems: 'center', minHeight: 53, gap: 12 }}>
          <span style={{ fontSize: 43, fontWeight: 700, letterSpacing: '-.025em', flex: 1, whiteSpace: 'nowrap' }}>{Array.from(prompt).slice(0, letters).join('')}<span style={{ display: 'inline-block', width: 3, height: 38, marginLeft: 5, background: C.ink, opacity: frame < 72 ? (Math.floor(frame / 7) % 2 ? .2 : 1) : 0, verticalAlign: '-4px' }} /></span>
          <div style={{ width: 58, height: 58, borderRadius: 18, display: 'grid', placeItems: 'center', background: C.mint }}><Arrow size={31} /></div>
        </div>
      </div>
    </Reveal>
    <Reveal delay={47} style={{ position: 'absolute', left: 119, top: 955, width: 754 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 25 }}><span style={{ fontSize: 32, fontWeight: 800 }}>小さなアイデアが、形になる。</span><span style={{ fontFamily: MONO, fontSize: 26, color: C.muted }}>PLAN</span></div>
      {tasks.map(([text, label, delay], i) => <Reveal key={text} delay={delay} distance={22} style={{ marginBottom: 14 }}><div style={{ display: 'flex', alignItems: 'center', gap: 23, minHeight: 83, padding: '9px 24px', borderRadius: 16, border: `1px solid ${C.line}`, background: i === 1 ? C.mint : C.white }}><div style={{ width: 32, height: 32, border: '2px solid #B6C4B8', borderRadius: 8 }} /><span style={{ flex: 1, fontSize: 35, fontWeight: 700 }}>{text}</span><span style={{ fontSize: 25, fontFamily: MONO, color: C.muted }}>{label}</span></div></Reveal>)}
    </Reveal>
    <Reveal delay={0} style={{ position: 'absolute', left: 119, top: 1367, fontSize: 27, color: C.muted }}>ワークフローのイメージ</Reveal>
  </Shell>;
}

function BuildCut() {
  const frame = useCurrentFrame();
  const code = [
    { text: 'function completeTask(task) {', color: '#D5E9DD' },
    { text: '  return {', color: '#C7D5CC' },
    { text: '    ...task,', color: '#C7D5CC' },
    { text: '    done: true,', color: '#BEF0CF', added: true },
    { text: '  };', color: '#C7D5CC' },
    { text: '}', color: '#C7D5CC' },
  ];
  return <Shell number="02">
    <Headline lines={['実装から、', 'テストまで。']} />
    <Reveal delay={12} style={{ position: 'absolute', top: 669, left: 96, width: 800 }}>
      <div style={{ background: C.ink, borderRadius: 24, padding: '28px 32px 31px', boxShadow: '0 26px 44px rgba(22,34,27,.15)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', paddingBottom: 24, marginBottom: 15, borderBottom: '1px solid #405346', color: '#D7E2D8' }}><span style={{ fontFamily: MONO, fontSize: 27 }}>task.ts</span><span style={{ fontSize: 26, color: '#BDEFCF' }}>変更を提案</span></div>
        {code.map((line, i) => {
          const visible = ramp(frame, 21 + i * 7, 12);
          return <div key={i} style={{ display: 'flex', alignItems: 'center', minHeight: 47, fontSize: 31, fontFamily: MONO, lineHeight: 1.5, color: line.color, opacity: visible, background: line.added ? `rgba(117,197,139,${.11 + .05 * Math.sin(frame / 15)})` : undefined, borderRadius: 6 }}><span style={{ width: 43, flex: 'none', color: '#718679', fontSize: 25, textAlign: 'center' }}>{line.added ? '+' : String(i + 1).padStart(2, '0')}</span><span style={{ whiteSpace: 'pre' }}>{line.text}</span></div>;
        })}
      </div>
    </Reveal>
    <div style={{ position: 'absolute', top: 1140, left: 119, width: 754 }}>
      {[['入力を確かめる', 67], ['変更の影響を見る', 90]].map(([text, at]) => <Reveal key={String(text)} delay={Number(at)} style={{ marginBottom: 17 }}><div style={{ display: 'flex', alignItems: 'center', gap: 22, padding: '18px 23px', border: `1px solid ${C.line}`, background: C.white, borderRadius: 17 }}><span style={{ display: 'grid', placeItems: 'center', width: 39, height: 39, borderRadius: '50%', background: C.mint }}><Check progress={ramp(frame, Number(at) + 8, 20)} /></span><span style={{ fontSize: 35, fontWeight: 700 }}>{text}</span></div></Reveal>)}
    </div>
    <Reveal delay={0} style={{ position: 'absolute', left: 119, top: 1367, fontSize: 27, color: C.muted }}>ワークフローのイメージ</Reveal>
  </Shell>;
}

function ReviewCut() {
  const frame = useCurrentFrame();
  return <Shell number="03">
    <Headline lines={['確かめて、', '次の一歩へ。']} />
    <Reveal delay={13} style={{ position: 'absolute', left: 96, top: 714, width: 800 }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14 }}><span style={{ fontSize: 173, fontWeight: 800, letterSpacing: '-.07em', lineHeight: 1 }}>Codex</span><span style={{ fontSize: 175, lineHeight: 1, fontWeight: 800, color: '#87BA9B' }}>.</span></div>
      <div style={{ width: 776 * ramp(frame, 25, 60), height: 5, background: '#A6DAB8', marginTop: 33 }} />
    </Reveal>
    <div style={{ position: 'absolute', top: 1005, left: 96, width: 800, display: 'flex', alignItems: 'center', gap: 21 }}>
      {['依頼', '実装', '確認'].map((text, i) => <React.Fragment key={text}>
        {i > 0 && <Reveal delay={35 + i * 16} style={{ flex: 'none', width: 42 }}><Arrow size={42} color="#748F7C" /></Reveal>}
        <Reveal delay={24 + i * 23} distance={20} style={{ flex: 1 }}><div style={{ height: 148, borderRadius: 23, border: `1px solid ${i === 2 ? '#90CBA3' : C.line}`, background: i === 2 ? C.mint : C.white, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 9 }}><span style={{ fontFamily: MONO, fontSize: 26, color: C.muted }}>0{i + 1}</span><span style={{ fontSize: 44, fontWeight: 800 }}>{text}</span></div></Reveal>
      </React.Fragment>)}
    </div>
    <Reveal delay={81} style={{ position: 'absolute', left: 96, top: 1297, width: 800, display: 'flex', alignItems: 'center', gap: 19 }}>
      <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#69A97D', flex: 'none', transform: `scale(${1 + .13 * Math.sin(frame / 8)})` }} />
      <span style={{ fontSize: 42, fontWeight: 700, letterSpacing: '-.025em' }}>まずは、小さな改善から。</span>
    </Reveal>
  </Shell>;
}

export const CodexShortRoot = () => <>
  <Composition id="CodexPrompt" component={PromptCut} durationInFrames={126} fps={24} width={1080} height={1920} />
  <Composition id="CodexBuild" component={BuildCut} durationInFrames={126} fps={24} width={1080} height={1920} />
  <Composition id="CodexReview" component={ReviewCut} durationInFrames={120} fps={24} width={1080} height={1920} />
</>;

registerRoot(CodexShortRoot);
