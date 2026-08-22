# AD-1T0 — ThetaData cutover: contract-identity ruling + frozen adapter spec (2026-08-22)

Authority: Chairman source ruling 2026-08-22 (`DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA`);
wave AD-1T0 in `WS:ADVANCED-DATA-OPTIONS`. Ruled by coo-fable on the live m1 census
(read-only, 2026-08-22) plus the source/PIT reconciliation analysis of the same date.
Scope: `scripts/build_options_intel_brief.py` (adapter) + its tests + contract §2 source
table. `engine/options_intel_brief.py` is BYTE-UNCHANGED. `intel_brief_heuristic/v1.2`,
all thresholds, direction laws, confidence ceilings, board ranking laws, Prophet
zero-rank, and `Q_flow = ABSENT` are FROZEN.

## §A. Contract-identity ruling (Fable)

The ThetaData source tuple **(root, expiration, strike, right)** is APPROVED as the
deterministic source-contract key for AD-1.

Census basis (all measured on the live store, exact commands in the AD-1T0 handoff):
9 sessions spanning 2013→2026 across all present universe roots — duplicate keys per
(tier, session): 0–1; **conflicting duplicates: 0** (the single duplicate found was a
byte-identical full row, removed by the store's load-time dedup); nonstandard root
spellings among all 381 store roots: **0**; `root` column vs directory name mismatches:
0; strike×1000 integrality violations: **0 / 2,104,998** (SPY 2026); cross-session key
stability (5 liquid roots, S−1→S, expiration > S): **100%** in both eod and oi tiers;
no vendor contract-id column exists in any tier and the v3 API's `symbol` field is the
echoed request root — there is no better first-party identifier to prefer.

Serialization law (adapter-side; NOT a new identity grammar — this is the engine's
existing key format fed from the source tuple):

```
strike_ticker = "O:" + ROOT + YYMMDD(expiration) + ("C"|"P") + zfill8(int(round(strike*1000)))
underlying    = ROOT (vendor root, verbatim)
```

Hard constraints, all fail-closed:
1. ROOT is embedded **verbatim** (global uniqueness of `strike_ticker` across roots
   within a session — the ΔOI merge at `engine/options_intel_brief.py:518` joins on
   `strike_ticker` alone; never substitute a normalized/base symbol).
2. Integrality assertion `abs(strike*1000 − round(strike*1000)) < 1e-6`; a violating
   row is routed to the adjusted/nonstandard **exclusion path**, never silently rounded
   (a rounded collision would manufacture a false ΔOI merge partner).
3. 8-digit width assertion on the strike field; overflow → exclusion path.
4. A digit-suffixed or otherwise nonstandard root structurally fails
   `_STANDARD_TICKER_RE` (letters-only root group, no backtrack) → excluded and counted
   in `contract_identity_exclusions` — byte-identical to the engine's legacy exclusion
   semantics. Population today: zero.
5. Post-load uniqueness assert per (session, root): after the store's full-row dedup,
   rows sharing (root, expiration, strike, right) with differing values ⇒ exclude the
   ENTIRE root for that session and count it in an adapter-level diagnostic (root-level
   exclusion, engine's coverage gate then reports it honestly). Never row-level silent
   dedup; never a whole-board crash.
6. (Review round 2026-08-22.) Additional fail-closed exclusions, all measured EMPTY on
   the live store but required structurally: `right ∉ {C, P}` after upper-casing →
   exclusion path, never coerced to "P"; non-finite strike (NaN, ±inf) and
   `strike <= 0` → exclusion path, never a crash and never a lawful-looking ticker.
7. (Review round, BLOCKER B1.) OI-baseline availability is a ROOT-LEVEL precondition:
   a root with eod rows but ZERO oi rows for a materialised session s is excluded from
   that session's chain frame entirely and counted in the exclusion diagnostic — the
   frozen engine's `oi_prev.fillna(0)` must never read an ABSENT baseline as a ZERO
   baseline (measured harm: Q_oi direction reversal on a put-heavy book). Row-level
   eod∖oi gaps (new listings, ~2% of rows) remain NaN→0 by engine law — genuinely-new
   contracts have a true zero baseline; the guard is against systemic slice absence,
   which the live census measured at 0 roots over the last 5 sessions.

`engine.thetadata_store.make_chain_provider()` is PROHIBITED on the AD-1 path (string
`expiry`, no `strike_ticker`, and the forbidden volume-weighted-strike spot fallback).
The adapter builds its own frames. `resolve_thetadata_store()` remains the ONLY store
resolution; `chain()`-equivalent assembly is done with narrow projected reads.

## §B. Frozen adapter mapping (PIT law)

Vendor clock: EOD report generated ~17:15 ET on S but **not retrievable on S's evening**
(measured 2026-07-31, `scripts/topup_thetadata_day.py` header); OPRA OI ~06:30 ET on D =
positions at end of previous trading day S. `available_to_model` for the whole panel =
publication availability (~06:30 ET on D), never market-effective time.

| Engine input | Source (tier, date-stamp) |
|---|---|
| chain[s] identity + `volume` | eod tier rows dated s (eod is the spine — measured superset of oi; retains the volume=0 population) |
| chain[s] `iv`, `delta` | greeks tier rows dated s (`implied_vol`, `delta`) |
| chain[s] `oi` (ΔOI baseline; presence term) | oi tier rows dated s (= EOD s−1 positions, known before s opens) |
| chain[s] `spot` | §D spot law |
| chain[s] `T` | (expiration − s).days / 365.0, clipped ≥ 0 (freeze the /365.0 divisor) |
| `chain_next` (D) | **oi tier rows dated D ONLY** (5 columns: identity + open_interest → underlying, strike_ticker, expiry, is_call, oi). No eod/greeks VALUE dated D is ever materialised into any frame. |
| dtypes | underlying category, expiry datetime64, K/T/iv/delta/oi/volume/spot **float32**, is_call bool (engine's declared production dtypes) |

Leak barrier (corrected wording, review round 2026-08-22): the barrier is a
FILTERING guarantee, not a never-opened guarantee. Session-presence counting for the
§C predicate necessarily reads identity/date columns across the candidate range in
every tier — including a D-dated eod probe when such rows exist — but (a) no
eod/greeks VALUE dated D is ever materialised into a scored frame (every value load
is bounded ≤ S; the D frame is the 5-column OI projection generated pre-open on D),
and (b) the presence counts that drive session selection bind into the
`session_presence` receipt (§F), so a D-dated row-population change that could move
`as_of_session` always moves `receipt_id`. Every s-dated feature is an
end-of-session-s quantity consumed only for sessions ≤ S.

## §C. Pair selection + committed sessions

`select_settled_pair` is frozen engine code. Producer-side predicate:

```
n_eod(s), n_oi(s) = count of UNIVERSE roots with ≥1 row dated s in that tier
full(s)  := is_nyse_session(s) AND n_eod(s) > 0
            AND n_oi(s) >= 0.90 * n_eod(s) AND n_eod(s) >= 0.90 * n_oi(s)
            # symmetric floor (review round): a half-written tier on EITHER side
            # disqualifies the session; a partial eod[D] (< 90% of oi[D]) can
            # therefore never flip D into F and move S.
F        = ascending [s : full(s)]
X        = next_nyse_session(max(F)), admitted iff n_oi(X) >= 0.90 * n_eod(max(F))
committed_sessions = sorted(F ∪ {X if admitted})
```

Role-safety: X is strictly the maximum, and `select_settled_pair` never binds the
maximum to the S role; at most one OI-only frontier is ever appended; interior
single-tier holes are excluded from both roles (honest one-observation loss). The 0.90
ratios are store-relative (block half-written tiers), NOT the universe coverage gate —
coverage vs the 375-name universe stays the engine's own `SOURCE_COVERAGE_GATE`.

Depth bound: committed sessions are the trailing `K` NYSE sessions ≤ S where
`K = max(largest CONFIG history window constant, legacy 28) + 1`; builder derives K
from the frozen CONFIG constants, cites each, and asserts K covers every window the
engine reads (incl. LOOKBACK+1 for spot history §D). Never load the store's full
13-year history into the nightly.

Staleness anchor stays `max(committed_sessions)` (producer behavior-preserving; the
morning-state generosity is recorded as a KNOWN LIMIT, deliberate).

## §D. Spot law (frozen ladder)

1. **Rung 1**: ThetaData greeks `underlying_price` for (s, root) — per-root median over
   that session's rows (one scalar; robust to a stray row). Raw basis, matches strikes.
2. **Rung 2**: `engine.price_ladder.resolve_close(sym, asof=s)` — ONLY accepted when
   `r.adjusted is True` AND the series' last index date == s (no cache fall-through, no
   stale prior close). Verified 375/375 universe union coverage, nightly-updated.
   Basis note (adjusted vs raw) applies only in the rare (S, ex-date) overlap — accept
   and disclose in KNOWN LIMITS.
3. **Rung 3**: spot ABSENT → the symbol is skipped by `session_metrics` (drops out of
   `present_names`; counts against SOURCE_COVERAGE_GATE; never ELIGIBILITY_GATE).

The volume-weighted strike proxy is FORBIDDEN in any score-affecting position.

`summary_spot` (history for v2/rv, c2, c3): **replaced, not dropped** — dropping kills
the risk board (contract §9: c3 fired 5/6, c2 2/6 of sampled crowding rows). New source:
per-session median greeks `underlying_price` for the root over the trailing LOOKBACK+1
committed-window sessions ≤ S (same raw basis as rung-1 spot — preserves the legacy
raw/raw consistency of the c2 comparison; single-source; receipt-covered). A root
without greeks history simply has a shorter window → the family goes absent per-name
(honest). The legacy `data/polygon_gex/summary_*.parquet` read is REMOVED.

## §E. P/GEX disposition

`site/gex/{SYM}.json` is legacy-Polygon-estate provenance ⇒ per directive §9 the
mechanics family is **ABSENT for the cutover, hard-disabled in the producer** — do NOT
rely on the `meta.asof == S` date coincidence (a date gate is not a source gate). All
verdicts None; `gex_confirm` manifest domain emitted empty (`root: None,
member_count: 0, state: "missing"`). Engine-visible consequence (asserted by test):
`M_gex ≡ 1.0`, mechanics_context nulled, affected LONG `fresh_until` S+1→S+3, no
board_state effect.

## §F. Receipts

Granularity ruling: **per-(session, tier) row digests over CONSUMED columns only**,
canonically sorted; whole-year file hashes are REJECTED (the nightly re-pull rewrites
year files → receipt churn would break contract §7's semantic no-op).

- eod → (root, expiration, strike, right, date, volume)
- oi → (root, expiration, strike, right, date, open_interest)
- greeks → (root, expiration, strike, right, date, implied_vol, delta, underlying_price)
- Canonical form: sort by identity, fixed decimal float repr, sha256 over UTF-8; never
  `hash_pandas_object`. Member keys: `thetadata://{tier}/{session}`. Domain roots fold
  into `input_receipts` (existing merkle idiom) so they bind `receipt_id`.
- Keep the three `source_manifest` KEYS (`gex_summary`, `gex_confirm`, `chains`) —
  `_empty_source_manifest()` hard-codes them. `chains` domain = the ThetaData digests.
  `gex_summary` domain = the spot/summary-spot authority manifest (rung-2 price files
  actually consumed + the spot-history slices), or empty when nothing consumed.
  `gex_confirm` = empty (§E).
- NEW `input_receipts` entry `spot_authority`: per-symbol rung used (1/2/3 counts) +
  sha256 over the per-symbol rung map INCLUDING, for every rung-2 symbol, the consumed
  resolved close VALUE (fixed decimal repr), the ladder `price_source` tag, and the
  series last index date — a rung-2 close change MUST move `receipt_id`
  (review round, BLOCKER B2; property-tested).
- NEW `input_receipts` entry `session_presence`: sha256 over the ordered per-candidate
  (session, n_eod, n_oi) counts consumed by the §C predicate — binds the presence
  facts that drive S/D selection (review round, M1). Counts are re-pull-stable, so
  contract §7's semantic no-op survives byte rewrites.
- `chains_S`/`chains_D` receipts: keep logical_source names; `path` becomes the logical
  URI; `sha256` = that session's composite digest. `store_resolution` receipt: the
  hash binds the resolver SOURCE TAG (env/data_dir/ops-wt), NOT the absolute path —
  a host/path migration with identical data must not churn `receipt_id`; the absolute
  resolved path is recorded in the diagnostic `_run` block only (review round, m5).
- Digest float canonicalisation normalises `-0.0` to `0.0` before repr (review round,
  m3). A corrupt/unreadable year parquet emits a line-start `::warning` and is
  visible in the receipt state, never only a debug log (review round, m6).
- Staleness anchor: `max(committed_sessions)` EXACTLY (§C law; review round BLOCKER
  B3 caught a drift to newest-eod-date — every Monday build would have published
  STALE_SOURCE with zero cards).
- Property tests: mutating a consumed (session, tier) slice moves `receipt_id`;
  rewriting an unconsumed session/column/root does not.

## §G. Producer behavior off the store host

`resolve_thetadata_store(required=False)` → None (e.g. GH macstudio runner: repo stub
refused by design, ops-wt path absent) ⇒ print a `::warning` naming every tried path,
**exit 0, leave the committed artifact bytes untouched** (self-skip pattern, mirrors
the tape lanes). NEVER write NO_SIGNAL/STALE from a stub; NEVER `required=True` crash
the nightly engine job. No daily.yml edit in this wave.

## §H. Out of scope (recorded, Sol-owned follow-ups)

- T1 spine daily-refresh universe: 48 roots (39 ∩ AD universe) vs 375 — whole-year
  re-pull ≈ 3 min/root/night makes full-universe nightly ≈ 19 h; expansion needs an
  incremental refresh design + Terminal budget ruling. THE coverage blocker.
- `scripts/publish_r2.py` symlink-blind `rglob` (thetadata_eod R2 sync failing nightly
  since ≥ 2026-08-08) — distribution-plane heal, separate PR.
- Store-bearing host is not a GitHub runner (theta-m1 label carried by a non-store
  host); RE-PIN RULE in daily.yml comments governs the return.
- Q_flow activation on ThetaData trade+NBBO: future model-version decision.
- Morning-cadence publication (S brief available ~06:30 ET on D): future wave.
