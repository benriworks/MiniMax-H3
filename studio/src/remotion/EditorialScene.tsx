import type {CSSProperties,ReactNode} from 'react';
import {AbsoluteFill,Img,OffthreadVideo,staticFile,useCurrentFrame} from 'remotion';
import type {CreatorScene} from './shortsMotion';
import {BUSINESS_COLORS as B,displayUnits,headlineSize,outCubic,SHORTS_COLORS as C} from './shortsMotion';

const Block=({children,style}:{children:ReactNode;style?:CSSProperties})=><div data-shorts-important style={{position:'absolute',left:72,width:828,...style}}>{children}</div>;
const card:CSSProperties={borderRadius:26,padding:'30px 32px',boxSizing:'border-box',fontSize:66,fontWeight:850,letterSpacing:'-.035em'};
const legacyLayouts=new Set(['hook','parallel','conversation','closing']);
const colors=[C.blue,C.lime,C.coral] as const;
const captionStyle:CSSProperties={fontSize:54,lineHeight:1.15,fontWeight:700,whiteSpace:'pre-line'};
const lineSize=(text:string|undefined,preferred:number,width=760)=>Math.max(54,Math.min(preferred,Math.floor(width/Math.max(1,...(text??'').split('\n').map(displayUnits)))));
const palette={
  memory:{bg:'#e9ddff',ink:'#211436',accent:'#7141bc',panel:'#fff9ff',muted:'#675575'},
  channels:{bg:'#082f37',ink:'#f5fbfa',accent:'#9af0d2',panel:'#164751',muted:'#b0d6dc'},
  calendar:{bg:'#fbefd8',ink:'#3b2d1b',accent:'#a15420',panel:'#fffaf0',muted:'#705f47'},
  research:{bg:'#102440',ink:'#edf5ff',accent:'#9bddff',panel:'#193b5e',muted:'#b3cce2'},
  permissions:{bg:'#fde2d7',ink:'#391f24',accent:'#a82f45',panel:'#fff7ee',muted:'#755259'},
  contrast:{bg:'#e9eee8',ink:'#18352b',accent:'#1e7358',panel:'#ffffff',muted:'#536b60'},
  statement:{bg:'#dfff78',ink:'#172920',accent:'#376c3b',panel:'#f5ffd8',muted:'#46643d'},
  recap:{bg:'#201a36',ink:'#f8f3ff',accent:'#ceb4ff',panel:'#35294f',muted:'#cec1e3'},
} as const;
const SemanticPhrase=({text}:{text:string})=><>{text.split(/(?<=[・→、])/u).map((part,i)=><span key={`${i}-${part}`} style={{display:'inline-block',whiteSpace:displayUnits(part)<=8?'nowrap':'normal'}}>{part}</span>)}</>;
const demonstrationLabels={before:'入力', 'first-output':'初回出力', revision:'修正', after:'仕上がり', export:'書き出し'} as const;

