# C8-C visual receipts

Crops for the Design-System PR chartered by the R4 composition verdict
(`research/reference_integrity/prophet-board-5514-r4-composition/verdict.yml`,
condition `C8-C-DS-PR-LANE`). Every shot is the SHIPPED `templates/theme.css`
rendered against the real `pv_css()` block from `templates/_prophet_card.html.j2` —
no mock palette, no reference stylesheet.

| file | shows |
|---|---|
| `01-stance-dark-en.png` | DA-002 cure, dark EN. Top lane = `origin/main`: the BUY chip and the `+2.14%` change print one ink. Bottom lane = C8-C: stance sits a tone off the tape. |
| `02-stance-light-en.png` | Same, light EN — the thinnest quadrant (dE 5.6). |
| `03-stance-dark-zh.png` | Same, dark ZH. 红涨 preserved: Buy is still red, derived from the flipped `--up`. |
| `04-stance-light-zh.png` | Same, light ZH — the widest separation (dE 23.3). |
| `05-ladder-dark-en.png` | `.mx-ladder--board`: six live cells in one recessed band, per-cell weight caps, the terminal Resolved cell dashed and physically outside the live sum. |
| `06-ladder-light-zh.png` | The same ladder on the light plane in Chinese. The weight grammar is achromatic, so it is byte-identical under the direction flip. |
| `07-ladder-390-dark-en.png` | 390px: the 4+3 wrap keeps every count and the divider survives, so "Resolved sits outside the total" never rests on a caption alone. |
| `08-touch-390-before.png` | Touch floor before: the `?` has no extended target and the view toggle is 22px. |
| `09-touch-390-after.png` | Touch floor after: 40x40 hit boxes (dashed overlay) around the unchanged `?` and ⚠N glyphs; the segmented toggle gets real 40px height because its buttons are adjacent. |

The touch pair is labelled `coarse-pointer forced` on the page itself: the rules are
gated on `@media (pointer: coarse)` and the capture binary has no device emulation,
so the gate is restated unconditionally for those two frames only. Geometry measured
under real coarse-pointer emulation: `.lens-q` 19x19 visible / 40x40 target,
`.pv-cau-btn` 40x40 target, `.st-view-toggle button` 45.6x40.
