"""Full-dialogue independent audio assistance and verifiable media checks."""
from pathlib import Path
import argparse,base64,hashlib,json,os,re,subprocess,sys,urllib.request,urllib.error
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import pcm
from tools.studio.dialogue_avatar import DialogueDriver,validate_windows
OUT=ROOT/'outputs/productions'/HERE.name/'v03'


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def audio_check():
    folder=OUT/'audio/ai-dialogue-review'
    if folder.exists():raise ValueError('Existing request; inspect the result before any new request')
    key=os.environ.get('GEMINI_API_KEY')
    if not key:raise ValueError('Gemini key unavailable')
    folder.mkdir(parents=True);audio=folder/'full-mix.mp3'
    subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(OUT/'audio/mix-premaster.wav'),'-c:a','libmp3lame','-b:a','128k',str(audio)],check=True)
    prompt='この日本語の男女の会話音声を最初から最後まで実際に聞いて点検してください。期待原稿は渡しません。JSONでtranscript（話者と実際に聞こえた各台詞全文）、pronunciation_observed（製品名、表の読み、数字）、audible_issues（余分な発話、読み間違い、音切れ、音量、BGMで不明瞭な箇所を時刻付きで。なければ空配列）、conversation_flow（男性の質問に女性が答え、作業を案内しているか）、music_impression（聞こえる曲調）、uncertaintiesを返してください。聞こえない語句を推測で補わないでください。'
    model='gemini-3.8-flash'
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],
        generationConfig=dict(responseMimeType='application/json',maxOutputTokens=9000))
    save(folder/'submission.json',dict(status='submitted',model=model,automatic_retry=False,prompt=prompt,
        audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest()))
    request=urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.build_opener(pcm.NoRedirect()).open(request,timeout=180) as response:data=json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as error:
        detail=re.sub(r'AIza[\w-]+|(?:key|token)=[^ &]+','[redacted]',error.read(32768).decode('utf-8',errors='replace'),flags=re.I)
        save(folder/'failure.json',dict(status='rejected',http_status=error.code,detail=detail[:1000],automatic_retry=False))
        raise RuntimeError('Audio check rejected; no automatic retry') from None
    except Exception:
        save(folder/'failure.json',dict(status='unknown',automatic_retry=False));raise
    save(folder/'response.json',data)
    result=json.loads(''.join(p.get('text','') for p in data['candidates'][0]['content']['parts']))
    result.update(model=model,verification='AI assistance; human final listening pending',usage=data.get('usageMetadata',{}),finish_reason=data['candidates'][0].get('finishReason'))
    save(folder/'review.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='transcript'},ensure_ascii=False),flush=True)


def technical():
    movie=OUT/'dots-transfer-detail-v03.mp4';plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(movie)]))
    v=next(s for s in probe['streams'] if s['codec_type']=='video');a=next(s for s in probe['streams'] if s['codec_type']=='audio')
    if (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))!=(1920,1080,'24/1',plan['frames']):raise ValueError('Unexpected video geometry or frames')
    if (a['codec_name'],a['sample_rate'],a['channels'])!=('aac','48000',2):raise ValueError('Unexpected audio format')
    decoded=subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(movie),'-f','null','-'],capture_output=True,text=True,check=True)
    if decoded.stderr.strip():raise ValueError('Decode diagnostics')
    stderr=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(movie),'-af','loudnorm=I=-16:TP=-1.2:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
    loud=json.JSONDecoder().raw_decode(stderr[stderr.rfind('{'):])[0];save(OUT/'audio/loudness-final.json',loud)
    if not -17<=float(loud['input_i'])<=-15 or float(loud['input_tp'])>-.9:raise ValueError('Review loudness')
    source=json.loads((OUT/'source-manifest.json').read_text(encoding='utf-8'))
    for item in source['old_videos_preserved']:
        if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Old movie changed')
    cuts=json.loads((OUT/'cut-map.json').read_text(encoding='utf-8'))
    config=json.loads((OUT/'render-config.json').read_text(encoding='utf-8'));audit=json.loads((OUT/'pip-policy-audit.json').read_text(encoding='utf-8'))
    validate_windows(config['windows_in_main_seconds'],round((plan['seconds']-plan['main_offset'])*24)/24,audit['protected'])
    moments=[0,1.5,3.5,4.7,*[(t['start']+t['end'])/2 for t in plan['chapters'][0]['turns']]]
    moments += [plan['main_offset']+(c['start']+c['end'])/2 for c in cuts]
    driver=DialogueDriver([t for c in plan['chapters'] for t in c['turns']])
    for speaker in ['male','female']:
        found={}
        for window in config['windows_in_main_seconds']:
            for frame in range(round((window['start']+plan['main_offset'])*24),round((window['end']+plan['main_offset'])*24)):
                time=frame/24;state=driver.state(time,speaker)
                if state['speaking']:found.setdefault(state['opened'],time)
            if len(found)==2:break
        if len(found)!=2:raise ValueError('Speech opening and closing states missing')
        moments+=list(found.values())
    qa=OUT/'qa';qa.mkdir(exist_ok=True);records=[]
    for i,time in enumerate(moments):
        path=qa/f'final-{i:02d}.jpg'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(time),'-i',str(movie),'-frames:v','1','-q:v','2',str(path)],check=True)
        records.append(dict(path=path.name,seconds=time))
    for page,start in enumerate(range(0,len(records),12),1):
        sheet=Image.new('RGB',(1440,1168),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for i,item in enumerate(records[start:start+12]):
            x,y=i%3*480,i//3*292;sheet.paste(Image.open(qa/item['path']).resize((480,270)),(x,y));draw.text((x+8,y+273),f"{item['seconds']:.3f}s",fill='black')
        sheet.save(qa/f'final-contact-{page:02d}.jpg',quality=94)
    save(qa/'final-frames.json',records)
    proofs=list((OUT/'voice').glob('*/turn-*/verified.json'));failures=list((OUT/'voice').glob('*/turn-*/failure.json'))
    if len(proofs)!=44 or failures:raise ValueError('Inspect voice request counts')
    save(OUT/'technical-verification.json',dict(status='technically_verified_review_pending',full_decode=True,loudness=loud,
        video=dict(path=movie.name,bytes=movie.stat().st_size,sha256=hashlib.sha256(movie.read_bytes()).hexdigest(),probe=probe),
        new_tts_successes=44,new_minimax_calls=0,new_imagegen_calls=0,old_videos_preserved=True,real_recording_speed=1,
        visual_sample_frames=len(records),mouth='PCM-envelope simple animation; not phoneme-aligned',human_final_listening=False,
        user_final_approval=False,published=False,mobile_device_playback_verified=False))
    print('Technical checks passed',plan['seconds'],'seconds;',len(records),'sample frames;',loud['input_i'],'LUFS',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['audio','technical']);a=p.parse_args()
    (audio_check if a.command=='audio' else technical)()
