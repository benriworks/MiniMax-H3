import {useCurrentFrame} from 'remotion';
import {Rise} from './ShortsMotionPrimitives';
import {SHORTS_COLORS as C,SHORTS_SAFE as S,outCubic} from './shortsMotion';
import type {CreatorScene,FeatureGraphic} from './shortsMotion';
import {WebRuntimeDiagram} from './WebRuntimeDiagram';

/** Original symbolic motion graphics; these are not replicas of product UI. */
function Icon({kind}:{kind:FeatureGraphic}){
  const f=useCurrentFrame();
  const common={fill:'none',stroke:'currentColor',strokeWidth:5,strokeLinecap:'round' as const,strokeLinejoin:'round' as const};
  return <svg aria-hidden viewBox="0 0 120 120" width="100%" height="100%" {...common}>
    {kind==='cloud'&&<><path d="M30 86h61a18 18 0 0 0 0-36 31 31 0 0 0-60-5 21 21 0 0 0-1 41Z"/><path d="M60 75V46m-12 12 12-12 12 12"/></>}
    {kind==='laptop'&&<><rect x="23" y="25" width="74" height="57" rx="6"/><path d="m23 82-11 13h96L97 82M49 94h22"/><path d="m43 52 11 10 23-23"/></>}
    {kind==='apps'&&<><rect x="12" y="13" width="35" height="35" rx="9"/><rect x="73" y="13" width="35" height="35" rx="9"/><rect x="12" y="73" width="35" height="35" rx="9"/><rect x="73" y="73" width="35" height="35" rx="9"/><path d="M47 30h26M30 48v25M90 48v25M47 90h26"/></>}
    {kind==='parallel'&&<><circle cx="60" cy="23" r="13"/><path d="M60 36v23M23 81V59h74v22M60 59v22"/><rect x="10" y="83" width="26" height="23" rx="6"/><rect x="47" y="83" width="26" height="23" rx="6"/><rect x="84" y="83" width="26" height="23" rx="6"/></>}
    {kind==='memory'&&<><path d="M31 21h62a8 8 0 0 1 8 8v72H39a8 8 0 0 1-8-8Z"/><path d="M31 36H17v69M47 43h37M47 59h30M47 75h18"/><circle cx="89" cy="87" r="20" fill={C.ink}/><path d="m79 87 7 7 13-14"/></>}
    {kind==='chat'&&<><path d="M17 22h86v61H51L28 101V83H17Z"/>{[0,1,2,3,4].map(i=>{const h=12+22*(.5+.5*Math.sin(f*.18+i*1.4));return <path key={i} d={`M${34+i*13} ${53-h/2}v${h}`}/>;})}</>}
    {kind==='schedule'&&<><rect x="17" y="23" width="86" height="80" rx="10"/><path d="M17 45h86M37 14v18M82 14v18M36 63h12M36 82h12"/><circle cx="79" cy="79" r="20"/><path d="M79 67v13l9 5"/></>}
    {kind==='research'&&<><circle cx="51" cy="50" r="33"/><path d="m76 76 28 28M33 58l13-14 13 9 12-20"/></>}
    {kind==='control'&&<><path d="m60 12 37 15v30c0 28-22 46-37 53-15-7-37-25-37-53V27Z"/><path d="m39 57 15 16 28-31"/></>}
    {kind==='release'&&<><path d="m60 10 12 34 35 16-35 14-12 36-13-36-34-14 34-16Z"/><circle cx="95" cy="19" r="4" fill="currentColor"/><circle cx="19" cy="102" r="3" fill="currentColor"/></>}
  </svg>;
}

export function FeatureDiagram({scene}:{scene:CreatorScene}){
  const f=useCurrentFrame(),light=scene.tone==='light',items=scene.items??[],color=light?'#235848':C.lime;
  const surface=light?'#fff':'#18283d',stroke=light?'#b6c9be':'#354c64';
  const centerY=items.length?140:220;
  if(scene.graphic==='web-services'||scene.graphic==='web-flow')return <WebRuntimeDiagram flow={scene.graphic==='web-flow'}/>;
  return <div style={{position:'absolute',left:S.left,top:660,width:S.width,height:590,color}}>
    <svg aria-hidden width="828" height="530" style={{position:'absolute',inset:0}}>
      <circle cx="414" cy={centerY} r={items.length?123:168} fill="none" stroke={stroke} strokeWidth="2"/>
      <circle cx="414" cy={centerY} r={items.length?140:189} fill="none" stroke={color} strokeWidth="4" strokeDasharray="50 1000" transform={`rotate(${f*2} 414 ${centerY})`}/>
      {items.map((_,i)=>{const x=(i+.5)*828/items.length;return <path key={i} d={`M414 ${centerY+120}V285H${x}V327`} fill="none" stroke={i===1?C.coral:color} strokeWidth="5" strokeDasharray="1000" strokeDashoffset={1000*(1-outCubic((f-10-i*3)/22))}/>;})}
    </svg>
    <Rise delay={3} style={{position:'absolute',left:items.length?330:299,top:centerY-(items.length?84:115),width:items.length?168:230,height:items.length?168:230}}><Icon kind={scene.graphic!}/></Rise>
    {items.map((item,i)=><Rise key={i} delay={15+i*6} style={{position:'absolute',left:i*828/items.length+7,top:330,width:828/items.length-14}}><div style={{background:surface,border:`2px solid ${stroke}`,borderTop:`7px solid ${i===1?C.coral:color}`,borderRadius:25,padding:'25px 6px',boxShadow:'0 20px 45px #0001'}}><div data-shorts-important style={{fontSize:54,fontWeight:850,textAlign:'center',color:light?C.ink:C.paper,whiteSpace:'nowrap',letterSpacing:'-.04em'}}>{item.label}</div></div></Rise>)}
    {scene.body&&<Rise delay={22} style={{position:'absolute',top:items.length?487:442,width:'100%',textAlign:'center'}}><div data-shorts-important style={{fontSize:60,fontWeight:850,lineHeight:1.2,color:light?C.ink:C.paper,whiteSpace:'pre-line'}}>{scene.body}</div></Rise>}
  </div>;
}

export function FeatureStatistic({scene}:{scene:CreatorScene}){
  const f=useCurrentFrame(),light=scene.tone==='light',p=outCubic(f/13);
  return <div style={{position:'absolute',left:S.left,top:735,width:S.width,textAlign:'center'}}>
    <div style={{height:6,background:light?'#b6c9be':'#354c64',marginBottom:40,transform:`scaleX(${p})`}}/>
    <div data-shorts-important style={{fontSize:Math.min(150,Math.floor(800/Math.max(1,[...scene.stat!].reduce((n,c)=>n+(c.charCodeAt(0)<128?.54:1),0)))),fontWeight:900,letterSpacing:'-.04em',color:light?'#235848':C.lime,transform:`scale(${.86+p*.14})`,whiteSpace:'nowrap'}}>{scene.stat}</div>
    <Rise delay={12}><div data-shorts-important style={{fontSize:60,fontWeight:800,lineHeight:1.5,whiteSpace:'pre-line',marginTop:38}}>{scene.body}</div></Rise>
  </div>;
}
