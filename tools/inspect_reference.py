from pathlib import Path
import sys, os
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.chdir(ROOT)
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw
import cv2, json, imageio_ffmpeg
r=Path("resource"); out=Path("analysis"); out.mkdir(exist_ok=True)
files=sorted(r.glob("*.png")); sheet=Image.new("RGB",(1200, ((len(files)+3)//4)*210),(32,34,40)); d=ImageDraw.Draw(sheet)
for i,p in enumerate(files):
 im=Image.open(p); print(p.name, im.size); im.thumbnail((288,175)); x=(i%4)*300; y=(i//4)*210; sheet.paste(im,(x,y)); d.text((x,y+178),p.stem.replace("屏幕截图 2026-10-20 ",""),fill="white")
sheet.save(out/"reference_sheet.jpg")
p=next(r.glob("*.mp4")); cap=cv2.VideoCapture(str(p)); fps=cap.get(cv2.CAP_PROP_FPS); n=cap.get(cv2.CAP_PROP_FRAME_COUNT); print("VIDEO",fps,n,n/fps,cap.get(3),cap.get(4)); print("FFMPEG",imageio_ffmpeg.get_ffmpeg_exe())
times=[0,.1,.2,.3,.4,.5,.65,.8,1,1.3,1.6,2,2.5,3,4,5,6,7,8,9]
sheet=Image.new("RGB",(1600,((len(times)+3)//4)*255),(32,34,40)); d=ImageDraw.Draw(sheet)
for i,t in enumerate(times):
 cap.set(cv2.CAP_PROP_POS_MSEC,t*1000); ok,frame=cap.read()
 if not ok: continue
 im=Image.fromarray(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)); im.thumbnail((396,225)); x=i%4*400; y=i//4*255; sheet.paste(im,(x,y)); d.text((x,y+228),str(t)+" s",fill="white")
sheet.save(out/"video_sheet.jpg"); cap.release()