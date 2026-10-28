import {displayUnits,isOfficialCaptureUrl} from './shortsMotion';
import type {CreatorCaption} from './shortsMotion';

export const COMPARISON_LAYOUTS=['fictional_case','signal','workspace','availability','decision'] as const;
export const COMPARISON_ICONS=['calendar','document','cloud','laptop','clock','message','eye','handoff','meter'] as const;
export type ComparisonPanel={label:string;detail?:string;icon?:typeof COMPARISON_ICONS[number];tone?:'sage'|'blue';state?:'active'|'muted';motion?:'close'};
type BaseScene={id:string;from:number;duration:number;eyebrow:string;headline:string;source_ids?:string[]};
export type ComparisonScene=BaseScene & (
  {kind:'comparison';layout:typeof COMPARISON_LAYOUTS[number];panels:ComparisonPanel[];note?:string;connection?:'local'} |
  {kind:'source';capture?:{origin:'official';image:string;title:string;source_url:string};points?:string[];fixtureLabel?:string} |
  {kind:'presenter';role:'opening'|'insight'|'closing';points:string[];note?:string;media?:string;mediaStart?:number;mediaDurationInFrames?:number;mediaPlayFrames?:number;fixtureLabel?:string}
);
export type ComparisonProps={title:string;durationInFrames:number;scenes:ComparisonScene[];captions:CreatorCaption[];mode:'fixture'|'production';showGuides?:boolean;presenterTreatment?:'card'|'immersive'};

/** Ends the wipe before the real video ends; no frozen final frame is needed. */
export function presenterTransition(frame:number,play:number){
  const progress=Math.max(0,Math.min(1,(frame-(play-6))/6));
  return {videoOn:frame<play,wipe:1-(1-progress)**3,summaryOn:frame>=play-3,summaryAge:Math.max(0,frame-play+3)};
}

/** The comparison alone also quotes the exact Meet dots landing page. */
export function isComparisonSourceUrl(value:string):boolean {
  return value==='https://learn.chatgpt.com/docs/dots'||isOfficialCaptureUrl(value);
}
function fits(text:string|undefined,units:number,lines=1,required=false):boolean {
  return typeof text==='string' ? (!required||Boolean(text.trim()))&&text.split('\n').length<=lines&&text.split('\n').every(line=>displayUnits(line)<=units) : !required&&text===undefined;
}
export function validateComparisonProps(value:ComparisonProps):ComparisonProps {
  if(!['fixture','production'].includes(value.mode))throw Error('Comparison mode must be explicit');
  if(value.presenterTreatment!==undefined&&!['card','immersive'].includes(value.presenterTreatment))throw Error('Unknown comparison presenter treatment');
  if(!Number.isInteger(value.durationInFrames)||value.durationInFrames<1440||value.durationInFrames>2160)throw Error('Comparison requires 60–90 seconds');
  if(!Array.isArray(value.scenes)||value.scenes.length<8||value.scenes.length>24)throw Error('Comparison requires 8–24 cuts');
  let end=0;const ids=new Set<string>();
  for(const [index,scene] of value.scenes.entries()){
    if(!scene.id||ids.has(scene.id))throw Error('Unique scene IDs required');ids.add(scene.id);
    if(scene.from!==end||!Number.isInteger(scene.duration)||scene.duration<24||scene.duration>192)throw Error('Comparison cuts must cover the timeline in 1–8 second cuts');
    if(!fits(scene.headline,10,2,true)||!fits(scene.eyebrow,15,1,true))throw Error('Comparison heading does not fit');
    if(scene.kind==='comparison'){
      if(!COMPARISON_LAYOUTS.includes(scene.layout)||!Array.isArray(scene.panels)||scene.panels.length<1||scene.panels.length>2)throw Error('Invalid comparison diagram');
      if(scene.connection!==undefined&&(scene.connection!=='local'||scene.layout!=='workspace'))throw Error('Invalid workspace connection');
      for(const panel of scene.panels){
        if(!fits(panel.label,11,1,true)||!fits(panel.detail,11,['workspace','availability'].includes(scene.layout)?1:2)
          ||(panel.icon!==undefined&&!COMPARISON_ICONS.includes(panel.icon))||(panel.tone!==undefined&&!['sage','blue'].includes(panel.tone))
          ||(panel.state!==undefined&&!['active','muted'].includes(panel.state))||(panel.motion!==undefined&&(panel.motion!=='close'||panel.icon!=='laptop')))throw Error('Comparison panel does not fit');
      }
      if(!fits(scene.note,14))throw Error('Comparison note does not fit');
    }else if(scene.kind==='source'){
      const capture=scene.capture;
      if(capture){
        if(capture.origin!=='official'||!/^capture-\d{2}\.png$/.test(capture.image)||!capture.title?.trim()||!isComparisonSourceUrl(capture.source_url))throw Error('Comparison needs a staged official source');
      }else if(value.mode!=='fixture'||!fits(scene.fixtureLabel,12,2,true))throw Error('Missing comparison source');
      if((scene.points??[]).length>2||(scene.points??[]).some(point=>!fits(point,14,1,true)))throw Error('Source points do not fit');
    }else if(scene.kind==='presenter'){
      if(!['opening','insight','closing'].includes(scene.role)||(scene.role==='opening'&&index!==0)||(scene.role==='closing'&&index!==value.scenes.length-1))throw Error('Invalid presenter position');
      if(!Array.isArray(scene.points)||scene.points.length<1||scene.points.length>2||scene.points.some(point=>!fits(point,8,2,true))||!fits(scene.note,14))throw Error('Presenter copy does not fit');
      if(scene.media){
        const start=scene.mediaStart??0,play=scene.mediaPlayFrames??scene.duration,total=scene.mediaDurationInFrames;
        if(!/^media-\d{2}\.mp4$/.test(scene.media)||!Number.isInteger(start)||start<0||!Number.isInteger(total)||total!<1
          ||!Number.isInteger(play)||play<24||play>scene.duration||start+play>total!)throw Error('Presenter video interval exceeds the actual clip');
      }else if(value.mode!=='fixture'||!fits(scene.fixtureLabel,12,2,true))throw Error('Production requires the actual presenter motion video');
    }else throw Error('Unknown comparison scene');
    end+=scene.duration;
  }
  if(end!==value.durationInFrames)throw Error('Comparison coverage mismatch');
  if(!Array.isArray(value.captions))throw Error('Captions must be an array');
  let previous=0;
  for(const cue of value.captions){
    if(!Number.isInteger(cue.start)||!Number.isInteger(cue.end)||cue.start<previous||cue.end<=cue.start||cue.end>end||!fits(cue.text,12,2,true))throw Error('Invalid comparison caption');
    previous=cue.end;
  }
  return value;
}
