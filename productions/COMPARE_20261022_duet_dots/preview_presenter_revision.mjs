// Static transition/face checks only; no full video rendering and no API calls.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../..'),studio=path.join(root,'studio');
const state=JSON.parse(await fs.readFile(path.join(here,'presenter-revision-state.json'),'utf8'));
const out=path.join(root,state.output),props=JSON.parse(await fs.readFile(path.join(out,'props.json'),'utf8'));
const require=createRequire(path.join(studio,'package.json'));
const {bundle}=require('@remotion/bundler'),{selectComposition,renderStill}=require('@remotion/renderer'),{chromium}=require('playwright');
const serveUrl=await bundle({entryPoint:path.join(studio,'src/remotion/comparisonEntry.tsx'),rootDir:studio,publicDir:path.join(out,'public'),outDir:path.join(out,'transition-bundle')});
const browserExecutable=chromium.executablePath(),composition=await selectComposition({serveUrl,id:'ProductComparison',inputProps:props,browserExecutable});
const samples=[];
for(const scene of props.scenes.filter(s=>s.media)){
  const play=scene.mediaPlayFrames;
  for(const local of [play-6,play-3,play-1,play,Math.min(scene.duration-1,play+10)])samples.push({name:`transition-${scene.id}-${local}.png`,frame:scene.from+local});
}
samples.push({name:'hero-cover.png',frame:24});
for(const sample of samples){await renderStill({composition,serveUrl,browserExecutable,inputProps:props,frame:sample.frame,imageFormat:'png',output:path.join(out,sample.name),overwrite:false});}
await fs.writeFile(path.join(out,'transition-preview.json'),JSON.stringify({actual_video:true,samples,full_render:false,tts_requests:0},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({event:'transition_previews_complete',samples:samples.length}));
