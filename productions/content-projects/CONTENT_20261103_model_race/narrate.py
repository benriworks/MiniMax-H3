"""Generate versioned Gemini dialogue after actual outline acceptance; no retries."""
from pathlib import Path
import argparse,json,os,sys,time
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize
from workspace_record import cli
OUT=ROOT/'outputs/content-projects'/HERE.name

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--video',choices=['short','full','all'],default='all');parser.add_argument('--limit',type=int);args=parser.parse_args()
    state=cli('get',project_id=HERE.name)['project']
    if not state['accepted_proposal'] or state['accepted_proposal']['proposal_id']!='proposal-v01':raise RuntimeError('Outline not accepted')
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(key,'GEMINI_API_KEY')[0]
    turns=[]
    for kind in (['short','full'] if args.video=='all' else [args.video]):turns+=json.loads((HERE/f'{kind}-dialogue-v03.json').read_text(encoding='utf-8'))['turns']
    pending=0;last=0
    for t in turns:
        target=OUT/'voice/v01'/t['id'];cached=(target/'verified.json').is_file()
        if not cached and args.limit is not None and pending>=args.limit:break
        if not cached and last:time.sleep(max(0,22-(time.monotonic()-last)))
        result=synthesize(target,t['reading'],t['speaker'],profile='conversational_v3')
        if not cached:last=time.monotonic();pending+=1
        print(json.dumps(dict(id=t['id'],speaker=t['speaker'],seconds=round(result['seconds'],3),cached=cached)),flush=True)

if __name__=='__main__':main()