/** Let the guide carry the opening and closing; keep the face clear of text. */
function FullscreenPresenterEditorial({scene,frame,progress}:{scene:CreatorScene;frame:number;progress:number}){
  const business=scene.visual_style==='business',enter=outCubic(frame/10);
  const accent=business?'#e3d6b9':C.lime;
  const supporting=[...(scene.items??[]).map(item=>`${item.label}${item.detail?`：${item.detail}`:''}`),...(scene.action?[scene.action]:[])];
  const step=Math.max(1,Math.floor(scene.duration/Math.max(1,supporting.length)));
  const support=supporting[Math.min(supporting.length-1,Math.floor(frame/step))];
  const supportEnter=outCubic((frame%step)/6);
  const scale=(business?1.01:1.05)+progress*.035;
  const playFrames=scene.mediaPlayFrames??scene.duration;
  const summary=playFrames<scene.duration?outCubic((frame-playFrames+6)/12):0;
  return <AbsoluteFill style={{background:'#090e18',color:'#fff',overflow:'hidden'}}>
    <div aria-hidden style={{position:'absolute',inset:0,background:`radial-gradient(ellipse at 70% 35%,${business?'#314e43':'#2a3b42'},#090e18 70%)`}}/>
    {frame<playFrames&&<AbsoluteFill data-shorts-visual data-presenter-treatment="fullscreen" style={{opacity:1-summary}}>
      <OffthreadVideo src={staticFile(scene.media!)} trimBefore={scene.mediaStart??0} muted style={{display:'block',width:'100%',height:'100%',objectFit:'cover',objectPosition:'center 32%',transform:`scale(${scale})`,transformOrigin:'center 32%'}}/>
    </AbsoluteFill>}
    <AbsoluteFill aria-hidden style={{background:'linear-gradient(180deg,rgba(5,10,18,.18) 0%,transparent 24%,transparent 43%,rgba(5,10,18,.58) 53%,rgba(5,10,18,.88) 69%,rgba(5,10,18,.68) 100%)'}}/>
    <div aria-hidden style={{position:'absolute',left:72,top:909-summary*240,width:94+70*enter,height:7,borderRadius:4,background:accent}}/>
    <Block style={{top:940-summary*240,fontSize:54,fontWeight:business?650:800,lineHeight:1.1,color:accent,textShadow:'0 3px 16px #0009'}}>{scene.body??scene.eyebrow}</Block>
    <Block style={{top:1015-summary*240,fontSize:headlineSize(scene.headline,82),fontWeight:business?800:950,lineHeight:1.1,letterSpacing:'-.035em',whiteSpace:'pre-line',textShadow:'0 4px 24px #0009',opacity:.8+.2*enter,transform:`translateY(${8*(1-enter)}px)`}}>{scene.headline}</Block>
    {support&&<Block style={{top:1210-summary*200,fontSize:lineSize(support,54,800),fontWeight:700,lineHeight:1.08,paddingLeft:18,borderLeft:`5px solid ${accent}`,boxSizing:'border-box',color:'#fff',textShadow:'0 3px 16px #0009',opacity:.65+.35*supportEnter,transform:`translateY(${5*(1-supportEnter)}px)`}}>{support}</Block>}
  </AbsoluteFill>;
}

