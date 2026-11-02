"""Verify handoff members and source preservation without paid calls."""
import hashlib,json,re,zipfile,py_compile
import produce as p

def main():
    inv=json.loads((p.OUT/'source-inventory.json').read_text(encoding='utf-8'))
    for entry in inv['files']:
        f=p.SOURCE/entry['path'];assert f.stat().st_size==entry['bytes'] and p.sha(f)==entry['sha256']
    for entry in inv['extracted']:
        f=p.OUT/entry['path'];assert f.stat().st_size==entry['bytes'] and p.sha(f)==entry['sha256']
    qcs={}
    for kind,expected in [('short',727),('full',3588)]:
        dest=p.OUT/'release/v01'/kind;q=json.loads((dest/'qc.json').read_text(encoding='utf-8'))
        video=dest/f'dots-wine-{kind}-v01.mp4';assert p.sha(video)==q['file']['sha256'];assert q['whole_decode']=='passed'
        assert int(q['frames'])==expected and -17<=float(q['loudness']['input_i'])<=-15 and float(q['loudness']['input_tp'])<=-1.4
        review=json.loads((p.OUT/'_private'/f'ai-listening-{kind}-v01/review.json').read_text(encoding='utf-8'));assert review['audible_issues']==[]
        qcs[kind]=dict(seconds=float(q['seconds']),frames=int(q['frames']),sha256=p.sha(video),bytes=video.stat().st_size,lufs=float(q['loudness']['input_i']),dbtp=float(q['loudness']['input_tp']),human_reviewed=False)
    folder=p.OUT/'blog-handoff/v01';document=(folder/'index.html').read_text(encoding='utf-8')
    images=re.findall(r'<img src="([^"]+)"',document)
    assert len(images)==8 and all((folder/x).is_file() for x in images)
    target=p.OUT/'blog-handoff/dots-wine-article-review-v01.zip'
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for line in z.read('MANIFEST.sha256').decode().splitlines():
            digest,name=line.split('  ',1);assert hashlib.sha256(z.read(name)).hexdigest()==digest
        members=len(z.namelist());assert all(not n.endswith(('.mp4','.wav','.blend','.py')) for n in z.namelist())
    for f in p.HERE.glob('*.py'):py_compile.compile(str(f),doraise=True)
    result=dict(source_files_unchanged=len(inv['files']),extracted_files_unchanged=len(inv['extracted']),videos=qcs,article_images=len(images),zip_members=members,zip_crc_and_hashes_verified=True,private_originals_in_zip=False,python_compilation='passed',human_reviewed=False,user_approved=False,published=False)
    p.save(p.OUT/'delivery-verification-v01.json',result)
    print(json.dumps(result,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
