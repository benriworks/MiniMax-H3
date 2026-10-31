"""Companion article diagrams, attributed excerpts and a portable public-only ZIP."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
FONT=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
BG='#F4F6F8';INK='#1F2937';ACCENT='#B3543A'

def diagram(name,title,cards,footer):
    p=OUT/'blog-handoff/v01/images';p.mkdir(parents=True,exist_ok=True)
    im=Image.new('RGB',(1600,840),BG);d=ImageDraw.Draw(im)
    def label(s,xy,size=48,fill=INK):d.text(xy,s,font=ImageFont.truetype(str(FONT),size),fill=fill)
    label(title,(70,55),62);svg=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630" width="1200" height="630"><rect width="1200" height="630" fill="{BG}"/><g font-family="Noto Sans JP,sans-serif" fill="{INK}"><text x="52" y="91" font-size="46">{title}</text>']
    width=(1460-(len(cards)-1)*36)/len(cards)
    for i,(heading,lines) in enumerate(cards):
        x=70+i*(width+36);d.rounded_rectangle((x,215,x+width,650),radius=22,fill='white',outline=ACCENT,width=4)
        label(heading,(x+30,245),52,ACCENT)
        svg.append(f'<rect x="{x*.75}" y="161" width="{width*.75}" height="326" rx="17" fill="white" stroke="{ACCENT}" stroke-width="3"/><text x="{(x+30)*.75}" y="224" font-size="39" fill="{ACCENT}">{heading}</text>')
        for j,line in enumerate(lines):
            label(line,(x+30,360+j*90),43)
            svg.append(f'<text x="{(x+30)*.75}" y="{(400+j*90)*.75}" font-size="32">{line}</text>')
    label(footer,(70,725),38);svg.append(f'<text x="52" y="573" font-size="28">{footer}</text></g></svg>')
    im.save(p/(name+'.png'));(p/(name+'.svg')).write_text(''.join(svg),encoding='utf-8')

def main():
    diagram('ultra-limits','認証済みUltraの利用制限',[('5時間の枠',['なし','短時間に集中して利用']),('週の上限',['残る','無制限の契約ではない'])],'出典：Claude公式プラン説明 / 2026-10-31確認')
    diagram('ultra-check','Ultraの設定で確認する順番',[('1 プラン',['Ultraの表示','自分の契約を確認']),('2 セッション',['Current session','バーの有無を確認']),('3 週使用量',['週の上限は残る','次の作業前に確認'])],'自動認証と電話番号の確認は別の手続きです')
    diagram('account-separation','切り替えても、アカウントの中身は別々',[('仕事用',['会話とメモリ','ファイル','設定と契約']),('個人用',['会話とメモリ','ファイル','設定と契約'])],'切り替えだけでは、会話の移動や有料プランの共有は行われません')
    handoff=OUT/'blog-handoff/v01'
    for name in ['article-claude-ultra.md','article-chatgpt-accounts.md','SOURCES_JA.md']:
        shutil.copy2(HERE/name,handoff/name)
    assets=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))['items']
    for item in assets:
        if item['kind']=='official_capture':shutil.copy2(ROOT/item['path'],handoff/'images'/Path(item['path']).name)
    (handoff/'README_JA.md').write_text('''# 記事草稿と図版のレビュー用素材

2026-10-31。記事2本の共通Markdown草稿、公式画面の短い抜粋、本文の説明図を収録しています。動画と記事は同じ調査を使用します。

- 記事本文は `article-claude-ultra.md` と `article-chatgpt-accounts.md`。
- 図は1600×840のPNGと1200×630のSVG。公式画面とは別の説明図です。
- 公式抜粋は `images/ultra-*.png` と `account-*.png`。引用範囲とURLは `asset-manifest.json`、根拠は `SOURCES_JA.md`。
- Claudeの撮影アカウントでUltra適用を実証していません。ChatGPTのスマホ実機での切替と通知も未検証です。私的画面、API応答、鍵、Drive識別子は含みません。
- blogの画像規定に合わせる写真と共通人物バナー、MDXの配置、内部リンク、公開は未実施。動画用人物を記事の共通人物として自動掲載しません。noteにも使える共通草稿です。
- 確認してほしい点：条件が伝わるか、手順を想像できるか、記事に補足したいことがあるか。
''',encoding='utf-8')
    public=[{k:v for k,v in item.items() if k!='original'} for item in assets if item['kind']=='official_capture']
    (handoff/'asset-manifest.json').write_text(json.dumps(dict(official_excerpts=public,diagrams='self-authored, not product screenshots',source_checked_at='2026-10-31'),ensure_ascii=False,indent=2),encoding='utf-8')
    files=sorted(p for p in handoff.rglob('*') if p.is_file() and p.name!='MANIFEST.sha256')
    manifest='\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(handoff).as_posix() for p in files)+'\n'
    (handoff/'MANIFEST.sha256').write_text(manifest,encoding='utf-8')
    target=handoff.parent/'AI-news-20261031-blog-review-v01.zip'
    if target.exists():raise RuntimeError('Preserve the existing handoff ZIP')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(handoff.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(handoff).as_posix())
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in manifest.splitlines():
            digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        members=len(z.namelist())
    print(json.dumps(dict(zip=str(target),bytes=target.stat().st_size,members=members,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),all_members_verified=True)))

if __name__=='__main__':main()
