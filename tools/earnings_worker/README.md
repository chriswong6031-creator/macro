# Earnings-call qualitative worker (Windows PC)

Standalone worker that polls Mastermind Terminal's committed transcript archive,
scores new or corrected calls, and publishes the qualitative overlay to
Cloudflare R2. The normal route is **local Qwen first**, with optional low-cost
DeepSeek/Kimi/Anthropic fallbacks. Part of the Stage Analysis program (SGA W4,
rulings **SGA-R5** and **SGA-R6**).

It runs **outside** the nightly render pipeline. The Mac Studio's nightly job
never calls the model — it only *fetches* the scores this worker publishes
(`scripts/fetch_earnings_scores.py`).

---

## The one law you must not break — SGA-R6 (single-writer / transport)

> **This worker is producer-only. It writes `data/earnings_calls/scores.parquet`
> locally and publishes it to R2. It NEVER touches git — no `add`, `commit`,
> `push`, or `pull`.** The nightly pipeline is the sole ledger advancer and pulls
> scores from R2.

The runner enforces this by construction: it has no git code path. Do not add
one. If you clone the repo on the PC just to import the harness, that's fine —
just never commit the gitignored `data/earnings_calls/` store, and never let a
scheduled task run `git`.

Also standing (SGA-R5): every score is **context-only** — never a trading signal,
gate, or sizing input. The scorer strips trading verbs (`buy`/`sell`/`short`/
`accumulate`/`add`/`trim`/…) from highlights automatically inside `score_text`.
You cannot bypass that filter from the worker.

---

## What it does each run

1. Fetch the current R2 score generation before writing, preserving the full
   accumulated history on a fresh worker checkout.
2. Read Terminal's `data/tx/index.json` commit marker and merge new/corrected
   `SYM/YYYYQn` bodies into a durable local pending queue.
3. Fetch only queued `.json.gz` bodies and render speaker/role-labelled text
   directly into the scorer—no second transcript copy and no vendor scraping.
4. Preserve both prepared remarks and the Q&A tail inside the bounded model
   context, then route local Qwen → DeepSeek → Kimi → Anthropic as configured.
5. Upsert by stable upstream record id. Provider failures stay pending and can
   never overwrite a healthy score or the committed Stage seed.
6. Attempt R2 publication on every invocation, including an idle run after an
   earlier failed publish.

A 2,000–3,500-name universe implies roughly 22–38 calls/day on average at four
calls per company per year, but earnings-season spikes can be hundreds per day.
The default safety ceiling is 64 attempts per invocation; the durable queue
carries overflow and makes repeated scheduled runs safe.

---

## Hardware / model

- **GPU:** RTX 5070, 12 GB VRAM.
- **Model:** **Qwen3-14B, Q4_K_M** GGUF (~9 GB) — fits fully on the GPU. This is
  the default. Quality-upgrade path (given 64 GB system RAM): **Qwen3-30B-A3B**
  (MoE) with partial CPU offload — slower, higher quality; only if you want it.
- Anything that speaks the **OpenAI Chat Completions** API works: **LM Studio**,
  **llama.cpp** (`llama-server`), or **vLLM**.

### Option A — LM Studio (easiest)

1. Install LM Studio, download **Qwen3-14B-Instruct (Q4_K_M GGUF)**.
2. Set GPU offload to **max** (all layers on GPU — the Q4 14B fits in 12 GB).
3. Start the **Local Server** (Developer tab → Start Server). Default endpoint:
   `http://localhost:1234/v1`. Note the **model id** shown in the server panel.

### Option B — llama.cpp (`llama-server`)

```powershell
# after building/installing llama.cpp with CUDA support:
llama-server ^
  --model "D:\models\Qwen3-14B-Q4_K_M.gguf" ^
  --n-gpu-layers 999 ^
  --ctx-size 16384 ^
  --host 127.0.0.1 --port 8000
```

Endpoint: `http://localhost:8000/v1`, model id: the filename LM/llama reports
(pass whatever the server advertises via `--model` on the worker).

---

## One-time Windows setup

```powershell
# 1. Clone the repo (read-only use — only to import the harness + scripts).
git clone <repo-url> C:\macro-dashboard
cd C:\macro-dashboard\tools\earnings_worker

# 2. Python 3.11+ venv with the two runtime deps the worker needs.
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install pandas pyarrow requests boto3 PyYAML

# 3. No transcript backfill directory is required. The default source is the
#    already-published Terminal archive at app.mastermind-x.com/data/tx.
```

### R2 credentials (the 4 env vars — same quad the Mac Studio uses)

Set these as **User environment variables** (System → Environment Variables) so
scheduled tasks inherit them. Without them, `publish` is a graceful no-op.

