"""Inspect modified real frames, clean turn-to-turn excerpt and a bounded ending audio check."""
import argparse,base64,json,os,urllib.request,wave,winreg
from PIL import Image,ImageDraw
import revise_v02 as rev
p=rev.p;DEST=rev.DEST;VIDEO=DEST/'tibo-28day-full-v02.mp4'
def media():
    qc=DEST/'qc-actual';qc.mkdir(exist_ok=True)
    times=[rev.START-.08,rev.START+.15,rev.START+1.5,rev.START+4.4,rev.START+6.2,420.25,420.5,422.0,426.5,431.5,433.8,434.3,434.5,439.3,444.0]
    records=[]
    for i,seconds in enumerate(times):
        file=qc/f'{i:02d}-{seconds:.2f}.jpg'
        p.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(seconds),'-i',str(VIDEO),'-frames:v','1','-q:v','2',str(file)])
        assert Image.open(file).size==(1920,1080);records.append(dict(file=file.name,seconds=seconds,sha256=p.sha(file)))
    sheet=Image.new('RGB',(1600,4*253),'#DDE4E5');d=ImageDraw.Draw(sheet)
    for i,item in enumerate(records):
        x=i%4*400;y=i//4*253;sheet.paste(Image.open(qc/item['file']).resize((400,225)),(x,y));d.text((x+4,y+232),item['file'],fill='#172F3E')
    sheet.save(qc/'contact-sheet.jpg',quality=92)
    p.save(qc/'samples.json',dict(video_sha256=p.sha(VIDEO),samples=records))
    excerpt=DEST/'tibo-ending-review-v02.mp4'
    if not excerpt.exists():p.run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(rev.START),'-i',str(VIDEO),'-t',str(rev.NEW_SECONDS-rev.START),'-c:v','libx264','-preset','fast','-crf','20','-threads','2','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-ar','48000','-movflags','+faststart',str(excerpt)])
    p.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(excerpt),'-f','null','-'])
    probe=json.loads(p.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(excerpt)]).stdout)
    video=next(s for s in probe['streams'] if s['codec_type']=='video');assert int(video['nb_frames'])==751
    with wave.open(str(DEST/'narration-padded.wav'),'rb') as w:
        w.setpos(round(rev.PLAN['seconds']*p.SR));assert set(w.readframes(10*p.SR))=={0}
    p.save(qc/'review-excerpt.json',dict(p.record(excerpt),seconds=751/24,frames=751,full_decode=True,starts_before_male_line=True,includes_complete_female_line=True,end_screen_voice_samples_zero=True))
    print(json.dumps(dict(actual_samples=len(records),excerpt=p.record(excerpt),seconds=751/24)))
def listening():
    folder=p.OUT/'_private/ai-ending-listening-v02'
    if folder.exists():raise RuntimeError('Prior request exists; no automatic retry')
    folder.mkdir(parents=True);audio=folder/'ending.mp3'
    p.run(['ffmpeg','-v','error','-nostdin','-ss',str(rev.START),'-i',str(VIDEO),'-vn','-c:a','libmp3lame','-b:a','128k',str(audio)])
    if not os.getenv('GEMINI_API_KEY'):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    model='gemini-3.8-flash';prompt='この動画末尾の実際の音だけを点検してください。台本は渡しません。JSONでtranscript（聞こえた台詞と概時刻）、audible_issues（音切れ、声が音楽に埋もれる部分、突然の音量段差。なければ空配列）、music_ending（最後の音楽の変化やフェードを観察した内容）、speech_after_dialogue（会話終了後に別の声が聞こえるか）、uncertaintiesを返してください。期待する内容を推測しないでください。'
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=1800))
    p.save(folder/'submission.json',dict(status='submitted',model=model,automatic_retry=False,audio_sha256=p.sha(audio),video_sha256=p.sha(VIDEO),prompt=prompt))
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=120) as response:data=json.loads(response.read(1_000_000))
    except Exception:
        p.save(folder/'failure.json',dict(status='unknown_or_rejected',automatic_retry=False));raise
    p.save(folder/'response.json',data);candidate=data['candidates'][0];assert candidate.get('finishReason')=='STOP'
    result=json.loads(''.join(x.get('text','') for x in candidate['content']['parts']));result['verification_type']='AI-assisted ending check, not human listening'
    p.save(folder/'review.json',result);print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['media','listening']);a=parser.parse_args();globals()[a.command]()
