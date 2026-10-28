// Dedicated comparison renderer. Does not alter CreatorShort or its 60s limit.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {selectComposition,renderMedia,renderStill} from '@remotion/renderer';
import {chromium} from 'playwright';
const studio=path.dirname(fileURLToPath(import.meta.url)),root=path.dirname(studio),out=path.resolve(process.argv[2]);
const base=path.join(root,'outputs','productions','COMPARE_20261022_duet_dots')+path.sep;
if(!out.startsWith(base))throw Error('Comparison output outside its production');
const stillsOnly=process.argv.includes('--stills-only');
const record=async p=>({path:path.relative(root,p).replaceAll('\\','/'),bytes:(await fs.stat(p)).size,sha256:createHash('sha256').update(await fs.readFile(p)).digest('hex').toUpperCase()});
const check=async r=>{const p=path.resolve(root,r.path);if(!p.startsWith(root+path.sep))throw Error('Outside workspace');const a=await record(p);if(a.bytes!==r.bytes||a.sha256!==r.sha256)throw Error('Changed input '+r.path);return p;};
const prep=JSON.parse(await fs.readFile(path.join(out,'preparation.json'),'utf8'));
for(const source of prep.sources)await check(source);
if(prep.source_audio_included!==false)throw Error('Presenter source audio must be excluded');
const names=['src/remotion/comparisonEntry.tsx','src/remotion/ComparisonComposition.tsx','src/remotion/comparisonMotion.ts','src/remotion/shortsMotion.ts','src/remotion/ShortsMotionPrimitives.tsx','src/remotion/ScreenTypography.tsx','public/template-assets/NotoSansJP-Variable.ttf','package.json','package-lock.json','comparison-render.mjs'];
const sources=[...prep.sources,...await Promise.all(names.map(n=>record(path.join(studio,n))))];
const pub=path.join(out,'public');await fs.mkdir(path.join(pub,'template-assets'),{recursive:true});
await fs.copyFile(path.join(studio,'public/template-assets/NotoSansJP-Variable.ttf'),path.join(pub,'template-assets/NotoSansJP-Variable.ttf'));
const inputProps=JSON.parse(await fs.readFile(path.join(out,'props.json'),'utf8'));
if(inputProps.mode!=='production')throw Error('Only actual production assets can produce this delivery');
const seen=new Set();
for(const scene of inputProps.scenes){
  const name=scene.media??scene.capture?.image;if(!name||seen.has(name))continue;seen.add(name);
  if(!/^(media-\d{2}\.mp4|capture-\d{2}\.png)$/.test(name))throw Error('Invalid staged filename');
  const file=path.join(pub,name),item=await record(file);
  if(!prep.sources.some(r=>r.path===item.path&&r.sha256===item.sha256&&r.bytes===item.bytes))throw Error('Unbound staged asset');
  if(scene.media)execFileSync('ffmpeg',['-v','error','-xerror','-i',file,'-f','null','-'],{windowsHide:true});
}
const browserExecutable=chromium.executablePath();
const serveUrl=await bundle({entryPoint:path.join(studio,'src/remotion/comparisonEntry.tsx'),rootDir:studio,publicDir:pub,outDir:path.join(out,'bundle')});
const composition=await selectComposition({serveUrl,id:'ProductComparison',browserExecutable,inputProps});
const previewPath=path.join(out,'preview.json');
let preview;
try{preview=JSON.parse(await fs.readFile(previewPath,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;}
if(preview){for(const source of [...preview.sources,...preview.images])await check(source);}
else{
  const images=[],frames=[];
  for(const [i,scene] of inputProps.scenes.entries()){
    const frame=scene.from+(scene.media?Math.floor(scene.mediaPlayFrames/2):Math.min(scene.duration-1,44));
    const output=path.join(out,`design-${String(i).padStart(2,'0')}.png`);
    await renderStill({composition,serveUrl,browserExecutable,inputProps,frame,imageFormat:'png',output,overwrite:false});
    images.push(await record(output));frames.push({scene:scene.id,frame,phase:scene.media?'motion':'main'});
    if(scene.media&&scene.duration>scene.mediaPlayFrames+2){
      const summary=path.join(out,`summary-${scene.id}.png`),after=scene.from+scene.mediaPlayFrames+2;
      await renderStill({composition,serveUrl,browserExecutable,inputProps,frame:after,imageFormat:'png',output:summary,overwrite:false});
      images.push(await record(summary));frames.push({scene:scene.id,frame:after,phase:'selfmade_summary'});
    }
    console.log(JSON.stringify({event:'scene_preview',scene:scene.id}));
  }
  const safe=path.join(out,'safe-area-preview.png');
  await renderStill({composition,serveUrl,browserExecutable,inputProps:{...inputProps,showGuides:true},frame:12,imageFormat:'png',output:safe,overwrite:false});
  images.push(await record(safe));
  await fs.copyFile(path.join(out,'design-00.png'),path.join(out,'cover.png'));
  for(const source of sources)await check(source);
  preview={sources,images,frames,review_status:'requires_visual_review',actual_presenter_motion:true,source_audio_included:false};
  await fs.writeFile(previewPath,JSON.stringify(preview,null,2)+'\n',{flag:'wx'});
}
if(stillsOnly){console.log(JSON.stringify({event:'stills_complete',output:out}));process.exit(0);}
const video=path.join(out,'timeline.mp4');let last=-1;
await renderMedia({composition,serveUrl,browserExecutable,inputProps,outputLocation:video,codec:'h264',pixelFormat:'yuv420p',colorSpace:'bt709',imageFormat:'png',crf:14,muted:true,concurrency:2,overwrite:false,onProgress:({progress})=>{const p=Math.floor(progress*10)*10;if(p>last){last=p;console.log(JSON.stringify({event:'render',percent:p}));}}});
for(const source of sources)await check(source);
const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',video],{encoding:'utf8',windowsHide:true}));
if(probe.streams.length!==1||probe.streams[0].codec_name!=='h264'||Number(probe.streams[0].nb_frames)!==inputProps.durationInFrames)throw Error('Timeline format mismatch or unexpected source audio');
await fs.writeFile(path.join(out,'render.json'),JSON.stringify({sources,timeline:await record(video),probe,encoding:{crf:14,format:'png',fps:24},design_frames:preview.frames,source_audio_included:false},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({event:'render_complete',output:out}));
