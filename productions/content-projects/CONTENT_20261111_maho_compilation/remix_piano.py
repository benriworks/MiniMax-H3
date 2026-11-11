"""Replace the score of the 60-second Maho compilation from its saved audio stems."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.studio.music_mix import music_gain_envelope

RATE = 48000
EPISODE = 30
DURATION = 60
OPENING = 10 * RATE
SOURCE_SHA256 = "ff90f386d86e8e608368ed87e5f814e5577fd300aa7929b76776335519888a9e"
TRACK_SHA256 = "dae498787497fa218a2ce24602edfc58279f21272b27e34fe2150fc4f473286e"
SPEECH = [(19.30, 25.50), (30.31, 32.91), (48.52, 50.71)]
TRACK_START = .505
MUSIC_GAIN_DB = -8.6
DUCK_GAIN = .38
OUTPUT_GAIN_DB = 2.55
OUTPUT_CEILING = .79
FADE_IN = .075
FADE_OUT = 3.2


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ffmpeg(*args, pcm=None, log="error"):
    return subprocess.run(
        ["ffmpeg", "-v", log, "-nostdin", *map(str, args)],
        input=pcm, check=True, stdout=subprocess.PIPE,
    ).stdout


def read_stem(path):
    with wave.open(str(path), "rb") as reader:
        actual = (reader.getframerate(), reader.getnchannels(), reader.getsampwidth(), reader.getnframes())
        if actual != (RATE, 2, 2, RATE * EPISODE):
            raise ValueError(f"Unexpected source PCM format: {path}")
        return np.frombuffer(reader.readframes(RATE * EPISODE), "<i2").reshape(-1, 2).astype(np.int32)


def decode_pcm(*args):
    raw = ffmpeg(*args, "-vn", "-ar", RATE, "-ac", 2, "-f", "f32le", "-")
    return np.frombuffer(raw, "<f4").reshape(-1, 2).copy()


def score_free_episode(folder, room_name):
    room, dialogue, old_piano, mix = [
        read_stem(folder / name) for name in [room_name, "dialogue.wav", "piano.wav", "mix.wav"]
    ]
    if np.max(np.abs(room + dialogue + old_piano - mix)) > 2:
        raise ValueError(f"Stems do not reconstruct the saved mix: {folder}")
    return room, dialogue, old_piano, mix


def apply_master(samples, gain_db, ceiling):
    filters = f"volume={gain_db}dB,alimiter=limit={ceiling}:level=false:latency=true:attack=4:release=50"
    raw = ffmpeg("-f", "f32le", "-ar", RATE, "-ac", 2, "-i", "pipe:0", "-af", filters, "-f",
                 "f32le", "-", pcm=samples.astype("<f4").tobytes())
    result = np.frombuffer(raw, "<f4").reshape(-1, 2)
    if result.shape != samples.shape:
        raise ValueError("Master processing shifted the timeline")
    return result


def dry_audio(base):
    first = base / "CONTENT_20261108_short_drama" / "edit"
    second = base / "CONTENT_20261111_short_drama_ep02" / "edit/v02"
    room, dialogue, old_piano, old_mix = score_free_episode(first / "v03", "room-and-effects.wav")
    revised = read_stem(first / "v04/mix.wav")
    if not np.array_equal(revised[OPENING:], old_mix[OPENING:]) or np.any(old_piano[:OPENING]):
        raise ValueError("The saved opening or its tail does not match the stem split")
    revised[OPENING:] = (room + dialogue)[OPENING:]
    room, dialogue, _, _ = score_free_episode(second, "pier-and-effects.wav")
    dry = np.concatenate((
        apply_master(revised / 32768., 3.8, .84),
        apply_master((room + dialogue) / 32768., 4.62, .82),
    ))
    bridge = room[round(4.70 * RATE):round(5.45 * RATE)] / 32768.
    time = np.arange(len(bridge)) / RATE
    bridge *= np.minimum(time / .36, 1)[:, None]
    bridge *= np.clip((.75 - time) / .38, 0, 1)[:, None]
    start = round(29.63 * RATE)
    dry[start:start + len(bridge)] += bridge * 10 ** (4.62 / 20)
    return dry * 10 ** (-.35 / 20)


def piano_audio(track):
    piano = decode_pcm("-i", track, "-ss", TRACK_START, "-t", DURATION)
    if len(piano) != DURATION * RATE:
        raise ValueError("The piano source is shorter than the selected excerpt")
    envelope = music_gain_envelope(
        DURATION, SPEECH, sample_rate=RATE, base_gain=10 ** (MUSIC_GAIN_DB / 20),
        duck_gain=DUCK_GAIN, edge_boost_db=0, attack_seconds=.23, release_seconds=.90,
    )
    piano *= envelope[:, None]
    intro = round(FADE_IN * RATE)
    outro = round(FADE_OUT * RATE)
    piano[:intro] *= np.linspace(0, 1, intro, dtype=np.float32)[:, None]
    piano[-outro:] *= np.linspace(1, 0, outro, dtype=np.float32)[:, None]
    return piano


def packet_hashes(path):
    return ffmpeg("-i", path, "-map", "0:v:0", "-c:v", "copy", "-f", "framehash", "-")


def dbfs(samples):
    return round(float(10 * np.log10(np.mean(samples ** 2))), 2)


def verify(source, target, dry, piano):
    raw = subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(target)])
    info = json.loads(raw)
    video, audio = info["streams"]
    assert (video["codec_name"], video["width"], video["height"], video["avg_frame_rate"], video["nb_frames"]) == (
        "h264", 1080, 1920, "24/1", "1440")
    assert (audio["codec_name"], audio["sample_rate"], audio["channels"]) == ("aac", "48000", 2)
    assert all(float(stream["start_time"]) == 0 and float(stream["duration"]) == DURATION for stream in (video, audio))
    assert float(info["format"]["duration"]) == DURATION
    packets = packet_hashes(target)
    assert packet_hashes(source) == packets
    ffmpeg("-xerror", "-i", target, "-f", "null", "-")
    measured = subprocess.run(
        ["ffmpeg", "-v", "info", "-nostdin", "-i", str(target), "-vn", "-af", "loudnorm=print_format=json",
         "-f", "null", "-"], check=True, capture_output=True, text=True,
    ).stderr
    loudness = json.JSONDecoder().raw_decode(measured[measured.rfind("{"):])[0]
    integrated, true_peak = float(loudness["input_i"]), float(loudness["input_tp"])
    if not -18 <= integrated <= -14 or not true_peak <= -1:
        raise ValueError(f"Encoded audio outside review target: {integrated} LUFS, {true_peak} dBTP")
    speech_levels = []
    for start, end in SPEECH:
        interval = slice(round(start * RATE), round(end * RATE))
        speech_levels.append({
            "from": start, "to": end, "dialogue_and_effects_rms_dbfs": dbfs(dry[interval]),
            "piano_rms_dbfs": dbfs(piano[interval]),
        })
    return dict(
        seconds=DURATION, frames=1440, video_packet_hash_and_timing_identical=True,
        video_packet_list_sha256=hashlib.sha256(packets).hexdigest(), full_decode="passed",
        integrated_lufs=integrated, true_peak_dbtp=true_peak,
        opening_250ms_piano_rms_dbfs=dbfs(piano[:RATE // 4]),
        speech_window_levels=speech_levels,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("media_root", type=Path, help="Directory containing the three content-project outputs")
    parser.add_argument("track", type=Path, help="Original yuuguredoki.mp3 from Music Atelier Amacha")
    parser.add_argument("--version", default="v02")
    args = parser.parse_args()
    if not re.fullmatch(r"v02(?:-[a-z0-9-]+)?", args.version):
        parser.error("Use v02 or a distinct v02-* review version")
    case = args.media_root.resolve() / "CONTENT_20261111_maho_compilation"
    source = case / "review/v01/maho-mata-futari-v01.mp4"
    output = case / "review" / args.version
    if output.exists():
        raise FileExistsError(output)
    if sha256(source) != SOURCE_SHA256 or sha256(args.track) != TRACK_SHA256:
        raise ValueError("The input video or piano source differs from the recorded original")

    dry = dry_audio(args.media_root.resolve())
    piano = piano_audio(args.track)
    mixed = apply_master(dry + piano, OUTPUT_GAIN_DB, OUTPUT_CEILING)
    peak = float(np.max(np.abs(mixed)))
    if not peak < .98:
        raise ValueError(f"Insufficient peak headroom: {peak}")
    with TemporaryDirectory(prefix=f"{args.version}-", dir=output.parent) as scratch:
        staging = Path(scratch) / "verified"
        staging.mkdir()
        target = staging / f"maho-mata-futari-{args.version}.mp4"
        ffmpeg(
            "-n", "-copyts", "-i", source, "-f", "f32le", "-ar", RATE, "-ac", 2, "-i", "pipe:0",
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-ar", RATE, "-ac", 2, "-t", DURATION, "-avoid_negative_ts", "disabled", "-movflags",
            "+faststart", target, pcm=mixed.astype("<f4").tobytes(),
        )
        result = verify(source, target, dry, piano)
        result.update(
            version=args.version, filename=target.name, sha256=sha256(target), bytes=target.stat().st_size,
            source_sha256=SOURCE_SHA256, track_sha256=TRACK_SHA256, track_start_seconds=TRACK_START,
            music_gain_db=MUSIC_GAIN_DB, duck_gain=DUCK_GAIN, fade_in_seconds=FADE_IN, fade_out_seconds=FADE_OUT,
            output_gain_db=OUTPUT_GAIN_DB, output_sample_ceiling=OUTPUT_CEILING,
            human_listening="unverified", mobile_playback="unverified", user_approved=False, published=False,
        )
        record = json.dumps(result, indent=2)
        (staging / "render.json").write_text(record + "\n", encoding="utf-8")
        staging.rename(output)
    print(record)


if __name__ == "__main__":
    main()
