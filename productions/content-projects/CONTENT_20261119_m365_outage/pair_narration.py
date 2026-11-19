"""Record the six vertical turns and the additional full-length sign-off."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    media = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(media.parents[2]))
    from tools.studio.dialogue_narration import synthesize

    def record(line):
        target = media / "voice" / line.get("voice_take","pair-v03") / line["id"] / "turn-00"
        proof = synthesize(target, line["reading"], line["speaker"], profile="conversational_v3")
        print(line["id"], proof["voice"], round(proof["seconds"], 2), flush=True)

    lines = json.loads((HERE / "dialogue-pair.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(record, lines))
