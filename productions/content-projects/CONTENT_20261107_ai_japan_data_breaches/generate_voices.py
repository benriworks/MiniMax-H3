"""Generate approved-case dialogue in bounded batches with Studio receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

CASE = Path(__file__).resolve().parent
ROOT = CASE.parents[2]
OUT = ROOT / 'outputs/content-projects' / CASE.name
VOICE = OUT / 'voice-v01'
sys.path.insert(0, str(ROOT))

from tools.studio.dialogue_narration import synthesize

PROFILE = 'conversational_v3'


def read_scripts(short_version='v02'):
    def load(name):
        return json.loads((CASE / name).read_text(encoding='utf-8'))
    display = load('dialogue-display-v01.json')
    voice = load('dialogue-tts-v01.json')
    if short_version == 'v02':
        revision = load('dialogue-short-revision-v02.json')
        for rows, field in ((display['short'], 'display'), (voice['short'], 'tts')):
            row = next(row for row in rows if row['id'] == revision['id'])
            row.update(text=revision[field], voice_revision=short_version)
    for kind, rows in display.items():
        assert [(r['id'], r['speaker']) for r in rows] == [(r['id'], r['speaker']) for r in voice[kind]]
    return display, voice


def voice_dir(row):
    revision = row.get('voice_revision')
    return VOICE / (row['id'] if revision is None else f"{row['id']}-{revision}")


def generate(row):
    proof = synthesize(voice_dir(row), row['text'], row['speaker'], profile=PROFILE)
    return row['id'], round(proof['seconds'], 3), proof.get('usage', {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kind', choices=['short', 'full', 'both'], default='both')
    parser.add_argument('--only', nargs='+')
    parser.add_argument('--short-version', choices=['v01','v02'], default='v02')
    parser.add_argument('--workers', type=int, choices=[1, 2, 3], default=3)
    args = parser.parse_args()
    _, voice = read_scripts(args.short_version)
    kinds = ('short', 'full') if args.kind == 'both' else (args.kind,)
    rows = [row for kind in kinds for row in voice[kind]]
    if args.only:
        rows = [row for row in rows if row['id'] in args.only]
        if len(rows) != len(args.only):
            raise ValueError('Unknown dialogue ID')
    # Do not schedule additional work after a failed wave. Preserve each receipt.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(rows), args.workers):
            futures = [pool.submit(generate, row) for row in rows[offset:offset + args.workers]]
            results = [f.result() for f in futures]
            for row_id, duration, usage in results:
                print(row_id, duration, usage, flush=True)


if __name__ == '__main__':
    main()
