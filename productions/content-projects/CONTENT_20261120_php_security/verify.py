"""Cross-check the delivered files, caption text, official dates, source hashes and reused voices."""
from collections import Counter
from pathlib import Path
import json
import platform
import subprocess
import PIL
from capture import HERE, ROOT, OUT, write, sha
from voice import load_story

def read(path):return json.loads(path.read_text(encoding="utf-8"))
def check_cut(kind,edition):
    base=OUT/"release"/edition/kind; qc=read(base/"qc.json")
    file=base/qc["file"]; timeline=read(base/"timeline.json")
    story=load_story(edition); script=story[kind]
    assert sha(file)==qc["sha256"] and file.stat().st_size==qc["bytes"]
    assert len(timeline["chapters"])==len(script) and qc["frames"]==sum(ch["frames"] for ch in timeline["chapters"])
    speakers=set();lines=[];lower=-1
    for plan,chapter in zip(timeline["chapters"],script,strict=True):
        assert plan["id"]==chapter["id"]
        captions=plan["captions"]
        text="".join(c["text"].replace("\n","") for c in captions)
        expected="".join(story["lines"][turn["line"]]["text"] for turn in chapter["turns"])
        assert text==expected and not any(term in text for term in ("聞き役","実務役"))
        for cue in captions:
            assert lower<=cue["start"]<cue["end"]<=plan["end"]
            lower=cue["end"]
        for turn in plan["turns"]:
            proof=read((ROOT/turn["voice_path"]).parent/"verified.json")
            item=next(x for x in proof["files"] if x["path"].endswith("voice.wav"))
            assert sha(ROOT/item["path"])==item["sha256"].lower()
            speakers.add(proof["voice"]);lines.append(dict(line=turn["line"],speaker=proof["voice"],sha256=item["sha256"].lower()))
    assert speakers=={"Aoede","Charon"} and qc["full_decode"]=="passed"
    assert qc["bgm"]["gain_profile"]=="explanation_v1"
    captions=sum(len(ch["captions"]) for ch in timeline["chapters"])
    assert captions==qc["captions"]==len(file.with_suffix(".srt").read_text(encoding="utf-8").strip().split("\n\n"))
    assert 0<header_order(file)
    title=story["titles"][kind]
    return dict(edition=edition,title=title,**qc,turn_count=len(lines),srt_sha256=sha(file.with_suffix(".srt")),
         chapters=[dict(title=ch["title"],start=round(ch["start"],3)) for ch in timeline["chapters"]],
         voice_lines=lines,decoded_review_frames=len(list((base/"decoded").glob("*.jpg")))-1)

def header_order(file):
    with file.open("rb") as f:data=f.read(1_000_000)
    moov,mdat=data.find(b"moov"),data.find(b"mdat")
    return moov if 0<moov<mdat else -1

def main():
    cuts={"short":check_cut("short","v01"),"full":check_cut("full","v02")}
    prior=check_cut("full","v01")
    old={r["line"]:r["sha256"] for r in prior["voice_lines"]}
    reused=sum(old.get(row["line"])==row["sha256"] for row in cuts["full"]["voice_lines"])
    assert reused==len(old)-1
    captures=read(OUT/"captures/manifest.json")
    for rec in captures:
        assert sha(OUT/"captures/quotes"/(rec["id"]+".png"))==rec["quote_sha256"]
        assert sha(OUT/"captures/original"/(rec["id"]+".png"))==rec["raw_sha256"]
    advisories=read(OUT/"captures/advisory-metadata.json")
    assert Counter(x["severity"] for x in advisories)=={"critical":7,"high":4,"medium":6}
    review=read(OUT/"release/v01/article/php-security-article-v01.qc.json")
    assert review["sha256"]==sha(OUT/"release/v01/article/php-security-article-v01.zip")
    inputs=read(OUT/"input-manifest.json")
    voice_proofs=[read(p) for p in (OUT/"voice/v01").glob("*/verified.json")]
    total_tokens=sum(p["usage"].get("totalTokenCount",0) for p in voice_proofs)
    proof=dict(date="2026-11-20",cuts=cuts,full_v01=dict(file=prior["file"],sha256=prior["sha256"],duration=prior["duration"]),
               full_v02_reused_turns=reused,source_captures=captures,vendor_advisories=advisories,inputs=inputs,
               tts=dict(verified_takes=len(voice_proofs),reported_total_tokens=total_tokens),article=review,
               runtime=dict(python=platform.python_version(),pillow=PIL.__version__,ffmpeg=subprocess.check_output(
               ["ffmpeg","-version"],encoding="utf-8").splitlines()[0]),
               phone_review="pending",human_listening="pending",published=False)
    write(HERE/"verification-v01.json",proof)
    print([(k,c["edition"],round(c["duration"],3),c["captions"]) for k,c in cuts.items()],reused,"full takes reused")
if __name__=="__main__":main()
