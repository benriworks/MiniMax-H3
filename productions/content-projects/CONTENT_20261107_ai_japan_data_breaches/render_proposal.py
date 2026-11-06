"""Render original text-only review sheets. Does not generate video or edit photos."""
from pathlib import Path
import hashlib
import json
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = ROOT / "outputs/content-projects" / HERE.name / "review/v01"
W, H = 1000, 1700
INK = "#15343D"
TEAL = "#006D77"
MUTED = "#546E76"
BG = "#F3F7F6"
FONT = Path("C:/Windows/Fonts/YuGothM.ttc")
BOLD = Path("C:/Windows/Fonts/YuGothB.ttc")


def font(size: int, bold: bool = False):
    return ImageFont.truetype(str(BOLD if bold else FONT), size)


def sheet(kicker, title):
    im = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(im)
    draw.rectangle((0, 0, W, 18), fill=TEAL)
    draw.text((58, 55), kicker, font=font(26, True), fill=TEAL)
    draw.text((58, 108), title, font=font(49, True), fill=INK)
    return im, draw


def lines(draw, x, y, texts, size=34, color=INK, line=60):
    for text in texts:
        assert draw.textlength(text, font=font(size)) <= W - x - 48, text
        draw.text((x, y), text, font=font(size), fill=color)
        y += line
    return y


def heading(draw, y, title):
    draw.rounded_rectangle((52, y, 948, y + 66), radius=12, fill="#DCEDEA")
    draw.text((72, y + 8), title, font=font(35, True), fill=TEAL)
    return y + 88


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ranking = json.loads((HERE / "ranking-v01.json").read_text(encoding="utf-8"))["ranking"][:10]
    im, draw = sheet("制作企画 v01 ／ 2026-11-07確認 ／ 未採用・未制作", "【AI】日本の情報漏えい")
    y = lines(draw, 60, 205, ["漏れた情報で、必要な対処は変わる。", "件数と内容を確認し、次の行動につなぐ。"], 37)
    y = heading(draw, y + 32, "フル 1本 ／ 約8〜9分の案")
    y = lines(draw, 65, y, ["結果から入る → AIによる攻撃の背景", "10位から1位：規模・対象情報・分かる原因", "順位外の本人確認書類 → 情報別の対処", "末尾は関連動画・登録用に10秒の余韻"], 34)
    y = heading(draw, y + 32, "ショート 1本 ／ 約60秒の案")
    y = lines(draw, 65, y, ["国内の2〜3例と、3つの対処に絞る。", "10事例を詰め込まず、フル・記事へ。"], 34)
    y = heading(draw, y + 32, "白衣の2人を継続")
    y = lines(draw, 65, y, ["朝倉 透：視聴者の疑問を言う役", "篠宮 凛：やわらかな返答で解説する役", "声は Charon ／ Aoede を継承する案。", "心配・注視・理解を台詞の意味へ合わせる。"], 33)
    y = heading(draw, y + 32, "今回の確認点")
    y = lines(draw, 65, y, ["次ページの暫定Top10と採点法、", "フル＋ショートの構成で進めてよいか。"], 34)
    assert y < H - 70
    draw.text((60, H - 66), "詳しい出典・条件・記事草稿は同じフォルダーの全文へ。", font=font(25), fill=MUTED)
    first = OUT / "01-plan-v01.png"
    im.save(first)

    im, draw = sheet("編集上の暫定順位 ／ 2026年11月7日時点の主な国内事例", "公表規模N × 影響Iの案")
    lines(draw, 60, 188, ["実害・企業の責任・個人の危険度の順位ではありません。"], 27)
    short = {
        "arara-message-202610": ("アララ メッセージ", "81,329,467メールアドレス", "持ち出し確認／人数ではない"),
        "cuenote-202610": ("Cuenote", "51,628,280件（延べ）", "可能性を含む公表範囲／調査継続"),
        "muji-app-202610": ("MUJIアプリ", "最大約2,726万件", "流出の可能性／カードは別区分"),
        "sagawa-tracking-202609": ("佐川急便", "最大約5,323万件（重複あり）", "流出の可能性／実人数ではない"),
        "epark-peakmanager-202607": ("EPARK PeakManager", "約2,218万レコード", "情報の外部取得／人数へ換算困難"),
        "estore-shopsserve-202605": ("Eストアー ショップサーブ", "約2,335万6,000人（概数）", "持ち出し確認／重複の可能性"),
        "sourcenext-202610": ("ソースネクスト", "22,519,960件", "不正取得確認／数字は可能性範囲"),
        "skyticket-server-202610": ("skyticket", "約1,464万件（主たる対象）", "確認と可能性が混在／別データは非加算"),
        "kddi-isp-mail-202605": ("KDDIのISP向けメール基盤", "12,231,954名（公式表記）", "漏えい確認／認証情報は一部対象"),
        "burgerking-jp-app-202610": ("バーガーキング日本公式アプリ", "約1,118万件", "漏えい確認／カード・PWの流出と区別"),
    }
    y = 254
    for rank, item in enumerate(ranking, 1):
        if rank % 2:
            draw.rounded_rectangle((46, y - 4, 954, y + 114), radius=10, fill="white")
        name, count, certainty = short[item["incident_id"]]
        draw.text((65, y + 19), str(rank), font=font(40, True), fill=TEAL)
        draw.text((136, y), name, font=font(32, True), fill=INK)
        draw.text((138, y + 40), count, font=font(30), fill=INK)
        draw.text((138, y + 79), certainty, font=font(23), fill=MUTED)
        draw.text((882, y + 14), f"I={item['impact']}", font=font(23, True), fill=TEAL)
        assert draw.textlength(name, font=font(32, True)) < 730, name
        y += 122
    lines(draw, 58, 1500, ["単位の違う数字を足して「被害人数」にしない。", "Iは1〜5の編集点。一部の機微情報が全件にあるとは限らない。", "採点を変えると順位も変わる。個人の対処は対象情報から選ぶ。"], 25, MUTED, 45)
    second = OUT / "02-ranking-v01.png"
    im.save(second)
    text = (HERE / "PROPOSAL_V01_JA.md").read_text(encoding="utf-8")
    text += "\n\n" + (HERE / "RANKING_V01_JA.md").read_text(encoding="utf-8")
    text += "\n\n" + (HERE / "ARTICLE_DRAFT_V01_JA.md").read_text(encoding="utf-8")
    (OUT / "03-proposal-and-article-v01.txt").write_text(text, encoding="utf-8")
    rows = []
    for path in [first, second, OUT / "03-proposal-and-article-v01.txt"]:
        rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
                     "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (OUT / "manifest.json").write_text(json.dumps({"status": "proposal_not_accepted", "artifacts": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"images": 2, "dimensions": [W, H], "status": "proposal_not_accepted"}))


if __name__ == "__main__":
    main()
