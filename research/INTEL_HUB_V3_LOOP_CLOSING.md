# Intelligence Hub V3 — Closing the Measure→Act Loop

**Charter (operator order 2026-07-21):** *"Upgrade revamp of intelligence_hub so it does better in the stocks it proposes."* Direction chosen by operator: **phased program (all three levers)**; loop posture **arm live, de-escalation-only, gated**; scope **US + CN/HK**.

Status: decision-grade masterplan. Diagnosis verified against this checkout. Supersedes the ranking-focused `INTELLIGENCE_HUB_V2_RESEARCH.md` (whose §5b edge-remaining ranking fix **already shipped** — `engine/intel_hub.py` is `intel_hub.command.v2`).

---

## 1. Diagnosis — what's actually wrong (verified, not asserted)

The hub's *ranking* is already a sophisticated V2 (edge-remaining, anti-consensus, sorts on `opportunity_score` first — `intel_hub.py:464,765`). The weakness is **the measure→act loop is open by design**:

| Layer | State | Evidence |
|---|---|---|
| **Ranking** (`intel_hub.py`) | GOOD — V2 edge-remaining, anti-chase, leading-vs-lagging gap | `SCHEMA=intel_hub.command.v2`; sort key `(opportunity_score, composite_conviction)` |
| **Measurement** (`radar_ic.py`, `hub_track_record.py`, `desk_scorer.py`) | GOOD but IGNORED — every track record is *"CONTEXT-ONLY — never fed into a score/size/allocation"* | `radar_ic.json`: IC=**−0.33** over 1977 matured obs; POSITIVE_DIVERGENCE (the leading *bullish* leg) dir_accuracy **0.361** |
| **Accountable leans** (`stock_desk.py`) | HONEST but no edge, and the headline metric is misleading | `stock_desk/track_record.json`: hit_rate 0.774 **but dir_accuracy 0.419**; "cautious" dir 0.353 (fights momentum via the `_reconcile` clamp on Extended names) |
| **Selection root** (`setups.py`/`residual_alpha.py`) | admits "NO validated forward edge at this horizon" | `stock_desk.py:14-20` disclaimer |

**The core pathology:** the system has *measured* that its leading feeder is currently inverted, but ranks on it anyway because track records are context-only. The 77% "hit rate" is an artifact of lenient falsifier bands (a "cautious" lean survives as a hit until the name rips >+5% vs SPY; ATO +4.13% cautious = "hit", directionally wrong).

**Honest caveat (load-bearing):** the radar −0.33 IC is a **pooled Spearman** over ~1 month / ~26 snapshot dates. It (a) overstates significance by ignoring the h-day overlap autocorrelation, and (b) is one-regime. It proves the loop is *essential and currently ignored* — NOT that radar is permanently dead. The governor's rigorous daily-HAC gate is designed so this uncertainty resolves itself (see §3.2).

---

## 2. Principle — the loop, done to house epistemics

CLAUDE.md: track records are context-only; *"LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations."* The V3 governor is the **deterministic, de-escalation-only** realization of exactly that permission:

