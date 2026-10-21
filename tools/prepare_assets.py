"""One-off asset preparation. Original resource files are never modified."""
from pathlib import Path
from PIL import Image, ImageChops
import numpy as np

ROOT=Path(__file__).resolve().parent.parent
out=ROOT/'assets'/'logos'; out.mkdir(parents=True,exist_ok=True)
im=Image.open(ROOT/'resource'/'team_catalog.png').convert('RGB')
bg=np.array(im.getpixel((1199,839)),dtype=float)
print('catalog background:', bg)
rows=[['mercedes','ferrari','mclaren'],['red_bull','racing_bulls','alpine'],['haas','audi','williams'],['aston_martin','cadillac']]
for row,teams in enumerate(rows):
 for col,team in enumerate(teams):
  for variant,dx in [('color',0),('white',190)]:
   box=(col*400+20+dx,row*210+48,col*400+183+dx,row*210+190)
   a=np.asarray(im.crop(box)).astype(float)
   dist=np.max(np.abs(a-bg),axis=2)
   alpha=np.clip((dist-2)/12,0,1)
   # Unmatte antialiased edges from the catalog background.
   rgb=np.clip((a-bg[None,None,:]*(1-alpha[:,:,None]))/np.maximum(alpha[:,:,None],.001),0,255)
   rgba=np.dstack([rgb,alpha*255]).astype('uint8')
   logo=Image.fromarray(rgba); bbox=logo.getbbox()
   if bbox: logo=logo.crop(bbox)
   logo.save(out/f'{team}_{variant}.png')
