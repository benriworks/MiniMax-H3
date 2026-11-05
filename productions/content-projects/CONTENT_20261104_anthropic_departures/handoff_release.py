"""Versioned public article kit; private originals and media are excluded."""
import json,shutil,zipfile,hashlib
from PIL import Image
from prepare import ROOT,HERE,OUT,save,sha

def build():
    dest=OUT/'article/v02';dest.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((OUT/'article/v01/assets.json').read_text(encoding='utf-8'))
    for asset in manifest:
        source=OUT/'article/v01'/asset['path'];target=dest/asset['path'];target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():shutil.copy2(source,target)
        assert sha(source)==sha(target)==asset['sha256'];assert tuple(asset['dimensions'])==Image.open(target).size
    save(dest/'assets.json',manifest)
    for name in ['ARTICLE_DRAFT_V02_JA.md','sources.json','TITLES_AND_PUBLICATION_JA.md','EDITING_REVIEW_V01_JA.md','ASSET_HANDOFF_JA.md','short-dialogue-v01.json','DELIVERY_QC_JA.md']:
        shutil.copy2(HERE/name,dest/name)
    shutil.copy2(OUT/'release/v01/short/captions.srt',dest/'captions.srt')
    records=[dict(path=p.relative_to(dest).as_posix(),sha256=sha(p),bytes=p.stat().st_size) for p in sorted(dest.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json'];save(dest/'SHA256SUMS.json',records)
    archive=OUT/'review/delivery-v01/anthropic-departures-article-v02.zip';archive.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(dest).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==len(records)+1
        for item in records:assert hashlib.sha256(z.read(item['path'])).hexdigest()==item['sha256']
        assert not any('_private' in n or n.lower().endswith(('.mp4','.wav','.mp3')) for n in z.namelist())
    for name,source in [('06_見出しと説明欄.txt','TITLES_AND_PUBLICATION_JA.md'),('07_記事草稿_v02.txt','ARTICLE_DRAFT_V02_JA.md')]:
        (archive.parent/name).write_text((HERE/source).read_text(encoding='utf-8'),encoding='utf-8')
    save(archive.parent/'package-checks.json',dict(sha256=sha(archive),bytes=archive.stat().st_size,payload_members=len(records),manifest_members=1,public_images=len(manifest),video_or_audio_included=False,private_raw_included=False))
    print(json.dumps(dict(package=archive.name,payload_members=len(records),images=len(manifest),bytes=archive.stat().st_size)),flush=True)

if __name__=='__main__':build()
