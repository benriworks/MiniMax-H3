"""Keep the verified Japanese sentences, ending in the pause before the stray English outro."""
import hashlib
import json
import sys
import wave
from pathlib import Path

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main(media):
    source=media/"voice/why3/turn-00"
    target=media/"voice/why-final/turn-00"
    target.mkdir(parents=True,exist_ok=True)
    proof=json.loads((source/"verified.json").read_text(encoding="utf-8"))
    with wave.open(str(source/"voice.wav"),"rb") as wav:
        assert wav.getframerate()==24000 and wav.getsampwidth()==2 and wav.getnchannels()==1
        assert sha(source/"voice.wav")==proof["sha256"]
        keep=round(10.98*wav.getframerate())
        samples=wav.readframes(keep)
        params=wav.getparams()
    output=target/"voice.wav"
    with wave.open(str(output),"wb") as wav:
        wav.setparams(params)
        wav.writeframes(samples)
    proof.update(source_sha256=proof["sha256"],sha256=sha(output),seconds=keep/24000,source="why3",end_sample=keep,edit="cut during the pause before English production directions")
    (target/"verified.json").write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__":
    main(Path(sys.argv[1]))
