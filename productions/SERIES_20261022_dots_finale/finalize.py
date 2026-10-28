"""Independently audit the five packaged presenter episodes, then write summaries.

Run only after all five state.json records say packaged. No paid service,
upload, credential lookup, speech generation, or rendering is performed.
"""
from datetime import datetime, timezone
from pathlib import Path
import copy
import hashlib
import json
import re
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import (
    audio_signature, check, load_supplied_narration, narration_inputs, read, record,
)

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
EXPECTED_NAMES = {'cover.png', 'captions.srt', 'youtube-title.txt', 'youtube-description.txt',
                  'narration.txt', 'SOURCES_JA.md', 'quality-report.json', 'index.html', 'manifest.json'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex[:8])
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def run(*args):
    return subprocess.run(list(map(str, args)), check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, creationflags=FLAGS).stdout


def audio_hash(path):
    return run('ffmpeg', '-v', 'error', '-nostdin', '-i', path, '-map', '0:a:0',
               '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-').decode().strip()


def verify_package(delivery, release):
    video = check(delivery['video'])
    archive = check(delivery['archive'])
    require(video.parent == release, 'Public MP4 is outside its recorded release')
    expected = EXPECTED_NAMES | {video.name}
    require({p.name for p in release.iterdir()} == expected, 'Unexpected public release content')
    manifest = read(release / 'manifest.json')
    require(set(manifest) == expected - {'manifest.json'}, 'Public manifest members differ')
    with zipfile.ZipFile(archive) as z:
        require(len(z.namelist()) == 10 and set(z.namelist()) == expected, 'ZIP members differ')
        require(z.testzip() is None, 'ZIP CRC failure')
        require(z.read('manifest.json') == (release / 'manifest.json').read_bytes(), 'ZIP manifest differs')
        for name, item in manifest.items():
            blob = z.read(name)
            require(blob == (release / name).read_bytes(), 'ZIP member differs from release: ' + name)
            require(len(blob) == item['bytes'] and hashlib.sha256(blob).hexdigest().upper() == item['sha256'],
                    'ZIP member size or hash differs: ' + name)
    return video, archive


