"""Package the reviewed supplement without research snapshots or internal story paths."""
from pathlib import Path
import argparse
import hashlib
import html
import json
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve(strict=True)
    if out.parent != ROOT / 'outputs/productions/SHORT_20261021_dots_cloud_benefits':
        raise ValueError('Unexpected production output')
    proof = json.loads((out / 'verification.json').read_text(encoding='utf-8'))
    if proof['review_status'] != 'verified_candidate_awaiting_user_review' or not proof['full_decode_verified']:
        raise ValueError('Technical and visual review required before packaging')
    video = ROOT / proof['delivery']['path']
    if video.parent != out or digest(video) != {k: proof['delivery'][k] for k in ['bytes', 'sha256']}:
        raise ValueError('Reviewed delivery changed')
    release = out / 'release'
    release.mkdir(exist_ok=False)
    for source, name in [(video, 'dots-02-extra-cloud-benefits.mp4'),
                         (out / 'cover.png', 'cover.png'), (out / 'captions.srt', 'captions.srt')]:
        shutil.copyfile(source, release / name)
    for name in ['youtube-title.txt', 'youtube-description.txt', 'SOURCES_JA.md']:
        shutil.copyfile(HERE / name, release / name)
    story = json.loads((out / 'story.json').read_text(encoding='utf-8'))
    (release / 'narration.txt').write_text('\n'.join(s['narration'] for s in story['scenes']) + '\n', encoding='utf-8')
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(out / 'music.wav'),
                    '-c:a', 'libmp3lame', '-b:a', '192k', str(release / 'bgm-bright-groove.mp3')],
                   check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    public_proof = {k: proof[k] for k in ['full_decode_verified', 'loudness', 'review_status', 'user_approved']}
    public_proof.update(duration_seconds=45, width=1080, height=1920, fps=24, frames=1080,
                        music_preset='bright_groove_v1', music_bpm=112, youtube_uploaded=False,
                        visual_review=proof['visual_review']['note'], listening_review=proof['listening_review'],
                        information_checked_date='2026-10-21')
    (release / 'quality-report.json').write_text(json.dumps(public_proof, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    title = html.escape((HERE / 'youtube-title.txt').read_text(encoding='utf-8').strip())
    description = html.escape((HERE / 'youtube-description.txt').read_text(encoding='utf-8'))
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>dotsクラウドPCのメリット</title><style>*{box-sizing:border-box}body{margin:0;background:#0b1120;color:#f5f1e8;font-family:system-ui,"Yu Gothic UI",sans-serif}main{max-width:1100px;margin:auto;padding:32px 22px;display:grid;grid-template-columns:minmax(260px,390px) 1fr;gap:40px}video{width:100%;max-height:84vh;aspect-ratio:9/16;background:#050a15;border-radius:20px}h1{font-size:clamp(26px,3vw,40px);line-height:1.4}.tag,a{color:#dfff78}p{line-height:1.8}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.8 system-ui}audio{width:100%}.links{display:flex;gap:16px;flex-wrap:wrap;margin:24px 0}summary{cursor:pointer;font-size:18px}.note{font-size:14px;color:#b9c6d8}@media(max-width:720px){main{grid-template-columns:1fr}video{max-height:72vh}}</style>
<main><video controls playsinline preload="metadata" poster="cover.png" src="dots-02-extra-cloud-benefits.mp4"></video><section><p class="tag">DOTS 02 / 補足編 · 45秒</p><h1>__TITLE__</h1><p>電源に縛られない。作業の続きを保てる。スマホから頼める。<br>手元のPCで動くAIとの違いを紹介します。</p><div class="links"><a href="dots-02-extra-cloud-benefits.mp4" download>動画を保存</a><a href="captions.srt" download>字幕</a><a href="SOURCES_JA.md">出典と条件</a></div><p>変更したBGM：明るい112 BPMのオリジナル曲</p><audio controls preload="none" src="bgm-bright-groove.mp3"></audio><details><summary>YouTubeの見出し・説明欄</summary><pre>__TITLE__</pre><pre>__DESCRIPTION__</pre></details><p class="note">形式・音量・完成画面の検証済み候補。聴感と内容の最終採用は利用者確認用。YouTubeには投稿していません。情報確認日：2026年10月21日。映像は独自図解と架空のキャラクターです。</p></section></main></html>'''
    (release / 'index.html').write_text(page.replace('__TITLE__', title).replace('__DESCRIPTION__', description), encoding='utf-8')
    manifest = {p.name: digest(p) for p in sorted(release.iterdir()) if p.is_file()}
    (release / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive = out / 'dots-02-extra-cloud-benefits.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=3) as z:
        for p in sorted(release.iterdir()):
            z.write(p, p.name)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('ZIP CRC failed')
        for name, item in manifest.items():
            if hashlib.sha256(z.read(name)).hexdigest().upper() != item['sha256']:
                raise ValueError('ZIP bytes changed')
    for name in ['dots-02-extra-cloud-benefits.mp4', 'cover.png', 'captions.srt', 'SOURCES_JA.md', 'bgm-bright-groove.mp3']:
        if not (release / name).is_file():
            raise ValueError('Broken preview reference')
    result = {'release': release.relative_to(ROOT).as_posix(), 'video': digest(release / 'dots-02-extra-cloud-benefits.mp4'),
              'archive': {'path': archive.relative_to(ROOT).as_posix(), **digest(archive)},
              'crc_and_all_member_hashes_verified': True, 'archive_members': len(manifest) + 1,
              'local_preview_references_verified': True, 'user_approved': False, 'youtube_uploaded': False}
    (out / 'delivery.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (HERE / 'delivery.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
