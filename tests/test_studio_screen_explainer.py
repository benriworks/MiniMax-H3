from __future__ import annotations

import copy
import unittest

from tests.test_studio_announcement_video import recipe
from tools.studio.announcement_video import (
    AnnouncementVideoValidationError,
    announcement_narration_segment_starts,
    announcement_recipe_audit_summary,
    announcement_recipe_digest,
    announcement_recipe_to_detailed_payload,
    validate_announcement_recipe_payload,
)


class ScreenExplainerTemplateTests(unittest.TestCase):
    def screen_recipe(self, seconds=5):
        value = recipe()
        value['template_preset'] = 'screen_explainer_ja_v1'
        for scene in value['scenes']:
            scene['start_ms'] = 0
            scene['end_ms'] = seconds * 1000
        return value

    def test_hard_cuts_preserve_screen_and_exact_scene_starts(self):
        for seconds in (5, 7, 10):
            with self.subTest(seconds=seconds):
                normalized = validate_announcement_recipe_payload(self.screen_recipe(seconds))
                detailed = announcement_recipe_to_detailed_payload(normalized)
                self.assertEqual(announcement_narration_segment_starts(normalized), (0, seconds * 1000, seconds * 2000))
                self.assertEqual([clip['transition_to_next'] for clip in detailed['clips']], [None] * 3)
                self.assertEqual([clip['layout_preset'] for clip in detailed['clips']], ['screen_explainer_v1'] * 3)
                self.assertEqual([clip['overlay']['position'] for clip in detailed['clips']], ['top'] * 3)
                self.assertEqual(announcement_recipe_audit_summary(normalized)['overlay_policy'], 'screen_explainer_safe_header_v1')

    def test_legacy_recipe_and_digest_remain_distinct(self):
        legacy = recipe()
        original = copy.deepcopy(legacy)
        screen = self.screen_recipe()
        self.assertNotEqual(announcement_recipe_digest(legacy), announcement_recipe_digest(screen))
        self.assertNotIn('layout_preset', announcement_recipe_to_detailed_payload(legacy)['clips'][0])
        self.assertEqual(legacy, original)
        self.assertEqual(announcement_recipe_digest(legacy), 'C9228C74A3DB6AB62DFB620AC0DBD185786CFA0EC5F108B8669B26B0DCE1FA33')
        self.assertEqual(announcement_recipe_digest(screen), '10C6A8564400729BB10C6BBC369DEAB41F357DFD3C78F62B569574E5EC89FD87')
        self.assertNotIn('focus_regions', announcement_recipe_audit_summary(screen))

    def test_explicit_focus_reaches_detailed_and_audit_without_changing_narration_timing(self):
        value = self.screen_recipe()
        baseline_digest = announcement_recipe_digest(value)
        region = {'x': 0.25, 'y': 0.25, 'width': 0.5, 'height': 0.5}
        value['scenes'][1]['focus_region'] = region
        normalized = validate_announcement_recipe_payload(value)
        self.assertEqual(normalized['scenes'][1]['focus_region'], region)
        detailed = announcement_recipe_to_detailed_payload(normalized)
        self.assertEqual(detailed['clips'][1]['focus_region'], region)
        self.assertNotIn('focus_region', detailed['clips'][0])
        self.assertNotEqual(announcement_recipe_digest(value), baseline_digest)
        self.assertEqual(announcement_narration_segment_starts(value), (0, 5000, 10000))
        self.assertEqual(announcement_recipe_audit_summary(normalized)['focus_regions'], [None, region, None])

    def test_focus_rejects_legacy_recipes_and_invalid_explicit_values(self):
        value = recipe()
        value['scenes'][0]['focus_region'] = {'x': 0, 'y': 0, 'width': 1, 'height': 1}
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload(value)
        for region in (None, {}, {'x': True, 'y': 0, 'width': 1, 'height': 1}, {'x': 0.8, 'y': 0, 'width': 0.3, 'height': 1}):
            value = self.screen_recipe()
            value['scenes'][0]['focus_region'] = region
            with self.subTest(region=region), self.assertRaises(AnnouncementVideoValidationError):
                validate_announcement_recipe_payload(value)

    def test_invalid_duration_unknown_template_and_destructive_sharpening_rejected(self):
        for change in ('duration', 'template', 'sharpen'):
            value = self.screen_recipe()
            if change == 'duration':
                value['scenes'][0]['end_ms'] = 4000
            elif change == 'template':
                value['template_preset'] = 'arbitrary'
            else:
                value['scenes'][0]['visual_preset'] = 'h3_low_res_sharp_v1'
            with self.subTest(change=change), self.assertRaises(AnnouncementVideoValidationError):
                validate_announcement_recipe_payload(value)

    def test_non_string_template_is_a_validation_error(self):
        for invalid in ([], {}, None, 1, True):
            value = self.screen_recipe()
            value['template_preset'] = invalid
            with self.subTest(value=invalid), self.assertRaises(AnnouncementVideoValidationError):
                validate_announcement_recipe_payload(value)

    def test_closed_theme_roundtrips_compiles_and_changes_only_visual_identity(self):
        legacy = self.screen_recipe()
        self.assertNotIn('screen_theme', validate_announcement_recipe_payload(legacy))
        self.assertNotIn('screen_theme', announcement_recipe_audit_summary(legacy))
        baseline = announcement_recipe_to_detailed_payload(legacy)
        digests = {announcement_recipe_digest(legacy)}
        for theme in ('neutral_v1', 'claude_desktop_v1', 'claude_code_v1', 'technical_v1', 'claude_editorial_v1'):
            with self.subTest(theme=theme):
                selected = {**legacy, 'screen_theme': theme}
                normalized = validate_announcement_recipe_payload(selected)
                self.assertEqual(normalized['screen_theme'], theme)
                self.assertEqual(announcement_recipe_audit_summary(selected)['screen_theme'], theme)
                detailed = announcement_recipe_to_detailed_payload(selected)
                self.assertEqual([clip['screen_theme'] for clip in detailed['clips']], [theme] * 3)
                self.assertEqual({key: value for key, value in detailed.items() if key != 'clips'},
                                 {key: value for key, value in baseline.items() if key != 'clips'})
                self.assertEqual(announcement_narration_segment_starts(selected), (0, 5000, 10000))
                digests.add(announcement_recipe_digest(selected))
        self.assertEqual(len(digests), 6)

    def test_unknown_theme_and_theme_on_announcement_are_rejected(self):
        for theme in (None, {}, [], True, 1, 'orange', 'https://example.com/font.ttf'):
            with self.subTest(theme=theme), self.assertRaises(AnnouncementVideoValidationError):
                validate_announcement_recipe_payload({**self.screen_recipe(), 'screen_theme': theme})
        with self.assertRaises(AnnouncementVideoValidationError):
            validate_announcement_recipe_payload({**recipe(), 'screen_theme': 'neutral_v1'})


if __name__ == '__main__':
    unittest.main()
