"""Transcribe the final mixed audio locally for a secondary check of dates and spoken figures."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from voice import OUT

def main():
    p=argparse.ArgumentParser()
    p.add_argument("kind",choices=("short","full"))
    p.add_argument("--model",type=Path,required=True)
    p.add_argument("--dependencies",type=Path)
    p.add_argument("--edition",choices=("v01","v02"),default="v01")
    args=p.parse_args()
    if args.dependencies:sys.path.insert(0,str(args.dependencies.resolve()))
    from faster_whisper import WhisperModel
    source=OUT/"release"/args.edition/args.kind/f"php-security-november-{args.kind}-{args.edition}.mp4"
    raw=subprocess.run(["ffmpeg","-v","error","-i",str(source),"-vn","-ac","1","-ar","16000","-f","f32le","pipe:1"],capture_output=True,check=True)
    model=WhisperModel(str(args.model),device="cpu",compute_type="int8",cpu_threads=4,local_files_only=True)
    segments,_=model.transcribe(np.frombuffer(raw.stdout,dtype="<f4"),language="ja",beam_size=3,
                                condition_on_previous_text=False,vad_filter=False)
    rows=[dict(start=round(s.start,2),end=round(s.end,2),text=s.text) for s in segments]
    tag=args.kind if args.edition=="v01" else args.kind+"-"+args.edition
    (OUT/"_private"/f"asr-{tag}.json").write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
    print(args.kind,len(rows),"segments",flush=True)
if __name__=="__main__":main()
