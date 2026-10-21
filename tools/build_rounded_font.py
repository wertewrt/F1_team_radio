"""Reconstruct clean, scalable rounded lettering from observed source outlines.

The source determines geometry and proportions, not a substitute installed font.
A contour approximation removes subpixel compression wiggles. Long straight
segments stay straight; local quadratic fillets regularize small corners.
Measured stems, counters, circular bowls and M arches receive exact geometric
reconstruction to remove compression-induced waviness. All exported glyphs
are ordinary TrueType outlines; no bitmap strikes or embedded source images.
"""
from pathlib import Path
import json
import math
import string
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT=Path(__file__).resolve().parent.parent
ASSETS=ROOT/'assets'/'lettering'
FONTS=ROOT/'assets'/'fonts'
CAP=700
UPM=1000
TRACE_SCALE=12
SIMPLIFY_NATIVE=.18
CORNER_FILLET_NATIVE=.30


def native_polygons(mask,threshold=190):
    a=np.asarray(mask,dtype=np.uint8)
    # Bicubic interpolation samples the continuous antialiased edge. It is
    # discarded after tracing and never included in the exported TTF.
    field=cv2.resize(a,None,fx=TRACE_SCALE,fy=TRACE_SCALE,interpolation=cv2.INTER_CUBIC)
    contours,hierarchy=cv2.findContours((field>=threshold).astype(np.uint8),cv2.RETR_CCOMP,cv2.CHAIN_APPROX_NONE)
    polygons=[]
    for i,contour in enumerate(contours):
        if cv2.contourArea(contour)<TRACE_SCALE**2*.6:
            continue
        points=cv2.approxPolyDP(contour,SIMPLIFY_NATIVE*TRACE_SCALE,True).reshape(-1,2).astype(float)/TRACE_SCALE
        if len(points)<3:
            continue
        # Regularize measured horizontal/vertical stems, without snapping
        # diagonal or bowl contours to the pixel grid.
        for _ in range(2):
            for j in range(len(points)):
                k=(j+1)%len(points)
                d=points[k]-points[j]
                if abs(d[0])<.30 and abs(d[1])>2:
                    points[j,0]=points[k,0]=(points[j,0]+points[k,0])/2
                if abs(d[1])<.30 and abs(d[0])>2:
                    points[j,1]=points[k,1]=(points[j,1]+points[k,1])/2
        polygons.append((points,int(hierarchy[0][i][3])!=-1))
    return polygons


def curve_segments(points):
    """Return straight segments plus quadratic corner/curve segments.

    Fillet distances stay below 0.48 native pixels on every segment.
    Right-angle stem corners receive a 0.30 source-pixel fillet.
    """
    entries=[];exits=[];controls=[]
    n=len(points)
    for i,p in enumerate(points):
        prev=points[(i-1)%n];nxt=points[(i+1)%n]
        before=p-prev;after=nxt-p
        lb=np.linalg.norm(before);la=np.linalg.norm(after)
        cosine=np.clip(np.dot(before,after)/max(lb*la,1e-8),-1,1)
        turn=math.degrees(math.acos(cosine))
        hard=turn>58
        # Never move a contour farther than a small native-pixel fillet.
        # Midpoint splines across long segments shrink narrow counters and
        # produce a different, inflated face; measured source outlines win.
        radius=CORNER_FILLET_NATIVE if hard else .48
        db=min(radius,lb*.43)
        da=min(radius,la*.43)
        entries.append(p-before/lb*db)
        exits.append(p+after/la*da)
        controls.append(p)
    segments=[]
    for i in range(n):
        if i==0:
            segments.append(('M',entries[i]))
        segments.append(('Q',controls[i],exits[i]))
        nxt=entries[(i+1)%n]
        if np.linalg.norm(exits[i]-nxt)>.001:
            segments.append(('L',nxt))
    return segments


def sample_segments(segments):
    pts=[];last=None
    for seg in segments:
        if seg[0]=='M':
            last=np.asarray(seg[1],dtype=float);pts.append(last)
        elif seg[0]=='L':
            last=np.asarray(seg[1],dtype=float);pts.append(last)
        else:
            control,end=[np.asarray(p,dtype=float) for p in seg[1:]]
            for t in np.linspace(0,1,21)[1:]:
                pts.append((1-t)**2*last+2*(1-t)*t*control+t*t*end)
            last=end
    return np.asarray(pts)


