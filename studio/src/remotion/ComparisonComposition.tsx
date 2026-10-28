import {useEffect} from 'react';
import type {CSSProperties,ReactNode} from 'react';
import {AbsoluteFill,Composition,Img,OffthreadVideo,Sequence,cancelRender,continueRender,delayRender,staticFile,useCurrentFrame} from 'remotion';
import {SCREEN_FONT_FAMILY,ScreenTypography} from './ScreenTypography';
import {ShortsGuides} from './ShortsMotionPrimitives';
import {BUSINESS_COLORS as B,outCubic,SHORTS_SAFE as S} from './shortsMotion';
import {presenterTransition,validateComparisonProps} from './comparisonMotion';
import type {ComparisonPanel,ComparisonProps,ComparisonScene} from './comparisonMotion';

const BLUE='#526f87';
const Box=({children,style}:{children:ReactNode;style?:CSSProperties})=><div data-shorts-important style={{position:'absolute',left:S.left,width:S.width,boxSizing:'border-box',whiteSpace:'pre-line',...style}}>{children}</div>;
function Symbol({kind,color=B.accent,size=76,close=0}:{kind?:ComparisonPanel['icon'];color?:string;size?:number;close?:number}){
  return <svg aria-hidden width={size} height={size} viewBox="0 0 80 80" fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
    {kind==='cloud'?<path d="M20 59H62C80 57 77 35 63 34C61 9 26 10 22 31C3 28 1 58 20 59Z"/>:
      kind==='laptop'?<><g transform={`translate(0 ${55*close*.85}) scale(1 ${1-close*.85})`}><rect x="13" y="14" width="54" height="41" rx="4"/></g><path d="M7 63H73M23 63L28 55H52L58 63"/></>:
      kind==='clock'?<><circle cx="40" cy="40" r="29"/><path d="M40 20V40L56 49"/></>:
      kind==='calendar'?<><rect x="12" y="19" width="56" height="48" rx="6"/><path d="M12 33H68M25 12V25M55 12V25M25 46H34M45 46H54M25 56H34"/></>:
      kind==='message'?<><path d="M14 14H66V53H36L19 67V53H14Z"/><path d="M25 28H55M25 40H45"/></>:
      kind==='eye'?<><path d="M6 40Q40 1 74 40Q40 79 6 40Z"/><circle cx="40" cy="40" r="12"/></>:
      kind==='handoff'?<><path d="M9 26H63L52 15M63 26L52 37M71 54H17L28 43M17 54L28 65"/></>:
      kind==='meter'?<><rect x="10" y="21" width="60" height="39" rx="7"/><path d="M25 31V50M40 31V50M55 31V50"/></>:
      <><path d="M18 8H49L64 24V72H18Z"/><path d="M49 8V24H64M29 37H52M29 49H52M29 61H46"/></>}
  </svg>;
}
function Panel({panel,top,height=234,index,frame,layout}:{panel:ComparisonPanel;top:number;height?:number;index:number;frame:number;layout:string}){
  const color=panel.tone==='blue'?BLUE:B.accent,reveal=outCubic((frame-index*10)/16),compact=layout==='workspace';
  return <div style={{position:'absolute',left:72,top,width:828,height,boxSizing:'border-box',border:`2px solid ${B.line}`,borderLeft:`6px solid ${color}`,borderRadius:22,background:B.panel,opacity:panel.state==='muted'?.75:1,transform:`translateY(${8*(1-reveal)}px)`}}>
    <div aria-hidden style={{position:'absolute',left:22,top:compact?32:24}}><Symbol kind={panel.icon} color={color} close={panel.motion==='close'?outCubic((frame-12)/30):0}/></div>
    <Box style={{left:126,top:compact?12:18,width:672,fontSize:60,fontWeight:750,lineHeight:1.16,letterSpacing:'-.025em',color}}>{panel.label}</Box>
    {panel.detail&&<Box style={{left:126,top:compact?81:99,width:672,fontSize:54,fontWeight:600,lineHeight:1.2,letterSpacing:'-.02em'}}>{panel.detail}</Box>}
    {layout==='signal'&&<div aria-hidden style={{position:'absolute',left:27,top:129,display:'flex',gap:8}}>{[0,1,2].map(i=><span key={i} style={{width:12,height:12,borderRadius:'50%',background:color,opacity:frame>12+index*10+i*12?.7:.15}}/>)}</div>}
    {layout==='availability'&&<div aria-hidden style={{position:'absolute',left:126,bottom:17,display:'flex',gap:9}}>{[0,1,2,3].map(i=><span key={i} style={{width:125,height:4,background:color,opacity:.2+.35*outCubic((frame-12-i*5)/14)}}/>)}</div>}
  </div>;
}
function Diagram({scene}:{scene:Extract<ComparisonScene,{kind:'comparison'}>}){
  const frame=useCurrentFrame(),workspace=scene.layout==='workspace';
  return <>
    {workspace&&<div aria-hidden style={{position:'absolute',left:360,top:563,width:252,height:240,display:'flex',alignItems:'center',justifyContent:'center',borderRadius:48,background:'#e4ebe4'}}><Symbol kind="cloud" size={180}/><div style={{position:'absolute',left:102,top:133,width:48,height:8,borderRadius:5,background:B.accent,opacity:.35+.35*Math.sin(frame/14)**2}}/>{scene.connection==='local'&&<svg width="828" height="75" style={{position:'absolute',top:235,left:-288}}><path d="M414 0V45M405 34L414 45L423 34" fill="none" stroke={B.accent} strokeWidth="4" strokeDasharray="8 8" strokeDashoffset={-frame%16}/></svg>}</div>}
    {scene.layout==='fictional_case'&&<svg aria-hidden width="48" height="40" style={{position:'absolute',left:462,top:875}}><path d="M24 1V31M13 20L24 31L35 20" fill="none" stroke={B.accent} strokeWidth="4"/></svg>}
    {scene.panels.map((panel,index)=><Panel key={index} panel={panel} top={workspace?850+index*166:638+index*282} height={workspace?151:234} index={index} frame={frame} layout={scene.layout}/>)}
    {scene.note&&<Box style={{top:1168,fontSize:54,lineHeight:1.14,fontWeight:600,color:B.muted}}>{scene.note}</Box>}
  </>;
}
function Source({scene}:{scene:Extract<ComparisonScene,{kind:'source'}>}){
  const capture=scene.capture,credit=capture?.source_url.includes('learn.chatgpt.com')?'引用：OpenAI公式資料':'引用：Anthropic公式資料';
  return <>
    {(scene.points??[]).map((point,index)=><Box key={index} style={{top:548+index*70,fontSize:54,lineHeight:1.13,fontWeight:650,color:B.muted}}>{point}</Box>)}
    <div data-shorts-visual style={{position:'absolute',left:72,top:710,width:828,height:430,border:`1px solid ${B.line}`,borderRadius:14,background:'#fff',overflow:'hidden',display:'flex',alignItems:'center',justifyContent:'center'}}>
      {capture?<Img alt={capture.title} src={staticFile(capture.image)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>:<div data-shorts-important style={{width:720,fontSize:62,lineHeight:1.4,fontWeight:650,textAlign:'center',whiteSpace:'pre-line'}}>{scene.fixtureLabel}</div>}
    </div>
    <Box style={{top:1168,fontSize:54,lineHeight:1.14,fontWeight:600,color:B.muted}}>{capture?credit:'素材未取得・確認用'}</Box>
  </>;
}
function Presenter({scene}:{scene:Extract<ComparisonScene,{kind:'presenter'}>}){
  const frame=useCurrentFrame(),play=scene.mediaPlayFrames??scene.duration,videoOn=frame<play;
  const summary=Boolean(scene.media)&&!videoOn;
  return <>
    {!summary&&<div data-shorts-visual style={{position:'absolute',left:550,top:555,width:350,height:605,borderRadius:24,overflow:'hidden',background:'#e4e8e2'}}>
      {scene.media?<Sequence durationInFrames={play}><OffthreadVideo src={staticFile(scene.media)} trimBefore={scene.mediaStart??0} muted style={{width:'100%',height:'100%',objectFit:'contain'}}/></Sequence>:<>
        <svg aria-hidden width="350" height="625"><circle cx="175" cy="170" r="64" fill="#b5c1b8"/><path d="M45 540V380Q45 270 175 270Q305 270 305 380V540" fill="#b5c1b8"/></svg>
        <div data-shorts-important style={{position:'absolute',left:20,top:405,width:310,fontSize:54,lineHeight:1.3,textAlign:'center',whiteSpace:'pre-line'}}>{'動画素材\n待機中'}</div>
      </>}
    </div>}
    {scene.points.map((point,index)=><Box key={index} style={{top:(summary?650:622)+index*(summary?210:238),width:summary?828:442,fontSize:summary?76:54,lineHeight:1.25,fontWeight:750,color:index?BLUE:B.accent,paddingLeft:summary?30:0,borderLeft:summary?`5px solid ${index?BLUE:B.accent}`:undefined}}>{point}</Box>)}
    {scene.note&&<Box style={{top:1168,fontSize:54,lineHeight:1.14,color:B.muted,fontWeight:650}}>{scene.note}</Box>}
  </>;
}
function ImmersivePresenter({scene}:{scene:Extract<ComparisonScene,{kind:'presenter'}>}){
  const frame=useCurrentFrame(),play=scene.mediaPlayFrames??scene.duration;
  const {videoOn,wipe,summaryOn,summaryAge}=presenterTransition(frame,play),entry=outCubic(frame/10),summaryEntry=outCubic(summaryAge/10);
  return <AbsoluteFill style={{background:B.paper,color:B.ink,overflow:'hidden'}}>
    {videoOn&&<>
      <AbsoluteFill data-shorts-visual style={{overflow:'hidden'}}>
        <Sequence durationInFrames={play}><OffthreadVideo src={staticFile(scene.media!)} trimBefore={scene.mediaStart??0} muted style={{width:'100%',height:'100%',objectFit:'cover',objectPosition:'center center'}}/></Sequence>
        <AbsoluteFill style={{background:'linear-gradient(180deg,rgba(15,22,25,.64) 0%,rgba(15,22,25,.24) 13%,rgba(15,22,25,0) 25%,rgba(15,22,25,0) 39%,rgba(15,22,25,.62) 51%,rgba(15,22,25,.88) 69%,rgba(15,22,25,.94) 100%)'}}/>
      </AbsoluteFill>
      <Box style={{top:216,fontSize:54,lineHeight:1.16,fontWeight:650,color:'#fff',textShadow:'0 2px 12px #1118',opacity:1-wipe}}>{scene.eyebrow}</Box>
      <Box style={{top:scene.headline.includes('\n')?805:850,fontSize:84,lineHeight:1.15,fontWeight:800,letterSpacing:'-.035em',color:'#fff',textShadow:'0 3px 20px #1118',transform:`translateY(${12*(1-entry)}px)`,opacity:entry*(1-wipe)}}>{scene.headline}</Box>
      {scene.points.map((point,index)=><Box key={index} style={{top:1015+index*76,fontSize:60,lineHeight:1.15,fontWeight:700,color:index?'#d1e4f0':'#e4efdf',textShadow:'0 2px 12px #1118',opacity:entry*(1-wipe)}}>{point}</Box>)}
      {scene.note&&<Box style={{top:1168,fontSize:54,lineHeight:1.14,color:'#fff',fontWeight:650,opacity:1-wipe}}>{scene.note}</Box>}
    </>}
    <AbsoluteFill aria-hidden style={{background:B.paper,transform:`translateY(${1920*(1-wipe)}px)`}}/>
    {summaryOn&&<>
      <Box style={{top:216,fontSize:54,lineHeight:1.16,fontWeight:650,color:B.muted}}>{scene.eyebrow}</Box>
      <Box style={{top:320,fontSize:84,lineHeight:1.15,fontWeight:800,letterSpacing:'-.035em',transform:`translateY(${12*(1-summaryEntry)}px)`,opacity:summaryEntry}}>{scene.headline}</Box>
      {scene.points.map((point,index)=>{const reveal=outCubic((summaryAge-index*4)/10);return <Box key={index} style={{top:650+index*210,fontSize:76,lineHeight:1.25,fontWeight:750,color:index?BLUE:B.accent,paddingLeft:30,borderLeft:`5px solid ${index?BLUE:B.accent}`,transform:`translateY(${18*(1-reveal)}px)`,opacity:reveal}}>{point}</Box>;})}
      {scene.note&&<Box style={{top:1168,fontSize:54,lineHeight:1.14,color:B.muted,fontWeight:650}}>{scene.note}</Box>}
    </>}
  </AbsoluteFill>;
}
function Scene({scene,presenterTreatment}:{scene:ComparisonScene;presenterTreatment?:ComparisonProps['presenterTreatment']}){
  const frame=useCurrentFrame(),entry=outCubic(frame/12);
  if(scene.kind==='presenter'&&scene.media&&presenterTreatment==='immersive')return <ImmersivePresenter scene={scene}/>;
  return <AbsoluteFill style={{background:B.paper,color:B.ink,overflow:'hidden'}}>
    <Box style={{top:216,fontSize:54,lineHeight:1.16,fontWeight:650,color:B.muted}}>{scene.eyebrow}</Box>
    <Box style={{top:320,fontSize:84,lineHeight:1.15,fontWeight:800,letterSpacing:'-.035em',transform:`translateY(${8*(1-entry)}px)`,opacity:.8+.2*entry}}>{scene.headline}</Box>
    {scene.kind==='source'?<Source scene={scene}/>:scene.kind==='presenter'?<Presenter scene={scene}/>:<Diagram scene={scene}/>}
  </AbsoluteFill>;
}
function ComparisonCaption({text,age}:{text:string;age:number}){
  const entry=outCubic(age/4);
  return <Box style={{top:1300,display:'flex',justifyContent:'center',opacity:.8+.2*entry,transform:`translateY(${6*(1-entry)}px)`}}>
    <div style={{fontSize:62,fontWeight:650,lineHeight:1.18,letterSpacing:'-.02em',textAlign:'center',whiteSpace:'pre-line',color:'#fff',background:B.ink,padding:'14px 23px',borderRadius:12,borderBottom:`3px solid ${B.accent}`}}>{text}</div>
  </Box>;
}
/** Runs after the pinned font is mounted; every frame checks the real text boxes. */
function SafeArea({frame}:{frame:number}){
  useEffect(()=>{
    const handle=delayRender('Comparison text-safe-area check');let disposed=false;
    document.fonts.ready.then(()=>{
      if(disposed)return;
      for(const el of document.querySelectorAll<HTMLElement>('[data-comparison-canvas] [data-shorts-important]')){
        const box=el.getBoundingClientRect(),canvas=el.closest('[data-comparison-canvas]')!.getBoundingClientRect(),scale=canvas.width/1080;
        const left=(box.left-canvas.left)/scale,right=(box.right-canvas.left)/scale,top=(box.top-canvas.top)/scale,bottom=(box.bottom-canvas.top)/scale;
        if(left<60||right>912||top<198||bottom>1490||el.scrollWidth>el.clientWidth+2){cancelRender(new Error(`Comparison text outside safe area at frame ${frame}: ${el.textContent} (${left},${top},${right},${bottom})`));return;}
      }
      continueRender(handle);
    }).catch(error=>{if(!disposed)cancelRender(error);});
    return ()=>{disposed=true;continueRender(handle);};
  },[frame]);
  return null;
}
export function ComparisonComposition(props:ComparisonProps){
  const value=validateComparisonProps(props),frame=useCurrentFrame(),cue=value.captions.find(c=>frame>=c.start&&frame<c.end);
  return <ScreenTypography><AbsoluteFill data-comparison-canvas style={{background:B.paper,fontFamily:SCREEN_FONT_FAMILY,fontSynthesis:'none'}}>
    {value.scenes.map(scene=><Sequence key={scene.id} from={scene.from} durationInFrames={scene.duration}><Scene scene={scene} presenterTreatment={value.presenterTreatment}/></Sequence>)}
    {cue&&<ComparisonCaption text={cue.text} age={frame-cue.start}/>}
    <div aria-hidden style={{position:'absolute',left:72,top:172,width:828,height:6,display:'flex',gap:7}}>{value.scenes.map(scene=><div key={scene.id} style={{flex:scene.duration,background:B.line,borderRadius:4,overflow:'hidden'}}><div style={{height:'100%',background:B.accent,width:`${Math.max(0,Math.min(1,(frame-scene.from)/scene.duration))*100}%`}}/></div>)}</div>
    {value.mode==='fixture'&&<div style={{position:'absolute',top:1555,left:72,width:828,fontSize:54,color:B.muted}}>内部確認用・音声と素材は未確定</div>}
    {value.showGuides&&<ShortsGuides/>}<SafeArea frame={frame}/>
  </AbsoluteFill></ScreenTypography>;
}
const preview:ComparisonProps={mode:'fixture',title:'Comparison layout preview',durationInFrames:1440,captions:[],scenes:Array.from({length:8},(_,index)=>({id:`fixture-${index}`,from:index*180,duration:180,kind:'comparison',layout:'decision',eyebrow:'構成確認用',headline:'使いたい流れを\n比べる。',panels:[{label:'確認すること',detail:'条件を確かめる',icon:'document'},{label:'次の操作',detail:'手順を見比べる',icon:'handoff',tone:'blue'}]}))};
export const ComparisonRegistration=()=> <Composition id="ProductComparison" component={ComparisonComposition} width={1080} height={1920} fps={24} durationInFrames={1440} defaultProps={preview} calculateMetadata={({props})=>({durationInFrames:validateComparisonProps(props).durationInFrames})}/>;
