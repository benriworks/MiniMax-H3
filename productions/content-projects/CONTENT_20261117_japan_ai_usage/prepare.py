"""Check pinned public data and derive the figures and presenter frames."""
import argparse
import csv
from hashlib import file_digest
import json
from pathlib import Path
import subprocess
import sys

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
FIGURES = OUT / "captures/figures"
ORIGINAL = OUT / "captures/original"
MOTION = OUT / "motion"
SOURCES = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
MOTION_HASHES = {
    "female-happy": "3fd4f5b669f62adeaa3d19d5c4b2e5b1b5eb81f53817e91a5f989d9fb0333956",
    "female-understanding": "df4967a3ab73e2eb598e020fd8959ed7756fdb5e4a24a64424dabd1f42897126",
    "male-happy": "5ed5ba936023146b157d6182c0574fe672b8ae8fd72ed632eeda4916af3dd2f8",
    "male-thinking": "b284c50afa0eb95cb81d9786f47d6ae4bd9670a27da60b56d6107af8eb1f7799",
}
sys.path.insert(0, str(ROOT))


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def check_dataset(path):
    facts = SOURCES["data"]
    if digest(path) != facts["sha256"]:
        raise ValueError("Claude dataset hash does not match the pinned edition")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = {(row["geo_id"], row["metric_id"]): float(row["value"])
                 for row in csv.DictReader(stream)
                 if (row["date_start"], row["date_end"]) == (facts["date_start"], facts["date_end_exclusive"])
                 and row["category_name"] == "overall" and row["hierarchy_level"] == "0"
                 and row["geo_level"] in {"country", "global"}
                 and row["metric_id"] in {"usage_per_capita_index", "use_case_work_pct", "usage_pct"}}
    indices = {code: value for (code, metric), value in rows.items()
               if metric == "usage_per_capita_index" and code != "GLOBAL"}
    rank = 1 + sum(value > indices["JPN"] for value in indices.values())
    if (rank, len(indices)) != (facts["rank"], facts["countries"]):
        raise ValueError("Country rank disagrees with the storyboard")
    for code, _, value in facts["indices"]:
        if indices[code] != value:
            raise ValueError(f"Usage index mismatch: {code}")
    work = {code: rows[code, "use_case_work_pct"] for code in ("JPN", "GLOBAL")}
    if work != facts["work_pct"] or rows["JPN", "usage_pct"] != facts["japan_usage_pct"]:
        raise ValueError("Use proportions disagree with the storyboard")
    save(OUT / "dataset-check.json", dict(dataset_sha256=facts["sha256"], rank=rank,
         countries=len(indices), indices=facts["indices"], work_pct=work,
         start=facts["date_start"], end_exclusive=facts["date_end_exclusive"]))
    print(f"May official CSV: Japan rank {rank} / {len(indices)}; use index {indices['JPN']}")


def derive_figures():
    FIGURES.mkdir(parents=True, exist_ok=True)
    records = []
    for item in SOURCES["images"]:
        path = ORIGINAL / item["original"]
        target = FIGURES / (item["id"] + ".webp")
        with Image.open(path) as opened:
            original_size = list(opened.size)
            image = opened.convert("RGB")
            if item.get("crop"):
                l, t, r, b = item["crop"]
                if not (0 <= l < r <= image.width and 0 <= t < b <= image.height):
                    raise ValueError(f"Invalid crop for {path.name}")
                image = image.crop(item["crop"])
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image.save(target, quality=83, method=5)
        records.append(dict(item, original_pixels=original_size, original_sha256=digest(path),
                            original_bytes=path.stat().st_size, pixels=list(image.size),
                            bytes=target.stat().st_size, sha256=digest(target),
                            path=target.relative_to(OUT).as_posix(), checked_at=SOURCES["checked_at"],
                            source_url=SOURCES["sources"][item["source"]]["url"]))
    save(FIGURES / "manifest.json", records)


def prepare_motion(source):
    MOTION.mkdir(exist_ok=True)
    records = {}
    for key, expected in MOTION_HASHES.items():
        original = source / f"{key}.mp4"
        if digest(original) != expected:
            raise ValueError(f"Presenter source does not match the earlier production: {key}")
        frames = MOTION / key
        frames.mkdir(exist_ok=True)
        if not list(frames.glob("*.jpg")):
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(original),
                            "-an", "-vf", "fps=12,scale=480:-2", str(frames / "%03d.jpg")],
                           check=True)
        count = len(list(frames.glob("*.jpg")))
        if count != 62:
            raise ValueError(f"Unexpected presenter frame count: {key} / {count}")
        records[key] = dict(sha256=expected, source_bytes=original.stat().st_size, frames=count)
    save(MOTION / "manifest.json", records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion-source", required=True, type=Path)
    args = parser.parse_args()
    check_dataset(OUT / "_private/aei-claude-ai.csv")
    derive_figures()
    prepare_motion(args.motion_source)


if __name__ == "__main__":
    main()
