"""Generate the two approved voices, preserving Gemini requests and receipts."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--media", required=True, type=Path)
    parser.add_argument("--short-revision", choices=("v02", "v03"))
    args = parser.parse_args()
    media = args.media.resolve()
    sys.path.insert(0, str(media.parents[2]))
    from tools.studio.dialogue_narration import synthesize

    story = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    readings = json.loads((HERE / "tts-v01.json").read_text(encoding="utf-8"))
    source = media / "voice/gemini-v01"
    selected = media / "voice/selected-v01"

    def select(scene, take, out, proof):
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(take / "voice.wav", out / "voice.wav")
        (out / "proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
        print(scene, proof["voice"], round(proof["seconds"], 3), flush=True)

    if args.short_revision:
        revision = args.short_revision
        revised = json.loads((HERE / f"short-{revision}.json").read_text(encoding="utf-8"))
        revised_selected = media / "voice" / f"selected-{revision}"
        for scene, text in revised.items():
            take = media / "voice" / f"gemini-{revision}" / scene
            proof = synthesize(take, text["reading"], "male", profile="conversational_v3")
            select(scene, take, revised_selected / scene / "turn-00", proof)
        for line in story["short"]:
            scene = line["id"]
            if scene not in revised:
                shutil.copytree(selected / scene, revised_selected / scene, dirs_exist_ok=True)
        return

    def generate(line):
        scene = line["id"]
        # Both cuts open with the same line and use the same verified take.
        take = "s01" if scene == "f01" else scene
        proof = synthesize(source / take, readings[scene], line["speaker"],
                           profile="conversational_v3")
        select(scene, source / take, selected / scene / "turn-00", proof)

    generate(story["short"][0])
    generate(story["short"][1])
    remaining = story["short"][2:] + story["full"][1:]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for index in range(0, len(remaining), 3):
            list(pool.map(generate, remaining[index:index + 3]))
    generate(story["full"][0])


if __name__ == "__main__":
    main()
