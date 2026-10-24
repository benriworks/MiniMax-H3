import {useEffect} from 'react';
import {AbsoluteFill,Composition,OffthreadVideo,Sequence,staticFile,useCurrentFrame,delayRender,continueRender,cancelRender} from 'remotion';
import {ScreenTypography,SCREEN_FONT_FAMILY} from './ScreenTypography';
import {CreatorCaption,CreatorHeadline,CutAccent,Rise,ShortsGuides} from './ShortsMotionPrimitives';
import {BUSINESS_COLORS as B,SHORTS_COLORS as C,SHORTS_SAFE as S,cameraMotion,validateCreatorProps} from './shortsMotion';
import type {CreatorScene,CreatorShortProps} from './shortsMotion';
import {FeatureDiagram,FeatureStatistic} from './FeatureDiagram';
import {EditorialScene} from './EditorialScene';

const Tick=({done=true}:{done?:boolean})=><svg width="60" height="60" viewBox="0 0 60 60" style={{flexShrink:0}}><rect x="2" y="2" width="56" height="56" rx="18" fill={done?C.lime:'#ffffff10'} stroke={done?C.lime:'#a6b3c0'} strokeWidth="3"/>{done&&<path d="m16 30 10 10 19-22" fill="none" stroke={C.ink} strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"/>}</svg>;
function Scene({scene,index}:{scene:CreatorScene;index:number}){
  const f=useCurrentFrame(),light=scene.tone==='light',ink=light?C.ink:C.paper;
  const motion=cameraMotion(f,scene.duration,index);
  const items=scene.items??[];
  if(scene.kind==='editorial'||scene.kind==='source')return <EditorialScene scene={scene} index={index}/>;
  return <AbsoluteFill style={{background:light?C.paper:C.ink,color:ink,overflow:'hidden'}}>
    {scene.media?<>
      <OffthreadVideo src={staticFile(scene.media)} trimBefore={scene.mediaStart??0} muted style={{width:'100%',height:'100%',objectFit:'cover',transform:`scale(${motion.scale}) translateX(${motion.x}px)`}}/>
      <AbsoluteFill style={{background:'linear-gradient(180deg,#060c1dde, #060c1d55 34%,transparent 53%,#060c1d22 65%,#060c1de8)'}}/>
    </>:<>
      <svg width="1080" height="1920" style={{position:'absolute',opacity:light?.12:.19}}><defs><pattern id={'dots'+index} width="48" height="48" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1.4" fill={ink}/></pattern></defs><rect width="1080" height="1920" fill={`url(#dots${index})`}/><circle cx={910-f*.6} cy={500+f*.3} r="385" fill="none" stroke={light?'#bb7255':C.blue} strokeWidth="2"/></svg>
      <div aria-hidden style={{position:'absolute',left:660,top:470,fontSize:520,fontWeight:900,lineHeight:1,color:light?'#0b112008':'#ffffff05'}}>{String(index+1).padStart(2,'0')}</div>
    </>}
    <div data-shorts-important style={{position:'absolute',left:S.left,top:218,display:'flex',alignItems:'center',gap:18,fontSize:54,fontWeight:750,letterSpacing:'.025em'}}><span style={{width:12,height:46,background:light?'#a3482a':C.lime}}/>{scene.eyebrow}</div>
    <CreatorHeadline text={scene.headline} accent={light?'':scene.accent} color={ink} style={{position:'absolute',left:S.left,top:335,width:S.width,textShadow:scene.media?'0 3px 30px #0009':undefined}}/>

    {scene.kind==='quote'&&<Rise delay={9} style={{position:'absolute',top:730,left:S.left,width:S.width}}>
      <div style={{padding:'34px 36px 40px',borderRadius:30,background:light?'#fff':'#19243a',boxShadow:'0 25px 65px #0002',border:`2px solid ${light?'#ddd3c4':'#31405a'}`}}>
        <div style={{fontSize:54,color:light?'#a3482a':C.lime,fontWeight:700,marginBottom:26}}>あなたのひとこと</div>
        <div data-shorts-important style={{fontSize:78,fontWeight:800,lineHeight:1.4,whiteSpace:'pre-line',letterSpacing:'-.045em'}}>{scene.body}</div>
      </div>
      <div style={{width:32,height:32,background:light?'#fff':'#19243a',transform:'rotate(45deg)',marginLeft:64,marginTop:-18}}/>
    </Rise>}
    {(scene.kind==='steps'||scene.kind==='cards')&&<div style={{position:'absolute',left:S.left,top:695,width:S.width}}>
      {items.map((item,i)=><Rise key={i} delay={8+i*9} style={{marginBottom:24}}><div style={{display:'flex',alignItems:'center',gap:26,padding:'28px 30px',borderRadius:24,background:light?'#fff':'#1c2940',borderLeft:`8px solid ${i===1?C.coral:light?'#508476':C.lime}`,boxShadow:'0 14px 30px #0001'}}>
        {scene.kind==='steps'&&<div style={{fontSize:56,fontWeight:800,color:light?'#a3482a':C.lime,width:66,flexShrink:0}}>{String(i+1).padStart(2,'0')}</div>}
        <div data-shorts-important style={{flex:1,display:scene.kind==='cards'?'flex':'block',alignItems:'center',gap:24}}><div style={{fontSize:66,fontWeight:850,letterSpacing:'-.035em',minWidth:scene.kind==='cards'?180:undefined}}>{item.label}</div>{item.detail&&<div style={{fontSize:54,color:light?'#52635e':'#b8c8df',letterSpacing:'-.025em'}}>{item.detail}</div>}</div>
      </div></Rise>)}
    </div>}
    {scene.kind==='checklist'&&<Rise delay={8} style={{position:'absolute',left:S.left,top:660,width:S.width}}>
      <div style={{background:light?'#fff':'#17283b',borderRadius:30,padding:26,boxShadow:'0 28px 60px #0002',border:`2px solid ${light?'#dadfd4':'#33475c'}`}}>
        <div data-shorts-important style={{fontSize:54,lineHeight:1.2,fontWeight:800,borderBottom:`2px solid ${light?'#dfdfd4':'#385064'}`,paddingBottom:16}}>{scene.body??'できたこと'}</div>
        {items.map((item,i)=><Rise key={i} delay={16+i*10}><div style={{display:'flex',alignItems:'center',gap:24,marginTop:20}}><Tick done={item.done!==false}/><span data-shorts-important style={{fontSize:60,lineHeight:1.1,fontWeight:700,letterSpacing:'-.035em'}}>{item.label}</span></div></Rise>)}
        <Rise delay={38}><div data-shorts-important style={{marginTop:24,padding:14,background:light?'#235848':C.lime,color:light?'#fff':C.ink,borderRadius:18,textAlign:'center',fontSize:60,lineHeight:1.1,fontWeight:800}}>{scene.action??'チェック完了'}</div></Rise>
      </div>
    </Rise>}
    {scene.kind==='compare'&&<div style={{position:'absolute',left:S.left,top:670,width:S.width}}>
      {items.map((item,i)=><Rise key={i} delay={8+i*20}><div style={{padding:'24px 28px',background:i===0?'#472c38':'#183f3e',color:C.paper,borderRadius:24,border:`2px solid ${i===0?C.coral:C.lime}`,marginBottom:24,transform:`translateX(${i===0?-6:6}px)`}}>
        <div style={{fontSize:54,lineHeight:1.2,fontWeight:800,color:i===0?C.coral:C.lime,marginBottom:12}}>{i===0?'BEFORE':'AFTER'}</div>
        <div data-shorts-important style={{fontSize:66,lineHeight:1.1,fontWeight:850,letterSpacing:'-.035em'}}>{item.label}</div>
      </div></Rise>)}
    </div>}
    {scene.kind==='hero'&&scene.body&&<Rise delay={13} style={{position:'absolute',left:S.left,top:1110,width:S.width}}><div data-shorts-important style={{display:'inline-block',color:C.ink,background:C.lime,padding:'18px 26px',fontSize:62,fontWeight:850,boxShadow:'0 10px 30px #0003',borderRadius:14}}>{scene.body}</div></Rise>}
    {scene.kind==='diagram'&&<FeatureDiagram scene={scene}/>}
    {scene.kind==='stat'&&<FeatureStatistic scene={scene}/>}
    <CutAccent index={index}/>
  </AbsoluteFill>;
}
export function CreatorShortComposition(props:CreatorShortProps){
  const value=validateCreatorProps(props),f=useCurrentFrame();
  useEffect(()=>{
    const handle=delayRender('Shorts safe-area layout check');
    document.fonts.ready.then(()=>{
      for(const el of document.querySelectorAll<HTMLElement>('[data-shorts-important]')){
        const box=el.getBoundingClientRect();
        // Remotion's canvas is scaled in the Player; use canvas-relative geometry.
        const canvas=el.closest('[data-creator-canvas]')!.getBoundingClientRect();
        const scale=canvas.width/1080;
        const left=(box.left-canvas.left)/scale,right=(box.right-canvas.left)/scale;
        const top=(box.top-canvas.top)/scale,bottom=(box.bottom-canvas.top)/scale;
        if(left<60||right>912||top<198||bottom>1490||el.scrollWidth>el.clientWidth+2){
          cancelRender(new Error(`Shorts text outside safe area at frame ${f}: ${el.textContent?.slice(0,30)} (${left},${top},${right},${bottom})`));return;
        }
      }
      continueRender(handle);
    }).catch(cancelRender);
    return ()=>continueRender(handle);
  },[f]);
  const cue=value.captions.find(c=>f>=c.start&&f<c.end);
  const activeStyle=value.scenes.find(scene=>f>=scene.from&&f<scene.from+scene.duration)?.visual_style;
  return <ScreenTypography><AbsoluteFill data-creator-canvas style={{fontFamily:SCREEN_FONT_FAMILY,fontSynthesis:'none',background:C.ink}}>
    {value.scenes.map((scene,i)=><Sequence key={scene.id} from={scene.from} durationInFrames={scene.duration}><Scene scene={scene} index={i}/></Sequence>)}
    {/* Keep 66px type: two lines, padding, border and the 12px entrance fit below 1490. */}
    {cue&&<AbsoluteFill style={{transform:'translateY(-33px)',pointerEvents:'none'}}><CreatorCaption text={cue.text} age={f-cue.start} visualStyle={activeStyle}/></AbsoluteFill>}
    <div aria-hidden style={{position:'absolute',top:172,left:S.left,width:S.width,display:'flex',gap:8}}>{value.scenes.map(scene=><div key={scene.id} style={{height:6,flex:scene.duration,background:activeStyle==='business'?B.line:'#ffffff33',overflow:'hidden',borderRadius:6}}><div style={{height:'100%',background:activeStyle==='business'?B.accent:C.lime,width:`${Math.max(0,Math.min(1,(f-scene.from)/scene.duration))*100}%`}}/></div>)}</div>
    {value.showGuides&&<ShortsGuides/>}
  </AbsoluteFill></ScreenTypography>;
}
const demo:CreatorShortProps={title:'Shorts Creator',durationInFrames:240,scenes:[{id:'preview',kind:'quote',from:0,duration:120,eyebrow:'SHORTS',headline:'伝えたいことを、\n動きに。',body:'ここに短い依頼を。',tone:'light'},{id:'end',kind:'steps',from:120,duration:120,eyebrow:'CREATE',headline:'ひとつずつ、\n形にしよう。',items:[{label:'考える'},{label:'つくる'}]}],captions:[]};
export const CreatorShortRegistration=()=> <Composition id="CreatorShort" component={CreatorShortComposition} width={1080} height={1920} fps={24} durationInFrames={240} defaultProps={demo} calculateMetadata={({props})=>({durationInFrames:validateCreatorProps(props).durationInFrames})}/>;
