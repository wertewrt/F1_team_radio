"""Extract rounded broadcast lettering from the supplied screenshots.

No installed or generated font participates. Full preset words are primary.
Pixels are dematted in encoded screenshot RGB, retaining observed blur/AA.
The small source cannot honestly supply detail absent from the screenshot.
Run: python tools/extract_lettering.py
"""
from pathlib import Path
import json
import sys
import string
import numpy as np
import cv2
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from teamradio.presets import DRIVERS
OUT = ROOT / 'assets' / 'lettering'
# Manually inspected card rectangles; exclusive right/bottom, native pixels.
SOURCES = {
'hulkenberg': ('174745', (13,16,343,192), (24,25,334,60)),
'hadjar': ('174758', (13,15,343,191), (145,24,333,59)),
'alonso': ('174845', (16,15,346,191), (145,24,337,59)),
'bearman': ('174857', (10,15,340,191), (88,24,331,59)),
'sainz': ('175106', (19,9,349,185), (197,18,340,52)),
'ocon': ('175125', (16,16,346,192), (207,25,337,59)),
'bortoleto': ('175138', (10,12,340,188), (55,21,331,55)),
'verstappen': ('175209', (10,10,340,186), (21,19,332,53)),
'norris': ('175229', (11,15,341,191), (158,24,332,59)),
'antonelli': ('175245', (16,15,346,191), (73,24,337,59)),
'colapinto': ('175453', (17,6,347,182), (74,15,337,49)),
'hamilton': ('175513', (10,15,340,191), (81,24,331,59)),
'gasly': ('175609', (17,18,347,194), (182,27,337,61)),
'stroll': ('175712', (11,9,341,185), (153,18,332,52)),
'piastri': ('175903', (16,15,346,191), (154,24,337,59)),
'leclerc': ('180012', (7,12,337,188), (128,21,327,55)),
'russell': ('180209', (10,15,340,191), (125,24,331,59)),
'perez': ('180333', (13,12,343,188), (183,21,333,55)),
'lawson': ('180805', (13,12,343,188), (128,21,333,55)),
'bottas': ('180835', (10,12,340,188), (143,21,331,55)),
'lindblad': ('181452', (16,15,346,191), (105,24,337,59)),
'tsunoda': ('181507', (5,7,335,183), (99,16,325,50)),
}
# The rightmost transition column is outside the 329-pixel dark panel.
SOURCES = {k:(stamp,(b[0],b[1],b[2]-1,b[3]),win) for k,(stamp,b,win) in SOURCES.items()}


def bbox(a, threshold=0.05):
    yy, xx = np.where(a > threshold)
    if len(xx) == 0:
        raise ValueError('Empty foreground')
    return [int(xx.min()),int(yy.min()),int(xx.max()+1),int(yy.max()+1)]


def normalized(b, card):
    x,y,r,d = card
    return [round((b[0]-x)/(r-x),7),round((b[1]-y)/(d-y),7),
            round((b[2]-x)/(r-x),7),round((b[3]-y)/(d-y),7)]


def dematte(rgb):
    """Project source RGB onto measured foreground/background color line.

    cv2 inpainting only estimates the dark background behind the lettering.
    Alpha itself is never eroded, thresholded into binary, or sharpened.
    A two-pixel support margin suppresses unrelated dark-card texture.
    """
    p = np.asarray(rgb, dtype=np.float32) / 255
    lum = p.max(axis=2)
    dark = np.median(p[lum < np.quantile(lum,.30)], axis=0)
    dist = np.linalg.norm(p-dark, axis=2)
    foreground = np.median(p[dist > np.quantile(dist,.77)],axis=0)
    direction = foreground-dark
    initial = np.clip(((p-dark)*direction).sum(2)/(direction@direction),0,1)
    holes = (initial>.06).astype(np.uint8)*255
    holes = cv2.dilate(holes,np.ones((3,3),np.uint8))
    # Telea interpolates existing RGB from the surrounding dark card.
    bg = cv2.inpaint((p*255).astype(np.uint8),holes,5,cv2.INPAINT_TELEA).astype(np.float32)/255
    bg = cv2.GaussianBlur(bg,(0,0),1.0)
    direction = foreground-bg
    alpha = np.clip(((p-bg)*direction).sum(2)/np.maximum((direction*direction).sum(2),1e-6),0,1)
    seed = (alpha>.20).astype(np.uint8)
    n,labels,stats,_ = cv2.connectedComponentsWithStats(seed,8)
    keep = np.zeros(seed.shape,np.uint8)
    for i in range(1,n):
        if stats[i,cv2.CC_STAT_AREA]>=5:
            keep[labels==i]=1
    support=cv2.dilate(keep,np.ones((5,5),np.uint8))
    alpha*=support
    # Smoothly suppress at most 1/255 of unrelated compression noise.
    alpha=np.clip((alpha-1/255)/(1-1/255),0,1)
    return alpha,foreground,bg


