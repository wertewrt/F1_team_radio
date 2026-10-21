"""python -m teamradio: graphical studio or unattended command-line export."""
from __future__ import annotations
import argparse
from dataclasses import asdict, fields
import json
from pathlib import Path
import sys
import threading
from .presets import DRIVERS, TEAMS
from .renderer import RenderConfig, CardRenderer


def main(argv=None):
    parser=argparse.ArgumentParser(description='F1 TEAM RADIO Studio · 语音驱动广播卡片')
    sub=parser.add_subparsers(dest='command')
    sub.add_parser('gui',help='打开中文桌面界面（默认）')
    sub.add_parser('presets',help='列出车手和车队预设')
    doctor=sub.add_parser('doctor',help='检查 Python、字体、FFmpeg 和编码器')
    for cmd in ('render','preview'):
        p=sub.add_parser(cmd,help='导出带语音的视频' if cmd=='render' else '导出一张 PNG 预览')
        p.add_argument('--config',type=Path,help='读取 JSON 配置，显式参数覆盖配置')
        p.add_argument('--audio',type=Path,required=cmd=='render',help='语音文件，支持中文路径')
        p.add_argument('--output','-o',type=Path,required=True)
        p.add_argument('--driver',choices=DRIVERS)
        p.add_argument('--name'); p.add_argument('--number'); p.add_argument('--team',choices=TEAMS)
        p.add_argument('--color',help='统一姓名、号码和波形颜色，如 #246DCB')
        p.add_argument('--logo',dest='logo_path',type=str); p.add_argument('--logo-variant',choices=['white','color'])
        p.add_argument('--size',help='画面大小，如 1920x1080')
        p.add_argument('--fps',type=int)
        for key in ('entrance','fade-out','hold','start-delay','card-scale','gain'):
            p.add_argument('--'+key,type=float)
        p.add_argument('--background',choices=['transparent','color'])
        p.add_argument('--background-color')
        p.add_argument('--position',choices=['center','top-left','top-right','bottom-left','bottom-right','custom'])
        p.add_argument('--custom-x',type=int); p.add_argument('--custom-y',type=int)
        dialogue_mode=p.add_mutually_exclusive_group()
        dialogue_mode.add_argument('--dialogue',dest='dialogue_file',type=Path,help='导入带 start/end/speaker/text 的留言 JSON 并启用下方文字框')
        dialogue_mode.add_argument('--no-dialogue',dest='dialogue_enabled',action='store_false',default=None,help='仅显示原来的上方卡片')
        p.add_argument('--dialogue-expand',type=float,help='文字框向下展开时间（秒）')
        p.add_argument('--dialogue-scroll',type=float,help='新段落滚至顶部的时间（秒）')
        p.add_argument('--dialogue-font-size',type=int,help='原始卡片坐标中的文字字号，14–40')
        p.add_argument('--save-config',type=Path,help='保存最终采用的配置')
        p.add_argument('--overwrite',action='store_true',help='允许替换已有导出文件')
        if cmd=='preview': p.add_argument('--time',type=float,default=1.4,help='预览时间（秒）')
    args=parser.parse_args(argv)
    if args.command in (None,'gui'):
        from .gui import main as gui_main
        gui_main(); return 0
    if args.command=='presets':
        for key,p in DRIVERS.items(): print(f"{key:13} {p['number']:>2}  {p['name']:12} {p['team']}")
        print('\nTeam colors:')
        for key,p in TEAMS.items(): print(f"{key:14} {p['color']}  logo={p['logo_variant']}")
        return 0
    if args.command=='doctor':
        import subprocess
        import numpy, PIL
        from .media import ffmpeg_exe
        from .presets import ASSETS, logo_path
        print('Python:',sys.version.split()[0]); print('NumPy:',numpy.__version__); print('Pillow:',PIL.__version__)
        print('FFmpeg:',ffmpeg_exe())
        result=subprocess.run([ffmpeg_exe(),'-hide_banner','-encoders'],capture_output=True,text=True,check=True)
        expected=['libx264','prores_ks','libvpx-vp9','mpeg4','gif','pcm_s16le','aac','libopus']
        missing=[v for v in expected if v not in result.stdout]
        for t in TEAMS:
            for variant in ('color','white'):
                if not logo_path(t,variant).is_file(): missing.append(str(logo_path(t,variant)))
        for fn in ('RadioRounded-Bold.ttf','RadioRounded-Radio.ttf','DejaVuSans-Bold.ttf','DejaVuSans.ttf'):
            if not (ASSETS/'fonts'/fn).is_file(): missing.append(fn)
        if missing: raise RuntimeError('缺少必需资源或编码器：'+', '.join(missing))
        print('OK · 23 个车手预设 / 11 队彩色与白色徽标 / 7 种导出格式')
        return 0
    data={}
    if args.config:
        data=json.loads(args.config.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict): raise ValueError('JSON 配置顶层须为对象')
        data.pop('_gui',None)  # Desktop saves optional UI state beside render fields.
        unknown=set(data)-{f.name for f in fields(RenderConfig)}
        if unknown: raise ValueError('配置中包含未知选项：'+', '.join(sorted(unknown)))
        if data.get('logo_path') and not Path(data['logo_path']).is_absolute():
            data['logo_path']=str((args.config.parent/data['logo_path']).resolve())
    for field in fields(RenderConfig):
        value=getattr(args,field.name,None)
        if value is not None: data[field.name]=value
    if args.dialogue_file:
        transcript=json.loads(args.dialogue_file.read_text(encoding='utf-8-sig'))
        data['dialogue']=transcript.get('dialogue') if isinstance(transcript,dict) else transcript
        data['dialogue_enabled']=True
    if args.size:
        try: data['width'],data['height']=map(int,args.size.lower().split('x'))
        except ValueError: raise ValueError('--size 格式须为 宽x高，如 1920x1080')
    config=RenderConfig(**data).validate()
    protected=[Path(__file__).resolve().parent.parent/'resource',Path(__file__).resolve().parent.parent/'assets',Path(__file__).resolve().parent]
    target=args.output.resolve()
    if any(target.is_relative_to(p.resolve()) for p in protected): raise ValueError('请导出到其他文件夹，不能覆盖素材或程序')
    if args.audio and target==args.audio.resolve(): raise ValueError('输出不能覆盖输入语音')
    if args.dialogue_file and target==args.dialogue_file.resolve(): raise ValueError('输出不能覆盖留言 JSON')
    if config.logo_path and target==Path(config.logo_path).resolve(): raise ValueError('输出不能覆盖自定义队标')
    if target.exists() and not args.overwrite: raise FileExistsError('输出已存在；请换文件名，或使用 --overwrite')
    if args.save_config:
        cfg_target=args.save_config.resolve()
        if cfg_target==target or (args.audio and cfg_target==args.audio.resolve()) or (args.dialogue_file and cfg_target==args.dialogue_file.resolve()) or (config.logo_path and cfg_target==Path(config.logo_path).resolve()):
            raise ValueError('配置路径不能与输入或输出文件相同')
        if any(cfg_target.is_relative_to(p.resolve()) for p in protected): raise ValueError('请将配置保存到工作区其他位置')
        if cfg_target.exists() and not args.overwrite: raise FileExistsError('配置已存在；使用 --overwrite 允许替换')
        cfg_target.parent.mkdir(parents=True,exist_ok=True)
        cfg_target.write_text(json.dumps(asdict(config),ensure_ascii=False,indent=2),encoding='utf-8')
    if args.command=='render':
        from .media import export_video
        if config.background=='transparent' and target.suffix.lower() in ('.mp4','.mkv','.avi'):
            print('提示：此格式不保留透明通道，将使用背景色铺底。')
        if target.suffix.lower()=='.gif': print('提示：GIF 不包含声音，颜色最多 256 种。')
        last=[-1]
        def progress(frac,message):
            percent=int(frac*100)
            if percent!=last[0]: print(f'\r{percent:3d}% {message:45}',end='',flush=True); last[0]=percent
        cancel=threading.Event()
        try: path=export_video(args.audio,target,config,progress=progress,cancel=cancel)
        except KeyboardInterrupt:
            cancel.set(); print('\n已取消，已有输出未被替换。'); return 130
        print('\n完成：',path); return 0
    if target.suffix.lower()!='.png': raise ValueError('预览输出须使用 .png 后缀')
    import numpy as np
    audio_start=config.start_delay+config.entrance
    if args.audio:
        from .media import AudioAnalyzer
        with AudioAnalyzer(args.audio,config.fps,config.gain) as analyzer:
            image=CardRenderer(config).frame(args.time,audio_start,analyzer.duration,analyzer.levels_at(args.time-audio_start))
    else:
        levels=np.array([.03,.09,.28,.75,.84,.51,.18,.07,.02],dtype=np.float32)
        image=CardRenderer(config).frame(args.time,audio_start,4,levels)
    target.parent.mkdir(parents=True,exist_ok=True); image.save(target)
    print('预览：',target); return 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as exc: print('错误：'+str(exc),file=sys.stderr); sys.exit(1)
