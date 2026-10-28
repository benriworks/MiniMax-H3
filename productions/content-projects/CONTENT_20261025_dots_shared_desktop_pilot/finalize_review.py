"""Finalize an AI-inspected candidate; never marks human adoption or publication."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'outputs/content-projects' / HERE.name
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import check, package, read, record


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def finalize():
    final = OUT / 'delivery-v01.json'
    if final.exists():
        previous = read(final)
        for item in previous['videos']:
            check(item['video'])
            check(item['verification'])
        check(previous['article_pdf'])
        print('Existing reviewed candidates preserved; no output rewritten')
        return
    receipt = read(OUT / 'drive-readback-v01.json')
    drive = {f['id']: f for f in receipt['files']}
    # Private file/folder identifiers stay with local upload readback records.
    bindings = read(OUT / 'drive-review-bindings-v01.json')
    ids = bindings['video_file_ids']
    folder_id = bindings['folder_id']
    article_id = bindings['article_file_id']
    deliveries = []
    for episode, file_id in enumerate(ids, 1):
        destination = ROOT / read(OUT / f'render-state-{episode:02d}-v01.json')['output']
        proof = read(destination / 'verification.json')
        video = check(proof['delivery'])
        assert proof['full_decode_verified'] and not proof['user_approved']
        assert int(drive[file_id]['size']) == video.stat().st_size
        assert drive[file_id]['parent_ids'] == [folder_id]
        assert drive[file_id]['mime_type'] == 'video/mp4'
        for source in proof['sources']:
            check(source)
        original = destination / 'verification-technical-v01.json'
        if not original.exists():
            shutil.copyfile(destination / 'verification.json', original)
        frames = [destination / 'contact-sheet.png', *sorted(destination.glob('preview-*.png'))]
        review = dict(checked_at=datetime.now(timezone.utc).isoformat(),
            review_status='ai_visual_review_passed', inspected_artifacts=[record(p) for p in frames],
            basis='Operator inspected whole contact sheet and 360px scene samples; primary headings/captions, character separation and source-to-scene correspondence checked.',
            limitation='Fine UI table text is retained as evidence; full item-by-item reading uses article originals and data comparison, not a claim that all text is readable at phone width.',
            human_listening='pending', mobile_device_playback='pending', user_approved=False, published=False)
        write(destination / 'ai-review-v01.json', review)
        proof.update(review_status='verified_candidate_awaiting_user_review', ai_review=record(destination / 'ai-review-v01.json'),
            human_reviewed=False, user_approved=False, published=False)
        write(destination / 'verification.json', proof)
        if not (destination / 'shorts-creator-review.zip').exists():
            package(destination)
        story = read(destination / 'story.json')
        deliveries.append(dict(episode=episode, title=story['title'], seconds=story['duration_seconds'],
            video=record(video), verification=record(destination / 'verification.json'),
            drive_file_id=file_id, drive_url=drive[file_id]['url'],
            drive_upload_and_metadata_verified=True, drive_browser_playback='recorded separately',
            mobile_device_playback='pending', human_listening='pending', user_approved=False, published=False))
    cloud = OUT / 'cloud/v01/dots-desktop-pilot-20261025'
    checks = []
    for line in (cloud / 'MANIFEST_SHA256.txt').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        path = cloud / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == actual
        checks.append(dict(path=name, sha256=actual))
    assert len(checks) == 59
    comparisons = read(cloud / 'case-demo/gui_row_comparison.json')
    assert comparisons['equal'] and comparisons['actualRows'] == comparisons['workbookRows']
    cases = read(cloud / 'case-demo/registered-cases.json')
    assert len(cases) == 3 and sum(row['amount'] for row in cases) == 250000
    metrics = read(cloud / 'blender/variant_metrics.json')
    assert metrics['source_sha256_before'] == metrics['source_sha256_after']
    assert hashlib.sha256((cloud / 'blender/source_scene.blend').read_bytes()).hexdigest() == metrics['source_sha256_before']
    write(OUT / 'cloud-receipt-verification-v01.json', dict(verified_at=datetime.now(timezone.utc).isoformat(),
        archive=record(cloud.parent / 'dots-desktop-pilot-20261025.zip'), sha256_verified_members=checks,
        source_copy_matches_preservation_record=True, case_gui_comparison_record_matches=True,
        case_records=3, total_yen=250000, root_operator_reperformed_all_cloud_gui_steps=False))
    pdf = OUT / 'blog-handoff/v02/dots-cloud-desktop-article-v03.pdf'
    assert int(drive[article_id]['size']) == pdf.stat().st_size
    write(OUT / 'delivery-v01.json', dict(content_project_id=HERE.name, finalized_at=datetime.now(timezone.utc).isoformat(),
        review_folder='https://drive.google.com/drive/folders/' + folder_id,
        videos=deliveries, article_pdf=record(pdf), article_pdf_drive_url=drive[article_id]['url'],
        article_pdf_pages=8, article_pdf_ai_layout_review='passed', article_handoff_version=2,
        workspace_revision=53, s3_uploaded=False, human_reviewed=False, user_approved=False, published=False))
    print('3 candidates finalized; 59 cloud members verified; human review and publication remain pending')


if __name__ == '__main__':
    finalize()
