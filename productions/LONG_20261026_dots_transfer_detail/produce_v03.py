"""Rebuild the conversation and timing without retiming actual recorded operations."""
from pathlib import Path
from copy import deepcopy
import argparse,json,math,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(HERE))
import revise_v02 as video
from tools.studio.longform_audio import plan_dialogue,assemble_audio,read_voice,SR
from tools.studio.dialogue_avatar import validate_windows,DialogueDriver
OLD=video.OLD;OUT=OLD.parent/'v03';FPS=24


def command(dest,args):
    with dest.with_suffix('.log').open('w',encoding='utf-8') as log:
        subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def static_seconds(item):
    name=Path(item['path']).name
    if '-mapping-' in name or '-compare-' in name:return 2
    if '-scope-' in name:return 4
    if '-approval-' in name:return 5
    if 'confirmation-native' in name:return 4
    if 'demo001-complete' in name:return 3
    if '-boundary-' in name:return 3
    if '-caution-' in name:return 4
    return 3.5


def prepare():
    if (OUT/'timeline.json').exists():raise ValueError('Prepared timeline exists; inspect rather than overwrite')
    script=json.loads((HERE/'script-v03.json').read_text(encoding='utf-8'))
    visuals=json.loads((OLD/'visuals.json').read_text(encoding='utf-8'))
    # Validate every reused and newly generated voice against its durable request result.
    for proofpath in (OUT/'voice').glob('*/turn-*/verified.json'):
        proof=json.loads(proofpath.read_text(encoding='utf-8'))
        for record in proof['files']:
            if video.fingerprint(ROOT/record['path']).upper()!=record['sha256'].upper():raise ValueError('Voice source changed')
    cuts=[];chapters=deepcopy(script['chapters']);cursor=0
    for chapter in chapters:
        cid=chapter['id'];items=[]
        for i,item in enumerate(visuals[cid]):
            if item['origin']=='existing_minimax_character_interlude':continue
            real=item['origin']=='new_real_gui_recording'
            minimum=item['seconds'] if real else static_seconds(item)
            items.append(dict(original=item,source=(OLD/'rendered-shots'/f'{int(cid[-2:]):02d}-{i:02d}.mp4').relative_to(ROOT).as_posix(),
                frames=round(minimum*FPS),real_recording=real,kind=Path(item['path']).stem))
        if cid=='chapter-09':
            items.append(dict(original=None,source=None,frames=4*FPS,real_recording=False,kind='result-summary'))
        voice_seconds=sum(len(read_voice(OUT/'voice'/cid/f'turn-{i:02d}'/'voice.wav'))/SR for i in range(len(chapter['turns'])))
        minimum=voice_seconds+.35*(len(chapter['turns'])-1)+.5+chapter['tail_seconds']
        target=max(sum(x['frames'] for x in items),math.ceil(minimum*FPS))
        expandable=[x for x in items if not x['real_recording']]
        extra=target-sum(x['frames'] for x in items)
        if extra and not expandable:
            item=dict(original=None,source=None,frames=0,real_recording=False,kind='procedure-summary')
            items.append(item);expandable=[item]
        for i,item in enumerate(expandable):item['frames']+=extra//len(expandable)+(i<extra%len(expandable))
        chapter.update(target_seconds=target/FPS,pause_mode='after_answer')
        for item in items:
            item.update(chapter=cid,start=cursor/FPS,end=(cursor+item['frames'])/FPS,seconds=item['frames']/FPS)
            cursor+=item['frames'];cuts.append(item)
    main=plan_dialogue(chapters,OUT/'voice');assert main['frames']==cursor
    # Use integral video frames for exact bounds; summing chapter floats can differ by 1 ULP.
    main['seconds']=main['frames']/FPS
    opening=plan_dialogue([dict(id='opening',title='今日は、何をしたい？',target_seconds=0,turns=script['opening'],pause_mode='after_answer')],OUT/'voice')
    arrival=124/FPS;prefix=arrival+opening['seconds']
    shifted=deepcopy(opening['chapters'])+deepcopy(main['chapters'])
    for i,chapter in enumerate(shifted):
        offset=arrival if i==0 else prefix
        chapter['start']+=offset;chapter['end']+=offset
        for turn in chapter['turns']:turn['start']+=offset;turn['end']+=offset
    frames=124+opening['frames']+main['frames']
    plan=dict(fps=FPS,seconds=frames/FPS,frames=frames,arrival_seconds=arrival,
        conversation_seconds=opening['seconds'],main_offset=prefix,chapters=shifted,alignment=main['alignment'])
    windows=[]
    def window(cut,kind,title,lines,male='curious',female='serious',start=None,end=None):
        windows.append(dict(start=cut['start'] if start is None else start,end=cut['end'] if end is None else end,
            kind=kind,title=title,lines=lines,male=male,female=female))
    for cut in cuts:
        k=cut['kind']
        if k.startswith('02-place'):window(cut,'before','同じクラウドPCでつなぐ',['Excelファイル → Webシステム','手元のPCとは別の作業場所'],female='neutral')
        elif k=='04-scope-0':window(cut,'emphasis','任せる範囲を先に決める',['対象は3件だけ','保存先と、止める条件も指定'])
        elif k.startswith('05-approval'):window(cut,'emphasis','登録の前に、人が確認',['対象・内容・保存先を照合','本人の返答を受けて再開'],male='serious')
        elif k.startswith('07-boundary'):window(cut,'before','確認と登録は別',['内容確認では、まだ未保存','この後の登録で保存される'])
        elif k=='result-summary':window(cut,'emphasis','保存後にも照合',['全15項目・3件・25万円','今回のデモでは元の表と一致'],male='pleased',female='pleased')
        elif k.startswith('10-caution'):window(cut,'caution','最後の照合は必要',['このデモで確認した拒否試験','すべてのミスを防ぐ保証ではない'],male='worried')
    final=[c for c in cuts if c['chapter']=='chapter-11'];a,b=final[0]['start'],final[-1]['end']
    window(final[0],'closing','小さな範囲から試そう',['範囲を決める → 人が確認','入力・登録 → 保存後に照合'],male='neutral',female='pleased',end=min(a+10,b-8))
    window(final[-1],'closing','入力を任せて、結果を確かめる',['まずは架空データと小さな範囲で','実運用にはシステムの利用権限が必要'],male='pleased',female='pleased',start=max(a+10,b-8))
    windows.sort(key=lambda x:x['start'])
    protected=[(c['start'],c['end']) for c in cuts if c['real_recording'] or '-mapping-' in c['kind'] or '-compare-' in c['kind']]
    validate_windows(windows,main['seconds'],protected)
    config=json.loads((HERE/'revision-v02.json').read_text(encoding='utf-8'))
    config.update(version='v03',opening_turns=script['opening'],windows_in_main_seconds=windows)
    config.pop('windows_in_original_main_seconds',None)
    video.save(OUT/'render-config.json',config);video.save(OUT/'cut-map.json',cuts);video.save(OUT/'timeline.json',plan)
    video.save(OUT/'audio/verification.json',assemble_audio(plan,OUT/'audio',music_style='bright'))
    video.save(OUT/'audio/mouth-gates.json',DialogueDriver([t for c in shifted for t in c['turns']]).gates)
    (OUT/'avatars').mkdir(exist_ok=True)
    for p in (OLD.parent/'v02/avatars').glob('*atlas.png'):shutil.copy2(p,OUT/'avatars'/p.name)
    (OUT/'fonts').mkdir(exist_ok=True);shutil.copy2(OLD/'fonts/meiryob.ttc',OUT/'fonts/meiryob.ttc')
    header=(OLD/'captions.ass').read_text(encoding='utf-8').split('[Events]')[0]
    lines=[header+'[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'];srt=[]
    for chapter in shifted:
        for turn in chapter['turns']:
            pieces=video.caption_phrases(turn['text']);at=turn['start'];weight=sum(map(len,pieces))
            for phrase in pieces:
                end=at+(turn['end']-turn['start'])*len(phrase)/weight
                lines.append(f'Dialogue: 0,{video.ass_time(at)},{video.ass_time(end)},{turn["speaker"].title()},,0,0,0,,{video.subtitle_text(phrase)}')
                def stamp(t):return '0'+video.ass_time(t).replace('.',',')+'0'
                srt.append(f'{len(srt)+1}\n{stamp(at)} --> {stamp(end)}\n{phrase}\n');at=end
    (OUT/'captions.ass').write_text('\n'.join(lines)+'\n',encoding='utf-8');(OUT/'captions.srt').write_text('\n'.join(srt),encoding='utf-8')
    preserved=[OLD/'dots-transfer-detail-v01.mp4',OLD.parent/'v02/dots-transfer-detail-v02.mp4']
    video.save(OUT/'source-manifest.json',dict(script_sha256=video.fingerprint(HERE/'script-v03.json'),producer_sha256=video.fingerprint(__file__),
        accepted_opening=dict(path=config['opening_clip'],sha256=video.fingerprint(ROOT/config['opening_clip'])),
        old_videos_preserved=[dict(path=p.relative_to(ROOT).as_posix(),sha256=video.fingerprint(p)) for p in preserved],
        sprites=[dict(path=p.relative_to(ROOT).as_posix(),sha256=video.fingerprint(p)) for p in (OUT/'avatars').glob('*atlas.png')],
        real_clip_speed=1,new_minimax_calls=0,new_imagegen_calls=0,new_voice_turns=44))
    video.save(OUT/'pip-policy-audit.json',dict(windows=windows,protected=protected,protected_operations_covered=0,
        layout='Reserved portrait sides, central takeaway, bottom captions',listener_mouth='closed',mouth='PCM-envelope simple animation; not phoneme-aligned'))
    print('Prepared',plan['seconds'],'seconds;',len(cuts),'cuts;',len(windows),'PIP windows;',sum(c['seconds'] for c in cuts if c['real_recording']),'seconds unchanged-speed real recordings',flush=True)


