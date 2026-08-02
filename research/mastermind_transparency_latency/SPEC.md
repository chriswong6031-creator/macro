# Mastermind Fast/Pro — reasoning transparency + latency overhaul (SPEC, pinned)

Operator order 2026-07-26: (1) show users how Fast/Pro is thinking/assessing their question
while they wait, WITHOUT leaking proprietary signal internals; (2) cut the response wait —
diagnosed causes below. One PR, Macro Dashboard repo only (the Terminal loads
`https://www.mastermind-x.com/mm_brain.js`, so both surfaces update from here).

## §0 ACCEPTANCE GATES (not done unless)

1. `python3 -m pytest tests/test_brain_gateway.py tests/test_brain_sse_keepalive.py
   tests/test_llm_auth.py tests/test_brain_guest.py tests/test_brain_threads.py
   tests/test_brain_internals_allowlist.py tests/test_brain_unlimited_quota.py
   tests/test_ask_brain.py tests/test_brain_doctrine.py -q` → green, including NEW tests
   for every behavior in this spec (status-event sequence, retry/timeout plumbing, cooled-key
   reordering, deepseek thinking-disable gating, cache_control placement, keepalive beat).
2. SSE contract stays backward-compatible: meta first, done last, `delta` still the single
   buffered full answer AFTER the advice filter (the filter law is untouchable), `tool`
   events keep their `name` field. New `status` events are ADDITIVE only.
3. Leak-safety: every user-visible string in new events comes from the hardcoded whitelists
   in this spec. NO raw tool params (except sanitized symbol/timeframe), NO tool results, NO
   model/provider names (debrand law), NO thinking text, NO system-prompt/digest text on the
   wire. Grep-proof: new event emission sites only reference `_TOOL_LABELS` /
   `_STAGE_LABELS` constants + `_safe_symbol()`-cleaned detail.
4. `templates/mm_brain.js` and `site/mm_brain.js` byte-identical
   (`python -m scripts.check_template_site_sync --fix`).
5. Old cached widget + new server: unknown `status` events are ignored by the deployed
   widget (verified — its dispatcher has no catch-all error branch); new widget + old server:
   timeline degrades to the current dots + generic labels with a live timer. Neither breaks.
6. No new blocking work on the SSE wire: status emission must never call the network or
   read files beyond what the loop already does.

## A. Diagnosed latency causes (evidence)

1. **Pro 429 walk (25–31s/turn measured in `journalctl -u macro-api`)**: all 5 OAuth keys are
   weekly-capped on opus/sonnet (429), each candidate costs ~2.2–2.6s because the SDK's
   default `max_retries=2` re-tries the SAME dead key with backoff (probe: 4.23s default vs
   0.49s with `max_retries=0`); the walk repeats for EVERY tool round + synthesis.
2. **DeepSeek v4 models think by default** (content[0] is a ThinkingBlock): v4-pro TTFT 3.68s
   vs v4-flash 1.45s on a one-liner; `thinking={"type":"disabled"}` IS accepted by the
   Anthropic-compat endpoint (probed: flash 2.55s→1.15s, v4-pro →1.05s) and cuts output
   tokens ~4×.
3. **Zero perceived progress**: the answer is buffered server-side (advice-filter law) and
   the widget shows bouncing dots + raw tool names only.
4. Prompt caching absent: `cache_control` works over the OAuth pool (probe: 2nd call
   1.56s→0.75s) and DeepSeek tolerates it (list-form system + cache_control accepted).
5. SDK default timeout 600s → a hung candidate can stall a turn ~10min.

## B. Backend changes (builder-backend)

Files: `engine/neuralweb/brain_gateway.py`, `engine/llm_auth.py`, `app/main.py`,
`config/brain.yml`, tests.

### B1. Client construction (engine/llm_auth.py `build_providers`)
- New optional cfg keys, threaded to ALL three client constructors (oauth, anthropic,
  deepseek): `client_max_retries` (int|None → SDK default when None) and
  `client_timeout_s` (float|None → SDK default when None; pass
  `timeout=httpx.Timeout(<v>, connect=5.0)`; plain float fallback acceptable if httpx
  unavailable in a stubbed test env — guard with try/except like the existing hook code).