def extract(image,window,card,filename):
    crop=image.crop(window)
    alpha,fg,bg=dematte(crop)
    core=bbox(alpha,.5)
    bound=bbox(alpha,.025)
    bound=[max(0,bound[0]-1),max(0,bound[1]-1),min(alpha.shape[1],bound[2]+1),min(alpha.shape[0],bound[3]+1)]
    x,y,r,d=bound
    mask=Image.fromarray(np.rint(alpha[y:d,x:r]*255).astype(np.uint8))
    mask.save(OUT/filename)
    absolute=[x+window[0],y+window[1],r+window[0],d+window[1]]
    core_abs=[core[0]+window[0],core[1]+window[1],core[2]+window[0],core[3]+window[1]]
    meta={'file':filename,'source_bbox':absolute,'source_window':list(window),'native_size':list(mask.size),
          'card_bbox':list(card),'bbox_normalized_to_card':normalized(absolute,card),
          'core_bbox':core_abs,'core_bbox_normalized_to_card':normalized(core_abs,card),
          'mask_core_bbox':[core[0]-x,core[1]-y,core[2]-x,core[3]-y],
          'cap_height':core[3]-core[1],'foreground_rgb':[int(round(v*255)) for v in fg],
          'alpha_bbox_threshold':.025,'cap_height_alpha_threshold':.5,
          'aspect_ratio':round(mask.width/mask.height,7),'kind':'source_word'}
    return mask,meta


