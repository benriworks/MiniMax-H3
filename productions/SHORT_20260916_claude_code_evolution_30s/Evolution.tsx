import {AbsoluteFill, Composition, registerRoot, useCurrentFrame} from 'remotion';
import {ScreenTypography, SCREEN_FONT_FAMILY} from '../../studio/src/remotion/ScreenTypography';

type Model = {name: string; date: string; score: number};
type Props = {models: Model[]};
const ease = (f: number, start = 0, duration = 18) => {
  const t = Math.max(0, Math.min(1, (f - start) / duration));
  return 1 - (1 - t) ** 3;
};
const colors = ['#F3EEE4', '#F3EEE4', '#172F36', '#F0DDD0', '#172F36', '#F3EEE4'];
const accent = '#A7462B';
const Hero = ({children, size = 87}: {children: React.ReactNode; size?: number}) =>
  <div style={{fontSize: size, lineHeight: 1.29, letterSpacing: '-0.045em', fontWeight: 800, whiteSpace: 'pre-line'}}>{children}</div>;

const Video = ({models}: Props) => {
  const frame = useCurrentFrame();
  const chapter = Math.min(5, Math.floor(frame / 120));
  const f = frame % 120;
  const dark = chapter === 2 || chapter === 4;
  const foreground = dark ? '#F9F4EB' : '#282A28';
  const muted = dark ? '#C8D8D6' : '#665D55';
  const pop = dark ? '#ECA487' : accent;
  const a = ease(f, 0, 12);
  const modelIndex = chapter - 1;
  return <ScreenTypography><AbsoluteFill style={{background: colors[chapter], color: foreground, fontFamily: SCREEN_FONT_FAMILY, fontSynthesis: 'none'}}>
    <svg width="1080" height="1920" style={{position: 'absolute', opacity: dark ? .12 : .09}}>
      <defs><pattern id="grid" width="72" height="72" patternUnits="userSpaceOnUse"><path d="M 72 0 L 0 0 0 72" fill="none" stroke={foreground} strokeWidth="1"/></pattern></defs>
      <rect width="1080" height="1920" fill="url(#grid)"/>
      <circle cx="1070" cy="535" r={310 + frame / 12} fill="none" stroke={foreground} strokeWidth="2"/>
    </svg>
    <div style={{position: 'absolute', left: 80, right: 150, top: 110, display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 30, fontWeight: 600, letterSpacing: '.04em'}}>
      <span>CLAUDE CODE</span><span style={{color: muted}}>モデルの進化編</span>
    </div>
    <div style={{position: 'absolute', left: 80, top: 188, height: 5, width: 850, background: dark ? '#3A5156' : '#D6CFC3'}}>
      <div style={{height: 5, width: `${(frame + 1) / 720 * 100}%`, background: pop}}/>
    </div>
    <div style={{position: 'absolute', left: 80, width: 850, top: 280, opacity: a, transform: `translateY(${(1 - a) * 26}px)`}}>
      {chapter === 0 && <>
        <div style={{fontSize: 35, color: accent, fontWeight: 700, marginBottom: 48}}>2026年 6月 → 9月</div>
        <Hero size={111}>{'たった\n3か月で。'}</Hero>
        <div style={{fontSize: 46, marginTop: 50, lineHeight: 1.55}}>Claude Codeを支える<br/>AIは、どう変わった？</div>
        <div style={{marginTop: 110, display: 'flex', flexDirection: 'column', gap: 20}}>
          {models.map((m, i) => <div key={m.name} style={{opacity: ease(f, 15 + i * 10), display: 'flex', alignItems: 'center', gap: 28, padding: '19px 28px', background: '#FFFFFFAA', borderLeft: `6px solid ${accent}`}}>
            <span style={{fontSize: 30, color: muted, width: 130}}>{['6月', '7月', '9月'][i]}</span><span style={{fontSize: 47, fontWeight: 700}}>{m.name}</span>
          </div>)}
        </div>
      </>}
      {chapter >= 1 && chapter <= 3 && <>
        <div style={{display: 'flex', alignItems: 'center', gap: 24, fontSize: 34, color: pop, fontWeight: 700, marginBottom: 52}}><span style={{fontSize: 60}}>0{chapter}</span><span>{models[modelIndex].date} 発表</span></div>
        <Hero size={103}>{models[modelIndex].name}</Hero>
        <div style={{height: 7, background: pop, marginTop: 30, width: `${ease(f, 6) * 235}px`}}/>
        <div style={{marginTop: 76}}><Hero size={73}>{['長く、複雑な\n開発タスクへ。', '性能 × 効率。\n日々の開発へ。', '問題の根本へ。\n長い作業にも。'][modelIndex]}</Hero></div>
        <div style={{marginTop: 96, background: dark ? '#28434A' : '#FFFFFFA8', padding: '40px 36px', borderRadius: 20, opacity: ease(f, 20)}}>
          <div style={{fontSize: 30, color: muted, marginBottom: 32}}>公式発表のポイント</div>
          {['長い課題を継続して進める', '高度な性能と費用効率', 'コーディングと課題解決'][modelIndex].split('\n').map(t => <div key={t} style={{fontSize: 46, fontWeight: 700}}>{t}</div>)}
          <div style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 38}}>{[0, 1, 2, 3, 4].map(i => <div key={i} style={{height: 13, flex: 1, background: pop, opacity: ease(f, 26 + i * 8)}}/>)}</div>
        </div>
        <div style={{fontSize: 30, color: muted, marginTop: 35}}>出典：Anthropic 公式発表</div>
      </>}
      {chapter === 4 && <>
        <div style={{fontSize: 32, color: pop, fontWeight: 700, marginBottom: 35}}>公式の開発評価で見る</div>
        <Hero size={74}>{'スコアにも、\n変化がある。'}</Hero>
        <div style={{fontSize: 36, marginTop: 34, color: muted}}>Terminal-Bench 4.0</div>
        <div style={{marginTop: 70}}>
          {models.map((m, i) => <div key={m.name} style={{marginBottom: 42}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12, fontSize: 39}}><span>{m.name}</span><b style={{fontSize: 50, color: i === 2 ? '#FFC8A9' : foreground}}>{m.score.toFixed(1)}<span style={{fontSize: 31}}> %</span></b></div>
            <div style={{height: 29, background: '#304C53', position: 'relative'}}>
              <div style={{height: 29, width: `${m.score * ease(f, 8 + i * 7, 24)}%`, background: i === 2 ? '#F2A17E' : '#A8C5C7'}}/>
            </div>
          </div>)}
          <div style={{display: 'flex', justifyContent: 'space-between', color: muted, fontSize: 25}}><span>0%</span><span>50%</span><span>100%</span></div>
        </div>
        <div style={{fontSize: 29, color: muted, marginTop: 38, lineHeight: 1.6}}>Anthropic公表の比較値（2026年9月）<br/>評価条件・出典は概要欄へ</div>
      </>}
      {chapter === 5 && <>
        <div style={{fontSize: 34, color: accent, fontWeight: 700, marginBottom: 54}}>次は、あなたの開発で。</div>
        <Hero size={90}>{'任せる仕事を、\nひとつ\n広げてみる。'}</Hero>
        <div style={{marginTop: 85, display: 'flex', gap: 16}}>{['長い課題', '効率', '解決力'].map((t, i) => <div key={t} style={{flex: 1, padding: '32px 0', textAlign: 'center', fontSize: 38, fontWeight: 700, borderTop: `5px solid ${accent}`, background: '#FFFFFFA8', opacity: ease(f, 14 + i * 10)}}>{t}</div>)}</div>
        <div style={{fontSize: 33, lineHeight: 1.8, marginTop: 64, color: muted}}>Fable 5 ／ Opus 5 ／ Fable 5.1<br/>2026年6月〜9月の公式発表より</div>
      </>}
    </div>
    <div style={{position: 'absolute', top: 1370, left: 80, width: 850, borderTop: `1px solid ${dark ? '#53666A' : '#CBBFB1'}`, paddingTop: 23, fontSize: 26, color: muted, lineHeight: 1.5}}>非公式の解説・編集図解｜Anthropicの提供・協賛ではありません</div>
  </AbsoluteFill></ScreenTypography>;
};
registerRoot(() => <Composition id="ClaudeEvolution30" component={Video} width={1080} height={1920} fps={24} durationInFrames={720} defaultProps={{models: []}}/>);
