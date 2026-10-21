"""Extract the ONE shared numeral alphabet directly from original screenshot pixels.

Run: python tools/extract_numerals.py
No fonts, manually traced polygons, or redesigned numeral contours are used.
The unavailable 9 is the 180-degree rotation of the extracted 6.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from collections import deque
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets' / 'numerals'
# Half-open extraction windows; include the native antialias fringe, exclude
# adjacent digits and the waveform below the baseline. Measured on originals.
SOURCES = {
    '0': ('175609', 'GASLY', (97, 93, 163, 184)),
    '1': ('175229', 'NORRIS', (21, 90, 86, 180)),
    '2': ('181507', 'TSUNODA', (15, 82, 82, 173)),
    '3': ('175209', 'VERSTAPPEN', (21, 85, 87, 176)),
    '4': ('175513', 'HAMILTON', (20, 90, 87, 180)),
    '5': ('175106', 'SAINZ', (29, 84, 96, 175)),
    '6': ('174758', 'HADJAR', (23, 90, 90, 181)),
    '7': ('180835', 'BOTTAS', (20, 86, 87, 179)),
    '8': ('175903', 'PIASTRI', (26, 90, 93, 182)),
}


def source_path(stamp):
    return next((ROOT / 'resource').glob('*' + stamp + '.png'))


def plane_fit(rgb, selected, xx, yy):
    design = np.stack([np.ones_like(xx), xx, yy], axis=-1)
    fit = np.linalg.lstsq(design[selected], rgb[selected], rcond=None)[0]
    return design @ fit


def largest_component(mask):
    visited = np.zeros_like(mask, dtype=bool)
    best = []
    h, w = mask.shape
    for y, x in np.argwhere(mask):
        if visited[y, x]:
            continue
        queue = deque([(int(y), int(x))]); visited[y, x] = True
        component = []
        while queue:
            py, px = queue.popleft(); component.append((py, px))
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = py + dy, px + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
                    visited[ny, nx] = True; queue.append((ny, nx))
        if len(component) > len(best):
            best = component
    out = np.zeros_like(mask, dtype=bool)
    for y, x in best:
        out[y, x] = True
    return out


def extract(rgb, neutral=False):
    a = np.asarray(rgb, dtype=float)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[-1:1:complex(h), -1:1:complex(w)]
    chroma = np.ptp(a, axis=2)
    value = a.max(axis=2)
    if neutral:
        candidates = (value > 130) & (chroma < 24)
    else:
        candidates = (chroma > 65) & (value > 100)
    foreground_seed = np.median(a[candidates], axis=0)
    distance = np.linalg.norm(a - foreground_seed, axis=2)
    interior = candidates & (distance < 32)
    foreground = plane_fit(a, interior, xx, yy)
    background_pixels = (value < 62) & (chroma < 32)
    background = plane_fit(a, background_pixels, xx, yy)
    v = foreground - background
    if neutral:
        q = v
    else:
        # Remove the white-outline component before unmatting the accent.
        # P = B + alpha*(F-B) + outline*(white-B). q is orthogonal
        # to white-B, so a white edge cannot become an opaque accent pixel.
        white = 255 - background
        q = v - white * (np.sum(v * white, axis=2) / np.sum(white * white, axis=2))[..., None]
    raw = np.clip(np.sum((a - background) * q, axis=2) / np.sum(v * q, axis=2), 0, 1)
    # Estimate row-dependent background glow from pixels safely outside the
    # opaque numeral. This removes waves visible behind the 4 and 7 without
    # changing the source contour or treating those waves as accent coverage.
    exclude = largest_component(raw >= .80)
    for _ in range(3):
        p = np.pad(exclude, 1)
        exclude = np.logical_or.reduce([p[dy:dy+h, dx:dx+w] for dy in range(3) for dx in range(3)])
    residual = np.zeros((h, 3))
    for y in range(h):
        keep = ~exclude[y]
        if keep.sum() >= 6:
            residual[y] = np.median((a - background)[y, keep], axis=0)
    residual = np.stack([np.convolve(np.pad(residual[:, c], 2, mode='edge'), np.ones(5)/5, mode='valid') for c in range(3)], axis=-1)
    background = background + residual[:, None, :]
    v = foreground - background
    if neutral:
        q = v
    else:
        white = 255 - background
        q = v - white * (np.sum(v * white, axis=2) / np.sum(white * white, axis=2))[..., None]
    raw = np.clip(np.sum((a - background) * q, axis=2) / np.sum(v * q, axis=2), 0, 1)
    # The screenshot waveform is faintly the same hue as the numeral. Keep
    # the connected opaque glyph and its 2-pixel AA fringe, not remote waves.
    core = largest_component(raw >= .60)
    support = core.copy()
    for _ in range(2):
        p = np.pad(support, 1)
        support = np.logical_or.reduce([p[dy:dy+h, dx:dx+w] for dy in range(3) for dx in range(3)])
    alpha = np.where(support, raw, 0)
    # Suppress sub-3% color noise, preserving intermediate edge coverage.
    alpha[alpha < .03] = 0
    info = {
        'foreground_seed_rgb': foreground_seed.round(3).tolist(),
        'foreground_center_rgb': foreground[h//2, w//2].round(3).tolist(),
        'background_center_rgb': background[h//2, w//2].round(3).tolist(),
        'opaque_component_threshold': .60,
        'alpha_noise_floor': .03,
        'fringe_radius_px': 2,
        'dematting': 'luminance' if neutral else 'accent with white-outline projection removed',
    }
    return alpha, info, foreground, background


def level_bbox(alpha, level):
    yy, xx = np.where(alpha >= level)
    return [int(xx.min()), int(yy.min()), int(xx.max()) + 1, int(yy.max()) + 1]


def marching_contours(alpha, level=.5):
    """Subpixel marching squares with linear interpolation, not binary stairs."""
    field = np.pad(alpha, 1)
    segments = []
    h, w = field.shape
    for y in range(h-1):
        for x in range(w-1):
            values = [field[y,x], field[y,x+1], field[y+1,x+1], field[y+1,x]]
            points = [(x-.5,y-.5),(x+.5,y-.5),(x+.5,y+.5),(x-.5,y+.5)]
            crossed = []
            for edge in range(4):
                j = (edge+1)%4
                if (values[edge] >= level) != (values[j] >= level):
                    t = (level-values[edge])/(values[j]-values[edge])
                    p = tuple(round(points[edge][c]+t*(points[j][c]-points[edge][c]), 8) for c in range(2))
                    crossed.append((edge,p))
            if len(crossed) == 2:
                segments.append((crossed[0][1], crossed[1][1]))
            elif len(crossed) == 4:
                # Asymptotic center decision for the rare ambiguous cell.
                by_edge = dict(crossed)
                if (np.mean(values) >= level) == (values[0] >= level):
                    pairs = [(0,1),(2,3)]
                else:
                    pairs = [(0,3),(1,2)]
                segments.extend((by_edge[i],by_edge[j]) for i,j in pairs)
    adjacency = {}
    for i,(p,q) in enumerate(segments):
        adjacency.setdefault(p,[]).append((i,q)); adjacency.setdefault(q,[]).append((i,p))
    used = set(); loops = []
    for i,(p,q) in enumerate(segments):
        if i in used: continue
        used.add(i); loop = [p]; current = q
        while current != p:
            loop.append(current)
            choices = [(j,n) for j,n in adjacency[current] if j not in used]
            if not choices: raise ValueError('Open marching-square contour')
            j,current = choices[0]; used.add(j)
        loops.append(loop)
    return sorted(loops,key=lambda p:abs(sum(p[i][0]*p[(i+1)%len(p)][1]-p[(i+1)%len(p)][0]*p[i][1] for i in range(len(p)))),reverse=True)


def fit_source_straights(loop, tolerance=.70, minimum_length=3.4):
    """Recover angular source edges from blur, fitting ONLY measured samples.

    RDP groups contour samples, then total-least-squares fits the interior of
    each source segment. Short blur arcs are replaced by intersections of the
    neighboring measured straight lines. No angle/vertex coordinates are supplied.
    """
    points=np.asarray(loop,dtype=float)
    split=int(np.argmax(np.sum((points-points[0])**2,axis=1)))
    chain=np.vstack([points,points[:1]])
    def rdp(a,b):
        delta=chain[b]-chain[a]; length=np.linalg.norm(delta)
        if b-a<2 or length<1e-8: return [a,b]
        offsets=chain[a+1:b]-chain[a]
        d=np.abs(delta[0]*offsets[:,1]-delta[1]*offsets[:,0])/length
        idx=int(np.argmax(d))+a+1
        if d.max()<=tolerance: return [a,b]
        return rdp(a,idx)[:-1]+rdp(idx,b)
    breaks=rdp(0,split)[:-1]+rdp(split,len(points))
    simplified=[tuple(chain[k]) for k in breaks[:-1]]
    def measured_line(segment):
        center=segment.mean(axis=0)
        _,_,axes=np.linalg.svd(segment-center,full_matrices=False)
        direction=axes[0]
        angle=np.arctan2(direction[1],direction[0])
        snapped=round(angle/(np.pi/4))*(np.pi/4)
        if abs(angle-snapped)<=np.deg2rad(7.5):
            direction=np.array([np.cos(snapped),np.sin(snapped)])
        return center,direction
    groups=[]
    for a,b in zip(breaks[:-1],breaks[1:]):
        segment=chain[a:b+1]
        if np.linalg.norm(segment[-1]-segment[0])<minimum_length: continue
        # Edge interiors contain no rounded corner transition.
        if len(segment)>6: segment=segment[1:-1]
        groups.append(segment)
    # Merge same-line fragments, including the cyclic first/last edge, using
    # both measured direction agreement and subpixel normal displacement.
    changed=True
    while changed and len(groups)>3:
        changed=False
        for i in range(len(groups)):
            j=(i+1)%len(groups)
            p,u=measured_line(groups[i]); q,v=measured_line(groups[j])
            normal=np.array([-u[1],u[0]])
            if abs(np.dot(u,v))>=np.cos(np.deg2rad(5)) and abs(np.dot(q-p,normal))<=.8:
                joined=np.vstack([groups[i],groups[j]])
                if j==0:
                    groups=[joined]+groups[1:i]
                else:
                    groups[i]=joined; del groups[j]
                changed=True; break
    lines=[measured_line(segment) for segment in groups]
    if len(lines)<3: return loop
    result=[]
    for i,(p,u) in enumerate(lines):
        q,v=lines[(i+1)%len(lines)]
        cross=u[0]*v[1]-u[1]*v[0]
        if abs(cross)<.08: continue
        offset=q-p
        distance=(offset[0]*v[1]-offset[1]*v[0])/cross
        intersection=p+distance*u
        # Refuse unsupported intersections far from any actual source edge.
        nearest=float(np.min(np.linalg.norm(points-intersection,axis=1)))
        if nearest>2.0: return simplified
        result.append(tuple(intersection))
    return result


def regularize_geometry(loops):
    """Restore clean dominant H/V/45 geometry without copying blur kinks."""
    grouped=[]
    for loop_index,loop in enumerate(loops):
        groups=[]
        for i,p in enumerate(loop):
            p=np.asarray(p); q=np.asarray(loop[(i+1)%len(loop)])
            delta=q-p; length=float(np.linalg.norm(delta))
            if length<(1.5 if loop_index else 4.0): continue
            orientation=int(round(np.arctan2(delta[1],delta[0])/(np.pi/4)))%4
            if not loop_index and orientation%2 and length<.1*np.ptp(np.asarray(loop)[:,1]) and min(p[1],q[1])>np.max(np.asarray(loop)[:,1])-.12*np.ptp(np.asarray(loop)[:,1]):
                continue
            theta=orientation*np.pi/4
            normal=np.array([-np.sin(theta),np.cos(theta)])
            groups.append({'orientation':orientation,'offset':float(np.dot((p+q)/2,normal)),'weight':length})
        changed=True
        while changed and len(groups)>3:
            changed=False
            for i,g in enumerate(groups):
                j=(i+1)%len(groups); other=groups[j]
                if g['orientation']==other['orientation']:
                    weight=g['weight']+other['weight']
                    merged={'orientation':g['orientation'],'offset':(g['offset']*g['weight']+other['offset']*other['weight'])/weight,'weight':weight}
                    if j==0: groups=[merged]+groups[1:i]
                    else: groups[i]=merged; del groups[j]
                    changed=True; break
        grouped.append(groups)
    # Repeated stems on the same source coordinate share a clean line.
    all_lines=[g for groups in grouped for g in groups]
    used=set()
    for i,g in enumerate(all_lines):
        if i in used: continue
        cluster=[(j,other) for j,other in enumerate(all_lines) if j not in used and other['orientation']==g['orientation'] and abs(other['offset']-g['offset'])<=.8]
        mean=sum(other['offset']*other['weight'] for _,other in cluster)/sum(other['weight'] for _,other in cluster)
        for j,other in cluster: other['offset']=mean; used.add(j)
    clean=[]
    for original,groups in zip(loops,grouped):
        polygon=[]
        for i,g in enumerate(groups):
            other=groups[(i+1)%len(groups)]
            theta=g['orientation']*np.pi/4; phi=other['orientation']*np.pi/4
            normals=np.array([[-np.sin(theta),np.cos(theta)],[-np.sin(phi),np.cos(phi)]])
            if abs(np.linalg.det(normals))<1e-6: continue
            polygon.append(tuple(np.linalg.solve(normals,np.array([g['offset'],other['offset']]))))
        clean.append(polygon if len(polygon)>=3 else original)
    return clean


def idealize_counters(digit, loops):
    """Restore symmetric source octagons and the source 4 triangular counter."""
    if digit not in ('4','6','8'): return loops
    result=[loops[0]]
    for loop in loops[1:]:
        points=np.asarray(loop); left,top=points.min(axis=0); right,bottom=points.max(axis=0)
        if digit=='4':
            leg=((right-left)+(bottom-top))/2
            result.append([(right,bottom-leg),(right,bottom),(right-leg,bottom)])
        else:
            chamfers=[]
            for i,p in enumerate(points):
                delta=points[(i+1)%len(points)]-p
                if abs(delta[0])>.5 and abs(delta[1])>.5:
                    chamfers.append((abs(delta[0])+abs(delta[1]))/2)
            chamfer=round(float(np.median(chamfers))*2)/2
            chamfer=min(chamfer,(right-left)/3,(bottom-top)/3)
            result.append([(left+chamfer,top),(right-chamfer,top),(right,top+chamfer),(right,bottom-chamfer),(right-chamfer,bottom),(left+chamfer,bottom),(left,bottom-chamfer),(left,top+chamfer)])
    return result


def restore_measured_chamfers(loops, raw_loops):
    # Preserve open-counter chamfers which short-edge blur filtering could
    # otherwise turn into square inner corners. Only original contour evidence
    # farther than 1.8px from the ideal intersection supports such a bevel.
    polygon=loops[0]; raw=np.asarray(raw_loops[0]); result=[]
    signed_area=sum(polygon[i][0]*polygon[(i+1)%len(polygon)][1]-polygon[(i+1)%len(polygon)][0]*polygon[i][1] for i in range(len(polygon)))
    for i,point in enumerate(polygon):
        p=np.asarray(point); before=np.asarray(polygon[i-1])-p; after=np.asarray(polygon[(i+1)%len(polygon)])-p
        axis_before=min(abs(before))<1e-6; axis_after=min(abs(after))<1e-6
        distance=float(np.min(np.linalg.norm(raw-p,axis=1)))
        if axis_before and axis_after and abs(np.dot(before,after))<1e-6 and distance>1.8 and (before[0]*after[1]-before[1]*after[0])*signed_area>0:
            cut=round(distance*np.sqrt(2)*2)/2
            cut=min(cut,np.linalg.norm(before)/3,np.linalg.norm(after)/3)
            result.extend([tuple(p+before/np.linalg.norm(before)*cut),tuple(p+after/np.linalg.norm(after)*cut)])
        else:
            result.append(tuple(p))
    return [result]+loops[1:]


def inside(point, polygon):
    x,y = point; hit = False
    for i,(ax,ay) in enumerate(polygon):
        bx,by = polygon[(i+1)%len(polygon)]
        if (ay>y) != (by>y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            hit = not hit
    return hit


def render_contours(loops, width, height, supersample=4):
    image = Image.new('L',(width*supersample,height*supersample))
    draw = ImageDraw.Draw(image)
    for i,loop in enumerate(loops):
        depth = sum(inside(loop[0],outer) for outer in loops[:i])
        draw.polygon([(x*height*supersample,y*height*supersample) for x,y in loop],fill=255 if depth%2==0 else 0)
    return image.resize((width,height),Image.Resampling.LANCZOS)


def comparison(rows, dest):
    # The same measured foreground plane colors both source-size previews.
    # No new outline is introduced: parent renderer owns the white hairline.
    font = ImageFont.truetype('C:/Windows/Fonts/consola.ttf', 13)
    canvas = Image.new('RGB', (1160, 80 + 440 * len(rows)), '#e8e8e8')
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 12), 'SOURCE PIXELS -> EXTRACTED SHARED FILL (no new white outline)', fill='black', font=font)
    draw.text((16, 36), 'Native source / fill composite; 400% source / fill composite. Screenshots remain untouched.', fill='black', font=font)
    for i, (digit, source, composite, alpha) in enumerate(rows):
        y = 80 + i * 440
        draw.text((12, y), digit, fill='black', font=font)
        draw.text((44, y + 18), 'source 1x', fill='black', font=font)
        draw.text((148, y + 18), 'fill 1x', fill='black', font=font)
        draw.text((272, y + 18), 'source 400%', fill='black', font=font)
        draw.text((570, y + 18), 'fill 400%', fill='black', font=font)
        draw.text((875, y + 18), 'alpha 400%', fill='black', font=font)
        canvas.paste(source, (44, y + 40)); canvas.paste(composite, (148, y + 40))
        for im, x in [(source, 272), (composite, 570), (alpha.convert('RGB'), 875)]:
            canvas.paste(im.resize((im.width * 4, im.height * 4), Image.Resampling.NEAREST), (x, y + 40))
    from io import BytesIO
    buffer = BytesIO(); canvas.save(buffer, format='PNG')
    dest.write_bytes(buffer.getvalue())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--height', type=int, default=704, help='shared PNG capheight, minimum 500')
    parser.add_argument('--comparison', default='analysis/numeral_comparison.png')
    args = parser.parse_args()
    if args.height < 500:
        parser.error('--height must be at least 500')
    OUT.mkdir(parents=True, exist_ok=True)
    metrics = {
        'schema_version': 1,
        'coordinate_convention': 'source boxes are half-open [left,top,right,bottom]; capheight is normalized to 1',
        'source_of_truth': 'original resource PNG RGB pixels; no font substitution or hand-designed contour',
        'reference_capheight': 88,
        'reference_gap': 7,
        'gap_per_height': 7 / 88,
        'output_capheight': args.height,
        'resampling': 'linear-interpolated marching squares at alpha .5; polygon rasterized at 4x target resolution and Lanczos antialias; native source alpha also retained',
        'white_outline': 'original pale outline removed by color projection where separable; renderer recreates hairline consistently',
        'digits': {},
    }
    rows = []; masks = {}; all_contours = {}
    native_out = OUT / 'source_alpha'; native_out.mkdir(exist_ok=True)
    for digit, (stamp, driver, box) in SOURCES.items():
        path = source_path(stamp)
        original = Image.open(path).convert('RGB').crop(box)
        alpha, info, fg, bg = extract(original, neutral=digit == '7')
        # Reject disconnected bright wave fragments before tracing. Source
        # alpha remains continuous; this only selects the one numeral.
        connected = largest_component(alpha >= .5)
        alpha[(alpha >= .5) & ~connected] = 0
        boundary = level_bbox(alpha, .50)
        loops = marching_contours(alpha)
        raw_loops = loops
        loops = idealize_counters(digit, regularize_geometry([fit_source_straights(loop, minimum_length=1.5 if i else 3.4) for i,loop in enumerate(loops)]))
        loops = restore_measured_chamfers(loops, raw_loops)
        info['contour_refinement'] = 'source-sample TLS fitting after .70px RDP grouping, then deblur dominant H/V/45 geometry, discard blur kinks below4px outer/1.5px counter, merge collinear fragments, align repeated stems within .8nativepx, restore symmetric measured octagonal counters6/8 and triangular4; no manually specified source vertices'
        info['raw_contour_points'] = [len(loop) for loop in raw_loops]
        info['fitted_contour_points'] = [len(loop) for loop in loops]
        points = np.array([p for loop in loops for p in loop])
        left, top = points.min(axis=0); right, bottom = points.max(axis=0)
        capheight = bottom-top; ratio = (right-left)/capheight
        normalized = [[[(x-left)/capheight,(y-top)/capheight] for x,y in loop] for loop in loops]
        all_contours[digit] = normalized
        width = round(args.height * ratio)
        image = render_contours(normalized, width, args.height)
        image.save(OUT / ('digit_' + digit + '.png'))
        source_alpha = Image.fromarray(np.rint(alpha * 255).astype('uint8'))
        source_alpha.save(native_out / ('digit_' + digit + '.png'))
        masks[digit] = image
        # Compare the FINAL high-resolution mask, placed back onto its exact
        # source coordinates at native scale, to the untouched source crop.
        # Render directly into the source window at 8x before reduction.
        high = Image.new('L',(original.width*8,original.height*8)); painter=ImageDraw.Draw(high)
        for i,loop in enumerate(loops):
            depth=sum(inside(loop[0],outer) for outer in loops[:i])
            painter.polygon([(x*8,y*8) for x,y in loop],fill=255 if depth%2==0 else 0)
        native_mask=high.resize(original.size,Image.Resampling.LANCZOS)
        raw_image=Image.new('L',high.size); raw_draw=ImageDraw.Draw(raw_image)
        for i,loop in enumerate(raw_loops):
            depth=sum(inside(loop[0],outer) for outer in raw_loops[:i])
            raw_draw.polygon([(x*8,y*8) for x,y in loop],fill=255 if depth%2==0 else 0)
        raw_pixels=np.asarray(raw_image)>127; fitted_pixels=np.asarray(high)>127
        info['native_source_boundary_iou_8x']=float(np.logical_and(raw_pixels,fitted_pixels).sum()/np.logical_or(raw_pixels,fitted_pixels).sum())
        smooth=np.asarray(native_mask,dtype=float)/255
        comp = np.clip(fg * smooth[..., None] + bg * (1 - smooth[..., None]), 0, 255).astype('uint8')
        rows.append((digit + ' ' + driver, original, Image.fromarray(comp), native_mask))
        source_box = [round(box[0]+left,6), round(box[1]+top,6), round(box[0]+right,6), round(box[1]+bottom,6)]
        metrics['digits'][digit] = {
            'source': path.relative_to(ROOT).as_posix(), 'driver': driver,
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'extraction_window': list(box), 'box': source_box,
            'native_width': round(float(right-left),6), 'native_capheight': round(float(capheight),6),
            'width_per_height': float(ratio),
            'contour_count': len(loops),
            'contour_level': .5,
            'source_alpha': 'assets/numerals/source_alpha/digit_' + digit + '.png',
            'output_size': [width, args.height],
            'alpha_50_bbox_in_window': boundary,
            'alpha_10_bbox_in_window': level_bbox(alpha, .10),
            **info,
        }
        print(digit, driver, source_box, image.size, json.dumps(info))
    # Derive the rounded common capheight/gap from actual repeated numerals.
    metrics['reference_capheight_measured_median']=float(np.median([v['native_capheight'] for v in metrics['digits'].values()]))
    metrics['reference_capheight']=round(metrics['reference_capheight_measured_median'])
    gap_checks=[('HAMILTON','175513',(90,90,156,180),'4'),('SAINZ','175106',(98,84,165,175),'5'),('BOTTAS','180835',(89,86,157,179),'7'),('TSUNODA','181507',(84,82,152,173),'2')]
    gaps=[]
    for name,stamp,second_box,digit in gap_checks:
        gap_alpha,_,_,_=extract(Image.open(source_path(stamp)).convert('RGB').crop(second_box),neutral=digit=='7')
        second_left=second_box[0]+min(p[0] for loop in marching_contours(gap_alpha) for p in loop)
        gap=float(second_left-metrics['digits'][digit]['box'][2])
        gaps.append({'driver':name,'source':source_path(stamp).relative_to(ROOT).as_posix(),'second_extraction_window':list(second_box),'gap_px':gap})
    metrics['reference_gap_measurements']=gaps
    metrics['reference_gap_measured_median']=float(np.median([v['gap_px'] for v in gaps]))
    metrics['reference_gap']=round(metrics['reference_gap_measured_median'])
    metrics['gap_per_height']=metrics['reference_gap']/metrics['reference_capheight']
    metrics['contour_interpretation']='half-coverage (.5) is the neutral fill/background boundary; .6 only identifies the connected glyph and is not a hard edge threshold. Bilinear marching interpolation preserves subpixel positions.'
    # Cross-check the SAME shared 6 against the independent RUSSELL source.
    validation_path=source_path('180209'); validation_box=(20,90,86,180)
    original=Image.open(validation_path).convert('RGB').crop(validation_box)
    va,vi,vfg,vbg=extract(original)
    vc=largest_component(va>=.5); va[(va>=.5)&~vc]=0
    vloops=marching_contours(va)
    vp=np.array([p for loop in vloops for p in loop])
    vl,vt=vp.min(axis=0); vr,vb=vp.max(axis=0)
    shared=[[(vl+x*(vr-vl)/metrics['digits']['6']['width_per_height'],vt+y*(vb-vt)) for x,y in loop] for loop in all_contours['6']]
    def window_mask(loops):
        im=Image.new('L',(original.width*8,original.height*8)); dr=ImageDraw.Draw(im)
        for i,loop in enumerate(loops):
            depth=sum(inside(loop[0],outer) for outer in loops[:i])
            dr.polygon([(x*8,y*8) for x,y in loop],fill=255 if depth%2==0 else 0)
        return im
    truth=window_mask(vloops); reused=window_mask(shared)
    ta=np.asarray(truth)>127; ra=np.asarray(reused)>127
    iou=float(np.logical_and(ta,ra).sum()/np.logical_or(ta,ra).sum())
    sm=reused.resize(original.size,Image.Resampling.LANCZOS); sa=np.asarray(sm,dtype=float)/255
    composite=Image.fromarray(np.clip(vfg*sa[...,None]+vbg*(1-sa[...,None]),0,255).astype('uint8'))
    validation_row=('6 RUSSELL shared HADJAR glyph',original,composite,sm)
    metrics['validation']={'shared_6_against_russell':{'source':validation_path.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(validation_path.read_bytes()).hexdigest(),'extraction_window':list(validation_box),'intersection_over_union_at_8x':iou,'alignment':'same shared HADJAR6 contours fitted only to independently measured RUSSELL6 capheight and width; no contour editing'}}
    comparison([rows[6],validation_row],OUT/'six_comparison.png')
    for start in (0,3,6):
        comparison(rows[start:start+3],OUT/('comparison_' + str(start) + '_' + str(start+2) + '.png'))
    rows.append(validation_row)
    masks['9'] = masks['6'].transpose(Image.Transpose.ROTATE_180)
    masks['9'].save(OUT / 'digit_9.png')
    sheet=Image.new('RGB',(2000,1200),'#15161f'); sheet_draw=ImageDraw.Draw(sheet)
    label_font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',28)
    for index in range(10):
        mask=masks[str(index)]; width=round(mask.width*500/mask.height)
        scaled=mask.resize((width,500),Image.Resampling.LANCZOS)
        x=(index%5)*400+(400-width)//2; y=(index//5)*600+65
        sheet_draw.text(((index%5)*400+20,(index//5)*600+15),str(index),font=label_font,fill='#eeeeee')
        sheet.paste(Image.new('RGB',scaled.size,'#4a7bc6'),(x,y),scaled)
    sheet.save(OUT/'alphabet.png')
    metrics['digits']['9'] = {
        **metrics['digits']['6'], 'derived_from': '6',
        'transform': 'rotate 180 degrees; no 9 exists in provided original source screenshots',
    }
    all_contours['9'] = [[[metrics['digits']['6']['width_per_height']-x, 1-y] for x,y in loop] for loop in all_contours['6']]
    hole_flags={d:[sum(inside(loop[0],outer) for outer in loops[:i])%2==1 for i,loop in enumerate(loops)] for d,loops in all_contours.items()}
    rounded={d:[[[round(float(x),6),round(float(y),6)] for x,y in loop] for loop in loops] for d,loops in all_contours.items()}
    contour_document={'schema_version':2,'units':'capheight=1; +x right; +y down; left/top ink bounds are zero','fill_rule':'evenodd','method':'source dematting and interpolated marching contours, TLS source-line fit, clean dominant H/V/45 geometry and parallel stem alignment; no hand-entered vertices','digits':rounded,'holes':hole_flags,'width_per_height':{d:v['width_per_height'] for d,v in metrics['digits'].items()}}
    (OUT / 'contours.json').write_text(json.dumps(contour_document, indent=2)+chr(10),encoding='utf-8')
    (OUT / 'metrics.json').write_text(json.dumps(metrics, indent=2) + chr(10), encoding='utf-8')
    comp_path = ROOT / args.comparison
    comp_path.parent.mkdir(parents=True, exist_ok=True)
    comparison(rows, comp_path)


if __name__ == '__main__':
    main()
