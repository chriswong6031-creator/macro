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
| `thinking` | **optional** list of the model's own reasoning segments (added 2026-07-26) |

Eval sidecar rows are `mastermind.response_eval.v1` (`grade` 1–5, `thumb`, `star`,
`tags[]`, `note`), append-only, latest-wins by `id`. The LLM contradiction pass writes
`contra_verdict` / `contra_signals` / `contra_note` / `contra_model` / `contra_ts` into
the **same** rows by merging on top of the current overlay — a machine verdict never
overwrites an operator's grade, and an operator's later grade never drops the verdict.

## Thinking capture — the contradiction corpus

`thinking` is an **additive optional field on the same v1 schema** (no version bump:
readers tolerate extra keys and pre-2026-07-26 rows simply lack it):

```json
"thinking": [{"round": 1, "phase": "tool", "model": "deepseek-v4-flash", "text": "…"},
             {"round": 3, "phase": "synthesis", "model": "claude-opus-5", "text": "…"}]
```

A Claude `redacted_thinking` block becomes the same shape with `"text": ""` and
`"redacted": true`. Bounds (`lib/mastermind_response_log._clean_thinking`): 6000 chars
per segment, 24 segments per turn. When the cap bites the kept window is the **first 23
plus the last** — a chain of thought frames the conflict up front, but the `synthesis`
segment rides last and *is* the decision this corpus exists to show, so middle tool
rounds are what gets dropped, never the ending.

**Why**: the answer text alone cannot tell you whether the assistant *wrestled* a
genuine contradiction between site signals, or smoothed one over. The reasoning can,
and it separates the two causes the operator needs to tell apart — **our data being
wrong** (system error) versus **the market being honestly split** (divergence).

Both lanes think: DeepSeek v4 reasons by default, and the Pro Claude lane runs
`thinking: adaptive`. Capture happens in `engine/neuralweb/brain_gateway.py`:
`_thinking_segments()` reads the `thinking` / `redacted_thinking` blocks out of each
Phase-1 `resp.content` (phase `tool`) and out of Phase 2's
`stream.get_final_message().content` (phase `synthesis`), and
`_run_brain_loop_stream` hands the trace back through a `thinking_out` side channel
next to `usage_out`/`answer_out`. A synthesis candidate that fails over discards its
reasoning with its buffer, so the log only ever holds the reasoning behind the answer
that actually shipped.

> **LEAK LAW — thinking is LOG-ONLY.** No SSE event carries it and no yielded string may
> contain it. This gateway serves paying users' widgets; the model's private reasoning is
> not product copy. `tests/test_brain_gateway.py::test_thinking_never_reaches_the_sse_wire`
> joins every event of a full stream run and asserts the text appears in none of them.
> Adding a "show reasoning" feature would be a new, deliberate product decision — not a
> side effect of this capture.

The gateway's system prompt also carries a **CONTRADICTORY SIGNALS** block in every mode
(`_CONTRADICTION_DIRECTIVE`, pinned by a test): check the calibrated contradiction tools
first, name the conflict plainly, **never overrule the desk** (the model may not pick
which reading is right, nor tell a user our data is wrong — the only permitted move is
*down*, to lower conviction / "unresolved"), and prefer "watch — don't chase" over a
forced call. The first draft told the model to judge staleness and "lean on the fresher"
reading; that originates a ranking the model may never invent (MNZ-R5) and was removed
2026-07-26 — a regression test pins the phrase as absent.

## Configuration

Logging is **ON** whenever a sink is configured and it is not explicitly disabled.

| env var | where | effect |
|---|---|---|
| `R2_ENDPOINT` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_BUCKET` | macro-api VPS (`/etc/macro-api.env`), admin/Mac | the R2 sink. **NOT implied by other R2 lanes** — `R2_RESEARCH_*` on the VPS does not satisfy this; the logger gates on the four **plain** `R2_*` names exactly (`lib.mastermind_response_log.enabled()`) |
| `MASTERMIND_RESPONSE_LOG_DISABLED` | any | truthy → hard-off (kill switch) |
| `MASTERMIND_RESPONSE_LOG_LOCAL_DIR` | any | optional local mirror dir (tests / VPS durability fallback) |
| `DEEPSEEK_API_KEY` | **admin host only** (`/etc/macro-admin.env`, or the local `.env`) | powers **⚡ Classify conflicts (LLM)**. Absent → the button answers `{"ok": false, "error": "no_llm_key"}` and the tab shows a non-blocking notice; the free ⚡ keyword scan is unaffected. The classifier calls `https://api.deepseek.com/anthropic/v1/messages` directly with `urllib` (no SDK in the admin venv), model `deepseek-v4-flash`, thinking disabled, 400 max tokens per row |

No new cron is required: the brain gateway PUTs to R2 directly (once
`/etc/macro-api.env` carries the plain `R2_*` keys — see above; a restart of
`macro-api` is needed after editing the env file). The admin pulls on demand (the
**Refresh from R2** button) — or wire
a periodic `refresh()` later. Because both surfaces proxy through this one gateway,
there is nothing to configure on the charting-app/Terminal side.

## Operating the admin view

Admin → **Neural Web → AI Response Logs**:

