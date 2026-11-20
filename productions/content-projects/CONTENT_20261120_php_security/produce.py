"""Plan, preview and export the two editions, keeping each successful MP4 immutable."""
from functools import partial
import argparse
import json
import math
from pathlib import Path
import sys
import tempfile

from PIL import Image, ImageOps
from voice import HERE, OUT, ROOT, load_story
from layout import Editor, PAPER, CARDS
from media_inputs import MUSIC
from capture import sha, write
# Reuse the established exporter, music mastering and QC. The previous case's default
# stem, sampling and music source remain its own when it is run directly.
sys.path.append(str(HERE.parent/"CONTENT_20261117_japan_ai_usage"))
from render import encode
from mix_audio import mix
from tools.studio.editorial_captions import timed_captions, PROTECTED
from tools.studio.longform_audio import read_voice, SR

FPS=24
PROTECT=(*PROTECTED,"PHP2Shell","PHP","レンタルサーバー","セキュリティ","セッション","11月19日","10月21日","10月23日","8.4.27","8.4.28","Critical","買い物かご","Webリクエスト")

def plan(kind,ed,edition="v01"):
    story=load_story(edition)
    protected=(*PROTECT,"Red Hat Enterprise Linux","Red Hat","Remi","Linux","PHP2Shell","データベース") if ed.named_sources else PROTECT
    current=0; chapters=[]
    for chapter in story[kind]:
        start=current/FPS; turns=[]; captions=[]
        cursor=start+(.28 if ed.short else .35)
        for item in chapter["turns"]:
            key=item["line"]; line=story["lines"][key]
            directory=OUT/"voice/v01"/key
            proof=json.loads((directory/"verified.json").read_text(encoding="utf-8"))
            path=directory/"voice.wav"
            expected=next(f["sha256"] for f in proof["files"] if f["path"].endswith("voice.wav"))
            if sha(path)!=expected.lower():
                raise ValueError(f"Voice hash changed: {key}")
            seconds=len(read_voice(path))/SR
            end=cursor+seconds
            turns.append(dict(**item,**line,start=cursor,end=end,voice_path=str(path)))
            captions.extend(timed_captions(line["text"],cursor,seconds,ed.caption[2]-ed.caption[0]-72,ed.size,protected=protected))
            cursor=end+(.22 if ed.short else .31)
        frame_count=math.ceil((turns[-1]["end"]-start+(.42 if ed.short else .60))*FPS)
        current+=frame_count
        chapters.append(dict(id=chapter["id"],title=chapter["title"],start=start,end=current/FPS,frames=frame_count,
                             turns=turns,captions=captions))
    return dict(fps=FPS,frames=current,seconds=current/FPS,chapters=chapters,
                voice={"method":"Gemini TTS","model":"gemini-2.5-flash-preview-tts","female":"Aoede","male":"Charon"})

def state(ch,time):
    turn=next((tr for tr in reversed(ch["turns"]) if time>=tr["start"]),ch["turns"][0])
    age=max(0,time-turn["start"]); dur=turn["end"]-turn["start"]
    views=turn["views"]
    # Cut from the speaker to evidence on the first clause. Tables retain their positions.
    cut=min(4.6,dur*.51)
    pos=int(len(views)>1 and age>=cut)
    view=views[pos]; within=age-(cut if pos else 0)
    segdur=(dur-cut if pos else cut) if len(views)>1 else dur
    count=len(CARDS[view][1]) if view in CARDS else 1
    phase=min(count-1,int(count*max(0,within)/max(.1,segdur)))
    motion=min(61,max(0,int((within+.25)*12))) if view in {"lead","close","question","duoask","guide-person"} else 0
    cap=next((c["text"] for c in ch["captions"] if c["start"]<=time<c["end"]),"")
    return view,turn["line"],motion,phase,cap

def audit(ed,timing,kind,edition):
    folder=OUT/"previews"/kind if edition=="v01" else OUT/"previews"/edition/kind
    folder.mkdir(parents=True,exist_ok=True)
    thumbs=[]; thumb=(225,400) if ed.short else (384,216)
    for ch in timing["chapters"]:
        times={ch["start"]+.1}
        times.update((c["start"]+c["end"])/2 for c in ch["captions"])
        for tr in ch["turns"]:
            for f in (.12,.37,.64,.90):
                times.add(tr["start"]+(tr["end"]-tr["start"])*f)
        seen=set()
        for tm in sorted(times):
            drawing=state(ch,tm)
            frame=ed.frame(ch,*drawing)
            if drawing[0] not in seen:
                seen.add(drawing[0]);frame.save(folder/f"{ch['id']}-{drawing[0]}.jpg",quality=90)
                thumbs.append(ImageOps.contain(frame,thumb))
    cols=4 if ed.short else 5
    sheet=Image.new("RGB",(cols*thumb[0],math.ceil(len(thumbs)/cols)*thumb[1]),PAPER)
    for i,pic in enumerate(thumbs):sheet.paste(pic,(i%cols*thumb[0],i//cols*thumb[1]))
    sheet.save(folder/"contact.jpg",quality=88)
    write(folder/"text-audit.json",list(ed.canvas.audit.values()))
    print(kind,round(timing["seconds"],3),timing["frames"],"frames;",len(ed.canvas.audit),"text layouts",flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("preview","render"))
    parser.add_argument("kind",choices=("short","full"))
    parser.add_argument("--edition", choices=("v01","v02","v03"),default="v01")
    args=parser.parse_args()
    if args.kind=="short" and args.edition=="v03":parser.error("Available short editions: v01, v02")
    named_sources=(args.kind,args.edition) in {("short","v02"),("full","v03")}
    ed=Editor(args.kind,named_sources=named_sources);timing=plan(args.kind,ed,args.edition)
    audit(ed,timing,args.kind,args.edition)
    if args.mode=="preview":return
    release=OUT/"release"/args.edition; release.mkdir(parents=True,exist_ok=True)
    final=release/args.kind
    if final.exists():raise FileExistsError(final)
    staging=Path(tempfile.mkdtemp(prefix=f".{args.kind}-",dir=release))
    mixer=partial(mix,source_path=OUT/"_private"/MUSIC["original"],music_spec=MUSIC)
    encode(ed,timing,args.kind,args.edition,staging,stem="php-security-november",mixer=mixer,sample_state=state)
    staging.rename(final)
if __name__=="__main__":
    main()
