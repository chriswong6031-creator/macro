# CN TuShare full-A spine contract — 2026-08-08

Status: foundation-only; synthetic verification complete, no live vendor request or bulk backfill.
Authority: `context_only` — data/universe infrastructure, never a signal or promotion.
Collector: `collectors/china_tushare_spine.py`
Manifest schema: `contracts/cn_tushare_a_share_spine_manifest.v1.schema.json`

## Purpose and stop-ship boundary

The existing A-share cache is a curated, split-adjusted subset. It cannot support
a survivorship-honest full-market verdict or an exact historical legal-ceiling
claim. This collector is the replacement substrate: point-in-time SH/SZ/BJ
identity and lifecycle, exact sessions, unadjusted nominal daily quotes, vendor
daily price limits, suspensions, daily indicators, ST state, and effective names.

**TuShare licensing/compliance: `CHAIRMAN_VERIFIED_PRIVATE / SATISFIED`.** The
controlling agreement and supporting evidence are confidential and outside
coding/agent scope under NDA/privacy constraints. No coding session or runtime
gate may request or verify those documents
(`DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE`, 2026-08-21, which
nulls the former written-grant/receipt/trust-allowlist requirement this contract
previously carried). DEP-EXACT gates only on independently technical exact-plane
correctness, access operation, canary, range-campaign and completeness
requirements. Until the live canary runs and the scalable cap plan is reviewed,
this lane is `foundation_only_range_shards_synthetic_no_live_canary` on that
technical evidence alone.

The Wave-0 Yahoo-derived 71,692-event artifact remains incompatible with exact
legal-limit strategy claims: its nominally “raw” prices are split-adjusted and its
reconstructed limits used binary/ties-to-even rounding. Do not merge its verdicts
with this plane or promote them as exact-limit evidence.

## Official contracts pinned

All links are primary TuShare or exchange documentation checked 2026-08-08/09.

| Endpoint/rule | Contract used | Collector consequence |
|---|---|---|
| Endpoint access/quota | vendor account tier | Ordinary access, entitlement and quota observation only. Compliance itself is settled privately (see above) and is never a runtime gate here. |
| `stock_basic` | <https://tushare.pro/document/2?doc_id=25> | SSE/SZSE/BSE × L/D/P/G; exact exchange/status, CNY, A-market, symbol/code checks; 6,000 cap. |
| `fund_basic` | <https://tushare.pro/document/2?doc_id=19> | Exchange-fund identities are independent `known_out_of_scope` witnesses, not silently discarded rows. |
| `bse_mapping` | <https://tushare.pro/document/2?doc_id=375> | Old BJ aliases must map to a canonical `920xxx.BJ` code; 1,000 cap. |
| `trade_cal` | <https://tushare.pro/document/2?doc_id=26> | Exact exchange/range/day response; SSE and SZSE must have identical open-session sets. |
| `bak_basic` | <https://tushare.pro/document/2?doc_id=262> | Exact-date historical stock-list witness from 2016; 7,000 cap. Pre-2016 stays an explicit gap. |
| `namechange` | <https://tushare.pro/document/2?doc_id=100> | Active year is refreshed to the actual end-date anchor; announcement dates must stay inside the request. A valid row is its own source evidence and lands with or without an external witness; only malformed keys, non-A identities, contradictory lifecycle intervals and unresolved same-day name conflicts block. |
| `daily` | <https://tushare.pro/document/2?doc_id=27> | Direct unadjusted nominal OHLCV, exact date, 6,000 cap; on cap the endpoint's requested interval switches to the bounded ticker×date-range campaign (amended 2026-08-13), correctness-tested synthetically and still gated. |
| `daily_basic` | <https://tushare.pro/document/2?doc_id=32> | Exact date/ticker; 6,000 cap; `limit_status` domain 0–6 and close/limit semantics are audited. |
| `stk_limit` | <https://tushare.pro/document/2?doc_id=183> | Exact source pre-close/up/down limits; 5,800 cap; non-A rows require independent exclusion or quarantine. |
| `suspend_d` | <https://tushare.pro/document/2?doc_id=214> | Successful empty days are checkpointed; only a full-day `S` with no timing explains a missing daily row. |
| `stock_st` | <https://tushare.pro/document/2?doc_id=397> | Exact daily ST membership from 2016-01-01; pre-2016 name inference remains partial. |
| SZSE 2026 Trading Rules | <https://docs.static.szse.cn/www/lawrules/rule/trade/current/W020260424690713155663.pdf> | CNY 0.01 tick and 四舍五入; one-tick separation/floor in the validator. |
| SSE 2026 Trading Rules | <https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml> | Current exchange rule provenance pinned alongside SZSE. |

