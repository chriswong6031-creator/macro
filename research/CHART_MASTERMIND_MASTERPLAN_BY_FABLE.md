# Chart Mastermind (CMX) — the Brain inhabits the Terminal chart

**Status:** CHARTERED; W1+W2 dispatched same-day
**Date:** 2026-07-22
**Owner program:** `chart-mastermind` (CMX)
**Operator directive (2026-07-22, verbatim intent):** "Allow for a more robust connection system between Mastermind AI and Terminal chart… different indicators, different timeframes, and drawings and labeling to help map out something. Make this process interactive and actually viewable by the user as it draws… an overlay… shows exactly what the Mastermind AI is thinking in full view… beautifully crafted, animated, and futuristic… how do we shove the world's best technical trader and his knowledge and strategies into Mastermind AI's head."
**Method:** main-loop Fable first-principles design (this doc) → Opus builds per wave → Opus review → Fable adjudication at promotion gates.
**Collision check (2026-07-22):** ACTIVE_BUILD_MAP clean (no in-flight chart-agent/drawing lane); DO_NOT_REBUILD clean (no kills touch this space). tradingview-mcp (github.com/atilaahmettaner/tradingview-mcp) verified 2026-07-22: server-side TA/data tools only — **no chart connection, no drawing, no closed loop**. Nothing to copy; our W6b bus already exceeds it.

---

## 0. Executive ruling — the chart is an instrument, not a puppet

