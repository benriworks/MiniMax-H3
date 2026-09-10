import React from 'react';
import { AbsoluteFill, Composition, Easing, Img, interpolate, registerRoot, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';

const C = { cream: '#F6F3EC', white: '#FFFDF8', ink: '#292720', muted: '#746F65', terracotta: '#BE664B', pale: '#F0D8CC', line: '#DDD7CB', green: '#B5D7BD' };
const FONT = '"Yu Gothic", "Yu Gothic UI", sans-serif';
const MONO = 'Consolas, monospace';
const ease = Easing.bezier(.2, .72, .24, 1);
const progress = (frame: number, start: number, length = 16) => interpolate(frame, [start, start + length], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: ease });

function Reveal({ children, delay = 0, style = {} }: { children: React.ReactNode; delay?: number; style?: React.CSSProperties }) {
  const frame = useCurrentFrame();
  const p = progress(frame, delay);
  return <div style={{ opacity: p, transform: `translateY(${(1 - p) * 22}px)`, ...style }}>{children}</div>;
}

function Cursor({ x, y, click = 0, size = 50 }: { x: number; y: number; click?: number; size?: number }) {
  return <div style={{ position: 'absolute', left: x, top: y, pointerEvents: 'none' }}>
    {click > 0 && click < 1 && <div style={{ position: 'absolute', width: 80, height: 80, left: -40, top: -40, borderRadius: '50%', border: `3px solid ${C.terracotta}`, opacity: 1 - click, transform: `scale(${.45 + click})` }} />}
    <svg width={size} height={size * 1.2} viewBox="0 0 42 50"><path d="M4 3v36l9-10 8 16 7-4-9-16 14-1Z" fill={C.ink} stroke={C.white} strokeWidth="3" strokeLinejoin="round" /></svg>
  </div>;
}

function Folder({ size = 45 }: { size?: number }) {
  return <svg width={size} height={size * .8} viewBox="0 0 50 40"><path d="M3 6h17l5 7h22v23H3Z" fill={C.pale} stroke={C.terracotta} strokeWidth="2.2" strokeLinejoin="round" /></svg>;
}

function Arrow({ size = 36, color = C.ink }: { size?: number; color?: string }) {
  return <svg width={size} height={size} viewBox="0 0 32 32"><path d="M6 16h20m-8-8 8 8-8 8" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg>;
}

function Shell({ number, children, photo = false }: { number: string; children: React.ReactNode; photo?: boolean }) {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  return <AbsoluteFill style={{ background: C.cream, color: C.ink, fontFamily: FONT, overflow: 'hidden' }}>
    <div style={{ position: 'absolute', left: 96, top: 174, right: 184, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 32, letterSpacing: '.025em', fontWeight: 700 }}>Claude Code</span>
      <span style={{ fontFamily: MONO, fontSize: 27, color: C.muted, letterSpacing: '.06em' }}>DESKTOP / {number}</span>
    </div>
    {children}
    {photo && <div style={{ position: 'absolute', left: 96, top: 1364, width: 800, fontSize: 27, color: C.muted }}>AI生成ビジュアル・画面は説明用</div>}
    <div style={{ position: 'absolute', left: 96, top: 1415, width: 800, fontSize: 26, color: C.muted }}>操作イメージ（実画面ではありません）</div>
    <div style={{ position: 'absolute', left: 96, right: 184, top: 1811, display: 'flex', justifyContent: 'space-between', color: C.muted, fontFamily: MONO, fontSize: 26 }}><span>OPEN · ASK · REVIEW</span><span>{number} / 03</span></div>
    <div style={{ position: 'absolute', left: 96, top: 1857, height: 3, width: 800, background: C.line }}><div style={{ height: '100%', width: `${(frame + 1) / durationInFrames * 100}%`, background: C.terracotta }} /></div>
  </AbsoluteFill>;
}

function Headline({ lines, fontSize = 94 }: { lines: [string, string]; fontSize?: number }) {
  return <div style={{ position: 'absolute', left: 96, top: 292, width: 800 }}>
    {lines.map((text, index) => <Reveal key={text} delay={index * 4}><div style={{ fontSize, lineHeight: 1.4, fontWeight: 800, letterSpacing: '-.04em', whiteSpace: 'nowrap' }}><span style={{ boxShadow: index === 1 ? `inset 0 -.13em ${C.pale}` : undefined }}>{text}</span></div></Reveal>)}
  </div>;
}

