---
workstream: WS:PROPHET-US-V4-RECOVERY
session: "builder (Sonnet, ROUTE:build, D2B2-CN-HK wave)"
model: sonnet
ended_because: complete
mission: >
  V4-D2B2-CN-HK (Sol authority adjudication 2026-08-20,
  DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK, resolving the China Alpha pr0d
  owner collision): admit the current source-supported China/HK listing
  population into the canonical Data OS security/issuer/listing master via
  its canonical builder, or return a typed refusal for every targeted object;
  then re-derive the GMI identity_resolution/v1 sidecar so real China/HK
  company nodes resolve through canonical Mastermind ids.
state_before: >
  At pin 0c95d986d010 (origin/main): the Data OS master was 100% US (705
  rows, 704 active + 1 VMRK tombstone from D2B1-R1). Every co:cn:*/co:hk:*
  GMI company node was NOT_IN_MASTER by design (D2A rule 7) — 1,021 cn + 147
  hk company nodes, ~75% of GMI China company nodes unresolved. The China
  Alpha wave pr0d had stopped at a D2B2 owner-collision escalation (its
  commission mistakenly pointed at WS:STOCK-IDENTITY); Sol ruled the China
  lane is not authorized to implement identity expansion itself.
changed:
  - path: scripts/build_security_master.py
    what: >
      A SEPARATE, additive admission stage: load_cn_hk_seeds() (target
      population from data/theme_graph/nodes.parquet, kind=company,
      market_scope in cn/hk — upstream graph truth, never the derived
      sidecar), load_cninfo_evidence() (CN existence evidence from committed
      data/china_filings/filings.parquet), load_hk_shorts_evidence() (HK
      existence evidence from committed data/hk_shorts/{positions,
      turnover}.parquet), mint_cn_hk_rows() (mints via
      lib.dataos.identity.normalize_cn_symbol/normalize_hk_symbol — no new
      grammar, no lib/dataos edits). New vendor space
      VENDOR_THEME_GRAPH_NATIVE = "theme_graph_native" (current-catalog,
      carries the GMI node's own suffix-qualified symbol spelling). Wired
      into build(): existing committed master rows are split by country
      BEFORE reaching mint_master_rows (a real bug found and fixed — see
      "danger_areas") and CN/HK rows are folded back in before the
      security-supersession/issuer-correction passes, which run unmodified
      over the combined set. New receipt block china_hk_admission (target_n,
      resolved_this_run, refused_this_run, resolved_total,
      refusals_this_run — named, per market, no silent drop).
  - path: data/reference/
    what: >
      security_master.parquet 705 -> 1,836 rows (+984 CN, +147 HK); every
      new row issuer_id=None/issuer_state=NO_ISSUER_EVIDENCE (settled by the
      existing apply_issuer_correction pass — no CN/HK issuer-evidence class
      introduced). vendor_aliases.parquet +1,131 theme_graph_native rows.
      US rows byte-identical (verified: 705 US rows, 704 active/1
      superseded, unchanged). _receipt.json gains china_hk_admission.
  - path: data/theme_graph/identity_resolution.parquet
    what: >
      One new generation baked by direct derive_rows()+write_identity_
      resolution() call (never the full theme_graph pipeline in a worktree,
      DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY) over the committed
      nodes.parquet + the new master. engine/theme_graph/
      identity_resolution.py needed ZERO code changes (already
      market-agnostic; F1's cross-market guard already covers cn/hk). CN
      RESOLVED 0->984 (96.4%), HK RESOLVED 0->147 (100%), all via
      join_method=vendor_alias (rule 6 — inception_code never string-equals
      the suffixed source_native_symbol for CN/HK, so rule 5 structurally
      cannot fire). US/intl/ca states unchanged.
  - path: data/theme_graph/_meta.json
    what: >
      identity_resolution_state_counts updated to match the new bake
      (RESOLVED 702->1833, NOT_IN_MASTER 1868->737); every other field
      (local_plane, per_suite, capability_counts, computed_at) left
      untouched — those describe the last FULL pipeline run, which this
      targeted sidecar-only bake did not re-run.
  - path: tests/test_dataos_security_master.py
    what: >
      +14 tests: 5 hostile fixtures on real committed data (A/H dual listing
      ICBC, renamed security 300223, SOE naming-collision 601988/601601,
      unresolved issuer, alias-only vendor id), complete-accounting +
      disclosure tests, mint_cn_hk_rows unit tests (idempotency, refusal
      typing, unparseable-symbol typing), F1 cross-market sanity, US-coverage
      -unchanged pin. 2 pre-existing tests rescoped (table-wide row/state
      counts -> country=="US"-scoped or master-fixture-derived — the table's
      grain is now multi-market, the underlying invariants are unchanged).
  - path: tests/test_theme_graph_identity_resolution.py
    what: >
      test_every_cn_hk_ca_node_is_not_in_master split: ca-only version
      retained (Canada remains unauthorized, still 100% NOT_IN_MASTER across
      every generation); +3 new tests — pre-D2B2-generation cn/hk still
      NOT_IN_MASTER (append-only history untouched), current-view
      resolution-rate assertions cross-checked against the master receipt's
      own accounting, join_method universally vendor_alias.
  - path: agentos/workstreams/{WS-PROPHET-US-V4-RECOVERY,WS-CHINA-ALPHA-INTELLIGENCE}.md
    what: >
      d2 wave / pr0d wave notes updated to BUILT_NOT_PROVEN with PR #6116 /
      branch claude/d2b2-cn-hk (immutable merge SHA recorded once merged).
verified:
  - claim: Start-pin census matches the contract's own re-census law.
    command: >
      pandas over data/theme_graph/identity_resolution.parquet's latest
      generation, market_scope in (cn,hk), resolution_state==NOT_IN_MASTER
      -> 1021 cn / 147 hk (sums with us 533 + ca 167 to the pre-existing
      1,868 total observation, confirming no double-count).
  - claim: >
      984/1021 CN codes and 147/147 HK codes have committed primary-source
      evidence; the CNInfo `exchange` column is unreliable for MIC
      assignment (sampled SZSE-range codes labelled "sse") and is never
      consulted — MIC comes only from the code's own numeric range via the
      existing lib.dataos.identity functions.
    command: >
      pandas intersection of theme_graph node codes against
      data/china_filings/filings.parquet sec_code / data/hk_shorts/
      {positions,turnover}.parquet stock_code, both zero-padded to canonical
      width; manual spot-check of exchange="sse" rows against known SZSE
      codes (300332, 002985, ...).
  - claim: Idempotent — a second build() run over both an empty scratch dir
      and the real committed baseline produces byte-identical
      security_master.parquet/vendor_aliases.parquet.
    command: >
      python3 -c script comparing security_master.parquet bytes across two
      consecutive BUILD.build(tmp, dry_run=False) calls, once from empty
      and once seeded from a copy of the real committed data/reference/.
  - claim: >
      Guard strict mode clean; census RESOLVED=1833, NOT_IN_MASTER=737,
      UNSUPPORTED_MARKET=233, DEFERRED=2, ENTITY_TYPE_CONFLICT=1 (2806
      total, row count unchanged).
    command: python3 scripts/check_theme_graph_contracts.py --strict
  - claim: 379 targeted tests green; agentos validate exit 0.
    command: >
      python3 -m pytest tests/test_dataos_identity.py
      tests/test_dataos_security_master.py tests/test_dataos_registry.py
      tests/test_theme_graph_identity_resolution.py
      tests/test_theme_graph_contracts.py tests/test_identity_seam_agreement.py
      -q; python3 scripts/agentos.py validate
next_actions:
  - >
    SURVIVAL PROOF (Sol's completion law): the first natural production
    nightly must demonstrate real China/HK nodes flowing source -> canonical
    master -> GMI projection, with the run id and the measured CN/HK
    resolution delta recorded in this WS's wave note and China Alpha's pr0d
    wave note. Neither wave flips to done before that.
  - >
    Record the immutable squash-merge SHA (never a mutable branch-head SHA)
    in both WS wave notes once this PR merges.
  - >
    The 37 CN refusals self-heal as CNInfo's committed accrual window
    widens (the collector is forward-only) — no action needed; a future
    nightly run of build_security_master.py will pick them up automatically
    when evidence lands, mint-once-safe.
  - >
    HK is at 100% today because SFC+HKEX committed data already covers every
    GMI-tracked HK code; a FUTURE GMI hk expansion (new co:hk:* nodes) will
    need the same evidence-availability check re-run — not automatic if the
    new codes are outside SFC's short-position/HKEX-turnover coverage.
unresolved:
  - >
    No issuer-evidence class exists for CN/HK (issuer_id stays null for the
    whole population this era) — a future child could introduce one (e.g.
    CNInfo org_id, or a GLEIF LEI lookup) under its own frozen contract; this
    child deliberately did not, to avoid any risk of fabricating an A/H or
    SOE-subsidiary issuer relationship without deterministic evidence.
  - >
    CNInfo's `exchange` column (collectors/china_filings.py) is unreliable
    for venue assignment — flagged but not fixed (out of this child's file
    scope; china_filings.py is not an owned file). Named here so a future
    session does not trust it.
unverified:
  - >
    The exact wall-clock date the nightly identity refresh (daily.yml,
    wired by D2B1 §7) will first pick up this merge and re-derive under
    production conditions — this session's bake was a local, targeted
    derive_rows() call, not the nightly's own run.
do_not_redo:
  - >
    Do not re-derive the GMI sidecar via the full scripts/build_theme_graph.py
    pipeline in a worktree — it diverges from main's own nightly state
    (DSC:THEME-GRAPH-FULL-REBAKE-DIVERGES-LOCALLY). Call
    engine.theme_graph.identity_resolution.derive_rows() +
    engine.theme_graph.store.write_identity_resolution() directly over the
    committed nodes.parquet, exactly as this PR did.
  - >
    Do not feed CN/HK master rows into scripts.build_security_master's
    mint_master_rows() `existing` parameter — its pending-transition fence
    (_compute_lost) is US-only and will flag every non-US row "lost" on the
    very next run (VERIFIED, then fixed here — see build()'s
    existing_us_rows/existing_cn_hk_rows split).
  - >
    Do not trust collectors/china_filings.py's `exchange` column for venue —
    it names the CNInfo query batch, not a verified listing venue (VERIFIED
    SZSE-range codes labelled "sse"). Derive venue from the code's own
    numeric range via lib.dataos.identity only.
  - >
    Do not store a CNInfo sec_name / HK stock_name into security_master.parquet
    — the schema has no name column by design, and CNInfo's sec_name
    demonstrably changes over time (300223 ST-flag removal) inside the
    committed evidence window; storing it would fabricate a historical name
    lineage this builder's current-identity-only law forbids.
danger_areas:
  - >
    A future session extending build_security_master.py for ANOTHER new
    market (Canada, per D2B2's still-unauthorized backlog) MUST repeat the
    country-split-before-mint_master_rows pattern this PR introduced, or
    reproduce the same false-"lost" regression for that market's rows too.
  - >
    _compute_lost / the pending-transition fence remain scoped to
    country=="US" existing rows by construction — if a future change widens
    mint_master_rows() itself to be market-generic, the fence's "lost" law
    (§5 of D2B1-R1) needs an explicit per-market re-derivation, not a blanket
    widening (a lost CN row and a lost US row are not evidenced the same
    way — the US fence's independence check is keyed to the SEC CIK map,
    which has no CN/HK analog yet).
---

# V4-D2B2-CN-HK handoff — China/HK canonical identity admission

PR #6116, branch `claude/d2b2-cn-hk`. Single-pass Sonnet builder session
(ROUTE:build) under `DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK`. Contract:
`research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md`.

Merge state: **BUILT_NOT_PROVEN**. `done` requires the first natural
production nightly to demonstrate real China/HK nodes flowing
source → canonical master → GMI projection, with a recorded run id and the
measured CN/HK resolution delta — per Sol's completion law, restated
verbatim in the frozen contract's "Completion law" section.
