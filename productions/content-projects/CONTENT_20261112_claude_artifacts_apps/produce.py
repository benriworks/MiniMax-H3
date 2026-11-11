"""Render two local review MP4s, matching narration and evidence to each cut."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import argparse
import json
import math
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageOps

from prepare import HERE, OUT, ROOT, FIGURES, MOTION, save

sys.path.insert(0, str(ROOT))
from tools.studio.editorial_captions import PROTECTED, timed_captions
from tools.studio.explainer_canvas import Canvas, box, fit, glyph, wrap
from tools.studio.longform_audio import assemble_audio, plan_dialogue, read_voice

FPS = 24
PAPER = "#F6F2E9"
WHITE = "#FFFFFF"
INK = "#1F2A28"
MUTED = "#4A5B56"
CORAL = "#A8442C"
PALE_CORAL = "#F3DED4"
GREEN = "#16624E"
PALE_GREEN = "#DFECE3"
BORDER = "#DBD4C6"
DARK = "#192A29"
CHECKED = "Claude 日本語Web版　11月12日撮影"
ANNOUNCEMENT = "Anthropic 公式発表　2026年11月10日"
APP_QUOTE = "出典　Anthropic公式デモ「Your apps have moved into Claude」"
WORDS = (*PROTECTED, "Claude Data", "Claude Sheets", "Claude Whiteboards", "Whiteboards",
         "67,250円", "64,000円", "70,000円", "29,250円", "2,750円", "Confluence",
         "Enterprise", "ダッシュボード", "外部アプリ", "ドキュメント検索")
VOICE_ROOT = OUT / "voice/selected-v01"


class Editor:
    def __init__(self, kind):
        self.short = kind == "short"
        self.w, self.h = (1080, 1920) if self.short else (1920, 1080)
        self.left, self.right = (76, 930) if self.short else (82, 1838)
        self.bottom = 1420 if self.short else 850
        self.font_size = 52 if self.short else 46
        self.caption_rect = (54, 1450, 952, 1640) if self.short else (82, 888, 1838, 1036)
        self.caption_width = self.caption_rect[2] - self.caption_rect[0] - 74
        self.canvas = Canvas()
        self.figures = {}

    def text(self, im, value, rect, size, color=INK, center=False):
        for point in range(size, 17, -1):
            widths = [glyph(line, point, color).width for line in value.split("\n")]
            height = sum(glyph(line, point, color).height for line in value.split("\n"))
            height += round(point * .26) * (len(widths) - 1) + (6 if len(widths) > 1 else 0)
            if max(widths) <= rect[2] - rect[0] and height <= rect[3] - rect[1]:
                self.canvas.text(im, value, rect, point, color, center=center)
                return
        raise ValueError(f"Text does not fit: {value}")

    def picture(self, im, name, rect, background=WHITE):
        if name not in self.figures:
            with Image.open(FIGURES / f"{name}.png") as src:
                self.figures[name] = src.convert("RGB")
        box(im, rect, background, radius=25, outline=BORDER, width=2)
        x0, y0, x1, y1 = rect
        fit(im, self.figures[name], (x0 + 16, y0 + 16, x1 - 16, y1 - 16))

    def list_cards(self, im, entries, rect):
        x0, y0, x1, y1 = rect
        gap = 17 if self.short else 16
        h = (y1 - y0 - gap * (len(entries) - 1)) // len(entries)
        for i, (label, detail, color) in enumerate(entries):
            y = y0 + i * (h + gap)
            box(im, (x0, y, x1, y + h), PALE_GREEN if color == GREEN else WHITE,
                radius=24, outline=BORDER, width=2)
            ImageDraw.Draw(im).rounded_rectangle((x0 + 15, y + 22, x0 + 23, y + h - 22), 4, fill=color)
            self.text(im, label, (x0 + 42, y + 10, x1 - 25, y + h // 2 + 4), 50 if self.short else 43, color)
            self.text(im, detail, (x0 + 42, y + h // 2, x1 - 25, y + h - 9), 34 if self.short else 33, MUTED)

    def stat(self, im, label, value, rect, highlight=False):
        x0, y0, x1, y1 = rect
        box(im, rect, PALE_GREEN if highlight else WHITE, radius=28, outline=BORDER, width=2)
        self.text(im, label, (x0 + 32, y0 + 24, x1 - 28, y0 + 81), 39 if self.short else 36, MUTED)
        self.text(im, value, (x0 + 30, y0 + 83, x1 - 25, y1 - 22), 96 if self.short else 90,
                  GREEN if highlight else INK)

    def portrait(self, im, clip, index, rect):
        src = MOTION / clip / f"{min(61, max(0, index)) + 1:03d}.jpg"
        with Image.open(src) as opened:
            # Keep head, hands, and tabletop together, excluding empty top space.
            crop = opened.crop((0, 135, opened.width, min(opened.height, 765))).convert("RGB")
        tile = ImageOps.fit(crop, (rect[2] - rect[0], rect[3] - rect[1]),
                            Image.Resampling.LANCZOS, centering=(.5, .44))
        mask = Image.new("L", tile.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tile.width - 1, tile.height - 1), 23, fill=255)
        im.paste(tile, rect[:2], mask)

    def header(self, im, title):
        x0, x1 = self.left, self.right
        y = 92 if self.short else 43
        self.text(im, "Claude", (x0, y, x1, y + 45), 39 if self.short else 34, CORAL)
        line_y = y + 59
        ImageDraw.Draw(im).line((x0, line_y, x1, line_y), fill=BORDER, width=2)
        if self.short:
            headings = {"Whiteboardsで企画を整理": "Whiteboardsで\n企画を整理",
                        "チャットの横で外部アプリを開く": "チャットの横で\n外部アプリを開く"}
            heading = headings.get(title, "\n".join(wrap(title, 14)))
            self.text(im, heading, (x0, 174, x1, 310), 65)
        else:
            self.text(im, title, (x0, 119, x1, 201), 64)

    def credit(self, im, value):
        self.text(im, value, (self.left, self.bottom - 51, self.right, self.bottom), 28 if self.short else 26, MUTED)

    def short_visual(self, im, visual, changed, motion):
        x, r = self.left, self.right
        if visual == "hook":
            self.stat(im, "変更前・40個", "64,000円", (x, 345, r, 572))
            self.stat(im, "変更後・45個", "67,250円", (x, 596, r, 823), True)
            self.picture(im, "sheet-after", (x, 854, 600, 1358))
            self.portrait(im, "female-happy", motion, (628, 854, r, 1358))
            self.credit(im, CHECKED)
        elif visual == "board":
            self.picture(im, "board", (x, 365, r, 750))
            self.list_cards(im, [
                ("会場を予約", "12月1日", CORAL), ("試食セットを手配", "12月5日", CORAL),
                ("チラシを配布", "12月8日", CORAL)], (x, 795, r, 1350))
            self.credit(im, CHECKED)
        elif visual == "sheet":
            self.picture(im, "sheet-after" if changed else "sheet-before", (x, 345, r, 1050))
            self.stat(im, "45個に変更後" if changed else "試食セット40個", "67,250円" if changed else "64,000円",
                      (x, 1090, r, 1354), changed)
            self.credit(im, CHECKED)
        elif visual == "app":
            self.picture(im, "confluence", (x, 380, r, 810))
            self.list_cards(im, [
                ("チャットの横／全画面", "対応アプリの画面をClaude内で表示", CORAL),
                ("Confluenceの例", "開いた文書にClaudeが要約を追記", GREEN)], (x, 850, r, 1340))
            self.credit(im, APP_QUOTE)
        elif visual == "short_access":
            self.list_cards(im, [
                ("Sheets・Whiteboards", "有料プランでベータ", CORAL),
                ("Claude Data", "一般提供・データ接続が必要", GREEN),
                ("外部アプリの新表示", "Web・デスクトップに順次展開", CORAL)], (x, 370, r, 1337))
            self.credit(im, ANNOUNCEMENT)
        else:
            raise ValueError(visual)

    def full_visual(self, im, visual, changed, motion, speaker):
        x, r = self.left, self.right
        left_pic = (x, 229, 1020, 786)
        right_notes = (1065, 229, r, 786)
        if visual == "hook":
            self.stat(im, "試食セット40個", "64,000円", (x, 231, 1040, 485))
            self.stat(im, "試食セット45個", "67,250円", (x, 515, 1040, 786), True)
            self.portrait(im, "male-thinking", motion if speaker == "male" else 61,
                          (1085, 231, 1445, 786))
            self.portrait(im, "female-happy", motion if speaker == "female" else 0,
                          (1466, 231, r, 786))
            self.credit(im, "架空の試食会　Claude Sheetsで再計算")
        elif visual == "release":
            self.picture(im, "official-artifacts", (x, 237, 996, 785))
            self.list_cards(im, [
                ("Whiteboards", "企画を整理・ベータ", CORAL),
                ("Sheets", "表を編集・ベータ", CORAL),
                ("Claude Data", "旧Dashboards・一般提供", GREEN)], (1040, 237, r, 785))
            self.credit(im, ANNOUNCEMENT)
        elif visual == "board":
            self.picture(im, "board", (x, 231, r, 772))
            self.credit(im, CHECKED)
        elif visual in {"sheet", "recalc"}:
            after = visual == "recalc" and changed
            self.picture(im, "sheet-after" if after else "sheet-before", left_pic)
            if visual == "sheet":
                notes = [
                    ("数量 × 単価", "金額の列で費目ごとに計算", CORAL),
                    ("合計 64,000円", "試食セット40個の場合", GREEN),
                    ("残額 6,000円", "上限70,000円から差し引き", CORAL)]
            elif after:
                notes = [
                    ("40個 → 45個", "B3の数量を手で変更", CORAL),
                    ("合計 67,250円", "D5　=SUM(D2:D4)", GREEN),
                    ("残額 2,750円", "D7　=D6-D5", CORAL)]
            else:
                notes = [
                    ("変更前", "試食セット40個", CORAL),
                    ("合計 64,000円", "残額 6,000円", GREEN)]
            self.list_cards(im, notes, right_notes)
            self.credit(im, CHECKED)
        elif visual == "excel":
            self.picture(im, "excel-menu", left_pic)
            self.list_cards(im, [
                ("Excel（.xlsx）を選ぶ", "Artifact名 → エクスポート", CORAL),
                ("D5  =SUM(D2:D4)", "保存値　67,250円", GREEN),
                ("D7  =D6-D5", "保存値　2,750円", CORAL)], right_notes)
            self.credit(im, "書き出したファイルの数式と保存値を確認")
        elif visual == "data":
            self.list_cards(im, [
                ("データを接続", "データウェアハウスやCRMなど", CORAL),
                ("Claudeに質問", "例　当日の来場者数を時間帯別に集計", CORAL),
                ("ダッシュボードを作成", "接続したデータの集計や可視化", GREEN)], (x, 231, 1195, 785))
            box(im, (1240, 231, r, 785), DARK, radius=25)
            self.text(im, "データ接続が必要", (1270, 311, r - 28, 425), 51, WHITE, True)
            self.text(im, "Claude Sheetsからの\nライブ連携は非対応", (1270, 473, r - 28, 632), 39, WHITE, True)
            self.credit(im, "出典　Claude Data・Claude Sheets 公式ヘルプ")
        elif visual == "admin":
            self.list_cards(im, [
                ("対象プラン", "Pro・Max・Ultra・Team・Enterprise", CORAL),
                ("Team", "Sheets・Whiteboards・Dataは既定でオン", GREEN),
                ("Enterprise", "Sheets／Whiteboardsは既定でオフ。Dataは11月19日から※", CORAL)],
                (x, 228, r, 760))
            self.text(im, "※組織の所有者がすでに設定を保存している場合は、その設定が優先されます。",
                      (x, 782, r, 826), 28, MUTED)
        elif visual == "app":
            self.picture(im, "confluence", (x, 245, 1195, 768))
            self.list_cards(im, [
                ("文書を開く", "横に表示、または全画面", CORAL),
                ("要約を頼む", "必要な操作を承認", GREEN),
                ("同じ文書で確認", "人も画面を直接操作できる", CORAL)], (1237, 245, r, 768))
            self.credit(im, APP_QUOTE)
        elif visual == "vercel":
            self.picture(im, "vercel-result" if changed else "vercel-permission", left_pic)
            self.list_cards(im, [
                ("Vercel・接続済み", "公開資料「Preview Deployments」を検索", CORAL),
                ("1回だけ許可する", "検索操作に限定", CORAL),
                ("結果はテキスト表示", "表示と操作の範囲は機能ごとに異なる", GREEN)], right_notes)
            self.credit(im, CHECKED)
        elif visual == "access":
            self.picture(im, "directory", (x, 229, 905, 786))
            self.list_cards(im, [
                ("対象は全プラン", "新しいClaudeのWeb・デスクトップで順次展開", GREEN),
                ("モバイル", "新しい横表示・全画面表示は非対応", CORAL),
                ("アプリを選ぶ", "カスタマイズ → コネクタから対応状況を確認", CORAL)],
                (944, 229, r, 786))
            self.credit(im, "出典　Anthropic 公式発表・インタラクティブコネクタ公式ヘルプ")
        else:
            raise ValueError(visual)

    def frame(self, scene, changed, motion, speaker, caption):
        im = Image.new("RGB", (self.w, self.h), PAPER)
        self.header(im, scene["title"])
        if self.short:
            self.short_visual(im, scene["visual"], changed, motion)
        else:
            self.full_visual(im, scene["visual"], changed, motion, speaker)
        if caption:
            box(im, self.caption_rect, DARK, radius=27)
            x0, y0, x1, y1 = self.caption_rect
            lines = caption.split("\n")
            gap = round(self.font_size * .23)
            tiles = [glyph(line, self.font_size, WHITE) for line in lines]
            height = sum(tile.height for tile in tiles) + gap * (len(tiles) - 1)
            assert height < y1 - y0 and all(tile.width < x1 - x0 for tile in tiles)
            y = round((y0 + y1 - height) / 2)
            for tile in tiles:
                im.paste(tile, (round((x0 + x1 - tile.width) / 2), y), tile)
                y += tile.height + gap
        return im


def build_plan(kind, editor):
    data = json.loads((HERE / "story-v01.json").read_text(encoding="utf-8"))
    scenes = data[kind]
    for scene in scenes:
        seconds = sum(len(read_voice(VOICE_ROOT / scene["id"] / f"turn-{i:02d}" / "voice.wav")) / 24000
                      for i in range(len(scene["turns"])))
        scene["target_seconds"] = min(scene["target_seconds"], seconds + (2.6 if kind == "short" else 4.0))
        scene["pause_mode"] = "after_answer"
    plan = plan_dialogue(scenes, VOICE_ROOT, FPS)
    for scene, chapter in zip(scenes, plan["chapters"], strict=True):
        chapter["visual"] = scene["visual"]
        chapter["captions"] = []
        for turn in chapter["turns"]:
            chapter["captions"].extend(timed_captions(turn["text"], turn["start"], turn["end"] - turn["start"],
                                         editor.caption_width, editor.font_size, protected=WORDS))
        turns = chapter["turns"]
        chapter["change"] = turns[-1]["start"] if len(turns) > 1 else turns[0]["start"] + 2.8
        if chapter["visual"] == "vercel":
            chapter["change"] = turns[-1]["start"] + (turns[-1]["end"] - turns[-1]["start"]) * .52
    return plan


def state(chapter, instant):
    speaker = "male" if len(chapter["turns"]) > 1 else "female"
    elapsed = instant - chapter["start"]
    for turn in chapter["turns"]:
        if instant >= turn["start"]:
            speaker = turn["speaker"]
            elapsed = instant - turn["start"]
    motion = min(61, max(0, int(elapsed * 12))) if chapter["visual"] == "hook" else 0
    caption = next((cue["text"] for cue in chapter["captions"] if cue["start"] <= instant < cue["end"]), "")
    return instant >= chapter["change"], motion, speaker, caption


def preview(editor, plan, folder):
    folder.mkdir(parents=True, exist_ok=True)
    cards = []
    for chapter in plan["chapters"]:
        for i, turn in enumerate(chapter["turns"]):
            instant = (turn["start"] + turn["end"]) / 2
            im = editor.frame(chapter, *state(chapter, instant))
            im.save(folder / f"{chapter['id']}-{i + 1}.jpg", quality=90)
            cards.append(im)
    tile_w = 216 if editor.short else 384
    tile_h = 384 if editor.short else 216
    columns = 5 if editor.short else 4
    sheet = Image.new("RGB", (tile_w * columns, tile_h * math.ceil(len(cards) / columns)), PAPER)
    for index, im in enumerate(cards):
        fit(sheet, im, (index % columns * tile_w, index // columns * tile_h,
                        (index % columns + 1) * tile_w, (index // columns + 1) * tile_h))
    sheet.save(folder / "contact.jpg", quality=90)


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")


def loudness(path):
    command = ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
               "-af", "loudnorm=I=-15:TP=-1.5:LRA=8:print_format=json", "-f", "null", "-"]
    output = run(command).stderr
    return json.loads(re.findall(r'\{\s*"input_i".*?\}', output, flags=re.S)[-1])


def normalize(source, destination):
    measured = loudness(source)
    options = ":".join(f"measured_{k}={measured['input_' + k]}" for k in ("i", "tp", "lra", "thresh"))
    af = f"loudnorm=I=-15:TP=-1.5:LRA=8:{options}:offset={measured['target_offset']}:linear=true"
    run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(source), "-af", af,
         "-ar", "48000", "-c:a", "pcm_s16le", str(destination)])


def srt_time(seconds):
    total = round(seconds * 1000)
    return f"{total // 3600000:02}:{total // 60000 % 60:02}:{total // 1000 % 60:02},{total % 1000:03}"


def encode(editor, plan, kind, folder):
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / f"claude-nov10-{kind}-v01.mp4"
    if destination.exists():
        raise FileExistsError("Keep existing review candidates. Create a new version for edits.")
    work = folder / "work"
    audio = assemble_audio(plan, work, music_style="calm")
    normalize(work / "mix-premaster.wav", work / "mix.wav")
    args = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-f", "image2pipe", "-framerate", str(FPS),
            "-c:v", "mjpeg", "-i", "pipe:0", "-i", str(work / "mix.wav"), "-map", "0:v", "-map", "1:a",
            "-vf", "scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", "4", "-g", "48",
            "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
            "-color_primaries", "bt709", "-color_trc", "bt709",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-t", f"{plan['seconds']:.8f}", "-movflags", "+faststart", str(destination)]
    with subprocess.Popen(args, stdin=subprocess.PIPE) as encoder:
        try:
            for chapter in plan["chapters"]:
                cache = {}
                for frame_number in range(chapter["frames"]):
                    instant = chapter["start"] + (frame_number + .5) / FPS
                    render_state = state(chapter, instant)
                    if render_state not in cache:
                        stream = BytesIO()
                        editor.frame(chapter, *render_state).save(stream, format="JPEG", quality=88)
                        cache[render_state] = stream.getvalue()
                    encoder.stdin.write(cache[render_state])
                print(f"{kind} {chapter['id']} encoded", flush=True)
        finally:
            encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("FFmpeg failed")
    run(["ffmpeg", "-v", "error", "-nostdin", "-xerror", "-i", str(destination), "-f", "null", "-"])
    metadata = json.loads(run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
                               str(destination)]).stdout)
    video, sound = metadata["streams"]
    assert (video["width"], video["height"], video["codec_name"], video["pix_fmt"]) == (
        editor.w, editor.h, "h264", "yuv420p")
    assert video["color_range"] == "tv" and video["color_space"] == "bt709"
    assert int(video["nb_frames"]) == plan["frames"]
    assert sound["codec_name"] == "aac" and sound["channels"] == 2
    assert abs(float(metadata["format"]["duration"]) - plan["seconds"]) < .09
    measurement = loudness(destination)
    assert -17.5 <= float(measurement["input_i"]) <= -13.0 and float(measurement["input_tp"]) < -0.9
    blob = destination.read_bytes()
    assert 0 < blob.find(b"moov") < blob.find(b"mdat")
    save(folder / "timeline.json", plan)
    save(folder / "qc.json", dict(path=destination.name, sha256=sha256(blob).hexdigest(), bytes=len(blob),
         video=f"{editor.w}x{editor.h} H.264 {FPS}fps", audio="48kHz stereo AAC",
         duration=plan["seconds"], frames=plan["frames"], full_decode="passed",
         audio_mix=audio, loudness=measurement, faststart=True,
         human_listening="未実施", user_adoption="未確認", publication="未公開"))
    cues = [cue for chapter in plan["chapters"] for cue in chapter["captions"]]
    (folder / f"claude-nov10-{kind}-v01.srt").write_text("\n\n".join(
        f"{i}\n{srt_time(cue['start'])} --> {srt_time(cue['end'])}\n{cue['text']}"
        for i, cue in enumerate(cues, start=1)) + "\n", encoding="utf-8")
    print(f"{destination.name} {len(blob)} bytes {plan['seconds']:.2f}s", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["preview", "render"])
    parser.add_argument("kind", choices=["short", "full"])
    args = parser.parse_args()
    editor = Editor(args.kind)
    plan = build_plan(args.kind, editor)
    if args.mode == "preview":
        preview(editor, plan, OUT / "previews/v01" / args.kind)
    else:
        encode(editor, plan, args.kind, OUT / "release/v01" / args.kind)


if __name__ == "__main__":
    main()
