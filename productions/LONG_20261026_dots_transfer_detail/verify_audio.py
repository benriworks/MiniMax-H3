"""One bounded AI-assisted listening check, distinct from human final audition."""
from pathlib import Path
import base64,hashlib,json,os,re,subprocess,sys,urllib.request,urllib.error

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/productions/LONG_20261026_dots_transfer_detail/v01'


def main():
    folder=OUT/'audio/ai-listening-v02'
    if folder.exists():
        raise RuntimeError('Prior listening request exists; inspect it instead of automatic resubmission')
    folder.mkdir(parents=True)
    audio=folder/'review-mix.mp3'
    subprocess.run(['ffmpeg','-v','error','-nostdin','-i',str(OUT/'audio/mix-premaster.wav'),'-c:a','libmp3lame','-b:a','128k',str(audio)],check=True)
    model='gemini-3.8-flash'
    prompt=('日本語の二人の解説音声を、実際に聞こえる内容に基づいて点検してください。'
        '期待する台本は渡しません。JSONで、transcript（男女の話者とおおよその時刻を含む全文）、'
        'pronunciation_observed（製品名のカタカナの聞こえ方、表の読み、Excelの拡張子の聞こえ方）、'
        'audible_issues（音切れ、余分な発話、話者の混同、BGMで聞き取れない箇所と時刻。なければ空配列）、'
        'uncertainties（断定できない部分）を返してください。聞こえない箇所を推測で埋めないでください。')
    body=dict(contents=[dict(parts=[dict(text=prompt),dict(inlineData=dict(mimeType='audio/mp3',data=base64.b64encode(audio.read_bytes()).decode()))])],
              generationConfig=dict(responseMimeType='application/json',maxOutputTokens=7000))
    key=os.environ.get('GEMINI_API_KEY')
    if not key:raise RuntimeError('Gemini key missing')
    (folder/'submission.json').write_text(json.dumps(dict(status='submitted',model=model,automatic_retry=False,audio_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),prompt=prompt),ensure_ascii=False,indent=2),encoding='utf-8')
    request=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/'+model+':generateContent',
        data=json.dumps(body).encode(),headers={'Content-Type':'application/json','x-goog-api-key':key},method='POST')
    try:
        with urllib.request.urlopen(request,timeout=180) as response:
            data=json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as e:
        detail=e.read(32768).decode('utf-8',errors='replace')
        detail=re.sub(r'AIza[\w-]+|(?:key|token)=[^ &]+','[redacted]',detail,flags=re.I)
        (folder/'failure.json').write_text(json.dumps(dict(http_status=e.code,automatic_retry=False,diagnostic=detail[:1000])),encoding='utf-8')
        raise RuntimeError('Listening verification request rejected; no automatic retry') from None
    except Exception:
        (folder/'failure.json').write_text(json.dumps(dict(status='unknown',automatic_retry=False)),encoding='utf-8')
        raise
    (folder/'response.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    content=''.join(p.get('text','') for p in data['candidates'][0]['content']['parts'])
    result=json.loads(content)
    result.update(verification_type='AI-assisted audio understanding, not human final listening',model=model,
        human_final_listening='pending',finish_reason=data['candidates'][0].get('finishReason'),usage=data.get('usageMetadata',{}))
    (folder/'review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('AI audio check completed; human final listening remains pending')


if __name__=='__main__':
    main()
