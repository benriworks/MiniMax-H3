"""Prepare documented captures, independently verify the export, and reuse approved-series motion."""
from pathlib import Path
from hashlib import sha256
from zipfile import ZipFile
import argparse
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name
RAW = OUT / "captures/original"
FIGURES = OUT / "captures/figures"
MOTION = OUT / "motion"
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

CROPS = {
    "board": ("whiteboard-finished", (1090, 470, 2030, 845), "claude-ui", "Whiteboardsの試食会企画"),
    "sheet-before": ("sheets-before", (0, 0, 340, 315), "claude-ui", "試食セット40個の予算表"),
    "sheet-after": ("sheets-after", (0, 0, 340, 315), "claude-ui", "試食セット45個とSUM式"),
    "excel-menu": ("sheets-export-menu", (2108, 36, 2553, 368), "claude-ui", "Excel形式のエクスポート"),
    "directory": ("connector-directory", (780, 73, 1772, 915), "claude-ui", "おすすめのインタラクティブコネクタ"),
    "vercel-permission": ("vercel-permission", (876, 966, 1700, 1149), "claude-ui", "Vercel公開文書検索の一回限りの許可"),
    "vercel-result": ("vercel-search-result", (887, 214, 1666, 518), "claude-ui", "公開ドキュメント検索の結果"),
    "official-artifacts": ("official-artifacts", (904, 202, 1627, 659), "official-artifacts", "11月10日のArtifacts発表"),
    "official-apps": ("official-apps", (904, 202, 1627, 659), "official-apps", "11月10日のインタラクティブコネクタ発表"),
    "confluence": ("official-apps-demo-panel", (923, 501, 1609, 754), "official-apps", "公式デモ約22秒。チャットの横のConfluence文書"),
}

HASHES = {
    "female-happy": "3fd4f5b669f62adeaa3d19d5c4b2e5b1b5eb81f53817e91a5f989d9fb0333956",
    "female-understanding": "df4967a3ab73e2eb598e020fd8959ed7756fdb5e4a24a64424dabd1f42897126",
    "male-happy": "5ed5ba936023146b157d6182c0574fe672b8ae8fd72ed632eeda4916af3dd2f8",
    "male-thinking": "b284c50afa0eb95cb81d9786f47d6ae4bd9670a27da60b56d6107af8eb1f7799",
}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def prepare_figures():
    FIGURES.mkdir(parents=True, exist_ok=True)
    records = []
    for name, (original, crop, source, description) in CROPS.items():
        raw = RAW / f"{original}.jpg"
        destination = FIGURES / f"{name}.png"
        with Image.open(raw) as im:
            assert 0 <= crop[0] < crop[2] <= im.width and 0 <= crop[1] < crop[3] <= im.height
            im.crop(crop).save(destination, optimize=True)
            original_size = im.size
        records.append(dict(id=name, source_id=source, description=description,
                            raw=raw.relative_to(OUT).as_posix(), raw_pixels=original_size,
                            crop=list(crop), path=destination.relative_to(OUT).as_posix(),
                            pixels=[crop[2] - crop[0], crop[3] - crop[1]],
                            raw_sha256=sha(raw), sha256=sha(destination), checked_at="2026-11-12"))
    save(FIGURES / "manifest.json", records)


def verify_workbook():
    path = RAW / "tasting-budget.xlsx"
    with ZipFile(path) as archive:
        if archive.testzip() or any("vbaProject" in name or "externalLink" in name for name in archive.namelist()):
            raise ValueError("Unexpected export content")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        title = workbook.find("s:sheets/s:sheet", NS).get("name")
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    cells = {cell.get("r"): cell for cell in sheet.findall(".//s:c", NS)}

    expected = {"B2": 1, "B3": 45, "B4": 100, "C2": 30000, "C3": 650, "C4": 80, "D6": 70000}
    assert title == "予算" and not any(cell.get("t") == "e" for cell in cells.values())
    assert all(int(cells[address].findtext("s:v", namespaces=NS)) == value
               for address, value in expected.items())
    lines = {f"D{row}": (f"B{row}*C{row}", expected[f"B{row}"] * expected[f"C{row}"])
             for row in (2, 3, 4)}
    total = sum(amount for _, amount in lines.values())
    lines.update({"D5": ("SUM(D2:D4)", total), "D7": ("D6-D5", expected["D6"] - total)})
    assert total == 67250 and lines["D7"][1] == 2750
    for address, (formula, cached) in lines.items():
        assert cells[address].findtext("s:f", namespaces=NS) == formula
        assert int(cells[address].findtext("s:v", namespaces=NS)) == cached
    save(FIGURES / "xlsx-verification.json", dict(sheet=title, inputs=expected,
         formulas={address: dict(formula="=" + formula, cached=cached)
                   for address, (formula, cached) in lines.items()},
         before=dict(quantity=40, total=64000, remainder=6000),
         method="Office Open XML readback and independent integer arithmetic",
         excel_desktop_recalculation="未検証", bytes=path.stat().st_size, sha256=sha(path)))


def prepare_motion(source):
    MOTION.mkdir(parents=True, exist_ok=True)
    for name, digest in HASHES.items():
        clip = source / f"{name}.mp4"
        if sha(clip) != digest:
            raise ValueError(f"Unexpected presenter clip for {name}")
        target = MOTION / name
        target.mkdir(exist_ok=True)
        if not list(target.glob("*.jpg")):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                            "-i", str(clip), "-an", "-vf", "fps=12,scale=480:-2",
                            str(target / "%03d.jpg")], check=True)
        if len(list(target.glob("*.jpg"))) != 62:
            raise ValueError(f"Expected 62 motion frames for {name}")
    save(MOTION / "manifest.json", HASHES)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--motion-source", type=Path, required=True)
    args = parser.parse_args()
    prepare_figures()
    verify_workbook()
    prepare_motion(args.motion_source)
    print("Prepared 10 crops, verified 5 exported formulas and 4 presenter clips.")


if __name__ == "__main__":
    main()
