"""Pilot lengths keep speech intact and fill the requested timeline exactly."""
import copy
import json
from pathlib import Path
import unittest

from tools.studio.shorts_creator import allocate_scenes, validate_story


class PilotDurationTests(unittest.TestCase):
    def test_pilot_lengths_preserve_speech_with_exact_frame_totals(self):
        story = json.loads((Path(__file__).resolve().parents[1] /
            'productions/SHORT_20260930_claude_code_creator/creator-story.json').read_text(encoding='utf-8'))
        speech = [2100, 2700, 1800, 2200, 2500, 2400]
        for seconds in (20, 25, 30, 35):
            with self.subTest(seconds=seconds):
                candidate = copy.deepcopy(story)
                candidate['duration_seconds'] = seconds
                validate_story(candidate)
                cuts = allocate_scenes(speech, seconds * 24)
                self.assertEqual(sum(cuts), seconds * 24)
                self.assertTrue(all(frames / 24 >= ms / 1000 for frames, ms in zip(cuts, speech)))
                self.assertLessEqual(max(cuts), 192)
        for unsupported in (19, 34, 36):
            with self.subTest(unsupported=unsupported):
                candidate = copy.deepcopy(story)
                candidate['duration_seconds'] = unsupported
                with self.assertRaises(ValueError):
                    validate_story(candidate)

    def test_overlong_script_is_rejected_instead_of_cutting_speech(self):
        with self.assertRaisesRegex(ValueError, 'Script is too long'):
            allocate_scenes([6000] * 6, 35 * 24)


if __name__ == '__main__':
    unittest.main()
