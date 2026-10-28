"""Versioned conversation opening and policy-based talking presenter cutaways."""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,json,math,shutil,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OLD=ROOT/'outputs/productions'/HERE.name/'v01';OUT=OLD.parent/'v02'
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_avatar import SpriteAtlas,PairAtlas,DialogueDriver,validate_windows
from tools.studio.longform_audio import plan_dialogue,assemble_audio
from graphics import font,base,INK,BG,LIME,WHITE
from render import ass_time,caption_phrases,subtitle_text
FPS=24


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def fingerprint(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def emotion(turn,chapter):
    text=turn['text']
    if chapter=='chapter-11':return 'pleased'
    if any(x in text for x in ['保証','止ま','不明','権限']):return 'serious'
    if any(x in text for x in ['安心','違う値','重複']):return 'worried'
    if any(x in text for x in ['一致','なるほど']):return 'pleased'
    if '？' in text or '?' in text:return 'curious'
    return 'neutral' if turn['speaker']=='male' else 'serious'


def prepare():
    config=json.loads((HERE/'revision-v02.json').read_text(encoding='utf-8'))
    validate_windows(config['windows_in_original_main_seconds'],280,
        protected=[(25,63),(72,110),(120,149),(155,223),(227,245),(263,270)])
    # Recheck all reused PCM bytes, not just filenames or previous success labels.
    for proofpath in sorted((OLD/'voice').glob('chapter-*/turn-*/verified.json')):
        proof=json.loads(proofpath.read_text(encoding='utf-8'))
        for record in proof['files']:
            if fingerprint(ROOT/record['path']).upper()!=record['sha256'].upper():raise ValueError('Reused voice changed')
    intro=plan_dialogue([dict(id='opening',title='いつもの入力、どうする？',target_seconds=0,
        turns=config['opening_turns'],tail_seconds=.5)],OUT/'voice')
    arrival=124/FPS
    prefix=arrival+intro['seconds']
    chapters=deepcopy(intro['chapters'])
    for chapter in chapters:
        chapter['start']+=arrival;chapter['end']+=arrival
        for turn in chapter['turns']:turn['start']+=arrival;turn['end']+=arrival
    original=json.loads((OLD/'timeline.json').read_text(encoding='utf-8'))
    for chapter in deepcopy(original['chapters']):
        chapter['start']+=prefix;chapter['end']+=prefix
        for turn in chapter['turns']:
            turn['start']+=prefix;turn['end']+=prefix;turn['emotion']=emotion(turn,chapter['id'])
        chapters.append(chapter)
    plan=dict(fps=FPS,seconds=prefix+original['seconds'],frames=round((prefix+original['seconds'])*FPS),
        arrival_seconds=arrival,conversation_seconds=intro['seconds'],main_offset=prefix,chapters=chapters)
    save(OUT/'timeline.json',plan)
    save(OUT/'audio/verification.json',assemble_audio(plan,OUT/'audio'))
    old_header=(OLD/'captions.ass').read_text(encoding='utf-8').split('[Events]')[0]
    lines=[old_header+'[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    srt=[];idx=1
    for chapter in chapters:
        for turn in chapter['turns']:
            pieces=caption_phrases(turn['text']);cursor=turn['start'];total=sum(map(len,pieces))
            for text in pieces:
                end=cursor+(turn['end']-turn['start'])*len(text)/total
                lines.append(f'Dialogue: 0,{ass_time(cursor)},{ass_time(end)},{turn["speaker"].title()},,0,0,0,,{subtitle_text(text)}')
                # ass_time starts with a single-hour digit; pad hours, not fraction.
                def stamp(t):
                    value=ass_time(t).replace('.',',')+'0'
                    return value if len(value.split(':')[0])==2 else '0'+value
                srt.append(f'{idx}\n{stamp(cursor)} --> {stamp(end)}\n{text}\n')
                idx+=1;cursor=end
    (OUT/'captions.ass').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (OUT/'captions.srt').write_text('\n'.join(srt),encoding='utf-8')
    (OUT/'fonts').mkdir(exist_ok=True);shutil.copy2(OLD/'fonts/meiryob.ttc',OUT/'fonts/meiryob.ttc')
    save(OUT/'pip-policy-audit.json',dict(protected_operations_covered=0,male='left',female='right',
        windows=config['windows_in_original_main_seconds'],layout='dedicated takeaways; reserved avatar sides and caption band',
        mouth='Audio-envelope-driven simple mouth movement; not phoneme-accurate lip sync',
        listener_mouth='closed',unchanged_main_voice_turns=40,new_opening_voice_turns=3))
    driver=DialogueDriver([t for c in chapters for t in c['turns']])
    save(OUT/'audio/mouth-gates.json',driver.gates)
    save(OUT/'source-manifest.json',dict(accepted_opening=dict(path=config['opening_clip'],sha256=fingerprint(ROOT/config['opening_clip'])),
        reused_picture=dict(path=str((OLD/'picture-master.mp4').relative_to(ROOT)),sha256=fingerprint(OLD/'picture-master.mp4')),
        sprites=[dict(path=str(p.relative_to(ROOT)),sha256=fingerprint(p)) for p in sorted((OUT/'avatars').glob('*atlas.png'))],
        old_video_preserved=dict(path=str((OLD/'dots-transfer-detail-v01.mp4').relative_to(ROOT)),sha256=fingerprint(OLD/'dots-transfer-detail-v01.mp4'))))
    print('Prepared',plan['seconds'],'seconds; main offset',prefix,'43 voice turns: 3 new and 40 reused',flush=True)


def cached_video(dest,signature,callback):
    proof=dest.with_suffix('.inputs.json')
    signature=dict(signature,renderer_sha256=fingerprint(__file__),avatar_code_sha256=fingerprint(ROOT/'tools/studio/dialogue_avatar.py'))
    if dest.exists():
        if proof.exists() and json.loads(proof.read_text(encoding='utf-8'))==signature:return
        raise ValueError('Preserve changed cached render: '+dest.name)
    callback();save(proof,signature)


def pipe_video(dest,seconds,frame_factory):
    count=round(seconds*FPS)
    with dest.with_suffix('.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen(['ffmpeg','-v','warning','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24',
            '-s','1920x1080','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18',
            '-pix_fmt','yuv420p','-threads','4',str(dest)],stdin=subprocess.PIPE,stderr=log,stdout=log)
        try:
            for i in range(count):proc.stdin.write(frame_factory(i/FPS).convert('RGB').tobytes())
            proc.stdin.close()
            if proc.wait()!=0:raise RuntimeError('Video encoder failed: '+str(log.name))
        except BaseException:
            proc.kill();proc.wait();raise


def centered(draw,y,text,size=56,fill=INK):
    draw.text(((1920-draw.textlength(text,font=font(size)))/2,y),text,font=font(size),fill=fill)


def takeaway(window,chapter):
    image=base(int(chapter['id'][-2:]),chapter['title']);draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((340,240,1580,835),radius=28,fill=WHITE)
    centered(draw,280,window['title'],52)
    centered(draw,425,window['lines'][0],54)
    draw.rounded_rectangle((420,540,1500,550),radius=5,fill=LIME)
    centered(draw,620,window['lines'][1],46)
    return image


def avatar_card(canvas,atlas,speaker,state,fallback,seconds):
    x=24 if speaker=='male' else 1608;y=425;size=288
    mood=state['emotion'] or fallback
    image=atlas.frame(mood,state['opened'],size)
    breath=round(math.sin(seconds*2.1+(0 if speaker=='male' else 1.7))*1.2)
    draw=ImageDraw.Draw(canvas)
    draw.rounded_rectangle((x-5,y-5,x+size+5,y+size+105),radius=21,fill='#101b34',
        outline=LIME if state['speaking'] else '#7f9799',width=4 if state['speaking'] else 2)
    canvas.paste(image,(x,y+breath))
    draw.text((x+25,y+size+14),'進行・質問' if speaker=='male' else '実務・解説',font=font(36),fill=WHITE)
    if state['speaking']:
        for k in range(3):
            height=8+(k+int(seconds*9))%3*5
            draw.rounded_rectangle((x+111+k*22,y+size+79-height,x+121+k*22,y+size+79),radius=3,fill=LIME)


def render(*, config_path=None, output_name='dots-transfer-detail-v02.mp4', picture_source=None, replace_interlude=True):
    if Path(output_name).name!=output_name or not output_name.endswith('.mp4'):raise ValueError('Expected MP4 filename')
    if (OUT/output_name).exists():raise ValueError('Preserve completed output before revision')
    config=json.loads(Path(config_path or HERE/'revision-v02.json').read_text(encoding='utf-8'))
    plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    driver=DialogueDriver([t for c in plan['chapters'] for t in c['turns']])
    pair=PairAtlas(OUT/'avatars/intro-atlas.png')
    sprites={s:SpriteAtlas(OUT/'avatars'/f'{s}-atlas.png',s) for s in ('male','female')}
    save(OUT/'avatars/registration.json',dict(pair=pair.registration,**{s:v.registration for s,v in sprites.items()}))
    folder=OUT/'segments';folder.mkdir(exist_ok=True)
    main_source=Path(picture_source or OLD/'picture-master.mp4')
    signature=dict(timeline=fingerprint(OUT/'timeline.json'),policy=fingerprint(config_path or HERE/'revision-v02.json'),
        source_manifest=fingerprint(OUT/'source-manifest.json'),picture_source=fingerprint(main_source))
    segments=[]
    def command(dest,args):
        with dest.with_suffix('.log').open('w',encoding='utf-8') as log:
            subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    arrival=folder/'00-arrival.mp4'
    cached_video(arrival,dict(signature,kind='arrival'),lambda:command(arrival,['ffmpeg','-v','warning','-nostdin','-n',
        '-i',str(ROOT/config['opening_clip']),'-an','-vf','scale=1920:1080,setsar=1',
        '-c:v','libx264','-crf','18','-preset','veryfast','-r','24','-threads','4',str(arrival)]))
    segments.append(arrival)
    convo=folder/'01-conversation.mp4'
    def dialogue_frame(local):
        time=local+plan['arrival_seconds'];opened=None
        for speaker in ('male','female'):
            if driver.state(time,speaker)['opened']:opened=speaker
        image=pair.frame(opened).resize((1920,1080),Image.Resampling.LANCZOS)
        # A very small camera push maintains a natural approach to the conversation.
        scale=1+min(local/plan['conversation_seconds'],1)*.012
        w,h=round(1920/scale),round(1080/scale)
        return image.crop(((1920-w)//2,(1080-h)//2,(1920+w)//2,(1080+h)//2)).resize((1920,1080),Image.Resampling.LANCZOS)
    cached_video(convo,dict(signature,kind='conversation'),lambda:pipe_video(convo,plan['conversation_seconds'],dialogue_frame))
    segments.append(convo)
    windows=config.get('windows_in_main_seconds',config.get('windows_in_original_main_seconds',[]))
    overrides=([dict(start=8,end=13,kind='replace_old_character_interlude')] if replace_interlude else [])+windows
    cursor=0;sequence=2
    def normal(a,b):
        nonlocal sequence
        if b<=a:return
        dest=folder/f'{sequence:02d}-main-{a:.0f}-{b:.0f}.mp4';sequence+=1
        cached_video(dest,dict(signature,kind='original',start=a,end=b),lambda:command(dest,['ffmpeg','-v','warning','-nostdin','-n',
            '-ss',str(a),'-i',str(main_source),'-t',str(b-a),'-an','-r','24',
            '-c:v','libx264','-crf','18','-preset','veryfast','-threads','4',str(dest)]))
        segments.append(dest)
    for window in overrides:
        a,b=window['start'],window['end'];normal(cursor,a)
        dest=folder/f'{sequence:02d}-takeaway-{a:.0f}-{b:.0f}.mp4';sequence+=1
        if window['kind']=='replace_old_character_interlude':
            background=Image.open(OLD/'graphics/01-flow-2.png').convert('RGB')
            callback=lambda dest=dest,background=background,a=a,b=b:pipe_video(dest,b-a,lambda _:background)
        else:
            chapter=next(c for c in plan['chapters'][1:] if c['start']-plan['main_offset']-1e-6<=a<c['end']-plan['main_offset']-1e-6)
            background=takeaway(window,chapter)
            def make_frame(local,window=window,background=background,a=a):
                image=background.copy();time=plan['main_offset']+a+local
                for speaker in ('male','female'):
                    avatar_card(image,sprites[speaker],speaker,driver.state(time,speaker),window[speaker],time)
                return image
            callback=lambda dest=dest,a=a,b=b,make_frame=make_frame:pipe_video(dest,b-a,make_frame)
        cached_video(dest,dict(signature,kind=window),callback)
        print('Rendered',dest.name,flush=True);segments.append(dest);cursor=b
    normal(cursor,plan['seconds']-plan['main_offset'])
    listing=OUT/'concat.txt';listing.write_text('\n'.join("file '"+p.as_posix()+"'" for p in segments),encoding='utf-8')
    command(OUT/'picture-master.mp4',['ffmpeg','-v','warning','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(OUT/'picture-master.mp4')])
    stderr=subprocess.run(['ffmpeg','-hide_banner','-nostdin','-i',str(OUT/'audio/mix-premaster.wav'),'-af',
        'loudnorm=I=-16:TP=-1.2:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True).stderr
    measurement=json.JSONDecoder().raw_decode(stderr[stderr.rfind('{'):])[0];save(OUT/'audio/loudness-pass1.json',measurement)
    af=f'loudnorm=I=-16:TP=-1.2:LRA=9:measured_I={measurement["input_i"]}:measured_TP={measurement["input_tp"]}:measured_LRA={measurement["input_lra"]}:measured_thresh={measurement["input_thresh"]}:offset={measurement["target_offset"]}:linear=true'
    dest=OUT/output_name
    with (OUT/'final-render.log').open('w',encoding='utf-8') as log:
        subprocess.run(['ffmpeg','-v','info','-nostdin','-n','-i','picture-master.mp4','-i','audio/mix-premaster.wav',
            '-vf','ass=captions.ass:fontsdir=fonts','-af',af,'-map','0:v','-map','1:a','-c:v','libx264','-preset','fast',
            '-crf','18','-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-pix_fmt','yuv420p','-movflags','+faststart',
            '-threads','6',dest.name],cwd=OUT,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print(dest,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['prepare','render']);args=parser.parse_args()
    (prepare if args.command=='prepare' else render)()
