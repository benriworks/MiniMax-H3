import unittest
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from tools.studio.text_layout import fit_explicit_lines, box_text_layout, visible_glyph_bbox


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

    def test_actual_japanese_and_latin_glyphs_are_centered_inside_button(self):
        face=Path(__file__).resolve().parents[1]/'studio/public/template-assets/NotoSansJP-Variable.ttf'
        for value,size in [('DAY 12',57),('前の作業',45),('再利用',45),('RESET',60)]:
            with self.subTest(value=value):
                im=Image.new('L',(400,160));d=ImageDraw.Draw(im);font=ImageFont.truetype(str(face),size)
                layout=box_text_layout(value,(20,20,380,140),lambda s:visible_glyph_bbox(s,font))
                for line in layout['placements']:d.text(line['origin'],line['text'],font=font,fill=255)
                left,top,right,bottom=im.getbbox()
                self.assertLessEqual(abs((left+right)/2-200),1)
                self.assertLessEqual(abs((top+bottom)/2-80),1)

    def test_multiline_label_is_top_aligned_and_stays_inside_box(self):
        face=Path(__file__).resolve().parents[1]/'studio/public/template-assets/NotoSansJP-Variable.ttf'
        im=Image.new('L',(400,200));d=ImageDraw.Draw(im);font=ImageFont.truetype(str(face),30)
        layout=box_text_layout('実物のXLSX\n専用ビューアで表示',(20,20,380,180),lambda s:visible_glyph_bbox(s,font),padding=12,line_gap=10)
        for line in layout['placements']:d.text(line['origin'],line['text'],font=font,fill=255)
        self.assertEqual(layout['vertical_alignment'],'top')
        left,top,right,bottom=im.getbbox()
        self.assertEqual(top,32)
        self.assertGreaterEqual(left,32);self.assertLessEqual(right,368);self.assertLessEqual(bottom,168)

    def test_button_text_overflow_requires_editorial_repair(self):
        with self.assertRaises(ValueError):
            box_text_layout('長いラベル',(0,0,30,20),lambda s:(0,10,200,60))
