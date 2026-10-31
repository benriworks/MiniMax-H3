"""Portable article draft, exact short excerpts and own figures; no private captures."""
from pathlib import Path
import datetime,hashlib,html,importlib.util,json,shutil,zipfile

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name

def main():
    spec=importlib.util.spec_from_file_location('article_figures',HERE.parent/'CONTENT_20261031_ai_news_ultra_accounts/build_handoff.py')
    figures=importlib.util.module_from_spec(spec);spec.loader.exec_module(figures);figures.OUT=OUT;figures.ACCENT='#087E82'
    figures.diagram('reset-types','利用枠の回復と、後で使う1回分',[('自動リセット',['対象の枠に直接反映','その場で回復','保管する券は増えない']),('バンクリセット',['後で使う1回分を保管','受取だけでは回復しない','対象と有効期限を確認'])],'出典：OpenAI「How resets work in Codex」/ 2026-11-01確認')
    figures.diagram('challenge-flow','28日間：毎日改善、または利用枠のリセット',[('序盤',['生成速度・方向修正','入力予測・文脈拡大']),('中盤',['容量・エラーの改善','キャッシュ・編集']),('終盤',['モデル・利用枠','最後の2日間は予告'])],'太平洋時間のDay番号 / Day27・28の配布完了は未確認')
    handoff=OUT/'blog-handoff/v01';(handoff/'images').mkdir(parents=True,exist_ok=True)
    plan=json.loads((HERE/'plan.json').read_text(encoding='utf-8'))
    rows=['# 日別の概要と確認範囲','', '2026-11-01 JST早朝確認。Day番号と日付はPacific基準。全ての機能を列挙した表ではありません。','', '| Day | Pacific日付 | 主な内容 | 状態 |','| --- | --- | --- | --- |']
    for day in plan['days']:
        n=day['day'];date=(datetime.date(2026,10,5)+datetime.timedelta(days=n-1)).isoformat()
        kind={'improvement':'改善の発表','reset':'リセット関連の発表','bank':'バンク付与の報告','forecast':'予告のみ・配布未確認'}[day['type']]
        label=day['label']
        if n==2:label='Auto-review等の改善＋リセット'
        if n==3:label='Cloud/Tailscale等＋バンクリセット'
        if n==18:kind='翌日朝までの反映予告'
        if n==20:kind='当日深夜までの予告'
        if n==13:kind='Doneの投稿。対応づけは補助資料も使用'
        rows.append(f'| {n} | {date} | {label} | {kind} |')
    rows+=['','個々のアカウントへの付与は未実証です。予告と反映を混ぜた総回数は出していません。出典URLと旧版の訂正は `SOURCES_JA.md` を参照。']
    (HERE/'daily-summary.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    for name in ['article-draft.md','daily-summary.md','SOURCES_JA.md','UPLOAD_TEXT_JA.md']:
        shutil.copy2(HERE/name,handoff/name)
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))
    public=[]
    for item in manifest['items']:
        if item['kind']!='source_excerpt':continue
        # Keep the very short reset completion crop as a source candidate, too.
        shutil.copy2(ROOT/item['path'],handoff/'images'/Path(item['path']).name)
        public.append({k:v for k,v in item.items() if k!='original'})
    (handoff/'asset-manifest.json').write_text(json.dumps(dict(excerpts=public,diagrams='self-authored 1600x840 PNG + 1200x630 SVG',private_originals_included=False),ensure_ascii=False,indent=2),encoding='utf-8')
    (handoff/'README_JA.md').write_text('# 動画と記事のレビュー用素材\n\n記事草稿、28日の日別表、出典、投稿文案、短い引用PNG、自作図のPNG/SVGです。私的原本、API応答、残量や保有数、鍵、署名URL、動画や音声は含みません。\n\n記事はblogを想定した共通Markdown草稿で、noteにも転用可能です。blogの人物バナー・カバー写真・MDX配置・最終表示・公開は未実施。記事と動画の採用は別です。\n\n原本の実寸と引用元はSOURCESとasset-manifestを参照。図のPNGは1600px、SVGは1200x630です。引用スクリーンショットはその寸法へ拡大して画質を増やしたものではありません。\n',encoding='utf-8')
    try:
        import markdown
        body=markdown.markdown((handoff/'article-draft.md').read_text(encoding='utf-8'),extensions=['tables'])
    except ImportError:
        body='<pre>'+html.escape((handoff/'article-draft.md').read_text(encoding='utf-8'))+'</pre>'
    (handoff/'index.html').write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Tiboの28日間・記事草稿</title><style>body{max-width:780px;margin:32px auto;padding:0 20px;background:#fafafa;color:#173041;font:18px/1.9 sans-serif}h1{font-size:30px;line-height:1.5}h2{margin-top:2em;font-size:25px}img{max-width:100%;height:auto}a{color:#087e82}pre{white-space:pre-wrap;font:inherit}table{font-size:15px;border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px}</style>'+body+'</html>',encoding='utf-8')
    files=sorted(p for p in handoff.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256')
    entries='\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(handoff).as_posix() for p in files)+'\n'
    (handoff/'MANIFEST.sha256').write_text(entries,encoding='utf-8')
    target=handoff.parent/'Tibo-28days-blog-review-v01.zip'
    if target.exists():raise RuntimeError('Preserve the previous ZIP; use a new handoff version')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(handoff.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(handoff).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in entries.splitlines():
            digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        members=len(z.namelist())
    print(json.dumps(dict(file=target.relative_to(ROOT).as_posix(),bytes=target.stat().st_size,members=members,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),all_members_verified=True)))

if __name__=='__main__':main()
