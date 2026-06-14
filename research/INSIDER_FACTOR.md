# Insider-buying factor — Phase 0 viability

*Does SEC Form-4 insider buying, constructed the way the literature says actually
carries edge, predict forward returns on our S&P-1500 universe — net of the
multiple-testing and survivorship haircuts the rest of the book is held to?*

Companion to [residual-alpha](RESIDUAL_ALPHA_MOMENTUM.md) and
[S&P Vector](SP_VECTOR_VIABILITY.md). Same gate discipline (IC → BH-FDR → quintile
L/S → Deflated Sharpe → block-bootstrap → split-half → PIT de-bias), same honest
verdict culture. **Status: built + measured. Verdict = context/confirmer leg, NOT
a standalone scored factor — a clean standalone verdict is blocked (not failed) by
the lack of point-in-time SMALL/MID-cap membership, which is exactly where the
signal lives.**

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

### PIT de-biased — actual S&P 500 members + recovered delistings (~395 names)

**Nothing survives BH-FDR.** ICs collapse to ~0.007–0.017 (t ~1), though the L/S
stays positive: `net_usd` Sharpe 0.52 (P(SR>0)=0.987), `net_usd_mcap` 0.46 — real
positive return, but failing the deflated-Sharpe bar. The `opp_*_mcap` L/S Sharpe
collapses to ~0.03 here.

---

## 3. Reading the gap — survivorship vs. the large-cap trap

Two effects are confounded in the biased→PIT collapse:

1. **Survivorship** (the residual-alpha lesson): scoring only current members
   inflates any signal correlated with survival. Real, present here.
2. **The large-cap restriction** (the bigger driver this time): the only PIT
   membership we have is **S&P 500**. Insider buying's edge is academically
   concentrated in **small/mid-caps** — and indeed the median *active* universe
   drops from ~300 names (full) to ~75–98 (S&P 500). Forcing the PIT test onto
   large caps removes the signal's natural habitat, so the FDR-miss there is not
   a clean refutation.

Tell-tale: `opp_buy_usd_mcap` is the strongest signal on the broad universe
(Sharpe 0.81, DSR 0.951) but near-dead on S&P 500 (Sharpe 0.03) — the opposite of
what a pure-survivorship artifact would do (those decay smoothly), and exactly what
a size-habitat effect predicts.

---

## 4. Verdict & path-to-GO

**Ship as a context/confirmer leg, not a standalone scored factor.** Identical
landing to residual-alpha: the construction is sound and the *opportunistic +
cluster + size-normalised* form (not the shipped naive net-dollar sum) is the right
one, but the strict-PIT standalone case can't be made with current data.

- **GO blocker (data, not signal):** point-in-time **S&P 400 / S&P 600** membership.
  With small/mid-cap PIT membership we could test the signal where it lives and
  separate survivorship from the large-cap trap. This is the single highest-value
  next step and is the same class of work as `scripts/residual_alpha_pit.py`.
- **Cheap immediate win (no GO needed):** upgrade the *existing* leaderboard from
  naive net-dollar to the **opportunistic, size-normalised, cluster-weighted**
  construction — it is strictly better signal at zero new data cost, and honest as
  "context, not a buy list."
- **Confirmer wiring:** the opportunistic-cluster signal is a natural Gate-2
  confirmer for the dislocation/narrative-shock framework and a per-stock conviction
  chip — context that sizes nothing, mirroring how the LLM catalyst layer is firewalled.

**Do NOT** wire it into the cross-sectional scoring composite on the strength of the
survivorship-biased panel alone — that is exactly the trap the gate exists to catch.

---

## 5. Reproduce

```
.venv/bin/python -m scripts.insider_phase0 --deep --pit --start 2006   # both panels → reports/insider-phase0.md
.venv/bin/python -m scripts.insider_phase0 --deep --start 2006 --horizon 21   # 1-month forward
# backfill (one-time, slow; resumable):
python -c "from collectors.sec_insider import backfill_panel; backfill_panel()"
```
