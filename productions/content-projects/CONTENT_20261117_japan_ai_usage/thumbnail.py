"""Build the YouTube Shorts thumbnail using the art from short v03."""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from prepare import OUT, ROOT, digest, save
from graphics import Editor, MOTION, PAPER, portrait
from tools.studio.explainer_canvas import FONT

SIZE = (2160, 3840)
NAME = "claude-japan-ai-short-thumbnail-v01"
PORTRAITS = (
    ("male-happy", 16, (144, 1536, 1060, 2752)),
    ("female-happy", 0, (1100, 1536, 2016, 2752)),
)
HEADLINE = ("顧客別の提案書", "AIで下書き")
INK = "#182F2D"
FOCUS = "#106353"


def centered_text(draw, value, top, size, weight, color):
    font = ImageFont.truetype(str(FONT), size)
    font.set_variation_by_axes([weight])
    left, rise, right, _bottom = draw.textbbox((0, 0), value, font=font)
    width = right - left
    if width > 1900:
        raise ValueError(f"Text exceeds the thumbnail's safe width: {value}")
    draw.text(((SIZE[0] - width) // 2 - left, top - rise), value, font=font, fill=color)


def render_thumbnail(folder):
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"{NAME}.png"
    if output.exists():
        raise FileExistsError(output)

    background = Image.linear_gradient("L").resize(SIZE)
    image = ImageOps.colorize(background, "#FFF8ED", "#F5DECA")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((-320, 2475, 2480, 4400), radius=450, fill="#DAEAE2")

    centered_text(draw, "Claude Code", 652, 106, 790, "#9C4127")
    centered_text(draw, HEADLINE[0], 900, 256, 880, INK)
    draw.rounded_rectangle((250, 1184, 1910, 1484), radius=51, fill=FOCUS)
    centered_text(draw, HEADLINE[1], 1226, 230, 870, "#FFFFFF")

    frame_sources = []
    for clip, index, rect in PORTRAITS:
        left, top, right, bottom = rect
        part, mask = portrait(clip, index, right - left, bottom - top)
        image.paste(part, (left, top), mask)
        path = MOTION / clip / f"{index + 1:03d}.jpg"
        frame_sources.append({
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": digest(path),
        })

    # Keep the customer name, title and first row from the actual video graphic.
    proposal = Image.new("RGB", (1080, 1920), PAPER)
    Editor("short", show_role_labels=False).proposal(proposal, "proposal-output", 0)
    proposal_area = (95, 364, 922, 798)
    excerpt = proposal.crop(proposal_area)
    excerpt = ImageOps.contain(excerpt, (1380, 708), method=Image.Resampling.LANCZOS)
    page = (326, 2410, 1834, 3220)
    shadow = Image.new("L", SIZE)
    ImageDraw.Draw(shadow).rounded_rectangle((326, 2434, 1834, 3244), radius=70, fill=105)
    image.paste("#203D32", (0, 0), shadow.filter(ImageFilter.GaussianBlur(36)))
    draw.rounded_rectangle(page, radius=70, fill="#FFFFFF")
    image.paste(excerpt, ((SIZE[0] - excerpt.width) // 2, 2444))
    draw.text((1735, 2482), "架空例", anchor="rt", font=ImageFont.truetype(str(FONT), 56), fill="#526660")

    image.save(output, optimize=True, dpi=(96, 96))
    with Image.open(output) as actual:
        actual.load()
        if actual.size != SIZE or actual.mode != "RGB" or actual.format != "PNG":
            raise ValueError("Unexpected thumbnail format")
        actual.resize((360, 640), Image.Resampling.LANCZOS).save(folder / "review-360.jpg", quality=92)
        actual.crop((0, 840, 2160, 3000)).resize((360, 360), Image.Resampling.LANCZOS).save(
            folder / "review-center-360.jpg", quality=92
        )
    metadata = {
        "video": "claude-japan-ai-short-v03.mp4",
        "text": list(HEADLINE),
        "image": {
            "filename": output.name,
            "size": list(SIZE),
            "bytes": output.stat().st_size,
            "sha256": digest(output),
        },
        "portrait_frames": frame_sources,
        "proposal_crop": list(proposal_area),
        "font": FONT.relative_to(ROOT).as_posix(),
        "font_sha256": digest(FONT),
        "user_approved": False,
        "youtube_applied": False,
    }
    save(folder / "manifest.json", metadata)
    print(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT / "thumbnail-v01")
    render_thumbnail(parser.parse_args().output_dir)
