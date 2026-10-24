import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from tools.studio.shorts_creator import load_supplied_narration,narration_inputs,record

class SuppliedNarrationTests(unittest.TestCase):
    def fixture(self,root):
        folder=root/'outputs/productions/example';folder.mkdir(parents=True)
        story={'id':'example','voice':'Aoede','rate':1,'pronunciations':[{'source':'AI','target':'エーアイ'}],
               'scenes':[{'narration':'AIを試す。'}]}
        def save(name,data):
            path=folder/name;path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');return path
        def audio(name,pcm):
            path=folder/name
            with wave.open(str(path),'wb') as wav:
                wav.setparams((1,2,24000,0,'NONE','not compressed'));wav.writeframes(pcm)
            return path
        original=audio('voice.wav',b'\x01\x02'*24000)
        narration=audio('narration.wav',b'\x01\x02'*24000)
        request=save('request.json',{'contents':[{'parts':[{'text':'Style\nTranscript:\nエーアイを試す。'}]}]})
        proof=save('verified.json',{'status':'technically_verified_listening_pending','model':'gemini-2.5-flash-preview-tts','voice':'Aoede',
            'files':[record(original),record(request)]})
        timings=save('timings.json',{'segments':[{'text':'AIを試す。','frames':24000,'duration_ms':1000}]})
        source=save('source.json',{'provider':'gemini','model':'gemini-2.5-flash-preview-tts','voice':'Aoede','inputs':narration_inputs(story),
            'generation_proofs':[record(proof)],'artifacts':[dict(record(p),name=p.name) for p in [narration,timings]]})
        return story,source

    def test_accepts_only_matching_inputs_and_verified_samples(self):
        with tempfile.TemporaryDirectory() as temp,patch('tools.studio.shorts_creator.ROOT',Path(temp)):
            story,source=self.fixture(Path(temp))
            voice,_=load_supplied_narration(story,source)
            self.assertEqual(voice['voice'],'Aoede')
            for field,value in [('voice','Kore'),('pronunciations',[])]:
                other=copy.deepcopy(story);other[field]=value
                with self.assertRaisesRegex(ValueError,'inputs changed'):load_supplied_narration(other,source)
            other=copy.deepcopy(story);other['scenes'][0]['narration']='別の原稿。'
            with self.assertRaisesRegex(ValueError,'inputs changed'):load_supplied_narration(other,source)

    def test_tampered_combined_audio_fails_even_after_its_hash_is_updated(self):
        with tempfile.TemporaryDirectory() as temp,patch('tools.studio.shorts_creator.ROOT',Path(temp)):
            story,source=self.fixture(Path(temp))
            path=source.parent/'narration.wav'
            with wave.open(str(path),'wb') as wav:
                wav.setparams((1,2,24000,0,'NONE','not compressed'));wav.writeframes(b'\x03\x04'*24000)
            data=json.loads(source.read_text(encoding='utf-8'))
            data['artifacts'][0]=dict(record(path),name=path.name)
            source.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'differs from verified speech'):load_supplied_narration(story,source)

    def test_failed_generation_and_inaccurate_timing_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp,patch('tools.studio.shorts_creator.ROOT',Path(temp)):
            story,source=self.fixture(Path(temp));data=json.loads(source.read_text(encoding='utf-8'))
            path=source.parent/'timings.json'
            timing=json.loads(path.read_text(encoding='utf-8'));timing['segments'][0]['duration_ms']=500
            path.write_text(json.dumps(timing),encoding='utf-8')
            data['artifacts'][1]=dict(record(path),name=path.name)
            source.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'duration mismatch'):load_supplied_narration(story,source)
            path=source.parent/'verified.json';proof=json.loads(path.read_text(encoding='utf-8'));proof['status']='unknown'
            path.write_text(json.dumps(proof),encoding='utf-8');data['generation_proofs']=[record(path)]
            source.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'not verified'):load_supplied_narration(story,source)

if __name__=='__main__':unittest.main()