def verify_episode(number, state):
    here = HERE / f'{number:02d}'
    out = (ROOT / state['output']).resolve(strict=True)
    require(out.parent == ROOT / f'outputs/productions/SHORT_20261022_dots_{number:02d}_editorial',
            'Unexpected episode output directory')
    delivery = read(here / 'delivery.json')
    require(delivery == read(out / 'delivery.json'), 'Latest delivery pointer differs from output record')
    release = (ROOT / delivery['release']).resolve(strict=True)
    require(release == out / 'release', 'Latest release pointer differs from active state')
    video, archive = verify_package(delivery, release)
    proof = read(out / 'verification.json')
    require(record(video)['sha256'] == record(check(proof['delivery']))['sha256'], 'Packaged MP4 differs from verified MP4')
    require(proof['review_status'] == 'verified_candidate_awaiting_user_review', 'Episode lacks completed visual review')
    require(proof.get('full_decode_verified') is True and proof.get('on_screen_tool_credit') is False,
            'Technical decode or credit policy is unverified')
    quality = read(release / 'quality-report.json')
    require(quality == delivery['quality'], 'Release quality record differs')
    require(quality['user_approved'] is False and quality['youtube_uploaded'] is False
            and quality['final_listening_review'] == 'pending', 'User review/publication status changed unexpectedly')

    probe = json.loads(run('ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', video))
    require(len(probe['streams']) == 2, 'Expected one video and one audio stream')
    v, a = probe['streams']
    require((v['codec_name'], v['width'], v['height'], v['avg_frame_rate'], int(v['nb_frames']))
            == ('h264', 1080, 1920, '24/1', 720), 'Current MP4 video format differs')
    require((a['codec_name'], a['sample_rate'], a['channels']) == ('aac', '48000', 2), 'Current MP4 audio format differs')
    require(abs(float(probe['format']['duration']) - 30) < .002, 'Current MP4 is not 30 seconds')
    require(proof['probe']['streams'][0]['nb_frames'] == v['nb_frames'], 'Technical frame evidence differs')
    loudness = proof['loudness']
    require(-18 <= float(loudness['input_i']) <= -14 and float(loudness['input_tp']) <= -1,
            'Measured completed audio fails loudness/peak bounds')

    preparation = read(out / 'preparation.json')
    render = read(out / 'render.json')
    for item in preparation['sources'] + render['sources']:
        check(item)
    review = proof.get('visual_review', {})
    evidence = [check(item) for item in review.get('evidence', [])]
    require(review.get('method') == 'AI-assisted visual inspection' and bool(review.get('note')),
            'Concrete completed visual-review note is missing')
    require(set(evidence) == {out / f'preview-{i:02d}.png' for i in range(7)} | {out / 'contact-sheet.png'},
            'Visual evidence does not cover all seven scenes and the contact sheet')
    check(proof['fact_review']['sources'])

    generation = (ROOT / state['generation']).resolve(strict=True)
    plan = read(generation / 'plan.json')
    require(check(plan['story']) == here / 'creator-story.json', 'Frozen source story changed')
    original = read(here / 'creator-story.json')
    voice, _ = load_supplied_narration(original, generation / 'voice-source.json')
    require(voice['voice'] == 'Aoede' and voice['model'] == 'gemini-2.5-flash-preview-tts', 'Voice/model changed')
    require(len(voice['generation_proofs']) == 7, 'Expected seven verified speech segments')
    require(voice.get('actual_billing_known') is False, 'Unknown actual billing must remain explicit')
    original_files = [record(check(item)) for item in plan['existing_deliveries']]
    require(len(original_files) == 12, 'Expected twelve protected earlier videos')

    revision = read(check(state['visual_revision']))
    require(revision['output'] == state['output'] and revision['additional_tts_requests'] == 0,
            'Visual revision output or new speech-call count differs')
    for key in ['original_story', 'render_story', 'presenter', 'presenter_proof', 'previous_state', 'narration_source']:
        check(revision[key])
    for item in revision['preserved_files']:
        check(item)
    if revision.get('previous_delivery'):
        check(revision['previous_delivery'])
    render_story = read(check(state['render_story']))
    require(render_story == read(out / 'story.json'), 'Rendered story differs from frozen visual revision')
    stripped = copy.deepcopy(render_story)
    for scene in stripped['scenes']:
        scene.pop('presenter', None)
    require(stripped == original and narration_inputs(render_story) == narration_inputs(original)
            and audio_signature(render_story) == audio_signature(original), 'Visual-only revision changed narration or story')

    props = read(out / 'props.json')
    timings = read(out / 'timings.json')['segments']
    require(len(props['scenes']) == 7 and len(timings) == 7 and props['durationInFrames'] == 720,
            'Scene count/timeline differs')
    cursor = 0
    for index, (scene, timing) in enumerate(zip(props['scenes'], timings, strict=True)):
        require(scene['from'] == cursor and 24 <= scene['duration'] <= 192, 'Scene coverage mismatch')
        start_ms = scene['from'] * 1000 / 24
        end_ms = (scene['from'] + scene['duration']) * 1000 / 24
        require(start_ms - 1 <= timing['start_ms'] < timing['end_ms'] <= end_ms + 1,
                'A speech segment is outside its scene window')
        require(timing['text'] == original['scenes'][index]['narration'], 'Completed speech text changed')
        cursor += scene['duration']
    require(cursor == 720, 'Scene coverage is not 720 frames')

    source_scenes = [(index, scene) for index, scene in enumerate(render_story['scenes']) if scene['kind'] == 'source']
    require(len(source_scenes) == 1, 'Expected one official excerpt per episode')
    capture_records = []
    for index, scene in source_scenes:
        capture = scene['capture']
        capture_proof_path = ROOT / capture['proof']
        capture_proof = read(capture_proof_path)
        require(capture_proof['review_status'] == 'capture_review_passed'
                and capture_proof['source_url'] == capture['source_url'], 'Official excerpt proof/source differs')
        capture_file = check(capture_proof['artifact'])
        check(capture_proof['context'])
        require(capture_file == ROOT / capture['path'], 'Captured image path differs')
        staged = out / 'public' / props['scenes'][index]['capture']['image']
        require(record(staged)['sha256'] == record(capture_file)['sha256'], 'Staged official excerpt changed')
        require('presenter' not in scene and 'presenter' not in props['scenes'][index], 'Presenter overlaps a source scene')
        capture_records.append(record(capture_proof_path))

    presenter_indices = [index for index, scene in enumerate(props['scenes']) if scene.get('presenter')]
    require(presenter_indices == [0, 6], 'Presenter is not limited to opening and closing')
    presenter_file = check(revision['presenter'])
    character_proof = read(check(revision['presenter_proof']))
    require(check(character_proof['artifact']) == presenter_file and character_proof['review_status'] == 'visual_review_passed'
            and character_proof['source_type'] == 'generated_humanoid' and character_proof['transparent'] is True,
            'Human presenter proof is invalid')
    for index, role in [(0, 'hook'), (6, 'recap')]:
        presenter = props['scenes'][index]['presenter']
        require(presenter['role'] == role and props['scenes'][index]['kind'] == 'editorial', 'Presenter role differs')
        require(record(out / 'public' / presenter['image'])['sha256'] == record(presenter_file)['sha256'], 'Staged presenter image changed')

    current_audio_hash = audio_hash(video)
    audio_identical = False
    if number in [5, 6, 7, 8]:
        require(revision['audio_method'] == 'previous_aac_stream_copy', 'Expected previous audio reuse')
        reuse = proof['audio_reuse']
        prior_video = check(reuse['source_delivery'])
        require(reuse['identical_audio_verified'] is True and current_audio_hash == audio_hash(prior_video)
                and current_audio_hash == reuse['packet_hash'], 'Independent AAC stream hash comparison failed')
        require(len(revision['preserved_files']) >= 3, 'Previous raw MP4, public MP4, and ZIP are not all preserved')
        audio_identical = True
    else:
        require(revision['audio_method'] == 'saved_verified_pcm_source', 'Episode 9 must use saved verified speech')

    submissions = []
    for path in sorted(generation.glob('scene-*/*/submission.json')):
        submission = read(path)
        require(submission.get('automatic_retry') is False, 'Automatic TTS retry appeared')
        require(submission['status'] in ['received_and_verified', 'unknown'], 'Unresolved or rejected submission in final generation')
        submissions.append({'record': record(path), 'status': submission['status']})
    verified = sum(item['status'] == 'received_and_verified' for item in submissions)
    unknown = sum(item['status'] == 'unknown' for item in submissions)
    require(verified == 7 and unknown == (1 if number == 9 else 0), 'Independent submission-marker count differs')
    require(voice['external_api_calls'] == verified + unknown, 'Voice-source total omits a submission')
    require(voice.get('verified_requests', verified) == verified and voice.get('unknown_previous_requests', 0) == unknown,
            'Voice-source verified/unknown count differs')
    if unknown:
        recovery_path = generation / 'manual-recovery.json'
        recovery = read(recovery_path)
        require(recovery['previous_unknown_requests'] == 1 and recovery['manual_replacement_requests_authorized'] == 1
                and recovery['automatic_retry'] is False and bool(recovery['reason']), 'Manual recovery evidence is invalid')
        require(record(recovery_path) == voice['manual_recovery'], 'Manual recovery hash differs')

    return {'episode': number, 'title': (release / 'youtube-title.txt').read_text(encoding='utf-8').strip(),
            'state': record(here / 'state.json'), 'delivery': record(here / 'delivery.json'),
            'video': record(video), 'archive': record(archive), 'cover': record(release / 'cover.png'),
            'release': release.relative_to(ROOT).as_posix(), 'verification': record(out / 'verification.json'),
            'zip_members': 10, 'duration_seconds': 30, 'frames': 720,
            'speech_segments': 7, 'speech_fits_scene_windows': True, 'official_captures': capture_records,
            'presenter': record(presenter_file), 'presenter_scenes': presenter_indices,
            'independent_audio_packet_hash': current_audio_hash, 'previous_audio_identical': audio_identical,
            'visual_revision_additional_tts_requests': 0, 'visual_revision_additional_tts_characters': 0,
            'verified_speech_requests': verified,
            'unknown_previous_requests': unknown, 'submission_records': submissions,
            'loudness_lufs': float(loudness['input_i']), 'true_peak_dbfs': float(loudness['input_tp']),
            'preserved_original_videos': original_files, 'preserved_previous_revision_files': revision['preserved_files']}


