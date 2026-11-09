"""Repair four dialogue readings while preserving video, captions, and cut times."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess

import numpy as np

from narrate import HERE, OUT, reading, synthesize
from produce import CREATION, digest, read, save
from remix_local import music_samples, remix, source_music
from tools.studio.longform_audio import SR, read_voice, write_pcm

TARGETS = {("f10", 0): "予想の読み",
           ("f13", 0): "Mythosの読みを統一",
           ("f18", 0): "方がいいの助詞を明瞭に",
           ("f18", 1): "Mythos 5.2の読みを統一"}


def pronunciation(scene, index, text):
    if (scene, index) == ("f18", 0):
        return "さいごの図は、数字が小さいほうが、いい？"
    value = text.replace("予想", "よそう").replace("Mythos 5.2", "ミュトス ファイブ・ポイント・ツー")
    return reading(value.replace("Mythos", "ミュトス"))


def generate(item):
    scene, index, turn, folder = item
    synthesize(folder, pronunciation(scene, index, turn["text"]), turn["speaker"], profile="conversational_v3")
    print(f"{scene}/{index} rerecorded", flush=True)


def align(voice, samples):
    original = read_voice(voice)
    rate = (len(original)+round(.05*SR))/samples
    if not .76 <= rate <= 1.30:
        raise ValueError(f"Reading needs a different take: tempo {rate:.3f}")
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(voice), "-af",
         f"atempo={rate:.8f},apad=whole_len={samples},atrim=end_sample={samples}",
         "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
        check=True, capture_output=True, creationflags=CREATION).stdout
    out = np.frombuffer(pcm, dtype="<f4").copy()
    if len(out) != samples or np.max(np.abs(out[-round(.015*SR):])) > .045:
        raise ValueError("Replacement does not end cleanly at the original cut")
    return out, rate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    initial = OUT/"release/v01/full"
    dest = OUT/"release/v03/full"
    if (dest/"fable-5-2-full-v03.mp4").exists():
        raise FileExistsError("Preserve existing review candidates")
    timeline = read(initial/"timeline.json")
    tasks = []
    for chapter in timeline["chapters"]:
        scene = chapter["scene"]
        for index, turn in enumerate(chapter["turns"]):
            if (scene, index) in TARGETS:
                folder = OUT/"voice/v02"/scene/f"turn-{index:02d}"
                folder.parent.mkdir(parents=True, exist_ok=True)
                tasks.append((scene,index,turn,folder))
    if len(tasks) != len(TARGETS):
        raise ValueError("Unexpected dialogue structure")
    with ThreadPoolExecutor(max_workers=2) as pool:
        for offset in range(0, len(tasks), 2):
            list(pool.map(generate, tasks[offset:offset+2]))
    speech = read_voice(initial/"work/narration.wav")
    receipts = []
    for scene,index,turn,folder in tasks:
        start = round(turn["start"]*SR)
        samples = len(read_voice(Path(turn["voice_path"])))
        replacement, rate = align(folder/"voice.wav", samples)
        speech[start:start+samples] = replacement
        receipts.append(dict(scene=scene, turn=index, start=turn["start"], end=turn["end"],
                             reason=TARGETS[(scene,index)], tempo=rate, source_sha256=digest(folder/"voice.wav")))
    dest.mkdir(parents=True, exist_ok=True)
    voice = dest/"narration-repaired.wav"
    write_pcm(voice, speech)
    save(dest/"voice-repair.json", receipts)
    local = source_music(args.inventory)
    samples, lufs, gain = music_samples(local)
    remix("full", local, samples, lufs, gain, revision="v03", narration=voice)


if __name__ == "__main__":
    main()
