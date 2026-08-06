# CN flow/positioning ex-ante battery — which unwired stores separated losers at admission?

**Instrument:** `research/cn_prophet_audit/flow_exante_battery.py`
**Frozen result:** `research/cn_prophet_audit/flow_exante_battery_results.json`
**Frame:** the audited 407-episode V1 loser frame (`v1_loser_audit_results.json`), 342 tickers,
**12 admission dates**, 2026-06-30 → 2026-07-17. Base loser rate **31.4%** (`excess ≤ 0`, CSI300-relative).
**Method:** mirrors `sector_intel_exante_test.py` — PIT join at each episode's admission date, per-bucket
`n` / `loser_rate` / `median_excess`, extended with Wilson 95% CIs, thin-cell labels, and a date-demeaned
column. Single-axis only. **No composite scoring, no multi-store blending** — that is a later prereg.

**This is an evidence layer, not a promotion.** Nothing here moves any signal to rank/size/gate authority.

---

## 0. Decision-relevant summary (ranked)

> **The headline: of the six purpose-collected flow/positioning stores, ZERO produced a testable
> separating axis on this frame. The only axis that separated is derived from the price/volume plane
> we already collect for free.** Four stores cannot be joined PIT at all. The 龙虎榜 store — the priority
> store, the one that directly addresses the relay-bimodality question — is coverage-starved to the point
> of being unanswerable, which is a *collection* verdict, not a null.

| # | Axis | Store | Verdict | Δ loser rate | Reads |
|---|---|---|---|---|---|
| 1 | `turnover_pctile_60d` | `china_stocks` (volume-derived) | **SEPARATES** | **+24.8pp** | admission-day volume ≥p90 of own 60d → 42.5% losers vs 17.7% below median. Monotone across all three buckets, survives date-demeaning, full 407 coverage |
| 2 | `volume_ratio_20d` | `china_stocks` (volume-derived) | **SEPARATES** | +23.5pp | same crowding leg, second cut — **not an independent store** |
| 3 | `margin_balance_change` (sign, tercile) | `china_margin_detail` | NULL | +8.4pp / +0.9pp | n=333. Rising margin balance is *directionally* worse but CIs overlap and the spread vanishes on date-demeaning (−0.12) |
| 4 | `holder_count_change` (sign, tercile) | `china_holder_counts` | NULL | −8.2pp / −5.3pp | n=339. "Chips concentrating" is directionally **worse**, not better — anti-folk-thesis, consistent raw and demeaned, but CIs overlap and the disclosure lags a median 99 days |
| 5 | `lhb_appeared` (3d, 10d) | `china_lhb/events` | NULL (underpowered) | +14.3pp / +18.3pp | only 20 / 31 of 407 episodes have any LHB event in window. Prior-killed construction, replication only |
| 6 | LHB net-buy sign / magnitude / reason-class / inst-seats | `china_lhb` | **UNUSABLE (coverage)** | — | 20–31 episodes (events), 27 (inst detail) vs a 40-episode floor |
| 7 | northbound, block trades, buyback, market-margin | 4 stores | **UNUSABLE (no PIT join)** | — | see §4 — this list is the data-collection to-do |

**Counts:** 16 features tested → **2 SEPARATES, 6 NULL, 8 UNUSABLE**. 4 stores unusable outright.

### What this earns

- **`turnover_pctile_60d` earns a display chip and a shadow lane** — it is the only axis that cleared the
  bar, it is fully covered, monotone, and (see §3) *not* a restatement of anything the pick chain already
  consumes. It is also the cheapest possible signal: it needs no new collection.
- **Nothing else earns anything yet.** The flow stores are not falsified here — most of them were never
  *askable*. Do not read the NULLs as kills; read the UNUSABLEs as a build queue.
- The direction of the one live result — heavy admission-day volume predicts losers — is consistent with
  the dormant zt/连板 chase-veto already noted in the masterplan (`assert_zt_not_positive`), and with the
  house rule that limit-up chase is a veto and never a positive rank.

