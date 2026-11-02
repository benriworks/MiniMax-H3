"""Article handoff and verified ZIP, excluding media binaries and private originals."""
import hashlib,html,json,re,shutil,zipfile
from pathlib import Path
from PIL import Image
import produce as p
def md_html(source):
    def inline(s):
        s=html.escape(s)
        s=re.sub(r'\[([^\]]+)\]\((https://[^)]+)\)',r'<a href="\2">\1</a>',s)
        return re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s)
    parts=[];paragraph=[];items=[]
    def flush():
        if paragraph:parts.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
        if items:parts.append('<ul>'+''.join('<li>'+inline(x)+'</li>' for x in items)+'</ul>');items.clear()
    for line in source.splitlines():
        if not line.strip():flush();continue
        image=re.fullmatch(r'!\[([^\]]*)\]\((images/[A-Za-z0-9_.-]+)\)',line)
        if image:flush();parts.append(f'<figure><img src="{image[2]}" alt="{html.escape(image[1])}"></figure>');continue
        if line.startswith('#'):
            flush();level=len(line)-len(line.lstrip('#'));parts.append(f'<h{level}>'+inline(line[level:].strip())+f'</h{level}>')
        elif line.startswith('- '):
            if paragraph:flush()
            items.append(line[2:])
        elif line.startswith('> '):flush();parts.append('<blockquote>'+inline(line[2:])+'</blockquote>')
        else:paragraph.append(line)
    flush();return '\n'.join(parts)
def main():
    dest=p.OUT/'blog-handoff/v01';images=dest/'images';images.mkdir(parents=True,exist_ok=True)
    names=['v3-final','v2-final','size-comparison','01_table','02_glass','03_wine_geometry','05_final_geometry']
    for n in names:shutil.copy2(p.ASSETS/(n+'.png'),images/(n+'.png'))
    shutil.copy2(p.ASSETS/'official-dots-heading.png',images/'official-dots-heading.png')
    plans={k:json.loads((p.OUT/'release/v01'/k/'timeline.json').read_text(encoding='utf-8')) for k in ['short','full']}
    def stamp(x):return f'{int(x)//60}:{int(x)%60:02}'
    text=['# 投稿用タイトルと概要欄','',p.SCRIPT['short_title'],'','完成した5秒のCGから、注ぎ終わりの動きと瓶の比率の修正を約30秒で紹介します。制作・確認・修正の詳しい流れはフル動画へ。','',p.SCRIPT['full_title'],'','dotsのクラウドPCでBlenderを使ったワインCGの制作例。実際の工程キャプチャと初版・v2・v3の映像で、注ぎ終わりと瓶の比率を見直す過程を紹介します。既存の男女による掛け合い、図解、字幕付き。','工程は実画面の静止画で、連続操作の録画ではありません。液体は形を制御するアニメーションで、流体の物理シミュレーションではありません。元CGは960×540。完全無人や制作全体の所要時間、厳密な750ml容量を実証したものではありません。','','## フル版チャプター']
    for key,title in [('f01','完成したワインCG'),('f04','クラウドPCのBlender'),('f06','実際の制作工程'),('f09','修正1：注ぎ終わり'),('f11','修正2：瓶とグラスの比率'),('f13','液体の表現と限界'),('f15','完成カットを確認'),('f16','確認して修正する')]:
        t=next(x for x in plans['full']['turns'] if x['id']==key);text.append(stamp(t['start'])+' '+title)
    text+=['','## 出典','https://learn.chatgpt.com/docs/dots/computers-and-apps','https://www.saverglass.com/en/our-products/catalog-still-wine/ancienne-75-cl-plate-unique','https://www.zwiesel-glas.com/en/shop/wine-glasses/red-wine-glasses/burgundy-red-wine-goblet-classico','','#ChatGPT #dots #Blender #AI活用','','フル末尾10秒は関連動画2枠とチャンネル登録の配置用。YouTube Studioの実際のクリック要素は投稿時に設定する。']
    (p.HERE/'UPLOAD_TEXT_JA.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    for name in ['article-draft.md','SOURCES_JA.md','UPLOAD_TEXT_JA.md']:shutil.copy2(p.HERE/name,dest/name)
    for kind,plan in plans.items():
        shutil.copy2(p.OUT/'release/v01'/kind/'captions.srt',dest/(kind+'-captions.srt'))
        (dest/(kind+'-narration.txt')).write_text('\n\n'.join(t['speaker']+'：'+t['text'] for t in plan['turns'])+'\n',encoding='utf-8')
    body=md_html((dest/'article-draft.md').read_text(encoding='utf-8'))
    (dest/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dotsとBlenderのワインCG・記事草稿</title><style>body{max-width:780px;margin:32px auto;padding:0 20px;color:#173041;background:#fafaf6;font:18px/1.9 sans-serif}h1{font-size:30px;line-height:1.5}h2{font-size:25px;margin-top:2.1em}figure{margin:1.5em 0}img{max-width:100%;height:auto}a{color:#087f83;overflow-wrap:anywhere}blockquote{margin:1em 0;padding:15px 22px;border-left:5px solid #087f83;background:#e8f2ef}</style>'+body+'</html>',encoding='utf-8')
    (dest/'README_JA.md').write_text('# レビュー用の記事・画像・投稿文\n\nindex.htmlがスマホ幅にも対応した記事草稿。Markdown・画像8点・出典・男女のナレーション・字幕・投稿文を含む。画像は私的保存パスとOSドックを除いた公開派生。元撮影・API応答・動画・音声は含めない。\n\nblogのAGENTS.mdと画像・文章規定を確認済み。草稿の準備までで、MDXの組み込み、ブログ固有の案内役バナー、掲載先でのスマホ表示、人による最終採用・公開は別。新しい動画の二人をブログのブランド人物に転用しない。\n',encoding='utf-8')
    manifest=[dict(path=x.relative_to(dest).as_posix(),bytes=x.stat().st_size,sha256=p.sha(x),size=list(Image.open(x).size)) for x in images.iterdir()]
    p.save(dest/'asset-manifest.json',dict(items=manifest,private_originals_included=False,source_native_screenshots=[1366,1024],official_quoted_words=7))
    files=sorted(x for x in dest.rglob('*') if x.is_file() and x.name!='MANIFEST.sha256');lines='\n'.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(dest).as_posix() for x in files)+'\n';(dest/'MANIFEST.sha256').write_text(lines,encoding='utf-8')
    target=p.OUT/'blog-handoff/dots-wine-article-review-v01.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for x in sorted(dest.rglob('*')):
            if x.is_file():z.write(x,x.relative_to(dest).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in lines.splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        count=len(z.namelist())
    p.save(p.OUT/'blog-handoff/verification-v01.json',dict(file=p.rec(target),members=count,crc_verified=True,all_member_hashes_verified=True,private_originals_included=False))
    im=Image.open(p.ASSETS/'v3-final.png').convert('RGB').resize((1280,720));p.box(im,(35,25,1245,175),'#173041');p.Canvas().text(im,'dots × Blender  ワインCGへ',(65,45,1215,150),58,'white');im.save(p.OUT/'release/v01/full/thumbnail.jpg',quality=95)
    print('handoff verified',count,'members',flush=True)
if __name__=='__main__':main()
