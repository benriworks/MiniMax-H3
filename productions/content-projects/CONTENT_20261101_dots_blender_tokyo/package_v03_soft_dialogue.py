"""Tokyo v03 article/asset handoff; no media binaries or private API responses."""
import hashlib,html,json,re,shutil,zipfile
from PIL import Image
import revise_v03_soft_dialogue as r

def main():
    dest=r.OUT/'blog-handoff/v03';images=dest/'images';images.mkdir(parents=True,exist_ok=True)
    for src in (r.OUT/'blog-handoff/v01/images').iterdir():
        if src.is_file():shutil.copy2(src,images/src.name)
    plan=json.loads((r.DEST/'timeline.json').read_text(encoding='utf-8'));qc=json.loads((r.DEST/'qc.json').read_text(encoding='utf-8'));frames=json.loads((r.DEST/'qc-actual/verification.json').read_text(encoding='utf-8'))
    def stamp(x):return f'{int(x)//60}:{int(x)%60:02}'
    post=['# 投稿タイトルと概要欄','',r.SCRIPT['title'],'','dotsのクラウドPCでBlenderを操作し、東京駅を題材にした簡略モデルを作る制作例です。依頼、段階的な制作、確認、修正の流れを男女の会話で紹介します。','実際の工程画面は静止画です。完成映像はCGのカメラ移動で、実在駅の空撮や正確な建築復元ではありません。','','## チャプター']
    for tid,title in [('f01','完成した3Dモデル'),('f03','クラウドPCのBlender'),('f05','仕上がりの伝え方'),('f06','大きな形から制作'),('f10','側面を見て修正'),('f12','完成CGで細部を確認'),('f13','使う前に人も確認')]:
        t=next(t for t in plan['turns'] if t['id']==tid);post.append(stamp(t['start'])+' '+title)
    post+=['','## 出典','https://learn.chatgpt.com/docs/dots/computers-and-apps','https://learn.chatgpt.com/docs/dots/controls','','#ChatGPT #dots #Blender #3Dモデル','','v03は女性の話し方と用語を直したレビュー候補。元の公開版は変更していません。末尾10秒は関連動画2枠と登録用で、実際のクリック要素はYouTube Studioで別途配置します。']
    (r.HERE/'UPLOAD_TEXT_V03_JA.md').write_text('\n'.join(post)+'\n',encoding='utf-8')
    shutil.copy2(r.HERE/'article-draft-v03.md',dest/'article-draft.md')
    for name in ['SOURCES_JA.md','UPLOAD_TEXT_V03_JA.md','script-v03-soft-dialogue.json']:shutil.copy2(r.HERE/name,dest/name)
    for name in ['captions.srt','script-display-and-spoken.json']:shutil.copy2(r.DEST/name,dest/name)
    (dest/'narration-v03.txt').write_text('\n\n'.join(('男性' if t['speaker']=='male' else '女性')+'：'+t['display'] for t in plan['turns'])+'\n',encoding='utf-8')
    # Use the established plain article preview renderer; no external scripts or publishing.
    import importlib.util
    spec=importlib.util.spec_from_file_location('tokyo_article_markup',r.HERE/'package.py');module=importlib.util.module_from_spec(spec)
    import sys
    sys.modules['produce']=r.e.tokyo
    try:spec.loader.exec_module(module)
    finally:sys.modules.pop('produce',None)
    body=module.md_html((dest/'article-draft.md').read_text(encoding='utf-8'))
    (dest/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>東京駅3Dモデル・記事草稿v03</title><style>body{max-width:780px;margin:auto;padding:24px;color:#173246;background:#fafaf6;font:18px/1.9 sans-serif}img{max-width:100%;height:auto}a{overflow-wrap:anywhere}figure{margin:24px 0}h1{font-size:30px}</style>'+body+'</html>',encoding='utf-8')
    (dest/'README_JA.md').write_text('# 東京駅full v03・記事素材\n\n女性のやわらかい会話、3D/簡略モデルの用語へ改訂した動画に対応する資料です。記事草稿は用語のみ追従し、元の出典・工程画面・CG画像を継承しています。新しい撮影や製品の再実証ではありません。\n\n動画の会話口調を記事の地の文へ強制しません。ブログの人物・画像規定を維持し、媒体ごとのMDX・スマホ表示・最終採用・公開は別。動画・音声・モデル・API応答・私的原本は含めません。\n',encoding='utf-8')
    r.e.save(dest/'validation-summary.json',dict(video_sha256=qc['sha256'],seconds=qc['seconds'],frames=qc['frames'],caption_states=frames['caption_states'],actual_frame_samples=frames['sample_count'],male_pcm_unchanged=frames['male_pcm_unchanged'],new_female_turns=10,human_reviewed=False,user_approved=False,published=False))
    references=re.findall(r'<img src="([^"]+)"',(dest/'index.html').read_text(encoding='utf-8'));assert references and all((dest/x).is_file() for x in references)
    files=sorted(x for x in dest.rglob('*') if x.is_file() and x.name!='MANIFEST.sha256');manifest='\n'.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(dest).as_posix() for x in files)+'\n';(dest/'MANIFEST.sha256').write_text(manifest,encoding='utf-8');target=r.OUT/'blog-handoff/tokyo-v03-soft-dialogue-article-materials.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for f in sorted(dest.rglob('*')):
            if f.is_file():z.write(f,f.relative_to(dest).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in manifest.splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        count=len(z.namelist());assert all(not n.endswith(('.mp4','.wav','.blend','.py')) for n in z.namelist())
    r.e.save(r.OUT/'blog-handoff/verification-v03.json',dict(sha256=r.e.sha(target),bytes=target.stat().st_size,members=count,all_hashes_and_crc=True,article_image_references=len(references),private_originals_included=False))
    print('PACKAGE',count,'members',len(references),'image references',flush=True)
if __name__=='__main__':main()
