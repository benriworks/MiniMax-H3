import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from PIL import Image
from tools.studio import shorts_creator as creator


class BusinessSourceShortsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch_root = patch.object(creator, 'ROOT', self.root)
        self.patch_root.start()
        self.folder = self.root / 'outputs/productions/fixture/captures'
        self.folder.mkdir(parents=True)
        Image.new('RGB', (24, 24), '#f4f1eb').save(self.folder / 'context.png')
        Image.new('RGB', (8, 8), '#f4f1eb').save(self.folder / 'crop.png')
        self.capture = {
            'origin': 'demonstration', 'product': 'Claude', 'phase': 'before', 'title': '実際の作業',
            'path': 'outputs/productions/fixture/captures/crop.png',
            'proof': 'outputs/productions/fixture/captures/proof.json',
        }
        self.proof = {
            'origin': 'demonstration', 'product': 'Claude', 'phase': 'before', 'title': '実際の作業',
            'artifact': creator.record(self.folder / 'crop.png'),
            'context': creator.record(self.folder / 'context.png'),
            'clip': {'x': 2, 'y': 2, 'width': 8, 'height': 8},
            'context_clip': {'x': 0, 'y': 0, 'width': 24, 'height': 24},
            'review_status': 'capture_review_passed', 'captured_at': '2026-10-22T12:00:00+09:00',
            'fictional_materials_only': True, 'personal_information_excluded': True,
        }
        self.write_proof()

    def tearDown(self):
        self.patch_root.stop()
        self.temp.cleanup()

    def write_proof(self):
        (self.folder / 'proof.json').write_text(json.dumps(self.proof), encoding='utf-8')

    def story(self):
        text = '内容を確認します。'
        scenes = [{'kind': 'editorial', 'editorial_layout': 'statement', 'visual_style': 'business',
                   'headline': '内容を確認', 'eyebrow': 'CLAUDE', 'narration': text, 'captions': [text]}
                  for _ in range(7)]
        scenes[1] = {'kind': 'source', 'visual_style': 'business', 'headline': '入力を確認',
                     'eyebrow': 'CLAUDE', 'narration': text, 'captions': [text], 'capture': copy.deepcopy(self.capture)}
        return {'schema_version': 1, 'id': 'fixture', 'title': '架空の資料', 'duration_seconds': 30,
                'voice': 'fixture', 'rate': 1, 'scenes': scenes}

    def test_official_allowlist_is_explicit_and_does_not_expand_legacy_dots(self):
        allowed = ['https://support.claude.com/en/articles/123-example#section',
                   'https://support.claude.com/ja/articles/123-test',
                   'https://claude.com/resources/articles/example',
                   'https://learn.chatgpt.com/docs/dots/tasks-and-memory',
                   'https://www.php.net/archive/2026.php#2026-10-21-5',
                   'https://www.ipa.go.jp/security/security-alert/2026/alert20261022.html',
                   'https://www.jpcert.or.jp/at/2026/at260033.html']
        for url in allowed:
            capture = {key: self.capture[key] for key in ['path', 'proof', 'title']}
            capture.update(origin='official', source_url=url)
            creator.validate_capture(capture, 'business')
        for url in ['http://support.claude.com/en/articles/123', 'https://support.claude.com.evil/en/articles/123',
                    'https://user@support.claude.com/en/articles/123', 'https://support.claude.com:8443/en/articles/123',
                    'https://support.claude.com/en/articles/123?account=1', 'https://claude.com/private/chat/123',
                    'https://www.php.net.evil/archive/2026.php', 'https://www.php.net/archive/2026.php?session=1',
                    'https://www.php.net/manual/en/index.php', 'https://www.ipa.go.jp/private/chat',
                    'https://www.jpcert.or.jp/at/2026/../../private']:
            capture['source_url'] = url
            with self.assertRaisesRegex(ValueError, 'source URL'):
                creator.validate_capture(capture, 'business')
        capture.pop('origin'); capture['source_url'] = allowed[0]
        with self.assertRaisesRegex(ValueError, 'dots source URL'):
            creator.validate_capture(capture)

    def test_fifty_second_story_preserves_measured_timing_contract(self):
        story = self.story(); story['duration_seconds'] = 50
        creator.validate_story(story)
        story['duration_seconds'] = 49
        with self.assertRaisesRegex(ValueError, 'duration'):
            creator.validate_story(story)

    def test_demonstration_is_closed_and_cannot_publish_account_urls(self):
        story = self.story(); creator.validate_story(story)
        for key, value in [('phase', 'unverified'), ('product', 'Unknown'), ('source_url', 'https://claude.ai/chat/private')]:
            invalid = copy.deepcopy(story); invalid['scenes'][1]['capture'][key] = value
            with self.assertRaises(ValueError):creator.validate_story(invalid)
        del story['scenes'][1]['visual_style']
        with self.assertRaisesRegex(ValueError, 'business style'):creator.validate_story(story)

    def test_capture_proof_binds_origin_phase_privacy_timestamp_and_context(self):
        source, records = creator.load_capture(self.capture)
        self.assertEqual(source, self.folder / 'crop.png')
        self.assertEqual(len(records), 3)
        for key, value in [('origin', 'official'), ('phase', 'after'), ('fictional_materials_only', False),
                           ('personal_information_excluded', False), ('captured_at', '2026-10-22'),
                           ('original_url', 'https://claude.ai/chat/private'),
                           ('clip', {'x': 20, 'y': 20, 'width': 8, 'height': 8})]:
            previous = copy.deepcopy(self.proof); self.proof[key] = value; self.write_proof()
            with self.assertRaises(ValueError):creator.load_capture(self.capture)
            self.proof = previous; self.write_proof()
        (self.folder / 'context.png').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'Source changed'):creator.load_capture(self.capture)

    def test_business_visual_rules_match_motion_and_evidence_layout(self):
        original = self.story()
        mutations = [lambda s: s['scenes'][0].update(visual_style='arbitrary'),
                     lambda s: s['scenes'][0].update(headline='一行目\n二行目\n三行目'),
                     lambda s: s['scenes'][1].update(body='証拠を覆う文章'),
                     lambda s: s['scenes'][2].update(editorial_layout='hook', media={'path': 'x', 'proof': 'x'}),
                     lambda s: s['scenes'][0].update(editorial_layout='hook', media={'path': 'x', 'proof': 'x'}, mediaStart=-1),
                     lambda s: s['scenes'][0].update(presenter={'path': 'x'})]
        for mutate in mutations:
            story = copy.deepcopy(original); mutate(story)
            with self.assertRaises(ValueError):creator.validate_story(story)
        story = copy.deepcopy(original)
        story['scenes'][0].update(editorial_layout='hook', media={'path': 'x', 'proof': 'x'}, mediaStart=0)
        creator.validate_story(story)

    def test_prepare_stages_demonstration_without_url_and_legacy_props_stay_equal(self):
        story = self.story()
        source = self.root / 'productions/story.json'; source.parent.mkdir()
        source.write_text(json.dumps(story), encoding='utf-8')
        module = self.root / 'tools/studio/shorts_creator.py'; module.parent.mkdir(parents=True)
        module.write_text('fixture'); (module.parent / 'narration.py').write_text('fixture')
        audio = self.root / 'outputs/narration.wav'
        with wave.open(str(audio), 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\0\0' * (24000 * 7))
        timings = self.root / 'outputs/timings.json'
        timings.write_text(json.dumps({'segments': [{'frames': 24000, 'duration_ms': 1000} for _ in range(7)]}), encoding='utf-8')
        voice = {'provider': 'fixture', 'artifacts': [dict(creator.record(audio), name='narration.wav'),
                                                    dict(creator.record(timings), name='timings.json')]}
        with patch.object(creator, '__file__', str(module)), patch('tools.studio.narration.generate_local_narration', return_value=voice):
            out = creator.prepare(source)
        props = creator.read(out / 'props.json')
        self.assertEqual(props['scenes'][1]['capture'], {'image': 'capture-00.png', 'title': '実際の作業',
                                                       'origin': 'demonstration', 'product': 'Claude', 'phase': 'before'})
        self.assertEqual(props['scenes'][1]['visual_style'], 'business')
        self.assertNotIn('https://', json.dumps(props))
        legacy = {'path': 'x', 'proof': 'x', 'source_url': 'https://learn.chatgpt.com/docs/dots/tasks-and-memory', 'title': '出典'}
        self.assertEqual(creator.staged_capture(legacy, 'capture-00.png'),
                         {'image': 'capture-00.png', 'source_url': legacy['source_url'], 'title': '出典'})


if __name__ == '__main__':unittest.main()
