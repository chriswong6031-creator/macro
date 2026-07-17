# Contagion Links (CGL) — directed cross-market contagion pressure, per-radar

**Status:** CHARTERED 2026-07-17 by operator order (in-session).
**Trigger:** the 2026-07 Korea crash spread sequentially into JP / TW / EZ / CN and, on 2026-07-16, into the US — and no surface could answer "how much of *my* market's risk is being imported, and from whom." The radars are 11 independent islands.
**Program code:** CGL. Rulings CGL-R1..R10. Workstreams W0..W5.
**Related programs:** IRD (`INTL_RISK_DESK_MASTERPLAN_BY_FABLE.md` — owns `engine/contagion.py` DY spillover / two-tier US-transmission read, display), RSR (`RISK_SCORING_REVAMP_MASTERPLAN_BY_FABLE.md` — W3 owns the *undirected* alert-breadth cascade meter), RRI (`RRI_S4_FAST_GLOBAL_LEG_PREREG.md` — c3b/c3c intl-breadth → **US** drawdown claims).

---

## §0 TL;DR

Build one directed contagion organ: for every radar market, a continuous **inbound contagion pressure** score — "how hard are crashing markets abroad pressing on THIS market" — computed from (a) a committed structural economic-linkage matrix and (b) market-measured directed spillover, weighted by how severely each source market is actually crashing. Wire it to all 11 risk radars (us, cn, hk, ca, kr, jp, tw, in, au, gb, ez) as: a display strip on every radar card, a named-source receipt ("Korea's crash is the main source of pressure here"), and a **shadow-scored radar variant** (contagion as a Tier-B escalator) forward-logged from day one so the score-affecting seam can be promoted through pre-registered gates.

**Scope fence (CGL-R1):** display-tier + shadow ledger now; zero changes to any existing radar calibration (inherits RSR-R1); live score adjustment activates only at promotion through §4 gates — earliest review 2026-10-17 (shared RSR clock).

## §1 Gap map (what exists, what is missing)

Verified against the tree on 2026-07-17:

| Existing | What it does | Why it doesn't cover this |
|---|---|---|
| `engine/contagion.py` (IRD) | DY VAR(2)/GFEVD spillover on a 14-ticker EM-heavy basket; corr tightening; two-tier **US-transmission** read | Basket ≠ radar markets (no CN/HK/TW proxies); output framed as "is EM stress reaching the US", not per-market inbound pressure; not joined to any radar |
| RSR W3 `deterioration_cascade.v1` (chartered) | Undirected breadth + velocity of foreign risk-off (n_alert across 10 intl logs, maturity-guarded) | Global meter — answers "how broad is the deterioration", not "who is pressing on market X and how hard"; alert-count basis |
| RRI S4 c3b/c3c (ratified prereg) | Intl breadth / radar-alert breadth as **US**-drawdown leads (intl_bridge claims) | US-only target; scoring-track study, no per-market surface |
| `crossmarket_leadlag` (intl_bridge CONTEXT) | 150-pair lead-lag census; 5 stable survivors, ALL timezone lag-1 | Ruled CONTEXT: "transmission read, NOT a forecastable lead" — CGL uses this as the mechanism being *displayed*, and claims nothing it killed |
| `engine/narrative_crossmarket.py` | Same-narrative-abroad display cross-references | Narrative-tier, never touches risk |

**Killed constructions this must not resurrect (DO_NOT_REBUILD §2):** RSR-R6a cross-organ flip-counter; RSR-R6b "4-of-4 defensive-lean floor bundle". Both are **count-conjunctions of alerts**. CGL-R2 below fences CGL out of that class structurally.

## §2 Rulings

