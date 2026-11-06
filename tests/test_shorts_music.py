import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
import wave

import numpy as np

from tools.studio.shorts_creator import audio_signature, sound_design, validate_story


class ShortsMusicTests(unittest.TestCase):
    scenes = [{'from': 0, 'kind': 'hero', 'items': []},
              {'from': 24, 'kind': 'steps', 'items': [{'label': '調査'}]}]

    def render(self, root, name, preset='electro_pop_v1', speech=((.2, 1.5),), profile='explanation_v1'):
        out = root / name
        out.mkdir()
        sound_design(out, self.scenes, speech, 2, preset, profile)
        return out

    def test_existing_default_score_and_effects_keep_original_pcm(self):
        # Captured before adding the preset: previously verified edits must stay stable.
        with tempfile.TemporaryDirectory() as temp:
            out = self.render(Path(temp), 'legacy', profile='legacy')
            expected = {'music.wav': '05AA1068D6ED757A1B63872DFB66BCE83A0DB50819197C2F4BDDB430374B0018',
                        'effects.wav': 'DEB4B0A41B868D9C7112540236DAE2B45D5357CB775AE85F1F668711BFB4BB78'}
            for name, digest in expected.items():
                self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest().upper(), digest)

    def test_alternate_score_is_repeatable_stereo_and_changes_only_music(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = self.render(root, 'old')
            new = self.render(root, 'new', 'bright_groove_v1')
            again = self.render(root, 'again', 'bright_groove_v1')
            self.assertNotEqual((old / 'music.wav').read_bytes(), (new / 'music.wav').read_bytes())
            self.assertEqual((new / 'music.wav').read_bytes(), (again / 'music.wav').read_bytes())
            self.assertEqual((old / 'effects.wav').read_bytes(), (new / 'effects.wav').read_bytes())
            with wave.open(str(new / 'music.wav'), 'rb') as wav:
                self.assertEqual((wav.getnchannels(), wav.getframerate(), wav.getnframes()), (2, 48000, 96000))
                pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2')
                self.assertLess(np.abs(pcm.astype(float)).max(), 32700)

    def test_default_mix_is_louder_and_keeps_effects_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            old=self.render(root,'old',speech=(),profile='legacy')
            new=self.render(root,'new',speech=())
            def rms(path):
                with wave.open(str(path/'music.wav'),'rb') as wav:
                    pcm=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(float)
                return np.sqrt(np.mean(pcm**2))
            self.assertGreater(rms(new),rms(old)*1.8)
            self.assertEqual((old/'effects.wav').read_bytes(),(new/'effects.wav').read_bytes())

    def test_new_music_keeps_narration_ducking(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            quiet = self.render(root, 'quiet', 'bright_groove_v1')
            full = self.render(root, 'full', 'bright_groove_v1', ())
            def energy(path):
                with wave.open(str(path / 'music.wav'), 'rb') as wav:
                    samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype='<i2').reshape(-1, 2)
                return np.mean(samples[24000:48000].astype(float) ** 2)
            self.assertLess(energy(quiet), energy(full) * .13)

    def test_music_change_invalidates_audio_reuse_and_unknown_presets_fail(self):
        story = {'id': 'example', 'scenes': []}
        explicit = copy.deepcopy(story)
        explicit['music_preset'] = 'electro_pop_v1'
        self.assertEqual(audio_signature(story), audio_signature(explicit))
        explicit['music_preset'] = 'bright_groove_v1'
        self.assertNotEqual(audio_signature(story), audio_signature(explicit))
        for preset in ['unknown', None, {}]:
            with self.assertRaisesRegex(ValueError, 'Unknown music preset'):
                validate_story({'schema_version': 1, 'duration_seconds': 45, 'music_preset': preset})


if __name__ == '__main__':
    unittest.main()
