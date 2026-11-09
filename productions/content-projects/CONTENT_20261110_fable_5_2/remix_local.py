"""Replace the background bed using the licensed local music inventory."""
import argparse
import json
import math
from pathlib import Path
import subprocess

import numpy as np

from produce import CREATION, OUT, digest, meter, normalize, read, run, save
from tools.studio.longform_audio import SR, read_voice, write_pcm

MUSIC = {
    "file": "yuugurenocampus.mp3",
    "title": "夕暮れのキャンパス",
    "artist": "甘茶（甘茶の音楽工房）",
    "source": "https://amachamusic.chagasi.com/music_yuugurenocampus.html",
    "terms": "https://amachamusic.chagasi.com/terms.html",
    "sha256": "19fd42bf8e542fe345e7b1209c4bcf227eaf8a572944022774fa0ff3e6a3bf66",
    "terms_checked_at": "2026-11-10",
    "content_id_registration_allowed": False,
}
TARGET_LUFS = -32.0
CROSSFADE_SECONDS = 2.0


def source_music(inventory):
    item = next(item for item in read(inventory) if item["file"] == MUSIC["file"])
    source = Path(item["local_path"])
    if digest(source) != MUSIC["sha256"]:
        raise ValueError("Local music source checksum changed")
    return source


def music_samples(source):
    metric = meter(source, "loudnorm=print_format=json")
    gain = 10 ** ((TARGET_LUFS - float(metric["input_i"])) / 20)
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", str(source), "-ar", str(SR),
         "-ac", "2", "-f", "f32le", "pipe:1"],
        capture_output=True, check=True, creationflags=CREATION).stdout
    samples = np.frombuffer(decoded, dtype="<f4").reshape(-1, 2) * gain
    return samples, float(metric["input_i"]), gain


def fit_music(source, n):
    length = len(source)
    crossfade = round(CROSSFADE_SECONDS*SR)
    if length <= 2*crossfade:
        raise ValueError("Track is too short to crossfade")
    out = np.zeros((n, 2), dtype=np.float32)
    step = length-crossfade
    starts = [0]
    while starts[-1]+length < n:
        starts.append(starts[-1]+step)
    for i, start in enumerate(starts):
        segment = source[:min(length, n-start)].copy()
        if i:
            fade = np.linspace(0, math.pi/2, min(crossfade, len(segment)), dtype=np.float32)
            segment[:len(fade)] *= np.sin(fade)[:, None]
        if i < len(starts)-1:
            fade = np.linspace(0, math.pi/2, crossfade, dtype=np.float32)
            segment[-crossfade:] *= np.cos(fade)[:, None]
        out[start:start+len(segment)] += segment
    for count, section in [(round(.3*SR), "head"), (round(1.2*SR), "tail")]:
        count = min(n, count)
        fade = np.linspace(0, 1, count, dtype=np.float32)[:, None]
        if section == "head":
            out[:count] *= fade
        else:
            out[-count:] *= fade[::-1]
    return out, [start/SR for start in starts[1:]]


def video_hash(path):
    return run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0",
                "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"]).stdout.strip().split("=", 1)[1]


def remix(kind, source, music, source_lufs, gain, *, revision="v02", narration=None):
    initial = OUT/"release/v01"/kind
    release = OUT/"release"/revision/kind
    release.mkdir(parents=True, exist_ok=True)
    previous = initial/f"fable-5-2-{kind}-v01.mp4"
    final = release/f"fable-5-2-{kind}-{revision}.mp4"
    if final.exists():
        raise FileExistsError("Preserve the v02 review candidate")
    old = read(initial/"verification.json")
    if digest(previous) != old["sha256"]:
        raise ValueError("The verified v01 video changed")
    voice = narration or initial/"work/narration.wav"
    speech = read_voice(voice)
    voice_hash = digest(voice)
    if len(speech) != round(old["seconds"]*SR):
        raise ValueError("Narration and v01 duration differ")
    bed, crossfades = fit_music(music, len(speech))
    combined = speech[:, None] + bed
    peak = float(np.max(np.abs(combined)))
    if peak >= 1:
        raise ValueError("Premaster exceeds full scale")
    work = release/"work"
    work.mkdir(exist_ok=True)
    write_pcm(work/"mix-premaster.wav", combined)
    normalize(work/"mix-premaster.wav", work/"mix.wav")
    temp = work/"muxed.mp4"
    run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(previous), "-i", str(work/"mix.wav"),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-movflags", "+faststart", str(temp)])
    expected_video = video_hash(previous)
    if video_hash(temp) != expected_video or digest(voice) != voice_hash or digest(source) != MUSIC["sha256"]:
        raise ValueError("Frozen video, narration, or licensed source did not verify")
    run(["ffmpeg", "-v", "error", "-nostdin", "-xerror", "-i", str(temp), "-f", "null", "-"])
    raw_probe = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(temp)])
    probe = json.loads(raw_probe.stdout)
    picture, audio = probe["streams"]
    actual = (picture["width"], picture["height"], int(picture["nb_frames"]), picture["avg_frame_rate"])
    if actual != (old["width"], old["height"], old["frames"], old["fps"]) or audio["codec_name"] != "aac":
        raise ValueError("Video geometry or audio codec changed unexpectedly")
    if abs(float(probe["format"]["duration"])-old["seconds"]) > .08:
        raise ValueError("Remix duration does not match the picture")
    loudness = meter(temp, "loudnorm=print_format=json")
    integrated, true_peak = float(loudness["input_i"]), float(loudness["input_tp"])
    if not -17.2 <= integrated <= -14.8 or true_peak > -1:
        raise ValueError(f"Unexpected final loudness: {loudness}")
    (release/"subtitles-ja.srt").write_bytes((initial/"subtitles-ja.srt").read_bytes())
    temp.rename(final)
    proof = dict(old, file=final.name, revision=revision, bytes=final.stat().st_size, sha256=digest(final),
                 graph_evidence_revision="v01",
                 integrated_lufs=integrated, true_peak_dbtp=true_peak, video_stream_sha256=expected_video,
                 video_stream_matches_v01=True, narration_sha256=voice_hash, original_v01_sha256=old["sha256"],
                 music=dict(MUSIC, input_lufs=source_lufs, source_linear_gain=gain, target_bed_lufs=TARGET_LUFS,
                            speech_ducking=False, edge_boost_db=0, head_fade_seconds=.3, tail_fade_seconds=1.2,
                            crossfade_seconds=CROSSFADE_SECONDS, loop_offsets_seconds=crossfades),
                 human_listening="pending", smartphone_playback="pending")
    save(release/"verification.json", proof)
    print(f"{final.name}: {proof['bytes']} bytes, {integrated:.2f} LUFS, {true_peak:.2f} dBTP", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--kind", choices=["short", "full", "all"], default="all")
    args = parser.parse_args()
    local = source_music(args.inventory)
    music, source_lufs, gain = music_samples(local)
    for kind in ("short", "full") if args.kind == "all" else (args.kind,):
        remix(kind, local, music, source_lufs, gain)


if __name__ == "__main__":
    main()
