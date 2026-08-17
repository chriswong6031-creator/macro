# D0R Workstream H — Real-data experience architecture

**Not implementation.** No third global header. No new token system. No frontend scores. Extend `_site_nav.html.j2` + `theme.css` + existing GovRev page grammar. Reference shots of the *current* entitled page live in `research/defense_intelligence/evidence/d0r-entitled-*.png` (1440, 820, 390). They are the substrate, not the sixteen target compositions.

Design doctrine: glance = state + plain-word stance; technicals in inspector; every panel answers “so what do I do”; falsifier language stays off the cycle surface.

## H2–H3. Sizes and required states

Sizes: **1440 / 820 / 390**.  
States that every composition must specify: complete/current; partial coverage; stale source/fresh transport; stale transport; identity unresolved; conflicting graph; corrected event; rights blocked; provider down; valid empty; model unavailable; shadow-only; warning/adverse; high uncertainty.

Live mapping from entitled A:

| State | Where it already exists |
|---|---|
| Partial / stale | Headline “Partial or stale coverage”; freshness.partial |
| Rights blocked | Radar overlay “part of a membership” **after** site_full 200 (bug) |
| Provider down / source unavailable | Opportunities 0 + SAM unavailable |
| Projection missing | Budget tab |
| Valid empty | none proven; do not use Radar 0 |
| Late / corrected | P00032 late discovery; action versions |
| Identity unresolved | mapping-backlog 21; filmstrip Members only |

## H1. Sixteen compositions

For each: first glance; what changed; financial why; priced vs remaining; evidence vs analysis; deterministic/inferred/unavailable; contradiction; next; evidence path; persistence; user action; authority.

### 1. Defense Intelligence Command Center
Glance: one sentence regime of the industrial base (“replenishment still funding; budget graph missing”). Changed: count of new **funded** actions since last cut, not ceilings. Financial why: which archetypes are in the tape today. Priced vs remaining: “tape is Aug 13.” Evidence: official award-change count. Analysis: none. Next: open Radar if unlocked, else Change Tape. Persist: last cut clock in the chrome. Action: watch list of golden names. Authority: display. **1440:** three rails (tape, radar, budget health). **820:** tape + health chips. **390:** health + one next action.

### 2. Defense Alpha Radar
Glance: exact-linked research queue, not a score. Changed: new `grc1-*` since last visit. Why: possible statement channel, no ratio if no denominator (already in radar JS). Priced vs remaining: crosscheck legs pending. Evidence: receipt + graph id. Contradiction: mapping backlog. Next: open company dossier. Action: research, not buy. Authority: cannot add candidates. **Live defect:** overlay lock at 1440 despite API 22 — D1 must show 22 or a typed failure, never membership CTA for an entitled user.

### 3. Theme War Room (first three from G2)
Glance: theme state in one line (“munitions: funding up, lines tight”). Changed: theme-tagged events. Why: capacity vs multiple. Priced: residual owner, not a frontend beta. Evidence: awards + P-1 + IR. Unavailable: licensed fleet. Next: issuer list. Persist: theme id in URL. Action: watch the roster.

### 4. Company Defense Dossier
Glance: archetype + funded vs total backlog in company words. Changed: last official action + last print. Why: transmission path. Priced: multiples from market owner. Evidence: 10-K + award. Contradiction: gov vs company monitor. Next: program links. **IRDM:** SATCOM service, P00032 incremental, late known_at. Do not use filmstrip “Members only” here after sign-in.

### 5. Program / Platform Dossier
Glance: phase + contract type + last GAO/DOT&E. Changed: PE / award. Why: EAC / quantity. Evidence: official PDFs. Null program on IRDM is honest. Next: suppliers only if licensed/official.

### 6. Industrial Bottleneck Atlas
Glance: the scarce input, not the prime. Changed: DPA / incident / line-rate. Why: conversion cap. Evidence: official CAPEX. Action: watch bottleneck names vs downstream.

### 7. Backlog / Revenue / Cash Cockpit
Glance: funded backlog walk vs FCF. Changed: last print. Why: WC and contract type. Data from Earnings/SEC only. GovRev supplies the award join.

