import assert from 'node:assert/strict';
import test from 'node:test';
import {isOfficialCaptureUrl,validateCreatorProps} from '../.security-test-dist/shortsMotion.js';

test('security citations accept bounded primary advisories and reject lookalikes',()=>{
  for(const url of [
    'https://www.php.net/archive/2026.php#2026-10-21-5',
    'https://www.ipa.go.jp/security/security-alert/2026/alert20261022.html',
    'https://www.jpcert.or.jp/at/2026/at260033.html',
  ]) assert.equal(isOfficialCaptureUrl(url),true,url);
  for(const url of [
    'http://www.php.net/archive/2026.php',
    'https://www.php.net.evil/archive/2026.php',
    'https://user@www.php.net/archive/2026.php',
    'https://www.php.net:8189/archive/2026.php',
    'https://www.php.net/archive/2026.php?account=1',
    'https://www.php.net/manual/en/index.php',
    'https://www.ipa.go.jp/private/chat',
    'https://127.0.0.1/archive/2026.php',
  ]) assert.equal(isOfficialCaptureUrl(url),false,url);
});

test('a fifty-second source story covers exactly 1200 frames',()=>{
  const scenes=Array.from({length:8},(_,i)=>({id:String(i),from:i*150,duration:150,kind:'source',visual_style:'business',eyebrow:'PHP公式',headline:'公式告知を確認',capture:{image:'capture-00.png',title:'PHP公式告知',origin:'official',source_url:'https://www.php.net/archive/2026.php#2026-10-21-5'}}));
  const props={title:'PHP2Shell',durationInFrames:1200,captions:[],scenes};
  assert.equal(validateCreatorProps(props).durationInFrames,1200);
  assert.throws(()=>validateCreatorProps({...props,durationInFrames:1199}));
});