- Default behavior for every existing consumer is UNCHANGED (both keys absent → identical
  clients as today). Only config/brain.yml lanes opt in.

### B2. config/brain.yml
```yaml
fast:
  deepseek_model: deepseek-v4-flash    # speed tier; v4-pro stays Pro's degraded rung
  deepseek_thinking: disabled          # v4 thinks by default; Fast answers directly
  client_max_retries: 0                # the failover chain IS the retry
  client_timeout_s: 120
pro:
  client_max_retries: 0
  client_timeout_s: 240                # long adaptive-thinking answers still fit
  # NOTE: pro's degraded deepseek-v4-pro rung keeps thinking ENABLED (quality backstop);
  # do NOT set deepseek_thinking on the pro lane.
```
Keep comments in the file explaining each (MNZ-R12 config-not-literals). Loader fallbacks in
`_load_brain_config` untouched.

### B3. Cooled-key skip-ahead (brain_gateway `_build_lane_providers`, pro branch only)
After assembling the full pro chain (oauth opus rungs + optional anthropic + degraded rungs):
partition the OPUS-model oauth rungs (model == lane opus_model AND name == "oauth") by
`engine.neuralweb.key_pool.is_cooling(cap_id)`. Keep all non-cooling rungs in place; keep the
FIRST cooling rung in place as a probe; MOVE the remaining cooling opus rungs to the very END
of the chain (after degraded rungs). Wrap in try/except → on ANY error keep the original
order (fail-open). Haiku degraded rungs reuse the same cap_ids but are NEVER reordered (they
work while opus is capped — cooling is keyed per-key, not per-model). Net effect: fully
capped pool = ONE fast 429 probe (~0.5s with max_retries=0) → DeepSeek serves; healthy pool =
unchanged order.

### B4. DeepSeek thinking gate (brain_gateway)
New helper `_deepseek_extra_params(model: str, deepseek_thinking: str|None) -> dict`:
returns `{"thinking": {"type": "disabled"}}` ONLY when model startswith "deepseek" and
deepseek_thinking == "disabled", else {}. Thread `deepseek_thinking` from lane_cfg through
`chat()` and `chat_stream()` into both loops' per-candidate kwargs (`_pmk`) so it merges the
same way effort/thinking do for Claude (and is NEVER sent to claude-* models). Research mode
inherits pro (no key → thinking stays on).

### B5. Prompt caching (both loops)
Where `system=system_prompt` and `tools=tool_schemas` are passed today, pass
`system=[{"type":"text","text":system_prompt,"cache_control":{"type":"ephemeral"}}]` and a
deep-copied tools list whose LAST tool dict carries `"cache_control":{"type":"ephemeral"}`.
Apply uniformly to Phase-1 creates AND Phase-2 stream (probed safe on OAuth claude + DeepSeek
compat). Build these ONCE per loop invocation (no per-round rebuild). Do not mutate the
module-level schema constants (deepcopy or shallow-copy list + copy of last dict).

### B6. `status` SSE events (brain_gateway `_run_brain_loop_stream` only; non-stream chat()
contract unchanged)
Event shape (ADDITIVE to existing contract; `detail` optional):
```json
{"type":"status","phase":"<phase>","label_en":"...","label_zh":"...","detail":"AAPL",
 "elapsed_ms":1234,"n":2}
```
`elapsed_ms` = ms since loop start (loop-local monotonic t0). Emission points, in order:
1. right after the meta yield: phase `start`;
2. after the grounding digest is attached: phase `grounding` (skip when digest empty);
3. immediately BEFORE each Phase-1 `_create_failover` call: phase `model`, `n`=round number
   (1-based); label varies by lane (see _STAGE_LABELS) and for n>=2 bakes the pass count
   into label_en/label_zh (e.g. "Analyzing in depth · pass 2" / "深度分析中 · 第 2 轮");
4. existing `tool` events GAIN `label_en`, `label_zh`, `detail` (sanitized symbol from
   params.symbol/params.ticker via `_safe_symbol`, uppercased; else omit) — `name` field
   stays for the old widget;
