"""Bind a reviewed, unchanged screenshot crop to a frozen story scene.

This never captures a desktop or invents a missing screen. Source pixels must
already have been obtained through the approved Computer Use workflow.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from PIL import Image
from tools.studio.shorts_creator import load_capture, read, record
from produce import save


def bind(episode, key, source, box, captured_at, review_basis):
    source = source.resolve(strict=True)
    if not source.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Keep private originals in outputs')
    stamp = datetime.fromisoformat(captured_at.replace('Z', '+00:00'))
    if stamp.utcoffset() is None:
        raise ValueError('Capture time needs a timezone')
    story = read(HERE / f'{episode:02d}/creator-story-v01.json')
    matches = [s['capture'] for s in story['scenes'] if s.get('capture', {}).get('path', '').endswith('/' + key + '.png')]
    if len(matches) != 1:
        raise ValueError('Expected exactly one story capture')
    capture = matches[0]
    target = ROOT / capture['path']
    proof = ROOT / capture['proof']
    if target.exists() or proof.exists():
        load_capture(capture)
        raise ValueError('Keep previous crop; create a new version instead')
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as original:
        width, height = original.size
        left, top, right, bottom = box
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError('Crop outside source')
        context = source
        if original.format != 'PNG':
            context = target.with_name(key + '-context-decoded.png')
            original.save(context, format='PNG')
            with Image.open(context) as decoded:
                assert decoded.tobytes() == original.tobytes()
        original.crop(box).save(target, format='PNG')
        with Image.open(target) as crop:
            assert crop.tobytes() == original.crop(box).tobytes()
        actual_format = original.format
    save(proof, dict(origin='demonstration', product=capture['product'], phase=capture['phase'],
        title=capture['title'], artifact=record(target), context=record(context),
        captured_original=dict(record(source), actual_format=actual_format),
        clip=dict(x=left, y=top, width=right-left, height=bottom-top),
        context_clip=dict(x=0, y=0, width=width, height=height), captured_at=stamp.isoformat(),
        derived_at=datetime.now(timezone.utc).isoformat(), review_status='capture_review_passed',
        fictional_materials_only=True, personal_information_excluded=True,
        pixel_exact_crop_verified=True, content_modified=False, review_basis=review_basis,
        capture_method='Computer Use real cloud desktop; unchanged screenshot crop'))
    load_capture(capture)
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--episode', type=int, choices=[1, 2, 3], required=True)
    parser.add_argument('--key', required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--box', type=int, nargs=4, required=True)
    parser.add_argument('--captured-at', required=True)
    parser.add_argument('--review-basis', required=True,
        help='Record the actual visual inspection; do not assert review before opening source and crop')
    args = parser.parse_args()
    bind(args.episode, args.key, args.source, args.box, args.captured_at, args.review_basis)
