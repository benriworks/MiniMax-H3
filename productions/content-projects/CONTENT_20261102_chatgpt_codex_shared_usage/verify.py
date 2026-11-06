"""Check final decoded frames and exact final audio without supplying the script."""
import argparse,base64,json,os,urllib.request,winreg
from PIL import Image
import produce as p
VIDEO=p.DEST/'chatgpt-codex-shared-usage-v01.mp4'
def frames():
    plan=json.loads((p.DEST/'timeline.json').read_text(encoding='utf-8'));folder=p.DEST/'qc-actual';folder.mkdir(exist_ok=True);records=[]
    for t in plan['turns']:
        for pct in [.08,.5,.92]:
            at=t['start']+(t['end']-t['start'])*pct;path=folder/f"{t['id']}-{pct:.2f}.jpg";p.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(VIDEO),'-frames:v','1','-q:v','2',str(path)]);assert Image.open(path).size==(1080,1920);records.append(dict(path=path.name,seconds=at,sha256=p.sha(path)))
    path=folder/'end.jpg';p.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(plan['body_seconds']+.5),'-i',str(VIDEO),'-frames:v','1',str(path)])
    chosen=[x['path'] for x in records if '-0.50' in x['path']]+['end.jpg'];sheet=Image.new('RGB',(810,480*((len(chosen)+2)//3)),'#D1DDE1')
    for i,name in enumerate(chosen):sheet.paste(Image.open(folder/name).resize((270,480)),(i%3*270,i//3*480))
    sheet.save(folder/'contact-sheet.jpg',quality=94);p.save(folder/'frames.json',dict(video=p.rec(VIDEO),samples=records,ending_sha256=p.sha(path),scope='24 scene samples and one ending frame; not every-frame human viewing'))
    print('25 actual frames saved',flush=True)
def listening():
    folder=p.OUT/'_private/ai-listening-v01'
    if folder.exists():raise RuntimeError('Existing submission; no automatic retry')
    folder.mkdir(parents=True);audio=folder/'final-audio.mp3';p.run(['ffmpeg','-v','error','-nostdin','-i',str(VIDEO),'-vn','-c:a','libmp3lame','-b:a','96k',str(audio)])
    if not os.getenv('GEMINI_API_KEY'):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    prompt='この日本語の男女の解説音声を聞こえる内容だけで点検。台本は渡しません。JSONでtranscript（概時刻と全文）、pronunciation_observed（製品名の読み）、audible_issues（余分な台詞、音切れ、声がBGMに埋もれる箇所。なければ空配列）、uncertaintiesを返す。聞こえない内容を作らない。'
    model='gemini-3.8-flash';body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=8000))
    p.save(folder/'submission.json',dict(model=model,status='submitted',automatic_retry=False,audio_sha256=p.sha(audio),video_sha256=p.sha(VIDEO),prompt=prompt))
    request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=120) as response:data=json.loads(response.read(2_000_000))
    except Exception:
        p.save(folder/'failure.json',dict(status='unknown_or_rejected',automatic_retry=False));raise
    p.save(folder/'response.json',data);candidate=data['candidates'][0]
    if candidate.get('finishReason')!='STOP':raise RuntimeError('Incomplete response retained; no retry')
    review=json.loads(''.join(x.get('text','') for x in candidate['content']['parts']));review['verification_type']='AI-assisted independent audio check; not human adoption';p.save(folder/'review.json',review);print(json.dumps(dict(audible_issues=review.get('audible_issues'),uncertainties=review.get('uncertainties')),ensure_ascii=False),flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['frames','listening']);args=a.parse_args();globals()[args.action]()
