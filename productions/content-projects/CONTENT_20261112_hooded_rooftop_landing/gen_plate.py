"""Create or edit one keyframe with the Gemini image API. Prompt file + optional reference images."""
import argparse, base64, json, os, sys, time, urllib.request, urllib.error
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("prompt", type=Path)
p.add_argument("output", type=Path)
p.add_argument("--ref", type=Path, action="append", default=[])
p.add_argument("--aspect", default="9:16")
p.add_argument("--model", default="gemini-3-pro-image")
a = p.parse_args()
key = os.environ.get("GEMINI_API_KEY") or sys.exit("GEMINI_API_KEY is not set")
if a.output.exists():
    sys.exit(f"{a.output} already exists")
parts = [{"inlineData": {"mimeType": "image/png" if r.suffix.lower() == ".png" else "image/jpeg",
                         "data": base64.b64encode(r.read_bytes()).decode()}} for r in a.ref]
parts.append({"text": a.prompt.read_text(encoding="utf-8")})
body = json.dumps({"contents": [{"parts": parts}],
                   "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": a.aspect}}}).encode()
url = f"https://generativelanguage.googleapis.com/v1beta/models/{a.model}:generateContent"
for attempt in range(1, 4):
    try:
        req = urllib.request.Request(url, body, {"Content-Type": "application/json", "x-goog-api-key": key})
        data = json.load(urllib.request.urlopen(req, timeout=170))
        for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                a.output.parent.mkdir(parents=True, exist_ok=True)
                a.output.write_bytes(base64.b64decode(part["inlineData"]["data"]))
                print(f"OK {a.output} {part['inlineData'].get('mimeType')}")
                sys.exit(0)
        print(f"attempt {attempt}: no image, finish={data.get('candidates', [{}])[0].get('finishReason')}")
    except (TimeoutError, OSError) as e:
        print(f"attempt {attempt}: {type(e).__name__} {e}") if not isinstance(e, urllib.error.HTTPError) else print(f"attempt {attempt}: HTTP {e.code} {e.read()[:300].decode(errors=chr(114)+chr(101)+chr(112)+chr(108)+chr(97)+chr(99)+chr(101))}")
    except urllib.error.HTTPError as e:
        print(f"attempt {attempt}: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
    time.sleep(8)
sys.exit(1)
