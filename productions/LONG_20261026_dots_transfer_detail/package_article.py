"""Public candidate images and article draft; never package private chat captures."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,zipfile
from PIL import Image
from markdown_it import MarkdownIt

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v01'


def record(path):return dict(path=path.relative_to(ROOT).as_posix(),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest().upper())


def main():
    dest=OUT/'blog-handoff/v01'
    if dest.exists():raise ValueError('Keep prior article package; use a new version')
    assets=dest/'assets';assets.mkdir(parents=True)
    cloud=OUT/'cloud/recordings'
    items=[
        ('source-table.png',cloud/'source-original.png','実XLSXを専用ビューアに表示した元の3件','demonstration_capture'),
        ('saved-list.png',cloud/'result-original.png','一覧再表示後の保存済み3件','demonstration_capture'),
        ('entry.png',cloud/'stills/scene04-demo001-007.png','一件目の全5欄を入力した実画面','demonstration_capture'),
        ('confirmation.png',cloud/'stills/scene04-demo001-010.png','登録前に確認する5項目と保存操作','demonstration_capture'),
        ('invalid-date.png',cloud/'stills/scene08-validation-016.png','不正日付の拒否と保存結果不変','demonstration_capture'),
        ('field-mapping.png',OUT/'graphics/03-mapping-2.png','元の列と入力欄の対応を編集で整理','editorial_graphic'),
        ('comparison.png',OUT/'graphics/09-compare-3.png','元の15項目と保存結果の照合を整理','editorial_graphic'),
        ('official-control-sentence.png',OUT/'captures/public/official-control-sentence.png','閲覧と操作権を区別する公式の一文','official_quote'),
    ]
    entries=[]
    for name,source,purpose,origin in items:
        target=assets/name;shutil.copy2(source,target)
        with Image.open(target) as im:width,height=im.size
        entries.append(dict(artifact=record(target),derived_from=record(source),width=width,height=height,
            purpose=purpose,origin=origin,content_modified=False,privacy_review='passed',user_approved_for_blog=False))
    # Additional native-size details make the date/amount readable on mobile.
    for name,bounds in [('date-detail.png',(35,315,580,450)),('amount-detail.png',(595,315,1135,450))]:
        source=cloud/'stills/scene04-demo001-007.png';target=assets/name
        with Image.open(source) as im:im.crop(bounds).save(target)
        with Image.open(target) as im:width,height=im.size
        entries.append(dict(artifact=record(target),derived_from=record(source),crop=list(bounds),width=width,height=height,
            origin='demonstration_capture',content_modified=False,purpose='小画面用の値の詳細。補間拡大なし。',privacy_review='passed',user_approved_for_blog=False))
    article=(HERE/'article-draft-v01.md').read_text(encoding='utf-8')
    article=article.replace('![登録前の確認画面。', '![納期の詳細](assets/date-detail.png)\n\n![金額の詳細](assets/amount-detail.png)\n\n![登録前の確認画面。')
    (dest/'article-draft-v01.md').write_text(article,encoding='utf-8')
    body=MarkdownIt('commonmark',{'html':False}).enable('table').render(article)
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots自動転記 詳細記事草稿v01</title>
<style>body{margin:0;background:#f3f1eb;color:#183e35;font-family:Meiryo,sans-serif}main{max-width:760px;margin:auto;padding:35px 22px}h1{font-size:30px;line-height:1.6}h2{font-size:25px;margin-top:50px}p,li{font-size:17px;line-height:2}a{color:#276b55}img{max-width:100%;height:auto;display:block;margin:24px auto;background:white;cursor:zoom-in}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;line-height:1.8}table{display:block;overflow:auto;font-size:15px;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #d1dbd2;white-space:nowrap}@media(max-width:500px){main{padding:20px 16px}h1{font-size:25px}p{font-size:16px}}</style><main>'''+body+'</main></html>'
    (dest/'index.html').write_text(page,encoding='utf-8')
    for p in assets.iterdir():assert p.stat().st_size>0
    for name in __import__('re').findall(r'!\[[^\]]*\]\(([^)]+)\)',article):assert (dest/name).is_file(),name
    manifest=dict(created_at=datetime.now(timezone.utc).isoformat(),assets=entries,private_originals_included=False,
        publication_target='blog',published=False,source_dimensions_note='Native GUI captures 1188x760, below the ~1400px target. Native detail crops and textual data supplement them. No enlargement is claimed as a higher-resolution original.',
        official_source='https://learn.chatgpt.com/docs/dots/computers-and-apps#use-the-cloud-computer',source_checked_at='2026-10-26')
    (dest/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    members=[dest/'index.html',dest/'article-draft-v01.md',dest/'asset-manifest.json',*assets.iterdir()]
    hashes={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in members}
    package=dest/'dots-transfer-detail-article-v01.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as archive:
        for p in members:archive.write(p,p.relative_to(dest).as_posix())
        archive.writestr('manifest-sha256.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert all(hashlib.sha256(archive.read(n)).hexdigest()==h for n,h in hashes.items())
    print('Article package verified:',len(entries),'candidate images',package)


if __name__=='__main__':main()
