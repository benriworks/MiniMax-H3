"""Bounded sequential TTS; no automatic retry of ambiguous outcomes."""
from pathlib import Path
import json,os,sys,time
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize
if not os.environ.get('GEMINI_API_KEY'):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as k:
        os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(k,'GEMINI_API_KEY')[0]
script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'))
for t in script['turns']:
    target=ROOT/'outputs/content-projects'/HERE.name/'voice/v01'/t['id']
    cached=(target/'verified.json').exists()
    p=synthesize(target,t['text'],t['speaker'],profile='conversational_v3')
    print(t['id'],round(p['seconds'],2),'cached' if cached else 'new',flush=True)
    if not cached:time.sleep(22)
