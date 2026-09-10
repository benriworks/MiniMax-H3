from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import wave

SCRIPT = Path(__file__).resolve().parents[1] / "assemble_audio_review.py"
spec = importlib.util.spec_from_file_location("audio_review", SCRIPT)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


class AudioReviewTests(unittest.TestCase):
    def test_exact_scheduled_pcm_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scheduled.wav"
            with wave.open(str(path), "wb") as handle:
                handle.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
                handle.writeframes(b"\0\0" * 21 * 48000)
            review.validate_pcm(path)

    def test_short_or_wrong_rate_pcm_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            for rate, seconds in ((48000, 4), (22050, 21)):
                path = Path(folder) / f"{rate}-{seconds}.wav"
                with wave.open(str(path), "wb") as handle:
                    handle.setparams((1, 2, rate, 0, "NONE", "not compressed"))
                    handle.writeframes(b"\0\0" * seconds * rate)
                with self.assertRaises(ValueError):
                    review.validate_pcm(path)

    def test_missing_and_outside_inputs_are_rejected(self) -> None:
        with self.assertRaises((ValueError, FileNotFoundError)):
            review.regular(Path("missing-review-input.wav"))
        with tempfile.NamedTemporaryFile() as handle:
            with self.assertRaises(ValueError):
                review.regular(Path(handle.name))

    def test_changed_input_hash_is_rejected(self) -> None:
        item = review.record(SCRIPT)
        self.assertEqual(review.checked(item), SCRIPT.resolve())
        with self.assertRaises(ValueError):
            review.checked({**item, "sha256": "0" * 64})


if __name__ == "__main__":
    unittest.main()
