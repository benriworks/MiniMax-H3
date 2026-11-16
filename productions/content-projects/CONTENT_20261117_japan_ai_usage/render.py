"""Lay out dialogue and render two frame-accurate, verified MP4s."""
import argparse
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess

from PIL import Image, ImageOps

from prepare import HERE, OUT, ROOT, digest, save
from graphics import Editor, PAPER, PROTECT
from mix_audio import loudness, mix
from tools.studio.editorial_captions import timed_captions
from tools.studio.longform_audio import plan_dialogue, read_voice

FPS = 24


def plan(kind, editor):
    story = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    voice = json.loads((OUT / "voice/selected.json").read_text(encoding="utf-8"))
    voice_root = OUT / "voice" / voice["method"]
    scenes = story[kind]
    for scene in scenes:
        duration = sum(len(read_voice(voice_root/scene["id"]/f"turn-{i:02d}"/"voice.wav"))/24000
                       for i in range(len(scene["turns"])))
        scene["target_seconds"] = min(scene["target_seconds"], duration + (1.28 if editor.short else 2.5))
        scene["tail_seconds"] = .39 if editor.short else .62
        scene["pause_mode"] = "after_answer"
    timing = plan_dialogue(scenes, voice_root, FPS)
    timing["voice"] = voice
    for scene, chapter in zip(scenes, timing["chapters"], strict=True):
        chapter["visual"] = scene["visual"]
        chapter["captions"] = [cue for turn in chapter["turns"] for cue in timed_captions(
            turn["text"], turn["start"], turn["end"]-turn["start"],
            editor.caption[2]-editor.caption[0]-73, editor.size, protected=PROTECT)]
    return timing


def sample(chapter, time):
    turn = chapter["turns"][0]
    for candidate in chapter["turns"]:
        if time >= candidate["start"]:
            turn = candidate
    cursor = max(0, time - turn["start"])
    fraction = cursor / (turn["end"] - turn["start"])
    phase = 0 if fraction < .25 else 1 if fraction < .62 else 2
    view = turn.get("view", chapter["visual"])
    motion = min(61, int(cursor*12)) if view in {"duo", "presenter"} else 0
    if view in {"duo", "presenter", "map", "bars"}:
        phase = 0
    caption = next((cue["text"] for cue in chapter["captions"] if cue["start"] <= time < cue["end"]), "")
    return view, turn["speaker"], phase, motion, caption


