# Source-extracted shared numeral alphabet

Rebuild with `python tools/extract_numerals.py` (Python, NumPy, Pillow). The default output capheight is 704 px. All digit PNGs are grayscale L masks, white = foreground, black = transparent. Use each PNG as an alpha channel and recolor it. All drivers must use this same alphabet. White hairline belongs to the renderer.

The actual original screenshot PNG RGB pixels supply digits 0 through 8. The script records original SHA256 hashes, extraction windows, precise source boundary boxes, RGB samples, width/capheight ratios and independent validation in metrics.json. Coordinates are half-open, source-image pixel coordinates. Width/height ratios are normalized to capheight=1; never force every numeral to a common width. Source blur causes small variations in screenshot dimensions.

The absent 9 is EXACTLY digit_6 rotated 180 degrees, both in the PNG and in the normalized contours. It is derived, not claimed to be present in any screenshot.

## Dematting and contours

The extractor estimates the colored accent and dark background from actual interior pixels and removes the white outline component by RGB projection. The gray 7 uses luminance because its fill and white outline cannot be independently separated by color. A spatial background correction and connected-component support reject source waveform contamination. Alpha is continuous, with only values under 3% rejected as noise. Original-resolution dematted alpha is retained in source_alpha/ for audit or direct interpolation.

The authoritative normalized contours in contours.json begin with marching squares and subpixel linear interpolation of continuous alpha at 50% coverage. All digits 0 through 8 fit measured edge samples using total least squares after 0.70-native-pixel RDP grouping. The final geometry restores exact horizontal, vertical and 45-degree edges, merges collinear fragments, aligns repeated stems within 0.8 native pixels, and rejects blur kinks shorter than 4 native pixels on exteriors or 1.5 pixels on counters. The source 6 and 8 counters become symmetric octagons using measured width, height and median chamfer; the 4 counter becomes a clean 45-degree triangle using measured leg dimensions. The 4 lower stem has parallel vertical sides and a flat bottom. These geometric constraints restore the clean underlying numeral design instead of reproducing low-resolution screenshot blur. No source contour coordinates are manually supplied. Native source alpha, contour point counts, source hashes and footprint overlap measurements remain available for audit.

High-resolution PNGs rasterize those contours at 4x output resolution and reduce with Lanczos antialiasing. The native source capheight median rounds to 88 px. Measured repeated-digit gaps are in metrics.json; their median rounds to 7 px (gap/capheight = 7/88). The source outline is roughly 0.5–0.8 native px and is not baked into the color mask where separable.

## Vector schema

contours.json schema_version=2 keeps digits[digit] as an array of closed loops, each loop an array of [x,y] points. Units are capheight=1, +x right, +y down, with the left/top ink bounds at zero. holes[digit] provides a matching boolean per loop (false=fill, true=counter), and fill_rule is evenodd. width_per_height gives each glyph advance width before adding the measured gap. Coordinates are rounded to six decimal places. Draw these vectors directly at the desired size; the 704px grayscale PNGs are previews and alpha-mask alternatives. alphabet.png is a 2000x1200 contact sheet with all ten glyphs at the same capheight.

## Evidence

six_comparison.png shows the untouched HADJAR and RUSSELL source crops beside composites using the ONE shared HADJAR-derived 6, at native scale and 400%. analysis/numeral_comparison.png shows all original source digits and final-mask composites. The compact comparison_0_2.png, comparison_3_5.png and comparison_6_8.png pages show the same full-resolution evidence in smaller groups. Comparisons omit a new white hairline so the recovered accent contour can be judged directly. RUSSELL validates the shared shape; it does not supply a per-driver alternative glyph.

A lossless inverse of a blurred screenshot cannot recover an unknown original vector with mathematical certainty. The provided masks and contours are measured source reconstructions, with native dematted pixels retained so every contour decision is reviewable.
