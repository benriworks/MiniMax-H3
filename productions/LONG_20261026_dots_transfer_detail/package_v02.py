"""Keep v01 intact; package the revised video, digest and shared article evidence."""
from pathlib import Path
import argparse,hashlib,json,math,re,shutil,subprocess,zipfile
from markdown_it import MarkdownIt
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v02';OLD=OUT.parent/'v01'


def main(digest_only=False):
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'));offset=plan['main_offset']
    digest=OUT/'演出確認ダイジェスト-v02.mp4'
    if digest.exists():raise ValueError('Existing digest; preserve before revision')
    spans=[(0,offset+3),(offset+20,offset+25),(offset+110,offset+118),(offset+223,offset+227),(offset+270,offset+280)]
    filters=[]
    for i,(a,b) in enumerate(spans):
        filters.extend([f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]',f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]'])
    filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(spans)))+f'concat=n={len(spans)}:v=1:a=1[v][a]')
    with (OUT/'digest.log').open('w',encoding='utf-8') as log:
        subprocess.run(['ffmpeg','-v','warning','-nostdin','-n','-i',str(OUT/'dots-transfer-detail-v02.mp4'),
            '-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','18',
            '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-movflags','+faststart','-threads','4',str(digest)],stdout=log,stderr=log,check=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(digest),'-f','null','-'],check=True)
    (OUT/'digest-spans.json').write_text(json.dumps(dict(seconds=sum(b-a for a,b in spans),source_spans=spans,
        purpose='レビュー用の抜粋。フル版とは別ファイル',full_decode=True),ensure_ascii=False,indent=2),encoding='utf-8')
    if digest_only:
        print('Updated digest only; previously verified article package unchanged',flush=True)
        return
    dest=OUT/'blog-handoff/v02'
    if dest.exists():raise ValueError('Preserve old article package')
    assets=dest/'assets';assets.mkdir(parents=True)
    original=OLD/'blog-handoff/v01'
    manifest=json.loads((original/'asset-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['assets']:
        src=ROOT/item['artifact']['path'];target=assets/src.name
        if hashlib.sha256(src.read_bytes()).hexdigest().upper()!=item['artifact']['sha256'].upper():raise ValueError('Changed source article image')
        shutil.copy2(src,target)
        item['artifact']['path']=target.relative_to(ROOT).as_posix()
    article=(original/'article-draft-v01.md').read_text(encoding='utf-8').replace('横長4分40秒','横長約4分55秒')
    article=article.replace('未公開の草稿。','未公開の草稿（動画v02対応）。',1)
    # Keep characters in the video; the article continues to use readable evidence images.
    (dest/'article-draft-v02.md').write_text(article,encoding='utf-8')
    source=(HERE/'article-draft-v01.md').read_text(encoding='utf-8').replace('横長4分40秒','横長約4分55秒').replace('未公開の草稿。','未公開の草稿（動画v02対応）。',1)
    (HERE/'article-draft-v02.md').write_text(source,encoding='utf-8')
    for name in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',article):assert (dest/name).is_file(),name
    oldpage=(original/'index.html').read_text(encoding='utf-8')
    style=oldpage[oldpage.index('<style>'):oldpage.index('</style>')+8]
    html='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots自動転記 記事草稿v02</title>'+style+'<main>'+MarkdownIt('commonmark',{'html':False}).enable('table').render(article)+'</main></html>'
    (dest/'index.html').write_text(html,encoding='utf-8')
    manifest.update(video_version='v02',new_product_claims=False,new_screen_capture='not applicable: character presentation revision only',
        character_artwork_in_article=False,published=False)
    (dest/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    members=[dest/'index.html',dest/'article-draft-v02.md',dest/'asset-manifest.json',*assets.iterdir()]
    hashes={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in members}
    package=dest/'dots-transfer-detail-article-v02.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for p in members:z.write(p,p.relative_to(dest).as_posix())
        z.writestr('manifest-sha256.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
    def timestamp(value):
        n=math.floor(value);return f'{n//60:02d}:{n%60:02d}'
    chapters=['00:00 2人の会話から始める']+[timestamp(c['start'])+' '+c['title'] for c in plan['chapters'][1:]]
    old=(HERE/'youtube-description.txt').read_text(encoding='utf-8')
    desc=re.sub(r'00:00 同じ情報.*?04:10 小さな範囲から試そう','\n'.join(chapters),old,flags=re.S)
    desc=desc.replace('男女2人の掛け合いと実操作','男女2人の掛け合い・表情のあるPIPと実操作')
    (HERE/'youtube-description-v02.txt').write_text(desc,encoding='utf-8')
    (OUT/'youtube-upload-v02.txt').write_text((HERE/'youtube-title.txt').read_text(encoding='utf-8')+'\n'+desc,encoding='utf-8')
    (OUT/'index.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots自動転記 動画v02</title><style>body{max-width:1100px;margin:28px auto;padding:18px;background:#f3f1eb;color:#183e35;font:18px/1.8 system-ui}video,img{max-width:100%}a{color:#276b55}</style>
<h1>【ChatGPT】Excelからシステムへ自動転記！dotsの実演と人の確認</h1><p>v02・約4分55秒。待ち合わせから短い会話で本編へ。男性は左、女性は右。PIPは実演前・強調・注意点・締めに表示し、実操作と詳細照合中は消します。</p>
<video controls playsinline preload="metadata" src="dots-transfer-detail-v02.mp4" poster="qa/final-04.jpg"></video>
<h2>演出確認ダイジェスト（約45秒）</h2><video controls playsinline preload="metadata" src="演出確認ダイジェスト-v02.mp4"></video>
<p>確認位置：0:00 導入、0:35 PIP、2:04 登録前の確認、4:44 締め。口は音声の強さに反応する簡易方式です。音素ごとの厳密な同期ではありません。</p>
<p><a href="blog-handoff/v02/index.html">記事草稿と画像10点</a> ／ <a href="youtube-upload-v02.txt">YouTubeタイトル・概要欄・章</a> ／ <a href="captions.srt">字幕</a></p>
<p>人の最終試聴、口形の自然さの最終評価、スマホ実機、完成物の採用・公開は未確認。記事用の実画面と公式引用はv01の原本を継続利用し、人物の演出変更を新しい製品実証とは扱いません。</p></html>''',encoding='utf-8')
    print('Packaged digest',sum(b-a for a,b in spans),'seconds and 10 unchanged evidence images',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--digest-only',action='store_true');args=parser.parse_args()
    main(args.digest_only)
