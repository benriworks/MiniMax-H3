"""Three bounded visual revisions; preserve the adopted audio bitstream and timing."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
from graphics import plate,font,INK,WHITE,LIME
from tools.studio.text_layout import fit_explicit_lines
OLD=ROOT/'outputs/productions'/HERE.name/'v03';OUT=OLD.parent/'v04';FPS=24


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(dest,args,*,cwd=None):
    with dest.with_suffix('.log').open('w',encoding='utf-8') as log:
        subprocess.run(args,cwd=cwd,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def prepare():
    if (OUT/'visual-revision.json').exists():raise ValueError('Existing prepared revision; inspect rather than overwrite')
    out=OUT/'graphics';out.mkdir(parents=True,exist_ok=True)
    # This PNG is an exact decoded source frame. It changes no captured UI pixels.
    raw=ROOT/'outputs/productions'/HERE.name/'v01/cloud/recordings/scene04-demo001.mp4'
    real=OUT/'captures/original/entry-complete-15.1.png';real.parent.mkdir(parents=True,exist_ok=True)
    run(real,['ffmpeg','-v','error','-nostdin','-n','-ss','15.1','-i',str(raw),'-frames:v','1',str(real)])
    heading=Image.new('RGBA',(1920,1080));draw=ImageDraw.Draw(heading)
    draw.rounded_rectangle((64,68,620,296),radius=22,fill=(7,24,53,228),outline=(116,153,194,180),width=2)
    draw.text((98,91),'Excelの3件を',font=font(64),fill=WHITE)
    draw.text((98,181),'案件管理へ',font=font(64),fill=LIME)
    heading.save(out/'opening-heading.png')
    note='実物のXLSX\n専用ビューアで表示\nExcel本体ではない'
    panel=plate(2,'クラウドPCを作業場所に',note,semantic_lines=True)
    overlay=Image.new('RGBA',(1920,1080));overlay.paste(panel.crop((1400,220,1851,826)),(1400,220))
    overlay.save(out/'viewer-note-overlay.png')
    confirmation=plate(6,'一件目を入力する','未登録の入力内容\n11月10日・12万円\n入力完了時の実画面\n静止して確認',semantic_lines=True)
    confirmation.save(out/'input-review-plate.png')
    changes=[dict(id='opening_heading',start_frame=0,end_frame=120,mode='overlay',image='graphics/opening-heading.png',
            reason='冒頭0〜5秒に題材を示す短い見出し。人物の顔と手を避ける。'),
        dict(id='viewer_note',start_frame=772,end_frame=1204,mode='overlay',image='graphics/viewer-note-overlay.png',
            reason='右の編集説明だけを意味ごとに改行。元のアプリ画面は変更しない。'),
        dict(id='unobscured_input_review',start_frame=3051,end_frame=3147,mode='real_still',image='graphics/input-review-plate.png',capture=real.relative_to(OUT).as_posix(),
            reason='同じ実録画15.1秒の入力完了フレーム。5項目が読める。確認画面とは呼び替えず、明示した静止説明。')]
    old=OLD/'dots-transfer-detail-v03.mp4';plan=json.loads((OLD/'timeline.json').read_text(encoding='utf-8'))
    assert plan['frames']==5955 and plan['seconds']==248.125
    save(OUT/'visual-revision.json',dict(version='v04',adopted_source_version='v03',frames=5955,seconds=248.125,changes=changes,
        source_video=dict(path=old.relative_to(ROOT).as_posix(),sha256=sha(old)),
        actual_frame=dict(path=real.relative_to(ROOT).as_posix(),sha256=sha(real),source_path=raw.relative_to(ROOT).as_posix(),source_sha256=sha(raw),source_seconds=15.1,
            content_modified=False,source_type='decoded real GUI recording frame',shows='completed input form, before confirmation and saving'),
        note_layout=fit_explicit_lines(note,375,lambda line,size:font(size).getlength(line)),audio_strategy='copy adopted v03 AAC bitstream',
        additional_tts_calls=0,additional_minimax_calls=0,new_capture='No new application capture. Existing real input-complete frame selected as expressly allowed by user.',
        capture_inspection='Current PC app/browser inventory checked. No live cloud-PC browser tab present. Existing recording inspected at 30 source times. No form submission or registration performed.'))
    for name in ['timeline.json','captions.ass','captions.srt','cut-map.json','pip-policy-audit.json']:
        shutil.copy2(OLD/name,OUT/name)
    shutil.copytree(OLD/'fonts',OUT/'fonts')
    print('Prepared exactly three visual intervals; adopted audio and 248.125-second timeline unchanged',flush=True)


def render():
    dest=OUT/'dots-transfer-detail-v04.mp4'
    if dest.exists():raise ValueError('Preserve completed revision')
    data=json.loads((OUT/'visual-revision.json').read_text(encoding='utf-8'))
    folder=OUT/'segments';folder.mkdir(exist_ok=True);segments=[];cursor=0
    source=OLD/'picture-master.mp4'
    def segment(a,b,change=None):
        target=folder/f'{a:04d}-{b:04d}.mp4';seconds=(b-a)/FPS
        args=['ffmpeg','-v','warning','-nostdin','-n']
        if change and change['mode']=='real_still':
            args+=['-loop','1','-framerate','24','-i',str(OUT/change['capture']),'-i',str(OUT/change['image']),'-filter_complex',
                '[0:v]scale=1280:650:force_original_aspect_ratio=decrease,pad=1280:650:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1[screen];[1:v][screen]overlay=70:200,format=yuv420p']
        else:
            args+=['-ss',str(a/FPS),'-i',str(source)]
            if change:args+=['-i',str(OUT/change['image']),'-filter_complex','[0:v][1:v]overlay=0:0,format=yuv420p']
        args+=['-an','-frames:v',str(b-a),'-r','24','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-threads','4',str(target)]
        signature=dict(start_frame=a,end_frame=b,change=change,source_sha256=sha(source),renderer_sha256=sha(__file__))
        proof=target.with_suffix('.inputs.json')
        if target.exists():
            if not proof.exists() or json.loads(proof.read_text(encoding='utf-8'))!=signature:raise ValueError('Changed cached segment')
        else:run(target,args);save(proof,signature)
        segments.append(target)
    for change in data['changes']:
        a,b=change['start_frame'],change['end_frame']
        if cursor<a:segment(cursor,a)
        segment(a,b,change);cursor=b
    if cursor<data['frames']:segment(cursor,data['frames'])
    listing=OUT/'concat.txt';listing.write_text('\n'.join("file '"+p.as_posix()+"'" for p in segments),encoding='utf-8')
    picture=OUT/'picture-master.mp4'
    if not picture.exists():run(picture,['ffmpeg','-v','warning','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(picture)])
    # Audio is stream copied from the adopted final, so no re-generation or re-encoding.
    run(dest,['ffmpeg','-v','info','-nostdin','-n','-i','picture-master.mp4','-i',str(OLD/'dots-transfer-detail-v03.mp4'),
        '-map','0:v','-map','1:a','-vf','ass=captions.ass:fontsdir=fonts','-c:v','libx264','-preset','fast','-crf','18',
        '-c:a','copy','-movflags','+faststart','-threads','6',dest.name],cwd=OUT)
    print(dest,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','render']);a=p.parse_args()
    (prepare if a.command=='prepare' else render)()
