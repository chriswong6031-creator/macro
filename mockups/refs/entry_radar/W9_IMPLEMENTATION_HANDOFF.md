# W9 implementation handoff — Live Entry Radar production UI

W8 stops here. W9 is a **separate commissioning**. Do not auto-roll.

Pinned Prophet Board at W8 start: merge `168a9be00691` / tree `d540f493a097`. Re-pin if that tree has moved.

---

## CAN COPY NOW

Approved visual / component / reference behaviour from `mockups/refs/entry_radar/`:

- Sister-language tokens, card geometry (12px / 74px / 232px min), density, chips, light-plane cards, zh direction flip, focus, reduced-motion
- Header + Probe Set headline + Radar lifecycle ladder (not Prophet's seven cells)
- Expert lane row including the disabled C4 context chip and **Best · unranked** (count dashed)
- Featured aura **= the Best-lane filter** (computed; the same set — not a silent 2-card glow)
- One card per `(ticker, expert)` — multi-expert tickers do not collapse
- Provisional vs confirmed vs nightly-confirmed freshness language
- Stale / unavailable / raw-basis / degraded demotion (no live-candidate look). Stale keeps its path.
- False-start history on the card, not only in a tooltip
- EN/ZH structural bilingualism
- Priority: **one board-level ACCRUING line**; card slot is an em-dash
- Opportunity drawer slot: `NOT YET MEASURED`
- Cards are **not links** (no `stock.html` — Prophet PRC-301 is not closed)
- Lifecycle hue is `--er-life`, never `--pv-buy` or `--ok`
- 390px is one column that **fits** — do not pin it with `overflow-x: hidden`
- RIG checks in `tools/verify.py` + `tests/test_entry_radar_w8_rig.py` as the production regression floor (adapt selectors, do not weaken)

Copy the **look and the information model**, not the synthetic payload.

**Do not copy the current card as contract §14 complete.** See BLOCKED_DATA below.

---

## NOT §14 COMPLETE — BLOCKED_DATA / ACCRUING

The W8 card is a founding subset. Contract §14 glance anatomy and drawer order are **not** shipped here. W9 must reserve the missing slots as `ACCRUING` or `UNAVAILABLE`. Treating their absence as permission to ship a smaller card is how a contract page is laundered.

Glance slots still BLOCKED_DATA (W4 fields):

- Component states: 1D Stoch / MACD-RSI / Structure / Lobe evidence
- Zone + invalidation on the glance footer (invalidation is drawer-only in this reference)

Drawer slots still ACCRUING / UNAVAILABLE (W4 fields):

- why-now
- what is recovering
- still structurally strong
- risk geometry / asymmetry
- what else sees it (lobes)
- trustworthiness / sample
- fire-path mini chart (arm / trough / turn / promotion)

Recorded Terminal families from §18 A1 (amber EARLY, STARTER pending/failed, RE-ENTRY reclaim/repair) are **not** Intelligence synonyms when they appear. Do not flatten them into C5.

---

## WAIT FOR W4

Do not invent live evaluator fields. W9 production wiring needs W4 for:

- Actual live evaluator episodes on the VPS 5-minute RTH loop
- Liveness / positive content-advanced heartbeat
- Freshness clocks (`known_at`, as-of, stale age)
- Provisional 1D LIVE reconstruction vs confirmed daily / confirmed 4H
- Raw-quote basis audit (refuse on mismatch — do not strip the gate)
- State transitions (PROBING → ARMED → TURNING → CANDIDATE → INVALIDATED | EXPIRED)
- `rearm_eligible` wiring
- Real quotes in `.nb-px` / `.nb-chg`
- Real C2 variant that fired
- Real C4 stratification features
- Real C5 `event_id` binding
- Degraded-evaluator signal from the live plane
- The reserved §14 glance and drawer slots listed above

Until W4, a production page that filled these from fixtures would be a lie.

---

## WAIT FOR W6

**Research Priority.** The board-level line stays `ACCRUING` and the card slot stays an em-dash until W6 ships a deterministic, provenance-decomposable score. No hand-waved 0–100. Best remains an unranked filter until then.

---

## WAIT FOR W7

**Outcome-calibrated Opportunity model.** The drawer slot stays `NOT YET MEASURED`. No win probability, no expected return, no “validated edge”.

---

## W9 must not

- Deploy this reference tree as `templates/entry_radar.html.j2` / `site/entry_radar.html` unchanged without live fields
- Treat the W8 reduced card as §14 complete
- Touch Prophet engine paths
- Flatten experts
- Present C4 as a firing detector
- Present provisional as confirmed, stale as live, unavailable as a non-fire
- Drop false-start history
- Auto-trade
- Invent a `#ticker` full-card link
- Pin 390 with `overflow-x: hidden`
