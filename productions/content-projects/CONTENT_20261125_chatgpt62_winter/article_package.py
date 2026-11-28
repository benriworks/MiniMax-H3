"""Bundle the offline illustrated article draft, public crops and sources."""
import hashlib
import html
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
import markdown
from PIL import Image

HERE=Path(__file__).resolve().parent
def digest(data):
    return hashlib.sha256(data).hexdigest()

def main(media):
    root=media/"article/v01"
    (root/"figures").mkdir(parents=True,exist_ok=True)
    content=(HERE/"article-draft.md").read_text(encoding="utf-8")
    assets=re.findall(r"!\[([^\]]+)\]\((figures/[^)]+)\)",content)
    images=[]
    for alt,key in assets:
        filename=Path(key).name
        src=media/"captures"/("official" if key.endswith(".webp") else "figures")/filename
        target=root/key
        shutil.copyfile(src,target)
        with Image.open(target) as im: size=im.size
        images.append(dict(file=key,alt=alt,pixels=size,sha256=digest(target.read_bytes())))
    (root/"article.md").write_text(content,encoding="utf-8")
    shutil.copyfile(HERE/"SOURCES_JA.md",root/"sources.md")
    (root/"figures.json").write_text(json.dumps(images,ensure_ascii=False,indent=2),encoding="utf-8")
    body=markdown.markdown(content,extensions=["tables"])
    style="html{color:#192e38;background:#f5f1e8;font:18px/1.9 system-ui,sans-serif}main{background:#fffdf7;max-width:780px;padding:3vw 5vw 8vw;margin:auto}h1{font-size:clamp(1.65rem,4vw,2.5rem);line-height:1.45}h2{line-height:1.6;margin-top:2.5rem}img{display:block;max-width:100%;height:auto;margin:1.7rem auto}table{border-collapse:collapse;width:100%;font-size:clamp(12px,2vw,16px)}td,th{padding:.5em;border-bottom:1px solid #aaa}a{color:#096864}"
    (root/"article.html").write_text('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GPT-6.2で宿の料金表を比べる</title><style>'+style+'</style><main>'+body+'</main></html>',encoding="utf-8")
    files=[root/p for p in ["article.md","article.html","sources.md","figures.json"]]+[root/x["file"] for x in images]
    manifest={p.relative_to(root).as_posix():digest(p.read_bytes()) for p in files}
    (root/"sha256.json").write_text(json.dumps(manifest,indent=2),encoding="ascii")
    archive=root/"chatgpt62-chat-article-v01.zip"
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
        for f in files+[root/"sha256.json"]: z.write(f,f.relative_to(root).as_posix())
    with zipfile.ZipFile(archive) as z:
        assert not z.testzip()
        assert set(z.namelist())==set(manifest)|{"sha256.json"}
        assert all(digest(z.read(k))==v for k,v in manifest.items())
    print(f"{len(images)} public figures, {len(manifest)+1} verified ZIP members")
if __name__=="__main__": main(Path(sys.argv[1]))
