"""Decoded evidence and independent, bounded audio inspection, never human acceptance."""
import argparse,base64,json,os,urllib.request,winreg
from PIL import Image,ImageDraw
import produce as p
def frames(kind):
    dest=p.OUT/'release/v01'/kind;plan=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));video=dest/f'dots-wine-{kind}-v01.mp4';folder=dest/'qc-actual';folder.mkdir(exist_ok=True);records=[]
    for t in plan['turns']:
        for pct in [.08,.5,.92]:
            at=t['start']+(t['end']-t['start'])*pct;path=folder/f"{t['id']}-{pct:.2f}.jpg"
            p.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(video),'-frames:v','1','-q:v','2',str(path)])
            assert Image.open(path).size==(plan['width'],plan['height']);records.append(dict(path=path.name,seconds=at,sha256=p.sha(path)))
    at=plan['body_seconds']+plan['end_seconds']/2;path=folder/'end.jpg';p.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(video),'-frames:v','1','-q:v','2',str(path)])
    subset=[x for x in records if '-0.50' in x['path']]+[dict(path='end.jpg')]
    w,h=(270,480) if kind=='short' else (480,270);sheet=Image.new('RGB',(w*3,h*((len(subset)+2)//3)),'#CED9DA')
    for i,x in enumerate(subset):sheet.paste(Image.open(folder/x['path']).resize((w,h)),(i%3*w,i//3*h))
    sheet.save(folder/'contact-sheet.jpg',quality=94);p.save(folder/'frames.json',dict(video=p.rec(video),samples=records,scope='Three decoded samples per spoken scene plus ending; not every-frame human viewing'))
    print(kind,'decoded samples',len(records)+1,flush=True)
def listening(kind):
    folder=p.OUT/'_private'/('ai-listening-'+kind+'-v01')
    if folder.exists():raise RuntimeError('Existing submission: inspect result; automatic retry disabled')
    folder.mkdir(parents=True);video=p.OUT/'release/v01'/kind/f'dots-wine-{kind}-v01.mp4';audio=folder/'final-audio.mp3'
    p.run(['ffmpeg','-v','error','-nostdin','-i',str(video),'-vn','-c:a','libmp3lame','-b:a','96k',str(audio)])
    if not os.getenv('GEMINI_API_KEY'):
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    prompt='この日本語の男女の解説動画を実際に聞こえる音声だけで点検。台本は渡しません。JSONでtranscript（概時刻と全文）、pronunciation_observed（製品名の読み）、audible_issues（余分な台詞、音切れ、聞き取りづらい箇所、声がBGMに埋もれる時刻。なければ空配列）、uncertaintiesを返す。聞こえない部分を作らない。'
    model='gemini-3.8-flash';body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=10000))
    p.save(folder/'submission.json',dict(status='submitted',model=model,automatic_retry=False,video_sha256=p.sha(video),audio_sha256=p.sha(audio),prompt=prompt))
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=120) as response:data=json.loads(response.read(2_000_000))
    except Exception:
        p.save(folder/'failure.json',dict(status='unknown_or_rejected',automatic_retry=False));raise
    p.save(folder/'response.json',data);candidate=data['candidates'][0]
    if candidate.get('finishReason')!='STOP':raise RuntimeError('Incomplete review preserved, no automatic retry')
    review=json.loads(''.join(x.get('text','') for x in candidate['content']['parts']));review['verification_type']='AI-assisted independent listening; not human adoption';p.save(folder/'review.json',review)
    print(kind,json.dumps(dict(audible_issues=review.get('audible_issues'),uncertainties=review.get('uncertainties')),ensure_ascii=False),flush=True)
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['frames','listening']);a.add_argument('--kind',choices=['short','full'],required=True);args=a.parse_args();globals()[args.action](args.kind)
