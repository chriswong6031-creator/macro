# B0 — Intent-normalization input matrix

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e`
**Question:** what inputs actually exist for reconstructing *active* manager intent, and where the lawful approximation

```
ΔQ_active ≈ Q_t − Q_(t−1) · (S_t / S_(t−1))
```

fails.

No scoring weights. No promotion.

---

## 1. Symbol table

| Symbol | Meaning | 13F filer (SMA / HF public sleeve) | Daily ETF / active ETF |
|---|---|---|---|
| `Q_i,f,t` | Shares of instrument *i* held by vehicle *f* at *t* | 13F information table `sshPrnamt` (CODE VERIFIED collector). Long 13(f) only. | Sponsor holdings file `shares` column (CODE VERIFIED schema `[ticker,name,weight_pct,shares,market_value,as_of]`) |
| `S_f,t` | Shares outstanding of vehicle *f* | **Does not exist.** A 13F filer is not a share class. | Official: N-PORT, sponsor SO, some NAV files (ProShares `historical_nav.csv`). **House does not currently store true S_f,t.** |
| AUM / NAV | Dollar book | 13F `value` is **reportable long 13(f) only**, units changed 2022-12-31 (CODE VERIFIED). Not AUM. | Sponsor AUM/NAV sometimes; N-PORT; not uniformly stored |
| Cash | Residual | Almost never in 13F | Often a "CASH" / currency line — **explicitly dropped** by `is_non_equity_holding` |
| Explicit trade feed | Tickets | No | **ARK trade-notification emails only** among configured sponsors (PRIMARY SOURCE VERIFIED page). Not ingested. |
| Create / redeem | Authorized-participant flow | N/A | Changes `S_f,t`. Scales every constituent roughly in proportion if the basket is in-kind. |
| Custom baskets / settlement | AP can use a custom or cash basket; T+1/T+2 settlement; FX; corporate actions | N/A | Makes `Q` move without a "decision" and without matching `S` 1:1 |

---

## 2. What the house already computes

### 2.1 Share-based flow normalization (the commission's formula, with a proxy S)

`collectors/holdings.py::active_changes_dir` (CODE VERIFIED):

```
so_ratio = sum(Q_t, common names) / sum(Q_{t-1}, common names)
expected = Q_{t-1} * so_ratio
ΔQ_active = Q_t − expected
```

This is the commission formula with

```
S_t / S_{t-1}  ≈  (Σ_i∈common Q_i,t) / (Σ_i∈common Q_i,t−1)
```

Guards already shipped:

- drop cash / FX / derivatives (`is_non_equity_holding`) — a prior bug printed −15,116,065% on cash lines
- drop names whose expected base `< min_base_frac` of the fund
- optional lifecycle rows for brand-new and full-exit (no % on new)

Windows: ARK 5 snapshots / 20% alert; sector-thematic 40 snapshots / 5% alert.

### 2.2 Median continuing-name ratio (second proxy)

`config.yml::etf_holdings.flow_min_scale_n` + `engine/holdings_signals.py` (CODE VERIFIED comments): if ≥5 continuing constituents, trust the **median** share ratio instead of the sum ratio; below that, fall back to the sum. Split/re-denomination guards (`flow_split_min_ratio`, `flow_split_mv_tol`, `flow_split_ratio_tol`) exist because a 25% window previously tagged dip-buys as splits.

### 2.3 Price-residual weight change (different construction)

`holdings_signals` on sector-SPDR top-10: residual of weight change after the stock's price move. On a **passive** index this residual is reconstitution / float, not conviction (config comment, D70). Do not mix this number with §2.1 and call both "intent."

### 2.4 13F QoQ share diff (no S term)

`engine/smart_money.py` diffs consecutive quarter snapshots into new/add/trim/exit. There is **no** `S_t` for a 13F filer. The lawful 13F analogue of create/redeem is:

- the filer received inflows/outflows to the strategy (unobserved)
- the filer revalued the book (value column, not shares)
- the filer amended (`13F-HR/A`)
- the filer omitted a confidential position
- the CUSIP map changed

A raw `Q_t − Q_{t-1}` on 13F is **not** ΔQ_active. It is ΔQ_reported.

---

## 3. Input availability matrix

| Input | Featured 13F desk | Universal 13F census | ARK daily | Dated ETF (Global X, Roundhill, Amplify) | Current-only ETF (SSGA, VanEck, …) | N-PORT quarterly |
|---|---|---|---|---|---|---|
| `Q_i,f,t` shares | Yes, 13(f) longs | Yes, same | Yes | Yes | Yes if tonight's collect ran | Yes, all registered funds |
| Weights | Computable from value | Computable | Yes | Yes | Yes | Yes |
| True `S_f,t` | **No** | **No** | **Not stored** (ARK publishes SO elsewhere; UNKNOWN if on the CSV) | **Not stored** | **Not stored** | **Yes** (fund-level) |
| AUM / NAV | No (13F value ≠ AUM) | No | Sometimes on site, not stored | Partial | Partial | Yes |
| Cash | No | No | Dropped if present | Dropped | Dropped | Present in filing |
| Explicit trades | No | No | Email feed **not ingested** | No | No | No |
| Create/redeem | N/A | N/A | Implicit in SO | Implicit in SO | Implicit in SO | **Explicit monthly** |
| Custom basket / settlement caveats | N/A | N/A | Unobserved | Unobserved | Unobserved | Partially (basket not public daily) |
| Amendment / restatement | `amendments/` PIT | Accession lineage | Overwrite if file changes | Overwrite if file changes | Overwrite | N-PORT/A |
| Confidential omission | Unobserved hole | Flagged `exclude_confidential_omissions: true` on public summary | N/A | N/A | N/A | N/A |
| Put/call / option overlay | 13F put/call column exists; public summary **excludes** put/call from equity actions | Same | Non-equity filter | Same | Same | Full |
| Off-13F book (shorts, credit, non-US, privates) | Unobserved | Unobserved | ETF is the whole vehicle | Same | Same | Registered fund is the whole vehicle |

---

## 4. Where `ΔQ_active ≈ Q_t − Q_{t-1}·(S_t/S_{t-1})` fails

Each row is a **mechanism**. The house proxy fails at least as often as true-S, plus the extra rows marked PROXY.

| # | Failure | Class most hit | Why the identity breaks | House status |
|---|---|---|---|---|
| F1 | True `S` missing | All ETFs today | Proxy assumes the overlapping book *is* the share class. A large single-name decision moves the proxy S. | **PROXY failure.** Median ratio (§2.2) is the mitigation already shipped. |
| F2 | In-kind create/redeem of a **custom** basket | Active ETFs (ARK especially) | AP delivers a non-pro-rata slice. `Q` of those names moves with `S` but not proportionally. | Unobserved. Looks like a PM add/trim. |
| F3 | Cash create/redeem | Active / thin baskets | Manager trades the cash; `Q` moves next day(s) while `S` moved today. | Timing false positive. |
| F4 | Settlement lag (T+1/T+2, FX, holidays) | Anything with non-US names | Snapshot day ≠ economic day. | Window length (5d vs 40d) is a blunt fix. |
| F5 | Corporate action (split, spin, ticker change, special dividend) | All | `Q` jumps; `S` may not. | Partial guards (`flow_split_*`). Tight on purpose after false splits deleted real decisions. |
| F6 | Cash / FX / derivative / receivable lines | Income, international, overlay | "Shares" are dollars or contracts. | **Filtered** (`is_non_equity_holding`). Residual risk: currency-shaped equity tickers (COP, PEN, EUR AU) — already a measured incident. |
| F7 | Options / covered-call roll | Class 7 | Equity sleeve static; option lines churn. Or the opposite. | Skip list exists; not a class flag. |
| F8 | Levered / inverse daily reset | Class 8 | Holdings are swaps; reset is not intent. | Not in universe (keep out). |
| F9 | Synthetic / FoF look-through | Class 9 | `Q` is another fund. Double count if both wrapper and underlying are in the panel. | Not modeled. |
| F10 | Index reconstitution / float adjustment | Class 5–6 | ΔQ_active is real but **not discretionary**. | Honest if labeled reconstitution; dishonest if labeled "manager bought." |
| F11 | Price-only weight change | Anyone using weights not shares | `w` moves when price moves even if `Q` and `S` are flat. | Share-based path avoids this. Weight-residual path does not. |
| F12 | 13F applying the ETF formula | Class 1–4 13F | There is no `S`. Scaling `Q` by anything is an invention. | Desk correctly does **unscaled** QoQ share diffs + book-weight context. |
| F13 | Inflows to an SMA/HF | Class 1–3 13F | New LP money scaled into existing names looks like "adds." | Unobserved. Book-weight *rank* is more robust than share counts. |
| F14 | Confidential 13F omission then reveal | 13F | A name "appears" in an amendment or next quarter that was held all along. | Amendment lane + `exclude_confidential_omissions`. |
| F15 | 13F-NT / late / missing filer | 13F | Treating missing as zero manufactures exits. | **Forbidden** in both desk and census (`notice_is_zero_portfolio: false`; missing ≠ zero). |
| F16 | Same-complex multi-vehicle | ARK family; adviser 13F + its ETF | ARKK and ARKW both "add" TSLA on the same create. Cross-fund consensus double-counts one decision. | Consensus `min_funds: 2` currently *rewards* this. Needs a complex key. |
| F17 | Share-class / CUSIP map change | 13F and ETF | GOOG/GOOGL, ticker reuse, CUSIP revision. | `share_class_equiv.yml` on the desk; ETF path is ticker-keyed. |
| F18 | Unit change / value column | 13F $ | 2022-12-31 thousands → dollars. Share diffs are invariant; $ diffs are not. | Read-time normalizer exists. |
| F19 | Put/call reported as shares | 13F | Option-equivalent shares look like equity. | Public census excludes put/call from equity actions. |
| F20 | Off-book shorts / hedges | HF 13F | Long add may be a short cover or a pair. | Unobserved. Class 4 exclusion is the blunt instrument. |

---

## 5. Lawful uses of the approximation (research/display)

Allowed, if labeled:

- **ETF reconstitution / selection residual** after a declared SO proxy, on class 5 vehicles, as a *theme membership / float-flow sensor*
- **ARK (class 1 vehicle) daily selection residual** after SO proxy, compared against the (not-yet-ingested) trade email as a future validation set
- **13F unscaled share diffs + book-weight + rank**, never scaled by a fake S, on class 1–3, as *descriptive* new/add/trim/exit

Not lawful:

- calling any of the above a buy/sell signal (`DNR:KILL-OWNERSHIP-BREAKAWAY`)
- applying the ETF formula to 13F
- treating missing filers as sellers
- fusing 13F ΔQ with insider / short / options into one sponsorship number

---

## 6. Cheapest next measurement (not a build)

If a later wave is allowed to capture one missing input, **true daily `S_f,t` for the dated-ETF and ARK universes** is the only term that converts the house proxy into the commission formula. ProShares `historical_nav.csv` is a free historical SO/AUM candidate for class 8 and a template. N-PORT is the official quarterly audit.

Do not start that capture from this census (PASS-0 §8): rights, Data OS routing, off-render R2 placement, own PR.
