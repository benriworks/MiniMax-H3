import unittest
import numpy as np
from tools.studio.longform_audio import music_bright
from tools.studio.music_mix import music_gain_envelope

class MusicAutomationTests(unittest.TestCase):
    def test_legacy_bright_music_is_unchanged(self):
        samples=music_bright(4)
        # Legacy waveform samples, with tolerance for platform floating-point math.
        np.testing.assert_allclose(samples[[100,1000,8000,24000,48000,72000,95000]],
            [[.0000980166,.0000895233],[-.0012141495,-.0009222881],[-.0005683642,-.0015943926],
             [.0028237719,.0035148270],[.0031481644,.0051834579],[-.0012652758,-.0025058964],
             [-.0001365145,-.0001018785]],atol=1e-7,rtol=1e-5)

    def test_edge_boost_and_smooth_speech_ducking(self):
        sr=1000
        gain=music_gain_envelope(8,[(3,4)],sample_rate=sr,base_gain=2,duck_gain=.2,
                                 intro_seconds=1,outro_seconds=2,edge_boost_db=3)
        self.assertAlmostEqual(float(gain[3500]),.4,places=5)
        self.assertAlmostEqual(float(gain[2000]),2.,places=5)
        self.assertGreater(float(gain[0]),2.8)
        self.assertGreater(float(gain[-1]),2.8)
        self.assertLess(float(np.max(np.abs(np.diff(gain)))),.02)

    def test_invalid_speech_interval_is_rejected(self):
        with self.assertRaises(ValueError):music_gain_envelope(5,[(4,6)])

if __name__=='__main__':unittest.main()
