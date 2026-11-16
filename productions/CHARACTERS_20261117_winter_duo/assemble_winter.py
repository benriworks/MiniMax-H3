"""Export the winter presenter clips, their keyframes, and a two-part review reel."""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.studio.explainer_canvas import Canvas, box

SHOTS = {
    "female-guide": ("女性・実務役", "片手を開いて案内", "説明や図を紹介する場面"),
    "male-question": ("男性・聞き役", "首を傾け、片手で質問", "疑問を挟む場面"),
    "female-concern": ("女性・実務役", "画面を見て考え、顔を上げる", "数字や原文を照合する場面"),
    "male-nod": ("男性・聞き役", "小さくうなずいて微笑む", "説明を聞いて納得する場面"),
}


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *map(str, args)], check=True)


def digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
                            capture_output=True, check=True)
    return json.loads(result.stdout)["streams"]


def summary(path):
    return dict(bytes=path.stat().st_size, sha256=digest(path))


def export_motion(root, name, target, edition):
    revised = edition == "v02" and name == "male-question"
    take = root / "clips" / (name + "-compact" if revised else name)
    target_file = target / "clips" / f"{name}-{'v02' if revised else 'v01'}.mp4"
    raw = take / "source.mp4"
    receipt = json.loads((take / "generation.json").read_text(encoding="utf-8"))
    if receipt["state"] != "saved" or digest(raw) != receipt["output_sha256"]:
        raise ValueError(f"Source receipt mismatch: {name}")
    ffmpeg("-n", "-i", raw, "-map", "0:v:0", "-c:v", "copy", "-movflags", "+faststart", target_file)
    ffmpeg("-xerror", "-i", target_file, "-f", "null", "-")
    streams = probe(target_file)
    if len(streams) != 1 or streams[0]["codec_type"] != "video":
        raise ValueError(f"Expected reusable video only: {name}")
    stream = streams[0]
    if (stream["width"], stream["height"], stream["r_frame_rate"], stream["nb_frames"]) != (
            768, 1344, "24/1", "124"):
        raise ValueError(f"Unexpected source framing: {name}")
    return dict(id=name, file=f"clips/{target_file.name}", role=SHOTS[name][0],
                motion=SHOTS[name][1], intended_use=SHOTS[name][2],
                resolution=[768, 1344], fps=24, frames=124, seconds=float(stream["duration"]),
                keyframe_sha256=receipt["input_sha256"], source_sha256=receipt["output_sha256"],
                source_bytes=receipt["bytes"], model=receipt["model"],
                provider_seconds=receipt["provider_seconds"], usage=receipt["usage"],
                has_audio=False, user_approved=False, **summary(target_file))


def label_card(target, left, right):
    im = Image.new("RGB", (1440, 1000), "#F5F2E9")
    canvas = Canvas()
    x0, x1 = 84, 804
    ImageDraw.Draw(im).rectangle((0, 0, 1440, 7), fill="#17685B")
    canvas.text(im, "男女キャラクター　冬服のモーション", (84, 29, 1356, 103),
                55, "#172C2C", center=False)
    for x, name in zip((x0, x1), (left, right), strict=True):
        role, title, _ = SHOTS[name]
        box(im, (x-2, 136, x+554, 876), "#FFFFFF", radius=9, outline="#DBD4C7", width=2)
        canvas.text(im, role, (x, 890, x+552, 923), 27, "#17685B", center=False)
        canvas.text(im, title, (x, 933, x+552, 980), 35, "#172C2C", center=False)
    im.save(target)


