"""Editorial clips from actual cloud Blender renders, separate from GUI proofs."""
from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import record


def run(*args):
    subprocess.run([str(a) for a in args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def filter_path(path):
    return str(path.resolve()).replace('\\', '/').replace(':', '\\:')


def build():
    source = OUT / 'cloud/v01/dots-desktop-pilot-20261025/blender'
    dest = OUT / 'editorial/blender-v01'
    dest.mkdir(parents=True, exist_ok=True)
    # A portrait canvas preserves the entire plate instead of cropping the model.
    canvas = 'scale=1080:848,pad=1080:1920:0:590:color=0xe8e2d9,setsar=1,fps=24'
    for name, label in [('initial', '修正前'), ('thicker_anko', 'あんこを30％厚く')]:
        target = dest / (name + '.mp4')
        if target.exists():
            raise ValueError('Preserve existing editorial output; use a new version')
        text = dest / (name + '.txt')
        text.write_text(label, encoding='utf-8')
        font = Path('C:/Windows/Fonts/meiryo.ttc')
        draw = f"drawtext=fontfile='{filter_path(font)}':textfile='{filter_path(text)}':fontsize=56:fontcolor=0x183e34:box=1:boxcolor=white@0.90:boxborderw=18:x=90:y=680"
        run('ffmpeg', '-v', 'error', '-nostdin', '-loop', '1', '-i', source / ('dorayaki_' + name + '.png'),
            '-vf', canvas + ',' + draw, '-t', '5.5', '-an', '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', target)
        run('ffmpeg', '-v', 'error', '-xerror', '-i', target, '-f', 'null', '-')
        run('ffmpeg', '-v', 'error', '-ss', '1', '-i', target, '-frames:v', '1', dest / (name + '-review.png'))
    # Two unchanged camera views; only the cut and labels are editorial.
    compare = dest / 'comparison.mp4'
    graph = '[0:v]trim=duration=2.5,setpts=PTS-STARTPTS[a];[1:v]trim=duration=3,setpts=PTS-STARTPTS[b];[a][b]concat=n=2:v=1:a=0[v]'
    run('ffmpeg', '-v', 'error', '-nostdin', '-i', dest / 'initial.mp4', '-i', dest / 'thicker_anko.mp4',
        '-filter_complex', graph, '-map', '[v]', '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', compare)
    run('ffmpeg', '-v', 'error', '-xerror', '-i', compare, '-f', 'null', '-')
    (dest / 'generation.json').write_text(json.dumps(dict(
        kind='editorial_video_from_blender_render',
        continuous_gui_recording=False,
        sources=[record(source / ('dorayaki_' + n + '.png')) for n in ('initial', 'thicker_anko')],
        artifacts=[record(dest / (n + '.mp4')) for n in ('initial', 'thicker_anko', 'comparison')],
        full_decode_verified=True, visual_review='pending'), ensure_ascii=False, indent=2), encoding='utf-8')
    print(dest)


if __name__ == '__main__':
    build()
