"""Extract one actual completed-video frame per cut for layout inspection."""
from pathlib import Path
import json, subprocess
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/productions/LONG_20261026_dots_transfer_detail/v01'


def main():
    review = OUT / 'review'
    review.mkdir(exist_ok=True)
    visuals = json.loads((OUT / 'visuals.json').read_text(encoding='utf-8'))
    rows = []
    cursor = 0.0
    for chapter, shots in visuals.items():
        for index, shot in enumerate(shots):
            moment = cursor + shot['seconds'] / 2
            dest = review / f'{chapter}-{index:02d}.jpg'
            subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-ss', str(moment),
                '-i', str(OUT / 'dots-transfer-detail-v01.mp4'), '-frames:v', '1', '-q:v', '2', str(dest)], check=True)
            rows.append(dict(chapter=chapter, cut=index, seconds=moment, frame=dest.name))
            cursor += shot['seconds']
    for page, start in enumerate(range(0, len(rows), 15), 1):
        sheet = Image.new('RGB', (1440, 5 * 292), '#eeeeee')
        draw = ImageDraw.Draw(sheet)
        for cell, item in enumerate(rows[start:start + 15]):
            x, y = cell % 3 * 480, cell // 3 * 292
            with Image.open(review / item['frame']) as image:
                sheet.paste(image.resize((480, 270)), (x, y))
            draw.text((x + 5, y + 272), f"{item['chapter']} / {item['cut']} / {item['seconds']:.1f}s", fill='black')
        sheet.save(review / f'contact-{page:02d}.jpg', quality=94)
    (review / 'frames.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print(f'Extracted {len(rows)} frames from completed MP4')


if __name__ == '__main__':
    main()
