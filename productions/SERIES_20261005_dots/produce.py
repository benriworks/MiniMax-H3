"""Prepare/render/review/package the dots series using the shared Shorts Creator."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import prepare,finish,check,read,record,run
HERE=Path(__file__).parent
STATE=HERE/'outputs.json'
SERIES_OUT=ROOT/'outputs/productions/SERIES_20261005_dots'

def save(p,value):
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def prepare_episodes(numbers):
    state=read(STATE) if STATE.exists() else {'episodes':{}}
    series=read(HERE/'series.json');errors=[]
    for number in numbers:
        ep=series['episodes'][number-1]
        try:
            out=prepare(ROOT/ep['story'])
            state['episodes'][str(number)]=out.relative_to(ROOT).as_posix()
            save(STATE,state)
        except (ValueError,subprocess.CalledProcessError,AssertionError) as e:
            print(json.dumps({'episode':number,'prepare_error':str(e)},ensure_ascii=False),flush=True)
            errors.append(number)
    if errors:raise SystemExit('Preparation failed: '+str(errors))

def episode_output(number):
    out=(ROOT/read(STATE)['episodes'][str(number)]).resolve(strict=True)
    if not out.is_relative_to(ROOT/'outputs/productions'):raise ValueError('Unexpected output')
    return out

def render_episode(number):
    out=episode_output(number)
    for source in read(out/'preparation.json')['sources']:check(source)
    log=out/'production.log'
    with log.open('a',encoding='utf-8') as f:
        if not (out/'render.json').exists():
            subprocess.run(['node',str(ROOT/'studio/creator-render.mjs'),str(out)],cwd=ROOT,check=True,
                           stdout=f,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if not (out/'verification.json').exists():finish(out)
    print(json.dumps({'event':'episode_rendered','number':number,'output':str(out)},ensure_ascii=False),flush=True)

def record_review(numbers,note):
    if not note:raise ValueError('Provide a concrete visual review note after inspecting the actual frames')
    for number in numbers:
        out=episode_output(number);proof=read(out/'verification.json')
        check(proof['delivery'])
        proof.update(review_status='verified_candidate_awaiting_user_review',user_approved=False,
                     visual_review={'reviewed_at':datetime.now(timezone.utc).isoformat(),'note':note,
                                    'evidence':[record(out/'contact-sheet.png')]+[record(p) for p in sorted(out.glob('preview-*.png'))]},
                     listening_review='User listening review pending; measured duration, no truncation, loudness and peak verified.',
                     fact_review={'checked_date':'2026-10-05','source_ledger':record(HERE/'SOURCES_JA.md')})
        save(out/'verification.json',proof)

def gallery(series):
    cards=[]
    for ep in series['episodes']:
        num=ep['number'];folder=f'{num:02d}';title=html.escape(ep['topic'])
        description=html.escape((HERE/folder/'youtube-description.txt').read_text(encoding='utf-8'))
        yt_title=html.escape((HERE/folder/'youtube-title.txt').read_text(encoding='utf-8').strip())
        cards.append(f'''<article><p class="number">DOTS {num:02d} / 09</p><h2>{title}</h2><video controls playsinline preload="none" poster="{folder}/cover.png" src="{folder}/dots-{folder}.mp4"></video><div class="links"><a href="{folder}/dots-{folder}.mp4" download>MP4</a><a href="{folder}/cover.png" download>カバー</a><a href="{folder}/captions.srt" download>字幕</a></div><details><summary>YouTubeのタイトル・説明欄</summary><h3>タイトル</h3><pre>{yt_title}</pre><h3>説明欄</h3><pre>{description}</pre><a href="{folder}/youtube-description.txt" download>説明欄を保存</a></details></article>''')
    return '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>dotsを30秒ずつ。</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b1120;color:#f5f1e8;font-family:system-ui,"Yu Gothic UI",Meiryo,sans-serif}main{max-width:1240px;margin:auto;padding:42px 24px 80px}header{max-width:880px;margin-bottom:44px}h1{font-size:clamp(34px,6vw,68px);letter-spacing:-.05em;margin:12px 0}p{line-height:1.8}.lead{font-size:20px}.number{color:#dfff78;letter-spacing:.12em;font-weight:800;font-size:14px;margin:0}a{color:#dfff78}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:28px}article{background:#152136;padding:22px;border-radius:22px;min-width:0}h2{font-size:24px;margin:9px 0 20px}video{width:100%;aspect-ratio:9/16;display:block;border-radius:14px;background:#060b15}.links{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0}.links a,.download{display:inline-block;padding:9px 16px;border:1px solid #536147;border-radius:9px;text-decoration:none}.download{background:#dfff78;color:#0b1120;font-weight:800}summary{cursor:pointer;line-height:1.7;font-size:15px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.8 system-ui,"Yu Gothic UI",sans-serif;padding:14px;background:#0b1120;border-radius:8px}h3{font-size:16px}footer{margin-top:42px;color:#aab6cb;font-size:14px;line-height:1.9}@media(max-width:920px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:590px){.grid{grid-template-columns:1fr}main{padding:28px 18px}article{max-width:440px;width:100%;margin:auto}}
</style><main><header><p class="number">9 SHORTS · 30 SECONDS EACH</p><h1>dotsを30秒ずつ。</h1><p class="lead">発表日から、クラウドPC、記憶、定期実行まで。<br>機能をひとつずつ知る、全9本のショートシリーズ。</p><p>各1080 × 1920・30秒／日本語ナレーションと字幕付き。<br>情報確認日：2026年10月5日。技術・画面検証済みの確認用候補です。</p><div class="links"><a class="download" href="../dots-shorts-series.zip" download>全9本・公開用ファイルを保存</a><a href="SOURCES_JA.md">公式出典・機能の条件</a><a href="YOUTUBE_UPLOAD_JA.md">公開手順と一覧</a></div></header><section class="grid">'''+''.join(cards)+'''</section><footer>OpenAI公式資料をもとにした非公式の紹介動画。図は独自のモーショングラフィックスで、実機録画ではありません。<br>公開用ZIPには動画、カバー、字幕、タイトル、説明欄、台詞、出典、ファイル照合用の一覧を収録しています。<br>内容・聴感の最終採否は利用者確認用。YouTubeへのアップロードは行っていません。</footer></main><script>document.querySelectorAll('video').forEach(v=>v.addEventListener('play',()=>document.querySelectorAll('video').forEach(o=>{if(o!==v)o.pause()})));</script></html>'''

def package_series():
    series=read(HERE/'series.json')
    for ep in series['episodes']:
        out=episode_output(ep['number']);proof=read(out/'verification.json')
        if proof['review_status']!='verified_candidate_awaiting_user_review':raise ValueError('Visual review missing')
        check(proof['delivery'])
        for source in read(out/'preparation.json')['sources']+read(out/'render.json')['sources']:check(source)
    dest=SERIES_OUT/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');release=dest/'release';release.mkdir(parents=True)
    reports=[]
    for ep in series['episodes']:
        num=ep['number'];out=episode_output(num);folder=release/f'{num:02d}';folder.mkdir()
        for source,name in [(out/'shorts-creator.mp4',f'dots-{num:02d}.mp4'),(out/'cover.png','cover.png'),(out/'captions.srt','captions.srt')]:shutil.copyfile(source,folder/name)
        for name in ['youtube-title.txt','youtube-description.txt','narration.txt']:shutil.copyfile(HERE/f'{num:02d}'/name,folder/name)
        proof=read(out/'verification.json')
        reports.append({'number':num,'topic':ep['topic'],'duration_seconds':30,'frames':720,'size':'1080x1920','fps':24,
                        'full_decode_verified':proof['full_decode_verified'],'lufs':proof['loudness']['input_i'],'true_peak_dbfs':proof['loudness']['input_tp'],
                        'visual_reviewed':True,'user_approved':False,'mp4_sha256':proof['delivery']['sha256']})
    shutil.copyfile(HERE/'SOURCES_JA.md',release/'SOURCES_JA.md')
    shutil.copyfile(HERE/'YOUTUBE_UPLOAD_JA.md',release/'YOUTUBE_UPLOAD_JA.md')
    for name in ['playlist-title.txt','playlist-description.txt']:shutil.copyfile(HERE/name,release/name)
    # The extracted gallery only links to files contained in the archive.
    page=gallery(series).replace('<a class="download" href="../dots-shorts-series.zip" download>全9本・公開用ファイルを保存</a>','')
    (release/'index.html').write_text(page,encoding='utf-8')
    (release/'README_JA.txt').write_text('dotsを30秒ずつ。全9本\n\nindex.htmlで一覧と動画を確認できます。各番号フォルダーのMP4がアップロード対象です。字幕は映像にも入っています。SRTをYouTubeで追加するかは任意です。詳細はYOUTUBE_UPLOAD_JA.mdを参照してください。\n\n情報確認日：2026年10月5日。YouTube未投稿・利用者の最終確認待ち。各30秒・1080×1920・24fps・H.264/AAC。\n',encoding='utf-8')
    save(release/'quality-report.json',reports)
    manifest={p.relative_to(release).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest().upper()} for p in sorted(release.rglob('*')) if p.is_file()}
    save(release/'manifest.json',manifest)
    # The archive opens as a self-contained gallery, without a broken link to itself.
    zip_path=dest/'dots-shorts-series.zip'
    with zipfile.ZipFile(zip_path,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for p in sorted(release.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(release).as_posix())
    with zipfile.ZipFile(zip_path) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for name,item in manifest.items():
            if hashlib.sha256(z.read(name)).hexdigest().upper()!=item['sha256']:raise ValueError('ZIP hash failed')
    save(dest/'package-verification.json',{'archive':record(zip_path),'crc_and_hashes_verified':True,'release_manifest':record(release/'manifest.json'),'episodes':reports,'user_approved':False})
    save(HERE/'delivery.json',{'release':release.relative_to(ROOT).as_posix(),'archive':record(zip_path),'gallery':record(release/'index.html')})
    print(json.dumps({'event':'series_packaged','release':str(release),'archive':str(zip_path)},ensure_ascii=False),flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','render','review','package'])
    parser.add_argument('--episodes',type=int,nargs='+',default=list(range(1,10)))
    parser.add_argument('--jobs',type=int,choices=[1,2,3],default=1)
    parser.add_argument('--note')
    args=parser.parse_args()
    if not all(1<=n<=9 for n in args.episodes):parser.error('Episode must be 1–9')
    if args.command=='prepare':prepare_episodes(args.episodes)
    elif args.command=='render':
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:list(pool.map(render_episode,args.episodes))
    elif args.command=='review':record_review(args.episodes,args.note)
    else:package_series()

if __name__=='__main__':main()
