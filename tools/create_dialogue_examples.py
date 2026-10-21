"""Generate reproducible portrait dialogue examples from the feature renderer."""
from pathlib import Path
import sys,json,wave,subprocess,os
from dataclasses import asdict
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT));os.chdir(ROOT)
from teamradio.renderer import RenderConfig,CardRenderer
from teamradio.media import AudioAnalyzer,export_video,ffmpeg_exe
OUT=ROOT/'examples'
short=[{'start':0.,'end':3.8,'speaker':'driver','text':'"CHECK THE CAR, I HAD WEIRD BEHAVIOUR LAST CORNER"'},
       {'start':4.,'end':7.5,'speaker':'other','text':'"OK, COPY. WE WILL HAVE A LOOK"'}]
hamilton=[{'start':0.,'end':7.5,'speaker':'other','text':'"CHARLES IS TRYING TO PICK UP THE PACE. HE IS NOW ON PLAN C, WE ARE ON B"'}]
long_text='"WE HAVE CHECKED THE CAR. THE TYRE PRESSURES ARE STABLE, THE TEMPERATURES ARE NORMAL AND THE BALANCE LOOKS GOOD. KEEP THE CURRENT SETTINGS FOR THE NEXT LAP, WATCH THE EXIT OF THE LAST CORNER, AND TELL US IF THE MOVEMENT HAPPENS AGAIN. WE WILL COMPARE YOUR DATA WITH THE PREVIOUS RUN BEFORE MAKING ANOTHER CHANGE."'
messages=short+[
 {'start':8.,'end':17.,'speaker':'other','text':long_text},
 {'start':17.5,'end':21.,'speaker':'driver','text':'"UNDERSTOOD. THE CAR FEELS BETTER NOW. I WILL KEEP PUSHING."'},
 {'start':21.5,'end':24.,'speaker':'other','text':'"COPY. BOX THIS LAP."'}]
# Join optional local TTS segments once; retain the joined WAV and its timing
# manifest so all later regenerations work without Windows speech synthesis.
voice=OUT/'dialogue_voice.wav'
timing=OUT/'dialogue_timing.json'
parts=[ROOT/'analysis'/f'dialogue_voice_{i}.wav' for i in range(len(messages))]
if all(path.is_file() for path in parts):
 joined=bytearray();cursor=0.;params=None;timed=[]
 for message,path in zip(messages,parts):
  with wave.open(str(path),'rb') as src:
   current=(src.getnchannels(),src.getsampwidth(),src.getframerate())
   if params is not None and current!=params: raise ValueError('Voice segment formats differ')
   params=current;data=src.readframes(src.getnframes());duration=src.getnframes()/src.getframerate()
  timed.append(dict(message,start=round(cursor,6),end=round(cursor+duration+.20,6)))
  joined.extend(data)
  pause=round(params[2]*.45)
  joined.extend(bytes(pause*params[0]*params[1]));cursor+=duration+pause/params[2]
 with wave.open(str(voice),'wb') as dst:
  dst.setnchannels(params[0]);dst.setsampwidth(params[1]);dst.setframerate(params[2]);dst.writeframes(joined)
 timing.write_text(json.dumps(timed,ensure_ascii=False,indent=2),encoding='utf-8')
if voice.is_file() and timing.is_file():
 messages=json.loads(timing.read_text(encoding='utf-8'));short=messages[:2]
else:
 voice=OUT/'demo_voice.wav'
configs={
 'dialogue_antonelli':RenderConfig(driver='antonelli',width=540,height=960,fps=20,dialogue_enabled=True,dialogue=short),
 'dialogue_hamilton':RenderConfig(driver='hamilton',width=540,height=960,fps=20,dialogue_enabled=True,dialogue=hamilton),
 'dialogue_scroll':RenderConfig(driver='antonelli',width=540,height=960,fps=20,dialogue_enabled=True,dialogue=messages),
}
for name,config in configs.items():
 data=asdict(config)
 if name!='dialogue_hamilton': data['_gui']={'format':'MP4','audio_path':voice.name}
 (OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'dialogue_messages.json').write_text(json.dumps(messages,ensure_ascii=False,indent=2),encoding='utf-8')
levels=np.array([.02,.07,.18,.5,.6,.35,.12,.04,.01],dtype=np.float32)
for name,time in [('dialogue_antonelli',short[1]['start']+.6),('dialogue_hamilton',4.)]:
 c=configs[name]; r=CardRenderer(c)
 r.frame(c.entrance+time,c.entrance,7.76,levels).save(OUT/(name+'.png'))
config=configs['dialogue_scroll']; r=CardRenderer(config)
long=messages[2]
times=[0.,.18,.5,short[1]['start']+.6,long['start']+.6,(long['start']+long['end'])/2,long['end']-.1,messages[3]['start']+.6,messages[4]['start']+.6]
sheet=Image.new('RGB',(1620,3000),'#242833');draw=ImageDraw.Draw(sheet)
font=ImageFont.truetype(str(ROOT/'assets/fonts/DejaVuSans.ttf'),22)
for i,t in enumerate(times):
 image=r.frame(config.entrance+t,config.entrance,messages[-1]['end'],levels)
 x=i%3*540;y=i//3*1000
 sheet.paste(image,(x,y),image)
 state=r.dialogue_panel.state_at(t)
 draw.text((x+15,y+962),f'{t:.2f}s / paragraph {(state["active_index"]+1 if state["active_index"] is not None else 0)}',font=font,fill='white')
sheet.save(OUT/'dialogue_stages.png')
# The demonstration uses an explicitly synthetic voice aligned to these quotes.
export_video(voice,OUT/'dialogue_demo.mp4',config)
result=subprocess.run([ffmpeg_exe(),'-hide_banner','-loglevel','error','-i',str(OUT/'dialogue_demo.mp4'),'-f','null','-'],capture_output=True,timeout=60)
if result.returncode: raise RuntimeError(result.stderr.decode('utf-8','replace'))
print('Dialogue samples created with synthetic demonstration voice:',voice.name)
print('Messages:',len(messages),'Last dialogue end:',messages[-1]['end'])
