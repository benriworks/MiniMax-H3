"""Verify release receipts, actual decoded caption frames, sources and reuse."""
from pathlib import Path
import ast,json,sys
from PIL import Image
from produce import ROOT,HERE,OUT,DEST,sha,save,run

def verify():
    plan=json.loads((DEST/'timeline.json').read_text(encoding='utf-8'));qc=json.loads((DEST/'qc.json').read_text(encoding='utf-8'));media=DEST/'anthropic-departures-short-v01.mp4'
    assert qc['sha256']==sha(media) and qc['full_decode'] and qc['frames']==plan['frames']==1098
    assert plan['seconds']==45.75 and -18<float(qc['final_aac_loudness']['input_i'])<-14 and float(qc['final_aac_loudness']['input_tp'])<=-1
    caption_count=0
    for turn in plan['turns']:
        receipt=json.loads((ROOT/turn['voice_path']).with_name('verified.json').read_text(encoding='utf-8'))
        for file in receipt['files']:assert sha(ROOT/file['path']).upper()==file['sha256']
        assert ''.join(x['text'].replace('\n','') for x in turn['subtitles'])==turn['display']
        assert turn['subtitles'][0]['start']==turn['voice_start']
        assert abs(turn['subtitles'][-1]['end']-turn['voice_start']-turn['voice_seconds'])<1e-6
        for a,b in zip(turn['subtitles'],turn['subtitles'][1:]):assert abs(a['end']-b['start'])<1e-6
        caption_count+=len(turn['subtitles'])
    layouts=json.loads((DEST/'text-layout-audit.json').read_text(encoding='utf-8'));assert all(x['fits'] for x in layouts)
    assert all(x['size']==56 for x in layouts if x['rect']==[70,1485,1010,1680])
    evidence=DEST/'decoded-frames';evidence.mkdir(parents=True,exist_ok=True);points=[('opening',0.25),('ending',plan['seconds']-.5)]
    for turn in plan['turns']:
        points += [(turn['id']+f'-caption-{i:02}',(x['start']+x['end'])/2) for i,x in enumerate(turn['subtitles'])]
    records=[];tiles=[]
    for name,seconds in points:
        target=evidence/(name+'.jpg')
        if not target.exists():run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(seconds),'-i',str(media),'-frames:v','1','-q:v','2',str(target)])
        image=Image.open(target);assert image.size==(1080,1920);tiles.append(image.resize((270,480),Image.Resampling.LANCZOS));records.append(dict(id=name,seconds=seconds,sha256=sha(target)))
    sheet=Image.new('RGB',(1080,480*((len(tiles)+3)//4)),'#10283D')
    for i,tile in enumerate(tiles):sheet.paste(tile,(270*(i%4),480*(i//4)))
    sheet.save(evidence/'contact-sheet.jpg',quality=94)
    manifest=json.loads((OUT/'asset-manifest-v01.json').read_text(encoding='utf-8'))['items']
    for item in manifest:
        assert sha(ROOT/item['path'])==item['sha256']
        if item.get('reuse'):assert sha(ROOT/item['source'])==item['sha256']
    for folder in ['voice/v01/s01','voice/v01/s02','voice/v01/s03','voice/v01/s04','voice/v01/s05','voice/v01/s06']:
        assert json.loads((OUT/folder/'submission.json').read_text(encoding='utf-8'))['status']=='received_and_verified'
    audio=json.loads((OUT/'_private/media-review/audio-six-lines-v01/review.json').read_text(encoding='utf-8'));av=json.loads((OUT/'_private/media-review/completed-short-v01/review.json').read_text(encoding='utf-8'))
    assert audio['audio_access_ok'] and not audio['material_issue'] and av['audiovisual_access_ok'] and not av['material_issues']
    handoff=json.loads((OUT/'_private/drive-video-v01.json').read_text(encoding='utf-8'));drive=handoff['readback']['structuredContent'];upload=handoff['upload']['structuredContent']
    parent=handoff['parent']['value']['structuredContent']['id']
    assert int(drive['size'])==media.stat().st_size and drive['shared'] is False and drive['parent_ids']==[parent]
    assert drive['id']==upload['id'] and drive['title']==upload['title'] and upload['parent_id']==parent
    for p in HERE.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    summary=dict(sha256=sha(media),seconds=plan['seconds'],frames=plan['frames'],bytes=media.stat().st_size,tts_requests=6,caption_states=caption_count,text_boxes=len(layouts),decoded_representatives=len(records),source_and_reuse_hashes=len(manifest),final_aac_loudness=qc['final_aac_loudness'],full_decode_receipt=True,audio_ai_material_issues=0,av_ai_material_issues=0,drive_metadata_verified=True,drive_playback_verified=False,human_final_listening=False,user_accepted_finished_video=False,published=False,decoded_frames=records)
    save(DEST/'delivery-checks.json',summary);print(json.dumps({k:v for k,v in summary.items() if k not in ['decoded_frames','final_aac_loudness']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    verify()
