"""Integrate captured Docs screens while preserving all verified narration."""
from pathlib import Path
import argparse,copy,json,shutil,sys
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[5]
HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.shorts_creator import check,read,record,write,prepare,finish,run,validate_story,narration_inputs,load_supplied_narration
CAPTURE=ROOT/'outputs/content-projects/CONTENT_20261023_claude_docs_reuse/captures/20261023-native-v01'
ASSETS=ROOT/'outputs/productions/SHORT_20261023_claude_docs_native_v03/captures'
OUT=ROOT/'outputs/content-projects/CONTENT_20261023_claude_docs_reuse'

def asset(index,name,title,phase,region=None):
    item=read(CAPTURE/'capture-manifest.json')['assets'][index]
    source=check(item['context'])
    with Image.open(source) as image:
        image=image.convert('RGB'); width,height=image.size
        if region is None:
            c=item['clip'];region=(c['x'],c['y'],c['x']+c['width'],c['y']+c['height'])
        crop=image.crop(region)
        private=ASSETS/'_private';private.mkdir(parents=True,exist_ok=True)
        context=private/(name+'-decoded.png')
        image.save(context)
        target=ASSETS/(name+'.png');crop.save(target)
        if ImageChops.difference(Image.open(target).convert('RGB'),crop).getbbox() is not None:
            raise ValueError('Crop pixels changed')
    proof={'schema_version':1,'origin':'demonstration','product':'Claude','phase':phase,'title':title,
        'artifact':record(target),'context':record(context),'raw_capture':record(source),
        'raw_capture_format':'JPEG','context_format':'PNG decoded from JPEG without resizing',
        'captured_at':item['captured_at'],'clip':{'x':region[0],'y':region[1],'width':crop.width,'height':crop.height},
        'context_clip':{'x':0,'y':0,'width':width,'height':height},
        'fictional_materials_only':True,'personal_information_excluded':True,'content_modified':False,
        'pixel_exact_crop_verified':True,'review_status':'capture_review_passed','ai_visual_review':'native_original_and_public_crop_checked',
        'user_approved':False,'operation':'decode original JPEG and rectangular crop only',
        'scope_note':'2026-10-23 native inspection of an existing fictional Docs document; no new text edit or prompt submission.'}
    write(ASSETS/(name+'.json'),proof)
    return {'path':target.relative_to(ROOT).as_posix(),'proof':(ASSETS/(name+'.json')).relative_to(ROOT).as_posix(),
        'origin':'demonstration','product':'Claude','phase':phase,'title':title}

def build():
    path=HERE/'creator-story.json'
    if path.exists():
        story=validate_story(read(path))
        baseline_state=read(ROOT/'productions/SERIES_20261023_editorial_revision/01/final-state.json')
        voice=ROOT/baseline_state['generation']/'voice-source.json'
        load_supplied_narration(story,voice)
        return path,voice,ROOT/baseline_state['output']
    baseline=read(ROOT/'productions/SERIES_20261023_editorial_revision/01/visual-v03/creator-story.json')
    story=copy.deepcopy(baseline)
    # The production ID remains stable because verified narration is bound to it.
    # The story path, output generation and review version identify this revision.
    captures={
        1:asset(0,'native-overview','Docsの文書パネル','after'),
        3:asset(1,'native-structure','見出しと企画概要の表','after',(360,250,1080,710)),
        4:asset(3,'native-selection','文章選択と編集メニュー','revision',(120,325,465,425)),
        7:asset(2,'native-comments','Docsとコメント欄','after'),
    }
    for i,capture in captures.items():
        s=story['scenes'][i]
        for key in ['body','action','items','editorial_layout','stat']:s.pop(key,None)
        s['kind']='source';s['capture']=capture
    story['editorial']['availability_note']='2026-10-23の実機キャプチャを4場面へ採用。保存済み文書・文章選択・Commentsを表示。直接入力・新規コメント送信・複数資料参照の追加実演は行っていない。初回と修正後の比較は2026-10-22の保存記録。'
    story['review_revision']='v03_native_screens'
    if narration_inputs(story)!=narration_inputs(baseline):raise ValueError('Narration changed')
    path=HERE/'creator-story.json'
    if path.exists() and read(path)!=story:raise ValueError('Frozen story changed')
    if not path.exists():write(path,validate_story(story))
    baseline_state=read(ROOT/'productions/SERIES_20261023_editorial_revision/01/final-state.json')
    voice=ROOT/baseline_state['generation']/'voice-source.json'
    load_supplied_narration(story,voice)
    return path,voice,ROOT/baseline_state['output']

def render():
    path,voice,prior=build()
    state_path=HERE/'state.json'
    state=read(state_path) if state_path.exists() else {'voice_source':record(voice),'prior_delivery':record(prior/'shorts-creator.mp4'),'external_api_calls':0}
    if 'output' not in state:
        out=prepare(path,narration_source=voice)
        if (out/'narration.wav').read_bytes()!=(prior/'narration.wav').read_bytes():raise ValueError('Narration WAV changed')
        state.update(output=out.relative_to(ROOT).as_posix(),status='prepared',narration_pcm_unchanged=True)
        write(state_path,state)
    out=ROOT/state['output']
    if not (out/'render.json').exists():run('node',ROOT/'studio/creator-render.mjs',out)
    if not (out/'verification.json').exists():finish(out)
    check(read(out/'verification.json')['delivery'])
    state['status']='rendered_awaiting_visual_review'
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':state['status'],'output':state['output'],'narration_pcm_unchanged':True}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['build','render'])
    args=parser.parse_args();render() if args.command=='render' else build()
