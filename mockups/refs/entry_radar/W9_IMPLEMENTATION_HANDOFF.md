# W9 implementation handoff — Live Entry Radar production UI

W8 stops here. W9 is a **separate commissioning**. Do not auto-roll.

Pinned Prophet Board at W8 start: merge `168a9be00691` / tree `d540f493a097`. Re-pin if that tree has moved.

---

## CAN COPY NOW

Approved visual / component / reference behaviour from `mockups/refs/entry_radar/`:

- Sister-language tokens, card geometry, density, chips, featured aura rule, light-plane cards, zh direction flip, focus, reduced-motion
- Header + Probe Set headline + Radar lifecycle ladder (not Prophet's seven cells)
- Expert lane row including the disabled C4 context chip
- Card anatomy: lifecycle + expert identity + optional C2 variant + quote + ACCRUING Priority + why line + freshness footer
- One card per `(ticker, expert)` — multi-expert tickers do not collapse
- Provisional vs confirmed vs nightly-confirmed freshness language
- Stale / unavailable / raw-basis / degraded demotion (no live-candidate look)
- False-start history on the card, not only in a tooltip
- Why drawer order
- Empty / anon / quiet states
- EN/ZH structural bilingualism
- RIG checks in `tools/verify.py` + `tests/test_entry_radar_w8_rig.py` as the production regression floor (adapt selectors, do not weaken)

Copy the **look and the information model**, not the synthetic payload.

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

Until W4, a production page that filled these from fixtures would be a lie.

---

## WAIT FOR W6

**Research Priority.** The glance slot stays `ACCRUING` until W6 ships a deterministic, provenance-decomposable score. No hand-waved 0–100.

---

## WAIT FOR W7

**Outcome-calibrated Opportunity model.** The drawer slot stays `NOT YET MEASURED`. No win probability, no expected return, no “validated edge”.

---

## W9 must not

- Deploy this reference tree as `templates/entry_radar.html.j2` / `site/entry_radar.html` unchanged without live fields
- Touch Prophet engine paths
- Flatten experts
- Present C4 as a firing detector
- Present provisional as confirmed, stale as live, unavailable as a non-fire
- Drop false-start history
- Auto-trade
