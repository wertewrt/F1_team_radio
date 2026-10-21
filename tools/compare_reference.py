"""Native-size source/render comparisons; wave heights matched only for comparison."""
from pathlib import Path
import sys,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from teamradio.renderer import CardRenderer,RenderConfig
from teamradio.presets import DRIVERS,TEAMS
DATA=json.loads((ROOT/'assets/lettering/lettering.json').read_text(encoding='utf-8'))
LEVELS={
 'hadjar':[.06,.08,.35,.48,.50,.07,.07,.08,.05],
 'sainz':[.06,.07,.19,.26,.19,.12,.09,.07,.05],
 'russell':[.05,.06,.10,.55,.95,.50,.47,.17,.05],
 'bottas':[.05,.09,.29,.75,.60,.44,.37,.32,.04],
 'piastri':[.05,.08,.12,.54,.99,.41,.13,.25,.05],
}
keys=['hadjar','sainz','russell','bottas','piastri']
SCALE=2; COL=329*SCALE; M=24
sheet=Image.new('RGB',(COL*2+M*3,(176*SCALE+68)*len(keys)+65),'#20232b')
draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype(str(ROOT/'assets/fonts/DejaVuSans-Bold.ttf'),19)
draw.text((M,18),'ORIGINAL RESOURCE (2x)',font=font,fill='white')
draw.text((COL+M*2,18),'CRISP VECTOR RECONSTRUCTION (2x)',font=font,fill='white')
records=[]
for i,key in enumerate(keys):
 entry=DATA['names'][key]
 original=Image.open(ROOT/entry['source_image']).convert('RGB').crop(entry['card_bbox'])
 cfg=RenderConfig(driver=key,width=658,height=352,card_scale=1)
 r=CardRenderer(cfg)
 levels=np.array(LEVELS[key],dtype=np.float32)
 generated=r.frame(2,cfg.entrance,4,levels).convert('RGB')
 y=65+i*(176*SCALE+68)
 draw.text((M,y),key.upper()+' / '+DRIVERS[key]['number'],font=font,fill='white')
 y+=30
 sheet.paste(original.resize((COL,176*SCALE),Image.Resampling.NEAREST),(M,y))
 sheet.paste(generated.resize((COL,176*SCALE),Image.Resampling.LANCZOS),(COL+M*2,y))
 records.append({'driver':key,'source':entry['source_image'],'source_card':entry['card_bbox'],'comparison_levels':LEVELS[key],'note':'Source-calibrated geometry, clean reconstructed vector glyphs; frozen nine wave levels are approximate screenshot measurements, not recovered original audio.'})
out=ROOT/'examples';out.mkdir(exist_ok=True)
sheet.save(out/'reference_comparison.png')
(out/'comparison_notes.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print('Wrote reference_comparison.png')
