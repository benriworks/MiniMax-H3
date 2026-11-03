"""Assemble reusable article materials and an evidence manifest; never publish."""
from pathlib import Path
import json,shutil,hashlib,zipfile
from PIL import Image
from produce import ROOT,HERE,OUT,ASSETS,save,sha

def build():
    dest=OUT/'article/v04';assets=dest/'assets';assets.mkdir(parents=True,exist_ok=True)
    old=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items']
    sources={s['source_id']:s for s in json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']}
    entries=[]
    alt={
      'timeline-v03':'二社の2026年6月から9月の主要なモデル発表を二段で整理した図',
      'prices-v03':'AstraとGPT-6.1 Solの標準API単価。入力10ドルと2ドル、出力50ドルと10ドル、各100万トークンあたり',
      'rumors-v03':'Fable 5.5の名称未確認、GPT-6.1 Astraの公開見送り報道、GPT-6.2 Astraの画像の出所不明を分けた図',
      'fable5':'AnthropicのFable 5とMythos 5公式発表の見出しと製品ビジュアル',
      'astra':'OpenAI公式ページに掲載されたGPT-6 Astraの製品ビジュアル',
      'fable51':'Anthropic公式のClaude Fable 5.1とMythos 5.1の見出し',
      'sol61':'OpenAI公式のAstraに迫る性能を5分の1の価格でというSol発表見出し',
      'opus55':'Anthropic公式のClaude Opus 5.5のモデル名と日付',
      'astra62-post-author':'名称目撃情報を投稿した一般ユーザーTokenGremlinの公開名',
      'astra62-usage-image':'投稿に添付された利用量内訳の画像。元の出所とモデルの実態は未確認'}
    for kind in ['timeline','prices','rumors']:
        p=OUT/'research-figures'/(kind+'-v03.png');q=assets/p.name;shutil.copy2(p,q)
        ids={'timeline':['fable5','opus5','fable51','astra','opus55','api-changelog'],'prices':['sol61-ja','sol61-model'],'rumors':['fable-next-report','astra61-wsj','astra62-post','astra62-clarification','astra62-provenance']}[kind]
        # Use the actual registered IDs; fail rather than invent source records.
        assert all(x in sources for x in ids),ids
        entries.append(dict(path='assets/'+q.name,kind='original_diagram',sha256=sha(q),dimensions=Image.open(q).size,alt=alt[q.stem],source_ids=ids,source_urls=[sources[x]['url'] for x in ids],checked_at='2026-11-03',caption='自作図。本文の条件を併記。媒体別のSVG派生は未実施。'))
    for x in old:
        if x['kind'] not in ['official_excerpt','social_excerpt']:continue
        p=ROOT/x['path'];q=assets/p.name;shutil.copy2(p,q)
        entries.append(dict(path='assets/'+q.name,kind=x['kind'],sha256=sha(q),dimensions=Image.open(q).size,alt=alt[q.stem],source_ids=[x['source_id']],source_url=sources[x['source_id']]['url'],checked_at='2026-11-03',parent_sha256=x['raw']['sha256'],parent_dimensions=x['original_dimensions'],crop_xyxy=x['crop_xyxy'],caption='公式発表の短い引用。独自実演ではない。' if x['kind']=='official_excerpt' else '一般ユーザー投稿の短い引用。元の画像の真正性は未確認。性能スコアではない。'))
    save(dest/'assets.json',dict(package_revision='v04',article_revision='v03',items=entries,native_capture_width=1237,source_upscaling_claimed=False))
    for name in ['ARTICLE_DRAFT_V03_JA.md','ASSET_HANDOFF_JA.md','WORDING_REVISION_JA.md','TITLES_AND_PUBLICATION_JA.md','sources.json']:
        shutil.copy2(HERE/name,dest/name)
    (OUT/'review/v03/07_記事草稿v03.txt').write_text((HERE/'ARTICLE_DRAFT_V03_JA.md').read_text(encoding='utf-8'),encoding='utf-8')
    provenance=list(old)
    for name in ['male-thinking','male-happy','female-understanding']:
        p=ASSETS/(name+'.mp4');original=next((ROOT/'outputs/content-projects/CONTENT_20261030_chatgpt_pro_usage_news/motions/v01'/name).glob('MiniMax*.mp4'))
        assert sha(p)==sha(original)
        provenance.append(dict(path=p.relative_to(ROOT).as_posix(),kind='reused_minimax_motion',sha256=sha(p),source=dict(path=original.relative_to(ROOT).as_posix(),sha256=sha(original))))
    provenance.append(dict(path='video:fable-art',kind='derived_video_crop',parent_asset='fable5.png',crop_xyxy=[0,120,1140,760],reason='Read the official product art without enlarging the website body text.'))
    save(OUT/'asset-manifest-v03.json',dict(items=provenance,article_assets=entries,ignored_media_not_in_git=True))
    manifest=[]
    for p in sorted(dest.rglob('*')):
        if p.is_file() and p.name!='SHA256SUMS.json':manifest.append(dict(path=p.relative_to(dest).as_posix(),sha256=sha(p),bytes=p.stat().st_size))
    save(dest/'SHA256SUMS.json',manifest)
    archive=OUT/'review/v04/model-race-article-kit-v04.zip';archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(dest).as_posix())
    with zipfile.ZipFile(archive) as z:
        for x in manifest:assert hashlib.sha256(z.read(x['path'])).hexdigest()==x['sha256']
    print(json.dumps(dict(article_assets=len(entries),zip_bytes=archive.stat().st_size,zip_sha256=sha(archive)),ensure_ascii=False))

if __name__=='__main__':build()
