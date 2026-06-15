# Insider-buying factor — Phase 0 viability

*Does SEC Form-4 insider buying, constructed the way the literature says actually
carries edge, predict forward returns on our S&P-1500 universe — net of the
multiple-testing and survivorship haircuts the rest of the book is held to?*

Companion to [residual-alpha](RESIDUAL_ALPHA_MOMENTUM.md) and
[S&P Vector](SP_VECTOR_VIABILITY.md). Same gate discipline (IC → BH-FDR → quintile
L/S → Deflated Sharpe → block-bootstrap → split-half → PIT de-bias), same honest
verdict culture. **Status: built + measured + mid/small-cap PIT membership now
reconstructed. Verdict = context/confirmer leg with `net_usd_mcap` (size-normalised
net buying, sector-neutral) as the construction. The first pass was blocked by having
only S&P 500 (large-cap) PIT membership; reconstructing point-in-time S&P 400/600
membership moved the de-biased test into the signal's mid/small-cap habitat, where a
construction now SURVIVES BH-FDR at two horizons (IC 0.029, t=2.9). Standalone GO
still blocked — by L/S deflated-Sharpe economics, not by the survivorship trap.**

---

## 0. What already existed vs. what this adds

`collectors/sec_insider.py` already shipped an aggregate **leaderboard**: net
open-market buy/sell dollars per ticker for the single most-recent published
quarter, surfaced on factors.html and the stock positioning chip. It had **never
been IC-tested**, and it sums every open-market trade into one net-dollar number —
which the literature says destroys the signal (routine noise swamps opportunistic
information; megacap dollars swamp small-cap conviction).

This phase adds the **point-in-time per-transaction panel** and the constructions
that carry edge:

- `collectors/sec_insider.backfill_panel` — resumable backfill of the SEC bulk
  Form 3/4/5 quarterly sets to a per-transaction long panel keyed on **FILING_DATE**
  (the only leak-free alignment date), with reporting-owner identity (`RPTOWNERCIK`),
  role flags (officer/director/10%) and title. **2,314,291 transactions · 16,834
  tickers · 2006-01-03 → 2026-03-31** (`data/sec_insider/insider_panel.parquet`,
  per-quarter cache under `panel/`).
- `engine/insider_factor.py` — causal cross-sectional signals: opportunistic-vs-
  routine (Cohen–Malloy–Pomorski), distinct-insider clusters, role weighting,
  market-cap size-normalisation.
- `scripts/insider_phase0.py` — the IC/FDR/DSR harness → `reports/insider-phase0.md`.
- `scripts/midsmall_pit.py` — reconstructs **point-in-time S&P 400/600 membership**
  from each Wikipedia page's current constituents + changes log (walk-backward into
  intervals, reconciled to current membership), unioned with the existing S&P 500 into
  `data/breadth/sp1500_pit_membership.parquet` (**3,286 intervals · 2,589 tickers**),
  plus best-effort delisted-price recovery (`_closes_delisted_1500.parquet`, +418 names
  → 74% PIT price coverage). This is the GO-blocker data from the first verdict.
- `tests/test_insider_factor.py` — 6 tests incl. the load-bearing no-look-ahead check.

### Gotcha — SEC WAF blocks `github.com` User-Agents
SEC's edge 403s ("Request Rate Threshold Exceeded") any UA string containing
`github.com` (scraper heuristic) and rejects non-contactable addresses, regardless
of request rate. The old `…@users.noreply.github.com` UA failed every GET. Fix:
config default is an `example.com` placeholder that passes; set `SEC_CONTACT_EMAIL`
in `.env` to supply a real contact privately (SEC fair-access prefers a real one).

---

## 1. Construction (all causal)

A trade enters a rebalance only once its `filing_date` has passed. The
routine/opportunistic flag for a trade in calendar month *M* of year *Y* references
only the same insider's trades in month *M* of years *Y−1/Y−2/Y−3* — strictly
earlier, so no look-ahead (trades in the first ~3 panel years are mostly tagged
opportunistic for lack of prior history; opportunistic variants are only reliable
from ~2009). Signals are trailing-`k`-month (default 6) sums/counts of FILINGS,
evaluated at each month-end rebalance; market cap is month-end price × most-recent
shares with `asof_date ≤ rebalance` (PIT, from `fundamentals_panel.parquet`).

