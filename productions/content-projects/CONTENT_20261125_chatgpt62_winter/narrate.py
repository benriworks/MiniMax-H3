"""Generate the two winter films' shared takes using the requested Gemini 3.8 voice model."""
import argparse
import base64
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import wave
from datetime import datetime, timezone
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from tools.studio.dialogue_narration import VOICES, payload, pcm

MODEL="gemini-3.8-flash-tts"

def decode(data):
    candidates=data.get("candidates",[])
    if len(candidates)!=1 or candidates[0].get("finishReason")!="STOP":
        raise ValueError("No complete speech candidate")
    items=[p["inlineData"] for p in candidates[0]["content"]["parts"] if "inlineData" in p]
    if len(items)!=1:
        raise ValueError("Expected one audio part")
    if items[0]["mimeType"].lower().split(";")[0] not in ("audio/wav","audio/x-wav"):
        return pcm.decode_audio(data, minimum_seconds=.25)
    wav=base64.b64decode(items[0]["data"],validate=True)
    with wave.open(io.BytesIO(wav),"rb") as stream:
        if (stream.getnchannels(),stream.getsampwidth(),stream.getframerate())!=(1,2,24000):
            raise ValueError("Unexpected speech format")
        n=stream.getnframes()
        if not 6000<=n<=45*24000 or len(stream.readframes(n))!=n*2:
            raise ValueError("Unexpected speech length")
    return wav,n/24000

def one(line,root,confirm):
    target=root/"voice"/line["id"]/"turn-00"
    body=payload(line["reading"],line["speaker"],"conversational_v3")
    cache=target/"response.json"
    if not target.exists():
        if not confirm:
            raise RuntimeError("Initial recording requires --generate")
        key=os.environ.get("GEMINI_API_KEY") or os.environ["GOOGLE_API_KEY"]
        target.mkdir(parents=True)
        pcm.save(target/"request.json",body)
        submission=dict(model=MODEL,voice=VOICES[line["speaker"]],state="submission_unknown",time=datetime.now(timezone.utc).isoformat())
        pcm.save(target/"submission.json",submission)
        req=urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
                data=json.dumps(body).encode(),headers={"Content-Type":"application/json","x-goog-api-key":key},method="POST")
        try:
            with urllib.request.build_opener(pcm.NoRedirect()).open(req,timeout=130) as result:
                raw=result.read(12000001)
            if len(raw)>12000000:
                raise ValueError("Oversize audio response")
            cache.write_bytes(raw)
        except urllib.error.HTTPError as err:
            submission.update(state="rejected",http=err.code)
            pcm.save(target/"submission.json",submission)
            raise RuntimeError(f"Speech API returned HTTP {err.code} for {line['id']}") from None
        pcm.save(target/"submission.json",submission|{"state":"response_saved"})
    if not cache.is_file() or json.loads((target/"request.json").read_text(encoding="utf-8"))!=body:
        raise RuntimeError(f"Review incomplete or changed take {line['id']}")
    data=json.loads(cache.read_bytes())
    wav,seconds=decode(data)
    output=target/"voice.wav"
    if output.exists():
        if output.read_bytes()!=wav: raise RuntimeError("Existing audio differs from saved response")
    else:
        output.write_bytes(wav)
    pcm.save(target/"verified.json",dict(model=MODEL,version=data.get("modelVersion"),voice=VOICES[line["speaker"]],seconds=seconds,
        sha256=hashlib.sha256(wav).hexdigest(),usage=data.get("usageMetadata"),mime=data["candidates"][0]["content"]["parts"][0].get("inlineData",{}).get("mimeType")))
    print(f"{line['id']} {VOICES[line['speaker']]} {seconds:.2f}s",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("media",type=Path)
    ap.add_argument("--generate",action="store_true")
    ap.add_argument("--only",nargs="+")
    args=ap.parse_args()
    story=json.loads((HERE/"dialogue.json").read_text(encoding="utf-8"))
    selected=set(args.only or story["short"]+story["full"])
    for line in story["lines"]:
        if line["id"] in selected: one(line,args.media,args.generate)