def picture():
    cuts=json.loads((OUT/'cut-map.json').read_text(encoding='utf-8'));plan=json.loads((OUT/'timeline.json').read_text(encoding='utf-8'))
    folder=OUT/'retimed-cuts';folder.mkdir(exist_ok=True);segments=[]
    for i,cut in enumerate(cuts):
        target=folder/f'{i:02d}-{cut["kind"]}.mp4';source=ROOT/cut['source'] if cut['source'] else None
        signature=dict(cut=cut,source_sha256=video.fingerprint(source) if source else None)
        def make(target=target,cut=cut,source=source):
            if cut['real_recording']:
                command(target,['ffmpeg','-v','warning','-nostdin','-n','-i',str(source),'-an','-frames:v',str(cut['frames']),
                    '-c:v','libx264','-preset','veryfast','-crf','18','-r','24','-threads','4',str(target)])
            else:
                image=target.with_suffix('.png')
                if source:command(image,['ffmpeg','-v','warning','-nostdin','-n','-i',str(source),'-frames:v','1',str(image)])
                else:
                    chapter=next(c for c in plan['chapters'] if c['id']==cut['chapter'])
                    w=dict(title='保存後にも照合' if cut['kind']=='result-summary' else '同じ手順で、残りの二件も',
                        lines=['全15項目・3件・25万円','今回のデモでは元の表と一致'] if cut['kind']=='result-summary' else ['入力 → 確認 → 登録','値が違えば、そこで止める'])
                    video.takeaway(w,chapter).save(image)
                command(target,['ffmpeg','-v','warning','-nostdin','-n','-loop','1','-i',str(image),'-frames:v',str(cut['frames']),
                    '-an','-c:v','libx264','-preset','veryfast','-crf','18','-r','24','-pix_fmt','yuv420p','-threads','4',str(target)])
        video.cached_video(target,signature,make);segments.append(target)
    listing=OUT/'main-concat.txt';listing.write_text('\n'.join("file '"+p.as_posix()+"'" for p in segments),encoding='utf-8')
    dest=OUT/'main-retimed.mp4'
    if not dest.exists():command(dest,['ffmpeg','-v','warning','-nostdin','-n','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(dest)])
    video.OUT=OUT
    video.render(config_path=OUT/'render-config.json',output_name='dots-transfer-detail-v03.mp4',picture_source=dest,replace_interlude=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['prepare','render']);a=p.parse_args()
    (prepare if a.command=='prepare' else picture)()
