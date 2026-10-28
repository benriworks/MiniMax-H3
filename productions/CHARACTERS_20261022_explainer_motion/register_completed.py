"""Bind reviewed motion outputs into character registries; never edit proofs."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/characters/explainer-motion-20261022'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}

def checked(item):
    path = ROOT/item['path']
    actual = record(path)
    if actual['bytes'] != item['bytes'] or actual['sha256'] != item['sha256']:
        raise ValueError('Asset hash changed: ' + item['path'])
    return actual

def save(path, value):
    temporary = path.with_suffix(path.suffix + '.motion-tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    temporary.replace(path)

entries = {}
for job in ['dots-male','dots-female','claude-shiori','codex-makoto','duet-dots-haruka']:
    path = OUT/job/'verification.json'
    proof = read(path)
    if (proof['review_status'] != 'visual_review_passed' or not proof['execution']['success']
            or not proof['artifact']['full_decode_verified'] or proof['provider'] != 'minimax'):
        raise ValueError('Motion is not reviewed: ' + job)
    entries[job] = {
        'provider': 'minimax', 'mode': 'local_h3_i2va',
        'generation_context': proof['generation_context'],
        'video': checked(proof['artifact']), 'proof': record(path),
        'source_presenter': checked(proof['source_presenter']),
        'source_keyframe': checked(proof['source_keyframe']),
        'width': 768, 'height': 1376, 'fps': 24, 'frames': 124,
        'start_frame': 0, 'review_status': 'visual_review_passed', 'user_approved': False,
        'usage': 'Muted visual character segment; Aoede is the single narrator',
    }

registry = ROOT/'productions/characters/motion-registry-20261022.json'
save(registry, {'schema_version':1, 'updated_at':datetime.now(timezone.utc).isoformat(),
                'clips':entries, 'status_note':'AI visual and technical verification complete; user acceptance remains separate.'})
duo_path = ROOT/'productions/characters/programmer-duo/reference-assets.json'
duo = read(duo_path)
duo['motion_references_20261022'] = {key:entries['dots-'+key] for key in ['male','female']}
save(duo_path, duo)
business_path = ROOT/'productions/characters/business-guides-20261022/characters.json'
business = read(business_path)
for character in business['characters']:
    character['motion_status'] = 'visual_review_passed'
    character['motion'] = entries[character['id']]
save(business_path, business)
print(json.dumps({'updated':[str(registry),str(duo_path),str(business_path)],'clips':len(entries),'proofs_modified':False}))
