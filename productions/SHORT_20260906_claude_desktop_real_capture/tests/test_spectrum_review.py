from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

import numpy as np

SCRIPT = Path(__file__).resolve().parents[1] / "spectrum_review.py"
spec = importlib.util.spec_from_file_location("spectrum_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class SpectrumReviewTests(unittest.TestCase):
    def test_inserted_gap_is_excluded_and_utterances_not_concatenated(self):
        rate = 2048
        t = np.arange(rate) / rate
        phrase = .5 * np.sin(2 * np.pi * 256 * t)
        samples = np.concatenate([phrase, np.zeros(rate), phrase / 2])
        intervals = [(0, 1), (2, 3)]
        f, power, individual = review.mean_speech_psd(samples, rate, intervals, 1024)
        samples[rate:2 * rate] = 1
        _, changed, _ = review.mean_speech_psd(samples, rate, intervals, 1024)
        np.testing.assert_array_equal(power, changed)
        np.testing.assert_allclose(power, (individual[0] + individual[1]) / 2)
        self.assertAlmostEqual(review.band_energy(f, power, 240, 272), .078125, places=8)

    def test_duration_weighting_uses_individual_power_not_db(self):
        rate = 2048
        first = .5 * np.sin(2 * np.pi * 256 * np.arange(rate) / rate)
        second = .25 * np.sin(2 * np.pi * 512 * np.arange(2 * rate) / rate)
        _, power, individual = review.mean_speech_psd(np.concatenate([first, second]), rate, [(0, 1), (1, 3)], 1024)
        np.testing.assert_allclose(power, (individual[0] + 2 * individual[1]) / 3)

    def test_short_empty_or_out_of_bounds_intervals_rejected(self):
        for intervals in ([], [(0, .1)], [(-1, 1)], [(0, 3)]):
            with self.assertRaises(ValueError):
                review.mean_speech_psd(np.zeros(2048), 2048, intervals, 1024)

    def test_prominence_distinguishes_flat_spectrum_from_fixed_line(self):
        f = np.arange(201)
        power = np.ones(201)
        self.assertAlmostEqual(review.line_prominence(f, power, 60), 0)
        power[60] = 100
        self.assertAlmostEqual(review.line_prominence(f, power, 60), 20)

    def test_quiet_summary_keeps_zero_distinct_from_low_level_content(self):
        samples = np.concatenate([np.zeros(20), np.full(20, .001), np.ones(20)])
        result = review.quiet_summary(samples, 1000, [(0, .06)])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["exact_zero_count"], 1)
        np.testing.assert_allclose(result["nonzero_rms_dbfs_min_median_max"], [-60, -60, -60])


if __name__ == "__main__":
    unittest.main()
