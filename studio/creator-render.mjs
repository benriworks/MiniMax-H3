import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {bundle} from '@remotion/bundler';
import {selectComposition,renderMedia,renderStill} from '@remotion/renderer';
import {chromium} from 'playwright';
import {validateCaptureForRender} from './capture-render-validation.mjs';
const studio=path.dirname(fileURLToPath(import.meta.url)),root=path.dirname(studio),out=path.resolve(process.argv[2]);
if(!out.startsWith(path.join(root,'outputs','productions')+path.sep))throw Error('Output outside production directory');
const record=async p=>({path:path.relative(root,p).replaceAll('\\','/'),bytes:(await fs.stat(p)).size,sha256:createHash('sha256').update(await fs.readFile(p)).digest('hex').toUpperCase()});
const check=async r=>{const p=path.resolve(root,r.path);if(!p.startsWith(root+path.sep))throw Error('Outside workspace');const a=await record(p);if(a.bytes!==r.bytes||a.sha256!==r.sha256)throw Error('Changed input '+r.path);return p;};
const prep=JSON.parse(await fs.readFile(path.join(out,'preparation.json'),'utf8'));
for(const source of prep.sources)await check(source);
const names=['src/remotion/creatorEntry.tsx','src/remotion/CreatorShortComposition.tsx','src/remotion/EditorialScene.tsx','src/remotion/shortsMotion.ts','src/remotion/ShortsMotionPrimitives.tsx','src/remotion/FeatureDiagram.tsx','src/remotion/ScreenTypography.tsx','public/template-assets/NotoSansJP-Variable.ttf','package.json','package-lock.json','creator-render.mjs','capture-render-validation.mjs'];
const sources=[...prep.sources,...await Promise.all(names.map(n=>record(path.join(studio,n))))];
const pub=path.join(out,'public');await fs.mkdir(path.join(pub,'template-assets'),{recursive:true});
await fs.copyFile(path.join(studio,'public/template-assets/NotoSansJP-Variable.ttf'),path.join(pub,'template-assets/NotoSansJP-Variable.ttf'));
const inputProps=JSON.parse(await fs.readFile(path.join(out,'props.json'),'utf8'));
const captureProofs=inputProps.scenes.some(scene=>scene.capture?.origin==='demonstration')
  ?await Promise.all(prep.sources.filter(source=>source.path.endsWith('.json')).map(async source=>JSON.parse(await fs.readFile(await check(source),'utf8')))):[];
const captureDisplay=[];
for(const [index,scene] of inputProps.scenes.entries())if(scene.capture){const file=path.join(pub,scene.capture.image);const meta=JSON.parse(execFileSync('ffprobe',['-v','error','-show_entries','stream=width,height,codec_name','-of','json',file],{encoding:'utf8',windowsHide:true})).streams[0];const staged=await record(file);captureDisplay.push({scene:index,...validateCaptureForRender(scene.capture,meta,staged,prep.sources,captureProofs)});sources.push(staged);}
for(const scene of inputProps.scenes)if(scene.presenter){
  if(scene.kind!=='editorial'||!/^presenter-\d{2}\.png$/.test(scene.presenter.image))throw Error('Invalid presenter asset');
  const file=path.join(pub,scene.presenter.image),asset=await record(file);
  if(!prep.sources.some(s=>s.path.startsWith('outputs/characters/')&&s.path.endsWith('.png')&&s.sha256===asset.sha256&&s.bytes===asset.bytes))throw Error('Staged presenter differs from reviewed source');
  sources.push(asset);
}
for(const scene of inputProps.scenes)if(scene.media){const file=path.join(pub,scene.media);execFileSync('ffmpeg',['-v','error','-xerror','-i',file,'-f','null','-'],{windowsHide:true});sources.push(await record(file));}
const browserExecutable=chromium.executablePath();
const serveUrl=await bundle({entryPoint:path.join(studio,'src/remotion/creatorEntry.tsx'),rootDir:studio,publicDir:pub,outDir:path.join(out,'bundle')});
const composition=await selectComposition({serveUrl,id:'CreatorShort',browserExecutable,inputProps});
for(const [i,scene] of inputProps.scenes.entries()){
  await renderStill({composition,serveUrl,browserExecutable,inputProps,frame:scene.from+Math.min(scene.duration-1,44),imageFormat:'png',output:path.join(out,`design-${String(i).padStart(2,'0')}.png`),overwrite:false});
}
await renderStill({composition,serveUrl,browserExecutable,inputProps:{...inputProps,showGuides:true},frame:36,imageFormat:'png',output:path.join(out,'safe-area-preview.png'),overwrite:false});
await fs.copyFile(path.join(out,'design-00.png'),path.join(out,'cover.png'));
console.log(JSON.stringify({event:'stills_ready',output:out}));
await fs.writeFile(path.join(out,'capture-display-review.json'),JSON.stringify({captures:captureDisplay,review_status:'requires_visual_review_of_rendered_scenes'},null,2)+'\n',{flag:'wx'});
const video=path.join(out,'timeline.mp4');let last=-1;
await renderMedia({composition,serveUrl,browserExecutable,inputProps,outputLocation:video,codec:'h264',pixelFormat:'yuv420p',colorSpace:'bt709',imageFormat:'png',crf:14,muted:true,concurrency:2,overwrite:false,onProgress:({progress})=>{const p=Math.floor(progress*10)*10;if(p>last){last=p;console.log(JSON.stringify({event:'render',percent:p}));}}});
for(const source of sources)await check(source);
const probe=JSON.parse(execFileSync('ffprobe',['-v','error','-show_streams','-show_format','-of','json',video],{encoding:'utf8',windowsHide:true}));
if(probe.streams.length!==1||Number(probe.streams[0].nb_frames)!==inputProps.durationInFrames)throw Error('Timeline format mismatch');
await fs.writeFile(path.join(out,'render.json'),JSON.stringify({sources,timeline:await record(video),probe,encoding:{crf:14,format:'png',fps:24},design_frames:inputProps.scenes.map(s=>s.from+Math.min(s.duration-1,44))},null,2)+'\n',{flag:'wx'});
console.log(JSON.stringify({event:'render_complete',output:out}));
