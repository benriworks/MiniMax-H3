"""Isolated FL2VA motion trial; reuse existing durable submission monitoring."""
from pathlib import Path
import importlib.util,json,shutil,subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=ROOT/'outputs/characters/dots-duo-opening-20261026/v01'
INPUT=ROOT/'runtime/ComfyUI/input/dots-duo-opening-20261026/v01'
spec=importlib.util.spec_from_file_location('existing_motion_runner',ROOT/'productions/CHARACTERS_20261022_explainer_motion/generate.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.OUT=OUT;runner.PRODUCTION=HERE;runner.INPUT=INPUT;runner.URL='http://127.0.0.1:8190'
JOB='entrance'


def ensure_runtime():
    stats=runner.request('/system_stats')
    args=stats.get('system',{}).get('argv',[])
    if '--port' not in args or args[args.index('--port')+1]!='8190' or str(OUT) not in args:
        raise RuntimeError('Not the isolated duo-intro runtime')
    return stats


def prepare(job,settings):
    dest=OUT/job;dest.mkdir(parents=True,exist_ok=True);INPUT.mkdir(parents=True,exist_ok=True)
    for name in ['start.png','end.png']:
        src=OUT/'keyframes'/name;target=INPUT/name
        if target.exists():
            if runner.record(src)['sha256']!=runner.record(target)['sha256']:raise ValueError('Changed frame')
        else:
            with src.open('rb') as reader,target.open('xb') as writer:shutil.copyfileobj(reader,writer)
    graph=runner.read(ROOT/'outputs/claude-acquired-20260919/graph.json')
    graph['105:6']={'class_type':'UnetLoaderGGUF','inputs':{'unet_name':'MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf'}}
    graph['turbo']={'class_type':'MiniMaxH3TurboLoRA','inputs':{'model':['105:6',0],
        'lora_name':'minimax_h3_turbo_v4_step600_ema.safetensors','strength':1.0,'low_vram':True}}
    graph['105:9']['inputs'].update(steps=8,model=['turbo',0])
    graph['105:16']['inputs']['model']=['turbo',0]
    graph['105:17']={'class_type':'MiniMaxH3TurboSampler','inputs':{}}
    graph['105:15']['inputs']['noise_seed']=2026102601
    graph['105:111']['inputs']['value']=5.0
    graph['105:104']['inputs'].update(prompt=(HERE/'prompt-v01.txt').read_text(encoding='utf-8'),
        width=1024,height=576,first_frame=['start',0],last_frame=['end',0])
    for name in ['start','end']:
        graph[name]={'class_type':'LoadImage','inputs':{'image':f'dots-duo-opening-20261026/v01/{name}.png'}}
    graph['92']['inputs']['filename_prefix']=job+'/MiniMax_H3_Dots_Duo_Entrance'
    p=dest/'graph.json'
    if p.exists():
        if runner.read(p)!=graph:raise ValueError('Changed graph; create another version')
    else:runner.save(p,graph)
    p=dest/'prompt.txt'
    if not p.exists():p.write_text((HERE/'prompt-v01.txt').read_text(encoding='utf-8'),encoding='utf-8')
    return dest,graph,OUT/'keyframes/start.png',INPUT/'start.png'


def verify(job,settings,dest,graph,source,frame,history,task_id):
    entry=history[task_id]
    if not (dest/'history.json').exists():runner.save(dest/'history.json',history)
    if entry['status'].get('status_str')!='success' or not entry['status'].get('completed'):
        raise RuntimeError('Generation failed; inspect history, do not resubmit')
    if entry['prompt'][2]!=graph:raise ValueError('Graph identity differs')
    files=list(runner.video_entries(entry['outputs']['92']))
    if len(files)!=1:raise ValueError('Unexpected output count')
    raw=(OUT/files[0]['subfolder']/files[0]['filename']).resolve()
    if not raw.is_relative_to(dest):raise ValueError('Output scope mismatch')
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(raw)]))
    stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    if (stream['width'],stream['height'],stream['avg_frame_rate'],int(stream['nb_frames']))!=(1024,576,'24/1',124):
        raise ValueError('Unexpected output geometry')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(raw),'-f','null','-'],check=True,creationflags=runner.FLAGS)
    for i in range(11):
        image=dest/f'frame-{i:02d}.png'
        if not image.exists():subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-ss',str(i*.5),'-i',str(raw),'-frames:v','1',str(image)],check=True,creationflags=runner.FLAGS)
    sheet=dest/'contact-sheet.jpg'
    if not sheet.exists():subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(raw),'-vf','fps=2,scale=384:216,tile=4x3','-frames:v','1','-q:v','2',str(sheet)],check=True,creationflags=runner.FLAGS)
    messages=entry['status']['messages']
    begin=next(m[1]['timestamp'] for m in messages if m[0]=='execution_start')
    end=next(m[1]['timestamp'] for m in messages if m[0]=='execution_success')
    proof=dict(schema_version=1,provider='minimax',mode='local_h3_fl2va',
        base='Q3_K_M',text_encoder='Q4_K_M',turbo=True,steps=8,seed=2026102601,
        first_frame=runner.record(INPUT/'start.png'),last_frame=runner.record(INPUT/'end.png'),
        execution=dict(prompt_id=task_id,success=True,elapsed_seconds=(end-begin)/1000),
        artifact=dict(runner.record(raw),full_decode_verified=True,probe=probe),
        review_status='awaiting_visual_review',user_approved=False,paid_minimax_api_calls=0)
    if not (dest/'verification.json').exists():runner.save(dest/'verification.json',proof)
    print(json.dumps(dict(event='generation_verified',artifact=runner.record(raw),elapsed_seconds=(end-begin)/1000)),flush=True)


runner.ensure_runtime=ensure_runtime;runner.prepare=prepare;runner.verify=verify
if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    runner.generate(JOB,{},args.prepare_only)
