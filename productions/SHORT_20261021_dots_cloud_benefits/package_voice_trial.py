"""Create a level-matched, no-BGM voice audition from verified Gemini WAVs."""
from pathlib import Path
import argparse
import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BASE = ROOT / 'outputs/productions/SHORT_20261021_dots_cloud_benefits/gemini-trials'
TITLE = '【ChatGPT】dots解説の声を比較！Geminiナレーションを試してみた'
FONT = Path('C:/Windows/Fonts/meiryob.ttc')


def record(p):
    return {'path': p.relative_to(ROOT).as_posix(), 'bytes': p.stat().st_size,
            'sha256': hashlib.sha256(p.read_bytes()).hexdigest().upper()}


def run(*args):
    return subprocess.run(list(map(str, args)), cwd=ROOT, check=True, capture_output=True,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def measure(path):
    result = run('ffmpeg', '-hide_banner', '-nostdin', '-i', path, '-af',
                 'loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json', '-f', 'null', '-')
    return json.loads(re.findall(r'\{[\s\S]*?\}', result.stderr.decode())[-1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--revision', default='comparison-v2')
    args = parser.parse_args()
    out = args.output.resolve(strict=True)
    if out.parent != BASE:
        raise ValueError('Unexpected trial output')
    if not re.fullmatch(r'comparison-[a-z0-9-]+', args.revision):
        raise ValueError('Invalid comparison revision name')
    results = json.loads((out / 'results.json').read_text(encoding='utf-8'))
    for voice in results['voices']:
        for source in voice['files']:
            if record(ROOT / source['path']) != source:
                raise ValueError('Verified voice input changed')
    plan = json.loads((out / 'plan.json').read_text(encoding='utf-8'))
    work = out / args.revision
    work.mkdir(exist_ok=False)
    release = work / 'release'
    release.mkdir()
    font = work / 'meiryob.ttc'
    shutil.copyfile(FONT, font)
    rel = lambda p: p.relative_to(ROOT).as_posix()
    def draw_line(name, content, size, x, y, color):
        file = work / (name + '.txt')
        file.write_text(content, encoding='utf-8')
        return (f'drawtext=fontfile={rel(font)}:textfile={rel(file)}:'
                f'fontsize={size}:fontcolor={color}:x={x}:y={y}')
    (release / 'youtube-title.txt').write_text(TITLE + '\n', encoding='utf-8')
    (release / 'transcript.txt').write_text(plan['transcript'] + '\n', encoding='utf-8')
    narration_lines = ['クラウドPC、何が便利？', '手元で動くAIと、', '作業場所が違います。',
                       'クラウドの作業は、', 'PCを切っても', '続けられます。']
    (release / 'display-transcript.txt').write_text('\n'.join(narration_lines), encoding='utf-8')
    common_lines = [draw_line('heading-1', '同じ原稿で', 54, 46, 205, '0xf5f1e8'),
                    draw_line('heading-2', '音声を聴き比べ', 54, 46, 285, '0xf5f1e8')]
    transcript_lines = [draw_line(f'transcript-{i}', line, 38, 46, 600 + i * 65, '0xf5f1e8')
                        for i, line in enumerate(narration_lines)]
    note_lines = [draw_line('note-1', 'BGMなし', 36, 46, 1060, '0xaebbd0'),
                  draw_line('note-2', '音量をそろえて比較', 36, 46, 1120, '0xaebbd0')]
    entries = [('windows-sayaka', '現在の音声 / Windows Sayaka', out / 'windows-sayaka.wav'),
               ('gemini-kore', 'Gemini / Kore', out / 'Kore/voice.wav'),
               ('gemini-aoede', 'Gemini / Aoede', out / 'Aoede/voice.wav')]
    reports = []
    clips = []
    for index, (slug, label, source) in enumerate(entries):
        measured = measure(source)
        normalizer = ('loudnorm=I=-16:TP=-1.5:LRA=9:linear=true:'
                      f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
                      f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
                      f"offset={measured['target_offset']}")
        audio = release / (slug + '.wav')
        run('ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', source, '-af', normalizer,
            '-ar', '48000', '-ac', '1', '-c:a', 'pcm_s16le', audio)
        with wave.open(str(audio), 'rb') as wav:
            seconds = wav.getnframes() / wav.getframerate()
        frames = math.ceil((seconds + .65) * 24)
        filters = ','.join([
            'drawbox=x=46:y=168:w=628:h=8:color=0xdfff78:t=fill',
            *common_lines,
            'drawbox=x=46:y=398:w=628:h=144:color=0x1c2940:t=fill',
            draw_line(slug + '-count', f'{index + 1:02} / 03', 36, 70, 418, '0xdfff78'),
            draw_line(slug + '-label', label, 36, 70, 476, '0xdfff78'),
            *transcript_lines, *note_lines])
        clip = work / (slug + '.mp4')
        run('ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'lavfi', '-i',
            'color=c=0x0b1120:s=720x1280:r=24', '-i', audio, '-vf', filters,
            '-af', 'adelay=150,apad', '-frames:v', frames, '-t', frames / 24,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', clip)
        clips.append(clip)
        final_audio = measure(clip)
        if not -18 <= float(final_audio['input_i']) <= -14 or float(final_audio['input_tp']) > -1:
            raise ValueError('Audition loudness or peak is outside limits')
        reports.append({'voice': label, 'source': record(source), 'audio': record(audio),
                        'speech_duration_seconds': seconds, 'frames': frames, 'loudness': final_audio})
    concat = work / 'audition-concat.txt'
    concat.write_text(''.join(f"file '{p.name}'\n" for p in clips), encoding='utf-8')
    video = release / 'gemini-voice-comparison.mp4'
    run('ffmpeg', '-v', 'error', '-nostdin', '-n', '-f', 'concat', '-safe', '1', '-i', concat,
        '-c', 'copy', '-movflags', '+faststart', video)
    run('ffmpeg', '-v', 'error', '-nostdin', '-xerror', '-i', video, '-f', 'null', '-')
    probe = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', video).stdout)
    visual, audio = probe['streams']
    if (visual['codec_name'], visual['width'], visual['height'], visual['avg_frame_rate'], int(visual['nb_frames'])) != ('h264', 720, 1280, '24/1', sum(r['frames'] for r in reports)) or audio['codec_name'] != 'aac':
        raise ValueError('Unexpected audition MP4 format')
    duration = float(probe['format']['duration'])
    if abs(duration - sum(r['frames'] for r in reports) / 24) > .05:
        raise ValueError('Concatenated audition duration mismatch')
    run('ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', video, '-vf', 'fps=1,scale=180:320,tile=8x4',
        '-frames:v', '1', work / 'contact-sheet.png')
    seconds = 0
    for index, item in enumerate(reports):
        run('ffmpeg', '-v', 'error', '-nostdin', '-n', '-ss', seconds + 1, '-i', video,
            '-frames:v', '1', '-vf', 'scale=360:640', work / f'preview-{index:02}.png')
        seconds += item['frames'] / 24
    cards = ''.join(f'<p>{html.escape(label)}</p><audio controls preload="none" src="{slug}.wav"></audio>' for slug, label, _ in entries)
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Geminiナレーションの聴き比べ</title><style>body{margin:0;background:#0b1120;color:#f5f1e8;font:18px/1.8 system-ui,"Yu Gothic UI",sans-serif}main{max-width:1000px;margin:auto;padding:28px;display:grid;grid-template-columns:minmax(240px,350px) 1fr;gap:32px}video{width:100%;max-height:85vh;border-radius:18px}audio{width:100%}h1{font-size:30px;line-height:1.5}a{color:#dfff78}pre{white-space:pre-wrap;font:inherit}@media(max-width:720px){main{grid-template-columns:1fr}video{max-height:65vh}}</style><main><video controls playsinline preload="metadata" src="gemini-voice-comparison.mp4"></video><section><h1>同じ原稿で、声を聴き比べ。</h1><p>Windows Sayaka → Gemini Kore → Gemini Aoede。BGMなしで音量をそろえています。</p>__CARDS__<pre>__TRANSCRIPT__</pre><a href="gemini-voice-comparison.mp4" download>比較動画を保存</a><p>自然さ・読み方・好みは試聴してご判断ください。利用者による採用とYouTube公開は未確認です。</p></section></main></html>'''
    (release / 'index.html').write_text(page.replace('__CARDS__', cards).replace('__TRANSCRIPT__', html.escape(plan['transcript'])), encoding='utf-8')
    result = {'status': 'technically_verified_listening_pending', 'video': record(video), 'duration_seconds': duration,
              'full_decode_verified': True, 'reports': reports, 'model': plan['model'],
              'gemini_generation_requests': 2, 'usage': [v['usage'] for v in results['voices']],
              'music': False, 'level_matching': 'two-pass loudnorm to -16 LUFS and -1.5 dBTP',
              'user_approved': False, 'youtube_uploaded': False}
    save_path = work / 'comparison-verification.json'
    save_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = {p.name: record(p) for p in release.iterdir() if p.is_file()}
    (release / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'video': result['video'], 'duration_seconds': duration,
                      'release': rel(release)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
