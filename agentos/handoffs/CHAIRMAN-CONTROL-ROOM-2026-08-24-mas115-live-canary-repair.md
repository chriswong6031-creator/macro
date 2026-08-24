---
workstream: WS:CHAIRMAN-CONTROL-ROOM
session: codex/mas115-live-canary-repair-20260824
model: sol
ended_because: blocked
mission: >
  Repair the failed disposable Multilogin canary, merge the bounded fix from
  protected Mastermind, run exactly one post-merge non-seat canary, and leave
  P0B recoverable without touching Chairman seats or widening into relay work.
state_before: >
  Three Chairman seats and one stopped disposable profile were provisioned.
  The first live canary on Mastermind 500fb139 started the exact disposable
  profile but rejected Multilogin's real six-process group as though launch
  required exactly one process. The harness had no unconditional teardown,
  so the exact disposable was manually stopped through a one-row filtered
  vendor UI action before repair work began.
changed:
  - path: mastermind PR #139
    what: >
      Replaced the truncating credential prompt with one fixed secret-owning
      Security.framework helper, split C1 into five explicit launch/navigation
      predicates, accepted one-or-more exact-profile processes from a strict
      zero baseline, retained one exact cleanup lease across ambiguous start
      response and C5 owner loss, and made cleanup failure veto v2 PASS.
  - path: agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md
    what: >
      Records both adverse live attempts, the accepted repair merge, the
      pre-launch HTTP 501 blocker and the no-blind-rerun continuation.
  - path: agentos/discoveries/DSC-CCR-SECURITY-CLI-PROMPT-TRUNCATES-LONG-MULTILOGIN-TOKEN.md
    what: >
      Preserves the verified long-secret enrollment landmine without recording
      a credential.
  - path: agentos/discoveries/DSC-CCR-MULTILOGIN-CLOUD-SEARCH-501-BLOCKS-NONSEAT-CANARY.md
    what: >
      Preserves the current external vendor blocker and its read-only falsifier.
verified:
  - claim: The first failed attempt was contained without touching a Chairman seat.
    command: >
      Compare sanitized pre/post process counts, map only the exact provisioned
      disposable identity in the vendor list, stop the single filtered row,
      and re-run local census counts.
    result: >
      Exact disposable process count returned to zero and Multilogin running
      count returned to the three-seat baseline; no private URL, browser
      content, credential, profile content, typing or message send was read.
  - claim: Mastermind PR #139 is accepted and merged from the exact reviewed head.
    command: >
      Inspect PR #139 base/head/files/check rollup; run 452 relevant local CCR
      tests; wait for hosted repository CI and all CodeQL lanes; record Sol
      exact-head review; squash merge.
    result: >
      Base 500fb139b93c0031f3397faa7d1a3c5ad298f95f; head
      b44e0c37f91ef3c77bd36c344ac5c05ad7e8318c; seven MAS-115 files; hosted
      CI ran all 296 discovered test modules with zero exclusions and passed;
      all CodeQL lanes passed; merge 933382619541bb9efa02a1b521168acfd99f5f0b;
      Sol acceptance comment 5394753115.
  - claim: The one exact-merge post-repair canary failed before any launch and cleaned safely.
    command: "python3 scripts/mas115_setup.py run-canary --vendor multilogin"
    result: >
      v2 verdict FAIL; C0 OK; C1 VENDOR_ERROR; C2/C3/C4/C8/C5 withheld;
      C6 VENDOR_ERROR; C7/C9/C10 expected-safe; cleanup OK/not-needed;
      exact disposable processes 0 before/after and other managed-profile
      processes 38 before/after.
  - claim: The current refusal is the authenticated cloud profile-search response, not DNS or local launcher reachability.
    command: >
      Run bounded read-only shape/status probes with the fixed Keychain pipe;
      emit only booleans, status codes, byte counts and schema absence.
    result: >
      Credential present; cloud DNS/direct transport reachable; launcher
      DNS/direct transport reachable; authenticated profile-search returned
      HTTP 501, 357 bytes, non-JSON. No response body, credential, identifier,
      name, URL, cookie, proxy, process argv or browser content was emitted.
unverified:
  - claim: The current official Multilogin profile-search contract can again return an accepted complete inventory census.
    what_would_verify: >
      Primary-source contract reconciliation plus one bounded read-only
      shape-only HTTP 200 JSON response and complete stable census.
  - claim: A disposable non-Chairman Multilogin profile passes C0-C10 plus v2 cleanup.
    what_would_verify: >
      After the read-only blocker is cleared, a separately explicit Chairman
      authorization and action-time credential confirmation release one fresh
      canary with every row and cleanup true.
  - claim: Open Sol can foreground the exact intended Chairman window.
    what_would_verify: >
      A current supported focus contract plus separately authorized non-seat
      and real-seat proof; exact URL navigation alone remains insufficient.
unresolved:
  - "Multilogin authenticated cloud profile-search returned HTTP 501/non-JSON at the post-merge canary boundary."
  - "No disposable P0B canary has passed."
  - "Programmatic intended-window foreground remains unsupported."
next_actions:
  - "Do not rerun the lifecycle canary from this receipt."
  - "Re-read the current official Multilogin profile-search contract and prove the bounded read-only accepted census first."
  - "After that proof, require a fresh explicit Chairman release and action-time native credential confirmation for one new disposable canary."
  - "Keep Chairman seats, ASD-A2/A3/A4, generic Wake and P1 held."
do_not_redo:
  - "Do not re-enroll the three Chairman seats or reprovision the existing stopped disposable profile."
  - "Do not use `security add-generic-password ... -w` for the long Multilogin token."
  - "Do not print, inspect or migrate credentials, private locators, profile content, response bodies, cookies, proxies, process argv or browser content."
  - "Do not adopt, restart, stop or otherwise mutate a Chairman seat."
  - "Do not merge stale Macro PR #6330; it predates the accepted A1, enrollment, PR #139 repair and both live receipts."
danger_areas:
  - "HTTP reachability is not an accepted vendor contract; the authenticated request can still return 501/non-JSON."
  - "A lifecycle retry before read-only census proof repeats an ambiguous external dependency and violates the one-carrier/no-blind-retry law."
  - "The short-lived Keychain credential may expire; presence is not current authorization or evidence of validity."
prs: [139]
decisions:
  - DEC:CCR-P0B-AUTOMATION-OWNED-NONSEAT-CANARY-ONLY
  - DEC:CCR-SOL-IDENTITY-IS-NOT-A-CHAT
discoveries:
  - DSC:CCR-SECURITY-CLI-PROMPT-TRUNCATES-LONG-MULTILOGIN-TOKEN
  - DSC:CCR-MULTILOGIN-CLOUD-SEARCH-501-BLOCKS-NONSEAT-CANARY
---

# Return point

Start from protected Mastermind merge `933382619541bb9efa02a1b521168acfd99f5f0b`,
current Macro main, Mastermind PR #139 and this handoff. The three Chairman seats
remain untouched and the disposable profile is stopped. Reconcile the current
official Multilogin cloud-search contract and prove the read-only accepted census;
do not perform another lifecycle attempt without a fresh explicit Chairman release.
