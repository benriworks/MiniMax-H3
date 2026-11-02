"""Verify actual decoded captions, evidence views and unchanged copied audio."""
import argparse,base64,json,os,re,urllib.request
from PIL import Image
import revise as r

def frames(key):
    cfg=r.CASES[key];dest=r.OUT/'release'/cfg['version']/key;p=json.loads((dest/'timeline.json').read_text(encoding='utf-8'));video=dest/cfg['name'];folder=dest/'qc-actual';folder.mkdir(exist_ok=True);records=[]
    for t in p['turns']:
        selections=[(f'sub-{i}',(c['start']+c['end'])/2) for i,c in enumerate(t['subtitles'])]
        selections+=[('early',t['start']+.3),('middle',(t['start']+t['end'])/2),('late',t['end']-.15)]
        for tag,at in selections:
            path=folder/(t['id']+'-'+tag+'.jpg');r.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(video),'-frames:v','1','-q:v','2',str(path)]);assert Image.open(path).size==(p['width'],p['height']);records.append(dict(path=path.name,seconds=at,sha256=r.sha(path),turn=t['id']))
    ending=folder/'ending.jpg';r.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(p['seconds']-2 if cfg['kind']=='full' else p['seconds']-.3),'-i',str(video),'-frames:v','1',str(ending)])
    subset=[x for x in records if 'middle' in x['path']]+[dict(path='ending.jpg')];w,h=(270,480) if cfg['kind']=='short' else (480,270);sheet=Image.new('RGB',(w*3,h*((len(subset)+2)//3)),r.BG)
    for i,x in enumerate(subset):sheet.paste(Image.open(folder/x['path']).resize((w,h)),(i%3*w,i//3*h))
    sheet.save(folder/'contact-sheet.jpg',quality=94)
    audio_same=None
    if key in ['tokyo-full','tibo-full']:
        def audio_hash(path):return r.run(['ffmpeg','-v','error','-nostdin','-i',str(path),'-map','0:a','-c','copy','-f','hash','-hash','sha256','-']).stdout.strip()
        audio_same=audio_hash(video)==audio_hash(next(cfg['old'].glob('*full-v*.mp4')));assert audio_same
    srt=(dest/'captions.srt').read_text(encoding='utf-8');assert '離す動\nき' not in srt and '約一点九倍' not in srt
    if key in ['wine-full','wine-short']:assert '約1.9倍' in srt
    oldqc=json.loads((cfg['old']/('verification.json' if key=='tibo-full' else 'qc.json')).read_text(encoding='utf-8'));oldfile=next(cfg['old'].glob('*'+('short' if cfg['kind']=='short' else 'full')+'-v*.mp4'));expected=oldqc.get('file',oldqc).get('sha256');assert r.sha(oldfile)==expected
    r.save(dest/'qc-actual/verification.json',dict(samples=records,sample_count=len(records)+1,copied_audio_identical=audio_same,original_video_unchanged=True,caption_states_checked=sum(len(t['subtitles']) for t in p['turns']),published_version_replaced=False,human_reviewed=False))
    print(key,'actual frames',len(records)+1,'caption states',sum(len(t['subtitles']) for t in p['turns']),'copied audio',audio_same,flush=True)

def listening(key):
    cfg=r.CASES[key];video=r.OUT/'release'/cfg['version']/key/cfg['name'];folder=r.OUT/'_private'/('ai-listening-'+key)
    if folder.exists():raise RuntimeError('Existing submission: inspect it; no automatic retry')
    folder.mkdir(parents=True);audio=folder/'final.mp3';r.run(['ffmpeg','-v','error','-nostdin','-i',str(video),'-vn','-c:a','libmp3lame','-b:a','96k',str(audio)])
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    prompt='この日本語の男女の解説を実際に聞こえる音声だけで点検。台本は渡しません。JSONでtranscript（時刻と全文）、pronunciation_observed（製品名や数字の読み）、audible_issues（余分な台詞、音切れ、声が音楽に埋もれる箇所など。なければ空配列）、uncertaintiesを返す。聞こえない部分を補完しない。'
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=10000));model='gemini-3.8-flash'
    r.save(folder/'submission.json',dict(model=model,status='submitted',automatic_retry=False,video_sha256=r.sha(video)))
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    with urllib.request.urlopen(req,timeout=120) as response:data=json.loads(response.read(2000000))
    r.save(folder/'response.json',data);c=data['candidates'][0];assert c.get('finishReason')=='STOP';review=json.loads(''.join(x.get('text','') for x in c['content']['parts']));r.save(folder/'review.json',review);print(key,json.dumps({k:review.get(k) for k in ['audible_issues','uncertainties']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['frames','listening']);a.add_argument('--video',choices=list(r.CASES),required=True);args=a.parse_args();globals()[args.action](args.video)