/** Opt-in evidence-first presentation; captured pixels are never recolored or animated. */
function BusinessEditorial({scene,frame}:{scene:CreatorScene;frame:number}){
  const enter=outCubic(frame/12),capture=scene.capture,items=scene.items??[],width=scene.media?492:828;
  const demonstration=capture?.origin==='demonstration';
  const domain=capture&&!demonstration?new URL(capture.source_url).hostname:'';
  const sourceLabel=capture?.origin==='demonstration'?demonstrationLabels[capture.phase]:domain;
  const officialCredits:Record<string,string>={'learn.chatgpt.com':'OpenAI公式資料','support.claude.com':'Anthropic公式資料','claude.com':'Anthropic公式資料','www.php.net':'PHP公式資料','www.ipa.go.jp':'IPA公式資料','www.jpcert.or.jp':'JPCERT/CC公式資料'};
  const credit=capture?.origin==='demonstration'?`こちらの実演・${capture.product}`:`引用：${officialCredits[domain]??domain}`;
  return <AbsoluteFill style={{background:B.paper,color:B.ink,overflow:'hidden'}}>
    <Block style={{top:216,fontSize:54,fontWeight:650,lineHeight:1.16,color:B.muted}}>{scene.eyebrow}</Block>
    <Block style={{top:320,fontSize:headlineSize(scene.headline,84),fontWeight:800,lineHeight:1.15,letterSpacing:'-.035em',whiteSpace:'pre-line',transform:`translateY(${8*(1-enter)}px)`,opacity:.8+.2*enter}}>{scene.headline}</Block>
    {scene.kind==='source'&&capture?<>
      <Block style={{top:532,fontSize:54,fontWeight:650,lineHeight:1.14,color:B.muted}}>{sourceLabel}</Block>
      <div data-shorts-visual style={{position:'absolute',left:72,top:610,width:828,height:550,background:'#fff',border:`1px solid ${B.line}`,boxSizing:'border-box',borderRadius:12,overflow:'hidden'}}>
        <Img alt={capture.title} src={staticFile(capture.image)} style={{display:'block',width:'100%',height:'100%',objectFit:'contain'}}/>
      </div>
      <Block style={{top:1180,fontSize:54,fontWeight:650,lineHeight:1.14,color:B.muted}}>{credit}</Block>
    </>:<>
      {scene.media&&<div data-shorts-visual style={{position:'absolute',left:600,top:650,width:300,height:534,background:B.panel,border:`1px solid ${B.line}`,borderRadius:18,overflow:'hidden'}}>
        <OffthreadVideo src={staticFile(scene.media)} trimBefore={scene.mediaStart??0} muted style={{display:'block',width:'100%',height:'100%',objectFit:'contain'}}/>
      </div>}
      {scene.body&&<Block style={{top:650,width,fontSize:lineSize(scene.body,62,width),fontWeight:650,lineHeight:1.28,letterSpacing:'-.025em',whiteSpace:'pre-line'}}>{scene.body}</Block>}
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{top:(items.length===3?755:855)+i*150,width,paddingLeft:20,borderLeft:`3px solid ${B.accent}`,boxSizing:'border-box',opacity:.8+.2*outCubic((frame-i*3)/12)}}>
        <div style={{fontSize:54,fontWeight:750,lineHeight:1.12,letterSpacing:'-.025em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,fontWeight:500,lineHeight:1.1,marginTop:8,color:B.muted,letterSpacing:'-.025em'}}>{item.detail}</div>}
      </Block>)}
      {scene.stat&&<Block style={{top:900,width,fontSize:lineSize(scene.stat,92,width),fontWeight:750,lineHeight:1.15,letterSpacing:'-.03em',color:B.accent}}>{scene.stat}</Block>}
      {scene.action&&<Block style={{top:1190,fontSize:54,fontWeight:650,lineHeight:1.14,color:B.muted}}>{scene.action}</Block>}
    </>}
  </AbsoluteFill>;
}