- **De-escalation only.** A signal's trust ∈ `[FLOOR, 1.0]`; the hub applies it as a **downward scale**. The governor can only REMOVE influence from a proven-mis-firing signal — never originate or boost one. `opportunity` is never increased by the governor.
- **Gated / pre-registered / arm-by-evidence.** A signal is demoted only when `n_matured ≥ MIN_N` **AND** a **rigorous daily-HAC** t (Newey-West lag=horizon — the overlap-robust path, never the naive pooled Spearman) is significant with the **wrong sign**. Until then trust = 1.0 (no change). This mirrors `engine.pooling.arming` — reuse it, don't reinvent.
- **Regime-conditioned.** Snapshots stamp the day's regime forward; grading breaks out `by_regime` so a signal that only fails in one regime can't be demoted on a blended average (and can't hide behind one either).
- **Audited.** Every decision → `data/hub/signal_governor.json` with `{n_matured, ic, t_hac, armed, trust, reason}`. FABLE-WHY-style audit trail.
- **Degrade-never-raise.** No track record / parse error ⇒ trust 1.0 (identity) ⇒ hub byte-identical to ungoverned. Absent governor file is a valid state.

This is the authorized doctrine change (context→action), scoped to de-escalation, gated by evidence. Nothing here sizes a position.

---

## 3. Phased build

### Phase 1 — Close the loop (THIS PR, US) — SHIPPED
1. **Persist the hub track-record** (`build_intel_hub.py`): `compute()` → `data/hub/track_record.json` (was ephemeral). ✅ SHIPPED. *Deferred to Phase 1b: extend `snapshot()` with per-feeder `dirs` + a `regime` stamp + `by_regime` grading — forward-accruing, no immediate effect, and the rigorous daily-HAC is already the primary curve-fit guard.*
2. **Rigorous radar IC** (`radar_ic.py`): emit a daily-HAC signed-IC + t (`ic_daily_hac`) alongside the pooled IC. ✅ SHIPPED.
3. **`engine/signal_governor.py`** — reads the matured track-records, applies the pre-registered gate (incl. the symmetric **inverted detection** the `proven` gate lacked, AND the `n_days ≥ horizon` non-degenerate-HAC validity bar), emits per-signal `trust` + audit. ✅ SHIPPED.
4. **Wire into `intel_hub.py`** — downward-only: a demoted feeder that is *bullishly driving* a name scales that name's `opportunity` by `trust` (provably ≤ ungoverned — the scalar-on-final-score form, NOT weight-scaling inside the edge average, which is non-monotone). Behind file-presence gate; `load_trust` re-clamps ≤ 1.0. ✅ SHIPPED.
5. **Tests** (`tests/test_signal_governor.py`, 15) — gate arms ONLY on significant wrong-sign + min-N + valid HAC; degenerate long horizon refused; de-escalation invariant; degrade-safe; downward-only through a real `_dossier`. ✅ SHIPPED.

### Phase 2 — Insider-cluster selection edge — SHIPPED (PR #3)
**Premise correction (verified against the repo's OWN deep validation):** the V2 note called insider clusters "FDR-surviving," but `data/research/insider_lh_ruler_p_results.parquet` shows they do NOT survive — `rejected_bh=False`, `_display_only=True`, `survivorship_biased=True` for every insider feature. So insider clusters are honestly **display-tier**, never a promoter. And they were already wired + flowing into the hub via `intel_discovery.scan_insider_clusters` (the docstring's "neither consumed by the hub today" was stale — 123 candidates surface live).

Two real gaps found and fixed, both epistemics-clean:
1. **Strength ordering (display-tier).** The scan flattened every strong cluster at the `disc_score` cap 0.45 and the injection sorted by raw buyer count — so a 19-buyer/1-officer cluster beat a 7-buyer/**7-officer** one. Added an uncapped `cluster_strength` (breadth + officer-fraction + $ + per-buyer conviction; no mcap — none exists for off-desk names) that orders the clusters and drives the bounded off-desk injection + the ranked tie-break (`composite_conviction`), while `disc_score` stays capped (never out-ranks a validated lead). Now the genuinely high-conviction accumulation (unanimous-officer clusters) surfaces.
2. **Per-feed measurement.** `hub_track_record` snapshots now carry the discovery `source`; `compute` adds a `by_source` forward-performance breakdown ("do insider-cluster names actually outperform?") — the evidence a display-tier feed needs to EARN promotion (or be dropped). Likely dormant near-term (quarterly-lagged panel) but starts the clock. US-only (insider = SEC Form 4; CN has no equivalent feed).

*(Not done: deepening the special-situations fusion at `intel_hub.py:905` — separate follow-on.)*

### Phase 3 — Recalibrate the accountable-lean layer (follow-on PR)
Fix the "cautious dir 0.353" problem: the `_reconcile` clamp forces caution on high-momentum Extended names that keep running at 21d. Options: momentum-aware horizon; allow "neutral" (not forced "cautious") on strong-momentum-but-extended; lengthen horizon where mean-reversion dominates. Recalibrate conviction to the (now loop-fed) track record.

### Phase 1b — CN/HK parity — SHIPPED (PR #2)
Region-parameterized the governor (`_REGIONS` config; `region` on `compute`/`load_trust`) + `hub_track_record.compute` (injectable `rows`/`fwd_rel_fn`/`bench`) — US behavior byte-identical (defaults). Built the **CN measurement half that did not exist**: `china_intel_hub.compute_track_record()` grades the CN hub's own claims **CSI300-relative** via the shared stats engine (verified on real data: 1,281 snapshots, 97 matured @5d — accruing, not yet HAC-significant). Wired the governor into `china_intel_hub._dossier` (downward-only, radar) + `build_china_intel_hub` (grade → persist → govern). **CN is honestly dormant** today: CN radar has 0 resolved outcomes (no `china_radar_ic` yet), and the hub composite needs ≥6 dated cross-sections (has 5). It arms as CN evidence accrues. Deferred: a `china_radar_ic` grader (needs `china_radar_ledger` to mature) is what lights up the CN radar lever.

---

## 4. What today's data actually does (measured, not predicted)

Ran the real maturation. The rigorous gate holds radar in **honest shadow** today — and the *reason* is itself the validation of the design:

| Horizon | n_matured | daily-HAC | verdict |
|---|---|---|---|
| 10d | 3911 | n_days 19, mean_ic −0.097, **t=−0.90** | valid HAC (19 ≥ 10), **not significant** → no demote |
| 21d | 1977 | n_days 11, mean_ic −0.267, t=−8.29 | **DEGENERATE** (11 daily ICs < lag 21) → **refused** |
| 63d | 0 | — | not matured |

The pooled Spearman (−0.33) and by-state (POSITIVE_DIVERGENCE dir 0.361) *look* alarming, but they are the SAME ~1 month of heavily-overlapping data viewed differently — ≈1.5 independent 21-day windows. The 21d HAC t=−8.29 is an artifact of `lag (21) > n_days (11)`; the *clean* 10d HAC says −0.90 (not significant). So the governor **correctly refuses to act** and reports the distance-to-arming: *"best is 21d with 11 daily ICs, need ≥21."* It arms automatically in ~10 trading days once the 21d span fills in.

**This is the honest outcome of "arm live, de-escalation-only, gated"** — the loop is live and will de-escalate radar the moment the evidence is independently sufficient, without curve-fitting to a thin bear-month window. Immediate ranking change today: none (radar trust 1.0). The deliverable is the self-correcting loop, proven to demote-and-only-demote when a signal *does* clear the gate (tests + a forced-trust real-hub probe: 6/30 names demoted, 0 invariant violations).

**Operator flip:** if you want radar de-escalated NOW on the striking-but-overlapping 1-month evidence, it's a one-line gate relaxation (drop the `n_days ≥ horizon` validity bar). I recommend against it on rigor grounds — but it's your call and reversible.

---

## 5. Files

- NEW `engine/signal_governor.py`, `tests/test_signal_governor.py`
- EDIT `engine/hub_track_record.py` (persist + snapshot schema + inverted detection + by_regime)
- EDIT `engine/radar_ic.py` (daily-HAC signed IC)
- EDIT `engine/intel_hub.py` (downward-only governor application)
- EDIT `scripts/build_intel_hub.py` (persist track-record; run governor)
- FOLLOW-ON `engine/china_intel_hub.py`, Phase 2/3

## 6. Non-negotiable invariants (test-enforced)
1. Governor absent/corrupt ⇒ hub output byte-identical to ungoverned.
2. `trust ≤ 1.0` always; governed `opportunity ≤ ungoverned opportunity` always.
3. A signal is demoted ONLY through the rigorous daily-HAC gate — never the pooled Spearman.
4. No track record ever sizes a position. Display + rank-de-escalation only.
