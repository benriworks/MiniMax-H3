import unittest
from tools.studio.text_layout import fit_explicit_lines


class SemanticTextLayoutTests(unittest.TestCase):
    def test_display_word_stays_on_the_same_authored_line(self):
        text='実物のXLSX\n専用ビューアで表示\nExcel本体ではない'
        result=fit_explicit_lines(text,375,lambda line,size:sum(.5 if c.isascii() else 1 for c in line)*size)
        self.assertEqual(result['lines'],text.splitlines())
        self.assertEqual(result['font_size'],41)
        self.assertIn('で表示',result['lines'][1])

    def test_overflow_is_rejected_instead_of_shrinking_below_readability(self):
        with self.assertRaises(ValueError):fit_explicit_lines('長い説明'*20,375,lambda line,size:len(line)*size)

    def test_invalid_width_and_blank_text_are_rejected(self):
        for text,width in [('',375),('説明',0),('説明',float('inf'))]:
            with self.assertRaises(ValueError):fit_explicit_lines(text,width,lambda line,size:len(line)*size)