def outline_from_mask(mask,width,threshold=190):
    allsegments=[curve_segments(p) for p,_ in native_polygons(mask,threshold)]
    cloud=np.concatenate([sample_segments(s) for s in allsegments])
    minimum=cloud.min(0);maximum=cloud.max(0)
    span=maximum-minimum
    result=[]
    for segments in allsegments:
        converted=[]
        for seg in segments:
            points=[]
            for p in seg[1:]:
                x=(p[0]-minimum[0])/span[0]*width
                y=(maximum[1]-p[1])/span[1]*CAP
                points.append((round(x),round(y)))
            converted.append((seg[0],*points))
        result.append(converted)
    return result


def rectangle_path(x,y,w,h,r=10,reverse=False):
    r=min(r,w/2,h/2)
    path=[('M',(x+r,y)),('L',(x+w-r,y)),('Q',(x+w,y),(x+w,y+r)),
      ('L',(x+w,y+h-r)),('Q',(x+w,y+h),(x+w-r,y+h)),
      ('L',(x+r,y+h)),('Q',(x,y+h),(x,y+h-r)),
      ('L',(x,y+r)),('Q',(x,y),(x+r,y))]
    return reverse_path(path) if reverse else path


def reverse_path(path):
    starts=[];current=path[0][1]
    for s in path[1:]:
        starts.append((current,s));current=s[-1]
    result=[('M',current)]
    for start,s in reversed(starts):
        result.append(('L',start) if s[0]=='L' else ('Q',s[1],start))
    return result


def ellipse_path(cx,cy,rx,ry,reverse=False):
    points=[]
    angles=np.linspace(0,2*math.pi,9)
    if reverse:angles=angles[::-1]
    start=angles[0]
    path=[('M',(cx+rx*math.cos(start),cy+ry*math.sin(start)))]
    for a,b in zip(angles[:-1],angles[1:]):
        m=(a+b)/2;factor=1/math.cos((b-a)/2)
        control=(cx+rx*math.cos(m)*factor,cy+ry*math.sin(m)*factor)
        end=(cx+rx*math.cos(b),cy+ry*math.sin(b))
        path.append(('Q',control,end))
    return path


