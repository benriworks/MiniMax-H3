"""Collect public-safe article derivatives; no blog commit or publication."""
from pathlib import Path
import hashlib,json,shutil,sys,zipfile
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name;DEST=OUT/'blog-handoff/v02'
def main():
 if DEST.exists():raise RuntimeError('Keep the old handoff; choose a new version')
 DEST.mkdir(parents=True);assets=DEST/'assets';assets.mkdir()
 font=ROOT/'studio/public/template-assets/NotoSansJP-Variable.ttf'
 def f(n):
  v=ImageFont.truetype(str(font),n);v.set_variation_by_axes([600]);return v
 im=Image.new('RGB',(1600,900),'#F4F1E8');d=ImageDraw.Draw(im)
 d.text((70,45),'Work・Codex：対象の枠は従来比2倍',font=f(65),fill='#172E3B')
 d.text((70,143),'Pro 100・500 ／ Pro 200の低い枠',font=f(43),fill='#087E82')
 base=683
 for x,h,label,word,col in [(200,190,'1','以前','#92A7AA'),(610,380,'2','変更後','#087E82')]:
  d.rounded_rectangle((x,base-h,x+245,base),radius=23,fill=col)
  d.text((x+100,base-h-85),label,font=f(66),fill=col)
  d.text((x+75,base+20),word,font=f(44),fill='#172E3B')
 d.line((120,base,950,base),fill='#CBD5D4',width=4)
 d.rounded_rectangle((1020,290,1530,695),radius=30,fill='white')
 for y,text in [(325,'Pro 200の高い枠'),(410,'据え置き'),(530,'予定の削減は撤回')]:d.text((1050,y),text,font=f(45 if y==325 else 48),fill='#B45135' if y>325 else '#172E3B')
 d.text((70,785),'各対象プランの以前＝1。絶対量・回数・時間のグラフではありません。',font=f(35),fill='#536B77')
 d.text((70,839),'プラン間の量比較ではありません。出典：OpenAI Pro公式ヘルプ（2026-10-31確認）',font=f(28),fill='#536B77')
 im.save(assets/'relative-allowance.png')
 for name in ['chatgpt-usage-header.png','chatgpt-plan-label.png','openai-allowance-short-quote-v02.png']:
  shutil.copy2(OUT/'captures'/name,assets/name)
 for source,target in [('article-draft-v02.md','article-draft.md'),('SOURCES_JA.md','SOURCES_JA.md'),('CAPTURE_AND_REVIEW_JA.md','CAPTURE_AND_REVIEW_JA.md')]:shutil.copy2(HERE/source,DEST/target)
 manifest=dict(version='v02',publication_approved=False,article_status='common_draft_not_placed_in_blog',assets=[])
 for p in sorted(assets.glob('*')):
  with Image.open(p) as pic:wh=pic.size
  manifest['assets'].append(dict(path=p.relative_to(DEST).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),width=wh[0],height=wh[1],privacy_review='passed',source='self-made relative chart' if p.name=='relative-allowance.png' else 'previous captured public-safe crop; see source ledger',user_approved_for_blog=False))
 (DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 with zipfile.ZipFile(OUT/'blog-handoff/ChatGPT-Pro-blog-review-v02.zip','x',zipfile.ZIP_DEFLATED) as z:
  for p in sorted(DEST.rglob('*')):
   if p.is_file():z.write(p,p.relative_to(DEST))
 print(json.dumps({'assets':len(manifest['assets']),'destination':str(DEST)}))
if __name__=='__main__':main()
