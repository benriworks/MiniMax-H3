"""Record each approved series voice once and preserve the per-line provider receipt."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("media", type=Path)
    parser.add_argument("--only", nargs="+")
    parser.add_argument("--take", default="v01")
    args = parser.parse_args()
    media = args.media.resolve()
    sys.path.insert(0, str(media.parents[2]))
    from tools.studio.dialogue_narration import synthesize

    scenes = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    readings = json.loads((HERE / "readings-v01.json").read_text(encoding="utf-8"))
    selected = [s for s in scenes if not args.only or s["id"] in args.only]
    output_name = "selected"
    if args.take != "v01":
        revised = json.loads((HERE / f"revision-{args.take}.json").read_text(encoding="utf-8"))
        selected = [s for s in selected if s["id"] in revised]
        readings.update({key:item["reading"] for key,item in revised.items()})
        output_name = f"selected-{args.take}"
        for scene in scenes:
            if scene["id"] not in revised:
                src = media / "voice/selected" / scene["id"]
                shutil.copytree(src,media/"voice"/output_name/scene["id"],dirs_exist_ok=True)

    def generate(scene):
        sid = scene["id"]
        target = media / "voice" / args.take / sid
        line = readings[sid]
        proof = synthesize(target, line, scene["speaker"], profile="conversational_v3")
        out = media / "voice" / output_name / sid / "turn-00"
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target / "voice.wav", out / "voice.wav")
        (out / "source.json").write_text(json.dumps({"take":args.take,"sha256":proof["files"][0]["sha256"]}), encoding="utf-8")
        print(sid, proof["voice"], round(proof["seconds"],2), flush=True)

    for item in selected[:2]:
        generate(item)
    failed = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(generate, item):item["id"] for item in selected[2:]}
        for job in as_completed(jobs):
            try:
                job.result()
            except Exception as err:
                failed.append(jobs[job])
                print(jobs[job], type(err).__name__, str(err)[:130], flush=True)
    if failed:
        raise SystemExit("Inspect provider receipts before a new take: "+", ".join(failed))


if __name__ == "__main__":
    main()
