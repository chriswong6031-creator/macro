# HK + Canada Prophet Shadow Substrate — Frozen Contract V1

Wave: shadow-contract (WS:PROPHET-HK-CA-REVAMP). Authority: execution packet §9 +
CEO Sol commissioning 2026-08-20, opened on the LEDGER-ERA settlement pass
2026-08-21. This contract freezes STORAGE + ISOLATION only. It is not a ranking
model, not a discovery-alpha wave, and it picks no winner.

Frozen after an Opus adversarial pre-implementation review (2026-08-21, verdict
FAIL on draft: 5 merge-blocking / 9 major findings — all amendments incorporated
below; the draft's K1–K10 suite was expanded to K1–K14 plus positive-control,
non-vacuity, and static-fence clauses). The review's finding IDs (F1–F18) are
cited inline so the builder and the post-build reviewer can trace each clause to
the attack it closes.

## 0. Governing precedents (carried forward)

- DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW — paired-row storage lawful ONLY while
  (1) same candidate population, (2) same ticker-level outcome, (3) zero authority.
  Lane A here is NOT a paired row: it is a SEPARATELY-KEYED lane, lawful under
  that DEC's fallback clause (F15). The paired row's for-free guarantee (no
  copy divergence) is therefore replaced by an explicit compensating invariant:
  a store validator asserts every Lane-A (date, ticker) exists in board_ledger
  with matching board_pos and board_definition.
- DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY — challenger output rides its
  own unambiguous column names; canonical columns are never repurposed.
- Packet §8 — board_ledger identity stays keep-FIRST (date,ticker). NEVER migrated.
- Packet §9.2 — when V4 `prophet.candidate_episode/v1` is available cross-market,
  ADOPT/MIGRATE rather than maintaining a permanent duplicate. (Census verdict
  2026-08-20: PLANNED ONLY — frozen schema name, zero code, US-first; the
  CAPABILITY_LEDGER row named `candidate_episode` is NOT_BUILT. Stable-key
  citation per house law, F17.)

## 1. Module + stores

One new market-parameterized module: `engine/board_shadow.py` (naming follows the
board_ledger family; the existing precedent for a second market is a duplicate
module — us_context_vector.py US-pinned STORE_DIR, china_prophet_shadow.py its
own STORE_DIR — this module deliberately parameterizes {HK, CA} instead).
US/CN stores are NOT refactored (out of scope).

Stores (parquet via pandas, keep-first dedupe on the declared key):

- Lane A (same-population rank pairs):  `data/prophet_shadow/{hk,ca}_rank_pairs.parquet`
  key: (date, ticker, challenger_definition), keep-first.
- Lane B (discovery observations):      `data/prophet_shadow/{hk,ca}_discovery.parquet`
  key: (session_date, security_ref, security_ref_raw, challenger_definition),
  keep-first. (security_ref_raw was added to the key by post-build review
  finding M4 — without it, the next session's keep-first merge silently
  destroyed one of two collision rows the collision counter had just sworn to
  preserve; see the clarifications block below.)

Single accreting file per market/lane (volume ≤ ~20 rows/session/challenger; the
US monthly-partition rationale — 3-14 GB/yr — does not apply at this volume).

SCHEMA LAW (F4 — replaces the draft's unbounded schema-union; these stores are
git-tracked parquet in a PUBLIC repository, the exact surface of the Filing
Forensics payload leak the house already paid for, see
tests/test_us_context_vector_payload_containment.py):

- Each lane pins an explicit column allowlist (`_SCHEMA_A`, `_SCHEMA_B`) owned by
  `engine/board_shadow.py`, enforced by `reindex(columns=…)` at the write seam
  (the board_ledger `_SCHEMA` pattern). No column reaches disk that is not in
  the allowlist.
- Lane B evidence families are REGISTERED, not free-form: a family contributes
  exactly `<family>_status` + `<family>_value`, and registering a new family is
  a reviewed code change to the module's family registry (which regenerates
  `_SCHEMA_B`). Registering a challenger or a family is never a schema
  MIGRATION (columns are additive) and never touches a production builder.
- A hard-fail DENYLIST of outcome/authority column families applies to both
  lanes and outranks the allowlist: `fwd_*`, `*_ret`, `excess*`, `mfe*`,
  `terminal_state*`, `hit_*`, `pnl*`, `rank_ic*`, `size*`, `weight*`, `gate*`,
  `plan*`, `featured*`. (`visible_to_user` / `published_authority` are the two
  pinned literal-False columns of §3 and are exempt from the `visible*`/
  `published*` pattern by exact name only.)
- At write time an unclassified column is DROPPED with a line-start `::warning`
  (bare print, flush=True, per the CLAUDE.md annotation law) and the same law is
  pinned by test (K11), in the dual runtime-dropper + hard-fail-test shape of
  test_the_runtime_drop_and_the_hard_fail_law_agree.

