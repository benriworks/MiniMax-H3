"""Decoded-frame and independent audio checks for Tokyo full v03 only."""
import argparse,base64,json,os,urllib.request
from pathlib import Path
from PIL import Image
import revise_v03_soft_dialogue as r

def frames():
    p=json.loads((r.DEST/'timeline.json').read_text(encoding='utf-8'));video=r.DEST/'dots-blender-tokyo-full-v03.mp4';dest=r.DEST/'qc-actual';dest.mkdir(exist_ok=True);records=[]
    renderer=r.e.TokyoRenderer('full')
    for t in p['turns']:
        for c in t['subtitles']:renderer.render(t,(c['start']+c['end'])/2-t['start'])
    audit=list(r.e.tokyo.AUDIT.values());assert audit and all('立体' not in a['text'] and '模型' not in a['text'] for a in audit)
    r.e.save(r.DEST/'layout/text-audit.json',audit)
    for t in p['turns']:
        times=[('sub-'+str(i),(s['start']+s['end'])/2) for i,s in enumerate(t['subtitles'])]+[(tag,t['start']+(t['end']-t['start'])*pct) for tag,pct in [('early',.08),('middle',.5),('late',.92)]]
        for tag,at in times:
            path=dest/(t['id']+'-'+tag+'.jpg');r.e.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(video),'-frames:v','1','-q:v','2',str(path)]);assert Image.open(path).size==(1920,1080);records.append(dict(path=path.name,seconds=at,sha256=r.e.sha(path)))
    ending=dest/'ending.jpg';r.e.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(p['seconds']-3),'-i',str(video),'-frames:v','1',str(ending)])
    sample=[x for x in records if 'middle' in x['path']]+[dict(path='ending.jpg')];sheet=Image.new('RGB',(1440,270*((len(sample)+2)//3)),r.e.BG)
    for i,x in enumerate(sample):sheet.paste(Image.open(dest/x['path']).resize((480,270)),(i%3*480,i//3*270))
    sheet.save(dest/'contact-sheet.jpg',quality=94)
    old=json.loads((r.OLD/'timeline.json').read_text(encoding='utf-8'));male_checks=[]
    for t in p['turns']:
        assert '模型' not in t['display'] and '立体' not in t['display']
        if t['speaker']=='male':
            a=Path(next(x['voice_path'] for x in old['turns'] if x['id']==t['id']));b=Path(t['voice_path']);assert r.e.sha(a)==r.e.sha(b);male_checks.append(t['id'])
    original=r.OLD/'dots-blender-tokyo-full-v02.mp4';assert r.e.sha(original)==json.loads((r.OLD/'qc.json').read_text(encoding='utf-8'))['sha256']
    srt=(r.DEST/'captions.srt').read_text(encoding='utf-8');assert '模型' not in srt and '立体' not in srt and '3D' in srt
    result=dict(samples=records,sample_count=len(records)+1,caption_states=sum(len(t['subtitles']) for t in p['turns']),male_pcm_unchanged=male_checks,new_female_turns=10,original_v02_unchanged=True,old_terminology_in_captions=False,human_reviewed=False,user_approved=False,published=False)
    r.e.save(dest/'verification.json',result);print(json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True)

def listening():
    folder=r.OUT/'_private/ai-listening-v03-soft-dialogue'
    if folder.exists():raise RuntimeError('Existing submission; inspect before any manual recovery')
    folder.mkdir(parents=True);video=r.DEST/'dots-blender-tokyo-full-v03.mp4';audio=folder/'final.mp3';r.e.run(['ffmpeg','-v','error','-nostdin','-i',str(video),'-vn','-c:a','libmp3lame','-b:a','96k',str(audio)])
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
    prompt='日本語の男女の解説動画を実音声だけで点検。台本は渡しません。JSONでtranscript（時刻・話者と全文）、pronunciation_observed（製品名や3Dの読み）、female_endings_observed（実際に聞こえた女性の文末表現）、audible_issues（余分な台詞・音切れ・聞き取り困難・声が音楽に埋もれる箇所。なければ空配列）、uncertainties。聞こえないところは補完しない。柔らかさの最終採用判断は人が行う。'
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],generationConfig=dict(responseMimeType='application/json',maxOutputTokens=10000));model='gemini-3.8-flash'
    r.e.save(folder/'submission.json',dict(status='submitted',model=model,automatic_retry=False,video_sha256=r.e.sha(video)))
    req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':os.environ['GEMINI_API_KEY']},method='POST')
    with urllib.request.urlopen(req,timeout=120) as response:data=json.loads(response.read(2000000))
    r.e.save(folder/'response.json',data);c=data['candidates'][0];assert c.get('finishReason')=='STOP';review=json.loads(''.join(x.get('text','') for x in c['content']['parts']));r.e.save(folder/'review.json',review)
    print(json.dumps({k:review.get(k) for k in ['audible_issues','uncertainties','female_endings_observed']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['frames','listening']);args=a.parse_args();globals()[args.action]()
