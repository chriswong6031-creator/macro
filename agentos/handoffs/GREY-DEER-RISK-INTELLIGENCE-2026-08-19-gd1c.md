---
workstream: "WS:GREY-DEER-RISK-INTELLIGENCE"
session: "claude/gd1c-design-era-20260819"
model: codex
ended_because: complete
discoveries:
  - DSC:GD1C-PIT-MEMBERSHIP-PREHISTORY-ABSENT
mission: >
  Execute GD-1C as a research-only prerequisite for any GD-5 build: freeze a
  fresh preregistration before outcome access, reconstruct the current
  leadership_crack.v1 definition over 2016-01-04..2026-07-31 with explicit PIT
  versus def_current_cf membership lanes, test frozen GD-H1/GD-H2 with
  episode-level effective N and every promotion gate, and return named
  per-hypothesis verdicts without production or authority changes.
state_before: >
  GD-1 was accepted with zero promotions under
  DEC:GD1-ACCEPTED-NO-PROMOTION. leadership_crack.v1 had a 15-row emission log
  beginning BROKEN in July 2026, no design-era emitted history, and no GD-1C
  preregistration or reconstruction artifacts. GD-1C was in_progress and every
  GD-5 wave remained gated on it.
changed:
  - path: research/grey_deer/gd1c/GD1C_PREREG_2026-08-19.md
    what: >
      New GD-1C registration freezing the verbatim GD-H1/GD-H2 hypotheses,
      primary PIT and secondary def_current_cf lanes, episode anchors,
      outcomes, folds, calibration, block bootstrap, BH family, all section 12
      gates, and BLOCKED-precedence law before design-era outcome access.
  - path: research/grey_deer/gd1c/
    what: >
      Research-only current-definition runner plus content-addressed
      reconstruction manifest/rows, independent episode ledger, eight-row gate
      scorecard, August out-of-design coverage, source-rights/gaps report,
      run receipt, and final results/adjudication. No data/ or site/ output.
  - path: agentos/discoveries/DSC-GD1C-PIT-MEMBERSHIP-PREHISTORY-ABSENT.md
    what: >
      Durable discovery with falsifier and so_what: tracked basket membership
      begins in June 2026 and cannot establish PIT cohort identity over the
      design era.
  - path: agentos/workstreams/WS-GREY-DEER-RISK-INTELLIGENCE.md
    what: >
      Existing canonical workstream only: adds the GD-1C discovery, records both
      BLOCKED primary verdicts and zero secondary PASSes, keeps GD-1C
      in_progress pending commissioned Fable acceptance review, and leaves
      GD-5A/B/C closed.
  - path: agentos/handoffs/GREY-DEER-RISK-INTELLIGENCE-2026-08-19-gd1c.md
    what: >
      This cold-start continuation/acceptance packet under the one canonical
      WS:GREY-DEER-RISK-INTELLIGENCE identity.
verified:
  - claim: >
      The preregistration freeze commit contains only the prereg file and
      predates every analysis artifact.
    command: >
      git diff-tree --no-commit-id --name-only -r
      fce7bfeb8c925748ed92b54a7b19901c3a9f35c1 && git log --reverse
      --format='%H %cI %s' -- research/grey_deer/gd1c/
    result: >
      Freeze fce7bfeb8c925748ed92b54a7b19901c3a9f35c1 names only
      GD1C_PREREG_2026-08-19.md; stamp 37ca71ecdd48 follows it; analysis commit
      722ddaf60443 follows both.
  - claim: >
      The registration receipt has the recorded tree and content digests.
    command: >
      git show -s --format='%H%n%cI%n%T'
      fce7bfeb8c925748ed92b54a7b19901c3a9f35c1 && git show
      fce7bfeb8c925748ed92b54a7b19901c3a9f35c1:research/grey_deer/gd1c/GD1C_PREREG_2026-08-19.md
      | shasum -a 256
    result: >
      Commit time 2026-08-19T21:38:16-07:00; tree
      97b0bbc485d256ed6270f604c96a8fee0a0f21da; prereg content SHA-256
      d197cfaab658924124c117246227dd17aae334938e0b3ba55fff3ddc264e3aed.
  - claim: >
      The primary PIT cohort membership is not reconstructable over the design
      era.
    command: >
      git log --reverse --format='%H|%cI|%s' --
      data/baskets/membership.json && jq
      '{ai_semiconductors:.baskets.ai_semiconductors,ai_infra:.baskets.ai_infra,memory_storage:.baskets.memory_storage,semicap_equipment:.baskets.semicap_equipment}'
      data/baskets/membership.json
    result: >
      Earliest tracked membership receipt is
      29721d07084c0332e1c2b5387a32addc1863c395 on 2026-06-14; the four current
      baskets are 2026-curated and expose retrospective added fields but no
      first-known per-member membership clocks covering 2016-2026.
  - claim: >
      GD-H1 and GD-H2 both return primary BLOCKED, and no secondary endpoint
      clears all frozen numeric gates.
    command: >
      python3 research/grey_deer/gd1c/GD1C_RECONSTRUCT_AND_TEST.py && python3
      -c "import pandas as p; d=p.read_csv('research/grey_deer/gd1c/GD1C_GATE_SCORECARD.csv'); print(d.groupby('hypothesis').primary_verdict.unique().to_dict(), d.all_secondary_numeric_gates.any())"
    result: >
      {'GD-H1': ['BLOCKED'], 'GD-H2': ['BLOCKED']} and False; 2,672
      reconstruction rows, 556 endpoint-episode rows, and eight gate records.
  - claim: >
      The fail-closed research verifier reproduces the topology, identity,
      effective-N, gate, digest and no-production-mutation checks.
    command: python3 research/grey_deer/gd1c/GD1C_VERIFY.py
    result: >
      PASS; freeze fce7bfeb8c925748ed92b54a7b19901c3a9f35c1; primary
      GD-H1=BLOCKED and GD-H2=BLOCKED; no secondary PASS; data_site_dirty=false.
  - claim: >
      Episode accounting is deduplicated and confined to the design era.
    command: >
      python3 -c "import pandas as p; d=p.read_csv('research/grey_deer/gd1c/GD1C_EPISODE_LEDGER.csv',parse_dates=['episode_anchor']); assert d.episode_anchor.max()<=p.Timestamp('2026-07-31'); assert not d.duplicated(['hypothesis','endpoint','episode_anchor']).any()"
    result: >
      Exit 0; 556 endpoint-episode rows are unique on hypothesis, endpoint and
      anchor, and no episode anchor exceeds 2026-07-31. The scorecard records
      204 GD-H1 raw fires collapsing to 64 effective episodes and 220 GD-H2 raw
      fires collapsing to 75 effective episodes.
  - claim: >
      AgentOS records are schema-valid.
    command: python3 scripts/agentos.py validate
    result: >
      0 errors; pre-existing advisory warnings only.
  - claim: >
      The research run mutated neither production data nor rendered site files.
    command: git status --short -- data site
    result: empty
