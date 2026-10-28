"""Lossless, explicitly planned crops of already captured fictional-work screens.

No UI control, AI image editing, resizing, monitoring, speech, or video rendering.
Create candidates, inspect their pixels, then record the separate crop review.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'outputs/evidence/claude-work-20261022'
PRIVATE = EVIDENCE / '_private'
OUT = EVIDENCE / 'demonstration'
PLAN = OUT / 'crop-plan.json'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def decoded_context(raw):
    """Keep original bytes; store identical decoded pixels as PNG when needed."""
    with Image.open(raw) as original:
        original_format = original.format
        if original_format == 'PNG':return raw, original_format
        if original_format != 'JPEG':raise ValueError('Unexpected screenshot encoding')
        target = PRIVATE / 'decoded-png' / raw.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():original.save(target, format='PNG')
        with Image.open(target) as converted:
            if converted.format != 'PNG' or converted.mode != original.mode or converted.size != original.size or converted.tobytes() != original.tobytes():
                raise ValueError('Context encoding conversion changed decoded pixels')
    return target, original_format


def context_fields(raw):
    context, original_format = decoded_context(raw)
    return {'context': record(context), 'raw_capture': record(raw), 'raw_capture_format': original_format,
            'context_encoding': {'method': 'original_png' if context == raw else 'JPEG_decoded_pixels_saved_as_lossless_PNG',
                                 'decoded_pixels_identical': True, 'original_bytes_preserved': True,
                                 'resized': False, 'ai_image_editing': False}}


def create(item):
    raw = PRIVATE / (item['raw'] + '.png')
    meta = raw.with_suffix('.json')
    metadata = read(meta)
    if metadata.get('product') != 'Claude' or metadata.get('fictional_materials_only') is not True:
        raise ValueError('Capture metadata must identify the fictional Claude demonstration')
    captured = datetime.fromisoformat(metadata['captured_at'].replace('Z', '+00:00'))
    if captured.utcoffset() is None:
        raise ValueError('Capture timestamp requires timezone')
    x, y, width, height = item['crop']
    if any(type(v) is not int for v in item['crop']) or min(x, y) < 0 or min(width, height) <= 0:
        raise ValueError('Use explicit integer crop coordinates')
    image_path = OUT / (item['id'] + '.png')
    proof_path = image_path.with_suffix('.json')
    contexts = context_fields(raw)
    with Image.open(raw) as original:
        if original.size != (metadata['width'], metadata['height']) or x + width > original.width or y + height > original.height:
            raise ValueError('Crop exceeds its unchanged original screenshot')
        cropped = original.crop((x, y, x + width, y + height))
        if image_path.exists():
            with Image.open(image_path) as previous:
                if previous.size != cropped.size or previous.mode != cropped.mode or previous.tobytes() != cropped.tobytes():
                    raise ValueError('An existing crop differs; assign a new candidate ID')
            proof = read(proof_path)
            if proof['context'] != contexts['context'] or proof['raw_capture'] != contexts['raw_capture'] or proof['raw_metadata'] != record(meta) or proof['artifact'] != record(image_path):
                raise ValueError('Existing capture evidence changed')
            return
        cropped.save(image_path, format='PNG')
        with Image.open(image_path) as saved:
            if saved.mode != cropped.mode or saved.tobytes() != cropped.tobytes():
                raise ValueError('Saved image is not a pixel-exact rectangular crop')
    proof = {
        'schema_version': 1, 'origin': 'demonstration', 'product': 'Claude', 'phase': item['phase'],
        'title': item['title'], 'artifact': record(image_path), **contexts,
        'raw_metadata': record(meta), 'clip': {'x': x, 'y': y, 'width': width, 'height': height},
        'context_clip': {'x': 0, 'y': 0, 'width': metadata['width'], 'height': metadata['height']},
        'captured_at': metadata['captured_at'], 'fictional_materials_only': True,
        'personal_information_excluded': False, 'review_status': 'awaiting_crop_review',
        'operation': 'lossless_rectangular_crop_only', 'content_modified': False,
        'ai_image_editing': False, 'pixel_exact_crop_verified': True,
        'source_captured_by': 'parent agent using Claude application UI',
        'root_visual_review_status': 'pending', 'user_approved': False,
        'scope_note': item['scope_note'],
    }
    if item.get('comparison_pair'):
        proof['comparison_pair'] = item['comparison_pair']
    if metadata.get('viewer'):
        proof['external_viewer'] = metadata['viewer']
        proof['exported_artifact'] = record(ROOT / metadata['source_file'])
        proof['viewer_protected_view_retained'] = metadata.get('protected_view_retained') is True
        proof['source_captured_by'] = 'parent agent opening the product export in the named external viewer'
    save(proof_path, proof)


def normalize_contexts(items):
    history = OUT / 'proof-history' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for item in items:
        proof_path = OUT / (item['id'] + '.json')
        proof = read(proof_path)
        raw = PRIVATE / (item['raw'] + '.png')
        if proof.get('raw_capture'):
            if proof['raw_capture'] != record(raw):raise ValueError('Original screenshot changed')
        elif proof['context'] != record(raw):raise ValueError('Previous original context changed')
        if proof['artifact'] != record(OUT / (item['id'] + '.png')) or proof['raw_metadata'] != record(raw.with_suffix('.json')):
            raise ValueError('Crop or metadata changed before context normalization')
        contexts = context_fields(raw)
        if all(proof.get(key) == value for key, value in contexts.items()):continue
        history.mkdir(parents=True, exist_ok=True)
        previous = history / proof_path.name
        previous.write_bytes(proof_path.read_bytes())
        proof.update(contexts)
        proof['previous_context_proof'] = record(previous)
        save(proof_path, proof)


def review(identifier, note):
    if not note or not note.strip():
        raise ValueError('A concrete visual/privacy inspection note is required')
    proof_path = OUT / (identifier + '.json')
    proof = read(proof_path)
    for key in ['artifact', 'context', 'raw_metadata', 'raw_capture'] + (['exported_artifact'] if proof.get('exported_artifact') else []):
        if record(ROOT / proof[key]['path']) != proof[key]:
            raise ValueError('Evidence changed after cropping')
    proof.update(review_status='capture_review_passed', personal_information_excluded=True,
                 review_method='AI-assisted inspection of original screenshot and exact crop',
                 reviewed_by='batch_production subagent', review_note=note,
                 reviewed_at=datetime.now(timezone.utc).isoformat())
    save(proof_path, proof)


def manifest():
    captures = []
    for item in read(PLAN)['crops']:
        path = OUT / (item['id'] + '.json')
        if path.exists():
            proof = read(path)
            captures.append({'id': item['id'], 'phase': proof['phase'], 'title': proof['title'],
                             'image': proof['artifact'], 'proof': record(path),
                             'review_status': proof['review_status'],
                             'root_visual_review_status': proof['root_visual_review_status']})
    result = {'schema_version': 1, 'product': 'Claude',
                                'created_at': datetime.now(timezone.utc).isoformat(),
                                'crop_only': True, 'ai_image_editing': False,
                                'root_visual_review_status': 'pending', 'captures': captures}
    operations = OUT / 'operations.json'
    if operations.exists():result['operations_record'] = record(operations)
    result['export_content_checks'] = [record(path) for path in sorted(OUT.glob('*.content-check.json'))]
    save(OUT / 'manifest.json', result)


def audit():
    results, pairs = [], {}
    for item in read(PLAN)['crops']:
        proof_path = OUT / (item['id'] + '.json')
        proof = read(proof_path)
        for key in ['artifact', 'context', 'raw_metadata', 'raw_capture'] + (['exported_artifact'] if proof.get('exported_artifact') else []):
            if record(ROOT / proof[key]['path']) != proof[key]:raise ValueError('Evidence hash changed')
        metadata = read(ROOT / proof['raw_metadata']['path'])
        if proof['captured_at'] != metadata['captured_at']:raise ValueError('Capture time changed')
        if proof['phase'] != item['phase'] or proof['title'] != item['title']:raise ValueError('Plan and proof differ')
        if proof['review_status'] != 'capture_review_passed' or proof['personal_information_excluded'] is not True:
            raise ValueError('Every included crop needs its individual visual/privacy review')
        if 'http://' in json.dumps(proof) or 'https://' in json.dumps(proof):raise ValueError('No URLs in demonstration evidence')
        rect = proof['clip']
        if [rect[k] for k in ['x', 'y', 'width', 'height']] != item['crop']:raise ValueError('Crop plan changed')
        with Image.open(ROOT / proof['context']['path']) as raw, Image.open(ROOT / proof['artifact']['path']) as crop:
            with Image.open(ROOT / proof['raw_capture']['path']) as original:
                if raw.format != 'PNG' or raw.mode != original.mode or raw.size != original.size or raw.tobytes() != original.tobytes():
                    raise ValueError('PNG context differs from decoded original screenshot pixels')
            expected = raw.crop((rect['x'], rect['y'], rect['x'] + rect['width'], rect['y'] + rect['height']))
            if crop.mode != expected.mode or crop.size != expected.size or crop.tobytes() != expected.tobytes():
                raise ValueError('Image is no longer the pixel-exact rectangular crop')
        pair = proof.get('comparison_pair')
        if pair:
            if pair in pairs and pairs[pair] != rect:raise ValueError('Before/after crop rectangles differ')
            pairs[pair] = rect
        results.append({'id': item['id'], 'pixel_exact_crop': True, 'raw_and_metadata_unchanged': True,
                        'proof': record(proof_path), 'root_visual_review_status': proof['root_visual_review_status']})
    result = {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'manifest': record(OUT / 'manifest.json'), 'passed': True, 'crops': results,
              'comparison_rectangles': pairs, 'count': len(results), 'ai_image_editing': False,
              'root_review_passed_count': sum(r['root_visual_review_status'] == 'passed' for r in results),
              'video_readability_review': 'pending', 'user_approved': False}
    save(OUT / 'audit.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create', 'review', 'audit', 'normalize-contexts'])
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--note')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    items = read(PLAN)['crops']
    if args.ids:
        selected = set(args.ids)
        if selected - {item['id'] for item in items}:
            raise ValueError('Unknown explicit crop ID')
        items = [item for item in items if item['id'] in selected]
    if args.command == 'create':
        for item in items:create(item)
    elif args.command == 'normalize-contexts':normalize_contexts(items)
    elif args.command == 'review':
        if not args.ids:raise ValueError('Explicit IDs are required after viewing each crop')
        for item in items:review(item['id'], args.note)
    manifest()
    if args.command == 'audit':audit()
    print(json.dumps({'processed': len(items), 'command': args.command, 'ai_image_editing': False}))


if __name__ == '__main__':main()
