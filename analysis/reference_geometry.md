# Reference geometry measured from original pixels

Measured from all 22 original screenshots and the original 476 × 296, 30 fps recording. No renderer edits are part of this analysis. Rectangles use half-open **[left, top, right, bottom]** pixel coordinates.

## Panel crop and aspect

All screenshot panels consistently span **329 × 176 source pixels**, with approximately ±1 pixel edge uncertainty from resampling. Aspect **1.869318**, near 15:8; it is visibly wider than 16:9. This is the sampled panel aspect; the original production resolution cannot be recovered from these screenshots. The surrounding game scene is excluded. All 22 source crop rectangles are in [reference_geometry.json](reference_geometry.json).

For requested 960 × 540 coordinates: x′=(x−left)×960/329; y′=(y−top)×540/176. This deliberately uses different x/y scales and does not imply a native 16:9 panel. Preserve 329:176 when displaying an undistorted panel.

## Source component bounds

Name/RADIO/logo bounds are visible ink cores from thresholded color or luminance within manually isolated ROIs. ±1 source pixel normally covers edge ambiguity. Numeral bounds include the pale edge where visible and are manually isolated from the waveform: ±2 pixels. The parent numeral and lettering analyses may refine outline-specific geometry.

| Reference | Panel crop | Name ink | RADIO ink | Numeral ink | Logo ink |
|---|---|---|---|---|---|
| SAINZ | 19, 9, 348, 185 | 200, 20, 337, 51 | 206, 53, 336, 81 | 30, 85, 164, 174 | 286, 145, 335, 173 |
| HADJAR | 13, 15, 342, 191 | 148, 26, 331, 56 | 200, 59, 330, 87 | 25, 91, 88, 180 | 260, 152, 329, 179 |
| BEARMAN | 10, 15, 339, 191 | 92, 27, 327, 56 | 197, 59, 327, 87 | 22, 91, 154, 180 | 273, 130, 328, 179 |
| BOTTAS | 10, 12, 339, 188 | 147, 24, 327, 53 | 197, 56, 327, 84 | 22, 88, 154, 177 | 264, 151, 327, 175 |

## Requested 960 × 540 rescale

Coordinates below have two decimals only to make the transform reproducible; they are not subpixel measurement claims. A ±1 source pixel error becomes ±2.92 horizontal / ±3.07 vertical rescaled pixels.

| Reference | Name ink | RADIO ink | Numeral ink | Logo ink |
|---|---|---|---|---|
| SAINZ | 528.15, 33.75, 927.9, 128.86 | 545.65, 135, 924.98, 220.91 | 32.1, 233.18, 423.1, 506.25 | 779.09, 417.27, 922.07, 503.18 |
| HADJAR | 393.92, 33.75, 927.9, 125.8 | 545.65, 135, 924.98, 220.91 | 35.02, 233.18, 218.84, 506.25 | 720.73, 420.34, 922.07, 503.18 |
| BEARMAN | 239.27, 36.82, 924.98, 125.8 | 545.65, 135, 924.98, 220.91 | 35.02, 233.18, 420.18, 506.25 | 767.42, 352.84, 927.9, 503.18 |
| BOTTAS | 399.76, 36.82, 924.98, 125.8 | 545.65, 135, 924.98, 220.91 | 35.02, 233.18, 420.18, 506.25 | 741.16, 426.48, 924.98, 500.11 |

Repeated RADIO local core is approximately [187,44,317,72], height28; name caps generally local top12, bottom41, height29. SAINZ/HADJAR colored low-contrast fringes extend the thresholded name box by ~1px. Screenshot distortion/compression can alter the outer threshold box.

## Additional team logos

High contrast core source boxes: Mercedes 175245 [284,130,333,179] (49×49); Ferrari 175513 [291,131,327,178] (36×47); Aston 174845 [262,162,333,177] and 175712 [257,156,328,171] (71×15). An antialias fringe can extend roughly 1px. Williams 175106 core49×28; Red Bull 174758 core69×27; Haas red 174857 55×49 including visible red blur; Cadillac 180835 core63×24. These are measured ink bounds, not equal-sized asset containers.

## Nine contiguous wave regions