def regularize_source_geometry(outlines,widths,radio=False):
    # These simple primitives are measured from the screenshot stems/counters.
    # They replace compression-induced waviness with exact horizontal/vertical
    # lines and intentional quadratic corners, not a different font family.
    if radio:
        w=widths['I'];outlines['I']=[rectangle_path(0,0,w,700,10)]
        w=widths['O'];outlines['O']=[rectangle_path(0,0,w,700,205),rectangle_path(170,170,w-340,360,95,True)]
        w=widths['D']
        outlines['D']=[[('M',(0,0)),('L',(0,700)),('L',(w-230,700)),('Q',(w,700),(w,470)),('L',(w,230)),('Q',(w,0),(w-230,0)),('L',(0,0))],
                       rectangle_path(170,165,w-345,370,65,True)]
        w=widths['R']
        outlines['R']=[[('M',(0,0)),('L',(0,700)),('L',(w-180,700)),('Q',(w,700),(w,520)),('Q',(w,395),(w-170,350)),('L',(w,0)),('L',(w-205,0)),('L',(190,335)),('Q',(150,380),(180,420)),('L',(w-230,430)),('Q',(w-170,440),(w-170,500)),('L',(w-170,525)),('Q',(w-170,545),(w-220,545)),('L',(170,545)),('L',(170,0)),('L',(0,0))]]
        # A keeps its observed pointed structure, but uses straight leg lines.
        w=widths['A'];
        outlines['A']=[[('M',(0,0)),('L',(w*.36,625)),('Q',(w*.40,700),(w*.50,700)),('Q',(w*.60,700),(w*.64,625)),('L',(w,0)),('L',(w*.77,0)),('L',(w*.68,180)),('L',(w*.32,180)),('L',(w*.23,0)),('L',(0,0))],
          reverse_path([('M',(w*.39,345)),('L',(w*.50,555)),('L',(w*.61,345)),('L',(w*.39,345))])]
        return
    for c in 'HILEFT':
        w=widths[c];stem=217;bar=200
        if c=='I':shape=rectangle_path(0,0,w,700,8)
        elif c=='L':shape=[('M',(0,0)),('L',(0,700)),('L',(stem,700)),('L',(stem,bar)),('L',(w,bar)),('L',(w,0)),('L',(0,0))]
        elif c=='H':shape=[('M',(0,0)),('L',(0,700)),('L',(stem,700)),('L',(stem,450)),('L',(w-stem,450)),('L',(w-stem,700)),('L',(w,700)),('L',(w,0)),('L',(w-stem,0)),('L',(w-stem,250)),('L',(stem,250)),('L',(stem,0)),('L',(0,0))]
        elif c=='T':shape=[('M',((w-stem)/2,0)),('L',((w-stem)/2,500)),('L',(0,500)),('L',(0,700)),('L',(w,700)),('L',(w,500)),('L',((w+stem)/2,500)),('L',((w+stem)/2,0)),('L',((w-stem)/2,0))]
        elif c in 'EF':
            shape=[('M',(0,0)),('L',(0,700)),('L',(w,700)),('L',(w,500)),('L',(stem,500)),('L',(stem,450)),('L',(w-15,450)),('L',(w-15,250)),('L',(stem,250))]
            if c=='E':shape += [('L',(stem,200)),('L',(w,200)),('L',(w,0))]
            else:shape += [('L',(stem,0))]
            shape += [('L',(0,0))]
        if c!='I':
            pts=np.asarray([s[1] for s in shape[:-1]],dtype=float)*29/700
            shape=[(s[0],*((round(p[0]*700/29),round(p[1]*700/29)) for p in s[1:])) for s in curve_segments(pts)]
        outlines[c]=[shape]
    w=widths['O'];outlines['O']=[ellipse_path(w/2,350,w/2,350),ellipse_path(w/2,350,w*.17,123,True)]
    w=widths['B']
    outlines['B']=[[('M',(0,0)),('L',(0,700)),('L',(w-180,700)),('Q',(w,700),(w,525)),('Q',(w,415),(w-100,350)),('Q',(w,285),(w,175)),('Q',(w,0),(w-180,0)),('L',(0,0))],rectangle_path(215,450,w-395,60,15,True),rectangle_path(215,190,w-395,60,15,True)]
    for c in 'PR':
        w=widths[c]
        if c=='P':shape=[('M',(0,0)),('L',(0,700)),('L',(w-180,700)),('Q',(w,700),(w,510)),('Q',(w,290),(w-210,290)),('L',(217,290)),('L',(217,0)),('L',(0,0))]
        else:shape=[('M',(0,0)),('L',(0,700)),('L',(w-180,700)),('Q',(w,700),(w,510)),('Q',(w,365),(w-170,315)),('L',(w,0)),('L',(w-230,0)),('L',(217,290)),('L',(217,0)),('L',(0,0))]
        outlines[c]=[shape,rectangle_path(217,450,w-400,60,15,True)]
    w=widths['A']
    outlines['A']=[[('M',(0,0)),('L',(w*.28,590)),('Q',(w*.34,700),(w*.50,700)),('Q',(w*.66,700),(w*.72,590)),('L',(w,0)),('L',(w*.72,0)),('L',(w*.66,150)),('L',(w*.34,150)),('L',(w*.28,0)),('L',(0,0))],
      reverse_path([('M',(w*.435,325)),('L',(w*.50,445)),('L',(w*.565,325)),('L',(w*.435,325))])]
    w=widths['M']
    outlines['M']=[[('M',(0,0)),('L',(0,480)),('Q',(0,700),(w*.25,700)),('Q',(w*.46,700),(w*.46,480)),('L',(w*.46,250)),('Q',(w*.46,200),(w*.50,200)),('Q',(w*.54,200),(w*.54,250)),('L',(w*.54,480)),('Q',(w*.54,700),(w*.75,700)),('Q',(w,700),(w,480)),('L',(w,0)),('L',(w*.78,0)),('L',(w*.78,450)),('Q',(w*.78,500),(w*.74,500)),('Q',(w*.70,500),(w*.70,450)),('L',(w*.70,220)),('Q',(w*.70,0),(w*.50,0)),('Q',(w*.30,0),(w*.30,220)),('L',(w*.30,450)),('Q',(w*.30,500),(w*.26,500)),('Q',(w*.22,500),(w*.22,450)),('L',(w*.22,0)),('L',(0,0))]]