unverified:
  - claim: >
      Fable has accepted the GD-1C scope, preregistration topology, and BLOCKED /
      no-promotion adjudication.
    what_would_verify: >
      Fable review on the GD-1C PR explicitly checking the commission, freeze
      topology, primary blocker, secondary labels, and section 12 scorecard.
  - claim: >
      A lawful PIT membership and first-available nominal-rate history can be
      recovered for a future primary rerun.
    what_would_verify: >
      Date-effective membership receipts covering the design era plus
      first-available DGS10/DGS30 vintages, followed by Fable approval and a new
      preregistration version before outcome access.
unresolved:
  - "Fable scope + prereg-topology acceptance review is still required by the GD-1C commission."
  - "PIT cohort membership for 2016-01-04..2026-07-31 is absent; current-membership rows remain def_current_cf."
  - "DGS10/DGS30 local files are latest-revised and cannot satisfy primary temporal integrity."
  - "GD-5A/B/C remain closed because neither hypothesis cleared a promotion gate."
next_actions:
  - "Fable reviews the PR against the canonical GD-1C commission and verifies freeze commit fce7bfeb8c925748ed92b54a7b19901c3a9f35c1 predates every outcome artifact."
  - "On acceptance, update the GD-1C wave from in_progress to done and record zero GD-5 promotions; do not make a GD-5 builder commission."
  - "If PIT membership and rate vintages are later recovered, obtain Fable approval and freeze a new preregistration version before rerunning outcomes."
do_not_redo:
  - "Do not relabel current 2026 membership or retrospective added dates as PIT identity."
  - "Do not pool pit_membership with def_current_cf rows or let the secondary lane rescue the primary BLOCKED verdict."
  - "Do not tune thresholds, endpoints, episodes, or volatility transforms on August 2026."
  - "Do not start GD-5A/B/C; GD-1C issued zero promotions."
  - "Do not infer any live market, Prophet, Portfolio, alert, rank, sizing, gate, or execution authority."
danger_areas:
  - "leadership_crack.v1 uses the current fresh-member denominator even before recent IPO rows exist; preserve this only when reproducing def_current_cf, never call it PIT."
  - "FRED DGS/VIX files are latest-revised and lack first-known clocks; they are secondary-only here."
  - "The full worktree is required before reading data; never run a writer into omitted data/ or site/ trees."
  - "A merge/rebase that rewrites prereg commit fce7bfeb8c92 invalidates the stamped SHA; merge moving main instead of rebasing this branch."
prs: [6038]
decisions:
  - DEC:GD1-ACCEPTED-NO-PROMOTION
---

# GD-1C continuation and acceptance packet

## Exact finding

The primary scientific question is unanswered by lawful PIT data and therefore
`BLOCKED`, not guessed. The current-definition/current-membership
`def_current_cf` substitute is informative but adverse: no endpoint clears all
gates, the adequately powered GD-H1 three-session/3% cell has AP below
prevalence, and every GD-H2 endpoint is under the adverse-outcome floor or fails
discrimination/calibration.

## August coverage

The full-design thresholds were +7 bp for both DGS10 and DGS30 three-session
changes and 0.0000126566 for realized-variance acceleration. H1 fires on
2026-08-10 without an adverse outcome and on 2026-08-18 with a one-session
current-cohort median residual of −4.78% (≥3% yes, ≥5% no; three-session outcome
unmatured). H2 fires on 2026-08-03/04, not on the motivating 2026-08-18 session.
August selected none of those thresholds.

## Authority

**GD-1C grants no live market, Prophet, Portfolio, alert, ranking, sizing,
gating, or execution authority.**
