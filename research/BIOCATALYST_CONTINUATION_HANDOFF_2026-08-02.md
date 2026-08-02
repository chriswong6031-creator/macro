# BioCatalyst continuation handoff — 2026-08-02

Canonical continuation note. This is a clean-room public-source build; do not use or transmit competitor credentials.

## B1 foundation

- PR: https://github.com/chriswong6031-creator/macro/pull/4227
- Branch/worktree: `claude/biocatalyst-b1b-20260802` at `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/biocatalyst-b1b-20260802`
- Current head: `c801354fa21`
- Fresh CI run: https://github.com/chriswong6031-creator/macro/actions/runs/30732736923
- The preceding run failed only because current `main` emitted a numeric JSON field named `validated`; `c801354fa21` masks only that JSON key while still catching prose on the same line. Local selftest and the full claim scan pass.
- Production ingestion must remain dark. No dedicated BioCatalyst R2 credentials or source-rights approval are present; keep `macro-biocatalyst.timer` disabled.

Next: wait for every PR check, squash-merge #4227, verify `origin/main`, wait for `https://mastermind-x.com/api/health` to advance, run `/opt/macro/app/deploy/biocatalyst-setup.sh` on the VPS, restart `macro-api`, and verify anonymous BioCatalyst API requests return `401` rather than `404`. Confirm the timer is disabled/inactive and do not run ingestion.

## B2 exact registry history

- Branch/worktree: `codex/biocatalyst-b2-history-20260802` at `/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/biocatalyst-b2-history-20260802`
- Pushed commit: `4bd93482948` (`feat(biocatalyst): add evidence-bound trial history`)
- Validation: 534 B2/B1 tests passed; final shared-UI regression slice 35 passed; workflow YAML, template/site sync, Node syntax, `py_compile`, and `git diff --check` passed. Red-team found no remaining P0-P2 issue under the documented single-writer public-root trust model.
- Browser QA passed at 390/820/1440, dark/light, English/Chinese, including exact V1 to V2 before/after history. The Settings focus/pointer close defect was fixed and live-browser verified.
- History remains rights-gated and dark (`production_ingest_allowed: false`). It emits exact source facts only: no materiality, protocol interpretation, forecast, Prophet authority, or trade authority.

B2 is based on the pre-squash B1 commit `993ce827e30251dad2204615d0c9c4e1475b3fd8`. After B1 lands, preserve the pushed branch as backup and create a fresh final branch without force-pushing:

```bash
git fetch origin
git rebase --onto origin/main 993ce827e30251dad2204615d0c9c4e1475b3fd8 codex/biocatalyst-b2-history-20260802
git switch -c codex/biocatalyst-b2-history-final-20260802
```

Resolve moving-main conflicts by retaining both BioCatalyst and newer shared CI/deploy/theme changes. Rerun the B2 test shards and UI checks, push the new branch, open a PR, squash-merge, then repeat production health/API/UI verification. Keep ingestion dark.

## Next parity lane

The next honest lane is B4A: the complete official weekday Drugs@FDA ZIP transformed into an FDA-native application/product/submission/action graph. An empty preparation worktree exists at `.claude/worktrees/biocatalyst-b4a-regulatory-20260802` on `codex/biocatalyst-b4a-regulatory-20260802`; rebase it to the future `origin/main` before use. Do not add ticker/company/trial fuzzy joins, pending PDUFA claims, approval odds, or medical claims. The following waves are Orange Book patents/exclusivities, then labels/shortages/safety, then shared-identity corporate/SEC consumers for cash runway, dilution, licensing economics, and governed Prophet context.
