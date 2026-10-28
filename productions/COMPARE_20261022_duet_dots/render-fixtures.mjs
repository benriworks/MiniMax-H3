// Review only. No API, TTS, public delivery, invented screenshots or still-as-video.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const here=path.dirname(fileURLToPath(import.meta.url)),root=path.resolve(here,'../..'),studio=path.join(root,'studio');
const require=createRequire(path.join(studio,'package.json'));
const {bundle}=require('@remotion/bundler'),{selectComposition,renderStill}=require('@remotion/renderer'),{chromium}=require('playwright');
const out=path.join(root,'outputs/productions/COMPARE_20261022_duet_dots',process.argv[2]??'fixture-01');
const pub=path.join(out,'public');await fs.mkdir(path.join(pub,'template-assets'),{recursive:true});
await fs.copyFile(path.join(studio,'public/template-assets/NotoSansJP-Variable.ttf'),path.join(pub,'template-assets/NotoSansJP-Variable.ttf'));
const script=JSON.parse(await fs.readFile(path.join(here,'script-draft.json'),'utf8'));
const captionPlan=JSON.parse(await fs.readFile(path.join(here,'caption-phrases.json'),'utf8'));
const custom={
  C03:{panels:[{label:'予定を確認',detail:'灯台珈琲の打ち合わせ',icon:'calendar'},{label:'会議資料を準備',detail:'判断が必要な点を整理',icon:'document',tone:'blue'}],note:'依頼の例・実行比較は未実施'},
  C04:{panels:[{label:'手元のPC',detail:'閉じても',icon:'laptop',motion:'close'},{label:'クラウドの仕事',detail:'続けられる',icon:'cloud',tone:'blue'}]},
  C05:{panels:[{label:'Duet',detail:'朝の要点まとめ',icon:'message'},{label:'一定間隔で確認',detail:'常時監視ではない',icon:'clock',tone:'blue'}]},
  C06:{panels:[{label:'dotsの自発フォロー',detail:'必要なフォローを考える',icon:'message'},{label:'定時の確認',detail:'予定として設定する',icon:'calendar',tone:'blue'}]},
  C09:{connection:'local',panels:[{label:'dots → Codex',detail:'許可した手元のPC',icon:'laptop'},{label:'作業を進める条件',detail:'PCがオンライン',icon:'handoff',tone:'blue'}],note:'許可・オンライン・アプリ起動'},
  C11:{panels:[{label:'Duet',detail:'Claudeと共通枠',icon:'meter'},{label:'背景の確認',detail:'動く分も枠を使う',icon:'clock',tone:'blue'}]},
  C12:{panels:[{label:'dotsとの会話',detail:'ChatGPT枠の対象外',icon:'message'}],note:'実作業の利用枠とは別'},
  C13:{panels:[{label:'Workの作業',detail:'Workの枠を使う',icon:'document'},{label:'Codexの作業',detail:'Codexの枠を使う',icon:'laptop',tone:'blue'}]},
};
const units=t=>[...t].reduce((n,c)=>n+(/[\x20-\x7e\uff61-\uff9f]/.test(c)?.54:1),0);
const props={title:script.title,mode:'fixture',durationInFrames:script.target_duration_seconds*24,scenes:[],captions:[],showGuides:false};
for(const scene of script.scenes){
  const from=scene.start_seconds_provisional*24,duration=(scene.end_seconds_provisional-scene.start_seconds_provisional)*24;
  const target={id:scene.id,from,duration,kind:scene.kind,eyebrow:'DUET × DOTS / 比較',headline:scene.headline,source_ids:scene.source_ids};
  if(scene.kind==='comparison')Object.assign(target,{layout:scene.layout,...custom[scene.id]});
  else if(scene.kind==='source')Object.assign(target,{points:scene.on_screen_points,fixtureLabel:'公式画像は準備中'});
  else Object.assign(target,{role:scene.layout==='midpoint'?'insight':scene.layout,points:scene.on_screen_points,fixtureLabel:'人物動画は準備中',...(scene.id==='C14'?{note:'速さ・品質の優劣は未検証'}:{})});
  props.scenes.push(target);
  const phrases=captionPlan.scenes[scene.id];
  if(phrases.join('').replaceAll('\n','')!==scene.narration||phrases.some(p=>p.split('\n').length>2||p.split('\n').some(line=>units(line)>12)))throw Error('Caption phrase mismatch '+scene.id);
  for(const [i,text] of phrases.entries()){const start=from+Math.floor(i/phrases.length*duration),end=from+Math.floor((i+1)/phrases.length*duration);props.captions.push({start,end,text});}
}
await fs.writeFile(path.join(out,'props.json'),JSON.stringify(props,null,2)+'\n',{flag:'wx'});
const serveUrl=await bundle({entryPoint:path.join(studio,'src/remotion/comparisonEntry.tsx'),rootDir:studio,publicDir:pub,outDir:path.join(out,'bundle')});
const browserExecutable=chromium.executablePath(),composition=await selectComposition({serveUrl,id:'ProductComparison',inputProps:props,browserExecutable});
const images=[];
for(const scene of props.scenes){const output=path.join(out,scene.id+'.png');await renderStill({composition,serveUrl,inputProps:props,browserExecutable,frame:scene.from+Math.min(44,scene.duration-1),output,imageFormat:'png',overwrite:false});const bytes=await fs.readFile(output);images.push({scene:scene.id,path:path.relative(root,output).replaceAll('\\','/'),bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex')});console.log(scene.id);}
await fs.writeFile(path.join(out,'review.json'),JSON.stringify({status:'fixture_requires_visual_review',real_speech_generated:false,actual_presenter_video:false,official_captures:false,provisional_timing:true,public_delivery:false,images},null,2)+'\n',{flag:'wx'});
