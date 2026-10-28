"""No network calls; verify measured evidence and fail-closed generation behavior."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch
import wave

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('comparison_production', HERE / 'produce.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProductionTests(unittest.TestCase):
    def test_actual_scene_audio_is_preserved_and_has_space(self):
        out = module.current_output()
        props = module.validate_preparation(out)
        state = module.read(module.STATE)
        raw = module.read(module.generation_folder(state) / 'timings.json')['segments']
        with wave.open(str(out / 'narration.wav'), 'rb') as wav:
            self.assertEqual(wav.getnframes(), props['durationInFrames'] * 1000)
            for index, (scene, segment) in enumerate(zip(props['scenes'], raw, strict=True)):
                offset = (scene['from'] + 3) * 1000
                wav.setpos(offset)
                with wave.open(str(module.generation_folder(state) / f'scene-{index:02d}/Aoede/voice.wav'), 'rb') as original:
                    self.assertEqual(wav.readframes(segment['frames']), original.readframes(original.getnframes()))
                self.assertLess(offset + segment['frames'], (scene['from'] + scene['duration']) * 1000)

    def test_duration_allocation_is_bounded_and_does_not_cut_speech(self):
        durations, total = module.allocate([24000 * 4] * 14)
        self.assertEqual(sum(durations), total)
        self.assertTrue(1440 <= total <= 2160)
        self.assertTrue(all(102 <= d <= 192 for d in durations))
        with self.assertRaisesRegex(ValueError, '8-second'):
            module.allocate([24000 * 9] + [24000 * 4] * 13)
        with self.assertRaisesRegex(ValueError, '60–90'):
            module.allocate([24000 * 4] * 14, target_seconds=91)

    def test_official_url_allowlist_rejects_credentials_queries_and_near_matches(self):
        self.assertTrue(module.official_url('https://learn.chatgpt.com/docs/dots'))
        for bad in ['https://learn.chatgpt.com/docs/dots?track=1', 'https://learn.chatgpt.com/docs/dots/other',
                    'https://claude.com.evil/resources/articles/x', 'https://person@claude.com/resources/articles/x',
                    'https://claude.com:8443/resources/articles/x']:
            self.assertFalse(module.official_url(bad))

    def test_three_reviewed_source_crops_match_exact_private_pixels(self):
        assets, sources = module.capture_assets()
        self.assertEqual(set(assets), {'C02', 'C07', 'C08'})
        self.assertGreater(len(sources), 9)

    def test_presenter_intervals_cover_original_motion_once(self):
        visited = [i for start, length in module.MOTION_INTERVALS.values() for i in range(start, start + length)]
        self.assertEqual(visited, list(range(124)))

    def test_unknown_submission_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            (parent / 'Aoede').mkdir()
            with patch.object(module.speech.urllib.request, 'build_opener', side_effect=AssertionError('No request allowed')):
                with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                    module.speech.synthesize(parent, '確認用です。', 'Aoede')

    def test_verified_generation_is_reused_without_paid_requests(self):
        with patch.object(module.speech, 'synthesize', side_effect=AssertionError('No request allowed')):
            module.generate()


if __name__ == '__main__':
    unittest.main()
