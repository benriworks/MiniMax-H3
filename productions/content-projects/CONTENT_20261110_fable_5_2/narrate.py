"""Generate frozen Aoede and Charon dialogue using the Studio narration contract."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
OUT = ROOT / "outputs/content-projects" / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.dialogue_narration import synthesize

PRONUNCIATION = {
    "Claude Fable 5.2": "クロード・フェイブル、ファイブ・ポイント・ツー",
    "Fable 5.2": "フェイブル、ファイブ・ポイント・ツー",
    "Mythos 5.2": "ミュトス、ファイブ・ポイント・ツー",
    "Opus 5.5": "オーパス、ファイブ・ポイント・ファイブ",
    "Gemini 4 Carbon": "ジェミニ・フォー・カーボン",
    "GPT-6.1 Sol": "ジーピーティー、シックス・ポイント・ワン、ソル",
    "Sol 6.2": "ソル、シックス・ポイント・ツー",
    "Elo": "イーロ",
    "Astra": "アストラ",
    "FrontierCode 2.0": "フロンティアコード、ツー・ポイント・ゼロ",
    "WANDR": "ワンダー",
    "BenchCAD 2.1": "ベンチキャド、ツー・ポイント・ワン",
    "Humanity’s Last Exam": "ヒューマニティーズ・ラスト・イグザム",
    "Chartography": "チャートグラフィー",
    "AutomationBench": "オートメーションベンチ",
    "OSWorld 2.1": "オーエスワールド、ツー・ポイント・ワン",
    "AA-Briefcase": "エーエー・ブリーフケース",
    "RoboDojo": "ロボ道場",
    "Claude Code": "クロードコード",
    "Claude": "クロード",
    "Anthropic": "アンソロピック",
    "OpenAI": "オープンエーアイ",
    "Lean": "リーン",
    "Xhigh": "エックスハイ",
    "Medium": "ミディアム",
    "High": "ハイ",
    "Low": "ロー",
    "Max": "マックス",
    "API": "エーピーアイ",
}
MODEL_NAMES = re.compile("|".join(map(re.escape, sorted(PRONUNCIATION, key=len, reverse=True))))
PERCENT = re.compile(r"(\d+)(?:\.(\d+))?%")
DIGITS = "ゼロ イチ ニ サン ヨン ゴ ロク ナナ ハチ キュウ".split()


def reading(text):
    spoken = MODEL_NAMES.sub(lambda hit: PRONUNCIATION[hit[0]], text)
    return PERCENT.sub(
        lambda hit: hit[1] + ("点" + " ".join(DIGITS[int(d)] for d in hit[2]) if hit[2] else "") + "パーセント",
        spoken)


def voice_dir(scene, index):
    return OUT / "voice/v01" / scene["id"] / f"turn-{index:02d}"


def generate(task):
    scene, index, turn = task
    target = voice_dir(scene, index)
    proof = synthesize(target, turn.get("reading", reading(turn["text"])), turn["speaker"],
                       profile="conversational_v3")
    print(f"{scene['id']}/{index} {proof['voice']} {proof['seconds']:.2f}s", flush=True)
    return proof


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=["short", "full"])
    parser.add_argument("--scene", action="append")
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=1)
    args = parser.parse_args()
    data = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8-sig"))
    tasks = [(scene, idx, turn) for scene in data[args.kind]
             if not args.scene or scene["id"] in args.scene for idx, turn in enumerate(scene["turns"])]
    if not tasks or not (HERE / "PROPOSAL_JA.md").is_file():
        raise ValueError("Production brief and selected dialogue are required")
    for scene, index, _ in tasks:
        voice_dir(scene, index).parent.mkdir(parents=True, exist_ok=True)
    # Submit a bounded batch at a time so a provider failure stops subsequent requests.
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for offset in range(0, len(tasks), args.workers):
            list(pool.map(generate, tasks[offset:offset+args.workers]))


if __name__ == "__main__":
    main()
