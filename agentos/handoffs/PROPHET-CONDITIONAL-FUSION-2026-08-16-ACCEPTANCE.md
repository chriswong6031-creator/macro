---
workstream: WS:PROPHET-CONDITIONAL-FUSION
session: prophet-fusion-acceptance (worktree prophet-fusion-acceptance-c24466)
model: opus
ended_because: complete
prs: ["#5764", "#5767"]
mission: >
  Close the single open post-merge acceptance item for the Chairman override that made
  C1 the canonical US Prophet ranker (PR #5753, b9473646cfbad8bcacbc727af0ef74fa9cb1f72b,
  merged 2026-08-15T13:17:23Z): verify the first authoritative post-merge nightly
  publishes us_prophet_v3 against the 14-item contract, re-run the order comparison on
  the new pool, record the three CEO adjudications, and re-cut W3.
state_before: >
  w2b shipped and merged; its handoff carried ONE unverified claim — that the first
  post-merge nightly publishes rank_by=us_prophet_v3 with a fusion receipt and no
  degradation. Board on main was the pre-override us_prophet_v2 artifact, as_of
  2026-08-13, because the 2026-08-14 nightly (31848262472) was CANCELLED.
changed:
  - path: scripts/us_prophet_fusion_compare.py + tests/test_us_prophet_fusion.py
    what: "PR #5764 (59bd57cf1af4). THE ACCEPTANCE SURFACE COULD NOT READ A v3 BOARD.
      Measured: ReplayMismatch on 69 of 69 rows. Two reads assumed the pre-override
      generation — the freeze check compared the replayed v2 against the PUBLISHED
      score (C1 on a fusion board), and old_rank read display_rank (already the FUSION
      rank, so every delta would have been zero — the new order compared against
      itself). Now reads the retired scorer off the artifact: prophet_shadow whenever
      the board publishes one. New test pins the strong invariant — the same pool must
      produce the same comparison from either board generation."
  - path: agentos/decisions/DEC-PROPHET-SHADOW-GRAIN-IS-A-PAIRED-ROW.md
    what: "PR #5767 (c2484fe7134b). Adjudication B — paired-row shadow accepted over a
      second board_definition key, CONDITIONAL on same population + same outcome + zero
      authority. Those three conditions are the decision."
  - path: agentos/decisions/DEC-FUSION-FAMILY-NEAR-CONSTANCY-IS-A-REGISTRY-QUESTION.md
    what: "PR #5767. Adjudication A — admissibility and discrimination are separate
      properties; the floor governs only the first. F8/F4 near-constancy is a registry
      question for W3, never a floor re-tune."
  - path: research/prophet_fusion/W3_SHADOW_RACE_RECUT.md
    what: "PR #5767. W3 re-cut: the chartered second scorer is DELETED, not deferred —
      production stamps the champion side nightly as prophet_shadow, so a separate
      replay is now a defect. Three lanes: the forward race (accrue now, read later,
      pre-registered), family discrimination (LOFO), coverage drift."
verified:
  - claim: the first post-merge nightly publishes a canonical us_prophet_v3 board that
      passes all 14 acceptance items
    command: "accept_v3.py against the PRODUCTION artifact fetched from the Pages
      deployment of run 31913143619 (deployed 2026-08-16T06:12:24Z)"
    result: "14 PASS · 0 FAIL · 0 NA. rank_by/board_definition/ranking.definition and
      every row's prophet.fusion.definition = us_prophet_v3; 71/71 rows carry both
      prophet.fusion and prophet_shadow(us_prophet_v2_shadow); 5 families active;
      floors captured as_of_night with gex_confirm_verdict stood down on measured
      coverage 0.478873 < 0.5; 0 unscored rows; no fallback stamp; no degradation
      receipt; ZERO us-board-fusion-degraded / us-prophet-fusion-unavailable lines in
      the 56,519-line engine log; HK still hk_prophet_v2 with no fusion block and no
      shadow."
  - claim: the board is ordered by C1 and not by the retired heuristic
    command: "acceptance check 9 — recompute both orders over the published pool"
    result: "published order == canonical fusion order; canonical order differs from
      the shadow order from rank 1 (AYI 16 -> 1); every row's score_authority is the C1
      string; zero rows where the canonical score equals the shadow score."
  - claim: the harness is non-vacuous — a FAIL means a real defect
    command: "three controls before the live run"
    result: "pre-override v2 board -> 11 FAIL; a correct v3 board built through the real
      production path -> 13 PASS/0 FAIL; a genuinely degraded board (fuse_board forced
      to raise) -> FAILs 1/2/10 with check 10 naming us_prophet_v2_fallback. Degradation
      is structurally non-silent: it changes the published definition AND emits a
      line-start ::warning."
  - claim: the order comparison runs on the new pool (STEP 3)
    command: "scripts/us_prophet_fusion_compare.py (post-#5764) over the live board"
    result: "old_definition=us_prophet_v2_shadow, basis=prophet_shadow.score_rank,
      n_buy=71. SITM promoted into the top 30, FORM demoted out; biggest gains RDDT,
      PNW, MTDR, AYI, OKE; biggest losses FORM, IREN, RKLB, SGML, SNPS. AYI 16->1 (+15),
      FTI 2->14 (-12), ONTO 1->4. This is an ORDER COMPARISON, not alpha evidence.
      Without #5764 it raises ReplayMismatch on all 71 rows and prints nothing."
  - claim: the HK suite failures predate the fusion merge
    command: "git checkout b9473646cfbad8bcacbc727af0ef74fa9cb1f72b^ && pytest
      tests/test_hk_board_rank.py"
    result: "13 failed at the PRE-merge commit — the identical TestG1Witnesses set. #5753's
      only change to engine/hk_board_rank.py is a one-line docstring edit, and the
      failing lane path calls hbr.total_return_z/build_leaders_rows, never the shared
      score_rows. Not a regression, not this workstream's."
