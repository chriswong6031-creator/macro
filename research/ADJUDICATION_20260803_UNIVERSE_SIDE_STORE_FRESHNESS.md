# Adjudication 2026-08-03 — universe() side-store freshness (CTRA / TPH / TCNNF / CWEN-A)

Status: ADJUDICATED (Fable main loop, 2026-08-03; adversarial Opus review applied).
Sibling of `ADJUDICATION_20260803_ORCL_NAME_SCORE_FLATLINE.md` §3 chip item (2) and of
PR #4463 (us_calls ledger integrity). Scope: names that enter the nightly name-score
scan (`scripts/build_stock_library.py::universe()`) through NON-`data/stocks` sources
whose series are frozen. The ledger side is settled (#4441 `bar_asof` gate refuses
their stamps; #4463 rules "no further ledger fix warranted") — this PR fixes the
**scan/display admission** and the **collector silence** that let it happen.

## §0. Verdict

**The scan scored four names off dead series for weeks because two side-store
collector lanes fail silent at the symbol level, and `universe()` admits any
non-empty series regardless of tip.** Root causes are external symbol-level
provider failures (Yahoo returns nothing for specific live symbols); the in-repo
defect is that both lanes drop requested-but-unreturned symbols with zero
disclosure, and the scan then presents stale scores as live authority.

Fix shipped here (disclosure + demotion, never fail-dark, CSP-R1):
1. **Scan demotion** — a full rec whose own `asof` lags the library's max tip by
   more than the canonical 7 calendar days (`engine.name_score_grader._MAX_BAR_LAG_DAYS`)
   keeps its searchable page (honest `feed_stale` disclosure on page + JSON) but
   loses scoring authority: no board/profile/standout membership, no potential
   call. Self-healing: the day the feed resumes, full authority returns.
2. **Collector never-silent** — the yahoo per-ticker lane reconciles requested vs
   returned symbols per run; the breadth lane discloses current-constituent
   columns that are not refreshing; a store-tip audit covers every name the
   yahoo group is asked to maintain. All line-start `::warning` (annotation law).
3. **No price-basis mixing, no history pruning, no membership edits** (§4).

## §1. Receipts (all re-measured 2026-08-03 in this worktree @ 4867eb54fbb)

| Name | Source read by `universe()` | Tip | Depth | Route in |
|---|---|---|---|---|
| CTRA | `data/yahoo/CTRA.parquet` | **2026-05-07** | 715 rows | `stock_search.extra_tickers` (config.yml:2356) |
| TPH | `data/yahoo/TPH.parquet` | **2026-05-13** | 719 rows | `stock_search.extra_tickers` (config.yml:2503) |
| TCNNF | `data/yahoo/TCNNF.parquet` | **2026-07-17** | **19 rows** (stub) | `stock_search.extra_tickers` (config.yml:2496) |
| CWEN-A | `data/smallcap_breadth/_closes_cache.parquet` column | **2026-06-26** (cache overall tip 2026-07-31) | 753 obs | smallcap constituents AND-gate (build_stock_library.py:518-519) |

- CTRA/TPH were **born stale**: created once by the #1267 desk-universe backfill
  (`123b0aaebf9`, 2026-07-04) already carrying May tips, and never rewritten since
  (1 commit each, ever). TCNNF missed that backfill, was born as a 1-row
  incremental the next nightly (`b35bac058e9`), grew to 19 rows, froze at 07-17.
- All three are **in the current nightly fetch list** (`collectors/yahoo.py::all_tickers()`
  → 737 names; CTRA batch 5, TCNNF batch 6, TPH batch 7 at batch_size 80).
  Membership never churned (`git log -S`: single addition, 2026-07-04). The brief's
  membership-churn hypothesis is **refuted**.
- **Batch-shape census kills the batch-failure hypothesis**: per-batch store tips
  vs the group max (2026-08-02) show batches 5/6/7 fully fresh except exactly
  CTRA/TCNNF/TPH. This is symbol-level: yfinance returns nothing for these
  symbols while their batch neighbors advance nightly. Direct probe: TCNNF →
  yfinance "possibly delisted; no price data found". Same-class finds: `K`
  (requested nightly, **no store file ever**), `FI`/`MMC` (no yahoo file AND
  never-populated breadth columns while sitting in breadth constituents),
  `RGI` (frozen 07-17), `CNH=X` (frozen 07-10, the one name `stale_series` can see).
- **Why silence was structural** (`collectors/yahoo.py`): `_extract()` drops a
  symbol absent from the batch response via `except KeyError` (log-only);
  `run_adapter()` and `detect_stale_series()` iterate only returned `frames` — a
  never-returned symbol is invisible to both (the mechanism that froze `_GSPC`
  for a month, per the module's own docstring); the only aggregate guard is the
  70% floor (`fetch()` raises only if >30% of the whole run vanishes). The
  store-tip tripwire `check_yahoo_freshness()` audits a hardcoded 3-name tuple
  (`^GSPC, SPY, ^VIX`).
- **CWEN-A** (`collectors/breadth.py`): Wikipedia S&P 600 membership lists BOTH
  Clearway classes since collector inception (2026-06-13) — no membership event.
  The class-A symbol went dead at Yahoo on **2026-06-26 (Russell-recon day;
  sibling CWEN advances daily in the same batches)** after one earlier
  stall-and-heal (06-18→06-26). `_merge_refreshed()`'s `fresh.combine_first(cached)`
  then carries the frozen column forward every night, indistinguishable from a
  departed name. Across all four breadth groups, 40 frozen columns exist and 22+10+7
  are correctly excluded by the constituents AND-gate — **CWEN-A is the single
  in-constituents leak** (plus FI/MMC as never-populated in-constituents columns).
- `data/yahoo` and the S&P-trio breadth caches are **git-tracked and NOT in the
  R2 restore set** — repo tips are the real runtime tips.

## §2. What the brief got wrong (re-measured per house law)

The brief cited a sibling "fix(stocks): retention fetch + per-name freshness
audit" PR as landed. **No such PR exists at HEAD** (merged or open). What exists:
#4441 (merged — ledger admission gate + echo quarantine) and #4463 (open —
group-level universe disclosures + Russell cache-restore parity). The
`data/stocks` collector staleness (QCOM/HOOD/MRVL/CVNA/HON/WDC/SATS,
`collectors/sector_holdings.py` top-20 union) remains **unfixed at HEAD** and
stays out of scope here (different lane/files; chipped again below). The
membership-churn framing ("refresh list vs union read") was also wrong for these
names — membership is intact; the provider went silent per-symbol.

## §3. Rulings

- **R1 (admission = demote, never delete; PROMOTION-tier gate only).** A name
  whose only source is frozen must not carry live scoring authority (rank, board,
  standout, potential call) — but deleting it from the library would be fail-dark
  for search and existing deep links (CSP-R1). Demote: page + search entry stay,
  `feed_stale {behind_days, lib_asof}` disclosed on the page and in the JSON,
  authority stripped. Threshold: strict > 7 calendar days behind the library's
  own max tip — the SAME 7-day constant as the ledger gate (import
  `_MAX_BAR_LAG_DAYS`) but a self-relative reference (library max tip), which is
  strictly LOOSER than the ledger gate's wall-clock stamp — safe direction, and
  deliberately free of calendar dependency at admission. Crypto's 24/7 tip leads
  the max on weekends, so the realistic equity headroom before a false demotion
  is ~3 calendar days on the worst holiday-weekend build, not 7. Self-relative
  blindness to a TOTAL freeze (every feed frozen together, tip frozen with them)
  is closed by a separate wall-clock DISCLOSURE (never a gate): a ::warning when
  the library tip itself, or a collector audit's ref tip, is >7d behind today.
- **R2 (mass-staleness circuit breaker — the gate must not fail-dark either).**
  If >20% of full recs would demote, the demotion DISARMS for that run with a
  loud `::warning` (a universe-wide freeze is a collector outage; blanking the
  boards would be fail-dark — partial output beats shipping nothing, CSP-R1).
  Disclosure still prints. Unusable/unparseable `asof` on a rec → fail-open for
  that rec + counted in a "gate DARK" warning (mirrors #4441 semantics).
- **R3 (CWEN-A stays itself).** CWEN-A is a distinct listed security on its own
  price line. It is NOT collapsed into CWEN for pricing
  (`config/share_class_equiv.yml` is 13F-consensus-only) and its series is NOT
  re-sourced — **no silent price-basis mixing**. Mechanically: demoted while
  frozen (R1); fully retires the day upstream membership drops it (constituents
  wholesale rewrite + AND-gate); fully heals the day Yahoo resumes the symbol.
  "Maintained-or-consciously-retired" is achieved by mechanism, not by a
  hand-curated retirement list.
- **R4 (collectors must be never-silent, not never-failing).** The union-forever
  breadth cache is a FEATURE (survivorship-honest archive for replay/backtest
  readers) — do not prune history. The yahoo per-ticker fetch keeps its 70%
  aggregate floor. What ships is disclosure: per-run requested-vs-returned
  reconciliation (yahoo), current-constituent stale/empty column report
  (breadth), and a store-tip audit across everything `all_tickers()` maintains.
  Heal path for the three extras: nightly 1mo fill the day the provider resumes;
  depth heal (TCNNF's 19-row stub) via the existing manual
  `backfill.yml --full-history --only yahoo` dispatch once symbols resolve —
  NOT by hand-written parquets from a task PR (seed script uses an adjusted
  basis; the nightly lane is `auto_adjust=False` — mixing bases inside one
  series is the #2120 seam-defect class).

- **R5 (accepted residual — cohort population shift, adversarial-review M4).**
  Removing demoted names from `profiles` shrinks the within-market percentile
  cohort and the conviction-accrual archive's per-basket n/median with no era
  marker in those artifacts. At current scale (4 names of ~1,500) this is noise,
  the 20% breaker caps the blast radius, and the nightly `::notice` prints the
  demotion count as the log-side marker. RULED accepted rather than built:
  stamping an era marker into the pre-registered accrual ledger's schema from a
  hygiene PR is the worse trade. Revisit trigger: any night the demotion count
  exceeds a handful, the accrual study owner adds the era break.

## §4. Boundaries honored / deliberately NOT here

- **No ledger changes** (#4441/#4463 own that layer; the scan-side authority
  strip means no call is even assembled for a demoted name — belt AND the
  grader's existing suspenders).
- **No `universe()` body edits** — #4463 (open, merge-on-green) owns that region;
  demotion happens post-workers in the serial rec loop, and composes with
  #4463's group-level annotations.
- **No data/ writes, no membership edits, no cache pruning, no re-sourcing.**
- **Chipped, out of scope:** (1) `data/stocks` collector retention fetch
  (QCOM/HOOD/MRVL/CVNA/HON/WDC/SATS still stale at HEAD — the load-bearing
  upstream defect named by #4441 §3, still unbuilt); (2) symbol-level
  resolution for the refused names — #4622 (open) established these are often
  **retired-symbol renames** (FI→FISV, MMC→MRSH; K = Kellanova delisted via the
  Mars close): CTRA and TPH must be resolved against the NASDAQ symbol
  directory + OpenFIGI CUSIP per the #4622 protocol (a rename is a KEY
  MIGRATION, never an in-place refetch) — until resolved, this PR's demotion
  keeps them honest; page copy is deliberately cause-neutral ("no new data
  since X") because stale-vs-delisted-vs-renamed is NOT established per name
  (#4616 law: delisted is not stale); (3) the ~19 other breadth-cache readers
  (factor panels, sector map, chart data, …) that read frozen columns with no
  freshness gate — same class, separate program.

## §5. Receipt appendix

- Per-batch census (store tip vs group max 2026-08-02): batches 0–9 → stale
  counts 0,1,1,0,0,1,1,1,0,0; missing-file: FI+MMC (batch 3), K (batch 5).
- CWEN-A cache timeline via git blobs: 06-25 snapshot tip 06-18 (stall),
  06-27 snapshot healed to 06-26, 06-30 snapshot frozen at 06-26 with 773 obs,
  live file 753 obs (rolling-window front-trim only — zero new rows since).
- Frozen-column census (10-day rule): breadth 7 (2 in-constituents: FI, MMC —
  0 obs ever), smallcap 23 (1 in-constituents: CWEN-A), midcap 10 (0
  in-constituents), russell cache CI-runner-only (absent in bare checkout).
