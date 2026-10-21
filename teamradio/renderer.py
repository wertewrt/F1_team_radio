"""Deterministic Pillow renderer. Source-measured typography and nine contiguous audio blocks.

All geometry uses a 329 x 176 source-card coordinate system. The diagonal reveal is
inspired by the supplied recording; source footage is never baked into output.
"""
from dataclasses import dataclass, field
from pathlib import Path
import math
import numbers
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageColor
from .presets import DRIVERS, TEAMS, ASSETS, logo_path

@dataclass
class RenderConfig:
    driver: str = 'albon'
    name: str | None = None
    number: str | None = None
    team: str | None = None
    color: str | None = None
    logo_path: str | None = None
    logo_variant: str | None = None
    width: int = 960
    height: int = 540
    fps: int = 30
    entrance: float = .95
    fade_out: float = .3
    hold: float = .25
    start_delay: float = 0
    background: str = 'transparent'
    background_color: str = '#10121a'
    card_scale: float = .90
    position: str = 'center'
    custom_x: int = 0
    custom_y: int = 0
    gain: float = 1
    dialogue_enabled: bool = False
    dialogue: list[dict] = field(default_factory=list)
    dialogue_expand: float = .35
    dialogue_scroll: float = .45
    dialogue_scroll_delay: float = 1.0
    dialogue_font_size: int = 26

    def content_duration(self, audio_duration):
        """Keep late messages on screen after the voice track has ended."""
        last = max((message["end"] for message in self.dialogue), default=0) if self.dialogue_enabled else 0
        return max(audio_duration, last)

    def validate(self):
        if self.driver not in DRIVERS: raise ValueError('未知车手预设：'+str(self.driver))
        if self.team is not None and self.team not in TEAMS: raise ValueError('未知车队：'+str(self.team))
        for key in ('width','height'):
            v=getattr(self,key)
            if isinstance(v,bool) or not isinstance(v,int) or v<64 or v>7680 or v%2:
                raise ValueError('画面宽高须为 64–7680 内的偶数')
        if not isinstance(self.fps,int) or isinstance(self.fps,bool) or not 1<=self.fps<=120: raise ValueError('帧率须为 1–120 的整数')
        for key in ('entrance','fade_out','hold','start_delay'):
            v=getattr(self,key)
            if not isinstance(v,numbers.Real) or not math.isfinite(v) or v<0:
                raise ValueError(key+' 须为不小于 0 的有限秒数')
        if not isinstance(self.card_scale,numbers.Real) or not math.isfinite(self.card_scale) or not .1<=self.card_scale<=1:
            raise ValueError('卡片比例须为 0.1–1')
        if not isinstance(self.gain,numbers.Real) or not math.isfinite(self.gain) or not .01<=self.gain<=20: raise ValueError('波形增益须为 0.01–20')
        if self.background not in ('transparent','color'): raise ValueError('背景须为 transparent 或 color')
        if self.position not in ('center','top-left','top-right','bottom-left','bottom-right','custom'): raise ValueError('未知卡片位置')
        for key in ('custom_x','custom_y'):
            if not isinstance(getattr(self,key),int): raise ValueError('自定义位置须为整数像素')
        for col in (self.color,self.background_color):
            if col is not None and (not isinstance(col,str) or re.fullmatch(r'#[0-9a-fA-F]{6}',col) is None):
                raise ValueError('颜色须为 #RRGGBB')
        if self.name is not None and (not isinstance(self.name,str) or not self.name.strip() or len(self.name)>80): raise ValueError('姓名须为 1–80 个字符')
        if self.number is not None:
            if not re.fullmatch(r'[0-9]{1,3}',str(self.number)): raise ValueError('车号须为 1–3 位数字')
        if self.logo_variant not in (None,'white','color'): raise ValueError('队标版本须为 white 或 color')
        if self.logo_path is not None and not Path(self.logo_path).is_file(): raise ValueError('自定义队标不存在')
        if not isinstance(self.dialogue_enabled,bool): raise ValueError("留言模式须为布尔值")
        for key in ("dialogue_expand","dialogue_scroll","dialogue_scroll_delay"):
            value=getattr(self,key)
            if isinstance(value,bool) or not isinstance(value,numbers.Real) or not math.isfinite(value) or not 0<=value<=10:
                raise ValueError("文字展开、滚动和滚动前停留时间须为 0–10 秒")
        if isinstance(self.dialogue_font_size,bool) or not isinstance(self.dialogue_font_size,int) or not 14<=self.dialogue_font_size<=40:
            raise ValueError("留言字号须为 14–40")
        from .dialogue import validate_messages
        self.dialogue=validate_messages(self.dialogue)
        return self

