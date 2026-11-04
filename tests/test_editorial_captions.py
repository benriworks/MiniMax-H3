import unittest
from tools.studio.editorial_captions import phrase_lines,caption_pages,display_text,timed_captions,speech_text
from tools.studio.editorial_presenters import face_geometry
from tools.studio.explainer_canvas import glyph

class EditorialCaptionTests(unittest.TestCase):
    def test_reported_word_and_number_regressions(self):
        value='瓶をまっすぐ起こしてから離す動きへ修正しました。'
        lines=phrase_lines(value,780,47)
        self.assertEqual(''.join(lines),value)
        self.assertTrue(any('離す動き' in s for s in lines))
        self.assertFalse(any(s.endswith('動') for s in lines))
        self.assertEqual(display_text('約一点九倍に直しました。'),'約1.9倍に直しました。')

    def test_product_and_decimal_boundaries_at_actual_width(self):
        value='ChatGPTとCodex、BlenderのPythonで約1.9倍に直しました。'
        pages=caption_pages(value,900,56)
        self.assertEqual(''.join(pages).replace('\n',''),value)
        lines='\n'.join(pages).splitlines()
        for word in ['ChatGPT','Codex','Blender','Python','約1.9倍']:
            self.assertTrue(any(word in s for s in lines),word)
        self.assertTrue(all(glyph(s,56,'white').width<=900 for s in lines))

    def test_rewording_required_instead_of_word_split(self):
        with self.assertRaisesRegex(ValueError,'Phrase exceeds'):
            phrase_lines('流体シミュレーション',120,60)

    def test_display_does_not_mutate_spoken_or_duration(self):
        spoken='ドッツにブレンダーを操作して作ってもらいました。'
        value=display_text(spoken);sub=timed_captions(value,1.2,6.7,900,56)
        self.assertIn('ドッツ',spoken);self.assertIn('dots',value)
        self.assertAlmostEqual(sub[0]['start'],1.2);self.assertAlmostEqual(sub[-1]['end'],7.9)
        for a,b in zip(sub,sub[1:]):self.assertAlmostEqual(a['end'],b['start'])

    def test_duo_face_anchors_match_instead_of_panel_size_only(self):
        a,b=[face_geometry(s,300) for s in ['male','female']]
        self.assertEqual(a['eyes'],b['eyes']);self.assertEqual(a['face_height'],b['face_height'])

    def test_reading_dictionary_and_explicit_override(self):
        self.assertEqual(speech_text('dotsがBlenderで約1.9倍へ。'),'ドッツがブレンダーで約一点九倍へ。')
        self.assertEqual(speech_text('Codex',explicit='指定した読み'),'指定した読み')

    def test_ascii_space_does_not_become_invisible_glyph_error(self):
        value='Blender Pythonの操作。'
        self.assertEqual(''.join(phrase_lines(value,1000,48)),value)

    def test_case_specific_model_names_stay_together_through_timing(self):
        value='今度はGPT-6.1 SolとGPT-6 Astraを比べます。'
        subs=timed_captions(value,2,7,610,48,protected=('GPT-6.1 Sol','GPT-6 Astra'))
        lines=[line for sub in subs for line in sub['text'].splitlines()]
        for name in ['GPT-6.1 Sol','GPT-6 Astra']:
            self.assertTrue(any(name in line for line in lines),name)
        self.assertEqual(''.join(lines),value)
        self.assertEqual(subs[0]['start'],2);self.assertEqual(subs[-1]['end'],9)
if __name__=='__main__':unittest.main()