`pro_bar` is not used. A calculated band is never substituted for `stk_limit`.

## Compliance status and the surviving pre-network gates

**TuShare licensing/compliance: `CHAIRMAN_VERIFIED_PRIVATE / SATISFIED`.** The
controlling agreement and supporting evidence are confidential and outside
coding/agent scope under NDA/privacy constraints. No coding session or runtime
gate may request, upload, inspect, persist, hash, quote, or re-verify those
documents, and no public-terms reading may reopen the question
(`DEC:CNLI-TUSHARE-COMPLIANCE-IS-CHAIRMAN-VERIFIED-PRIVATE`).

The former `--authorization-receipt` / `--authorization-trust-allowlist` receipt,
grant-document hash, entitlement chain, and code-reviewed trust-root mechanism is
**REMOVED from the runtime, not merely bypassed**, and is guarded against return
by the anti-resurrection tests in `tests/test_china_tushare_spine.py`. Those
tests fail if the identifiers, the CLI flags, the manifest fields, or equivalent
renamed constructs reappear.

What still gates the collector before any store write or network call, all of it
technical:

- `BULK_HISTORICAL_BACKFILL_READY` — a **technical readiness** gate (live canary
  parity, sustained throughput, range/completeness correctness), never a
  licensing gate. It is `False` until a separately reviewed change cites those
  measurements. Because that gate waits on canary evidence, the canary itself is
  **not** gated on it: `collect(canary=True)` (lane `mode=canary`) performs real
  collection while the gate is still `False`, hard-bounded to
  `CANARY_MAX_REQUESTS` (12) requests over `CANARY_MAX_RANGE_DAYS` (5) calendar
  days, never with `allow_bulk`, and refusing a documented row cap rather than
  starting the unproven ticker-range campaign. `mode=backfill` stays refused
  until the gate is promoted.
- token hygiene — the token is read only through `collectors.tushare_client` and
  is never accepted, persisted, hashed, or logged by the spine; artifacts are
  scanned for configured credential bytes before hashing or receipting.
- the private-store path validator, the single-writer lock, the bounded request
  budget and the `--allow-bulk` safety ceiling.
- exact request/schema binding, cap-probe discard, immutable per-attempt
  receipts, lossless source-row accounting, PIT/lifecycle reconciliation, and
  the completeness equation.

Ordinary vendor access, endpoint entitlement and quota behaviour continue to be
observed and recorded as technical facts (for example a typed
`vendor_unavailable_or_unlicensed` refusal for an endpoint the account cannot
reach). That is access observation, not compliance adjudication.

## Identity, lifecycle, and point-in-time universe

- Repository tickers are `600519.SS`, `000001.SZ`, and `920163.BJ`.
- Vendor-observed codes remain in `source_ts_code`; stable IDs are
  `CN-XSHG-600519`, `CN-XSHE-000001`, and `CN-XBSE-920163`.
- Old BJ codes remain aliases. Every canonical BSE mapping target must be `920xxx`.
- SH 688/689 is STAR; the official SZ `300000–309999` allocation is ChiNext
  (including the 309800–309999 CDR range); BJ is BSE; other admitted A code
  families are main board.
- `list_date` is inclusive; `delist_date` is the inclusive effective end. BSE
  eligibility cannot precede 2021-11-15.
- `bak_basic` is the exact-day PIT eligibility witness from 2016 onward. Before
  2016, stock lifecycle is the best available construction and the manifest
  explicitly refuses to call that an independent daily-universe witness.
- `bak_basic` corroborates rather than replaces lifecycle eligibility. The shard
  and coverage universe is the frozen `lifecycle ∪ PIT` set. Post-2016
  lifecycle/PIT differences are receipted with samples; which of them block
  completeness is governed by the source-union law below.
- **Historical PIT construction is source-UNION, never current-snapshot
  intersection** (`DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`, Sol 2026-08-26).
  The current `stock_basic` snapshot is a lifecycle/reference *witness*, not
  exhaustive historical membership authority: it is a CURRENT snapshot used to
  classify HISTORICAL sessions, so intersecting against it is a survivorship
  filter. A well-formed A-share `bak_basic` PIT observation therefore LANDS even
  when the current snapshot omits it, carrying
  `current_stock_basic_witness_missing = true`.
