"""New dialogue composition must preserve the existing upper-card animation."""
import unittest,json,tempfile,wave,zipfile
from pathlib import Path
import numpy as np
from PIL import Image
from teamradio.renderer import CardRenderer,RenderConfig
from teamradio.media import export_video

class DialogueIntegrationTests(unittest.TestCase):
    def test_upper_animation_is_pixel_identical_at_equal_card_size(self):
        messages=[{'start':0.,'end':4.,'speaker':'driver','text':'"CHECK THE CAR"'}]
        classic=CardRenderer(RenderConfig(width=658,height=352,card_scale=1))
        new=CardRenderer(RenderConfig(width=658,height=904,card_scale=1,dialogue_enabled=True,dialogue=messages))
        self.assertEqual((classic.w,classic.h),(new.w,new.h))
        self.assertEqual((classic.x,classic.y),(new.x,new.y))
        levels=np.array([.02,.07,.2,.5,.7,.4,.1,.03,.01])
        for t in (.1,.3,.7,.95,1.4,2.2):
            with self.subTest(t=t):
                old=classic.frame(t,.95,5.,levels)
                top=new.frame(t,.95,5.,levels).crop((0,0,658,352))
                np.testing.assert_array_equal(np.asarray(old),np.asarray(top))

    def test_dialogue_end_extends_video_but_keeps_original_audio_duration(self):
        config=RenderConfig(width=164,height=226,fps=10,card_scale=1,entrance=.1,hold=.1,fade_out=.2,
          dialogue_enabled=True,dialogue=[{'start':.2,'end':1.2,'speaker':'other','text':'"COPY. WE WILL CHECK."'}])
        self.assertEqual(config.content_duration(.4),1.2)
        classic=RenderConfig(dialogue=config.dialogue)
        self.assertEqual(classic.content_duration(.4),.4)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'voice.wav'
            with wave.open(str(source),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(16000)
                stream.writeframes(np.zeros(6400,dtype='<i2').tobytes())
            output=root/'text.zip'
            export_video(source,output,config)
            with zipfile.ZipFile(output) as archive:
                meta=json.loads(archive.read('metadata.json'))
                self.assertAlmostEqual(meta['audio_duration'],.4)
                self.assertAlmostEqual(meta['duration'],1.6)
                self.assertEqual(meta['frame_count'],16)
                self.assertTrue(meta['dialogue_enabled'])
                self.assertEqual(meta['dialogue'][0]['speaker'],'other')
                import io
                late=Image.open(io.BytesIO(archive.read('frames/00000011.png'))).convert('RGBA')
                self.assertTrue(np.asarray(late)[110:,:,3].any())

    def test_dialogue_configuration_validation(self):
        for kwargs in ({'dialogue_enabled':'yes'},{'dialogue_font_size':0},{'dialogue_expand':-1},
                       {'dialogue_scroll':float('nan')},{'dialogue':[{'start':0,'end':1,'speaker':'driver','text':'No quotes'}]}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError): RenderConfig(**kwargs).validate()

if __name__=='__main__':unittest.main()
