---
workstream: "WS:STOCK-IDENTITY"
session: "claude/si-w3s-dead-control (worktree stock-identity-w3s-control-46d8fa)"
model: opus
ended_because: blocked
prs: [6678]
mission: >
  Operation SI-W3S-DEAD-CONTROL-V1 (packet commit 0e65358a3e15707f1f769720bce195a99078c6bf,
  blob 421638c488dfa7c44a36608e1e1fbf3b07c96714). Produce either >=5 identity-resolved
  terminated U.S. instruments with lawful full adjusted OHLCV that run through the existing
  Stock Identity fingerprint/episode machinery, or the typed blocker BLOCKED_NO_LAWFUL_DATA.
  W3S is a hard survivorship predecessor of W5/Q1 and does not wait on W3A/W3AR.
state_before: >
  config/delisted_symbols.yml held 3 resolved exit rows (AVB, CTRA, TPH) — not the 2 rows the
  commission packet recorded as starting truth, so the packet's "verified starting truth" was
  already stale. Neither engine/stock_identity/dead_control.py nor
  scripts/stock_identity_build_dead_control.py existed. The prior W3S inventory had returned
  NEEDS_BOUNDED_SOURCE_ACT. data/stock_identity/ohlcv carried exactly 2 symbols (BABA, WPM).
changed:
  - path: research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md
    what: >
      NEW and load-bearing. Preregisters the candidate population (P = S-A union S-B union S-C
      with per-source hashes), the deterministic ordering, the S1-S10 screen ladder with one
      exclusion code per screen, the blinding rule (no screen may read returns, drawdowns,
      fingerprint values, episodes or any outcome), and the no-hand-picking rule (every passer
      is accepted; five is a floor for success, never a target to select down to). Committed
      BEFORE any tape was screened, which is the entire scientific value of the cohort.
      Amendment A1 — also recorded before any tape read — corrects S10 from "the Polygon leg
      only" to "any code-asserted split+dividend-adjusted leg", because the original wording
      was drafted around the dead-name store and silently barred data/baskets/ohlcv, an
      existing registered plane. Section 10 records the execution result.
  - path: engine/stock_identity/dead_control.py
    what: >
      NEW. Executes the registered ladder and selects nothing. Population enumeration with
      SHA-256 per source, the zero-volume flat-forward padding stripper, a plane-tip liveness
      check, and the screens. Reuses engine.stock_identity.hygiene for ticker-identity verdicts
      and .plane for loading; adds no provider, no collector and no new price plane.
  - path: scripts/stock_identity_build_dead_control.py
    what: >
      NEW CLI. Exit 0 = RESULT (>=5 controls each with a passing compatibility smoke), exit 3 =
      BLOCKED_NO_LAWFUL_DATA. Writes data/stock_identity/control/dead_control_cohort.json and
      emits a line-start ::warning on the blocked path. Never pads a short cohort.
  - path: data/stock_identity/control/dead_control_cohort.json
    what: >
      NEW receipt. The full 223-name candidate and exclusion ledger — every eligible candidate
      with its terminal disposition and exactly one exclusion code — plus per-source content
      hashes, plane tips, the directory window, and an all-false authority block.
  - path: tests/test_stock_identity_dead_control.py
    what: >
      NEW. 13 tests over a hermetic fixture repo, including the registration's hostile
      fixtures: live-name-relabeled-dead, index-exited-but-listed, OTC ADR never
      exchange-listed, successor splice, reused ticker, key migration, close-only tape and
      short history — each must be REFUSED — plus one clean tape that must be ACCEPTED (so the
      refusals are not vacuous), determinism, the no-authority invariant, and a pin that
      MIN_SESSIONS tracks fingerprint.MIN_SESSIONS rather than being a local knob.
