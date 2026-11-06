"""Download relevant original figures linked by the three official articles.

This is source retrieval, not a browser screenshot or a recreated website.
"""
import hashlib
import html
import json
import re
from pathlib import Path

import requests
from PIL import Image
from produce import ROOT, HERE, OUT, save, sha


def fetch():
    original=OUT/'_private/web-originals-v04'
    public=OUT/'official/v04';public.mkdir(parents=True,exist_ok=True)
    pages={'gpt':'https://openai.com/index/language-unsupervised/',
           'transformer':'https://research.google/blog/transformer-a-novel-neural-network-architecture-for-language-understanding/',
           'bert':'https://research.google/blog/open-sourcing-bert-state-of-the-art-pre-training-for-natural-language-processing/'}
    requests_list=[]
    for key,needle,asset in [('transformer','image2.png','google-attention-original'),
                             ('transformer','transform20fps.gif','google-transformer-motion-original'),
                             ('bert','-RLAbr6kPNUo','google-bert-gpt-elmo-original'),
                             ('bert','/f1.png','google-bert-mask-original'),
                             ('bert','/f2.png','google-bert-next-sentence-original')]:
        text=(original/(key+'.html')).read_text(encoding='utf-8')
        links=list(dict.fromkeys(html.unescape(u) for u in re.findall(r'href="([^"]+)"',text) if 'bp.blogspot' in u and needle in u))
        assert len(links)==1,(key,needle,links)
        requests_list.append((key,asset,links[0]))
    text=(original/'gpt.html').read_text(encoding='utf-8')
    tag=next(t for t in re.findall(r'<img\b[^>]*>',text) if 'alt="Language Unsupervised"' in t)
    image_url=html.unescape(re.search(r'\bsrc="([^"]+)"',tag)[1])
    requests_list.append(('gpt','openai-2018-article-image',image_url))
    records=[]
    for key,asset,url in requests_list:
        ext='.gif' if '.gif' in url else '.webp' if '.webp' in url else '.png'
        path=public/(asset+ext)
        if not path.exists():
            response=requests.get(url,timeout=45);response.raise_for_status();path.write_bytes(response.content)
        with Image.open(path) as im:
            width,height=im.size;frames=getattr(im,'n_frames',1)
        records.append(dict(asset_id=asset,path=path.relative_to(ROOT).as_posix(),source_url=pages[key],
                            original_url=url,checked_at='2026-11-06',publisher='OpenAI' if key=='gpt' else 'Google Research',
                            width=width,height=height,frames=frames,bytes=path.stat().st_size,sha256=sha(path),
                            method='Official linked image downloaded directly; not a PC/browser screenshot',
                            purpose='Critique/explanation of the historical research, with on-screen citation and description/article source link'))
    save(public/'manifest.json',records);save(HERE/'official-assets-v04.json',records)
    print(json.dumps([dict(asset_id=x['asset_id'],dimensions=[x['width'],x['height']],frames=x['frames']) for x in records]))


if __name__=='__main__':fetch()
