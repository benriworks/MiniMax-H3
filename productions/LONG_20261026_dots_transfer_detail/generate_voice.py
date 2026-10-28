"""Generate only unsubmitted dialogue turns with the shared 22-second cadence."""
from pathlib import Path
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/productions' / HERE.name / 'v01'
sys.path.insert(0, str(ROOT))
from tools.studio.dialogue_narration import synthesize
from prepare_script import save


def main():
    script = json.loads((HERE / 'script-v01.json').read_text(encoding='utf-8'))
    spec = importlib.util.spec_from_file_location('shared_cadence', ROOT / 'productions/SERIES_20261022_dots_finale/produce.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    save(OUT / 'voice/plan.json', dict(script=script, maximum_requests=40, automatic_retry=False,
         model=shared.speech.MODEL, user_approved=False, male_voice='Charon is a new dialogue candidate; female remains selected Aoede'))
    with shared.generation_lock():
        cadence = shared.SubmissionCadence()
        for chapter in script['chapters']:
            for i, turn in enumerate(chapter['turns']):
                target = OUT / 'voice' / chapter['id'] / f'turn-{i:02d}'
                if not target.exists():
                    cadence.before_submission()
                profile = 'quoted_dialogue_v2' if chapter['id']=='chapter-11' and i==0 else 'standard'
                proof = synthesize(target, turn['spoken'], turn['speaker'], profile)
                print(json.dumps(dict(chapter=chapter['id'], turn=i, seconds=proof['seconds'], speaker=turn['speaker'])), flush=True)
    print('All 40 turns verified; final listening pending', flush=True)


if __name__ == '__main__':
    main()