verified:
  - claim: The builder returns BLOCKED_NO_LAWFUL_DATA with 0 accepted from a 223-name population.
    command: python3 scripts/stock_identity_build_dead_control.py
    result: >
      "population=223 accepted=0 compatible=0 terminal_state=BLOCKED_NO_LAWFUL_DATA", process
      exit 3. Exclusions E1_NOT_TERMINATED=100, E3_NOT_US_LISTED=119,
      E6_NO_LAWFUL_ADJUSTED_OHLCV=2, E8_TAPE_CONTAMINATED=2.
  - claim: The cohort build is deterministic across runs.
    command: python3 -c "import json,hashlib; from engine.stock_identity import dead_control as dc; [hashlib.sha256(json.dumps(dc.build_cohort('.'),sort_keys=True).encode()).hexdigest() for _ in range(2)]"
    result: both runs hash 1901c97382b5b635 — byte-identical.
  - claim: Every hostile fixture is refused and a clean terminated tape is accepted.
    command: python3 -m pytest tests/test_stock_identity_dead_control.py -q
    result: 13 passed.
  - claim: A terminated tape runs clean through the CURRENT fingerprint and episode inputs.
    command: python3 -c "plane.load_symbol -> fingerprint.compute_raw + episodes.build_catalog using sealed data/stock_identity/constants/si_constants_v1.json"
    result: >
      FBRX 2355 sessions -> 64 metrics, 52 non-null, 50 episodes. TWO 3179 sessions -> 64
      metrics, 52 non-null, 46 episodes. The pipeline is proven end to end.
  - claim: data/stocks/AVB.parquet carries real bars past AVB's own ledger last_session.
    command: python3 -c "import pandas as pd; print(pd.read_parquet('data/stocks/AVB.parquet').tail(8))"
    result: >
      bars through 2026-08-24 with real volume (17,443,419 on 2026-08-17) against
      config/delisted_symbols.yml last_session 2026-08-14 — the documented successor splice.
  - claim: plane.load_symbol does not truncate a tape at the delisted ledger's last_session.
    command: sed -n '112,160p' engine/stock_identity/plane.py; grep -rn "last_session" engine/stock_identity/
    result: >
      the loader sorts, de-duplicates and drops non-positive closes only; no delisted-ledger
      truncation exists, so a contaminated parquet reaches the behavioral layer intact.
  - claim: The existing dead-name owner already requests adjusted full bars but persists close only.
    command: sed -n '120,145p' collectors/edgar_deadname_prices.py
    result: >
      URL carries "?adjusted=true&sort=asc&limit=50000", then
      s = pd.Series([b["c"] for b in res]) discards o/h/l/v; the persisted schema at :235-236 is
      ticker,date,close,source.
  - claim: No Polygon credential is resolvable in this environment.
    command: python3 -c "import os; from lib import config; os.environ.get('POLYGON_API_KEY'); config.load()"
    result: env POLYGON_API_KEY ABSENT, config.polygon.api_key ABSENT, config.keys.polygon ABSENT.
  - claim: With open PR #6668's exit ledger the same unmodified ladder accepts exactly 2.
    command: git show pr6668:config/delisted_symbols.yml > tmp; swap into place; dead_control.build_cohort('.'); restore
    result: >
      accepted=2 (FBRX, TWO); AVB still E8_TAPE_CONTAMINATED, CTRA/TPH still
      E6_NO_LAWFUL_ADJUSTED_OHLCV. Ledger restored afterwards, git diff clean.
  - claim: The working tree carries no unintended data/ writes despite starting sparse.
    command: git status --porcelain
    result: only the four intended new paths are present.
unverified:
  - claim: LEG, EQR and RMAX are genuinely terminated rather than stale, halted or venue-changed.
    what_would_verify: >
      a #4622-protocol adjudication per name — a Form 25/25-NSE accession or a
      completed-transaction 8-K, plus current directory absence — which is exactly the evidence
      PR #6668 supplies for FBRX and TWO. All three are currently EXCLUDED at S1 and were never
      accepted; they appear only inside a labelled feasibility probe.
  - claim: Persisting o/h/l/v from the existing Polygon dead-name call would yield >=5 controls.
    what_would_verify: >
      run scripts/build_dead_name_prices.py with a POLYGON_API_KEY present and re-screen. Note
      that store is close-only today and is a DIFFERENT plane from baskets_ohlcv_v1, which
      supplied the only qualifying tapes observed here, so the act is necessary but may not be
      sufficient.
