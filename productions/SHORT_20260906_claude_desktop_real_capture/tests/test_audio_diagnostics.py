"""Pure signal tests: no Studio service, FFmpeg or synthesis is invoked."""
import importlib.util
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location("audio_diagnostics", Path(__file__).resolve().parents[1] / "audio_diagnostics.py")
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


class AudioDiagnosticsTests(unittest.TestCase):
    def test_fixed_delay_and_gain_recovered(self):
        rng = np.random.default_rng(15)
        reference = np.zeros(6000)
        reference[200:5500] = rng.normal(0, .06, 5300)
        candidate = np.r_[np.zeros(17), reference[:-17]] * .72
        measured, aligned = audio.residual(reference, candidate, 48000)
        self.assertEqual(measured["lag_samples"], 17)
        self.assertAlmostEqual(measured["least_squares_candidate_gain"], .72)
        np.testing.assert_allclose(reference, aligned, atol=1e-12)

    def test_negative_lag_and_length(self):
        a = np.arange(10, dtype=float)
        np.testing.assert_equal(audio.align(a, -2, 10), [0, 0, 0, 1, 2, 3, 4, 5, 6, 7])
        np.testing.assert_equal(audio.align(a, 2, 10), [2, 3, 4, 5, 6, 7, 8, 9, 0, 0])

    def test_dropouts_flag_only_short_interior_gap(self):
        a = np.full(48000, .1)
        a[:4800] = 0
        a[12000:12480] = 0
        a[24000:28800] = 0
        row = audio.diagnostics(a, 48000)
        self.assertEqual(row["possible_short_dropout_count"], 1)
        self.assertEqual(row["possible_short_dropouts"][0]["duration_ms"], 10)

    def test_reject_nonfinite_signal(self):
        with self.assertRaises(ValueError):
            audio.diagnostics(np.array([0, float("nan")]), 48000)

    def test_no_periodic_noise_verdict_for_tone(self):
        a = .1*np.sin(2*np.pi*180*np.arange(48000)/48000)
        row = audio.diagnostics(a, 48000)
        self.assertEqual(row["full_scale_samples"], 0)
        self.assertEqual(row["possible_short_dropout_count"], 0)
        self.assertIn("do not establish noise", row["periodicity_warning"])

    def test_reject_path_traversal_before_io(self):
        with self.assertRaises(ValueError):
            audio.checked_path({"rel_path": "../outside.wav"})


if __name__ == "__main__":
    unittest.main()
