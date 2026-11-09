"""Assemble the two Fable 5.2 review videos from official captures and verified dialogue."""
import argparse
from bisect import bisect_right
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
OUT = ROOT / "outputs/content-projects" / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.editorial_captions import PROTECTED, phrase_lines, timed_captions
from tools.studio.explainer_canvas import Canvas, box, glyph
from tools.studio.longform_audio import assemble_audio, plan_dialogue
from narrate import PRONUNCIATION

FPS = 24
PAPER, LIGHT, INK = "#F4F1E8", "#FFFCF5", "#162D31"
DARK, MUTE, ACCENT = "#142F31", "#4F6262", "#AE492E"
TEAL, GOLD, PALE = "#096A60", "#F6CC96", "#DDECE2"
MYTHOS = "#614B77"
QUOTE = "引用  Anthropic公式発表 ／ 2026年11月9日"
TERMS = PROTECTED + tuple(PRONUNCIATION) + ("アプリとClaude Code", "標準API単価", "フェルマーの最終定理")
CLIPS = ("male-thinking", "female-understanding", "male-happy", "female-happy")
CREATION = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", creationflags=CREATION)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def prepare_motion(source):
    motions = OUT / "motion"
    motions.mkdir(parents=True, exist_ok=True)
    proof = {x["name"]: x for x in read(source / "motion-provenance.json")}
    manifest = {}
    for clip in CLIPS:
        src = source / "assets" / (clip+".mp4")
        if digest(src) != proof[clip]["sha256"]:
            raise ValueError(f"Motion source hash mismatch: {clip}")
        target = motions / src.name
        if not target.exists():
            shutil.copyfile(src, target)
        if digest(target) != proof[clip]["sha256"]:
            raise ValueError(f"Motion copy hash mismatch: {clip}")
        cache = motions / clip
        cache.mkdir(exist_ok=True)
        receipt = cache / "complete.json"
        if not receipt.exists():
            run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(target), "-an",
                 "-vf", "fps=12,scale=480:-2", "-q:v", "2", str(cache / "%03d.jpg")])
            save(receipt, dict(source_sha256=digest(target), frames=len(list(cache.glob("*.jpg")))))
        manifest[clip] = dict(read(receipt), source=proof[clip]["path"])
    save(motions / "manifest.json", manifest)


def make_plan(story, kind):
    scenes = story[kind]
    voice_root = OUT / "voice/v01"
    minimum = []
    for scene in scenes:
        minimum.append(dict(id=scene["id"], title=scene["visual"], turns=scene["turns"],
                            target_seconds=scene["min"], tail_seconds=.4, pause_mode="after_answer"))
        for index in range(len(scene["turns"])):
            audio = voice_root / scene["id"] / f"turn-{index:02d}" / "voice.wav"
            proof = read(audio.with_name("verified.json"))
            expected = next(f["sha256"] for f in proof["files"] if f["path"].endswith("/voice.wav"))
            if digest(audio).lower() != expected.lower():
                raise ValueError(f"Frozen voice was changed: {audio}")
    plan = plan_dialogue(minimum, voice_root, fps=FPS)
    cue_width, size = (822, 50) if kind == "short" else (1340, 49)
    for scene, chapter in zip(scenes, plan["chapters"], strict=True):
        chapter["scene"] = scene["id"]
        chapter["visual"] = scene["visual"]
        if "graph" in scene:
            chapter["graph"] = scene["graph"]
        cues = []
        for turn in chapter["turns"]:
            cues += timed_captions(turn["text"], turn["start"], turn["end"]-turn["start"],
                                   cue_width, size, protected=TERMS)
            turn["voice_path"] = str(Path(turn["voice_path"]).resolve())
        chapter["cues"] = cues
    plan["kind"] = kind
    plan["revision"] = story["version"]
    return plan


