"""Transcribe each new take without handing the script to the recognizer."""
import json
import sys
from pathlib import Path
import wave
import numpy as np
from faster_whisper import WhisperModel

media,repository=map(Path,sys.argv[1:3])
model=WhisperModel(str(repository),device="cpu",compute_type="int8",cpu_threads=5)
out=media/"qa"
out.mkdir(exist_ok=True)
path=out/"asr.json"
transcripts=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
for audio in sorted((media/"voice").glob("*/turn-00/voice.wav")):
    key=audio.parents[1].name
    digest=json.loads((audio.parent/"verified.json").read_text(encoding="utf-8"))["sha256"]
    if transcripts.get(key,{}).get("sha256")==digest: continue
    with wave.open(str(audio),"rb") as stream:
        samples=np.frombuffer(stream.readframes(stream.getnframes()),dtype="<i2").astype(np.float32)/32768
        rate=stream.getframerate()
    pcm=np.interp(np.arange(0,len(samples),rate/16000),np.arange(len(samples)),samples).astype(np.float32)
    seg,_=model.transcribe(pcm,language="ja",beam_size=3,condition_on_previous_text=False)
    transcripts[key]={"text":"".join(x.text for x in seg),"sha256":digest}
    path.write_text(json.dumps(transcripts,ensure_ascii=False,indent=2),encoding="utf-8")
    print(key,flush=True)
