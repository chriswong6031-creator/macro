# feat(brain): live reasoning timeline + Fast/Pro latency overhaul

Operator order: show users how Fast/Pro is assessing their question while they wait
(without leaking proprietary signal internals), and cut the response wait itself.

## What users see now
While the answer is being produced, the chat bubble shows a live, bilingual reasoning
timeline — "Reading your question → Loading today's market state → Checking AAPL's track
record ✓ → Analyzing in depth → Writing your answer · ~180 words → Final quality check" —
with a running m:ss timer, collapsing to a quiet "Analyzed for Ns · k checks" chip (click
to expand the steps) when the answer lands. Works on both surfaces (Macro widget +
Terminal — the Terminal loads mm_brain.js from this site).

Leak-safety: every visible string comes from two hardcoded whitelists (stage labels + a
53-tool label map, EN/ZH); the only dynamic field is the sanitized ticker symbol. No tool
params/results, no model/provider names, no thinking text, no prompt/digest text ever
reaches the wire. This REMOVES an existing leak: the old widget printed raw internal tool
names ("Reading read_world_state…") to users.

## Why it was slow (measured)
1. **Pro walked 5 weekly-capped OAuth keys at ~2.4s each (SDK max_retries=2 re-tries dead
   keys) for EVERY model round + synthesis** — 25–31s of pure dead air per turn in the VPS
   journal (Jul 26 01:58/02:50/02:53 bursts), before DeepSeek even started.
2. **DeepSeek v4 models think silently by default** — probe: v4-pro 3.68s to first output
   on a one-liner vs v4-flash 1.45s; `thinking:{"type":"disabled"}` is accepted and cut
   probes to ~1.1s with ~4× fewer output tokens.
3. **Live guest Fast turn: 29.5s end-to-end**, of which 26s total silence (answer is
   buffered by the advice-filter law — unchanged — but nothing narrated the wait).
4. No prompt caching on multi-round turns (probe: OAuth claude 2nd call 1.56s→0.75s).
5. SDK default 600s timeout let a hung candidate stall a turn for minutes.

## Fixes
- `client_max_retries: 0` + `client_timeout_s` (fast 120 / pro 240) on brain-lane clients
  only (config/brain.yml → llm_auth.build_providers; all other consumers byte-identical).
  A dead-key probe drops 4.23s → 0.49s.
- Cooled-key skip-ahead: when the OAuth pool is rate-capped, ONE opus probe stays first
  and the other cooled opus rungs move behind the degraded models (fail-open: still tried
  last). Fully-capped Pro now reaches its serving model in ~0.5s instead of 25–31s.
- Fast lane → `deepseek-v4-flash` + `deepseek_thinking: disabled` (the lane is named
  Fast; flash is the speed tier). Pro's degraded v4-pro rung KEEPS thinking (quality
  backstop while the opus pool is capped). One-line revert if answer quality dips.
- Prompt caching (`cache_control`) on system + tools for every candidate (probed safe on
  OAuth claude AND DeepSeek compat) — cheaper + faster rounds 2+.
- `status` SSE events narrate every stage (additive contract; old cached widgets ignore
  them; cursor-safe under #3574's run registry — only generator-emitted events, keepalive
  comments untouched).

## Expected after deploy
- Fast: ~29s → **roughly 6–12s** typical, with live narration throughout.
- Pro (pool still capped): ~45–70s → **roughly 20–30s** (v4-pro w/ thinking serves), honest
  "Analyzing in depth" narration. NOTE: real Opus-5 service for Pro still requires operator
  action — a metered ANTHROPIC_API_KEY on the VPS or Max-tier subs (standing decision from
  2026-07-25); this PR cannot un-cap the subscription pool.

## Verification
- (attach) widget harness screenshots EN/ZH + timed live SSE probe before/after.
- Full brain suites green; template↔site sync check green.
