"""Audit all five latest packages without speech, rendering, uploads, or input edits."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from tools.studio.shorts_creator import check, load_capture, load_supplied_narration, read, record, validate_story

PUBLIC_NAMES = {'cover.png', 'captions.srt', 'youtube-title.txt', 'youtube-description.txt',
                'narration.txt', 'SOURCES_JA.md', 'quality-report.json', 'index.html', 'manifest.json'}


def require(value, message):
    if not value:
        raise ValueError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def probe(path):
    return json.loads(subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
        '-of', 'json', str(path)], check=True, capture_output=True,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)).stdout)


def package_check(delivery, out):
    video, archive = check(delivery['video']), check(delivery['archive'])
    release = out / 'release'
    require(video.parent == release and ROOT / delivery['release'] == release, 'Release pointer mismatch')
    names = PUBLIC_NAMES | {video.name}
    require({p.name for p in release.iterdir()} == names, 'Unexpected public release file')
    manifest = read(release / 'manifest.json')
    require(set(manifest) == names - {'manifest.json'}, 'Public hash manifest differs')
    with zipfile.ZipFile(archive) as z:
        require(len(z.namelist()) == 10 and set(z.namelist()) == names and z.testzip() is None,
                'ZIP members or CRC failed')
        for name in names:
            blob = z.read(name)
            require(blob == (release / name).read_bytes(), 'Archive file differs: ' + name)
            if name != 'manifest.json':
                require(manifest[name] == {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest().upper()},
                        'Archive hash differs: ' + name)
    return video, archive, release


def revision_check(state, story_path, generation):
    preserved, visited = [], set()
    while state.get('renderer_revision'):
        path = check(state['renderer_revision'])
        require(path not in visited, 'Cyclic renderer history')
        visited.add(path)
        revision = read(path)
        previous = read(check(revision['previous_state']))
        require(revision['output'] == state['output'] and revision['previous_output'] == previous['output'],
                'Renderer revision does not connect the current and previous outputs')
        require(check(revision['original_story']) == story_path
                and check(revision['narration_source']) == generation / 'voice-source.json'
                and ROOT / previous['generation'] == generation, 'Renderer revision belongs to another story or voice')
        require(revision['additional_tts_requests'] == 0 and revision['old_output_unchanged'] is True,
                'Renderer revision altered speech or old output')
        for name in ['original_story', 'previous_state', 'narration_source']:
            check(revision[name])
        for item in revision['preserved_files']:
            check(item)
            preserved.append(item)
        state = previous
    return list({item['path']: item for item in preserved}.values())


def verify_episode(number):
    here = HERE / f'{number:02d}'
    state = read(here / 'state.json')
    require(state['status'] == 'packaged', 'Episode is not packaged: ' + str(number))
    out = (ROOT / state['output']).resolve(strict=True)
    require(out.parent == ROOT / f'outputs/productions/SHORT_20261022_claude_{number:02d}_work', 'Wrong output folder')
    delivery = read(here / 'delivery.json')
    require(delivery == read(out / 'delivery.json'), 'Delivery records differ')
    video, archive, release = package_check(delivery, out)
    proof = read(out / 'verification.json')
    require(record(video)['sha256'] == record(check(proof['delivery']))['sha256'], 'Packaged video differs from proof')
    require(proof['review_status'] == 'verified_candidate_awaiting_user_review' and proof['full_decode_verified'] is True
            and proof['on_screen_tool_credit'] is False, 'Technical/visual verification is incomplete')
    quality = read(release / 'quality-report.json')
    require(quality == delivery['quality'] and quality['user_approved'] is False
            and quality['youtube_uploaded'] is False and quality['final_listening_review'] == 'pending',
            'Publication or review state differs')
    current = probe(video)
    require(len(current['streams']) == 2, 'Expected two streams')
    v, a = current['streams']
    require((v['codec_name'], v['width'], v['height'], v['avg_frame_rate'], int(v['nb_frames']))
            == ('h264', 1080, 1920, '24/1', 720), 'Video format differs')
    require((a['codec_name'], a['sample_rate'], a['channels']) == ('aac', '48000', 2), 'Audio format differs')
    require(abs(float(current['format']['duration']) - 30) < .002, 'Video duration differs')
    require(-18 <= float(proof['loudness']['input_i']) <= -14 and float(proof['loudness']['input_tp']) <= -1,
            'Loudness bounds failed')
    for item in read(out / 'preparation.json')['sources'] + read(out / 'render.json')['sources']:
        check(item)
    review = proof['visual_review']
    require(review['method'] == 'AI-assisted visual inspection' and bool(review['note']), 'Missing review note')
    require({check(item) for item in review['evidence']} == {out / f'preview-{i:02d}.png' for i in range(7)}
            | {out / 'contact-sheet.png'}, 'Review does not cover all scenes')
    check(proof['fact_review']['sources'])
    generation = ROOT / state['generation']
    plan = read(generation / 'plan.json')
    require(check(plan['story']) == here / 'creator-story.json', 'Frozen story differs')
    story = validate_story(read(here / 'creator-story.json'))
    require(story == read(out / 'story.json'), 'Prepared story differs from fixed input')
    voice, _ = load_supplied_narration(story, generation / 'voice-source.json')
    require(voice['voice'] == 'Aoede' and voice['model'] == 'gemini-2.5-flash-preview-tts'
            and len(voice['generation_proofs']) == 7 and voice['actual_billing_known'] is False, 'Speech source differs')
    submissions = [read(path) for path in generation.rglob('submission.json')]
    require(all(item.get('automatic_retry') is False for item in submissions), 'Automatic retry found')
    verified = sum(item['status'] == 'received_and_verified' for item in submissions)
    rejected = sum(item['status'] == 'rejected' for item in submissions)
    require(verified == 7 and rejected == (1 if number == 1 else 0) and len(submissions) == verified + rejected,
            'Submission count or unresolved request differs')
    require((voice['verified_requests'], voice['previous_rejected_requests'], voice['unknown_previous_requests'],
             voice['external_api_calls']) == (verified, rejected, 0, verified + rejected), 'Request accounting differs')
    if rejected:
        history = read(check(voice['rejected_attempt_history']))
        require(len(history['attempts']) == rejected, 'Rejected request history count differs')
        for attempt in history['attempts']:
            check(attempt['request']); submission = read(check(attempt['submission']))
            require(submission['status'] == 'rejected' and submission['error'] == 'api_key_invalid'
                    and attempt['replacement_authorized'] is True, 'Rejection was not explicit and authorized')
    originals = [record(check(item)) for item in plan['existing_deliveries']]
    require(len(originals) == len({item['path'] for item in originals}) == 26,
            'Expected all 26 distinct protected earlier videos')
    props, timing = read(out / 'props.json'), read(out / 'timings.json')['segments']
    require(len(props['scenes']) == len(timing) == 7 and props['durationInFrames'] == 720, 'Timeline shape differs')
    captures, media, cursor = [], [], 0
    for index, (scene, interval, source) in enumerate(zip(props['scenes'], timing, story['scenes'], strict=True)):
        require(scene['from'] == cursor and 24 <= scene['duration'] <= 192, 'Scene coverage differs')
        require(cursor * 1000 / 24 - 1 <= interval['start_ms'] < interval['end_ms']
                <= (cursor + scene['duration']) * 1000 / 24 + 1, 'Speech falls outside its scene')
        require(interval['text'] == source['narration'], 'Narration changed')
        cursor += scene['duration']
        if source.get('capture'):
            capture = source['capture']; load_capture(capture)
            cp = read(ROOT / capture['proof'])
            require(cp['review_status'] == 'capture_review_passed' and cp['origin'] == capture['origin'], 'Capture review differs')
            require(record(out / 'public' / scene['capture']['image'])['sha256'] == cp['artifact']['sha256'], 'Staged crop changed')
            captures.append({'scene': index, 'origin': capture['origin'], 'phase': capture.get('phase'),
                             'proof': record(ROOT / capture['proof'])})
        if source.get('media'):
            mp = read(ROOT / source['media']['proof'])
            asset = check(mp['artifact'])
            check(mp['source_presenter']); check(mp['source_keyframe'])
            require(mp['provider'] == 'minimax' and mp['review_status'] == 'visual_review_passed'
                    and mp['execution']['success'] is True, 'Character video proof differs')
            require(record(out / 'public' / scene['media'])['sha256'] == record(asset)['sha256'], 'Staged character video differs')
            require(scene['kind'] == 'editorial' and scene['visual_style'] == 'business'
                    and 24 <= scene['mediaPlayFrames'] <= scene['duration']
                    and scene.get('mediaStart', 0) + scene['mediaPlayFrames'] <= scene['mediaDurationInFrames'], 'Character coverage differs')
            actual_media = probe(asset)['streams'][0]
            require(int(actual_media['nb_frames']) == scene['mediaDurationInFrames']
                    and actual_media['avg_frame_rate'] == '24/1', 'Character duration differs from actual MP4')
            media.append({'scene': index, 'artifact': record(asset), 'proof': record(ROOT / source['media']['proof']),
                          'source_frames': scene['mediaDurationInFrames'], 'play_frames': scene['mediaPlayFrames'],
                          'summary_frames_after_media': scene['duration'] - scene['mediaPlayFrames']})
    require(cursor == 720 and [item['scene'] for item in media] == [0, 6], 'Character/timeline placement differs')
    require(sum(item['origin'] == 'official' for item in captures) == 1
            and sum(item['origin'] == 'demonstration' for item in captures) == 4, 'Capture provenance counts differ')
    tail_evidence = None
    if number == 3:
        tail_path = HERE / 'audit-20261023/episode-03-media-end/review.json'
        tail = read(tail_path)
        require(record(check(tail['source']))['sha256'] == record(video)['sha256']
                and tail['root_visual_review_status'] == 'passed'
                and [item['frame'] for item in tail['frames']] == [709, 715, 719], 'Material-end review differs')
        for item in tail['frames']:
            check(item['artifact'])
        tail_evidence = record(tail_path)
    return {'episode': number, 'title': (release / 'youtube-title.txt').read_text(encoding='utf-8').strip(),
            'video': record(video), 'archive': record(archive), 'cover': record(release / 'cover.png'),
            'release': release.relative_to(ROOT).as_posix(), 'verification': record(out / 'verification.json'),
            'duration_seconds': 30, 'frames': 720, 'zip_members': 10, 'speech_segments': 7,
            'verified_speech_requests': verified, 'previous_rejected_requests': rejected, 'unknown_requests': 0,
            'visual_revision_additional_tts_requests': 0, 'captures': captures, 'character_media': media,
            'media_end_review': tail_evidence,
            'preserved_videos': originals, 'preserved_renderer_files': revision_check(state, here / 'creator-story.json', generation)}


def main():
    require(all(read(HERE / f'{n:02d}' / 'state.json')['status'] == 'packaged' for n in range(1, 6)),
            'All five episodes must be packaged before aggregate audit')
    episodes = []
    for n in range(1, 6):
        episodes.append(verify_episode(n))
        print(json.dumps({'event': 'episode_audit_passed', 'episode': n}), flush=True)
    originals = {item['path']: item for ep in episodes for item in ep['preserved_videos']}
    require(len(originals) == 26 and all({item['path']: item for item in ep['preserved_videos']} == originals
            for ep in episodes), 'Protected video sets differ among the five generation plans')
    totals = {'episodes': 5, 'seconds': 150, 'frames': 3600, 'scene_reviews': 35, 'official_capture_proofs': 5,
              'demonstration_capture_scenes': 20, 'character_video_scenes': 10, 'verified_speech_requests': 35,
              'previous_rejected_requests': 1, 'unknown_requests': 0, 'external_api_calls': 36,
              'visual_revision_additional_tts_requests': 0, 'protected_existing_videos': len(originals)}
    checked_at = datetime.now(timezone.utc).isoformat()
    report = {'schema_version': 1, 'series': 'SERIES_20261022_claude_work', 'checked_at': checked_at,
              'status': 'verified_candidate_awaiting_user_review', 'technical_status': 'verified',
              'method': 'Independent current ffprobe, ZIP CRC/member hash readback, frozen audio and provenance audit',
              'totals': totals, 'episodes': episodes, 'user_approved': False, 'final_listening_review': 'pending',
              'youtube_uploaded': False, 'actual_billing_known': False, 's3_sharing': 'separate sanitized records'}
    report_path = ROOT / 'verification/shorts-claude-work-2026-10-23.json'
    save(report_path, report)
    save(HERE / 'delivery.json', {**{key: report[key] for key in ['schema_version', 'series', 'checked_at', 'status',
         'totals', 'user_approved', 'final_listening_review', 'youtube_uploaded', 'actual_billing_known']},
         'verification': record(report_path), 'episodes': [{key: ep[key] for key in
             ['episode', 'title', 'video', 'archive', 'cover', 'release', 'verification']} for ep in episodes]})
    print(json.dumps({'event': 'series_audit_verified', 'report': str(report_path), 'totals': totals}), flush=True)


if __name__ == '__main__':
    main()