- **Refresh from R2** — pull new answers into the local ledger (idempotent; dedup by id).
- **Filter** — surface, lane, model, graded/ungraded, 👍/👎, flagged, errors, free-text
  search, plus **🧠 thinking** (rows carrying a reasoning trace), **⚡ conflicts** (rows the
  deterministic scan hits), and a **verdict** dropdown (the LLM's contradiction label).
- **Row** — click to expand the full question, answer, and metadata (provider, latency,
  tokens, hashed user, thread, page/symbol), plus a collapsed **🧠 Thinking (n segments ·
  m chars)** section rendering each segment as `[phase · round n · model]`.
  The list response carries only the trace's SIZE (`thinking_meta`); the trace itself is
  fetched on first expand from
  `GET /api/mastermind_ai/response_logs/thinking?id=<id>` (→ `mastermind_logs.thinking_trace`)
  and cached on the row until the next reload. A single trace can run to ~144k chars, so
  300 of them in one list payload is the load the lazy fetch exists to avoid.
  **Export is the exception and keeps the full trace** — it is operator-triggered and capped.
- **Grade** — 1–5 + 👍/👎 + ⚑ flag + tags + note → **Save verdict** (writes the sidecar).
- **Classify conflicts (LLM)** — see below.
- **Export** — JSONL (full rows + eval + `thinking` + the scan) or CSV (flattened, with
  `thinking_chars` / `contra_hit` / `contra_verdict`) of the current filter, for
  batch evaluation / training-set curation in external tooling.

## Contradiction assessment (the two tiers)

**Tier 1 — deterministic, free, always on. A TRIAGE hint, not a detector.**
`_scan_contradiction` greps the answer AND every thinking segment for conflict stems (EN:
contradict, conflict, inconsisten, disagree, diverg, at odds, mixed signals, tension
between, opposite direction; ZH: 矛盾, 冲突, 不一致, 分歧, 相悖) and puts
`contra: {hit, terms, src}` on the row. It runs at **read time and is never stored**, so
widening the pattern list re-scores the whole existing corpus.

`src` (`answer` | `thinking` | `both`) says **where the wording appeared, and nothing
more**. A `thinking`-only hit is a row worth OPENING — it is not evidence that the model
worked a conflict out privately and shipped a smooth answer. Substring stems over free
text have loud failure modes in both directions:

- **False positives** — TA vocabulary (`MACD divergence`, `bullish divergence`), negated
  mentions (`there is no conflict between them`, `these do not disagree`), and the
  contradiction doctrine's own vocabulary echoed back out of the system prompt (the model
  reasoning "the doctrine says name any conflict" trips `conflict` with no conflict present).
- **False negatives** — a genuine contradiction described without a stem word ("breadth
  says risk-on, credit says the opposite" — no listed stem in ZH or EN form) scores clean.

So `n_contra` and the **⚡ n candidates (keyword triage)** pill are a **candidate count,
not a contradiction rate**, and neither number belongs in a claim about how often the
assistant hits conflicts. The discriminators are the **Tier-2 LLM verdict** and, finally,
the **operator reading the trace**.

**Tier 2 — LLM verdict, on demand.** **⚡ Classify conflicts (LLM)** takes up to 20
un-verdicted candidates (scan hit *or* any reasoning present), newest first, and labels
each `none` / `system_error` / `market_divergence` / `unclear` with the conflicting
signal names and a one-line note. The tab reports
`classified n / skipped m of N candidates` — **N is the count before the batch limit**,
i.e. how much work is left, so press again to continue. Only one batch runs at a time per
admin process: a second click or a second tab gets `{"ok": false, "error": "busy"}` and a
"batch already running" notice rather than a second bill for the same rows.

```bash
curl -s -XPOST localhost:8799/api/mastermind_ai/response_logs/classify \
     -d '{"limit": 20}' | python -m json.tool
```

Rows are skipped (counted, never fatal) on a network error; an unparseable reply is
recorded as `unclear` / `"unparseable"` so it is not re-billed on the next pass. Repeat
runs are additive — a row that already has a `contra_verdict` is never re-classified,
so clearing a verdict means editing the sidecar.

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

- `thinking` is the model's private reasoning about a real user's question. It is stored
  exactly like the answer (hashed `user_ref`, gitignored ledger, same R2 prefix) and is
  **never** shown to the user — see the leak law above.
- **Two operator actions send this material off the box, and both are deliberate:**
  1. **Export** (JSONL/CSV download) — the file lands wherever the operator puts it.
  2. **⚡ Classify conflicts (LLM)** — this is the non-obvious one. Each candidate row's
     **question (≤600 chars), answer (≤1600 chars), and thinking excerpts (≤~1800 chars,
     whatever the 4000-char budget leaves)** are POSTed to **DeepSeek's API**
     (`api.deepseek.com`) — **including rows whose turn was served by Claude**, since the
     classifier is one fixed small model regardless of which lane produced the answer.
     Pressing that button is therefore an explicit decision to share those excerpts, and
     the real user questions inside them, with a third-party provider. It is never
     automatic: nothing is sent on page load, on refresh, or on a filter change.
     Without `DEEPSEEK_API_KEY` set for the admin process, nothing ever leaves — the
     button answers `{"ok": false, "error": "no_llm_key"}` before reading a single row,
     and the free ⚡ keyword triage keeps working.
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
# Unit + admin route contract + thinking capture / leak law / doctrine pin
python -m pytest tests/test_mastermind_response_log.py tests/test_admin_mastermind_logs.py \
                tests/test_brain_gateway.py tests/test_brain_doctrine.py -q

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
