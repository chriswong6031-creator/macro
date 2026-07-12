# Metabolism Arming Checklist

Operator runbook for arming the autonomous metabolism loop.
Written by: Fable (2026-07-11, wave W6). Revised by Fable (2026-07-11 v2):
auto-chain crons, multi-key failover, admin-panel switch, and the ruleset
form of Act 2 (the original classic-branch-protection command would have
rejected the pipeline's direct pushes to main — do not use it).
Ruling: R-V4-1 — shadow-first law; R-V5-1..10 (durability + self-repair).

---

## (a) What ships armed-gated today

Nine GitHub Actions workflows drive the metabolism loop. The gating is two-layer: the job-level condition `if: vars.AUTONOMY_PAUSED != 'true'` lets the job START even when the variable is unset (so paused no-op runs stay visible in the run history), and the in-script re-check — `AUTONOMY_PAUSED` must equal the exact string `false` — is what actually fails closed before any real action. Net behavior: unset/anything-but-`false` = paused; only Act 5's explicit `false` arms:

| Workflow | Cron | Purpose |
|---|---|---|
| `metabolism-heartbeat.yml` | `45 * * * *` (hourly) | Freshness + health monitor; writes organism_state + insight_bus rows |
| `metabolism-agenda.yml` | `15 9 * * *` (daily 09:15 UTC) | SENSE + AGENDA: builds TIL fitness card + organism_state + agenda artifact |
| `metabolism-propose.yml` | `45 9 * * *` (daily 09:45 UTC) | PROPOSE: Opus lobe-brain emits docket + registers fitness contracts |
| `metabolism-adjudicate.yml` | `15 10 * * *` (daily 10:15 UTC) | ADJUDICATE: iterates ALL pending propose branches; orchestrator + adversary + two-key resolve |
| `metabolism-build.yml` | `45 10 * * *` (daily 10:45 UTC) | BUILD: Sonnet draft-PR sessions on authorized proposals (also `workflow_dispatch` per-cycle) |
| `metabolism-verify.yml` | `15 11 * * *` (daily 11:15 UTC) | VERIFY: grades realized fitness deltas on matured contracts |
| `metabolism-audit.yml` | `45 11 * * *` (daily 11:45 UTC) | AUDIT (V7): deterministic containment + adversarial Opus code review of each build-lane draft PR; writes audit record + governance event; required by MERGE gate step 5.5 |
| `metabolism-merge.yml` | `15 12 * * *` (daily 12:15 UTC) | MERGE: serialized two-key + green-CI + fence-checked + **audit-approved** merges (also `workflow_dispatch`) |
| `metabolism-dream.yml` | `0 6 * * 0` (Sunday 06:00 UTC) | DREAM: preference_prior + lessons anti-rot resummary |
| `metabolism-gc.yml` | `20 7 * * *` (daily 07:20 UTC) | GC: reaps leaked build worktrees. Deliberately UNGATED — cleanup must run even while paused; it is read-and-remove only |

Every armed workflow re-checks `AUTONOMY_PAUSED` in shell before any real action, and every workflow carries an `if: failure()` Telegram operator notify (silent skip when the Telegram secrets are absent). The autonomy loop will never author code, merge a PR, or advance any forward ledger until Act 5 below is executed.

---

## (b) The Six Acts (exact commands)

### Act 1 — Set secrets

```bash
# Pool OAuth keys (each from `claude setup-token` on a separate Max account).
# ANY SUBSET WORKS: the failover waterfall (engine/llm_auth.py, 2026-07-11)
# tries pool keys non-cooling-first by 5h load, then the legacy
# CLAUDE_CODE_OAUTH_TOKEN, then ANTHROPIC_API_KEY, then DeepSeek. A missing,
# revoked (401/403), or rate-limited (429/529) key is cooled in the ledger
# and skipped — it degrades the pool, never breaks a stage.
gh secret set CLAUDE_CODE_OAUTH_TOKEN_1
gh secret set CLAUDE_CODE_OAUTH_TOKEN_2   # optional
gh secret set CLAUDE_CODE_OAUTH_TOKEN_3   # optional

# Fallback Anthropic API key (if the whole OAuth pool is exhausted)
gh secret set ANTHROPIC_API_KEY

# Telegram digest + failure notifies (optional — loop operates without it)
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
```

All secrets are name-only references in `config/capability_manifest.yml` — no values are stored in the repo.

### Act 2 — Branch protection with required status checks (RULESET form — do NOT use classic protection)

The three REQUIRED status checks gate every PR the loop opens. They are the job
names of the always-on `.github/workflows/fences.yml` (which runs on EVERY PR —
the path-gated copies in `ci.yml` alone would leave non-metabolism PRs stuck on
"Expected — waiting for status" if made required).

**Why a ruleset and not the classic branch-protection API:** this repo's
pipeline pushes directly to `main` dozens of times a day (render lanes, live
quotes, metabolism artifact commits) using the workflow `GITHUB_TOKEN`. Classic
protection with required checks + `enforce_admins=true` rejects those pushes and
freezes the nightly. The ruleset below gets the same PR gate while letting the
`github-actions` app (and ONLY that app) bypass for direct pushes:

```bash
REPO="chriswong6031-creator/macro"

gh api --method POST "repos/$REPO/rulesets" --input - <<'JSON'
{
  "name": "main-metabolism-fences",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "required_status_checks", "parameters": {
        "strict_required_status_checks_policy": false,
        "required_status_checks": [
          { "context": "self-mod-fence",    "integration_id": 15368 },
          { "context": "capability-broker", "integration_id": 15368 },
          { "context": "grader-manifest",   "integration_id": 15368 }
        ]
    }}
  ],
  "bypass_actors": [
    { "actor_id": 15368, "actor_type": "Integration", "bypass_mode": "always" }
  ]
}
JSON
```

Design notes (deliberate deviations from the original draft of this Act):
- `15368` is the `github-actions` app id. Bypass covers the pipeline's direct
  pushes. The loop's own merges use `METABOLISM_MERGE_PAT` (Act 3) — a PAT
  carries the OPERATOR's identity, not the app's, so **loop merges remain fully
  subject to the three required checks**. Do NOT add an admin/owner bypass:
  that would let the PAT-driven merge lane skip the fences.
- `strict_required_status_checks_policy: false` (the original said `strict:true`):
  strict mode requires every PR branch to be up-to-date with `main` before
  merging — with main advancing every ~15 minutes here, that makes every PR
  permanently unmergeable.
- `integration_id: 15368` pins each required context to checks produced by
  GitHub Actions itself, so another app cannot spoof a green fence.

Verify the ruleset is active:

```bash
gh api "repos/$REPO/rulesets" | jq '.[] | {name, enforcement}'
gh api "repos/$REPO/rules/branches/main" | jq '[.[].type]'
```

Expected: `main-metabolism-fences` / `active`, and the rule types include
`deletion`, `non_fast_forward`, `required_status_checks`.

### Act 3 — Merge PAT (WITHOUT workflows scope)

The metabolism loop needs a PAT to merge its own draft PRs via the serialized merge lane. The PAT must NOT have `workflows` scope (preventing the loop from editing CI).

Since 2026-07-11 this PAT is actually CONSUMED: `metabolism-merge.yml` (merge
step) and `metabolism-build.yml` (draft-PR creation) use
`${{ secrets.METABOLISM_MERGE_PAT || secrets.GITHUB_TOKEN }}`. The PAT matters
for two reasons beyond least-privilege: (1) PRs created by `GITHUB_TOKEN` never
trigger `pull_request` workflows (GitHub anti-recursion), so without the PAT the
loop's draft PRs would sit with NO CI checks — permanently unmergeable once
Act 2's required checks are enforced; (2) merges by the PAT are subject to the
Act 2 ruleset (the PAT is not a bypass actor).

```bash
# Mint at: Settings > Developer settings > Personal access tokens > Fine-grained tokens.
#   Repository access: ONLY this repo.
#   Permissions: Contents (read+write), Pull requests (read+write).
#   DO NOT grant Workflows. DO NOT grant Administration.

gh secret set METABOLISM_MERGE_PAT
```

### Act 4 — Register metabolism-build in capability_manifest.yml

`claude_code_oauth_1/2/3` already include `metabolism-build` in `allowed_lanes` (confirmed in `config/capability_manifest.yml`). No edit is required — the lane is pre-registered.

To verify:

```bash
python3 -c "
import yaml
with open('config/capability_manifest.yml') as f:
    d = yaml.safe_load(f)
for cap in d.get('capabilities', []):
    if 'metabolism-build' in cap.get('allowed_lanes', []):
        print(cap['capability_id'], ':', cap['allowed_lanes'])
"
```

Expected: `claude_code_oauth_1`, `claude_code_oauth_2`, `claude_code_oauth_3` each print with `metabolism-build` in their `allowed_lanes` list.

How `_resolve_key_ref` falls back: `scripts/metabolism_build._resolve_key_ref()` calls `engine.neuralweb.capability_broker.resolve(cap_id, lane="metabolism-build")`. The broker checks the manifest; if `metabolism-build` is absent from `allowed_lanes`, it returns `{allowed: False}` and the dispatch is refused (fail-closed). The lane is already present — this step is a verification, not an edit.

### Act 5 — Flip the arming variable (do this LAST)

```bash
# Flip LAST — after all acts above are confirmed.
gh variable set AUTONOMY_PAUSED --body false
```

This is the single irreducible arming act. Every metabolism stage reads `AUTONOMY_PAUSED` as its first action; only the exact string `false` arms the loop. Any other value (unset, `true`, empty) keeps all stages inert. The variable was explicitly seeded to `true` on 2026-07-11 so the paused state is visible rather than implicit.

Equivalent UI: the **Metabolism tab at https://admin.mastermind-x.com** carries an
arm/pause switch that PATCHes this same variable (requires Act 6 below), plus the
key-pool health board and recent metabolism runs.

To re-pause immediately:

```bash
gh variable set AUTONOMY_PAUSED --body true
```

### Act 6 — Admin-panel switch token (optional but recommended)

The admin console's Metabolism switch needs a server-side GitHub token to read
and write the `AUTONOMY_PAUSED` variable. Without it the tab degrades to a
read-only UNKNOWN view (switch disabled).

```bash
# Mint a SECOND fine-grained PAT (separate from Act 3 — do not widen the merge PAT):
#   Repository access: ONLY this repo.
#   Permissions: Actions (read), Variables (read+write).
gh secret set ADMIN_GH_TOKEN

# Deliver it to the VPS (/etc/macro-admin.env as GH_TOKEN=...) + restart admin:
gh workflow run deploy-api-secrets.yml
```

---

## (c) Pre-arming evidence

### Run the shadow cycle harness

Before arming, run the shadow-first harness to produce verifiable arming evidence:

```bash
python -m scripts.metabolism_shadow_cycle
```

This runs the full SENSE → AGENDA → PROPOSE → ADJUDICATE → BUILD(dry_run) → VERIFY(seeded) → DREAM cycle against real repo state while `AUTONOMY_PAUSED` stays unset. The real `data/metabolism/` stores are never touched. Artifacts land in `data/metabolism/shadow/<cycle_id>/`.

### What a healthy summary.json looks like

```json
{
  "schema": "metabolism.shadow_cycle.v1",
  "cycle_id": "shadow-20261015-0945",
  "ts": "2026-10-15T09:45:00+00:00",
  "stages": {
    "sense_fitness":         { "status": "ok",   "artifact": "...", "note": "fitness card written to shadow root" },
    "sense_organism_state":  { "status": "ok",   "artifact": "...", "note": "organism_state written to shadow root" },
    "sense_insight_bus":     { "status": "ok",   "artifact": "...", "note": "N insight_bus rows emitted" },
    "agenda":                { "status": "ok",   "artifact": "...", "note": "agenda: N items; provider=null" },
    "propose":               { "status": "ok",   "artifact": "...", "note": "docket: 1 proposals; provider=null" },
    "adjudicate":            { "status": "ok",   "artifact": null,  "note": "orch=1 adversary=1 resolve: 1/1 authorized" },
    "build":                 { "status": "ok",   "artifact": "...", "note": "dry_run BUILD: 1 proposals processed" },
    "verify":                { "status": "ok",   "artifact": "...", "note": "verify: outcome=UNVERIFIABLE ... honest_null=True" },
    "dream":                 { "status": "ok",   "artifact": "...", "note": "dream: status=paused" },
    "artifact_collection":   { "status": "ok",   "artifact": "...", "note": "N artifacts collected" }
  },
  "stubbed_stages": ["agenda", "propose", "adjudicate"],
  "real_stores_untouched": true,
  "wall_seconds": 12.4
}
```

Key things to check:
- `real_stores_untouched: true` — the real data stores were not modified
- `verify.note` contains `honest_null=True` — UNVERIFIABLE is correct (seeded contract has no graded data yet)
- `dream.note` contains `status=paused` — correct in a shadow run (the dream engine gates itself on `AUTONOMY_PAUSED`); after arming, expect `insufficient_data` until ≥10 contracts close (~2026-10-15)
- `stubbed_stages` lists agenda/propose/adjudicate when run with `--no-llm` (the default)

### Three v3 first-armed-cycle retro-checks

When the first real armed cycle runs, verify these three properties:

1. **Freshness header fires on a staled artifact.** Run `python -m engine.metabolism.organism_state` with a fitness card older than the configured SLA (`config/metabolism_context_sla.yml`). The organism_state `gaps` block should list the stale artifact with a `freshness_sla_breach` gap entry.

2. **Recall surfaces a seeded prior-FAIL.** Seed a FAIL lesson into `data/metabolism/lessons.jsonl` (use `engine.metabolism.memory.append_lesson()` with `verdict="FAIL"`). Then run `engine.metabolism.recall.recall_lessons()` — the FAIL lesson should appear in the recalled text with its `FAIL` verdict preserved (the FAIL-floor ensures it is never silently dropped).

3. **Grounding flags a bogus lobe_id.** Seed an organism_state entry with a `lobe_id` not present in `config/lobe_charters.yml`. The grounding check in `engine.metabolism.grounding` should emit a `contradiction` insight_bus row flagging the unknown lobe.

---

## (d) Post-arming day-1 verification

### Which workflow runs to watch

After flipping `AUTONOMY_PAUSED=false`, monitor GitHub Actions for the first full day:

| Time (UTC) | Workflow | What to watch for |
|---|---|---|
| Hourly :45 | metabolism-heartbeat | Should produce organism_state.json; no errors in the `commit_artifacts` step |
| 09:15 | metabolism-agenda | Agenda artifact committed to branch; N items in `data/metabolism/agenda/<cycle_id>.json` |
| 09:45 | metabolism-propose | Docket committed; proposals > 0; `registered` contracts > 0 in trial_ledger.jsonl |
| 10:15 | metabolism-adjudicate | Governance rows written; `two_key` resolve row shows authorized count |
| 11:15 | metabolism-verify | Verify record written; `outcome=UNVERIFIABLE` is correct (no mature contracts yet) |
| 11:45 | metabolism-audit | Audit records written to `data/metabolism/audit/<pr>.json`; each record has `verdict` and `head_sha`; governance events appended to `data/neuralweb/governance.jsonl` with `event_type=metabolism_audit` |
| Sunday 06:00 | metabolism-dream | preference_prior.json written; armed runs show `status=insufficient_data` until ≥10 closed contracts (~2026-10-15) |

### Where artifacts land

All artifacts are committed to branches named `metabolism/<stage>-<cycle_id>` and PRs are opened as DRAFT. Artifacts are also committed to `main` by the respective workflow step:

- `data/metabolism/fitness/til.json` — TIL fitness card (SENSE stage)
- `data/metabolism/organism_state.json` — whole-organism health
- `data/metabolism/insight_bus.jsonl` — append-only stigmergy bus
- `data/metabolism/agenda/<cycle_id>.json` — ranked agenda
- `data/metabolism/dockets/<cycle_id>.json` — PROPOSE docket
- `data/metabolism/verify/<cycle_id>.json` — VERIFY record
- `data/metabolism/preference_prior.json` — DREAM preference prior
- `data/metabolism/lessons.jsonl` — VERIFY-appended lessons
- `data/metabolism/strategic_memory.jsonl` — VERIFY-appended strategic memory

### Break-glass

To immediately halt all autonomous activity — either flip the switch on the
**Metabolism tab at https://admin.mastermind-x.com** (one click, confirm
dialog), or:

```bash
gh variable set AUTONOMY_PAUSED --body true
```

Every in-flight stage will no-op on its next invocation. Running stages cannot be interrupted mid-run, but they will not dispatch any further sessions or write to real stores after the guard fires on the next stage boundary.

For a deeper pause that also prevents the variable from being reset accidentally, disable the workflows directly:

```bash
gh workflow disable metabolism-heartbeat.yml
gh workflow disable metabolism-agenda.yml
gh workflow disable metabolism-propose.yml
gh workflow disable metabolism-adjudicate.yml
gh workflow disable metabolism-build.yml
gh workflow disable metabolism-merge.yml
gh workflow disable metabolism-verify.yml
gh workflow disable metabolism-dream.yml
```

(`metabolism-gc.yml` may stay enabled — it is ungated by design and only reaps
leaked worktrees; disable it too only if you want zero metabolism activity of
any kind.)

Re-enable with `gh workflow enable <name>` and then re-flip `AUTONOMY_PAUSED=false`.
