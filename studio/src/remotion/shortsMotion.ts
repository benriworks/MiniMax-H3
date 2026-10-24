/** Shared, deterministic editorial motion. Safe area is our production guide. */
export const SHORTS_SAFE = {left:72, top:210, width:828, bottom:1490, captionTop:1300} as const;
export const SHORTS_COLORS = {ink:'#0b1120', paper:'#f5f1e8', lime:'#dfff78', coral:'#ff876a', blue:'#8de1ff'} as const;
export const BUSINESS_COLORS = {ink:'#252d31',paper:'#f4f1eb',accent:'#688070',muted:'#57645e',line:'#d8ddd6',panel:'#fffdf9'} as const;
export const clamp01 = (x:number) => Math.max(0,Math.min(1,x));
export const outCubic = (x:number) => 1-(1-clamp01(x))**3;
export const displayUnits = (text:string) => [...text].reduce((n,c)=>n+(/[\x20-\x7e\uff61-\uff9f]/.test(c)?.54:1),0);
export const headlineSize = (text:string, preferred=108) => Math.min(preferred,Math.floor(800/Math.max(1,...text.split('\n').map(displayUnits))));
export const headlineFits = (text:string) => text.trim().length>0 && text.split('\n').length<=3 && headlineSize(text)>=54;
export function cameraMotion(frame:number,duration:number,index=0) {
  const progress=clamp01(frame/Math.max(1,duration-1));
  return {scale:1.015+.055*(index%2?1-progress:progress),x:Math.sin(progress*Math.PI)* (index%2?-9:9)};
}
export function titleMotion(frame:number) {
  const enter=outCubic(frame/9);
  return {opacity:.35+.65*enter, y:(1-enter)*32, scale:.94+.06*enter};
}
export const FEATURE_GRAPHICS = ['release','cloud','apps','parallel','memory','chat','schedule','research','control','laptop','web-services','web-flow'] as const;
export const EDITORIAL_LAYOUTS = ['hook','parallel','conversation','closing','memory','channels','calendar','research','permissions','contrast','statement','recap'] as const;
export type EditorialLayout = typeof EDITORIAL_LAYOUTS[number];
export type FeatureGraphic = typeof FEATURE_GRAPHICS[number];
export type CreatorItem = {label:string; detail?:string; done?:boolean};
export const DEMONSTRATION_PHASES = ['before','first-output','revision','after','export'] as const;
export const DEMONSTRATION_PRODUCTS = ['Claude','Codex','ChatGPT'] as const;
export type CreatorCapture = {image:string;title:string} & (
  {origin?:'official';source_url:string} |
  {origin:'demonstration';product:typeof DEMONSTRATION_PRODUCTS[number];phase:typeof DEMONSTRATION_PHASES[number]}
);
export function isOfficialCaptureUrl(value:string):boolean {
  try {
    const url=new URL(value);
    if(url.protocol!=='https:'||url.username||url.password||url.port||url.search)return false;
    return (url.hostname==='learn.chatgpt.com'&&/^\/docs\/dots\/[a-z-]+$/.test(url.pathname))
      ||(url.hostname==='support.claude.com'&&/^\/(?:en|ja)\/articles\/[^/]+$/.test(url.pathname))
      ||(url.hostname==='claude.com'&&/^\/resources\/articles\/[^/]+$/.test(url.pathname))
      ||(url.hostname==='www.php.net'&&/^\/archive\/[0-9]{4}\.php$/.test(url.pathname))
      ||(url.hostname==='www.ipa.go.jp'&&/^\/security\/security-alert\/[0-9]{4}\/alert[0-9]{8}\.html$/.test(url.pathname))
      ||(url.hostname==='www.jpcert.or.jp'&&/^\/at\/[0-9]{4}\/at[0-9]{6}\.html$/.test(url.pathname));
  } catch {return false;}
}
export type CreatorScene = {
  id:string; kind:'hero'|'quote'|'steps'|'cards'|'checklist'|'compare'|'diagram'|'stat'|'editorial'|'source';
  from:number; duration:number; eyebrow:string; headline:string; accent?:string;
  body?:string; action?:string; items?:CreatorItem[]; media?:string; mediaStart?:number;
  mediaPlayFrames?:number; mediaDurationInFrames?:number;
  tone?:'dark'|'light'; illustration?:boolean;
  graphic?:FeatureGraphic; stat?:string;
  editorial_layout?:EditorialLayout;
  visual_style?:'business';
  capture?:CreatorCapture;
  presenter?:{image:string;role:'hook'|'recap'};
};
export type CreatorCaption = {start:number;end:number;text:string};
export type CreatorShortProps = {scenes:CreatorScene[];captions:CreatorCaption[];durationInFrames:number;title:string;showGuides?:boolean};
export function validateCreatorProps(value:CreatorShortProps):CreatorShortProps {
  if(!Number.isInteger(value.durationInFrames)||value.durationInFrames<240||value.durationInFrames>1440)throw Error('Expected 10–60 second short');
  if(!Array.isArray(value.scenes)||value.scenes.length<1||value.scenes.length>24)throw Error('Invalid scene count');
  let end=0;
  for(const [sceneIndex,scene] of value.scenes.entries()){
    if(scene.from!==end||!Number.isInteger(scene.duration)||scene.duration<24||scene.duration>192)throw Error('Scenes must cover the timeline with 1–8 second cuts');
    if(!headlineFits(scene.headline))throw Error('Headline does not fit the safe area');
    if(scene.media && !/^media-\d{2}\.mp4$/.test(scene.media))throw Error('Unstaged video');
    if(scene.mediaPlayFrames!==undefined||scene.mediaDurationInFrames!==undefined){
      if(!scene.media||scene.kind!=='editorial'||!Number.isInteger(scene.mediaPlayFrames)
        ||!Number.isInteger(scene.mediaDurationInFrames)||scene.mediaPlayFrames!<24
        ||scene.mediaPlayFrames!>scene.duration||!Number.isInteger(scene.mediaStart??0)
        ||(scene.mediaStart??0)<0||(scene.mediaStart??0)+scene.mediaPlayFrames!>scene.mediaDurationInFrames!)throw Error('Invalid editorial video playback window');
    }
    if(scene.visual_style!==undefined){
      if(scene.visual_style!=='business'||!['editorial','source'].includes(scene.kind))throw Error('Unknown or misplaced visual style');
      const oneLine=(text:string|undefined,max:number)=>(text??'').split('\n').length===1&&displayUnits(text??'')<=max;
      if(scene.headline.split('\n').length>2||scene.headline.split('\n').some(line=>displayUnits(line)>10))throw Error('Business headline needs at most two short lines');
      if(!oneLine(scene.eyebrow,15)||!oneLine(scene.action,12))throw Error('Business label is too long');
      if(scene.presenter)throw Error('Business guides require a staged motion clip, not a still presenter');
      if(scene.media){
        if(scene.kind!=='editorial'||!['hook','closing'].includes(scene.editorial_layout!)
          ||(scene.editorial_layout==='hook'&&sceneIndex!==0)||(scene.editorial_layout==='closing'&&sceneIndex!==value.scenes.length-1))throw Error('Business motion clips belong only in the opening or closing');
        if(!Number.isInteger(scene.mediaStart??0)||(scene.mediaStart??0)<0)throw Error('Invalid business video start');
      }
      const bodyLines=(scene.body??'').split('\n'),items=scene.items??[],narrow=Boolean(scene.media);
      if(bodyLines.length>2||bodyLines.some(line=>displayUnits(line)>(narrow?9:12))||items.length>(narrow?2:3)
        ||items.some(item=>!oneLine(item.label,narrow?8:10)||!oneLine(item.detail,narrow?8:11))||!oneLine(scene.stat,narrow?8:12))throw Error('Business content does not fit');
      if(items.length===3&&bodyLines.length>1)throw Error('Three business items need a single-line introduction');
      if(scene.stat&&items.length)throw Error('Use either business items or a statistic');
      if(scene.kind==='source'&&(scene.body||scene.action||scene.stat||items.length||scene.media))throw Error('Business source scenes reserve the center for evidence');
    }
    if(scene.presenter){
      if(scene.kind!=='editorial'||!/^presenter-\d{2}\.png$/.test(scene.presenter.image)||!['hook','recap'].includes(scene.presenter.role))throw Error('Unstaged or misplaced presenter');
      const items=scene.items??[],hook=scene.presenter.role==='hook';
      if(items.length>(hook?2:3)||items.some(item=>displayUnits(item.label)>(hook?6:items.length===3?4:6)||displayUnits(item.detail??'')>(hook?7:8)))throw Error('Presenter text does not fit its layout');
    }
    if(scene.kind==='editorial'&&scene.media&&scene.visual_style!=='business'){
      if(scene.presenter||(sceneIndex!==0&&sceneIndex!==value.scenes.length-1)||!Number.isInteger(scene.mediaStart??0)||(scene.mediaStart??0)<0)throw Error('Editorial motion guide belongs only in the opening or closing');
      const items=scene.items??[],hook=sceneIndex===0;
      if(items.length>(hook?2:3)||items.some(item=>displayUnits(item.label)>(hook?6:items.length===3?4:6)||displayUnits(item.detail??'')>(hook?7:8)))throw Error('Motion guide text does not fit its layout');
    }
    if(!['hero','quote','steps','cards','checklist','compare','diagram','stat','editorial','source'].includes(scene.kind))throw Error('Unknown scene kind');
    if(scene.kind==='editorial'&&!EDITORIAL_LAYOUTS.includes(scene.editorial_layout!))throw Error('Unknown editorial layout');
    if(scene.kind==='editorial'&&scene.visual_style!=='business'&&EDITORIAL_LAYOUTS.indexOf(scene.editorial_layout!)>=4){
      const narrow=scene.editorial_layout==='channels'||scene.editorial_layout==='calendar';
      const oneLine=(text:string|undefined,max:number)=>(text??'').split('\n').length===1&&displayUnits(text??'')<=max;
      const items=scene.items??[],bodyLines=(scene.body??'').split('\n');
      if(items.length>(scene.editorial_layout==='contrast'?2:3)||items.some(item=>!oneLine(item.label,narrow?7:10)||!oneLine(item.detail,narrow?7:11)))throw Error('Editorial item text does not fit its layout');
      if(bodyLines.length>(scene.editorial_layout==='statement'?2:1)||bodyLines.some(line=>displayUnits(line)>12)||!oneLine(scene.action,12)||!oneLine(scene.stat,scene.editorial_layout==='channels'?4:8))throw Error('Editorial text does not fit its layout');
    }
    if(scene.kind==='source'){
      const capture=scene.capture;
      if(!capture||!/^capture-\d{2}\.png$/.test(capture.image)||!capture.title?.trim()||displayUnits(capture.title)>18)throw Error('Unstaged or untitled source capture');
      if(capture.origin==='demonstration'){
        if(scene.visual_style!=='business'||!DEMONSTRATION_PRODUCTS.includes(capture.product)||!DEMONSTRATION_PHASES.includes(capture.phase)||'source_url' in capture)throw Error('Invalid demonstration capture');
      }else if(capture.origin==='official'){
        if(scene.visual_style!=='business'||!isOfficialCaptureUrl(capture.source_url))throw Error('Unattributed official capture');
      }else if(capture.origin!==undefined||!/^https:\/\/learn\.chatgpt\.com\/docs\/dots\/[a-z-]+(?:#[a-z-]+)?$/.test(capture.source_url))throw Error('Unattributed legacy capture');
    }
    if(scene.kind==='diagram'&&(!FEATURE_GRAPHICS.includes(scene.graphic!)||(scene.items??[]).length>3||(scene.items??[]).some(i=>displayUnits(i.label)>4)))throw Error('Invalid feature diagram');
    if(scene.kind==='stat'&&(!scene.stat||displayUnits(scene.stat)>8))throw Error('Invalid feature statistic');
    end+=scene.duration;
  }
  if(end!==value.durationInFrames)throw Error('Scene coverage mismatch');
  let captionEnd=0;
  for(const cue of value.captions){
    if(!Number.isInteger(cue.start)||!Number.isInteger(cue.end)||cue.start<captionEnd||cue.end<=cue.start||cue.end>end)throw Error('Invalid caption timing');
    if(cue.text.split('\n').length>2||cue.text.split('\n').some(line=>displayUnits(line)>12))throw Error('Caption does not fit');
    captionEnd=cue.end;
  }
  return value;
}
