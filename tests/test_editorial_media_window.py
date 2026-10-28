import unittest

from tools.studio.shorts_creator import presenter_media_window


class EditorialMediaWindowTests(unittest.TestCase):
    def setUp(self):
        self.probe = {'width': 768, 'height': 1376, 'duration': '5.166667'}

    def test_short_source_stops_at_124_frames_without_cutting_long_scene(self):
        result = presenter_media_window(self.probe, {'kind': 'editorial'}, 150)
        self.assertEqual(result, {'mediaPlayFrames': 124, 'mediaDurationInFrames': 124})
        self.assertEqual(presenter_media_window(self.probe, {'kind': 'editorial', 'mediaStart': 24}, 150)['mediaPlayFrames'], 100)

    def test_scene_shorter_than_source_uses_only_its_own_duration(self):
        self.assertEqual(presenter_media_window(self.probe, {'kind': 'editorial'}, 96)['mediaPlayFrames'], 96)

    def test_insufficient_source_and_invalid_time_fail_before_render(self):
        for start in (-1, True, 101, 124):
            with self.subTest(start=start), self.assertRaises(ValueError):
                presenter_media_window(self.probe, {'kind': 'editorial', 'mediaStart': start}, 150)
        with self.assertRaises(ValueError):
            presenter_media_window({**self.probe, 'duration': 'NaN'}, {'kind': 'editorial'}, 150)

    def test_other_scene_types_keep_the_original_duration_requirement(self):
        with self.assertRaises(ValueError):
            presenter_media_window(self.probe, {'kind': 'hero'}, 150)
        self.assertEqual(presenter_media_window(self.probe, {'kind': 'hero'}, 96), {})


if __name__ == '__main__':
    unittest.main()