---

## 1. Prior kills honored (mandatory first step)

Grepped `research/` + `reports/` and read `research/DO_NOT_REBUILD.md` before designing any axis.

| Prior verdict | Source | How this battery complies |
|---|---|---|
| **Raw LHB hot-money appearance flag — FALSIFIED (wrong sign, −1.43%/21d)**; only the inst-seat ≥2 accruing construction survives | `CHINA_PICK_LAB_MASTERPLAN_BY_FABLE.md:209`, `ENGINE_FIX_MASTERPLAN.md:167-168`, `QUALITATIVE_SIGNAL_CHINA_AUDIT_FOR_FABLE.md` F1 | The appearance flag is **not re-tested as a hypothesis** — it is carried as a row explicitly tagged `prior_killed_construction: true`, replication/context only. The **new** axes are net-buy *sign*, net-buy *magnitude*, *institutional-seat composition* (`cnlab_lhb_inst`), and **admission-reason class** (up-deviation vs down-deviation vs turnover vs amplitude) — none previously tested |
| **Block-trade PREMIUM flag — demoted wrong-sign (−0.60%/5d)**; deep-DISCOUNT leg probationary (+3.45%/21d) | `ENGINE_FIX_MASTERPLAN.md:167-168` | Moot — the store is UNUSABLE (snapshot-only, §4). Neither leg is tested |
| **`cn_supply_absorption` family (incl. D4-01b) — CLOSED**; price-only absorption ≡ momentum | `DO_NOT_REBUILD.md:105`, `reports/d4-cn-supply-absorption-phase0.md` | No absorption construction is tested anywhere in this battery |
| **`d2_cn_holder_sale_calendar` — DIRECTIONAL FAIL (anti-hypothesis)**; 减持 execution windows show *positive* excess; display-only, positive-direction hypotheses need fresh prereg | `reports/d2-cn-holder-sale-phase0.md`, Fable ruling | The holder axis here is the **holder-COUNT disclosure** (`china_holder_counts`, 股东户数), a different store and a different construction from the 减持 sale calendar. No 减持-window axis is tested |
| **`f501_cn_block_sector_readthrough`** phase-0 exists on the LG-CN-SUPPLY lane | `reports/f501-block-sector-readthrough-phase0.md` | No sector-readthrough construction is tested; this battery is name-level only |
| **`slf051_cn_margin_impulse`** — R3-legal de-escalation/conditioning gate, no escalation fused | `reports/slf051-cn-margin-impulse-phase0.md` | The margin axis here is a **per-name balance change**, not the market-level impulse gate. Reported as a separation measurement, never as an escalation |
| Northbound net flow / margin velocity / raw LHB **falsified as standalone TIMING signals** | `A_SHARE_MARKET_MECHANICS_AND_CHINA_SYSTEM_UPGRADE_FOR_CLAUDE.md:50` | **This is not a timing test.** It is a conditional loser-separation test *inside an already-admitted candidate pool* — a different construction. Per house epistemics, a standalone null is retained as a confluence input, so measuring it at display tier is lawful |

---

## 2. The one axis that separated

**`turnover_pctile_60d`** — admission-day volume percentile vs the name's own trailing 60 sessions.
Fully PIT (uses only bars dated ≤ admission). Coverage 407/407.

| bucket | n | loser rate | Wilson 95% | median excess | date-demeaned |
|---|---|---|---|---|---|
| `p0_50` | 96 | **0.177** | [0.114, 0.265] | +5.98 | +2.81 |
| `p50_90` | 205 | 0.322 | [0.262, 0.389] | +4.72 | +0.63 |
| `p90_100` | 106 | **0.425** | [0.335, 0.520] | +1.70 | **−1.88** |

