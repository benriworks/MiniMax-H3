"""Validate prepared evidence, drafts and received Drive metadata, not AV quality."""
from pathlib import Path
import hashlib,json,re,sys
from PIL import Image
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name

def validate():
    sources=json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources']
    ids={s['source_id'] for s in sources};assert len(ids)==len(sources)
    for s in sources:
        assert s['url'].startswith('https://') and not re.search(r'(?i)(x-amz-|[?&](key|token|sig)=)',s['url'])
    count=0
    for kind in ['full','short']:
        script=json.loads((HERE/f'{kind}-dialogue-v02-draft.json').read_text(encoding='utf-8'))
        turns=script['turns'];assert len({t['id'] for t in turns})==len(turns)
        for t in turns:
            assert t['speaker'] in ['male','female'] and 1<=len(t['reading'])<=300
            assert set(t['source_ids'])<=ids
            assert not re.search(r'Fable|Opus|GPT-|Astra|Anthropic|OpenAI',t['reading'])
            count+=1
    manifest=json.loads((OUT/'asset-manifest.json').read_text(encoding='utf-8'))
    for asset in manifest['items']:
        for item in [asset]+([asset['raw']] if 'raw' in asset else [])+([asset['source']] if 'source' in asset else []):
            path=ROOT/item['path'];assert path.stat().st_size==item['bytes']
            assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
    labels=0
    for kind in ['timeline','prices','rumors']:
        path=OUT/'research-figures'/(kind+'-v02.png')
        with Image.open(path) as image:assert image.size==(1920,1080)
        rows=json.loads(path.with_name(kind+'-v02-layout.json').read_text(encoding='utf-8'))
        assert all(r['fits'] for r in rows);labels+=len(rows)
    files=0
    expected_parent=json.loads((OUT/'_private/drive-preproduction-v01.json').read_text(encoding='utf-8'))['folder']
    for version in ['v01','v02']:
        receipt=OUT/'_private'/f'drive-preproduction-readback-{version}.json'
        for item in json.loads(receipt.read_text(encoding='utf-8')):
            meta=item['result']['structuredContent']
            assert meta['title']==item['name']
            assert int(meta['size'])==(OUT/item['local_path']).stat().st_size
            assert meta['parent_ids']==[expected_parent] and meta['shared'] is False
            files+=1
    report=dict(checked_at='2026-11-03',sources=len(sources),dialogue_turns=count,asset_files=len(manifest['items']),research_diagrams=3,measured_labels=labels,drive_files_size_and_parent_verified=files,remote_media_hash_verified=False,paid_generation_calls=0,video_rendered=False,audio_listened=False,human_reviewed=False,user_approved=False,published=False)
    (OUT/'preproduction-qc.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':validate()
