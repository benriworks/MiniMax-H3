"""Check the official images and prepare their video and article derivatives."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
RAW = OUT / "captures/original"
FIGURES = OUT / "captures/figures"
MOTION = OUT / "motion"
SOURCES = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))

MOTION_HASHES = {
    "female-happy": "3fd4f5b669f62adeaa3d19d5c4b2e5b1b5eb81f53817e91a5f989d9fb0333956",
    "female-understanding": "df4967a3ab73e2eb598e020fd8959ed7756fdb5e4a24a64424dabd1f42897126",
    "male-happy": "5ed5ba936023146b157d6182c0574fe672b8ae8fd72ed632eeda4916af3dd2f8",
    "male-thinking": "b284c50afa0eb95cb81d9786f47d6ae4bd9670a27da60b56d6107af8eb1f7799",
}

DETAILS = {
    "participant-detail": ("participant.png", (1915, 1010, 2930, 1751)),
    "plan-detail": ("meeting-plan.png", (92, 264, 3004, 1675)),
    "notes-detail": ("meeting-page.png", (730, 143, 1685, 864)),
}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def derive(source, crop, destination, article=False):
    with Image.open(source) as image:
        original = list(image.size)
        image = image.convert("RGB")
        if crop:
            if not 0 <= crop[0] < crop[2] <= image.width or not 0 <= crop[1] < crop[3] <= image.height:
                raise ValueError(f"Crop outside source: {source.name}")
            image = image.crop(tuple(crop))
        if article:
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            image.save(destination, quality=83, method=5)
        else:
            image.save(destination, compress_level=4)
        return original, list(image.size)


def prepare():
    FIGURES.mkdir(parents=True, exist_ok=True)
    records = []
    for item in SOURCES["images"]:
        source = RAW / item["original"]
        source_hash = digest(source)
        if item.get("sha256") and source_hash != item["sha256"]:
            raise ValueError(f"Official image hash changed: {source.name}")
        path = FIGURES / f"{item['id']}.webp"
        original, pixels = derive(source, item.get("crop"), path, article=True)
        if path.stat().st_size > 230_000:
            raise ValueError(f"Inspect compression for {path.name}")
        records.append(dict(**{key: value for key, value in item.items() if key != "sha256"},
            original_pixels=original, original_sha256=source_hash, original_bytes=source.stat().st_size,
            pixels=pixels, bytes=path.stat().st_size, sha256=digest(path),
            path=path.relative_to(OUT).as_posix(), checked_at=SOURCES["checked_at"],
            source_url=SOURCES["sources"][item["source"]]["url"]))
    for name, (source, crop) in DETAILS.items():
        derive(RAW / source, crop, FIGURES / f"{name}.png")
    save(FIGURES / "manifest.json", records)


def prepare_motion(source):
    MOTION.mkdir(parents=True, exist_ok=True)
    for name, expected in MOTION_HASHES.items():
        clip = source / f"{name}.mp4"
        if digest(clip) != expected:
            raise ValueError(f"Presenter provenance mismatch: {name}")
        dest = MOTION / name
        dest.mkdir(exist_ok=True)
        if not list(dest.glob("*.jpg")):
            subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n",
                            "-i", str(clip), "-an", "-vf", "fps=12,scale=480:-2",
                            str(dest / "%03d.jpg")], check=True)
        if len(list(dest.glob("*.jpg"))) != 62:
            raise ValueError(f"Presenter frame count mismatch: {name}")
    save(MOTION / "manifest.json", MOTION_HASHES)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion-source", type=Path, required=True)
    args = parser.parse_args()
    prepare()
    prepare_motion(args.motion_source)
    print("Six official sources prepared and four existing presenter motions verified.")


if __name__ == "__main__":
    main()