Monotone in all three columns. Extreme-bucket Wilson CIs are disjoint (0.265 < 0.335). The
median-excess spread is −4.28 raw and **−4.69 after date-demeaning** — it does not depend on the
admission-date effect. The top decile of a name's own volume distribution is the only place in this
battery where median date-adjusted excess goes **negative**.

`volume_ratio_20d` (admission-day volume ÷ own 20-session median) is the same leg cut differently:
low 22.1% losers vs high 45.6%, Δ +23.5pp, demeaned spread −3.63. It is reported for robustness, **not**
as independent evidence.

### Verdict rule (pre-stated, applied identically to all 16 features)

`SEPARATES` requires **all three**: (a) both compared buckets `n ≥ 15`; (b) Wilson 95% loser-rate CIs
disjoint; (c) the median-excess spread keeps its sign after date-demeaning. Anything else is `NULL`.
`UNUSABLE` = coverage < 40 episodes, or the store admits no PIT join.

---

## 3. Is the crowding axis just something we already consume?

A separating axis that merely re-states an existing engine field earns no chip. Checked (frozen in the
JSON as `redundancy_check`; a validity check, **not** a blend):

- `corr(turnover_pctile, day0_ret)` = **0.261** — weak; not a restatement of the day-0 move.
- `corr(turnover_pctile, setup)` = **0.172** — weak; not a restatement of the engine's own setup score.
- The engine's `extended` veto fires on **9 of 407** episodes — effectively dormant.
- Inside the non-extended subset (n=398) the gradient is intact: **0.160 → 0.320 → 0.416**.

**Reading: the axis carries information the chain does not currently consume.** The one genuine overlap
is with the washout leg — washout admissions arrive on heavier volume (mean pctile 0.794 vs 0.665) — so
any wiring must be specified against `washout`, not on top of it.

---

## 4. UNUSABLE stores — the data-collection to-do

This list is itself a deliverable. None of these is a null; each is a store that cannot be asked the
question at all.

**1. `data/china_connect/northbound.parquet` — DEAD + wrong granularity.**
No per-name dimension exists (columns are market-level `net`/`buy`/`sell`/`turnover`/`hold_mktcap`), **and**
the series is a frozen placeholder: `net` has **zero non-null values after 2024-08-16**, i.e. it is null
across the entire admission window (51 window rows, 0 non-null). This confirms the standing
`CHINA_ENGINE_PROBLEM_BRAINSTORM` finding that northbound is a dead placeholder still assembled into the
feature frame.
*To-do:* collect per-name 沪深港通持股 holdings; separately, un-freeze the market-level feed (~2 years dead).

**2. `data/china_block_trades/detail.parquet` — SNAPSHOT-ONLY, look-ahead by construction.**
330 rows carrying a **single `asof=2026-08-03`** — observed *after* every episode's admission
(2026-06-30…2026-07-17), with no accruing history. `data/china_block_tape/` does not exist. A PIT join is
impossible; an as-is join would leak.
*To-do:* convert the collector from snapshot-overwrite to **append-only daily accrual** (per-trade date +
premium/discount). Until then the probationary deep-DISCOUNT leg (+3.45%/21d, t≈3.4 — the best
northbound replacement found) **cannot be tested on any historical frame**. This is the highest-value
collection fix in the list.

**3. `data/china_buyback/buyback.parquet` — SNAPSHOT-ONLY, no disclosure date.**
5,436 rows, single `asof=2026-08-03`, and the only temporal field is a mutable `progress` string
(`完成实施`/`实施中`/`董事会预案`). **No column records when a program became known**, so a program announced
after admission is indistinguishable from one active before it.
*To-do:* collect the announcement date (公告日) plus status-transition dates, append-only. **One column
makes this store testable.**

**4. `data/china_margin/balance.parquet` — market-level, not a name axis.**
No ticker dimension. Across 12 admission dates it is a date-level constant, indistinguishable from the
admission-date effect. *No to-do* — it is correctly market-level; use as regime context, never as a name
feature.