# Original source-card dimensions, independent of the output video's aspect.
CARD_WIDTH, CARD_HEIGHT = 329, 176
CARD_ASPECT = CARD_WIDTH / CARD_HEIGHT

from functools import lru_cache
import json

@lru_cache(maxsize=1)
def _lettering():
    return json.loads((ASSETS/'lettering'/'lettering.json').read_text(encoding='utf-8'))

@lru_cache(maxsize=1)
def _numerals():
    return json.loads((ASSETS/'numerals'/'contours.json').read_text(encoding='utf-8'))['digits']


def number_mask(text,height):
    """Rasterize clean straight vector contours at the requested resolution."""
    height=max(1,int(height)); gap=max(1,round(height*7/88))
    padding=max(2,math.ceil(height/88)); ss=2
    glyphs=[]
    for ch in str(text):
        contours=_numerals()[ch]
        width=max(1,math.ceil(max(x for path in contours for x,y in path)*height))
        canvas=Image.new('1',(width*ss,height*ss))
        for path in contours:
            layer=Image.new('1',canvas.size)
            ImageDraw.Draw(layer).polygon([(round(x*height*ss),round(y*height*ss)) for x,y in path],fill=1)
            canvas=ImageChops.logical_xor(canvas,layer)
        glyphs.append(canvas.convert('L').resize((width,height),Image.Resampling.LANCZOS))
    result=Image.new('L',(sum(g.width for g in glyphs)+gap*(len(glyphs)-1)+padding*2,height+padding*2))
    x=padding
    for glyph in glyphs:
        result.paste(glyph,(x,padding)); x+=glyph.width+gap
    return result


def _font_path(text,radio=False):
    filename='RadioRounded-Radio.ttf' if radio else 'RadioRounded-Bold.ttf'
    path=ASSETS/'fonts'/filename
    if any(ord(c)>0x3000 for c in text) and Path('C:/Windows/Fonts/msyhbd.ttc').is_file():
        path=Path('C:/Windows/Fonts/msyhbd.ttc')
    elif any(not(c.isascii() and (c.isalpha() or c in " -.'")) for c in text):
        path=ASSETS/'fonts'/'DejaVuSans-Bold.ttf'
    return path


def _vector_text(text,width,height,radio=False):
    """Render TrueType curves at final scale, never enlarge a screenshot word."""
    font=ImageFont.truetype(str(_font_path(text,radio)),max(16,height*2))
    bbox=font.getbbox(text)
    mask=Image.new('L',(max(1,bbox[2]-bbox[0])+8,max(1,bbox[3]-bbox[1])+8))
    ImageDraw.Draw(mask).text((4-bbox[0],4-bbox[1]),text,font=font,fill=255)
    ink=mask.getbbox()
    return mask.crop(ink).resize((max(1,round(width)),max(1,round(height))),Image.Resampling.LANCZOS)


def _tint(mask,color):
    layer=Image.new('RGBA',mask.size,color); layer.putalpha(mask); return layer


# Actual source-logo footprints. No universal bounding box that enlarges W/McLaren.
LOGO_SIZES={
    'williams':(49,28),'mercedes':(49,49),'ferrari':(36,47),
    'red_bull':(69,27),'racing_bulls':(44,47),'mclaren':(53,29),
    'haas':(55,49),'audi':(64,24),'alpine':(61,34),
    'aston_martin':(71,15),'cadillac':(63,24),
}


