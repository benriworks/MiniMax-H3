"""Pose-only revision: same approved man, concerned expression and chin support."""
from pathlib import Path
import argparse,copy,importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import read,record,check,audio_signature,validate_story,load_reusable_audio,prepare as prepare_short

def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if read(path)!=value:raise ValueError('Frozen revision metadata changed: '+str(path))
        return
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def motion():
    location=ROOT/'productions/CHARACTERS_20261022_explainer_motion/generate.py'
    definition=importlib.util.spec_from_file_location('php_v04_motion',location)
    gen=importlib.util.module_from_spec(definition);definition.loader.exec_module(gen)
    gen.PRODUCTION=HERE;gen.OUT=OUT/'motion/v02';gen.INPUT=ROOT/'runtime/ComfyUI/input'/(HERE.name+'-motion-v02')
    original_read=gen.read
    gen.read=lambda path:original_read(HERE/'motion-graph-v01.json') if path==ROOT/'outputs/claude-acquired-20260919/graph.json' else original_read(path)
    def prompt(spec):
        return ('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
            'integrated_multimodal_description: [Shot 1] A single continuous five-second vertical live-action shot. The only person is the exact fictional adult Japanese man from Picture 1. Preserve his identity, age, face shape, dark thin-frame glasses, black hairstyle, navy blazer, light-blue shirt, grey trousers, body proportions, standing composition, office background and soft daylight. '
            'Only his expression and right arm change. From 0.0 to 0.4 seconds his closed-mouth smile fades into a mildly concerned, thoughtful expression: eyebrows draw together slightly, lips relax without smiling, and his gaze lowers a little. '
            'From 0.4 to 1.6 seconds he slowly bends his right elbow and brings his loosely curled right hand up from his waist. The fingers form a relaxed loose fist, with the knuckle side resting gently against the underside of his chin. The thumb stays relaxed along the curled fingers. '
            'From 1.6 to 5.0 seconds he keeps the loose fist gently supporting his chin, looking slightly downward as if wondering whether his website is affected. He looks a little puzzled and concerned, not frightened, angry or distressed. Keep the pose still except for quiet breathing and one natural blink. '
            'His left hand stays relaxed near his waist; it does not touch his face or cross his body. Keep the glasses, eyes and mouth fully visible. Keep exactly two coherent arms and natural hands, with no extra fingers or limbs and no hand passing through the chin. The camera is locked and the whole movement is slow and understated. No nodding, no smile at the end, no talking or lip-sync, no pointing, no punch, no props, no added people, no cuts, no text, logos or watermarks.\n\n'
            'overall_soundscape: Very quiet office room tone and subtle fabric movement only. No speech, vocalization, music or dramatic sound effects.\n\n'
            'non_diegetic_music: N/A\n')
    gen.prompt=prompt
    source=(OUT/'characters/miura-wataru/v01/reference.png').relative_to(ROOT).as_posix()
    spec={'source':source,'source_presenter':source,'identity':'Approved Miura Wataru version 1; fictional adult Japanese male, 36','motion':'Mild concern, relaxed right fist gently supporting underside of chin; left hand relaxed at waist','seed':2026102504}
    gen.OUT.mkdir(parents=True,exist_ok=True)
    save(HERE/'motion-spec-v04.json',spec)
    target=HERE/'prompts/miura-concerned-chin-v04.txt'
    expected=prompt(spec)
    if target.exists() and target.read_text(encoding='utf-8')!=expected:raise ValueError('Frozen prompt changed')
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(expected,encoding='utf-8')
    gen.generate('miura-concerned-chin-v04',spec,False)

def prepare():
    proof_path=OUT/'motion/v02/miura-concerned-chin-v04/visual-review.json'
    proof=read(proof_path);clip=check(proof['artifact'])
    if proof.get('review_status')!='visual_review_passed':raise ValueError('Review the actual chin-support gesture before editing')
    baseline=read(HERE/'creator-story-v03.json');story=copy.deepcopy(baseline)
    story['scenes'][0]['media']={'path':clip.relative_to(ROOT).as_posix(),'proof':proof_path.relative_to(ROOT).as_posix()}
    # Omit the neutral reference-frame lead-in; retain 91 genuine motion frames.
    story['scenes'][0]['mediaStart']=24
    assert audio_signature(story)==audio_signature(baseline)
    validate_story(story)
    path=HERE/'creator-story-v04.json';save(path,story)
    state=HERE/'render-state-v04.json'
    if state.exists():
        previous=ROOT/read(state)['output']
        for item in read(previous/'preparation.json')['sources']:check(item)
        print(previous);return
    old=ROOT/read(HERE/'delivery-v03.json')['output']
    output=prepare_short(path,reuse_audio=old)
    save(state,{'revision':'v04','output':output.relative_to(ROOT).as_posix(),'only_scene_zero_media_changed':True,'user_approved':False})
    print(output)

def preflight():
    baseline=read(HERE/'creator-story-v03.json')
    previous=ROOT/read(HERE/'delivery-v03.json')['output']
    voice,reuse,files,sources=load_reusable_audio(baseline,previous)
    props=read(files['props.json'])
    reference=OUT/'characters/miura-wataru/v01/reference.png'
    approval=read(reference.parent/'approval.json')
    if approval['reference_sha256']!=record(reference)['sha256']:raise ValueError('Approved reference changed')
    save(HERE/'edit-plan-v04.json',{'revision':'v04','previous_delivery':record(previous/'shorts-creator.mp4'),
        'approved_reference':record(reference),'character_version':1,'duration_frames':props['durationInFrames'],
        'replacement_scene':0,'replacement_interval_frames':[0,props['scenes'][0]['duration']],
        'change':'Mild concern, loosely curled right hand gently supporting underside of chin',
        'preserve':'All narration, subtitles, captions, diagrams, factual claims, music, effects and timings',
        'audio_reuse':reuse,'new_gemini_requests':0,'new_series_or_character':False,'old_artifacts_overwritten':False})
    print('Pose-only plan verified:',props['scenes'][0]['duration'],'opening frames; encoded audio will be stream-copied')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['motion','prepare','preflight']);args=parser.parse_args();globals()[args.command]()
