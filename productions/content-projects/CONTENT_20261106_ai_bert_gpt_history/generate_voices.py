"""Generate frozen Gemini Aoede/Charon turns; never retry ambiguous/rejected calls."""
from pathlib import Path
import argparse,json,os,sys

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize

def key_from_user_environment():
    if os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'):return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
        for name in ['GEMINI_API_KEY','GOOGLE_API_KEY']:
            try:value=winreg.QueryValueEx(key,name)[0]
            except FileNotFoundError:continue
            if value:os.environ[name]=value;return
    raise RuntimeError('No configured Gemini key; values are never printed')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('kind',choices=['short','full']);p.add_argument('--turn',action='append');p.add_argument('--script-version',default='v01');a=p.parse_args()
    if not (HERE/'adoption-v01.json').is_file():raise RuntimeError('Outline and character adoption required')
    key_from_user_environment()
    data=json.loads((HERE/(a.kind+'-dialogue-'+a.script_version+'.json')).read_text(encoding='utf-8'))
    for t in data['turns']:
        if a.turn and t['id'] not in a.turn:continue
        proof=synthesize(ROOT/'outputs/content-projects'/HERE.name/'voice/v01'/t['id'],t['spoken'],t['speaker'],profile='conversational_v3')
        print(json.dumps(dict(turn=t['id'],voice=proof['voice'],seconds=proof['seconds'],status=proof['status'])),flush=True)
