"""Real-font composition inspection before costly full encoding; no success claim for media."""
from pathlib import Path
import json,math
from PIL import Image,ImageDraw
import produce as p
def main():
    dest=p.OUT/'design-review/v01';dest.mkdir(parents=True,exist_ok=True)
    r=p.Renderer();r.plan={'seconds':500};fallback=p.OUT/'voice/v01/01-00/voice.wav'
    images=[];seen=set()
    for original in p.SCRIPT['turns']:
        if original['visual'] in seen:continue
        seen.add(original['visual']);t=dict(original,start=0,end=15,voice_path=str(fallback),voice_start=.2,voice_seconds=14,subtitles=[dict(start=0,end=15,text=original['text'][:29])])
        im=r.draw(t,6);im.save(dest/(t['visual']+'.png'));images.append((t['visual'],im))
    sheet=Image.new('RGB',(1600,math.ceil(len(images)/4)*255),'#DDE4E5');d=ImageDraw.Draw(sheet)
    for i,(name,im) in enumerate(images):
        x=i%4*400;y=i//4*255;sheet.paste(im.resize((400,225)),(x,y));d.text((x+4,y+231),name,fill='#172F3E')
    sheet.save(dest/'contact-sheet.jpg',quality=92)
    p.save(dest/'label-layout-audit.json',list(p.AUDIT.values()))
    for item in p.AUDIT.values():
        for placement in item['placements']:
            x,y,x2,y2=placement['ink_bounds'];assert 0<=x<x2<=1920 and 0<=y<y2<=1080
    print(json.dumps(dict(design_samples=len(images),label_layouts=len(p.AUDIT),scope='Design only; final frame/audio review still required')))
if __name__=='__main__':
    main()