| Variable | Purpose |
|---|---|
| `R2_ENDPOINT` | Cloudflare R2 S3 endpoint URL |
| `R2_ACCESS_KEY_ID` | R2 access key id |
| `R2_SECRET_ACCESS_KEY` | R2 secret access key |
| `R2_BUCKET` | R2 bucket name |

Optional endpoint overrides (avoid editing the repo config on the PC):

| Variable | Purpose |
|---|---|
| `EARNINGS_LLM_BASE_URL` | local endpoint, e.g. `http://localhost:1234/v1` |
| `EARNINGS_LLM_MODEL` | local model id, e.g. `qwen3-14b` |
| `LOCAL_LLM_API_KEY` | only if your server requires a bearer token |
| `EARNINGS_PROVIDER_ORDER` | optional waterfall, e.g. `openai_compat,deepseek,kimi,anthropic` |
| `DEEPSEEK_API_KEY` | enables the low-cost DeepSeek fallback |
| `MOONSHOT_API_KEY` | enables the optional Kimi fallback |
| `ANTHROPIC_API_KEY` | enables the last-resort Anthropic fallback |
| `TERMINAL_TX_BASE_URL` | optional Terminal archive override |

---

## Running it

```powershell
# First migration run: score a deliberate recent slice. This requires the
# Terminal index dates extension and persists the forward cursor.
python run_worker.py --terminal-auto --bootstrap-since 2026-07-24 ^
  --base-url http://localhost:1234/v1 --model qwen3-14b

# Every scheduled run after that: discover and score only new/corrected calls.
python run_worker.py --terminal-auto ^
  --base-url http://localhost:1234/v1 --model qwen3-14b

# Zero-touch fallback when the local endpoint is asleep or the queue spikes.
python run_worker.py --terminal-auto ^
  --provider-order openai_compat,deepseek,kimi,anthropic

# Test against a local Terminal archive and keep all writes off R2.
python run_worker.py --terminal-auto --terminal-tx-root D:\terminal\public\data\tx ^
  --bootstrap-since 2026-07-24 --no-publish
```

With no provider override the CLI remains local-only. Cloud models are called
only when explicitly added to `--provider-order` or `EARNINGS_PROVIDER_ORDER`
and their API key is present.

### Legacy flat transcript mode

`D:\earnings\transcripts\NVDA_2026Q1.json`:

```json
{
  "ticker": "NVDA",
  "quarter": "Q1",
  "year": 2026,
  "call_date": "2026-05-28",
  "text": "Operator: Good afternoon ... (full transcript or press release) ..."
}
```

The flat-file `--tickers`/`--queue`/`--auto` modes remain for diagnostics and 8-K
cold starts. They are no longer the production intake path; Terminal is the
canonical transcript source and its stable body id/hash is the idempotency key.

---

## Scheduling (Task Scheduler)

Run after the close and again later in the evening during earnings season. Each
run is idempotent, and the second run drains burst overflow or retries a sleeping
local endpoint. Create a Basic Task → Daily → *Start a program*:

- **Program:** `C:\macro-dashboard\tools\earnings_worker\.venv\Scripts\python.exe`
- **Arguments:** `run_worker.py --terminal-auto --limit 64`
- **Start in:** `C:\macro-dashboard\tools\earnings_worker`

Equivalent `schtasks` one-liner (PowerShell, adjust paths):

```powershell
schtasks /Create /TN "EarningsQualWorker" /SC DAILY /ST 18:30 ^
  /TR "C:\macro-dashboard\tools\earnings_worker\.venv\Scripts\python.exe C:\macro-dashboard\tools\earnings_worker\run_worker.py --terminal-auto --limit 64"
```

Make sure the task **runs whether the user is logged on or not** only if the R2
env vars are set at the **system** level; otherwise run it under your user
account so it inherits your user env vars. The task must **never** run git.

---

## Troubleshooting

- **`openai_compat_error` / connection refused** — the local server isn't up, or
  `--base-url` is wrong. Start LM Studio's server / `llama-server` and re-check.
- **`invalid_json`** — the model returned prose. The harness already retries once
  with a "JSON only" reminder; a persistent failure usually means the context was
  truncated (raise the server `--ctx-size`) or the model is too small — use the
  14B, not a 4B.
- **Publish no-ops silently** — the R2 env quad is missing. Set the 4 variables.
- **Duplicate work** — Terminal's stable record id plus canonical body hash make
  re-running safe; a corrected body automatically re-enters the pending queue.
- **Nothing scored** — the first default Terminal run intentionally seeds a
  forward-only cursor. Use `--bootstrap-since YYYY-MM-DD` on a new state file for
  an explicit bounded catch-up; otherwise an empty queue means it is current.
- **Publish failed once** — leave the local store intact and rerun. Even an idle
  invocation retries R2 publication.
