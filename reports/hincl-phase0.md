# H-INCL Phase-0 — Stock-Connect Southbound (港股通) Inclusion Events

## **VERDICT: STEP-1 roster feasibility PASS (dated add/remove series 2016→ built free from the SSE 港股通标的调整 archive). STEP-2 event study: NO-GO on both gated trials (announcement-drift, effective-day-demand). The inclusion demand is REAL but fully impounded BEFORE the dashboard can act — the added name rallies ~+5.3% vs HSI in the 10 sessions INTO the next-open fill, then drifts flat-to-negative (post-fill +20d CAR −0.3%, HAC t 0.46, DSR 0.07, split-half sign-flips). Underpowered on the in-tree mega-cap panel (only 39 of 466 add events, K=25 episodes). ACCRUE-lean note: register a deeper-panel re-run once the ~500-name expanded HSCI panel lands. Nothing is wired.**

Pre-registered in `research/H_INCL_PREREG.md` (committed 2026-07-03 as a SEPARATE commit BEFORE the
roster was scraped or any statistic ran — the commit timestamp is the audit trail). Roster collector
`scripts/collect_hk_connect_roster.py` → `data/hk_connect_roster/roster.parquet` (+ `PROVENANCE.md`).
Event study `scripts/hincl_event_study.py`. Reports-only per masterplan W3 acceptance; NO engine/board
wiring.

---

## 1. STEP-1 — roster feasibility (this battery's gate) → **PASS**

The battery brief made roster feasibility the gate: obtain a HISTORICAL southbound Connect
eligibility roster with effective dates 2016→, or return **BLOCKED-DATA**. Result: a usable, free,
dated add/remove series was found and built. What was tried:

| Source | Result | Usable for 2016→ dated roster? |
|---|---|---|
| HKEX "View All Eligible Securities" (+ `Change_of_*_Lists.xls`) | lists **SSE/SZSE = NORTHBOUND**; no SEHK southbound list on this page | **No** |
| akshare `stock_hk_ggt_components_em` (港股通成份股) | CURRENT snapshot only, no effective dates, no removals; host `push2.eastmoney.com` WAF/UA-blocked on our network | **No** |
| HKEX CCASS "Southbound Shareholding Search By Date" (`mutualmarket.aspx?t=hk`) | per-date holder set = roster as-of that date, BUT empirically a **strict ~365-day rolling window** (2026/07/03…2025/07/03 populate ~840 codes; 2025/07/02 and earlier return the 7.5 KB empty page) | **No** — cannot reach 2016 |
| **SSE 港股通公告 archive** (`sse.com.cn/services/hkexsc/disclo/announ/`) | paginated `s_list_N.shtml` (page 1 + N=2…27), **194 关于沪港通下港股通标的调整/名单调整 notices, floor 2015-09**; each `c_YYYYMMDD_ID.shtml` a structured table with **调入(add)/调出(remove)** rows + effective-date phrasing | **YES — built** |
| SZSE 深港通 notices | parse identically (调入/调出/生效 verified) | robustness cross-check (list API 500s to our UA) |

**Roster built:** `data/hk_connect_roster/roster.parquet` — **796 rows, 2015-09 → 2026-07**:
**466 ADD events across 444 distinct tickers**, 330 remove events. Adds by year:
2018:27 · 2019:30 · 2020:31 · 2021:77 · 2022:31 · 2023:42 · 2024:65 · 2025:84 · 2026:79. This is
exactly the PIT southbound-eligibility roster the red-team demanded H1 needs (CRITIC:quant MAJOR),
delivered as a side-benefit. (Had the SSE archive not existed, the pre-registered fallback was
BLOCKED-DATA + capture the CCASS 1-y rolling window forward and re-run ~2028.)

---

## 2. Pre-registered gates vs results (STEP-2 event study)

Primary horizon **+20d**, episode-level CARs (one obs per distinct add-date; semi-annual review
batches are ONE episode — the pre-registered effective-N rule). Family = 2 gated trials; program DSR
`n_trials = 30`.

