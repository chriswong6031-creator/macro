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
status: done
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
    status: done
  - id: W3
    title: "Chairman-directed follow-up: CN/HK/CA dates lit + fold-not-truncate chip (#6752)"
    status: done
next_action: >
  Program complete (live receipts 2026-09-02: US 3 chips persisting 2026-08-31; CN 24
  chips over 4 dates; HK 4 over 3; CA 10 over 5; Intl null pending upstream as_of).
  Remaining accruals are self-serve: CN's first more_actionable fossil row (self-heal
  floor) and the optional rank-authority-safe HK/CA ledger coverage extension, each
  needing its own authorization if pursued.
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
    absence-proofs UNSOUND there — the coverage-floor law
    (DSC:PROPHET-BOARD-TENURE-COVERAGE-FLOOR). Floor GATING is OFF by
    Chairman-directed acceptance (2026-09-02, #6752): CN/HK/CA mint dates from
    canonical-fossil streaks with the bounded demote-return limitation disclosed
    (too-recent date possible, understatement only; CN self-heals via forward
    more_actionable persistence; HK leaders/laggards and CA laggards remain
    unfossiled because persisting display-tier lanes into board_ledger is documented
    to corrupt Spearman rank-IC grading — a rank-authority-safe extension is a
    separately authorized follow-up)."
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
