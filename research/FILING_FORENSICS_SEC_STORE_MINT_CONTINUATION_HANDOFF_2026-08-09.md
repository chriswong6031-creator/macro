# Filing Forensics SEC store mint ruling — continuation handoff (2026-08-09)

**Status: implementation COMPLETE and pushed; waiting on CI, then squash-merge + live
verification.** Nothing is half-built. A fresh session's job is to land PR #5044 and
verify the lane's first real nightly run, not to write code.

Ruling implemented: `research/FILING_FORENSICS_SEC_STORE_MINT_ADJUDICATION_2026-08-08.md`
(§5 = R1–R6, §6 = compat walls, §7 = phased plan, §8 = what it does NOT license).
Registry key `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`.

---

## 0. State at a glance

| | |
|---|---|
| PR | **#5044** `fix(forensics): dedupe the SEC store to one manifest per (accession, content)` |
| Branch | `claude/sharp-benz-061439`, worktree `.claude/worktrees/sharp-benz-061439` |
| Head | `585e1211d00` (pushed; local tree clean) |
| Base at last rebase | `48d13f4347e`; main has since moved (was `02427e97b99` at handoff) |
| Labels | `merge-on-green` armed |
| CI | fresh run pending on `585e1211d00` at handoff time |
| Suite | **1859 passed** across all 51 forensics-referencing test files, `TZ=UTC` |

**Dependency worth knowing: PR #5019 is still OPEN.** That is the adjudication document
itself plus the `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` registry row. This PR implements a
ruling whose doc has not landed. The two are independent — #5044 does not import the doc —
but if you cite the doc by repo path before #5019 merges, the path does not exist on main.

---

## 1. What shipped (all four phases)

- **R1 content key** — `manifest_content_key()` in `engine/fundamental_forensics/sec_document_spine.py`.
  Canonical-JSON digest excluding `manifest_id`, `clocks.recorded_at`, and each document's
  `retrieval.retrieved_at`/`receipt_id`. Keeps `content_sha256`/`byte_length`/`storage_key`
  (byte identity). Derived OUTSIDE the persisted body — no schema field was added, so the
  first post-migration run re-mints nothing.
- **R2 first retention** — reuse returns the stored manifest verbatim, carrying its original
  `recorded_at` forward. Never rewritten.
- **R3 observation log** — schema `fundamental_forensics.sec_observation_log/v1`, one
  immutable object per run under `observation_root`, outside the restorable trees. Rows bind
  ticker/cik/accession/form/manifest_id/content_key/observed_at/outcome, outcome ∈
  `{unchanged, new_content, new_filing, missing}`. Per-ticker receipt writes retired (R6),
  folded into the object's `ticker_receipts`.
- **R4 forward-only** — nothing deleted or rewritten; existing `runs/acquisition/**` keeps restoring.
- **R5 identity untouched** — `_manifest_id`, `manifest_id_for`, `validate_manifest_identity`,
  `manifest_storage_key` are byte-identical to main. Both spine files are pure additions.
- **Phase 4** — `coverage.cached_primary_manifest_versions` counts distinct content keys, so
  it is honest over the historical duplicates R4 forbids deleting. Meaning stated at the
  definition site.

---

## 2. THE TRAP — read this before touching the acquisition loop

**#5022 (`--reuse-local-archive`) and this ruling edit the same loop, and `git` merges them
cleanly while producing broken semantics.** This already happened once, during the rebase,
and was caught only by reading the merged loop line by line.

The lane arms `--reuse-local-archive` in `.github/workflows/filing-forensics-sec.yml`, so the
reuse branch — not the fetch branch — is the path production runs. The clean merge produced:

1. reuse branch calling `persist_filing_manifest` instead of `retain_filing_manifest`, so it
   minted a manifest per run and **R1 was defeated on the only leg the lane uses**; and
2. reuse branch emitting **no observation row at all**, so **R3's log was empty** there.

**Every existing test stayed green through both defects, because they all exercise the fetch
leg.** A green suite does not prove this code path. `test_warm_archive_reuse_still_dedupes_and_still_observes`
in `tests/test_fundamental_forensics_acquisition.py` now pins the reuse leg specifically —
do not delete or weaken it, and if you touch that loop, re-read both branches.

**§8 honesty field.** Under reuse the primary is proved from retained bytes, not a fresh SEC
response, so an `unchanged` row would assert a check that did not happen. Rows carry
`primary_verification` ∈ `{network_refetch, local_reuse}` (`null` when the run never reached
the primary). Submissions are ALWAYS fetched fresh in both flag states, so the filing-level
re-derivation is genuine either way; the field only stops the log overclaiming at byte level.
If you ever make `unchanged` imply a re-download again, §8 is violated.

---

## 3. What remains

