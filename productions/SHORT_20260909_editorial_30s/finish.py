"""Finish a scoped editorial production with existing Studio local workers.

No Studio database rows, fake stage attempts, paid API calls, or publication.
The local run namespace below is a filesystem work ID, not a saved Studio Run.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.studio.assembly import assemble_local_video, assembly_cache_key, resolve_tool_identity
from tools.studio.narration import generate_local_narration
from tools.studio.security import workspace_path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest().upper()


def checked(record):
    path = workspace_path(ROOT, record["path"], must_exist=True)
    if path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
        raise ValueError("Source identity changed")
    return path


def save(path: Path, data):
    content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if path.exists():
        if path.read_bytes() != content:
            raise ValueError("Refusing to overwrite earlier evidence")
        return
    with path.open("xb") as handle:
        handle.write(content)


def validate_story(story):
    if story["theme"] != "claude_editorial_v1" or story["duration_ms"] != 30000:
        raise ValueError("Only the approved 30s theme is supported")
    if story["voice"] != "Microsoft Sayaka" or story["rate"] != 0:
        raise ValueError("Keep the previous local voice settings")
    if len(story["segments"]) != 6 or len(story["headlines"]) != 3:
        raise ValueError("Three chapters and six brief captions required")
    starts = [segment["start_ms"] for segment in story["segments"]]
    if starts != [500, 4700, 10500, 14700, 20500, 24700]:
        raise ValueError("Unexpected speech schedule")
    for segment in story["segments"]:
        text = segment["text"]
        if not isinstance(text, str) or not text.strip() or "\n" in text:
            raise ValueError("Caption must be one short phrase")
        units = sum(1 if 0x20 <= ord(char) <= 0x7e else 2 for char in text)
        if units > 38:
            raise ValueError("Caption exceeds shared Shorts readability budget")
    return tuple(starts)


def validate_timings(story, document):
    expected = validate_story(story)
    if len(document["segments"]) != 6:
        raise ValueError("Missing speech segment")
    for i, row in enumerate(document["segments"]):
        deadline = expected[i + 1] if i < 5 else 29000
        # Do not let a phrase leak across a chapter boundary.
        deadline = min(deadline, (i // 2 + 1) * 10000)
        if (row["text"] != story["segments"][i]["text"] or row["start_ms"] != expected[i]
                or not row["start_ms"] < row["end_ms"] <= deadline):
            raise ValueError("Speech exceeds its editorial slot; do not accelerate or truncate it")


def main(manifest: Path):
    manifest = workspace_path(ROOT, manifest, must_exist=True)
    output = manifest.parent
    report = read(manifest)
    story = report["story"]
    starts = validate_story(story)
    sources = [*report["sources"], *report["panels"], report["timeline"]]
    for source in sources:
        checked(source)
    # Unique filesystem namespace and content-bound assembly; no database claim.
    namespace = hashlib.sha256(str(output).encode()).hexdigest()[:32]
    run_id = "run_" + namespace
    production_id = "production_" + namespace
    narration_result_path = output / "narration-result.json"
    if narration_result_path.exists():
        narration = read(narration_result_path)
        for item in narration["artifacts"]:
            checked({**item, "path": item["rel_path"]})
    else:
        narration = generate_local_narration(ROOT, production_id=production_id, run_id=run_id,
            payload={"voice": story["voice"], "rate": story["rate"], "pronunciations": [],
                "segments": [{"text": s["text"]} for s in story["segments"]]}, segment_start_ms=starts)
        save(narration_result_path, narration)
    narr_files = {item["name"]: ROOT / item["rel_path"] for item in narration["artifacts"]}
    timings = read(narr_files["timings.json"])
    validate_timings(story, timings)
    print(json.dumps({"event": "narration_verified", "timings": timings["segments"]}, ensure_ascii=False), flush=True)
    source = checked(report["timeline"])
    identity = resolve_tool_identity()
    key = assembly_cache_key(digest(source), digest(narr_files["narration.wav"]), digest(narr_files["captions.srt"]), True,
        caption_style_preset="shorts_ja_large_v1", audio_mix_preset="narration_only_v1", tool_identity=identity)
    result_path = output / "assembly-result.json"
    if result_path.exists():
        assembly = read(result_path)
        if assembly["cache_key"] != key:
            raise ValueError("Assembly inputs changed")
        for item in assembly["artifacts"]:
            checked({**item, "path": item["rel_path"]})
    else:
        assembly = assemble_local_video(ROOT, production_id=production_id, run_id=run_id, cache_key=key,
            source_video=source, narration_wav=narr_files["narration.wav"], captions_srt=narr_files["captions.srt"],
            include_captioned=True, caption_style_preset="shorts_ja_large_v1", audio_mix_preset="narration_only_v1")
        save(result_path, assembly)
    masters = {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    for item in assembly["artifacts"]:
        if item["name"] not in {"master-clean.mp4", "master-captioned.mp4"}:
            continue
        path = ROOT / item["rel_path"]
        p = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], creationflags=flags))
        v = next(s for s in p["streams"] if s["codec_type"] == "video")
        a = next(s for s in p["streams"] if s["codec_type"] == "audio")
        if (len(p["streams"]) != 2 or v["codec_name"] != "h264" or v["width"] != 1080 or v["height"] != 1920
                or v["avg_frame_rate"] != "24/1" or int(v["nb_frames"]) != 720 or float(p["format"]["duration"]) != 30
                or a["codec_name"] != "aac" or int(a["sample_rate"]) != 48000):
            raise ValueError("Final media format mismatch")
        subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-f", "null", "-"], check=True, creationflags=flags)
        masters[item["name"]] = {**item, "probe": p, "full_decode_verified": True}
    if len(masters) != 2:
        raise ValueError("Both master variants are required")
    captioned = ROOT / masters["master-captioned.mp4"]["rel_path"]
    for second in [2, 6, 11.5, 16, 21.5, 26, 29.5]:
        image = output / f"final-{second:g}s.png"
        if not image.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-n", "-ss", str(second), "-i", str(captioned), "-frames:v", "1", str(image)], check=True, creationflags=flags)
    for source_record in sources:
        checked(source_record)
    publication = output / "publication.txt"
    if not publication.exists():
        with publication.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(story["title"] + "\n\n" + story["description"] + "\n\n字幕あり: " + str(captioned.relative_to(ROOT))
                + "\n字幕なし（見出し・図解は残る）: " + masters["master-clean.mp4"]["rel_path"]
                + "\n\n音声品質の改善・公開受入は未実施。通常Studio画面の保存Runではなく共通workerを利用した制作スクリプトによる出力。\n")
    verification = {"schema_version": 1, "studio_database_run": False, "workflow": report["workflow"], "masters": masters,
        "timings": timings, "tools": identity, "narration_settings": {"voice": story["voice"], "rate": story["rate"]},
        "paid_api_calls": 0, "new_capture": False, "new_image_generation": False, "public_quality_verified": False,
        "format_and_full_decode_verified": True, "caption_timing_verified": True, "audio_quality_improved": False}
    save(output / "verification.json", verification)
    package = output / "editorial-30s-review-package.zip"
    package_items = {"master-captioned.mp4": captioned, "master-clean.mp4": ROOT / masters["master-clean.mp4"]["rel_path"],
        "publication.txt": publication, "story.json": Path(__file__).with_name("story.json"), "render.json": manifest,
        "verification.json": output / "verification.json", **narr_files}
    if not package.exists():
        with zipfile.ZipFile(package, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, path in package_items.items():
                archive.write(path, name)
    with zipfile.ZipFile(package) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(package_items):
            raise ValueError("Review package failed verification")
        for name, path in package_items.items():
            if hashlib.sha256(archive.read(name)).hexdigest().upper() != digest(path):
                raise ValueError("Review package content changed")
    print(json.dumps({"event": "production_complete", "captioned": str(captioned), "review_package": str(package), "verification": str(output / "verification.json")}), flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
