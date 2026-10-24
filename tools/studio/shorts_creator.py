"""Reusable local editorial Shorts pipeline: measured speech -> scenes -> render -> QC.

Run: python -m tools.studio.shorts_creator make --story productions/.../creator-story.json
No API, public upload, arbitrary shell/filter, or generated-tool credit is added.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import wave
import zipfile
import struct
from urllib.parse import urlsplit

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
FPS = 24
KINDS = {'hero', 'quote', 'steps', 'cards', 'checklist', 'compare', 'diagram', 'stat', 'editorial', 'source'}
EDITORIAL_LAYOUTS = {'hook', 'parallel', 'conversation', 'closing', 'memory', 'channels', 'calendar', 'research', 'permissions', 'contrast', 'statement', 'recap'}
FEATURE_GRAPHICS = {'release','cloud','apps','parallel','memory','chat','schedule','research','control','laptop','web-services','web-flow'}
MUSIC_PRESETS = {'electro_pop_v1', 'bright_groove_v1'}
DEMONSTRATION_PRODUCTS = {'Claude', 'Codex', 'ChatGPT'}
DEMONSTRATION_PHASES = {'before', 'first-output', 'revision', 'after', 'export'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}

def check(item):
    p = (ROOT/item.get('path', item.get('rel_path'))).resolve(strict=True)
    if not p.is_relative_to(ROOT) or record(p)['sha256'] != item['sha256'] or p.stat().st_size != item['bytes']:
        raise ValueError('Source changed')
    return p

def run(*args, capture=False):
    result = subprocess.run(list(map(str,args)), check=True, creationflags=FLAGS,
                            stdout=subprocess.PIPE if capture else None, stderr=subprocess.PIPE if capture else None)
    return result

def ffmpeg(*args):
    return run('ffmpeg','-v','error','-nostdin','-n',*args)

def units(text):
    return sum(.54 if ord(c)<128 or '\uff61'<=c<='\uff9f' else 1 for c in text)

def presenter_media_window(probe, scene, duration):
    """Bind editorial playback to real source time; never loop its final frame."""
    seconds=float(probe['duration'])
    start=scene.get('mediaStart',0)
    if (int(probe['width'])<768 or int(probe['height'])<1344
            or not math.isfinite(seconds) or seconds<=0
            or type(start) is not int or start<0):
        raise ValueError('Source resolution/duration too low')
    if scene['kind']!='editorial':
        if seconds+1/FPS<(duration+start)/FPS:
            raise ValueError('Source resolution/duration too low')
        return {}
    source_frames=math.floor(seconds*FPS+0.00001)
    available=source_frames-start
    if available<FPS:
        raise ValueError('Editorial guide needs at least one second of real video')
    return {'mediaPlayFrames':min(duration,available),'mediaDurationInFrames':source_frames}

def official_capture_url(value):
    """Closed public-document URLs for explicitly attributed new captures."""
    try:
        source=urlsplit(value)
        if (source.scheme!='https' or source.username or source.password or source.port
                or source.query or source.netloc!=source.hostname):return False
        return bool(
            (source.hostname=='learn.chatgpt.com' and re.fullmatch(r'/docs/dots/[a-z-]+',source.path))
            or (source.hostname=='support.claude.com' and re.fullmatch(r'/(?:en|ja)/articles/[^/]+',source.path))
            or (source.hostname=='claude.com' and re.fullmatch(r'/resources/articles/[^/]+',source.path))
            or (source.hostname=='www.php.net' and re.fullmatch(r'/archive/[0-9]{4}\.php',source.path))
            or (source.hostname=='www.ipa.go.jp' and re.fullmatch(r'/security/security-alert/[0-9]{4}/alert[0-9]{8}\.html',source.path))
            or (source.hostname=='www.jpcert.or.jp' and re.fullmatch(r'/at/[0-9]{4}/at[0-9]{6}\.html',source.path)))
    except (TypeError,ValueError):return False

def validate_business_scene(scene,index,count):
    if scene.get('visual_style')!='business' or scene['kind'] not in {'editorial','source'}:
        raise ValueError('Unknown or misplaced visual style')
    one_line=lambda text,maximum:len(text.split('\n'))==1 and units(text)<=maximum
    if len(scene['headline'].split('\n'))>2 or any(units(line)>10 for line in scene['headline'].split('\n')):
        raise ValueError('Business headline needs at most two short lines')
    if not one_line(scene.get('eyebrow',''),15) or not one_line(scene.get('action',''),12):
        raise ValueError('Business label is too long')
    if scene.get('presenter'):raise ValueError('Business guides require motion clips, not still presenters')
    narrow=bool(scene.get('media'))
    if narrow:
        layout=scene.get('editorial_layout')
        if (scene['kind']!='editorial' or layout not in {'hook','closing'}
                or (layout=='hook' and index!=0) or (layout=='closing' and index!=count-1)):
            raise ValueError('Business motion clips belong only in the opening or closing')
        start=scene.get('mediaStart',0)
        if type(start) is not int or start<0:raise ValueError('Invalid business video start')
    lines=scene.get('body','').split('\n');items=scene.get('items',[])
    if (len(lines)>2 or any(units(line)>(9 if narrow else 12) for line in lines)
            or len(items)>(2 if narrow else 3)
            or any(not one_line(item['label'],8 if narrow else 10)
                   or not one_line(item.get('detail',''),8 if narrow else 11) for item in items)
            or not one_line(scene.get('stat',''),8 if narrow else 12)):
        raise ValueError('Business content does not fit')
    if len(items)==3 and len(lines)>1:raise ValueError('Three business items need a single-line introduction')
    if scene.get('stat') and items:raise ValueError('Use either business items or a statistic')
    if scene['kind']=='source' and any([scene.get('body'),scene.get('action'),scene.get('stat'),items,scene.get('media')]):
        raise ValueError('Business source scenes reserve the center for evidence')

def validate_capture(capture,visual_style=None):
    if not isinstance(capture,dict):raise ValueError('Expected a cited source capture')
    origin=capture.get('origin')
    required={'path','proof','source_url','title'}
    if origin=='official':required.add('origin')
    elif origin=='demonstration':required={'path','proof','title','origin','product','phase'}
    elif 'origin' in capture:raise ValueError('Unknown capture origin')
    if set(capture)!=required:raise ValueError('Expected a cited source capture')
    if any(not isinstance(value,str) or not value for value in capture.values()):
        raise ValueError('Source capture fields must be nonempty text')
    if not re.fullmatch(r'outputs/productions/[A-Za-z0-9_-]+/captures/[A-Za-z0-9_-]+\.png',capture['path']) or not re.fullmatch(r'outputs/productions/[A-Za-z0-9_-]+/captures/[A-Za-z0-9_-]+\.json',capture['proof']):
        raise ValueError('Source capture paths must stay inside production captures')
    if origin is not None and visual_style!='business':raise ValueError('Explicit capture origin requires business style')
    if origin=='demonstration':
        if capture['product'] not in DEMONSTRATION_PRODUCTS or capture['phase'] not in DEMONSTRATION_PHASES:
            raise ValueError('Unknown demonstration product or phase')
    elif origin=='official':
        if not official_capture_url(capture['source_url']):raise ValueError('Expected an official source URL')
    else:
        # Keep the original dots URL contract unchanged for existing stories.
        source=urlsplit(capture['source_url'])
        if source.scheme!='https' or source.hostname!='learn.chatgpt.com' or not source.path.startswith('/docs/dots/') or source.username or source.password or source.query:
            raise ValueError('Expected an official dots source URL')
    if units(capture['title'])>18:raise ValueError('Source title is too long')

def load_capture(capture):
    """Validate an already reviewed crop and return its immutable local inputs."""
    proof_path=ROOT/capture['proof'];proof=read(proof_path);source=check(proof['artifact'])
    if (proof.get('review_status')!='capture_review_passed' or proof.get('title')!=capture['title']
            or source!=(ROOT/capture['path']).resolve() or source.suffix.lower()!='.png'):
        raise ValueError('Unverified source capture')
    origin=capture.get('origin')
    if origin is None:
        if proof.get('source_url')!=capture['source_url']:raise ValueError('Unverified official source capture')
    else:
        if proof.get('origin')!=origin:raise ValueError('Capture origin differs from its proof')
        try:
            captured=datetime.fromisoformat(proof['captured_at'].replace('Z','+00:00'))
            if captured.utcoffset() is None:raise ValueError('Timezone is required')
        except (KeyError,AttributeError,TypeError,ValueError):
            raise ValueError('Capture proof needs a timestamp with timezone') from None
        if origin=='official':
            if proof.get('source_url')!=capture['source_url']:raise ValueError('Official source URL differs from proof')
        else:
            if (proof.get('product')!=capture['product'] or proof.get('phase')!=capture['phase']
                    or proof.get('fictional_materials_only') is not True
                    or proof.get('personal_information_excluded') is not True):
                raise ValueError('Demonstration proof needs matching phase and fictional/privacy checks')
            if any(key in proof for key in ['source_url','original_url','browser_url','url']) or re.search(r'https?://',json.dumps(proof),re.I):
                raise ValueError('Demonstration proof must not retain a private account URL')
    context=check(proof['context']);crop=proof['clip'];original=proof['context_clip']
    if not (crop['width']>0 and crop['height']>0 and crop['x']>=original['x'] and crop['y']>=original['y']
            and crop['x']+crop['width']<=original['x']+original['width']
            and crop['y']+crop['height']<=original['y']+original['height']):
        raise ValueError('Capture crop lies outside its original context')
    for image,region in [(source,crop),(context,original)]:
        with image.open('rb') as stream:header=stream.read(24)
        if header[:8]!=b'\x89PNG\r\n\x1a\n' or struct.unpack('>II',header[16:24])!=(region['width'],region['height']):
            raise ValueError('Capture PNG dimensions differ from recorded crop')
    return source,[record(proof_path),record(source),record(context)]

def staged_capture(capture,image):
    """Keep legacy props byte-compatible and omit account URLs from demos."""
    if 'origin' not in capture:return {'image':image,'source_url':capture['source_url'],'title':capture['title']}
    result={'image':image,'title':capture['title'],'origin':capture['origin']}
    if capture['origin']=='official':result['source_url']=capture['source_url']
    else:result.update(product=capture['product'],phase=capture['phase'])
    return result

def validate_story(story):
    if story.get('schema_version') != 1 or story.get('duration_seconds') not in [15,30,45,50,60]:
        raise ValueError('Use schema 1 and a 15/30/45/50/60 second duration')
    music_preset=story.get('music_preset','electro_pop_v1')
    if not isinstance(music_preset,str) or music_preset not in MUSIC_PRESETS:
        raise ValueError('Unknown music preset')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',story.get('id','')):
        raise ValueError('Invalid production id')
    scenes = story.get('scenes')
    if not isinstance(scenes,list) or not 3<=len(scenes)<=24:
        raise ValueError('Use 3–24 scenes')
    for scene_index,scene in enumerate(scenes):
        if scene.get('kind') not in KINDS or not isinstance(scene.get('narration'),str) or not 1<=len(scene['narration'])<=80:
            raise ValueError('Invalid scene')
        lines=scene.get('headline','').split('\n')
        if len(lines)>3 or not all(0<units(line)<=14 for line in lines):
            raise ValueError('Headline must fit three readable lines')
        if units(scene.get('eyebrow',''))>15 or len(scene.get('items',[]))>3:
            raise ValueError('Too much on-screen information')
        if any(units(i['label'])>10 or units(i.get('detail',''))>11 for i in scene.get('items',[])):
            raise ValueError('Shorten item labels/details')
        if scene['kind']=='diagram' and (scene.get('graphic') not in FEATURE_GRAPHICS or any(units(i['label'])>4 for i in scene.get('items',[]))):
            raise ValueError('Invalid feature diagram or overlong node label')
        if scene['kind']=='stat' and (not scene.get('stat') or units(scene['stat'])>8):
            raise ValueError('Invalid feature statistic')
        if scene['kind']=='editorial' and scene.get('editorial_layout') not in EDITORIAL_LAYOUTS:
            raise ValueError('Unknown editorial layout')
        if 'visual_style' in scene:validate_business_scene(scene,scene_index,len(scenes))
        if 'presenter' in scene:
            presenter=scene['presenter']
            if (scene['kind']!='editorial' or not isinstance(presenter,dict)
                    or set(presenter)!={'path','proof','role'}
                    or presenter.get('role') not in {'hook','recap'}
                    or (presenter['role']=='hook' and scene_index!=0)
                    or (presenter['role']=='recap' and scene_index!=len(scenes)-1)):
                raise ValueError('Presenter belongs only in editorial opening or closing scenes')
            for key,extension in [('path','png'),('proof','json')]:
                if not isinstance(presenter[key],str) or not re.fullmatch(r'outputs/characters/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.'+extension,presenter[key]):
                    raise ValueError('Presenter paths must stay inside character assets')
        if scene['kind']=='editorial' and scene.get('visual_style')!='business' and scene.get('editorial_layout') not in {'hook','parallel','conversation','closing'}:
            layout=scene['editorial_layout']
            if len(scene.get('body','').split('\n'))>(2 if layout=='statement' else 1):
                raise ValueError('Editorial body exceeds its layout')
            if '\n' in scene.get('action','') or units(scene.get('action',''))>12:
                raise ValueError('Shorten editorial action')
            if units(scene.get('stat',''))>(4 if layout=='channels' else 8):
                raise ValueError('Shorten editorial statistic')
            if layout=='contrast' and len(scene.get('items',[]))>2:
                raise ValueError('Editorial contrast compares two items')
            if any('\n' in value for item in scene.get('items',[]) for value in [item['label'],item.get('detail','')]):
                raise ValueError('Editorial items require single lines')
            if layout in {'channels','calendar'} and any(units(item['label'])>7 or units(item.get('detail',''))>7 for item in scene.get('items',[])):
                raise ValueError('Editorial side-panel text is too long')
        if scene['kind']=='source':
            validate_capture(scene.get('capture',{}),scene.get('visual_style'))
        if any(units(line)>(9 if scene['kind']=='quote' else 12) for line in scene.get('body','').split('\n')):
            raise ValueError('Shorten scene body')
        parts=scene.get('captions',[])
        if not parts or any(not p or any(units(line)>12 for line in p.split('\n')) or len(p.split('\n'))>2 for p in parts):
            raise ValueError('Caption phrases must fit')
        normalize=lambda s:re.sub(r'[\s、。！？!?,.]','',s)
        if normalize(''.join(parts))!=normalize(scene['narration']):
            raise ValueError('Captions must match the spoken text')
    return story

def allocate_scenes(speech_ms, total_frames):
    """Preserve every spoken sample; spread remaining breathing space over cuts."""
    durations=[max(30,math.ceil(ms*FPS/1000)+5) for ms in speech_ms]
    remaining=total_frames-sum(durations)
    if remaining<0:
        raise ValueError(f'Script is too long by {-remaining/FPS:.2f}s; shorten it or select a faster voice rate')
    for i in range(remaining): durations[i%len(durations)]+=1
    if max(durations)>192: raise ValueError('A scene exceeds 8 seconds; add a meaningful cut')
    return durations

def pcm_write(path,samples,sr):
    with wave.open(str(path),'wb') as f:
        f.setparams((1 if samples.ndim==1 else samples.shape[1],2,sr,0,'NONE','not compressed'))
        f.writeframes((np.clip(samples,-.999,.999)*32767).astype('<i2').tobytes())

def bright_groove(total, sr, duration):
    """Original 112 BPM major-key plucks, soft bass and shaker; no external audio."""
    track=np.zeros((total,2));rng=np.random.default_rng(1021);beat=60/112
    chords=[(174.61,220.,261.63,329.63),(146.83,174.61,220.,261.63),
            (116.54,174.61,220.,293.66),(130.81,196.,261.63,293.66)]
    def add(start,signal,pan=0):
        off=round(start*sr);n=min(len(signal),total-off)
        if off<0 or n<=0:return
        track[off:off+n]+=signal[:n,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)])
    for step in range(math.ceil(duration/beat)):
        start=step*beat;chord=chords[(step//4)%4]
        t=np.arange(round(.65*sr))/sr
        bass=np.sin(2*np.pi*chord[0]/2*t)*np.minimum(t/.012,1)*np.exp(-t*7)*.095
        if step%2==0:add(start,bass)
        for subdivision in range(2):
            position=start+subdivision*beat/2
            note=chord[(step*2+subdivision)%4]*2
            env=np.minimum(t/.008,1)*np.exp(-t*8)*np.minimum((.65-t)/.06,1)
            pluck=(np.sin(2*np.pi*note*t)+.24*np.sin(4*np.pi*note*t)+.08*np.sin(6*np.pi*note*t))*env*.050
            add(position,pluck,(-1 if subdivision==0 else 1)*.42)
            noise=rng.normal(0,1,round(.055*sr))
            high=noise-np.convolve(noise,np.ones(8)/8,mode='same')
            shaker=high*np.exp(-np.arange(len(noise))/520)*(.010 if subdivision else .006)
            add(position,shaker,(-1)**step*.18)
        if step%2==0:
            tt=np.arange(round(.16*sr))/sr
            add(start,np.sin(2*np.pi*(45*tt+4*(1-np.exp(-30*tt))))*np.exp(-tt*32)*.075)
        else:
            noise=rng.normal(0,1,round(.09*sr))
            add(start,np.convolve(noise,np.ones(6)/6,mode='same')*np.exp(-np.arange(len(noise))/750)*.027)
        if step%4==0:
            tt=np.arange(round(1.7*sr))/sr
            pad=sum(np.sin(2*np.pi*note*tt) for note in chord)/4
            add(start,pad*np.minimum(tt/.08,1)*np.exp(-tt*2)*.026)
    return track

def sound_design(out, scenes, speech, duration, music_preset='electro_pop_v1'):
    """Original selectable score; legacy default and edit accents stay deterministic."""
    if music_preset not in MUSIC_PRESETS:raise ValueError('Unknown music preset')
    sr=48000; total=round(duration*sr); t_all=np.arange(total)/sr
    music=np.zeros((total,2)); fx=np.zeros_like(music); rng=np.random.default_rng(930)
    def tone(track,start,length,freq,amp,pan=0,decay=5):
        off=round(start*sr); n=min(round(length*sr),total-off)
        if off<0 or n<=0:return
        t=np.arange(n)/sr
        env=np.minimum(t/.006,1)*np.minimum((n/sr-t)/.05,1)*np.exp(-decay*t)
        signal=(np.sin(2*np.pi*freq*t)+.17*np.sin(4*np.pi*freq*t))*env*amp
        track[off:off+n]+=signal[:,None]*np.array([math.sqrt((1-pan)/2),math.sqrt((1+pan)/2)])
    chords=[(130.81,164.81,196.00,246.94),(110.,130.81,164.81,196.),(87.31,130.81,174.61,220.),(98.,146.83,196.,246.94)]
    for beat in range(math.ceil(duration*2)):
        start=beat*.5; chord=chords[(beat//8)%4]
        tone(music,start,.4,chord[0]/2,.13,decay=6)
        tone(music,start+.25,.65,chord[beat%4]*4,.047,pan=.45*(-1)**beat,decay=6)
        if beat%2==0:
            off=round(start*sr); n=min(round(.18*sr),total-off); tt=np.arange(n)/sr
            kick=np.sin(2*np.pi*(48*tt+7*(1-np.exp(-24*tt))))*np.exp(-tt*26)*.13
            music[off:off+n]+=kick[:,None]
        else:
            off=round(start*sr); n=min(5000,total-off)
            clap=rng.normal(0,1,n)*np.exp(-np.arange(n)/950)*.018
            music[off:off+n]+=clap[:,None]
        for pan,note in zip([-.55,-.2,.2,.55],chord):tone(music,start,1.1,note,.018,pan,decay=1.8)
    if music_preset=='bright_groove_v1':music=bright_groove(total,sr,duration)
    for index,scene in enumerate(scenes):
        start=scene['from']/FPS
        if index:
            off=max(0,round((start-.09)*sr)); n=min(round(.2*sr),total-off)
            noise=rng.normal(0,1,n); filtered=np.convolve(noise,np.ones(12)/12,mode='same')
            swoosh=filtered*np.sin(np.linspace(0,np.pi,n))**2*.055
            fx[off:off+n]+=swoosh[:,None]
        for item in range(min(3,len(scene.get('items',[])))):
            tone(fx,start+.34+item*.38,.15,720+item*120,.026,decay=20)
        if scene['kind']=='checklist' or index==len(scenes)-1:
            for i,note in enumerate([659.25,783.99,987.77]):tone(fx,start+.12+i*.065,.36,note,.046,pan=(i-1)*.25,decay=10)
    duck=np.ones(total)
    for a,b in speech:
        duck=np.minimum(duck,1-.66*np.clip((t_all-a+.075)/.075,0,1)*np.clip((b+.20-t_all)/.20,0,1))
    fade=np.minimum(t_all/.05,1)*np.clip((duration-t_all)/.30,0,1)
    music*= (duck*fade)[:,None];fx*=fade[:,None]
    pcm_write(out/'music.wav',music,sr);pcm_write(out/'effects.wav',fx,sr)

def audio_signature(story):
    """Only visual changes may keep a previous edit's speech, cuts and score."""
    return {**{k:story.get(k) for k in ['id','duration_seconds','voice','rate','pronunciations']},
            'music_preset':story.get('music_preset','electro_pop_v1'),
            'scenes':[{'narration':s['narration'],'captions':s['captions'],
                       'kind':s['kind'],'item_count':len(s.get('items',[]))} for s in story['scenes']]}