function DesktopCut() {
  const frame = useCurrentFrame();
  const selected = frame >= 46;
  const move = progress(frame, 20, 25);
  const click = progress(frame, 45, 16);
  return <Shell number="01">
    <Headline lines={['Claude Code、', 'アプリで使える。']} />
    <Reveal delay={13} style={{ position: 'absolute', top: 655, left: 96, width: 800 }}>
      <div style={{ height: 641, boxSizing: 'border-box', background: C.white, borderRadius: 27, border: `1px solid ${C.line}`, boxShadow: '0 27px 56px rgba(48,39,30,.10)', overflow: 'hidden' }}>
        <div style={{ height: 83, display: 'flex', alignItems: 'center', gap: 12, padding: '0 30px', borderBottom: `1px solid ${C.line}` }}><span style={{ width: 13, height: 13, borderRadius: '50%', background: '#D6B3A5' }} /><span style={{ width: 13, height: 13, borderRadius: '50%', background: '#DDD4BE' }} /><span style={{ width: 13, height: 13, borderRadius: '50%', background: '#BFCCB8' }} /><span style={{ marginLeft: 19, fontSize: 29, color: C.muted }}>Claude デスクトップ</span></div>
        <div style={{ display: 'flex', padding: '23px 24px 0', gap: 14 }}>
          {['Chat', 'Cowork', 'Code'].map((tab, index) => <div key={tab} style={{ flex: 1, textAlign: 'center', fontFamily: MONO, fontSize: 38, padding: '18px 8px 20px', borderRadius: 15, background: selected ? index === 2 ? C.terracotta : '#F5F2EB' : index === 0 ? C.pale : '#F5F2EB', color: selected && index === 2 ? C.white : C.ink, fontWeight: 700, boxShadow: selected && index === 2 ? '0 8px 15px rgba(190,102,75,.18)' : undefined }}>{tab}</div>)}
        </div>
        <Reveal delay={53} style={{ position: 'absolute', top: 271, left: 40, width: 720 }}>
          <div style={{ fontSize: 47, fontWeight: 800 }}>Code タブを開く</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 35 }}><span style={{ fontFamily: MONO, fontSize: 29, background: '#EAE7DF', borderRadius: 10, padding: '8px 19px' }}>Local</span><span style={{ fontSize: 30, color: C.muted }}>PCのプロジェクトから</span></div>
        </Reveal>
        <Reveal delay={79} style={{ position: 'absolute', left: 40, top: 477, width: 720 }}><div style={{ display: 'flex', gap: 22, alignItems: 'center', border: `1px solid ${C.line}`, borderRadius: 17, padding: '23px 26px' }}><Folder /><span style={{ flex: 1, fontSize: 34, fontWeight: 700 }}>フォルダを選択</span><Arrow /></div></Reveal>
        <Cursor x={155 + move * 482} y={380 - move * 233} click={click} />
      </div>
    </Reveal>
  </Shell>;
}

function FolderCut() {
  const frame = useCurrentFrame();
  const prompt = 'ボタンの色を変えて';
  const typed = Math.floor(interpolate(frame, [56, 100], [0, Array.from(prompt).length], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' }));
  const move = progress(frame, 12, 28);
  return <Shell number="02" photo>
    <Headline lines={['フォルダを選んで、', 'やりたいことを入力。']} fontSize={80} />
    <div style={{ position: 'absolute', left: 0, top: 582, width: 1080, height: 764, overflow: 'hidden' }}>
      <Img src={staticFile('desktop-hero.png')} style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: '50% 48%', transform: `translateX(${-frame * .10}px) scale(${1.025 + frame / 126 * .045})`, transformOrigin: '50% 50%' }} />
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg,rgba(246,243,236,.25),transparent 20%,transparent 70%,rgba(246,243,236,.92))' }} />
    </div>
    <Reveal delay={12} style={{ position: 'absolute', left: 104, top: 1010, width: 776 }}>
      <div style={{ display: 'flex', gap: 22, alignItems: 'center', padding: '25px 31px', borderRadius: 18, background: 'rgba(255,253,248,.97)', border: `1px solid ${C.line}`, boxShadow: '0 18px 36px rgba(41,31,23,.14)' }}><Folder /><span style={{ fontFamily: MONO, fontSize: 39, flex: 1, fontWeight: 700 }}>my-project</span><span style={{ fontSize: 25, background: C.pale, borderRadius: 8, padding: '8px 13px', color: C.ink }}>選択</span></div>
    </Reveal>
    <Reveal delay={43} style={{ position: 'absolute', left: 104, top: 1156, width: 776 }}>
      <div style={{ padding: '21px 27px 24px', borderRadius: 19, background: C.white, border: `2px solid ${C.terracotta}`, boxShadow: '0 17px 35px rgba(41,31,23,.11)' }}>
        <div style={{ fontSize: 25, color: C.muted, marginBottom: 14 }}>やりたいことを入力</div>
        <div style={{ display: 'flex', alignItems: 'center', minHeight: 47, gap: 15 }}><div style={{ flex: 1, fontSize: 41, fontWeight: 700, whiteSpace: 'nowrap', letterSpacing: '-.02em' }}>{Array.from(prompt).slice(0, typed).join('')}<span style={{ display: 'inline-block', width: 3, height: 35, background: C.terracotta, marginLeft: 6, verticalAlign: '-4px', opacity: Math.floor(frame / 8) % 2 ? .2 : 1 }} /></div><span style={{ display: 'grid', placeItems: 'center', background: C.terracotta, width: 47, height: 47, borderRadius: 13 }}><Arrow size={28} color={C.white} /></span></div>
      </div>
    </Reveal>
    <div style={{ opacity: frame < 58 ? 1 : 1 - progress(frame, 58, 12) }}><Cursor x={590 + move * 205} y={920 + move * 117} click={progress(frame, 38, 15)} size={45} /></div>
  </Shell>;
}

