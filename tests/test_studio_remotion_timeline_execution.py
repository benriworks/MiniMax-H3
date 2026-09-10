from __future__ import annotations

import json
import unittest

from tools.studio.remotion_timeline_execution import (
    RemotionTimelineError,
    RemotionTimelineValidationError,
    compile_remotion_timeline,
    remotion_timeline_audit_payload,
    remotion_timeline_cache_key,
    normalize_internal_clips,
    remotion_timeline_public_result,
    validate_remotion_timeline_payload,
    validate_focus_region,
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
        self.assertEqual(
            ["preserve_v1", "preserve_v1"],
            [clip["visual_preset"] for clip in normalized["clips"]],
        )
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
            {
                **self.public_payload(),
                "clips": [
                    {
                        **self.public_payload()["clips"][0],  # type: ignore[index]
                        "visual_preset": "unsharp=1.0",
                    },
                    self.public_payload()["clips"][1],  # type: ignore[index]
                ],
            },
        )
        for body in invalid:
            with self.subTest(body=body), self.assertRaises(RemotionTimelineValidationError):
                validate_remotion_timeline_payload(body)

    def test_rejects_non_string_visual_presets_as_validation_errors(self) -> None:
        for visual_preset in ([], {}, None, 1):
            payload = self.public_payload()
            clips = payload["clips"]
            assert isinstance(clips, list)
            first = clips[0]
            assert isinstance(first, dict)
            first["visual_preset"] = visual_preset
            with self.subTest(visual_preset=visual_preset), self.assertRaises(
                RemotionTimelineValidationError
            ):
                validate_remotion_timeline_payload(payload)

    def test_layout_omission_preserves_historical_payload_compile_and_cache(self) -> None:
        clips = self.internal_clips()
        self.assertTrue(all("layout_preset" not in item for item in clips))
        self.assertTrue(all("layout_preset" not in item for item in compile_remotion_timeline(clips)["clips"]))
        key = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity())
        self.assertEqual(key, "A26F91DCB95DFBE4C6CAABC909AE92C963E7FAF2A7D97494D3E7A3BD90404054")
        self.assertTrue(all("layout_preset" not in item for item in remotion_timeline_audit_payload(clips, cache_key=key)["clips"]))

    def test_explicit_layout_is_bound_to_compile_audit_and_cache(self) -> None:
        clips = self.internal_clips()
        clips[0]["overlay"] = None
        baseline = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity())
        keys = set()
        for preset in ("full_bleed_v1", "screen_explainer_v1"):
            with self.subTest(preset=preset):
                selected = [{**clips[0], "layout_preset": preset}, clips[1]]
                normalized = normalize_internal_clips(selected)
                self.assertEqual(normalized[0]["layout_preset"], preset)
                self.assertNotIn("layout_preset", normalized[1])
                self.assertEqual(compile_remotion_timeline(selected)["clips"][0]["layout_preset"], preset)
                key = remotion_timeline_cache_key(selected, tool_identity=self.tool_identity())
                self.assertNotEqual(key, baseline)
                keys.add(key)
                self.assertEqual(remotion_timeline_audit_payload(selected, cache_key=key)["clips"][0]["layout_preset"], preset)
        self.assertEqual(len(keys), 2)

    def test_focus_is_optional_and_binds_compile_audit_and_cache(self) -> None:
        clips = self.internal_clips()
        clips[0].update(layout_preset="screen_explainer_v1", overlay=None)
        baseline = remotion_timeline_cache_key(clips, tool_identity=self.tool_identity())
        self.assertNotIn("focus_region", normalize_internal_clips(clips)[0])
        self.assertNotIn("focus_region", compile_remotion_timeline(clips)["clips"][0])
        region = {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}
        selected = [{**clips[0], "focus_region": region}, clips[1]]
        self.assertEqual(normalize_internal_clips(selected)[0]["focus_region"], region)
        self.assertEqual(compile_remotion_timeline(selected)["clips"][0]["focus_region"], region)
        key = remotion_timeline_cache_key(selected, tool_identity=self.tool_identity())
        self.assertNotEqual(key, baseline)
        self.assertEqual(remotion_timeline_audit_payload(selected, cache_key=key)["clips"][0]["focus_region"], region)
        moved = [{**selected[0], "focus_region": {**region, "x": 0.2}}, selected[1]]
        self.assertNotEqual(key, remotion_timeline_cache_key(moved, tool_identity=self.tool_identity()))

    def test_theme_is_optional_closed_and_bound_to_compile_audit_and_cache(self) -> None:
        clips = self.internal_clips()
        clips[0].update(layout_preset="screen_explainer_v1", overlay=None)
        keys = {remotion_timeline_cache_key(clips, tool_identity=self.tool_identity())}
        self.assertNotIn("screen_theme", normalize_internal_clips(clips)[0])
        for theme in ("neutral_v1", "claude_desktop_v1", "claude_code_v1", "technical_v1"):
            with self.subTest(theme=theme):
                selected = [{**clips[0], "screen_theme": theme}, clips[1]]
                self.assertEqual(normalize_internal_clips(selected)[0]["screen_theme"], theme)
                self.assertEqual(compile_remotion_timeline(selected)["clips"][0]["screen_theme"], theme)
                key = remotion_timeline_cache_key(selected, tool_identity=self.tool_identity())
                keys.add(key)
                self.assertEqual(remotion_timeline_audit_payload(selected, cache_key=key)["clips"][0]["screen_theme"], theme)
                self.assertNotIn("screen_theme", selected[1])
        self.assertEqual(len(keys), 5)
        for theme in (None, {}, [], 1, True, "orange", "../font.ttf"):
            with self.subTest(theme=theme), self.assertRaises(RemotionTimelineValidationError):
                normalize_internal_clips([{**clips[0], "screen_theme": theme}, clips[1]])
        for layout in (None, "full_bleed_v1"):
            invalid = {**self.internal_clips()[0], "screen_theme": "neutral_v1"}
            if layout is not None:
                invalid["layout_preset"] = layout
            with self.subTest(layout=layout), self.assertRaises(RemotionTimelineValidationError):
                normalize_internal_clips([invalid, clips[1]])
        self.assertEqual(compile_remotion_timeline(clips)["duration_in_frames"], compile_remotion_timeline(selected)["duration_in_frames"])

    def test_focus_accepts_bounded_regions_and_normalizes_integral_floats(self) -> None:
        for region in (
            {"x": 0, "y": 0, "width": 1, "height": 1},
            {"x": 0.8, "y": 0.8, "width": 0.2, "height": 0.2},
            {"x": 0, "y": 0.25, "width": 0.5, "height": 0.75},
            {"x": 0.0001, "y": 0.1234, "width": 0.9999, "height": 0.8766},
        ):
            with self.subTest(region=region):
                self.assertEqual(validate_focus_region(region), region)
        self.assertEqual(json.dumps(validate_focus_region({"x": -0.0, "y": 0.0, "width": 1.0, "height": 1.0})), '{"x": 0, "y": 0, "width": 1, "height": 1}')

    def test_focus_rejects_non_numbers_unknown_keys_outside_bounds_and_other_layouts(self) -> None:
        region = {"x": 0.25, "y": 0.25, "width": 0.5, "height": 0.5}
        invalid = [None, [], {}, {**region, "unexpected": 1}, {"x": 0, "y": 0, "width": 1}]
        for field in region:
            invalid.extend({**region, field: value} for value in (None, True, "0.5", float("nan"), float("inf"), -0.01, 1.01, 10 ** 1000, 0.00001, 0.20001, 0.2500000001))
        invalid.extend([{**region, "width": 0.1999}, {**region, "height": 0.1999}, {**region, "x": 0.6}, {**region, "y": 0.6}])
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(RemotionTimelineValidationError):
                validate_focus_region(value)
        for layout in (None, "full_bleed_v1"):
            clips = self.internal_clips()
            clips[0].update(focus_region=region, overlay=None)
            if layout is not None:
                clips[0]["layout_preset"] = layout
            with self.subTest(layout=layout), self.assertRaises(RemotionTimelineValidationError):
                normalize_internal_clips(clips)

    def test_screen_layout_rejects_unknown_values_cropping_and_unsafe_headlines(self) -> None:
        payload = self.public_payload()
        original = payload["clips"][0]
        second = payload["clips"][1]
        valid = {**original, "layout_preset": "screen_explainer_v1", "overlay": {
            **original["overlay"], "text": "画面を選んで\n変更を確認", "position": "top",
        }}
        self.assertEqual(validate_remotion_timeline_payload({"schema_version": 1, "clips": [valid, second]})["clips"][0]["layout_preset"], "screen_explainer_v1")
        invalid = [
            {**valid, "layout_preset": value} for value in (None, [], {}, True, 1, "contain", "screen_explainer_v2")
        ] + [
            {**valid, "visual_preset": "h3_low_res_sharp_v1"},
            {**valid, "overlay": {**valid["overlay"], "position": "center"}},
            {**valid, "overlay": {**valid["overlay"], "text": "one\ntwo\nthree"}},
            {**valid, "overlay": {**valid["overlay"], "text": "画" * 11}},
            {**valid, "overlay": {**valid["overlay"], "text": "a" * 21}},
        ]
        for first in invalid:
            with self.subTest(first=first), self.assertRaises(RemotionTimelineValidationError):
                validate_remotion_timeline_payload({"schema_version": 1, "clips": [first, second]})
        broken_internal = self.internal_clips()
        broken_internal[0]["layout_preset"] = "arbitrary"
        with self.assertRaises(RemotionTimelineValidationError):
            normalize_internal_clips(broken_internal)

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
        self.assertEqual(audit["clips"][0]["visual_preset"], "preserve_v1")
        self.assertEqual(
            audit["output_policy"]["policy_version"],
            "remotion-source-fidelity-v2",
        )
        self.assertEqual(audit["output_policy"]["video_crf"], 16)
        self.assertEqual(
            audit["output_policy"]["render_frame_image_format"], "png"
        )
        explicit_body = self.public_payload()
        explicit_body["clips"] = [
            {**item, "visual_preset": "preserve_v1"}
            for item in explicit_body["clips"]  # type: ignore[union-attr]
        ]
        explicit_public = validate_remotion_timeline_payload(explicit_body)["clips"]
        explicit_preserve = [
            {
                **item,
                "source_path": clips[index]["source_path"],
                "source_bytes": clips[index]["source_bytes"],
                "source_sha256": clips[index]["source_sha256"],
            }
            for index, item in enumerate(explicit_public)
        ]
        self.assertEqual(
            key,
            remotion_timeline_cache_key(
                explicit_preserve, tool_identity=self.tool_identity()
            ),
        )
        sharpened = [dict(item) for item in clips]
        sharpened[0] = {**sharpened[0], "visual_preset": "h3_low_res_sharp_v1"}
        self.assertNotEqual(
            key,
            remotion_timeline_cache_key(
                sharpened, tool_identity=self.tool_identity()
            ),
        )
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
