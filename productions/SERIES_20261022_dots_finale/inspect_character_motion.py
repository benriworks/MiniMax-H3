"""Extract actual completed-MP4 motion evidence for AI visual review."""
import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def record(path): return {'path':path.relative_to(ROOT).as_posix(),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest().upper()}

parser=argparse.ArgumentParser()
parser.add_argument('--episode',type=int,required=True,choices=range(5,10))
parser.add_argument('--review-note',help='Concrete note only after actually inspecting the extracted images')
args=parser.parse_args()
state=read(HERE/f'{args.episode:02d}'/'state.json')
out=ROOT/state['output']
proof=read(out/'verification.json')
video=ROOT/proof['delivery']['path']
assert record(video)['sha256']==proof['delivery']['sha256']
props=read(out/'props.json')
records=[]
paths=[]
for label,index in [('hook',0),('closing',6)]:
    scene=props['scenes'][index]
    for position,offset in enumerate([6,48,min(scene['duration']-6,84)]):
        frame=scene['from']+offset
        image=out/f'motion-{label}-{position}.png'
        if not image.exists():
            subprocess.run(['ffmpeg','-v','error','-n','-ss',str(frame/24),'-i',str(video),'-frames:v','1','-vf','scale=360:640:flags=lanczos',str(image)],check=True,creationflags=FLAGS)
        paths.append(image)
        records.append({'scene':index,'frame':frame,'scene_frame':offset,'image':record(image)})
sheet=out/'motion-contact-sheet.png'
if not sheet.exists():
    montage=Image.new('RGB',(1080,1280),(15,20,28))
    for index,path in enumerate(paths):
        with Image.open(path) as image:
            montage.paste(image.convert('RGB'),((index%3)*360,(index//3)*640))
    montage.save(sheet)
evidence=out/'motion-evidence.json'
if not evidence.exists():
    with evidence.open('x',encoding='utf-8') as stream:
        json.dump({'episode':args.episode,'video':record(video),'method':'Frames extracted from the completed MP4, not separate design renders','samples':records,'contact_sheet':record(sheet),'status':'awaiting_visual_inspection'},stream,ensure_ascii=False,indent=2)
if args.review_note:
    review=out/'motion-visual-review.json'
    with review.open('x',encoding='utf-8') as stream:
        json.dump({'status':'passed','method':'AI visual inspection of completed MP4 samples','reviewed_at':datetime.now(timezone.utc).isoformat(),'note':args.review_note,'evidence':record(evidence)},stream,ensure_ascii=False,indent=2)
print(json.dumps({'episode':args.episode,'sheet':str(sheet),'evidence':str(evidence)}))
