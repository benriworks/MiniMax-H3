"""Inspect the genuine Claude PPTX export without altering any source bytes.

ZIP/XML checks establish content and file provenance, not PowerPoint appearance.
The parent separately opens the downloaded artifact in PowerPoint for review.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'outputs/evidence/claude-work-20261022'
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def verify():
    path = EVIDENCE / 'exports/02-slides-revised.pptx'
    original = record(path)
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise ValueError('PPTX member CRC mismatch')
        members = archive.namelist()
        if len(set(members)) != len(members):
            raise ValueError('Duplicate PPTX package members')
        parsed = {name: ET.fromstring(archive.read(name)) for name in members
                  if name.endswith(('.xml', '.rels'))}
        relationships = {r.attrib['Id']: r.attrib for r in parsed['ppt/_rels/presentation.xml.rels']}
        slides = []
        for item in parsed['ppt/presentation.xml'].findall('p:sldIdLst/p:sldId', NS):
            relationship = relationships[item.attrib['{' + NS['r'] + '}id']]
            if relationship.get('TargetMode') == 'External':
                raise ValueError('Slides must be embedded in the genuine export')
            member = posixpath.normpath(posixpath.join('ppt', relationship['Target']))
            if not re.fullmatch(r'ppt/slides/slide\d+\.xml', member):
                raise ValueError('Unexpected slide target')
            document = parsed[member]
            slides.append({'member': member,
                           'text': [node.text or '' for node in document.findall('.//a:t', NS)],
                           'explicit_fonts': sorted({node.attrib['typeface'] for node in document.iter()
                                                     if 'typeface' in node.attrib})})
        notes = {name: [node.text or '' for node in document.findall('.//a:t', NS)]
                 for name, document in parsed.items() if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', name)}
    joined = ['\n'.join(s['text']) for s in slides]
    all_text = '\n'.join(joined)
    notes_text = '\n'.join('\n'.join(values) for values in notes.values())
    checks = {
        'five_embedded_slides_in_presentation_order': len(slides) == 5,
        'price_650_yen': len(joined) > 2 and '650円' in joined[2],
        'budget_30000_yen': len(joined) > 4 and '3万円' in joined[4],
        'revised_year_and_date_separate_runs': len(joined) > 3 and '2026年' in slides[3]['text'] and '11月10日〜11月16日' in slides[3]['text'],
        'time_14_to_17': len(joined) > 3 and '14時〜17時' in joined[3],
        'announcement_channels_preserved': len(joined) > 3 and '店内掲示・自社SNS' in joined[3],
        'pastry_and_staff_remain_undecided': len(slides) > 4 and all(value in slides[4]['text'] for value in ['焼き菓子の種類', '担当者の割り当て']) and slides[4]['text'].count('未定') == 2,
        'unset_targets_preserved_in_speaker_notes': '目標来店数・売上予測・割引率は未設定。' in notes_text,
        'purpose_matches_post_partial_edit': len(joined) > 1 and '平日午後の来店を増やす' in joined[1],
        'explicit_slide_fonts_are_arial': all(s['explicit_fonts'] == ['Arial'] for s in slides),
        'no_invented_numeric_tokens': set(re.findall(r'\d+', all_text)) <= {'02', '03', '04', '05', '2', '3', '4', '5', '650', '2026', '11', '10', '16', '14', '17'},
    }
    if record(path) != original:
        raise ValueError('Source PPTX changed during inspection')
    raw = EVIDENCE / '_private/05-slides-export-menu-native.png'
    meta = EVIDENCE / '_private/05-slides-export-menu-native.json'
    result = {
        'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
        'artifact': original, 'export_version': 'current_revised_slides_after_schedule_edit',
        'provenance': {'product': 'Claude', 'feature': 'Slides PowerPoint export',
                       'export_option': 'PowerPoint basic fonts',
                       'reported_saved_at': '2026-10-22T16:05:00Z', 'saved_time_precision': 'minute',
                       'save_observation_source': 'Parent agent witnessed a normal Save dialog and completion; no new permission prompt.',
                       'reported_font_substitution': 'Noto Sans JP to Arial (basic fonts)',
                       'native_export_menu': record(raw), 'native_export_menu_metadata': record(meta),
                       'fictional_materials_only': True},
        'zip_crc_passed': True, 'all_xml_parsed': True, 'zip_member_count': len(members),
        'slides': slides, 'speaker_notes': notes, 'checks': checks,
        'content_checks_passed': all(checks.values()), 'original_file_unchanged': True,
        'review_method': 'Read-only CRC, presentation relationship order, XML text/font and stated input checks',
        'powerpoint_rendered_appearance_verified': False, 'user_approved': False,
        'scope_notes': ['Slide text explicitly uses Arial; actual Japanese font fallback and appearance require native PowerPoint inspection.',
                        'Unset visitor/sales/discount targets survive in slide 5 speaker notes, not the visible slide body.',
                        'This is the revised deck. It is not evidence of the original pre-revision layout.'],
    }
    output = EVIDENCE / 'demonstration/02-slides-revised.content-check.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': output.relative_to(ROOT).as_posix(),
                      'content_checks_passed': result['content_checks_passed'],
                      'failed': [key for key, value in checks.items() if not value]}))
    if not result['content_checks_passed']:
        raise ValueError('Inspect the saved failed content checks before continuing')


if __name__ == '__main__':
    verify()
