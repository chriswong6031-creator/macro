---
workstream: WS:CHINA-ALPHA-INTELLIGENCE
session: claude/china-alpha-freeze-activation (records vehicle claude/pr0d-authority-records)
model: fable
ended_because: complete
mission: >
  FABLE-00 China Alpha activation close-out under two same-day Sol directives
  (operator-relayed 2026-08-20). First: the P1 acceptance review — hold #6050
  mechanically (four-part protocol), repair the vertical slice on the same
  vehicle (dossier template consumer for the visit tape), re-arm on evidence,
  merge, keep P1 BUILT_NOT_PROVEN. Second: the PR-0D authority adjudication —
  OWNER-ROUTE, DO NOT REBUILD: correct the mistaken WS:STOCK-IDENTITY /
  engine/stock_identity/ seam pointer to canonical Data OS identity authority,
  commission exactly one bounded child D2B2-CN-HK under
  WS:PROPHET-US-V4-RECOVERY, encode China pr0d as OWNER_ROUTED_WAIT /
  consumer-verifier, prefer immutable merge SHAs in durable receipts, and
  dispatch a bounded proof-only session for PR-0B/P1. No later verticals
  (P1B/L0/R1/R2) started.
state_before: >
  #6050 (P1 visit tape) merged 2026-08-20T10:54:34Z as squash c54d1b55f673
  after the Sol-directed hold/repair cycle; PR-0B #6045 merged as squash
  fdbf543b2333 (BUILT_NOT_PROVEN); RIGHTS-0 done. The PR-0D China-lane builder
  had STOPPED at the D2B2 owner collision (its commission pointed at
  WS:STOCK-IDENTITY / engine/stock_identity/ while canonical identity
  expansion is the V4 D2 program on lib/dataos, with D2B2 explicitly
  Sol-gated); the collision packet had been returned to Sol. WS receipts
  cited a mutable branch-head SHA for #6045.
changed:
  - path: research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md
    what: >
      NEW frozen contract + spawn commission for the one bounded child Sol
      authorized: admit the source-supported China/HK listing population into
      the canonical Data OS master via scripts/build_security_master.py +
      lib/dataos/identity.py (or typed refusals for every target), re-derive
      the GMI identity projection; eleven frozen boundaries (start-pin
      re-census by market — 1,868 is observation not contract; CN/HK only,
      US/Canada unauthorized; canonical builder only; D2B1 issuer law;
      primary sources only; A/H law; current-identity semantics; complete
      accounting; sidecar re-derived; zero Earnings/event work; zero
      score/rank/Prophet change) + Sol's acceptance-test list verbatim.
  - path: agentos/decisions/DEC-CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK.md
    what: >
      NEW decision record of the Sol adjudication — owner-route rationale,
      rejected alternatives (China-lane build on either seam; full-backlog
      authorization), affects, evidence chain (d2 Gate-1 amendment, collision
      packet, D2A/D2B1/D2B1-R1 contracts).
  - path: research/china_alpha_intelligence/commissions/PR-0D_china_identity_extension.md
    what: >
      authority-seam correction — owner-route banner (do NOT spawn a
      China-lane builder from this file) + the four mistaken seam-pointer
      sites (coordination gate, SCOPE spine, FROZEN SPEC, OWNED FILES)
      replaced with the canonical Data OS seam and the D2B2-CN-HK route; text
      preserved as the China-lane requirement record.
  - path: research/CHINA_ALPHA_INTELLIGENCE_MASTERPLAN.md
    what: >
      §0-bis Execution rulings, §13 PR-0D block, and §16 prose corrected to
      the owner route (authority-seam correction, not an architecture
      rewrite); §0-ter.6 boundary unchanged.
  - path: agentos/workstreams/WS-CHINA-ALPHA-INTELLIGENCE.md
    what: >
      pr0d wave encoded OWNER_ROUTED_WAIT / consumer-verifier with the
      adopt-by-reference + natural-nightly done-gate; pr0b/#6045 and
      p1/#6050 receipts re-pointed at immutable squash SHAs (fdbf543b2333 /
      c54d1b55f673); pr0b flipped to DONE on the accrued asia-close receipt
      (run 32348780228 -> commit baf4cf7c9291) with the
      asia-close-writes-China-planes lane correction recorded in the
      completion-law landmine; p1 partial receipt (page half proven live,
      data half pending) recorded; top-level next_action rewritten to the closed-activation
      state (proof-only verification + owner-child adoption; no new
      verticals without a Sol directive); depends_on += WS:PROPHET-US-V4-RECOVERY;
      decisions += DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK.
  - path: agentos/workstreams/WS-PROPHET-US-V4-RECOVERY.md
    what: >
      d2 wave note amended — D2B2-CN-HK AUTHORIZED 2026-08-20 with contract
      pointer and consumer-verifier note; full D2B2 US/Canada backlog and
      D2B3/D2C/D2D/D2E remain NOT authorized.