class Editor:
    def __init__(self, story, kind):
        self.kind = kind
        self.story = story
        self.short = kind == "short"
        self.size = (1080, 1920) if self.short else (1920, 1080)
        self.canvas = Canvas()
        self.caps = OUT / "captures-v02/quotes"
        self.frames = {clip: sorted((OUT/"motion"/clip).glob("*.jpg")) for clip in CLIPS}
        if any(not frames for frames in self.frames.values()):
            raise ValueError("Verified presenter motion has not been prepared")
        self.quotes = {}

    def label(self, im, value, rect, size, color=INK, *, center=False, wrap=False):
        width = rect[2]-rect[0]
        for px in range(size, max(21, size-27), -1):
            try:
                lines = phrase_lines(value, width, px, protected=TERMS) if wrap else value.split("\n")
            except ValueError:
                continue
            tiles = [glyph(line, px, color) for line in lines]
            if max(tile.width for tile in tiles) <= width and (
                    sum(tile.height for tile in tiles)+round(px*.26)*(len(tiles)-1)+6 <= rect[3]-rect[1]):
                self.canvas.text(im, "\n".join(lines), rect, px, color, center=center)
                return
        raise ValueError(f"Text overflows layout: {value!r} in {rect}")

    @lru_cache(maxsize=48)
    def asset(self, name, width, height):
        paths = {"demo-input": OUT/"demo/fixture.png", "demo-output": OUT/"demo/output-excerpt.png"}
        path = paths.get(name, self.caps/(name+".png"))
        with Image.open(path) as image:
            image = image.convert("RGB")
            if name == "release-header":
                w, h = image.size
                image = image.crop((round(w*.21), round(h*.235), round(w*.79), round(h*.48)))
            return ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)

    def picture(self, im, name, rect):
        left, top, right, bottom = rect
        tile = self.asset(name, right-left, bottom-top)
        x, y = left+(right-left-tile.width)//2, top+(bottom-top-tile.height)//2
        im.paste(tile, (x, y))
        return (x, y, x+tile.width, y+tile.height)

    def header(self, im, label="CLAUDE  /  FABLE 5.2", *, dark=False, tag=None):
        fg = GOLD if dark else TEAL
        if self.short:
            self.label(im, label, (68, 131, 750, 188), 31, fg)
            if tag:
                self.label(im, tag, (750, 131, 948, 188), 31, fg, center=True)
            ImageDraw.Draw(im).line((68, 201, 948, 201), fill=fg, width=2)
        else:
            self.label(im, label, (84, 35, 1420, 85), 26, fg)
            if tag:
                self.label(im, tag, (1470, 35, 1836, 85), 26, fg, center=True)
            ImageDraw.Draw(im).line((84, 92, 1836, 92), fill=fg, width=2)

    def title(self, im, value, *, color=INK):
        rect = (68, 226, 948, 389) if self.short else (84, 111, 1836, 197)
        self.label(im, value, rect, 63 if self.short else 65, color, wrap=True)

    def source(self, im, text):
        rect = (68, 1371, 948, 1421) if self.short else (87, 851, 1834, 895)
        self.label(im, text, rect, 29 if self.short else 25, MUTE)

    def graph(self, im, scene):
        data = self.story["graphs"][scene["graph"]]
        color = MYTHOS if data["asset"] in {"cve", "audit"} else TEAL
        tag = f"{data['number']:02d} / 09"
        self.header(im, "公式グラフ  ／  "+data["section"], tag=tag)
        self.title(im, data["title"])
        if self.short:
            box(im, (57, 385, 958, 1093), LIGHT, 24)
            rect = self.picture(im, data["asset"], (67, 398, 948, 1084))
            self.label(im, data["value"], (72, 1102, 940, 1232), 111, color)
            comparison = {
                "wandr": "Opus 5.5の最高スコア相当",
                "hle": "Opus 5.5の最高スコア相当",
            }
            self.label(im, comparison.get(data["asset"], data["condition"]), (74, 1242, 942, 1355), 39, wrap=True)
        else:
            box(im, (84, 204, 1086, 845), LIGHT, 26)
            rect = self.picture(im, data["asset"], (94, 206, 1076, 843))
            self.label(im, data["label"], (1142, 244, 1828, 310), 42, color, wrap=True)
            self.label(im, data["value"], (1136, 332, 1828, 488), 123, color)
            self.label(im, data["condition"], (1143, 501, 1830, 600), 43, wrap=True)
            ImageDraw.Draw(im).line((1142, 616, 1829, 616), fill="#C4D3CB", width=2)
            self.label(im, data["detail"], (1143, 642, 1830, 825), 36, MUTE, wrap=True)
        self.source(im, QUOTE)
        self.quotes[scene["id"]] = dict(asset=data["asset"], frame_rect=rect)

    def table(self, im, scene):
        self.header(im, "公式比較表", tag=f"{scene['part']} / 3")
        self.title(im, scene["title"])
        asset = f"benchmark-table-{scene['part']}"
        self.picture(im, asset, (82, 215, 1372, 844))
        self.label(im, scene["value"], (1411, 333, 1835, 490), 64, TEAL, wrap=True)
        self.label(im, scene["condition"], (1416, 532, 1834, 807), 37, MUTE, wrap=True)
        self.source(im, QUOTE)

    def price(self, im):
        self.header(im, "API単価  ／  100万トークンあたり")
        self.title(im, "入力も出力も2割減")
        rects = [(68, 450, 948, 787), (68, 820, 948, 1157)] if self.short else [
            (84, 252, 934, 699), (980, 252, 1836, 699)]
        for (x, y, right, bottom), label, before, after in zip(
                rects, ("入力", "出力"), ("$10", "$50"), ("$8", "$40"), strict=True):
            box(im, (x, y, right, bottom), LIGHT, 25)
            self.label(im, label, (x+37, y+38, right-37, y+112), 50, TEAL)
            self.label(im, f"{before} → {after}", (x+35, y+125, right-35, bottom-40), 109, INK)
        foot = "Fable 5.1 → Fable 5.2 ／ 標準API"
        self.label(im, foot, (68, 1202, 948, 1313) if self.short else (88, 717, 1832, 824),
                   34 if self.short else 40, MUTE)
        self.source(im, "出典  Claude Platform Docs ／ 2026年11月10日確認")

    def release(self, im):
        self.header(im, "発表日  ／  2026年11月9日")
        self.title(im, "FableとMythosが同時に更新")
        self.picture(im, "release-header", (85, 220, 1184, 785))
        for index, (name, text) in enumerate([
                ("Fable 5.2", "広く提供。サイバーと生物分野に強い保護措置。"),
                ("Mythos 5.2", "同じ基盤モデル。所定の審査を通った組織が利用。")]):
            y = 274+index*250
            box(im, (1197, y, 1836, y+205), LIGHT, 22)
            self.label(im, name, (1222, y+14, 1810, y+92), 49, TEAL if not index else MYTHOS)
            self.label(im, text, (1225, y+100, 1806, y+198), 34, MUTE, wrap=True)
        self.source(im, QUOTE)

    def axes(self, im):
        self.header(im, "グラフの読み方")
        self.title(im, "同じスコアに、いくらで届く？")
        draw = ImageDraw.Draw(im)
        box(im, (84, 217, 1256, 829), LIGHT, 23)
        draw.line((233, 338, 233, 726, 1147, 726), fill=MUTE, width=4)
        draw.line((237, 510, 1070, 510), fill="#B8CFCA", width=3)
        for x, name in [(508, "費用が低い"), (987, "費用が高い")]:
            draw.ellipse((x-17, 493, x+17, 527), fill=TEAL if x==508 else ACCENT)
            self.label(im, name, (x-136, 555, x+136, 620), 36, center=True)
        self.label(im, "スコア", (252, 286, 515, 338), 40)
        self.label(im, "試行やタスクあたりの費用", (263, 742, 1145, 806), 36, center=True)
        self.label(im, "横軸は対数目盛り", (1320, 338, 1835, 420), 49, TEAL)
        self.label(im, "比較する点の推論設定と、\nツールの有無も確認", (1320, 455, 1835, 680), 38, MUTE)
        self.source(im, "模式図  ／  比較する軸の説明")

    def demo(self, im, output):
        self.header(im, "実演  ／  Claude Code")
        self.title(im, "グラフの交点を読む" if not output else "2週目で逆転、4週目は4件差")
        self.picture(im, "demo-output" if output else "demo-input", (84, 215, 1347, 844))
        self.label(im, "実行ログの抜粋" if output else "架空データ",
                   (1376, 313, 1830, 389), 49, TEAL)
        aside = "目盛りから読み取った概算と明記。" if output else "新工程が初めて下回る週は？\n4週目の差は？"
        self.label(im, aside, (1376, 433, 1830, 709), 42, MUTE, wrap=True)
        self.source(im, "実行環境  Windows ／ claude-fable-5-2 ／ 2026年11月10日")

    def access(self, im):
        self.header(im, "Claude Platform Docs")
        self.title(im, "長い入力と出力に対応")
        items = [("100万", "コンテキスト"), ("12万8千", "最大出力"), ("High", "APIの既定 effort")]
        for index, (value, label) in enumerate(items):
            x = 84+index*595
            box(im, (x, 291, x+560, 659), LIGHT, 26)
            self.label(im, value, (x+23, 331, x+535, 487), 106, TEAL, center=True)
            self.label(im, label, (x+22, 507, x+538, 628), 41, center=True)
        self.label(im, "ClaudeアプリとClaude Codeの既定はMedium", (86, 712, 1834, 804), 42, MUTE)
        self.source(im, "出典  Claude Platform Docs・Anthropic公式発表")

    def sol(self, im):
        self.header(im, "OPENAI  ／  公開モデル")
        self.title(im, "GPT-6.1 Solで公開されたこと")
        self.picture(im, "sol-docs", (85, 250, 1070, 746))
        self.label(im, "$2  ／  $10", (1130, 320, 1834, 486), 112, TEAL)
        self.label(im, "入力 ／ 出力\n標準API・100万トークンあたり", (1134, 508, 1834, 741), 43, MUTE)
        self.source(im, "出典  OpenAI公式発表・APIモデル一覧 ／ 2026年11月10日確認")

    def workflow(self, im):
        self.header(im, "次のモデルに期待すること")
        self.title(im, "ブラウザやアプリを操作して、保存まで")
        for index, value in enumerate(("入力", "操作", "結果を確認", "保存")):
            x = 84+index*446
            box(im, (x, 306, x+405, 522), LIGHT, 22)
            self.label(im, f"0{index+1}", (x+25, 319, x+380, 390), 33, TEAL)
            self.label(im, value, (x+24, 395, x+381, 498), 55)
        box(im, (84, 595, 1834, 756), PALE, 22)
        self.label(im, "送信など、影響のある操作は人に確認", (119, 628, 1798, 724), 56, TEAL)

    @lru_cache(maxsize=64)
    def portrait(self, name, index, width, height):
        path = self.frames[name][index]
        with Image.open(path) as im:
            w, h = im.size
            cropped = im.crop((round(w*.04), round(h*.13), round(w*.96), round(h*.88)))
            return ImageOps.fit(cropped, (width, height), Image.Resampling.LANCZOS, centering=(.5, .36))

    def character_spec(self, scene):
        if scene["visual"] == "axes":
            return [("female-understanding", (1580, 617, 1834, 828))]
        if scene["visual"] not in {"hero", "future", "closing"}:
            return []
        happy = scene["visual"] == "closing"
        clips = ("male-happy", "female-happy") if happy else ("male-thinking", "female-understanding")
        if self.short:
            rects = [(68, 679, 491, 1287), (514, 679, 937, 1287)]
            if scene["visual"] == "future":
                rects = [(68, 780, 491, 1330), (514, 780, 937, 1330)]
        else:
            rects = [(1046, 267, 1423, 827), (1450, 267, 1827, 827)]
        return list(zip(clips, rects, strict=True))

    def cast(self, im, scene, frame):
        for clip, (x, y, right, bottom) in self.character_spec(scene):
            index = min(len(self.frames[clip])-1, frame//2)
            tile = self.portrait(clip, index, right-x, bottom-y)
            box(im, (x-3, y-3, right+3, bottom+3), "#799D8E", 17)
            mask = Image.new("L", tile.size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile.width-1, tile.height-1), 15, fill=255)
            im.paste(tile, (x, y), mask)

    def presenter_base(self, im, scene):
        visual = scene["visual"]
        heads = {
            "hero": ("モデル解説  ／  2026.11", "性能向上\n標準API単価は2割減", "Anthropic発表  ／  11月9日"),
            "future": ("次のSolに期待", "もしSol 6.2の\nようなモデルが出るなら", "期待・仮の呼称  ／  正式発表未確認"),
            "closing": ("9図から見えたこと", "スコアと\n仕事の費用を見る", "全9図をフル版へ" if self.short else "図の読み方と実演は記事草稿へ"),
        }
        label, title, footer = heads[visual]
        self.header(im, label, dark=True)
        if self.short:
            self.label(im, title, (70, 270, 947, 540), 100, "white")
            self.label(im, footer, (71, 553, 948, 644), 36, GOLD, wrap=True)
            if visual == "future":
                self.label(im, "完了率 ／ 時間と費用 ／ 根拠", (71, 665, 945, 740), 39, "#DCF0E4")
        else:
            self.label(im, title, (85, 304, 1019, 548), 103, "white")
            self.label(im, footer, (87, 580, 1018, 674), 42, GOLD, wrap=True)
            if visual == "future":
                self.label(im, "完了率 ／ 時間と費用 ／ 根拠", (88, 721, 1000, 810), 40, "#DCF0E4")
        if visual == "hero":
            self.label(im, "Claude Fable 5.2", (85, 159, 1010, 258) if not self.short else
                       (70, 212, 947, 266), 73 if not self.short else 47, GOLD)

    def base(self, scene):
        visual = scene["visual"]
        presenter = visual in {"hero", "future", "closing"}
        im = Image.new("RGB", self.size, DARK if presenter else PAPER)
        if presenter:
            self.presenter_base(im, scene)
        elif visual in ("graph", "table"):
            getattr(self, visual)(im, scene)
        elif visual.startswith("demo-"):
            self.demo(im, visual == "demo-output")
        else:
            getattr(self, visual)(im)
        return im

    def captions(self, im, text):
        if not text:
            return
        rect = (57, 1442, 957, 1614) if self.short else (218, 901, 1702, 1058)
        box(im, rect, "#152C30", 25)
        # Center the actual ink in the two-line band as well as in one-line cues.
        size = 50 if self.short else 49
        tiles = [glyph(line, size, "#FFFFFF") for line in text.split("\n")]
        gap = round(size*.26)
        height = sum(t.height for t in tiles)+gap*(len(tiles)-1)
        y = rect[1]+((rect[3]-rect[1])-height)//2
        for tile in tiles:
            if tile.width > rect[2]-rect[0]-50 or tile.height > 57 or y < rect[1]+8:
                raise ValueError(f"Caption crosses safety bounds: {text}")
            x = rect[0]+((rect[2]-rect[0])-tile.width)//2
            im.paste(tile, (x, y), tile)
            y += tile.height+gap

    def jpeg(self, im):
        buf = BytesIO()
        im.save(buf, format="JPEG", quality=95, subsampling=0)
        return buf.getvalue()

    def frame(self, scene, base, frame, cue):
        im = base.copy()
        self.cast(im, scene, frame)
        self.captions(im, cue)
        return im


