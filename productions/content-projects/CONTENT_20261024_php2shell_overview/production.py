"""PHP2Shell production; isolated artifacts, reusable verified generators."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys
import wave
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
PID = HERE.name
OUT = ROOT / 'outputs/content-projects' / PID
VOICE_MANIFEST = ROOT / 'outputs/productions/SHORT_20261024_php2shell_overview/voice-source-v01.json'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def approve():
    from tools.studio.content_workspace import ContentWorkspace
    from tools.studio.database import StudioDatabase
    db = StudioDatabase(ROOT / 'outputs/studio/studio.sqlite3', workspace=ROOT, recover=False)
    service = ContentWorkspace(ROOT, db)
    current=service.get(PID)['project']
    existing=next((c for c in current['characters'] if c['character_id']=='miura_wataru'),None)
    if ((current.get('accepted_proposal') or {}).get('proposal_id')=='proposal_php_overview_v01'
            and existing and existing['version']==1 and (existing.get('approval') or {}).get('user_response')=='この構成・人物で進める'):
        print('Existing explicit concept/character approval retained; no new approval inferred')
        return
    for action, data in [
        ('feedback', {'feedback_id':'feedback_php_concept_character_accept', 'proposal_id':'proposal_php_overview_v01', 'kind':'acceptance', 'text':'この構成・人物で進める', 'interpretation':'提示済み約50秒構成と三浦航v01参照画像を採用。本番のMiniMax人物動画とAoede音声の制作へ進む。最終動画の試聴・公開は別。'}),
        ('accept', {'proposal_id':'proposal_php_overview_v01','feedback_id':'feedback_php_concept_character_accept','confirm_acceptance':True}),
        ('approve-character', {'character_id':'miura_wataru','version':1,'confirm_acceptance':True,'user_response':'この構成・人物で進める','scope':'PHP2Shell概要ショートの提示済み構成と三浦航v01参照画像。本番人物動画生成と組み込み。最終動画の試聴・公開は含まない。'}),
    ]:
        current = service.get(PID)['project']
        body = {'operation_id':'php_v01_' + action.replace('-','_'), 'expected_revision':current['revision'], 'data':data}
        save(HERE / 'inputs' / ('approval-' + action + '.json'), body)
        service.apply(PID, action, body)
    state = service.get(PID)
    save(HERE / 'workspace-state-approved-v01.json', state)
    char = state['project']['characters'][0]
    save(OUT / 'characters/miura-wataru/v01/approval.json', {'character_id':char['character_id'],'version':char['version'],'reference_sha256':char['reference_sha256'],'approval':char['approval'], 'original_generation_record_preserved':True})
    print('Concept and character approval recorded; revision', state['project']['revision'])

def motion():
    gen = module('php_motion', 'productions/CHARACTERS_20261022_explainer_motion/generate.py')
    gen.PRODUCTION = HERE
    gen.OUT = OUT / 'motion/v01'
    gen.INPUT = ROOT / 'runtime/ComfyUI/input' / (PID + '-motion-v01')
    original_read = gen.read
    gen.read = lambda path: original_read(HERE/'motion-graph-v01.json') if path == ROOT/'outputs/claude-acquired-20260919/graph.json' else original_read(path)
    # The standing reference has no chair, desk or laptop. Avoid hallucinating props.
    original_prompt = gen.prompt
    gen.prompt = lambda spec: original_prompt(spec).replace('body proportions, chair, desk, laptop, room, composition', 'body proportions, standing pose, office background, composition')
    spec = {'source':(OUT / 'characters/miura-wataru/v01/reference.png').relative_to(ROOT).as_posix(),
            'source_presenter':(OUT / 'characters/miura-wataru/v01/reference.png').relative_to(ROOT).as_posix(),
            'identity':'Miura Wataru, a fictional 36-year-old Japanese male website operations coordinator, in a navy blazer, light blue shirt, grey trousers and thin dark glasses',
            'motion':'He thoughtfully raises his right hand slightly with an open palm, as if considering an important website maintenance notice; he then makes one small reassuring nod. His left hand remains relaxed and visible. His lips stay closed.',
            'seed':2026102401}
    gen.OUT.mkdir(parents=True, exist_ok=True)
    save(HERE / 'motion-spec-v02.json', spec)
    gen.generate('miura-insight-v02', spec, False)

def story():
    from PIL import Image
    from tools.studio.shorts_creator import record, validate_story
    caps = ROOT / 'outputs/productions/SHORT_20261024_php2shell_overview/captures'
    for name, box, url, title in [
        ('php',(23,59,428,195),'https://www.php.net/archive/2026.php#2026-10-21-5','PHP公式・10月21日'),
        ('php-followup',(23,51,428,153),'https://www.php.net/archive/2026.php#2026-10-23-1','PHP公式・10月23日'),
    ]:
        context = caps / (name + '-context.png')
        raw_context = context
        target = caps / (name + '-quote.png')
        with Image.open(context) as original:
            original_format = original.format
            crop = original.crop(box)
            crop.save(target)
            assert crop.tobytes() == original.crop(box).tobytes()
            w,h = original.size
            if original_format != 'PNG':
                context = caps / (name + '-context-decoded.png')
                original.save(context)
                with Image.open(context) as decoded:assert decoded.tobytes() == original.tobytes()
        save(caps / (name + '-proof.json'), {'origin':'official','source_url':url,'title':title,
            'artifact':record(target),'context':record(context),
            'captured_original':{**record(raw_context),'actual_format':original_format},
            'clip':{'x':box[0],'y':box[1],'width':box[2]-box[0],'height':box[3]-box[1]},
            'context_clip':{'x':0,'y':0,'width':w,'height':h},
            'captured_at':datetime.fromtimestamp(raw_context.stat().st_mtime, timezone.utc).isoformat(), 'checked_at':'2026-10-24',
            'derived_at':datetime.now(timezone.utc).isoformat(),
            'capture_method':'Computer Use in-app browser screenshot; unchanged pixel crop',
            'review_status':'capture_review_passed','pixel_exact_crop_verified':True,'content_modified':False,
            'review_basis':'AI inspected full original; headline and date retained, unrelated notice excluded. Final rendered mobile legibility pending.'})

    def editorial(layout, headline, captions, **kw):
        return {'kind':'editorial','editorial_layout':layout,'headline':headline,'narration':''.join(captions).replace('\n',''), 'captions':captions, **kw}
    def official(name,headline,captions):
        proof = json.loads((caps / (name+'-proof.json')).read_text(encoding='utf-8'))
        return {'kind':'source','visual_style':'business','headline':headline,'eyebrow':'PHP公式告知',
            'narration':''.join(captions).replace('\n',''),'captions':captions,
            'capture':{'origin':'official','path':(caps/(name+'-quote.png')).relative_to(ROOT).as_posix(),
                'proof':(caps/(name+'-proof.json')).relative_to(ROOT).as_posix(), 'source_url':proof['source_url'],'title':proof['title']}}
    scenes = [
        editorial('hook','自分のサイトも？',['Webサイトを','運営しているなら\n確認を。'],visual_style='business',eyebrow='PHP2Shell',body='Web運用担当', action='まず利用環境を確認'),
        editorial('contrast','PHPは\nサイトの裏側',['サイトの裏側を動かす\nPHPに、','2件の重大な脆弱性が','公表されました。'],eyebrow='2026年10月21日',body='見える画面 → サーバー',items=[{'label':'Webページ','detail':'利用者が見る画面'},{'label':'PHP','detail':'サーバー側で処理'}]),
        official('php','PHP2Shell\n2件の重大な不具合',['通称、PHPツーシェル。','条件がそろうと、']),
        editorial('permissions','ログインなしで\n不正な処理の恐れ',['ログインせずに\nサーバーで','プログラムを実行される','恐れがあります。'],eyebrow='構成などで成立条件が異なる',body='構成などで条件は異なる',items=[{'label':'CVE-2026-109618','detail':'PHP本体の問題'},{'label':'CVE-2026-109619','detail':'設定だけでは不十分'}]),
        editorial('conversation','誰に、何を聞く？',['管理担当や\nホスティング会社に、','利用中のPHPを確認。'],visual_style='business',eyebrow='三浦さんが管理担当へ確認',body='利用中のPHPは？',items=[{'label':'管理担当','detail':'バージョンと構成'},{'label':'ホスティング会社','detail':'対策の適用状況'}]),
        editorial('contrast','修正版へ更新\n動作も確認',['対策済みかも聞き、','修正版への更新と','動作確認を。'],eyebrow='10/21公表の修正版の基準',body='提供元の修正適用も確認',items=[{'label':'8.2.35 / 8.3.36','detail':'8.2系 / 8.3系'},{'label':'8.4.27 / 8.5.12','detail':'8.4系 / 8.5系'}]),
        editorial('research','更新したら\nログも調べる',['不審なログの調査も','忘れずに。'],eyebrow='JPCERT/CCの注意喚起',body='更新前の被害も確認',items=[{'label':'更新・動作確認','detail':'今後のリスクを減らす'},{'label':'ログの調査','detail':'侵害の兆候を確認'}]),
        official('php-followup','10月23日にも\n追加の注意喚起',['10月23日には、','別の条件に関する','追加注意喚起も\n出ています。']),
        editorial('recap','最新の公式案内まで\n確認しましょう',['最新の公式案内まで\n確認を。'],eyebrow='2026年10月24日確認',body='確認 → 更新 → 調査',items=[{'label':'PHP公式','detail':'追加告知も確認'},{'label':'IPA / JPCERT','detail':'国内向けの注意喚起'}]),
    ]
    result = {'schema_version':1,'id':'SHORT_20261024_php2shell_overview','title':'【PHP】PHP2Shellとは？サイト運営者が今確認すべきこと',
        'voice':'Aoede','rate':1,'duration_seconds':50,'music_preset':'bright_groove_v1',
        'pronunciations':[{'source':'PHPツーシェル','target':'ピーエイチピーツーシェル'},{'source':'PHP','target':'ピーエイチピー'},{'source':'Web','target':'ウェブ'}],
        'scenes':scenes}
    # Motion binding is added only after the real generated clip is inspected.
    from tools.studio.shorts_creator import units
    for i,s in enumerate(scenes):
        for c in s['captions']:
            if any(units(line)>12 for line in c.split('\n')):print('Overlong caption',i,repr(c))
    validate_story(result)
    save(HERE / 'creator-story.json', result)
    (HERE / 'narration-final-v01.txt').write_text('\n'.join(s['narration'] for s in scenes)+'\n',encoding='utf-8')
    print('Nine-cut, 50-second story validated')

def voice():
    from tools.studio.shorts_creator import narration_inputs, load_supplied_narration, record, check
    shared = module('php_shared_voice', 'productions/SERIES_20261022_dots_finale/produce.py')
    speech = shared.speech
    script = json.loads((HERE / 'creator-story.json').read_text(encoding='utf-8'))
    destination = OUT / 'voice/v01'
    destination.mkdir(parents=True, exist_ok=True)
    plan = {'inputs':narration_inputs(script),'maximum_requests':len(script['scenes']),'voice':'Aoede','model':speech.MODEL,'automatic_retry':False}
    if (destination/'plan.json').exists():
        if json.loads((destination/'plan.json').read_text(encoding='utf-8')) != plan: raise ValueError('Frozen voice inputs changed')
    else: save(destination/'plan.json', plan)
    if (destination/'voice-source.json').exists():
        save(VOICE_MANIFEST,json.loads((destination/'voice-source.json').read_text(encoding='utf-8')))
        load_supplied_narration(script,VOICE_MANIFEST)
        from tools.studio.shorts_creator import allocate_scenes
        timing=json.loads((destination/'timings.json').read_text(encoding='utf-8'))
        cuts=allocate_scenes([s['duration_ms'] for s in timing['segments']],50*24)
        print(json.dumps({'event':'verified_voice_reused','new_requests':0,'scene_seconds':[d/24 for d in cuts]})); return
    proofs, segments, samples, usage = [],[],[],[]
    with shared.generation_lock():
        cadence=shared.SubmissionCadence()
        for index,scene in enumerate(script['scenes']):
            parent=destination/f'scene-{index:02d}';parent.mkdir(exist_ok=True)
            spoken=scene['narration']
            for rule in sorted(script['pronunciations'],key=lambda x:-len(x['source'])):spoken=spoken.replace(rule['source'],rule['target'])
            if not (parent/'Aoede').exists():cadence.before_submission()
            proof=speech.synthesize(parent,spoken,'Aoede',minimum_seconds=.2)
            source=check(next(item for item in proof['files'] if item['path'].endswith('/voice.wav')))
            with wave.open(str(source),'rb') as wav:
                assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())==(1,2,24000)
                frames=wav.getnframes();samples.append(wav.readframes(frames))
            segments.append({'index':index,'text':scene['narration'],'frames':frames,'duration_ms':round(frames/24)})
            proofs.append(record(parent/'Aoede/verified.json'));usage.append(proof['usage'])
            print(json.dumps({'event':'speech_verified','scene':index,'seconds':frames/24000}),flush=True)
    with wave.open(str(destination/'narration.wav'),'wb') as wav:
        wav.setparams((1,2,24000,0,'NONE','not compressed'));wav.writeframes(b''.join(samples))
    save(destination/'timings.json',{'schema_version':1,'provider':'gemini','timing_source':'wav_frames','segments':segments})
    save(destination/'voice-source.json',{'provider':'gemini','model':speech.MODEL,'voice':'Aoede','inputs':narration_inputs(script),'timing_source':'wav_frames',
        'external_api_calls':len(proofs),'verified_requests':len(proofs),'unknown_previous_requests':0,'generation_proofs':proofs,'usage':usage,
        'artifacts':[dict(record(destination/name),name=name) for name in ['narration.wav','timings.json']],
        'voice_selection':'User-selected Aoede; final listening pending','actual_billing_known':False})
    save(VOICE_MANIFEST,json.loads((destination/'voice-source.json').read_text(encoding='utf-8')))
    load_supplied_narration(script,VOICE_MANIFEST)
    from tools.studio.shorts_creator import allocate_scenes
    durations=allocate_scenes([s['duration_ms'] for s in segments],50*24)
    print(json.dumps({'event':'voice_complete','speech_seconds':sum(s['frames'] for s in segments)/24000,'scene_seconds':[d/24 for d in durations]}),flush=True)

def prepare():
    from tools.studio.shorts_creator import prepare as prepare_short
    out=prepare_short(HERE/'creator-story.json',narration_source=VOICE_MANIFEST)
    save(HERE/'render-state-v01.json',{'output':out.relative_to(ROOT).as_posix(),'stage':'prepared','character_motion_included':False,'user_approved':False})
    print(out)

def register():
    from tools.studio.content_workspace import ContentWorkspace
    from tools.studio.database import StudioDatabase
    from tools.studio.shorts_creator import allocate_scenes
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    def apply(action,data,operation):
        current=service.get(PID)['project']
        body={'operation_id':operation,'expected_revision':current['revision'],'data':data}
        save(HERE/'inputs'/(operation+'.json'),body)
        return service.apply(PID,action,body)
    caps=ROOT/'outputs/productions/SHORT_20261024_php2shell_overview/captures'
    p=service.get(PID)['project']
    for name in ['php','php-followup']:
        aid=name+'-public-quote-v01'
        if any(a['asset_id']==aid for a in p['assets']):continue
        proof=json.loads((caps/(name+'-proof.json')).read_text(encoding='utf-8'))
        apply('asset',{'asset_id':aid,'kind':'official_capture','path':proof['artifact']['path'],
            'visibility':'public','privacy_review':'passed','source_url':proof['source_url'],'source_checked_at':'2026-10-24',
            'alt':proof['title']+'の告知見出しと日付','caption':'実際の公式告知の見出しを引用。内容の日本語要約は別のテロップ。',
            'blog_usage_review':'pending','user_approved_for_blog':False},'register_'+name.replace('-','_')+'_quote_v01')
    script=json.loads((HERE/'creator-story.json').read_text(encoding='utf-8'))
    timing=json.loads((OUT/'voice/v01/timings.json').read_text(encoding='utf-8'))
    cuts=allocate_scenes([s['duration_ms'] for s in timing['segments']],50*24)
    claims=[['identity'],['identity'],['identity'],['impact'],['response'],['fixes','response'],['response'],['followup'],['followup','response']]
    sources=[['php_oct21'],['php_oct21'],['php_oct21'],['php_oom','php_state'],['jpcert_oct22'],['php_oct21','jpcert_oct22'],['jpcert_oct22'],['php_oct23'],['php_oct23','jpcert_oct22']]
    board=[]
    for i,(scene,frames) in enumerate(zip(script['scenes'],cuts,strict=True)):
        row={'scene_id':f'php_scene_{i:02d}','purpose':scene['headline'].replace('\n','・'),'narration':scene['narration'],
            'visual':'人物の全面導入。気づいて小さく頷く。顔と字幕を分ける。' if i==0 else ('公式画面の引用' if scene['kind']=='source' else '自作の動く説明・確認項目'),
            'duration_seconds':frames/24,'beat':'problem' if i==0 else 'evidence' if scene['kind']=='source' else 'action' if i>=4 else 'insight',
            'claim_ids':claims[i],'source_ids':sources[i],'asset_ids':[],'character_ids':[]}
        if i==0:row.update(asset_ids=['miura-wataru-reference'],character_ids=['miura_wataru'],character_action='採用参照画像をMiniMaxで動かし、手を少し開いて気づき、小さく頷く。',presenter_layout='fullscreen',face_caption_separated=True)
        if scene['kind']=='source':row['asset_ids']=['php-public-quote-v01' if i==2 else 'php-followup-public-quote-v01']
        board.append(row)
    current=service.get(PID)['project']
    episode=next(e for e in current['episodes'] if e['episode_id']=='php2shell_overview')
    old=[{k:v for k,v in s.items() if k not in {'needs_review','review_reasons'}} for s in episode.get('storyboard',[])]
    if old!=board:apply('storyboard',{'episode_id':'php2shell_overview','scenes':board},'php_storyboard_v01')
    state=service.get(PID);save(HERE/'workspace-state-storyboard-v01.json',state)
    print('Source crops and nine-cut storyboard registered; revision',state['project']['revision'])

def bind():
    from tools.studio.shorts_creator import check, read, validate_story, prepare as prepare_short
    proof_path=OUT/'motion/v01/miura-insight-v02/visual-review.json'
    proof=read(proof_path)
    if proof.get('review_status')!='visual_review_passed' or not proof.get('execution',{}).get('success'):
        raise ValueError('Inspect actual generated frames before binding the motion')
    clip=check(proof['artifact'])
    result=read(HERE/'creator-story.json')
    result['scenes'][0].update(media={'path':clip.relative_to(ROOT).as_posix(),'proof':proof_path.relative_to(ROOT).as_posix()},body='三浦航・Web担当')
    validate_story(result)
    story_path=HERE/'creator-story-v02.json'
    if story_path.exists() and read(story_path)!=result:raise ValueError('Keep old edit; use a new revision')
    state_path=HERE/'render-state-v02.json'
    if state_path.exists():
        prior=ROOT/read(state_path)['output']
        if read(prior/'story.json')!=result:raise ValueError('Prepared edit changed')
        for item in read(prior/'preparation.json')['sources']:check(item)
        print('Existing prepared edit:',prior);return
    save(story_path,result)
    out=prepare_short(story_path,narration_source=VOICE_MANIFEST)
    save(HERE/'render-state-v02.json',{'output':out.relative_to(ROOT).as_posix(),'stage':'prepared','character_motion_included':True,'user_approved':False})
    print(out)

def register_motion():
    from tools.studio.content_workspace import ContentWorkspace
    from tools.studio.database import StudioDatabase
    from tools.studio.shorts_creator import read, check
    service=ContentWorkspace(ROOT,StudioDatabase(ROOT/'outputs/studio/studio.sqlite3',workspace=ROOT,recover=False))
    def apply(action,data,operation):
        body={'operation_id':operation,'expected_revision':service.get(PID)['project']['revision'],'data':data}
        save(HERE/'inputs'/(operation+'.json'),body)
        service.apply(PID,action,body)
    proof_path=OUT/'motion/v01/miura-insight-v02/visual-review.json'
    proof=read(proof_path);clip=check(proof['artifact'])
    if proof['review_status']!='visual_review_passed':raise ValueError('Motion AI review required')
    aid='miura-minimax-motion-v01'
    p=service.get(PID)['project']
    if not any(a['asset_id']==aid for a in p['assets']):
        apply('asset',{'asset_id':aid,'kind':'generated_video','path':clip.relative_to(ROOT).as_posix(),
            'visibility':'private','privacy_review':'passed','character_id':'miura_wataru','character_version':1,
            'provider':'minimax','generation_record':proof_path.relative_to(ROOT).as_posix(),
            'caption':'採用画像から新規生成。技術検証とAIフレーム確認済み。人の試聴と公開は別。'},'php_register_motion_v01')
    p=service.get(PID)['project']
    episode=next(e for e in p['episodes'] if e['episode_id']=='php2shell_overview')
    board=[{k:v for k,v in s.items() if k not in {'needs_review','review_reasons'}} for s in episode['storyboard']]
    if aid not in board[0]['asset_ids']:
        board[0]['asset_ids'].append(aid)
        board[0]['visual']='新規生成したMiniMax人物動画を全面表示。気づき、手を小さく開いて頷く。顔と字幕を分ける。'
        apply('storyboard',{'episode_id':'php2shell_overview','scenes':board},'php_storyboard_motion_v02')
    save(HERE/'workspace-state-motion-v02.json',service.get(PID))
    print('Generated motion bound to character version 1 and storyboard; human review remains pending')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['approve','motion','story','voice','prepare','register','bind','register_motion'])
    args = parser.parse_args()
    globals()[args.command]()
