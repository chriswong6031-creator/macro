# B2-01 label_map_audit.py — mutation proof
Mutation target: the map selected-object dt (site 5) — the ONLY byte-unique occurrence of `L('Strength','强度')` immediately followed by `</dt><dd class="tnum">'+d.score+'</dd>'` in the built candidate. Applied to an in-memory COPY inside a throwaway temp directory; the real proposal file is never touched.
**Pristine baseline green:** YES (0 failing assertions)
**Mutation produced a unique red naming only site5:** YES

## Mutated-copy failing assertions
- [en] site5 map-selected-dt: got 'Score', want 'Strength'
- [zh] site5 map-selected-dt: got '评分', want '强度'
