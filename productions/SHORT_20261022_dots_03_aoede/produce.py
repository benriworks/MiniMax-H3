"""Replace the next dots episode's voice with verified Gemini Aoede speech."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import importlib.util
import json
import shutil
import sys
import uuid
import wave
import zipfile
import hashlib
import html
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import prepare,finish,record,read,check,narration_inputs,run
HERE=Path(__file__).parent
STATE=HERE/'state.json'
OUT=ROOT/'outputs/productions/SHORT_20261022_dots_03_aoede'
spec=importlib.util.spec_from_file_location('gemini_speech',ROOT/'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py')
speech=importlib.util.module_from_spec(spec)
spec.loader.exec_module(speech)

def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def generated_folder(state):
    path=(ROOT/state['generation']).resolve(strict=True)
    if path.parent!=OUT/'voice-generations':raise ValueError('Unexpected voice generation directory')
    return path

def generate():
    if STATE.exists():raise ValueError('Production already has a generation record; reuse it without new API calls')
    story=read(HERE/'creator-story.json')
    for scene in story['scenes']:
        spoken=scene['narration']
        for rule in sorted(story['pronunciations'],key=lambda x:-len(x['source'])):
            spoken=spoken.replace(rule['source'],rule['target'])
        speech.payload(spoken,'Aoede')
    source_files=list((ROOT/'outputs/productions/SERIES_20261005_dots/20261005T153642158910Z/release').glob('*/dots-*.mp4'))
    source_files.append(ROOT/'outputs/productions/SHORT_20261021_dots_cloud_benefits/20261021T094421120681Z/release/dots-02-extra-cloud-benefits.mp4')
    if len(source_files)!=10:raise ValueError('Missing preserved series or supplement')
    out=OUT/'voice-generations'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    out.mkdir(parents=True)
    save(out/'plan.json',{'story':record(HERE/'creator-story.json'),'inputs':narration_inputs(story),
        'maximum_requests':len(story['scenes']),'voice':'Aoede','model':speech.MODEL,'automatic_retry':False,
        'existing_deliveries':[record(p) for p in source_files]})
    state={'generation':out.relative_to(ROOT).as_posix(),'status':'generating'}
    save(STATE,state)
    proofs=[];segments=[];samples=[];usage=[]
    last_submission=0
    for index,scene in enumerate(story['scenes']):
        spoken=scene['narration']
        for rule in sorted(story['pronunciations'],key=lambda x:-len(x['source'])):
            spoken=spoken.replace(rule['source'],rule['target'])
        parent=out/f'scene-{index:02d}'
        parent.mkdir()
        time.sleep(max(0,22-(time.monotonic()-last_submission)))
        last_submission=time.monotonic()
        proof=speech.synthesize(parent,spoken,'Aoede',minimum_seconds=.2)
        source=check(next(a for a in proof['files'] if a['path'].endswith('/voice.wav')))
        with wave.open(str(source),'rb') as wav:
            frames=wav.getnframes();samples.append(wav.readframes(frames))
        segments.append({'index':index,'text':scene['narration'],'frames':frames,'duration_ms':round(frames/24)})
        proofs.append(record(parent/'Aoede/verified.json'));usage.append(proof['usage'])
        print(json.dumps({'event':'speech_verified','scene':index,'seconds':round(frames/24000,3)},ensure_ascii=True),flush=True)
    with wave.open(str(out/'narration.wav'),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'))
        wav.writeframes(b''.join(samples))
    save(out/'timings.json',{'schema_version':1,'provider':'gemini','timing_source':'wav_frames','segments':segments})
    voice={'provider':'gemini','model':speech.MODEL,'voice':'Aoede','inputs':narration_inputs(story),
        'timing_source':'wav_frames','external_api_calls':len(proofs),'generation_proofs':proofs,'usage':usage,
        'artifacts':[dict(record(out/name),name=name) for name in ['narration.wav','timings.json']],
        'voice_selection':'Aoede preferred by user; production listening pending','actual_billing_known':False}
    save(out/'voice-source.json',voice)
    state['status']='speech_generated';save(STATE,state)
    print(json.dumps({'event':'all_speech_verified','source':str(out/'voice-source.json')}),flush=True)

def prepare_video():
    state=read(STATE)
    if 'output' in state:raise ValueError('Video already prepared; use the recorded output')
    generation=generated_folder(state)
    check(read(generation/'plan.json')['story'])
    out=prepare(HERE/'creator-story.json',narration_source=generation/'voice-source.json')
    state.update(output=out.relative_to(ROOT).as_posix(),status='prepared');save(STATE,state)

def video_folder():
    state=read(STATE);out=(ROOT/state['output']).resolve(strict=True)
    if out.parent!=OUT:raise ValueError('Unexpected video output')
    return state,out

def render():
    state,out=video_folder()
    if not (out/'render.json').exists():run('node',ROOT/'studio/creator-render.mjs',out)
    if not (out/'verification.json').exists():finish(out)
    state['status']='awaiting_visual_review';save(STATE,state)

def review(note):
    if not note:raise ValueError('Inspect completed frames and provide a concrete review note')
    state,out=video_folder();proof=read(out/'verification.json');check(proof['delivery'])
    proof.update(review_status='verified_candidate_awaiting_user_review',user_approved=False,
        visual_review={'method':'AI-assisted visual inspection','note':note,'reviewed_at':datetime.now(timezone.utc).isoformat(),
                       'evidence':[record(p) for p in sorted(out.glob('preview-*.png'))]+[record(out/'contact-sheet.png')]},
        listening_review='Aoede selected by user in audition; final episode listening review pending.',
        fact_review={'checked_date':'2026-10-22','sources':record(HERE/'SOURCES_JA.md')})
    save(out/'verification.json',proof)
    state['status']=proof['review_status'];save(STATE,state)

def package():
    state,out=video_folder();proof=read(out/'verification.json')
    if proof['review_status']!='verified_candidate_awaiting_user_review':raise ValueError('Visual review required')
    check(proof['delivery'])
    for original in read(generated_folder(state)/'plan.json')['existing_deliveries']:check(original)
    release=out/'release';release.mkdir(exist_ok=False)
    name='dots-03-apps-aoede.mp4'
    for source,target in [(out/'shorts-creator.mp4',release/name),(out/'cover.png',release/'cover.png'),(out/'captions.srt',release/'captions.srt')]:
        shutil.copyfile(source,target)
    for filename in ['youtube-title.txt','youtube-description.txt','SOURCES_JA.md']:
        shutil.copyfile(HERE/filename,release/filename)
    story=read(out/'story.json')
    (release/'narration.txt').write_text('\n'.join(s['narration'] for s in story['scenes'])+'\n',encoding='utf-8')
    quality={'duration_seconds':30,'width':1080,'height':1920,'fps':24,'frames':720,'voice':'Aoede','model':speech.MODEL,
        'music_preset':story['music_preset'],'loudness':proof['loudness'],'full_decode_verified':True,
        'review_status':proof['review_status'],'final_listening_review':'pending','user_approved':False,'youtube_uploaded':False,
        'existing_9_episodes_and_supplement_unchanged':True,'information_checked_date':'2026-10-22',
        'caption_timing':'display-unit weighting inside measured speech, not word alignment'}
    save(release/'quality-report.json',quality)
    title=html.escape((HERE/'youtube-title.txt').read_text(encoding='utf-8').strip())
    description=html.escape((HERE/'youtube-description.txt').read_text(encoding='utf-8'))
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dotsのアプリ連携</title><style>body{margin:0;background:#0b1120;color:#f5f1e8;font:18px/1.8 system-ui,"Yu Gothic UI",sans-serif}main{max-width:1050px;margin:auto;padding:28px;display:grid;grid-template-columns:minmax(240px,360px) 1fr;gap:32px}video{width:100%;max-height:85vh;border-radius:18px}h1{font-size:30px;line-height:1.5}a{color:#dfff78}pre{white-space:pre-wrap;font:inherit}@media(max-width:720px){main{grid-template-columns:1fr}video{max-height:70vh}}</style><main><video controls playsinline preload="metadata" poster="cover.png" src="__VIDEO__"></video><section><p>DOTS 03 / アプリ連携 · 30秒</p><h1>__TITLE__</h1><p>Aoedeナレーション版。明るい112 BPMのオリジナルBGMと字幕付き。</p><p><a href="__VIDEO__" download>完成MP4を保存</a> / <a href="captions.srt" download>字幕</a> / <a href="SOURCES_JA.md">公式出典</a></p><details><summary>YouTubeの見出し・説明欄</summary><pre>__TITLE__</pre><pre>__DESCRIPTION__</pre></details><p>技術・完成画面の確認済み。最終試聴とYouTube公開は利用者確認用。</p></section></main></html>'''
    (release/'index.html').write_text(page.replace('__VIDEO__',name).replace('__TITLE__',title).replace('__DESCRIPTION__',description),encoding='utf-8')
    manifest={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest().upper()} for p in sorted(release.iterdir())}
    save(release/'manifest.json',manifest)
    archive=out/'dots-03-apps-aoede.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for p in sorted(release.iterdir()):z.write(p,p.name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for filename,item in manifest.items():
            if hashlib.sha256(z.read(filename)).hexdigest().upper()!=item['sha256']:raise ValueError('ZIP hash mismatch')
    delivery={'release':release.relative_to(ROOT).as_posix(),'video':record(release/name),'archive':record(archive),
        'crc_and_all_member_hashes_verified':True,'members':len(manifest)+1,'quality':quality}
    save(out/'delivery.json',delivery);save(HERE/'delivery.json',delivery)
    state['status']='packaged';save(STATE,state)
    print(json.dumps({'event':'packaged','video':str(release/name),'bytes':(release/name).stat().st_size,'sha256':record(release/name)['sha256']},ensure_ascii=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['generate','prepare','render','review','package'])
    parser.add_argument('--note')
    args=parser.parse_args()
    try:
        if args.command=='generate':generate()
        elif args.command=='prepare':prepare_video()
        elif args.command=='render':render()
        elif args.command=='review':review(args.note)
        else:package()
    except Exception as error:
        print(json.dumps({'status':'error','error_type':type(error).__name__,
            'message':str(error) if isinstance(error,(ValueError,RuntimeError)) else 'Production stopped; inspect local state without resubmitting speech.'},ensure_ascii=True),flush=True)
        raise SystemExit(1)