The explicit nine-region requirement yields boundaries local **0,36.56,73.11,109.67,146.22,182.78,219.33,255.89,292.44,329**. The 960-space boundaries are 0,106.67,213.33,320,426.67,533.33,640,746.67,853.33,960. Adjacent regions share their boundary; there are no geometric gaps and the domain continues under both number and logo. Visible steps corroborate x≈86/123/159/196 in HADJAR and x≈156/193/230/266 in BEARMAN. Several transitions disappear when adjacent blocks have similar heights. Hidden boundaries are an equal-width partition constraint, not independent pixel observations.

Wave baseline is the panel bottom (source y185,191,191,188 respectively; ±1px). The source screenshots contain a soft top transition, so a single exact topmost pixel is not an exact latent block height. The JSON records **visible transition ranges** and corresponding height ranges for every observable region. Null means the numeral hides the contour; no value was invented. Under-logo blocks have a visible continuous low floor below the logo.

| Reference | Observable source top transition ranges, regions 1→9 |
|---|---|
| SAINZ | hidden; hidden; hidden; hidden; 166–172; 177–181; 178–182; 177–181; 178–182 |
| HADJAR | hidden; hidden; 164–172; 154–162; 154–164; 183–188; 181–187; 183–188; 180–187 |
| BEARMAN | hidden; hidden; hidden; hidden; 177–185; 178–185; 185–191; 181–188; 181–188 |
| BOTTAS | hidden; hidden; hidden; hidden; 124–160; 144–164; 174–182; 180–187; 181–188 |

Recording frame66 (2.2s): baseline y220; video region boundaries x117,153.67,190.33,227,263.67,300.33,337,373.67,410.33,447. Regions1–4 hidden; visible top ranges regions5–9 approximately159–172,175–185,207–215,210–217,211–218. Video uses its330px sampled width for the 960 transform; normalized polygon points and wave height ranges are included in JSON.

BOTTAS region5 has a long soft/fine-textured rise (y124–160), so the screenshot does not uniquely identify a single hard block top. Fine vertical intensity variation is visible inside the continuous envelope; it does not establish additional separated histogram regions.

## Dark diagonal background

The same broad rising-right diagonal bands occur at aligned panel-local coordinates across teams. Local(180,90) is [35,34,46] SAINZ, [34,33,44] HADJAR, [34,33,42] BEARMAN, [34,33,44] BOTTAS; the common dark area local(230,110) is [22,21,33], [22,21,33], [22,21,30], [22,21,30]. Other samples and exact locations are recorded in JSON. Those correspondences support a shared background texture. They do not identify a mathematical sinusoid, native alpha value, or exact precompression color. Scene influence, compression and antialiasing account for some small differences; avoid treating one screenshot RGB sample as a universal flat fill.

## Recording entrance

Full panel is approximately source [117,44,447,220], ±1px; the sampled video can give a 330px outer extent because of antialias coverage. A faint diagonal line already exists at frame0 through about0.9s. Clear active growth starts around1.0s, and the full rectangle emerges around1.93–2.0s. At30fps timing uncertainty is at least33ms, with repeated encoded frames at several points.

The clipping edges rise right at **−45°±1° in source pixels**. At1.2s, measured polygon vertices are approximately (333,45),(360,45),(199,208),(171,208), giving x+y≈378 and405. Their midline x+y≈392 is ~22px left of the final panel center x+y≈414. At1.4s top spans x304–398,y44; at1.5s top spans x263–440,y44. These points have ±2–3px manual edge uncertainty.

Observed phases: thin strip1.0–1.2s; broadening clipped content1.2–1.5s; near rectangle with relaxing top-left/lower-right corners1.5–1.93s. A ~20px lower-right corner cut persists at1.8s and ~10px at1.9s. Name position also settles: left≈207 at1.6s versus201 at2.2s. Therefore a stationary center clip alone does not fully describe the observed entrance. Easing functions or an exact mathematical clip center cannot be uniquely inferred from these compressed frames.

Evidence: original-pixel annotated grids [SAINZ](geometry_grid_sainz.png), [HADJAR](geometry_grid_hadjar.png), [BEARMAN](geometry_grid_bearman.png), [BOTTAS](geometry_grid_bottas.png); [recording overview](geometry_video_overview.png); exact frames [1.2s](geometry_frame_036.png), [1.4s](geometry_frame_042.png), [1.5s](geometry_frame_045.png), [1.6s](geometry_frame_048.png), [1.8s](geometry_frame_054.png), [1.9s](geometry_frame_057.png), [1.933s](geometry_frame_058.png), [2.2s](geometry_frame_066.png).