- **CGL-R1 (scope fence).** Ships display-tier with forward shadow ledgers from day one. No threshold, band, weight, or gate of any existing radar changes. The shadow escalator becomes live-score-affecting only via §4 promotion. Consistent with the epistemics house law and RSR-R1/R2.
- **CGL-R2 (construction class).** The pressure number is a **continuous, linkage-weighted sum of source-market severities measured from price structure** (drawdown + downside velocity). No alert counting, no radar-state input, no conjunction-of-flags appears anywhere in the number. Radar states of source markets appear only as Tier-2 display receipts. This is a different construction class from the RSR-R6 kills; the kill closed count-conjunctions, not the directed-pressure search space.
- **CGL-R3 (timezone honesty).** The dynamic linkage matrix is computed on NYSE-close-aligned US-listed ETF proxies only (the IRD idiom) — never on mixed-timezone local closes. Source severity uses local benches and carries a per-market `as_of`. The tz lag-1 transmission finding is displayed as mechanism, never claimed as a forecastable lead.
- **CGL-R4 (Tier-B law).** Contagion pressure may only **escalate** an already-warm radar (incumbent gated state ≥ watch), by at most one band, never originate state from calm — in shadow today and at promotion tomorrow. Same law as the US radar's Tier-B scares.
- **CGL-R5 (matrix law).** The structural linkage matrix is a **committed, versioned constant** (`structural.v1`) with per-row rationale in code review. Changes require a PR and bump the version; a version bump **restarts shadow accrual** (the graded construction changed). No LLM may set, adjust, or escalate any weight (LLM de-escalate-only law).
- **CGL-R6 (lane gates).** History and shadow-ledger appends obey `ledger_lane_armed()` (COLLECT_LANE=nightly); off-lane invocations are read-only. LETHAL known trap: asia-close sets NO COLLECT_LANE (#2688/#2693 class) — CGL appends run on the nightly lane only, from `scripts/build_intl.py`.
- **CGL-R7 (degradation).** Missing/stale proxy → that market's dynamic column is null and the blend falls back to structural-only **with disclosure** (`dynamic: null`, `gaps[]` populated). A null never blocks the artifact, the display, or accrual.
- **CGL-R8 (surface law).** Glance tier is plain words under `docs/DESIGN_DOCTRINE.md` — banned at glance: GFEVD/VAR/DY/percentile jargon. Receipts (linkage weight, source drawdown, spillover share) live at hover/Tier-2. Bilingual EN/ZH dual-span; no translated text in `title=`.
- **CGL-R9 (coordination).** RSR-W3 keeps the undirected cascade meter and any macro-level cascade tile. CGL owns the per-market directed strip on radar cards and the directed who-presses-whom table on intl.html. Shared artifacts are extended additive-key only.
- **CGL-R10 (schema law).** `contagion_links.v1` and every consumer are additive-only: tolerate unknown keys, never pattern-match the key set (#2687 law).

## §3 Frozen construction v1

Markets `M` = {us, cn, hk, ca, kr, jp, tw, in, au, gb, ez}.

**ETF proxies (dynamic matrix; all NYSE-aligned):** us=SPY (yahoo), cn=FXI (yahoo), hk=EWH (intl_etf), ca=EWC, kr=EWY, jp=EWJ, tw=EWT, in=INDA, au=EWA, gb=EWU, ez=equal-weight mean(EWG, EWQ, EWI, EWP) (intl_etf).

**Local benches (severity):** the 11 radar bench series already registered in `engine/risk_radar.py` / `engine/risk_radar_intl.PROFILES` (us=`yahoo/_GSPC`).

1. **Dynamic directed matrix D[src→dst]:** Garman-Klass vol per proxy → VAR(2) → GFEVD at horizon 10, window 150bd — the IRD frozen params (`engine/contagion.py`: DY_WINDOW=150, VAR_LAG=2, HORIZON=10), applied to the 11-proxy panel. D[src→dst] = src's share of dst's forecast-error variance, off-diagonal, row-normalized over sources for each dst.
2. **Structural matrix S[src→dst]:** committed `structural.v1`, weights in [0,1] from trade + financial + supply-chain exposure, normalized over sources for each dst. Anchor priors (reviewed in-PR): CN→HK strongest single link; KR↔JP↔TW mutual tech-supply block; CN→AU commodities; US→every market elevated (global beta); EZ↔GB; US↔CA.
3. **Blend:** L = 0.5·S + 0.5·D per dst row; where D is null (CGL-R7) L = S.
4. **Source severity** σ[src] ∈ [0,1] from the LOCAL bench: `dd21 = 1 − close/rolling_max(close, 21)`, `ret10 = 10-session pct change`; σ = clip(max(dd21 / 0.10, −ret10 / 0.07), 0, 1). Frozen saturation: a 10% 21-day drawdown or a −7% 10-day return is full severity.
5. **Inbound pressure:** `P_raw[dst] = Σ_{src≠dst} L[src→dst] · σ[src]`. Score = `pct_rank_window(P_raw_series, 504)` (`engine/indicators.py`), computed causally. The P_raw history series is built with the SAME blended construction as today's print: D is refit causally at a 5-session stride over the trailing 504+150 sessions (each refit uses only data through its date) and forward-filled between refits; σ is fully vectorized. Day-1 percentiles are therefore real, not cold-start, and substrate ≡ live construction.
6. **Display levels:** LOW < 0.75 ≤ MODERATE < 0.90 ≤ HIGH (percentile).
7. **Shadow escalator (frozen):** `pressure_pct ≥ 0.90 AND incumbent gated state ≥ watch` → shadow state = incumbent + 1 band (cap risk-off); else shadow = incumbent. Incumbent read from each market's live forward log / snapshot; staleness disclosed via `incumbent_as_of`.
8. **Receipts per dst:** top-3 exporters by `L[src→dst]·σ[src]` with linkage weight, source dd21/ret10, and plain-word EN/ZH lines.

**Artifacts:**
- `data/contagion_links/latest.json` — schema `contagion_links.v1`: `built`, `params`, `matrix {structural_version, static, dynamic, blended}`, `severity {mkt: {sigma, dd21, ret10, as_of}}`, `pressure {mkt: {raw, pct, level, top_exporters[], shadow_state, incumbent_state, incumbent_as_of}}`, `gaps[]`. Site copy: `site/riskdata/contagion_links.json`.
- `data/contagion_links/history.jsonl` — nightly append (lane-gated, first-writer-wins by as_of): per-market `{asof, market, p_raw, pct, level, top_exporter}`.
- Shadow forward logs: `data/risk_radar_intl/<mkt>_forward_log_contagion.jsonl` (10 markets) + `data/risk_radar/forward_log_contagion.jsonl` (us) — RRI shadow-log idiom, graded later by the same h21 machinery.

**Persistence law (post-review, 2026-07-17):** ALL persistence — `latest.json`, the site copy, `history.jsonl`, shadow logs — is nightly-lane-gated (`ledger_lane_armed()`). Off-lane invocations (re-render, closing-bell, asia-close) compute in-memory for display only and never overwrite the committed artifact (never-darken, the #2658 class). Asia-close consumers (cn/hk cards) read the committed nightly artifact and disclose its age in plain words when stale vs the page's own as_of.

**Pipeline slot:** computed inside `scripts/build_intl.py` after `intl_run.run()` (radar snapshots available; nightly lane armed; off the render-critical path — the panel math is pure numpy on ≤11 series, sub-second).

## §4 Pre-registered promotion gates — S-CGL-1 (FROZEN ON MERGE)

Frozen before any construction↔outcome relationship is computed. This PR builds display + forward accrual only; outcome joins land in a later Stage-A replay PR (W3).

- **Family:** `cgl_2026h2`, declared N = 2 (h21 primary, h10 secondary).
- **H1 (primary, h21):** On escalated-only days (shadow ≠ incumbent), pooled across the 11 markets over the replay windows: P(local bench ≥5% drawdown within 21 sessions) ≥ **1.25×** the permutation-null mean, with cluster-Wilson lower bound at z=1.645, AND permutation p < 0.05 (stricter of p-rules binds with BH-FDR at N=2).
- **Robustness (all must pass for GO):** era split (pre-2016 / 2016+) ratio > 1.0 in both; split-half ratio > 1.0 in both; breadth ratio > 1.0 in ≥ 6 of 11 markets.
- **Verdict grammar:** GO / ACCRUE / NO-GO / KILL. Live accrual bar regardless of replay verdict: ≥30 graded shadow rows and shadow do-no-harm vs incumbent before any live swap (RRI Stage-B idiom).
- **Promotion review:** not before **2026-10-17** (shared RSR-R2 clock). Promotion seam: contagion enters each radar as a Tier-B escalator under CGL-R4 — never a new origin scare — via explicit operator ruling on weights.

## §5 Workstreams

| W | What | Tier | Status |
|---|---|---|---|
| W0 | This charter; registry check (no kills to append; no collisions — §1) | docs | this PR |
| W1 | `engine/contagion_links.py` + artifacts + shadow ledgers + radar-card contagion strip + intl.html directed table + tests | display + ledger | this PR (BUILD-NOW) |
| W2 | Macro/mx5 hero chip + turn-tile join (coordinate with #2692 tiles and RSR-W0 shipped chips) | display | next PR |
| W3 | Stage-A replay gauntlet — S-CGL-1 outcome joins per §4 | prereg execution | after ≥1 nightly accrual, own PR |
| W4 | `structural.v2` from measured trade/financial data (annual refresh lane, versioned per CGL-R5) | data | later |
| W5 | Promotion review (with RSR W6) | gauntlet | 2026-10-17+ |

## §6 Come-back checks

- First nightly after merge: `data/contagion_links/latest.json` exists; 11 shadow logs each gain their first row; KR should print as the top exporter into JP/TW with HIGH pressure if the crash persists.
- First asia-close after merge: confirm NO CGL appends happened off-lane (CGL-R6).
- 2026-07-24: history.jsonl has ≥5 rows/market → percentile path sanity check vs the live episode.
- First nightly: verify per-market proxy history depth — a market whose proxy panel has <~400 overlapping sessions degrades to cold-start percentiles (pct null → level low, no shadow escalation; fails safe but must be visible in `gaps[]`).

*Drafted: Fable, 2026-07-17. Operator order in-session; display-tier build proceeds under house law, promotion gates frozen above.*
