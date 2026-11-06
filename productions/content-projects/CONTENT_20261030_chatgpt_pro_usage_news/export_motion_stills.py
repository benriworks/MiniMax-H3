"""Collect newly generated pose stills for article reuse, without blog publication."""
from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=ROOT/'outputs/content-projects'/HERE.name

def main():
 dest=OUT/'blog-handoff/motion-assets-v01';dest.mkdir(parents=True,exist_ok=True)
 jobs=json.loads((HERE/'motion-jobs-v01.json').read_text(encoding='utf-8'))['jobs'];items=[]
 for job,data in jobs.items():
  parent=OUT/'motions/v01'/job;proof=parent/'verification.json';review=parent/'visual-review.json'
  if not proof.exists() or not review.exists():raise RuntimeError('Pose not yet verified and visually reviewed: '+job)
  if json.loads(review.read_text(encoding='utf-8'))['status']!='visual_review_passed':raise RuntimeError('Pose review pending')
  target=dest/(job+'.png');source=parent/('public-frame-3.png' if (parent/'public-derivative.json').exists() else 'frame-3.png')
  if target.exists() and target.read_bytes()!=source.read_bytes():raise RuntimeError('Preserve the prior still')
  if not target.exists():shutil.copy2(source,target)
  items.append(dict(path=target.name,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),parent_video=json.loads(proof.read_text(encoding='utf-8'))['artifact'],frame_seconds=3,source='new locally generated MiniMax H3 I2VA video',character='dots_'+data['who'],pose=data['pose'],kind='frame_from_generated_video',fictional_adult=True,user_approved_for_blog=False,privacy_review='passed'))
 (dest/'manifest.json').write_text(json.dumps(dict(version='motion-assets-v01',items=items,publication_approved=False,notes='Optional source material. The blog uses its own guide-character/image rules; do not place both video presenters automatically.'),ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(dict(still_count=len(items),destination=str(dest))))
if __name__=='__main__':main()