def srt_stamp(seconds):
    seconds, ms = divmod(round(seconds*1000), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{ms:03d}"


def write_plan(path, plan):
    save(path/"timeline.json", plan)
    cues = [cue for chapter in plan["chapters"] for cue in chapter["cues"]]
    text = "\n\n".join(f"{i}\n{srt_stamp(cue['start'])} --> {srt_stamp(cue['end'])}\n{cue['text']}"
                       for i, cue in enumerate(cues, 1))
    (path/"subtitles-ja.srt").write_text(text+"\n", encoding="utf-8")


def preflight(editor, scenes, plan, dest):
    dest.mkdir(parents=True, exist_ok=True)
    for scene, chapter in zip(scenes, plan["chapters"], strict=True):
        base = editor.base(scene)
        for cue in chapter["cues"]:
            probe = base.copy()
            editor.captions(probe, cue["text"])
        cue = max(chapter["cues"], key=lambda c: len(c["text"]))["text"]
        editor.frame(scene, base, min(36, chapter["frames"]-1), cue).save(dest/(scene["id"]+".jpg"), quality=91)
    save(dest/"quote-layout.json", editor.quotes)
    save(dest/"text-layout.json", list(editor.canvas.audit.values()))


def meter(path, filter_expr):
    report = run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path), "-af", filter_expr,
                  "-f", "null", "-"]).stderr
    return json.JSONDecoder().raw_decode(report[report.rindex("{"):])[0]


