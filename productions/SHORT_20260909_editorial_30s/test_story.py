import copy
import importlib.util
import json
from pathlib import Path
import unittest

folder = Path(__file__).parent
spec = importlib.util.spec_from_file_location("editorial_finish", folder / "finish.py")
finish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finish)


class StoryTests(unittest.TestCase):
    def setUp(self):
        self.story = json.loads((folder / "story.json").read_text(encoding="utf-8"))

    def test_six_short_captions_in_three_chapters(self):
        self.assertEqual(len(finish.validate_story(self.story)), 6)

    def test_long_caption_rejected(self):
        self.story["segments"][0]["text"] = "あ" * 20
        with self.assertRaises(ValueError):
            finish.validate_story(self.story)

    def test_voice_change_rejected(self):
        self.story["voice"] = "Paid Voice"
        with self.assertRaises(ValueError):
            finish.validate_story(self.story)

    def test_actual_timings_must_not_cross_cut(self):
        rows = [{**s, "end_ms": s["start_ms"] + 2000} for s in self.story["segments"]]
        finish.validate_timings(self.story, {"segments": rows})
        rows[1]["end_ms"] = 10001
        with self.assertRaises(ValueError):
            finish.validate_timings(self.story, {"segments": rows})

    def test_validation_does_not_mutate_story(self):
        before = copy.deepcopy(self.story)
        finish.validate_story(self.story)
        self.assertEqual(before, self.story)

    def test_wrong_caption_or_start_is_rejected(self):
        rows = [{**s, "end_ms": s["start_ms"] + 2000} for s in self.story["segments"]]
        rows[0]["text"] = "別の音声"
        with self.assertRaises(ValueError):
            finish.validate_timings(self.story, {"segments": rows})


if __name__ == "__main__":
    unittest.main()
