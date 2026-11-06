"""Portable article + sources + native-resolution diagrams; private footage stays local."""
from pathlib import Path
import datetime,hashlib,html,json,shutil,zipfile
import produce as p
def main():
    dest=p.OUT/'blog-handoff/v01';target=dest.parent/'Tibo-full-blog-review-v01.zip'
    if dest.exists() or target.exists():raise RuntimeError('Preserve prior handoff; choose a new version')
    (dest/'images').mkdir(parents=True)
    r=p.Renderer();r.plan={'seconds':500};r.presenter=lambda *args,**kwargs:None
    fallback=p.OUT/'voice/v01/01-00/voice.wav'
    for visual in ['benefits','compare','tiers']:
        original=next(t for t in p.SCRIPT['turns'] if t['visual']==visual)
        t=dict(original,start=0,end=15,voice_path=str(fallback),voice_start=.2,voice_seconds=14,subtitles=[])
        r.draw(t,12.8).save(dest/'images'/(visual+'.png'))
    manifest=json.loads((p.OUT/'asset-manifest.json').read_text(encoding='utf-8'));excerpts=[]
    wanted=['tibo-promise-excerpt','tibo-day27-excerpt','usage-reset-description-current']
    for item in manifest['items']:
        if Path(item['path']).stem not in wanted:continue
        source=p.ROOT/item['path'];dst=dest/'images'/source.name;shutil.copy2(source,dst)
        assert p.sha(source)==p.sha(dst)
        excerpts.append(dict(path='images/'+source.name,sha256=p.sha(dst),bytes=dst.stat().st_size,source_url=item.get('url') or 'https://x.com/thsottiaux/status/2106845241357824205',width=p.Image.open(dst).width,height=p.Image.open(dst).height))
    old=json.loads((p.HERE.parent/'CONTENT_20261101_tibo_28day_recap/plan.json').read_text(encoding='utf-8'))
    rows=['# 日別の概要と確認範囲','', '2026-11-01 10時台 JST確認。日付はPacific、原投稿の画面表示はJST。全機能の網羅表ではありません。','', '| Day | Pacific日付 | 主な内容 | 状態 |','| --- | --- | --- | --- |']
    for day in old['days']:
        n=day['day'];date=(datetime.date(2026,10,5)+datetime.timedelta(days=n-1)).isoformat()
        state={'improvement':'改善の発表','reset':'リセット関連の発表','bank':'バンク付与の報告','forecast':'予告・個別反映は未実証'}[day['type']]
        label=day['label']
        if n==2:label='Auto-review等の改善とリセット'
        if n==3:label='Cloud/Tailscale等とバンク付与報告'
        if n==18:state='翌朝までの反映予告'
        if n==20:state='深夜までの予告'
        if n==13:state='Doneの投稿。日別の対応づけは補助資料も使用'
        if n==27:label='バンクリセット、Banked 1/2';state='今回本人の投稿を確認。個人の受領は未実証'
        if n==28:label='バンクリセットの予告';state='未発表。Pacificでは未来'
        rows.append(f'| {n} | {date} | {label} | {state} |')
    rows+=['','予告や発表を、全員への反映回数と同一視した総回数は出していません。原投稿はSOURCESと元ショート案件の出典表から確認できます。']
    (p.HERE/'daily-summary.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    plan=json.loads((p.DEST/'timeline.json').read_text(encoding='utf-8'))
    def stamp(s):m,s=divmod(int(s),60);return f'{m:02}:{s:02}'
    lines=[p.SCRIPT['title'],'','毎日改善、またはリセット。Tiboの28日間チャレンジを、速さ、続けやすさ、利用枠の3つの視点で振り返ります。','自動リセットとバンクリセットの違い、Pro200の条件、使用量画面での確認方法まで、二人の掛け合いで説明します。','','【確認範囲】2026年11月1日10時台 JST。Day27の本人投稿まで確認。Day28は未発表として扱っています。公開が後になる場合は最新発表を確認してください。','リセットの使用や個別付与の実証、速度の実測をした動画ではありません。ボタンと券の動きは説明用の演出です。','','【チャプター】']
    lines += [stamp(c['start'])+' '+c['title'] for c in plan['chapters']]
    lines+=['','【主な出典】','Tiboの開始宣言：https://x.com/thsottiaux/status/2106845241357824205','Day27：https://x.com/thsottiaux/status/2116692529970311254','リセット：https://help.openai.com/en/articles/20001498-how-resets-work-in-codex','Pro条件：https://help.openai.com/en/articles/9793128-about-chatgpt-pro-tiers','リリースノート：https://help.openai.com/en/articles/6825453-chatgpt-release-notes','','#Codex #ChatGPT #OpenAI']
    (p.HERE/'UPLOAD_TEXT_JA.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name in ['article-draft.md','SOURCES_JA.md','daily-summary.md','UPLOAD_TEXT_JA.md']:shutil.copy2(p.HERE/name,dest/name)
    (dest/'README_JA.md').write_text('# フル動画と記事のレビュー素材\n\n共通Markdown草稿、出典、日別表、投稿用見出しとチャプター、短い引用画像3点と自作1920×1080図3点です。個人情報入り原本、API応答、動画、音声、署名URLは含みません。\n\nblogのAGENTS.md・文体・画像規定を確認し、記事用の案内役は動画の二人と分けています。カバー写真、案内役1人のバナー、MDX実装と表示、最終採用・公開は未実施。noteへも共通草稿から派生できます。\n\nアプリ原本は通常のブラウザ幅約1240pxで撮影し、1400pxを満たすと称して拡大していません。図3点はネイティブ1920pxです。スマホの可読性は最終掲載先で要確認。\n',encoding='utf-8')
    p.save(dest/'asset-manifest.json',dict(excerpts=excerpts,diagrams=[dict(path='images/'+name+'.png',sha256=p.sha(dest/'images'/(name+'.png')),width=1920,height=1080,self_authored=True) for name in ['benefits','compare','tiers']],private_originals_included=False))
    try:
        import markdown
        body=markdown.markdown((dest/'article-draft.md').read_text(encoding='utf-8'),extensions=['tables'])
    except ImportError:body='<pre>'+html.escape((dest/'article-draft.md').read_text(encoding='utf-8'))+'</pre>'
    (dest/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tiboチャレンジ・記事草稿</title><style>body{max-width:780px;margin:32px auto;padding:0 20px;background:#fafafa;color:#173041;font:18px/1.9 sans-serif}h1{font-size:30px;line-height:1.5}h2{margin-top:2em;font-size:25px}img{max-width:100%;height:auto}a{color:#087e82}pre{white-space:pre-wrap;font:inherit}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style>'+body+'</html>',encoding='utf-8')
    files=sorted(x for x in dest.rglob('*') if x.is_file());entries='\n'.join(hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.relative_to(dest).as_posix() for x in files)+'\n'
    (dest/'MANIFEST.sha256').write_text(entries,encoding='utf-8')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for file in sorted(dest.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(dest).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in entries.splitlines():digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        count=len(z.namelist())
    p.save(p.OUT/'blog-handoff/verification-v01.json',dict(p.record(target),members=count,crc_verified=True,all_member_hashes_verified=True,private_originals_included=False))
    print(json.dumps(dict(p.record(target),members=count)))
if __name__=='__main__':main()
