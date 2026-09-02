---
key: PROPHET-CANDIDATE-ADDED-DATE
title: Prophet candidate "Added date" — truthful board-tenure chip across five boards
objective: >
  Restore the fan-favorite per-candidate "Added <Mon D>" / "入榜 <MM-DD>" chip on every
  Prophet stock-candidate card surface truthfully: board_since = the market-session date
  the candidate entered its CURRENT uninterrupted sequence of published, name-visible
  Prophet-board observations, with left-censoring and coverage-floor soundness (a date
  the history cannot prove is null, never fabricated), page-level "Data through"
  freshness preserved on every market, and the three clocks (board freshness, candidate
  tenure, plan/signal vintage) permanently separated.
status: active
program: prophet
repos: [macro]
owner: fable
class: build
blast_radius: user_facing
ambiguity: specified
owns_paths:
  - engine/prophet_board_since.py
  - tests/test_prophet_board_since.py
  - tests/test_prophet_candidate_added_date_surfaces.py
  - tests/test_prophet_card_added_date.py
  - tests/test_build_china_library_more_actionable_guard.py
  - mockups/refs/prophet-candidate-added-date-e2e/
waves:
  - id: W1
    title: "E2E build + double adversarial review + evidence + merge + live proof (#6719)"
    status: done
  - id: W2
    title: "Nightly persistence receipt (US dates retained; CN floor row appears)"
    status: in_progress
next_action: >
  Confirm the nightly-persistence receipt (US live cards retain Added dates after the
  next daily run; CN fossil gains its first more_actionable row), then flip status to
  done. HK/CA coverage extension remains a separate unauthorized follow-up.
decisions:
  - DEC:SOL-HOLD-IS-A-MERGE-BARRIER
landmines:
  - "board_since is CURRENT-STREAK tenure from published fossils, NEVER first-ever
    appearance, and NEVER signal.asof / board as_of / build date / wall clock /
    candidate_episode.opened_at. Left-censored (present at the oldest observation
    with starts_at_inception=False) => null, no chip. All four markets are
    adjudicated starts_at_inception=False with git receipts (see the 2026-09-02
    handoff)."
  - "Membership != display. Tenure is sustained by fossil presence in ANY live
    name-visible lane (US buy+watch+leaders+laggards+ran; HK/CA
    entry_open+setting_up+watch; CN live-definition rows); the chip renders only on
    pv_card surfaces. A lane the page shows but the fossil does not persist makes
    absence-proofs UNSOUND there — that is the coverage-floor law
    (DSC:PROPHET-BOARD-TENURE-COVERAGE-FLOOR), and why HK and CA ship null pending a
    rank-authority-safe ledger coverage extension (a follow-up program that needs its
    own authorization; HK leaders/laggards and CA laggards are name-visible but
    unfossiled, and persisting display-tier lanes into board_ledger is documented to
    corrupt Spearman rank-IC grading)."
  - "CN persists more_actionable rows under a distinct <definition>_more_actionable
    board_definition, appended ONLY when the same build has a non-empty featured set
    (scripts/build_china_library.py guard) — otherwise a zero-featured night lets the
    shelf hijack china_standout_track._latest_definition_frame's headline pick inside
    grading authority. CN dates accrue only for names joining after the dynamic floor
    (first more_actionable fossil row post-merge)."
  - "Intl has NO point-in-time membership ledger: board_since is artifact
    carry-forward only (prior committed site/factordata/intl_setups.json read before
    the single write; minting gated on BOTH as_ofs being valid ISO with current >
    prior; as_of is currently null upstream, so Intl ships all-null until that is
    repaired). Git-history bootstrapping was REJECTED: dead under render.yml
    fetch-depth:1 and network-bound on the blobless clone."
  - "grade_us_board::_board_tenure (grading authority) uses different
    missing-observation semantics (consecutive as_of dates; a gap resets) — the two
    tenures are documented as divergent, deliberately NOT reconciled."
  - "US locked shell / unlocked payload parity is structural: one shared
    _us_board_cards.html.j2 partial feeds both. Never add a second derivation path."
do_not_redo:
  - "Do not revert #6532/#6544 (board-freshness header repair) or reintroduce any
    per-card as-of date on candidate cards."
  - "Do not resurrect the #6687 resolver semantics: it emitted the oldest-history
    date under left-censoring and preferred computed dates over persisted truth."
  - "Do not weaken tests/test_p_mp1_shell_nonus_byte_parity.py to keyword scans or
    merge-base diff pins — its guards are merge-safe SHA-256 byte pins of current
    content, kept that way after two proven self-destruct/weakening incidents."
---
