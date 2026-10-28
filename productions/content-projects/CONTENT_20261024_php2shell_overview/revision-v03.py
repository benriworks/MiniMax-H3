"""Japan relevance and illustrated server-side PHP; preserve prior deliveries."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import copy
import importlib.util
import json
import sys
import wave

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import read,record,check,validate_story,narration_inputs,load_supplied_narration,allocate_scenes,prepare as prepare_short
OUT=ROOT/'outputs/content-projects'/HERE.name
VOICE=ROOT/'outputs/productions/SHORT_20261024_php2shell_overview/voice-source-v03.json'

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build():
    baseline=read(HERE/'creator-story-v02.json')
    def scene(kind,headline,captions,**kw):
        return dict(kind=kind,headline=headline,narration=''.join(captions).replace('\n',''),captions=captions,**kw)
    hook=copy.deepcopy(baseline['scenes'][0])
    hook.update(headline='WordPressも\n他人事ではない',narration='WordPressのサイトも、他人事ではありません。',captions=['WordPressのサイトも、','他人事ではありません。'])
    additions=[hook,
        scene('stat','日本国内サーバーの\nPHP利用率',['日本国内のサーバーでは、','言語を判別できたサイトの','9割以上がPHPです。'],
            eyebrow='W3Techs / 2026.10.24',tone='light',stat='92.4%',body='サーバー側の言語を\n判別できたサイト'),
        scene('diagram','WordPressも\nPHPで動く',['PHPは、WordPressや','フォーム、買い物の\n仕組みを','動かす言語です。'],
            eyebrow='PHPで動くサービスの例',tone='light',graphic='web-services'),
        scene('diagram','人がアクセス\nサーバーで処理',['アクセスを受けると、','サーバーで処理し、','結果を画面に返します。'],
            eyebrow='処理する場所はサーバー',tone='light',graphic='web-flow'),
    ]
    old=copy.deepcopy(baseline['scenes'][1:])
    # The announcement keeps its verified narration but now uses actual evidence.
    old[0]={**copy.deepcopy(baseline['scenes'][2]),'headline':'10月21日\nPHPに重大な不具合','narration':old[0]['narration'],'captions':old[0]['captions']}
    old[1].update(kind='editorial',editorial_layout='permissions',headline='通称PHP2Shell\n2件の重大な不具合',eyebrow='構成などで成立条件が異なる',body='PHP本体の脆弱性')
    old[1].pop('capture');old[1].pop('visual_style')
    old[-1]['eyebrow']='2026年10月25日確認'
    result={**baseline,'title':'【PHP】WordPressも要確認！PHP2Shellの概要と対策','duration_seconds':60,
        'pronunciations':baseline['pronunciations']+[{'source':'WordPress','target':'ワードプレス'}], 'scenes':additions+old}
    validate_story(result)
    path=HERE/'creator-story-v03.json'
    if path.exists() and read(path)!=result:raise ValueError('Frozen revision changed; use v04')
    save(path,result)
    (HERE/'narration-final-v03.txt').write_text('\n'.join(s['narration'] for s in result['scenes'])+'\n',encoding='utf-8')
    captures=OUT/'captures/revision-v03'
    evidence=[]
    for filename,url,purpose in [
        ('w3techs-original.jpg','https://w3techs.com/technologies/breakdown/pl-php/server_location','Japan 92.4%; server-side language known, server location Japan; data date 2026-10-24'),
        ('wordpress-original.jpg','https://wordpress.org/about/requirements/','WordPress official PHP host requirement; not a recommendation to use unpatched PHP 8.3'),
    ]:
        target=captures/filename
        evidence.append({'artifact':record(target),'source_url':url,'purpose':purpose,'captured_at':datetime.fromtimestamp(target.stat().st_mtime,timezone.utc).isoformat(),'privacy_review':'passed','ai_visual_review':'original inspected; no private data','visibility':'private'})
    save(captures/'capture-preflight.json',{'checked_at':'2026-10-25','status':'available_and_saved','app':'in-app browser','login':'not_required','save_method':'Computer Use screenshot; original JPEG bytes retained','captures':evidence,'usage':'research evidence; video uses attributed factual statistic and original conceptual illustrations'})
    print('Twelve scenes / 60 seconds; four new voice segments, eight reusable')

def voice():
    spec=importlib.util.spec_from_file_location('php_v03_shared',ROOT/'productions/SERIES_20261022_dots_finale/produce.py')
    shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
    script=read(HERE/'creator-story-v03.json')
    previous=read(OUT/'voice/v01/voice-source.json')
    previous_story=read(HERE/'creator-story-v02.json')
    destination=OUT/'voice/v03';destination.mkdir(parents=True,exist_ok=True)
    plan={'inputs':narration_inputs(script),'maximum_new_requests':4,'reused_previous_scene_indices':list(range(1,9)),'automatic_retry':False,'voice':'Aoede','model':shared.speech.MODEL}
    if (destination/'plan.json').exists() and read(destination/'plan.json')!=plan:raise ValueError('Frozen speech inputs changed')
    save(destination/'plan.json',plan)
    if VOICE.exists():
        load_supplied_narration(script,VOICE);print('Verified voice reused; zero requests');return
    pieces=[];segments=[];proofs=[];usage=[]
    with shared.generation_lock():
        cadence=shared.SubmissionCadence()
        for index,scene in enumerate(script['scenes']):
            if index<4:
                parent=destination/f'scene-{index:02d}';parent.mkdir(exist_ok=True)
                spoken=scene['narration']
                for rule in sorted(script['pronunciations'],key=lambda x:-len(x['source'])):spoken=spoken.replace(rule['source'],rule['target'])
                if not (parent/'Aoede').exists():cadence.before_submission()
                proof=shared.speech.synthesize(parent,spoken,'Aoede',minimum_seconds=.2)
                proof_record=record(parent/'Aoede/verified.json')
            else:
                old_index=index-3
                assert previous_story['scenes'][old_index]['narration']==scene['narration']
                proof_record=previous['generation_proofs'][old_index]
                proof=read(check(proof_record))
            wav_path=check(next(a for a in proof['files'] if a['path'].endswith('/voice.wav')))
            with wave.open(str(wav_path),'rb') as wav:
                assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())==(1,2,24000)
                frames=wav.getnframes();pieces.append(wav.readframes(frames))
            segments.append({'index':index,'text':scene['narration'],'frames':frames,'duration_ms':round(frames/24)})
            proofs.append(proof_record);usage.append(proof['usage'])
            print(json.dumps({'scene':index,'speech_seconds':frames/24000,'reused':index>=4}),flush=True)
    with wave.open(str(destination/'narration.wav'),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'));wav.writeframes(b''.join(pieces))
    save(destination/'timings.json',{'schema_version':1,'provider':'gemini','timing_source':'wav_frames','segments':segments})
    save(VOICE,{'provider':'gemini','model':shared.speech.MODEL,'voice':'Aoede','inputs':narration_inputs(script),'timing_source':'wav_frames',
        'external_api_calls':4,'verified_requests':4,'reused_verified_segments':8,'historical_api_calls':9,'total_project_api_calls':13,'unknown_previous_requests':0,
        'generation_proofs':proofs,'usage':usage,'usage_scope':'includes eight historically generated segments',
        'artifacts':[dict(record(destination/name),name=name) for name in ['narration.wav','timings.json']],
        'voice_selection':'User-selected Aoede; final revision listening pending','actual_billing_known':False})
    load_supplied_narration(script,VOICE)
    cuts=allocate_scenes([s['duration_ms'] for s in segments],60*24)
    save(destination/'allocation.json',{'speech_seconds':sum(s['frames'] for s in segments)/24000,'scene_frames':cuts})
    print(json.dumps({'event':'speech_ready','scene_seconds':[n/24 for n in cuts]}),flush=True)

def prepare():
    state=HERE/'render-state-v03.json'
    if state.exists():
        p=ROOT/read(state)['output']
        for item in read(p/'preparation.json')['sources']:check(item)
        print(p);return
    output=prepare_short(HERE/'creator-story-v03.json',narration_source=VOICE)
    save(state,{'output':output.relative_to(ROOT).as_posix(),'revision':'v03','stage':'prepared','user_approved':False})
    print(output)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['build','voice','prepare']);args=p.parse_args();globals()[args.command]()
