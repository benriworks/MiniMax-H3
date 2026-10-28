"""Technical revision checks and a single bounded independent intro-audio check."""
from pathlib import Path
import argparse,base64,hashlib,json,os,re,subprocess,sys,urllib.request,urllib.error
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v02';OLD=OUT.parent/'v01'
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import pcm
from tools.studio.dialogue_avatar import DialogueDriver


def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def audio_check():
    folder=OUT/'audio/ai-intro-review'
    if folder.exists():raise ValueError('Prior request exists; inspect it instead of resubmitting')
    key=os.environ.get('GEMINI_API_KEY')
    if not key:raise ValueError('Gemini key unavailable')
    folder.mkdir(parents=True)
    audio=folder/'intro.mp3'
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(OUT/'audio/mix-premaster.wav'),'-t',str(plan['main_offset']),
        '-c:a','libmp3lame','-b:a','128k',str(audio)],check=True)
    prompt='この日本語音声を実際に聞いてJSONで点検してください。期待する原稿は渡しません。transcript（話者と全文）、pronunciation_observed（製品名の聞こえ方）、audible_issues（余分な発話、音切れ、BGMで不明瞭な所。なければ空配列）、uncertaintiesを返してください。聞こえない内容を推測しないでください。'
    model='gemini-3.8-flash'
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],
        generationConfig=dict(responseMimeType='application/json',maxOutputTokens=2000))
    save(folder/'submission.json',dict(status='submitted',model=model,automatic_retry=False,prompt=prompt,
        audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest()))
    request=urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.build_opener(pcm.NoRedirect()).open(request,timeout=150) as response:
            data=json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as error:
        detail=re.sub(r'AIza[\w-]+|(?:key|token)=[^ &]+','[redacted]',error.read(32768).decode('utf-8',errors='replace'),flags=re.I)
        save(folder/'failure.json',dict(status='rejected',http_status=error.code,detail=detail[:1000],automatic_retry=False))
        raise RuntimeError('Audio check rejected; no automatic retry') from None
    except Exception:
        save(folder/'failure.json',dict(status='unknown',automatic_retry=False));raise
    save(folder/'response.json',data)
    result=json.loads(''.join(p.get('text','') for p in data['candidates'][0]['content']['parts']))
    result.update(model=model,verification='AI assistance; human final listening pending',usage=data.get('usageMetadata',{}),
        finish_reason=data['candidates'][0].get('finishReason'))
    save(folder/'review.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)


def technical():
    movie=OUT/'dots-transfer-detail-v02.mp4'
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(movie)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_frames']))!=(1920,1080,'24/1',plan['frames']):
        raise ValueError('Unexpected media geometry or frame count')
    decode=subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(movie),'-f','null','-'],capture_output=True,text=True,check=True)
    if decode.stderr.strip():raise ValueError('Decode diagnostics require review')
    loud=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(movie),'-af','loudnorm=I=-16:TP=-1.2:LRA=9:print_format=json',
        '-f','null','-'],capture_output=True,text=True,check=True).stderr
    loud=json.JSONDecoder().raw_decode(loud[loud.rfind('{'):])[0]
    save(OUT/'audio/loudness-final.json',loud)
    if not -17<=float(loud['input_i'])<=-15 or float(loud['input_tp'])>-.9:raise ValueError('Review final loudness')
    source=json.loads((OUT/'source-manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256((ROOT/source['old_video_preserved']['path']).read_bytes()).hexdigest()!=source['old_video_preserved']['sha256']:
        raise ValueError('Old final video changed')
    driver=DialogueDriver([t for c in plan['chapters'] for t in c['turns']])
    moments=[0,1.5,3,4.7,*[(t['start']+t['end'])/2 for t in plan['chapters'][0]['turns']],
        *[plan['main_offset']+t for t in [.8,20.7,21.5,24,63.5,111,113,150,166,201,223.8,246,252,271,276,279]]]
    qa=OUT/'qa';qa.mkdir(exist_ok=True)
    frame_records=[]
    # Explicitly choose one open and closed mouth during each speaker's real voice.
    for speaker in ('male','female'):
        found={}
        for w in json.loads((HERE/'revision-v02.json').read_text(encoding='utf-8'))['windows_in_original_main_seconds']:
            for frame in range(round((w['start']+plan['main_offset'])*24),round((w['end']+plan['main_offset'])*24)):
                t=frame/24;state=driver.state(t,speaker)
                if state['speaking']:found.setdefault(bool(state['opened']),t)
            if len(found)==2:break
        if len(found)!=2:raise ValueError('Did not find open and closed states during speech: '+speaker)
        for opened,t in found.items():moments.append(t)
    for i,t in enumerate(moments):
        dest=qa/f'final-{i:02d}.jpg'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(t),'-i',str(movie),'-frames:v','1','-q:v','2',str(dest)],check=True)
        frame_records.append(dict(path=dest.name,seconds=t))
    for page,start in enumerate(range(0,len(frame_records),12),1):
        sheet=Image.new('RGB',(1440,4*292),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for i,item in enumerate(frame_records[start:start+12]):
            x,y=i%3*480,i//3*292
            sheet.paste(Image.open(qa/item['path']).resize((480,270)),(x,y))
            draw.text((x+8,y+273),f"{item['seconds']:.3f}s",fill='black')
        sheet.save(qa/f'final-contact-{page:02d}.jpg',quality=94)
    save(qa/'final-frames.json',frame_records)
    save(OUT/'technical-verification.json',dict(status='technically_verified_review_pending',
        video=dict(path=movie.name,bytes=movie.stat().st_size,sha256=hashlib.sha256(movie.read_bytes()).hexdigest(),probe=probe),
        full_decode=True,loudness=loud,frames_for_visual_review=len(frame_records),old_video_preserved=True,
        new_tts_requests=4,effective_new_lines=3,manually_replaced_line=1,reused_voice_turns=40,unknown_tts_outcomes=0,new_imagegen_calls=3,
        new_minimax_video_calls=0,opening_minimax_clip='user accepted existing run-in trial',
        mouth_type='simple PCM-envelope gates; not phoneme-aligned',human_final_listening=False,
        user_final_approval=False,published=False,mobile_device_playback_verified=False))
    print('Technical checks passed; final frames extracted:',len(frame_records),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['audio','technical']);a=p.parse_args()
    (audio_check if a.command=='audio' else technical)()
