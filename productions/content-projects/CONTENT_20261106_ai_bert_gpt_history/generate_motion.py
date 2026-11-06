"""Accepted scientist duo: local H3 reactions with frozen inputs and durable jobs."""
from pathlib import Path
import argparse, importlib.util, json, shutil, subprocess, sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
OUT=ROOT/'outputs/content-projects'/HERE.name/'motions/v03-q2'
INPUT=OUT/'input'
URL='http://127.0.0.1:8192'
RUNTIME=Path('C:/Users/mono_/MiniMaxH3')
spec=importlib.util.spec_from_file_location('ai_history_durable_h3',ROOT/'productions/CHARACTERS_20261022_explainer_motion/generate.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.ROOT=ROOT;runner.OUT=OUT;runner.INPUT=INPUT;runner.URL=URL;runner.PRODUCTION=HERE

def ready_resources(sample):
    # The Q3 diffusion pilot reduces both weight and activation memory.
    # Retain 12 GiB free physical RAM, 22 GiB commit headroom and the
    # independent critical-pressure interruption from the durable wrapper.
    return (sample['ram_available_bytes']>=12*runner.GIB
            and sample['commit_available_bytes']>=22*runner.GIB
            and sample['disk_free_bytes']>=20*runner.GIB)

def ensure_runtime():
    stats=runner.request('/system_stats');args=stats.get('system',{}).get('argv',[])
    if '--port' not in args or args[args.index('--port')+1]!='8192' or str(OUT) not in args or str(INPUT) not in args:
        raise RuntimeError('Not this isolated production service')
    if not (HERE/'adoption-v01.json').is_file():raise RuntimeError('Explicit adoption record required')
    return stats

def prepare(job,item):
    dest=OUT/job;dest.mkdir(parents=True,exist_ok=True)
    source=ROOT/'outputs/content-projects'/HERE.name/'characters/v02'/(item['who']+'-reference-input-v02.png')
    frame=INPUT/job/'keyframe.png';frame.parent.mkdir(parents=True,exist_ok=True)
    if not frame.exists():
        with source.open('rb') as src,frame.open('xb') as dst:shutil.copyfileobj(src,dst)
    if runner.record(frame)['sha256']!=runner.record(source)['sha256']:raise RuntimeError('Frozen reference changed')
    prompt=item['prompt'];path=dest/'prompt.txt'
    if path.exists() and path.read_text(encoding='utf-8')!=prompt:raise RuntimeError('Frozen prompt changed')
    if not path.exists():path.write_text(prompt,encoding='utf-8')
    graph=runner.read(RUNTIME/'outputs/claude-acquired-20260919/graph.json')
    graph['105:6']={'class_type':'UnetLoaderGGUF','inputs':{'unet_name':'MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf'}}
    graph['105:13']['inputs']['clip_name']='qwen3vl-32B-MiniMax-H3-Q2_K.gguf'
    graph['105:104']['inputs'].update(prompt=prompt,first_frame=['keyframe',0],width=480,height=864)
    graph['keyframe']={'class_type':'LoadImage','inputs':{'image':job+'/keyframe.png'}}
    graph['turbo-lora']={'class_type':'MiniMaxH3TurboLoRA','inputs':{'model':['105:6',0],'lora_name':'minimax_h3_turbo_v4_step600_ema.safetensors','strength':1.0,'low_vram':True}}
    graph['105:9']['inputs'].update(steps=8,model=['turbo-lora',0])
    graph['105:16']['inputs']['model']=['turbo-lora',0]
    graph['105:17']={'class_type':'MiniMaxH3TurboSampler','inputs':{}}
    graph['105:15']['inputs']['noise_seed']=item['seed']
    graph['92']['inputs']['filename_prefix']=job+'/MiniMax_H3_'+job.replace('-','_')
    path=dest/'graph.json'
    if path.exists() and runner.read(path)!=graph:raise RuntimeError('Frozen graph changed')
    if not path.exists():runner.save(path,graph)
    return dest,graph,source,frame

def verify(job,item,dest,graph,source,frame,history,prompt_id):
    entry=history[prompt_id]
    if not (dest/'history.json').exists():runner.save(dest/'history.json',history)
    if entry['status'].get('status_str')!='success' or entry['status'].get('completed') is not True:
        raise RuntimeError('Inspect the saved failed history; do not resend')
    if entry['prompt'][2]!=graph:raise RuntimeError('Executed graph differs')
    entries=list(runner.video_entries(entry['outputs']['92']))
    if len(entries)!=1:raise RuntimeError('Unexpected output count')
    raw=(OUT/entries[0]['subfolder']/entries[0]['filename']).resolve()
    if not raw.is_relative_to(dest.resolve()):raise RuntimeError('Output escaped own job')
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(raw)],creationflags=runner.FLAGS))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    if (video['width'],video['height'],video['avg_frame_rate'],int(video['nb_frames']))!=(480,864,'24/1',124):raise RuntimeError('Unexpected output dimensions/frames')
    subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(raw),'-f','null','-'],check=True,creationflags=runner.FLAGS)
    for sec in (0,1,2,3,4):
        target=dest/f'frame-{sec}.png'
        if not target.exists():subprocess.run(['ffmpeg','-v','error','-n','-ss',str(sec),'-i',str(raw),'-frames:v','1',str(target)],check=True,creationflags=runner.FLAGS)
    sheet=dest/'contact-sheet.jpg'
    if not sheet.exists():subprocess.run(['ffmpeg','-v','error','-n','-i',str(raw),'-vf','fps=1,scale=240:-1,tile=5x1','-frames:v','1','-q:v','2',str(sheet)],check=True,creationflags=runner.FLAGS)
    msgs=entry['status']['messages'];begin=next(m[1]['timestamp'] for m in msgs if m[0]=='execution_start');end=next(m[1]['timestamp'] for m in msgs if m[0]=='execution_success')
    proof=dict(schema_version=1,verified_at=runner.now(),provider='minimax',production_id=HERE.name,job=job,mode='I2VA',profile='lowvram_turbo',generation_context='generated_for_this_revision',paid_video_api_calls=0,
        source_keyframe=runner.record(frame),approved_parent=runner.record(ROOT/'outputs/content-projects'/HERE.name/'characters/v02/ai-history-duo-scientists-v02.png'),
        execution=dict(prompt_id=prompt_id,elapsed_seconds=(end-begin)/1000,success=True),settings=dict(seed=item['seed'],steps=8,sampler='MiniMaxH3TurboSampler',low_vram_merge=True,width=480,height=864,fps=24,frames=124,requested_duration_seconds=5),
        artifact=dict(**runner.record(raw),full_decode_verified=True,probe=probe),inputs=[runner.record(dest/n) for n in ['graph.json','prompt.txt','request.json','submission.json','history.json']],contact_sheet=runner.record(sheet),review_status='awaiting_visual_review',userApproved=False)
    if not (dest/'verification.json').exists():runner.save(dest/'verification.json',proof)
    print(json.dumps(dict(event='generation_verified',job=job,path=proof['artifact']['path'],elapsed_seconds=proof['execution']['elapsed_seconds'])),flush=True)

runner.ensure_runtime=ensure_runtime;runner.prepare=prepare;runner.verify=verify;runner.ready_resources=ready_resources

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',action='append');parser.add_argument('--prepare-only',action='store_true');args=parser.parse_args()
    jobs=runner.read(HERE/'motion-prompts-v01-draft.json')['jobs']
    for job in (args.job or list(jobs)):
        if job not in jobs:raise ValueError('Unknown job')
        item=dict(jobs[job],source='outputs/content-projects/'+HERE.name+'/characters/v02/'+jobs[job]['who']+'-reference-input-v02.png')
        runner.generate(job,item,args.prepare_only)
