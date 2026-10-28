"""Bounded conversational re-recording; durable per-turn requests and no retries."""
from pathlib import Path
import importlib.util,json,sys
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/productions'/HERE.name/'v03'
sys.path.insert(0,str(ROOT))
from tools.studio.dialogue_narration import synthesize


def main():
    script=json.loads((HERE/'script-v03.json').read_text(encoding='utf-8'))
    chapters=[dict(id='opening',turns=script['opening']),*script['chapters']]
    spec=importlib.util.spec_from_file_location('dialogue_cadence_v3',ROOT/'productions/SERIES_20261022_dots_finale/produce.py')
    shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
    voice=OUT/'voice';voice.mkdir(parents=True,exist_ok=True)
    expected=dict(maximum_requests=sum(len(c['turns']) for c in chapters),automatic_retry=False,
        model=shared.speech.MODEL,profile='conversational_v3',chapters=chapters)
    frozen=voice/'plan.json'
    if frozen.exists():
        if json.loads(frozen.read_text(encoding='utf-8'))!=expected:raise ValueError('Changed frozen script; use another version')
    else:frozen.write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
    with shared.generation_lock():
        cadence=shared.SubmissionCadence()
        for chapter in chapters:
            for i,line in enumerate(chapter['turns']):
                target=voice/chapter['id']/f'turn-{i:02d}'
                if not target.exists():cadence.before_submission()
                proof=synthesize(target,line['spoken'],line['speaker'],'conversational_v3')
                print(json.dumps(dict(chapter=chapter['id'],turn=i,speaker=line['speaker'],seconds=proof['seconds'])),flush=True)
    print('All conversational voices received; listening review remains separate',flush=True)


if __name__=='__main__':main()