## 2. Lane A — same-population rank challenger

Question: given the exact same candidate population and realized ticker outcomes,
does a challenger order the names better?

Row columns (`_SCHEMA_A`, exhaustive at merge):
  date, market, ticker,
  incumbent_definition   — the live board stamp at observation
                           (ca_prophet_branch_b_v1 / hk_prophet_v2), normalized
                           by IMPORTING board_ledger._definition_or_none — the
                           module binds THE function object, never a
                           re-implementation ("same as" is not enough; two
                           normalizers feeding one exact-equality comparison
                           must be one object — F6, LEDGER-ERA lesson),
  incumbent_rank         — board_pos READ BACK from
                           data/board_ledger/<m>_board.parquet for the exact
                           (date, ticker) AFTER append_board returns. NEVER
                           re-derived by enumerating the calls list: board_pos
                           is minted inside append_board after a ticker-less
                           row skip, so an independent enumerate silently
                           records a phantom board order (F5),
  incumbent_lane         — buy | watch,
  challenger_definition,
  challenger_rank        — dense rank over the EXACT minted population, NULL for
                           unscored names,
  challenger_rank_domain — enum, literal 'minted_population' (F9): the stored
                           ranks are defined over the minted population and
                           nothing else. Any published rank-IC must re-rank
                           BOTH columns on the joined graded frame at analysis
                           time — stored ranks are never compared directly to a
                           graded-frame statistic, because grade()'s frame
                           legitimately drops delisted and unfilled rows (the
                           LEDGER-ERA receipt measured this split in
                           production),
  challenger_score_raw, challenger_score_conservative,
  challenger_coverage    — count(challenger_rank NOT NULL) / population_n; the
                           incumbent minted population is the ONLY denominator,
  population_n           — the exact count of rows minted for this
                           (date, market, challenger_definition) (F8). Store
                           validator identities: population_n == count(rows for
                           that key) and challenger_coverage reproduces from the
                           stored columns. Coverage over ANY other denominator —
                           including any SUBSET of the incumbent list (e.g.
                           buy-lane only) — is a violation,
  challenger_offlist_n   — count of names the challenger emitted that are NOT in
                           the incumbent population (surfaced, never silently
                           dropped-and-forgotten; off-population names belong to
                           Lane B, never here),
  stamped_at             — write-clock ISO timestamp (prospectivity receipt).

Population law (attack class 2): rows are minted ONLY from the exact `calls`
list handed to board_ledger.append_board in the same build pass. The writer
takes that list as its sole population input and CANNOT re-originate. A name the
challenger did not score gets a row with challenger_rank/scores NULL (missing ≠
zero) and coverage reflecting it. A name the challenger added is filtered out
and counted in challenger_offlist_n.

Outcome law (attack classes: private grader, duplicate outcome computation):
Lane A stores NO outcome columns, ever. Outcomes come at analysis time by JOIN
against board_ledger's graded spine on (date, ticker) — one grader
(board_ledger.grade), one fill law (next-bar), one suspension law. The module
never reads price history and never computes a return — enforced as a CALL
surface, not an import surface (F7): see K3.

Authority law: NOTHING in production reads either store. No rank, gate, plan,
publication, Featured, Brain, or entry effect. visible-to-user surface: none.
Enforced statically repo-wide (F12): see K6.

## 3. Lane B — population-changing discovery challenger

Question: does broader/different origination surface opportunities the incumbent
never saw? Separate zero-authority research observation store — NEVER forced into
board_ledger or a Lane-A paired row.