/** Opt-in on-air guide: the PNG stays unchanged; only its display framing moves. */
function PresenterEditorial({scene,index,frame,progress}:{scene:CreatorScene;index:number;frame:number;progress:number}){
  const theme=palette[scene.editorial_layout as keyof typeof palette]??palette.statement;
  const presenter=scene.presenter,hook=(presenter?.role??(index===0?'hook':'recap'))==='hook',items=scene.items??[];
  const enter=outCubic(frame/11),float=Math.sin(progress*Math.PI*2)*3;
  const reveal=(i:number)=>outCubic((frame-4-i*5)/12);
  const columns=items.length||1,cardWidth=(828-16*(columns-1))/columns;
  return <AbsoluteFill style={{background:theme.bg,color:theme.ink,overflow:'hidden'}}>
    <div aria-hidden style={{position:'absolute',left:hook?-100:420,top:hook?670:520,width:730,height:730,borderRadius:'50%',background:`radial-gradient(circle,${theme.accent}26,${theme.accent}00 70%)`}}/>
    <div aria-hidden style={{position:'absolute',left:74,top:1580,width:828,height:2,background:`${theme.accent}28`}}/>
    <Block style={{top:216,...captionStyle,opacity:.85}}>{scene.eyebrow}</Block>
    <Block style={{top:335,fontSize:headlineSize(scene.headline,100),fontWeight:950,lineHeight:1.12,letterSpacing:'-.05em',whiteSpace:'pre-line',transform:`translateY(${12*(1-enter)}px)`,opacity:.65+.35*enter}}>{scene.headline}</Block>

    <div data-shorts-visual style={{position:'absolute',left:hook?72:600,top:(hook?650:580)+12*(1-enter)+float,width:hook?430:300,height:hook?620:350,overflow:'hidden',borderRadius:hook?'100px 100px 30px 30px':'80px 80px 20px 20px',maskImage:'linear-gradient(#000 0%,#000 91%,transparent 100%)',opacity:.7+.3*enter}}>
      {scene.media?<OffthreadVideo src={staticFile(scene.media)} trimBefore={scene.mediaStart??0} muted style={{display:'block',width:'100%',height:'100%',objectFit:'cover',objectPosition:'center 25%'}}/>:presenter&&<Img alt="番組ナビゲーター" src={staticFile(presenter.image)} style={{position:'absolute',width:hook?650:480,height:hook?975:720,left:hook?-110:-90,top:0,objectFit:'contain',filter:`drop-shadow(0 16px 18px ${theme.ink}22)`}}/>}
    </div>

    {hook?<>
      {scene.body&&<Block style={{left:500,top:652,width:400,fontSize:54,fontWeight:850,lineHeight:1.18,letterSpacing:'-.045em',whiteSpace:'pre-line'}}>{scene.body}</Block>}
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{left:500,top:805+i*224,width:400,height:208,boxSizing:'border-box',padding:'12px',borderRadius:24,background:i?theme.accent:theme.panel,color:i?theme.bg:theme.ink,boxShadow:`0 15px 30px ${theme.ink}12`,transform:`translateY(${9*(1-reveal(i))}px)`,opacity:.65+.35*reveal(i)}}>
        <div aria-hidden style={{position:'absolute',left:-13,top:38,width:28,height:28,background:i?theme.accent:theme.panel,transform:'rotate(45deg)',borderRadius:4}}/>
        <div style={{position:'relative',fontSize:54,fontWeight:950,lineHeight:1.03,letterSpacing:'-.04em'}}>{item.label}</div>
        {item.detail&&<div style={{position:'relative',fontSize:54,fontWeight:650,lineHeight:1.03,letterSpacing:'-.04em',marginTop:8,opacity:.85}}>{item.detail}</div>}
      </Block>)}
      {items.length===1&&scene.stat&&<Block style={{left:528,top:1065,width:372,fontSize:lineSize(scene.stat,90,360),fontWeight:950,lineHeight:1.1,color:theme.accent,letterSpacing:'-.05em'}}>{scene.stat}</Block>}
    </>:<>
      {scene.body&&<Block style={{left:72,top:665,width:495,fontSize:60,fontWeight:850,lineHeight:1.25,letterSpacing:'-.045em',whiteSpace:'pre-line'}}><SemanticPhrase text={scene.body}/></Block>}
      {items.length===3?<Block style={{top:945,display:'flex',flexDirection:'column',gap:5}}>{items.map((item,i)=><div key={`${i}-${item.label}`} style={{height:76,boxSizing:'border-box',padding:'9px 18px',display:'flex',gap:14,alignItems:'center',background:theme.panel,borderRadius:18,borderLeft:`6px solid ${colors[(i+index)%3]}`,opacity:.65+.35*reveal(i)}}>
        <div style={{width:240,flexShrink:0,fontSize:54,fontWeight:950,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,fontWeight:650,lineHeight:1,color:theme.muted,letterSpacing:'-.045em'}}>{item.detail}</div>}
      </div>)}</Block>:<Block style={{top:945,display:'flex',gap:16}}>{items.map((item,i)=><div key={`${i}-${item.label}`} style={{width:cardWidth,height:220,boxSizing:'border-box',padding:'13px 12px',background:theme.panel,borderRadius:24,borderTop:`6px solid ${colors[(i+index)%3]}`,opacity:.65+.35*reveal(i)}}>
        <div style={{fontSize:lineSize(item.label,60,cardWidth-24),fontWeight:950,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,fontWeight:650,lineHeight:1,marginTop:10,color:theme.muted,letterSpacing:'-.045em'}}>{item.detail}</div>}
      </div>)}</Block>}
      {scene.action&&<Block style={{top:1195,...captionStyle,fontWeight:850,color:theme.accent}}>{scene.action}</Block>}
    </>}
  </AbsoluteFill>;
}