def review_frames(editor, timing, folder, video=None):
    folder.mkdir(parents=True, exist_ok=True)
    size = (216, 384) if editor.short else (432, 243)
    review = []
    for chapter in timing["chapters"]:
        points = [(chapter["start"]+.16, "start")]
        for i, turn in enumerate(chapter["turns"]):
            points.append(((turn["start"]+turn["end"])/2, f"turn-{i:02d}"))
        if not video:
            for cue in chapter["captions"]:
                editor.frame(chapter, *sample(chapter, (cue["start"]+cue["end"])/2))
        for time, label in points:
            path = folder / f"{chapter['id']}-{label}.jpg"
            if video:
                subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-ss", f"{time:.5f}",
                                "-i", str(video), "-frames:v", "1", "-vf", "scale=720:-2", str(path)], check=True)
                with Image.open(path) as opened:
                    picture = opened.copy()
            else:
                picture = editor.frame(chapter, *sample(chapter, time))
                picture.save(path, quality=93)
            review.append(ImageOps.contain(picture, size))
    columns = 5 if editor.short else 4
    sheet = Image.new("RGB", (columns*size[0], math.ceil(len(review)/columns)*size[1]), PAPER)
    for i, picture in enumerate(review):
        sheet.paste(picture, (i % columns * size[0], i // columns * size[1]))
    sheet.save(folder / "contact.jpg", quality=90)


def timestamp(seconds):
    ms = round(seconds*1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def encode(editor, timing, kind, edition, folder):
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"claude-japan-ai-{kind}-{edition}.mp4"
    if output.exists():
        raise FileExistsError("Preserve the existing edition")
    audio, bed = mix(timing, folder / "work")
    command = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "image2pipe", "-framerate", str(FPS),
               "-c:v", "mjpeg", "-i", "pipe:0", "-i", str(audio), "-map", "0:v", "-map", "1:a",
               "-vf", "scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "4", "-g", "48",
               "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
               "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-t", f"{timing['seconds']:.8f}",
               "-movflags", "+faststart", str(output)]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
        try:
            for chapter in timing["chapters"]:
                cache = {}
                for frame in range(chapter["frames"]):
                    state = sample(chapter, chapter["start"]+(frame+.5)/FPS)
                    if state not in cache:
                        data = BytesIO()
                        editor.frame(chapter, *state).save(data, format="JPEG", quality=92)
                        cache[state] = data.getvalue()
                    process.stdin.write(cache[state])
                print(chapter["id"], flush=True)
        finally:
            process.stdin.close()
        if process.wait():
            raise RuntimeError("MP4 encoding failed")
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-xerror", "-i", str(output),
                    "-f", "null", "-"], check=True)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of",
                       "json", str(output)], capture_output=True, check=True).stdout)
    picture, sound = probe["streams"]
    if (picture["width"], picture["height"], picture["codec_name"], picture["pix_fmt"], picture["color_space"]) != (
            editor.w, editor.h, "h264", "yuv420p", "bt709"):
        raise ValueError("Unexpected video stream")
    if (int(picture["nb_frames"]) != timing["frames"] or sound["channels"] != 2 or
            sound["codec_name"] != "aac" or abs(float(probe["format"]["duration"])-timing["seconds"]) > .08):
        raise ValueError("Unexpected duration, sample layout, or audio stream")
    measures = loudness(output)
    if not (-18 <= float(measures["input_i"]) <= -14 and float(measures["input_tp"]) <= -1):
        raise ValueError(f"Final AAC loudness outside the house profile: {measures}")
    with output.open("rb") as stream:
        header = stream.read(1_000_000)
    if not 0 < header.find(b"moov") < header.find(b"mdat"):
        raise ValueError("Required MP4 fast start atom order")
    captions = [cue for chapter in timing["chapters"] for cue in chapter["captions"]]
    output.with_suffix(".srt").write_text("\n\n".join(
        f"{i}\n{timestamp(cue['start'])} --> {timestamp(cue['end'])}\n{cue['text']}"
        for i, cue in enumerate(captions, 1)) + "\n", encoding="utf-8")
    for chapter in timing["chapters"]:
        for turn in chapter["turns"]:
            turn["voice_path"] = Path(turn["voice_path"]).relative_to(ROOT).as_posix()
    save(folder / "timeline.json", timing)
    review_frames(editor, timing, folder / "decoded", video=output)
    proof = dict(file=output.name, bytes=output.stat().st_size, sha256=digest(output),
                 duration=timing["seconds"], resolution=[editor.w, editor.h], fps=FPS, frames=timing["frames"],
                 captions=len(captions), integrated_lufs=float(measures["input_i"]),
                 true_peak_dbtp=float(measures["input_tp"]), voice=timing["voice"], bgm=bed,
                 full_decode="passed", human_listening="pending", user_approved=False, published=False)
    save(folder / "qc.json", proof)
    print(json.dumps(proof, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preview", "render"))
    parser.add_argument("kind", choices=("short", "full"))
    parser.add_argument("--edition", choices=("v01", "v02"), default="v01")
    args = parser.parse_args()
    editor = Editor(args.kind)
    timing = plan(args.kind, editor)
    if args.mode == "preview":
        review_frames(editor, timing, OUT / "previews" / args.edition / args.kind)
        print(f"{args.kind} {timing['seconds']:.3f}s; {timing['frames']} frames")
    else:
        encode(editor, timing, args.kind, args.edition, OUT / "release" / args.edition / args.kind)


if __name__ == "__main__":
    main()