| signal | what |
|---|---|
| `buy_usd` | gross open-market purchase $ — size-confounded baseline |
| `net_usd` | purchase − sale $ |
| `n_buyers` | distinct insiders buying — cluster/breadth, size-robust |
| `opp_buy_usd` / `opp_buyers` | opportunistic-only $ / distinct buyers (CMP) |
| `role_buy_usd` | role-weighted $ (CEO/CFO 1.5 · officer 1.0 · director 0.6 · 10% 0.3) |
| `*_mcap` | net/opp/role $ ÷ PIT market cap — size-normalised |

Each scored raw, `|SN` (within-GICS demeaned), and `|act` (IC among only names with
insider activity — the conditional "does more buying beat less among buyers").

---

## 2. Results (window 6mo · forward 63d · 2006–2026 · 242 monthly rebalances)

### Survivorship-biased — full current-member universe (~1374 priced names)

| signal | mean IC | t_HAC | q_FDR | L/S Sharpe | DSR |
|---|--:|--:|--:|--:|--:|
| `opp_buy_usd_mcap\|act` | 0.0376 | 3.68 | 0.003 | — | — |
| `role_buy_usd_mcap\|act` | 0.0349 | 3.52 | 0.003 | — | — |
| `opp_buy_usd_mcap` | 0.0163 | 3.69 | 0.003 | **0.81** | **0.951 SURVIVES** |
| `role_buy_usd_mcap` | 0.0162 | 3.61 | 0.003 | 0.81 | 0.950 MARGINAL |
| `opp_buyers` | 0.0146 | 3.10 | 0.006 | — | — |
| `n_buyers` | 0.0145 | 3.06 | 0.007 | — | — |
| `buy_usd` (baseline) | 0.0144 | 3.22 | 0.005 | — | — |
| `net_usd_mcap` | — | — | — | 0.48 | 0.55 FAILS |

**12 signals survive BH-FDR(10%).** The size-normalised opportunistic/role dollars
are the clear leaders; `opp_buy_usd_mcap` long/short earns **Sharpe 0.81, DSR 0.951,
P(SR>0)=1.0, +8369% cum** net of 5bps. The Cohen–Malloy–Pomorski opportunistic split
adds value where it should (size-normalised + conditional forms); on the bare
distinct-buyer count it is a wash (`opp_buyers` 0.0146 ≈ `n_buyers` 0.0145).

### PIT de-biased — S&P 500-only (large-cap, ~395 names)

**Nothing survives BH-FDR.** ICs collapse to ~0.007–0.017 (t ~1), though the L/S
stays positive: `net_usd` Sharpe 0.52 (P(SR>0)=0.987), `net_usd_mcap` 0.46 — real
positive return, but failing the deflated-Sharpe bar. The `opp_*_mcap` L/S Sharpe
collapses to ~0.03 here. This is the wrong habitat (see §3) — resolved below.

### PIT de-biased — S&P 1500, mid-cap era (2012–2026 · ~749 names · 170 rebalances)

Adding point-in-time **mid/small-cap** membership (§3) moves the de-biased test to
where insider buying actually lives. Now a signal **survives**:

| signal | mean IC | t_HAC | q_FDR | half-stability | L/S Sharpe (P>0) |
|---|--:|--:|--:|---|--:|
| **`net_usd_mcap\|SN`** | **0.0289** | **2.90** | **0.10 — SURVIVES** | 0.031→0.027 | — |
| `n_buyers\|SN` | 0.0163 | 2.15 | 0.21 | 0.015→0.017 | — |
| `opp_buy_usd_mcap` | 0.0112 | 2.28 | 0.21 | stable | — |
| `role_buy_usd_mcap` | 0.0112 | 2.24 | 0.21 | stable | — |
| `net_usd_mcap` (L/S) | — | — | — | — | 0.55 (0.984) |