5. before Phase-2 synthesis stream opens: phase `synthesis`;
6. DURING Phase-2 text accumulation, throttled to >=1.5s apart: phase `writing`,
   `n`=len(full_answer) (chars; the widget renders a word estimate) — same label as
   synthesis; emit only when at least one chunk arrived since the last one;
7. after the stream closes, before the advice filter + delta: phase `review`.
No status events on the early-return paths (sanitize error, quota, prescreen, no-providers)
— those already emit immediate meta+done.

`_STAGE_LABELS` (hardcoded dict, exact copy):
- start:      EN "Reading your question"            ZH "正在理解您的问题"
- grounding:  EN "Loading today's market state"     ZH "载入今日市场状态"
- model.fast: EN "Working out the answer"           ZH "推理中"
- model.pro:  EN "Analyzing in depth"               ZH "深度分析中"
- synthesis/writing: EN "Writing your answer"       ZH "撰写回答中"
- review:     EN "Final quality check"              ZH "最终质量核查"

`_TOOL_LABELS` (hardcoded; fallback for unknown names EN "Gathering data" ZH "整理数据"):
get_quote "Fetching the latest quote"/"获取最新行情"; get_symbol_intel "Checking the current
read"/"查看最新解读"; get_symbol_backtest "Reviewing the track record"/"回顾历史表现";
screen_universe "Screening the market"/"筛选市场"; get_fundamentals "Reading the
financials"/"查阅财务数据"; get_earnings "Checking earnings"/"查看财报";
get_insider_activity "Checking insider activity"/"查看内部人交易"; get_congress_trades
"Checking congressional trades"/"查看国会交易记录"; get_smart_money "Following institutional
money"/"追踪机构资金"; get_stage_peers "Comparing similar stocks"/"对比同类股票"; get_movers
"Scanning today's movers"/"扫描今日异动"; get_house_view "Consulting the house view"/"查询本
站观点"; get_watchlist "Reading your watchlist"/"读取您的自选列表"; get_portfolio_brief
"Reviewing your portfolio"/"查看您的组合"; render_inline_chart "Drawing a chart"/"绘制图表";
annotate_chart "Marking key levels"/"标记关键位置"; chart_digest "Reading your chart"/"读取您
的图表"; read_chart_state "Reading your chart"/"读取您的图表"; measure_line "Measuring chart
levels"/"测量图表位置"; set_chart_symbol "Switching the chart"/"切换图表";
set_chart_timeframe "Adjusting the timeframe"/"调整周期"; toggle_chart_indicator "Updating
indicators"/"更新指标"; run_chart_detection "Scanning chart patterns"/"扫描图表形态";
emit_chart_command "Drawing on your chart"/"在图表上标注"; context_search "Searching the
research library"/"检索研究库"; context_open "Opening research notes"/"查阅研究笔记";
read_world_state "Reading the world dashboard"/"读取全球市场概览"; read_options_entry_state
"Checking options positioning"/"查看期权布局"; explain_options_context "Explaining the
options setup"/"解读期权背景"; query_options_confluence "Cross-checking options signals"/
"交叉核对期权信号"; list_options_contradictions "Checking for conflicting options reads"/
"排查期权矛盾信号"; query_spine "Cross-referencing market drivers"/"交叉核对市场驱动";
read_kernel "Consulting the market map"/"查询市场关联图"; read_graph "Tracing market
connections"/"梳理市场关联"; read_contradictions "Weighing conflicting evidence"/"权衡矛盾
证据"; read_governance "Checking data quality gates"/"核查数据质量"; read_artifact "Opening
a research note"/"查阅研究记录"; read_factor_state "Checking factor conditions"/"查看因子状
态"; list_factor_contradictions "Checking for factor conflicts"/"排查因子矛盾";
explain_factor_context "Explaining factor context"/"解读因子背景"; read_cycle_pattern_state
"Reading the market cycle"/"读取市场周期"; read_mechanism_pathways "Tracing cause and
effect"/"梳理因果路径"; read_theme_state "Checking the theme dashboard"/"查看主题面板";
read_theme_thesis "Reading the theme thesis"/"读取主题论点"; read_theme_pathways "Tracing
theme linkages"/"梳理主题关联"; read_theme_asymmetry "Weighing theme risk/reward"/"权衡主题
风险收益"; read_theme_options_witness "Checking options confirmation"/"查看期权佐证";
read_theme_clinical "Reviewing theme checkpoints"/"审视主题检查点"; read_theme_trade_flows
"Tracking theme trade flows"/"追踪主题资金流"; read_liquidity_plumbing "Checking market
liquidity"/"查看市场流动性"; read_china_decision_packet "Reading the China desk brief"/
"读取中国市场简报"; read_special_situations "Scanning special situations"/"扫描特殊机会";
read_stage_analysis "Checking the stage analysis"/"查看阶段分析".
(53 total tools exist — `_all_brain_tool_schemas(root, page='terminal',
internals_allowed=True)` is the authoritative enumeration; every name there MUST have a
whitelist entry, and a unit test must assert full coverage so a future tool cannot ship
label-less. The raw snake_case names currently shown to users are themselves an internal-
naming leak this change removes.)

