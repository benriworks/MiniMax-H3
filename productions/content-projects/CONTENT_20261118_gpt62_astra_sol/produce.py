"""Compose the GPT-6.2 review cuts from timed PCM, presenter motion and evidence."""
import argparse
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from tools.studio.editorial_captions import PROTECTED, timed_captions
from tools.studio.explainer_canvas import Canvas, box, fit
from tools.studio.longform_audio import assemble_audio, plan_dialogue

FPS = 24
PROTECT = (*PROTECTED, "GPT-6.2 Astra", "GPT-6.2 Sol", "GPT-6.2",
           "ChatGPT Work", "100万トークン", "OpenAI", "Astra", "Sol")
PAPER, LIGHT, PALE = "#0D1929", "#F4F8FC", "#B8CBDF"
TEAL, GOLD = "#6DE4D3", "#FFD895"
TEAL_BG, GOLD_BG, PANEL, LINE = "#143B44", "#473524", "#142437", "#324C64"
MOTIONS = {
    "male-thinking": "b284c50afa0eb95cb81d9786f47d6ae4bd9670a27da60b56d6107af8eb1f7799",
    "female-understanding": "df4967a3ab73e2eb598e020fd8959ed7756fdb5e4a24a64424dabd1f42897126",
    "female-happy": "3fd4f5b669f62adeaa3d19d5c4b2e5b1b5eb81f53817e91a5f989d9fb0333956",
}
CROPS = {
    "app-model-picker": ("work-picker.png", (1485, 870, 1750, 1030)),
    "app-composer": ("work-picker.png", (1058, 867, 1840, 1252)),
    "slide-template": ("official-slides.png", (985, 517, 1579, 931)),
    "slide-comparison": ("official-slide-results.png", (570, 129, 1960, 553)),
    "slide-astra-detail": ("official-slide-results.png", (1283, 132, 1952, 553)),
}
STEPS = {
    "sol": [("変更箇所を伝える", "予約ボタンの文言"),
            ("差分を確認する", "小さな修正・レビュー"),
            ("文書の下書きにも", "メールや説明文")],
    "astra": [("原因を追う", "予約の記録と通知処理"),
              ("修正する", "問題がある箇所を直す"),
              ("影響をテストする", "予約と通知を確認")],
    "request": [("再現手順", "何をすると起きる？"), ("確認範囲", "どの機能まで見る？"),
                ("検証結果", "実施したテスト・残った点")],
    "access": [("ChatGPT Work", "通常のChatからWorkへ"),
               ("Codex", "モデル選択から切り替え"), ("利用条件", "プランと組織設定を確認")],
}


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, encoding="utf-8")


