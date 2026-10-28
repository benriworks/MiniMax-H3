"""Crop explicitly planned regions from verified native PNG captures.

Original screens, earlier compressed crops and the original crop plan stay intact.
No resizing, content edits, UI control, API calls, or automatic visual approval.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import load_capture
EVIDENCE = ROOT / 'outputs/evidence/claude-work-20261022'
OUT = EVIDENCE / 'demonstration'
PRIVATE = EVIDENCE / '_private'
PLAN = OUT / 'native-crop-plan.json'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def create(item):
    raw = PRIVATE / (item['raw'] + '.png')
    meta = raw.with_suffix('.json')
    data = read(meta)
    raw_record = record(raw)
    if (data.get('product') != 'Claude' or data.get('fictional_materials_only') is not True
            or data.get('format') != 'PNG' or data.get('sha256') != raw_record['sha256']):
        raise ValueError('Expected recorded unmodified native fictional Claude PNG')
    if datetime.fromisoformat(data['captured_at'].replace('Z', '+00:00')).utcoffset() is None:
        raise ValueError('Timestamp requires timezone')
    x, y, width, height = item['crop']
    if any(type(v) is not int for v in item['crop']) or min(x, y) < 0 or min(width, height) <= 0:
        raise ValueError('Invalid crop coordinates')
    image_path = OUT / (item['id'] + '.png')
    proof_path = image_path.with_suffix('.json')
    with Image.open(raw) as original:
        if original.format != 'PNG' or original.size != (data['width'], data['height']) or x + width > original.width or y + height > original.height:
            raise ValueError('Original format/dimensions or crop bounds differ')
        crop = original.crop((x, y, x + width, y + height))
        if image_path.exists():
            with Image.open(image_path) as previous:
                if previous.mode != crop.mode or previous.size != crop.size or previous.tobytes() != crop.tobytes():
                    raise ValueError('Use a new ID rather than replacing a previous crop')
            old = read(proof_path)
            if old['context'] != raw_record or old['raw_metadata'] != record(meta):
                raise ValueError('Existing capture provenance changed')
            return
        crop.save(image_path, format='PNG')
    proof = {'schema_version': 1, 'origin': 'demonstration', 'product': 'Claude',
             'phase': item['phase'], 'title': item['title'], 'artifact': record(image_path),
             'context': raw_record, 'raw_capture': raw_record, 'raw_metadata': record(meta),
             'raw_capture_format': 'PNG', 'viewer': data.get('viewer', 'Claude Desktop'),
             'clip': {'x': x, 'y': y, 'width': width, 'height': height},
             'context_clip': {'x': 0, 'y': 0, 'width': data['width'], 'height': data['height']},
             'captured_at': data['captured_at'], 'fictional_materials_only': True,
             'personal_information_excluded': False, 'content_modified': False,
             'operation': 'lossless_rectangular_crop_only', 'ai_image_editing': False,
             'pixel_exact_crop_verified': True, 'review_status': 'awaiting_crop_review',
             'root_visual_review_status': 'pending', 'user_approved': False,
             'source_captured_by': 'parent agent using DPI-aware native PNG screenshot capture',
             'scope_note': item['scope_note']}
    source_file = data.get('source_file') or item.get('source_file')
    if source_file:
        proof['exported_artifact'] = record(ROOT / source_file)
        proof['external_viewer'] = data['viewer']
        proof['export_binding_source'] = ('capture_metadata' if data.get('source_file') else 'parent_capture_handoff')
        proof['protected_view_retained'] = item.get('protected_view_retained', False)
    save(proof_path, proof)

def verify(item, require_review=True):
    proof_path = OUT / (item['id'] + '.json')
    proof = read(proof_path)
    for key in ['artifact', 'context', 'raw_capture', 'raw_metadata'] + (['exported_artifact'] if proof.get('exported_artifact') else []):
        if record(ROOT / proof[key]['path']) != proof[key]:
            raise ValueError('Evidence changed: ' + item['id'])
    with Image.open(ROOT / proof['context']['path']) as original, Image.open(ROOT / proof['artifact']['path']) as crop:
        x, y, width, height = item['crop']
        expected = original.crop((x, y, x + width, y + height))
        if original.format != 'PNG' or crop.format != 'PNG' or crop.size != expected.size or crop.mode != expected.mode or crop.tobytes() != expected.tobytes():
            raise ValueError('Crop is not the exact native screenshot rectangle')
    if require_review:
        capture = {'origin': 'demonstration', 'product': 'Claude', 'phase': proof['phase'], 'title': proof['title'],
                   'path': proof['artifact']['path'], 'proof': proof_path.relative_to(ROOT).as_posix()}
        load_capture(capture)
    return proof

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create', 'review', 'audit'])
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--note')
    args = parser.parse_args()
    items = read(PLAN)['crops']
    selected = [i for i in items if not args.ids or i['id'] in args.ids]
    if args.ids and set(args.ids) - {i['id'] for i in items}:
        raise ValueError('Unknown native capture ID')
    if args.command == 'review' and (not args.ids or not args.note):
        raise ValueError('Review requires explicit inspected IDs and a concrete note')
    for item in selected:
        if args.command == 'create':
            create(item)
        elif args.command == 'review':
            proof = verify(item, require_review=False)
            proof.update(review_status='capture_review_passed', personal_information_excluded=True,
                         review_method='AI-assisted actual native screen and crop inspection plus pixel-exact comparison',
                         reviewed_by='episode_visuals subagent', review_note=args.note,
                         reviewed_at=datetime.now(timezone.utc).isoformat())
            save(OUT / (item['id'] + '.json'), proof)
        else:
            verify(item)
    captures = []
    for item in items:
        proof_path = OUT / (item['id'] + '.json')
        if proof_path.exists():
            proof = read(proof_path)
            captures.append({'id': item['id'], 'title': proof['title'], 'phase': proof['phase'],
                             'image': proof['artifact'], 'proof': record(proof_path), 'review_status': proof['review_status']})
    save(OUT / 'native-manifest.json', {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
         'captures': captures, 'lossless_native_contexts': True, 'original_assets_preserved': True,
         'private_context_excluded_from_delivery': True, 'user_approved': False})
    print(json.dumps({'processed': len(selected), 'command': args.command, 'native_png_only': True}))

if __name__ == '__main__':
    main()
