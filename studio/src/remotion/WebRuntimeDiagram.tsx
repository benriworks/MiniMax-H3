import type {CSSProperties} from 'react';
import {useCurrentFrame} from 'remotion';
import {outCubic,SHORTS_SAFE as S} from './shortsMotion';

/** A conceptual server-side runtime, not a screenshot or a claim about all sites. */
export function WebRuntimeDiagram({flow}:{flow:boolean}){
  const f=useCurrentFrame(),request=outCubic((f-5)/24),processing=outCubic((f-30)/18),reply=outCubic((f-60)/24);
  const ink='#183e50',blue='#267ea3',green='#247c61',purple='#6553a6';
  const label=(left:number,top:number,width:number,text:string,extra:CSSProperties={})=><div data-shorts-important style={{position:'absolute',left,top,width,fontSize:54,fontWeight:800,lineHeight:1.12,textAlign:'center',whiteSpace:'nowrap',color:ink,...extra}}>{text}</div>;
  return <div role="img" aria-label={flow?'利用者のアクセスをサーバー内のPHPが処理し、結果をブラウザーに返す流れ':'サーバーの中でPHPがWordPressやフォーム、買い物の仕組みを動かす例'} data-shorts-visual data-runtime-illustration={flow?'request-response':'services'} style={{position:'absolute',left:S.left,top:660,width:S.width,height:590}}>
    <svg aria-hidden viewBox="0 0 828 590" width="828" height="590" style={{position:'absolute',inset:0}}>
      <defs>
        <linearGradient id="runtime-rack" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#edf4f6"/><stop offset="1" stopColor="#d1e1e7"/></linearGradient>
        <marker id="runtime-request" markerWidth="20" markerHeight="20" viewBox="0 0 10 10" markerUnits="userSpaceOnUse" refX="9" refY="5" orient="auto"><path d="M0 0 9 5 0 10Z" fill={blue}/></marker>
        <marker id="runtime-reply" markerWidth="20" markerHeight="20" viewBox="0 0 10 10" markerUnits="userSpaceOnUse" refX="9" refY="5" orient="auto"><path d="M0 0 9 5 0 10Z" fill={green}/></marker>
      </defs>
      {/* Neutral visitor illustration, not a new presenter or identifiable person. */}
      <ellipse cx="129" cy="425" rx="124" ry="19" fill="#173b5014"/>
      <path d="M58 310v-41c0-48 31-76 71-76s71 28 71 76v41" fill="#487585"/>
      <circle cx="129" cy="168" r="45" fill="#efc7a8"/>
      <path d="M85 161c-5-61 98-66 90 6-14-16-29-23-49-20-19 3-29 11-41 14Z" fill="#263a44"/>
      <path d="M112 180q16 12 32 0" fill="none" stroke="#a86e54" strokeWidth="4" strokeLinecap="round"/>
      <rect x="23" y="260" width="211" height="142" rx="14" fill={reply>.5&&flow?'#fffef7':'#f8fcfd'} stroke={blue} strokeWidth="6"/>
      <path d="M23 289h211" stroke={blue} strokeWidth="4"/>
      {[44,60,76].map(x=><circle key={x} cx={x} cy="275" r="4" fill={blue}/>)}
      <rect x="48" y="310" width={flow?32+130*reply:136} height="17" rx="5" fill={flow?green:'#80b4c7'}/>
      <rect x="48" y="343" width="95" height="9" rx="4" fill="#afc9d2"/>
      <rect x="48" y="365" width={flow?35+105*reply:124} height="9" rx="4" fill="#afc9d2"/>
      <path d="m23 405-16 16h243l-16-16" fill="#b3ccd7" stroke={blue} strokeWidth="5" strokeLinejoin="round"/>
      {/* A physical server containing application examples and the PHP runtime. */}
      <path d="m350 99 23-17h435l20 17v355H350Z" fill="#a9c2ce"/>
      <rect x="350" y="99" width="478" height="354" rx="22" fill="url(#runtime-rack)" stroke="#537c8e" strokeWidth="5"/>
      <rect x="365" y="116" width="448" height="84" rx="13" fill="#fff" stroke="#a4c0cb" strokeWidth="2"/>
      <path d="M384 135h37v43h-37Zm7 10h23m-23 10h23m-23 10h14" fill="none" stroke={blue} strokeWidth="4"/>
      <rect x="365" y="217" width="224" height="100" rx="13" fill="#fff" stroke="#a4c0cb" strokeWidth="2"/>
      <rect x="597" y="217" width="216" height="100" rx="13" fill="#fff" stroke="#a4c0cb" strokeWidth="2"/>
      <path d="M378 232h32m-32 10h48m185-12h12l7 18h27l6-13h-39" fill="none" stroke={blue} strokeWidth="3"/>
      <rect x="374" y="339" width="430" height="88" rx="14" fill={purple} opacity={flow?.8+.2*processing:1}/>
      {flow&&<rect x="366" y="331" width="446" height="104" rx="20" fill="none" stroke={purple} strokeWidth="5" opacity={processing*(.4+.2*Math.sin(f*.16))}/>}
      <path d="M255 290h77" fill="none" stroke={blue} strokeWidth="7" markerEnd="url(#runtime-request)" opacity={flow?request:.7}/>
      <circle cx={255+70*(flow?((f/40)%1):.65)} cy="290" r="8" fill={blue} opacity={request}/>
      {flow&&<path d="M588 461v47H10v-85" fill="none" stroke={green} strokeWidth="7" markerEnd="url(#runtime-reply)" strokeDasharray="720" strokeDashoffset={720*(1-reply)}/>}
    </svg>
    {label(0,12,302,flow?'①アクセス':'利用する人')}
    {label(375,12,428,'サーバー')}
    {label(423,129,378,'WordPress')}
    {label(366,252,224,'フォーム')}
    {label(597,252,216,'買い物')}
    {label(374,347,430,flow?'② PHPで処理':'PHP',{fontSize:flow?62:74,color:'#fff'})}
    {label(0,436,300,'ブラウザー')}
    {flow?label(290,520,538,'③ 画面が返る',{color:green,opacity:reply}):label(345,484,483,'PHPが動かす例',{color:purple})}
  </div>;
}
