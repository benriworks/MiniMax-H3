"""Evidence normalization preserves original bytes and rejects changed pixels."""
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('demonstration_evidence', ROOT / 'productions/SERIES_20261022_claude_work/prepare_demonstrations.py')
evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evidence)


class EvidenceEncodingTests(unittest.TestCase):
    def test_misnamed_jpeg_keeps_original_bytes_and_decoded_pixels(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            with patch.object(evidence, 'PRIVATE', tmp_path):
                source = tmp_path / 'screen.png'
                Image.new('RGB', (23, 17), (82, 137, 192)).save(source, format='JPEG')
                original_bytes = source.read_bytes()
                context, original_format = evidence.decoded_context(source)
                self.assertEqual(original_format, 'JPEG')
                self.assertNotEqual(context, source)
                self.assertTrue(context.read_bytes().startswith(b'\x89PNG'))
                self.assertEqual(source.read_bytes(), original_bytes)
                with Image.open(source) as raw, Image.open(context) as png:
                    self.assertEqual((png.mode, png.size, png.tobytes()), (raw.mode, raw.size, raw.tobytes()))
                self.assertEqual(evidence.decoded_context(source)[0], context)
                Image.new('RGB', (23, 17), (0, 0, 0)).save(context, format='PNG')
                with self.assertRaisesRegex(ValueError, 'changed decoded pixels'):
                    evidence.decoded_context(source)
                self.assertEqual(source.read_bytes(), original_bytes)


    def test_actual_png_is_kept_without_conversion(self):
        with TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            with patch.object(evidence, 'PRIVATE', tmp_path):
                source = tmp_path / 'screen.png'
                Image.new('RGB', (23, 17), (82, 137, 192)).save(source, format='PNG')
                original = source.read_bytes()
                self.assertEqual(evidence.decoded_context(source), (source, 'PNG'))
                self.assertEqual(source.read_bytes(), original)
                self.assertFalse((tmp_path / 'decoded-png').exists())


if __name__ == '__main__':unittest.main()
