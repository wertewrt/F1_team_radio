import unittest
import numpy as np
from PIL import ImageChops
from teamradio.renderer import CardRenderer, RenderConfig, number_mask
from teamradio.presets import DRIVERS, TEAMS, logo_path

class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=RenderConfig(width=320,height=180,entrance=.6,hold=.2,fade_out=.3)
        cls.r=CardRenderer(cls.config)
        cls.zeros=np.zeros(9,dtype=np.float32)

    def test_roster_and_albon_match_sainz_team(self):
        self.assertEqual(len(DRIVERS),23)
        self.assertEqual(DRIVERS['albon']['number'],'23')
        self.assertEqual(DRIVERS['albon']['team'],DRIVERS['sainz']['team'])
        for t in TEAMS:
            for variant in ('white','color'): self.assertTrue(logo_path(t,variant).is_file())

    def test_diagonal_entry_reveals_monotonically(self):
        alpha=[np.asarray(self.r.frame(t,.6,1,self.zeros))[:,:,3].sum() for t in (.01,.1,.3,.6)]
        self.assertTrue(all(a<b for a,b in zip(alpha,alpha[1:])))
        self.assertEqual(self.r.frame(-.1,.6,1,self.zeros).getbbox(),None)

    def test_fade_time_and_alpha(self):
        full=np.asarray(self.r.frame(1.8,.6,1,self.zeros))[:,:,3].astype(float)
        half=np.asarray(self.r.frame(1.95,.6,1,self.zeros))[:,:,3].astype(float)
        self.assertAlmostEqual(half.sum()/full.sum(),.5,delta=.01)
        self.assertIsNone(self.r.frame(2.1,.6,1,self.zeros).getbbox())

    def test_wave_changes_pixels_in_lower_band_only(self):
        a=self.r.frame(1,.6,1,self.zeros)
        b=self.r.frame(1,.6,1,np.ones(9,dtype=np.float32))
        diff=ImageChops.difference(a,b).convert('RGB').getbbox()
        self.assertIsNotNone(diff)
        self.assertGreater(diff[1],90)

    def test_one_accent_controls_name_number_and_wave(self):
        rgb=(22,190,91)
        r=CardRenderer(RenderConfig(width=960,height=540,color='#16BE5B'))
        fg=np.asarray(r._foreground); matches=np.all(fg[:,:,:3]==rgb,axis=2)&(fg[:,:,3]>240)
        self.assertGreater(matches[:200].sum(),1000)
        self.assertGreater(matches[200:,:450].sum(),1000)
        wave=np.asarray(r._wave(np.ones(9)))
        visible=wave[:,:,3]>170
        self.assertTrue(np.all(wave[:,:,:3][visible]==rgb))

    def test_white_hairline_and_shared_digits(self):
        r=CardRenderer(RenderConfig(width=960,height=540,color='#0055AA'))
        fg=np.asarray(r._foreground)[200:,:450]
        edge=(fg[:,:,0]>150)&(fg[:,:,1]>150)&(fg[:,:,2]>150)&(fg[:,:,3]>50)
        self.assertGreater(edge.sum(),100)
        # Every number uses the same source-extracted alphabet regardless of team.
        for text in ('0','23','55','77','0123456789'):
            mask=number_mask(text,140)
            self.assertIsNotNone(mask.getbbox())

    def test_name_logo_override_does_not_mutate_preset(self):
        before=DRIVERS['albon'].copy()
        c=RenderConfig(name='MY DRIVER',number='99',logo_path=str(logo_path('ferrari','white')),color='#123456',width=320,height=180)
        r=CardRenderer(c)
        self.assertEqual(r.team,'williams')
        self.assertEqual(r.name,'MY DRIVER')
        self.assertEqual(DRIVERS['albon'],before)

    def test_nine_contiguous_regions_extend_under_logo(self):
        r=CardRenderer(RenderConfig(width=658,height=352,card_scale=1))
        levels=np.linspace(.2,1,9,dtype=np.float32)
        alpha=np.asarray(r._wave(levels))[:,:,3]
        # Every x-column has nonzero audio at the baseline, including the last
        # region at the card's right edge underneath the team badge.
        self.assertTrue(np.all(alpha[-1,:]>0))
        boundaries=np.rint(np.linspace(0,r.w,10)).astype(int)
        heights=[]
        for left,right in zip(boundaries[:-1],boundaries[1:]):
            x=(left+right)//2
            rows=np.flatnonzero(alpha[:,x]>30)
            heights.append(r.h-rows[0])
        self.assertTrue(all(a<b for a,b in zip(heights,heights[1:])))
        for edge in boundaries[1:-1]:
            self.assertGreater(int(alpha[-2,edge-1]),0)
            self.assertGreater(int(alpha[-2,edge]),0)
        self.assertFalse(np.asarray(r._wave(np.zeros(9)))[:,:,3].any())

    def test_clean_vectors_render_at_high_resolution_without_bitmap_words(self):
        from pathlib import Path
        from unittest import mock
        from PIL import Image
        from teamradio.renderer import _vector_text, _numerals
        original=Image.open
        def guarded(path,*args,**kwargs):
            if 'lettering' in Path(str(path)).parts and str(path).endswith('.png'):
                raise AssertionError('Runtime must not enlarge screenshot lettering')
            return original(path,*args,**kwargs)
        with mock.patch('teamradio.renderer.Image.open',side_effect=guarded):
            high=_vector_text('ALBON',155*8,29*8)
            radio=_vector_text('RADIO',130*8,27*8,radio=True)
            CardRenderer(RenderConfig(width=640,height=360,name='ALBON'))
        self.assertEqual(high.size,(1240,232))
        self.assertEqual(radio.size,(1040,216))
        # Straight source-restored numeral segments are exact H/V/45 degrees,
        # with normalized coordinates that can be rendered at any resolution.
        for loops in _numerals().values():
            for path in loops:
                for p,q in zip(path,path[1:]+path[:1]):
                    dx,dy=abs(q[0]-p[0]),abs(q[1]-p[1])
                    self.assertTrue(min(dx,dy,abs(dx-dy))<2e-5)
        small=number_mask('63',88); large=number_mask('63',1056)
        self.assertGreater(large.width,small.width*11)
        self.assertEqual(large.height,1056+24)

    def test_source_typography_families_remain_distinct(self):
        import json
        from teamradio.presets import ASSETS
        data=json.loads((ASSETS/'lettering/lettering.json').read_text(encoding='utf-8'))
        self.assertEqual(data['names']['hadjar']['kind'],'source_word')
        self.assertEqual(data['names']['albon']['kind'],'composed_word')
        self.assertEqual(data['radio']['text'],'RADIO')
        from PIL import Image
        six=np.asarray(Image.open(ASSETS/'numerals/digit_6.png'))
        # The source 6 cap has a narrow upper stem; the lower bowl is wider.
        self.assertLess(np.count_nonzero(six[5]>128),six.shape[1]*.5)
        self.assertGreater(np.count_nonzero(six[int(six.shape[0]*.65)]>128),six.shape[1]*.55)
        for key in ('hadjar','sainz','bottas'):
            mask=Image.open(ASSETS/'lettering'/data['names'][key]['file'])
            self.assertEqual(mask.mode,'L')
            self.assertEqual(int(np.asarray(mask).min()),0)

    def test_portrait_and_input_validation(self):
        r=CardRenderer(RenderConfig(width=540,height=960))
        self.assertAlmostEqual(r.w/r.h,329/176,delta=.01)
        for kwargs in ({'width':321},{'fade_out':-.1},{'fps':0},{'gain':float('nan')},{'number':'A3'},{'color':'red'},{'card_scale':0}):
            with self.assertRaises(ValueError): RenderConfig(**kwargs).validate()

if __name__=='__main__': unittest.main()