verified:
  - claim: "#6045 squash merge SHA is fdbf543b2333ec6077988ffd571966f180008cc5, #6050 is c54d1b55f673cb383c00889e8f4ab809614666ba"
    command: "gh pr view 6045/6050 --json mergeCommit"
  - claim: "AgentOS schema passes with the new DEC + WS edits"
    command: "python3 scripts/agentos.py validate (run pre-push in this PR)"
  - claim: "PR-0B receipt accrued: asia-close run 32348780228 (post-merge checkout, asia job success) produced commit baf4cf7c9291 whose data/china_prophet_rank/candidates.parquet carries all intel_* columns — 1,636-1,640 non-null covered rows, 4 typed intel_unavailable_reason refusals"
    command: "gh run view 32348780228 --json jobs; git merge-base --is-ancestor fdbf543b2333... <run head>; git show baf4cf7c9291:data/china_prophet_rank/candidates.parquet + pyarrow (proof-only inspection 2026-08-20)"
  - claim: "China planes are written by asia-close.yml only — daily.yml resets data/china* in its collect step (lane correction recorded in WS landmine + masterplan §0-bis)"
    command: "grep -n 'git reset -q -- data/' .github/workflows/daily.yml; grep -rn build_china_intel .github/workflows/*.yml"
  - claim: "production china_intel page serves the #6050 K2c visits block with honest not-yet-covered states"
    command: "curl -s https://www.mastermind-x.com/china_intel.html | grep -n 'Institutional visits'; diff <(git show baf4cf7c9291:site/china_intel.html) <(git show 8e73239563ef:site/china_intel.html) — asset-stamp-only diff"
do_not_redo:
  - "Do not spawn a China-lane identity builder from PR-0D_china_identity_extension.md — the file's banner and DEC:CHINA-IDENTITY-OWNER-ROUTE-D2B2-CN-HK route implementation to the D2B2-CN-HK child; the 2026-08-20 builder's STOP at the collision was correct behavior, not a failure to finish."
  - "Do not authorize or start the D2B2 US/Canada backlog, D2B3, D2C, D2D, or D2E from this ruling — Sol bounded the authorization to the China/HK slice only."
  - "Do not manufacture a nightly/asia-close run to green PR-0B or P1 — the proof standard is the first qualifying NATURAL post-merge run; RECEIPT_NOT_YET_ACCRUED leaves them BUILT_NOT_PROVEN."
  - "Do not start P1B, L0, R1, R2, or later China Alpha verticals without a new Sol directive."
danger_areas:
  - "The D2B2-CN-HK builder writes data/reference/ through the canonical builder — sparse-worktree law applies (opt into the full tree; never git add an unexpected data/ diff)."
  - "New pytest suites must be wired into .github/ci/legacy-jobs.yml owner lanes in the same PR or contract-delta reds the vehicle (this exact latch bit #6050)."
unverified:
  - claim: "P1's zero collected visit rows (n_candidates=0 in commit a14ac56627c9) reflects a genuinely quiet filing day rather than a latent category-classification defect in collectors/china_filings.py"
    what_would_verify: "the first asia-close run on a day with a real 投资者关系活动记录表 filing persisting >=1 row; or a targeted read of the institutional_visit category taxonomy against that day's raw filings"
unresolved:
  - "P1 data-half receipt: the wave stays BUILT_NOT_PROVEN until the first qualifying natural asia-close run persists >=1 real institutional_visit row AND the production dossier desktop/mobile crops with honest failure states are captured (page half already proven live 2026-08-20 — render commit baf4cf7c9291 serving on https://www.mastermind-x.com/china_intel.html)."
  - "D2B2-CN-HK execution: contract frozen and authorized, child not yet merged; China pr0d waits to adopt its immutable merge SHA by reference."
next_actions:
  - "D2B2-CN-HK child executes research/prophet_v4/d2/D2B2_CN_HK_FROZEN_CONTRACT_2026-08-20.md under WS:PROPHET-US-V4-RECOVERY (spawn commission = the contract's SECTION block; merge = BUILT_NOT_PROVEN; Sol reviews the return)."
  - "P1 data-half proof: re-inspect after the next natural asia-close run (early-bird cron 06:00Z, backstops through 11:15Z) — RECEIPT_ACCRUED needs >=1 real institutional_visit row in data/china_visits/ plus the production crops; never manufacture a run. PR-0B needs nothing further (receipt accrued, wave done)."
  - "When D2B2-CN-HK merges, record its immutable merge SHA on China wave pr0d (BUILT_NOT_PROVEN, adopt-by-reference); pr0d done only on the natural-nightly source -> master -> GMI proof with measured CN/HK resolution delta."
---

# China Alpha activation close-out — 2026-08-20

Cold-stranger summary: the activation's four waves ended the day as
pr0b DONE (#6045, squash fdbf543b2333; receipt = asia-close run 32348780228
→ commit baf4cf7c9291, intel_* columns live with typed refusals), rights0
done, p1 BUILT_NOT_PROVEN (#6050, squash c54d1b55f673, repaired dossier
consumer merged after the Sol hold/repair cycle; page half proven live,
zero real visit rows yet), and pr0d OWNER_ROUTED_WAIT — Sol's adjudication
routed China/HK identity implementation to the bounded child D2B2-CN-HK
under the V4 D2 / Data OS owner rather than a China-lane build. The frozen
contract, decision record, seam corrections, receipt hygiene (immutable
merge SHAs), and the asia-close-writes-China-planes lane correction all
landed in the records PR carrying this handoff. Remaining production proof
(p1 data half, pr0d owner chain) accrues on natural runs only.
