"""Editorial regression checks for the real Claude tutorial, not visual acceptance."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.studio.announcement_video import (
    announcement_narration_segment_starts,
    announcement_recipe_to_detailed_payload,
    validate_announcement_recipe_payload,
)


class RealClaudeRecipeTests(unittest.TestCase):
    def setUp(self) -> None:
        request = Path(__file__).resolve().parents[1] / "request.json"
        self.recipe = validate_announcement_recipe_payload(
            json.loads(request.read_text(encoding="utf-8"))["recipe"]
        )

    def test_opening_retains_application_context(self) -> None:
        first = self.recipe["scenes"][0]
        self.assertEqual(first["role"], "hook")
        self.assertNotIn("focus_region", first)
        first_clip = announcement_recipe_to_detailed_payload(self.recipe)["clips"][0]
        self.assertNotIn("focus_region", first_clip)
        self.assertEqual(first_clip["layout_preset"], "screen_explainer_v1")

    def test_visual_revision_keeps_source_and_speech_timing(self) -> None:
        self.assertEqual(announcement_narration_segment_starts(self.recipe), (0, 7000, 14000))
        self.assertEqual({scene["video_artifact_id"] for scene in self.recipe["scenes"]},
                         {"art_9e344d7299e339f7781c17d5832985dc"})
        self.assertEqual([(scene["start_ms"], scene["end_ms"]) for scene in self.recipe["scenes"]],
                         [(0, 7000), (15000, 22000), (23000, 30000)])
        self.assertEqual(self.recipe["voice"], "Microsoft Sayaka")
        self.assertEqual(self.recipe["rate"], 0)

    def test_silent_capture_is_not_mixed_as_recorded_speech(self) -> None:
        self.assertEqual(self.recipe["audio_mix_preset"], "narration_only_v1")
        self.assertTrue(all(scene["volume_percent"] == 0 for scene in self.recipe["scenes"]))
        self.assertEqual([scene["narration"] for scene in self.recipe["scenes"]], [
            "条件を添えて、三案まとめて依頼。",
            "候補が出たら、使う表現を選びます。",
            "最後は、日付と文字数を確認。",
        ])


if __name__ == "__main__":
    unittest.main()
