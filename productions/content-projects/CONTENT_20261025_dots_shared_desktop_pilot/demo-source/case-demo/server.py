#!/usr/bin/env python3
"""Local-only demo. No notifications, accounting, external APIs or dependencies."""
import datetime, json, re, threading, uuid, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
BASE=Path(__file__).resolve().parent
ROOT=BASE.parent
STORE=BASE/'registered-cases.json'
WORKBOOK=BASE/'outputs/case-demo/demo-cases.xlsx'
LOCK=threading.Lock()
PENDING={}
def read_cases():
    return json.loads(STORE.read_text()) if STORE.exists() else []
def validate(data, existing):
    d={k:str(data.get(k,'')).strip() for k in ['id','customer','name','due','amount']}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,39}',d['id']): raise ValueError('案件IDは英数字・ハイフン・アンダースコアで入力してください。')
    if any(x['id'].casefold()==d['id'].casefold() for x in existing): raise ValueError('この案件IDは登録済みです。重複登録はできません。')
    if not d['customer'] or not d['name']: raise ValueError('顧客名と案件名を入力してください。')
    if len(d['customer'])>100 or len(d['name'])>150: raise ValueError('顧客名または案件名が長すぎます。')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d['due']): raise ValueError('納期は YYYY-MM-DD 形式で入力してください。')
    try: datetime.date.fromisoformat(d['due'])
    except ValueError: raise ValueError('実在する日付を入力してください。')
    if not re.fullmatch(r'\d+',d['amount']): raise ValueError('金額は0以上の整数で入力してください。')
    d['amount']=int(d['amount'])
    if d['amount']>999999999999: raise ValueError('金額は999999999999円以下で入力してください。')
    return d
def workbook_rows():
    ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(WORKBOOK) as z:
        strings=[]
        if 'xl/sharedStrings.xml' in z.namelist():
            strings=[''.join(s.itertext()) for s in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
        root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        result=[]
        for row in root.findall('m:sheetData/m:row',ns):
            r=int(row.attrib['r'])
            if r>4: continue
            values=['']*5
            for c in row.findall('m:c',ns):
                col=ord(c.attrib['r'][0])-65
                if col>4: continue
                v=c.find('m:v',ns); text=v.text if v is not None else ''
                if c.attrib.get('t')=='s': text=strings[int(text)]
                elif c.attrib.get('t')=='inlineStr': text=''.join(c.find('m:is',ns).itertext())
                elif r>1 and col==3:
                    text=(datetime.date.fromisoformat(text[:10]).isoformat() if c.attrib.get('t')=='d' else (datetime.datetime(1899,12,30)+datetime.timedelta(days=float(text))).date().isoformat())
                elif r>1 and col==4: text=int(float(text))
                values[col]=text
            result.append(values)
    return {'app':'dots ローカルXLSXビューア','filename':WORKBOOK.name,'sheet':'架空案件','headers':result[0],'rows':result[1:],'total':sum(r[4] for r in result[1:])}
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw): super().__init__(*a,directory=str(ROOT),**kw)
    def end_headers(self):
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');super().end_headers()
    def send_json(self,obj,status=200):
        body=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/api/cases': return self.send_json({'rows':read_cases()})
        if self.path=='/api/workbook': return self.send_json(workbook_rows())
        if self.path=='/': self.path='/case-demo/index.html'
        return super().do_GET()
    def do_POST(self):
        if self.headers.get('Origin') not in (None,'http://127.0.0.1:8765','http://localhost:8765'):
            return self.send_json({'error':'Local origin only'},403)
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n>10000: raise ValueError('入力が大きすぎます。')
            data=json.loads(self.rfile.read(n))
            with LOCK:
                if self.path=='/api/confirm':
                    d=validate(data,read_cases());token=uuid.uuid4().hex;PENDING[token]=d
                    return self.send_json({'token':token,'row':d})
                if self.path=='/api/register':
                    token=data.get('token');d=PENDING.get(token)
                    if not d: raise ValueError('内容確認からやり直してください。')
                    rows=read_cases();d=validate(d,rows);rows.append(d)
                    temp=STORE.with_suffix('.tmp');temp.write_text(json.dumps(rows,ensure_ascii=False,indent=2));temp.replace(STORE);PENDING.pop(token,None)
                    return self.send_json({'saved':True,'row':d})
                return self.send_json({'error':'Not found'},404)
        except (ValueError,TypeError) as e: return self.send_json({'error':str(e)},400)
if __name__=='__main__':
    print('Demo only: http://127.0.0.1:8765/case-demo/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',8765),Handler).serve_forever()
