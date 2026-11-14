"""Synthesize one line with Gemini TTS and save a 24 kHz mono WAV. Refuses to overwrite."""
import argparse, base64, json, os, sys, time, urllib.error, urllib.request, wave
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("text")
p.add_argument("output", type=Path)
p.add_argument("--voice", default="Aoede")
p.add_argument("--style", default="落ち着いた報道番組のアナウンサーとして、はっきりと、やや速めに読んでください: ")
p.add_argument("--model", default="gemini-2.5-flash-preview-tts")
a = p.parse_args()
key = os.environ.get("GEMINI_API_KEY") or sys.exit("GEMINI_API_KEY is not set")
if a.output.exists():
    sys.exit(f"{a.output} already exists")
body = json.dumps({"contents": [{"parts": [{"text": a.style + a.text}]}],
                   "generationConfig": {"responseModalities": ["AUDIO"],
                                        "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": a.voice}}}}}).encode()
url = f"https://generativelanguage.googleapis.com/v1beta/models/{a.model}:generateContent"
for attempt in range(1, 4):
    try:
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
        data = json.load(urllib.request.urlopen(req, timeout=120))
        pcm = base64.b64decode(data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
        a.output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(a.output), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        print(f"OK {a.output} {len(pcm) / 48000:.2f}s")
        sys.exit(0)
    except urllib.error.HTTPError as e:
        print(f"attempt {attempt}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
    except (KeyError, IndexError, OSError) as e:
        print(f"attempt {attempt}: {type(e).__name__} {e}")
    time.sleep(8)
sys.exit(1)
