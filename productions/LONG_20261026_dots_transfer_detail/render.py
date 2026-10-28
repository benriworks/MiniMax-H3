"""Render reviewable 16:9 chapters, with real footage and separate editorial graphics."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,hashlib,json,math,re,shutil,subprocess,sys,wave
from copy import deepcopy
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v01'
sys.path.insert(0,str(ROOT))
from tools.studio.longform_audio import plan_dialogue,assemble_audio
from graphics import editorial,plate,base,text,box,INK,BG,WHITE,MUTED


def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def run(args,log):
    with Path(log).open('w',encoding='utf-8') as f:
        subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def ass_time(t):
    c=round(t*100);return f'{c//360000}:{c//6000%60:02d}:{c//100%60:02d}.{c%100:02d}'


def caption_phrases(s,limit=36):
    sentences=[x for x in re.findall(r'.*?[。？！?！]|.+$',s) if x]
    pieces=[]
    for sentence in sentences:
        pieces.extend([sentence] if len(sentence)<=limit else re.findall(r'.*?、|.+$',sentence))
    result=[];current=''
    for piece in pieces:
        if current and (len(current+piece)>limit or len(current)>6):result.append(current);current=''
        while len(piece)>limit:
            result.append(piece[:limit]);piece=piece[limit:]
        current+=piece
    if current:result.append(current)
    return result


def subtitle_text(s):
    if len(s)>22:
        middle=math.ceil(len(s)/2)
        near=[i+1 for i,c in enumerate(s) if c in '、。' and middle-5<=i<=middle+3]
        cut=min(near,key=lambda i:abs(i-middle)) if near else middle
        s=s[:cut]+'\\N'+s[cut:]
    return s.replace('{','').replace('}','')


def prepare():
    script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'))
    chapters=deepcopy(script['chapters'])
    chapters[0]['title']='同じ情報の入力をdotsに任せる'
    chapters[-1]['tail_seconds']=3.5
    plan=plan_dialogue(chapters,OUT/'voice')
    save(OUT/'timeline.json',plan)
    save(OUT/'audio/verification.json',assemble_audio(plan,OUT/'audio'))
    headers='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Female,Meiryo,56,&H00FFFFFF,&H00FFFFFF,&H00193329,&H00193329,1,0,0,0,100,100,0,0,3,16,0,2,140,140,32,1
Style: Male,Meiryo,56,&H00FFFFFF,&H00FFFFFF,&H00563E25,&H00563E25,1,0,0,0,100,100,0,0,3,16,0,2,140,140,32,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    lines=[];srt=[];idx=1
    for chapter in plan['chapters']:
        for turn in chapter['turns']:
            phrases=caption_phrases(turn['text']);weight=sum(len(p) for p in phrases)
            cursor=turn['start']
            for p in phrases:
                end=cursor+(turn['end']-turn['start'])*len(p)/weight
                lines.append(f'Dialogue: 0,{ass_time(cursor)},{ass_time(end)},{turn["speaker"].title()},,0,0,0,,{subtitle_text(p)}')
                def st(t):
                    value=ass_time(t).replace('.',',')+'0'
                    return value if len(value.split(':',1)[0])==2 else '0'+value
                srt.append(f'{idx}\n{st(cursor)} --> {st(end)}\n{p}\n');idx+=1;cursor=end
    (OUT/'captions.ass').write_text(headers+'\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'captions.srt').write_text('\n'.join(srt),encoding='utf-8')
    fonts=OUT/'fonts';fonts.mkdir(exist_ok=True)
    shutil.copy2('C:/Windows/Fonts/meiryob.ttc',fonts/'meiryob.ttc')
    arts=OUT/'graphics';arts.mkdir(exist_ok=True)
    types={1:['flow'],2:['place'],3:['mapping'],4:['scope'],5:['approval'],6:['mapping'],7:['boundary'],8:['scope'],9:['compare'],10:['caution'],11:['flow']}
    for chapter in plan['chapters']:
        n=int(chapter['id'][-2:])
        for kind in types[n]:
            states=range(5) if kind in ('mapping','compare') else range(4) if kind=='flow' else [-1]
            for active in states:
                editorial(n,chapter['title'],kind,active=active).save(arts/f'{n:02d}-{kind}-{active}.png')
    print('Audio, exact turn timing, captions, editorial plates prepared:',plan['seconds'],'seconds',flush=True)


def render_shot(shot,chapter,index):
    n=int(chapter['id'][-2:]);folder=OUT/'rendered-shots';folder.mkdir(exist_ok=True)
    dest=folder/f'{n:02d}-{index:02d}.mp4'
    duration=shot['seconds'];source=ROOT/shot['path']
    if not source.is_file():raise ValueError('Missing reviewed source: '+str(source))
    signature=dict(shot=shot,chapter=chapter['title'],source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        graphics_sha256=hashlib.sha256((HERE/'graphics.py').read_bytes()).hexdigest())
    cache=dest.with_suffix('.inputs.json')
    if dest.exists():
        if cache.exists() and json.loads(cache.read_text(encoding='utf-8'))==signature:return dest
        raise ValueError('Cached cut differs; preserve the old revision before rerendering')
    inputs=['ffmpeg','-v','warning','-nostdin','-y']
    is_image=source.suffix.lower() in ('.png','.jpg','.jpeg','.webp')
    if is_image:inputs+=['-loop','1','-framerate','24']
    elif shot.get('start'):inputs+=['-ss',str(shot['start'])]
    inputs+=['-i',str(source)]
    if shot.get('fullframe'):
        filters='scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0xf3f1eb,setsar=1,fps=24,format=yuv420p'
        if not is_image and not shot.get('composed'):
            raise ValueError('Full-frame source videos require a reviewed composed plate')
    else:
        note=shot.get('note','内容を確認しながら進める')
        panel=OUT/'graphics'/f'{n:02d}-plate-{index:02d}.png'
        plate(n,chapter['title'],note).save(panel)
        inputs+=['-i',str(panel)]
        speed=shot.get('speed',1)
        crop=shot.get('crop')
        crop_filter=f'crop={crop[2]}:{crop[3]}:{crop[0]}:{crop[1]},' if crop else ''
        processing=f'setpts=(PTS-STARTPTS)/{speed},{crop_filter}scale=1280:650:force_original_aspect_ratio=decrease,pad=1280:650:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1,fps=24'
        filters=f'[0:v]{processing}[screen];[1:v][screen]overlay=70:200,format=yuv420p'
        # Real footage is never secretly repeated or frozen. Explicit still cuts
        # are labeled in their prepared plate, and time compression is disclosed.
        if not is_image:
            probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-of','json',str(source)],text=True))
            available=(float(probe['format']['duration'])-shot.get('start',0))/speed
            if available+.08<duration:raise ValueError('Footage too short; add an explicit still or another cut')
    command=inputs+['-filter_complex',filters,'-an','-t',str(duration),'-r','24','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-threads','4',str(dest)]
    run(command,dest.with_suffix('.log'))
    save(cache,signature)
    print('Rendered',dest.name,duration,flush=True)
    return dest


def render():
    if (OUT/'dots-transfer-detail-v01.mp4').exists():
        raise ValueError('Preserve the completed draft before rendering a revised one')
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    visuals=json.loads((OUT/'visuals.json').read_text(encoding='utf-8'))
    files=[]
    for chapter in plan['chapters']:
        shots=visuals[chapter['id']]
        if abs(sum(s['seconds'] for s in shots)-(chapter['end']-chapter['start']))>.04:
            raise ValueError('Shot durations do not match spoken chapter: '+chapter['id'])
        files += [render_shot(s,chapter,i) for i,s in enumerate(shots)]
    listing=OUT/'concat.txt'
    listing.write_text('\n'.join("file '"+p.as_posix()+"'" for p in files),encoding='utf-8')
    run(['ffmpeg','-v','warning','-nostdin','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(OUT/'picture-master.mp4')],OUT/'concat.log')
    # A first pass measures the actual voice+BGM mix; no assumed loudness number.
    measured=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(OUT/'audio/mix-premaster.wav'),'-af','loudnorm=I=-16:TP=-1.2:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
    measurement=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0]
    save(OUT/'audio/loudness-pass1.json',measurement)
    af=f'loudnorm=I=-16:TP=-1.2:LRA=9:measured_I={measurement["input_i"]}:measured_TP={measurement["input_tp"]}:measured_LRA={measurement["input_lra"]}:measured_thresh={measurement["input_thresh"]}:offset={measurement["target_offset"]}:linear=true:print_format=json'
    vf="ass=captions.ass:fontsdir=fonts"
    dest=OUT/'dots-transfer-detail-v01.mp4'
    with (OUT/'final-render.log').open('w',encoding='utf-8') as stream:
        subprocess.run(['ffmpeg','-v','info','-nostdin','-y','-i','picture-master.mp4','-i','audio/mix-premaster.wav','-vf',vf,
            '-af',af,'-map','0:v','-map','1:a','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-b:a','192k','-ar','48000',
            '-ac','2','-pix_fmt','yuv420p','-movflags','+faststart','-threads','6','dots-transfer-detail-v01.mp4'],cwd=OUT,stdout=stream,stderr=subprocess.STDOUT,check=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print(dest,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','render']);args=parser.parse_args()
    (prepare if args.command=='prepare' else render)()