def make_reel(target, clips, edition):
    reel = target / f"winter-duo-preview-{edition}.mp4"
    intermediates = target / "_preview"
    intermediates.mkdir()
    panels = []
    lookup = {clip["id"]: clip["file"] for clip in clips}
    for i, pair in enumerate((("male-question", "female-guide"), ("male-nod", "female-concern"))):
        background = intermediates / f"caption-{i}.png"
        panel = intermediates / f"panel-{i}.mp4"
        label_card(background, *pair)
        inputs = [target / lookup[clip] for clip in pair]
        ffmpeg("-n", "-i", inputs[0], "-i", inputs[1], "-loop", "1", "-framerate", "24",
               "-i", background, "-filter_complex_threads", "1", "-filter_complex",
               "[0:v]crop=768:1024:0:200,scale=552:736,setsar=1[left];"
               "[1:v]crop=768:1024:0:200,scale=552:736,setsar=1[right];"
               "[2:v][left]overlay=84:138:shortest=1[half];"
               "[half][right]overlay=804:138:shortest=1,format=yuv420p[video]",
               "-map", "[video]", "-frames:v", "124", "-an", "-c:v", "libx264", "-crf", "17",
               "-preset", "fast", panel)
        panels.append(panel.name)
    concat = intermediates / "panels.txt"
    concat.write_text("".join(f"file '{name}'\n" for name in panels), encoding="utf-8")
    ffmpeg("-n", "-f", "concat", "-safe", "1", "-i", concat, "-c:v", "copy", "-movflags", "+faststart", reel)
    ffmpeg("-xerror", "-i", reel, "-f", "null", "-")
    metadata = probe(reel)
    if len(metadata) != 1 or metadata[0]["nb_frames"] != "248":
        raise ValueError("Review reel frame count mismatch")
    return reel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_folder", type=Path)
    parser.add_argument("--edition", choices=("v01", "v02"), default="v02")
    args = parser.parse_args()
    root = args.source_folder.resolve()
    target = root / ("review" if args.edition == "v01" else "review-v02")
    target.mkdir(exist_ok=False)
    (target / "clips").mkdir()
    (target / "keyframes").mkdir()
    clips = [export_motion(root, name, target, args.edition) for name in SHOTS]
    keyframes = []
    for role in ("female", "male"):
        path = root / "keyframes" / f"{role}-winter.png"
        destination = target / "keyframes" / path.name
        destination.write_bytes(path.read_bytes())
        frame = summary(destination)
        if {clip["keyframe_sha256"] for clip in clips if clip["id"].startswith(role)} != {frame["sha256"]}:
            raise ValueError(f"Motion and winter keyframe mismatch: {role}")
        with Image.open(destination) as opened:
            keyframes.append(dict(file=f"keyframes/{path.name}", pixels=list(opened.size), **frame))
    reel = make_reel(target, clips, args.edition)
    receipt = dict(schema_version=1, edition=args.edition, keyframes=keyframes, clips=clips,
                   reel=dict(file=reel.name, frames=248, fps=24, **summary(reel)))
    manifest = target / "motion-manifest.json"
    manifest.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = target / "README.md"
    readme.write_text(
        f"# 男女キャラクターの冬服 {args.edition}\n\n"
        "基準画PNG 2点と、映像編集に使える無音のMP4 4本が入っています。\n"
        "解説に使うときは必要な動きの区間を選び、ナレーションは別トラックへ置きます。\n"
        "ショートの縦フレームは素材を全幅で、横動画のPIPは手が外に出ない範囲で切り出せます。\n"
        "女性は片手案内・確認の視線、男性は質問の手振り・相づち。"
        "顔と衣装の対応、時刻、ハッシュは motion-manifest.json で確認できます。\n",
        encoding="utf-8")
    members = [readme, manifest, reel, *sorted((target / "clips").glob("*.mp4")),
               *sorted((target / "keyframes").glob("*.png"))]
    archive = target / f"winter-duo-assets-{args.edition}.zip"
    with ZipFile(archive, "x", compression=ZIP_DEFLATED, compresslevel=5) as dest:
        for path in members:
            dest.write(path, path.relative_to(target).as_posix())
    with ZipFile(archive) as saved:
        assert saved.testzip() is None
        for path in members:
            assert saved.read(path.relative_to(target).as_posix()) == path.read_bytes()
    print(json.dumps(dict(zip=summary(archive), members=len(members), **receipt), ensure_ascii=False))


if __name__ == "__main__":
    main()
