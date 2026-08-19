# Research Vault — Bug Fix Wave 4 (Publication Integrity) · continuation handoff

**Date:** 2026-08-19 · **PR:** [#5986](https://github.com/mastermindx-market-intelligence/macro/pull/5986)
**Branch:** `claude/research-vault-publication-integrity`
**Program home:** `research/RESEARCH_VAULT_MASTERPLAN.md`
**Mission:** make the Research Vault incapable of presenting or recording a
successful publication when its catalog, PDF objects, search corpus, or hourly
publication plane actually failed.

---

## §0 State at handoff

| Item | State |
|---|---|
| Code fixes (Defects 1–7) | **Merged** — see §2 |
| Unit/integration tests | 444 passing (research vault + neighbours) |
| Browser verification | Done, all four client states — §5 |
| **Production correction audit** | **NOT RUN** — needs R2 creds, see §6 |
| **Live hourly-run acceptance** | **NOT RUN** — see §6 |

The next session's whole job is §6. Nothing in the merged code depends on its
outcome; §6 measures the *existing* store, which the code changes never touched.

---

## §1 The architectural line this wave drew

The vault's fail-soft mechanisms are deliberate and were kept. The defect was
that **item availability and publication authority had blurred together**, so a
failed publication-plane operation produced normal-looking successful output.

> **Fail soft on documents. Fail closed on publication authority.**

Concretely:
- one bad PDF → that report fails, the batch continues, lane stays green;
- a failed corpus/catalog publish → nothing advances, lane goes **red**.

## §2 What changed (commit-by-commit)

| Commit | Defects | Change |
|---|---|---|
| `9fbad3c` | 1, 3, visibility | Serving tier reads freshness from `generated_at`; strict catalog read; universal catalog-membership filter on search; browser source selection |
| `078d2b9` | 2 (P0), 4, 5, 6 | Destructive-bootstrap refusal; `CatalogPublishResult`; PDF-promotion gate; publication ordering; CLI/workflow exit semantics |
| `fb21e24` | 7 | `peek → fetch → debit` download ordering |
| `325d3a5` | — | Fixes found by browser verification (see §5) |
| `72cd98f` | — | Read-only id-set census tooling |

### Frozen semantics (do not drift)

- **Freshness clock = `catalog.generated_at`**, never the newest item's
  `published_at`. The hourly ingest rewrites the catalog every run even when it
  admits nothing, so `generated_at` is the only clock that ticks hourly whether
  or not the vault changed. Keying on `published_at` reds a correctly-running
  vault during any quiet week.
- **Thresholds:** `fresh ⟺ age ≤ 2h` (boundary inclusive); future-clock
  tolerance 5 min. Mirrored in `site/research_vault_app.js`
  (`FRESH_MAX_AGE_MS` / `FUTURE_TOLERANCE_MS`) — **keep the two in step.**
- **Publication order:** `corpus → catalog → receipts → repo mirror`, each
  gating the next. The catalog is the visibility commit.
- **A legitimately empty vault is FRESH.** Valid schema + recent clock +
  `items: []`. Do not "fix" this into an error; the whole point of Defect 3 is
  that corruption looked like emptiness, and the symmetric mistake is making
  emptiness look like corruption.

## §3 Two judgment calls a future session may want to revisit

**1. Ingest validates differently from serving.** `catalog.validate()` takes
`check_future_clock` and `check_items`, both `False` on the ingest path. Both are
*serving* rules: the serving tier must answer "which ids are admitted" and cannot
trust an unreadable clock. Ingest makes no freshness claim and rewrites
`generated_at` on the next publish. Enforcing either during ingest converts
ordinary runner clock skew, or a single malformed row, into a refused publish
over a mature vault — an outage worse than the drift, and one that self-heals.

**2. RECEIPTS are the destructive-bootstrap trigger, not "any prior state".**
The first implementation gated on receipts **or** vault PDFs **or** corpus, and
it **wedged a brand-new vault permanently** the first time a publish failed
(empty catalog published → next run sees "history" → refuses forever). The
correct rule is mechanical:

> A rebuild from zero is safe exactly when every document will be re-admitted.
> The pass admits "inbox PDFs without a receipt". Therefore a *receipted*
> document is the one thing a rebuild provably drops.

Promoted PDFs and corpus rows without receipts re-ingest normally, so they are
**counted as operator context and warned about, not gated on**. Both inputs that
reach zero rows are covered: an unavailable catalog **and** one that parses
cleanly with an empty item list.

## §4 Traps discovered while building (cost real time)

1. **A `--local` CLI run writes the LIVE repo mirror.** Writing this wave's own
   tests truncated `data/research_vault/catalog.json` from 1,402 rows to 1,
   because a subprocess `--local` run snapshotted its two-document scratch vault
   over the real file. Fixed by `--repo-dir` / `RESEARCH_REPO_SNAPSHOT_DIR`; a
   store override now travels with a snapshot override — on **both** the ingest
   CLI and the census. **Never point either at a scratch store without also
   passing `--repo-dir`**: for the census the symptom is quieter but just as
   wrong, a nonsense mirror lag that can raise a false freeze-§B alarm.
2. **`ci-authority/codex/merge-queue-pilot` is FAILURE on every open PR**
   (`context_reason: inactive_base_context` — the check is scoped to base ref
   `codex/merge-queue-pilot`, not `main`). Verified across 12 concurrent PRs.
   It is *not* an authority-change rejection: the payload says
   `allowed: true, reason: same_repo_admin_authority_change`. Do not try to fix
   it from a feature PR.
3. **A NEW `tests/test_*.py` reds `unrun-suite`.** `scripts/audit_unrun_tests.py`
   fails any collecting suite no `run:` step names. The documented remedy —
   adding a step to `.github/ci/legacy-jobs.yml` — is a CI_AUTHORITY path AND a
   global invalidator, which drops the PR's path scoping and makes it inherit
   main's entire red set. So this wave's ~69 new tests were **folded into the
   already-wired `tests/test_research_vault.py`** under a `WAVE 4` banner, with
   `_w4_`-prefixed helpers to avoid colliding with that file's existing
   `_item`/`_seed_pdf`/`_cat`/`_dt`. Do not split them back out into new files.
4. **Unit tests did not catch two real client defects.** See §5 — the hero
   counters and the ZH timestamp. Static JS assertions test the code you thought
   to write; only rendering the page tests the page.

## §5 Browser verification (done)

Local harness (`scratchpad/serve.py`) serving the built page plus a controllable
`/api/research/catalog`. All four source-selection branches walked:

| Scenario | Status line | Result |
|---|---|---|
| Fresh live | `This week · Updated hourly` | ✅ 1,402 total, hero populated |
| Live 3h old | `Saved snapshot · live update delayed · updated Aug 19, 2026 · 09:38 UTC` | ✅ real generation time shown |
| API stale, bake newer | same, showing the **bake's** 09:22 UTC clock | ✅ bake chosen, not relabelled live |
| No valid copy | `Live research unavailable · try again shortly` | ✅ every counter `—` |

Console clean throughout. **This pass found two defects the unit tests missed:**

- the hero read **"0 new institutional reports this week · 0 highlighted · 0
  desks publishing"** while the feed said "unavailable" — the same false
  empty-vault claim, in bigger type, above the fold;
- the Chinese status span carried an **English** date, because `fmtWhen` reads
  the live `<html data-lang>` while both spans are written in one paint.

Both fixed in `325d3a5` and pinned by tests.

## §6 WHAT IS LEFT — production acceptance (needs R2 credentials)

The R2 research-bucket secrets exist only on the self-hosted runner, so both
remaining items run there. Tooling is merged and ready.

### 6a. Correction audit (the id-set census)

```bash
gh workflow run research-ingest.yml -f run_census=true
```

Runs `scripts/research_vault_census.py` (read-only; a test asserts every object
is byte-identical before and after) under `always()`, and uploads
`research-vault-census` as an artifact. Record:

- `CATALOG_IDS`, `VAULT_PDF_IDS`, `CORPUS_IDS`, `RECEIPTED_IDS` counts;
- each mismatch direction and **its disposition** — do NOT force the sets equal:

| Direction | Meaning | Action |
|---|---|---|
| `catalog − pdf` | user-visible dead reports (open → 404) | repair from source, or withdraw from availability |
| `receipt − catalog` | stranded processed reports | classify first: historical failed publish vs intentional deletion vs superseded duplicate. `recovery_sources` in the JSON gives each receipt's source `pdf_key` |
| `corpus − catalog` | publication-ahead rows | fine transiently; persistent = failed catalog publish. Serving tier already hides them |
| `catalog − corpus` | browsable, not searchable | rebuild the corpus row |
| mirror newer than R2 | **invariant violation** | reported as `::error`; means the mirror advanced past a failed publish |

**Recovery rule (freeze):** do **not** delete a receipt first. Reconstruct from
the receipt's source mapping + inbox/vault evidence, prove id/count consistency
against corpus + last known-good git snapshot, and only then touch a receipt.
Never blindly re-ingest the historical vault.

### 6b. Observe one real hourly run

Let a normal top-of-hour run happen and record: workflow run ID; catalog
`generated_at` pre/post; item count pre/post; `catalog_published`;
`corpus_published`; promoted-PDF failures; receipt flush count; repo snapshot
generation. **A green workflow must correlate with a successful canonical
publish** — that correlation is the thing Defect 6 removed and this wave
restored.

### 6c. Live API + browser + quota

- `GET /api/research/catalog` → `catalog_health.state == "fresh"`, sane
  `age_seconds`, and the browser saying "Updated hourly" only inside the window.
- Stale/missing/malformed simulation **in a staged store, never by corrupting
  production**.
- Pick one report admitted by that run: appears in catalog, appears in Pro
  search, PDF opens, download succeeds.
- Quota: allowance decreases exactly once on a successful download; unchanged
  against a missing-object fixture.

## §7 Publication failure that can still occur, and why it is safe

Between the corpus put and the catalog put, the corpus can hold a row the
catalog has not admitted. This is **by design** and safe because:

- the corpus is not a user-visible surface — search results are filtered to
  catalog-admitted ids for **every** tier (`app/research.py::_catalog_ids`);
- receipts do not flush, so those documents re-ingest next run;
- the repo mirror does not advance, so the SSR fallback cannot show them;
- `upsert` is idempotent, so the retry is a no-op for already-present rows.

The residual is an *ahead* corpus row, never a *visible* one. Closing it fully
would need a two-phase commit across two R2 objects, which the freeze explicitly
rules out ("do not build a generalized distributed transaction framework") and
which would buy nothing the visibility filter does not already provide.

## §8 Do not redo

- Do not add a second catalog, manifest, health database, or lifecycle store —
  the health block is a pure projection of the catalog and the clock.
- Do not make `catalog.load()` strict; the repair utilities need the fail-soft
  version. `read_strict` is the serving/publication contract.
- Do not gate the destructive-bootstrap refusal on vault PDFs or corpus rows
  (see §3.2 — it wedges new vaults).
- Do not enforce the future-clock or per-row rules on the ingest path (§3.1).
- Do not try to fix `ci-authority/codex/merge-queue-pilot` from a feature PR
  (§4.2).
