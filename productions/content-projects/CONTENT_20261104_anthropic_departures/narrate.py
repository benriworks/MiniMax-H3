"""Six accepted lines, cached Gemini speech and no automatic resubmission."""
from pathlib import Path
import json,os,sys,time
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize
from workspace_record import cli
OUT=ROOT/'outputs/content-projects'/HERE.name

def main():
    project=cli('get',project_id=HERE.name)['project']
    if not project['accepted_proposal'] or project['accepted_proposal']['proposal_id']!='proposal-v01':
        raise RuntimeError('Accepted proposal-v01 is required')
    if not os.getenv('GEMINI_API_KEY'):
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as registry:
            os.environ['GEMINI_API_KEY']=winreg.QueryValueEx(registry,'GEMINI_API_KEY')[0]
    script=json.loads((HERE/'short-dialogue-v01.json').read_text(encoding='utf-8'))
    last=0
    for turn in script['turns']:
        target=OUT/'voice/v01'/turn['id'];cached=(target/'verified.json').is_file()
        if not cached and last:time.sleep(max(0,22-(time.monotonic()-last)))
        proof=synthesize(target,turn['reading'],turn['speaker'],profile='conversational_v3')
        if not cached:last=time.monotonic()
        print(json.dumps(dict(id=turn['id'],speaker=turn['speaker'],seconds=round(proof['seconds'],3),cached=cached)),flush=True)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
