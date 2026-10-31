"""Six isolated H3 I2VA reactions; durable submission and original monitoring."""
from pathlib import Path
import argparse,importlib.util,json,shutil,sys
from PIL import Image,ImageOps

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
MEDIA_ROOT=Path('C:/Users/mono_/MiniMaxH3')
PROJECT=ROOT/'outputs/content-projects'/HERE.name
OUT=PROJECT/'motions/v01';INPUT=OUT/'input';URL='http://127.0.0.1:8191'
spec=importlib.util.spec_from_file_location('durable_h3_runner',ROOT/'productions/CHARACTERS_20261022_explainer_motion/generate.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.ROOT=ROOT;runner.OUT=OUT;runner.INPUT=INPUT;runner.PRODUCTION=HERE;runner.URL=URL

def prompt(item):
 return ('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n\n'
  'integrated_multimodal_description: [Shot 1] A single continuous five-second vertical stylized 3D anime shot. '
  'Preserve exactly the identity, adult age, face, hair, clothing, body shape, seated position, laptop, desk, dark uncluttered room and cyan-magenta rim lighting in Picture 1. '
  'The only person is '+item['identity']+'. '+item['motion']+' '
  'The camera holds a static shot. Keep the face and all active hands visible, with coherent anatomy, exactly two arms, and natural hands. '
  'Keep background, chair, laptop shape and lighting stable. Keep the mouth closed after the initial frame: no talking, lip-sync, vocalizations, extra people, extra objects, confetti, crystals, generated words, logos or watermarks. '
  'Use readable, distinctly different gestures with continuous purposeful motion through the final second; no rapid camera movement, abrupt pose jumps or morphing.\n\n'
  'overall_soundscape: Quiet indoor room ambience with faint clothing movement. No speech, singing or dramatic sound effects.\n\n'
  'non_diegetic_music: N/A\n')

def ensure_runtime():
 stats=runner.request('/system_stats');args=stats.get('system',{}).get('argv',[])
 if '--port' not in args or args[args.index('--port')+1]!='8191' or str(OUT) not in args or str(INPUT) not in args:raise RuntimeError('Not the dedicated reaction-motion runtime')
 return stats

def prepare(job,item):
 dest=OUT/job;dest.mkdir(parents=True,exist_ok=True)
 source=PROJECT/f"characters/{item['who']}-reference.png"
 target=INPUT/job/'keyframe.png';target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():
  with Image.open(source) as im:ImageOps.fit(im.convert('RGB'),(768,1376),method=Image.Resampling.LANCZOS).save(target)
 expected=prompt(item);p=dest/'prompt.txt'
 if p.exists() and p.read_text(encoding='utf-8')!=expected:raise RuntimeError('Frozen prompt changed')
 if not p.exists():p.write_text(expected,encoding='utf-8')
 graph=runner.read(MEDIA_ROOT/'outputs/claude-acquired-20260919/graph.json')
 graph['105:104']['inputs'].update(prompt=expected,first_frame=['keyframe',0],width=768,height=1376)
 graph['keyframe']={'class_type':'LoadImage','inputs':{'image':job+'/keyframe.png'}}
 graph['105:15']['inputs']['noise_seed']=item['seed']
 graph['92']['inputs']['filename_prefix']=job+'/MiniMax_H3_'+job.replace('-','_')
 p=dest/'graph.json'
 if p.exists() and runner.read(p)!=graph:raise RuntimeError('Frozen graph changed')
 if not p.exists():runner.save(p,graph)
 return dest,graph,source,target

runner.ensure_runtime=ensure_runtime;runner.prepare=prepare
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--prepare-only',action='store_true');p.add_argument('--job',action='append');a=p.parse_args()
 jobs=runner.read(HERE/'motion-jobs-v01.json')['jobs']
 for name in (a.job or list(jobs)):
  item=dict(jobs[name],source=f'outputs/content-projects/{HERE.name}/characters/{jobs[name]["who"]}-reference.png')
  runner.generate(name,item,a.prepare_only)