def normalize(premaster, mixed):
    loud = "loudnorm=I=-16:TP=-1.8:LRA=9"
    measured = meter(premaster, loud+":print_format=json")
    names = ("i", "lra", "tp", "thresh")
    values = ":".join(f"measured_{name}={measured['input_'+name]}" for name in names)
    limiter = f"{loud}:{values}:offset={measured['target_offset']}:linear=true"
    run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(premaster), "-af", limiter,
         "-ar", "48000", "-c:a", "pcm_s16le", str(mixed)])
    return measured


def render_picture(editor, scenes, plan, path):
    cmd = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "image2pipe", "-framerate", str(FPS),
           "-vcodec", "mjpeg", "-i", "pipe:0", "-an", "-vf",
           "scale=in_range=full:out_range=limited:out_color_matrix=bt709,format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-threads", "6",
           "-color_primaries", "bt709", "-colorspace", "bt709", "-color_trc", "bt709", str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATION)
    try:
        for scene, chapter in zip(scenes, plan["chapters"], strict=True):
            base = editor.base(scene)
            cache = {}
            moves = editor.character_spec(scene)
            motion_limit = max((len(editor.frames[clip])-1 for clip, _ in moves), default=0)
            cues = chapter["cues"]
            cue_starts = [cue["start"] for cue in cues]
            for frame in range(chapter["frames"]):
                instant = chapter["start"]+(frame+.5)/FPS
                idx = bisect_right(cue_starts, instant)-1
                cue = cues[idx]["text"] if idx >= 0 and instant < cues[idx]["end"] else ""
                key = (min(motion_limit, frame//2), cue)
                if key not in cache:
                    cache.clear()
                    cache[key] = editor.jpeg(editor.frame(scene, base, frame, cue))
                proc.stdin.write(cache[key])
            print(f"{editor.kind} {scene['id']} done", flush=True)
    except BaseException:
        proc.stdin.close()
        proc.wait()
        error = proc.stderr.read().decode(errors="replace")
        if error:
            print(error, file=sys.stderr)
        raise
    proc.stdin.close()
    err = proc.stderr.read()
    if proc.wait():
        raise RuntimeError(err.decode(errors="replace"))


def verify(path, editor, plan, dest):
    run(["ffmpeg", "-v", "error", "-nostdin", "-xerror", "-i", str(path), "-f", "null", "-"])
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(path)]).stdout)
    video, audio = probe["streams"]
    if (video["width"], video["height"]) != editor.size or int(video["nb_frames"]) != plan["frames"]:
        raise ValueError("Encoded dimensions/frame count differ from the edit")
    if (video["codec_name"], audio["codec_name"], video["pix_fmt"]) != ("h264", "aac", "yuv420p"):
        raise ValueError("Invalid review codecs")
    if abs(float(probe["format"]["duration"])-plan["seconds"]) > .08:
        raise ValueError("AAC and video do not match the requested time")
    loudness = meter(path, "loudnorm=print_format=json")
    if not -17.2 <= float(loudness["input_i"]) <= -14.8 or float(loudness["input_tp"]) > -1:
        raise ValueError(f"Unexpected final loudness: {loudness}")
    coverage = []
    stills = dest/"verified-frames"
    stills.mkdir(exist_ok=True)
    for chapter in plan["chapters"]:
        instant = (chapter["start"]+chapter["end"])/2
        still = stills/(chapter["scene"]+".png")
        run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{instant:.6f}", "-i", str(path),
             "-frames:v", "1", str(still)])
        if "graph" in chapter:
            quote = editor.quotes[chapter["scene"]]
            x, y, right, bottom = quote["frame_rect"]
            ref = editor.asset(quote["asset"], right-x, bottom-y)
            if ref.size != (right-x, bottom-y):
                ref = ref.resize((right-x, bottom-y), Image.Resampling.LANCZOS)
            with Image.open(still) as actual:
                pixels = np.asarray(actual.convert("RGB").crop(quote["frame_rect"]), dtype=np.float32)
            expected = np.asarray(ref, dtype=np.float32)
            mae = float(np.mean(np.abs(pixels-expected)))
            if mae > 5:
                raise ValueError(f"Encoded quote differs from its source: {quote['asset']} ({mae:.2f})")
            coverage.append(dict(quote, start=chapter["start"], end=chapter["end"],
                                 still=still.relative_to(dest).as_posix(), pixel_mean_error=round(mae, 3)))
    if [item["asset"] for item in coverage] != list(editor.story["graphs"]):
        raise ValueError("Graph inclusion or source order changed")
    return dict(sha256=digest(path), bytes=path.stat().st_size, seconds=plan["seconds"], frames=plan["frames"],
                width=video["width"], height=video["height"], fps=video["avg_frame_rate"],
                video="H.264", audio="AAC 48kHz", integrated_lufs=float(loudness["input_i"]),
                true_peak_dbtp=float(loudness["input_tp"]), full_decode=True, graph_coverage=coverage,
                human_listening="pending", smartphone_playback="pending", user_approved=False, published=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["prepare-motion", "preview", "render"])
    parser.add_argument("kind", choices=["short", "full"], nargs="?")
    parser.add_argument("--motion-source", type=Path)
    args = parser.parse_args()
    if args.mode == "prepare-motion":
        prepare_motion(args.motion_source)
        return
    story = read(HERE/"story-v01.json")
    kind = args.kind
    editor = Editor(story, kind)
    plan = make_plan(story, kind)
    folder = OUT/"release"/story["version"]/kind
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder/f"fable-5-2-{kind}-{story['version']}.mp4"
    if dest.exists():
        raise FileExistsError("Preserve an existing candidate and create a new revision for changed inputs")
    write_plan(folder, plan)
    preflight(editor, story[kind], plan, folder/"preview")
    print(f"{kind}: {plan['seconds']:.3f}s, {plan['frames']} frames", flush=True)
    if args.mode == "preview":
        return
    stage = folder/"work"
    stage.mkdir(exist_ok=True)
    audio = assemble_audio(plan, stage, music_style="calm")
    normalize(stage/"mix-premaster.wav", stage/"mix.wav")
    picture = stage/"picture.mp4"
    render_picture(editor, story[kind], plan, picture)
    temp = stage/"muxed.mp4"
    run(["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(picture), "-i", str(stage/"mix.wav"),
         "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-ar", "48000", "-movflags", "+faststart", str(temp)])
    proof = verify(temp, editor, plan, folder)
    temp.rename(dest)
    save(folder/"verification.json", dict(proof, file=dest.name, music=audio))
    print(f"{dest.name}: {proof['bytes']} bytes, {proof['integrated_lufs']} LUFS", flush=True)


if __name__ == "__main__":
    main()
