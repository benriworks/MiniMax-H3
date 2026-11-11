"""Build the forward-pitch landing for the revised parkour shot from saved footage."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import cv2
import numpy as np

from assemble_review import FPS, SHOT_FRAMES, digest, ffprobe


class RooftopProjection:
    """Project a textured roof plane and distant skyline through a pitched camera."""

    def __init__(self, plate, landing_frame):
        height, width = landing_frame.shape[:2]
        self.width, self.height = width, height
        self.focal = height / (2 * math.tan(math.radians(40)))
        self.cx, self.cy = (width - 1) / 2, (height - 1) / 2
        self.x = ((np.arange(width, dtype=np.float32) - self.cx) / self.focal)[None, :]
        self.up = ((self.cy - np.arange(height, dtype=np.float32)) / self.focal)[:, None]
        ph, pw = plate.shape[:2]
        self.surface = plate[round(ph * .47):round(ph * .65), round(pw * .44):round(pw * .63)]
        self.skyline = plate[:round(ph * .165)]
        self.upper_sky = plate[:round(ph * .085), round(pw * .29):round(pw * .77)]
        self.horizon = ph * .145
        contact = landing_frame[:height // 4, width // 4:width * 3 // 4]
        self.floor_tint = np.clip(
            np.median(contact, axis=(0, 1)) - np.median(self.surface, axis=(0, 1)), -25, 25
        ).astype(np.float32)

    def render(self, pitch, advance):
        radians = math.radians(pitch)
        sin_pitch, cos_pitch = math.sin(radians), math.cos(radians)
        dy = self.up * cos_pitch - sin_pitch
        dz = self.up * sin_pitch + cos_pitch
        shape = (self.height, self.width)
        yaw = np.arctan2(self.x, dz)
        elevation = np.arctan2(dy, np.hypot(self.x, dz))
        sky_u = ((.5 + .47 * np.sin(yaw)) * (self.skyline.shape[1] - 1)).astype(np.float32)
        sky_v = np.clip(self.horizon - elevation * self.horizon / 1.08, 0,
                        self.skyline.shape[0] - 1).astype(np.float32)
        backdrop = cv2.remap(self.skyline, sky_u, sky_v, cv2.INTER_LINEAR)
        if pitch > 315:
            # Restore the real forward skyline through the recovery anchor alone.
            clear_sky_v = np.minimum(sky_v, self.skyline.shape[0] * .52)
            clear_sky = cv2.remap(self.skyline, sky_u, clear_sky_v, cv2.INTER_LINEAR)
            recovery = min((pitch - 315) / 28, 1)
            backdrop = cv2.addWeighted(backdrop, 1 - recovery, clear_sky, recovery, 0)
        # Use a separate plane at the zenith so clouds stay continuous across the pole.
        cloud_height, cloud_width = self.upper_sky.shape[:2]
        upper_depth = np.maximum(dy, .40)
        cloud_u = (cloud_width * (.50 + .53 * self.x / upper_depth)).astype(np.float32)
        cloud_v = np.broadcast_to(
            (cloud_height * (.48 + .37 * dz / upper_depth)).astype(np.float32), shape
        ).copy()
        clouds = cv2.remap(self.upper_sky, cloud_u, cloud_v, cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_REFLECT_101)
        cloud_mix = np.clip((elevation - .48) / .39, 0, 1)[..., None]
        backdrop = backdrop * (1 - cloud_mix) + clouds * cloud_mix

        height = .58 - .26 * math.sin(math.pi * advance)
        ray_scale = height / np.maximum(-dy, .003)
        ground_x = ray_scale * self.x
        ground_z = 1.24 + 1.56 * advance + ray_scale * dz
        u = (ground_x * 222 + 20).astype(np.float32)
        v = np.broadcast_to((ground_z * 222 + 83).astype(np.float32), shape).copy()
        floor = cv2.remap(self.surface, u, v, cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_REFLECT_101).astype(np.float32)
        floor += self.floor_tint
        # Two coping strips are visible in the backward-facing portion of the pitch.
        coping = (np.abs(ground_z) > .07) & (np.abs(ground_z) < .19)
        floor += coping[..., None] * np.array([27, 27, 26], dtype=np.float32)
        deck = (np.abs(ground_x) < 5.5) & (ground_z > -12) & (ground_z < 21) & (dy < 0)
        slot = np.abs(ground_z) <= .07
        floor *= np.where(slot, .24, 1)[..., None]
        return np.where(deck[..., None], np.clip(floor, 0, 255), backdrop).astype(np.uint8)

    def blend_anchor(self, scene, anchor, pitch, anchor_pitch):
        delta = pitch - anchor_pitch
        reach = 63.0
        if abs(delta) >= reach:
            return scene
        sin_delta, cos_delta = math.sin(math.radians(delta)), math.cos(math.radians(delta))
        up = self.up * cos_delta - sin_delta
        depth = np.maximum(self.up * sin_delta + cos_delta, .001)
        mx = (self.cx + self.focal * self.x / depth).astype(np.float32)
        my = self.cy - self.focal * up / depth
        my = np.broadcast_to(my.astype(np.float32), mx.shape).copy()
        image = cv2.remap(anchor, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        edge = np.minimum(np.minimum(mx, self.width - 1 - mx), np.minimum(my, self.height - 1 - my))
        strength = math.cos(abs(delta) / reach * math.pi / 2) ** 2
        feather = np.clip((edge + 1) / (1 + 6.8 * abs(delta)), 0, 1)
        alpha = (feather * feather * (3 - 2 * feather) * strength)[..., None]
        return (scene * (1 - alpha) + image * alpha).astype(np.uint8)


def read_clip(path):
    reader = cv2.VideoCapture(str(path))
    frames = []
    try:
        while True:
            success, frame = reader.read()
            if not success:
                break
            frames.append(frame)
    finally:
        reader.release()
    if not frames:
        raise ValueError(f"Could not decode {path}")
    return frames


def audio_filters(source_ranges, output_counts):
    filter_parts = ["[1:a:0]aresample=48000,asplit=3[a0][a1][a2]"]
    for index, ((start, end), count) in enumerate(zip(source_ranges, output_counts, strict=True)):
        duration = count / FPS
        filter_parts.append(
            f"[a{index}]atrim=start={start / FPS:.8f}:end={end / FPS:.8f},"
            f"asetpts=PTS-STARTPTS,atempo={(end - start) / count:.8f},"
            f"aformat=channel_layouts=stereo,apad,atrim=duration={duration:.8f},"
            f"afade=t=in:d=0.008,afade=t=out:st={duration - .008:.8f}:d=0.008[p{index}]"
        )
    filter_parts.append("[p0][p1][p2]concat=n=3:v=0:a=1,atrim=duration=5[a]")
    return ";".join(filter_parts)


def encode_pov(source, output, frames, projection, edit):
    start = edit["source_start_frame"]
    entry = edit["source_entry_frame"]
    exit_frame = edit["source_resume_frame"]
    counts = (edit["approach_frames"], edit["pitch_frames"],
              SHOT_FRAMES - edit["approach_frames"] - edit["pitch_frames"])
    ranges = ((start, entry + 1), (entry + 1, exit_frame), (exit_frame, len(frames)))
    if not (0 <= start <= entry < exit_frame - 1 < len(frames) - 1 and min(counts) > 0):
        raise ValueError("Invalid edit ranges for the source and the 120-frame shot.")
    before = np.rint(np.linspace(start, entry, counts[0])).astype(int)
    after = np.rint(np.linspace(exit_frame, len(frames) - 1, counts[2])).astype(int)
    first_pitch, last_pitch = edit["entry_pitch_degrees"], 360 + edit["resume_pitch_degrees"]
    # Slow slightly around the inverted roofline, then carry the motion up to the sky.
    step = np.linspace(0, 1, counts[1] + 2)[1:-1]
    angles = np.interp(step, [0, .20, .40, .55, .79, 1],
                       [first_pitch, 121, 171, 197, 289, last_pitch])
    shutter = np.gradient(angles) * .26

    def render_sample(angle, position):
        image = projection.render(angle, position)
        image = projection.blend_anchor(image, frames[entry], angle, first_pitch)
        return projection.blend_anchor(image, frames[exit_frame], angle, last_pitch)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "rawvideo", "-pixel_format", "bgr24",
        "-video_size", f"{projection.width}x{projection.height}", "-framerate", str(FPS), "-i", "pipe:0",
        "-i", str(source), "-filter_complex", audio_filters(ranges, counts),
        "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
        "-threads", "4", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", str(output),
    ]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as encoder:
        assert encoder.stdin is not None
        try:
            for index in before:
                encoder.stdin.write(frames[index].tobytes())
            for position, angle, sweep in zip(step, angles, shutter, strict=True):
                earlier = render_sample(angle - sweep, position)
                center = render_sample(angle, position)
                later = render_sample(angle + sweep, position)
                blur = cv2.addWeighted(earlier, .5, later, .5, 0)
                exposed = cv2.addWeighted(center, .55, blur, .45, 0)
                encoder.stdin.write(exposed.tobytes())
            for index in after:
                encoder.stdin.write(frames[index].tobytes())
        finally:
            encoder.stdin.close()
        if encoder.wait() != 0:
            raise ValueError("Could not encode the revised first-person shot.")
    return [round(float(angle), 3) for angle in angles]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_root", type=Path)
    parser.add_argument("edit", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    media = args.media_root
    edit = json.loads(args.edit.read_text(encoding="utf-8"))
    target = args.output or media / "shots/v03/02-pov-roll-review"
    source = media / "shots/v03/02-pov/source.mp4"
    receipt = json.loads(source.with_name("generation.json").read_text(encoding="utf-8"))
    if receipt["state"] != "saved" or digest(source) != receipt["output_sha256"]:
        raise ValueError("The first-person source does not match its generation record.")
    plate_path = media / "plates/v03/inputs/pov-start.png"
    plate = cv2.imread(str(plate_path))
    if plate is None:
        raise ValueError(f"Could not read the roof projection plate at {plate_path}")
    video = next(s for s in ffprobe(source)["streams"] if s["codec_type"] == "video")
    if video["avg_frame_rate"] != "24/1":
        raise ValueError("The revised first-person source must be 24 fps.")
    frames = read_clip(source)
    if not 0 <= edit["source_entry_frame"] < len(frames):
        raise ValueError("The landing anchor lies outside the first-person source.")
    projection = RooftopProjection(plate, frames[edit["source_entry_frame"]])
    target.mkdir(parents=True, exist_ok=False)
    pending = target / "pending.mp4"
    angles = encode_pov(source, pending, frames, projection, edit)
    probe = ffprobe(pending)
    stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    if int(stream["nb_frames"]) != SHOT_FRAMES or float(probe["format"]["duration"]) != 5:
        raise ValueError("The edited first-person shot must have 120 frames and last 5.000 s.")
    output = target / "source.mp4"
    pending.rename(output)
    record = dict(edit, state="rendered", output_sha256=digest(output), bytes=output.stat().st_size,
                  source_sha256=receipt["output_sha256"], projection_plate_sha256=digest(plate_path),
                  pitch_by_insert_frame_degrees=angles, frames=SHOT_FRAMES, duration_seconds=5)
    (target / "derivation.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
