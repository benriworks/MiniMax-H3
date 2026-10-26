"""Package all three requested fixes and keep article evidence consistent."""
from pathlib import Path
import hashlib,json,re,shutil,subprocess,zipfile
from PIL import Image
from markdown_it import MarkdownIt
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v04';OLD=OUT.parent/'v03'


def save(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    spans=[(0,8),(39,48),(124.5,132.5)];filters=[]
    for i,(a,b) in enumerate(spans):filters.extend([f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]',f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]'])
    filters.append(''.join(f'[v{i}][a{i}]' for i in range(3))+'concat=n=3:v=1:a=1[v][a]')
    digest=OUT/'3か所の修正確認-v04.mp4'
    with (OUT/'digest.log').open('w',encoding='utf-8') as log:
        subprocess.run(['ffmpeg','-v','warning','-nostdin','-n','-i',str(OUT/'dots-transfer-detail-v04.mp4'),'-filter_complex',';'.join(filters),
            '-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-b:a','192k','-ar','48000','-ac','2',
            '-movflags','+faststart','-threads','4',str(digest)],stdout=log,stderr=log,check=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(digest),'-f','null','-'],check=True)
    save(OUT/'digest-spans.json',dict(seconds=25,source_spans=spans,full_decode=True,purpose='修正した3か所だけの抜粋。会話全体のレビューとは別。'))
    old=OLD/'blog-handoff/v03';dest=OUT/'blog-handoff/v04';assets=dest/'assets';assets.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((old/'asset-manifest.json').read_text(encoding='utf-8'));entries=[]
    raw=OUT/'captures/original/entry-complete-15.1.png'
    for item in manifest['assets']:
        src=ROOT/item['artifact']['path'];name=src.name
        # Do not carry the cursor-obscured confirmation image into the new article package.
        if name=='confirmation.png':continue
        target=assets/name
        if name=='entry.png':
            shutil.copy2(raw,target);item['derived_from']=dict(path=raw.relative_to(ROOT).as_posix(),bytes=raw.stat().st_size,sha256=hashlib.sha256(raw.read_bytes()).hexdigest().upper())
            item.update(purpose='入力完了直後の実録フレーム。5項目と120000が読める。登録前の入力画面。',content_modified=False)
        else:
            assert hashlib.sha256(src.read_bytes()).hexdigest().upper()==item['artifact']['sha256'].upper()
            shutil.copy2(src,target)
        item['artifact']=dict(path=target.relative_to(ROOT).as_posix(),bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest().upper())
        entries.append(item)
    article=(old/'article-draft-v03.md').read_text(encoding='utf-8').replace('動画v03対応','動画v04対応')
    article=re.sub(r'!\[登録前の確認画面。[^\n]+\]\(assets/confirmation.png\)\n\n','',article)
    article=article.replace('一件目を入力したフォーム。日付と金額も明示されている','一件目の入力完了直後の実画面。金額120000と日付を確認できる')
    (dest/'article-draft-v04.md').write_text(article,encoding='utf-8')
    source=(HERE/'article-draft-v03.md').read_text(encoding='utf-8').replace('動画v03対応','動画v04対応')
    source=re.sub(r'!\[登録前の確認画面。[^\n]+\]\(assets/confirmation.png\)\n\n','',source)
    source=source.replace('一件目を入力したフォーム。日付と金額も明示されている','一件目の入力完了直後の実画面。金額120000と日付を確認できる')
    (HERE/'article-draft-v04.md').write_text(source,encoding='utf-8')
    for name in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',article):assert (dest/name).is_file(),name
    page=(old/'index.html').read_text(encoding='utf-8');style=page[page.index('<style>'):page.index('</style>')+8]
    (dest/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots転記 記事草稿v04</title>'+style+'<main>'+MarkdownIt('commonmark',{'html':False}).enable('table').render(article)+'</main></html>',encoding='utf-8')
    manifest.update(assets=entries,video_version='v04',new_product_claims=False,new_screen_capture='Existing actual frame selected; no new capture or numeric editing',published=False)
    save(dest/'asset-manifest.json',manifest)
    members=[dest/'article-draft-v04.md',dest/'index.html',dest/'asset-manifest.json',*assets.iterdir()]
    hashes={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in members};package=dest/'dots-transfer-detail-article-v04.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for p in members:z.write(p,p.relative_to(dest).as_posix())
        z.writestr('manifest-sha256.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(name)).hexdigest()==value for name,value in hashes.items())
    shutil.copy2(OLD/'youtube-upload-v03.txt',OUT/'youtube-upload-v04.txt')
    (OUT/'index.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots転記 v04</title><style>body{max-width:1100px;margin:auto;padding:24px;background:#f3f1eb;color:#183e35;font:18px/1.8 system-ui}video{max-width:100%}</style><h1>Excelからシステムへ自動転記 v04</h1><p>0〜5秒の見出し、0:44付近の説明改行、2:07付近の入力内容確認用の実フレームを修正。音声・BGM・尺は採用済みv03を維持。</p><video controls playsinline src="dots-transfer-detail-v04.mp4" poster="qa/after-01.png"></video><h2>3か所の修正確認（25秒の抜粋）</h2><video controls playsinline src="3か所の修正確認-v04.mp4"></video><p><a href="blog-handoff/v04/index.html">記事草稿と画像9点</a> ／ <a href="youtube-upload-v04.txt">見出しと概要欄</a></p><p>v03は採用済み。v04の最終採用・公開とスマホ実機は別確認。</p></html>''',encoding='utf-8')
    print('Packaged 25-second revision excerpt, article v04 with 9 evidence images, posting text',flush=True)


if __name__=='__main__':main()
