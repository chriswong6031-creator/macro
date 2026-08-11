# Calcbench parity — Wave 0B continuation handoff (2026-08-11)

Supersedes the §1 status table of
`research/CALCBENCH_PARITY_CLAUDE_CONTINUATION_HANDOFF_2026-08-06.md` for
everything below. That document remains the canonical description of the
*program*; this one is the canonical description of the *current state*.

**Opening instruction for the next session:**

> Read this handoff. All six GitHub secrets now exist. Rerun
> `attested-history-aapl-seed.yml` from `main` after the value-free credential
> diagnostic repair lands. The run will identify the rejected writer field
> without printing its value; correct that field, then run the Wave 0B chain in
> §5. Do not debug acquisition before the writer store passes admission.

---

## §0 STATUS AT A GLANCE

| Item | State | Evidence |
|---|---|---|
| Wave 0A — dedicated reader, code | **live verified** | `app/forensics.py` on main binds `build_attested_history_store` (2 refs), **0** `research_vault` refs; live API healthy; `/api/forensics/state` → 401 fails closed |
| Wave 0A — credential binding | **PARTIAL** | All 6 GitHub secrets exist; VPS delivery is not yet live-verified (§2, §4.1) |
| Dedicated R2 bucket | **created 2026-08-11** | `mastermind-attested-history-prod`, account `641d31a6bc84bccd90f347ac753275b3` (§3) |
| Seed run | **never succeeded** | `31528819923` attempts 1–2 reached `writer-store` and rejected the writer parent before R2 I/O; 0 artifacts |
| Wave 0B | **blocked** | Needs a valid writer parent and successful seed first |
| Waves 1–8 | **not started** | Strictly sequential behind 0B |

`main` was green as of 2026-08-08T10:38Z. Repo has **moved** to
`mastermindx-market-intelligence/macro` (was `chriswong6031-creator/macro`).

---

## §1 WHAT THE BLOCKER ACTUALLY IS

The seed has never produced a single artifact. Not because the pipeline is
broken — **the pipeline is proven good** (§4.2) — but because the protected
writer parent is rejected by local credential-format admission before the
first R2 request.

Verified 2026-08-11:

