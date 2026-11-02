"""Guard the real font layout and the broken product-name regression from news previews."""
import numpy as np
import unittest
from PIL import Image
from tools.studio.explainer_canvas import Canvas,wrap

class ExplainerCanvasTests(unittest.TestCase):
    def test_mixed_product_names_keep_whole_words(self):
        value='対象はPlus・Pro・Business。Instant chatは対象外。'
        lines=wrap(value,15)
        assert ''.join(lines)==value
        for product in ['Plus','Pro','Business','Instant','chat']:
            assert any(product in line for line in lines)

    def test_single_line_center_uses_actual_visible_ink(self):
        im=Image.new('RGB',(1100,260),'white');c=Canvas();c.text(im,'Plus・Pro・Business',(50,50,1050,210),65,'black')
        yy,xx=np.where(np.min(np.asarray(im),axis=2)<100)
        assert abs((xx.min()+xx.max())/2-550)<=3
        assert abs((yy.min()+yy.max())/2-130)<=3

    def test_overflow_requires_rewording_instead_of_shrinking(self):
        with self.assertRaisesRegex(ValueError,'overflow'):
            Canvas().text(Image.new('RGB',(150,100),'white'),'開始日・具体枠は未記載',(10,10,140,90),65)

if __name__=='__main__':unittest.main()
