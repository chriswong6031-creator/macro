---
key: EXECUTIVE-DR-V1-ARCHITECTURE
question: >
  How does the Executive OS lifecycle database get failure-independent, verifiable,
  explicitly-restorable off-host recovery, given a production runtime that runs
  `python3.12 -I -S` (no site-packages), a control host whose privileged state fleet
  sessions cannot read, no reachable Cloudflare credential to mint a DR bucket, and a
  harness that (correctly) blocks session-side credential handling?
answer: >
  Reuse the existing verified backup primitive unchanged; add a stdlib+system-openssl
  encrypt-then-MAC export layer (AES-256-CTR via `openssl enc` in password mode — key
  material never on argv — plus independent stdlib HMAC-SHA256, MAC-before-decrypt) with
  a closed envelope `mastermind.executive_dr_export/v1`; ship create-only to GitHub
  release assets (drill lane: the Mastermind repo's own DRAFT releases via the ephemeral
  workflow GITHUB_TOKEN, pruned to newest 8; production lane: the dedicated private
  `executive-dr-vault` repo via a ceremony-provisioned fine-grained PAT); prove recovery
  continuously with a weekly hosted-runner clean-environment drill (fabricate real
  Runtime → backup → encrypt → ship → discard local → fetch → decrypt →
  verify_restore_drill → logical-state equality); deliver nightly cadence as a
  ships-disabled launchd daemon + installer wiring armed at the next host ceremony; and
  concentrate every credential act (standing key custody = Chairman password
  manager + 0400 host file, NEVER a GitHub secret co-located with the ciphertext; vault
  PAT; optional R2) into ONE documented Chairman ceremony. No hot standby, no automatic
  failover, no second runtime; restore is explicit, offline, and never overwrites the
  live DB.
rationale: >
  (1) The production interpreter's `-I -S` isolation makes pip crypto structurally
  unreachable, so "add cryptography" was never a real option — the reviewed unit is the
  composition over primitives that already exist on every target host. (2) The estate has
  no reachable Cloudflare API credential and the harness blocks session-side token
  handling, so the only transport armable WITHOUT a human ceremony is GitHub — and the
  drill lane gets genuine least-privilege for free via the workflow's ephemeral
  repo-scoped GITHUB_TOKEN. (3) Executive OS is production-inert (LaunchDaemons
  state=missing pending H0/P0), so shipping DR as source + release material + a
  CI-provable drill makes the next arming ceremony carry DR from day one instead of
  bolting it on after. (4) Adversarial review (opus) was load-bearing, not ceremonial:
  it caught a CONFIRMED cross-implementation break — LibreSSL writes the `Salted__`
  header under `-S`, OpenSSL 3.x omits it — that both the 31-test suite and the CI drill
  were structurally blind to (same binary on both sides); fixed by normalizing stored
  ciphertext to headerless with per-process feature detection, pinned by a
  both-directions cross-binary test.
alternatives:
  - option: "Litestream continuous WAL replication first"
    why_not: "Packet-gated behind DR-L0 falsifier; adds a runtime co-process + its own recovery semantics before the simpler verified-artifact vertical exists; its restore/reset MCP is a model-facing hazard."
  - option: "Promote `cryptography` to base deps for AEAD"
    why_not: "Production runs -I -S with no site-packages; the dependency could never reach the runtime that matters."
  - option: "R2/S3 immutable bucket as the first transport"
    why_not: "No reachable Cloudflare credential; minting a scoped token is a human ceremony. R2 (T-R2) remains the preferred production target, armable at the same ceremony — code seams and runbook section ship now."
  - option: "Store the standing master key as a GitHub Actions secret for CI cold-restore"
    why_not: "Review M6: key and ciphertext at the same provider collapse the trust separation client-side encryption exists to create. Consequence accepted: CI cold-restore of production exports is impossible by design; cold-restore is a ceremony activity."
  - option: "Copy the fleet admin token into an Actions secret so the drill can write a separate vault repo"
    why_not: "Blocked by the harness classifier and rightly so; draft releases on the source repo with the ephemeral GITHUB_TOKEN achieve the same proof with strictly less credential exposure."
evidence:
  - "Mastermind PR #358 squash-merged as 9ed1a2020246348118a0c83e4207284c5bd51d60 (required `test` check green on the updated head)"
  - "First live drill: run 33594694384 conclusion=success; receipt: ok=true, offline=false, logical_state_equal=true, fetch_to_verified_ms=1438, export a3c390bd15ec46668edd9a9d2e9e37f1; vault state after: exactly one Draft release, zero git tags"
  - "Cross-implementation pin: tests/test_executive_dr.py -k cross_implementation passed both directions against /opt/homebrew/opt/openssl@3/bin/openssl on the control host"
  - "Adversarial review packet: 3 BLOCKERS (LibreSSL/OpenSSL Salted__ divergence; workflow missing GITHUB_TOKEN mapping; unexecutable nightly token provisioning) + 10 MAJORS, all fixed in Mastermind commit 2774420b"
  - "Frozen architecture: Mastermind research/MASTERMIND_EXECUTIVE_DR_V1_ARCHITECTURE_2026-09-01.md; runbook ops/executive_os/DR_RUNBOOK.md"
affects:
  - "WS:EXECUTIVE-OS-DISASTER-RECOVERY"
  - executive-os
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-09-02
---

Chairman authorization chain: direct-delivery of the operation packet into the live Fable
COO session 2026-09-01, plus the same-day Chairman override "keep going … take on COO
leadership and continue until full completion" — recorded here because the packet's
native routing was a ChatGPT Pro Sol session and this decision would otherwise read as a
seat overreach. Remaining ceremony-gated items (standing key custody, vault PAT, optional
R2 enrollment, nightly daemon arming, full-ceremony RTO measurement) are enumerated in
`ops/executive_os/DR_RUNBOOK.md` §ceremony and in the workstream's next_action.