Every external "AI + chart" effort adapts to a chart it does not own (CDP puppeteering of TradingView, or skipping the chart entirely). Their ceiling: brittle selectors, screenshot perception, no state read-back, no visible agency. **We own both ends** — the Brain (server tool-loop, `engine/neuralweb/brain_gateway.py`) and the chart (our Terminal's own canvas + quote-hub + pine worker). Therefore CMX is not UI automation; it is a **typed, bidirectional, replayable chart API** where the human and the AI manipulate the same canvas and the AI's hand is visible, narrated, and measurable.

**Second ruling — "genius technician" is a system property, not a model weight.** Skill decomposes: perception (deterministic code — we own it), doctrine (a written, versioned library), judgment (frontier reasoner — rented), calibration (our ledgers — nobody else has this), discipline (output contract + validators). Consequences:

- **No open-weight fine-tune.** The training set doesn't exist; manufacturing it makes it more valuable as retrieval-context + eval ground truth than as SFT fodder; a tuned open model loses to Opus-class reasoning exactly where technician skill lives (conflict resolution, restraint, composition); weights staleness fights our nightly-updating edge; weights leak — engines/ledgers/doctrine don't. **Revisit conditions** (both must hold): frontier API economics break, AND evals show skills+frontier plateauing below a trained specialist on a named subtask.
- **Lane split is measured, not assumed.** Fast/DeepSeek + doctrine handles protocolized single-shot reads; **Opus owns agentic chart sessions** (long tool loops, restraint, conflict resolution). Fable = design (this lane) and possibly a future premium deep-study mode via the standing gate. The eval bench (W5) arbitrates the split.

## 1. Architecture — five organs + a gym

| Organ | What | Wave |
|---|---|---|
| **Hands** | Chart Bus v2: full typed command vocabulary incl. drawing primitives, AI layer, scenes, undo, acks | W1 |
| **Eyes** | Deterministic structural digests (swings/levels/trendline candidates/gaps/ATR/multi-TF) + chart-state mirror + fit metrics | W2 |
| **Face** | Conductor overlay: docked orb, stepwise animated strokes, intent captions, thinking rail, ghost cursor | W3 |
| **Education** | Technician Doctrine library + fixed reading protocol + output contract, intent-routed loading | W4 |
| **Gym** | Eval bench (deterministic + rubric) + AI-read claims ledger + autopsy feedback → calibrated priors | W5 |
| Later | Lane-split experiments, scene library, multi-chart campaigns, premium deep-study, intraday server-side fit metrics | W6+ |

**The one capability that changes the game: verifiable drawing.** Every AI drawing returns fit metrics (touch count, max deviation in ATRs) computed against the exact rendered series. Drawing becomes plan → act → **measure** → refine. Screenshot-based systems can never close this loop.

## 2. Wire contract v2 (LAW — both repos build to this; shape-pinned by tests on BOTH ends)

The #2982/#2984 lesson (nested-vs-flat `command` break) is standing: the shapes below are the contract; changes require a same-PR update to both repos' shape tests.

### 2.1 Command envelope (gateway → SSE `command` event → widget `CFG.onCommand` → host)

Backward compatible: v1 keys (`{on:true, symbol?, tf?, inds?, detect?}`) remain valid. V2 adds `op`:

```json
{ "on": true, "v": 2, "batch_id": "b_7f3a", "seq": 3,
  "op": "draw.trendline", "id": "ai_tl_1",
  "args": { "symbol": "NVDA", "tf": "1D",
            "p1": {"t": 1721606400, "p": 118.42}, "p2": {"t": 1737244800, "p": 96.10},
            "extend": "right", "style": {"kind": "solid", "width": 2},
            "text": "Rising support" },
  "caption": "Marking the demand shelf under June's range" }
```

**Ops:** `chart.set_symbol` `chart.set_tf` `chart.set_indicators` `chart.set_range` · `draw.trendline` `draw.ray` `draw.hline` `draw.zone` `draw.channel` `draw.fib` `draw.path` `draw.label` `draw.marker` `draw.risk_box` · `scene.begin{title}` `scene.end` · `ai.clear` `ai.undo{n}`.
**Rules:** ids namespaced `ai_*`; AI ops may never mutate `by:"user"` objects; `ai.clear` clears only `by:"ai"`; `caption` = plain text ≤140 chars, rendered as textContent only (W3 consumes; inert until then); per-batch cap 24 ops; total AI objects cap 60 (reject with ack error, never silent-drop); all numbers finite, prices > 0, times sane. Both ends validate (gateway before emit; Terminal zod at the boundary — unknown op → rejected ack, never a crash).

### 2.2 State + acks (Terminal → same-origin proxy → `POST /api/brain/chart/state` on macro-api)

Debounced ≤1/2s on change; auth identical to other brain routes (Terminal proxy injects Bearer; device headers ride with `BRAIN_PROXY_SECRET`).

```json
{ "client": "terminal",
  "session": { "symbol": "NVDA", "tf": "1D",
    "indicators": [{"name": "EMA", "params": {"len": 21}}],
    "visible_range": {"from": 1710000000, "to": 1737244800},
    "capabilities": {"tfs": ["1m","5m","15m","1H","4H","1D","1W"], "indicators": ["EMA","SMA","RSI","MACD","BB","VWAP"]},
    "drawings": [
      {"id": "ai_tl_1", "by": "ai", "op": "draw.trendline", "args": {"p1": {"t":1,"p":1}, "p2": {"t":2,"p":2}},
       "fit": {"touches": 4, "max_dev_atr": 0.31}},
      {"id": "u_3", "by": "user", "op": "draw.hline", "args": {"p": 112.5}} ] },
  "acks": [{"batch_id": "b_7f3a", "seq": 3, "id": "ai_tl_1", "ok": true}] }
```

- **Fit metrics computed Terminal-side on ack** (against the exact rendered series — works on every TF) for trendline/ray/hline/zone: touch count within 0.5×ATR(14) band, max deviation in ATRs. Server-side `measure_line` (W2) covers daily/weekly pre-draw planning; intraday server-side = W6.
- Gateway stores latest session per (user_id, client), TTL ~10 min, in-process store (no DB); agent reads it via the `read_chart_state` tool. `capabilities` kills hallucinated indicator/TF names: the agent must choose from the reported enums.

### 2.3 New brain tools (gateway registry)

`chart_digest(symbol, tf∈{1D,1W}, sections?)` → structural skeleton (§3) · `measure_line(symbol, tf, p1, p2)` → fit verdict · `read_chart_state()` → §2.2 session (Terminal client only; dashboard returns `{connected:false}`) · chart commands emitted through the existing W6b command tool, schema extended to §2.1.

## 3. W2 — Eyes: digest spec (deterministic; LLM interprets, never computes)

From daily bars (reuse the exact read-only loader `_chart_for_chat` uses; **never persist** — MM_DATA_GUARD reader-that-writes class is a known lethal): swing pivots (ZigZag, ATR-scaled threshold) · trend segments from pivots · S/R level clusters (price clustering of pivots; touches + recency + side) · trendline candidates (pivot-pair fits ranked by touches/deviation) · unfilled gaps · ATR/realized-vol context · weekly-resample snapshot for multi-TF. Output: compact typed JSON, calibrated plain-word labels, **no formulas/thresholds in text** (anti-distillation: outputs yes, internals never). Volume profile + divergences = W2b, not W2 (scope discipline).

## 4. W3 — Face (design lane: main-loop Fable / designer-opus; build: Opus)

Conductor overlay (glass vignette, never a modal — chart stays live); docked breathing orb (thinking=breathe, acting=pulse-per-command, done=settle); stepwise application ~400ms pacing with per-op intent captions; **skip → apply instantly** always visible; thinking rail = the *designed tool-loop trace* (intent + finding per step; plain-word law; never raw CoT, never internals), expandable; ghost cursor gliding to the next landing point; AI-layer legend chip ("AI layer · 7 objects", eye toggle, clear); full `prefers-reduced-motion` respect (pacing→instant, strokes→fades). The command queue + pacing hooks are built in W1; W3 animates them.

## 5. W4 — Education: Technician Doctrine library

Modular versioned skill files, intent-routed (never one blob): lenses (structure, trend, S/R, volume character, multi-TF, risk framing) + playbooks (Weinstein **wired to our live stage engine**, base patterns, phase/accumulation reading, liquidity concepts). Each file: definitions → validity conditions → procedure (naming OUR tools: "call `chart_digest`; a trendline claim requires `measure_line` ≥3 touches ≤0.5 ATR") → invalidation → output contract → worked examples. Fixed reading protocol: top-down multi-TF, structure before overlays, every read ends **thesis + invalidation level + what-would-change-my-mind**. Doctrine is written in our own words (no ingested copyrighted text). Fable drafts; Opus reviews; bench (W5) arbitrates iterations.

## 6. W5 — Gym: bench + flywheel

Deterministic tasks (find the swings; is this a valid base per spec; where is invalidation) + rubric-judged blind A/Bs. Every AI chart read logged as a falsifiable claim (thesis, levels, horizon) → Prophet-style autopsy grading → per-setup calibration fed back into doctrine priors. **Framing law:** superhuman breadth + consistency + calibration — never "predicts better than humans"; the word "validated" stays CI-guarded.

## 7. House-law bindings

- **LLM-never-originates:** the agent interprets deterministic digests and calibrated engine outputs; drawings are geometry-verified; AI-read stats ship **display-tier**; any promotion to authority (rank/size/gate) goes through the gauntlet. A null on any doctrine lens never blocks building or accrual.
- **Advice layer intact:** chart reads are research framing with invalidation levels — never personal orders; `_post_filter_advice` continues to govern. **No autotrading, ever** (prohibited category; the bus draws and configures charts — it never touches order flow).
- **Anti-distillation:** new tools return outputs (levels, states, fit metrics), never engine internals, prompts, or file paths; `_prescreen_message`/`_leak_screen` stay in force on chart sessions.
- **PRD-R2:** annotations/labels stay named-states + levels; no fused per-position composite risk numbers.
- **Monetization:** agentic chart sessions are **Pro-gated** (Fast keeps single-shot reads + light commands); unlimited-operator allowlist bypasses as built.
- **Ops:** macro static assets auto-deploy (macro-update); gateway changes need `systemctl restart macro-api`; Terminal ships only via `bash /opt/terminal/terminal-build.sh`. Bilingual EN/ZH; `title=` attributes English-only.

## 8. Gates & kills

- **W1 gate:** shape tests both repos; forged/malformed command → rejected ack (never crash); AI cannot touch user objects (test-pinned); caps enforced.
- **W3 gate:** 390px + reduced-motion pass; skip control; screenshot taste review before merge.
- **W4/W5 gate:** doctrine iterations must show bench lift; two consecutive no-lift iterations → stop iterating prose, rethink structure (add tools/context instead).
- **Kill criteria:** if Terminal-side fit metrics prove unreliable across TFs → fall back to server-side daily-only and re-scope W6; if the state mirror can't stay coherent under concurrent human+AI editing → drop to command-only (no read-back) and redesign before W3 ships.

## 9. Non-goals

No CDP/TradingView puppeteering; no open-weight training (revisit conditions in §0); no order execution of any kind; no intraday server-side fit metrics in v1; no new billing meters in W1 (rides existing lanes/quotas).
