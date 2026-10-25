import tempfile
import unittest
from pathlib import Path
import numpy as np
from tools.studio.longform_audio import SR, plan_dialogue, write_pcm


class LongFormAudioTests(unittest.TestCase):
    def test_final_voice_leaves_requested_music_postroll(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'chapter-01'/'turn-00'
            path.mkdir(parents=True)
            write_pcm(path/'voice.wav',np.zeros(SR,dtype=np.float32))
            p=plan_dialogue([dict(id='chapter-01',title='終わり',target_seconds=5,tail_seconds=3.5,
                turns=[dict(speaker='female',text='確認')])],directory)
            self.assertGreaterEqual(p['seconds']-p['chapters'][0]['turns'][-1]['end'],3.5)

    def test_long_speech_expands_chapter_instead_of_trimming(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'chapter-01'
            for i in range(2):
                path=folder/f'turn-{i:02d}'
                path.mkdir(parents=True)
                write_pcm(path/'voice.wav',np.zeros(SR*2,dtype=np.float32))
            plan=plan_dialogue([dict(id='chapter-01',title='確認',target_seconds=3,
                turns=[dict(speaker='female',text='あ'),dict(speaker='male',text='い')])],directory)
            self.assertGreaterEqual(plan['seconds'],5.35)
            self.assertAlmostEqual(plan['chapters'][0]['turns'][0]['end']-.5,2)
            self.assertLessEqual(plan['chapters'][0]['turns'][-1]['end'],plan['seconds'])

    def test_extra_hold_never_overlaps_the_next_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            for i in range(3):
                path=Path(directory)/'chapter-01'/f'turn-{i:02d}'
                path.mkdir(parents=True)
                write_pcm(path/'voice.wav',np.zeros(SR,dtype=np.float32))
            p=plan_dialogue([dict(id='chapter-01',title='表',target_seconds=12,
                turns=[dict(speaker='female',text='あ')]*3)],directory)
            turns=p['chapters'][0]['turns']
            self.assertTrue(all(a['end']<b['start'] for a,b in zip(turns,turns[1:])))
            self.assertLessEqual(turns[-1]['end'],12)


if __name__=='__main__':unittest.main()
