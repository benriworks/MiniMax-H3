"""Package only public draft materials with explicit sources and byte checks."""
import json,shutil,zipfile,hashlib
from prepare import ROOT,HERE,OUT,ASSETS,save,sha
from PIL import Image

def build():
    dest=OUT/'article/v01';assets=dest/'assets';assets.mkdir(parents=True,exist_ok=True)
    records=[]
    alts={'cat-quote':'Cat Wu氏が退社を発表した本人投稿の冒頭','thariq-quote':'Thariq氏がAnthropicを退社したと記した本人投稿の冒頭','anthony-quote':'Anthony氏が前日を最終勤務日と記した本人投稿の冒頭','official-role':'Claude公式のCat Wu氏による製品管理の記事見出し','departures-timeline':'直近3人の担当と日本時間の退社発表日','product-handoff-observation':'コード修正の依頼、変更確認、修正の流れと今後の観察点を示す自作図'}
    manifest=json.loads((OUT/'asset-manifest-v01.json').read_text(encoding='utf-8'))['items']
    sources={s['source_id']:s for s in json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']}
    for name in ['cat-quote','thariq-quote','anthony-quote','official-role']:
        p=ASSETS/(name+'.png');q=assets/p.name;shutil.copy2(p,q)
        x=next(v for v in manifest if v['asset_id']==name)
        records.append(dict(path='assets/'+q.name,alt=alts[name],sha256=sha(q),dimensions=Image.open(q).size,source_url=sources[x['source_id']]['url'],checked_at='2026-11-04',crop_xyxy=x['crop_xyxy'],parent_sha256=x['parent_sha256']))
    for name in ['departures-timeline','product-handoff-observation']:
        p=assets/(name+'.png');records.append(dict(path='assets/'+p.name,alt=alts[name],sha256=sha(p),dimensions=Image.open(p).size,source='Original explanatory diagram, not an observed effect of the departures.'))
    save(dest/'assets.json',records)
    for name in ['ARTICLE_DRAFT_JA.md','PROPOSAL_JA.md','EDITING_REVIEW_JA.md','sources.json']:
        shutil.copy2(HERE/name,dest/name)
    sums=[dict(path=p.relative_to(dest).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json'];save(dest/'SHA256SUMS.json',sums)
    archive=OUT/'review/v01/anthropic-departures-draft-article-v01.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(dest).as_posix())
    with zipfile.ZipFile(archive) as z:
        for x in sums:assert hashlib.sha256(z.read(x['path'])).hexdigest()==x['sha256']
    text='企画v01／ショート1本／構成確認待ち／音声・動画は未生成\n\n'+(HERE/'PROPOSAL_JA.md').read_text(encoding='utf-8')+'\n\n会話草稿：\n'
    script=json.loads((HERE/'short-dialogue-v01-draft.json').read_text(encoding='utf-8'))
    for t in script['turns']:text+=t['id']+' '+('男性' if t['speaker']=='male' else '女性')+'\n'+t['display']+'\n\n'
    (OUT/'review/v01/01_構成と会話草稿.txt').write_text(text,encoding='utf-8')
    (OUT/'review/v01/03_記事草稿.txt').write_text((HERE/'ARTICLE_DRAFT_JA.md').read_text(encoding='utf-8'),encoding='utf-8')
    print('Public draft package verified:',len(sums),'files; images:',len(records))

if __name__=='__main__':build()
