"""Verify and package the spring and summer presenter variations."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from tools.studio.explainer_canvas import Canvas

SPEC = json.loads((HERE / "motion-spec.json").read_text(encoding="utf-8"))
CLIPS = {clip["id"]: clip for clip in SPEC["clips"]}
LOOKS = {look["key"]: look for look in SPEC["looks"]}
SEASONS = {"spring": ("春服", "#2B6556"), "summer": ("夏服", "#215F80")}
SAMPLES = (0.08, 0.75, 1.35, 1.95, 2.55, 3.25, 4.15, 4.95)


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def identity(path):
    return {"bytes": path.stat().st_size, "sha256": digest(path)}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *map(str, args)], check=True)


def streams(path):
    process = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                             check=True, capture_output=True)
    return json.loads(process.stdout)["streams"]


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def raw_take(root, clip, take_name):
    take = root / "clips" / take_name
    record = json.loads((take / "generation.json").read_text(encoding="utf-8"))
    video = take / "source.mp4"
    keyframe = root / "keyframes" / f"{clip['key']}.png"
    expected = digest(keyframe)
    if (record["state"] != "saved" or record["model"] != SPEC["provider"] or
            record["seconds"] != SPEC["durationSeconds"] or record["resolution"] != SPEC["resolution"] or
            record["input_sha256"] != expected or digest(video) != record["output_sha256"]):
        raise ValueError(f"Saved receipt, video or keyframe mismatch for {take_name}")
    last = record.get("last_image_sha256")
    if last is not None and last != expected:
        raise ValueError(f"The end keyframe differs from the neutral start for {take_name}")
    return video, record


def inspect(root, season, reviews):
    """
    Read actual frames at fixed times and decode the entire source; only visual
    review can decide whether the requested expression is visible and usable.
    """
    folder = root / "qc" / season
    folder.mkdir(parents=True, exist_ok=True)
    items = [clip for clip in SPEC["clips"] if clip["key"].startswith(season)]
    width, image_h, label_h = 200, 225, 28
    sheet = Image.new("RGB", (width*len(SAMPLES), (image_h+label_h)*len(items)), "#F5F2E9")
    labels = ImageDraw.Draw(sheet)
    for row, clip in enumerate(items):
        choice = reviews.get(clip["id"], {})
        taken = choice.get("take", clip["id"])
        source, _ = raw_take(root, clip, taken)
        ffmpeg("-xerror", "-i", source, "-f", "null", "-")
        for col, seconds in enumerate(SAMPLES):
            photo = folder / f"{taken}-{seconds:.2f}.jpg"
            if not photo.is_file():
                ffmpeg("-n", "-ss", seconds, "-i", source, "-frames:v", "1", "-q:v", "2", photo)
            with Image.open(photo) as image:
                cropped = image.crop((0, round(image.height*.15), image.width, round(image.height*.87)))
                tile = ImageOps.contain(cropped, (width-4, image_h-4))
                x, y = col*width, row*(image_h+label_h)
                sheet.paste(tile, (x+(width-tile.width)//2, y))
                labels.text((x+5, y+image_h), f"{clip['id'].split('-', 1)[1]}  {seconds:.2f}s", fill="#172D2B")
        print(f"{clip['id']}: decoded and {len(SAMPLES)} actual frames sampled", flush=True)
    sheet.save(folder / "contact.jpg", quality=91)


def export_clip(root, target, clip, review):
    name = clip["id"]
    source, record = raw_take(root, clip, review["take"])
    relative = Path("clips") / name.split("-", 1)[0] / f"{name}-{review['version']}.mp4"
    path = target / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg("-n", "-i", source, "-map", "0:v:0", "-c:v", "copy", "-movflags", "+faststart", path)
    ffmpeg("-xerror", "-i", path, "-f", "null", "-")
    info = streams(path)
    if len(info) != 1 or info[0]["codec_type"] != "video":
        raise ValueError(f"Expected a single silent video stream in {name}")
    stream = info[0]
    width, height = stream["width"], stream["height"]
    frames, seconds = int(stream["nb_frames"]), float(stream["duration"])
    if (stream["r_frame_rate"] != "24/1" or width < 720 or height <= width or
            not 4.9 <= seconds <= 5.3 or abs(seconds - frames/24) > .01):
        raise ValueError(f"Unexpected duration, aspect, or format for {name}")
    return dict(id=name, look_id=clip["key"], file=relative.as_posix(), motion=review["observed"],
                intended_use=clip["use"], visual_notes=review["notes"], usable_seconds=review["usable_seconds"],
                width=width, height=height, fps=24, frames=frames, seconds=seconds, has_audio=False,
                model=record["model"], mode="FL2VA" if record.get("last_image_sha256") else "I2VA",
                source_sha256=record["output_sha256"], source_bytes=record["bytes"],
                keyframe_sha256=record["input_sha256"], provider_seconds=record["provider_seconds"],
                usage=record["usage"], user_approved=False, **identity(path))


def card(path, season, left, right):
    name, accent = SEASONS[season]
    page = Image.new("RGB", (1440, 1000), "#F5F2E9")
    ImageDraw.Draw(page).rectangle((0, 0, 1440, 8), fill=accent)
    canvas = Canvas()
    canvas.text(page, f"{name}のキャラクター素材", (84, 24, 1356, 106), 57, "#172D2B", center=False)
    for x, role, clip in zip((84, 804), ("男性・聞き役", "女性・実務役"), (left, right), strict=True):
        canvas.text(page, role, (x, 890, x+552, 924), 29, accent, center=False)
        canvas.text(page, clip["motion"], (x, 935, x+552, 982), 35, "#172D2B", center=False)
    page.save(path)


def panel_filter(left, right):
    parts = []
    for i, data in enumerate((left, right)):
        width, height = data["width"], data["height"]
        crop_height = (width*4//3)//2*2
        y = round(height*.148/2)*2
        if y+crop_height > height:
            y = max(0, (height-crop_height)//2*2)
        parts.append(
            f"[{i}:v]crop={width}:{crop_height}:0:{y},scale=552:736,setsar=1,"
            f"tpad=stop_mode=clone:stop_duration=0.4[actor{i}]")
    return ";".join(parts + [
        "[2:v][actor0]overlay=84:138:shortest=1[half]",
        "[half][actor1]overlay=804:138:shortest=1,format=yuv420p[video]",
    ])


def make_reel(target, clips, folder, edition):
    lookup = {clip["id"]: clip for clip in clips}
    panels, counts = [], []
    for i, pair in enumerate(SPEC["pairs"]):
        left, right = (lookup[name] for name in pair)
        season = pair[0].split("-", 1)[0]
        title_path = folder / f"labels-{i}.png"
        path = folder / f"panel-{i}.mp4"
        card(title_path, season, left, right)
        count = max(left["frames"], right["frames"])
        ffmpeg("-n", "-i", target / left["file"], "-i", target / right["file"], "-loop", "1",
               "-framerate", "24", "-i", title_path, "-filter_complex_threads", "1", "-filter_complex",
               panel_filter(left, right), "-map", "[video]", "-frames:v", count, "-an",
               "-c:v", "libx264", "-crf", "17", "-preset", "fast", path)
        panels.append(path.name)
        counts.append(count)
    entries = folder / "panels.txt"
    entries.write_text("".join(f"file '{panel}'\n" for panel in panels), encoding="utf-8")
    reel = target / f"spring-summer-duo-preview-{edition}.mp4"
    ffmpeg("-n", "-f", "concat", "-safe", "1", "-i", entries, "-c:v", "copy", "-movflags", "+faststart", reel)
    ffmpeg("-xerror", "-i", reel, "-f", "null", "-")
    info = streams(reel)
    if len(info) != 1 or int(info[0]["nb_frames"]) != sum(counts):
        raise ValueError("Preview frame count mismatch")
    return dict(file=reel.name, frames=sum(counts), fps=24, seconds=sum(counts)/24, **identity(reel))


def create_package(root, reviews, edition):
    out = root / ("review-" + edition)
    if out.exists():
        raise FileExistsError(f"Preserve the existing edition in {out.name}")
    if set(reviews) != set(CLIPS) or any(item.get("status") != "visual_review_passed"
                                        for item in reviews.values()):
        raise ValueError("Record visual observations for all eight motions before export")
    with TemporaryDirectory(prefix="build-", dir=root) as room:
        scratch = Path(room)
        target = scratch / "package"
        (target / "keyframes").mkdir(parents=True)
        clips = [export_clip(root, target, clip, reviews[clip["id"]]) for clip in SPEC["clips"]]
        stills = []
        for key, outfit in LOOKS.items():
            source = root / "keyframes" / f"{key}.png"
            relative = Path("keyframes") / source.name
            path = target / relative
            path.write_bytes(source.read_bytes())
            with Image.open(path) as sample:
                stills.append(dict(id=key, file=relative.as_posix(), outfit=outfit["outfit"],
                                   pixels=list(sample.size), **identity(path)))
        reel = make_reel(target, clips, scratch, edition)
        manifest = dict(schema_version=1, edition=edition, keyframes=stills, clips=clips, preview=reel)
        save_json(target / "motion-manifest.json", manifest)
        rows = "\n".join(f"| {clip['file']} | {clip['motion']} | {clip['intended_use']} |" for clip in clips)
        (target / "README.md").write_text(
            "# 男女キャラクターの春服と夏服\n\n"
            "衣装ごとの基準画PNG4枚と、編集に使える無音の縦MP4が8本入っています。"
            "映像には音声を別トラックで重ねてください。確認用MP4では男性が左、女性が右です。\n\n"
            "| ファイル | 動き | 使いどころ |\n| --- | --- | --- |\n" + rows + "\n\n"
            "編集に使う区間の目安、素材版とハッシュは motion-manifest.json を参照してください。\n",
            encoding="utf-8")
        members = sorted(path for path in target.rglob("*") if path.is_file())
        hashes = {path.relative_to(target).as_posix(): digest(path) for path in members}
        archive = target / f"spring-summer-duo-assets-{edition}.zip"
        with ZipFile(archive, "x", compression=ZIP_DEFLATED, compresslevel=5) as dest:
            for path in members:
                dest.write(path, path.relative_to(target).as_posix())
            dest.writestr("SHA256SUMS.json", json.dumps(hashes, indent=2)+"\n")
        with ZipFile(archive) as saved:
            checksums = json.loads(saved.read("SHA256SUMS.json"))
            if saved.testzip() is not None or set(saved.namelist()) != set(hashes) | {"SHA256SUMS.json"}:
                raise ValueError("ZIP member verification failed")
            for path in members:
                name = path.relative_to(target).as_posix()
                if checksums[name] != hashes[name] or saved.read(name) != path.read_bytes():
                    raise ValueError(f"ZIP member changed: {name}")
        save_json(target / "qc.json", dict(zip=dict(file=archive.name, members=len(members)+1, **identity(archive)),
                   preview=reel, no_audio=True, complete_decode=True, visually_sampled=True))
        target.rename(out)
    print(out)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("inspect", "package"))
    parser.add_argument("source_folder", type=Path)
    parser.add_argument("--season", choices=tuple(SEASONS))
    parser.add_argument("--edition", default="v01", choices=("v01", "v02", "v03"))
    args = parser.parse_args()
    root = args.source_folder.resolve(strict=True)
    review = HERE / "motion-review.json"
    reviewed = json.loads(review.read_text(encoding="utf-8")) if review.is_file() else {}
    if args.operation == "inspect":
        for season in ((args.season,) if args.season else SEASONS):
            inspect(root, season, reviewed)
    else:
        create_package(root, reviewed, args.edition)


if __name__ == "__main__":
    main()
