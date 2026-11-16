"""Generate one recorded voice edition using the shared Gemini or local SAPI path."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import re
import subprocess

from prepare import HERE, OUT, digest, save
from tools.studio.dialogue_narration import synthesize
from tools.studio.longform_audio import read_voice

READINGS = {"Claude": "クロード", "Upper middle": "アッパー ミドル", "Cowork": "コワーク",
            "AI": "エーアイ", "AWS": "エーダブリューエス", "API": "エーピーアイ",
            "ChatGPT": "チャットジーピーティー", "A4": "エーよん",
            "6.40": "ろくてんよんぜろ", "3.87": "さんてんはちなな",
            "3.78": "さんてんななはち", "1.91": "いってんきゅういち",
            "1.0": "いってんぜろ", "％": "パーセント",
            "11月20日": "じゅういちがつ はつか", "24日": "にじゅうよっか",
            "6月26日": "ろくがつ にじゅうろくにち", "2週間": "にしゅうかん"}
TOKENS = re.compile("|".join(re.escape(key) for key in sorted(READINGS, key=len, reverse=True)))
LOCAL = {"female": "Microsoft Sayaka", "male": "Microsoft Ichiro"}


def lines():
    story = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    for kind in ("short", "full"):
        for scene in story[kind]:
            for i, turn in enumerate(scene["turns"]):
                text = turn.get("reading") or TOKENS.sub(lambda match: READINGS[match[0]], turn["text"])
                yield kind, scene["id"], f"turn-{i:02d}", turn, text


def render_gemini(turns):
    root = OUT / "voice/gemini-v01"
    # Create scene folders before starting workers. Concurrent creation can
    # make Windows resolve one sibling with an extended path prefix.
    for _, scene, _, _, _ in turns:
        (root / scene).mkdir(parents=True, exist_ok=True)

    def request(item):
        _, scene, take, turn, text = item
        target = root / scene / take
        proof = synthesize(target, text, turn["speaker"], profile="conversational_v3")
        print(f"{scene}/{take}: {proof['voice']} {proof['seconds']:.2f}s", flush=True)

    first = next(turn for turn in turns if turn[3]["speaker"] == "female")
    request(first)
    remaining = [turn for turn in turns if turn != first]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i in range(0, len(remaining), 2):
            list(pool.map(request, remaining[i:i+2]))
    save(OUT / "voice/selected.json", {"method": "gemini-v01", "voices": {"female": "Aoede", "male": "Charon"}})


def render_local(turns):
    root = OUT / "voice/local-v01"
    if root.exists():
        raise FileExistsError("Preserve the existing local voice edition")
    requests = []
    for kind, scene, take, turn, reading in turns:
        target = root / scene / take
        target.mkdir(parents=True)
        requests.append(dict(voice=LOCAL[turn["speaker"]], rate=2 if kind == "short" else 0,
                             reading=reading, dest=str(target / "source.wav")))
    manifest = root / "requests.json"
    save(manifest, requests)
    generated = subprocess.run(["pwsh", "-NoProfile", "-NonInteractive", "-File",
                                str(HERE / "local_voice_worker.ps1"), "-ManifestPath", str(manifest)],
                               capture_output=True, encoding="utf-8")
    if generated.returncode:
        raise RuntimeError(generated.stderr.strip() or "Local SAPI failed")
    version = json.loads(generated.stdout)
    for item, request in zip(turns, requests, strict=True):
        _, scene, take, turn, reading = item
        raw = root / scene / take / "source.wav"
        voice = raw.with_name("voice.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(raw),
                        "-af", "highpass=f=72", "-ar", "24000", "-ac", "1",
                        "-c:a", "pcm_s16le", str(voice)], check=True)
        seconds = len(read_voice(voice)) / 24000
        if not 1 < seconds < 32:
            raise ValueError(f"{scene}/{take} unexpected duration {seconds}")
        save(raw.with_name("provenance.json"), dict(request, dest=raw.name, display=turn["text"],
             voice_hash=digest(voice), seconds=seconds, versions=version))
        print(f"{scene}/{take}: {request['voice']} {seconds:.2f}s", flush=True)
    save(OUT / "voice/selected.json", {"method": "local-v01", "voices": LOCAL})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=("gemini", "local"))
    args = parser.parse_args()
    try:
        (render_gemini if args.provider == "gemini" else render_local)(list(lines()))
    except (ValueError, RuntimeError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
