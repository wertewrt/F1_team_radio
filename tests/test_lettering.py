"""Asset checks for source identity, counters, AA, and isolated atlas glyphs."""
import json
from pathlib import Path
import string
import unittest

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from teamradio.presets import DRIVERS

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets' / 'lettering'


class LetteringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.metrics=json.loads((ASSETS/'lettering.json').read_text(encoding='utf-8'))

    def test_all_presets_have_native_words_with_honest_provenance(self):
        self.assertEqual(set(self.metrics['names']),set(DRIVERS))
        for key,entry in self.metrics['names'].items():
            with self.subTest(driver=key):
                with Image.open(ASSETS/entry['file']) as source:
                    mask=source.copy()
                self.assertEqual(mask.mode,'L')
                self.assertEqual(list(mask.size),entry['native_size'])
                if key=='albon':
                    self.assertEqual(entry['kind'],'composed_word')
                    self.assertIsNone(entry['source_image'])
                else:
                    self.assertEqual(entry['kind'],'source_word')
                    self.assertTrue((ROOT/entry['source_image']).is_file())
                    x,y,r,b=entry['source_bbox']
                    self.assertEqual(mask.size,(r-x,b-y))
                    self.assertGreaterEqual(entry['cap_height'],28)
                    self.assertLessEqual(entry['cap_height'],29)

    def test_masks_have_real_transparency_and_continuous_antialias(self):
        entries=list(self.metrics['names'].values())+[self.metrics['radio']]
        for entry in entries:
            with self.subTest(file=entry['file']):
                a=np.asarray(Image.open(ASSETS/entry['file']))
                self.assertEqual(int(a.min()),0)
                self.assertGreaterEqual(int(a.max()),250)
                self.assertEqual(int(a[0,0]),0)
                self.assertGreater(len(np.unique(a)),200)
                self.assertGreater(float((a==0).mean()),.05)
                self.assertGreater(float(((a>0)&(a<255)).mean()),.15)
        # A source O must contain a genuinely transparent counter.
        o=np.asarray(Image.open(ASSETS/'glyph_O.png'))
        self.assertLess(int(o[o.shape[0]//2,o.shape[1]//2]),8)

    def test_atlas_has_one_letter_body_and_documented_derivations(self):
        self.assertEqual(set(self.metrics['glyphs']),set(string.ascii_uppercase))
        for c,entry in self.metrics['glyphs'].items():
            with self.subTest(letter=c):
                a=np.asarray(Image.open(ASSETS/entry['file']))
                self.assertEqual(a.shape[0],35)
                _,_,stats,_=cv2.connectedComponentsWithStats((a>128).astype(np.uint8),8)
                bodies=[s for s in stats[1:] if s[cv2.CC_STAT_AREA]>5]
                self.assertEqual(len(bodies),1,'neighboring letter leaked into glyph')
                self.assertEqual(entry['core_bbox'][0],2)
                self.assertGreater(len(np.unique(a)),100)
                if c in 'FQX':
                    self.assertEqual(entry['kind'],'derived_glyph')
                else:
                    self.assertEqual(entry['kind'],'source_glyph')
                    self.assertIn('source_bbox',entry)

    def test_clean_fonts_preserve_counter_topology_and_curved_outlines(self):
        from fontTools.ttLib import TTFont
        for filename in ('RadioRounded-Bold.ttf','RadioRounded-Radio.ttf'):
            path=ROOT/'assets'/'fonts'/filename
            font=TTFont(path)
            self.assertEqual(font['head'].unitsPerEm,1000)
            self.assertEqual(font['OS/2'].sCapHeight,700)
            self.assertTrue(all(ord(c) in font.getBestCmap() for c in string.ascii_uppercase))
            self.assertNotIn('EBDT',font)
            self.assertNotIn('CBDT',font)
            self.assertNotIn('sbix',font)
            self.assertTrue(any(not flag&1 for flag in font['glyf']['O'].flags))
            font.close()
        path=ROOT/'assets'/'fonts'/'RadioRounded-Bold.ttf'
        font=ImageFont.truetype(str(path),400)
        for c,holes in [('A',1),('B',2),('O',1),('P',1),('R',1),('M',0)]:
            with self.subTest(letter=c):
                bb=font.getbbox(c)
                mask=Image.new('L',(bb[2]-bb[0]+12,bb[3]-bb[1]+12))
                ImageDraw.Draw(mask).text((6-bb[0],6-bb[1]),c,font=font,fill=255)
                contours,hierarchy=cv2.findContours((np.asarray(mask)>128).astype(np.uint8),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
                counters=sum(1 for i,contour in enumerate(contours) if hierarchy[0][i][3]!=-1 and cv2.contourArea(contour)>15)
                self.assertEqual(counters,holes,'a source counter collapsed or has incorrect winding')

    def test_radio_is_a_complete_original_word_with_measured_capheight(self):
        entry=self.metrics['radio']
        self.assertEqual(entry['text'],'RADIO')
        self.assertEqual(entry['native_size'],[134,32])
        self.assertEqual(entry['cap_height'],27)
        self.assertEqual(entry['mask_core_bbox'],[2,2,132,29])
        self.assertEqual(entry['kind'],'source_word')
        self.assertIn('175125',entry['source_image'])


if __name__=='__main__':
    unittest.main()