def digest(path):
    with path.open("rb") as file:
        return sha256(file.read()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def prepare(media, source):
    figures = media / "captures/figures"
    figures.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, (filename, bounds) in CROPS.items():
        original = media / "captures/original" / filename
        destination = figures / (name + ".webp")
        with Image.open(original) as im:
            size = list(im.size)
            assert bounds[2] <= size[0] and bounds[3] <= size[1]
            cropped = im.convert("RGB").crop(bounds)
            cropped.save(destination, quality=90)
        manifest.append(dict(asset=name, original=filename, original_pixels=size,
                             original_sha256=digest(original), original_bytes=original.stat().st_size,
                             crop=list(bounds), pixels=list(cropped.size), bytes=destination.stat().st_size,
                             sha256=digest(destination),
                             path=destination.relative_to(media).as_posix()))
    save(figures / "manifest.json", manifest)
    for name, expected in MOTIONS.items():
        clip = source / (name + ".mp4")
        if digest(clip) != expected:
            raise ValueError(f"Presenter source changed: {clip.name}")
        out = media / "motion" / name
        out.mkdir(parents=True, exist_ok=True)
        if not list(out.glob("*.jpg")):
            run("ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(clip), "-an",
                "-vf", "fps=12,scale=480:-2", "-q:v", "3", str(out / "%03d.jpg"))
        if len(list(out.glob("*.jpg"))) != 62:
            raise ValueError(f"Check extracted presenter frames: {name}")
    save(media / "motion/manifest.json", MOTIONS)


class Editor:
    def __init__(self, kind, media, story):
        self.media, self.story = media, story
        self.short = kind == "short"
        self.size = (1080, 1920) if self.short else (1920, 1080)
        self.left, self.right = (72, 952) if self.short else (104, 1816)
        self.top, self.bottom = (368, 1330) if self.short else (235, 820)
        self.caption = (72, 1425, 952, 1640) if self.short else (104, 880, 1816, 1012)
        self.caption_font = 49 if self.short else 45
        self.canvas = Canvas()
        self.bg = Image.new("RGB", self.size)
        draw = ImageDraw.Draw(self.bg)
        for y in range(self.size[1]):
            t = y / self.size[1]
            c = tuple(round(a + (b - a) * t) for a, b in zip((19, 35, 56), (9, 18, 30)))
            draw.line((0, y, self.size[0], y), fill=c)

    def message(self, im, value, rect, size, color=LIGHT, center=False):
        self.canvas.text(im, value, rect, size, color, center=center)

    @lru_cache(maxsize=14)
    def base(self, index, phase):
        scene = self.story[index]
        visual = scene["visual"]
        im = self.bg.copy()
        x, r, y, b = self.left, self.right, self.top, self.bottom
        box(im, (x, 92, x + 60, 100) if self.short else (x, 51, x + 60, 58), TEAL, 4)
        if visual != "hero":
            self.message(im, "GPT-6.2  /  Astra & Sol",
                         (x, 118, r, 177) if self.short else (x, 70, r, 116), 32, PALE)
        self.message(im, scene["title"], (x, 192, r, 317) if self.short else (x, 127, r, 213),
                     64 if self.short else 64)
        if visual in {"hero", "end"}:
            self.model_choices(im)
        elif visual in STEPS:
            self.steps(im, visual, phase)
        elif visual in {"picker", "template", "slides", "slide-detail"}:
            self.evidence(im, visual, phase)
        elif visual == "price":
            self.prices(im, index)
        return im

    def model_choices(self, im):
        x, r, y, b = self.left, self.right, self.top, self.bottom
        if self.short:
            rects = [(x, y, r, y+150), (x, y+170, r, y+320)]
        else:
            mid = (x+r)//2
            rects = [(x, y, mid-10, y+136), (mid+10, y, r, y+136)]
        for (a, c, d, e), (name, use, tint, accent) in zip(
            rects, [("Sol", "ふだんの仕事", TEAL_BG, TEAL),
                    ("Astra", "難しい仕事", GOLD_BG, GOLD)], strict=True
        ):
            box(im, (a, c, d, e), tint, 25)
            self.message(im, name, (a+36, c+12, a+266, e-15), 67, accent)
            self.message(im, use, (a+271, c+13, d-28, e-16), 48)

    def steps(self, im, visual, phase):
        x, r, y, b = self.left, self.right, self.top, self.bottom
        tint, accent = (GOLD_BG, GOLD) if visual == "astra" else (TEAL_BG, TEAL)
        if self.short:
            layout = [(x, y+30+offset*219, r, y+30+offset*219+188) for offset in range(3)]
        else:
            gap = 24
            width = (r-x-2*gap)//3
            layout = [(x+offset*(width+gap), y+85, x+offset*(width+gap)+width, b-85)
                      for offset in range(3)]
        for index, ((a, c, d, e), (heading, detail)) in enumerate(zip(layout, STEPS[visual], strict=True)):
            active = index == phase
            box(im, (a, c, d, e), tint if active else PANEL, 26, accent if active else LINE, 2)
            if self.short:
                self.message(im, heading, (a+30, c+18, d-22, c+81), 52, accent if active else LIGHT)
                self.message(im, detail, (a+32, c+88, d-22, e-15), 38, PALE)
            else:
                self.message(im, heading, (a+34, c+100, d-28, c+169), 50, accent if active else LIGHT)
                self.message(im, detail, (a+35, c+173, d-26, c+245), 36, PALE)

    @lru_cache(maxsize=8)
    def figure(self, name):
        with Image.open(self.media / "captures/figures" / (name + ".webp")) as im:
            return im.convert("RGB")

    def evidence(self, im, visual, phase):
        x, r, y, b = self.left, self.right, self.top, self.bottom
        if visual == "picker":
            items = (("app-composer", "入力欄のモデル表示を開く"),
                     ("app-model-picker", "モデルを選択 → Sol／Astra"))
            if self.short:
                name, detail = items[phase > 0]
                fit(im, self.figure(name), (x, y+86, r, y+695))
                self.message(im, detail, (x, y+711, r, y+790), 44, LIGHT, True)
            else:
                middle = x+1032
                for (name, detail), (left, right) in zip(items, ((x,middle-22),(middle+24,r)), strict=True):
                    fit(im, self.figure(name), (left, y+30, right, b-120))
                    self.message(im, detail, (left, b-108, right, b-52), 35, LIGHT, True)
            credit = "ユーザーPCのCodex画面  /  2026.11.18"
        else:
            figures = {"template": "slide-template", "slides": "slide-comparison",
                       "slide-detail": "slide-astra-detail"}
            notes = {"template": "見本の画像に合わせ、最新状況を1枚にまとめる",
                     "slides": "左は GPT-6 Astra　／　右は GPT-6.2 Astra",
                     "slide-detail": "2店舗で試験導入　／　次の作業・担当・日付"}
            fit(im, self.figure(figures[visual]), (x, y, r, b-91))
            self.message(im, notes[visual], (x, b-91, r, b-39), 38, LIGHT, True)
            credit = "出典  OpenAI「Introducing GPT-6.2 Astra and Sol」"
        self.message(im, credit, (x, b-25, r, b+24), 26, PALE, True)

    def prices(self, im, index):
        x, r, y, b = self.left, self.right, self.top, self.bottom
        if self.story[index]["id"] == "f14":
            self.message(im, "同じトークン量で比較", (x, y, r, y+70), 42, PALE)
            for i, (name, factor, tint, accent) in enumerate(
                [("Sol", "1×", TEAL_BG, TEAL), ("Astra", "4×", GOLD_BG, GOLD)]
            ):
                top = y + 110 + i*140
                box(im, (x, top, r, top+115), PANEL, 23)
                box(im, (x, top, x+(r-x)*(i*3+1)//4, top+115), tint, 23)
                self.message(im, name, (x+38, top, x+275, top+115), 52, accent)
                self.message(im, factor, (r-230, top, r-37, top+115), 58, accent, True)
            self.message(im, "実際の費用は、入力・出力などの使用量で変わる。", (x, b-104, r, b-23), 39, PALE)
            return
        self.message(im, "米ドル / 100万トークン・標準API", (x, y, r, y+64), 40, PALE)
        rows = [("Sol", "$2", "$0.10", "$10", TEAL, TEAL_BG),
                ("Astra", "$8", "$0.40", "$40", GOLD, GOLD_BG)]
        cols = (x+375, x+770, x+1245)
        for left, label in zip(cols, ("入力", "キャッシュ入力", "出力"), strict=True):
            self.message(im, label, (left, y+80, left+342, y+156), 42, PALE, True)
        for i, (name, *values, accent, tint) in enumerate(rows):
            top = y+170+i*149
            box(im, (x, top, r, top+130), tint, 24)
            self.message(im, name, (x+38, top+9, x+352, top+121), 60, accent)
            for left, value in zip(cols, values, strict=True):
                self.message(im, value, (left, top+10, left+342, top+119), 59, LIGHT, True)
        self.message(im, "出典  OpenAI公式発表  /  2026.11.18確認", (x, b-82, r, b-20), 34, PALE)

    @lru_cache(maxsize=96)
    def portrait(self, motion, number, width, height):
        path = self.media / "motion" / motion / f"{number:03}.jpg"
        with Image.open(path) as picture:
            crop = picture.crop((0, 170, 480, 660))
            return ImageOps.fit(crop, (width, height), Image.Resampling.BICUBIC, centering=(.5, .11))

    def presenters(self, im, scene, elapsed):
        x, r, y, b = self.left, self.right, self.top, self.bottom
        visual = scene["visual"]
        speaker = scene["speaker"]
        if visual == "duo" and self.short:
            width = 754
            height = 710
            a = (x+r-width)//2
            c = y+56
            box(im, (a, c, a+width, c+height), TEAL, 23)
            frame = min(62, int(elapsed*12) + 1)
            portrait = self.portrait("male-thinking", frame, width-6, height-6)
            im.paste(portrait, (a+3, c+3), portrait_mask(width-6, height-6))
            return
        if visual == "duo":
            rect = (x, y+18, r, b-22)
        elif self.short:
            rect = (x, y+380, r, b)
        else:
            rect = (x, y+175, r, b+12)
        a, c, d, e = rect
        gap = 20
        width = (d-a-gap)//2
        height = min(e-c, width)
        top = c + (e-c-height)//2
        for i, person in enumerate(("male", "female")):
            left = a+i*(width+gap)
            active = person == speaker
            accent = TEAL if person == "male" else GOLD
            motion = ("male-thinking" if person == "male" else
                      ("female-happy" if active and visual == "end" else "female-understanding"))
            # Brief activity is played once per cut. Hold the last stable pose for reading.
            number = min(62, int(elapsed*12) + 1) if active else min(27, int(elapsed*6) + 1)
            box(im, (left, top, left+width, top+height), accent if active else LINE, 23)
            image = self.portrait(motion, number, width-6, height-6)
            im.paste(image, (left+3, top+3), portrait_mask(width-6, height-6))

    def frame(self, index, elapsed, fraction, caption):
        scene = self.story[index]
        visual = scene["visual"]
        phase = min(2, int(fraction * 3)) if visual in STEPS else int(fraction >= .46)
        im = self.base(index, phase).copy()
        if visual in {"hero", "duo", "end"}:
            self.presenters(im, scene, elapsed)
        if caption:
            a, b, c, d = self.caption
            box(im, self.caption, "#07111F", 27, LINE, 2)
            lines = caption.split("\n")
            center_top = b+(d-b-2*self.caption_font-18)//2 if len(lines) == 2 else b
            self.message(im, caption, (a+25, center_top, c-25, d), self.caption_font, LIGHT, True)
        return im


@lru_cache(maxsize=16)
def portrait_mask(width, height):
    mask = Image.new("L", (width, height))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width-1, height-1), 20, fill=255)
    return mask


def timeline(story, voice_root, editor):
    chapters = [dict(id=s["id"], title=s["title"], target_seconds=s["target_seconds"],
                     tail_seconds=(1.35 if s["visual"] == "end" else .30),
                     turns=[dict(speaker=s["speaker"], text=s["display"])]) for s in story]
    plan = plan_dialogue(chapters, voice_root, fps=FPS)
    for chapter, scene in zip(plan["chapters"], story, strict=True):
        turn = chapter["turns"][0]
        chapter["captions"] = timed_captions(scene["display"], turn["start"],
            turn["end"]-turn["start"], editor.caption[2]-editor.caption[0]-60,
            editor.caption_font, protected=PROTECT)
    return plan


def caption_at(chapter, point):
    return next((p["text"] for p in chapter["captions"]
                 if p["start"] <= point < p["end"]), "")


def srt_time(seconds):
    millis = round(seconds*1000)
    minutes, millis = divmod(millis, 60000)
    hours, minutes = divmod(minutes, 60)
    seconds, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def loudness(path):
    output = run("ffmpeg", "-nostdin", "-hide_banner", "-i", str(path),
                 "-vn", "-af", "loudnorm=I=-16:TP=-1.65:LRA=10:print_format=json",
                 "-f", "null", "-").stderr
    return json.loads(re.findall(r"\{[^{}]+\}", output)[-1])


def render(kind, version, editor, plan, folder):
    folder.mkdir(parents=True, exist_ok=False)
    audio = assemble_audio(plan, folder, music_style="bright")
    premaster = folder / "mix-premaster.wav"
    measured = loudness(premaster)
    normal = ("loudnorm=I=-16:TP=-1.65:LRA=10:linear=true:"
              f"measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:"
              f"measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:"
              f"offset={measured['target_offset']}")
    mix = folder / "mix-normalized.wav"
    run("ffmpeg", "-nostdin", "-v", "error", "-n", "-i", str(premaster),
        "-af", normal, "-ar", "48000", str(mix))
    path = folder / f"gpt62-astra-sol-{kind}-{version}.mp4"
    partial = folder / f".{path.name}"
    w, h = editor.size
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-n", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(FPS), "-i", "pipe:0", "-i", str(mix),
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", "6",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(partial)]
    with subprocess.Popen(cmd, stdin=subprocess.PIPE) as encoder:
        try:
            for i, chapter in enumerate(plan["chapters"]):
                for frame in range(chapter["frames"]):
                    elapsed = frame/FPS
                    point = chapter["start"] + elapsed
                    image = editor.frame(i, elapsed, frame/chapter["frames"], caption_at(chapter, point))
                    encoder.stdin.write(image.tobytes())
                print(kind, chapter["id"], flush=True)
        finally:
            encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("FFmpeg render failed")
    run("ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(partial), "-f", "null", "-")
    final_loudness = loudness(partial)
    assert -18 <= float(final_loudness["input_i"]) <= -14 and float(final_loudness["input_tp"]) <= -1
    partial.rename(path)
    subtitles = [p for c in plan["chapters"] for p in c["captions"]]
    srt = "\n\n".join(f"{index}\n{srt_time(p['start'])} --> {srt_time(p['end'])}\n" +
                        p["text"] for index, p in enumerate(subtitles, 1))
    (folder / "captions.srt").write_text(srt + "\n", encoding="utf-8")
    for chapter in plan["chapters"]:
        for turn in chapter["turns"]:
            turn["voice_path"] = Path(turn["voice_path"]).relative_to(folder.parents[2]).as_posix()
    save(folder / "timeline.json", plan)
    save(folder / "verification.json", dict(video=path.name, pixels=editor.size, fps=FPS,
        seconds=plan["seconds"], frames=plan["frames"], bytes=path.stat().st_size,
        sha256=digest(path), full_decode=True, caption_states=len(subtitles),
        measured_text_states=len(editor.canvas.audit), final_lufs=float(final_loudness["input_i"]),
        final_dbtp=float(final_loudness["input_tp"]), audio=audio, user_approved=False, published=False))
    print(path, flush=True)


def preview(editor, plan, folder):
    folder.mkdir(parents=True, exist_ok=True)
    tiles = []
    for index, chapter in enumerate(plan["chapters"]):
        for caption in chapter["captions"]:
            elapsed = (caption["start"]+caption["end"])/2 - chapter["start"]
            editor.frame(index, elapsed, elapsed/(chapter["end"]-chapter["start"]), caption["text"])
        elapsed = (chapter["end"]-chapter["start"])*.58
        im = editor.frame(index, elapsed, .58, caption_at(chapter, chapter["start"]+elapsed))
        im.save(folder / (chapter["id"] + ".jpg"), quality=91)
        im.thumbnail((400, 365))
        tiles.append(im)
    width, height = tiles[0].size
    columns = 4
    sheet = Image.new("RGB", (columns*width, ((len(tiles)+columns-1)//columns)*height), PAPER)
    for index, tile in enumerate(tiles):
        sheet.paste(tile, (index%columns*width, index//columns*height))
    sheet.save(folder / "contact-sheet.jpg", quality=92)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preview", "render", "prepare"))
    parser.add_argument("--kind", choices=("short", "full"))
    parser.add_argument("--version", choices=("v01", "v02", "v03"), default="v01")
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--motion-source", type=Path)
    args = parser.parse_args()
    media = args.media.resolve()
    if args.mode == "prepare":
        prepare(media, args.motion_source)
        return
    if not args.kind:
        parser.error("--kind is required to preview or render")
    story = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))[args.kind]
    if args.version != "v01":
        if args.kind != "short":
            parser.error("The revision is for the short cut")
        edited = json.loads((HERE / f"short-{args.version}.json").read_text(encoding="utf-8"))
        story = [scene | {"display": edited[scene["id"]]["display"]}
                 if scene["id"] in edited else scene for scene in story]
    editor = Editor(args.kind, media, story)
    plan = timeline(story, media / "voice" / ("selected-" + args.version), editor)
    if args.mode == "preview":
        preview(editor, plan, media / "preflight" / args.version / args.kind)
    else:
        render(args.kind, args.version, editor, plan, media / "release" / args.version / args.kind)


if __name__ == "__main__":
    main()
