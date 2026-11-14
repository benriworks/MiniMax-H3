"""Produce local review narration when Gemini returns a billing rejection."""
from pathlib import Path
from hashlib import sha256
import argparse
import json
import re
import subprocess

from narrate import HERE, OUT, READINGS, WORDS
from tools.studio.longform_audio import read_voice

VOICES = {"female": ("Microsoft Sayaka", 0), "male": ("Microsoft Ichiro", 0)}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--pwsh", default="pwsh")
    args = parser.parse_args()
    story = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    root = OUT / "voice" / ("local-samples" if args.sample else "local-v01")
    if root.exists():
        raise FileExistsError(f"Preserve the previous voice run: {root}")
    selects = [(scene["id"], i, turn) for kind in ("short", "full") for scene in story[kind]
               for i, turn in enumerate(scene["turns"])
               if not args.sample or scene["id"] in {"s-board", "f-join"}]
    manifest = []
    evidence = []
    for scene_id, index, turn in selects:
        folder = root / scene_id / f"turn-{index:02d}"
        folder.mkdir(parents=True)
        raw = folder / "source.wav"
        reading = WORDS.sub(lambda match: READINGS[match[0]], turn["text"])
        reading = re.sub(r"11月12日", "十一月十二日", reading)
        reading = re.sub(r"11月13日", "十一月十三日", reading)
        voice, rate = VOICES[turn["speaker"]]
        manifest.append(dict(voice=voice, rate=rate, reading=reading, dest=str(raw)))
        evidence.append((folder, turn, raw))
    request = root / "requests.json"
    write(request, manifest)
    finished = subprocess.run([args.pwsh, "-NoProfile", "-NonInteractive", "-File",
                               str(HERE / "local_voice_worker.ps1"), "-ManifestPath", str(request)],
                              capture_output=True, text=True, encoding="utf-8")
    if finished.returncode:
        raise RuntimeError(finished.stderr.strip() or "Windows speech synthesis failed.")
    environment = json.loads(finished.stdout)
    for (folder, turn, original), line in zip(evidence, manifest, strict=True):
        target = folder / "voice.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(original),
                        "-af", "highpass=f=72", "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le",
                        str(target)], check=True)
        seconds = len(read_voice(target)) / 24000
        if not 1.5 < seconds < 40:
            raise ValueError(f"Unexpected narration duration: {seconds:.2f}")
        provenance = dict(engine="Windows SAPI via System.Speech", voice=line["voice"],
                          speaker=turn["speaker"], reading=line["reading"], display=turn["text"],
                          rate=line["rate"], source_sha256=digest(original), sha256=digest(target),
                          seconds=seconds, **environment)
        write(folder / "provenance.json", provenance)
        print(f"{folder.parent.name}/{folder.name}: {line['voice']} {seconds:.2f}s")


if __name__ == "__main__":
    main()
