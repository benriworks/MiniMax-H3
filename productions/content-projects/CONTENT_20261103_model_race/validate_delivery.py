"""Check documentation references and exclude private/media files from Git scope."""
import json,re,py_compile
from pathlib import Path
from urllib.parse import unquote
from produce import ROOT,HERE,OUT,dest,save,sha

def main():
    files=list(HERE.glob('*.md'))+[ROOT/'AGENTS.md',ROOT/'ARCHITECTURE.md',ROOT/'ARCHITECTURE_DIAGRAM.md',ROOT/'docs/video-production/README.md',ROOT/'docs/video-production/PRODUCTION_KNOWHOW_JA.md']
    links=0
    for path in files:
        value=path.read_text(encoding='utf-8')
        assert not re.search(r'AIza[\w-]{25,}|AKIA[A-Z0-9]{16}|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]{20,}|X-Amz-Signature=|drive\.google\.com/(?:file/d|drive/folders)/',value),path
        for match in re.finditer(r'(!?)\[[^\]]*\]\(([^)]+)\)',value):
            target=match[2].split('#')[0].strip('<>')
            if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
            local=(OUT/'article/v04'/unquote(target)) if path.name=='ARTICLE_DRAFT_V03_JA.md' and target.startswith('assets/') else path.parent/unquote(target)
            assert local.exists(),(path.name,target)
            links+=1
    py=list(HERE.glob('*.py'))+[ROOT/'tools/studio/editorial_captions.py',ROOT/'tests/test_editorial_captions.py']
    for p in py:py_compile.compile(str(p),doraise=True)
    sources=json.loads((HERE/'sources.json').read_text(encoding='utf-8'))['sources'];assert len({x['source_id'] for x in sources})==21
    for kind in ['short','full']:
        folder=dest(kind);qc=json.loads((folder/'qc.json').read_text(encoding='utf-8'));assert sha(ROOT/qc['path'])==qc['sha256']
        plan=json.loads((folder/'timeline.json').read_text(encoding='utf-8'));assert plan['source_script_sha256']==sha(HERE/f"{kind}-dialogue-{plan['script_revision']}.json")
    print(json.dumps(dict(documents=len(files),local_links=links,python_syntax=len(py),sources=len(sources),release_hashes=2),ensure_ascii=False))

if __name__=='__main__':main()
