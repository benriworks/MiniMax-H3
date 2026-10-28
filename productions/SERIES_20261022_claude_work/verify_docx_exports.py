"""Read-only content checks of explicitly named fictional Claude DOCX exports.

This verifies the exported package and XML text, not Word-rendered appearance.
The source DOCX is never modified. Reports remain local production evidence.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / 'outputs/evidence/claude-work-20261022'
OUT = EVIDENCE / 'demonstration'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
PROFILES = {'01-docs-first.docx': 'first', '01-docs-revised.docx': 'revised',
            '01-docs-final.docx': 'final'}


def record(path):
    return {'path': path.relative_to(ROOT).as_posix(), 'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper()}


def text(element):
    return ''.join(t.text or '' for t in element.findall('.//w:t', NS))


def verify(name):
    if name not in PROFILES:raise ValueError('Unknown export/version; define its expected content explicitly')
    path = EVIDENCE / 'exports' / name
    original = record(path)
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        if corrupt:raise ValueError('DOCX has an invalid ZIP member CRC')
        document = ET.fromstring(archive.read('word/document.xml'))
        members = archive.namelist()
    paragraphs = [text(p) for p in document.findall('.//w:p', NS) if text(p)]
    joined = '\n'.join(paragraphs)
    rows = [[text(c) for c in row.findall('w:tc', NS)] for row in document.findall('.//w:tr', NS)]
    fields = {row[0]: row[1] for row in rows if len(row) == 2}
    budget_bold = any(text(run) == '3万円' and run.find('w:rPr/w:b', NS) is not None
                      for run in document.findall('.//w:r', NS))
    bullet_paragraphs = [text(p) for p in document.findall('.//w:p', NS)
                         if p.find('w:pPr/w:numPr', NS) is not None]
    profile = PROFILES[name]
    expected_purpose = ('平日午後の来店を増やす。' if profile == 'final'
                        else '平日午後に来店するきっかけを作る。')
    expected_numbers = {'1', '2', '3', '4', '5', '6', '650', '2026', '11', '10', '16', '14', '17'}
    numbers = re.findall(r'\d+', joined)
    checks = {
        'price_650_yen': fields.get('価格') == '650円',
        'budget_30000_yen': '告知予算：3万円' in paragraphs,
        'period_2026_11_10_to_11_16': fields.get('実施期間') == '2026年11月10日〜11月16日',
        'time_14_to_17': fields.get('提供時間') == '14時〜17時',
        'pastry_undecided': fields.get('焼き菓子の種類') == '未定',
        'targets_sales_discount_undecided': fields.get('目標来店数・売上予測・割引率') == '未定',
        'staff_assignment_still_pending': any('担当者の割り当て' in p for p in paragraphs),
        'purpose_matches_export_version': expected_purpose in paragraphs,
        'no_unexpected_numeric_tokens': set(numbers) <= expected_numbers,
    }
    if profile == 'first':
        checks.update(original_headings=('5. 予算' in paragraphs and '6. 未決定事項' in paragraphs),
                      initial_checkbox_list=all(any(p == '☐ ' + value for p in paragraphs)
                                               for value in ['焼き菓子の種類', '担当者の割り当て']),
                      initial_budget_not_bold=not budget_bold)
    else:
        checks.update(revised_headings=('5. 告知予算' in paragraphs and '6. これから決めること' in paragraphs),
                      budget_bold=budget_bold,
                      revised_bullet_list=all(value in bullet_paragraphs
                                             for value in ['焼き菓子の種類', '担当者の割り当て']),
                      checkbox_symbols_removed='☐' not in joined)
    if record(path) != original:raise ValueError('Source DOCX changed during inspection')
    output = OUT / (path.stem + '.content-check.json')
    result = {'schema_version': 1, 'checked_at': datetime.now(timezone.utc).isoformat(),
              'artifact': original, 'export_version': profile, 'zip_crc_passed': True,
              'zip_members': members, 'paragraphs': paragraphs, 'table_fields': fields,
              'numeric_tokens': numbers, 'checks': checks, 'content_checks_passed': all(checks.values()),
              'original_file_unchanged': True, 'review_method': 'Read-only ZIP/XML extraction and explicit input comparison',
              'word_rendered_appearance_verified': False, 'user_approved': False,
              'scope_note': '本文・数値・書式XMLの照合。Word等で開いた見た目の確認、利用者の採用、公開は別記録。'}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'file': name, 'content_checks_passed': result['content_checks_passed'],
                      'failed': [key for key, value in checks.items() if not value]}, ensure_ascii=False))
    if not result['content_checks_passed']:raise ValueError('Export content checks failed; inspect the saved report')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--files', nargs='+', required=True, choices=PROFILES)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for filename in args.files:verify(filename)
