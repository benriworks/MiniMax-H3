import tempfile,unittest,wave
from pathlib import Path
import numpy as np
from tools.studio.dialogue_avatar import validate_windows,voice_gate,DialogueDriver,registered_translation,SpriteAtlas
from PIL import Image


class AvatarPolicyTests(unittest.TestCase):
    def test_presenters_cannot_cover_registration_or_overlap_each_other(self):
        window=dict(start=2,end=4,male='curious',female='serious')
        with self.assertRaises(ValueError):validate_windows([window],10,protected=[(3,5)])
        with self.assertRaises(ValueError):validate_windows([window,dict(window,start=3,end=6)],10)
        self.assertTrue(validate_windows([window],10,protected=[(4,6)]))

    def test_audio_silence_stays_closed_and_listener_cannot_talk(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'voice.wav';rate=24000
            samples=np.concatenate([np.zeros(rate//2),np.sin(2*np.pi*220*np.arange(rate//2)/rate)*.2])
            with wave.open(str(p),'wb') as f:
                f.setparams((1,2,rate,0,'NONE','not compressed'));f.writeframes((samples*32767).astype('<i2').tobytes())
            gate=voice_gate(p)
            self.assertFalse(any(gate['gates'][:12]));self.assertTrue(any(gate['gates'][12:]))
            driver=DialogueDriver([dict(start=2,end=3,speaker='female',voice_path=str(p))])
            self.assertFalse(driver.state(2.8,'male')['opened'])
            self.assertFalse(driver.state(2.1,'female')['opened'])
            self.assertTrue(driver.state(2.8,'female')['opened'])
            self.assertFalse(driver.state(3,'female')['opened'])

    def test_registration_corrects_translation_without_scaling(self):
        rng=np.random.default_rng(42)
        original=Image.fromarray(rng.integers(0,255,(80,80,3),dtype=np.uint8))
        shifted=Image.fromarray(np.roll(np.asarray(original),(3,-2),(0,1)))
        aligned,shift=registered_translation(original,shifted)
        self.assertEqual(shift,(2,-3))
        self.assertTrue(np.array_equal(np.asarray(aligned)[5:-5,5:-5],np.asarray(original)[5:-5,5:-5]))

    def test_atlas_registration_handles_a_24_pixel_generated_panel_offset(self):
        rng=np.random.default_rng(9)
        tile=rng.integers(0,255,(400,400,3),dtype=np.uint8)
        sheet=Image.new('RGB',(800,2000))
        for row in range(5):
            sheet.paste(Image.fromarray(tile),(0,row*400))
            sheet.paste(Image.fromarray(np.roll(tile,-24,axis=1)),(400,row*400))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'atlas.png';sheet.save(path)
            atlas=SpriteAtlas(path,'female')
            self.assertTrue(all(item['shift']==(24,0) for item in atlas.registration))


if __name__=='__main__':unittest.main()