**5. `data/china_lhb/*` — PIT-safe but coverage-starved (the priority store).**
This is the important one. The store *is* append-only and *is* joinable PIT, but on this frame:

| axis | window | episodes covered | floor |
|---|---|---|---|
| net-buy sign / magnitude / reason-class | trailing 3 sessions | **20** / 407 | 40 |
| net-buy sign / magnitude / reason-class | trailing 10 sessions | **31** / 407 | 40 |
| institutional-seat composition (`detail`) | latest PIT snapshot | **27** / 407 | 40 |

The 10-session cut was run *only* to establish whether the store is testable at all (a coverage question,
disclosed; both windows are reported and neither was selected on its result). It is not.
`china_lhb/detail.parquet` — the only file carrying `inst_net_buy_yi` / `n_inst_buy` / `n_inst_sell` —
accrues from 2026-07-01 and covers just 10–18 episode tickers per snapshot.

**Consequence: the relay-bimodality question — *who bought the limit day* — is not answerable on the V1
frame.** That is a collection verdict, not a null. Reaching the 40-episode floor requires either a longer
episode frame (the V1 era is 18 calendar days) or broader LHB snapshot coverage.

---

## 5. NULLs (printed, not hidden)

**Margin (`china_margin_detail`, n=333).** Rising margin balance is directionally worse (33.7% vs 25.3%
losers) but Wilson CIs overlap and the demeaned spread is −0.12 — essentially zero.
**The briefed 5/20-session margin velocity does not exist in this store**: it carries only a paired
`(date, prior_date)` delta with a **~29-day gap**, so the tested axis is a *monthly* balance change,
disclosed as such. A true 5/20-session velocity needs the accruing per-`asof` series, which begins
2026-07-01 and is therefore shorter than the trailing window for most episodes.

**Holder counts (`china_holder_counts`, n=339).** PIT rule applied strictly: only records whose
**`notice_date` ≤ admission date**. Result runs *against* the folk thesis — "chips concentrating"
(holder count falling) shows a **higher** loser rate (35.2% vs 27.0%), and the direction is consistent
raw and demeaned (+0.69 → +1.28 median excess in favour of *dispersing*). It is nonetheless a clean
NULL: the Wilson CIs overlap ([0.283, 0.427] vs [0.210, 0.341]). Directionally interesting, not
resolvable here, and **not** offered as a reversal finding.
**Disclosure lag is severe:** median **99 days** between the reported period end and the admission date
(n=339) — the "positioning" is up to a quarter stale by construction.

**LHB appearance (replication row).** Directionally consistent with the known wrong-sign drain
(45.0% losers at 3d, 48.4% at 10d, vs a 31.4% base), but n=20/31 makes the CIs uninformative
([0.258, 0.658] and [0.320, 0.652]) and most of the raw penalty dissolves under date-demeaning
(−3.10 → −0.57 at 3d). **This neither confirms nor challenges the prior kill** and is not offered as
evidence either way.

---

## 6. Honesty ledger

- **One era, in-sample.** 18 calendar days, 12 admission dates. No out-of-sample split exists on this
  frame. Nothing here is validated in the CI-guarded sense of that word.
- **Heavy date clustering.** 407 episodes on 12 dates. Every spread is reported raw *and* date-demeaned,
  and the verdict rule *requires* survival of date-demeaning — but 12 dates is still 12 dates.
- **No multiplicity correction.** 16 features tested. A `SEPARATES` verdict is a display-tier candidate
  and a shadow-lane nomination, nothing more.
- **Per-store disclosure lags** are stated inline in §4/§5 and in each feature's `note` field in the JSON.
- **No promotion claim.** No axis is ranked, sized, or gated on the strength of this document.
- **Correlated cuts are labeled.** `volume_ratio_20d` is the same leg as `turnover_pctile_60d`; the two
  `SEPARATES` verdicts are one finding, not two.

## 7. Reproduce

```
python3 research/cn_prophet_audit/flow_exante_battery.py   # ~8s, writes the frozen JSON
```
