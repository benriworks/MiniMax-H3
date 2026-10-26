import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.error import HTTPError
from tools.studio.dialogue_narration import ROOT,payload,synthesize


class DialogueSafetyTests(unittest.TestCase):
    def test_unknown_speaker_cannot_construct_a_paid_request(self):
        with self.assertRaises(ValueError):payload('こんにちは','unknown')

    def test_quoted_dialogue_is_audio_only_and_keeps_the_voice(self):
        p=payload('入力を任せる','male','quoted_dialogue_v2')
        self.assertIn('<transcript>\n入力を任せる\n</transcript>',p['contents'][0]['parts'][0]['text'])
        self.assertEqual(p['generationConfig']['responseModalities'],['AUDIO'])
        self.assertEqual(p['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'],'Charon')

    def test_quoted_female_dialogue_does_not_request_a_male_voice(self):
        p=payload('任せてみよう','female','quoted_dialogue_v2')
        self.assertIn('Japanese female voice',p['contents'][0]['parts'][0]['text'])
        self.assertEqual(p['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'],'Aoede')

    def test_conversation_profile_quotes_questions_without_asking_for_an_answer(self):
        p=payload('何をしたいの？','male','conversational_v3')
        text=p['contents'][0]['parts'][0]['text']
        self.assertIn('never answer it',text)
        self.assertIn('<transcript>\n何をしたいの？\n</transcript>',text)
        self.assertEqual(p['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'],'Charon')

    def test_a_definite_rejection_is_not_submitted_again(self):
        error=HTTPError('https://example.invalid',400,'Bad request',{},io.BytesIO(json.dumps({'error':{'status':'INVALID_ARGUMENT','message':'Expected audio'}}).encode()))
        opener=Mock();opener.open.side_effect=error
        with tempfile.TemporaryDirectory(dir=ROOT/'outputs',prefix='dialogue-safety-') as directory:
            target=Path(directory)/'turn'
            with patch.dict(os.environ,{'GEMINI_API_KEY':'fake-unit-test-key'}),patch('urllib.request.build_opener',return_value=opener):
                with self.assertRaisesRegex(RuntimeError,'rejected'):synthesize(target,'確認します','female')
                with self.assertRaisesRegex(RuntimeError,'incomplete'):synthesize(target,'確認します','female')
            self.assertEqual(opener.open.call_count,1)
            self.assertEqual(json.loads((target/'submission.json').read_text())['status'],'rejected')

    def test_an_unknown_outcome_also_blocks_automatic_resubmission(self):
        opener=Mock();opener.open.side_effect=TimeoutError()
        with tempfile.TemporaryDirectory(dir=ROOT/'outputs',prefix='dialogue-safety-') as directory:
            target=Path(directory)/'turn'
            with patch.dict(os.environ,{'GEMINI_API_KEY':'fake-unit-test-key'}),patch('urllib.request.build_opener',return_value=opener):
                with self.assertRaisesRegex(RuntimeError,'unknown'):synthesize(target,'確認します','female')
                with self.assertRaisesRegex(RuntimeError,'incomplete'):synthesize(target,'確認します','female')
            self.assertEqual(opener.open.call_count,1)
            self.assertEqual(json.loads((target/'submission.json').read_text())['status'],'unknown')


if __name__=='__main__':unittest.main()
