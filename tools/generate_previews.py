from pathlib import Path
import sys, os
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from teamradio.renderer import RenderConfig, CardRenderer
from teamradio.presets import DRIVERS
out=Path('examples'); out.mkdir(exist_ok=True)
levels=np.array([.03,.09,.28,.75,.84,.51,.18,.07,.02],dtype='float32')
entrance=RenderConfig().entrance
r=CardRenderer(RenderConfig())
r.frame(1.7,entrance,3,levels).save(out/'albon_preview.png')
r=CardRenderer(RenderConfig(driver='sainz'))
r.frame(1.7,entrance,3,levels).save(out/'sainz_preview.png')
sheet=Image.new('RGB',(1600,((len(DRIVERS)+3)//4)*250),(31,34,43)); d=ImageDraw.Draw(sheet)
for i,key in enumerate(DRIVERS):
 r=CardRenderer(RenderConfig(driver=key,width=384,height=216))
 im=r.frame(1.7,entrance,3,levels)
 px=i%4*400+8; py=i//4*250
 sheet.paste(im,(px,py),im); d.text((px+10,py+220),key,fill='white')
sheet.save(out/'all_presets.jpg')
r=CardRenderer(RenderConfig(width=480,height=270))
sheet=Image.new('RGB',(1440,600),(44,47,55)); d=ImageDraw.Draw(sheet)
for i,t in enumerate([0,.15,.35,.60,.95,4.33]):
 im=r.frame(t,entrance,3,levels); px=i%3*480; py=i//3*300
 sheet.paste(im,(px,py),im); d.text((px+12,py+275),f'{t:.2f} s',fill='white')
sheet.save(out/'animation_stages.jpg')