def source_image(key):
    stamp,card,window=SOURCES[key]
    p=ROOT/'resource'/('屏幕截图 2026-10-20 '+stamp+'.png')
    return Image.open(p).convert('RGB'),p,card,window


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    metrics={'version':1,'mask_mode':'L','bbox_convention':'xyxy, exclusive right/bottom, native source pixels',
      'method':'RGB color-line alpha estimate against inpainted local dark background; observed blur retained',
      'limitations':'Sources are ~330x176 cards: masks reproduce observed low-resolution silhouettes, not unavailable font detail. F/Q/X and ALBON are explicitly composed.',
      'names':{},'glyphs':{},'sources':{}}
    masks={}
    for key in SOURCES:
        image,path,card,window=source_image(key)
        mask,meta=extract(image,window,card,'name_'+key+'.png')
        meta.update(source_image=path.relative_to(ROOT).as_posix(),text=DRIVERS[key]['name'])
        masks[key]=mask
        metrics['names'][key]=meta
        # RADIO is consistently ~44 pixels below the top, to 75 pixels.
        radio_window=(card[2]-150,card[1]+42,card[2]-7,card[1]+75)
        rm,rmeta=extract(image,radio_window,card,'radio_'+key+'.png')
        rmeta.update(source_image=path.relative_to(ROOT).as_posix(),text='RADIO')
        metrics['sources'][key]={'name':meta,'radio':rmeta,'image_size':list(image.size)}
    # Most neutral clean word: full RADIO from the original OCON screenshot.
    radio=Image.open(OUT/'radio_ocon.png').copy()
    radio.save(OUT/'radio.png')
    metrics['radio']=dict(metrics['sources']['ocon']['radio'],file='radio.png')
    # Individual glyph splitting is deliberately separate from exact preset words.
    build_atlas(metrics,masks)
    (OUT/'lettering.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    comparison(metrics)
    print(json.dumps({'names':len(metrics['names']),'glyphs':len(metrics['glyphs']),'radio':metrics['radio'],'out':str(OUT)},ensure_ascii=False))


def build_atlas(metrics,masks):
    # Explicit native column cuts, measured between distinct letter bodies.
    # No connected component is allowed to contain two atlas letters.
    cuts={
      'A':('bearman',58,93), 'B':('bearman',0,30),
      'C':('colapinto',0,30), 'D':('hadjar',68,99),
      'E':('bearman',30,58), 'G':('gasly',0,32),
      'H':('hadjar',0,34), 'I':('piastri',31,43),
      'J':('hadjar',98,121), 'K':('hulkenberg',92,123),
      'L':('antonelli',197,223), 'M':('bearman',123,168),
      'N':('antonelli',37,71), 'O':('ocon',0,33),
      'P':('piastri',0,31), 'R':('bearman',93,123),
      'S':('piastri',78,106), 'T':('piastri',105,137),
      'U':('tsunoda',62,94), 'V':('verstappen',0,37),
      'W':('lawson',60,109), 'Y':('gasly',119,153),
      'Z':('sainz',110,142),
    }
    glyphs={}
    for letter,(key,left,right) in cuts.items():
        word=np.asarray(masks[key],dtype=np.float32)/255
        piece=word[:,left:right].copy()
        n,labels,stats,_=cv2.connectedComponentsWithStats((piece>.5).astype(np.uint8),8)
        owner=1+int(np.argmax(stats[1:,cv2.CC_STAT_AREA]))
        support=cv2.dilate((labels==owner).astype(np.uint8),np.ones((5,5),np.uint8))
        piece*=support
        cb=bbox(piece,.5)
        core_height=cb[3]-cb[1]
        scale=29/core_height
        # Keep observed 2-pixel AA margins, adding transparent outer pixels.
        area=Image.fromarray(np.rint(piece*255).astype(np.uint8))
        cropbox=(cb[0]-2,cb[1]-3,cb[2]+2,cb[3]+3)
        area=area.crop(cropbox)
        area=area.resize((max(1,round(area.width*scale)),35),Image.Resampling.LANCZOS)
        # Match sidebearings so advance yields exactly one pixel ink gap.
        shift=bbox(np.asarray(area)/255,.5)[0]-2
        if shift:
            area=area.crop((shift,0,area.width+min(0,shift),35))
        glyphs[letter]=area
        src=metrics['names'][key]
        sx=src['source_bbox'][0]+left+cropbox[0]
        sy=src['source_bbox'][1]+cropbox[1]
        meta={'source_image':src['source_image'],'source_driver':key,
              'source_bbox':[sx,sy,sx+cropbox[2]-cropbox[0],sy+cropbox[3]-cropbox[1]],
              'source_column_cut':[left,right], 'kind':'source_glyph',
              'scale_from_source':scale,'original_cap_height':core_height}
        save_glyph(letter,area,meta,metrics)
    # F keeps E's native horizontal bars and vertical stroke. Only the
    # nonexistent lower bar is removed using a soft vertical stroke mask.
    e=np.asarray(glyphs['E'],dtype=np.float32)/255
    f=e.copy()
    stem_profile=e[22].copy()
    stem_profile[12:16]=e[22,:4][::-1]
    stem_profile[16:]=0
    f[22:]=np.minimum(f[22:],stem_profile[None,:])
    glyphs['F']=Image.fromarray(np.rint(f*255).astype(np.uint8))
    save_glyph('F',glyphs['F'],{'kind':'derived_glyph','derived_from':['E'],
      'construction':'E lower bar removed, preserving its measured stem profile'},metrics)
    # Q adds a short source-R diagonal leg to O. It is explicitly derived,
    # never claimed to have appeared in a supplied screenshot.
    o=np.asarray(glyphs['O'],dtype=np.float32)/255
    r=np.asarray(glyphs['R'],dtype=np.float32)/255
    q=o.copy()
    tail=r[23:33,max(0,r.shape[1]-13):r.shape[1]-1]
    th,tw=tail.shape
    q[-th:, -tw-1:-1]=np.maximum(q[-th:,-tw-1:-1],tail)
    glyphs['Q']=Image.fromarray(np.rint(q*255).astype(np.uint8))
    save_glyph('Q',glyphs['Q'],{'kind':'derived_glyph','derived_from':['O','R'],
      'construction':'O plus short original R diagonal stroke'},metrics)
    # X uses the source V diagonals, compressed to the upper half and mirrored.
    v=glyphs['V'].crop((0,3,glyphs['V'].width,32))
    half=v.resize((v.width,15),Image.Resampling.LANCZOS)
    x=Image.new('L',(v.width,35))
    x.paste(half,(0,3))
    top=np.asarray(x,dtype=np.uint8)
    bottom=np.flipud(top)
    glyphs['X']=Image.fromarray(np.maximum(top,bottom))
    save_glyph('X',glyphs['X'],{'kind':'derived_glyph','derived_from':['V'],
      'construction':'Source V diagonals compressed vertically and mirrored'},metrics)
    metrics['atlas']={'cap_height':29,'canvas_height':35,'cap_top':3,
      'baseline':32,'letter_gap':1,'space_advance':15,
      'advance_rule':'Place each glyph at pen; next pen += advance; masks include two-pixel blur sidebearings. Advance gives a 1-pixel gap between 50%-alpha ink boxes.',
      'synthetic_letters':['F','Q','X']}
    # Compose only the missing preset. All observed presets retain full words.
    text='ALBON'
    advances=[metrics['glyphs'][c]['advance'] for c in text]
    width=sum(advances[:-1])+glyphs[text[-1]].width
    composed=np.zeros((35,width),np.uint8)
    pen=0
    for c,advance in zip(text,advances):
        a=np.asarray(glyphs[c]);
        composed[:,pen:pen+a.shape[1]]=np.maximum(composed[:,pen:pen+a.shape[1]],a)
        pen+=advance
    albon=Image.fromarray(composed)
    albon.save(OUT/'name_albon.png')
    cb=bbox(composed/255,.5)
    # Nominal placement shares SAINZ's original right ink edge and cap top.
    ref=metrics['names']['sainz']
    ink_right=ref['core_bbox'][2]
    x=ink_right-cb[2]
    y=ref['core_bbox'][1]-cb[1]
    placed=[x,y,x+width,y+35]
    coreplaced=[x+cb[0],y+cb[1],x+cb[2],y+cb[3]]
    metrics['names']['albon']={'file':'name_albon.png','text':'ALBON',
       'native_size':list(albon.size),'cap_height':29,'kind':'composed_word',
       'source_image':None,'source_bbox':None,'card_bbox':ref['card_bbox'],
       'nominal_layout_bbox':placed,'bbox_normalized_to_card':normalized(placed,ref['card_bbox']),
       'core_bbox':None,'mask_core_bbox':cb,
       'core_bbox_normalized_to_card':normalized(coreplaced,ref['card_bbox']),
       'foreground_rgb':ref['foreground_rgb'],'aspect_ratio':width/35,
       'construction':'A,L,B,O,N from extracted atlas, one native pixel ink gap; no glyph dilation'}
    atlas_comparison(metrics,glyphs,albon)


def save_glyph(letter,mask,meta,metrics):
    filename='glyph_'+letter+'.png'
    mask.save(OUT/filename)
    cb=bbox(np.asarray(mask)/255,.5)
    meta.update(file=filename,native_size=list(mask.size),cap_height=29,baseline=32,
                core_bbox=cb,advance=cb[2]-cb[0]+1)
    metrics['glyphs'][letter]=meta


def atlas_comparison(metrics,glyphs,albon):
    sheet=Image.new('RGB',(1440,760),(21,23,31))
    draw=ImageDraw.Draw(sheet)
    draw.text((12,8),'ROUNDED SOURCE GLYPHS / F Q X ARE DOCUMENTED DERIVATIONS',fill='white')
    for i,c in enumerate(string.ascii_uppercase):
        x=(i%9)*160+12;y=(i//9)*175+35
        m=glyphs[c]
        colored=Image.new('RGB',m.size,(21,23,31))
        colored.paste((76,228,209),(0,0,*m.size),m)
        colored=colored.resize((m.width*3,m.height*3),Image.Resampling.NEAREST)
        sheet.paste(colored,(x,y+18))
        draw.text((x,y),c+(' / derived' if c in 'FQX' else ''),fill='white')
    draw.text((12,574),'ALBON / composed from original glyphs at original 29px capheight',fill='white')
    colored=Image.new('RGB',albon.size,(21,23,31))
    colored.paste((43,109,202),(0,0,*albon.size),albon)
    sheet.paste(colored.resize((albon.width*4,140),Image.Resampling.NEAREST),(12,600))
    sheet.save(OUT/'atlas_comparison.png')


def comparison(metrics):
    width=1160
    sheet=Image.new('RGB',(width,95*(len(SOURCES)+2)),(32,34,40))
    draw=ImageDraw.Draw(sheet)
    draw.text((12,7),'ORIGINAL SOURCE CROP (4x)                      EXTRACTED ALPHA, SAME COLOR (4x)',fill='white')
    for i,(key,src) in enumerate(SOURCES.items()):
        image,_,card,win=source_image(key)
        meta=metrics['names'][key]
        b=meta['source_bbox']
        original=image.crop(b)
        mask=Image.open(OUT/meta['file'])
        pixels=np.asarray(image.crop(win)).reshape(-1,3)
        bg=tuple(np.median(pixels[pixels.max(1)<np.quantile(pixels.max(1),.20)],axis=0).astype(int))
        rendered=Image.new('RGB',mask.size,bg)
        rendered.paste(tuple(meta['foreground_rgb']),(0,0,*mask.size),mask)
        # Equal scale; no font reconstruction or normalized spacing in this check.
        scale=min(4,535/original.width,65/original.height)
        size=(round(original.width*scale),round(original.height*scale))
        y=30+i*95
        sheet.paste(original.resize(size,Image.Resampling.NEAREST),(12,y+18))
        sheet.paste(rendered.resize(size,Image.Resampling.NEAREST),(590,y+18))
        draw.text((12,y),key.upper(),fill='white')
    y=30+len(SOURCES)*95
    m=metrics['radio']; image=Image.open(ROOT/m['source_image']); mask=Image.open(OUT/'radio.png')
    original=image.crop(m['source_bbox']); bg=(23,23,32)
    rendered=Image.new('RGB',mask.size,bg);rendered.paste(tuple(m['foreground_rgb']),(0,0,*mask.size),mask)
    sheet.paste(original.resize((original.width*4,original.height*4)),(12,y+18))
    sheet.paste(rendered.resize((mask.width*4,mask.height*4)),(590,y+18))
    draw.text((12,y),'RADIO / complete source word',fill='white')
    sheet.save(OUT/'comparison.png')


if __name__=='__main__':
    main()
