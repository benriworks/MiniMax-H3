import unittest
import numpy as np
from tools.studio.closing_visuals import celebration_layer,end_screen,END_SCREEN_LAYOUT

class ClosingVisualTests(unittest.TestCase):
    def test_celebration_moves_and_excludes_face_centers_and_caption_area(self):
        args=dict(faces=[(665,282,985,565),(1000,365,1320,675)])
        first=np.asarray(celebration_layer(2.0,**args));later=np.asarray(celebration_layer(2.8,**args))
        self.assertFalse(np.array_equal(first,later))
        self.assertTrue(np.array_equal(first,np.asarray(celebration_layer(2.0,**args))))
        self.assertGreater(int(first[:,:,3].sum()),10000)
        self.assertEqual(int(first[:270,:,3].max()),0)
        self.assertEqual(int(first[850:,:,3].max()),0)
        self.assertLessEqual(int(first[400:445,790:850,3].max()),1)
        self.assertLessEqual(int(first[495:545,1135:1185,3].max()),1)

    def test_end_screen_holds_clear_nonoverlapping_video_and_subscription_regions(self):
        def no_text(*args,**kwargs):pass
        a=np.asarray(end_screen(0,label=no_text));b=np.asarray(end_screen(9.8,label=no_text))
        cx,cy=END_SCREEN_LAYOUT['subscribe']['center'];radius=END_SCREEN_LAYOUT['subscribe']['radius']
        for v in END_SCREEN_LAYOUT['videos']:
            x,y,x2,y2=v['rect']
            self.assertEqual((x2-x)*9,(y2-y)*16)
            self.assertTrue(0<x<x2<1920 and 0<y<y2<1080)
            self.assertTrue(x2<cx-radius or x>cx+radius)
            self.assertTrue(np.array_equal(a[y:y2,x:x2],b[y:y2,x:x2]))
        self.assertTrue(np.array_equal(a[cy-40:cy+40,cx-40:cx+40],b[cy-40:cy+40,cx-40:cx+40]))
        self.assertEqual(END_SCREEN_LAYOUT['seconds'],10.0)
        self.assertTrue(END_SCREEN_LAYOUT['requires_youtube_studio_elements'])

if __name__=='__main__':unittest.main()