- That observation alone grants **no trading/event authority and no
  canonical-identity authority**. Authority is graded: a complete same-session
  positive-volume daily observation *plus* the required exact legal-limit/session
  evidence proves historical trading even when current `stock_basic` omits the
  security, and such a security must never be silently removed from the
  historical exact universe. A PIT-observed row without that evidence stays
  source-accounted but **non-event-eligible**; `never listed` may not be inferred
  unless an explicit lifecycle source establishes that stronger state. Data
  OS/GMI remains the canonical identity owner — no historical CN-Limit identity
  master exists.
- PIT-only listing keys **propagate into downstream historical source
  acquisition, including `name_history`**, so the same survivorship filter is not
  recreated one stage later.
- **A valid `namechange` row is its own sufficient source evidence**
  (`DEC:CNLI-NAMECHANGE-IS-ITS-OWN-SOURCE-AUTHORITY`, Sol 2026-08-27). It needs no
  contemporary `stock_basic`, `bak_basic`, PIT or other external witness merely to
  EXIST in the name-history plane — the PIT witness only reaches back to
  2016-01-01, so requiring corroboration would restore the current snapshot as
  sole authority for every earlier row. Every source row instead carries exactly
  one deterministic disposition: **externally corroborated**, **`NAMECHANGE_ONLY`**,
  or **explicit conflict/quarantine**.
- `NAMECHANGE_ONLY` counts as **terminal source completeness** and grants **zero
  PIT membership, positive-volume trading, exact-event, canonical-identity, rank
  or score authority**. Name history is a leaf: nothing reads it but its own
  receipt builder, and a namechange-only ticker must never enter
  `_all_known_a_tickers` — otherwise a name assertion would bootstrap itself into
  the universe membership this law denies it.
- The rule applies **row by row across the frozen epoch**. Pre-2016 is not
  special-cased and the witness-missing percentage is **not an admission
  threshold**; the rate is telemetry. Malformed keys, contradictory lifecycle
  intervals, incomplete responses and unresolved source conflicts stay
  fail-closed.
- Completeness of the name-history plane therefore requires **all source rows
  deterministically reconciled with zero unresolved conflicts — not 100% external
  corroboration**.
- Completeness remains fail-closed for malformed or conflicting keys, incomplete
  source responses, unresolved source contradictions (including a PIT row whose
  master lifecycle window contradicts the observed trade date), positive-volume
  rows without required exact legal-band evidence, and any unknown disposition.
  The current-snapshot omission rate is recorded as **telemetry, never as an
  exclusion threshold** — a threshold on it would reintroduce the survivorship
  filter as a tunable.

Reference refresh is generation-atomic. Raw `stock_basic`, `fund_basic`, and BSE
mapping units land under an immutable staging generation; derived master/alias/
classification artifacts compile inside that same generation; only then does one
atomic pointer promotion expose it. The reader recomputes the promoted generation's
semantic hash against the pointer once per collector/manifest operation, then pins
that immutable generation ID through hot-path lookups. An interrupted refresh
leaves the previous generation readable and cannot mix source vintages.

## Exact request and source-row accounting law

Every request persists a receipt containing its endpoint, exact fields, parameters,
unit, contract hash, observed time, actual returned columns, row count, response
status, and semantic response hash. A code-0 response is an attested empty only
when the vendor supplied a real nonempty `fields` array and a real `items=[]`;
malformed code-0 shells fail closed.

Responses must bind exactly to the request:

- `stock_basic`: requested exchange/status plus CNY/A-market/symbol/code;
- `trade_cal`: returned exchange and every requested calendar day;
- `namechange`: announcement anchor within the requested range;
- daily/PIT endpoints: exact trade date, and for a range-campaign leaf the exact
  ticker plus dates inside the leaf's bounds, at most one row per market session
  (amended 2026-08-13); and
- all endpoints: returned column order exactly equals requested fields.

Every source unit records and exposes this equation:

```text
source_rows = landed_A_rows + known_excluded_rows + quarantined_unknown_rows
```

