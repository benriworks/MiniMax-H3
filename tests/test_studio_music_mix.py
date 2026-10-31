import unittest
from pathlib import Path
import tempfile
import numpy as np
from tools.studio.longform_audio import music_bright, assemble_audio, write_pcm, read_voice, SR
from tools.studio.music_mix import music_gain_envelope, default_bgm_bed, DEFAULT_BGM_PROFILE

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

    def test_default_bed_matches_v04_explicit_settings_and_preserves_input(self):
        raw=music_bright(4,fade_in_seconds=0,fade_out_seconds=0)
        original=raw.copy();spans=[(.6,2.2)]
        expected=music_bright(4,fade_in_seconds=.08,fade_out_seconds=.25)
        expected*=music_gain_envelope(4,spans,base_gain=1.3*10**(4/20),duck_gain=.2,edge_boost_db=3.)[:,None]
        np.testing.assert_array_equal(default_bgm_bed(raw,4,spans),expected)
        np.testing.assert_array_equal(raw,original)

    def test_longform_default_keeps_voice_and_records_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);voice=root/'voice.wav'
            write_pcm(voice,np.sin(np.arange(SR)*2*np.pi*440/SR).astype(np.float32)*.2)
            plan={'seconds':4,'chapters':[{'turns':[{'voice_path':str(voice),'start':1}]}]}
            info=assemble_audio(plan,root/'new',music_style='bright')
            assemble_audio(plan,root/'old',music_style='bright',bgm_mix_profile='legacy')
            self.assertEqual(info['bgm_mix_profile'],DEFAULT_BGM_PROFILE['id'])
            self.assertEqual((root/'new/narration.wav').read_bytes(),(root/'old/narration.wav').read_bytes())
            self.assertEqual(info['duck_gain'],.2)

if __name__=='__main__':unittest.main()