def load_reusable_audio(story, prior):
    prior=prior.resolve(strict=True)
    if not prior.is_relative_to(ROOT/'outputs/productions'/story['id']):
        raise ValueError('Reuse audio from the same production')
    prep=read(prior/'preparation.json');proof=read(prior/'verification.json')
    if proof['review_status']!='verified_candidate_awaiting_user_review':
        raise ValueError('Reuse requires a verified previous delivery')
    files={}
    for name in ['story.json','props.json','narration.wav','music.wav','effects.wav','timings.json','captions.srt']:
        item=next((r for r in prep['sources'] if (ROOT/r['path']).resolve()==prior/name),None)
        if item is None:raise ValueError('Missing verified audio input: '+name)
        files[name]=check(item)
    if audio_signature(read(files['story.json']))!=audio_signature(story):
        raise ValueError('Audio input changed; generate new narration and music')
    delivery=check(proof['delivery'])
    if delivery!=prior/'shorts-creator.mp4':raise ValueError('Unexpected previous delivery')
    voice=read(prior/'voice-source.json')
    for artifact in voice['artifacts']:
        p=check(artifact)
        if not any((ROOT/r['path']).resolve()==p and r['sha256']==artifact['sha256'] for r in prep['sources']):
            raise ValueError('Narration not bound to previous preparation')
    sources=[record(p) for p in [prior/'preparation.json',prior/'verification.json',prior/'voice-source.json',delivery,*files.values()]]
    return voice,{'source_delivery':record(delivery),'method':'aac_stream_copy'},files,sources