| # | Trial (anchor · fill) | Episode-K (gate ≥8) | mean CAR +20d | HAC t (gate ≥+2.0) | BH-FDR reject (α.10) | DSR (gate ≥0.90) | Split-half same-sign | Surv. LB mean · t | **Verdict** |
|---|---|---|---|---|---|---|---|---|---|
| T-ANN | announcement · next bar after announce | 25 | **+1.57%** | **0.46** | no (q=.61) | **0.074** | **FLIPS** (+5.7% → −2.3%) | +0.09% · 0.45 | **NO-GO** |
| T-EFF | effective · 2nd bar after announce | 25 | **−1.04%** | −0.29 | no (q=.61) | **0.007** | FLIPS (+5.0% → −6.6%) | −0.06% · −0.29 | **NO-GO** |

Every gate is missed by a wide margin on both trials. BH-FDR rejects neither (q=0.61 both). The
survivorship lower bound (impute the 419 non-panel adds at CAR=0) barely moves the mean — the
mega-cap panel is ~all survivors, so the bound is tight and does not rescue either trial.

### Horizon curve (episode-level, K=25)
| horizon | T-ANN mean CAR / HAC t / DSR | T-EFF mean CAR / HAC t / DSR |
|---|---|---|
| +5d  | **+2.07% / 1.65 / 0.28** | +0.85% / 0.54 / 0.09 |
| +10d | +1.89% / 0.92 / 0.12 | −1.28% / −0.61 / 0.004 |
| +20d | +1.57% / 0.46 / 0.07 | −1.04% / −0.29 / 0.007 |
| +40d | +0.62% / 0.20 / 0.03 | −1.46% / −0.39 / 0.007 |
| +60d | +1.26% / 0.36 / 0.04 | −0.20% / −0.05 / 0.017 |

The ONLY marginal cell is **T-ANN +5d (t=1.65, split-half same-sign, DSR 0.28)** — a fast-decay
announcement drift hint, consistent with the mechanism front-running and dying within a week. It does
not clear the gate at any horizon and is not a GO; it is the seed of the ACCRUE note (§5).

---

## 3. The mechanism, in event time (why NO-GO despite a real effect)

The event-time CAR curve (`data/experiments/hincl_car_curve.json`, 38 in-panel add events,
announce-anchored, next-bar fill at t=0):

