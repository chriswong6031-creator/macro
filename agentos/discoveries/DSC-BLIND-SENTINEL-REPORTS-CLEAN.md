---
key: BLIND-SENTINEL-REPORTS-CLEAN
claim: >
  A sensing function that returns the SAME empty result for "read failed" and "nothing is
  wrong" makes blindness indistinguishable from health, and every downstream consumer then
  reports green. In scripts/metabolism_immune.py, `_resolve_repo()` fell back to the literal
  string "owner/repo" whenever `gh repo view` failed, so every check-run read hit
  `/repos/owner/repo/commits/<sha>/check-runs` and 404'd; `_get_required_red_checks` had no
  way to say "the read failed" separately from "there are no reds", so it returned `[]`
  either way and the lane logged `red_required=0` on every run. `main()` then returned 0
  unconditionally regardless of what happened inside. This ran every 2 hours for ~9 days
  (from 2026-08-17T07:17Z) while ci-main-heartbeat.yml failed every 6 hours on
  `contract-drift` and `tier-gate`, and ~14 PRs sat blocked until a human found the reds by
  hand. The proximate trigger was a dead METABOLISM_MERGE_PAT (owner `chriswong6031-creator`,
  pre-transfer, rejected by the enterprise 366-day PAT-lifetime policy) — but the sharp part
  is that because the secret EXISTS, `secrets.METABOLISM_MERGE_PAT || secrets.GITHUB_TOKEN`
  never fell through to the live token: `||` only tests presence, never validity, so an
  existing-but-dead secret is worse than a missing one. The bug was also independently fatal
  even with a live token: `_get_main_sha()` read live origin/main HEAD, but
  ci-main-heartbeat.yml's own check-runs live on the SHA the heartbeat itself ran on, and
  main advances roughly 17 commits/hour against the heartbeat's 6-hourly cron, so sensing
  HEAD alone structurally reads a commit that never carried the heartbeat's check-runs.
falsifier: >
  Point scripts/metabolism_immune.py at a repo where `gh repo view` fails (or the resolved
  owner/repo path 404s) and check whether the run distinguishes that from a genuinely clean
  main. Pre-repair (origin/main before this PR): both paths converge on
  `_get_required_red_checks -> []` and `main() -> 0` — indistinguishable from the outside.
  Post-repair: `_resolve_repo()` returns `None` (never the literal "owner/repo" — pinned by
  name in tests/test_metabolism_immune.py::test_resolve_repo_never_returns_owner_repo_literal),
  `_get_required_red_checks` returns `None` (not `[]`) on a failed read while still returning
  `[]` on a genuinely successful empty read, and `main()` exits 2 instead of 0. Also
  falsifiable by re-reading `.github/workflows/metabolism-immune.yml`'s old
  `GH_TOKEN: ${{ secrets.METABOLISM_MERGE_PAT || secrets.GITHUB_TOKEN }}` line and confirming
  the PAT secret is present-but-expired in the repo's secret store — the `||` never
  engages the fallback for a present-but-invalid value, only for an absent one.
so_what: >
  When a monitoring/sensing lane reports "healthy" or "clean", verify it performed an
  AFFIRMATIVE SUCCESSFUL READ before trusting the emptiness — a green sentinel is evidence
  only if its empty/clean result is reachable through a code path that is structurally
  distinct from its failure result (None vs [], not the same value from two different
  causes). Never let `||` between two credentials stand in as the liveness test for a
  secret — test the credential's actual validity (a successful authenticated call), because
  a present-but-dead secret defeats an absence-only fallback silently and permanently. And
  when a periodic sensor's target itself runs on a slower cadence than the process moving
  underneath it, sensing the live head alone is not enough: union-sense across the live head
  AND the target's own last-observed SHA (scripts/metabolism_immune.py's
  `_sense_required_red_checks`), or the sensor structurally reads a commit that never
  carried the signal it exists to see. This generalizes past this one lane: any repo-wide
  "is main red" instrument that reads a single point-in-time ref is vulnerable to the same
  cadence-mismatch blindness against any slower-cadence workflow it means to observe.
