"""One accepted portrait short: quoted evidence, a bounded analysis, and dialogue."""
from pathlib import Path
from functools import lru_cache
import argparse,hashlib,json,math,subprocess,sys
import numpy as np
from PIL import Image,ImageDraw,ImageOps
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.explainer_canvas import Canvas,box,fit,arrow
from tools.studio.editorial_captions import timed_captions,phrase_lines,PROTECTED
from tools.studio.editorial_presenters import equalized_face
from tools.studio.dialogue_avatar import SpriteAtlas,voice_gate
from tools.studio.longform_audio import SR,read_voice,write_pcm
from tools.studio.music_mix import DEFAULT_BGM_PROFILE,default_bgm_bed
from tools.studio.audio_motifs import sunny_loop
from workspace_record import cli
OUT=ROOT/'outputs/content-projects'/HERE.name;ASSETS=OUT/'assets';DEST=OUT/'release/v01/short';FPS=24
NAVY='#10283D';TEAL='#087E82';GOLD='#D3A447';PAPER='#F7F5F0';MUTED='#BDD0D8'
PROTECT=PROTECTED+('Claude Code','Anthropic','Thariq Shihipar','Anthony Morris','Cat Wu','Thariq','Anthony')
PEOPLE=[dict(id='thariq',name='Thariq Shihipar',date='10/24',role='Claude Codeの開発'),dict(id='anthony',name='Anthony Morris',date='10/24',role='デスクトップ版を開発'),dict(id='cat',name='Cat Wu',date='11/4',role='Claude Codeの製品責任者')]
VISUALS=['hook','question','evidence','impact-question','analysis','closing']

def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args):return subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def smooth(x):x=max(0,min(1,x));return x*x*(3-2*x)
def accepted():
    p=cli('get',project_id=HERE.name)['project']
    if not p['accepted_proposal'] or p['accepted_proposal']['proposal_id']!='proposal-v01':raise RuntimeError('Outline acceptance required')

def motion_cache():
    manifest=[]
    for name in ['male-thinking','female-thinking']:
        p=ASSETS/(name+'.mp4');cache=OUT/'motion-cache'/name
        if (cache/'complete.json').exists():
            receipt=json.loads((cache/'complete.json').read_text(encoding='utf-8'));assert receipt['sha256']==sha(p)
        else:
            cache.mkdir(parents=True,exist_ok=True)
            run(['ffmpeg','-v','error','-nostdin','-n','-i',str(p),'-vf',"fps=24,scale=w='min(700,iw)':h=-2",'-q:v','2',str(cache/'%04d.jpg')])
            receipt=dict(sha256=sha(p),frames=len(list(cache.glob('*.jpg'))));save(cache/'complete.json',receipt)
        manifest.append(dict(name=name,path=p.relative_to(ROOT).as_posix(),**receipt,crop_normalized=[.20,.28,.82,.64],fit_centering=[.12 if name.startswith('male-') else .5,.45],use='Reaction footage played once, then held; no phoneme lip-sync claim.'))
    save(OUT/'motion-provenance-v01.json',manifest)

