"""One isolated local H3 Turbo applause shot; durable identity, no resubmission."""
from pathlib import Path
import importlib.util,json,subprocess
from PIL import Image,ImageOps
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MEDIA=Path('C:/Users/mono_/MiniMaxH3')
OUT=ROOT/'outputs/content-projects'/HERE.name/'motions/v03'
INPUT=OUT/'input'
spec=importlib.util.spec_from_file_location('duo_runner',ROOT/'productions/CHARACTERS_20261026_dots_duo_opening/generate.py')
duo=importlib.util.module_from_spec(spec);spec.loader.exec_module(duo)
runner=duo.runner
runner.ROOT=ROOT;runner.OUT=OUT;runner.INPUT=INPUT;runner.PRODUCTION=HERE;runner.URL='http://127.0.0.1:8192'
duo.OUT=OUT;duo.INPUT=INPUT

def ensure_runtime():
    stats=runner.request('/system_stats');args=stats['system']['argv']
    if '--port' not in args or args[args.index('--port')+1]!='8192' or str(OUT) not in args:raise RuntimeError('Not the dedicated full-video runtime')
    return stats

def prepare(job,settings):
    dest=OUT/job;dest.mkdir(parents=True,exist_ok=True);INPUT.mkdir(parents=True,exist_ok=True)
    source=MEDIA/'outputs/characters/dots-duo-opening-20261026/v01/keyframes/end.png'
    frame=INPUT/'start.png'
    if not frame.exists():ImageOps.fit(Image.open(source).convert('RGB'),(768,448),method=Image.Resampling.LANCZOS).save(frame)
    graph=runner.read(MEDIA/'outputs/claude-acquired-20260919/graph.json')
    graph['105:6']={'class_type':'UnetLoaderGGUF','inputs':{'unet_name':'MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf'}}
    graph['turbo']={'class_type':'MiniMaxH3TurboLoRA','inputs':{'model':['105:6',0],'lora_name':'minimax_h3_turbo_v4_step600_ema.safetensors','strength':1.0,'low_vram':True}}
    graph['105:9']['inputs'].update(steps=8,model=['turbo',0]);graph['105:16']['inputs']['model']=['turbo',0]
    graph['105:17']={'class_type':'MiniMaxH3TurboSampler','inputs':{}}
    graph['105:15']['inputs']['noise_seed']=2026110102;graph['105:111']['inputs']['value']=3.0
    graph['105:104']['inputs'].update(prompt=(HERE/'motion-prompt-v02.txt').read_text(encoding='utf-8'),width=768,height=448,first_frame=['start',0])
    graph['105:104']['inputs'].pop('last_frame',None)
    graph['start']={'class_type':'LoadImage','inputs':{'image':'start.png'}}
    graph['92']['inputs']['filename_prefix']=job+'/MiniMax_H3_Tibo_Applause'
    if (dest/'graph.json').exists():
        if runner.read(dest/'graph.json')!=graph:raise ValueError('Frozen graph changed')
    else:runner.save(dest/'graph.json',graph)
    (dest/'prompt.txt').write_text((HERE/'motion-prompt-v02.txt').read_text(encoding='utf-8'),encoding='utf-8')
    return dest,graph,frame,frame

def verify(job,settings,dest,graph,source,frame,history,task_id):
    entry=history[task_id]
    if not (dest/'history.json').exists():runner.save(dest/'history.json',history)
    if entry['status'].get('status_str')!='success' or not entry['status'].get('completed'):raise RuntimeError('Generation failed; no resubmission')
    if entry['prompt'][2]!=graph:raise ValueError('Graph identity differs')
    files=list(runner.video_entries(entry['outputs']['92']))
    if len(files)!=1:raise ValueError('Unexpected output count')
    raw=(OUT/files[0]['subfolder']/files[0]['filename']).resolve()
    if not raw.is_relative_to(dest):raise ValueError('Output scope mismatch')
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(raw)]))
    stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    if (stream['width'],stream['height'],stream['avg_frame_rate'],int(stream['nb_frames']))!=(768,448,'24/1',76):raise ValueError('Unexpected geometry')
    subprocess.run(['ffmpeg','-v','error','-nostdin','-xerror','-i',str(raw),'-f','null','-'],check=True,creationflags=runner.FLAGS)
    sheet=dest/'contact-sheet.jpg'
    if not sheet.exists():subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-i',str(raw),'-vf','fps=2,scale=384:216,tile=4x3','-frames:v','1','-q:v','2',str(sheet)],check=True,creationflags=runner.FLAGS)
    messages=entry['status']['messages'];begin=next(m[1]['timestamp'] for m in messages if m[0]=='execution_start');end=next(m[1]['timestamp'] for m in messages if m[0]=='execution_success')
    proof=dict(schema_version=1,provider='minimax',mode='local_h3_i2va',base='Q3_K_M',text_encoder='Q4_K_M',turbo=True,steps=8,seed=2026110102,first_frame=runner.record(frame),execution=dict(prompt_id=task_id,success=True,elapsed_seconds=(end-begin)/1000),artifact=dict(runner.record(raw),full_decode_verified=True,probe=probe),review_status='awaiting_visual_review',user_approved=False,paid_minimax_api_calls=0)
    if not (dest/'verification.json').exists():runner.save(dest/'verification.json',proof)
    print(json.dumps(dict(event='generation_verified',artifact=runner.record(raw),elapsed_seconds=(end-begin)/1000)),flush=True)

runner.ensure_runtime=ensure_runtime;runner.prepare=prepare;runner.verify=verify
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    runner.generate('applause',{},a.prepare_only)
