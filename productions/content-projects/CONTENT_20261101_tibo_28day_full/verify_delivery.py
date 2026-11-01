"""Inspect decoded frames and one bounded independent full-audio review, not human adoption."""
import argparse,base64,json,os,subprocess,urllib.request,winreg
from PIL import Image,ImageDraw
import produce as p
def frames():
    plan=json.loads((p.DEST/'timeline.json').read_text(encoding='utf-8'));video=p.DEST/'tibo-28day-full-v01.mp4';qc=p.DEST/'qc-actual';qc.mkdir(exist_ok=True);records=[]
    for t in plan['turns']:
        for frac in [.08,.6,.94]:
            at=t['start']+(t['end']-t['start'])*frac;name=t['id']+f'-{frac:.2f}.jpg';path=qc/name
            p.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(video),'-frames:v','1','-q:v','2',str(path)])
            assert Image.open(path).size==(1920,1080);records.append(dict(name=name,seconds=at,sha256=p.sha(path)))
    for subset,filename in [(records,'all-frames'),([x for x in records if '-0.60' in x['name']],'all-turns')]:
        cols=4;rows=(len(subset)+cols-1)//cols;sheet=Image.new('RGB',(1600,rows*252),'#DDE4E5');d=ImageDraw.Draw(sheet)
        for i,r in enumerate(subset):
            x=i%cols*400;y=i//cols*252;sheet.paste(Image.open(qc/r['name']).resize((400,225)),(x,y));d.text((x+5,y+230),r['name']+' '+str(round(r['seconds'],1)),fill='#172F3E')
        sheet.save(qc/(filename+'.jpg'),quality=90)
    p.save(qc/'frames.json',dict(video_sha256=p.sha(video),samples=records,scope='108 sampled decoded frames; not a per-frame human review'))
    print(json.dumps(dict(actual_samples=len(records))))
def listening():
    folder=p.OUT/'_private/ai-listening-v01'
    if folder.exists():raise RuntimeError('Prior submission exists; no automatic retry')
    folder.mkdir(parents=True);audio=folder/'final-audio.mp3';video=p.DEST/'tibo-28day-full-v01.mp4'
    p.run(['ffmpeg','-v','error','-nostdin','-i',str(video),'-vn','-c:a','libmp3lame','-b:a','96k',str(audio)])
    if not os.getenv('GEMINI_API_KEY'):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    prompt='日本語の男女の解説動画を実際に聞こえる内容だけで点検してください。台本は渡しません。JSONで、transcript（概時刻と全文）、pronunciation_observed（製品名の読み）、audible_issues（余分な台詞、読まれていない部分、音切れ、声がBGMに埋もれる時刻。なければ空配列）、uncertaintiesを返してください。音楽や効果音の意味は推測しないでください。聞こえない部分を作らないでください。'
    model='gemini-3.8-flash';body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=12000))
    p.save(folder/'submission.json',dict(status='submitted',automatic_retry=False,model=model,audio_sha256=p.sha(audio),video_sha256=p.sha(video),prompt=prompt))
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=120) as response:data=json.loads(response.read(2_000_000))
    except Exception:
        p.save(folder/'failure.json',dict(status='unknown_or_rejected',automatic_retry=False));raise
    p.save(folder/'response.json',data);candidate=data['candidates'][0]
    if candidate.get('finishReason')!='STOP':raise ValueError('Incomplete AI review; keep response without resubmission')
    result=json.loads(''.join(x.get('text','') for x in candidate['content']['parts']));result.update(verification_type='AI-assisted independent audio check; not human audition',usage=data.get('usageMetadata',{}))
    p.save(folder/'review.json',result);print(json.dumps(dict(audible_issues=result.get('audible_issues'),uncertainties=result.get('uncertainties')),ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['frames','listening']);a=parser.parse_args();globals()[a.command]()
