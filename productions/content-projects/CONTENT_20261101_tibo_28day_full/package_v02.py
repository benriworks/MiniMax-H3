"""Reuse the approved article material; add end-screen guidance and revision previews."""
import hashlib,json,shutil,zipfile
import produce as p
def main():
    dest=p.OUT/'blog-handoff/v02';target=dest.parent/'Tibo-full-review-materials-v02.zip'
    if dest.exists() or target.exists():raise RuntimeError('Keep prior review version')
    shutil.copytree(p.OUT/'blog-handoff/v01',dest)
    upload=(p.HERE/'UPLOAD_TEXT_JA.md').read_text(encoding='utf-8').replace('06:37 続ける改善に、拍手を','06:37 続ける改善に、拍手を\n07:14 関連動画とチャンネル登録')
    (p.HERE/'UPLOAD_TEXT_V02_JA.md').write_text(upload,encoding='utf-8')
    shutil.copy2(p.HERE/'UPLOAD_TEXT_V02_JA.md',dest/'UPLOAD_TEXT_V02_JA.md')
    shutil.copy2(p.HERE/'END_SCREEN_SETUP_JA.md',dest/'END_SCREEN_SETUP_JA.md')
    for source,name in [('placement-guide.png','end-screen-placement-guide.png'),('09-02-0.6.png','celebration-v02.png')]:
        shutil.copy2(p.OUT/'release/v02/design-review'/source,dest/'images'/name)
    shutil.copy2(p.OUT/'release/v02/end-screen-layout.json',dest/'end-screen-layout.json')
    (dest/'REVISION_V02_JA.md').write_text('# 動画v02の改訂\n\n称賛の光演出を強化し、末尾に10秒の終了画面を追加。本文・36セリフ・既存の引用・記事草稿と図はv01を再利用しています。\n\nYouTubeの実際の動画・登録要素はEND_SCREEN_SETUP_JA.mdを参照して後から設定します。背景画像だけでクリック機能が付くわけではありません。公開・設定操作は行っていません。\n\n原寸ガイドと光演出の画像をimagesへ追加しました。個人情報入り原本・動画・音声・署名URLは同梱しません。\n',encoding='utf-8')
    manifest=json.loads((dest/'asset-manifest.json').read_text(encoding='utf-8'))
    manifest['revision_v02_artwork']=[dict(path='images/'+name,sha256=p.sha(dest/'images'/name),width=1920,height=1080,self_authored=True) for name in ['end-screen-placement-guide.png','celebration-v02.png']]
    p.save(dest/'asset-manifest.json',manifest)
    files=sorted(x for x in dest.rglob('*') if x.is_file() and x.name!='MANIFEST.sha256')
    entries='\n'.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(dest).as_posix() for x in files)+'\n'
    (dest/'MANIFEST.sha256').write_text(entries,encoding='utf-8')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(dest.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(dest).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in entries.splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        members=len(z.namelist())
    p.save(p.OUT/'blog-handoff/verification-v02.json',dict(p.record(target),members=members,all_member_hashes_verified=True,crc_verified=True,article_body_unchanged=True,private_originals_included=False))
    print(json.dumps(dict(p.record(target),members=members)))
if __name__=='__main__':main()
