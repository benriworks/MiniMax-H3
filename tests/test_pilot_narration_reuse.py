"""A changed reading must regenerate audio even when display text is unchanged."""
import copy
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / 'productions/content-projects/CONTENT_20261025_dots_shared_desktop_pilot/produce.py'
SPEC = importlib.util.spec_from_file_location('pilot_audio_reuse_tests', PATH)
PILOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PILOT)


class NarrationReuseTests(unittest.TestCase):
    def test_reading_change_invalidates_identical_display_text(self):
        scene = dict(narration='元の表と照合。')
        old = dict(pronunciations=[])
        fixed = dict(pronunciations=[dict(source='表と', target='ひょうと')])
        self.assertNotEqual(PILOT.spoken_text(old, scene), PILOT.spoken_text(fixed, scene))
        self.assertEqual(PILOT.spoken_text(fixed, scene), '元のひょうと照合。')

    def test_visual_only_revision_preserves_verified_audio(self):
        story = dict(pronunciations=[dict(source='dots', target='ドッツ')])
        old = dict(narration='dotsと共同作業。', headline='旧見出し')
        new = dict(old, headline='新しい実画面')
        self.assertEqual(PILOT.spoken_text(story, old), PILOT.spoken_text(story, new))

    def test_longer_pronunciation_rule_takes_precedence(self):
        story = dict(pronunciations=[dict(source='表', target='おもて'), dict(source='表計算', target='ひょうけいさん')])
        self.assertEqual(PILOT.spoken_text(story, dict(narration='表計算')), 'ひょうけいさん')


if __name__ == '__main__':
    unittest.main()
