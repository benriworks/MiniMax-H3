"""Build frame-exact review candidates from the frozen case scripts and assets."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np

from generate_voices import CASE, ROOT, OUT, read_scripts, voice_dir
from visuals import Renderer, PEOPLE, PROTECTED_TERMS, TITLES
from tools.studio.editorial_captions import timed_captions
from tools.studio.longform_audio import SR, read_voice, write_pcm, music
from tools.studio.music_mix import music_gain_envelope

FPS = 24
REVISIONS = {'full':'v02', 'short':'v02'}
OUTPUT_ROOT = OUT/'release'


def hash_file(path):
    h = sha256()
    with path.open('rb') as file:
        for block in iter(lambda: file.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr[-3500:])
    return result


def folder(kind):
    return OUTPUT_ROOT / REVISIONS[kind] / kind


def make_timeline(kind):
    scripts, _ = read_scripts(REVISIONS['short'])
    short = kind == 'short'
    rows = scripts[kind]
    durations = [len(read_voice(voice_dir(row) / 'voice.wav')) / SR for row in rows]
    end_hold = 2.6 if short else 10.0
    lead, tail = (.14, .38) if short else (.12, .43)
    if short:
        extra = max(0, 59.5 - end_hold - sum(durations) - len(rows) * (lead + tail))
        weights = (1, 2, 2, 2, 3, 2, 3, 1)
        holds = [extra * w / sum(weights) for w in weights]
    else:
        holds = [(.70 if row['visual'] in ('rank', 'split', 'identity', 'step1', 'evidence') else .20)
                 for row in rows]
    cursor = 0
    turns = []
    for row, seconds, hold in zip(rows, durations, holds, strict=True):
        voice_start = cursor / FPS + lead
        frame_count = math.ceil((lead + seconds + tail + hold) * FPS)
        captions = timed_captions(row['text'], voice_start, seconds, 868 if short else 1580,
                                  54 if short else 50, protected=PROTECTED_TERMS)
        turns.append(row | dict(start_frame=cursor, end_frame=cursor + frame_count,
                                voice_start=voice_start, voice_seconds=seconds, captions=captions,
                                voice_path=(voice_dir(row) / 'voice.wav').relative_to(ROOT).as_posix()))
        cursor += frame_count
    frames = cursor + round(end_hold * FPS)
    return dict(kind=kind, title=TITLES[kind], version=REVISIONS[kind], fps=FPS, frames=frames,
                body_frames=cursor, end_hold=(frames-cursor)/FPS, seconds=frames/FPS,
                width=1080 if short else 1920, height=1920 if short else 1080,
                alignment='PCM turn boundaries; phrase-weighted caption timing', turns=turns)


def state_segments(timeline):
    """Only the character portions need dense updates."""
    for row in timeline['turns']:
        start, end = row['start_frame'], row['end_frame']
        marks = {start, end}
        marks.update(min(end, start+round(t*FPS)) for t in (2.0, 2.4, 3.2, 5.0))
        for caption in row['captions']:
            marks.update((math.ceil(caption['start']*FPS), math.ceil(caption['end']*FPS)))
        if row['id'] in PEOPLE:
            marks.update(range(start, min(start+112, end), 2))
        cuts = sorted(marks)
        for a, b in zip(cuts, cuts[1:]):
            if b > a:
                yield row, a, b
    yield None, timeline['body_frames'], timeline['frames']


def stage(kind, still_only=False):
    timeline = make_timeline(kind)
    directory = folder(kind)
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / 'video-only.mp4'
    if output.exists():
        raise FileExistsError(output)
    renderer = Renderer(kind, focused_quotes=timeline['version']=='v02')
    shots = directory / 'shots'
    shots.mkdir(exist_ok=True)
    playlist = ['ffconcat version 1.0']
    intervals = []
    for index, (row, a, b) in enumerate(state_segments(timeline)):
        # Dry-check every layout, without JPEG encoding each repeated motion frame.
        local = (a - row['start_frame'])/FPS if row is not None else 0
        p = shots / f'{index:05d}.jpg'
        try:
            frame = renderer.frame(row, local, a/FPS, a/timeline['frames'])
        except ValueError as exc:
            raise ValueError(f'{kind} {(row or {}).get("id", "end")} at {a/FPS:.3f}: {exc}') from exc
        if not still_only:
            frame.save(p, quality=94, subsampling=0)
        playlist += [f"file 'shots/{p.name}'", 'option framerate 24', f'duration {(b-a)/FPS:.9f}']
        intervals.append({'file':p.name, 'turn':(row or {}).get('id','end'), 'start_frame':a, 'end_frame':b})
    save(directory / 'timeline.json', timeline)
    save(directory / 'layout-audit.json', list(renderer.canvas.audit.values()))
    save(directory / 'image-timing.json', intervals)
    print(kind, 'stills', len(intervals), 'seconds', timeline['seconds'], flush=True)
    if still_only:
        return
    playlist += [f"file 'shots/{p.name}'", 'option framerate 24']
    sequence = directory / 'sequence.ffconcat'
    sequence.write_text('\n'.join(playlist)+'\n', encoding='utf-8')
    run(['ffmpeg','-v','error','-nostdin','-n','-f','concat','-safe','0','-i',str(sequence),
         '-vf','fps=24,format=yuv420p','-frames:v',str(timeline['frames']),'-an','-c:v','libx264',
         '-preset','veryfast','-crf','19','-movflags','+faststart',str(output)])
    print(kind, 'video track', output.stat().st_size, flush=True)


def meter(path):
    result = run(['ffmpeg','-hide_banner','-nostdin','-i',str(path),'-af',
                  'loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-'])
    return json.JSONDecoder().raw_decode(result.stderr[result.stderr.rfind('{'):])[0]


def audio(kind):
    timeline = make_timeline(kind)
    directory = folder(kind)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory/'mix.wav').exists():
        raise FileExistsError(directory/'mix.wav')
    seconds = timeline['seconds']
    total = round(seconds*SR)
    speech = np.zeros(total, dtype=np.float32)
    ranges = []
    levels = []
    for turn in timeline['turns']:
        path = ROOT / turn['voice_path']
        pcm = read_voice(path)
        active = pcm[np.abs(pcm)>.012]
        if not len(active):
            raise ValueError(f'Silent voice {turn["id"]}')
        rms = float(np.sqrt(np.mean(active**2)))
        gain = min(.13/rms, .72/float(np.max(np.abs(pcm))))
        start = round(turn['voice_start']*SR)
        speech[start:start+len(pcm)] = pcm*gain
        ranges.append((turn['voice_start'], turn['voice_start']+len(pcm)/SR))
        levels.append(dict(turn=turn['id'], speaker=turn['speaker'], seconds=len(pcm)/SR,
                           gain=gain, active_rms=rms*gain, sha256=hash_file(path)))
    bed = music(seconds, fade_in_seconds=.8, fade_out_seconds=2.2)
    write_pcm(directory/'bgm-unmixed.wav', bed)
    loud = float(meter(directory/'bgm-unmixed.wav')['input_i'])
    bed *= 10**((-30-loud)/20)
    bed *= music_gain_envelope(seconds, ranges, base_gain=1., duck_gain=.88,
                               edge_boost_db=0., attack_seconds=.24, release_seconds=1.35)[:,None]
    mix = speech[:,None] + bed
    write_pcm(directory/'narration.wav', speech)
    write_pcm(directory/'mix.wav', mix)
    save(directory/'audio-provenance.json', dict(source='tools.studio.longform_audio.music',
         external_samples=False, target_bed_lufs=-30, duck_gain=.88, edge_boost_db=0,
         release_seconds=1.35, max_pre_master_peak=float(np.max(np.abs(mix))), levels=levels))
    print(kind, 'audio mix', seconds, flush=True)


def mux(kind):
    directory = folder(kind)
    timeline = json.loads((directory/'timeline.json').read_text(encoding='utf-8'))
    version = REVISIONS[kind]
    target = directory/f'ai-japan-data-breaches-2026-{kind}-{version}.mp4'
    stats = meter(directory/'mix.wav')
    filt = ('loudnorm=I=-16:TP=-1.5:LRA=9:measured_I='+stats['input_i']+':measured_TP='+stats['input_tp']+
            ':measured_LRA='+stats['input_lra']+':measured_thresh='+stats['input_thresh']+
            ':offset='+stats['target_offset']+':linear=true')
    run(['ffmpeg','-v','error','-nostdin','-n','-i',str(directory/'video-only.mp4'),
         '-i',str(directory/'mix.wav'),'-map','0:v:0','-map','1:a:0','-c:v','copy',
         '-af',filt,'-c:a','aac','-b:a','192k','-ar','48000','-t',str(timeline['seconds']),
         '-movflags','+faststart',str(target)])
    run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(target),'-f','null','-'])
    probe = json.loads(run(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(target)]).stdout)
    video = next(s for s in probe['streams'] if s['codec_type']=='video')
    assert (video['width'], video['height'], int(video['nb_frames'])) == (
        timeline['width'], timeline['height'], timeline['frames'])
    assert abs(float(probe['format']['duration'])-timeline['seconds'])<.08
    levels = meter(target)
    assert -18. < float(levels['input_i']) < -14. and float(levels['input_tp']) <= -1.
    layout = json.loads((directory/'layout-audit.json').read_text(encoding='utf-8'))
    assert layout and all(x['fits'] for x in layout)
    qc = dict(kind=kind, revision=version, file=target.name, sha256=hash_file(target),
              bytes=target.stat().st_size, seconds=timeline['seconds'], frames=timeline['frames'],
              width=video['width'],height=video['height'],fps=FPS, full_decode=True,
              layout_states=len(layout), final_aac_loudness=levels, human_reviewed=False,
              user_approved=False,published=False)
    save(directory/'qc.json', qc)
    print(json.dumps(qc, ensure_ascii=False), flush=True)


def main():
    global OUTPUT_ROOT
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan','stills','video','audio','mux'])
    parser.add_argument('kind', choices=['short','full'])
    parser.add_argument('--version', choices=['v01','v02'])
    parser.add_argument('--run', help='Separate local reproduction folder')
    args = parser.parse_args()
    if args.run:
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,45}', args.run):
            parser.error('Run name must contain lowercase letters, digits or dashes')
        OUTPUT_ROOT = OUT/'reproduction'/args.run
    if args.version:
        REVISIONS[args.kind] = args.version
    if args.action == 'plan':
        timeline = make_timeline(args.kind)
        print(timeline['seconds'], sum(t['voice_seconds'] for t in timeline['turns']))
    elif args.action in ('stills','video'):
        stage(args.kind, still_only=args.action=='stills')
    else:
        (audio if args.action=='audio' else mux)(args.kind)


if __name__ == '__main__':
    main()