### B7. Keepalive — REVISED after PR #3574 landed (run-registry rebase)
PR #3574 replaces `_sse_keepalive` with `app/brain_runs.py` (server-side run registry:
generator pumped into an ordered buffer; clients re-attach with a CURSOR counting buffered
events; `brain_runs.follow()` emits `: keepalive` comments during dead air). Cursor law:
every `data:` event a client parses bumps its cursor (`handleEvent` returns true for all
types except `run`), so ONLY generator-emitted (buffered) events may ride as data events.
A follow-side visible "beat" would desync cached widgets by one per beat → **beats are
DROPPED. Keep `: keepalive` comments exactly as brain_runs ships them.** The widget's
elapsed timer is client-side. Generator-emitted `status` events are buffered like any
other event and replay correctly on re-attach — no cursor concern.

## C. Widget changes (builder-widget)

Files: `templates/mm_brain.js` + `site/mm_brain.js` (byte-identical pair). House idioms:
`L(en, zh)` for copy, existing CSS custom props (--mmb-info, --mmb-muted, --mmb-font),
`el(tag, cls)`, reduced-motion block at the top of the stylesheet.

### C1. Reasoning timeline (replaces the bare 3-dot bubble content while streaming)
- Same assistant-bubble shell (orb mark stays). Inside: a `.mmb-think` block:
  - header line: current-stage label (from latest `status`/`tool` event; before any event:
    L('Reading your question','正在理解您的问题')) + right-aligned live elapsed `0:07`
    (client interval, 1s tick, starts at send).
  - below: up to the 3 most recent completed step lines, dimmed, each prefixed by a small ✓
    (CSS ::before, no new assets); the current step keeps the existing pulse-dot idiom
    (borrow `.mmb-tool::before`). Older steps beyond 3 drop off (remove node).
- Event handling additions to the SSE dispatcher:
  - `status`: phase `beat` → no visual change (timer is client-side; optionally a one-frame
    opacity pulse on the header). Any other phase → push the previous current step into the
    done list, set header label to `L(label_en, label_zh)`; phase `writing` with `n` →
    header shows label + ' · ~' + estimate, where estimate = zh() ? (n + ' 字') :
    (Math.max(1, Math.round(n/6)) + ' words').
  - `tool`: prefer `label_en`/`label_zh` (+ ` · ` + detail when present); when absent (old
    server), show L('Reading market data','读取市场数据') — NEVER the raw `name` in the
    timeline. Tool steps append to the step list like stages.
  - Ignore status events after done (guard on doneSeen).
- On first `delta`: collapse the timeline into a single muted summary chip rendered ABOVE
  the answer text inside the bubble: L('Analyzed for {t}s · {k} checks',
  '分析 {t} 秒 · {k} 项核查') where t = whole seconds since send, k = tool-step count (omit
  the ' · …checks' part when k=0). Clicking the chip toggles the full recorded step list
  (small dimmed lines, static). The chip must NOT interfere with MdStream text streaming
  (insert as a sibling node before the .mmb-txt target, mirroring how `steps` works today).