unverified:
  - claim: F4/F8 near-constancy is PERSISTENT rather than pool-specific
    what_would_verify: "LOFO over genuinely distinct sessions. Tonight's pool overlaps
      the 2026-08-13 committed board by 92% (67 shared names, 4 in, 2 out) and carries
      the SAME as_of 2026-08-13, so the two reads are one session, not two. The numbers
      replicate almost exactly (F1 6.28/5.86, F2 5.66/4.72, F5 2.54/2.32, F4 0.62/0.58,
      F8 0.11/0.12) but that is a re-run over a near-identical pool. Honest-N = 1
      session. This is the W3 Lane C question and it remains OPEN."
  - claim: a v3 night ACCRUES to the forward-race substrate
    what_would_verify: "a nightly whose engine commit actually pushes. Tonight's did
      not, so no v3 row exists in data/us_prophet_rank/candidates/ (latest stamp_date
      2026-08-12) and the LEDGER DAY for this night is lost by the engine's own words."
unresolved:
  - "THE FIRST POST-MERGE NIGHTLY'S PUBLISH PATH FAILED — infrastructure, not fusion.
    Engine (run 31913143619, job 95103895599) built the board correctly and wrote it
    (log: `wrote us_standouts.json (71 buy · rank_by=us_prophet_v3 · 79 eligible / 1596
    universe)`) but could not push: Prophet checkpoint NOT pushed (12 attempts
    exhausted) -> `the final engine commit is fenced from publishing this uncheckpointed
    Prophet tree`; options PIT checkpoint NOT pushed (12 attempts); then step 141
    `commit engine outputs` — 7 rebase/push attempts, 600s time budget exhausted. The
    SAME failure hit the 09:16Z dispatch (31876586624) on a PRE-merge head, so it is
    neither new nor fusion-caused. Net effect: the site still deploys via the Pages
    artifact (which is what this acceptance read), the ledger day does not. Owned by the
    Prophet US availability strand — open issue #5742, rescue budget 1 of 2 spent. A
    daily.yml run was still in flight, so this session did NOT dispatch."
  - "The board's as_of did not advance — still 2026-08-13 while 2026-08-14 is owed
    (#5742). The ranker is verified; the SESSION is stale. Acceptance is a statement
    about the ranker, not about data freshness."
  - "Five per-leg store columns go NULL from the first v3 night: us_context_vector.py
    :899-901/:1070-1071 and us_candidate_lanes.py:481-482 read components/points off
    `prophet`, which on a v3 row is empty because the legs moved to prophet_shadow.
    Verified: v2 row -> prophet_signal 1.0, v3 row -> None. Null-not-zero, so acceptance
    item 12 still holds, but the retired scorer's legs stop accruing for the forward
    race. No US test pins them, so it is silent. Chipped (task_8c904665) with the
    design call left open — leaving them null is defensible."
  - "(inherited) insider_cluster serving-dead; the §13.0 live closure; short_int
    knowable-lag reconciliation; sue_z re-home; PR-1a advisories A3/A4/A5/A7"
next_actions:
  - "W3 Lane A — stand up the forward-race accrual and PRE-REGISTER before any read
    (research/prophet_fusion/W3_SHADOW_RACE_RECUT.md §2). It has no promotion arm."
  - "W3 Lane B — lofo_displacement() in engine/us_prophet_fusion.py; the measure is
    already computable via aggregate(family_keys=...) with no new machinery."
  - "W3 Lane C — the open question above: is F4/F8 near-constancy persistent? Needs
    distinct SESSIONS, not re-runs of one."
  - "Not this workstream: the engine publish-path contention (#5742) and the
    prophet_shadow store columns (task_8c904665)."
do_not_redo:
  - "Do not re-run the acceptance against the repo artifact expecting v3 — the first
    v3 board was NEVER COMMITTED. site/factordata/us_standouts.json on main is still
    the pre-override v2 board, as_of 2026-08-13. The v3 evidence is the Pages
    deployment of run 31913143619 plus that run's engine log."
  - "Do not regenerate the committed FUSION_BOARD_COMPARISON.md from the live pool —
    the script reads site/factordata/us_standouts.json from the repo, which is still v2,
    so a committed comparison built from a production-only artifact would not reproduce
    and would break the freeze check. The new-pool numbers live in this record instead."
  - "Do not read the two LOFO tables as two nights. 92% pool overlap, same as_of."
  - "(inherited) every PR-0/1a/1b/2/2b do_not_redo remains binding, and the two
    decisions in #5767 now close the shadow-grain and near-constancy questions."
danger_areas:
  - "A nightly can publish to the SITE while failing to publish to GIT. `publish`
    succeeded and deployed a v3 board at 06:12:24Z while `engine` concluded failure and
    main kept the v2 artifact. Anything that verifies 'what shipped' by reading the repo
    will report the wrong board on such a night, in either direction."
  - "The engine's fail-closed is load-bearing and worked: an unpushed Prophet checkpoint
    FENCED the final commit rather than publishing a tree it could not vouch for. Do not
    'fix' that fence to make nightlies green."
  - "extract_members must track grade_us_board._row_features — unchanged from w2b and
    still the drift no parity test can see."
---

Cold-stranger summary: the Chairman override's last open claim is now **verified on the
real thing**. The first authoritative post-merge nightly built a canonical
`us_prophet_v3` board over 71 live rows and it passes all fourteen acceptance items —
canonical stamp everywhere the definition is restated, both the fusion receipt and the
`us_prophet_v2_shadow` block on every row, as-of-night floors captured with a measured
reason for the one stood-down member, nulls still null, no fallback, no degradation
line anywhere in a 56k-line engine log, HK untouched.

The twist worth carrying forward is *where* that evidence lives. The nightly's engine
job **failed** — three push-contention failures ending in `commit engine outputs`
exhausting its 600s budget — so the board was never committed, and `main` still serves
the pre-override v2 artifact from 2026-08-13. But `publish` succeeded, so the v3 board
went live via the Pages artifact. A night can therefore ship to the site and not to git,
and any check that reads the repo to learn "what shipped" will be wrong on such a night.
The ranker is accepted; the accrual for this night is lost, and that belongs to the
Prophet availability strand (#5742), not to fusion.

Two things this session found that the acceptance itself did not ask for: the comparison
machinery could not read a v3 board at all (`ReplayMismatch`, 69/69 — fixed in #5764,
and Step 3 would otherwise have printed nothing), and the retired scorer's per-leg store
columns silently go null from the first v3 night. The honest limit on the family
diagnostics: tonight's pool overlaps the previous one by 92% at the same `as_of`, so the
replicated LOFO ordering is one session, not two, and whether F4/F8 near-constancy
persists is still open — which is exactly what W3 Lane C is for.

*Supersedes `PROPHET-CONDITIONAL-FUSION-2026-08-15-OVERRIDE.md` as the latest record for
this workstream without altering it; that file remains the w2b implementation account.*

## PR-3A reconciliation (2026-08-16)

The YAML `unresolved` / `next_actions` blocks above are this acceptance session's
record and are not rewritten. Subsequent merges closed two items a cold reader
would otherwise reopen:

- **Shadow-store / task_8c904665:** resolved by #5769 /
  `DEC:US-SHADOW-ACCRUES-UNDER-ITS-OWN-COLUMN-FAMILY`. Canonical five-leg nulls on
  v3 are correct. Do not copy `prophet_shadow_*` into canonical `prophet_*`.
- **#5742** remains external availability/push-path debt, not Fusion ranking logic.
  W3 counts durable paired stamps, not Pages-only nights.

