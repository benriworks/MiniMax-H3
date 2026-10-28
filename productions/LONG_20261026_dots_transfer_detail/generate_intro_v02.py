"""Submit only three new opening lines; retain all existing main narration."""
from pathlib import Path
import importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v02'
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize


def main():
    config=json.loads((HERE/'revision-v02.json').read_text(encoding='utf-8'))
    spec=importlib.util.spec_from_file_location('shared_intro_cadence',ROOT/'productions/SERIES_20261022_dots_finale/produce.py')
    shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
    root=OUT/'voice/opening';root.mkdir(parents=True,exist_ok=True)
    plan=root.parent/'plan.json'
    expected=dict(maximum_requests=3,automatic_retry=False,turns=config['opening_turns'],reused_main_turns=40)
    if plan.exists():
        if json.loads(plan.read_text(encoding='utf-8'))!=expected:raise ValueError('Changed intro plan')
    else:plan.write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
    with shared.generation_lock():
        cadence=shared.SubmissionCadence()
        for i,turn in enumerate(config['opening_turns']):
            target=root/f'turn-{i:02d}'
            if not target.exists():cadence.before_submission()
            proof=synthesize(target,turn['spoken'],turn['speaker'],'quoted_dialogue_v2')
            print(json.dumps(dict(turn=i,seconds=proof['seconds'],speaker=turn['speaker'])),flush=True)


if __name__=='__main__':main()