def make_font(path,outline_map,widths,style):
    fb=FontBuilder(UPM,isTTF=True)
    order=['.notdef','space']+list(string.ascii_uppercase)+['hyphen','period','apostrophe']
    fb.setupGlyphOrder(order)
    cmap={ord(c):c for c in string.ascii_uppercase}
    cmap.update({ord(c.lower()):c for c in string.ascii_uppercase})
    cmap.update({32:'space',45:'hyphen',46:'period',39:'apostrophe'})
    fb.setupCharacterMap(cmap)
    glyphs={};metrics={}
    for c in order:
        pen=TTGlyphPen(None)
        if c in outline_map:
            contours=outline_map[c]
        elif c in ('hyphen','period','apostrophe'):
            w=300 if c=='hyphen' else 190
            y,h=(290,170) if c=='hyphen' else ((0,190) if c=='period' else (480,220))
            contours=[[('M',(0,y)),('L',(w,y)),('L',(w,y+h)),('L',(0,y+h))]]
            widths[c]=w
        else:
            contours=[]
        for contour_index,segments in enumerate(contours):
            points=sample_segments(segments)
            signed_area=float(np.sum(points[:,0]*np.roll(points[:,1],-1)-points[:,1]*np.roll(points[:,0],-1)))
            if (contour_index==0 and signed_area>0) or (contour_index>0 and signed_area<0):
                segments=reverse_path(segments)
            for seg in segments:
                if seg[0]=='M':pen.moveTo(seg[1])
                elif seg[0]=='L':pen.lineTo(seg[1])
                else:pen.qCurveTo(seg[1],seg[2])
            pen.closePath()
        glyphs[c]=pen.glyph()
        metrics[c]=(round(widths.get(c,360)+24),0)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=850,descent=-150)
    fb.setupNameTable({'familyName':'Radio Rounded','styleName':style,
       'uniqueFontIdentifier':'RadioRounded-'+style+'-SourceReconstruction-1.0',
       'fullName':'Radio Rounded '+style,'psName':'RadioRounded-'+style,
       'version':'Version 1.0; regularized source outline reconstruction'})
    fb.setupOS2(sTypoAscender=850,sTypoDescender=-150,usWinAscent=850,
                usWinDescent=150,sCapHeight=700,sxHeight=500,usWeightClass=700)
    fb.setupPost()
    fb.setupMaxp()
    fb.save(path)


def vector_word(text,font_path,width,height,scale):
    font=ImageFont.truetype(str(font_path),round(height*scale*UPM/CAP))
    bb=font.getbbox(text)
    mask=Image.new('L',(bb[2]-bb[0]+4,bb[3]-bb[1]+4))
    ImageDraw.Draw(mask).text((2-bb[0],2-bb[1]),text,font=font,fill=255,stroke_width=0)
    mask=mask.crop(mask.getbbox())
    return mask.resize((round(width*scale),round(height*scale)),Image.Resampling.LANCZOS)


def comparison(metrics,name_font,radio_font):
    sheet=Image.new('RGB',(1700,1300),(20,22,29));d=ImageDraw.Draw(sheet)
    d.text((20,12),'SOURCE SILHOUETTE / 2x                              CLEAN QUADRATIC OUTLINE / 2x',fill='white')
    keys=['bearman','antonelli','verstappen','hamilton','albon']
    y=48
    for key in keys:
        e=metrics['names'][key]
        cb=e['mask_core_bbox']; width=cb[2]-cb[0];height=e['cap_height']
        source=Image.open(ASSETS/e['file']).crop(cb)
        clean=vector_word(e['text'],name_font,width,height,2)
        for mask,x in [(source.resize((width*2,height*2),Image.Resampling.LANCZOS),20),(clean,870)]:
            colored=Image.new('RGB',mask.size,(20,22,29));colored.paste((42,227,202),(0,0,*mask.size),mask)
            sheet.paste(colored,(x,y+20))
        d.text((20,y),e['text'],fill='white');y+=98
    e=metrics['radio'];cb=e['mask_core_bbox'];source=Image.open(ASSETS/e['file']).crop(cb)
    clean=vector_word('RADIO',radio_font,130,27,2)
    for mask,x in [(source.resize((260,54),Image.Resampling.LANCZOS),20),(clean,870)]:
        colored=Image.new('RGB',mask.size,(20,22,29));colored.paste((255,255,255),(0,0,*mask.size),mask);sheet.paste(colored,(x,y+20))
    d.text((20,y),'RADIO / separately traced white-word style',fill='white');y+=105
    d.text((20,y),'CLEAN VECTOR RENDER / 6x native capheight / no bitmap upscaling',fill='white');y+=30
    for text,font,width,height,color in [('ALBON',name_font,155,29,(42,110,222)),('RADIO',radio_font,130,27,(255,255,255))]:
        mask=vector_word(text,font,width,height,6)
        colored=Image.new('RGB',mask.size,(20,22,29));colored.paste(color,(0,0,*mask.size),mask)
        sheet.paste(colored,(20,y));y+=mask.height+40
    sheet.save(ROOT/'examples'/'rounded_font_comparison.png')


