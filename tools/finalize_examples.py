"""Regenerate every published example from the current vector renderer."""
from pathlib import Path
import sys,runpy,gc,json,subprocess
from dataclasses import asdict
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
import os
os.chdir(ROOT)
from teamradio.renderer import CardRenderer,RenderConfig
from teamradio.media import AudioAnalyzer,export_video,ffmpeg_exe
OUT=ROOT/'examples'
voice=OUT/'demo_voice.wav'
runpy.run_path(str(ROOT/'tools/generate_previews.py'),run_name='__main__')
runpy.run_path(str(ROOT/'tools/compare_reference.py'),run_name='__main__')
with AudioAnalyzer(voice) as audio:
    for driver,size,name,t in [
        ('albon',(1920,1080),'albon_preview.png',1.5),
        ('russell',(1920,1080),'russell_preview.png',1.5),
        ('hadjar',(1920,1080),'hadjar_preview.png',1.5),
        ('russell',(3840,2160),'russell_4k.png',1.5),
    ]:
        config=RenderConfig(driver=driver,width=size[0],height=size[1])
        card=CardRenderer(config)
        frame=card.frame(t,config.entrance,audio.duration,audio.levels_at(t-config.entrance))
        frame.save(OUT/name)
        print('PNG',name,frame.size)
        del frame,card
        gc.collect()
config=RenderConfig(driver='albon')
(OUT/'albon.json').write_text(json.dumps(asdict(config),indent=2,ensure_ascii=False),encoding='utf-8')
for suffix in ('mp4','webm'):
    target=OUT/('albon_demo.mp4' if suffix=='mp4' else 'albon_alpha.webm')
    export_video(voice,target,config)
    # Decode the complete file, including audio, to validate actual muxed output.
    result=subprocess.run([ffmpeg_exe(),'-hide_banner','-loglevel','error','-i',str(target),'-f','null','-'],capture_output=True,timeout=60)
    if result.returncode: raise RuntimeError(result.stderr.decode('utf-8','replace'))
    print('VIDEO',target.name,target.stat().st_size,'bytes; decoded completely')
# Give the revised motion clip a distinct name for review in media players.
import shutil
shutil.copyfile(OUT/'albon_demo.mp4',OUT/'centered_wave_demo.mp4')
print('All final examples generated from clean vector typography and a stationary central waveform.')
