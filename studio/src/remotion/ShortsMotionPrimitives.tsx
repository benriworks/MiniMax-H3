import type {CSSProperties,ReactNode} from 'react';
import {AbsoluteFill,useCurrentFrame} from 'remotion';
import {BUSINESS_COLORS,SHORTS_SAFE,SHORTS_COLORS,headlineSize,titleMotion,outCubic} from './shortsMotion';
import {SCREEN_FONT_FAMILY} from './ScreenTypography';

export function CreatorHeadline({text,accent='',color=SHORTS_COLORS.paper,preferred=108,style={}}:{text:string;accent?:string;color?:string;preferred?:number;style?:CSSProperties}) {
  const frame=useCurrentFrame(), motion=titleMotion(frame);
  const parts=accent?text.split(accent):[text];
  return <div data-shorts-important style={{fontFamily:SCREEN_FONT_FAMILY,fontWeight:900,fontSize:headlineSize(text,preferred),lineHeight:1.16,letterSpacing:'-.035em',whiteSpace:'pre-line',color,opacity:motion.opacity,transform:`translateY(${motion.y}px) scale(${motion.scale})`,transformOrigin:'left center',...style}}>
    {parts.map((part,i)=><span key={i}>{i>0&&<span style={{color:SHORTS_COLORS.lime}}>{accent}</span>}{part}</span>)}
  </div>;
}
export function CreatorCaption({text,age,visualStyle}:{text:string;age:number;visualStyle?:'business'}) {
  const rise=outCubic(age/4),business=visualStyle==='business';
  return <div data-shorts-important style={{position:'absolute',left:SHORTS_SAFE.left,top:SHORTS_SAFE.captionTop,width:SHORTS_SAFE.width,display:'flex',justifyContent:'center',transform:`translateY(${(1-rise)*12}px)`,opacity:.7+.3*rise}}>
    <div style={{fontFamily:SCREEN_FONT_FAMILY,fontSize:66,fontWeight:business?650:850,lineHeight:1.3,letterSpacing:'-.025em',textAlign:'center',whiteSpace:'pre-line',color:'#fff',background:business?BUSINESS_COLORS.ink:'#0b1120ed',padding:'17px 23px',borderRadius:business?12:18,boxShadow:business?'none':'0 8px 30px #0003',borderBottom:business?`3px solid ${BUSINESS_COLORS.accent}`:`5px solid ${SHORTS_COLORS.lime}`}}>{text}</div>
  </div>;
}
export function CutAccent({index}:{index:number}) {
  const f=useCurrentFrame();
  if(index===0||f>5)return null;
  const p=outCubic(f/5);
  return <AbsoluteFill aria-hidden style={{background:SHORTS_COLORS.lime,transform:`translateX(${100+p*100}%)`,left:'-200%',width:'200%',opacity:.22*(1-p),pointerEvents:'none'}}/>;
}
export function Rise({children,delay=0,style={}}:{children:ReactNode;delay?:number;style?:CSSProperties}) {
  const f=useCurrentFrame(),p=outCubic((f-delay)/9);
  return <div style={{opacity:p,transform:`translateY(${(1-p)*28}px)`,...style}}>{children}</div>;
}
export const ShortsGuides=()=> <AbsoluteFill aria-hidden style={{pointerEvents:'none'}}>
  <div style={{position:'absolute',left:SHORTS_SAFE.left,top:SHORTS_SAFE.top,width:SHORTS_SAFE.width,height:SHORTS_SAFE.bottom-SHORTS_SAFE.top,border:'3px dashed #43e6b8',boxShadow:'0 0 0 600px #f0475930'}}/>
  <div style={{position:'absolute',top:1520,left:72,fontSize:40,color:'#fff'}}>表示UIの余白（制作上の目安）</div>
</AbsoluteFill>;
