"""Select verified v01 speech and render only the three revised lines."""
import json
from pathlib import Path
import shutil

from prepare import HERE, OUT, ROOT, digest, save
from narrate import TOKENS, READINGS
from tools.studio.dialogue_narration import synthesize

BASE_STORY = HERE / "story-v01.json"
REVISION = HERE / "story-short-v02.json"
SELECTED = OUT / "voice/selected-short-v02.json"
METHOD = "gemini-short-v02"


def revised_story():
    story = json.loads(BASE_STORY.read_text(encoding="utf-8"))
    edits = {scene["id"]: scene for scene in json.loads(REVISION.read_text(encoding="utf-8"))}
    if not set(edits) <= {scene["id"] for scene in story["short"]}:
        raise ValueError("A revision references an unknown short scene")
    story["short"] = [edits.get(scene["id"], scene) for scene in story["short"]]
    return story


def voice_source(story):
    takes = {}
    for scene in story["short"]:
        for index, turn in enumerate(scene["turns"]):
            key = (scene["id"], turn["speaker"], turn["text"], turn.get("reading"))
            takes[key] = Path(scene["id"]) / f"turn-{index:02}"
    return takes


def generate():
    old_story = json.loads(BASE_STORY.read_text(encoding="utf-8"))
    old_takes = voice_source(old_story)
    base = json.loads((OUT / "voice/selected.json").read_text(encoding="utf-8"))
    voices = base["voices"]
    chosen, reuses, requests = [], [], []
    for key, target in voice_source(revised_story()).items():
        scene, speaker, phrase, reading = key
        item = {"path": target, "speaker": speaker, "phrase": phrase, "reading": reading}
        old = old_takes.get(key)
        if old is None:
            requests.append(item)
        else:
            reuses.append((old, item))
    revision_root = OUT / "voice" / METHOD
    for source, item in reuses:
        directory = OUT / "voice" / base["method"] / source
        proof = json.loads((directory / "verified.json").read_text(encoding="utf-8"))
        original = directory / "voice.wav"
        actual = digest(original)
        if proof["voice"] != voices[item["speaker"]] or not any(
                value["sha256"].lower() == actual and ROOT / value["path"] == original
                for value in proof["files"]):
            raise ValueError(f"Prior narration verification failed: {source}")
        dest = revision_root / item["path"] / "voice.wav"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copyfile(original, dest)
        if digest(dest) != actual:
            raise ValueError(f"Reused narration differs: {dest.name}")
        chosen.append(dict(path=item["path"].as_posix(), source=source.as_posix(),
                           voice=proof["voice"], sha256=actual, status="reused"))
    for item in requests:
        dest = revision_root / item["path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        text = item["reading"] or TOKENS.sub(lambda match: READINGS[match[0]], item["phrase"])
        proof = synthesize(dest, text, item["speaker"], profile="conversational_v3")
        if proof["voice"] != voices[item["speaker"]]:
            raise ValueError("The new turn did not use the established voice")
        print(f"{item['path']} {proof['voice']} {proof['seconds']:.3f}s", flush=True)
        chosen.append(dict(path=item["path"].as_posix(), voice=proof["voice"],
                           sha256=digest(dest / "voice.wav"), seconds=proof["seconds"], status="generated"))
    save(SELECTED, dict(method=METHOD, voices=voices))
    save(revision_root / "takes.json", chosen)
    print(f"{len(reuses)} reused, {len(requests)} new turns")


if __name__ == "__main__":
    generate()