`net_usd_mcap|SN` (size-normalised **net** buying, sector-neutral) clears BH-FDR(10%)
at q≈0.10, with a 63% hit rate and stable ICs across both halves. It also survives at
the **21-day** horizon (independent confirmation) and decays out by **126 days** — the
months-long decay insider signals are supposed to show, not a cherry-picked horizon.
The L/S still earns a positive but **DSR-failing** Sharpe (0.55, costs+haircut). Note
the construction that wins under PIT is the size-normalised **net**-dollar form, not
the bare cluster counts (which collapse to ~0 here) — and the `|act` conditional goes
negative, so the edge is **buyers-vs-field, not gradations among buyers**.

---

## 3. Reading the gap — survivorship vs. the large-cap trap (RESOLVED)

Two effects were confounded in the S&P-500 biased→PIT collapse:

1. **Survivorship** (the residual-alpha lesson): scoring only current members
   inflates any signal correlated with survival. Real, present here.
2. **The large-cap restriction** (the bigger driver): the *original* PIT membership
   was **S&P 500 only**, but insider buying's edge is concentrated in **small/mid-caps**.

Tell-tale that #2 dominated: `opp_buy_usd_mcap` was the strongest signal on the broad
universe (Sharpe 0.81, DSR 0.951) but near-dead on S&P 500 (Sharpe 0.03) — the opposite
of a pure-survivorship artifact (those decay smoothly), exactly what a size-habitat
effect predicts.

**This is now resolved** with reconstructed point-in-time S&P 400/600 membership
(`scripts/midsmall_pit.py`, §0). The eligible universe ramps ~500 (pre-2012, large)
→ ~920 (2012–19, +mid) → ~1500 (2020+, full), and in the mid-cap era a de-biased
FDR survivor appears (`net_usd_mcap|SN`) — confirming the signal is real in its
habitat, not a survivorship artifact. The irreducible gap left: the free Wikipedia
S&P 600 changes log only reaches ~2020, so **small-caps proper enter the de-biased
test only from 2020** (~6y, low power), and 26% of historical members can't be
re-priced on Yahoo (paid CRSP would close both).

---

## 4. Verdict after Phase 0 (superseded by §6 after Phase 1)

**Ship as a context/confirmer leg, with `net_usd_mcap` (size-normalised net buying,
sector-neutral) as the construction.** Same landing as residual-alpha — but a
**stronger** version of it: we now have a *point-in-time, survivorship-de-biased,
FDR-surviving* signal in the universe where it lives (mid-cap era, two horizons),
not just a survivorship-biased one. What still blocks a clean **standalone** GO is
the deflated-Sharpe/cost economics (L/S DSR ≈ 0.53), plus the residual data ceiling
(small-caps only from 2020; 26% of departed members unpriceable on free data).

- **GO blocker now narrowed to economics, not the survivorship trap.** The size
  effect is confirmed; the remaining questions are whether the L/S clears DSR with
  better execution assumptions and whether the small-cap (pre-2020) and unpriceable
  tail would push it over. That tail needs **paid CRSP** — the same honest ceiling
  residual-alpha hit.
- **Cheap immediate win (no GO needed):** upgrade the *existing* leaderboard from
  naive net-dollar to the **size-normalised, sector-neutral, opportunistic/cluster**
  construction — strictly better signal at zero new data cost, honest as "context,
  not a buy list."
- **Confirmer wiring:** `net_usd_mcap|SN` is a natural Gate-2 confirmer for the
  dislocation/narrative-shock framework and a per-stock conviction chip — context
  that sizes nothing, mirroring how the LLM catalyst layer is firewalled.

**Do NOT** wire it into the cross-sectional scoring composite as a standalone alpha:
one borderline FDR survivor (q≈0.10) whose L/S fails DSR is a *confirmer*, not a
sizer. The honest framing is "real signal, sub-threshold standalone economics."

---

## 5. Phase 1 — long-only economics + orthogonality (`reports/insider-phase1.md`)

Two follow-ups decide whether `net_usd_mcap` is more than a confirmer, both PIT
S&P 1500, mid-cap era 2012–2026 (170 rebalances):