- repo scope — all four `R2_ATTESTED_HISTORY_*` reader/address names exist
- org scope — 0 secrets
- environment `attested-history-seed` — exactly 2, both `..._SEED_...`,
  updated `2026-08-11T03:27:33Z` / `03:27:39Z` (the operator rotated these to
  the new bucket's token)
- run `31528819923` attempt 1 rejected at `writer-store`; after correcting the
  endpoint secret from a bare host to the required HTTPS URL, attempt 2
  rejected at the same stage. The remaining rejected field is therefore in
  the protected writer parent and must be named by the sanitized diagnostic.

---

## §2 THE SIX SECRETS — CURRENT SCOPES AND VALUES

All four at **repository** scope. Not environment scope: the operator workflow
(`attested-history-operator.yml`) declares no `environment:`, so environment
secrets are invisible to it.

| Secret | Value |
|---|---|
| `R2_ATTESTED_HISTORY_ENDPOINT` | `https://641d31a6bc84bccd90f347ac753275b3.r2.cloudflarestorage.com` |
| `R2_ATTESTED_HISTORY_BUCKET` | `mastermind-attested-history-prod` |
| `R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID` | *(read-only R2 token's key id)* |
| `R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY` | *(read-only R2 token's secret)* |

Already present (environment `attested-history-seed`, do not move them):
`R2_ATTESTED_HISTORY_SEED_ACCESS_KEY_ID`,
`R2_ATTESTED_HISTORY_SEED_SECRET_ACCESS_KEY`.

**Format rules — all three enforced by regex, all three easy to get wrong:**

- endpoint: `^https://[a-f0-9]{32}\.r2\.cloudflarestorage\.com$` — HTTPS URL,
  with no trailing slash and no `/bucket` path. The earlier bare-host
  instruction was wrong: the production credential signer rejects it.
- bucket: `^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$` — lowercase.
- access key: `^[A-Za-z0-9]{16,128}$`.

**The read-only token must be a SECOND, SEPARATE R2 API token.**
`validate_production_environment_boundary()` rejects identical writer and
read-only parent access key IDs. Reusing one token fails even with all six
secrets present.

To verify without reading values:

```bash
gh api --paginate repos/mastermindx-market-intelligence/macro/actions/secrets \
  --jq '.secrets[].name | select(test("ATTESTED";"i"))'
```

Expect all four names. `--paginate` is mandatory: the repository has more than
one API page of secrets, and inspecting only page 1 falsely reported them
absent during this continuation.

---

## §3 THE BUCKET — AND THE ONE THAT LOOKED RIGHT BUT WASN'T

Correct: **`mastermind-attested-history-prod`** (created 2026-08-11, empty).

Rejected candidate: `mastermind-fundamental-forensics-prod`. The name is
plausible but the bucket is the **shared research store** — it contains
`research/research_vault/`, `research/capital_structure/`,
`research/earnings_wire_private/`, `research/research_inbox/`, and
`research/fundamental_forensics/`.

Why it must not be used:

- the attested store writes `fundamental_forensics/` at the **bucket root**
  (`attested_history_store.py:14`; `STORAGE_CONTROL_PREFIX =
  "fundamental_forensics/attested-history-seed-control/v1"`), confirmed by a
  local hermetic run;
- the `fundamental_forensics/` visible in that bucket is nested under
  `research/` — different path, existing research-tier content;
- it is the bucket Wave 0A **disconnected the API from**. Pointing
  `R2_ATTESTED_HISTORY_BUCKET` at it re-creates the exact defect the wave
  fixed, and grants the writer token access to the whole research store.

**Identifying tell:** the dedicated bucket is EMPTY, because the seed has
never succeeded. If a future session is unsure which bucket is which, the
empty one is the right one.

---

## §4 CORRECTIONS AND FINDINGS — READ BEFORE TRUSTING ANY EARLIER NOTE

### 4.1 "Credentials bound" was false, and the workflow reported success

An earlier session (and an earlier version of the canonical handoff) recorded
the Wave 0A credential-binding half as done: *"credentials bound, delivery
workflow green, service healthy."* **All three observations were true and the
conclusion was still wrong.**

`.github/workflows/deploy-api-secrets.yml` builds its env file with:

```bash
_add() { local n="$1" v; v="$(printf '%s' "$2" | tr -d '\r\n ')"; \
         if [ -n "$v" ]; then _lines="${_lines}${n}=${v}"$'\n'; fi; }
```

It appends a line **only if the value is non-empty**, and never errors when it
is empty. With the four secrets absent it delivered nothing for them, exited
0, and the API restarted healthy — because the fail-closed reader correctly
reports "not configured" rather than crashing. Green workflow, healthy
service, **zero credentials bound**.

The repair now requires each of the four dedicated reader/address inputs before
building or delivering the VPS env. A future missing value fails the workflow
loudly with the variable name and never prints the value. This must still be
verified by a successful delivery run and live API behavior after merge.

### 4.2 The seed pipeline is proven good — do not debug it

Run locally against a hermetic store (no credentials at all):

```bash
python3 -m scripts.seed_fundamental_forensics_attested_history \
  --enable-aapl-seed --work-dir <new> --output-dir <new> \
  --sec-user-agent "MastermindX Fundamental Forensics data@mastermind-x.com" \
  --local-store <new-dir>
```

It completed end-to-end and produced all four artifacts:

```
attested_history_operator_packet.json        7047 bytes
attested_history_seed_receipt.json           2077
attested_history_preflight_receipt.json      1933
attested_history_seed_bundle_receipt.json     995
```

…and a correct object layout: `fundamental_forensics/sec-source/v1/…`,
`fundamental_forensics/query-snapshots/v1/…`,
`fundamental_forensics/attested-history-seed-control/v1/…`.

Requires `scripts engine config contracts requirements collectors lib` on the
path — an extract missing `collectors` or `lib` fails at import, which looks
like a pipeline fault and isn't.

### 4.3 Seed failures are now diagnosable (PR #5145, merged)

Previously the sole operator-facing output was `seed failed; inspect the
protected runner diagnostics` — and **no such diagnostics existed**. A bare
`except Exception` discarded the traceback, wrote nothing, and `RUNNER_TEMP`
is cleaned between jobs. Diagnosing the last failure required reproducing the
whole pipeline locally.

Now on main:

- `AttestedHistorySeedError` → message verbatim (81 raise sites audited by AST
  walk: 75 static sentences, 6 interpolating only a `{field}` **name**, none
  carrying a value; the invariant is documented on the exception class)
- any other exception → `unexpected {ClassName} (detail suppressed)` — never
  the message, never the traceback
- both carry a static `stage` marker: `environment-boundary`,
  `run-provenance`, `dependency-lock`, `writer-store`, `readonly-store`,
  `acquire`, `preflight`

Verified against the real failure:

```
::error ...::seed failed at stage environment-boundary: dedicated attested-history parent credentials are unavailable
```

### 4.4 GitHub renders `***` for unset secrets too

The failed run's env block showed `***` for all eight `FF_ATTESTED_*`
variables, which reads as "all set". It is not evidence of anything — that is
just how a secret-derived env value is rendered. **Trust the secrets API, not
the log.**

---

## §5 WAVE 0B RUNBOOK

Preconditions: all six secrets present (§2); bucket is
`mastermind-attested-history-prod` (§3); PR #5145 on main (already true).

1. **Dispatch** — `gh workflow run attested-history-aapl-seed.yml --ref main
   -f enable_aapl_seed=true`. Gated `enable_aapl_seed == true && ref == main`.
2. **Approve** — the run pauses on environment `attested-history-seed`
   (required reviewer `chriswong6031-creator`). *The operator's standing
   instruction of 2026-08-09 was "run approved. you run" — an agent may
   approve on that authority, but say so plainly.* Note run 31170827673 was
   **cancelled** rather than approved on a previous attempt; confirm the run
   actually reaches `in_progress`.
3. **On failure** — read the `::error` annotation. It now names the stage and,
   for `AttestedHistorySeedError`, the exact cause. Do not reproduce locally
   before reading it.
4. **On success** — download artifact
   `attested-history-aapl-seed-<run_id>-<run_attempt>`. Independently
   **recompute byte lengths and SHA-256s** rather than trusting the receipts.
   Verify repo / commit / ref / workflow / run / attempt / dependency-lock /
   environment / storage-control-probe / issuer / accession / object IDs, and
   the explicit nonclaims.
5. **Packet-activation PR** — commit the sealed packet to
   `config/fundamental_forensics/attested_history_operator.v1.json` and
   replace the inert absence assertion at the end of
   `tests/test_fundamental_forensics_attested_history_operator.py::test_contracts_and_workflow_are_inert_and_no_production_packet_exists`:

   ```python
   assert not (ROOT / "config" / "fundamental_forensics" / "attested_history_operator.v1.json").exists()
   ```

   with byte-exact admission + Git provenance + workflow binding + tamper
   rejection. **Never hand-edit the packet.** Leave the ~40 surrounding
   inertness assertions on the operator workflow intact — they must still hold
   after activation.
6. **Zero-write replay** — after that merges, `gh workflow run
   attested-history-operator.yml --ref main -f enable_readonly_preflight=true`.
   Accept **only** on zero writes and zero write attempts.

---

## §6 STILL OPEN (operator decisions, not agent work)

1. **Git history retains the leaked paid body.** PR #4960 purged HEAD —
   `data/us_prophet_rank/candidates/2026-07.parquet` no longer carries
   `forensics__findings` (722 rows) or `forensics__disclosure_changes`. History
   rewrite across ~50 active worktrees is an operator call, deliberately not
   made.
2. **Calcbench password rotation** — outstanding since the original handoff; it
   appeared in chat and must never become an ingestion dependency.
3. **Three `HOLD-` rows** filed in `research/DO_NOT_REBUILD.md` by PR #4961.
   The significant one: the same detector id means **quarterly** YoY on the
   Filing Forensics page and **annual** YoY on stock pages, with identical
   thresholds. Fixing it moves published numbers, so it was pinned, not
   decided.
4. **`deploy-api-secrets.yml` silent skip** (§4.1) — unfixed.

---

## §7 SESSION LEDGER (2026-08-07 → 08-11)

Merged: **#4960** paid-forensics leak containment (seam + parquet purge +
repo-wide guard); **#4961** detector evaluability authority (all three
implementations, 11/11 mutations, 3 `HOLD-` rows); **#4963** → landed via
**#4965** (third-party structural skip, main heal); **#5145** diagnosable seed
failure.

Verified live on main, not merely merged: leak columns absent from both
candidate parquets, and a nightly appended **after** the fix (2026-08-08
08:47Z, ~2h post-merge) growing `2026-08.parquet` 1,513 → 3,022 rows **without
re-introducing them** — production proof the seam holds.

**The recurring defect class across all of it:** a check reporting safety it
was not providing. A CI suite that never executed. A guard whose sweep was
narrower than its own docstring. A parquet test that could not fail because
round-tripped lists are `ndarray`, not `list`. A mutation that emptied nothing
and read green. A Chinese fixture whose token was not one of the four matched
forms. A workflow that skipped empty secrets and exited 0. A failure message
pointing at diagnostics that never existed. Assume the same of anything here
marked "done" that you have not personally observed.
