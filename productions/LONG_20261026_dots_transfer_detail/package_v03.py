"""Versioned review digest, article evidence and posting text for the new dialogue."""
from pathlib import Path
import hashlib,json,math,re,shutil,subprocess,zipfile
from markdown_it import MarkdownIt
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v03';OLD=OUT.parent/'v01'


def main():
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'));config=json.loads((OUT/'render-config.json').read_text(encoding='utf-8'));offset=plan['main_offset']
    # Include complete question-and-answer turns, not arbitrary mid-sentence excerpts.
    opening_end=plan['chapters'][0]['turns'][-1]['end']+.4
    scope=next(c for c in plan['chapters'] if c['id']=='chapter-04')
    closing=plan['chapters'][-1]
    spans=[(0,opening_end),(scope['turns'][0]['start']-.25,scope['turns'][1]['end']+.3),
        (closing['turns'][-2]['start']-.25,plan['seconds'])]
    digest=OUT/'会話とBGM確認-v03.mp4'
    filters=[]
    for i,(a,b) in enumerate(spans):filters.extend([f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]',f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]'])
    filters.append(''.join(f'[v{i}][a{i}]' for i in range(len(spans)))+f'concat=n={len(spans)}:v=1:a=1[v][a]')
    with (OUT/'digest.log').open('w',encoding='utf-8') as log:
        subprocess.run(['ffmpeg','-v','warning','-nostdin','-n','-i',str(OUT/'dots-transfer-detail-v03.mp4'),'-filter_complex',';'.join(filters),
            '-map','[v]','-map','[a]','-c:v','libx264','-preset','veryfast','-crf','18','-c:a','aac','-b:a','192k','-ar','48000','-ac','2',
            '-movflags','+faststart','-threads','4',str(digest)],stdout=log,stderr=log,check=True)
    subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(digest),'-f','null','-'],check=True)
    (OUT/'digest-spans.json').write_text(json.dumps(dict(seconds=sum(b-a for a,b in spans),source_spans=spans,full_decode=True,
        purpose='新版の会話とBGMを確認する抜粋。質問と返答の途中で切らない。'),ensure_ascii=False,indent=2),encoding='utf-8')
    dest=OUT/'blog-handoff/v03';assets=dest/'assets';assets.mkdir(parents=True,exist_ok=False)
    original=OLD/'blog-handoff/v01';manifest=json.loads((original/'asset-manifest.json').read_text(encoding='utf-8'))
    for item in manifest['assets']:
        src=ROOT/item['artifact']['path'];target=assets/src.name
        if hashlib.sha256(src.read_bytes()).hexdigest().upper()!=item['artifact']['sha256'].upper():raise ValueError('Changed evidence image')
        shutil.copy2(src,target);item['artifact']['path']=target.relative_to(ROOT).as_posix()
    duration=f'横長約{int(plan["seconds"]//60)}分{round(plan["seconds"]%60):02d}秒'
    def revised(text):
        return text.replace('横長4分40秒',duration).replace('未公開の草稿。','未公開の草稿（動画v03対応）。',1)
    article=revised((original/'article-draft-v01.md').read_text(encoding='utf-8'))
    (dest/'article-draft-v03.md').write_text(article,encoding='utf-8')
    (HERE/'article-draft-v03.md').write_text(revised((HERE/'article-draft-v01.md').read_text(encoding='utf-8')),encoding='utf-8')
    for name in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',article):assert (dest/name).is_file(),name
    oldpage=(original/'index.html').read_text(encoding='utf-8');style=oldpage[oldpage.index('<style>'):oldpage.index('</style>')+8]
    html='<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots自動転記 記事草稿v03</title>'+style+'<main>'+MarkdownIt('commonmark',{'html':False}).enable('table').render(article)+'</main></html>'
    (dest/'index.html').write_text(html,encoding='utf-8')
    manifest.update(video_version='v03',new_product_claims=False,new_screen_capture='not applicable: dialogue and soundtrack revision only',published=False)
    (dest/'asset-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    members=[dest/'index.html',dest/'article-draft-v03.md',dest/'asset-manifest.json',*assets.iterdir()]
    hashes={p.relative_to(dest).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in members}
    package=dest/'dots-transfer-detail-article-v03.zip'
    with zipfile.ZipFile(package,'x',zipfile.ZIP_DEFLATED) as z:
        for p in members:z.write(p,p.relative_to(dest).as_posix())
        z.writestr('manifest-sha256.json',json.dumps(hashes,indent=2))
    with zipfile.ZipFile(package) as z:
        assert z.testzip() is None
        assert all(hashlib.sha256(z.read(n)).hexdigest()==h for n,h in hashes.items())
    def stamp(s):
        n=math.floor(s);return f'{n//60:02d}:{n%60:02d}'
    chapters=['00:00 今日は何をしたい？']+[stamp(c['start'])+' '+c['title'] for c in plan['chapters'][1:]]
    desc=(HERE/'youtube-description.txt').read_text(encoding='utf-8')
    desc=re.sub(r'00:00 同じ情報.*?04:10 小さな範囲から試そう','\n'.join(chapters),desc,flags=re.S)
    desc=desc.replace('男女2人の掛け合いと実操作','男性の質問と女性の実演案内・表情のあるPIPと実操作')
    (HERE/'youtube-description-v03.txt').write_text(desc,encoding='utf-8')
    (OUT/'youtube-upload-v03.txt').write_text((HERE/'youtube-title.txt').read_text(encoding='utf-8')+'\n'+desc,encoding='utf-8')
    (OUT/'index.html').write_text('''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dots自動転記 動画v03</title><style>body{max-width:1100px;margin:28px auto;padding:18px;background:#f3f1eb;color:#183e35;font:18px/1.8 system-ui}video{max-width:100%}a{color:#276b55}</style>
<h1>【ChatGPT】Excelからシステムへ自動転記！dotsの実演と人の確認</h1><p>v03。男性がやりたいことを聞き、女性が答えて作業を案内する会話へ再構築。声はCharon／Aoede。BGMは112 BPMの明るいメジャー調。</p><video controls playsinline preload="metadata" src="dots-transfer-detail-v03.mp4" poster="qa/final-05.jpg"></video><h2>会話とBGMの確認用抜粋</h2><video controls playsinline preload="metadata" src="会話とBGM確認-v03.mp4"></video>
<p>実演の操作速度を維持し、男性左・女性右のPIPを継続。入力や詳細照合の間は人物を出しません。口は音声強度で動く簡易方式です。</p><p><a href="blog-handoff/v03/index.html">記事草稿と根拠画像10点</a> ／ <a href="youtube-upload-v03.txt">タイトル・概要欄・章</a> ／ <a href="captions.srt">字幕</a></p><p>人の最終試聴、スマホ実機、完成物の採用・公開は別確認。旧版v01・v02を保持しています。</p></html>''',encoding='utf-8')
    print('Packaged',round(sum(b-a for a,b in spans),2),'second review excerpt and 10 unchanged article evidence images',flush=True)


if __name__=='__main__':main()