**Long-only beats L/S decisively.** Insider buying is one-sided; the L/S short leg
(least-buying / net sellers) was a forced, weak hedge. A long-only top-quintile/decile
tilt vs the EW eligible universe earns **active Sharpe 0.70–0.73**, bootstrap
**P(SR>0) ≈ 0.997**, 95% Sharpe CI clear of zero — vs the dollar-neutral L/S at
DSR≈0.53. But it sits on the **Deflated-Sharpe boundary**: FAILS at the conservative
whole-program haircut (n_trials=12 → DSR ~0.85) and only clears at a lenient
long-only-family haircut (n_trials≈4 → DSR ~0.95). Robustly positive long tilt,
**borderline as a standalone sizer**.

**Orthogonality is the robust win.** Mean cross-sectional rank-correlation of
`net_usd_mcap|SN` with **12-1 momentum −0.02, log-size 0.06, 1-month reversal 0.02**
— all ≈ 0. Per-date OLS residualisation against those three controls leaves the IC
**unattenuated** (0.0143 → 0.015). The edge is **distinct alpha, not a momentum/size
proxy** — safe to add alongside the existing value/quality/momentum/residual-alpha
legs without double-counting.

---

## 6. Verdict (updated after Phase 1)

**Ship as an ORTHOGONAL conviction/confirmer leg, expressed LONG-ONLY, with
`net_usd_mcap` (size-normalised net buying, sector-neutral) as the construction.**

- The signal is **real** (PIT-de-biased FDR survivor in its mid-cap habitat, two
  horizons), its long-only economics **clearly beat** the dollar-neutral form, and it
  is **orthogonal** to the factors already in the book — three independent reasons it
  earns a place as context/conviction.
- It is **NOT a standalone dollar-neutral alpha sizer**: the L/S fails DSR outright,
  and even the stronger long-only tilt is only borderline under an honest
  multiple-testing haircut. Sizing it standalone would over-claim.
- **Cheap immediate win — DONE.** `engine/equity_factors._insider_block` now ranks the
  factors.html leaderboard by **net buying as a % of market cap** (+ distinct-insider
  CLUSTER count when the panel is present), with three graceful tiers: panel (6-mo
  window, true clusters) → single-quarter aggregate size-normalised (LIVE in CI from
  `insider.parquet`, no panel needed) → legacy raw-$ . Template shows "% cap · $ · 👥".
  Verified: the megacap dollar leaderboard becomes a conviction board (STAA 4.5%/2
  buyers, SONO 2.6%/4-buyer cluster). Still honest as "context, not a buy list."
- **Per-stock positioning chip — ALSO DONE.** `engine/stock_fundamentals._load_insider`
  now uses the same tiered construction (panel: trailing window + distinct-insider
  clusters + net buying as % of cap → aggregate size-normalised → factors.json), and
  `stock.html` renders "Net buying (% cap) · net $ · distinct insiders". Verified
  headlessly (node): STAA +4.48%/2 buyers, SONO +2.58%/4 buyers, and a megacap with
  trivial flow reads a clean "≈0%" rather than "−0.00%". The chip now tells you the
  flow relative to the company's size, not just a raw dollar figure.
- Remaining ceiling for a standalone verdict: small-caps pre-2020 + the 26% of
  departed members unpriceable on free data = **paid CRSP** (same wall as residual-alpha).

---

## 7. Reproduce

```
# 1500 PIT membership (mid/small-cap) — one-time, scrapes Wikipedia + best-effort delisted prices:
.venv/bin/python -m scripts.midsmall_pit
# Phase-0 (both panels: survivorship-biased + S&P 1500 PIT) → reports/insider-phase0.md:
.venv/bin/python -m scripts.insider_phase0 --deep --pit --start 2012            # mid-cap era headline
.venv/bin/python -m scripts.insider_phase0 --deep --pit --start 2012 --horizon 21   # robustness (also survives)
# Phase-1 (long-only economics + orthogonality) → reports/insider-phase1.md:
.venv/bin/python -m scripts.insider_phase1
# panel backfill (one-time, slow; resumable):
python -c "from collectors.sec_insider import backfill_panel; backfill_panel()"
```