class CardRenderer:
    def __init__(self,config):
        self.config=config.validate()
        preset=DRIVERS[config.driver]; self.team=config.team or preset['team']
        self.color=ImageColor.getrgb(config.color or TEAMS[self.team]['color'])
        self.name=(config.name or preset['name']).strip().upper()
        self.number=str(config.number if config.number is not None else preset['number'])
        aspect=CARD_WIDTH/(CARD_HEIGHT+276) if config.dialogue_enabled else CARD_ASPECT
        width=min(config.width*config.card_scale,config.height*config.card_scale*aspect)
        self.w=max(16,int(width)); self.h=max(9,round(self.w/CARD_ASPECT))
        self.dialogue_panel=None
        if config.dialogue_enabled:
            from .dialogue import DialoguePanel
            self.dialogue_panel=DialoguePanel(config.dialogue,self.color,self.w,expand=config.dialogue_expand,
                scroll=config.dialogue_scroll,scroll_delay=config.dialogue_scroll_delay,font_size=config.dialogue_font_size)
        self.layout_h=self.h+(self.dialogue_panel.max_height if self.dialogue_panel else 0)
        self.x,self.y=self._position()
        self._base,self._foreground=self._static_layers()
        self._xx=np.arange(self.w,dtype=np.float32)[None,:]/self.w
        self._yy=np.arange(self.h,dtype=np.float32)[:,None]/self.h
        # Recording strip centre is ~21 source pixels left of the final centre.
        diagonal=(self._xx-.5)*self.w+(self._yy-.5)*self.h+21*self.w/329
        self._diag=np.abs(diagonal)/(.5*(self.w+self.h)+21*self.w/329)
        self._zero=Image.new('RGBA',(config.width,config.height))

    def _position(self):
        c=self.config; margin=round(min(c.width,c.height)*.05)
        if c.position=='custom': return c.custom_x,c.custom_y
        if c.position=='center': return (c.width-self.w)//2,(c.height-self.layout_h)//2
        return (margin if c.position.endswith('left') else c.width-self.w-margin,
                margin if c.position.startswith('top') else c.height-self.layout_h-margin)

    def _static_layers(self):
        s=max(4,min(12,math.ceil(self.w/329*1.4)))
        W,H=329*s,176*s
        with Image.open(ASSETS/'background'/'reference_panel.png') as source:
            base=source.convert('RGBA').resize((W,H),Image.Resampling.LANCZOS)
        # Source screenshots show a shallow accent glow along the top edge.
        pixels=np.array(base,dtype=np.float32)
        yy,xx=np.mgrid[:H,:W].astype(np.float32); yy/=H; xx/=W
        top=np.exp(-yy/.12)[:,:,None]
        neutral=np.array([19,20,30],dtype=np.float32)
        tint=np.asarray(self.color,dtype=np.float32)/255*42
        top_rgb=neutral+tint[None,None,:]*(.35+.65*xx[:,:,None])
        pixels[:,:,:3]=pixels[:,:,:3]*(1-top)+top_rgb*top
        base=Image.fromarray(np.clip(pixels,0,255).astype('uint8'))
        fg=Image.new('RGBA',(W,H))
        data=_lettering()
        # Source images supply dimensions only. Every letter below is drawn
        # from smooth TrueType contours at this output's actual pixel scale.
        entry=next((item for item in data['names'].values() if item['text']==self.name),None)
        if entry and entry.get('core_bbox') and entry.get('card_bbox'):
            core=entry['core_bbox']; card=entry['card_bbox']
            px=core[0]-card[0]; name_width=core[2]-core[0]
        elif entry and entry.get('mask_core_bbox'):
            core=entry['mask_core_bbox']; name_width=core[2]-core[0]
            px=317-name_width
        else:
            font=ImageFont.truetype(str(_font_path(self.name)),700)
            bbox=font.getbbox(self.name)
            cap=font.getbbox('H')[3]-font.getbbox('H')[1]
            name_width=min(305,(bbox[2]-bbox[0])*29/max(1,cap))
            px=317-name_width
        nm=_vector_text(self.name,name_width*s,29*s)
        fg.alpha_composite(_tint(nm,self.color),(round(px*s),12*s))
        rm=_vector_text('RADIO',130*s,27*s,radio=True)
        fg.alpha_composite(_tint(rm,(253,253,255)),(187*s,44*s))
        # h88, x12, lower edge164 are measured source pixels, not 16:9 scaling.
        nh=(88 if len(self.number)<=2 else 76)*s
        mask=number_mask(self.number,nh)
        pad=max(2,math.ceil(nh/88))
        stroke_radius=max(1,round(.55*s))
        stroke=mask.filter(ImageFilter.MaxFilter(stroke_radius*2+1))
        outline=_tint(stroke.point(lambda a:round(a*.48)),(238,242,251))
        ink=_tint(mask,self.color)
        number=Image.alpha_composite(outline,ink)
        nx=12*s-pad; ny=164*s-nh-pad
        shadow=_tint(stroke.point(lambda a:round(a*.48)),(0,0,0))
        fg.alpha_composite(shadow,(nx+round(1.1*s),ny+round(1.4*s)))
        fg.alpha_composite(number,(nx,ny))
        variant=self.config.logo_variant or TEAMS[self.team]['logo_variant']
        measured_logo=ASSETS/'reference_logos'/f'{self.team}_{variant}.png'
        path=(Path(self.config.logo_path) if self.config.logo_path else
              measured_logo if measured_logo.is_file() else logo_path(self.team,variant))
        try:
            with Image.open(path) as source: logo=source.convert('RGBA')
        except Exception as exc: raise ValueError('无法读取队标图片：'+str(path)) from exc
        lw,lh=LOGO_SIZES[self.team]
        if self.config.logo_path: lw,lh=69,49
        scale=min(lw*s/logo.width,lh*s/logo.height)
        logo=logo.resize((max(1,round(logo.width*scale)),max(1,round(logo.height*scale))),Image.Resampling.LANCZOS)
        fg.alpha_composite(logo,(317*s-logo.width,164*s-logo.height))
        return base.resize((self.w,self.h),Image.Resampling.LANCZOS),fg.resize((self.w,self.h),Image.Resampling.LANCZOS)

    def _wave(self,levels):
        """Nine abutting histogram blocks, including the strip below the logo."""
        a=np.asarray(levels,dtype=np.float32).reshape(-1)
        if not np.isfinite(a).all(): a=np.zeros(9,dtype=np.float32)
        if len(a)==96: a=np.array([np.mean(part) for part in np.array_split(a,9)])
        if len(a)!=9: a=np.zeros(9,dtype=np.float32)
        a=np.clip(a,0,1)
        w,h=self.w,self.h
        boundaries=np.rint(np.linspace(0,w,10)).astype(int)
        heights=np.rint(a*h*(68/176)).astype(int)
        if float(a.max())>.005:
            # At small output sizes the quiet edge bumps must not round away.
            heights=np.where(a>0,np.maximum(heights,max(1,round(h*.6/176))),0)
        alpha=np.zeros((h,w),dtype=np.float32)
        for i,height in enumerate(heights):
            if height<=0: continue
            start=h-height
            # Flat contiguous caps, with soft upper fringes and no x-axis gaps.
            vertical=np.linspace(.42,.84,height,dtype=np.float32)
            edge=min(height,max(1,round(h/176*1.2)))
            vertical[:edge]*=np.linspace(.12,1,edge)
            alpha[start:,boundaries[i]:boundaries[i+1]]=vertical[:,None]
        if np.max(alpha)>0:
            # Fine scan texture lives INSIDE each solid block; its minimum stays
            # opaque enough that it never separates the nine macro columns.
            native_x=np.arange(w)*329/w
            scan=.84+.16*(.5+.5*np.cos(native_x*np.pi))
            alpha*=scan[None,:]
            mask=Image.fromarray(np.clip(alpha*255,0,255).astype('uint8'))
            mask=mask.filter(ImageFilter.GaussianBlur(max(.35,w/329*.75)))
        else: mask=Image.new('L',(w,h))
        return _tint(mask,self.color)

    def frame(self,t,audio_start,audio_duration,levels):
        c=self.config
        canvas=(Image.new('RGBA',(c.width,c.height),ImageColor.getrgb(c.background_color)+(255,))
                if c.background=='color' else self._zero.copy())
        begin=c.start_delay; end=audio_start+c.content_duration(audio_duration)+c.hold
        if t<begin or t>=end+c.fade_out: return canvas
        card=Image.alpha_composite(self._base,self._wave(levels))
        card=Image.alpha_composite(card,self._foreground)
        if c.entrance>0 and t<begin+c.entrance:
            p=max(0,min(1,(t-begin)/c.entrance))
            # Slow narrow-strip phase followed by the full diagonal expansion.
            q=p**1.65
            band=np.clip((q*1.02-self._diag)*min(self.w,self.h)+.5,0,1)
            mask=Image.fromarray((band*255).astype('uint8'))
            card.putalpha(ImageChops.multiply(card.getchannel('A'),mask))
            if p<.22:
                flash=Image.new('RGBA',card.size,(225,236,245))
                fm=np.clip((.003-self._diag)*400,0,1)*(1-p/.22)*95
                flash.putalpha(Image.fromarray(fm.astype('uint8')))
                card=Image.alpha_composite(card,flash)
        if t>=end and c.fade_out>0:
            opacity=max(0,1-(t-end)/c.fade_out)
            card.putalpha(card.getchannel('A').point(lambda v:round(v*opacity)))
        canvas.alpha_composite(card,(self.x,self.y))
        if self.dialogue_panel is not None and t>=audio_start:
            panel=self.dialogue_panel.frame(t-audio_start)
            if t>=end and c.fade_out>0:
                opacity=max(0,1-(t-end)/c.fade_out)
                panel.putalpha(panel.getchannel("A").point(lambda value:round(value*opacity)))
            canvas.alpha_composite(panel,(self.x,self.y+self.h))
        return canvas
