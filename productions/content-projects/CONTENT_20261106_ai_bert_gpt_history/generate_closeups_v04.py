"""Two new close reaction shots; preserve the accepted duo and all old jobs."""
import importlib.util
import json
import shutil
from pathlib import Path

import generate_motion as base

base.OUT=base.ROOT/'outputs/content-projects'/base.HERE.name/'motions/v04-closeups'
base.INPUT=base.OUT/'input'
base.runner.OUT=base.OUT
base.runner.INPUT=base.INPUT
original_prepare=base.prepare


def prepare(job,item):
    # The proven graph/runtime stays identical; only frozen first frames and
    # prompts are new, in a separate output root with its own service.
    dest=base.OUT/job;dest.mkdir(parents=True,exist_ok=True)
    source=base.ROOT/'outputs/content-projects'/base.HERE.name/'characters/v04'/(item['who']+'-close-input.png')
    frame=base.INPUT/job/'keyframe.png';frame.parent.mkdir(parents=True,exist_ok=True)
    if not frame.exists():shutil.copy2(source,frame)
    if base.runner.record(frame)['sha256']!=base.runner.record(source)['sha256']:raise RuntimeError('Frozen input changed')
    prompt=item['prompt'];path=dest/'prompt.txt'
    if path.exists() and path.read_text(encoding='utf-8')!=prompt:raise RuntimeError('Frozen prompt changed')
    if not path.exists():path.write_text(prompt,encoding='utf-8')
    graph=base.runner.read(base.RUNTIME/'outputs/claude-acquired-20260919/graph.json')
    graph['105:6']={'class_type':'UnetLoaderGGUF','inputs':{'unet_name':'MiniMax-H3-FL2VA-Pruned-Q3_K_M.gguf'}}
    graph['105:13']['inputs']['clip_name']='qwen3vl-32B-MiniMax-H3-Q2_K.gguf'
    graph['105:104']['inputs'].update(prompt=prompt,first_frame=['keyframe',0],width=480,height=864)
    graph['keyframe']={'class_type':'LoadImage','inputs':{'image':job+'/keyframe.png'}}
    graph['turbo-lora']={'class_type':'MiniMaxH3TurboLoRA','inputs':{'model':['105:6',0],'lora_name':'minimax_h3_turbo_v4_step600_ema.safetensors','strength':1.0,'low_vram':True}}
    graph['105:9']['inputs'].update(steps=8,model=['turbo-lora',0]);graph['105:16']['inputs']['model']=['turbo-lora',0]
    graph['105:17']={'class_type':'MiniMaxH3TurboSampler','inputs':{}}
    graph['105:15']['inputs']['noise_seed']=item['seed'];graph['92']['inputs']['filename_prefix']=job+'/MiniMax_H3_'+job.replace('-','_')
    path=dest/'graph.json'
    if path.exists() and base.runner.read(path)!=graph:raise RuntimeError('Frozen graph changed')
    if not path.exists():base.runner.save(path,graph)
    return dest,graph,source,frame


base.runner.prepare=prepare
if __name__=='__main__':
    jobs=base.runner.read(base.HERE/'motion-prompts-v04-closeups.json')['jobs']
    for job,item in jobs.items():base.runner.generate(job,item,False)