unresolved:
  - >
    The shortfall is adjudication EVIDENCE, not data. A labelled feasibility probe shows 6
    plane-resident names clear the tape screens S5-S10, but only 2 have committed termination
    evidence and only after PR #6668 merges. Roughly 3 further lawful adjudications are needed
    to reach five, and ISSC is a known key migration that real evidence would reject at S2, so
    the true adjudication target is narrower than the probe's six.
  - >
    data/stocks/AVB.parquet still carries 6 post-last_session successor bars at base
    5037814d4367, although the ledger's own comment states the store was "restored to the real
    AvalonBay basis and truncated at last_session" on 2026-08-28. Either that heal did not land
    or it did not truncate. This is a live hazard for every Stock Identity consumer, not only W3S.
  - >
    PR #6668 (claude/reused-tickers-delist-adjudication) is the upstream dependency and is
    currently labelled both merge-on-green and merge-blocked.
next_actions:
  - >
    Sol ruling: proceed by commissioning roughly 3 further #4622 adjudications for
    plane-resident terminated names (the narrow, high-yield path), or hold W3S until the
    dead-name OHLCV persistence act can be run with a real Polygon credential.
  - Land PR #6668 to convert FBRX and TWO from E1_NOT_TERMINATED to accepted controls (2 of 5).
  - >
    Investigate the AVB truncation gap independently of W3S — a contaminated tape sitting on a
    registered plane will silently reach fingerprint and episode consumers.
  - >
    Re-run python3 scripts/stock_identity_build_dead_control.py after any of the above. It is
    deterministic and re-screens the entire population; no state needs resetting.
do_not_redo:
  - >
    Do NOT treat collectors.edgar_deadnames.dead_universe() as a death list. It closes on a
    CLOSED S&P membership row, which is an INDEX EXIT; 172 of its 1,083 names still trade
    today. Measured here: 119 of 223 candidates fail S3 for exactly this reason.
  - >
    Do NOT treat absence from the exchange symbol directory as death. That is the normal LIVE
    state of an OTC ADR — ANGPY, IMPUY and RHHBY all sit in the population for this reason.
  - >
    Do NOT trust a dead name's tape because it is long and adjusted. yfinance splices the
    acquirer's continuing series onto the dead symbol (the AVB case) and plane.load_symbol will
    not truncate it for you.
  - Do NOT re-derive the history floor. It is fingerprint.MIN_SESSIONS = 252, pinned by a test.
  - >
    Do NOT pad the cohort to five, hand-pick names after seeing tapes, or widen providers or
    criteria to clear the bar. The registration forbids all four and an explicit Sol act is
    required to change any of them; the honest terminal state is exit 3.
  - >
    The bounded Polygon persistence act was NOT run — not because it is wrong or forbidden, but
    because no credential is resolvable in this environment. Do not re-diagnose it as blocked
    for any other reason, and do not repeat the credential search.
danger_areas:
  - >
    _plane_tip needs a meaningful file count to mean anything. Below TIP_MIN_FILES = 20 the
    candidate becomes its own modal tip and the S8 liveness check would refuse the very tape it
    exists to protect, so it returns None below the floor deliberately.
  - >
    Screen ORDER is load-bearing because the first failure assigns the code, so reordering
    changes which cause is reported and can mask the real one. Padding must be stripped before
    S7 counts sessions, and the curated ledger's last_session must be checked before the
    directory-cadence heuristic so a splice is reported against the strongest evidence.
  - >
    TERMINAL_GRACE_SESSIONS = 10 absorbs symbol-directory snapshot cadence — the archive has a
    real 9-day gap — and nothing else. Raising it starts admitting successor series.
  - >
    The registration is the law and this module only executes it. Editing a screen so the
    cohort reaches five is precisely the failure the preregistration exists to prevent.
---

# W3S Dead Instrument Control Set — BLOCKED_NO_LAWFUL_DATA

The cohort law is `research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md`; this
record is the session receipt. Terminal state is the typed blocker, not a failure to build:
the screens ran over 223 candidates and refused every one, and the refusals are the finding.
The two halves a survivorship control needs — proven termination and a lawful full adjusted
tape — exist in this repo but not on the same names.
