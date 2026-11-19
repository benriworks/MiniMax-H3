"""Speak only the unique approved-for-production lines. Cache each provider receipt."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import json
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.dialogue_narration import synthesize

def load_story(edition):
    story=json.loads((HERE/"story-v01.json").read_text(encoding="utf-8"))
    if edition=="v02":
        patch=json.loads((HERE/"full-v02.json").read_text(encoding="utf-8"))
        scene=next(ch for ch in story["full"] if ch["id"]==patch["chapter"])
        turn=next(t for t in scene["turns"] if t["line"]==patch["replace"])
        turn["line"]=patch["line"]
        story["lines"][patch["line"]]={k:patch[k] for k in ("speaker","text","reading")}
    return story

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("short","full","all"), default="all")
    parser.add_argument("--edition", choices=("v01","v02"), default="v01")
    parser.add_argument("--line", help="Render one named line from this edition")
    args=parser.parse_args()
    story=load_story(args.edition)
    kinds=("short","full") if args.kind=="all" else (args.kind,)
    keys=list(dict.fromkeys(t["line"] for kind in kinds for ch in story[kind] for t in ch["turns"]))
    if args.line:
        if args.line not in keys:parser.error("Line does not occur in the selected cut")
        keys=[args.line]
    cache=OUT/"voice"/"v01"
    cache.mkdir(parents=True,exist_ok=True)
    def speak(key):
        line=story["lines"][key]
        proof=synthesize(cache/key,line["reading"],line["speaker"],profile="conversational_v3")
        print(key,proof["voice"],round(proof["seconds"],2),flush=True)
    speak(keys[0])
    with ThreadPoolExecutor(max_workers=2) as workers:
        for i in range(1,len(keys),2):
            list(workers.map(speak,keys[i:i+2]))
if __name__=="__main__":
    main()
