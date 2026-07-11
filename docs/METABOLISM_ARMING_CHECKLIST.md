# Metabolism Arming Checklist

Operator runbook for arming the autonomous metabolism loop.
Written by: Fable (2026-07-11, wave W6).
Ruling: R-V4-1 — shadow-first law.

---

## (a) What ships armed-gated today

Six GitHub Actions workflows drive the metabolism loop. The gating is two-layer: the job-level condition `if: vars.AUTONOMY_PAUSED != 'true'` lets the job START even when the variable is unset (so paused no-op runs stay visible in the run history), and the in-script re-check — `AUTONOMY_PAUSED` must equal the exact string `false` — is what actually fails closed before any real action. Net behavior: unset/anything-but-`false` = paused; only Act 5's explicit `false` arms:

| Workflow | Cron | Purpose |
|---|---|---|
| `metabolism-heartbeat.yml` | `45 * * * *` (hourly) | Freshness + health monitor; writes organism_state + insight_bus rows |
| `metabolism-agenda.yml` | `15 9 * * *` (daily 09:15 UTC) | SENSE + AGENDA: builds TIL fitness card + organism_state + agenda artifact |
| `metabolism-propose.yml` | `45 9 * * *` (daily 09:45 UTC) | PROPOSE: Opus lobe-brain emits docket + registers fitness contracts |
| `metabolism-adjudicate.yml` | `15 10 * * *` (daily 10:15 UTC) | ADJUDICATE: orchestrator + adversary + two-key resolve |
| `metabolism-verify.yml` | `15 11 * * *` (daily 11:15 UTC) | VERIFY: grades realized fitness deltas on matured contracts |
| `metabolism-dream.yml` | `0 6 * * 0` (Sunday 06:00 UTC) | DREAM: preference_prior + lessons anti-rot resummary |

Every workflow re-checks `AUTONOMY_PAUSED` in shell before any real action. BUILD (`metabolism-build.yml`) runs on `workflow_dispatch` (per-cycle, not cron) and is also armed-gated. The autonomy loop will never author code, merge a PR, or advance any forward ledger until Act 5 below is executed.

---

## (b) The Five Acts (exact commands)

### Act 1 — Set secrets

```bash
# Primary OAuth key (required — without this, all LLM stages no-op)
gh secret set CLAUDE_CODE_OAUTH_TOKEN_1

# Optional additional keys for load distribution across the 5-hour window
gh secret set CLAUDE_CODE_OAUTH_TOKEN_2
gh secret set CLAUDE_CODE_OAUTH_TOKEN_3

# Fallback Anthropic API key (if OAuth pool is exhausted)
gh secret set ANTHROPIC_API_KEY

# Telegram digest (optional — loop operates without it)
gh secret set TELEGRAM_BOT_TOKEN
gh secret set TELEGRAM_CHAT_ID
```

All secrets are name-only references in `config/capability_manifest.yml` — no values are stored in the repo.

### Act 2 — Branch protection with required status checks

The three REQUIRED status checks gate every PR the loop opens:

```bash
# Add self-mod fence, capability redline, and grader manifest as required checks.
# Replace OWNER/REPO with the actual GitHub repo slug.
REPO="OWNER/REPO"

gh api --method PUT "repos/$REPO/branches/main/protection" \
  --field required_status_checks='{"strict":true,"contexts":["self-mod-fence","capability-broker","grader-manifest"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":0,"dismiss_stale_reviews":false}' \
  --field restrictions=null \
  --field allow_force_pushes=false \
  --field allow_deletions=false
```

Verify the protection is active:

```bash
gh api "repos/$REPO/branches/main/protection" | jq '.required_status_checks.contexts'
```

Expected output includes `"self-mod fence selftest"`, `"capability broker + redline test suite"`, `"grader manifest (fitness graders + immutable configs unchanged)"`.

### Act 3 — Merge PAT (WITHOUT workflows scope)

The metabolism loop needs a PAT to merge its own draft PRs via the serialized merge lane. The PAT must NOT have `workflows` scope (preventing the loop from editing CI).

```bash
# Mint a PAT with scopes: repo (read+write), pull_requests — NOT workflows.
# The GitHub web UI: Settings > Developer settings > Personal access tokens > Fine-grained tokens.
# Recommended scopes: Contents (read+write), Pull requests (read+write).
# DO NOT add workflow permissions.

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
# Flip LAST — after all four acts above are confirmed.
gh variable set AUTONOMY_PAUSED --body false
```

This is the single irreducible arming act. Every metabolism stage reads `AUTONOMY_PAUSED` as its first action; only the exact string `false` arms the loop. Any other value (unset, `true`, empty) keeps all stages inert.

To re-pause immediately:

```bash
gh variable set AUTONOMY_PAUSED --body true
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

To immediately halt all autonomous activity:

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

Re-enable with `gh workflow enable <name>` and then re-flip `AUTONOMY_PAUSED=false`.