- **t−10 → t0: +5.3% vs HSI.** The added name rallies hard INTO the fill bar. The market front-runs
  the not-yet-effective inclusion; by the time the name is tradable from a nightly-rendered dashboard
  read next morning (fill = next open after the SSE announcement's real-world availability), the
  inclusion pop has already happened.
- **t0 → +20d: −0.3%** (essentially flat, mild give-back). The marginal southbound buyer's demand is
  impounded pre-effective; post-fill there is buy-the-rumour-sell-the-fact drift, not continuation.
- **t0 → +60d: −0.4%** — no durable post-inclusion continuation on this panel.

This is precisely the implementation-lag honesty the red-team demanded (CRITIC:hk MAJOR
"execution-horizon decay … a nightly-rendered dashboard cannot capture a weekly-horizon demand shock
whose edge is largely gone by the next open"). The mechanism is causal and its price impact is
visible — it is simply **not capturable** at the dashboard's fill point. A ranker built on "recently
added to Connect" would be buying AFTER the move.

**Exploratory (non-gated):** removal (调出) side, effective +20d — mean CAR −2.4%, HAC t −0.59,
K=14 (weak de-rate direction, not significant). Pre-run into the fill: +4.3% (announce) / +6.2%
(effective) — the pre-fill rally is the whole story on both anchors.

---

## 4. Effective-N & why this is under-powered (pre-stated, not post-hoc)

The pre-reg §6 warned the binding limit is the panel, not the roster: **466 add events, but only 39
land on a name in the 157-name `closes_deep` mega-cap panel (37–38 studiable after the suspension /
window rules), across just 25 distinct add-dates → episode-K = 25.** Most Connect ADDITIONS are the
small/mid-caps *entering* eligibility — the very names absent from a mega-cap panel and the very names
where the marginal-buyer demand shock is largest. So the studiable sample is both thin (K=25) and
skewed to the least-affected (already-large) names. K=25 clears the K≥8 floor, so these are *reported*
verdicts (not "uncomputable"), but DSR≥0.90 on 25 noisy episodes is a high bar the effect gets nowhere
near (best DSR 0.28).

### The two-variant construction is a ~1-session offset, not the ideal wide separation
The masterplan's "announcement drift vs inclusion-day demand" ideal needs the TRUE effective date,
which SSE notices state in heterogeneous prose ("其将被调入…范围", per-name stability-period endings) —
not reliably parseable across 194 notices. Per the pre-reg fallback, T-EFF fills one bar after T-ANN.
So T-ANN and T-EFF differ by a single session here; the true effective date is typically several
sessions-to-weeks after announce for periodic reviews. **Read T-EFF as a lower-offset proxy, not the
literal inclusion day.** The event-time curve (which brackets t−10..+60 around the announce fill)
is the honest object; it already shows the impound is pre-fill regardless of the exact effective bar.

---

## 5. Verdict, honestly (NO-GO with an ACCRUE path)

- **T-ANN: NO-GO.** Positive but far sub-threshold (HAC t 0.46, DSR 0.07), split-half sign-flips.
- **T-EFF: NO-GO.** Negative post-fill, DSR 0.007, split-half sign-flips.
- **Not KILL** — nothing is significantly negative to actively fade (|t| well under 2).
- **ACCRUE note (registered):** the +5d announce drift (t=1.65, same-sign split-half, DSR 0.28) plus
  the clear pre-fill rally say the *mechanism is real and fast*. The test is under-powered by the
  panel, not by the mechanism. The registered accrual path: re-run once the planned `hk_stocks_ext`
  ~500-name expanded HSCI panel lands (masterplan W1), which lifts studiable-K by including the small/
  mid-caps that ARE the additions. Only then is a decision-grade read of the fast pre-effective drift
  possible — and even then the dashboard-capturability question (impound is pre-fill) likely stands.

Honest prior check: the brief called H-INCL "the HK battery most likely to GO." On the in-tree panel
it does NOT go — the effect exists but lives in the pre-fill window and in names off our panel. That
is a scope/implementation finding, held to the same gates as every other battery.

---

## 6. What this does NOT show (pre-committed)

- **Not a full-universe result.** 157 mega-caps; the small/mid-cap additions where demand-impact is
  largest are unobserved. Studiable-K=25 is a floor on power, not the true event count.
- **Not "no inclusion effect exists."** The +5.3% pre-fill rally IS the inclusion effect — it is just
  impounded before the dashboard's fill point. The NO-GO is about capturability + our panel, not about
  the mechanism's existence.
- **Not causal identification** beyond timing (index-membership changes correlate with size/liquidity/
  A-share events that also move price).
- **Not tradeable net of costs/HK borrow;** CAR is gross index-relative buy-and-hold.
- **Survivorship:** current-constituent panel; §2 reports the imputed-0 lower bound (tight here). The
  true small-cap universe is unobserved — a scope limit, not a correctable bias.
- **Roster scope:** the file is the SSE (沪港通) southbound adjustment record; the union SH+SZ roster
  is ~90% overlapping; SZSE (深港通) is a cross-check, not exhaustively unioned. Pre-2018 additions are
  sparse/ad-hoc (bulk table notices start ~2018); the effective-date is the announce+1 fallback, not
  in-text parsed.

---

## 7. Artifacts
- `data/hk_connect_roster/roster.parquet` (+ `PROVENANCE.md`) — the dated add/remove series (committed).
- `scripts/collect_hk_connect_roster.py` — roster collector (collect-lane; no render dependency).
- `scripts/hincl_event_study.py` — event study.
- `data/experiments/hincl_event_study_results.json` — full stats (all horizons, CIs, split-half, LB).
- `data/experiments/hincl_car_curve.json` — the event-time CAR curve.
- Registry: `data/experiments/registry_seed.json` id `hkca_h_incl_connect_events`.
