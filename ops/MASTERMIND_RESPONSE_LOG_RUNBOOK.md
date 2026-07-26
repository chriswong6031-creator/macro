# Mastermind AI response log — runbook

Consistently logs **every user-facing answer** the Mastermind AI produces, across
**both** surfaces, into one batch-evaluatable corpus surfaced in the admin panel's
**Mastermind AI → AI Response Logs** section. The corpus exists to evaluate answers
in batches and to improve the assistant (better context, better skills, training data).

## Architecture (why R2, and why one instrumentation point)

**Both** user-facing surfaces run the same `mm_brain.js` widget against the same
macro brain gateway (`/api/brain/stream`, `engine/neuralweb/brain_gateway.py`):

- **Macro Dashboard** — `mm_brain.js` launched by `theme.js` (anchor `br`).
- **Terminal** (charting-app) — mounts the production `mm_brain.js` via `BrainWidget`
  (anchor `top`) and proxies `/api/brain/*` to `https://mastermind-x.com`. Its old
  `/api/copilot` DeepSeek route is deprecated and unused.

`mm_brain.js` stamps `context.page` = `terminal` (anchor `top`) or `dashboard`
(otherwise). So a **single** log call inside `chat_stream` captures both surfaces and
derives `surface` from that page tag — there is **no separate Terminal write path** and
the charting-app repo needs no change.

The gateway runs on a remote VPS; the admin panel reads local files on the Mac.
Cloudflare R2 is the transport every other artifact already rides. Each answer is
written as **one immutable object**:

```
mastermind_response_logs/<surface>/<YYYY-MM-DD>/<id>.json
```

```
 Macro Dashboard widget ─┐                         ┌─ Terminal widget (charting-app)
 (mm_brain.js, page=      │  POST /api/brain/stream │   mm_brain.js via BrainWidget,
  dashboard)              ▼                         ▼   page=terminal → /api/brain/* proxy)
              ┌───────────────────────────────────────────────┐
              │ macro-api  engine/neuralweb/brain_gateway.py   │
              │   chat_stream → _log_brain_response            │
              │   surface = (page=='terminal' ? terminal:macro)│
              └───────────────────────────┬───────────────────┘
                                          │ best-effort R2 PUT (fire-and-forget)
                                          ▼
                     Cloudflare R2  mastermind_response_logs/<surface>/<date>/<id>.json
                                          │  admin/mastermind_logs.refresh() (list + get new)
                                          ▼
                 data/mastermind/response_log.jsonl  (admin-local, gitignored)
                 data/mastermind/response_eval.jsonl (operator verdicts, gitignored)
                                          │
                                          ▼
                 Admin panel → Neural Web → **AI Response Logs**
                 (filter · expand Q/A · grade/thumb/flag/tag/note · JSONL/CSV export)
```

- **Write side** is *in-process and best-effort* — the answer is already on the wire
  before the log is written; a missing credential or a network blip is a silent no-op
  and never disturbs the chat path.
- **Read side** (the admin) ingests the R2 prefix incrementally, dedup by `id`.
- **Eval is a separate local sidecar** overlaid by `id` at read time — grading never
  mutates the immutable corpus, and re-ingesting can never clobber a verdict.

## Schema — `mastermind.response_log.v1`

Contract + writer: `lib/mastermind_response_log.py`. One row per answer:

| field | notes |
|---|---|
| `id` | uuid hex; R2 object stem; dedup key |
| `ts` | ISO-8601 UTC |
| `surface` | `macro` \| `terminal` |
| `lane` / `mode` | `fast`/`pro`; `chat`/`research` (macro); terminal → `fast`/`chat` |
| `model` / `provider` | e.g. `claude-opus-4-8`/`claude_api`, `deepseek-chat`/`deepseek` |
| `thread_id` | conversation id (null for stateless/guest) |
| `user_ref` | **hashed** (`u_<sha256[:16]>`) or `guest` — raw ids/emails are NEVER stored |
| `question` / `answer` | text (image markers stripped upstream; length-bounded) |
| `input_tokens` / `output_tokens` / `latency_ms` | metering |
| `context` | small scalar dict (`page`, `symbol`, …) |
| `citations` / `tools` / `lang` | macro-side extras |
| `flags` | `{filtered, degraded, error, screened}` |

Eval sidecar rows are `mastermind.response_eval.v1` (`grade` 1–5, `thumb`, `star`,
`tags[]`, `note`), append-only, latest-wins by `id`.

## Configuration

Logging is **ON** whenever a sink is configured and it is not explicitly disabled.