kind: landmine
verified_at: 2026-08-18
verified_by: >
  Run 32128421266 log line `gh api /repos/owner/repo/commits/a49e448d…/check-runs failed:
  gh: Not Found (HTTP 404)` immediately followed by `IMMUNE: main_sha=a49e448d
  red_required=0` (the smoking-gun pair proving the collapse). Repair citations in this PR:
  (A) `_resolve_repo()` scripts/metabolism_immune.py:407-460 (env var / gh repo view / git
  remote resolution order, never memoizes None, never returns the literal "owner/repo");
  (B) `_get_required_red_checks()` scripts/metabolism_immune.py:285-364 returns
  `None`/`list[dict]` distinctly; single call site scripts/metabolism_immune.py:1070 inside
  `_sense_required_red_checks`; (C) `_get_heartbeat_head_sha()`
  scripts/metabolism_immune.py:181-212 + `_sense_required_red_checks()`
  scripts/metabolism_immune.py:215-283 (two-SHA union, de-duped by name, no --paginate on the
  workflow-runs query); (D) `main()` scripts/metabolism_immune.py:1215-1259, exit 2 on
  `sensing_failed` at line 1255, exit 0 otherwise (including when reds are found — a
  successful sensing run); (E) `.github/workflows/metabolism-immune.yml`: `checks: read` +
  `actions: read` added at lines 34-35, checkout `token:` and the run-immune-lane step's
  `GH_TOKEN` both switched to `secrets.GITHUB_TOKEN` alone, `METABOLISM_MERGE_PAT` passed
  through as its own env var at line 76 and consumed only by
  `_heal_pr_create_env()` (scripts/metabolism_immune.py:525-541), scoped to the single
  `gh pr create` call at scripts/metabolism_immune.py:716. New regression tests added in
  tests/test_metabolism_immune.py (9 of the added tests fail against origin/main's
  pre-repair implementation and pass against this PR's; full before/after counts in the PR
  description).
scope: [macro]
confidence: verified
---

## Detail

Framing credit: the phrase "a guard whose green is indistinguishable from its blindness" for
this class of bug was coined on the peer session that produced PR #5885 (see
`agentos/handoffs/` around that PR for the append-only-evidence trap it names — a different
instance of the same underlying shape: a mechanism whose success path and failure path
converge on output a caller cannot tell apart).

### Why the `||` fallback is the sharper lesson than "the PAT expired"

PATs expire; that alone is routine and was always going to happen eventually. The design
flaw is that `secrets.METABOLISM_MERGE_PAT || secrets.GITHUB_TOKEN` is a **presence** test,
not a **validity** test. A secret that is deleted or unset correctly falls through to
`GITHUB_TOKEN` and the lane degrades gracefully (loses the "draft PRs trigger CI" property,
keeps sensing). A secret that still exists but is dead (expired, revoked, wrong scope) never
falls through — GitHub Actions has no way to express "use A, but only if A actually
authenticates" inside `||`. Any workflow using this pattern to chain a preferred credential
over a fallback should be read as: this degrades safely on ABSENCE, and NOT AT ALL on
INVALIDITY. The two credentials in this repo's remaining uses of the same `||` shape
(`metabolism-build.yml` and others carrying `METABOLISM_MERGE_PAT || GITHUB_TOKEN`) carry
the identical latent risk — none of that is touched by this PR (out of scope: rotating or
validating the PAT is the operator's action, not this repair's), but the pattern itself is
now a named landmine other sessions should recognize on sight rather than re-diagnose from
symptoms.

### Why "empty vs empty" is the general shape, not a metabolism-immune quirk

The two-value collapse here (successful-empty vs failed-empty both rendering as `[]`) is
structurally the same shape as a null hypothesis test that can't tell "no signal" from "no
data" — the fix in both cases is to make the failure mode a DIFFERENT VALUE than the null
result, never the same value reached by two different roads. `_get_required_red_checks`'s
new contract (`None` = SENSING FAILED, `[]` = read succeeded and main is clean) is the
concrete instance; the general form is worth checking anywhere a "detector" or "monitor"
function currently has a single empty/falsy return covering both its honest-negative and its
i-couldn't-tell paths.