### 8. Government versus Company Truth Monitor
Glance: “award tape says X; last 10-Q says Y.” Changed: divergence. Why: next print surprise (H-divergence). Evidence: both clocks. Action: wait for print, don’t chase the notice.

### 9. Dislocation Lab
Glance: charge / protest / quality / de-escalation. Changed: 8-K or GAO. Why: contained vs recurring. Priced: already moved? Options owner. Action: stance chip only, no score.

### 10. Change Tape / Catalyst Calendar
Glance: **500 governed changes** (entitled proven) with truth filters. Changed: selected row. Why: Watch — do not chase (already on IRDM inspector). Evidence: receipts + official URL. **Fix:** agency facet as names, not Python dicts. **390:** one row + inspector stack, not three columns.

### 11. Global Defense Source Search
Glance: one query box over *owned* artifacts (awards, filings, GAO). Changed: hit list with type tags. Evidence: click-through. Do not imply Janes.

### 12. Reporting Wave / Peer Read-Through
Glance: who prints this week in the golden set. Changed: peer print. Why: read-through by archetype, not ETF. Calendar from Earnings owner.

### 13. Portfolio Exposure / Stress Map
Glance: holdings × archetype × theme (user portfolio if Terminal). Stress: FP, CR, de-escalation. No ranker. Authority display.

### 14. Research and Model Lab
Glance: preregistered H-* status (not results). Shadow-only until gauntlet. Model unavailable is a first-class state.

### 15. Operator console
Glance: source health, cut clocks, graph id, paywall plane, SAM/budget rails. Live: `/api/health` checkout vs cut date; cookie vs bearer. Not a user cycle page; keep below Calibration / internal.

### 16. Mobile event-to-evidence
Glance: one event, one why, one official link, one stance. **390 entitled shot** shows wrapped tabs — keep one primary rail. Action: copy link / open source. Persist: event id in URL.

## H4. Information hierarchy (applies to all)

If the first screen cannot answer “what changed / why it might matter / what to do (including watch),” the composition fails. Technical IDs (`govws-*`, UEI) live in inspector. EN/ZH parity; no translated `title=` attributes.

## H5. Boundaries recap

- Existing nav families only.  
- Real golden data in mockups (IRDM P00032, HII late discovery, 500 tape, Radar 22).  
- Failure states first-class (budget missing, SAM unavailable, late discovery, Radar hydrate miss).  
- No frontend-computed order.

## H6. Reference receipts

| File | What it proves |
|---|---|
| `d0r-entitled-desktop-changes-tab.png` | 500 tape + IRDM inspector + Watch stance + dict leak on sibling card |
| `d0r-entitled-desktop-candidates.png` | Radar locked overlay after site_full |
| `d0r-entitled-desktop-budget.png` | Budget request rail unavailable |
| `d0r-entitled-mobile-390.png` | 390 wrap |
| `d0r-entitled-tablet-820.png` | 820 |
| `d0r-unentitled-*.png` | compact 2-row teaser for anonymous |

D1–D2 **target** compositions (frozen this close, real golden data, not live-page screenshots) live under `research/defense_intelligence/evidence/compositions/` — not the omitted `mockups/` tree:

| File | Surface | Widths |
|---|---|---|
| `d1-change-tape-rescued.html` | Change Tape after rescue (500, P00032 late, deobligation minus, agency **names**) | 1440 / 820 / 390 via CSS |
| `d1-candidate-radar-entitled.html` | Radar **22** after site_full; mapping backlog 21; no membership overlay | same |
| `d1-budget-sam-failure.html` | Typed Budget `PROJECTION_MISSING` + SAM `SOURCE_UNAVAILABLE` | same |
| `d2-company-dossier-irdm.html` | IRDM dossier: SATCOM service, $18.4M obligation ≠ revenue, null denominator | same |

These are the Gate 10 reference compositions. Entitled production PNGs remain **substrate** (`d0r-entitled-*.png`), not targets.

D3–D16 compositions stay prose until those waves; D1 must not invent a third header or frontend scores.
