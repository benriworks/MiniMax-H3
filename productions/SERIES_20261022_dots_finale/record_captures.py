"""Bind reviewed browser crops to their untouched source screenshots."""
from pathlib import Path
import json
import shutil
import hashlib
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'output/playwright/dots-finale-20261022'

def record(p):
    return dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest().upper())

CAPTURES=[
    (5,'official-memory','tasks-and-memory','Tasks and memory','2026-10-22T10:06:07.661Z',(760,1688,2132,560),(760,1688,483,100),'Persistent memory'),
    (6,'official-call','channels','Message your dot','2026-10-22T10:01:46.053Z',(768,1001,2116,998),(2278,1136,472,233),'Alfred 02:34'),
    (7,'official-recurring','tasks-and-memory','Tasks and memory','2026-10-22T10:06:07.802Z',(760,1686,2132,560),(760,1686,446,102),'Recurring tasks'),
    (8,'official-research','tasks-and-memory','Tasks and memory','2026-10-22T10:06:07.928Z',(760,1685,2132,560),(760,1685,529,102),'Proactive research'),
    (9,'official-rules','controls','Control your dot','2026-10-22T10:07:23.014Z',(768,1023,2116,659),(768,1438,527,123),'Ask before taking action'),
]

def main():
    for n,slug,page,title,when,context_box,box,quoted in CAPTURES:
        folder=ROOT/f'outputs/productions/SHORT_20261022_dots_{n:02d}_editorial/captures'
        folder.mkdir(parents=True,exist_ok=True)
        source=BASE/(slug+'.png');context=BASE/('channels-context.png' if n==6 else slug+'-context.png')
        with Image.open(source) as im:assert im.size==box[2:]
        with Image.open(context) as im:assert im.size==context_box[2:]
        target=folder/source.name;shutil.copyfile(source,target)
        proof=dict(schema_version=1,artifact=record(target),context=record(context),context_clip=dict(zip(['x','y','width','height'],context_box)),clip=dict(zip(['x','y','width','height'],box)),source_url=f'https://learn.chatgpt.com/docs/dots/{page}',title=title,captured_at=when,browser_viewport=dict(width=3696,height=3000),browser_zoom=3,content_modified=False,review_status='capture_review_passed',review_method='AI-assisted visual inspection of each actual crop and preserved browser context; no account content present',type='Official documentation excerpt or UI illustration, not a live execution recording',quoted_text=quoted)
        (folder/(slug+'.json')).write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'reviewed_captures':len(CAPTURES),'quoted_english_words_by_source':{'tasks-and-memory':6,'channels':2,'controls':4}}))

if __name__=='__main__':main()