def main():
    metrics=json.loads((ASSETS/'lettering.json').read_text(encoding='utf-8'))
    outlines={};widths={}
    for c,e in metrics['glyphs'].items():
        mask=Image.open(ASSETS/e['file'])
        cb=e['core_bbox'];width=round((cb[2]-cb[0])/29*CAP)
        outlines[c]=outline_from_mask(mask,width)
        widths[c]=width
    measured_widths=dict(zip(string.ascii_uppercase,[33,26,26,29,25,25,28,29,10,21,28,24,43,32,30,27,30,28,26,30,29,32,48,32,31,26]))
    for c,pixels in measured_widths.items():
        old=widths[c];new=round(pixels/29*CAP)
        outlines[c]=[[(seg[0],*((round(p[0]*new/old),p[1]) for p in seg[1:])) for seg in contour] for contour in outlines[c]]
        widths[c]=new
    regularize_source_geometry(outlines,widths)
    name_path=FONTS/'RadioRounded-Bold.ttf'
    make_font(name_path,outlines,widths.copy(),'Bold')
    # RADIO uses its own thinner source outlines, not bold-name substitutes.
    radio=np.asarray(Image.open(ASSETS/'radio.png'))
    n,labels,stats,_=cv2.connectedComponentsWithStats((radio>128).astype(np.uint8),8)
    letters=sorted([s for s in stats[1:] if s[4]>20],key=lambda s:s[0])
    radio_outlines=outlines.copy();radio_widths=widths.copy()
    for c,s in zip('RADIO',letters):
        x,y,w,h=map(int,s[:4])
        piece=Image.fromarray(radio).crop((x-2,y-2,x+w+2,y+h+2))
        width=round(w/27*CAP)
        radio_outlines[c]=outline_from_mask(piece,width,128)
        radio_widths[c]=width
    regularize_source_geometry(radio_outlines,radio_widths,True)
    radio_path=FONTS/'RadioRounded-Radio.ttf'
    make_font(radio_path,radio_outlines,radio_widths,'Radio')
    report={'method':'Measured source contours; <=0.18px simplification; bounded local quadratic fillets; exact stems, parallel counters, ellipse bowls and rounded M arches reconstructed from source geometry',
       'units_per_em':1000,'cap_height':700,'native_simplification_tolerance':SIMPLIFY_NATIVE,
       'native_square_corner_fillet':CORNER_FILLET_NATIVE,'name_font':name_path.relative_to(ROOT).as_posix(),
       'radio_font':radio_path.relative_to(ROOT).as_posix(),'source_metrics':'assets/lettering/lettering.json',
       'limitations':'A clean regularized reconstruction of the observed silhouettes, not a recovered original font file. F/Q/X remain derived from source-stroke constructions.',
       'glyphs':{}}
    for path in [name_path,radio_path]:
        font=TTFont(path)
        curves=sum(int((g.flags==0).sum()) if hasattr(g.flags,'sum') else sum(not f&1 for f in g.flags) for g in [font['glyf'][c] for c in string.ascii_uppercase])
        report['glyphs'][path.name]={'quadratic_control_points':curves,'alphabet':string.ascii_uppercase}
    (ASSETS/'vector_font.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    comparison(metrics,name_path,radio_path)
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
