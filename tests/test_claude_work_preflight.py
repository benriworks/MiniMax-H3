"""Exercise paid-generation guards without invoking any external service."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.studio import shorts_creator as creator

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'productions/SERIES_20261022_claude_work' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


builder = module('claude_work_builder_test', 'build_story_drafts.py')
driver = module('claude_work_driver_test', 'produce.py')


class ClaudeWorkPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for target in (builder, driver, creator):
            change = patch.object(target, 'ROOT', self.root)
            change.start(); self.addCleanup(change.stop)
        self.addCleanup(self.temp.cleanup)
        for relative, data in [(driver.PRESENTER, b'presenter'), (driver.KEYFRAME, b'reviewed frame'),
                               ('runtime/keyframe.png', b'reviewed frame'), ('outputs/new.mp4', b'recorded video')]:
            path = self.root / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        self.proof_path = self.root / 'outputs/verification.json'
        self.proof = {'provider': 'minimax', 'review_status': 'visual_review_passed', 'execution': {'success': True},
                      'artifact': creator.record(self.root / 'outputs/new.mp4'),
                      'source_presenter': creator.record(self.root / driver.PRESENTER),
                      'source_keyframe': creator.record(self.root / 'runtime/keyframe.png')}
        self.write_proof()

    def write_proof(self):
        self.proof_path.write_text(json.dumps(self.proof), encoding='utf-8')

    def test_verified_runtime_copy_of_office_keyframe_is_accepted(self):
        result = builder.media_from_proof('outputs/verification.json')
        self.assertEqual(result['path'], 'outputs/new.mp4')

    def test_different_keyframe_with_consistent_self_proof_is_rejected(self):
        (self.root / 'runtime/keyframe.png').write_bytes(b'another character')
        self.proof['source_keyframe'] = creator.record(self.root / 'runtime/keyframe.png')
        self.write_proof()
        with self.assertRaisesRegex(ValueError, 'reviewed new Claude'):
            builder.media_from_proof('outputs/verification.json')

    def run_preflight(self, phases):
        production = driver.Production(1)
        production.here = self.root / 'production'; production.here.mkdir()
        production.story_path = production.here / 'creator-story.json'
        production.story_path.write_text('{}')
        for name in ['youtube-title.txt', 'youtube-description.txt', 'SOURCES_JA.md']:
            (production.here / name).write_text('【Claude】架空資料の確認', encoding='utf-8')
        scenes = [{'media': {'path': 'outputs/new.mp4', 'proof': 'outputs/verification.json'}}]
        for index, phase in enumerate([None, *phases]):
            origin = 'official' if phase is None else 'demonstration'
            capture = {'origin': origin, 'path': 'outputs/capture.png', 'proof': f'outputs/proof-{index}.json'}
            proof = {'origin': origin, 'review_status': 'capture_review_passed',
                     'artifact': creator.record(self.root / driver.PRESENTER),
                     'context': creator.record(self.root / driver.PRESENTER)}
            capture['path'] = driver.PRESENTER
            if phase is None:
                capture['source_url'] = proof['source_url'] = 'https://support.claude.com/en/articles/test'
            else:
                capture.update(product='Claude', phase=phase); proof.update(product='Claude', phase=phase)
            (self.root / capture['proof']).write_text(json.dumps(proof), encoding='utf-8')
            scenes.append({'capture': capture})
        with patch.object(production, 'story', return_value={'duration_seconds': 30, 'scenes': scenes}), patch.object(driver, 'load_capture'):
            return production.preflight()

    def test_genuine_first_output_can_be_a_before_edit_baseline(self):
        result = self.run_preflight(['first-output', 'after'])
        self.assertEqual(result['paid_requests_submitted'], 0)

    def test_after_only_screens_are_not_a_comparison(self):
        with self.assertRaisesRegex(ValueError, 'before/after screen evidence'):
            self.run_preflight(['after', 'export'])

    def test_before_and_first_output_do_not_establish_a_revision(self):
        with self.assertRaisesRegex(ValueError, 'before/after screen evidence'):
            self.run_preflight(['before', 'first-output'])

    def test_explicit_rejected_request_is_counted_separately(self):
        generation = self.root / 'generation'; generation.mkdir()
        request = generation / 'request.json'; request.write_text('{}')
        submission = generation / 'submission.json'
        submission.write_text(json.dumps({'status': 'rejected', 'error': 'api_key_invalid'}))
        history = generation / 'rejected-attempts.json'
        history.write_text(json.dumps({'attempts': [{'request': creator.record(request),
            'submission': creator.record(submission), 'replacement_authorized': True}]}))
        result = driver.request_accounting(generation, 7)
        self.assertEqual((result['external_api_calls'], result['verified_requests'],
                          result['previous_rejected_requests'], result['unknown_previous_requests']), (8, 7, 1, 0))

    def test_unknown_submission_cannot_be_relabelled_as_rejected(self):
        generation = self.root / 'generation'; generation.mkdir()
        request = generation / 'request.json'; request.write_text('{}')
        submission = generation / 'submission.json'
        submission.write_text(json.dumps({'status': 'unknown', 'error': 'api_key_invalid'}))
        (generation / 'rejected-attempts.json').write_text(json.dumps({'attempts': [{
            'request': creator.record(request), 'submission': creator.record(submission),
            'replacement_authorized': True}]}))
        with self.assertRaisesRegex(ValueError, 'authorized replacement'):
            driver.request_accounting(generation, 7)


if __name__ == '__main__':
    unittest.main()
