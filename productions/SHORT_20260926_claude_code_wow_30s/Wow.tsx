import type {ReactNode} from 'react';
import {AbsoluteFill, Composition, OffthreadVideo, Sequence, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import {ScreenTypography, SCREEN_FONT_FAMILY} from '../../studio/src/remotion/ScreenTypography';

type Segment = {start_ms: number; text: string; caption: string[]};
type Props = {segments: Segment[]; captions: boolean};
const ink = '#101c29', cream = '#fff8ec', mint = '#a9f0d2', orange = '#ee9469';
const ease = (f: number, start = 0, duration = 16) => {
  const t = Math.max(0, Math.min(1, (f - start) / duration));
  return 1 - (1 - t) ** 3;
};
const Text = ({children, size = 86, style = {}}: {children: ReactNode; size?: number; style?: React.CSSProperties}) => {
  if (size < 54) throw new Error('Typography below 54px');
  return <div style={{fontSize: size, fontWeight: 850, lineHeight: 1.24, letterSpacing: '-.045em', whiteSpace: 'pre-line', ...style}}>{children}</div>;
};
const Appear = ({f, start = 0, children, style = {}}: {f: number; start?: number; children: ReactNode; style?: React.CSSProperties}) => {
  const a = ease(f, start);
  return <div style={{opacity: a, transform: `translateY(${(1-a)*35}px) scale(${.97+.03*a})`, ...style}}>{children}</div>;
};
const Check = ({color = mint}: {color?: string}) => <svg width="60" height="60" viewBox="0 0 60 60" style={{flexShrink:0}}><circle cx="30" cy="30" r="27" fill={color}/><path d="m17 30 9 9 18-20" fill="none" stroke={ink} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"/></svg>;
const Panel = ({children, style = {}}: {children: ReactNode; style?: React.CSSProperties}) => <div style={{padding: 34, borderRadius: 30, background:'#fffdf6', color:ink, boxShadow:'0 24px 60px #07101c25', ...style}}>{children}</div>;

const Scene = ({chapter}: {chapter:number}) => {
  const f = useCurrentFrame();
  const video = chapter === 0 || chapter === 5;
  const dark = chapter === 0 || chapter === 2 || chapter === 3 || chapter === 5;
  const fg = dark ? cream : ink;
  const pop = dark ? mint : '#b14c2e';
  return <AbsoluteFill style={{background:dark ? ink : '#f1eadf', color:fg}}>
    {video ? <><OffthreadVideo src={staticFile(chapter === 0 ? 'opening.mp4' : 'closing.mp4')} muted style={{width:'100%',height:'100%',objectFit:'cover'}}/>
      <AbsoluteFill style={{background:'linear-gradient(180deg,#061020b0 0%,#06102020 34%,transparent 56%,#061020a0 77%,#061020ee 100%)'}}/>
    </> : <><svg width="1080" height="1920" style={{position:'absolute',opacity:dark ? .11 : .07}}>
      <defs><pattern id={'grid'+chapter} width="80" height="80" patternUnits="userSpaceOnUse"><path d="M80 0H0V80" fill="none" stroke={fg} strokeWidth="1"/></pattern></defs>
      <rect width="1080" height="1920" fill={`url(#grid${chapter})`}/>
      <circle cx="1020" cy="280" r={240+f*.3} fill="none" stroke={fg} strokeWidth="3"/>
    </svg><div style={{position:'absolute',left:64,top:100,display:'flex',gap:24,alignItems:'center'}}><Text size={54} style={{color:pop}}>0{chapter}</Text><Text size={54}>CLAUDE CODE</Text></div></>}

    {chapter === 0 && <>
      <Appear f={f} style={{position:'absolute',left:330,top:130,width:680,textShadow:'0 4px 22px #000'}}>
        <Text size={98} style={{color:'#ffe3a5'}}>Claude Code</Text><Text size={94} style={{marginTop:16}}>何がすごい？</Text>
      </Appear>
      <div style={{position:'absolute',left:64,top:1244,width:900,display:'flex',gap:12}}>{['考える','つくる','確かめる'].map((t,i)=><Appear key={t} f={f} start={12+i*14} style={{flex:1}}><div style={{background:'#102135e8',border:'2px solid #ffe3a5',borderRadius:20,padding:'30px 4px',textAlign:'center'}}><Text size={66}>{t}</Text></div></Appear>)}</div>
    </>}

    {chapter === 1 && <>
      <Appear f={f} style={{position:'absolute',left:64,top:260,width:900}}><Text size={88}>{'日本語で、\nつくりたいを伝える。'}</Text></Appear>
      <Appear f={f} start={10} style={{position:'absolute',left:64,top:612,width:900}}><Panel>
        <Text size={54} style={{color:'#a44b32',marginBottom:24}}>あなたの依頼</Text>
        <Text size={70}>{'やることリストを\n作って。完了数も見たい。'.slice(0,Math.max(0,Math.floor((f-10)/1.2)))}</Text>
      </Panel></Appear>
      <Appear f={f} start={40} style={{position:'absolute',left:64,top:1038,width:900}}><Panel style={{background:'#d6e8df',padding:32}}>
        <Text size={54} style={{color:'#355849',marginBottom:26}}>まずは手順を整理</Text>
        <div style={{display:'flex',gap:14}}>{['読む','計画する','つくる'].map((t,i)=><div key={t} style={{flex:1,borderTop:'5px solid #4b8973',paddingTop:24,opacity:ease(f,42+i*12)}}><Text size={58}>{t}</Text></div>)}</div>
      </Panel></Appear>
    </>}

    {chapter === 2 && <>
      <Appear f={f} style={{position:'absolute',left:64,top:260,width:900}}><Text size={98}>{'ファイルを越えて、\nまとめて編集。'}</Text></Appear>
      <div style={{position:'absolute',left:80,top:650,width:860}}>{[
        ['画面','ボタンと一覧'],['機能','完了数を数える'],['見た目','色と余白を整える']
      ].map(([title,detail],i)=><Appear key={title} f={f} start={12+i*18} style={{marginBottom:28}}><Panel style={{display:'flex',alignItems:'center',gap:28,padding:'30px 28px',background:'#213448',color:cream,borderLeft:`9px solid ${i===1?orange:mint}`}}>
        <div style={{width:180,flexShrink:0}}><Text size={60} style={{color:i===1?orange:mint,whiteSpace:'nowrap'}}>{title}</Text></div><div style={{flex:1}}><Text size={54}>{detail}</Text><div style={{height:8,borderRadius:8,background:'#486577',marginTop:26,width:`${40+55*ease(f,15+i*18,32)}%`}}/></div><Check/>
      </Panel></Appear>)}</div>
      <Appear f={f} start={72} style={{position:'absolute',left:64,top:1290,width:900}}><Text size={70} style={{textAlign:'center',color:mint}}>ひとつのアプリへ。</Text></Appear>
    </>}

    {chapter === 3 && <>
      <Appear f={f} style={{position:'absolute',left:64,top:260,width:900}}><Text size={98}>{'直す。\nテストで確かめる。'}</Text></Appear>
      <div style={{position:'absolute',left:64,top:646,width:900}}>
        <Panel style={{background:f<47?'#522d36':'#244a42',color:cream,border:`3px solid ${f<47?'#f7a0a8':mint}`,transition:'none'}}>
          <div style={{display:'flex',alignItems:'center',gap:24}}>{f<47?<Text size={74} style={{color:'#ffb4b8'}}>!</Text>:<Check/>}<Text size={64}>{f<47?'完了数が更新されない':'完了数の更新を修正'}</Text></div>
        </Panel>
        <div style={{height:74,display:'flex',justifyContent:'center',alignItems:'center'}}><svg width="38" height="56" viewBox="0 0 38 56"><path d="M19 0v44m-14-12 14 16 14-16" fill="none" stroke={mint} strokeWidth="5"/></svg></div>
        <Panel style={{background:'#213448',color:cream}}><Text size={54} style={{color:'#bfd2db',marginBottom:26}}>動作をチェック</Text>{['追加できる','完了にできる','件数が合う'].map((t,i)=><div key={t} style={{display:'flex',gap:22,alignItems:'center',marginTop:22,opacity:ease(f,50+i*15)}}><Check/><Text size={62}>{t}</Text></div>)}</Panel>
      </div>
    </>}

    {chapter === 4 && <>
      <Appear f={f} style={{position:'absolute',left:64,top:260,width:900}}><Text size={98}>{'対話で、\nもう一歩よくする。'}</Text></Appear>
      <Appear f={f} start={8} style={{position:'absolute',left:64,top:585,width:900}}><Panel style={{padding:30}}>
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',borderBottom:'3px solid #e0dfd6',paddingBottom:22}}><Text size={62}>やることリスト</Text><Text size={54} style={{color:'#39735b'}}>1 / 3 完了</Text></div>
        {['企画を考える','画面をつくる','動きを確認'].map((t,i)=><div key={t} style={{display:'flex',gap:24,alignItems:'center',marginTop:30}}>{i===0?<Check color="#c4e8d3"/>:<div style={{width:56,height:56,border:'3px solid #a7b9b3',borderRadius:12,flexShrink:0}}/>}<Text size={60} style={{color:i===0?'#6a7d75':ink,textDecoration:i===0?'line-through':'none'}}>{t}</Text></div>)}
        <div style={{marginTop:30,padding:'20px 28px',borderRadius:f>50?22:8,background:f>50?'#295f4d':'#607b70',color:'white',textAlign:'center'}}><Text size={60}>＋ 追加する</Text></div>
      </Panel></Appear>
      <Appear f={f} start={32} style={{position:'absolute',left:88,top:1224,width:856}}><Panel style={{background:'#eed3bf',padding:'26px 30px'}}><Text size={58}>{'「ボタンをもっと\n押しやすくして」'}</Text></Panel></Appear>
    </>}

    {chapter === 5 && <>
      <Appear f={f} style={{position:'absolute',left:280,top:135,width:720,textShadow:'0 4px 22px #000'}}><Text size={88} style={{color:'#ffe3a5'}}>{'アイデアを、\n動くカタチに。'}</Text></Appear>
      <Appear f={f} start={18} style={{position:'absolute',left:64,top:1238,width:900}}><Panel style={{background:'#102135e8',color:cream,border:'2px solid #ffe3a5',textAlign:'center',padding:'25px 20px'}}><Text size={67}>まずは、小さなアプリから。</Text></Panel></Appear>
    </>}

    {!video && <div style={{position:'absolute',left:64,top:1466,width:900,color:dark?'#b4cacd':'#586860',fontSize:54,fontWeight:600}}>図解イメージ</div>}
  </AbsoluteFill>;
};

const Wow = ({segments,captions}:Props) => {
  const frame = useCurrentFrame();
  const chapter = Math.min(5,Math.floor(frame/120));
  const f = frame%120;
  return <ScreenTypography><AbsoluteFill style={{fontFamily:SCREEN_FONT_FAMILY,fontSize:54,fontSynthesis:'none',background:ink}}>
    {[0,1,2,3,4,5].map(i=><Sequence key={i} from={i*120} durationInFrames={120}><Scene chapter={i}/></Sequence>)}
    {captions && <div style={{position:'absolute',left:54,top:1570,width:916,boxSizing:'border-box',padding:'24px 20px',minHeight:200,borderRadius:22,background:'#07111af0',border:'2px solid #52616d',opacity:ease(f,2,6)}}><Text size={54} style={{color:cream,lineHeight:1.48,textAlign:'center',fontWeight:750,letterSpacing:'-.04em'}}>{segments[chapter]?.caption.join('\n')}</Text></div>}
    <div style={{position:'absolute',left:64,top:1805,width:900,color:chapter===1||chapter===4?'#586860':'#c4d0d3',fontSize:54,fontWeight:500}}>非公式解説｜出典は概要欄</div>
    <div style={{position:'absolute',left:0,bottom:0,height:9,width:`${(frame+1)/720*100}%`,background:orange}}/>
  </AbsoluteFill></ScreenTypography>;
};
registerRoot(()=><Composition id="ClaudeWow30" component={Wow} durationInFrames={720} fps={24} width={1080} height={1920} defaultProps={{segments:[],captions:true}}/>);
