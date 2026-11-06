"""Companion article v04: large diagrams plus original official quotations."""
import hashlib,html,json,re,shutil,zipfile
from pathlib import Path
from markdown_it import MarkdownIt
from produce_v04 import old,Renderer,ROOT,HERE,OUT


def build():
    dest=OUT/'article/v04';assets=dest/'assets';assets.mkdir(parents=True,exist_ok=True)
    plan=json.loads((OUT/'release/v03/full/timeline.json').read_text(encoding='utf-8'));r=Renderer('full');records=[]
    for aid,tid,local,scene,alt in [
        ('article-word-vectors','f07',3,'vectors','単語の数値表現。点の位置は説明用で、実測値ではない'),
        ('article-bank-context','f08',3,'context','bankが銀行または川岸を表す具体例'),
        ('article-self-attention','f13',8,'relations','単語間の関係を説明する自作図。線は実測値ではない'),
        ('article-gpt-next','f22',8,'gpt_example','過去の文から次を予測する学習の説明例'),
        ('article-bert-mask','f28',8,'bert_example','前後の手掛かりで隠した言葉を予測する学習の説明例'),
        ('article-initial-gpt-vs-bert','f31',8,'compare','初代GPTとBERTの主な学習目標の違い'),
        ('article-history-timeline','f34',3,'timeline','2003・2013・2017・2018年の代表的な研究年表')]:
        t=next(dict(t) for t in plan['turns'] if t['id']==tid);t['subtitles']=[]
        # Call the individual illustration method so article images have no
        # presenters, live dialogue caption, or video-only series badge.
        im=r.background().copy();r.dark=False
        if scene=='vectors':r.vectors(im,local)
        elif scene=='context':r.bank(im,local)
        elif scene=='relations':r.relations(im,local)
        elif scene in {'gpt_example','bert_example'}:r.example(im,local,'gpt' if scene.startswith('gpt') else 'bert')
        elif scene=='compare':r.result(im,local)
        else:r.timeline(im,local)
        im=im.crop((0,0,1920,872));path=assets/(aid+'.png');im.save(path)
        records.append(dict(asset_id=aid,path='assets/'+path.name,width=im.width,height=im.height,sha256=old.sha(path),bytes=path.stat().st_size,alt=alt,kind='original_diagram'))
    official=json.loads((HERE/'official-assets-v04.json').read_text(encoding='utf-8'))
    for aid in ['google-attention-original','google-bert-gpt-elmo-original','google-bert-mask-original','openai-2018-article-image']:
        source=next(x for x in official if x['asset_id']==aid);im=r.image(aid);path=assets/(aid+'.png');im.save(path)
        label={'google-attention-original':'Google ResearchのSelf-Attention原図（2017年8月31日）',
               'google-bert-gpt-elmo-original':'Google ResearchのBERT・初代GPT・ELMo比較原図（2018年11月2日）',
               'google-bert-mask-original':'Google ResearchのMasked LMの説明例（2018年11月2日）',
               'openai-2018-article-image':'OpenAIの初代GPT発表記事の掲載画像（2018年6月11日）。画像：Ben Barry'}[aid]
        records.append(dict(source,path='assets/'+path.name,alt=label,caption=label,sha256=old.sha(path),bytes=path.stat().st_size,kind='official_quotation',derivative='RGBA composited on white for display; diagram labels/content unchanged'))
    old.save(dest/'assets.json',records);old.save(HERE/'article-assets-v04.json',dict(package_root=dest.relative_to(ROOT).as_posix(),items=records))
    raw=(HERE/'ARTICLE_DRAFT_V04_JA.md').read_text(encoding='utf-8')
    base=raw.split('## 画像の割当と媒体別の残り')[0]
    if '## 公式の原図も照らし合わせる' not in base:base+='\n## 公式の原図も照らし合わせる\n'+raw.rsplit('## 公式の原図も照らし合わせる',1)[1]
    base='\n'.join(x for x in base.splitlines() if not x.startswith('2026-11-06作成。'))
    md=MarkdownIt('commonmark').enable('table');sections=base.split('\n## ');rendered=md.render(sections[0])
    mapping={'単語の並びを数える方法から、数値の表現を学ぶ方法へ':['article-word-vectors','article-bank-context'],
             '2017年、Transformerが登場':['google-attention-original','article-self-attention'],
             '初代GPT：次のトークンを予測して事前学習':['openai-2018-article-image','article-gpt-next'],
             'BERT：前後の文脈から隠した部分を予測':['google-bert-gpt-elmo-original','google-bert-mask-original','article-bert-mask'],
             'どちらが上、という比較にしない':['article-initial-gpt-vs-bert','article-history-timeline']}
    by_id={x['asset_id']:x for x in records}
    for section in sections[1:]:
        heading=section.split('\n',1)[0];rendered+=md.render('## '+section)
        for aid in mapping.get(heading,[]):
            a=by_id[aid];caption=html.escape(a.get('caption',a['alt']))
            if a.get('source_url'):caption+='　<a href="'+html.escape(a['source_url'],quote=True)+'">出典の公式記事</a>（2026-11-06確認）'
            style=' style="max-width:400px;margin:auto"' if aid=='openai-2018-article-image' else ''
            rendered+='<figure><img'+style+' src="'+a['path']+'" alt="'+html.escape(a['alt'],quote=True)+'"><figcaption>'+caption+'</figcaption></figure>'
    rendered=rendered.replace('まで：言葉の数値化','まで<br>言葉の数値化')
    css=re.search(r'<style>(.*?)</style>',(OUT/'article/v03/index.html').read_text(encoding='utf-8'),re.S)[1]
    (dest/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GPT・BERT誕生史：改訂記事v04</title><style>'+css+'</style><main><p class="status">改訂レビュー用の記事草稿v04／未公開</p>'+rendered+'</main></html>',encoding='utf-8')
    (dest/'article-draft-v04.md').write_text(base,encoding='utf-8');shutil.copy2(HERE/'sources.json',dest/'sources.json')
    files=[dict(path=p.relative_to(dest).as_posix(),bytes=p.stat().st_size,sha256=old.sha(p)) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json']
    old.save(dest/'SHA256SUMS.json',files);archive=OUT/'review/v04/ai-history-article-materials-v04.zip';archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for item in files:z.write(dest/item['path'],item['path'])
        z.write(dest/'SHA256SUMS.json','SHA256SUMS.json')
    with zipfile.ZipFile(archive) as z:
        for item in files:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
        assert not any('_private' in n or n.lower().endswith(('.mp4','.wav','.mp3','.gif')) for n in z.namelist())
    old.save(archive.with_suffix('.json'),dict(bytes=archive.stat().st_size,sha256=old.sha(archive),images=len(records),per_member_sha256_verified=True,contains_original_music_or_video=False))
    print(json.dumps(dict(images=len(records),official_quotations=4,archive_bytes=archive.stat().st_size)))


if __name__=='__main__':build()
