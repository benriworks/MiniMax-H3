"""Package a technically/visually checked candidate with truthful hearing status.

This explicit review-delivery route does not mark unavailable listening as passed.
It preserves the strict full-review route in the already frozen produce.py.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import zipfile

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('comparison_production', HERE / 'produce.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def package_review(output=None, state_path=None):
    out = output or p.current_output()
    state_path = state_path or p.STATE
    if out.resolve().parent != p.OUT_ROOT or (p.ROOT / p.read(state_path)['output']).resolve() != out.resolve():
        raise ValueError('Review output must match the selected comparison state')
    props = p.validate_preparation(out)
    proof = p.read(out / 'verification.json')
    p.check(proof['delivery'])
    review_path = out / 'visual-review.json'
    review = p.read(review_path)
    required = ['all_14_scenes_visually_reviewed', 'source_images_accurate_and_legible',
                'motion_intervals_and_summary_reviewed', 'no_private_content']
    if not all(review.get(field) is True for field in required):
        raise ValueError('Actual visual review is required')
    if review.get('narration_listened') is not False or not review.get('listening_limitation'):
        raise ValueError('This route must explicitly record hearing unavailable')
    if (proof.get('full_decode_verified') is not True or proof.get('source_audio_included') is not False
            or not -18 <= float(proof['loudness']['input_i']) <= -14
            or float(proof['loudness']['input_tp']) > -1):
        raise ValueError('Technical checks must pass before review delivery')
    preview = p.read(out / 'preview.json')
    for source in preview['sources'] + preview['images']:
        p.check(source)
    proof.update(review_status='technical_and_visual_passed_listening_pending', visual_review=p.record(review_path),
                 narration_listened=False, user_approved=False)
    p.save(out / 'verification.json', proof)
    note = '\n聴感について：この実行環境は音声入力に非対応のため実聴していません。発話のPCM一致・尺・配置・完全decode・音量は検証済みです。音声の読みと聞きやすさは利用者確認待ちです。\n'
    if '聴感について：' not in (out / 'README_JA.txt').read_text(encoding='utf-8'):
        with (out / 'README_JA.txt').open('a', encoding='utf-8') as handle:
            handle.write(note)
    page_path = out / 'index.html'
    page = page_path.read_text(encoding='utf-8')
    if '映像の目視と技術検査は合格。' not in page:
        page = page.replace('<details>', '<p>映像の目視と技術検査は合格。音声の読みと聞きやすさは利用者確認待ちです。</p><details>', 1)
    page_path.write_text(page, encoding='utf-8')
    delivery = out / 'delivery'
    delivery.mkdir(exist_ok=False)
    copies = {'shorts-creator.mp4': 'duet-vs-dots-3-differences.mp4', 'cover.png': 'cover.png',
              'captions.srt': 'captions.srt', 'title.txt': 'title.txt', 'description.txt': 'description.txt',
              'sources-public.json': 'sources.json', 'README_JA.txt': 'README_JA.txt'}
    for source, target in copies.items():
        shutil.copyfile(out / source, delivery / target)
    public_proofs = []
    for item in p.read(HERE / 'captures/manifest.json')['public_assets']:
        if not item.get('preferred'):
            continue
        source, original = p.check(item['artifact']), p.read(p.check(item['proof']))
        target = delivery / 'official-captures' / source.name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        public_proofs.append({'id': item['id'], 'scene_id': item['scene_id'], 'file': target.relative_to(delivery).as_posix(),
             'sha256': item['artifact']['sha256'], 'source_url': item['source_url'], 'title': item['title'],
             'captured_at': original['captured_at'], 'quote_words': item['quoted_words'], 'content_modified': False,
             'pixel_exact_crop_verified': True, 'personal_information_excluded': True})
    p.save(delivery / 'official-captures/provenance.json', public_proofs)
    p.save(delivery / 'verification-public.json', {'review_status': proof['review_status'], 'user_approved': False,
         'ai_assisted_visual_review': True, 'narration_listened': False, 'listening_status': 'pending_user_review',
         'full_decode_verified': True, 'original_speech_pcm_preserved': True,
         'width': 1080, 'height': 1920, 'fps': 24, 'seconds': props['durationInFrames'] / 24,
         'source_audio_included': False, 'loudness': proof['loudness'], 'private_context_excluded': True,
         's3_uploaded': False, 'youtube_uploaded': False})
    members = []
    for path in sorted(delivery.rglob('*')):
        if path.is_file():
            item = p.record(path)
            item['path'] = path.relative_to(delivery).as_posix()
            members.append(item)
    p.save(delivery / 'manifest.json', {'schema_version': 1, 'members': members, 'manifest_self_excluded': True})
    archive = out / 'comparison-delivery.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as target:
        for path in sorted(delivery.rglob('*')):
            if path.is_file():
                target.write(path, path.relative_to(delivery).as_posix())
    with zipfile.ZipFile(archive) as result:
        if result.testzip() is not None or set(result.namelist()) != {m['path'] for m in members} | {'manifest.json'}:
            raise ValueError('ZIP membership or CRC mismatch')
        for item in members:
            content = result.read(item['path'])
            if len(content) != item['bytes'] or hashlib.sha256(content).hexdigest().upper() != item['sha256']:
                raise ValueError('ZIP member hash mismatch')
    p.save(out / 'delivery-manifest.json', {'archive': p.record(archive),
         'video': p.record(delivery / copies['shorts-creator.mp4']), 'created_at': datetime.now(timezone.utc).isoformat(),
         'zip_members': len(members) + 1, 'zip_member_hashes_verified': True, 'private_context_excluded': True,
         'review_status': proof['review_status'], 'narration_listened': False, 's3_uploaded': False, 'youtube_uploaded': False})
    state = p.read(state_path)
    state['status'] = 'packaged_review_candidate_listening_pending'
    p.save(state_path, state)
    print(json.dumps({'event': 'review_candidate_packaged', 'output': str(out), 'archive': str(archive), 'narration_listened': False}))


if __name__ == '__main__':
    package_review()