| env var | where | effect |
|---|---|---|
| `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | macro-api VPS (`/etc/macro-api.env`), admin/Mac | the R2 sink. **NOT implied by other R2 lanes** — `R2_RESEARCH_*` on the VPS does not satisfy this; the logger gates on the four **plain** `R2_*` names exactly (`lib.mastermind_response_log.enabled()`) |
| `MASTERMIND_RESPONSE_LOG_DISABLED` | any | truthy → hard-off (kill switch) |
| `MASTERMIND_RESPONSE_LOG_LOCAL_DIR` | any | optional local mirror dir (tests / VPS durability fallback) |

No new cron is required: the brain gateway PUTs to R2 directly (once
`/etc/macro-api.env` carries the plain `R2_*` keys — see above; a restart of
`macro-api` is needed after editing the env file). The admin pulls on demand (the
**Refresh from R2** button) — or wire
a periodic `refresh()` later. Because both surfaces proxy through this one gateway,
there is nothing to configure on the charting-app/Terminal side.

## Operating the admin view

Admin → **Neural Web → AI Response Logs**:

- **Refresh from R2** — pull new answers into the local ledger (idempotent; dedup by id).
- **Filter** — surface, lane, model, graded/ungraded, 👍/👎, flagged, errors, free-text search.
- **Row** — click to expand the full question, answer, and metadata (provider, latency,
  tokens, hashed user, thread, page/symbol).
- **Grade** — 1–5 + 👍/👎 + ⚑ flag + tags + note → **Save verdict** (writes the sidecar).
- **Export** — JSONL (full rows + eval) or CSV (flattened) of the current filter, for
  batch evaluation / training-set curation in external tooling.

## When the tab says "Ingest dark"

The tab computes ingest health on every load (`mastermind_logs.ingest_health`): a
full-width **"⚠️ Ingest dark since <date>"** banner means the newest ledger row is
≥ 2 days old — or the ledger has never seen a row. Per-surface red pills
(`macro dark Nd` / `terminal dark Nd`) cover the asymmetric case where one surface
keeps writing while the other silently stops.

This surface exists because the failure already happened: the logger shipped
2026-07-24 but `/etc/macro-api.env` had no plain `R2_*` keys, so `enabled()` was
False and the bucket held **zero** objects until 2026-07-26 — with nothing anywhere
saying so. Recovery recipe from that incident:

1. On the VPS: back up the env file (`cp -p /etc/macro-api.env
   /etc/macro-api.env.bak.YYYYMMDD`), append the four plain `R2_*` lines,
   `systemctl restart macro-api`.
2. Send one guest turn: `POST https://www.mastermind-x.com/api/brain/stream` with
   `{"message":"…","lane":"fast"}`.
3. Confirm a fresh object under `mastermind_response_logs/macro/<today>/` in the
   bucket, then **Refresh from R2** in the tab.

If the banner persists with recent R2 objects present, the problem is the
admin-side pull, not the writers. Two known causes, both silent by design
(`refresh()` reports "no R2 creds — ledger unchanged" for either): missing plain
`R2_*` creds in the admin's own environment (`/etc/macro-admin.env` for the
deployed panel), or **boto3 absent from the admin's venv** (`/opt/macro/.venv` on
the VPS — the import is lazy and fail-soft; `setup-admin.sh` installs it since
2026-07-26). Both were hit on 2026-07-26: creds + boto3 had to be added before the
deployed panel's first successful refresh (7 rows).

## Privacy & retention

- The corpus holds real user questions and answers. Both ledgers are **gitignored**
  (`data/mastermind/response_log.jsonl`, `response_eval.jsonl`) — admin-local only,
  never committed, never deployed.
- User identity is stored **hashed** (`user_ref`); raw ids/emails never enter a row.
- R2 objects have no lifecycle policy here — prune the `mastermind_response_logs/`
  prefix (or add an R2 lifecycle rule) if you want a bounded retention window.
- Kill switch: set `MASTERMIND_RESPONSE_LOG_DISABLED=1` on any surface to stop logging
  it without a redeploy of the answer path.

## Verify

```bash
# Unit + admin route contract
python -m pytest tests/test_mastermind_response_log.py tests/test_admin_mastermind_logs.py -q

# End-to-end against a seeded data root (admin open when ADMIN_PASSWORD unset)
ROOT=$(mktemp -d); mkdir -p "$ROOT/data/mastermind"
printf '%s\n' '{"id":"r1","schema":"mastermind.response_log.v1","ts":"2026-07-24T12:00:00+00:00","surface":"macro","model":"claude-opus-4-8","question":"q","answer":"a","flags":{}}' > "$ROOT/data/mastermind/response_log.jsonl"
MACRO_ADMIN_ROOT="$ROOT" python -m admin --port 8799 &
curl -s 'http://127.0.0.1:8799/api/mastermind_ai/response_logs?limit=5' | python -m json.tool
```

## Surfaces

Both are captured by the **single** instrumentation in
`engine/neuralweb/brain_gateway.py` (`chat_stream` → `_log_brain_response`; the
screened-refusal path is logged too):

- **Macro Dashboard** — `mm_brain.js` (anchor `br`) → `context.page` != `terminal`
  → `surface = "macro"`.
- **Terminal** (charting-app) — `mm_brain.js` via `BrainWidget` (anchor `top`) proxies
  `/api/brain/*` to this gateway → `context.page == "terminal"` → `surface = "terminal"`.

The charting-app repo requires **no change**: it already routes all AI answers through
this gateway. (Its legacy `terminal/app/api/copilot/route.ts` DeepSeek path is
deprecated/unused; if it is ever revived as a direct-to-model path, it would need its
own writer to the same R2 prefix.)
