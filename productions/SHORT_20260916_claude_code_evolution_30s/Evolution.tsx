import {AbsoluteFill, Composition, OffthreadVideo, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import {ScreenTypography, SCREEN_FONT_FAMILY} from '../../studio/src/remotion/ScreenTypography';

type Model = {name: string; date: string; score: number};
type Props = {models: Model[]; eyecatchSrc: string};
const ease = (f: number, start = 0, duration = 18) => {
  const t = Math.max(0, Math.min(1, (f - start) / duration));
  return 1 - (1 - t) ** 3;
};
const colors = ['#142327', '#F3EEE4', '#172F36', '#F0DDD0', '#172F36', '#F3EEE4'];
const accent = '#A7462B';
const Hero = ({children, size = 96}: {children: React.ReactNode; size?: number}) => {
  if (size < 54) throw new Error('All video typography must be at least 54px');
  return <div style={{fontSize: size, lineHeight: 1.27, letterSpacing: '-0.04em', fontWeight: 800, whiteSpace: 'pre-line'}}>{children}</div>;
};

const Video = ({models, eyecatchSrc}: Props) => {
  const frame = useCurrentFrame();
  const chapter = Math.min(5, Math.floor(frame / 120));
  const f = frame % 120;
  const dark = chapter === 0 || chapter === 2 || chapter === 4;
  const foreground = dark ? '#FFF9F0' : '#282A28';
  const muted = dark ? '#DAE6E4' : '#61574E';
  const pop = dark ? '#FFBB96' : accent;
  const a = ease(f, 0, 10);
  const modelIndex = chapter - 1;
  return <ScreenTypography><AbsoluteFill style={{background: colors[chapter], color: foreground, fontFamily: SCREEN_FONT_FAMILY, fontSize: 54, fontSynthesis: 'none', textShadow: chapter === 0 ? '0 2px 10px rgba(0,0,0,.75)' : 'none'}}>
    {chapter === 0 ? <>
      <OffthreadVideo src={staticFile(eyecatchSrc)} muted style={{position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', filter: 'brightness(1.14) saturate(1.12)'}}/>
      <AbsoluteFill style={{background: 'linear-gradient(180deg, rgba(5,15,36,.58) 0%, rgba(5,15,36,.18) 27%, rgba(5,15,36,0) 38%, rgba(5,15,36,0) 65%, rgba(5,15,36,.38) 76%, rgba(5,15,36,.70) 100%)'}}/>
    </> : <svg width="1080" height="1920" style={{position: 'absolute', opacity: dark ? .10 : .07}}>
      <defs><pattern id="grid" width="72" height="72" patternUnits="userSpaceOnUse"><path d="M 72 0 L 0 0 0 72" fill="none" stroke={foreground} strokeWidth="1"/></pattern></defs>
      <rect width="1080" height="1920" fill="url(#grid)"/>
      <circle cx="1070" cy="535" r={310 + frame / 12} fill="none" stroke={foreground} strokeWidth="2"/>
    </svg>}
    <div style={{position: 'absolute', left: 80, width: 850, top: 94, display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 54, fontWeight: 600}}>
      <span>CLAUDE CODE</span><span style={{color: muted}}>モデルの進化</span>
    </div>
    <div style={{position: 'absolute', left: 80, top: 196, height: 6, width: 850, background: dark ? '#4A6065' : '#D6CFC3'}}>
      <div style={{height: 6, width: `${(frame + 1) / 720 * 100}%`, background: pop}}/>
    </div>
    <div style={{position: 'absolute', left: 80, width: 850, top: 272, opacity: a, transform: `translateY(${(1 - a) * 24}px)`}}>
      {chapter === 0 && <>
        <div style={{fontSize: 60, color: pop, fontWeight: 700, marginBottom: 38}}>2026年 6月 → 9月</div>
        <Hero size={144}>{'たった\n3か月で。'}</Hero>
      </>}
      {chapter >= 1 && chapter <= 3 && <>
        <div style={{display: 'flex', alignItems: 'center', gap: 24, fontSize: 54, color: pop, fontWeight: 700, marginBottom: 46}}><span style={{fontSize: 70}}>0{chapter}</span><span>{models[modelIndex].date} 発表</span></div>
        <Hero size={110}>{models[modelIndex].name}</Hero>
        <div style={{height: 7, background: pop, marginTop: 25, width: `${ease(f, 6) * 235}px`}}/>
        <div style={{marginTop: 58}}><Hero size={86}>{['長く、複雑な\n開発タスクへ。', '性能 × 効率。\n日々の開発へ。', '問題の根本へ。\n長い作業にも。'][modelIndex]}</Hero></div>
        <div style={{marginTop: 58, background: dark ? '#28434A' : '#FFFFFFBF', padding: '32px 36px', borderRadius: 20, opacity: ease(f, 20)}}>
          <div style={{fontSize: 54, color: muted, marginBottom: 22}}>公式発表のポイント</div>
          <div style={{fontSize: 62, lineHeight: 1.35, whiteSpace: 'pre-line', fontWeight: 700}}>{['長い課題を\n継続して進める', '高度な性能と\n費用効率', 'コーディングと\n課題解決'][modelIndex]}</div>
        </div>
      </>}
      {chapter === 4 && <>
        <Hero size={82}>{'開発評価の\nスコアが向上。'}</Hero>
        <div style={{fontSize: 54, marginTop: 25, color: muted}}>Terminal-Bench 4.0</div>
        <div style={{marginTop: 43}}>
          {models.map((m, i) => <div key={m.name} style={{marginBottom: 28}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12, fontSize: 60}}><span>{m.name}</span><b style={{fontSize: 70, color: i === 2 ? '#FFC8A9' : foreground}}>{m.score.toFixed(1)}<span style={{fontSize: 54}}> %</span></b></div>
            <div style={{height: 33, background: '#365158', position: 'relative'}}>
              <div style={{height: 33, width: `${m.score * ease(f, 8 + i * 7, 24)}%`, background: i === 2 ? '#F2A17E' : '#A8C5C7'}}/>
            </div>
          </div>)}
          <div style={{display: 'flex', justifyContent: 'space-between', color: muted, fontSize: 54}}><span>0%</span><span>50%</span><span>100%</span></div>
        </div>
      </>}
      {chapter === 5 && <>
        <div style={{fontSize: 58, color: accent, fontWeight: 700, marginBottom: 48}}>次は、あなたの開発で。</div>
        <Hero size={104}>{'任せる仕事を、\nひとつ\n広げてみる。'}</Hero>
        <div style={{marginTop: 70, display: 'flex', gap: 16}}>{['長い課題', '効率', '解決力'].map((t, i) => <div key={t} style={{flex: 1, padding: '28px 0', textAlign: 'center', fontSize: 54, fontWeight: 700, borderTop: `6px solid ${accent}`, background: '#FFFFFFBF', opacity: ease(f, 14 + i * 10)}}>{t}</div>)}</div>
        <div style={{fontSize: 58, lineHeight: 1.5, marginTop: 54, color: muted}}>6月 → 7月 → 9月<br/>進化を、実際の開発へ。</div>
      </>}
    </div>
    <div style={{position: 'absolute', top: 1288, left: 80, width: 850, borderTop: `2px solid ${dark ? '#6C858A' : '#BCAE9F'}`, padding: chapter === 0 ? '22px 20px 16px' : '22px 0 0', boxSizing: 'border-box', background: chapter === 0 ? 'rgba(5,15,36,.52)' : 'transparent', fontSize: 54, color: muted, lineHeight: 1.38, whiteSpace: 'pre-line'}}>{chapter === 4 ? '公式比較・2026年9月\n条件は概要欄（非公式解説）' : chapter === 0 ? 'MiniMax H3 生成映像\n非公式解説・出典は概要欄' : '非公式の解説\n出典・詳細は概要欄へ'}</div>
  </AbsoluteFill></ScreenTypography>;
};
registerRoot(() => <Composition id="ClaudeEvolution30" component={Video} width={1080} height={1920} fps={24} durationInFrames={720} defaultProps={{models: [], eyecatchSrc: 'eyecatch.mp4'}}/>);
