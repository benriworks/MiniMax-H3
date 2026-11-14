"""Synthesize the frozen short and full dialogue with the Studio speaker presets."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import json
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.dialogue_narration import synthesize

READINGS = {
    "Claude Meetings": "クロード ミーティングス", "Claude Code": "クロード コード",
    "Code Mode": "コードモード", "Claude": "クロード", "Meetings": "ミーティングス",
    "Google Calendar": "グーグルカレンダー", "Google Meet": "グーグルミート",
    "Add Claude": "アド クロード", "Team": "チーム", "Enterprise": "エンタープライズ",
    "JavaScript": "ジャバスクリプト", "2.1.323": "に てん いち てん さんにさん",
    "Fable 5.2": "フェイブル ご てん に", "VS Code": "ブイエスコード",
    "ChatGPT Wallet": "チャットジーピーティー ウォレット", "Codex": "コーデックス", "Pro": "プロ",
    "2027年2月10日": "二千二十七年 二月十日",
}
WORDS = re.compile("|".join(re.escape(word) for word in sorted(READINGS, key=len, reverse=True)))


def generate(item):
    scene, index, turn = item
    target = OUT / "voice/v01" / scene / f"turn-{index:02d}"
    target.parent.mkdir(parents=True, exist_ok=True)
    reading = WORDS.sub(lambda match: READINGS[match[0]], turn["text"])
    try:
        proof = synthesize(target, reading, turn["speaker"], profile="conversational_v3")
    except (ValueError, RuntimeError) as error:
        print(f"{scene}/{index} {type(error).__name__}: {error}", flush=True)
        return False
    select(scene, index, target, proof)
    return True


def select(scene, index, target, proof):
    selected = OUT / "voice/selected-v01" / scene / f"turn-{index:02d}"
    selected.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target / "voice.wav", selected / "voice.wav")
    (selected / "provenance.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(f"{scene}/{index} {proof['voice']} {proof['seconds']:.2f}s", flush=True)


def recover(item):
    scene, index, turn = item
    take = f"turn-{index:02d}"
    base = OUT / "voice/v01" / scene / take
    if (base / "verified.json").exists():
        return generate(item)
    response = base / "response.json"
    if not response.is_file():
        raise ValueError(f"Missing a received response for {scene}/{index}")
    body = json.loads(response.read_text(encoding="utf-8"))
    if body.get("promptFeedback") or [c.get("finishReason") for c in body["candidates"]] != ["OTHER"]:
        raise ValueError(f"Inspect the response for {scene}/{index} before recovery")
    alternate = OUT / "voice/v02" / scene / take
    alternate.parent.mkdir(parents=True, exist_ok=True)
    reading = WORDS.sub(lambda match: READINGS[match[0]], turn["text"])
    proof = synthesize(alternate, reading, turn["speaker"], profile="standard")
    select(scene, index, alternate, proof)
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["short", "full", "both"])
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=3)
    parser.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    story = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    kinds = ("short", "full") if args.kind == "both" else (args.kind,)
    turns = [(scene["id"], index, turn) for kind in kinds for scene in story[kind]
             for index, turn in enumerate(scene["turns"])]
    action = recover if args.recover else generate
    # Verify one usable take before submitting the remaining dialogue.
    if not action(turns[0]):
        sys.exit(1)
    remaining = turns[1:]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(remaining), args.workers):
            batch = remaining[offset:offset + args.workers]
            if not all(list(pool.map(action, batch))):
                sys.exit(1)


if __name__ == "__main__":
    main()
