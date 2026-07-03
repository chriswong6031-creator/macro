# W2-A Narrative Tags — Execution Report (2026-07-03)

*Executor: Sonnet 4.6. Wave: W2 of the China Alpha Program.*
*Deliverables: `engine/china_narrative_tags.py` + `tests/test_china_alpha_w2a.py`.*

---

## Status

SHIPPED. 39/39 tests pass. Both spec exemplars resolve correctly from live data.

---

## What was built

### `engine/china_narrative_tags.py`

Three public functions:

**`narrative_heat(closes, memberships_curated, memberships_ths, bench_series) -> dict`**

Computes per-basket heat records for all curated (22 baskets, `data/baskets_china/`) and THS
(237 baskets, `data/baskets_china_ths/`) baskets. Breadth is vectorised from the member closes
panel (pct above their own 20d MA at the last date). rel20 = basket EW 20d return minus CSI300
20d return, in pp. Returns `{basket_id: {level, rel20, breadth, source, n_members, n_covered}}`.

Live counts as of 2026-07-03: 259 baskets computed (22 curated + 237 THS), several skipped for
<3 covered members.

**`name_tags(heat, memberships_curated, memberships_ths, radar) -> dict`**

Per-ticker dict. For each ticker, finds the strongest qualifying theme (by rel20) it belongs to,
then attaches the `build_radar()` join if the ticker appears in any radar basket's `top_members`.
Returns `{ticker: {theme, level, rel20, breadth, source, basket_id, n_members, n_covered, radar}}`.

Live: 812 tickers tagged as of 2026-07-03.

**`ab_tier(stage, tag) -> "A" | "B" | None`**

Display + ledger only. A = stage in {ENTRY, RIPENING} AND (level=="HOT" OR radar honesty in
{validated, partial}). B = stage in {ENTRY, RIPENING} otherwise. RAN_LATE -> None. Rank influence
is NOT wired in W2 (masterplan F4 / F3 discipline: rank influence only after W6 grade calibration).

**`build_narrative_tags() -> dict`**

Convenience loader: loads all data sources, calls narrative_heat + name_tags + build_radar,
returns `{heat, tags, as_of, n_baskets, n_tagged, provenance}`. Safe for builder calls.

---

## Live values for spec exemplars

| Ticker | Basket | Name | Level | rel20 | Breadth | Source |
|--------|--------|------|-------|-------|---------|--------|
| 300725.SZ | ths_synbio | Synthetic Biology | HOT | +17.8pp | 87.5% | THS |
| 688306.SS | ths_solid_state | Solid-State Battery | HOT | +31.84pp | 81.8% | THS |

Both tickers are tagged HOT from their primary qualifying basket. 688306.SS is also in 15 other
THS baskets; solid-state battery carries the highest rel20 of its qualifying baskets (31.84pp vs
humanoid robots 15.08pp, etc.) so it wins the strongest-theme selection.

CSI300 (510300.SS) 20d return on 2026-07-03: -1.02pp. Basket raw 20d returns are therefore
higher than the absolute numbers suggest.

---

## Design decisions

**rel20 computed directly from member closes, not from the basket artifact perf field.**
The spec says "rel20 = 20d return vs CSI300 (exists in basket artifacts)" as the first option,
but the basket artifacts are only available when `compute_china_baskets()` and
`compute_china_ths_baskets()` run as part of a full render. The narrative_heat function is
designed to be callable independently (e.g., from the board builder without triggering a full
baskets render). Computing rel20 from the closes panel directly is the same math (`_perf` in
`engine/baskets.py` uses the same EW level approach) and is always available. This is not a
deviation — the spec's "exists in basket artifacts" is a data-availability note, not a mandate
to read the artifact file.

**Breadth = pct of covered members above their own 20d MA, not the basket EW 20d MA.**
Per-member breadth is the standard definition and matches the spec. The breadth window is 20
bars (not 21 — the 20d return uses the bar at position -21 as the base, but MA is computed over
the trailing 20 closes). This matches `pandas.rolling(20).mean()` semantics.

**strongest qualifying theme = highest rel20 among qualifying baskets.**
"Qualifying" means level is not None (HOT or WARMING). A basket with level=None does not compete
for the primary tag even if it has higher rel20 than qualifying baskets (which would be unusual
but possible if a high-rel20 basket has low breadth). If no basket qualifies, theme fields are
None and the ticker still appears in the tags dict only if it has a radar join.

**Radar join uses top_members list from build_radar(), not raw membership.**
`build_radar()` limits top_members to the top 8 by 63d return. A ticker in a radar basket but
outside its top-8 will not get the radar join from that basket. This is intentional — it mirrors
what the radar page displays and avoids silently attributing a basket's honesty tag to a member
that is not being featured by the radar.

---

## Spec compliance checklist

- [x] rel20 = 20d return vs CSI300 — computed and correct
- [x] breadth = pct of members above their 20d MA — computed per spec
- [x] HOT threshold: rel20 >= +5pp AND breadth >= 60% — tested at boundary
- [x] WARMING threshold: rel20 >= 0 AND breadth >= 50% — tested at boundary
- [x] Strongest qualifying theme by rel20 — correctly selects highest-rel20 qualifying basket
- [x] Radar join: basket_id, narr_rank, global_ai (state + honesty verbatim) — attached from build_radar()
- [x] Honesty tags preserved verbatim (validated/partial/2024+-only/weak) — unit tested
- [x] A-tier: HOT OR radar honesty in {validated, partial} — unit tested all cases
- [x] B-tier: ENTRY/RIPENING without A condition — unit tested
- [x] RAN_LATE -> no tier — unit tested
- [x] Graceful degradation: None closes -> empty dict; None memberships -> empty dict; None radar -> no crash — unit tested
- [x] Missing radar keys tolerated (missing rank_63d, missing global_ai) — unit tested
- [x] 300725.SZ -> Synthetic Biology tag, rel20 > 0 — live verified: +17.8pp HOT
- [x] 688306.SS -> Solid-State/robotics-family tag — live verified: Solid-State Battery +31.84pp HOT
- [x] Narrative is DESCRIPTIVE positioning lens, NOT validated alpha — stated in module docstring and provenance field
- [x] Rank influence NOT wired in W2 — ab_tier is display+ledger only; no _cn_bonus or blend changes

---

## Thresholds documentation (for W6 calibration)

HOT: rel20 >= +5pp AND breadth >= 60%
WARMING: rel20 >= 0pp AND breadth >= 50%

These are pre-registered display heuristics chosen to be directionally sensible
(breadth > 60% means a majority of names are actually participating; rel20 > 5pp
is a meaningful outperformance vs the index). They are NOT backtest-derived.
W6 will calibrate them from forward grades: if HOT-tagged ENTRY names do not
outperform untagged ENTRY names on 21d CSI300-relative excess, the thresholds
move or the tier collapses to a chip.

---

## Files changed

- `engine/china_narrative_tags.py` — new module (W2-A deliverable)
- `tests/test_china_alpha_w2a.py` — 39 unit tests (all synthetic except Section 5 live block)

No changes to: `_cn_bonus`, blend, board order, rank signals, or any W-tier/W1 machinery.
The law is honored: narrative never creates admission or rank in W2.