Row columns (`_SCHEMA_B` = the fixed columns below + registered families):
  session_date, market,
  security_ref           — canonical ref, produced by the ONE importable
                           canonicalizer `board_shadow.canonical_ref()` — pinned
                           by test to whatever the board producers store (today:
                           identity over board_ledger's verbatim `str(ticker)`)
                           so no second identity truth is minted (F11),
  security_ref_raw       — the pre-canonical ref exactly as received; never
                           overwritten (F11),
  ref_collision_n        — count of DISTINCT raw refs seen for this
                           (session_date, security_ref); a collision (two raw
                           refs canonicalizing together in one session) is
                           COUNTED and logged with a line-start `::warning`,
                           never silently collapsed (F11),
  challenger_definition, candidate_origin,
  first_seen_at          — forward evidence clock, resolved at write time as
                           min(existing first_seen_at for (security_ref,
                           challenger_definition), stamped_at). Re-observation
                           NEVER advances it; only a challenger_definition bump
                           restarts it (F14 — "never reset a forward evidence
                           clock"),
  <family>_status        — per REGISTERED evidence family: ok | missing | stale
  <family>_value         — value column paired with its status column;
                           missing ≠ zero (value NULL + status=missing),
                           stale ≠ missing (status=stale keeps last value),
  availability_status, availability_source
                         — independent availability read; the substrate carries
                           the fields, real reads are wired by hk-discovery
                           (census: no HK/CA eligibility sidecar exists in code —
                           DEC:PROPHET-RANK-PRESERVED-MARKET-ELIGIBILITY-SIDECAR
                           is unbuilt and names only US/CN),
  visible_to_user        — literal False on every row,
  published_authority    — literal False on every row,
  stamped_at             — write-clock ISO timestamp.

Prospectivity law (attack class: retro-fabrication/backfill — F10; the build's
`asof` is a DATA date, so asof-equality alone cannot see a re-run):
- The writer refuses any row whose session_date != the current build's asof
  session (K8a), AND
- refuses any row whose session closed before the writing process started —
  a wall-clock fence: stamped_at's date may not exceed session_date beyond the
  market's settle window (K8b; mirrors the settled-session fence
  china_prophet_shadow carries), AND
- refuses any session_date older than the store's current max session_date for
  that market (no filling holes behind the head).
Historical challenger evidence is never written as if observed live.
Append-only, keep-first; no updates, no deletes, no forward-clock resets.

Outcome law: no outcome columns in this store, and no outcome computation in
this module. The outcome path for discovery names is a THIRD DOOR, explicitly
out of scope here (F13): a FUTURE governed evaluator wave that imports
engine.grading.forward_metrics / fill_index and the identical suspension law
and writes to its OWN separately keyed store. It is named here so this
contract's kills (K3 is scoped to engine/board_shadow.py only) do not pre-block
the evaluator Lane B depends on. board_ledger.grade() cannot serve (it iterates
only its own store's rows), inserting discovery names into board_ledger is
forbidden (K7), and a challenger-private calculator is forbidden (K3).

## 4. Lane gates + wiring

Writes are lane-gated exactly like board_ledger.append_board: HK only when
engine.ledger_lane.asia_advance_enabled(); CA only when
nightly_advance_enabled(); import failure = off-lane, fail-closed. This inherits
"intraday lanes discard data/ writes". (Gate mapping verified against the real
lanes: CN_LANE=asia is the lane that builds HK; COLLECT_LANE=nightly the lane
that builds CA.)

Wiring — one fail-soft call per market, placed DOWNSTREAM OF PUBLICATION, with
the ordering stated per market because it differs (F1 — the draft's blanket
"adjacent to append_board" claim was FALSE for HK):
- CA: after the append_board call in build_canada's board-ledger block. The
  public artifact canada_standouts.json is already serialized by then
  (build_canada_library.main() writes it once and returns), but the PAGE
  view-model is still live — so ordering alone is NOT the isolation argument
  (F2); K1's identity set covers the rendered pages.
- HK: after the hk_standouts.json write in build_hk_library (the existing
  append_board site sits ~189 lines UPSTREAM of that write, with the very
  buy/watch list objects that get serialized still live in scope — a shadow
  call there could mutate the published board). The HK shadow call goes BELOW
  the artifact write.
- Both markets: the writer deep-copies its population input on entry, and a
  test asserts the writer's argument shares no object identity with anything
  reachable from the published artifact dict (F1 defense-in-depth).
- A refactor that hoists either call upstream of its market's artifact write is
  a contract breach even if bytes happen to match.

The module holds a challenger registry that is EMPTY at merge. The registry is
keyed `(market, challenger_definition)` — a market-scoped tuple, not a bare
`challenger_definition` string (post-merge Sol review correction, 2026-08-21;
see the dated section below) — and `register_challenger(market, definition, *,
rank_fn=None, discovery_fn=None)` takes `market` as a required first positional
argument, normalizes it (`str(market).upper()`) and raises `ValueError`
immediately if it does not resolve into `MARKETS`. Market binding is EXPLICIT
and decided by the caller at registration time — a `rank_fn`/`discovery_fn`
must NEVER decide market membership itself by inspecting tickers, board
definitions, env vars, or other incidental state.

`write_shadow(market)` selects ONLY that market's own registrations via the
module-level seam `_registrations_for(market)`. **This claim is
trust-bounded, not absolute** (round-2 post-build adversarial review, D2 —
the original "an HK write is structurally incapable of executing or writing
a CA-registered challenger, and vice versa" wording was FALSIFIED by a
reentrant-challenger reproduction and is corrected here): the seam plus the
`(market, definition)` key mean the substrate structurally never MIS-LANES a
registration — `_registrations_for(market)` never SELECTS a foreign-market
challenger's spec for a well-behaved caller, which is what K15-K19 prove. But
a registered `rank_fn`/`discovery_fn` is TRUSTED, reviewed in-repo code, not
a hostile input the registry is a security boundary against: nothing in the
selection seam stops a registered function that itself calls `write_shadow`
again — including for the OTHER market — from executing that other market's
own registrations from inside its own call. A challenger that mutates
`CHALLENGER_REGISTRY` directly, imports this module to call its private
functions, or otherwise behaves as hostile code is a CODE-REVIEW matter for
whoever reviews and merges that challenger, named as such — never a runtime
guarantee this module can enforce against code it already trusted enough to
register. One concrete reentrant shape is closed structurally rather than
left to review alone: `write_shadow` refuses ANY reentrant call — for either
market — with `registry_state=reentrant_refused`, fail-soft, via a
module-level guard set for the duration of one top-level call (D2(a)); a
challenger that calls `write_shadow` for the other market mid-pass gets that
inner call refused rather than executed.

The registry-state ladder is FOUR mutually distinguishable POST-GATE states,
each with its own log line carrying a `registry_state=` token (corrected,
D5 — the error path previously logged no such token; it does now). These are
reached only after the market/asof/lane pre-gate checks (`unsupported_market`
/ `no_asof` / `off_lane`) and the reentrancy check above have already passed
— those pre-gate returns are unchanged by this ladder and carry no
`registry_state=` requirement of their own:
- `no_challenger_registered` — the registry is globally EMPTY (an empty store
  must be distinguishable from a broken writer — F16).
- `no_challenger_for_market` — the registry holds registrations, but NONE for
  this call's market (a foreign-market registration must never be silently
  treated as this market's own — the defect the 2026-08-21 correction
  repairs).
- `wrote_n_rows n=<n>` — this market has at least one registration; `n=0` is
  a lawful successful zero-row pass (e.g. every registered
  rank_fn/discovery_fn yielding nothing this session). **Semantics
  (D7):** a SINGLE registered challenger raising — inside its own
  `rank_fn`/`discovery_fn` call, or inside that one registration's own lane
  write — does NOT flip the whole pass to `error`. It is caught by a
  per-registration guard, logged as `challenger_failed definition=<d>`, and
  skipped; the remaining registrations still run, and the pass still
  concludes `wrote_n_rows n=<n>` where `<n>` is the TRUE accumulated count
  from every registration that succeeded.
- `error` — a SUBSTRATE-level failure below the per-registration boundary
  (e.g. the incumbent-positions read itself exploding), never a single
  challenger raising (fail-soft: log + skip, never raise into the build).
  The returned `written` count on this path is the true accumulated total up
  to the point of failure, not hardcoded to 0.

When a challenger registers, the store paths get wired into the
surface-freshness absent-vs-stale vocabulary in that wave. Registering a
challenger later requires ZERO schema migration and ZERO production-builder
surgery.

## 5. Structural distinguishability

Lane A and Lane B are separate files with separate keys and separate schemas; a
same-population comparison can never silently absorb an off-population name
(offlist filter + counter), and a discovery observation can never carry an
incumbent rank pairing. The two questions stay answerable independently.

## 6. Required tests + executed mutation kills

STANDING CLAUSES (apply to every kill):
- POSITIVE CONTROL (F3): every writer-exercising kill carries a control arm that
  monkeypatches the lane gate on (CN_LANE=asia / COLLECT_LANE=nightly),
  registers a fixture challenger, and FAILS THE SUITE if the control arm wrote
  zero rows. Without this, every kill passes against the lane-gated no-op the
  merge-state module is.
- NON-VACUITY (F2): the adversarial fixture challenger MUST produce an order
  that differs from the incumbent's, asserted explicitly (the
  DEC:PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW evidence shape: "the shadow's own
  rank differs from the board order on the fixture, so the test is not
  vacuous").
- FULL CHECKOUT (F18): kills that read site/ or data/ bytes are marked
  needs_full_checkout so they SKIP LOUDLY in a sparse worktree instead of
  passing against husks.

Principal failure classes (both must have EXECUTED kills, not shape inspection):
  K1 zero-authority breach — byte-identity harness whose identity set is
     everything DOWNSTREAM of the shadow call site (F2), per market:
     CA — site/canada.html, site/canada_stocks.html,
     site/factordata/canada_standouts.json, site/factordata/ca_track_ledger.json,
     data/board_ledger/ca_board.parquet;
     HK — site/hk.html + HK stock pages, site/factordata/hk_standouts.json,
     site/factordata/hk_track_ledger.json, data/board_ledger/hk_board.parquet
     (parquet compared per the K7 rule below, since grade() legitimately
     rewrites it on-lane). Asserted byte-identical with the shadow module
     absent, present-empty, present-with-adversarial-challenger (whose order
     differs — non-vacuity), and present-with-a-writer-that-mutates-a-call-row
     (→ must FAIL). The aliasing assertion of §4 (writer argument shares no
     object identity with the published dict) is part of K1.
  K2 silent population divergence — mutation: writer takes the challenger's name
     list as the row population → offlist/coverage tests fail; comparison no
     longer reports itself same-population.

Additional kills (one named test each):
  K3 private grader — enforced as a CALL surface scoped to engine/board_shadow.py
     ONLY (F7, F13): (i) AST guard — any Name/Attribute in the module resolving
     to grading.*, store.read, pd.read_parquet, pd.read_csv, _hk_close,
     _ca_close, _bench_close, forward_metrics, terminal_state, fill_index, or
     open() under a data path → fail; (ii) runtime half — monkeypatch
     lib.store.read and pandas.read_parquet to raise inside the writer's own
     execution (excluding its sanctioned board-parquet read-back of §2, which
     uses a pinned helper), and assert a full positive-control writer pass
     still succeeds; (iii) schema half — outcome columns cannot reach disk
     (§1 denylist, K11). Mutation: add an outcome computation via
     board_ledger's internal helpers (no forbidden import names) → fails.
  K4 era pooling — two-part (F6): (i) whitespace-bearing incumbent_definition
     stamp → normalizer test fails unless stripped; (ii) identity —
     assert board_shadow's normalizer IS board_ledger._definition_or_none
     (`is`, not equality), plus a monkeypatch extending the nullish set
     asserting both sides move together.
  K5 missing→0 — challenger missing score coerced to 0 → null-law test fails.
  K6 leakage — repo-wide STATIC fence (F12; a byte-identity harness cannot
     detect a reader of an empty store, and the CN shadow precedent was read by
     a production builder and rendered to users with zero tests firing):
     a CI test walks engine/, scripts/, app/, admin/, templates/ for the store
     path literal `prophet_shadow` and hard-fails on any hit outside
     engine/board_shadow.py and its own tests. The K1 build harness (run with a
     POPULATED store whose order differs) is the second fence.
  K7 board-ledger protection — shadow writer adding columns or rows to
     data/board_ledger/*.parquet → test fails. Harness rule (F-K7): grade()
     legitimately rewrites that parquet on-lane, so the assertion is schema
     equality + (date,ticker) key-set equality + board_pos equality across
     build arms, never byte equality.
  K8 backfill — K8a: writer accepts session_date != current asof → refusal test
     fails. K8b (F10): writer invoked with asof = today−5 under a live wall
     clock → refusal; plus behind-the-head refusal (session_date < store max).
  K9 identity divergence (F11) — two distinct raw refs canonicalizing to one
     security_ref in one session → COUNTED collision (ref_collision_n) + a
     line-start ::warning, and the second observation is never silently
     dropped; mirror kill: two refs that do NOT canonicalize together must not
     be merged.
  K10 coverage substitution (F8) — coverage computed over ANY denominator other
     than population_n — including a strict SUBSET of the incumbent list (e.g.
     dropping the watch lane) → store-validator identities fail.
  K11 unclassified column (F4) — an unregistered column reaching the writer →
     runtime drop + ::warning, and the hard-fail test pins the dropper and the
     law agree.
  K12 incumbent-rank fidelity (F5) — a calls list containing one ticker-less
     row → shadow incumbent_rank must equal board_ledger board_pos for every
     ticker (kills the independent-enumerate phantom board).
  K13 rank-domain (F9) — challenger ranks 1..k over only its scored subset
     while population_n > k → fail (dense rank over the minted population with
     NULLs is the only lawful shape).
  K14 forward-clock (F14) — re-observing a name on a later session must not
     advance first_seen_at.

Market-scoped registration kills (K15–K20, added by the post-merge Sol review
correction, 2026-08-21 — see the dated section below):
  K15 HK-only discovery isolation — an HK-only discovery_fn (call-sentinel)
     must never be invoked, and must write zero rows, during a CA
     write_shadow call; POSITIVE CONTROL: the same registration fires and
     writes under HK.
  K16 CA-only discovery isolation — symmetric mirror of K15.
  K17 Lane-A rank_fn isolation — the same isolation as K15/K16 for rank_fn
     challengers, both directions, with positive controls.
  K18 simultaneous mixed-lane registration — one HK challenger and one CA
     challenger registered AT THE SAME TIME (a mixed Lane-A/Lane-B pair): an
     HK pass executes only the HK definition (the CA sentinel stays silent,
     HK's stores carry only the HK definition), and a CA pass executes only
     the CA definition (symmetrically).
  K19 executed mutation kill — `_registrations_for` monkeypatched to ignore
     its market argument and return every registered definition regardless
     of market (the exact shape of the original merged defect) → the
     K15-style isolation assertions must FAIL (the foreign challenger's
     function actually executes) → restored → suite passes clean again.
     Proves K15–K18 are non-vacuous, not decorative.
  K20 registry-state ladder — with a foreign-market-only registration,
     `write_shadow` returns `registry_state == "no_challenger_for_market"`
     and `written == 0`, distinguishable from `no_challenger_registered`,
     `error`, and `wrote_n_rows n=0` (the last produced via an own-market
     challenger that legitimately yields nothing).

Cross-store validator (F15): every Lane-A (date, ticker) exists in board_ledger
with matching board_pos and board_definition — the compensating invariant for
choosing a separately-keyed lane over the DEC's paired row.

## 7. Out of scope (this wave)

No challenger model, no HK factor/intelligence work, no CA sector/name
intelligence, no availability read implementation, no US SCORE_WEIGHTS change,
no winner, no performance claims, no user-visible change of any kind. The
governed discovery-outcome evaluator (§3 third door) is a later wave. The
surface-freshness wiring for the shadow stores activates with the first
registered challenger, not at merge.

## Post-review clarifications (2026-08-21)

Recorded during the Opus adversarial post-build review, round 2. These are
CLARIFICATIONS of the frozen text above, not design changes — nothing here
alters what §§1-6 require; each note either resolves an ambiguity the build
exposed or documents a deliberate, reviewed departure from the literal text.

- **M4 (design amendment, reviewed)** — `_LANE_B_KEY` includes
  `security_ref_raw` (the §1 key line above now reflects this). The narrower
  key could not represent two raw refs canonicalizing to one security_ref:
  keep-first on the next session's merge silently dropped the second
  collision row after ref_collision_n had counted it. K9's kill now asserts
  both collision rows survive a later-session merge.
- **n1** — "`_SCHEMA_B`" in §1/§3 is realized in code as `schema_b()`, a
  function of `FAMILY_REGISTRY` (fixed columns + registered families),
  because the schema is only fully known once families are registered. There
  is no separate `_SCHEMA_B` constant; `schema_b()` is the one and only
  source of the Lane B allowlist.
- **n2** — `first_seen_at`'s "min-carry" (§3) is implemented as a TRUE
  `min(prior_min, stamped_at)`, not "prior_min if one already exists". The
  distinction matters under clock skew: ISO-8601 UTC timestamps from
  different machines/runners are not guaranteed monotonic relative to a
  prior write's own stamp, and "never advances, only carries the earliest"
  means exactly that — the true minimum of the two candidates, not an
  unconditional preference for whichever value happens to already be on
  disk.
- **n4** — K13's operative reading is the PARENTHETICAL: "dense rank over
  the minted population is the only lawful shape", i.e. NULL for every
  unscored name, dense (not sparse) ranks for the scored subset. The
  alternative reading ("ranks 1..k over only the scored subset") is the
  MUTATION K13 exists to kill, not an equally valid interpretation — a
  reader parsing K13's prose in isolation could plausibly read it either
  way, and this note pins which one is contractual.
- **F18 status note** — as built, F18 (needs_full_checkout marking) is
  currently VACUOUSLY satisfied: every kill in tests/test_board_shadow.py
  builds its own tmp_path fixtures and none reads real `site/`/`data/` bytes,
  so no test carries the `needs_full_checkout` marker. This is a deliberate
  engineering choice (SCOPE guidance: prefer tmp_path fixtures so most kills
  run in a sparse worktree), not an oversight — but it means F18's clause is
  presently unexercised rather than proven. K1's HK leg is UNIT-LEVEL for
  this same reason (see the build packet's DEVIATIONS): a full end-to-end
  render of `compute_hk_standouts` against real `site/hkstockdata/` bytes,
  if ever added, would be the first test to actually need the marker.

## Post-merge Sol review correction (2026-08-21): market-scoped registration

CEO Sol's post-merge review of the shadow-contract wave (merged fc5282f438fb,
PR #6178) found a defect the pre-merge adversarial review did not catch:
`CHALLENGER_REGISTRY` was keyed by `challenger_definition` ALONE, and
`write_shadow(market)` iterated `sorted(CHALLENGER_REGISTRY)` — every
registration in the dict, regardless of which market it was meant for. The
first real registrant would therefore have executed in BOTH the HK and CA
lanes: an HK-only rank_fn or discovery_fn would have run (and written rows)
during a CA build pass too, with no structural barrier stopping it. Zero
production registrants existed at merge (the registry ships EMPTY by
contract §4/§7), so no backward compatibility with the unscoped
`register_challenger(definition, ...)` API was owed — this is a repair, not a
migration.

**Repair shape** (implemented in this correction PR, which carries this
wave's FINAL closure — the shadow-contract wave's own closure record,
PR #6187, is SUPERSEDED by this repair for the registration surface it
touches):
- `CHALLENGER_REGISTRY: dict[tuple[str, str], dict[str, Callable | None]]` —
  keyed `(market, challenger_definition)`, one flat canonical dict (not
  nested, not per-market modules).
- `register_challenger(market, definition, *, rank_fn=None,
  discovery_fn=None)` — `market` is a required first positional argument,
  normalized (`str(market).upper()`) and validated against `MARKETS`
  fail-loud (`ValueError`) at registration time, never fail-soft — a future
  registrant that gets its market argument wrong must be told immediately,
  not silently mis-lane its writes.
- `_registrations_for(market)` — the module-level selection seam
  `write_shadow` uses to learn which `(challenger_definition, spec)` pairs
  apply to its own call. It is the SOLE authority on market scoping (it
  returns the spec directly, not a bare name a second lookup would have to
  re-derive market membership for) — the seam K19's executed mutation kill
  targets.
- The registry-state ladder grew a fourth state,
  `no_challenger_for_market`, distinguishing "registrations exist, none for
  THIS market" from the pre-existing `no_challenger_registered` (globally
  empty), `wrote_n_rows n=<n>` (including the lawful `n=0` case), and
  `error` states. See §4 above for the full ladder.
- New executed kills K15–K20 (tests/test_board_shadow.py) prove the
  isolation structurally, including K19's executed mutation kill: with
  `_registrations_for` monkeypatched to ignore market scoping (the exact
  shape of the original defect), the K15-style isolation assertions are
  shown to genuinely FAIL — a foreign challenger's function actually
  executes and writes into the wrong market's store — before the fix is
  restored and the suite is shown green again. This is what proves the
  isolation kills are non-vacuous rather than decorative.

No storage layout, Lane A/B key, prospectivity law, board-ledger keep-FIRST
identity, outcome denylist, or publication-isolation clause changed. The
builder call sites in `scripts/build_canada.py` and
`scripts/build_hk_library.py` are untouched (they call `write_shadow(calls,
market=..., asof=...)`, which is unaffected by the registration-side repair).
No challenger was registered in production as part of this correction — the
registry remains EMPTY at merge, as it was before.

## Wave HK-DISCOVERY-SHADOW (2026-08-22): first registered challenger + freshness activation

This wave registers the FIRST production challenger and, per §4's deferred
clause ("when a challenger registers, the store paths get wired into the
surface-freshness absent-vs-stale vocabulary in that wave"), activates the
freshness wiring. Nothing in §§1-7 is weakened; this section records the
wave's additive contracts. The build survived an Opus adversarial review
(MERGE-BLOCKED round with findings F1-F13, all adjudicated and repaired
before ship — see the wave's Agent OS handoff for the ledger).

### Registration

- Exactly ONE challenger: `register_challenger("HK", "hk_discovery_v1",
  discovery_fn=...)`, wired in `scripts/build_hk_library.py` inside
  `compute_hk_standouts`, textually and causally BETWEEN the
  `hk_standouts.json` persist and the existing fail-soft
  `write_shadow(calls, market="HK", ...)` call. The market literal appears
  only at this registration call. No CA registration, no Lane-A `rank_fn`,
  and `FAMILY_REGISTRY` remains the empty tuple (families are Wave 6
  HK-NATIVE-INTEL).
- The discovery function is a pure closure over an explicitly assembled,
  DEEP-COPIED evidence bundle of pre-cut structures (the §4 F1 non-aliasing
  invariant applied to the Lane-B path): it takes no market, reads no env,
  reads no published artifact, and consumes no board rank / composite-score
  order / featured / published-membership field (source-fenced + permutation-
  tested).

### Candidate origination (deterministic origin ledger)

A name is a candidate iff ≥1 origin predicate fires; `candidate_origin` is
the "+"-joined list of firing origins in this FIXED canonical order, with
deterministic sub-tokens in parens:

1. `washout_reclaim` — 2W washout/reclaim state-map emergence
   (`engine.cycles._tf_state`-derived map built in `compute_hk_standouts`).
2. `leadership` — `engine.hk_leadership.compute()` membership (fixed
   mega-cap cohort; the population limitation is honest and recorded).
3. `ripening` — the UNCAPPED `hk_board_rank.build_ripening_rows` admission
   (a second call with `cap=10**9, ready_cap=10**9`; the display call and
   its caps are untouched; the uncapped kwargs are pinned by a named test).
4. `aged_turn` — the bare `hk_board_rank.ran_admits` admission predicate
   (probed identical to the display builder's; anchor/close-series drops are
   display-only and deliberately NOT applied to the research population).
5. `blocked_signal(<reason-slug>)` — the bare `hk_board_rank.veto_admits`
   admission predicate PLUS the display builder's own staleness bound
   (`VETOED_MAX_SESSIONS`): a veto older than the bound is no longer news
   about this tape and does NOT re-mint a fresh observation each session
   (adversarial-review finding F2 — unbounded stale-state accretion).
6. `hk_native_onset(southbound)` — the per-name southbound signal fired
   this session.
7. `ah_dislocation` — `ah_value_signal` emergence for names WITH a
   resolvable A/H twin only; a no-twin name never fires and never receives
   a fabricated zero (missing ≠ zero).

A-twin lead/read-through emergence (packet §10.2's eighth class) is
DELIBERATELY ABSENT: censused NOT PRESENT in current code, and this wave
invents no new alpha machinery. UI caps exist only in display lanes; the
research population carries NO producer cap (executed mutation kill K-D1).

### Availability (first real read — independent, fail-closed)

Frozen enum: ENTRY_OPEN, WAIT_PULLBACK, WAIT_CONFLUENCE, RAN_DONT_CHASE,
RIGHTS_BLOCKED, UNAVAILABLE_DATA. Fixed precedence: missing required inputs
→ UNAVAILABLE_DATA (`missing_inputs(...)`); placement/rights flag →
RIGHTS_BLOCKED; knife → WAIT_PULLBACK; ran/extension → RAN_DONT_CHASE; gate
passed with every hygiene read AVAILABLE → ENTRY_OPEN; else
WAIT_CONFLUENCE. Availability is computed from hygiene/entry reads invoked
for the candidate set (never scraped from the buys loop) and shares no
input with the origin predicates. Read-availability is explicit: when the
placement gate, knife pass, or extension map is unavailable AS A WHOLE, a
name that would otherwise be ENTRY_OPEN reports UNAVAILABLE_DATA with a
source naming the unavailable read — unknown NEVER defaults to a pass.
Correction (Sol pre-settlement review, 2026-08-22): the K-D4 arms as first
merged closed this only for EXPLICIT `False` flags — an OMITTED flag
defaulted to available, and two tests asserted that default on purpose. The
repair wave makes ENTRY_OPEN reachable only when `plc_available`,
`knife_available`, and `extension_available` are all explicitly present and
affirmatively True; omitted/`None` fails closed to UNAVAILABLE_DATA with a
`…_unavailable(unstated)` source (executed mutation kill: restoring the
default fails four named tests). Known per-name blockers
(RIGHTS_BLOCKED/WAIT_PULLBACK/RAN_DONT_CHASE/WAIT_CONFLUENCE) are not
weakened by an absent flag. Per-name absence inside an available read is
a genuine False. Availability preserves "interesting but wait": it is never
buy authority.

### Freshness receipt (absent-vs-stale vocabulary)

Because Lane B is append-only, a lawful zero-candidate session leaves no
trace in the parquet — store bytes alone cannot distinguish "healthy zero"
from "stale". `write_shadow` therefore writes
`data/prophet_shadow/<market>_discovery_receipt.json` (market-prefixed
basename, inside the write-surface fence) on every POST-GATE pass for a
market with ≥1 registration: `{market, as_of, registry_state, written,
definitions, challenger_failures, stamped_at}`. Pre-gate refusals
(off-lane/no-asof/unsupported/reentrant) write nothing; a market with zero
registrations writes nothing (a CA pass with only the HK registration
creates NO CA file — proven with the real registration, kill K-D7).
Receipt write is best-effort fail-soft and does not alter D7 semantics;
per-registration failures are named in `challenger_failures` while the pass
still concludes `wrote_n_rows n=<true sibling count>`.

`scripts/check_surface_freshness.check_hk_discovery_freshness()` is the
SOLE reader: warn-only (exit 0), on the HK session clock
(`lib.hk_calendar`), with DISTINCT line-start annotations for absent /
stale (HK-session gap) / substrate `error` / non-empty
`challenger_failures`, and SILENCE on a fresh zero-candidate receipt. The
receipt is deliberately NOT in `_ARTIFACTS`: it must never join the
first-class surface list, the SURFACE STALE escalation, or the ops paging
spine (review finding F1 — a zero-authority research store may not page an
operator). The receipt reaches the sentinel's checkout via the asia-close
lane's `git add data/` commit; `daily.yml` neither writes nor
cache-restores `data/prophet_shadow/`, so no W0b-class clobber vector
exists today (re-check if a cache ever covers that directory).

### Zero authority (unchanged)

`hk_standouts.json` and every HK Brain input are byte/behavior unchanged:
the registration block sits downstream of the persist, reads none of the
published payload, and the display lanes keep their existing caps. The
challenger writes only `data/prophet_shadow/hk_*`. `visible_to_user=False`
and `published_authority=False` on every row.
