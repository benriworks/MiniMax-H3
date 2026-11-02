"""Companion draft articles, revised captions and source-based comparison images."""
import hashlib,html,json,re,shutil,zipfile
from PIL import Image
import revise as r

def main():
    dest=r.OUT/'review-materials/v01';images=dest/'comparison-images';images.mkdir(parents=True,exist_ok=True);catalog=[];summary=[]
    def shot(key,turn,local,name):
        cfg=r.CASES[key];p=json.loads((r.OUT/'release'/cfg['version']/key/'timeline.json').read_text(encoding='utf-8'));t=next(t for t in p['turns'] if t['id']==turn);at=t['start']+local;file=images/(name+'.jpg');video=r.OUT/'release'/cfg['version']/key/cfg['name']
        r.run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(at),'-i',str(video),'-frames:v','1','-q:v','2',str(file)]);catalog.append(dict(path=file.relative_to(dest).as_posix(),seconds=at,video=key,sha256=r.sha(file),native_size=list(Image.open(file).size)))
    shot('wine-short','s04',.8,'wine-before');shot('wine-short','s04',2.4,'wine-after');shot('wine-full','f02',2,'wine-large');shot('wine-full','f11',4.5,'wine-numeric-caption');shot('tokyo-full','f11',3,'tokyo-side');shot('tibo-full','05-03',3,'tibo-caption')
    for key,cfg in r.CASES.items():
        source=r.OUT/'release'/cfg['version']/key;plan=json.loads((source/'timeline.json').read_text(encoding='utf-8'));qc=json.loads((source/'qc.json').read_text(encoding='utf-8'));check=json.loads((source/'qc-actual/verification.json').read_text(encoding='utf-8'))
        folder=dest/'captions-and-scripts'/key;folder.mkdir(parents=True,exist_ok=True)
        for name in ['captions.srt','script-display-and-spoken.json']:shutil.copy2(source/name,folder/name)
        summary.append(dict(video=key,version=cfg['version'],title=plan['title'],seconds=plan['seconds'],sha256=qc['sha256'],bytes=qc['bytes'],caption_states=check['caption_states_checked'],decoded_samples=check['sample_count'],copied_audio_identical=check['copied_audio_identical'],human_reviewed=False,published=False))
    # Article facts are unchanged. Preserve each article's own relative image namespace.
    for name,old in [('wine',r.wine.OUT),('tokyo',r.tokyo.OUT),('tibo',r.tibo.OUT)]:
        src=old/'blog-handoff/v01';target=dest/'article-drafts'/name;target.mkdir(parents=True,exist_ok=True)
        for f in src.iterdir():
            if f.is_file() and f.suffix=='.md':shutil.copy2(f,target/f.name)
        if (src/'images').exists():shutil.copytree(src/'images',target/'images',dirs_exist_ok=True)
    (dest/'README_JA.md').write_text('''# 改訂版の比較・記事引き継ぎ

動画4本の比較用資料です。captions-and-scriptsに改訂字幕と表示/読み原稿、comparison-imagesに完成MP4の実フレーム、article-draftsに元の記事草稿・出典・画像を保存しています。元の公開版を変更していません。動画本体・音声・モデル・API応答・私的原本は含めません。

字幕の文節改行、数字表示、成果物の拡大、ワイン縦版の同位置前後切り替え、東京駅の側面拡大、PIP顔高と目線を改訂しました。比較画像は動画の版面確認用で、ブログのブランド人物バナーへ転用する画像ではありません。記事の事実と原素材は継承し、公開媒体への組み込みとスマホ表示・ユーザー採用は別です。

Tiboの内容と確認時点は元版の2026年11月1日です。Day28を追加取材した最新版ではありません。音声未評価の参考意見を音質不良の証拠とはしていません。東京駅とTiboの音声は元版とhashが一致します。ワインでは必要な4台詞を生成し、独立AI点検は指摘なしでした。
''',encoding='utf-8')
    r.save(dest/'comparison-assets.json',catalog);r.save(dest/'validation-summary.json',summary)
    figures=''.join('<figure><img src="'+html.escape(x['path'])+'"><figcaption>'+html.escape(x['video'])+' '+str(round(x['seconds'],2))+'s</figcaption></figure>' for x in catalog)
    (dest/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>字幕と成果物・改訂比較</title><style>body{max-width:1200px;margin:auto;padding:24px;background:#f7f4ec;color:#173246;font:18px/1.7 sans-serif}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}figure{margin:0}img{max-width:100%;max-height:700px;object-fit:contain}</style><h1>字幕と成果物の見せ方・改訂比較</h1><p>動画の新版は未採用・未公開。既存の記事草稿と出典はarticle-draftsへ収録しています。</p><div class="grid">'+figures+'</div></html>',encoding='utf-8')
    files=sorted(x for x in dest.rglob('*') if x.is_file() and x.name!='MANIFEST.sha256');manifest='\n'.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(dest).as_posix() for x in files)+'\n';(dest/'MANIFEST.sha256').write_text(manifest,encoding='utf-8');target=r.OUT/'review-materials/editorial-revision-materials-v01.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dest.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(dest).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in manifest.splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        assert all(not n.endswith(('.mp4','.wav','.blend','.py')) for n in z.namelist());members=len(z.namelist())
    r.save(r.OUT/'review-materials/verification.json',dict(bytes=target.stat().st_size,sha256=r.sha(target),members=members,crc_and_all_hashes=True,comparison_images=len(catalog),videos=summary))
    print('PACKAGE',members,'members',target.stat().st_size,'bytes',flush=True)
if __name__=='__main__':main()