/** Abstract editorial diagrams. These are deliberately distinct from product UI. */
function ExtendedEditorial({scene,index,frame,progress}:{scene:CreatorScene;index:number;frame:number;progress:number}){
  const layout=scene.editorial_layout as keyof typeof palette;
  const theme=palette[layout],items=scene.items??[],enter=outCubic(frame/11);
  const reveal=(i:number)=>outCubic((frame-i*5)/12);
  return <AbsoluteFill style={{background:theme.bg,color:theme.ink,overflow:'hidden'}}>
    <div aria-hidden style={{position:'absolute',left:610,top:495,width:720,height:720,borderRadius:layout==='calendar'?100:'50%',border:`3px solid ${theme.accent}20`,transform:`rotate(${progress*12}deg)`}}/>
    <div aria-hidden style={{position:'absolute',left:-360,top:1090,width:800,height:800,borderRadius:'50%',background:`${theme.accent}0b`}}/>
    <Block style={{top:216,...captionStyle,opacity:.85}}>{scene.eyebrow}</Block>
    <Block style={{top:335,fontSize:headlineSize(scene.headline,100),fontWeight:950,lineHeight:1.12,letterSpacing:'-.05em',whiteSpace:'pre-line',transform:`translateY(${12*(1-enter)}px)`,opacity:.65+.35*enter}}>{scene.headline}</Block>
    {scene.body&&layout!=='statement'&&<Block style={{top:680,...captionStyle,color:theme.muted}}>{scene.body}</Block>}

    {layout==='memory'&&<>
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{top:755+i*140,left:72+i*14,width:800-i*14,boxSizing:'border-box',height:132,padding:'10px 26px 10px 40px',borderRadius:'4px 24px 24px 4px',background:theme.panel,borderLeft:`9px solid ${theme.accent}`,boxShadow:`0 ${9-i*2}px 18px ${theme.ink}0d`,transform:`translateY(${9*(1-reveal(i))}px)`,opacity:.6+.4*reveal(i)}}>
        <div style={{fontSize:54,fontWeight:900,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,lineHeight:1,color:theme.muted,marginTop:4,letterSpacing:'-.035em'}}>{item.detail}</div>}
      </Block>)}
    </>}

    {layout==='channels'&&<>
      <svg aria-hidden width="828" height="410" viewBox="0 0 828 410" style={{position:'absolute',left:72,top:755}}>
        {items.map((item,i)=><path key={`${i}-${item.label}`} d={`M 145 ${60+i*135} C 335 ${60+i*135},310 202,540 202`} fill="none" stroke={`${theme.accent}70`} strokeWidth="5" strokeDasharray="10 13" strokeDashoffset={-frame*2}/>) }
      </svg>
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{left:72,top:755+i*140,width:460,height:132,padding:item.detail?'9px 22px':'28px 22px',boxSizing:'border-box',borderRadius:24,background:theme.panel,border:`2px solid ${theme.accent}50`,opacity:.6+.4*reveal(i)}}>
        <div style={{fontSize:lineSize(item.label,item.detail?54:62,416),fontWeight:850,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,lineHeight:1,color:theme.muted,marginTop:4,letterSpacing:'-.04em'}}>{item.detail}</div>}
      </Block>)}
      <Block style={{left:605,top:840,width:295,height:295,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',borderRadius:'50%',background:theme.accent,color:theme.bg,boxShadow:`0 0 ${40+10*Math.sin(frame*.09)}px ${theme.accent}20`}}>
        <div style={{fontSize:lineSize(scene.stat??'dot',76,260),fontWeight:950,letterSpacing:'-.045em',lineHeight:1.1}}>{scene.stat??'dot'}</div>
        <div aria-hidden style={{display:'flex',gap:9,alignItems:'center',height:60,marginTop:18}}>{Array.from({length:9},(_,i)=><div key={i} style={{width:7,height:14+30*(.5+.5*Math.sin(frame*.2+i*1.1)),borderRadius:9,background:theme.bg,opacity:.6}}/>)}</div>
      </Block>
    </>}

    {layout==='calendar'&&<>
      <Block style={{top:758,width:352,height:345,background:theme.panel,border:`3px solid ${theme.accent}30`,borderRadius:28,padding:'28px 22px',boxSizing:'border-box',boxShadow:`0 15px 24px ${theme.ink}0a`}}>
        <div style={{fontSize:lineSize(scene.stat??'',82,300),fontWeight:950,letterSpacing:'-.06em',textAlign:'center'}}>{scene.stat}</div>
        <div aria-hidden style={{display:'grid',gridTemplateColumns:'repeat(5, 1fr)',gap:12,marginTop:28}}>{Array.from({length:15},(_,i)=><div key={i} style={{height:42,borderRadius:8,background:i===Math.min(14,Math.floor(progress*15))?theme.accent:`${theme.accent}${i<5?'38':'14'}`,transform:i===Math.min(14,Math.floor(progress*15))?'scale(1.12)':undefined}}/>)}</div>
      </Block>
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{top:754+i*140,left:460,width:440,height:132,boxSizing:'border-box',padding:'10px 18px',borderLeft:`6px solid ${theme.accent}`,opacity:.6+.4*reveal(i)}}>
        <div style={{fontSize:54,fontWeight:900,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,lineHeight:1,color:theme.muted,marginTop:4,letterSpacing:'-.05em'}}>{item.detail}</div>}
      </Block>)}
    </>}

    {layout==='research'&&<>
      <svg aria-hidden width="828" height="390" viewBox="0 0 828 390" style={{position:'absolute',left:72,top:755}}>
        <path d="M 80 52 L 270 52 L 395 310 L 740 310 M 78 178 L 317 178 M 80 310 L 395 310" fill="none" stroke={`${theme.accent}55`} strokeWidth="5"/>
        <circle cx={80+progress*660} cy="310" r="12" fill={theme.accent}/>
      </svg>
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{top:755+i*140,left:72+i*37,width:754-i*37,height:132,boxSizing:'border-box',padding:'9px 26px',background:theme.panel,borderRadius:22,border:`2px solid ${theme.accent}40`,transform:`translateY(${9*(1-reveal(i))}px)`,opacity:.6+.4*reveal(i)}}>
        <div style={{fontSize:54,fontWeight:850,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,lineHeight:1,color:theme.muted,marginTop:4,letterSpacing:'-.035em'}}>{item.detail}</div>}
      </Block>)}
    </>}

    {layout==='permissions'&&<>
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{top:755+i*140,height:132,boxSizing:'border-box',borderRadius:24,padding:'8px 24px',background:theme.panel,display:'flex',gap:22,alignItems:'center',border:`2px solid ${theme.accent}20`,opacity:.6+.4*reveal(i)}}>
        <div aria-hidden style={{width:82,height:82,borderRadius:item.done?'50%':20,background:item.done?'#265d49':theme.accent,display:'flex',alignItems:'center',justifyContent:'center',flexShrink:0}}>
          <svg width="54" height="54" viewBox="0 0 54 54">{item.done?<path d="m10 27 12 12 23-25" stroke="#fff" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" fill="none"/>:<><path d="M20 13v28M34 13v28" stroke="#fff" strokeWidth="7" strokeLinecap="round"/></>}</svg>
        </div>
        <div style={{minWidth:0,flex:1}}><div style={{fontSize:54,fontWeight:900,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>{item.detail&&<div style={{fontSize:54,lineHeight:1,marginTop:4,color:theme.muted,letterSpacing:'-.035em'}}>{item.detail}</div>}</div>
      </Block>)}
    </>}

    {layout==='contrast'&&<>
      {items.slice(0,2).map((item,i)=><Block key={`${i}-${item.label}`} style={{top:775+i*185,height:170,boxSizing:'border-box',padding:'16px 28px 16px 110px',borderRadius:28,background:i?theme.accent:theme.panel,color:i?'#fff':theme.ink,boxShadow:'0 12px 24px #102b2110',opacity:.6+.4*reveal(i)}}>
        <div aria-hidden style={{position:'absolute',left:30,top:32,fontSize:64,fontWeight:900,lineHeight:1}}>{i+1}</div>
        <div style={{fontSize:lineSize(item.label,60,680),fontWeight:950,lineHeight:1.1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,lineHeight:1,marginTop:8,opacity:.8,letterSpacing:'-.035em'}}>{item.detail}</div>}
      </Block>)}
    </>}

    {layout==='statement'&&<>
      <div aria-hidden style={{position:'absolute',left:90,top:741,width:775,height:398,borderRadius:46,background:theme.panel,transform:`rotate(${-1+progress*2}deg)`,boxShadow:'0 24px 60px #21401a10'}}/>
      <Block style={{top:scene.stat?755:816,left:104,width:764,fontSize:lineSize(scene.body,scene.stat?72:100,750),fontWeight:950,lineHeight:1.35,letterSpacing:'-.045em',whiteSpace:'pre-line'}}>{scene.body}</Block>
      {scene.stat&&<Block style={{top:965,left:104,width:764,fontSize:lineSize(scene.stat,120,750),fontWeight:950,lineHeight:1.1,color:theme.accent,letterSpacing:'-.06em'}}>{scene.stat}</Block>}
    </>}

    {layout==='recap'&&<>
      {items.map((item,i)=><Block key={`${i}-${item.label}`} style={{top:755+i*140,height:132,boxSizing:'border-box',padding:'10px 24px 10px 112px',background:theme.panel,borderRadius:24,borderLeft:`6px solid ${colors[i%3]}`,opacity:.6+.4*reveal(i)}}>
        <div aria-hidden style={{position:'absolute',left:24,top:21,fontSize:64,fontWeight:950,color:colors[i%3],letterSpacing:'-.05em'}}>{String(i+1).padStart(2,'0')}</div>
        <div style={{fontSize:54,fontWeight:900,lineHeight:1,letterSpacing:'-.035em'}}>{item.label}</div>
        {item.detail&&<div style={{fontSize:54,lineHeight:1,marginTop:4,color:theme.muted,letterSpacing:'-.035em'}}>{item.detail}</div>}
      </Block>)}
    </>}
    {scene.action&&<Block style={{top:1180,...captionStyle,fontWeight:800,color:theme.accent}}>{scene.action}</Block>}
    <div aria-hidden style={{position:'absolute',left:72,top:1550,width:828,height:2,background:`${theme.accent}30`}}/>
    <div aria-hidden style={{position:'absolute',left:72+(index%3)*24,top:1610,width:48,height:48,borderRadius:'50%',background:theme.accent,opacity:.25}}/>
  </AbsoluteFill>;
}