def narration_inputs(story):
    return {key:story.get(key,[]) for key in ['id','voice','rate','pronunciations']} | {
        'segments':[s['narration'] for s in story['scenes']]}

def load_supplied_narration(story,source):
    source=source.resolve(strict=True)
    if not source.is_relative_to(ROOT/'outputs/productions'):
        raise ValueError('Narration source must be inside production outputs')
    voice=read(source)
    if (voice.get('provider'),voice.get('model'),voice.get('voice')) not in [
        ('gemini','gemini-2.5-flash-preview-tts','Aoede'),('gemini','gemini-2.5-flash-preview-tts','Kore')]:
        raise ValueError('Unverified narration provider, model or voice')
    if voice.get('inputs')!=narration_inputs(story):
        raise ValueError('Narration inputs changed')
    artifacts=voice.get('artifacts',[])
    if len(artifacts)!=2 or {a.get('name') for a in artifacts}!={'narration.wav','timings.json'}:
        raise ValueError('Expected narration and measured timing artifacts')
    files={a['name']:check(a) for a in artifacts}
    proof_files=voice.get('generation_proofs',[])
    if len(proof_files)!=len(story['scenes']):raise ValueError('Missing speech generation proof')
    sources=[record(source)]
    for item in proof_files:
        proof_path=check(item);proof=read(proof_path)
        if proof.get('status')!='technically_verified_listening_pending' or proof.get('model')!=voice['model'] or proof.get('voice')!=voice['voice']:
            raise ValueError('Speech generation not verified')
        sources.append(record(proof_path))
        sources.extend(record(check(a)) for a in proof['files'])
    timing=read(files['timings.json']);segments=timing.get('segments',[])
    with wave.open(str(files['narration.wav']),'rb') as wav:
        if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth())!=(24000,1,2):
            raise ValueError('Expected verified 24kHz mono narration')
        if len(segments)!=len(story['scenes']) or sum(s['frames'] for s in segments)!=wav.getnframes():
            raise ValueError('Narration sample count mismatch')
    cursor=0
    for scene,segment,item in zip(story['scenes'],segments,proof_files,strict=True):
        proof=read(check(item))
        spoken=scene['narration']
        for rule in sorted(story.get('pronunciations',[]),key=lambda x:-len(x['source'])):
            spoken=spoken.replace(rule['source'],rule['target'])
        request_path=next(check(a) for a in proof['files'] if a['path'].endswith('/request.json'))
        request_text=read(request_path)['contents'][0]['parts'][0]['text']
        if request_text.split('Transcript:\n',1)[-1]!=spoken:
            raise ValueError('Speech request transcript mismatch')
        if segment['text']!=scene['narration'] or not isinstance(segment['frames'],int) or segment['frames']<=0:
            raise ValueError('Narration segment mismatch')
        if abs(segment['duration_ms']-segment['frames']/24)>1:
            raise ValueError('Narration duration mismatch')
        original=next(check(a) for a in proof['files'] if a['path'].endswith('/voice.wav'))
        with wave.open(str(original),'rb') as wav:
            if wav.getnframes()!=segment['frames']:raise ValueError('Speech proof sample count mismatch')
        with wave.open(str(files['narration.wav']),'rb') as combined, wave.open(str(original),'rb') as original_wav:
            combined.setpos(cursor)
            if combined.readframes(segment['frames'])!=original_wav.readframes(segment['frames']):
                raise ValueError('Combined narration differs from verified speech')
        cursor+=segment['frames']
    return voice,sources

