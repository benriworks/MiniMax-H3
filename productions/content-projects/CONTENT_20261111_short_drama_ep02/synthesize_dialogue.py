"""Synthesize the two episode lines, preserving responses for local recovery."""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.studio.dialogue_narration import VOICES, payload, pcm

MODEL = "gemini-3.8-flash-tts"
API = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
LINES = (
    ("d01-father", "male", "an older father casually framing a photo of his adult daughter"),
    ("d02-maho", "female", "an adult daughter gently inviting her father into the photo"),
)


def decode(data):
    candidates = data.get("candidates", [])
    if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
        raise ValueError("Expected one complete audio candidate")
    clips = [part["inlineData"] for part in candidates[0]["content"]["parts"] if "inlineData" in part]
    if len(clips) != 1 or clips[0]["mimeType"].lower().split(";")[0] not in {"audio/wav", "audio/x-wav"}:
        return pcm.decode_audio(data, minimum_seconds=.2)
    original = base64.b64decode(clips[0]["data"], validate=True)
    with wave.open(io.BytesIO(original), "rb") as stream:
        samples = stream.readframes(stream.getnframes())
        duration = stream.getnframes() / stream.getframerate()
        if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 24000):
            raise ValueError("Expected 24 kHz mono 16-bit speech")
        if not .2 <= duration <= 12 or len(samples) != stream.getnframes() * 2:
            raise ValueError("Malformed or unexpectedly long speech")
    return original, duration


def synthesize(target, speaker, actor, transcript, confirm):
    request = payload(transcript, speaker, "quoted_dialogue_v2")
    part = request["contents"][0]["parts"][0]
    part["text"] = part["text"].replace(
        f"Use the configured calm professional Japanese {speaker} voice.",
        f"Act as {actor}. Speak naturally in a quiet Japanese family drama.",
    )
    response = target / "response.json"
    if target.exists():
        if not response.is_file() or json.loads((target / "request.json").read_text(encoding="utf-8")) != request:
            raise ValueError(f"Check the previous submission before retrying {target.name}")
    else:
        if not confirm:
            raise ValueError("Initial speech submission requires --confirm-billable")
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Gemini API key is not configured")
        target.mkdir(parents=True)
        pcm.save(target / "request.json", request)
        state = {"model": MODEL, "voice": VOICES[speaker], "state": "submission_unknown",
                 "submitted_utc": datetime.now(timezone.utc).isoformat(), "automatic_retry": False}
        pcm.save(target / "submission.json", state)
        post = urllib.request.Request(API, data=json.dumps(request).encode(), method="POST",
                                      headers={"Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.build_opener(pcm.NoRedirect()).open(post, timeout=120) as result:
                raw = result.read(8_000_001)
        except urllib.error.HTTPError as error:
            state.update(state="rejected", http_status=error.code)
            pcm.save(target / "submission.json", state)
            raise RuntimeError(f"Gemini rejected {target.name} with HTTP {error.code}") from None
        if len(raw) > 8_000_000:
            raise ValueError("Speech response exceeded its size limit")
        response.write_bytes(raw)
        state["state"] = "response_saved"
        pcm.save(target / "submission.json", state)
    data = json.loads(response.read_text(encoding="utf-8"))
    wav, seconds = decode(data)
    voice_path = target / "voice.wav"
    if voice_path.exists():
        if voice_path.read_bytes() != wav:
            raise ValueError(f"Existing WAV differs from the saved response for {target.name}")
    else:
        voice_path.write_bytes(wav)
    proof = {"model": MODEL, "voice": VOICES[speaker], "seconds": seconds,
             "sha256": hashlib.sha256(wav).hexdigest(), "usage": data.get("usageMetadata", {})}
    pcm.save(target / "verified.json", proof)
    print(f"{target.name} {proof['voice']}: {seconds:.3f} seconds", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--reading", type=Path, default=Path(__file__).with_name("dialogue-read-v01.txt"))
    parser.add_argument("--line", choices=[line[0] for line in LINES])
    parser.add_argument("--confirm-billable", action="store_true")
    args = parser.parse_args()
    blocks = args.reading.read_text(encoding="utf-8").strip().split("\n\n")
    prepared = list(zip(LINES, blocks, strict=True))
    for (name, speaker, actor), block in prepared:
        if args.line and args.line != name:
            continue
        target = args.output / name
        initial = not target.exists()
        synthesize(target, speaker, actor, block.split("\n", 1)[1], args.confirm_billable)
        if initial and not args.line and name == LINES[0][0]:
            time.sleep(22)


if __name__ == "__main__":
    main()
