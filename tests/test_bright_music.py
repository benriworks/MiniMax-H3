import unittest
import numpy as np
from tools.studio.longform_audio import music_bright,assemble_audio,SR


class BrightMusicTests(unittest.TestCase):
    def test_reproducible_stereo_bed_is_finite_and_not_clipped(self):
        a=music_bright(2);b=music_bright(2)
        self.assertEqual(a.shape,(2*SR,2))
        self.assertTrue(np.isfinite(a).all());self.assertTrue(np.array_equal(a,b))
        self.assertGreater(float(np.max(np.abs(a))),.01)
        self.assertLess(float(np.max(np.abs(a))),.5)

    def test_unknown_profile_cannot_write_a_mix(self):
        with self.assertRaises(ValueError):assemble_audio({},None,music_style='unknown')


if __name__=='__main__':unittest.main()