Known fund exclusions come from the independent `fund_basic` identity table. The
other documented `stk_limit` contaminant is B shares: official exchange code
contracts independently identify SSE `900xxx` and SZSE `200xxx` as out of A-share
scope ([SSE code guide](https://www.sse.com.cn/lawandrules/guide/stock/jyglywznylc/zn/c/c_20260713_10825354.shtml),
[SZSE code table](https://www.szse.cn/marketServices/technicalservice/doc/P020241212550140892927.pdf)).
Unknown rows are retained under `source_row_classification/quarantined_unknown`
with their decoded raw payload and block completion. Name-history orphans use the
same quarantine/equation and do not land in the A-share name partition. No row may
disappear merely because it was absent from the A-share master.

Terminal state is not trusted by assertion. Each unit stores semantic receipts for
its exact landed-A subset, independently known-excluded ledger, and quarantine
ledger, then recomputes all three on resume and manifest build. Its decoded request
receipt must occupy the canonical store-contained path and re-derive the exact
endpoint, unit, fields, and parameters. Missing, moved, swapped, or tampered source,
classification, request, or reference-generation artifacts reopen the unit.

## Sessions, prices, and event equality

The canonical market clock is not a union of stock prints. It begins at a frozen,
definition-versioned mainland calendar epoch — `mainland-joint-complete-v1`,
`1992-01-01` — requires exact SSE/SZSE calendar-day and open-session equality,
validates `pretrade_date` adjacency, and assigns one immutable
`market_session_position` counted from that epoch. TuShare does not publish BSE in
the documented `trade_cal` venue list, so BSE explicitly inherits that consensus
from launch.

The epoch is the earliest year for which `trade_cal` supplies a JOINTLY complete
SSE+SZSE calendar, established by outcome-blind source census
(`scripts/research/cn_limit_calendar_epoch_census.py`; receipt
`research/cn_limit_alpha_sol/DEP_EXACT_CALENDAR_EPOCH_CENSUS_2026-08-26.md`) and
frozen in source. It is never selected at runtime, so two runs over one store can
never disagree about which date owns which ordinal; moving it requires a new
definition string, never an in-place edit, so artifacts minted under different
definitions stay distinguishable. Compiled sessions carry `calendar_epoch` and
`calendar_epoch_definition` for exactly that reason.

This supersedes the previous fixed 1991-01-01 anchor. TuShare returns 182 of 365
days for SZSE 1991 against SSE's 365, which is SOURCE-HISTORY TRUNCATION and not
evidence that the missing civil dates fell outside the trading system. History
before the epoch is therefore typed `PRE_EPOCH_SOURCE_UNSUPPORTED`: it is never
imputed as closed, never assigned a session position, and one venue's history is
never borrowed as another's. The exact-range binding check that rejected SZSE 1991
stays as-is — relaxing it would let a truncated response prove its own truncation
legitimate anywhere in the range. Because the axis is built from every landed
partition rather than the requested window, the epoch is enforced where the axis
is compiled, not merely at the collection constant.

`daily.vol` is stored in lots and `positive_volume` is exactly `volume_lots > 0`.
Zero-volume source rows remain in the substrate. Any traded/listing-session claim
must filter the flag; other endpoints must join daily before making such a claim.

All non-null prices are exact CNY-cent ticks. Positive-volume `daily` rows require
finite nonnegative volume/amount, positive complete OHLC/pre-close, and coherent
OHLC ordering. `stk_limit` requires both bounds or neither, with upper strictly
above positive pre-close and lower at or below pre-close (equality is legal only
at the one-cent floor). `event_daily` then enforces:

- one-to-one daily, daily-basic, and limit keys;
- daily/stk-limit previous-close equality;
- daily/daily-basic close equality;
- bounded OHLC inside the exact source interval;
- `daily_basic.limit_status` domain/direction/one-price semantics; and
- touch/seal flags only by integer-cent equality for positive-volume bounded rows.

`a_share_limit_price_bounds()` uses Decimal `ROUND_HALF_UP`, enforces a one-tick
move and one-tick floor, and rejects off-tick inputs. It is validator-only because
effective-dated IPO/ST/board/no-limit state must not be guessed from one ratio.

## Cap fallback, scheduling, and resumability

> **Amended 2026-08-13.** The original 2026-08-08 text specified an exact
> **date×ticker** fallback: one request per ticker per trade date. That design was
> named in the same paragraph as combinatorially unsuitable for a 2011-present
> full-A backfill, and it has been **superseded in code** by the bounded
> **ticker×date-range campaign** the original text named as the promotion
> prerequisite. The paragraphs below describe the design as implemented in
> `collectors/china_tushare_range_shards.py`. The gate itself is unchanged:
> `BULK_HISTORICAL_BACKFILL_READY` remains code-reviewed `False`. The superseded
> date-by-ticker wording is retained in this note only so the amendment is legible;
> it is no longer the contract.

Whole-market responses at the documented limit are potentially truncated. For
`daily`/`daily_basic` (6,000) and `stk_limit` (5,800), the collector freezes the
exact lifecycle-eligible union PIT ticker set and switches the **entire requested
interval for that endpoint** to an immutable per-ticker **date-range campaign**.
The switch is per endpoint and per interval, not per day: once a cap is documented,
the whole-market fast path is abandoned for that endpoint's requested range rather
than retried day by day.

A campaign freezes a plan (`plan.json`) whose identity hash binds the endpoint,
the requested fields, the source row cap, the canonical market-session list, the
frozen query-identity set, and the reference generation that produced it. The plan
is immutable: re-entering `ensure_campaign` with different inputs is rejected
rather than silently re-planned. The plan splits each query identity's requested
interval into deterministic contiguous market-session chunks of at most
`cap - 1` sessions (`deterministic_contiguous_market_session_chunks_cap_minus_one_v1`),
so a single leaf response can never itself sit at the cap and be ambiguously
truncated. Each such chunk is a **leaf**, keyed by a hash of its own contract.

Each leaf carries its own atomic state file and an immutable numbered attempt
receipt per physical request, so a bounded run resumes with zero redundant calls.
Retries are deterministic: unattempted leaves precede previously attempted ones,
and among attempted leaves the fewest-attempts leaf goes first
(`unattempted_then_fewest_attempts`). A leaf response is bound before it lands —
exact requested columns, no rows crossing the requested ts_code or date bounds, no
duplicate ticker/date keys, and at most one row per requested market session.

Terminal leaves are transposed back to exact source days: the campaign resolves
BSE old/new code aliases (canonical preferred when the rows are equal; conflicting
rows are retained in their own artifact and **block** rather than being silently
picked), writes a terminal index, and only then normalizes and replaces each exact
day, binding the day's receipt to the campaign. A campaign cannot close while any
alias conflict stands.

The capped whole-market response is atomically relabeled
`non_authoritative_cap_probe`; its observed rows are exposed as discarded probe
rows and never enter the authoritative source equation. The parent source count
must equal the sum of request-bound terminal child rows. Expected request volume
for endpoint `e` is `H_e + I_e * ceil(S/(C_e-1)) + R_e` for `S` requested sessions,
`I_e` query identities, cap `C_e`, whole-market probes `H_e`, and retries `R_e` —
bounded, and the basis on which throughput is to be judged.

**The technical gate is unchanged and this design does not open it.**
`BULK_HISTORICAL_BACKFILL_READY` remains code-reviewed `False`; network and
injected collection still fail before store mutation, and manifest completeness
still cannot close. The range-shard campaign is verified **synthetically only** —
every test injects responses, none contacts the vendor. Promotion additionally
requires a live canary against real quota, which has not been run; the manifest
states this directly as `cap_fallback.live_canary_complete: false` alongside
`live_canary_required_for_promotion: true`. Opening the gate is a separate,
separately reviewed change resting on canary/throughput/correctness evidence —
never on a licensing artifact.

Unattempted source units precede retries; retries are deterministic. Active-year
name history uses an end-date-qualified unit so a partial-year success cannot
masquerade as a completed year. State and monthly partitions use same-directory
temporary files plus `os.replace`; exact source days replace prior rows, including
empty tombstones. One nonblocking advisory lock permits a single writer per local
store. There is no distributed multi-host lease.

The default store is outside Git:

```text
~/.local/share/macro-dashboard/china_tushare_spine/
  reference/current_generation.json
  reference/generations/<generation-id>/
    source_bse_mapping.parquet
    source_stock_basic/{SSE,SZSE,BSE}_{L,D,P,G}.parquet
    source_fund_basic/E_{L,D,I}.parquet
    security_master.parquet
    identity_aliases.parquet
    instrument_classification.parquet
  reference/trade_calendar/year=YYYY.parquet
  reference/market_sessions.parquet
  bak_basic/year=YYYY/month=MM/part.parquet
  name_history/year=YYYY.parquet
  {daily,daily_basic,stk_limit,suspend_d,stock_st}/year=YYYY/month=MM/part.parquet
  source_row_classification/{known_excluded,quarantined_unknown}/...
  source_shards/{daily,daily_basic,stk_limit}/...   # legacy date x ticker; read-only
  range_campaigns/<campaign-id>/plan.json           # amended 2026-08-13
  range_campaigns/<campaign-id>/leaves/<xx>/<leaf-id>.json
  range_campaigns/<campaign-id>/terminal_index.parquet
  range_campaigns/<campaign-id>/campaign_receipt.json
  range_campaigns/<campaign-id>/alias_conflicts.parquet
  source_range_shards/{daily,daily_basic,stk_limit}/<campaign-id>/<xx>/<leaf-id>.parquet
  receipts/requests/<endpoint>/<unit>/<request-hash>.json
  event_daily/year=YYYY/month=MM/part.parquet
  coverage/daily_security_coverage.parquet
  collection_state.json
  completeness_manifest.json
```

The legacy in-repo `data/china_tushare_spine/` containment subtree is ignored.
Every other repository-local store path is rejected so paid raw data cannot become
stageable through a renamed directory. HTTPS-only transport with redirects disabled comes from the shared reviewed
client. Vendor bodies, payloads, and exceptions are never logged. Logical decoded
values—including DataFrame attrs/metadata, columns, unused category values, and
index levels—are scanned before writes and after Parquet reads. A temporary Parquet
file is byte-scanned and decoded/roundtripped before atomic promotion; raw receipt
bytes are scanned before hashing.

## Completeness manifest

`completeness_manifest.json` closes only when all of the following are true:

1. the immutable operational-backfill code gate has been separately promoted on
   canary/throughput/correctness evidence;
3. the current reference generation, exact calendar, active-year name unit, and
   every required source unit are request-bound and complete;
4. all per-unit source equations hold, unknown count is zero, name orphan count is
   zero, and any range campaign is terminal with every leaf verified, every day
   receipt bound, and no standing alias conflict (amended 2026-08-13);
5. every requested post-2016 session has a `bak_basic` witness, lifecycle and PIT
   sets reconcile under the source-union law — every lifecycle-eligible security
   is witnessed in PIT, and no PIT row contradicts its own master lifecycle
   window; a PIT row absent from the current `stock_basic` witness is a legal
   union member and is counted as telemetry, not as a mismatch (amended
   2026-08-26, `DEC:CNLI-HISTORICAL-PIT-IS-SOURCE-UNION`) — and every requested
   daily endpoint unit is complete (pre-start endpoints are explicitly N/A);
6. duplicate-key, dense-key, lifecycle, exact-session, suspension, and daily
   security coverage checks close;
7. the canonical exact-price event join closes; and
8. source, semantic, schema/query-contract, request-count, coverage, lifecycle,
   data-gap, and ore receipts are present.

`generated_at` is excluded from `manifest_identity_sha256`, so the same content
retains a stable identity. Request observations and collection-state changes remain
part of content identity. Artifacts are private and must not be committed.

## Remaining technical/data gaps

- No token, endpoint entitlement, throughput, or live sample was exercised in this
  wave. This is intentionally `NO LIVE`.
- Exact-date×ticker cap recovery is not a viable long-horizon backfill plan. A
  ticker×date-range implementation and measured request/retry budget are required
  before the immutable operational gate may change.
- `bak_basic` and exact daily `stock_st` begin in 2016; pre-2016 PIT universe and
  exact ST membership remain named gaps.
- Direct BSE calendar provenance is absent from the documented endpoint.
- Same-key vendor corrections replace local materialization; there is no bitemporal
  raw-response revision ledger.
- No minute, auction, order-book, first-seal, fillability, pre-open float, or chip
  history is collected.
- Calculated historical bounds have not been reconciled against `stk_limit` across
  every rule era; calculations remain validator-only.

## Ore ledger

Constructed: atomic lifecycle/reference generations; BSE 920
aliases; PIT 2016+ universe; exact session positions; lossless source classification;
request-bound schemas/receipts; bounded ticker×date-range cap campaigns, synthetically
verified and still operationally gated (amended 2026-08-13);
multi-artifact terminal binding; discarded cap-probe accounting; nominal OHLCV and
positive-volume state; daily-basic/limit/suspension/ST/name provenance; lifecycle
and coverage reconciliation; integer-cent exact-source event rows; half-up
validator; exact equality and vendor-bound checks.

Not tested: live vendor access, adjusted `pro_bar`, pre-2016 exact universe/ST,
direct BSE calendar, **live cap-trigger parity for the ticker×date-range
campaign** (the mechanism is verified synthetically only — no test contacts the
vendor; amended 2026-08-13), vendor retry throughput and paid request cost,
historical calculated-band parity across rule eras, minute/
auction/order-book/seal-time/fillability histories, and actual bulk throughput.
Any future null must name which of those construction spaces was not measured.
