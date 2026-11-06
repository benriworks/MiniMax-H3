"""Inspect provided Drive media and safely extract source ZIPs without executing code."""
from pathlib import Path,PurePosixPath
import hashlib,json,subprocess,zipfile
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent;OUT=ROOT/'outputs/content-projects'/HERE.name;SOURCE=OUT/'_private/source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def run(a):return subprocess.run(a,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def main():
    inventory=[];extracted=[];frames=[];dest=OUT/'_private/inspection';dest.mkdir(parents=True,exist_ok=True)
    for p in sorted(SOURCE.rglob('*')):
        if not p.is_file():continue
        item=dict(path=p.relative_to(SOURCE).as_posix(),bytes=p.stat().st_size,sha256=sha(p))
        if p.suffix=='.zip':
            target=OUT/'_private/extracted'/p.stem;target.mkdir(parents=True,exist_ok=True)
            with zipfile.ZipFile(p) as z:
                if sum(x.file_size for x in z.infolist())>300_000_000:raise ValueError('Unexpected ZIP expansion')
                for x in z.infolist():
                    rel=PurePosixPath(x.filename.replace('\\','/'))
                    if rel.is_absolute() or '..' in rel.parts or any(':' in part for part in rel.parts):raise ValueError('Unsafe ZIP path')
                    if (x.external_attr>>16)&0o170000==0o120000:raise ValueError('ZIP symlink excluded')
                    path=(target/str(rel)).resolve();path.relative_to(target.resolve())
                    if x.is_dir():path.mkdir(parents=True,exist_ok=True);continue
                    path.parent.mkdir(parents=True,exist_ok=True)
                    if not path.exists():path.write_bytes(z.read(x))
                    extracted.append(dict(path=path.relative_to(OUT).as_posix(),bytes=path.stat().st_size,sha256=sha(path)))
            item['zip_members']=[x.filename for x in z.infolist()]
        elif p.suffix.lower() in ['.png','.jpg','.jpeg']:
            im=Image.open(p);item['dimensions']=list(im.size);frames.append((p,p.stem))
        elif p.suffix=='.mp4':
            probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(p)]).stdout);item['probe']=probe;seconds=float(probe['format']['duration'])
            for i,t in enumerate([.1,seconds*.28,seconds*.55,seconds*.85,max(.1,seconds-.1)]):
                path=dest/(p.stem+f'-{i}.jpg');run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(t),'-i',str(p),'-frames:v','1','-q:v','2',str(path)]);frames.append((path,p.stem+' '+str(round(t,2))))
        inventory.append(item)
    sheet=Image.new('RGB',(1280,240*((len(frames)+2)//3)),'#D8DFE2');d=ImageDraw.Draw(sheet)
    for i,(path,title) in enumerate(frames):
        im=Image.open(path).convert('RGB');im.thumbnail((420,210));x=i%3*426;y=i//3*240;sheet.paste(im,(x,y));d.text((x+4,y+216),title[:60],fill='#183243')
    sheet.save(dest/'source-contact-sheet.jpg',quality=93)
    (OUT/'source-inventory.json').write_text(json.dumps(dict(files=inventory,extracted=extracted,source_unchanged=True,source_scripts_executed=False),ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(source_files=len(inventory),extracted_files=len(extracted),images_inspected=len(frames),text_files=[x['path'] for x in extracted if Path(x['path']).suffix in ['.md','.txt','.json','.jsonl','.py']])))
if __name__=='__main__':main()
