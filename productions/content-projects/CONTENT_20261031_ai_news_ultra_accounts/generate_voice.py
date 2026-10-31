"""Bounded Aoede requests for the two user-specified news briefs; no automatic retry."""
from pathlib import Path
import importlib.util,json,os,sys,time

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
OUT=ROOT/'outputs/content-projects'/HERE.name
sys.path.insert(0,str(ROOT))

def main():
    if not (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')) and os.name=='nt':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
                os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(key,'GEMINI_API_KEY')[0]
        except FileNotFoundError:pass
    spec=importlib.util.spec_from_file_location('news_speech',ROOT/'productions/SHORT_20261021_dots_cloud_benefits/gemini_voice_trial.py')
    speech=importlib.util.module_from_spec(spec);spec.loader.exec_module(speech)
    plan=json.loads((HERE/'plan.json').read_text(encoding='utf-8'))
    last=0
    for episode in plan['episodes']:
        for i,scene in enumerate(episode['scenes']):
            parent=OUT/episode['id']/f'voice/v01/scene-{i:02d}'
            parent.mkdir(parents=True,exist_ok=True)
            if not (parent/'Aoede').exists():
                delay=max(0,22-(time.monotonic()-last))
                if delay:time.sleep(delay)
                last=time.monotonic()
            proof=speech.synthesize(parent,scene['spoken'],'Aoede',minimum_seconds=.2)
            print(json.dumps(dict(episode=episode['id'],scene=i,seconds=proof['duration_seconds'],status=proof['status'])),flush=True)

if __name__=='__main__':main()
