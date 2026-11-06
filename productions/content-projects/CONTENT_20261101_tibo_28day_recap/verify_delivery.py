"""Inspect real frames and one bounded, independent AI-assisted audio check."""
from pathlib import Path
import argparse,base64,hashlib,importlib.util,json,os,subprocess,urllib.request,urllib.error
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name

def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def save(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def frames(version):
    spec=importlib.util.spec_from_file_location('tibo_render',HERE/'produce.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
    dest=OUT/'tibo-recap/release'/version;video=dest/f'tibo-recap-{version}.mp4';qc=dest/'qc';qc.mkdir(exist_ok=True)
    timeline=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));samples=[]
    for s,part in zip(p.EP['scenes'],timeline):
        start=part['start'];duration=part['end']-start
        if 'days' not in s:
            for t in [.55,min(3.5,duration-.1),duration-.18]:samples.append((f"scene-{part['index']:02}-{t:.2f}",start+t))
        else:
            for day in s['days']:
                # Find the actual day interval using the renderer's own weighted timing.
                times=[k/24 for k in range(part['frames']) if p.day_for(s,k/24,duration)[0]==day]
                assert times
                for frac in ([.13,.4,.75] if day in [2,3,18,20] else [.6]):
                    t=times[min(len(times)-1,round((len(times)-1)*frac))];samples.append((f'day-{day:02}-{frac:.2f}',start+t))
    records=[]
    for name,t in samples:
        path=qc/(name+'.png')
        run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(t),'-i',str(video),'-frames:v','1',str(path)])
        with Image.open(path) as im:assert im.size==(1080,1920)
        records.append(dict(name=name,seconds=t,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    cols=6;sheet=Image.new('RGB',(cols*180,((len(records)+cols-1)//cols)*345),'#DDE3E3');d=ImageDraw.Draw(sheet)
    for i,r in enumerate(records):
        im=Image.open(qc/(r['name']+'.png')).resize((180,320));x=(i%cols)*180;y=(i//cols)*345;sheet.paste(im,(x,y));d.text((x+3,y+322),r['name'],fill='#172F3E')
    sheet.save(qc/'contact-sheet.jpg');save(qc/'frames.json',dict(video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),samples=records))
    print(json.dumps(dict(real_frames=len(records),days=26,forecast_in_scene=True)))

def listening(version):
    folder=OUT/'_private'/('ai-listening-'+version)
    if folder.exists():raise RuntimeError('Prior request exists; inspect instead of automatic resubmission')
    folder.mkdir(parents=True);audio=folder/'final-aac-review.mp3'
    run(['ffmpeg','-v','error','-nostdin','-i',str(OUT/'tibo-recap/release'/version/f'tibo-recap-{version}.mp4'),'-vn','-c:a','libmp3lame','-b:a','128k',str(audio)])
    if not os.environ.get('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    model='gemini-3.8-flash'
    prompt='日本語の解説動画の完成音声を実際に聞こえる内容だけで点検してください。台本は渡しません。JSONでtranscript（おおよその時刻と全文）、pronunciation_observed（製品名の聞こえ方）、audible_issues（音切れ、余分な台詞、BGMで聞こえない部分と時刻。なければ空配列）、uncertaintiesを返してください。聞こえない所を推測しないでください。'
    if version=='v07':prompt+=' effect_observationsとして、聞こえる効果音の種類と概時刻も記載してください。音声が音楽や効果音に埋もれていないかを優先し、効果音の意味は推測せず音響的な違いを述べてください。'
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=6500))
    save(folder/'submission.json',dict(status='submitted',model=model,automatic_retry=False,prompt=prompt,audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest()))
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=120) as response:data=json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as e:
        save(folder/'failure.json',dict(http_status=e.code,automatic_retry=False));raise RuntimeError('Audio review rejected; no automatic retry') from None
    except Exception:
        save(folder/'failure.json',dict(status='unknown',automatic_retry=False));raise
    save(folder/'response.json',data)
    candidate=data['candidates'][0];assert candidate.get('finishReason')=='STOP'
    result=json.loads(''.join(part.get('text','') for part in candidate['content']['parts']))
    result.update(verification_type='AI-assisted, not human final audition',model=model,usage=data.get('usageMetadata',{}))
    save(folder/'review.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['frames','listening']);p.add_argument('--version',default='v07');a=p.parse_args();globals()[a.command](a.version)