def plan():
    accepted();DEST.mkdir(parents=True,exist_ok=True)
    script=HERE/'short-dialogue-v01.json';turns=[];cursor=0
    for t,visual in zip(json.loads(script.read_text(encoding='utf-8'))['turns'],VISUALS,strict=True):
        p=OUT/'voice/v01'/t['id']/'voice.wav';proof=json.loads(p.with_name('verified.json').read_text(encoding='utf-8'))
        assert sha(p).upper()==next(x['sha256'] for x in proof['files'] if x['path'].endswith('voice.wav'))
        seconds=len(read_voice(p))/SR;lead=.15;tail=.30 if t['speaker']=='male' else .5
        if visual=='closing':tail=1.25
        if visual=='evidence':tail=.7
        frames=math.ceil((lead+seconds+tail)*FPS);end=cursor+frames/FPS
        row=dict(t,visual=visual,start=cursor,end=end,frames=frames,voice_start=cursor+lead,voice_seconds=seconds,voice_path=p.relative_to(ROOT).as_posix())
        row['subtitles']=timed_captions(t['display'],row['voice_start'],seconds,930,56,protected=PROTECT)
        if visual=='evidence':
            # Initial boundaries are reading-length estimates; AV inspection may refine them.
            parts=['開発に携わったタリクさんと、','デスクトップ版を作ったアンソニーさん。','さらに、製品責任者のキャット・ウーさんも、退社を発表した。']
            lengths=[len(x) for x in parts];boundaries=np.cumsum([0]+lengths)/sum(lengths)*seconds
            row['evidence_boundaries']=[float(x)+lead for x in boundaries]
            row['evidence_alignment']='Reading-length estimate, subject to actual audio inspection.'
            override=HERE/'timing-overrides-v01.json'
            if override.is_file():
                offsets=json.loads(override.read_text(encoding='utf-8'))['s03_person_topic_seconds']
                assert offsets[0]==0 and all(a<b for a,b in zip(offsets,offsets[1:])) and offsets[-1]<seconds
                boundaries=np.array(offsets+[seconds]);row['evidence_boundaries']=[float(x)+lead for x in boundaries]
                row['evidence_alignment']='AI-assisted listening of actual PCM: topic clauses at 0.0, 2.7, 4.9 seconds. Approximate, not phoneme alignment.'
            clauses=['開発に携わったThariqさんと、','デスクトップ版を作ったAnthonyさん。','さらに、製品責任者のCat Wuさんも、退社を発表した。']
            row['subtitles']=[]
            for clause,a,b in zip(clauses,boundaries[:-1],boundaries[1:],strict=True):
                row['subtitles']+=timed_captions(clause,cursor+lead+float(a),float(b-a),930,56,protected=PROTECT)
        turns.append(row);cursor=end
    result=dict(video_id='anthropic-departures-short',revision='v01',width=1080,height=1920,fps=FPS,seconds=cursor,frames=round(cursor*FPS),turns=turns,source_script_sha256=sha(script),acceptance='adoption-v01.json')
    for t in turns:assert ''.join(s['text'].replace('\n','') for s in t['subtitles'])==t['display']
    save(DEST/'timeline.json',result)
    def stamp(value):
        ms=round(value*1000);h,ms=divmod(ms,3600000);m,ms=divmod(ms,60000);s,ms=divmod(ms,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'
    captions=[c for t in turns for c in t['subtitles']]
    (DEST/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}" for i,s in enumerate(captions))+'\n',encoding='utf-8')
    print(json.dumps(dict(seconds=cursor,captions=len(captions))),flush=True);return result

class Renderer:
    def __init__(self):
        self.c=Canvas();self.gates={};self.images={p.stem:Image.open(p).convert('RGB') for p in ASSETS.glob('*.png') if 'atlas' not in p.stem}
        self.atlas={s:SpriteAtlas(ASSETS/(s+'-atlas.png'),s) for s in ['male','female']}
        self.motions={s:sorted((OUT/'motion-cache'/(s+'-thinking')).glob('*.jpg')) for s in ['male','female']}
    def text(self,im,v,r,size=54,color='white',center=True):self.c.text(im,v,r,size,color,center)
    def wrap(self,value,width=950,size=54):return '\n'.join(phrase_lines(value,width,size,protected=PROTECT))
    @lru_cache(maxsize=30)
    def base(self,label,title,warm=False):
        im=Image.new('RGB',(1080,1920),PAPER if warm else NAVY);box(im,(45,45,1035,116),GOLD if label=='考察' else TEAL,18)
        self.text(im,label,(60,51,1020,108),38,NAVY if label=='考察' else 'white')
        self.text(im,self.wrap(title),(60,165,1020,330),54,NAVY if warm else 'white');return im
    @lru_cache(maxsize=280)
    def motion_tile(self,who,index,width,height):
        source=Image.open(self.motions[who][index]).convert('RGB');w,h=source.size
        source=source.crop((round(w*.20),round(h*.28),round(w*.82),round(h*.64)))
        return ImageOps.fit(source,(width,height),method=Image.Resampling.LANCZOS,centering=(.12 if who=='male' else .5,.45))
    def motion(self,im,who,local,rect):
        index=min(len(self.motions[who])-1,max(0,int(local*FPS)))
        im.paste(self.motion_tile(who,index,rect[2]-rect[0],rect[3]-rect[1]),rect[:2])
    @lru_cache(maxsize=40)
    def face(self,who,mood,opened,size):return equalized_face(self.atlas[who],who,mood,opened,size)
    def pair(self,im,t,local):
        for who,x in [('male',65),('female',615)]:
            active=who==t['speaker'];opened=False
            if active:
                if t['id'] not in self.gates:self.gates[t['id']]=voice_gate(ROOT/t['voice_path'],FPS)['gates']
                idx=math.floor((t['start']+local-t['voice_start'])*FPS);g=self.gates[t['id']];opened=g[idx] if 0<=idx<len(g) else False
            mood='curious' if active else 'serious';box(im,(x-7,613,x+407,1027),TEAL if active else '#496275',22)
            im.paste(self.face(who,mood,opened,400),(x,620))
    def source(self,im,text,warm=False):self.text(im,text,(60,1760,1020,1845),28,'#4F6975' if warm else MUTED,False)
    def caption(self,im,t,local):
        now=t['start']+local
        page=next((s['text'] for s in t['subtitles'] if s['start']<=now<s['end']),None)
        if page is None and t['voice_start']+t['voice_seconds']<=now<t['voice_start']+t['voice_seconds']+.18:page=t['subtitles'][-1]['text']
        if page:
            box(im,(35,1470,1045,1700),'#081B2A',20);self.text(im,page,(70,1485,1010,1680),56)
    def frame(self,t,local,total=None):
        visual=t['visual']
        if visual=='hook':
            im=self.base('Claude Code｜退社発表','キーマン3人が退社').copy();self.text(im,'改善を続けられるか？',(60,350,1020,435),56,GOLD)
            self.motion(im,'male',local,(45,505,465,1230))
            for i,p in enumerate(PEOPLE):
                y=510+i*245;shift=-round(25*(1-smooth((local-i*.17)/.5)))
                if local<i*.17:continue
                box(im,(505+shift,y,1030+shift,y+210),'#1D4156',18)
                self.text(im,p['name'],(515+shift,y+15,1020+shift,y+85),36)
                self.text(im,p['date']+' 発表（JST）',(515+shift,y+104,1020+shift,y+167),36,GOLD)
            self.source(im,'出典：各氏の本人投稿。2026年11月4日確認。')
        elif visual in ['question','impact-question']:
            im=self.base('視聴者の疑問','どんな人たちが離れた？' if visual=='question' else '開発への影響は？').copy()
            self.pair(im,t,local);self.text(im,'本人発表と考察を分けて見る',(60,1150,1020,1230),44,MUTED)
        elif visual=='evidence':
            bounds=t['evidence_boundaries'];person=max(0,min(2,sum(local>=b for b in bounds[1:-1])))
            p=PEOPLE[person];im=self.base('本人の発表',p['name'],True).copy()
            self.text(im,p['date']+' 発表（日本時間）',(70,355,1010,435),48,TEAL)
            self.text(im,self.wrap(p['role'],950,48),(65,495,1015,665),48,NAVY)
            box(im,(45,750,1035,1120),'#000000',18);fit(im,self.images[p['id']+'-quote'],(65,770,1015,1090))
            self.text(im,'退社を発表',(90,1190,990,1290),60,TEAL)
            self.source(im,'引用：'+p['name']+' 本人のX投稿\n発表日と最終勤務日は別。2026年11月4日確認。',True)
        elif visual=='analysis':
            im=self.base('考察','使いやすさを作る知見を、引き継げるか').copy()
            fit(im,self.images['official-role'],(55,360,1025,650));box(im,(65,740,1015,1310),PAPER,24)
            self.text(im,'モデル ＋ 製品の仕組み',(90,765,990,850),48,TEAL)
            phase=max(0,min(2,int(max(0,local-.8)/max(.1,t['voice_seconds']-.8)*3)))
            for i,value in enumerate(['コードの修正を頼む','変更を確かめる','必要な所を直す']):
                y=890+i*132;box(im,(130,y,950,y+90),'#F1DFAF' if i==phase else '#DCE9EC',16)
                self.text(im,value,(150,y+12,930,y+78),46,NAVY)
                if i<2:arrow(im,[(540,y+92),(540,y+128)],TEAL,6)
            self.source(im,'引用：Claude公式 Cat Wu氏のPM記事（2026年3月）\n退社の影響を実測した図ではない。')
        else:
            im=self.base('今後、見るところ','機能改善・使い勝手・安定性').copy();self.motion(im,'female',local,(45,440,495,1220))
            for i,value in enumerate(['機能が改善されるか','操作で迷わないか','安心して使えるか']):
                y=510+i*225;box(im,(535,y,1035,y+170),'#285167' if local>t['voice_seconds']*.55+i*.55 else '#1D4156',18)
                self.text(im,value,(550,y+35,1020,y+135),40)
            self.text(im,self.wrap('共通原因・開発への影響は未確認',950,48),(60,1280,1020,1430),48,GOLD)
            self.source(im,'考察は今後の観察点。将来の品質を断定しない。')
        self.caption(im,t,local)
        # A modest global progress track; it is not a performance or attrition chart.
        if total:
            d=ImageDraw.Draw(im);d.rectangle((45,1870,1035,1876),fill='#325468');d.rectangle((45,1870,45+round(990*(t['start']+local)/total),1876),fill=TEAL if visual=='evidence' else GOLD)
        return im

def preview():
    p=json.loads((DEST/'timeline.json').read_text(encoding='utf-8'));r=Renderer();dest=DEST/'layout';dest.mkdir(parents=True,exist_ok=True);tiles=[];count=0
    for t in p['turns']:
        for i,s in enumerate(t['subtitles']):
            local=(s['start']+s['end'])/2-t['start'];r.frame(t,local,p['seconds']).save(dest/f"{t['id']}-caption-{i:02}.jpg",quality=92);count+=1
        points=[.04,.5,.95]
        if t['visual']=='evidence':points=[(a+b)/2/(t['end']-t['start']) for a,b in zip(t['evidence_boundaries'],t['evidence_boundaries'][1:])]
        for i,frac in enumerate(points):
            im=r.frame(t,(t['end']-t['start'])*frac,p['seconds']);im.save(dest/f"{t['id']}-visual-{i}.jpg",quality=92)
            if i==1 or t['visual']=='evidence':tiles.append(im.resize((270,480),Image.Resampling.LANCZOS))
    sheet=Image.new('RGB',(1080,480*math.ceil(len(tiles)/4)),NAVY)
    for i,tile in enumerate(tiles):sheet.paste(tile,(270*(i%4),480*(i//4)))
    sheet.save(dest/'contact-sheet.jpg',quality=94);save(DEST/'text-layout-audit.json',list(r.c.audit.values()))
    print(json.dumps(dict(caption_states=count,text_boxes=len(r.c.audit),representative_images=len(tiles))),flush=True)

def audio_mix(p):
    n=round(p['seconds']*SR);voice=np.zeros(n,np.float32);records=[]
    for t in p['turns']:
        samples=read_voice(ROOT/t['voice_path']);active=samples[np.abs(samples)>.018];rms=float(np.sqrt(np.mean(active**2))) if len(active) else .12
        gain=max(.7,min(1.6,.12/max(rms,.001)));gain=min(gain,.88/max(float(np.abs(samples).max()),.001))
        a=round(t['voice_start']*SR);voice[a:a+len(samples)]+=samples*gain
        records.append(dict(id=t['id'],speaker=t['speaker'],active_rms=rms,derived_gain=gain,original_sha256=sha(ROOT/t['voice_path'])))
    loop,meta=sunny_loop(sample_rate=SR);music=np.tile(loop,(math.ceil(n/len(loop)),1))[:n]
    music=default_bgm_bed(music,p['seconds'],[(t['voice_start'],t['voice_start']+t['voice_seconds']) for t in p['turns']],sample_rate=SR)
    mixed=voice[:,None]+music;peak=float(np.abs(mixed).max());mixed*=min(1,.94/max(peak,.001))
    write_pcm(DEST/'narration.wav',voice);write_pcm(DEST/'music-loop.wav',loop);write_pcm(DEST/'music-mixed.wav',music);write_pcm(DEST/'mix.wav',mixed)
    save(DEST/'audio-plan.json',dict(bgm=dict(DEFAULT_BGM_PROFILE),loop=meta,voices=records,effects=[],note='Bounded gain on derived mix only. Original voice unchanged; no celebratory cues for departures.'))
    meter_text=run(['ffmpeg','-hide_banner','-nostdin','-i',str(DEST/'mix.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-']).stderr
    meter=json.JSONDecoder().raw_decode(meter_text[meter_text.rfind('{'):])[0];save(DEST/'mix-meter.json',meter)
    return 'loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+meter['input_i']+':measured_TP='+meter['input_tp']+':measured_LRA='+meter['input_lra']+':measured_thresh='+meter['input_thresh']+':offset='+meter['target_offset']+':linear=true'

def render():
    accepted();p=json.loads((DEST/'timeline.json').read_text(encoding='utf-8'));target=DEST/'anthropic-departures-short-v01.mp4';r=Renderer();parts=[]
    if target.exists():
        qc=json.loads((DEST/'qc.json').read_text(encoding='utf-8'));assert qc['sha256']==sha(target);print('Existing verified release retained',flush=True);return
    code_hash=sha(Path(__file__));plan_hash=sha(DEST/'timeline.json')
    for t in p['turns']:
        path=DEST/'segments'/(t['id']+'.mp4');path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            proof=json.loads(path.with_suffix('.json').read_text(encoding='utf-8'));assert proof['code_sha256']==code_hash and proof['plan_sha256']==plan_hash and proof['sha256']==sha(path)
        else:
            proc=subprocess.Popen(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pix_fmt','rgb24','-s','1080x1920','-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','19','-pix_fmt','yuv420p','-threads','4',str(path)],stdin=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                for i in range(t['frames']):proc.stdin.write(r.frame(t,i/FPS,p['seconds']).tobytes())
                proc.stdin.close();error=proc.stderr.read();code=proc.wait()
                if code:raise RuntimeError(error.decode(errors='replace'))
            except BaseException:
                proc.kill();proc.wait()
                if path.exists():path.rename(path.with_suffix('.failed.mp4'))
                raise
            save(path.with_suffix('.json'),dict(sha256=sha(path),code_sha256=code_hash,plan_sha256=plan_hash,frames=t['frames']))
        parts.append(path);print(t['id'],'rendered',flush=True)
    listing=DEST/'concat.txt';listing.write_text('\n'.join("file '"+x.as_posix()+"'" for x in parts),encoding='utf-8');normalizer=audio_mix(p);temp=target.with_name(target.stem+'-assembling.mp4')
    run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-i',str(DEST/'mix.wav'),'-map','0:v','-map','1:a','-c:v','copy','-af',normalizer,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(p['seconds']),'-movflags','+faststart',str(temp)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(temp),'-f','null','-'])
    probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(temp)]).stdout);video=next(x for x in probe['streams'] if x['codec_type']=='video')
    assert int(video['nb_frames'])==p['frames'] and abs(float(probe['format']['duration'])-p['seconds'])<.1
    measured=run(['ffmpeg','-hide_banner','-nostdin','-i',str(temp),'-af','loudnorm=print_format=json','-f','null','-']).stderr;meter=json.JSONDecoder().raw_decode(measured[measured.rfind('{'):])[0]
    assert -18<float(meter['input_i'])<-14 and float(meter['input_tp'])<=-1,meter
    temp.rename(target);save(DEST/'qc.json',dict(status='technical_candidate_human_review_pending',sha256=sha(target),bytes=target.stat().st_size,seconds=p['seconds'],frames=p['frames'],probe=probe,final_aac_loudness=meter,full_decode=True,full_caption_layout=bool((DEST/'text-layout-audit.json').exists()),user_approved=False,published=False))
    print(json.dumps(dict(ready=target.name,seconds=p['seconds'],bytes=target.stat().st_size,LUFS=meter['input_i'],true_peak=meter['input_tp'])),flush=True)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['motion','plan','preview','render']);args=parser.parse_args()
    if args.action=='motion':motion_cache()
    elif args.action=='plan':plan()
    elif args.action=='preview':preview()
    else:render()
