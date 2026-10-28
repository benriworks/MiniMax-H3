// Preview only: actual prepared props and character videos, no full render or API.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(here,'../..'),studio=path.join(root,'studio');
const require=createRequire(path.join(studio,'package.json'));
const {bundle}=require('@remotion/bundler');
const {selectComposition,renderStill}=require('@remotion/renderer');
const {chromium}=require('playwright');
const read=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const record=async p=>({path:path.relative(root,p).replaceAll('\\','/'),bytes:(await fs.stat(p)).size,sha256:createHash('sha256').update(await fs.readFile(p)).digest('hex').toUpperCase()});
const check=async value=>{const p=path.join(root,value.path),v=await record(p);if(v.bytes!==value.bytes||v.sha256!==value.sha256)throw Error('Changed input '+value.path);return p;};
const ref=await read(path.join(here,'fullframe-revision-plan.json'));
const planPath=await check(ref.plan),plan=await read(planPath);
const previewName=process.argv[2]??'layout-preview';
if(!/^layout-preview(?:-[a-z0-9]+)?$/.test(previewName))throw Error('Expected a dedicated layout-preview folder name');
const boundaryMode=process.argv[3]==='--boundaries';
const captionMode=process.argv[3]==='--caption-entries';
if(process.argv[3]&&!boundaryMode&&!captionMode)throw Error('Unsupported preview option');
const out=path.join(path.dirname(planPath),previewName);
await fs.mkdir(out,{recursive:false});
const sourceNames=['src/remotion/creatorEntry.tsx','src/remotion/CreatorShortComposition.tsx','src/remotion/EditorialScene.tsx','src/remotion/shortsMotion.ts','src/remotion/ShortsMotionPrimitives.tsx','src/remotion/FeatureDiagram.tsx','src/remotion/ScreenTypography.tsx','public/template-assets/NotoSansJP-Variable.ttf','package.json','package-lock.json'];
const sources=await Promise.all(sourceNames.map(n=>record(path.join(studio,n))));
const figures=[];
for(const number of [5,6,7,8,9]){
  const state=await read(path.join(here,String(number).padStart(2,'0'),'state.json'));
  if(state.status!=='prepared')throw Error('Expected newly prepared output');
  const production=path.join(root,state.output);
  const receipt=await read(await check(state.character_video_revision));
  if(receipt.previous_output!==plan.episodes.find(ep=>ep.episode===number).previous_output)throw Error('Wrong revision parent');
  const prep=await read(path.join(production,'preparation.json'));
  for(const entry of prep.sources)await check(entry);
  const inputProps=await read(path.join(production,'props.json'));
  const pub=path.join(production,'public');
  await fs.mkdir(path.join(pub,'template-assets'),{recursive:true});
  await fs.copyFile(path.join(studio,'public/template-assets/NotoSansJP-Variable.ttf'),path.join(pub,'template-assets/NotoSansJP-Variable.ttf'));
  const serveUrl=await bundle({entryPoint:path.join(studio,'src/remotion/creatorEntry.tsx'),rootDir:studio,publicDir:pub,outDir:path.join(out,`bundle-${number}`)});
  const browserExecutable=chromium.executablePath();
  const composition=await selectComposition({serveUrl,id:'CreatorShort',browserExecutable,inputProps});
  const specs=[['hook',0],['closing',6]];
  if(captionMode)specs.push(['longest',-1]);
  const captionWeight=text=>[...text].reduce((total,c)=>total+(c.charCodeAt(0)<128?0.58:1),0);
  for(const [baseLabel,index] of specs){
    if(captionMode){
      const match=index<0?null:inputProps.scenes[index];
      const cues=inputProps.captions.filter(c=>!match||(c.start>=match.from&&c.start<match.from+match.duration));
      const cue=cues.reduce((best,c)=>captionWeight(c.text)>captionWeight(best.text)?c:best);
      const output=path.join(out,`episode-${number}-${baseLabel}-caption-entry.png`);
      await renderStill({composition,serveUrl,browserExecutable,inputProps,frame:cue.start,imageFormat:'png',output,overwrite:false});
      figures.push({episode:number,scene:index,label:baseLabel+'-caption-entry',frame:cue.start,caption:cue.text,caption_age:0,image:await record(output),prepared_output:state.output,props:await record(path.join(production,'props.json'))});
      continue;
    }
    const scene=inputProps.scenes[index];
    if(!scene.media)throw Error('Expected actual character video');
    if(scene.mediaPlayFrames!==undefined&&scene.mediaPlayFrames!==scene.duration)throw Error('dots media must cover its full unchanged scene');
    const label=baseLabel+(boundaryMode?'-end':'');
    const frame=scene.from+(boundaryMode?scene.duration-1:Math.min(scene.duration-1,44));
    const output=path.join(out,`episode-${number}-${label}.png`);
    await renderStill({composition,serveUrl,browserExecutable,inputProps,frame,imageFormat:'png',output,overwrite:false});
    figures.push({episode:number,scene:index,label,frame,image:await record(output),prepared_output:state.output,props:await record(path.join(production,'props.json'))});
  }
  console.log(JSON.stringify({event:'fullframe_layout_preview',episode:number,output:out}));
}
for(const entry of sources)await check(entry);
await fs.writeFile(path.join(out,'review.json'),JSON.stringify({status:'awaiting_root_visual_review',actual_prepared_timing:true,actual_character_video:true,boundary_frames:boundaryMode,caption_entry_frames:captionMode,full_video_rendered:false,tts_requests:0,new_minimax_generations:0,plan:ref.plan,sources,figures},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({event:'all_fullframe_stills_ready',output:out,images:figures.length}));
