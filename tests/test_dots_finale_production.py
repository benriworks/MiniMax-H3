import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import wave

from tools.studio import shorts_creator

PATH = Path(__file__).resolve().parents[1] / 'productions/SERIES_20261022_dots_finale/produce.py'
SPEC = importlib.util.spec_from_file_location('dots_finale_test_driver', PATH)
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)


class FinaleProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.here = self.root / 'productions/SERIES_20261022_dots_finale'
        (self.here / '05').mkdir(parents=True)
        self.patches = [patch.object(driver, 'ROOT', self.root), patch.object(driver, 'HERE', self.here),
                        patch.object(shorts_creator, 'ROOT', self.root), patch.object(driver.speech, 'ROOT', self.root)]
        for item in self.patches:
            item.start()
        self.production = driver.Production(5)
        self.story = {'schema_version': 1, 'id': self.production.id, 'duration_seconds': 30,
                      'voice': 'Aoede', 'rate': 1, 'pronunciations': [], 'music_preset': 'bright_groove_v1',
                      'scenes': [{'kind': 'editorial', 'editorial_layout': 'hook', 'headline': '記憶を使う。',
                                  'eyebrow': 'DOTS 05', 'narration': text, 'captions': [text]}
                                 for text in ['好みを伝える。', '前の話を使う。', '内容を確かめる。']]}
        driver.save(self.production.story_path, self.story)

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def synthetic_success(self, parent, text, voice, **kwargs):
        """Deterministic local fixture. Never connects to an audio provider."""
        target = parent / voice
        target.mkdir()
        driver.save(target / 'request.json', driver.speech.payload(text, voice))
        with wave.open(str(target / 'voice.wav'), 'wb') as wav:
            wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            wav.writeframes(b'\x01\x02' * 24000)
        proof = {'status': 'technically_verified_listening_pending', 'model': driver.speech.MODEL,
                 'voice': voice, 'usage': {'totalTokenCount': 30},
                 'files': [driver.record(target / name) for name in ['voice.wav', 'request.json']]}
        driver.save(target / 'verified.json', proof)
        return proof

    def test_episode_selection_is_closed(self):
        self.assertEqual(driver.selected_episodes('all'), [5, 6, 7, 8, 9])
        self.assertEqual(driver.selected_episodes('05'), [5])
        for value in ['4', '../05', '5,6', '10']:
            with self.assertRaises(ValueError):
                driver.selected_episodes(value)

    def test_completed_generation_is_reused_without_new_requests(self):
        cadence = Mock()
        with patch.object(driver, 'preserved_deliveries', return_value=[]), \
                patch.object(driver.speech, 'synthesize', side_effect=self.synthetic_success) as synthesize:
            self.production.generate(cadence)
            self.assertEqual(synthesize.call_count, 3)
        with patch.object(driver.speech, 'synthesize') as synthesize:
            self.production.generate(cadence)
            synthesize.assert_not_called()
        self.assertEqual(cadence.before_submission.call_count, 3)

    def test_changed_frozen_story_stops_before_new_requests(self):
        with patch.object(driver, 'preserved_deliveries', return_value=[]), \
                patch.object(driver.speech, 'synthesize', side_effect=self.synthetic_success):
            self.production.generate(Mock())
        self.story['title'] = 'A changed visual plan'
        driver.save(self.production.story_path, self.story)
        with patch.object(driver.speech, 'synthesize') as synthesize:
            with self.assertRaisesRegex(ValueError, 'Source changed'):
                self.production.generate(Mock())
            synthesize.assert_not_called()

    def test_unknown_partial_submission_is_not_retried(self):
        calls = 0

        def interrupt_after_first(parent, text, voice, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return self.synthetic_success(parent, text, voice, **kwargs)
            (parent / voice).mkdir()
            driver.save(parent / voice / 'submission.json', {'status': 'unknown', 'automatic_retry': False})
            raise RuntimeError('Unknown fixture submission')

        with patch.object(driver, 'preserved_deliveries', return_value=[]), \
                patch.object(driver.speech, 'synthesize', side_effect=interrupt_after_first):
            with self.assertRaisesRegex(RuntimeError, 'Unknown fixture'):
                self.production.generate(Mock())
        cadence = Mock()
        with patch.object(driver.speech.urllib.request, 'build_opener') as network:
            with self.assertRaisesRegex(RuntimeError, 'Previous submission is incomplete'):
                self.production.generate(cadence)
            network.assert_not_called()
            cadence.before_submission.assert_not_called()

    def test_request_cadence_survives_a_new_process_instance(self):
        with patch.object(driver.time, 'time', return_value=100), patch.object(driver.time, 'sleep') as sleep:
            driver.SubmissionCadence().before_submission()
            sleep.assert_not_called()
        with patch.object(driver.time, 'time', return_value=105), patch.object(driver.time, 'sleep') as sleep:
            driver.SubmissionCadence().before_submission()
            sleep.assert_called_once_with(17)
        self.assertEqual(json.loads((self.here / 'api-cadence.json').read_text())['last_submission_epoch'], 105)

    def test_explicit_unknown_manual_attempt_is_counted_without_retrying(self):
        folder = self.root / 'manual-accounting'
        folder.mkdir()
        self.assertEqual(driver.request_accounting(folder, 7),
                         {'external_api_calls': 7, 'verified_requests': 7, 'unknown_previous_requests': 0})
        record = {'previous_unknown_requests': 1, 'manual_replacement_requests_authorized': 1,
                  'reason': 'Explicit recovery after inspection; original unknown attempt preserved'}
        driver.save(folder / 'manual-recovery.json', record)
        with patch.object(driver.speech, 'synthesize') as synthesize:
            result = driver.request_accounting(folder, 7)
            self.assertEqual(result['external_api_calls'], 8)
            self.assertEqual(result['verified_requests'], 7)
            self.assertEqual(result['unknown_previous_requests'], 1)
            synthesize.assert_not_called()
        record['manual_replacement_requests_authorized'] = 0
        driver.save(folder / 'manual-recovery.json', record)
        with self.assertRaisesRegex(ValueError, 'explicitly recorded'):
            driver.request_accounting(folder, 7)

    def test_presenter_revision_changes_only_opening_and_closing_annotations(self):
        before = json.dumps(self.story, sort_keys=True)
        presenter = {'path': 'outputs/characters/dots-guide-20261022/guide.png',
                     'proof': 'outputs/characters/dots-guide-20261022/guide.json'}
        visual = driver.presenter_story(self.story, presenter)
        self.assertEqual(json.dumps(self.story, sort_keys=True), before)
        self.assertEqual(visual['scenes'][0]['presenter']['role'], 'hook')
        self.assertNotIn('presenter', visual['scenes'][1])
        self.assertEqual(visual['scenes'][-1]['presenter']['role'], 'recap')
        self.assertEqual(driver.audio_signature(visual), driver.audio_signature(self.story))
        self.assertEqual(driver.narration_inputs(visual), driver.narration_inputs(self.story))
        self.story['scenes'][0]['kind'] = 'source'
        with self.assertRaisesRegex(ValueError, 'editorial opening'):
            driver.presenter_story(self.story, presenter)

    def test_visual_revision_preserves_original_and_routes_completed_video_to_audio_reuse(self):
        with patch.object(driver, 'preserved_deliveries', return_value=[]), \
                patch.object(driver.speech, 'synthesize', side_effect=self.synthetic_success):
            self.production.generate(Mock())
        original_story_bytes = self.production.story_path.read_bytes()
        state = driver.read(self.production.state_path)
        previous = self.production.out_root / 'original-completed'
        previous.mkdir()
        (previous / 'shorts-creator.mp4').write_bytes(b'original completed fixture')
        driver.save(previous / 'verification.json', {
            'review_status': 'verified_candidate_awaiting_user_review',
            'delivery': driver.record(previous / 'shorts-creator.mp4')})
        state.update(output=previous.relative_to(self.root).as_posix(), status='packaged')
        driver.save(self.production.state_path, state)
        asset = self.root / 'outputs/characters/dots-guide-20261022/guide.png'
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b'presenter fixture')
        proof = asset.with_suffix('.json')
        driver.save(proof, {'artifact': driver.record(asset), 'review_status': 'visual_review_passed',
                            'source_type': 'generated_humanoid', 'transparent': True})
        revised = self.production.out_root / 'new-visual-output'

        def prepare_visual(story_path, **kwargs):
            self.assertEqual(kwargs, {'reuse_audio': previous})
            revised.mkdir()
            (revised / 'story.json').write_bytes(story_path.read_bytes())
            driver.save(revised / 'preparation.json', {'sources': [driver.record(asset), driver.record(proof)],
                                                       'audio_reuse': {'method': 'aac_stream_copy'}})
            return revised

        with patch.object(driver, 'prepare', side_effect=prepare_visual) as prepare, \
                patch.object(driver.speech, 'synthesize') as synthesize:
            self.production.revise_visuals(asset, proof)
            prepare.assert_called_once()
            synthesize.assert_not_called()
        self.assertEqual(self.production.story_path.read_bytes(), original_story_bytes)
        self.assertEqual((previous / 'shorts-creator.mp4').read_bytes(), b'original completed fixture')
        new_state, current = self.production.video_folder()
        self.assertEqual(current, revised)
        receipt = driver.read(driver.check(new_state['visual_revision']))
        self.assertEqual(receipt['additional_tts_requests'], 0)
        self.assertEqual(receipt['audio_method'], 'previous_aac_stream_copy')
        self.assertTrue(receipt['narration_inputs_unchanged'])


if __name__ == '__main__':
    unittest.main()
