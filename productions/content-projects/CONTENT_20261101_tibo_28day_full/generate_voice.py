"""Sequential cached paid TTS; no retries after ambiguous/rejected outcomes."""
from pathlib import Path
import json,os,sys,time,winreg
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize
if not os.getenv('GEMINI_API_KEY'):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(key,'GEMINI_API_KEY')[0]
script=json.loads((HERE/'script-v01.json').read_text(encoding='utf-8'))
out=ROOT/'outputs/content-projects'/HERE.name/'voice/v01'
previous=0
for turn in script['turns']:
    target=out/turn['id'];cached=(target/'verified.json').exists()
    if not cached:time.sleep(max(0,22-(time.monotonic()-previous)))
    proof=synthesize(target,turn['text'],turn['speaker'],profile='conversational_v3')
    if not cached:previous=time.monotonic()
    print(json.dumps(dict(id=turn['id'],speaker=turn['speaker'],seconds=proof['seconds'],cached=cached)),flush=True)
print('All dialogue turns technically verified; listening pending.',flush=True)
