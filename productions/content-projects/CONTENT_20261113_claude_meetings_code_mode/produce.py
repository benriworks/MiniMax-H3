"""Render the vertical and horizontal editions and verify their complete MP4 streams."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import argparse
import json
import math
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps

from prepare import ROOT, HERE, OUT, FIGURES, MOTION, save

sys.path.insert(0, str(ROOT))
from tools.studio.editorial_captions import PROTECTED, caption_pages, timed_captions
from tools.studio.explainer_canvas import Canvas, box, fit, glyph
from tools.studio.longform_audio import plan_dialogue, read_voice
from mix_audio import loudness, mix

FPS = 24
INK, SOFT, PAPER = "#18312E", "#4C605A", "#F6F3EB"
MINT, LINEN, WHITE = "#E3EDE5", "#F6DED0", "#FFFFFF"
GREEN, ORANGE, BORDER = "#0B6154", "#963822", "#D9D4C6"
CAPTION = "#172825"
MAJOR = "出典  Anthropic「Introducing Claude Meetings」2026.11.12"
HELP = "出典  Claude Help Center「Use Claude Meetings」"
CODE = "出典  Claude Code Docs・v2.1.323リリース"
OPENAI = "出典  OpenAI公式発表・Codex変更履歴（11月13日）"
PROTECT = (*PROTECTED, "Claude Meetings", "Claude Code", "Google Meet", "Google Calendar",
           "Code Mode", "Whiteboards", "ホワイトボード", "アクション項目", "Enterprise",
           "JavaScript", "2.1.323", "11月12日", "11月13日", "2027年2月10日", "ChatGPT Wallet")
VOICE = OUT / "voice/local-v01"

BOARD = [("会場を予約", "場所と日程を確保"), ("招待状を送る", "参加者へ案内"), ("名札を印刷", "人数確定後の準備")]
NOTES = [("決まったこと", "まとめと決定事項"), ("次の担当と期限", "アクション項目"), ("会話と資料", "文字起こし・文書・ボード")]
SETUP = [("Google Calendarを接続", "組織でコネクタを有効化"), ("Meetingsで予定を選ぶ", "Google Meetの会議"), ("全員の同意を確認", "Add Claudeで参加者に追加")]
TERMS = [("Team・Enterprise", "Teamは既定オン／Enterpriseは管理者が有効化"),
         ("ベータ対象外の例", "ZDR・HIPAA対応構成・顧客管理の暗号化鍵"),
         ("会議の文書とボード", "2027年2月10日まで無料。接続ツールは利用量に計上")]


class Editor:
    def __init__(self, kind):
        self.short = kind == "short"
        self.w, self.h = (1080, 1920) if self.short else (1920, 1080)
        self.x, self.r = (66, 941) if self.short else (76, 1844)
        self.y = 333 if self.short else 203
        self.b = 1341 if self.short else 826
        self.caption = (52, 1430, 955, 1639) if self.short else (76, 904, 1844, 1040)
        self.size = 49 if self.short else 45
        self.canvas = Canvas()
        self.photos = {}

    def label(self, im, text, rect, size, color=INK, center=False):
        for point in range(size, max(18, size - 16), -1):
            tiles = [glyph(line, point, color) for line in text.split("\n")]
            h = sum(tile.height for tile in tiles) + (len(tiles)-1) * round(point * .26)
            if max(tile.width for tile in tiles) <= rect[2]-rect[0] and h+6 <= rect[3]-rect[1]:
                self.canvas.text(im, text, rect, point, color, center=center)
                return
        raise ValueError(f"Cannot fit {text!r} in {rect}")

    def image(self, im, name, rect):
        if name not in self.photos:
            ext = "png" if name.endswith("-detail") else "webp"
            with Image.open(FIGURES / f"{name}.{ext}") as opened:
                self.photos[name] = opened.convert("RGB")
        x0,y0,x1,y1 = rect
        box(im, rect, WHITE, radius=23, outline=BORDER, width=2)
        fit(im, self.photos[name], (x0+11, y0+11, x1-11, y1-11))

    def cards(self, im, rows, rect, active=0):
        x0,y0,x1,y1 = rect
        gap = 15 if self.short else 13
        height = (y1-y0-gap*(len(rows)-1))//len(rows)
        for i,(title,detail) in enumerate(rows):
            y = y0+i*(height+gap)
            highlight = i == active
            box(im, (x0,y,x1,y+height), MINT if highlight else WHITE,
                radius=24, outline=BORDER, width=2)
            self.label(im, title, (x0+27,y+12,x1-23,y+height//2+9), 44 if self.short else 38,
                       GREEN if highlight else INK)
            self.label(im, detail, (x0+27,y+height//2+6,x1-23,y+height-10),
                       34 if self.short else 30, SOFT)

    def paired(self, im, name, rows, active=0):
        x,y,r,b = self.x,self.y,self.r,self.b
        if self.short:
            photo_h = 570 if len(rows) == 1 else 497
            self.image(im, name, (x,y,r,y+photo_h))
            self.cards(im, rows, (x,y+photo_h+22,r,b), active)
        else:
            photo_w = 1085
            self.image(im, name, (x,y,x+photo_w,b))
            self.cards(im, rows, (x+photo_w+26,y,r,b), active)

    def portrait(self, im, clip, frame, rect):
        path = MOTION / clip / f"{min(61,max(0,frame))+1:03d}.jpg"
        with Image.open(path) as picture:
            crop = picture.crop((16, 207, 464, 657))
            thumb = ImageOps.fit(crop, (rect[2]-rect[0],rect[3]-rect[1]),
                                 Image.Resampling.LANCZOS, centering=(.5,.40))
        mask = Image.new("L", thumb.size)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,thumb.width-1,thumb.height-1), 22, fill=255)
        im.paste(thumb, rect[:2], mask)

    def dialogue(self, im, speaker, motion, paired=False):
        x,y,r,b = self.x,self.y,self.r,self.b
        if self.short:
            self.image(im, "meeting-plan", (x,y,r,y+454))
            self.portrait(im, "female-happy", motion, (x+167,y+482,r-168,b))
            return
        if paired:
            widths = ((x,y,x+673,b), (x+694,y,x+1367,b))
            for voice, rect in zip(("male","female"), widths, strict=True):
                clip = "male-thinking" if voice == "male" else "female-understanding"
                self.portrait(im, clip, motion if speaker == voice else 0, rect)
            self.cards(im, [("会議の結果", "次に動く人が分かる")],
                       (x+1390,y+130,r,b-124), 0)
        else:
            self.image(im, "participant", (x,y,x+1130,b))
            clip = "male-thinking" if speaker == "male" else "female-happy"
            self.portrait(im, clip, motion, (x+1154,y+36,r,b-35))

    def flow(self, im, phase):
        x,r,y,b = self.x,self.r,self.y,self.b
        if self.short:
            self.paired(im, "code-screen", [("Claudeが手順を組む", "探す → 読む → 必要な結果を返す"),
                       ("Code Modeは任意", "Claude Code v2.1.323の実験機能")], phase % 2)
            return
        width = (r-x-96)//3
        for row, label in enumerate(("通常のツール呼び出し", "Code Mode")):
            y0 = y+row*295
            self.label(im, label, (x,y0,r,y0+50), 44, GREEN if row else INK)
            y1 = y0+65
            if row:
                box(im, (x,y1,r,y1+181), MINT, radius=28, outline=BORDER)
                self.label(im, "1つのJavaScript", (x+28,y1+15,r-27,y1+70), 33, GREEN)
            for i, text in enumerate(("ファイルを探す", "中身を読む", "結果をまとめる")):
                left=x+i*(width+48)
                active=phase >= i
                if not row:
                    box(im,(left,y1,left+width,y1+181),WHITE,radius=22,outline=BORDER)
                self.label(im,text,(left+17,y1+72,left+width-17,y1+137),43,
                           GREEN if active else SOFT, True)
                if i<2:
                    self.label(im,"→",(left+width+1,y1+74,left+width+47,y1+138),36,ORANGE,True)

    def visual(self, im, scene, phase, speaker, motion):
        x,y,r,b = self.x,self.y,self.r,self.b
        if scene in {"s-board","f-hook","f-board"}:
            if scene == "f-hook" and phase == 2:
                self.dialogue(im,speaker,motion,paired=True)
            else:
                name = "plan-detail" if phase > 0 and scene != "f-hook" else "meeting-plan"
                self.paired(im, name, BOARD if scene != "f-hook" else
                            [("話し合いの最中","日程をホワイトボードに"),("会議が終わったら","同じ資料から作業を始める")],
                            phase % (2 if scene == "f-hook" else 3))
            return MAJOR
        if scene in {"s-join","f-join"}:
            if not self.short and phase == 0:
                self.dialogue(im,speaker,motion)
            else:
                self.paired(im, "participant-detail" if phase > 1 else "participant",
                            [("Claudeのタイル", "参加者として表示"), ("声・チャットで依頼", "通常は会議チャットに文字で回答")],
                            0 if phase < 2 else 1)
            return MAJOR
        if scene in {"s-notes","f-notes"}:
            self.paired(im, "meeting-page" if phase == 0 else "notes-detail", NOTES, min(phase,2))
            return MAJOR
        if scene in {"s-access","f-setup"}:
            rows = [("Team・Enterprise", "Google Meetでベータを順次展開"), *SETUP[::2]] if self.short else SETUP
            self.paired(im, "help-screen", rows, min(phase,2))
            return HELP
        if scene == "f-privacy":
            if phase == 0:
                self.dialogue(im,speaker,motion,paired=True)
                return None
            self.cards(im, [("参加者全員の同意", "文字起こしを先に説明"), ("外部ゲストの会議", "Teamは既定で許可／Enterpriseは管理者が許可"),
                            ("会議ページの閲覧", "招待された組織内の人が確認。外部ゲストはアクセス不可")],
                       (x,y,r,b), min(phase,2))
            return HELP
        if scene == "f-terms":
            self.cards(im,TERMS,(x,y,r,b),min(phase,2))
            return HELP
        if scene == "f-check":
            self.paired(im,"launch-screen",[("今回の映像は公式例", "このアカウントでの参加は未検証"),
                       ("日本語会議で見る点", "担当・期限・決定事項を原発言と照合")],min(phase,1))
            return MAJOR
        if scene in {"s-code","f-compare"}:
            self.flow(im,phase)
            return CODE
        if scene == "f-code":
            self.paired(im,"code-screen",[("Claude Code v2.1.323","11月12日 UTCの公式リリース"),
                       ("Code Mode", "複数のツール操作をJavaScriptで実行"),
                       ("実験機能", "既定では無効。使う人が有効化")],min(phase,2))
            return CODE
        if scene == "f-code-requirements":
            self.cards(im,[("対話型ターミナル","ネイティブ版 v2.1.323以降。WindowsはGit for Windows"),
                       ("対応モデル","Opus 5.5／Sonnet 5.5／Haiku 5.5／Fable 5.2"),
                       ("使える環境を確認","Desktop・VS Codeパネル・SDK・クラウドは対象外")],
                       (x,y,r,b),min(phase,2))
            return CODE
        if scene == "f-openai":
            self.cards(im,[("ChatGPT Wallet","米国の対象Proで順次。dotsでの支払いを承認"),
                       ("Codex CLI 0.169.0","ターミナルのサイドチャットなどを更新")],
                       (x,y,r,b),min(phase,1))
            return OPENAI
        if scene in {"s-end","f-end"}:
            if not self.short and phase == 0:
                self.dialogue(im,speaker,motion,paired=True)
                return None
            self.paired(im,"meeting-plan",[("会議で決まったこと","日程・担当・次の作業に")],0)
            return MAJOR
        raise ValueError(scene)

    def frame(self, chapter, phase, speaker, motion, caption):
        im = Image.new("RGB",(self.w,self.h),PAPER)
        x,r,y,b=self.x,self.r,self.y,self.b
        draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,self.w,9),fill=GREEN)
        self.label(im,"AIニュース  /  11月13日", (x,72 if self.short else 34,r,124 if self.short else 78),
                   34 if self.short else 32,ORANGE)
        draw.line((x,151 if self.short else 91,r,151 if self.short else 91),fill=BORDER,width=2)
        title=chapter["title"]
        header=(x,177,r,311) if self.short else (x,108,r,185)
        if self.short:
            title="\n".join(caption_pages(title,r-x,60,protected=PROTECT))
        self.label(im,title,header,60 if self.short else 58)
        credit=self.visual(im,chapter["id"],phase,speaker,motion)
        if credit:
            self.label(im,credit,(x,b+10,r,b+59),25 if self.short else 25,SOFT)
        if caption:
            x0,y0,x1,y1=self.caption
            box(im,self.caption,CAPTION,radius=27)
            tiles=[glyph(line,self.size,WHITE) for line in caption.split("\n")]
            gap=round(self.size*.25)
            height=sum(t.height for t in tiles)+gap*(len(tiles)-1)
            assert height <= y1-y0-22 and max(t.width for t in tiles) <= x1-x0-55
            top=(y0+y1-height)//2
            for tile in tiles:
                im.paste(tile,((x0+x1-tile.width)//2,top),tile)
                top+=tile.height+gap
        return im


def plan(kind,editor):
    story=json.loads((HERE/"story-v01.json").read_text(encoding="utf-8"))
    scenes=story[kind]
    for scene in scenes:
        duration=sum(len(read_voice(VOICE/scene["id"]/f"turn-{index:02d}"/"voice.wav"))/24000
                     for index in range(len(scene["turns"])))
        scene["target_seconds"]=min(scene["target_seconds"],duration+(1.35 if kind=="short" else 3.1))
        scene["tail_seconds"] = .40 if kind=="short" else .54
        scene["pause_mode"]="after_answer"
    timing=plan_dialogue(scenes,VOICE,FPS)
    for chapter in timing["chapters"]:
        chapter["captions"] = [
            cue for turn in chapter["turns"] for cue in timed_captions(
                turn["text"],turn["start"],turn["end"]-turn["start"],
                editor.caption[2]-editor.caption[0]-75,editor.size,protected=PROTECT)]
    return timing


def sample(chapter,t):
    turn=chapter["turns"][0]
    for item in chapter["turns"]:
        if item["start"] <= t:
            turn=item
    turns=chapter["turns"]
    if len(turns)==1:
        a=turn["start"]
        h=turn["end"]-a
    else:
        a=turns[-1]["start"]
        h=turns[-1]["end"]-a
    phase = 0 if t < a+.23*h else 1 if t < a+.60*h else 2
    if chapter["id"]=="f-hook":
        phase=0 if t<chapter["start"]+2.8 else 2 if t<a+1.4 else 1
    if chapter["id"] in {"f-join","f-privacy","f-end"} and len(turns)>1:
        phase=0 if t<a else 1 if t<a+.54*h else 2
    motion=min(61, max(0,int((t-turn["start"])*12)))
    if not ((chapter["id"]=="f-hook" and phase==2) or
            (chapter["id"] in {"f-join","f-privacy","f-end"} and phase==0)):
        motion=0
    caption=next((x["text"] for x in chapter["captions"] if x["start"]<=t<x["end"]),"")
    return phase,turn["speaker"],motion,caption


def review_frames(editor,timing,folder,video=None):
    folder.mkdir(parents=True,exist_ok=True)
    size = (232, 412) if editor.short else (462, 260)
    review=[]
    for chapter in timing["chapters"]:
        points=[(float(chapter["start"])+.12,"open"),
                ((chapter["turns"][-1]["start"]+chapter["turns"][-1]["end"])/2,"answer")]
        for time,label in points:
            path=folder/f"{chapter['id']}-{label}.jpg"
            if video:
                width = 540 if editor.short else 960
                subprocess.run(["ffmpeg","-v","error","-nostdin","-y","-ss",f"{time:.5f}","-i",str(video),
                                "-frames:v","1","-vf",f"scale={width}:-2",str(path)],check=True)
                with Image.open(path) as image:
                    review.append(ImageOps.contain(image,size))
            else:
                image=editor.frame(chapter,*sample(chapter,time))
                image.save(path,quality=94)
                review.append(ImageOps.contain(image,size))
        # Verify every caption and deliberate composition even if it isn't on the contact sheet.
        if not video:
            for cue in chapter["captions"]:
                editor.frame(chapter,*sample(chapter,(cue["start"]+cue["end"])/2))
    columns=4 if editor.short else 3
    sheet=Image.new("RGB",(columns*size[0],size[1]*math.ceil(len(review)/columns)),PAPER)
    for i,image in enumerate(review):
        sheet.paste(image,((i%columns)*size[0],(i//columns)*size[1]))
    sheet.save(folder/"contact.jpg",quality=89)


def timestamp(seconds):
    ms=round(seconds*1000)
    return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"


def encode(editor,timing,kind,folder):
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/f"claude-1113-{kind}-v01.mp4"
    if output.exists():
        raise FileExistsError("Use a new edition to preserve the earlier MP4")
    audio, receipt=mix(timing,folder/"work")
    args=["ffmpeg","-v","error","-nostdin","-n","-f","image2pipe","-framerate",str(FPS),
          "-c:v","mjpeg","-i","pipe:0","-i",str(audio),"-map","0:v","-map","1:a",
          "-vf","scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p",
          "-c:v","libx264","-preset","veryfast","-crf","18","-threads","4","-g","48",
          "-color_range","tv","-colorspace","bt709","-color_primaries","bt709","-color_trc","bt709",
          "-c:a","aac","-b:a","160k","-ar","48000","-t",f"{timing['seconds']:.8f}",
          "-movflags","+faststart",str(output)]
    with subprocess.Popen(args,stdin=subprocess.PIPE) as proc:
        try:
            for chapter in timing["chapters"]:
                cache={}
                for i in range(chapter["frames"]):
                    state=sample(chapter,chapter["start"]+(i+.5)/FPS)
                    if state not in cache:
                        data=BytesIO()
                        editor.frame(chapter,*state).save(data,format="JPEG",quality=91)
                        cache[state]=data.getvalue()
                    proc.stdin.write(cache[state])
                print(chapter["id"],flush=True)
        finally:
            proc.stdin.close()
        if proc.wait():
            raise RuntimeError("MP4 encoding failed")
    subprocess.run(["ffmpeg","-v","error","-nostdin","-xerror","-i",str(output),"-f","null","-"],check=True)
    probe=json.loads(subprocess.run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(output)],
                                    capture_output=True,check=True).stdout)
    picture,sound=probe["streams"]
    assert (picture["width"],picture["height"],picture["codec_name"],picture["pix_fmt"],picture["color_space"]) == (
        editor.w,editor.h,"h264","yuv420p","bt709")
    assert int(picture["nb_frames"])==timing["frames"] and sound["channels"]==2 and sound["codec_name"]=="aac"
    assert abs(float(probe["format"]["duration"])-timing["seconds"]) < .08
    measured=loudness(output)
    assert -17 <= float(measured["input_i"]) <= -13 and float(measured["input_tp"]) < -.9
    blob=output.read_bytes()
    assert 0 < blob.find(b"moov") < blob.find(b"mdat")
    captions=[cue for chapter in timing["chapters"] for cue in chapter["captions"]]
    srt="\n\n".join(f"{i}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n{c['text']}"
                    for i,c in enumerate(captions,start=1))
    output.with_suffix(".srt").write_text(srt+"\n",encoding="utf-8")
    save(folder/"timeline.json",timing)
    review_frames(editor,timing,folder/"decoded-review",video=output)
    record=dict(file=output.name,bytes=len(blob),sha256=sha256(blob).hexdigest(),
                duration=timing["seconds"],resolution=[editor.w,editor.h],frames=timing["frames"],
                captions=len(captions),integrated_lufs=float(measured["input_i"]),
                true_peak_dbtp=float(measured["input_tp"]),bgm=receipt,
                full_decode="passed",caption_layout="passed",human_listening="pending",
                video_acceptance="pending",publication="unpublished")
    save(folder/"qc.json", record)
    print(json.dumps(record,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["preview","render"])
    parser.add_argument("kind",choices=["short","full"])
    args=parser.parse_args()
    editor=Editor(args.kind)
    timing=plan(args.kind,editor)
    if args.mode=="preview":
        review_frames(editor,timing,OUT/"previews/v01"/args.kind)
        print(f"{args.kind} {timing['seconds']:.2f}s")
    else:
        encode(editor,timing,args.kind,OUT/"release/v01"/args.kind)


if __name__=="__main__":
    main()
