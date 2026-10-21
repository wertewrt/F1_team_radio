"""Build the application icon from original geometric lettering (Pillow only)."""
from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).resolve().parents[1]
image=Image.new('RGBA',(256,256),(0,0,0,0))
draw=ImageDraw.Draw(image)
draw.rounded_rectangle((4,4,252,252),radius=44,fill='#10131d')
draw.rounded_rectangle((20,20,236,236),radius=31,outline='#246dcb',width=8)
for x,h in zip(range(43,223,21),(32,52,88,125,154,116,77,46,25)):
    draw.rounded_rectangle((x,128-h/2,x+14,128+h/2),radius=5,fill='#57ddbe')
path=root/'packaging'/'app.ico';path.parent.mkdir(exist_ok=True)
image.save(path,sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print(path)
