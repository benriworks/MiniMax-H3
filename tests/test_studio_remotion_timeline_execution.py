from __future__ import annotations

import json
import unittest

from tools.studio.remotion_timeline_execution import (
    RemotionTimelineError,
    RemotionTimelineValidationError,
    compile_remotion_timeline,
    remotion_timeline_audit_payload,
    remotion_timeline_cache_key,
    remotion_timeline_public_result,
    validate_remotion_timeline_payload,
)


ARTIFACT_ONE = "art_00000000000000000000000000000001"
ARTIFACT_TWO = "art_00000000000000000000000000000002"


class RemotionTimelineExecutionTests(unittest.TestCase):
    def public_payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "clips": [
                {
                    "video_artifact_id": ARTIFACT_ONE,
                    "start_ms": 0,
                    "end_ms": 2_000,
                    "volume_percent": 80,
                    "transition_to_next": {"type": "fade", "duration_ms": 500},
                    "overlay": {
                        "text": "生成AIを、もっと身近に。",
                        "start_ms": 250,
                        "end_ms": 1_750,
                        "position": "bottom",
                        "style_preset": "shorts_ja_large_v1",
                    },
                },
                {
                    "video_artifact_id": ARTIFACT_TWO,
                    "start_ms": 100,
                    "end_ms": 1_600,
                    "volume_percent": 0,
                    "transition_to_next": None,
                    "overlay": None,
                },
            ],
        }

    def internal_clips(self) -> list[dict[str, object]]:
        payload = validate_remotion_timeline_payload(self.public_payload())
        return [
            {
                **clip,
                "source_path": f"registered/clip-{index}.mp4",
                "source_bytes": 1_000 + index,
                "source_sha256": str(index + 1) * 64,
            }
            for index, clip in enumerate(payload["clips"])
        ]

    def tool_identity(self) -> dict[str, object]:
        return {
            "remotion": {"version": "4.0.517", "sha256": "A" * 64},
            "chromium": {"version": "151.0.7922.34", "sha256": "B" * 64},
        }

    def test_validates_exact_closed_recipe(self) -> None:
        normalized = validate_remotion_timeline_payload(self.public_payload())
        self.assertEqual(normalized, self.public_payload())
        invalid = (
            {**self.public_payload(), "component": "Arbitrary"},
            {**self.public_payload(), "schema_version": 2},
            {
                **self.public_payload(),
                "clips": [
                    {
                        **self.public_payload()["clips"][0],  # type: ignore[index]
                        "css": "position:fixed",
                    }
                ],
            },
        )
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(RemotionTimelineValidationError):
                validate_remotion_timeline_payload(body)

    def test_rejects_unbounded_or_inconsistent_controls(self) -> None:
        clips = self.public_payload()["clips"]  # type: ignore[assignment]
        first = clips[0]  # type: ignore[index]
        second = clips[1]  # type: ignore[index]
        cases = (
            [{**first, "volume_percent": 101}, second],
            [{**first, "transition_to_next": {"type": "slide", "duration_ms": 500}}, second],
            [{**first, "transition_to_next": {"type": "fade", "duration_ms": 2_000}}, second],
            [first, {**second, "transition_to_next": {"type": "fade", "duration_ms": 100}}],
            [
                {
                    **first,
                    "overlay": {
                        **first["overlay"],  # type: ignore[index]
                        "text": "one\ntwo\nthree\nfour\nfive",
                    },
                },
                second,
            ],
        )
        for clips_value in cases:
            with self.subTest(clips=clips_value), self.assertRaises(RemotionTimelineValidationError):
                validate_remotion_timeline_payload(
                    {"schema_version": 1, "clips": clips_value}
                )

    def test_compiles_half_up_frame_timing_and_transition_overlap(self) -> None:
        compiled = compile_remotion_timeline(self.internal_clips())
        self.assertEqual(compiled["frame_rate"], 24)
        self.assertEqual(compiled["duration_in_frames"], 72)
        self.assertEqual(compiled["duration_ms"], 3_000)
        self.assertEqual(compiled["clips"][0]["duration_in_frames"], 48)
        self.assertEqual(
            compiled["clips"][0]["transition_to_next"]["duration_in_frames"], 12
        )
        self.assertEqual(compiled["clips"][1]["start_frame"], 36)
        self.assertEqual(compiled["clips"][1]["trim_before_frame"], 2)
        self.assertEqual(compiled["clips"][1]["trim_after_frame"], 38)

    def test_cache_and_audit_bind_controls_without_storing_raw_telop(self) -> None:
        clips = self.internal_clips()
        key = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity())
        audit = remotion_timeline_audit_payload(clips, cache_key=key)
        serialized = json.dumps(audit, ensure_ascii=False)
        self.assertRegex(key, r"^[0-9A-F]{64}$")
        self.assertNotIn("生成AIを、もっと身近に。", serialized)
        self.assertEqual(audit["clips"][0]["overlay"]["text_chars"], 13)
        changed = [dict(item) for item in clips]
        changed[0] = {**changed[0], "volume_percent": 79}
        self.assertNotEqual(
            key,
            remotion_timeline_cache_key(changed, tool_identity=self.tool_identity()),
        )

    def test_public_result_is_closed_and_requires_audio_policy(self) -> None:
        raw = {
            "duration_ms": 3_000,
            "cache_key": "C" * 64,
            "cache_hit": False,
            "provider": "local_remotion_timeline",
            "provider_task_id": None,
            "actual_cost": 0,
            "timing_source": "remotion_frames",
            "has_audio": True,
        }
        result = remotion_timeline_public_result(
            raw,
            expected_cache_key="C" * 64,
            expected_duration_ms=3_000,
            cache_hit=False,
            artifacts=[],
        )
        self.assertEqual(result["video_dimensions"], {"width": 1080, "height": 1920})
        self.assertEqual(result["output_policy"]["audio"], "aac_48000_stereo")
        with self.assertRaises(RemotionTimelineError):
            remotion_timeline_public_result(
                {**raw, "has_audio": False},
                expected_cache_key="C" * 64,
                expected_duration_ms=3_000,
                cache_hit=False,
                artifacts=[],
            )


if __name__ == "__main__":
    unittest.main()
