"""Compare real speech frames with a stationary central nine-block cluster."""
from pathlib import Path
import sys
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from teamradio.renderer import RenderConfig,CardRenderer
from teamradio.media import AudioAnalyzer
cfg=RenderConfig(width=480,height=270)
r=CardRenderer(cfg)
times=[.20,.35,.55,.75,1.0,1.3,1.7,2.1,2.5]
sheet=Image.new('RGB',(1440,945),'#232730')
d=ImageDraw.Draw(sheet)
f=ImageFont.truetype(str(ROOT/'assets/fonts/DejaVuSans-Bold.ttf'),17)
with AudioAnalyzer(ROOT/'examples/demo_voice.wav') as a:
    for i,t in enumerate(times):
        levels=a.levels_at(t)
        frame=r.frame(t+cfg.entrance,cfg.entrance,a.duration,levels)
        x=i%3*480;y=i//3*315
        sheet.paste(frame,(x,y),frame)
        state=f'peak block {int(np.argmax(levels))+1}' if float(levels.max())>.001 else 'silence'
        d.text((x+14,y+278),f'Audio {t:.2f}s / {state}',font=f,fill='white')
        print(f'{t:.2f}s',np.round(levels,3).tolist())
sheet.save(ROOT/'examples/wave_motion_check.png')
