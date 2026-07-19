# Earnings-call qualitative worker (Windows PC)

Standalone worker that scores earnings calls with a **local Qwen** model on the
operator's Windows PC and publishes the results to Cloudflare R2. Part of the
Stage Analysis program (SGA W4, rulings **SGA-R5** and **SGA-R6**).

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

1. Pick tickers — from `--tickers`, from the upcoming-earnings priority queue
   (`--queue` → `data/earnings_calls/queue.json`), or `--auto` (everything
   un-scored in the transcripts dir).
2. Load each ticker's transcript text from `--transcripts-dir` (one JSON per
   filing: `{ticker, quarter, year, call_date, text}`).
3. Score it with `engine.earnings_qual.score_text` against your **local**
   OpenAI-compatible endpoint (Qwen).
4. Upsert rows into `data/earnings_calls/scores.parquet` (atomic write, keyed
   `(ticker, quarter, year, source)`, never rescores the same `source_sha256`).
5. Publish `scores.parquet` + a small `manifest.json` to R2.

`~7 calls/day rolling` covers the full US earnings cadence (~2,552 names/yr). The
config daily cap is `8`.

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

# 3. Point the worker at your transcript store (one JSON per filing).
#    Schema per file: {"ticker","quarter","year","call_date","text"}
mkdir D:\earnings\transcripts
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

---

## Running it

```powershell
# score a specific set, against LM Studio's default port:
python run_worker.py --tickers NVDA,AAPL,MSFT ^
  --transcripts-dir D:\earnings\transcripts ^
  --base-url http://localhost:1234/v1 --model qwen3-14b

# score whatever is un-scored (bounded by the daily cap of 8):
python run_worker.py --auto --transcripts-dir D:\earnings\transcripts

# use the upcoming-earnings priority queue (data/earnings_calls/queue.json):
python run_worker.py --queue --limit 8 --transcripts-dir D:\earnings\transcripts

# local dry test — score but do NOT publish to R2:
python run_worker.py --tickers NVDA --transcripts-dir D:\earnings\transcripts --no-publish
```

The worker always forces the **local** endpoint first on the PC lane; it never
calls a cloud model from the PC.

### Transcript file format

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

The transcript-vendor decision (Finnhub paid / FMP / EDGAR-only) is deferred to
W6. Until a vendor is wired, you can drop 8-K Item-2.02 press-release text into
these files (set the same schema) and the worker scores it identically; the Mac's
cold-start lane can also pull 8-K text automatically
(`python -m engine.earnings_qual --source 8k`).

---

## Scheduling (Task Scheduler)

Run once a day (e.g. 18:30, after the US close, before the Mac's nightly). Create
a Basic Task → Daily → *Start a program*:

- **Program:** `C:\macro-dashboard\tools\earnings_worker\.venv\Scripts\python.exe`
- **Arguments:** `run_worker.py --queue --limit 8 --transcripts-dir D:\earnings\transcripts`
- **Start in:** `C:\macro-dashboard\tools\earnings_worker`

Equivalent `schtasks` one-liner (PowerShell, adjust paths):

```powershell
schtasks /Create /TN "EarningsQualWorker" /SC DAILY /ST 18:30 ^
  /TR "C:\macro-dashboard\tools\earnings_worker\.venv\Scripts\python.exe C:\macro-dashboard\tools\earnings_worker\run_worker.py --queue --limit 8 --transcripts-dir D:\earnings\transcripts"
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
- **Duplicate work** — the store dedups on `source_sha256`; re-running is safe and
  cheap (already-scored text is skipped).
- **Nothing scored** — no transcript matched your `--tickers`, or everything is
  already scored. Check `--transcripts-dir` and the file `ticker` fields.
