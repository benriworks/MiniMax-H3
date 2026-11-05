"""Versioned common-article kit: direct-render figures, citations, portable HTML."""
from pathlib import Path
import hashlib,html,json,shutil,sys,zipfile
from markdown_it import MarkdownIt
from produce import ROOT,HERE,OUT,Renderer,plan,save,sha

DEST=OUT/'article/v03'

def build():
    assets=DEST/'assets';assets.mkdir(parents=True,exist_ok=True);p=plan('full');r=Renderer('full');records=[]
    choices=[('article-history-timeline','f34',4.0,'ニューラル言語モデル、word2vec、Transformer、GPTとBERTの代表的な年表'),('article-bank-context','f08',3.8,'bankが文脈により銀行や川岸を表す例'),('article-word-vectors','f07',5.0,'学習した単語表現を扱う模式図。配置は実測値ではない'),('article-self-attention','f13',4.0,'語同士の関係の模式図。Attentionの実測値ではない'),('article-transformer-branches','f26',3.2,'Transformerを共通の土台とする二つの研究。GPTとBERTを直接の親子関係にはしない'),('article-gpt-next','f22',4.2,'前のトークンから次を予測する学習の説明例。初代GPTの実行結果ではない'),('article-bert-mask','f28',2.2,'前後の文脈から隠した部分を予測する学習の説明例。BERTの実行結果ではない'),('article-initial-gpt-vs-bert','f31',3.5,'初代GPTとBERTの学習方法の比較。現在の全モデルの二分法ではない')]
    for aid,tid,local,alt in choices:
        t=dict(next(t for t in p['turns'] if t['id']==tid));t['subtitles']=[]
        if aid=='article-transformer-branches':t.update(visual='gpt_bert',chapter='compare')
        im=r.frame(t,local,t['start']+local).crop((0,0,1920,875));target=assets/(aid+'.png');im.save(target)
        records.append(dict(asset_id=aid,path='assets/'+target.name,dimensions=list(im.size),bytes=target.stat().st_size,sha256=sha(target),alt=alt,source='Original diagram rendered at article resolution, not extracted from MP4'))
    quote_data=json.loads((OUT/'article/v01/quote-assets-v01.json').read_text(encoding='utf-8'))['items']
    labels={'transformer-2017':'Vaswaniほか（2017）Attention Is All You Need','gpt-2018':'Radfordほか（2018）初代GPT論文','bert-2018':'Devlinほか（2018）BERT論文'}
    for q in quote_data:
        src=ROOT/q['path'];target=assets/src.name;shutil.copy2(src,target)
        records.append(dict(q,path='assets/'+target.name,alt=labels[q['source_id']]+'の題名部分',caption=labels[q['source_id']]))
    save(DEST/'assets.json',dict(items=records,checked_at='2026-11-06',scope='Common video-to-article material; blog-specific cover/banner/MDX pending'))
    save(HERE/'article-assets-v03.json',dict(checked_at='2026-11-06',package_root=DEST.relative_to(ROOT).as_posix(),items=records))
    by_id={x['asset_id']:x for x in records}
    def figure(aid):
        x=by_id[aid];caption=html.escape(x.get('caption',x['alt']))
        if x.get('source_url'):caption+='　<a href="'+html.escape(x['source_url'],quote=True)+'">原典</a>（2026-11-06確認）'
        return '<figure><img src="'+x['path']+'" alt="'+html.escape(x['alt'],quote=True)+'"><figcaption>'+caption+'</figcaption></figure>'
    raw=(HERE/'ARTICLE_DRAFT_V03_JA.md').read_text(encoding='utf-8');body=raw.split('## 画像の割当と媒体別の残り')[0]
    body='\n'.join(line for line in body.splitlines() if not line.startswith('2026-11-06作成。'))
    sections=body.split('\n## ');md=MarkdownIt('commonmark').enable('table');rendered=md.render(sections[0])
    assignment={'単語の並びを数える方法から、数値の表現を学ぶ方法へ':['article-word-vectors','article-bank-context'],'2017年、Transformerが登場':['transformer-2017-paper-title-quote','article-self-attention'],'初代GPT：次のトークンを予測して事前学習':['gpt-2018-paper-title-quote','article-gpt-next'],'BERT：前後の文脈から隠した部分を予測':['bert-2018-paper-title-quote','article-bert-mask'],'どちらが上、という比較にしない':['article-transformer-branches','article-initial-gpt-vs-bert','article-history-timeline']}
    for section in sections[1:]:
        heading=section.split('\n',1)[0];rendered+=md.render('## '+section)
        rendered+=''.join(figure(aid) for aid in assignment.get(heading,[]))
    css='''*{box-sizing:border-box}body{margin:0;background:#edf2f4;color:#173246;font-family:"Yu Gothic","Meiryo",sans-serif;line-height:1.9;font-size:17px}main{max-width:920px;margin:auto;padding:40px;background:white}h1{font-size:30px;line-height:1.5}h2{font-size:23px;line-height:1.6;margin-top:2.4em;color:#087e82}a{color:#087e82;overflow-wrap:anywhere}figure{margin:24px 0;break-inside:avoid}figure img{width:100%;height:auto;display:block;border:1px solid #d5e1e4;border-radius:8px}figcaption{font-size:13px;color:#526873;margin-top:8px}table{border-collapse:collapse;width:100%;font-size:15px;line-height:1.7}th,td{border:1px solid #c6d7dc;padding:10px;text-align:left;vertical-align:top}th{background:#edf4f4}.status{color:#b84735;font-size:14px}@media(max-width:600px){main{padding:22px 16px}body{font-size:16px}h1{font-size:25px}h2{font-size:21px}th,td{padding:6px;font-size:13px}figcaption{font-size:12px}}@media print{@page{size:A4;margin:15mm}body{background:white;font-size:10.5pt;line-height:1.8}main{max-width:none;padding:0}h1{font-size:20pt}h2{font-size:15pt;break-after:avoid}figure img{border-radius:0}figcaption{font-size:8.5pt}table{font-size:9pt}.status{font-size:9pt}p{orphans:3;widows:3}}'''
    rendered=rendered.replace('言葉を学んだ？BERTとGPT','言葉を学んだ？<br>BERTとGPT')
    (DEST/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>記事草稿v03：BERT・GPTが生まれるまで</title><style>'+css+'</style><main><p class="status">レビュー用の記事草稿v03／未公開</p>'+rendered+'</main></html>',encoding='utf-8')
    shutil.copy2(HERE/'ARTICLE_DRAFT_V03_JA.md',DEST/'article-draft-v03.md');shutil.copy2(HERE/'sources.json',DEST/'sources.json')
    records_files=[dict(path=f.relative_to(DEST).as_posix(),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(DEST.rglob('*')) if f.is_file() and f.name!='SHA256SUMS.json' and '.playwright' not in f.as_posix() and f.suffix.lower() in {'.html','.md','.json','.png'}]
    save(DEST/'SHA256SUMS.json',records_files)
    archive=OUT/'review/v03/ai-history-article-materials-v03.zip';archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for x in records_files:z.write(DEST/x['path'],x['path'])
        z.write(DEST/'SHA256SUMS.json','SHA256SUMS.json')
    with zipfile.ZipFile(archive) as z:
        for x in records_files:assert hashlib.sha256(z.read(x['path'])).hexdigest()==x['sha256']
        assert not any('_private' in n or n.lower().endswith(('.mp3','.wav','.mp4')) for n in z.namelist())
    save(archive.with_suffix('.json'),dict(bytes=archive.stat().st_size,sha256=sha(archive),files=len(records_files)+1,images=len(records),per_member_sha256_verified=True,private_or_media_included=False))
    print(json.dumps(dict(article_images=len(records),package=archive.name,bytes=archive.stat().st_size)),flush=True)

if __name__=='__main__':build()
