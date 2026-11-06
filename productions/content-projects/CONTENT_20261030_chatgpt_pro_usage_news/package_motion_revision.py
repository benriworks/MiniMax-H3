"""Archive the new motion bank and reproducible editorial inputs, never credentials."""
from pathlib import Path
import hashlib,importlib.util,json,zipfile
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=ROOT/'outputs/content-projects'/HERE.name

def main():
 spec=importlib.util.spec_from_file_location('motion_editor',HERE/'render_motion_revision.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.checked_sources()
 release=OUT/'release/v03';qc=json.loads((release/'verification.json').read_text(encoding='utf-8'))
 if qc['full_decode']!='passed' or qc.get('ai_visual_review') is not True:raise RuntimeError('Final visual/technical review is not complete')
 files=[]
 for job in m.JOBS:
  d=OUT/'motions/v01'/job
  for name in ['graph.json','prompt.txt','request.json','submission.json','history.json','verification.json','visual-review.json','frame-3.png','public-frame-3.png','public-closeup-v01.mp4','public-derivative.json']:
   p=d/name
   if p.exists():files.append(p)
  data=json.loads((d/'verification.json').read_text(encoding='utf-8'));files.append(ROOT/data['artifact']['path'])
  files.append(OUT/'motions/v01/input'/job/'keyframe.png')
 for name in ['male-reference.png','female-reference.png']:files.append(OUT/'characters'/name)
 for name in ['chatgpt-usage-header.png','chatgpt-plan-label.png','openai-allowance-short-quote-v02.png']:files.append(OUT/'captures'/name)
 for v in ['v02','v03']:
  for name in ['chatgpt-pro-usage-'+v+'.mp4','timeline.json','delivery.json','verification.json','motion-provenance.json']:
   p=OUT/'release'/v/name
   if p.exists():files.append(p)
 files+=sorted((OUT/'blog-handoff/motion-assets-v01').glob('*.png'))
 for name in ['motion-jobs-v01.json','produce.py','render_motion_revision.py','inspect_motion_revision.py','export_motion_stills.py','MOTION_REVISION_V03_JA.md']:
  files.append(HERE/name)
 dest=OUT/'release/v03/ChatGPT-Pro-H3-motion-reuse-v01.zip'
 if dest.exists():raise RuntimeError('Preserve the old archive; choose a new version')
 manifest=[]
 with zipfile.ZipFile(dest,'x',zipfile.ZIP_DEFLATED) as archive:
  for p in sorted(set(files)):
   rel=p.relative_to(ROOT).as_posix();assert '_private' not in rel and 'drive-upload' not in rel
   data=p.read_bytes();archive.writestr(rel,data);manifest.append(dict(path=rel,bytes=len(data),sha256=hashlib.sha256(data).hexdigest()))
  archive.writestr('MANIFEST.json',json.dumps(dict(files=manifest,publication_approved=False),ensure_ascii=False,indent=2))
  archive.writestr('README_JA.txt','新規H3人物動画6本の原本、編集用派生、参照画像、原稿・検証と本編v02/v03を保存しています。\nGitHubの同じ版のリポジトリへ、アーカイブの相対パスのまま復元できます。モデル・実行環境は別途必要です。APIキー・Drive識別子・個人情報入り画面原本は含めません。\n男性の納得ポーズの原本には意図しない胸元の文字があります。公開・再利用には同フォルダーのpublic-closeup-v01.mp4を使ってください。public-derivative.jsonに原本hashと切り出し範囲を記録しています。\n人物の新規シリーズへの割り当て、記事掲載、完成動画の最終採用・公開は別途判断してください。\n')
 with zipfile.ZipFile(dest) as archive:
  if archive.testzip() is not None:raise RuntimeError('Archive integrity failure')
  for entry in manifest:
   if hashlib.sha256(archive.read(entry['path'])).hexdigest()!=entry['sha256']:raise RuntimeError('Archive member hash mismatch')
 print(json.dumps(dict(path=str(dest),bytes=dest.stat().st_size,members=len(manifest)+2,sha256=hashlib.sha256(dest.read_bytes()).hexdigest())))
if __name__=='__main__':main()
