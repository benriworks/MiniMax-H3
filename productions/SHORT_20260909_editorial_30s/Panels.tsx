import { AbsoluteFill, Composition, Img, registerRoot, staticFile, useCurrentFrame } from 'remotion';
import { ScreenTypography, SCREEN_FONT_FAMILY } from '../../studio/src/remotion/ScreenTypography';

const cream = '#faf9f5';
const orange = '#d97757';
const ink = '#24211f';
const enter = (frame: number, at: number) => 1 - (1 - Math.min(1, Math.max(0, (frame - at) / 14))) ** 3;

// Editorial illustrations only. Never simulate product UI or an actual AI response.
const Panel = ({ kind }: { kind: 'hook' | 'cta' }) => {
  const f = useCurrentFrame();
  return <ScreenTypography><AbsoluteFill style={{ background: kind === 'hook' ? cream : orange, color: ink, fontFamily: SCREEN_FONT_FAMILY, fontSynthesis: 'none', overflow: 'hidden' }}>
    {kind === 'hook' ? <>
      <Img src={staticFile('illustration.png')} style={{ position: 'absolute', height: 1080, width: 1620, left: -170, bottom: 0, objectFit: 'contain', transform: `scale(${1 + f / 239 * .025})` }} />
      <div style={{ position: 'absolute', top: 52, right: 56, fontSize: 34, color: '#585650', fontWeight: 600 }}>コンセプトイラスト</div>
      <div style={{ position: 'absolute', right: 52, top: 178, width: 620, display: 'flex', flexDirection: 'column', gap: 25 }}>
        {[['目的', '開店を知らせる'], ['日付', '9月20日'], ['文字数', '各案40字以内']].map(([label, value], i) => {
          const a = enter(f, 36 + i * 48);
          return <div key={label} style={{ opacity: a, transform: `translateY(${(1 - a) * 30}px)`, background: cream, border: `3px solid ${orange}`, borderRadius: 20, padding: '20px 30px', boxShadow: '0 12px 26px #24211f0e' }}>
            <div style={{ color: '#7a4937', fontSize: 37, fontWeight: 600 }}>{label}</div>
            <div style={{ marginTop: 8, fontSize: 63, fontWeight: 700 }}>{value}</div>
          </div>;
        })}
      </div>
      <div style={{ position: 'absolute', bottom: 52, right: 54, background: ink, color: cream, borderRadius: 15, padding: '20px 30px', fontSize: 44, fontWeight: 700, opacity: enter(f, 178) }}>この条件で、３案ください。</div>
    </> : <>
      <div style={{ position: 'absolute', left: 75, top: 58, right: 75, display: 'flex', justifyContent: 'space-between', fontSize: 38, fontWeight: 600 }}><span>公開前のチェック</span><span>編集図解</span></div>
      <div style={{ position: 'absolute', left: 75, right: 75, top: 180, display: 'flex', gap: 40 }}>
        {[['日付', '9月20日', '実際の予定と照合'], ['文字数', '40字以内', '数えて、必要なら調整']].map(([label, value, note], i) => {
          const a = enter(f, 12 + i * 68);
          return <div key={label} style={{ flex: 1, background: cream, borderRadius: 24, height: 505, padding: '34px 40px', opacity: a, transform: `translateY(${(1 - a) * 45}px)` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 42, color: '#7a4937', fontWeight: 600 }}><span>0{i + 1}</span><span>{label}</span></div>
            <div style={{ marginTop: 40, fontWeight: 700, fontSize: 104 }}>{value}</div>
            <div style={{ height: 6, background: orange, marginTop: 26, width: `${enter(f, 35 + i * 68) * 100}%` }} />
            <div style={{ marginTop: 36, fontSize: 44, fontWeight: 600 }}>{note}</div>
          </div>;
        })}
      </div>
      <div style={{ position: 'absolute', left: 75, right: 75, bottom: 126, fontSize: 53, fontWeight: 700, color: cream, background: ink, padding: '20px 30px', borderRadius: 15, opacity: enter(f, 135) }}>下書き → 自分で確認 → 公開</div>
      <div style={{ position: 'absolute', left: 75, bottom: 45, fontSize: 31, fontWeight: 500 }}>依頼条件の例です。AIの回答が条件を満たすとは限りません。</div>
    </>}
  </AbsoluteFill></ScreenTypography>;
};

const Root = () => <>
  <Composition id="EditorialHook30" component={Panel} width={1920} height={1080} fps={24} durationInFrames={240} defaultProps={{ kind: 'hook' as const }} />
  <Composition id="EditorialCta30" component={Panel} width={1920} height={1080} fps={24} durationInFrames={240} defaultProps={{ kind: 'cta' as const }} />
</>;
registerRoot(Root);