export function EditorialScene({scene,index}:{scene:CreatorScene;index:number}){
  const f=useCurrentFrame(),p=Math.min(1,f/Math.max(1,scene.duration-1));
  const entrance=outCubic(f/9),layout=scene.editorial_layout;
  const light=scene.kind==='source'||layout==='hook'||layout==='closing';
  const ink=light?C.ink:C.paper,bg=layout==='hook'?'#f6e6cf':layout==='closing'?'#dfff78':light?'#f5f1e8':C.ink;
  if(scene.kind==='editorial'&&scene.media)return <FullscreenPresenterEditorial scene={scene} frame={f} progress={p}/>;
  if(scene.visual_style==='business')return <BusinessEditorial scene={scene} frame={f}/>;
  if(scene.presenter||(scene.kind==='editorial'&&scene.media))return <PresenterEditorial scene={scene} index={index} frame={f} progress={p}/>;
  if(scene.kind==='editorial'&&layout&&!legacyLayouts.has(layout))return <ExtendedEditorial scene={scene} index={index} frame={f} progress={p}/>;
  return <AbsoluteFill style={{background:bg,color:ink,overflow:'hidden'}}>
    <div aria-hidden style={{position:'absolute',width:1000,height:1000,borderRadius:'50%',border:`3px solid ${light?'#0b112012':'#ffffff0e'}`,top:620-f*.4,left:400-f*.2}}/>
    <Block style={{top:216,fontSize:54,fontWeight:800,letterSpacing:'.015em',opacity:.85}}>{scene.eyebrow}</Block>
    <Block style={{top:335,fontSize:headlineSize(scene.headline,108),fontWeight:950,lineHeight:1.12,letterSpacing:'-.055em',whiteSpace:'pre-line',transform:`translateY(${12*(1-entrance)}px)`,opacity:.6+.4*entrance}}>{scene.headline}</Block>

    {layout==='hook'&&<>
      <Block style={{top:680,fontSize:160,fontWeight:950,letterSpacing:'-.07em'}}>1 <span style={{color:'#a3482a'}}>→</span> 2</Block>
      <Block style={{top:955,display:'flex',gap:24}}>{['調査','資料整理'].map((text,i)=><div key={text} style={{...card,width:402,background:i?'#0b1120':'#fff',color:i?'#fff':C.ink,transform:`translateY(${16*Math.sin((p+i*.5)*Math.PI)}px)`,borderBottom:`8px solid ${i?C.coral:'#508476'}`}}>{text}</div>)}</Block>
      <Block style={{top:1160,fontSize:54,fontWeight:750}}>仕事を分けて進める。</Block>
    </>}

    {layout==='parallel'&&<>
      <Block style={{top:620,fontSize:54,color:C.blue}}>たとえば、企画の準備</Block>
      {['競合調査','資料整理'].map((text,i)=><Block key={text} style={{top:735+i*225,...card,background:i?'#392938':'#173c42',border:`2px solid ${i?C.coral:C.blue}`}}>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}><span>{text}</span><span style={{fontSize:54,color:i?C.coral:C.blue}}>{i?'整理中':'調査中'}</span></div>
        <div aria-hidden style={{height:12,marginTop:28,background:'#ffffff20',borderRadius:8,overflow:'hidden'}}><div style={{width:`${22+Math.min(1,Math.max(0,(p-i*.13)))*64}%`,height:'100%',background:i?C.coral:C.blue}}/></div>
      </Block>)}
    </>}

    {layout==='conversation'&&<>
      <Block style={{top:695,...card,background:C.lime,color:C.ink,fontSize:76,lineHeight:1.4}}>資料整理を先に。</Block>
      <Block style={{top:930,...card,background:'#1c2940',borderLeft:`10px solid ${C.coral}`,fontSize:60}}>資料整理を優先</Block>
      <Block style={{top:1105,fontSize:54,color:'#b8c8df'}}>作業中も、会話を続けられる。</Block>
    </>}

    {scene.kind==='source'&&scene.capture&&<>
      <Block style={{top:615,fontSize:54,color:'#52635e',fontWeight:650}}>learn.chatgpt.com</Block>
      <Block style={{top:710,height:390,background:'#fff',borderRadius:20,boxShadow:'0 22px 70px #0b11201a',overflow:'hidden'}}>
        <Img alt={`${scene.capture.title}の該当箇所`} src={staticFile(scene.capture.image)} style={{width:'100%',height:'100%',objectFit:'contain',display:'block'}}/>
      </Block>
      <Block style={{top:1170,fontSize:54,color:'#52635e'}}>引用：OpenAI公式資料</Block>
    </>}

    {layout==='closing'&&<>
      <Block style={{top:745,fontSize:92,fontWeight:950,lineHeight:1.3,letterSpacing:'-.05em'}}>何を、<br/>同時に任せたい？</Block>
      <Block style={{top:1110,fontSize:54,fontWeight:800}}>次回：記憶と好み</Block>
    </>}
    <div aria-hidden style={{position:'absolute',right:170,top:640,width:18,height:18,borderRadius:'50%',background:index%2?C.coral:'#508476',opacity:.5}}/>
  </AbsoluteFill>;
}
