"""Independently transcribe the selected voice stems without a transcript prompt."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from faster_whisper import WhisperModel


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("media",type=Path)
    ap.add_argument("model",type=Path)
    args=ap.parse_args()
    model=WhisperModel(str(args.model),device="cpu",compute_type="int8",cpu_threads=4)
    out=args.media/"_private/asr"
    out.mkdir(parents=True,exist_ok=True)
    scenes=json.loads((Path(__file__).resolve().parent/"story-v01.json").read_text(encoding="utf-8"))
    for s in scenes:
        raw=subprocess.check_output(["ffmpeg","-nostdin","-loglevel","error","-i",str(args.media/"voice/selected"/s["id"]/"turn-00/voice.wav"),"-f","f32le","-ar","16000","-ac","1","-"])
        segments,_=model.transcribe(np.frombuffer(raw,dtype="<f4"),language="ja",beam_size=3,condition_on_previous_text=False)
        data=[{"start":p.start,"end":p.end,"text":p.text.strip()} for p in segments]
        (out/(s["id"]+".json")).write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8")
        print(s["id"],''.join(p["text"] for p in data),flush=True)


if __name__=="__main__":
    main()