def prepare(story_path,reuse_audio=None,narration_source=None):
    from .narration import generate_local_narration
    story_path=story_path.resolve(strict=True)
    if not story_path.is_relative_to(ROOT/'productions'):raise ValueError('Story must be in productions')
    story=validate_story(read(story_path));total=story['duration_seconds']*FPS
    if reuse_audio is not None and narration_source is not None:
        raise ValueError('Choose previous audio or supplied narration')
    supplied=None
    if narration_source is not None:supplied=load_supplied_narration(story,narration_source)
    out=ROOT/'outputs/productions'/story['id']/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out.mkdir(parents=True)
    sources=[record(story_path),record(Path(__file__)),record(ROOT/'tools/studio/narration.py')]
    write(out/'story.json',story)
    media_map={}
    capture_map={}
    presenter_map={}
    for scene in story['scenes']:
        if scene.get('presenter'):
            from PIL import Image
            presenter=scene['presenter'];proof_path=ROOT/presenter['proof'];proof=read(proof_path)
            source=check(proof['artifact'])
            if (proof.get('review_status')!='visual_review_passed' or proof.get('source_type')!='generated_humanoid'
                    or proof.get('transparent') is not True or source!=(ROOT/presenter['path']).resolve()):
                raise ValueError('Unverified human presenter asset')
            with Image.open(source) as character:
                if (character.format!='PNG' or character.mode!='RGBA' or min(character.size)<768
                        or character.size!=(proof.get('width'),proof.get('height'))
                        or character.getchannel('A').getextrema()[0]!=0):
                    raise ValueError('Expected a high-resolution transparent presenter PNG')
            presenter_map[presenter['path']]=source
            sources.extend([record(proof_path),record(source)])
        if scene.get('capture'):
            capture=scene['capture'];source,capture_sources=load_capture(capture)
            capture_map[capture['path']]=source
            sources.extend(capture_sources)
        if 'media' not in scene:continue
        media=scene['media'];proof=read(ROOT/media['proof']);source=check(proof['artifact'])
        if source!=(ROOT/media['path']).resolve() or not proof['execution']['success'] or proof['review_status']!='visual_review_passed':raise ValueError('Unverified media')
        media_map[media['path']]=source
        sources.extend([record(ROOT/media['proof']),record(source)])
    audio_reuse=None;prior_files={}
    if supplied is not None:
        voice,supplied_sources=supplied
        sources.extend(supplied_sources)
    elif reuse_audio is not None:
        voice,audio_reuse,prior_files,reuse_sources=load_reusable_audio(story,reuse_audio)
        sources.extend(reuse_sources)
    else:
        token=uuid.uuid4().hex
        voice=generate_local_narration(ROOT,production_id='production_'+token,run_id='run_'+token,payload={
            'voice':story['voice'],'rate':story['rate'],'pronunciations':story.get('pronunciations',[]),
            'segments':[{'text':s['narration']} for s in story['scenes']]})
    write(out/'voice-source.json',voice)
    files={a['name']:check(a) for a in voice['artifacts']}
    sources.extend(record(p) for p in files.values())
    raw_timing=read(files['timings.json'])['segments']
    with wave.open(str(files['narration.wav']),'rb') as w:
        sr=w.getframerate();assert w.getnchannels()==1 and w.getsampwidth()==2
        raw=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float)/32768
    durations=allocate_scenes([s['duration_ms'] for s in raw_timing],total)
    voice_track=np.zeros(round(story['duration_seconds']*sr));scenes=[];captions=[];timings=[];cursor=0
    pub=out/'public';pub.mkdir()
    staged={}
    for index,(source_path,p) in enumerate(media_map.items()):
        name=f'media-{index:02d}.mp4';shutil.copyfile(p,pub/name);staged[source_path]=name
    capture_staged={}
    for index,(source_path,p) in enumerate(capture_map.items()):
        name=f'capture-{index:02d}.png';shutil.copyfile(p,pub/name);capture_staged[source_path]=name
    presenter_staged={}
    for index,(source_path,p) in enumerate(presenter_map.items()):
        name=f'presenter-{index:02d}.png';shutil.copyfile(p,pub/name);presenter_staged[source_path]=name
    for i,(scene,duration,timing) in enumerate(zip(story['scenes'],durations,raw_timing,strict=True)):
        start=cursor+3
        begin=sum(s['frames'] for s in raw_timing[:i]);count=timing['frames'];samples=raw[begin:begin+count]
        if len(samples)!=count:raise ValueError('Speech sample range')
        off=round(start*sr/FPS);voice_track[off:off+count]=samples
        end=start+math.ceil(count/sr*FPS)
        item={k:v for k,v in scene.items() if k not in ['narration','captions','media','capture','presenter']}
        item.update(id=f'scene-{i:02d}',from_=cursor,duration=duration)
        item['from']=item.pop('from_')
        if scene.get('capture'):
            capture=scene['capture']
            item['capture']=staged_capture(capture,capture_staged[capture['path']])
        if scene.get('presenter'):
            presenter=scene['presenter']
            item['presenter']={'image':presenter_staged[presenter['path']],'role':presenter['role']}
        if 'media' in scene:
            item['media']=staged[scene['media']['path']]
            probe=json.loads(run('ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height,duration,avg_frame_rate','-of','json',media_map[scene['media']['path']],capture=True).stdout)['streams'][0]
            item.update(presenter_media_window(probe,item,duration))
        scenes.append(item)
        timings.append({'scene':i,'start_ms':round(start*1000/FPS),'end_ms':round((off+count)*1000/sr),'duration_ms':round(count*1000/sr),'text':scene['narration']})
        parts=scene['captions'];weight=sum(units(s) for s in parts);part_start=start;used=0
        for j,part in enumerate(parts):
            used+=units(part);part_end=end if j==len(parts)-1 else start+round((end-start)*used/weight)
            if part_end-part_start<10:raise ValueError('Caption phrase is too brief')
            captions.append({'start':part_start,'end':part_end,'text':part});part_start=part_end
        cursor+=duration
    pcm_write(out/'narration.wav',voice_track,sr)
    sound_design(out,scenes,[(x['start_ms']/1000,x['end_ms']/1000) for x in timings],story['duration_seconds'],story.get('music_preset','electro_pop_v1'))
    write(out/'timings.json',{'policy':'measured_speech_frame_scenes_v1','segments':timings,'captions':'phrase durations distributed by display units within measured speech'})
    def srt_time(frame):
        ms=round(frame*1000/FPS);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'
    (out/'captions.srt').write_text('\n\n'.join(f"{i+1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}" for i,c in enumerate(captions))+'\n',encoding='utf-8')
    props={'title':story['title'],'scenes':scenes,'captions':captions,'durationInFrames':total,'showGuides':False}
    write(out/'props.json',props)
    if audio_reuse:
        previous_props=read(prior_files['props.json'])
        if previous_props['captions']!=captions or any(
            (a['from'],a['duration'])!=(b['from'],b['duration'])
            for a,b in zip(previous_props['scenes'],scenes,strict=True)):
            raise ValueError('Scene or caption timing changed; cannot reuse audio')
        for name in ['narration.wav','music.wav','effects.wav','timings.json','captions.srt']:
            if record(out/name)['sha256']!=record(prior_files[name])['sha256']:
                raise ValueError('Audio layout changed; cannot reuse '+name)
    sources.extend(record(out/n) for n in ['story.json','props.json','narration.wav','music.wav','effects.wav','timings.json','captions.srt'])
    write(out/'preparation.json',{'sources':sources,'audio_reuse':audio_reuse,'music_preset':story.get('music_preset','electro_pop_v1'),
        'new_generation':supplied is not None,'new_video_generation':False,'narration_provider':voice['provider'],
        'external_api_calls':voice.get('external_api_calls',0) if supplied else 0,'on_screen_tool_credit':False})
    print(json.dumps({'event':'prepared','output':str(out),'scene_durations':[round(n/FPS,2) for n in durations]}),flush=True)
    return out

