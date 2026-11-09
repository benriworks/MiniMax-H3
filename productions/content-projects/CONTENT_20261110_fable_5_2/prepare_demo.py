"""Render a clearly labeled excerpt of the actual single Claude Code run."""
import json
from pathlib import Path
import re
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "outputs/content-projects" / Path(__file__).parent.name / "demo"
sys.path.insert(0, str(ROOT))
from tools.studio.editorial_captions import phrase_lines
from tools.studio.explainer_canvas import Canvas, box

MODEL = "claude-fable-5-2"
EXPECTED = ("2週目", "20件", "17件", "4件", "目盛り")


def main():
    raw = json.loads((OUT/"first.raw.json").read_text(encoding="utf-8-sig"))
    if raw["is_error"] or list(raw["modelUsage"]) != [MODEL] or raw["modelUsage"][MODEL]["canonicalModel"] != MODEL:
        raise ValueError("The requested model could not be verified for this run")
    paragraphs = [re.sub(r"\*\*", "", p) for p in raw["result"].split("\n\n")[:3]]
    if len(paragraphs) != 3 or any(word not in " ".join(paragraphs) for word in EXPECTED):
        raise ValueError("The original answer does not match the chart reading")
    record = dict(model=MODEL, actual_run=True, input=(OUT/"prompt.txt").read_text(encoding="utf-8"),
                  output_excerpt=paragraphs, expected=dict(week=2, prior=20, new=17, week4_gap=4),
                  runs=1, clip_label="実行ログからの抜粋。Markdownの強調記号のみ除去。")
    (OUT/"record.json").write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    im = Image.new("RGB", (1510, 855), "#102E31")
    canvas = Canvas()
    canvas.text(im, "Claude Code   ／   実行ログの抜粋", (69, 55, 1436, 139), 51, "#F6CE9C", center=False)
    canvas.text(im, MODEL, (69, 142, 1436, 218), 42, "#B3D7C9", center=False)
    box(im, (64, 238, 1446, 801), "#FFFCF5", 26)
    y = 289
    for index, paragraph in enumerate(paragraphs):
        size = 45 if index < 2 else 36
        lines = phrase_lines(paragraph, 1245, size)
        canvas.text(im, "\n".join(lines), (123, y, 1393, y+145), size, "#17363A", center=False)
        y += 164 if index < 2 else 90
    im.save(OUT/"output-excerpt.png")


if __name__ == "__main__":
    main()
