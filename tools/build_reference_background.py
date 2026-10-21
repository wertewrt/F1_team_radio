"""Recover visible background pixels from aligned user reference cards.
Foreground is masked before robust stacking; always-hidden pixels are inpainted.
No game footage or driver lettering is baked into the resulting background.
"""
from pathlib import Path
import json
import cv2
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parent.parent
# Interior panel boxes, excluding the filmed game around each UI card.
BOXES={
 '174745':(14,15,343,190),'174758':(13,15,342,190),
 '174845':(20,18,350,195),'174857':(10,15,336,190),
 '175106':(19,9,348,185),'175125':(14,14,342,190),
 '175138':(10,12,338,187),'175209':(10,10,339,185),
 '175229':(17,13,345,188),'175245':(22,16,351,192),
 '175453':(24,11,353,185),'175513':(10,15,339,191),
 '175609':(17,19,345,194),'175712':(11,9,340,185),
 '175903':(16,16,345,191),'180012':(11,13,339,189),
 '180209':(10,15,338,190),'180333':(11,10,340,186),
 '180805':(11,10,340,186),'180835':(10,12,339,187),
 '181452':(15,17,344,192),'181507':(5,7,334,181),
}
W,H=960,512
stack=[]
for stamp,box in BOXES.items():
 p=next((ROOT/'resource').glob('*'+stamp+'.png'))
 a=np.array(Image.open(p).convert('RGB').crop(box).resize((W,H),Image.Resampling.BICUBIC)).astype(np.float32)
 # remove bright lettering/numbers/logos and accent-coloured wave.
 hi=a.max(2); low=a.min(2)
 invalid=(hi>70)|((hi-low>22)&(hi>35))
 invalid[round(H*.78):,:]=True
 invalid=cv2.dilate(invalid.astype('uint8'),np.ones((7,7),np.uint8))>0
 a[invalid]=np.nan
 stack.append(a)
with np.errstate(all='ignore'):
 import warnings
 with warnings.catch_warnings():
  warnings.simplefilter('ignore',RuntimeWarning)
  bg=np.nanmedian(np.stack(stack),axis=0)
missing=~np.isfinite(bg).all(2)
bg=np.nan_to_num(bg,nan=18).astype('uint8')
# Fill masked bottom with the recoverable central card design before inpainting.
bg=cv2.inpaint(bg,(missing.astype('uint8')*255),18,cv2.INPAINT_TELEA)
# Use a single well-exposed source for the final texture. Complete foreground
# rectangles include soft colour/shadow fringes, which must not ghost into art.
p=next((ROOT/'resource').glob('*174758.png'))
raw=np.array(Image.open(p).convert('RGB').crop((13,15,342,191)))
mask=np.zeros(raw.shape[:2],np.uint8)
for x0,y0,x1,y1 in [(130,7,322,42),(181,42,322,77),(8,73,80,169),(239,132,323,173),(0,139,329,176)]:
    mask[y0:y1,x0:x1]=255
mask=cv2.dilate(mask,np.ones((5,5),np.uint8))
clean=cv2.inpaint(raw,mask,18,cv2.INPAINT_NS)
bg=np.array(Image.fromarray(clean).resize((W,H),Image.Resampling.BICUBIC))
# Reinstate diagonal bands only where the source is actually visible; softly
# extrapolate the pattern through permanently hidden lettering/logo areas.
visible=(mask==0).astype(np.uint8)*255
valid=np.array(Image.fromarray(visible).resize((W,H),Image.Resampling.BILINEAR).filter(__import__('PIL.ImageFilter',fromlist=['GaussianBlur']).GaussianBlur(10))).astype(float)/255
yy,xx=np.mgrid[:H,:W].astype(float)
u=(xx+yy)/(W+H)
pattern=np.exp(-((u-.38)/.06)**2)*2.5+np.exp(-((u-.59)/.018)**2)*4+np.exp(-((u-.64)/.025)**2)*3
continuation=np.zeros_like(bg,dtype=float)
for k,b in enumerate((19,19,29)): continuation[:,:,k]=b+pattern
bg=np.clip(bg*valid[:,:,None]+continuation*(1-valid[:,:,None]),0,255).astype('uint8')
# The transparent video canvas is separate; the card panel itself is opaque.
out=ROOT/'assets'/'background'; out.mkdir(exist_ok=True)
Image.fromarray(bg).save(out/'reference_panel.png')
(out/'recovery.json').write_text(json.dumps({'size':[W,H],'boxes':BOXES,'method':'aligned visible dark pixels, median, inpaint always-hidden regions','hidden_pixel_fraction':float(missing.mean())},indent=2),encoding='utf-8')
print('background recovered; inpainted fraction',missing.mean())