function ReviewCut() {
  const frame = useCurrentFrame();
  const showAfter = progress(frame, 32, 20);
  const pointer = progress(frame, 70, 28);
  return <Shell number="03">
    <Headline lines={['変更を見て、', '自分で確認。']} />
    <Reveal delay={11} style={{ position: 'absolute', left: 96, top: 647, width: 800 }}>
      <div style={{ background: C.white, border: `1px solid ${C.line}`, borderRadius: 24, padding: '25px 32px 31px', boxShadow: '0 23px 45px rgba(48,39,30,.07)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontFamily: MONO, fontSize: 28, color: C.muted, marginBottom: 23 }}><span>BEFORE</span><span>AFTER</span></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 28 }}>
          <div style={{ flex: 1, padding: '22px 0', background: '#6D7A91', color: C.white, borderRadius: 15, textAlign: 'center', fontSize: 35, fontWeight: 800 }}>保存する</div>
          <Arrow size={38} color={C.muted} />
          <div style={{ flex: 1, padding: '22px 0', background: C.terracotta, color: C.white, borderRadius: 15, textAlign: 'center', fontSize: 35, fontWeight: 800, opacity: showAfter }}>保存する</div>
        </div>
        <div style={{ marginTop: 30, borderTop: `1px solid ${C.line}`, paddingTop: 21, fontFamily: MONO, fontSize: 31, lineHeight: 1.65 }}><div style={{ color: '#8C6965' }}>− background: #6D7A91;</div><div style={{ color: '#835A43', opacity: progress(frame, 48, 15), background: C.pale, borderRadius: 6 }}>+ background: #BE664B;</div></div>
      </div>
    </Reveal>
    <Reveal delay={67} style={{ position: 'absolute', top: 1090, left: 119, width: 754 }}><div style={{ display: 'flex', alignItems: 'center', gap: 18 }}><span style={{ display: 'grid', placeItems: 'center', width: 43, height: 43, borderRadius: '50%', background: C.green }}><svg width="29" height="29" viewBox="0 0 32 32"><path d="m7 16 6 6L26 9" fill="none" stroke={C.ink} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="36" strokeDashoffset={36 * (1 - progress(frame, 77, 25))} /></svg></span><span style={{ fontSize: 34, fontWeight: 700 }}>差分と動作を、自分で確認</span></div></Reveal>
    <Reveal delay={86} style={{ position: 'absolute', top: 1228, left: 96, width: 800 }}><span style={{ fontSize: 41, fontWeight: 800, letterSpacing: '-.03em' }}>まずは、小さな修正から。</span></Reveal>
    <Reveal delay={3} style={{ position: 'absolute', top: 1344, left: 96, width: 800 }}><span style={{ fontSize: 30, fontWeight: 600, color: C.muted }}>対象の有料プランが必要</span></Reveal>
    <div style={{ opacity: frame < 112 ? progress(frame, 60) : 1 - progress(frame, 112, 8) }}><Cursor x={800 - pointer * 105} y={867 - pointer * 74} click={progress(frame, 98, 15)} size={42} /></div>
  </Shell>;
}

export const ClaudeDesktopShortRoot = () => <>
  <Composition id="ClaudeDesktop" component={DesktopCut} durationInFrames={126} fps={24} width={1080} height={1920} />
  <Composition id="ClaudeFolder" component={FolderCut} durationInFrames={126} fps={24} width={1080} height={1920} />
  <Composition id="ClaudeReview" component={ReviewCut} durationInFrames={120} fps={24} width={1080} height={1920} />
</>;

registerRoot(ClaudeDesktopShortRoot);
