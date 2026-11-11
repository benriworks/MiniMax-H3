"""Replace the rooftop approach while carrying the reviewed roll and sound into v04."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from assemble_review import FPS, SHOT_FRAMES, digest, ffprobe, sampled_video_filter


CROSSING_FRAMES = 20
APPROVED_TAIL_FRAME = 150
TRACK_TIMESCALE = 12288


def ffmpeg(*arguments, capture=False):
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-xerror",
         *map(str, arguments)],
        check=True, capture_output=capture, text=capture,
    )
    return result.stdout if capture else None


def verified_shot(media, name):
    path = media / "shots/v04" / name / "source.mp4"
    generation = json.loads(path.with_name("generation.json").read_text(encoding="utf-8"))
    if generation["state"] != "saved" or digest(path) != generation["output_sha256"]:
        raise ValueError(f"Generation record does not match {name}.")
    video = next(s for s in ffprobe(path)["streams"] if s["codec_type"] == "video")
    if video["avg_frame_rate"] != "24/1":
        raise ValueError(f"Expected 24 fps in {name}.")
    return path, int(video["nb_frames"]), generation["output_sha256"]


def video_frame_hashes(path, start):
    value = ffmpeg("-i", path, "-map", "0:v:0", "-vf", f"trim=start_frame={start}",
                   "-an", "-f", "framehash", "-hash", "sha256", "-", capture=True)
    return [line.rsplit(",", 1)[-1].strip() for line in value.splitlines()
            if line.lstrip().startswith("0,")]


def audio_hash(path):
    return ffmpeg("-i", path, "-map", "0:a:0", "-c:a", "copy",
                  "-f", "hash", "-hash", "sha256", "-", capture=True).strip().split("=", 1)[1]


def check_timeline(path):
    probe = ffprobe(path)
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    if (video["codec_name"], video["width"], video["height"], video["avg_frame_rate"],
            int(video["nb_frames"]), float(probe["format"]["duration"])) != (
            "h264", 1080, 1920, "24/1", 2 * SHOT_FRAMES, 10.0):
        raise ValueError("The revised review must be a ten-second portrait H.264 file.")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "frame=best_effort_timestamp:stream=time_base", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    timeline = json.loads(result.stdout)
    pts = [int(item["best_effort_timestamp"]) for item in timeline["frames"]]
    expected = [index * (TRACK_TIMESCALE // FPS) for index in range(2 * SHOT_FRAMES)]
    if timeline["streams"][0]["time_base"] != f"1/{TRACK_TIMESCALE}" or pts != expected:
        raise ValueError("The revised timeline is missing a frame or has moved a boundary.")
    ffmpeg("-i", path, "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-")
    return probe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_root", type=Path)
    parser.add_argument("--version", default="v04-review")
    args = parser.parse_args()
    if not re.fullmatch(r"v04(?:-[a-z0-9-]+)?", args.version):
        parser.error("Choose v04 or a separate v04-* output.")
    media = args.media_root.resolve()
    approved = media / "review/v03-review/rooftop-parkour-pov-test-v03-review.mp4"
    approved_record = json.loads(approved.with_name("render.json").read_text(encoding="utf-8"))
    approved_hash = digest(approved)
    if approved_hash != approved_record["sha256"]:
        raise ValueError("The reviewed v03 video does not match its render record.")

    overhead, overhead_frames, overhead_hash = verified_shot(media, "01-overhead-locked")
    crossing, crossing_frames, crossing_hash = verified_shot(media, "02-pov-crossing")
    landing_start = SHOT_FRAMES + CROSSING_FRAMES
    filters = [
        sampled_video_filter(0, overhead_frames, SHOT_FRAMES, "aerial"),
        sampled_video_filter(1, crossing_frames, CROSSING_FRAMES, "crossing"),
        f"[2:v:0]trim=start_frame={landing_start}:end_frame={APPROVED_TAIL_FRAME},"
        f"setpts=N/({FPS}*TB),setsar=1,format=yuv420p[landing]",
        "[aerial][crossing][landing]concat=n=3:v=1:a=0[v]",
    ]

    target = media / "review" / args.version
    target.mkdir(parents=True, exist_ok=False)
    pending = target / "pending.mp4"
    with TemporaryDirectory(prefix="stitch-", dir=target) as temp:
        temp = Path(temp)
        ffmpeg("-i", overhead, "-i", crossing, "-i", approved,
               "-filter_complex_threads", "2", "-filter_complex", ";".join(filters),
               "-map", "[v]", "-an", "-r", str(FPS), "-c:v", "libx264", "-preset", "fast",
               "-crf", "16", "-threads", "4", "-video_track_timescale", TRACK_TIMESCALE,
               temp / "prefix.mp4")
        ffmpeg("-ss", f"{APPROVED_TAIL_FRAME / FPS:.8f}", "-i", approved, "-map", "0:v:0",
               "-c:v", "copy", "-an", "-avoid_negative_ts", "disabled", temp / "tail.mp4")
        playlist = temp / "stitch.ffconcat"
        playlist.write_text(
            "ffconcat version 1.0\nfile 'prefix.mp4'\n"
            f"duration {APPROVED_TAIL_FRAME / FPS:.8f}\nfile 'tail.mp4'\n",
            encoding="ascii",
        )
        ffmpeg("-f", "concat", "-safe", "1", "-i", playlist, "-i", approved,
               "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
               "-video_track_timescale", TRACK_TIMESCALE, "-movflags", "+faststart", pending)

    record = check_timeline(pending)
    approved_frames = video_frame_hashes(approved, APPROVED_TAIL_FRAME)
    output_frames = video_frame_hashes(pending, APPROVED_TAIL_FRAME)
    original_audio = audio_hash(approved)
    if len(approved_frames) != 2 * SHOT_FRAMES - APPROVED_TAIL_FRAME or approved_frames != output_frames:
        raise ValueError("The reviewed tail must match at the pixel level.")
    if original_audio != audio_hash(pending):
        raise ValueError("The reviewed AAC payload must match.")
    output = target / f"rooftop-parkour-pov-test-{args.version}.mp4"
    pending.rename(output)
    record.update(
        version=args.version, sha256=digest(output), decode="passed",
        cut_at_seconds=5.0, new_crossing_frames=CROSSING_FRAMES,
        sources={
            "overhead": {"path": overhead.relative_to(media).as_posix(),
                         "sha256": overhead_hash, "frames": overhead_frames},
            "crossing": {"path": crossing.relative_to(media).as_posix(),
                         "sha256": crossing_hash, "frames": crossing_frames},
            "reviewed_v03": {"path": approved.relative_to(media).as_posix(), "sha256": approved_hash},
        },
        reviewed_tail_first_frame=APPROVED_TAIL_FRAME, matching_tail_frames=len(output_frames),
        reviewed_tail_frame_hashes_sha256=hashlib.sha256("\n".join(output_frames).encode("ascii")).hexdigest(),
        original_aac_sha256=original_audio,
    )
    (target / "render.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
