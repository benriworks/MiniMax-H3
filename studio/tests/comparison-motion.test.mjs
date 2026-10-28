import assert from 'node:assert/strict';
import test from 'node:test';
import {createRequire} from 'node:module';
import {writeFile} from 'node:fs/promises';
await writeFile(new URL('../.comparison-test-dist/package.json',import.meta.url),'{"type":"commonjs"}\n');
const require=createRequire(import.meta.url);
const {validateComparisonProps,isComparisonSourceUrl,presenterTransition}=require('../.comparison-test-dist/comparisonMotion.js');
const {validateCreatorProps,isOfficialCaptureUrl}=require('../.comparison-test-dist/shortsMotion.js');
const baseline=()=>({title:'test',mode:'fixture',durationInFrames:1440,captions:[],scenes:Array.from({length:8},(_,i)=>({id:String(i),from:i*180,duration:180,kind:'comparison',layout:'signal',eyebrow:'比較',headline:'確かめる',panels:[{label:'条件',detail:'内容を確認',icon:'clock'}]}))});
const reject=change=>{const props=baseline();change(props);assert.throws(()=>validateComparisonProps(props));};
test('comparison accepts 60–90 seconds without extending the legacy route',()=>{
  assert.equal(validateComparisonProps(baseline()).durationInFrames,1440);
  const full=baseline();full.scenes=Array.from({length:12},(_,i)=>({...full.scenes[0],id:String(i),from:i*180}));full.durationInFrames=2160;
  assert.equal(validateComparisonProps(full).durationInFrames,2160);
  assert.throws(()=>validateCreatorProps({...full,durationInFrames:2160}));
  reject(p=>p.durationInFrames=2161);reject(p=>p.durationInFrames=1439);
});
test('cuts and captions cannot escape or overlap the allocated timeline',()=>{
  reject(p=>p.scenes[2].from++);reject(p=>p.scenes[2].duration=193);reject(p=>p.scenes[2].id='0');
  reject(p=>p.captions=[{start:100,end:140,text:'確認'},{start:130,end:160,text:'確認'}]);
  reject(p=>p.captions=[{start:1400,end:1441,text:'確認'}]);
  reject(p=>p.captions=[{start:0,end:40,text:'一'.repeat(13)}]);
});
test('closed readable diagram contracts reject arbitrary layouts and overflow',()=>{
  reject(p=>p.scenes[0].layout='unknown');reject(p=>p.scenes[0].panels[0].icon='fake-ui');
  reject(p=>p.scenes[0].connection='local');reject(p=>p.scenes[0].panels[0].motion='close');
  reject(p=>p.scenes[0].headline='一'.repeat(11));reject(p=>p.scenes[0].panels[0].detail='一'.repeat(12));
  reject(p=>p.scenes[0].panels.push({label:'two'},{label:'three'}));
});
test('comparison adds only the exact Meet dots root while legacy allowlist stays closed',()=>{
  assert.equal(isComparisonSourceUrl('https://learn.chatgpt.com/docs/dots'),true);
  assert.equal(isOfficialCaptureUrl('https://learn.chatgpt.com/docs/dots'),false);
  for(const url of ['http://learn.chatgpt.com/docs/dots','https://learn.chatgpt.com/docs/dots?x=1','https://learn.chatgpt.com/docs/dots/','https://learn.chatgpt.com.evil.test/docs/dots'])assert.equal(isComparisonSourceUrl(url),false);
});
test('missing source/presenter assets are explicit fixtures, never production fallbacks',()=>{
  const p=baseline();p.scenes[0]={...p.scenes[0],kind:'source',fixtureLabel:'公式画像は準備中'};validateComparisonProps(p);
  assert.throws(()=>validateComparisonProps({...p,mode:'production'}));
  p.scenes[0]={...p.scenes[0],kind:'presenter',role:'opening',points:['確認する'],fixtureLabel:'人物動画は準備中'};validateComparisonProps(p);
  assert.throws(()=>validateComparisonProps({...p,mode:'production'}));
  delete p.scenes[0].fixtureLabel;assert.throws(()=>validateComparisonProps(p));
});
test('actual motion interval fits the MP4; longer scenes switch away without freeze/loop',()=>{
  const p=baseline();p.scenes[0]={...p.scenes[0],kind:'presenter',role:'opening',points:['確認する'],media:'media-00.mp4',mediaStart:10,mediaPlayFrames:100,mediaDurationInFrames:124};p.mode='production';validateComparisonProps(p);
  assert.throws(()=>validateComparisonProps({...p,scenes:[{...p.scenes[0],mediaStart:30},...p.scenes.slice(1)]}));
  assert.throws(()=>validateComparisonProps({...p,scenes:[{...p.scenes[0],mediaPlayFrames:181},...p.scenes.slice(1)]}));
  assert.throws(()=>validateComparisonProps({...p,scenes:[{...p.scenes[0],media:'../video.mp4'},...p.scenes.slice(1)]}));
});
test('immersive presenter is opt-in and completes the wipe before real footage ends',()=>{
  const p=baseline();validateComparisonProps(p);
  validateComparisonProps({...p,presenterTreatment:'immersive'});
  assert.throws(()=>validateComparisonProps({...p,presenterTreatment:'unknown'}));
  assert.deepEqual(presenterTransition(0,36),{videoOn:true,wipe:0,summaryOn:false,summaryAge:0});
  assert.equal(presenterTransition(30,36).wipe,0);
  assert.equal(presenterTransition(35,36).videoOn,true);
  assert.ok(presenterTransition(35,36).wipe>.99);
  assert.equal(presenterTransition(33,36).summaryOn,true);
  assert.deepEqual(presenterTransition(36,36),{videoOn:false,wipe:1,summaryOn:true,summaryAge:3});
  assert.deepEqual(presenterTransition(48,36),{videoOn:false,wipe:1,summaryOn:true,summaryAge:15});
});
