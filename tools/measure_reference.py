"""Reference-only pixel measurements; does not import or modify renderer."""
from pathlib import Path
import cv2, numpy as np, json
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'analysis'
OUT.mkdir(exist_ok=True)
refs={'SAINZ':'175106','HADJAR':'174758','BEARMAN':'174857','BOTTAS':'180835'}
for name,stamp in refs.items():
 p=ROOT/'resource'/f'屏幕截图 2026-10-20 {stamp}.png'
 a=np.array(Image.open(p).convert('RGB'))
 print(name,a.shape)
 for y in [9,12,15,20,50,100,180,185,189,191]:
  if y<a.shape[0]:
   q=np.mean(abs(np.diff(a[y].astype(float),axis=0)),axis=1)
   ids=np.argsort(q)[-8:]
   print('row',y,sorted([(int(i),round(float(q[i]),1)) for i in ids]))
 im=Image.fromarray(a).resize((a.shape[1]*4,a.shape[0]*4),Image.Resampling.NEAREST)
 d=ImageDraw.Draw(im)
 for x in range(0,a.shape[1],10):
  d.line((x*4,0,x*4,a.shape[0]*4),fill=(80,65,65),width=1);d.text((x*4+1,0),str(x),fill='yellow')
 for y in range(0,a.shape[0],10):
  d.line((0,y*4,a.shape[1]*4,y*4),fill=(80,65,65),width=1);d.text((0,y*4+1),str(y),fill='yellow')
 im.save(OUT/f'geometry_grid_{name.lower()}.png')
cap=cv2.VideoCapture(str(next((ROOT/'resource').glob('*.mp4'))))
fps=cap.get(cv2.CAP_PROP_FPS);n=cap.get(cv2.CAP_PROP_FRAME_COUNT)
print('video',fps,n,n/fps,cap.get(3),cap.get(4))
times=[0,.5,.9,1,1.1,1.2,1.3,1.4,1.5,1.6,1.7,1.8,1.9,2,2.2,2.5,3,4,5,6]
ims=[]
for t in times:
 cap.set(cv2.CAP_PROP_POS_MSEC,t*1000);ok,a=cap.read()
 if not ok:continue
 im=Image.fromarray(cv2.cvtColor(a,cv2.COLOR_BGR2RGB)); im.thumbnail((640,360))
 ims.append((t,im))
sheet=Image.new('RGB',(640*4,390*((len(ims)+3)//4)),(45,45,45));d=ImageDraw.Draw(sheet)
for i,(t,im) in enumerate(ims):
 x=i%4*640;y=i//4*390;sheet.paste(im,(x,y));d.text((x,y+362),str(t),fill='white')
sheet.save(OUT/'geometry_video_overview.png')
cap.release()
cap=cv2.VideoCapture(str(next((ROOT/'resource').glob('*.mp4'))))
for fi in [29,30,31,32,33,34,35,36,39,42,45,46,47,48,49,50,51,52,53,54,55,57,60,66]:
 cap.set(cv2.CAP_PROP_POS_FRAMES,fi);ok,a=cap.read()
 if ok:Image.fromarray(cv2.cvtColor(a,cv2.COLOR_BGR2RGB)).save(OUT/f'geometry_frame_{fi:03d}.png')
cap.release()
crops={'SAINZ':(19,9,348,185),'HADJAR':(13,15,342,191),'BEARMAN':(10,15,339,191),'BOTTAS':(10,12,339,188)}
rois={'SAINZ':[(190,15,342,52),(195,50,342,84),(25,80,170,177),(275,137,340,177)],'HADJAR':[(140,23,335,58),(190,55,335,89),(20,87,92,183),(250,146,334,183)],'BEARMAN':[(85,23,332,59),(190,56,333,90),(17,87,160,182),(265,124,334,183)],'BOTTAS':[(140,20,332,55),(188,52,332,88),(17,84,160,180),(258,145,331,181)]}
for name,stamp in refs.items():
 a=np.array(Image.open(ROOT/'resource'/f'屏幕截图 2026-10-20 {stamp}.png').convert('RGB'))
 print('RAW_THRESHOLD_COMPONENTS_NOT_FINAL',name,'Numeral threshold may include wave; use manually isolated report boxes.')
 for kind,roi in zip(['name','radio','number','logo'],rois[name]):
  l,t,r,b=roi;q=a[t:b,l:r].astype(float)
  if name in ['SAINZ','HADJAR'] and kind in ['name','number']:m=(q[:,:,2]-q[:,:,0]>35)&(q[:,:,2]>90)
  elif name=='HADJAR' and kind=='logo':m=(q.max(2)>110)&(q.max(2)-q.min(2)>45)
  elif name=='BEARMAN' and kind=='logo':m=(q[:,:,0]>90)&(q[:,:,0]-q[:,:,1]>50)
  else:m=q.mean(2)>(85 if name=='BOTTAS' and kind in ['name','number'] else 130)
  yy,xx=np.where(m)
  print(kind,[int(xx.min()+l),int(yy.min()+t),int(xx.max()+l+1),int(yy.max()+t+1)])
 print('RGB local',[(p,a[p[1]+crops[name][1],p[0]+crops[name][0]].tolist()) for p in [(20,20),(100,40),(110,70),(110,100),(180,90),(230,110),(250,120),(220,140)]])
report=json.loads((OUT/'reference_geometry.json').read_text(encoding='utf8'))
for name,v in report['representatives'].items():
 im=Image.open(ROOT/'resource'/f"屏幕截图 2026-10-20 {v['stamp']}.png").convert('RGB').resize((1464,808),Image.Resampling.NEAREST)
 sx=1464/Image.open(ROOT/'resource'/f"屏幕截图 2026-10-20 {v['stamp']}.png").width
 sy=808/Image.open(ROOT/'resource'/f"屏幕截图 2026-10-20 {v['stamp']}.png").height
 d=ImageDraw.Draw(im)
 colors={'name':'yellow','radio':'cyan','numeral':'lime','logo':'magenta'}
 c=v['crop_source_xyxy']
 d.rectangle((c[0]*sx,c[1]*sy,c[2]*sx,c[3]*sy),outline='white',width=2)
 for k,box in v['boxes'].items():
  l,t,r,b=box['source_xyxy'];d.rectangle((l*sx,t*sy,r*sx,b*sy),outline=colors[k],width=2)
  d.text((l*sx,t*sy-12),k+' '+','.join(map(str,[l,t,r,b])),fill=colors[k])
 for i,x in enumerate(v['wave']['boundaries_x_source']):
  d.line((x*sx,(c[3]-20)*sy,x*sx,c[3]*sy),fill='orange',width=2)
  if i<9:d.text((x*sx+2,(c[3]-7)*sy),str(i+1),fill='white')
 im.save(OUT/f'geometry_boxes_{name.lower()}.png')