- Stop button / error card / abort paths: remove the timeline node the same places `steps`
  is removed today; on stop keep the summary chip if a delta already arrived, else nothing.
- Reduced motion: no pulse/opacity animation (extend the existing media block).
- Keep total added CSS ≲ 45 lines, matching the widget's compact visual voice (12px,
  muted, calm — no spinners, no progress bars, no percentage fakery).

### C2. Back-compat
Old server (no status events): the header shows the pre-event default label with the live
timer, tool events show the generic label — strictly better than today's dots. No layout
shift when the answer lands (chip + text occupy the same bubble).

## D. Explicitly OUT of scope
- The advice-filter/buffered-delta law stays (no token streaming to the client).
- Supabase thread-store round-trips (~0.3–0.6s) — separate ticket if ever needed.
- Restoring real Opus-5 capacity on Pro (operator-level: metered ANTHROPIC_API_KEY in
  /etc/macro-api.env or Max-tier subs — see mastermind-pro-opus5-intensity memory). This PR
  makes Pro fast + honest while capped, it cannot un-cap the pool.
- Cross-provider ThinkingBlock-in-history edge (pre-existing, rare).

---

## §E AMENDMENT 2026-08-01 — Contract S supersedes the buffered single delta (W5)

Operator order 2026-08-01 (latency wave; Deepvue teardown docket
`research/DEEPVUE_COMPETITIVE_TEARDOWN_AND_MASTERMIND_BUILD_DOCKET_2026-08-01.md`
§6.6 "Mastermind's latency cause" and §6.8 "Exact Mastermind latency path").
**§D bullet 1 and the `delta` clause of §0 gate 2 are SUPERSEDED. The historical
sections above are left exactly as written — they record what shipped in July, not what
ships now.**

### What changed

`_run_brain_loop_stream` Phase 2 now emits display text AS IT IS WRITTEN: one or more
`delta` events instead of exactly one. The SSE sequence becomes

```
meta → status*/tool*/annotate*/command*/chart* → delta+ → retract? → suggest? → done
```

`suggest` and `done` keep their existing shape and position. `delta` keeps its shape
(`{"type":"delta","text":…}`); it is now append-only and may arrive many times — which the
deployed widget already handles, because `MdStream` has been an accumulate-and-drain
incremental renderer since W6. ONE new event type, `retract`
(`{"type":"retract","text":…}`), replaces everything streamed so far with `text` (empty
text = wipe only). It is a generator-emitted, buffered event, so it obeys the §B7 cursor
law like any other data event and replays correctly on re-attach.

### Why the old law no longer holds

§D bullet 1 protected the advice filter: "advice cannot be un-sent once on the wire."
That filter — `ask_brain._post_filter_advice` — has been a documented **no-op
pass-through** since the operator's 2026-07-26 directive allowing direct buy/sell
answers. The law was costing 30–77s of perceived latency (measured live, docket §6.7) to
protect a function that returns its input unchanged.

### What still holds, and how

The leak screen (`_leak_screen` over `_LEAK_SENTINELS`) is real and keeps full authority:

1. **Holdback.** The trailing `_LEAK_HOLDBACK_CHARS` (default 256, floored at the longest
   sentinel) of the accumulated answer is never emitted. A system-prompt echo therefore
   lands inside a window that is still server-side when it is caught.
2. **Per-chunk sentinel sweep.** Every SDK chunk is swept before any flush decision, over
   a window backed up by `_MAX_SENTINEL_LEN - 1` so a sentinel split across two chunks is
   still seen whole (equivalent to re-scanning the full answer, at O(n) not O(n²)). A hit
   stops the stream mid-body, emits `retract` carrying the distill refusal, and marks the
   turn `filtered`.
3. **`[NEXT]` holdback.** A trailing partial line that could still grow into the marker is
   held whole; once a complete `[NEXT]` line lands, display text stops for good and the
   remainder is suggestions material. No marker fragment can reach the wire.
