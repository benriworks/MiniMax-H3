"""Read-only source inventory, real video samples and capture contact sheets."""
from pathlib import Path
import hashlib,json,subprocess
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
SOURCE=Path('C:/Users/mono_/Videos/安全ムービー動画ライブラリ/00_Blender')
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest().upper()
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sheet(items,dest):
    cols=3;rows=(len(items)+cols-1)//cols;canvas=Image.new('RGB',(1500,rows*330),'#DCE4E8');d=ImageDraw.Draw(canvas)
    for i,(name,path) in enumerate(items):
        x=i%cols*500;y=i//cols*330;im=ImageOps.contain(Image.open(path).convert('RGB'),(490,295))
        canvas.paste(im,(x+(500-im.width)//2,y+(295-im.height)//2));d.text((x+8,y+303),name,fill='#152C3D')
    canvas.save(dest,quality=92)
def main():
    dest=OUT/'_private/source-inspection';dest.mkdir(parents=True,exist_ok=True);records=[];frames=[];captures=[]
    for path in sorted(SOURCE.rglob('*')):
        if not path.is_file():continue
        rel=path.relative_to(SOURCE).as_posix();item=dict(path=rel,bytes=path.stat().st_size,sha256=sha(path))
        if path.suffix=='.mp4':
            probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]).stdout);item['probe']=probe
            v=next(s for s in probe['streams'] if s['codec_type']=='video');seconds=float(probe['format']['duration'])
            print(json.dumps(dict(path=rel,width=v['width'],height=v['height'],fps=v['avg_frame_rate'],seconds=seconds,audio=any(s['codec_type']=='audio' for s in probe['streams']))),flush=True)
            for i,t in enumerate([.15,seconds*.5,max(.1,seconds-.15)]):
                frame=dest/(path.stem+f'-{i}.jpg');run(['ffmpeg','-v','error','-nostdin','-y','-ss',str(t),'-i',str(path),'-frames:v','1','-q:v','2',str(frame)])
                frames.append((path.stem+f' {t:.1f}s',frame))
        elif path.suffix.lower() in ['.png','.jpg']:
            with Image.open(path) as im:item.update(width=im.width,height=im.height,format=im.format)
            if '/captures/' in '/'+rel or '/renders/' in '/'+rel:captures.append((path.name,path))
        records.append(item)
    save(OUT/'source-inventory.json',dict(source_root=str(SOURCE),source_unchanged=True,items=records))
    sheet(frames,dest/'video-contact-sheet.jpg');sheet(captures,dest/'capture-contact-sheet.jpg')
    print(json.dumps(dict(files=len(records),video_samples=len(frames),capture_samples=len(captures))))
if __name__=='__main__':main()
