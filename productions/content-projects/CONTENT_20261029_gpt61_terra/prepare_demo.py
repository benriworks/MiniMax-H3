"""Isolated fictional banner / genuine Terra API vision evaluation. No retry."""
from pathlib import Path
import base64, hashlib, json, os, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / 'outputs/content-projects' / HERE.name / 'v01'
OUT.mkdir(parents=True, exist_ok=True)
def save(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rec(p):
    return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
def banner(x=870, size=100):
    im=Image.new('RGB',(1600,1000),'#f4efdf'); d=ImageDraw.Draw(im)
    font=lambda n:ImageFont.truetype('C:/Windows/Fonts/YuGothB.ttc',n)
    d.rounded_rectangle((70,65,680,165),30,fill='#d6e4cb')
    d.text((105,75),'週末、つくるを楽しもう',font=font(38),fill='#294433')
    d.ellipse((100,300,600,800),fill='#e8ad65')
    d.rounded_rectangle((235,390,480,640),25,fill='#315846')
    d.polygon([(230,390),(355,280),(480,390)],fill='#315846')
    d.rounded_rectangle((312,475,402,640),15,fill='#f4efdf')
    d.text((x,240),'秋のものづくり体験会',font=font(size),fill='#20392d')
    d.text((780,490),'11月14日（土） 10:00–16:00',font=font(38),fill='#315846')
    d.text((780,565),'みどり工房 ／ 参加無料',font=font(38),fill='#315846')
    d.rounded_rectangle((780,700,1480,805),30,fill='#315846')
    d.text((835,715),'家族で楽しむ、はじめての工作',font=font(34),fill='white')
    d.text((90,905),'架空イベント・検証用画像',font=font(30),fill='#607464')
    return im

before=OUT/'banner-before.png'
if not before.exists():banner().save(before)
if len(sys.argv)>1 and sys.argv[1]=='assets':
    print(json.dumps(rec(before)));sys.exit()
target=OUT/'terra-api'
if target.exists():
    print('Existing submission preserved; inspect before any further calls.');sys.exit()
target.mkdir()
prompt='この架空の告知バナーを校正してください。見出しの読みやすさ・画面外へのはみ出しを確認し、観察した問題と修正案を日本語で短く返してください。画像は1600×1000pxです。見出しは「秋のものづくり体験会」です。他の要素を避けて全体を読める見出しのx座標とフォントサイズを提案してください。title_xは700〜850、title_font_sizeは40〜66の範囲。問題が見つからなければ正直にそう書いてください。'
schema={'type':'object','properties':{'issue':{'type':'string'},'fix':{'type':'string'},'title_x':{'type':'integer'},'title_font_size':{'type':'integer'}},'required':['issue','fix','title_x','title_font_size'],'additionalProperties':False}
body={'model':'gpt-6.1-terra','store':False,'reasoning':{'effort':'low'},'max_output_tokens':1600,
      'input':[{'role':'user','content':[{'type':'input_text','text':prompt},{'type':'input_image','image_url':'data:image/png;base64,'+base64.b64encode(before.read_bytes()).decode()}]}],
      'text':{'format':{'type':'json_schema','name':'banner_review','strict':True,'schema':schema}}}
save(target/'request-summary.json',{'model':body['model'],'prompt':prompt,'input':rec(before),'reasoning':body['reasoning'],'store':False,'schema':schema})
save(target/'submission.json',{'status':'submitted','automatic_retry':False,'at':datetime.now(timezone.utc).isoformat()})
req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['OPENAI_API_KEY'],'Content-Type':'application/json'},method='POST')
try:
    with urllib.request.urlopen(req,timeout=100) as r:data=json.load(r)
except urllib.error.HTTPError as e:
    # Controlled status only; no provider response or credentials in console.
    save(target/'submission.json',{'status':'rejected','http_status':e.code,'automatic_retry':False})
    print('Terra request rejected; HTTP',e.code);sys.exit(1)
except Exception:
    save(target/'submission.json',{'status':'unknown','automatic_retry':False})
    print('Terra outcome unknown; no automatic retry');sys.exit(1)
save(target/'response.json',data)
txt=''.join(c.get('text','') for o in data.get('output',[]) for c in o.get('content',[]) if c.get('type')=='output_text')
review=json.loads(txt);save(target/'review.json',review)
if not (700<=review['title_x']<=850 and 40<=review['title_font_size']<=66):
    raise ValueError('Suggestion outside the explicitly bounded layout')
banner(review['title_x'],review['title_font_size']).save(OUT/'banner-after.png')
save(target/'submission.json',{'status':'received','response_id':data.get('id'),'response_model':data.get('model'),'usage':data.get('usage'),'automatic_retry':False,'completed_at':datetime.now(timezone.utc).isoformat()})
save(OUT/'demo-proof.json',{'input':rec(before),'output':rec(OUT/'banner-after.png'),'model_review':rec(target/'review.json'),'method':'Genuine Terra vision API; Python applies returned position and size. No computer-use API call.','independent_after_check':'pending','user_approved':False})
print(json.dumps({'review':review,'model':data.get('model'),'usage':data.get('usage')},ensure_ascii=False))