4. **Final full-answer pass, unchanged and still the authority.** Citations → advice
   filter → `_leak_screen` → `_split_suggestions` → `_screen_suggestions` all still run on
   the COMPLETE answer. The streamed prefix is then reconciled against the result: a
   prefix match tops it up with the remaining text, a mismatch retracts and replaces it.
   That is the belt-and-suspenders path for anything the streaming guards missed.
5. **Mid-body provider failure.** A candidate that dies after putting text on screen is
   wiped with an empty `retract` before the next candidate writes a character, so a
   failover can never append one model's sentence to another's.

Config lives in the new `streaming:` block of `config/brain.yml`
(`flush_chars` / `flush_seconds` / `leak_holdback_chars`); an absent block or key takes
the module defaults. §0 gates 1, 3, 4, 5 and 6 are unchanged and still binding — leak
safety in particular is *stricter* here, not looser. Tests: `tests/test_brain_streaming.py`.

Unchanged by this amendment: the non-streaming `chat()`, `/api/ask`, Phase-1 tool rounds,
quota paths, and the `status` contract (the `writing` beat now speaks only in the gaps
where no text is flowing, which is what it always meant).

---

## §F AMENDMENT (W5.1) — the ROUNDS stream too, behind a commitment horizon

§E's closing line "Phase-1 tool rounds [unchanged]" is SUPERSEDED. The post-merge VPS
bench of W5 (PR #4220) measured `ttfv_ms == total_ms` with `n_deltas: 1` on the live
lane — 42.7s buffered on a broad probe, 18.5s native. Cause: Phase-2 synthesis fires
only when the tool budget runs out mid-investigation, and the dominant turn never gets
there. The model writes its final answer INSIDE a tool round, and that round's model
call was the blocking `_create_failover`. W5 streamed the rare path.

### What changed

Every round's model call in `_run_brain_loop_stream` is now a `messages.stream()` over
the same candidate walk (same per-candidate `_pmk`, dead-credential marking, pool
cooling, failover-worthy-errors-only contract), forwarding text through the SAME
machinery Phase 2 uses. That machinery is now ONE object, `_StreamGate` — flush policy,
leak holdback, chunk-overlapped sentinel sweep, `[NEXT]` seal — shared by both paths, so
they cannot fork. Tool_use blocks reach the parallel executor from
`get_final_message()`, which is where the SDK assembles them: same objects, same ids,
same inputs as a blocking `create()`.

### The commitment horizon

A round's text is AMBIGUOUS in a way synthesis text is not: it may be the answer, or a
sentence of narration before a tool call. So a round forwards nothing until it has
written `_STREAM_COMMIT_CHARS` (default 200, overridable as `streaming.commit_chars`)
with no tool_use block open. On the fast lane DeepSeek's "let me check" reasoning rides
thinking blocks, so pre-tool display text is rare and short.

| Case | Wire |
|---|---|
| tool_use before the horizon | nothing shown — byte-identical to pre-W5.1 |
| tool_use in the live message snapshot | display freezes there; nothing shown |
| round ends `end_turn` past the horizon | streamed; the §E reconciliation ships the tail |
| narration crosses the horizon, then tools | ONE empty `retract` wipes it; the tool round proceeds; `filtered` stays FALSE (a wipe is not a screening event) |
| candidate dies mid-round after showing text | empty `retract`, next candidate streams into a clean bubble |
| sentinel caught mid-round | stream abandoned, refusal `retract`, `filtered` TRUE — §E's leak law verbatim |
| one-chunk provider (codex `_Stream`) | never flushes mid-round: one buffered delta, exactly as before |

Safety net: if every candidate's STREAM attempt fails and nothing was shown, the round
retries once through the blocking `_create_failover` before degrading. `stream` + `tools`
is a request shape this loop never sent before; a provider whose compat endpoint rejects
it must not black out the lane (cf. the 2026-07-25 deepseek-chat retirement).

Unchanged: Phase-2 synthesis behaviour, `_run_brain_loop` (non-streaming), the instant
lane, prescreen, quota, and every §0 gate. Tests: `tests/test_brain_streaming.py`.