def finish(out):
    prep=read(out/'preparation.json');rendered=read(out/'render.json');props=read(out/'props.json')
    for item in prep['sources']+rendered['sources']:check(item)
    duration=props['durationInFrames']/FPS
    video=check(rendered['timeline']);delivery=out/'shorts-creator.mp4'
    audio_reuse=prep.get('audio_reuse')
    if audio_reuse:
        prior=check(audio_reuse['source_delivery'])
        ffmpeg('-i',video,'-i',prior,'-map','0:v:0','-map','1:a:0','-c','copy','-t',duration,'-movflags','+faststart',delivery)
        def audio_hash(p):
            return run('ffmpeg','-v','error','-i',p,'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-',capture=True).stdout.decode().strip()
        original_hash=audio_hash(prior)
        if original_hash!=audio_hash(delivery):raise ValueError('Audio stream changed')
        audio_reuse={**audio_reuse,'packet_hash':original_hash,'identical_audio_verified':True}
    else:
        # Explicit stereo voice keeps the music's stereo field intact.
        ffmpeg('-i',out/'narration.wav','-i',out/'music.wav','-i',out/'effects.wav','-filter_complex',
               '[0:a]aresample=48000,highpass=f=75,lowpass=f=10500,acompressor=threshold=0.16:ratio=2:attack=12:release=120,pan=stereo|c0=c0|c1=c0[v];[v][1:a][2:a]amix=inputs=3:duration=longest:normalize=0[a]',
               '-map','[a]','-ar','48000','-ac','2','-c:a','pcm_s24le','-t',duration,out/'mix.wav')
        measure=run('ffmpeg','-hide_banner','-nostdin','-i',out/'mix.wav','-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-',capture=True)
        measurement=json.loads(re.findall(r'\{[\s\S]*?\}',measure.stderr.decode())[-1])
        norm=f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={measurement['input_i']}:measured_TP={measurement['input_tp']}:measured_LRA={measurement['input_lra']}:measured_thresh={measurement['input_thresh']}:offset={measurement['target_offset']}:linear=true:print_format=summary"
        ffmpeg('-i',video,'-i',out/'mix.wav','-map','0:v:0','-map','1:a:0','-c:v','copy','-af',norm,'-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',duration,'-movflags','+faststart',delivery)
    probe=json.loads(run('ffprobe','-v','error','-show_streams','-show_format','-of','json',delivery,capture=True).stdout)
    v,a=probe['streams'];assert v['codec_name']=='h264' and a['codec_name']=='aac'
    assert (v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))==(1080,1920,'24/1',props['durationInFrames'])
    assert abs(float(probe['format']['duration'])-duration)<.002 and a['sample_rate']=='48000' and a['channels']==2
    ffmpeg('-xerror','-i',delivery,'-f','null','-')
    result=run('ffmpeg','-hide_banner','-nostdin','-i',delivery,'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-',capture=True)
    loudness=json.loads(re.findall(r'\{[\s\S]*?\}',result.stderr.decode())[-1])
    assert -18<=float(loudness['input_i'])<=-14 and float(loudness['input_tp'])<=-1.0
    ffmpeg('-i',delivery,'-vf',f'fps=1,scale=216:384,tile=6x{math.ceil(duration/6)}','-frames:v','1',out/'contact-sheet.png')
    for i,scene in enumerate(props['scenes']):
        second=(scene['from']+min(scene['duration']-1,40))/FPS
        ffmpeg('-ss',second,'-i',delivery,'-frames:v','1','-vf','scale=360:640:flags=lanczos',out/f'preview-{i:02d}.png')
    write(out/'verification.json',{'delivery':record(delivery),'probe':probe,'full_decode_verified':True,'loudness':loudness,
        'sources':rendered['sources'],'audio_reuse':audio_reuse,'review_status':'awaiting_visual_review','user_approved':False,
        'quality_policy':{'loudness_lufs':[-18,-14],'true_peak_dbfs_max':-1,'font_min_px':54,'safe_area':[72,210,900,1490]},
        'new_generation':prep.get('new_generation',False),'new_video_generation':False,
        'narration_provider':prep.get('narration_provider','windows_sapi'),'external_api_calls':prep.get('external_api_calls',0),
        'on_screen_tool_credit':False})
    print(json.dumps({'event':'assembled','output':str(out),'loudness_lufs':loudness['input_i'],'true_peak_dbfs':loudness['input_tp']}),flush=True)
    review_page(out,loudness)