1. **Watch CI on `585e1211d00` to conclusion.** ~30–40 min per pack, but the self-hosted pool
   has been congested (one run took ~1.5h with packs queued 80+ min). Do not `gh run watch` at
   default interval — house law, quota is one shared bucket.
2. **Triage any red as base-side vs mine** using §4 below.
3. **Squash-merge** on concluded green — or leave it to the `merge-on-green` sweeper, which is
   armed. Do not `--admin` past a genuine red.
4. **Live verification after merge:** the lane runs at 02:30 UTC. Confirm the first real
   nightly run shows the store no longer growing — `bytes_retained` should already be
   ~submissions-only from #5022; what THIS change adds is that the manifest tree stops
   growing. Check the run's observation object exists at
   `$HOME/.cache/mm-ffsec/observations/runs/acquisition/<run_id>.json` on the runner, and that
   `.github/workflows/filing-forensics-sec.yml:119-173`'s restore self-check still passes.

---

## 4. Base-side red triage (this cost real time; do not redo it blind)

Main was red repeatedly during this work. Method that worked:

- **A docs-only sibling PR is a free control** — #5019 touches 4 doc/config files, so any pack
  it fails is base-side. Cite it and move on.
- **But the probe is ASYMMETRIC.** A pack the sibling *passed* while you failed proves nothing
  either way: pack composition rebalances (`ci-pack-N` is not a stable job id), and a run that
  straddles UTC midnight can flip a time-dependent fixture. That exact case happened here —
  `test_earnings_seasons.py` passed at 22:17Z and failed at 01:03Z on `assert 'stale' == 'ready'`.
- **For those, run the real control:** `git worktree add --detach <tmp> origin/main`, run the
  one test there under `TZ=UTC`. If it fails on clean main with none of your diff present,
  that settles it. Grepping the test for your modules is corroboration, never the control.
- Reds seen and healed upstream during this work: #5032 (four base-side reds), #5065
  (earnings fixture date bomb, superseded #5064). Do not open competing heals — check
  `gh pr list --search "<test file>"` first.

---

## 5. Verification commands

```bash
cd "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/sharp-benz-061439"
TZ=UTC python -m pytest tests/test_sec_document_spine.py tests/test_fundamental_forensics_acquisition.py tests/test_fundamental_forensics_disclosure_bundle.py tests/test_filing_forensics_sec_lane.py tests/test_fundamental_forensics_filing_package_materializer.py tests/test_fundamental_forensics_disclosure_projection.py tests/test_fundamental_forensics_wave2_operator.py -q
```

R5-protected tests that must stay green (the whole point of R5):
`tests/test_sec_document_spine.py` — three-clocks-present, deterministic round-trip at a fixed
`RECORDED_AT`, storage-key-binds-identity.

**Live two-run probe** (this is the acceptance evidence; a green fixture suite does NOT
substitute). Script kept at the session scratchpad `probe2.sh`; it runs the real
`scripts.run_fundamental_forensics_wave2` twice against AAPL with different clocks, run 2 with
`--reuse-local-archive` as the lane does. Expected on this branch:

```
run1 (cold, network) : manifests=8 observations=1 digest=364d247bf228…
run2 (warm, --reuse) : manifests=8 observations=2 digest=364d247bf228…
NO NEW OBJECTS · BYTE-IDENTICAL · gained exactly 1 · all rows unchanged/local_reuse
```

Baseline on unmodified main for the same probe: **8 → 16 manifests, digest CHANGED**. Re-derive
that baseline in a detached `origin/main` worktree if you need to prove the probe is not vacuous.

---

## 6. Deferred — NOT licensed by this ruling

- **Archive receipt sidecars still mint nightly** (~48/night, orphaned but harmless). Same
  category error as R1 in a different artifact. Deliberately left out: fixing it here would
  have been scope the ruling did not grant. Needs its own adjudication.
- **Observation log is not R2-replicated.** Durability is runner cache retention. A third
  synced tree is impossible without breaking every published snapshot — `SOURCE_KINDS =
  ("raw", "archive")` is hard-validated at `engine/fundamental_forensics/source_sync.py:463`
  and `:513`, and existing snapshot manifests would fail validation. An off-host copy needs
  its own prefix and publisher.
- **Historical duplicate reclamation** — R4 forbids it here; needs `ffsecsrc_` pin proof
  (§6 Wall 1: `filing_package.py:1145-1176` pins manifests by exact storage key, and AAPL is
  both a Wave-2 target and the attested-history seed subject).
- **Submissions retention horizon** — now the dominant remaining growth (~12/day). Ruling §9.
- **Sibling store** `engine/capital_structure/source_identity.py` has its own `manifest_id_for`
  and was never audited for the same category error. Ruling §9.
- Detector semantics — the three standing `DNR:HOLD-FF-*` rows are untouched and must stay so.
