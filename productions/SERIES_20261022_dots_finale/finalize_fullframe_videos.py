"""Audit the fullscreen-character revision while preserving earlier delivery audits."""
from datetime import datetime, timezone
from pathlib import Path
import copy
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('dots_previous_audit',HERE/'finalize.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
read,record,check,require=old.read,old.record,old.check,old.require
PLAN_REF=read(HERE/'fullframe-revision-plan.json')['plan']
PLAN_PATH=check(PLAN_REF)
PLAN=read(PLAN_PATH)
for backup in PLAN['old_metadata_snapshots']:
    check(backup['snapshot'])


def audit(number):
    here=HERE/f'{number:02d}'
    state=read(here/'state.json')
    require(state['status']=='packaged','Episode is not packaged')
    out=ROOT/state['output']
    receipt=read(check(state['character_video_revision']))
    require(receipt['output']==state['output'] and receipt['additional_tts_requests']==0,'Revision identity or speech count differs')
    for key in ['original_story','render_story','previous_state','previous_delivery','narration_source']:
        check(receipt[key])
    for item in receipt['preserved_files']: check(item)
    delivery=read(here/'delivery.json')
    require(delivery==read(out/'delivery.json'),'Delivery pointers differ')
    video,archive=old.verify_package(delivery,ROOT/delivery['release'])
    proof=read(out/'verification.json')
    require(record(video)['sha256']==record(check(proof['delivery']))['sha256'],'Completed/public MP4 differ')
    require(proof['review_status']=='verified_candidate_awaiting_user_review' and proof['full_decode_verified'] and proof['on_screen_tool_credit'] is False,'Verification gate incomplete')
    review=proof['visual_review']
    evidence={check(item) for item in review['evidence']}
    require(evidence=={out/f'preview-{i:02d}.png' for i in range(7)}|{out/'contact-sheet.png'},'Seven-scene visual evidence missing')
    require(bool(review['note']) and '動' in review['note'],'Concrete character-movement review missing')
    motion=read(out/'motion-evidence.json')
    require(check(motion['video'])==ROOT/proof['delivery']['path'] and len(motion['samples'])==6,'Motion samples mismatch')
    for sample in motion['samples']: check(sample['image'])
    check(motion['contact_sheet'])
    require((out/'motion-visual-review.json').exists(),'Motion visual review record missing')
    movement_review=read(out/'motion-visual-review.json')
    require(movement_review['status']=='passed' and bool(movement_review['note']),'Movement visual inspection incomplete')
    check(movement_review['evidence'])
    for item in read(out/'preparation.json')['sources']+read(out/'render.json')['sources']: check(item)
    original=read(check(receipt['original_story']))
    story=read(out/'story.json')
    require(story==read(check(receipt['render_story'])),'Render story differs')
    stripped=copy.deepcopy(story)
    for i in [0,6]:
        stripped['scenes'][i].pop('media');stripped['scenes'][i].pop('mediaStart')
    require(stripped==original and old.audio_signature(story)==old.audio_signature(original) and old.narration_inputs(story)==old.narration_inputs(original),'Nonvisual story changed')
    props=read(out/'props.json');timings=read(out/'timings.json')['segments']
    require(len(props['scenes'])==7 and props['durationInFrames']==720,'Scene duration changed')
    require([i for i,s in enumerate(props['scenes']) if s.get('media')]==[0,6],'Motion appears outside opening/closing')
    require(not any(s.get('presenter') for s in props['scenes']),'Old PNG presenter remains')
    cursor=0
    for scene,timing in zip(props['scenes'],timings,strict=True):
        require(scene['from']==cursor and cursor*1000/24-1<=timing['start_ms']<timing['end_ms']<=(cursor+scene['duration'])*1000/24+1,'Speech/scene time differs')
        cursor+=scene['duration']
    require(cursor==720,'Timeline does not cover 30 seconds')
    for index,clip in zip([0,6],receipt['clips'],strict=True):
        for key in ['artifact','proof','presenter','keyframe']: check(clip[key])
        character=read(check(clip['proof']))
        require(character['review_status']=='visual_review_passed' and character['provider']=='minimax' and character['execution']['success'],'Character not reviewed')
        require(record(out/'public'/props['scenes'][index]['media'])['sha256']==clip['artifact']['sha256'],'Staged character changed')
        scene=props['scenes'][index]
        require(scene.get('mediaPlayFrames')==scene['duration'] and scene.get('mediaDurationInFrames')==124
                and scene.get('mediaStart',0)+scene['duration']<=124,'Unchanged dots scene must remain inside actual video frames')
    captures=[]
    for index,scene in enumerate(story['scenes']):
        if scene['kind']=='source':
            capture=read(ROOT/scene['capture']['proof'])
            require(capture['review_status']=='capture_review_passed' and capture['source_url']==scene['capture']['source_url'],'Official capture mismatch')
            asset=check(capture['artifact']);check(capture['context'])
            require(record(out/'public'/props['scenes'][index]['capture']['image'])['sha256']==record(asset)['sha256'],'Official excerpt changed')
            require(not props['scenes'][index].get('media'),'Character overlaps source excerpt')
            captures.append(record(ROOT/scene['capture']['proof']))
    require(len(captures)==1,'Expected one official excerpt')
    prior=read(check(receipt['previous_delivery']));prior_release=ROOT/prior['release'];release=ROOT/delivery['release']
    for name in ['narration.txt','captions.srt','youtube-title.txt','youtube-description.txt','SOURCES_JA.md']:
        require((release/name).read_bytes()==(prior_release/name).read_bytes(),'Existing text/captions changed: '+name)
    audio=old.audio_hash(video);previous_audio=old.audio_hash(check(prior['video']))
    require(audio==previous_audio==proof['audio_reuse']['packet_hash'] and proof['audio_reuse']['identical_audio_verified'],'AAC packets changed')
    probe=json.loads(old.run('ffprobe','-v','error','-show_streams','-show_format','-of','json',video))
    v,a=probe['streams']
    require((v['codec_name'],v['width'],v['height'],v['avg_frame_rate'],int(v['nb_frames']))==('h264',1080,1920,'24/1',720),'Video format mismatch')
    require((a['codec_name'],a['sample_rate'],a['channels'])==('aac','48000',2) and abs(float(probe['format']['duration'])-30)<.002,'Audio/length mismatch')
    loudness=proof['loudness']
    require(-18<=float(loudness['input_i'])<=-14 and float(loudness['input_tp'])<=-1,'Loudness bounds failed')
    plan=read(ROOT/state['generation']/'plan.json')
    originals=[record(check(item)) for item in plan['existing_deliveries']]
    require(len(originals)==12,'Original protected set mismatch')
    voice,_=old.load_supplied_narration(original,ROOT/state['generation']/'voice-source.json')
    require(voice['voice']=='Aoede' and len(voice['generation_proofs'])==7,'Saved voice differs')
    quality=read(release/'quality-report.json')
    require(quality==delivery['quality'] and quality['previous_completed_video_audio_identical'] and quality['visual_revision_additional_tts_requests']==0 and quality['user_approved'] is False,'Package quality status mismatch')
    baseline=next(item for item in PLAN['episodes'] if item['episode']==number)
    require(receipt['previous_output']==baseline['previous_output'] and state['output']!=baseline['previous_output'],'Fullscreen revision does not follow the protected motion version')
    require(record(video)['sha256']!=baseline['video']['sha256'] and audio==baseline['audio_packet_hash'],'Fullscreen picture/audio identity failed')
    require('全面' in review['note'],'Fullscreen framing inspection must be recorded after actual visual review')
    renderer=next(item for item in read(out/'render.json')['sources'] if item['path']=='studio/src/remotion/EditorialScene.tsx')
    previous_renderer=next(item for item in PLAN['renderer_before_revision'] if item['used_by_previous_video']['path']==renderer['path'])
    require(renderer['sha256']!=previous_renderer['used_by_previous_video']['sha256'],'Fullscreen renderer was not adopted')
    check(baseline['video']);check(baseline['archive']);check(baseline['verification'])
    if receipt.get('superseded_preparation'):
        superseded=receipt['superseded_preparation']
        for key in ['state','preparation','props','revision']: check(superseded[key])
        require(superseded['audio_and_timing_unchanged'],'Repreparation must preserve audio and timing')
    return {'episode':number,'title':(release/'youtube-title.txt').read_text(encoding='utf-8').strip(),
        'video':record(video),'archive':record(archive),'release':delivery['release'],'cover':record(release/'cover.png'),
        'verification':record(out/'verification.json'),'contact_sheet':record(out/'contact-sheet.png'),'motion_evidence':record(out/'motion-evidence.json'),'motion_contact_sheet':record(out/'motion-contact-sheet.png'),'motion_review':record(out/'motion-visual-review.json'),
        'audio_packet_hash':audio,'previous_audio_identical':True,'narration_bytes_unchanged':True,'additional_tts_requests':0,
        'official_captures':captures,'loudness_lufs':float(loudness['input_i']),'true_peak_dbfs':float(loudness['input_tp']),
        'protected_original_videos':originals,'preserved_previous_files':receipt['preserved_files'],'clips':receipt['clips']}

episodes=[]
for number in range(5,10):
    episodes.append(audit(number))
    print(json.dumps({'event':'motion_episode_audit_passed','episode':number}),flush=True)
require(all(ep['protected_original_videos']==episodes[0]['protected_original_videos'] for ep in episodes),'Original sets differ')
report={'schema_version':1,'series':'SERIES_20261022_dots_finale','revision':'fullframe_character_motion','pre_revision_plan':PLAN_REF,'checked_at':datetime.now(timezone.utc).isoformat(),
    'status':'verified_candidate_awaiting_user_review','technical_status':'verified','episodes':episodes,
    'totals':{'episodes':5,'seconds':150,'frames':3600,'scene_reviews':35,'motion_review_samples':30,'official_capture_proofs':5,'previous_aac_streams_identical':5,'additional_tts_requests':0,'additional_tts_characters':0,'protected_original_videos':12},
    'user_approved':False,'final_listening_review':'pending','youtube_uploaded':False,'s3_uploaded_for_this_revision':False}
report_path=PLAN_PATH.parent/'final-verification.json'
old.save(report_path,report)
old.save(HERE/'fullframe-character-delivery.json',{'schema_version':1,'status':report['status'],'verification':record(report_path),'totals':report['totals'],'episodes':[{key:ep[key] for key in ['episode','title','video','archive','cover','release','verification','contact_sheet','motion_contact_sheet']} for ep in episodes],'user_approved':False,'final_listening_review':'pending','youtube_uploaded':False,'s3_uploaded_for_this_revision':False})
print(json.dumps({'event':'all_motion_revisions_verified','report':str(report_path),'delivery':str(HERE/'fullframe-character-delivery.json')}))