def review_page(out,loudness):
    story=read(out/'story.json');props=read(out/'props.json');title=html.escape(story['title'])
    previous=''
    if story.get('previous_video'):
        p=(ROOT/story['previous_video']).resolve(strict=True)
        if not p.is_relative_to(ROOT/'outputs') or p.suffix!='.mp4':raise ValueError('Invalid comparison video')
        src=html.escape(os.path.relpath(p,out).replace('\\','/'),quote=True)
        previous=f'<button id="previous" data-src="{src}">以前の動画</button>'
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title>
<style>*{box-sizing:border-box}body{margin:0;background:#0b1120;color:#f5f1e8;font-family:"Yu Gothic UI",Meiryo,sans-serif}main{max-width:1130px;margin:0 auto;padding:38px 22px;display:grid;grid-template-columns:minmax(270px,400px) 1fr;gap:48px}.player{position:relative;aspect-ratio:9/16;max-height:84vh;margin:auto}video{width:100%;height:100%;display:block;border-radius:18px;background:#090d16}h1{font-size:clamp(28px,4vw,48px);letter-spacing:-.04em;line-height:1.35}p,li{font-size:18px;line-height:1.8}.eyebrow{color:#dfff78;font-weight:750;font-size:14px;letter-spacing:.12em}.controls,.links{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}button,.links a{font:inherit;padding:12px 18px;border:1px solid #3e4a63;border-radius:12px;background:#19243a;color:#f5f1e8;cursor:pointer;text-decoration:none}button[aria-pressed=true],.links a:first-child{background:#dfff78;color:#0b1120}a{color:#dfff78}.note{color:#aebbd0;font-size:14px}.guide{display:none;position:absolute;inset:0;pointer-events:none;border-radius:18px;overflow:hidden}.guide:before{content:"";position:absolute;left:6.67%;right:16.67%;top:10.94%;bottom:22.4%;border:2px dashed #4af1bb;box-shadow:0 0 0 400px #f64f5e32}.guide.show{display:block}.guide span{position:absolute;bottom:14%;left:8%;font-size:12px;background:#102030d9;padding:8px}.metrics{display:flex;gap:24px;margin:25px 0}.metrics strong{display:block;color:#dfff78;font-size:28px}.metrics span{color:#aebbd0;font-size:14px}details{margin:24px 0}summary{cursor:pointer}details img{width:100%;margin-top:16px}@media(max-width:720px){main{grid-template-columns:1fr;padding:22px 18px;gap:22px}.player{max-height:72vh}h1{margin-top:0}.metrics{gap:16px}button,.links a{padding:10px 13px}}</style>
<main><div class="player"><video id="video" controls playsinline preload="metadata" poster="cover.png" src="shorts-creator.mp4"></video><div class="guide" id="guide"><span>文字の安全域・表示UIの余白の目安</span></div></div><section><p class="eyebrow">SHORTS CREATOR / LOCAL PREVIEW</p><h1>__TITLE__</h1><p>短い言葉と動きで、伝わるテンポへ。</p><div class="controls"><button id="current" aria-pressed="true">改善版</button>__PREVIOUS__<button id="guides" aria-pressed="false">安全域を表示</button></div><p id="mode" class="note" aria-live="polite">改善版を表示中</p><div class="metrics"><div><strong>__SECONDS__秒</strong><span>1080 × 1920</span></div><div><strong>__SCENES__カット</strong><span>発話に合わせた構成</span></div><div><strong>__LUFS__</strong><span>LUFS 実測</span></div></div><ul><li>冒頭から主題を見せる、大きな動く見出し</li><li>短い字幕・意味の切れ目で変わる構図</li><li>声に合わせて下がるBGMと控えめな効果音</li><li>生成ツール名の表示なし</li></ul><div class="links"><a href="shorts-creator.mp4" download>動画を保存</a><a href="shorts-creator-review.zip" download>制作一式を保存</a><a href="captions.srt" download>字幕</a></div><details><summary>場面一覧を見る</summary><img src="contact-sheet.png" alt="完成映像の場面一覧"></details><p class="note">非公式の紹介動画。開発画面は図解で、実操作の録画ではありません。<br>字幕の細分化は発話区間内で文字量から配分しています。安全域は端末ごとに異なる表示UIを想定した制作上の目安です。<br>技術検証済み・内容と聴感は利用者確認用。YouTubeへの投稿はしていません。</p></section></main>
<script>const video=document.getElementById('video'),mode=document.getElementById('mode'),current=document.getElementById('current'),previous=document.getElementById('previous');function choose(src,label,old){video.pause();video.src=src;video.poster=old?'':'cover.png';video.load();mode.textContent=label;current.setAttribute('aria-pressed',String(!old));previous?.setAttribute('aria-pressed',String(old))}current.onclick=()=>choose('shorts-creator.mp4','改善版を表示中',false);if(previous)previous.onclick=()=>choose(previous.dataset.src,'以前の動画を表示中',true);document.getElementById('guides').onclick=function(){const on=this.getAttribute('aria-pressed')!=='true';this.setAttribute('aria-pressed',String(on));document.getElementById('guide').classList.toggle('show',on);this.textContent=on?'安全域を隠す':'安全域を表示'};</script></html>'''
    for key,value in {'TITLE':title,'PREVIOUS':previous,'SECONDS':str(story['duration_seconds']),'SCENES':str(len(props['scenes'])),'LUFS':loudness['input_i']}.items():page=page.replace('__'+key+'__',value)
    if any(scene.get('capture',{}).get('origin')=='official' for scene in story['scenes']):
        page=page.replace('非公式の紹介動画。開発画面は図解で、実操作の録画ではありません。',
            '公式資料の引用と自作の説明を含む解説動画です。引用画面の出典は動画と出典記録で確認できます。')
    (out/'index.html').write_text(page,encoding='utf-8')
    (out/'README_JA.txt').write_text(f"{story['title']}\n\n1080×1920 / 24fps / {story['duration_seconds']}秒\nローカル制作、生成ツール名の画面表示なし。\n発話実測による場面配置、フレーズ字幕、オリジナルBGM・効果音。\n音声：{story['voice']}、速度{story['rate']}。\nIntegrated loudness: {loudness['input_i']} LUFS / true peak: {loudness['input_tp']} dBFS\n\n字幕時刻の細分化は発話区間内の文字数配分で、単語アラインメントではありません。\n検証済み候補と利用者の採否は別に記録します。公開操作は行っていません。\n",encoding='utf-8')

def package(out):
    proof=read(out/'verification.json')
    if proof['review_status']!='verified_candidate_awaiting_user_review':raise ValueError('Visual review is required before packaging')
    check(proof['delivery'])
    files=['shorts-creator.mp4','cover.png','captions.srt','story.json','timings.json','verification.json','README_JA.txt']
    manifest={n:record(out/n) for n in files}
    with zipfile.ZipFile(out/'shorts-creator-review.zip','x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for name in files:z.write(out/name,name)
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(out/'shorts-creator-review.zip') as z:
        assert z.testzip() is None
        for name,item in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest().upper()==item['sha256']
    write(out/'package-verification.json',{'zip':record(out/'shorts-creator-review.zip'),'crc_and_hashes_verified':True})

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','make','finish','package'])
    parser.add_argument('--story',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--reuse-audio',type=Path,help='Verified previous output from this production; visual changes only')
    parser.add_argument('--narration-source',type=Path,help='Verified segmented Gemini narration; never submits an API request')
    args=parser.parse_args()
    if args.command in ['prepare','make']:
        if args.story is None:parser.error('--story is required')
        out=prepare(args.story,args.reuse_audio,args.narration_source)
        if args.command=='make':
            run('node',ROOT/'studio/creator-render.mjs',out)
            finish(out)
    else:
        if args.output is None:parser.error('--output is required')
        out=args.output.resolve(strict=True)
        if not out.is_relative_to(ROOT/'outputs/productions'):parser.error('Output must be inside outputs/productions')
        if args.command=='finish':finish(out)
        else:package(out)

if __name__=='__main__':main()
