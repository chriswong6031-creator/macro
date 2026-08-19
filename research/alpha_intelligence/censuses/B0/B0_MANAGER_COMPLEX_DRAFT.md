# B0 — Manager-complex draft (data-only)

**Lane:** GROK-B0 · **Date:** 2026-08-18 · **Pin:** `3d12412e561e`
**This is not a scoring scheme.** No weights, no grades, no promotion. It is a map of *distinguishable economic objects* so later B work does not treat Citadel, ARKK, Vanguard, and Baker Bros as the same 13F row.

**Adopt, do not replace:** `config.yml::smart_money.funds[].style`, `config/institutional_13f.yml` `research_bench.exclude_manager_classes`, and the SM2-R6 exclusion comment.

---

## 1. Object model (data only)

A **complex** is the economic decision-maker we want to talk about.
A **filer** is a CIK that signs a 13F.
A **vehicle** is a fund/SMA/ETF/share class that publishes holdings or trades.
A **book line** is `(vehicle, instrument, as_of)` with shares and/or weight.

```
complex 1---* filer (CIK)
complex 1---* vehicle (ETF ticker, 13F-only SMA, mutual fund)
vehicle  1---* book line
filer    1---* 13F accession
vehicle  0---1 registered-fund N-PORT / daily holdings file
```

**Identity keys (proposed, not frozen):**

| Key | Source | Notes |
|---|---|---|
| `cik` | 13F cover | Filer, not complex |
| `related_ciks[]` | 13F OTHERMANAGER / OTHERMANAGER2 + Form ADV related persons | Census already parses both relationships (`reported_by`, `included_managers`) |
| `crd` / `lei` | Form ADV | UNKNOWN whether house stores these |
| `vehicle_ticker` | sponsor / N-PORT | ARKK ≠ ARK Investment Management 13F |
| `complex_id` | house-assigned, frozen per quarter | Required to stop "today's famous name" survivorship |

**Standing law already in-tree:** do not auto-promote a census filer onto the featured desk (`may_auto_promote_featured_funds: false`).

---

## 2. Nine classes the commission asked to distinguish

These are **vehicle-level** first, then rolled to the complex only when every material vehicle shares the class. A complex that runs both an index ETF and a concentrated SMA is **mixed** and must stay mixed.

