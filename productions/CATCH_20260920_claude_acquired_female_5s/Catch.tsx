import {AbsoluteFill, Composition, OffthreadVideo, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import {ScreenTypography, SCREEN_FONT_FAMILY} from '../../studio/src/remotion/ScreenTypography';

type Props = {source: string};
const ease = (frame: number, start: number, duration: number) => {
  const t = Math.max(0, Math.min(1, (frame - start) / duration));
  return 1 - (1 - t) ** 3;
};

const Catch = ({source}: Props) => {
  const frame = useCurrentFrame();
  const reveal = ease(frame, 25, 9);
  const badge = ease(frame, 18, 10);
  const settle = frame < 34 ? 0 : Math.sin((frame - 34) * .28) * Math.exp(-(frame - 34) / 9) * .035;
  return <ScreenTypography><AbsoluteFill style={{background: '#091126', color: '#fff5dc', fontFamily: SCREEN_FONT_FAMILY, fontSize: 54, fontSynthesis: 'none'}}>
    <OffthreadVideo src={staticFile(source)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}}/>
    <AbsoluteFill style={{background: 'linear-gradient(180deg,rgba(6,12,33,.48),transparent 27%,transparent 65%,rgba(6,12,33,.2) 80%,rgba(6,12,33,.66))'}}/>
    <div style={{position: 'absolute', top: 72, left: 188, width: 880, display: 'flex', justifyContent: 'center', opacity: badge, transform: `translateY(${(1 - badge) * -24}px)`}}>
      <div style={{border: '3px solid #fce197', borderRadius: 10, padding: '12px 34px 16px', background: 'linear-gradient(110deg,#362b22ed,#665020ed,#30253eed)', boxShadow: '0 0 40px #ffc76650,inset 0 0 22px #ffcb4930', fontSize: 60, fontWeight: 900, letterSpacing: '.1em', color: '#ffe7a6'}}>LEGENDARY</div>
    </div>
    <div style={{position: 'absolute', top: 1356, left: 62, width: 890, boxSizing: 'border-box', opacity: reveal, transform: `translateY(${(1 - reveal) * 60}px) scale(${.92 + .08 * reveal + settle})`, transformOrigin: 'center', border: '4px solid #e9c171', borderRadius: 22, background: 'linear-gradient(135deg,rgba(9,19,51,.96),rgba(25,29,57,.96))', boxShadow: '0 12px 60px #0009,0 0 40px #ffd36430,inset 0 0 32px #ffd3640f', padding: '24px 24px 34px', textAlign: 'center'}}>
      <div style={{height: 3, width: 330, margin: '0 auto 15px', background: 'linear-gradient(90deg,transparent,#ffe2a0,transparent)'}}/>
      <div style={{fontSize: 128, lineHeight: 1.13, fontWeight: 900, letterSpacing: '-.03em', color: '#ffe4a0', textShadow: '0 4px 0 #54401c'}}>Claudeを</div>
      <div style={{fontSize: 102, lineHeight: 1.32, fontWeight: 900, letterSpacing: '-.04em', marginTop: 8}}>手に入れた！</div>
    </div>
    <div style={{position: 'absolute', left: 64, top: 1766, fontSize: 54, fontWeight: 600, color: '#f5f2eb', textShadow: '0 2px 8px #000,0 0 16px #000'}}>MiniMax H3 生成映像</div>
  </AbsoluteFill></ScreenTypography>;
};

registerRoot(() => <Composition id="ClaudeAcquired5" component={Catch} width={1080} height={1920} fps={24} durationInFrames={120} defaultProps={{source: 'source.mp4'}}/>);