def main():
    states = {n: read(HERE / f'{n:02d}' / 'state.json') for n in range(5, 10)}
    require(all(state['status'] == 'packaged' for state in states.values()), 'All five latest episodes must be packaged before finalizing')
    episodes = []
    for number, state in states.items():
        episodes.append(verify_episode(number, state))
        print(json.dumps({'event': 'episode_audit_passed', 'episode': number}), flush=True)
    originals = episodes[0]['preserved_original_videos']
    require(all(ep['preserved_original_videos'] == originals for ep in episodes), 'Protected earlier-video lists differ')
    require(sum(ep['verified_speech_requests'] for ep in episodes) == 35, 'Expected 35 verified speech requests')
    require(sum(ep['unknown_previous_requests'] for ep in episodes) == 1, 'Expected one preserved unknown speech request')
    require(sum(ep['previous_audio_identical'] for ep in episodes) == 4, 'Expected four unchanged previous AAC streams')
    require(len({ep['presenter']['sha256'] for ep in episodes}) == 1, 'The five presenter assets differ')
    checked_at = datetime.now(timezone.utc).isoformat()
    report = {'schema_version': 1, 'series': 'SERIES_20261022_dots_finale', 'checked_at': checked_at,
              'status': 'verified_candidate_awaiting_user_review', 'technical_status': 'verified',
              'method': 'Independent hash, ZIP readback, current ffprobe, AAC packet comparison, and evidence audit',
              'episodes': episodes, 'totals': {'episodes': 5, 'seconds': 150, 'frames': 3600, 'scene_reviews': 35,
                                             'official_capture_proofs': 5, 'presenter_opening_closing_pairs': 5,
                                             'verified_speech_requests': 35, 'unknown_previous_requests': 1,
                                             'total_speech_requests': 36, 'visual_revision_additional_tts_requests': 0,
                                             'visual_revision_additional_tts_characters': 0,
                                             'previous_aac_streams_identical': 4, 'protected_original_videos': 12,
                                             'preserved_previous_revision_artifacts': sum(len(ep['preserved_previous_revision_files']) for ep in episodes)},
              'actual_billing_known': False, 'user_approved': False, 'final_listening_review': 'pending',
              'youtube_uploaded': False, 's3_sharing': 'Recorded separately; signed URLs are not persisted here'}
    report_path = ROOT / 'verification/shorts-dots-finale-2026-10-22.json'
    save(report_path, report)
    delivery = {'schema_version': 1, 'series': report['series'], 'checked_at': checked_at,
                'status': report['status'], 'verification': record(report_path), 'totals': report['totals'],
                'episodes': [{key: ep[key] for key in ['episode', 'title', 'video', 'archive', 'cover', 'release', 'verification']}
                             for ep in episodes],
                'user_approved': False, 'final_listening_review': 'pending', 'youtube_uploaded': False,
                'actual_billing_known': False}
    save(HERE / 'delivery.json', delivery)
    readme_path = HERE / 'README.md'
    readme = readme_path.read_text(encoding='utf-8')
    replacement = ('2026年10月22日の最終集約検証では、人物版の第5〜9回すべてが `packaged` です。'
                   '各MP4・ZIPのサイズとSHA-256、ZIP全10メンバー、完成形式と720フレーム、35場面の確認証跡、'
                   '公式引用5件、人物の冒頭・締め配置、旧12動画と第5〜8回の旧納品物を独立照合しました。'
                   '第5〜8回のAAC音声は前版と同一です。成功した音声要求35件と結果不明1件を別集計し、人物追加によるTTSは0件です。'
                   '最新成果物は本フォルダーの `delivery.json`、集約検証は `verification/shorts-dots-finale-2026-10-22.json` に記録しています。')
    updated, count = re.subn(r'2026年10月22日の本README更新時点では、[^\n]+', replacement, readme)
    if count == 1:
        readme_path.write_text(updated, encoding='utf-8')
    elif '2026年10月22日の最終集約検証では、' not in readme:
        raise ValueError('README status paragraph was not found; reports passed but documentation needs review')
    print(json.dumps({'event': 'series_audit_verified', 'episodes': 5, 'report': str(report_path),
                      'delivery': str(HERE / 'delivery.json'), 'user_approved': False}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__,
                          'message': str(error) if isinstance(error, ValueError) else 'Final audit stopped; inspect local evidence.'}), flush=True)
        raise SystemExit(1)