| # | Class | What the 13F / holdings file *is* | What ΔQ_active would mean | House prior art | Example complexes (illustrative, not a roster expansion) |
|---|---|---|---|---|---|
| 1 | Concentrated discretionary active | High-conviction longs; few names; 13F ≈ the public sleeve of the idea | Initiation / add / trim / exit is the object | `smart_money` styles: `superinvestor_value`, `activist`, `quality_growth` (Akre, TCI, Polen — quality is still concentrated-ish) | Berkshire, Pershing, Baupost, TCI, Appaloosa |
| 2 | Diversified discretionary active | Many names, still human/PM selected; 13F is a diluted idea tape | Only top-of-book or size-thresholded lines are interpretable | `tiger_crossover` often lands here (Viking, Lone Pine) | Viking, Durable, Egerton |
| 3 | Sector-specialist active | Book is a sector by mandate; initiation inside the sector ≠ "we discovered healthcare" | Within-theme rotation is the object; entry into a name is comparable only to sector peers | `sector_healthcare`, `sector_other` | Baker Bros, RA Capital, Perceptive, RTW, Casdin, Kimmeridge, Basswood |
| 4 | Systematic active | 13F is a factor/stat-arb/inventory residual, not a thesis | Almost never an "intent" | SM2-R6 exclusions: RenTech, Citadel, Millennium, Two Sigma, DE Shaw, Jane Street, SIG. Census `exclude_manager_classes: [quant_market_maker, …]` | Those names — **keep excluded from consensus** |
| 5 | Thematic passive / index | Rules-based theme basket; daily holdings exist | ΔQ_active = reconstitution / float / corporate-action, **not** a PM call. Still useful as a *theme membership sensor* | `etf_holdings` universe design (sector/thematic only; SPY/QQQ excluded on purpose) | Global X LIT/BOTZ, SSGA Kensho, VanEck SMHX |
| 6 | Broad passive / index | Cap-weight or broad style box | ΔQ_active is mechanical. House already refuses to put SPY/QQQ/DIA/MDY/RSP on the conviction board | Vanguard unsupported; iShares blocked; Invesco QQQ collected but should stay class 6 | SPY, VTI, QQQ, IWM |
| 7 | Options / income overlay | "Holdings" include calls, covered-call overlays, option income ETFs | Share diffs on the equity sleeve mix overlay rolls with equity intent | Roundhill MAGS/QDTE/*W already skipped as messy; class must be first-class so they are not scored as class 1 | QYLD, XYLD, many Roundhill / Defiance products |
| 8 | Leveraged / inverse | Daily reset; holdings are swaps/T-bills/futures | Share diffs are not PM conviction | ProShares candidate feed; not in current universe (good) | SSO, SH, TQQQ, SQQQ |
| 9 | Synthetic / fund-of-funds | Look-through is another fund or a swap on an index | 13F/holdings of the wrapper double-count the underlying | N-PORT + "fund of funds" lines; included-manager 13F relationships | Some liquid alts, some buffer ETFs, some 13F "other manager" combos |

---

## 3. Mapping the live featured roster (data only)

Source: `config.yml::smart_money.funds` (51 slugs, 51 unique CIKs). **CODE VERIFIED this session.**

| House `style` | Count (active unless noted) | Draft class (provisional) | Why |
|---|---|---|---|
| `superinvestor_value` | 13 active + Scion closed | 1 (concentrated discretionary) | Low turnover_hint; public sleeve is the idea |
| `activist` | 10 | 1, with 13D as a *better* clock than 13F | Pershing, Third Point, ValueAct, Icahn, Elliott, Starboard, Trian, JANA, Engaged, Sachem, Corvex (11 if Third Point counted here — config says activist) |
| `quality_growth` | 6 | 1 or 2 depending on name count | Akre, TCI, Egerton, AKO, Polen, Durable |
| `tiger_crossover` | 9 | 2, sometimes 1 (Coatue/Altimeter can look concentrated in a theme) | Lone Pine, Tiger Global, Viking, Coatue, D1, Altimeter, Whale Rock, Dragoneer, Light Street |
| `event_distressed` | 3 | 1, credit-aware | Appaloosa, Oaktree, Mudrick — 13F misses the credit book |
| `sector_healthcare` | 5 | 3 | Baker Bros, RA Capital, Perceptive, RTW, Casdin |
| `sector_other` | 2 | 3 | Kimmeridge (energy), Basswood (financials) |
| `macro_satellite` | 2 | 1 public sleeve + large off-13F book | Duquesne, Soros — **13F is a satellite, not the strategy** |

`status: closed` already on Scion. Adjudication comments also drop avenue/silverpoint (stale), fundsmith (no 13F), tudor/moore (macro noise), melvin (closed). Those belong in the ontology as **historical / non-comparable**, not as missing data.

---

## 4. Classification inputs that already exist vs still missing

| Input | Exists? | Use |
|---|---|---|
| CIK + legal name | Yes | Filer key |
| House `style` / `turnover_hint` | Yes, featured desk only | Seed labels for class 1–3; not for the 8k filer universe |
| 13F OTHERMANAGER / OTHERMANAGER2 | Yes, census parser | Parent/affiliate / combination reports |
| `exclude_manager_classes` | Yes, research bench | Passive, quant_MM, custody, bank, insurer, pension |
| Name-count / HHI of the book | Computable from census holdings | Separate class 1 from class 2 **without** a human style tag |
| Turnover of shares QoQ | Computable after intent norm | High turnover + huge book → class 4 suspect |
| Vehicle has a daily holdings URL | Yes, etf_holdings registry | Class 5–8 |
| Vehicle is leveraged/inverse/options | Partial (skipped tickers, not a field) | Need an explicit vehicle flag |
| Form ADV strategy text | No house owner found | Candidate identity input, not a holding |
| PM person identity | Featured names are in the `name:` string only | Do not build a people graph in B0 |

---

## 5. Rules that keep this data-only

1. A class label is a **description of the publication**, not a quality score.
2. Class 4 and class 6 rows may appear in the universal evidence plane and **must not** enter featured-desk consensus or crowding counts (already the SM2-R6 law).
3. Class 5 ΔQ_active is a **reconstitution sensor**, lawful as display/research, not as "the manager bought."
4. Class 7–9 are **false-positive factories** for any share-diff intent model. Tag them before computing ΔQ_active.
5. Same-complex multi-vehicle (ARKK+ARKW+ARKG, or a 13F adviser + its ETF) is a **dedup key**, not extra conviction. See casebook "same-manager multi-fund duplication."
6. Do not freeze this ontology until #5822 China institutional masterplan is reconciled (CN public-fund / southbound / LHB are different objects).
7. No auto-promotion from class membership to the featured desk.

---

## 6. What this draft deliberately does not decide

- How many names is "concentrated"
- Whether Coatue is class 1 or 2
- Any weight for "specialist"
- Whether class 3 should get a different Prophet family later (that is K5 / Eval OS, not B0)
