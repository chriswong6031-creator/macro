# Real-Time Earnings / Breaking-Event Fast-Lane Architecture
**Status:** Design document — scaffolded 2026-07-19. Phase-A buildable now; Phase-B requires operator keys + always-on host.**

---

## 1. The problem with scheduled posts for breaking events

The existing Content Studio is **schedule-driven**: a nightly plan runs at a fixed time and publishes posts for the next session. That model is correct for signal posts (a swing setup found at midnight is still valid at 8 AM), but it is **wrong for breaking events**:

- AAPL reports at 16:05 ET. The market-moving information is public at 16:05.
- A scheduled post at 22:00 ET is 6 hours late. Social reach decays fast: the first
  15-30 minutes after a surprise release dominate engagement (algorithm freshness + the
  active-reaction window before everyone has said it).
- A Truth-Social post from a market-moving account is irrelevant by the time the nightly
  plan picks it up.

**The fast-lane is event-driven, not schedule-driven.** Detection → card render → copy →
audit → publish in under ~2 minutes, triggered the moment the event is detected.

---

## 2. Earnings ingestion — how to get numbers within seconds

### 2.1 The problem

Earnings are released via SEC 8-K, the company's investor relations website, and
wire services (GlobeNewswire, BusinessWire, PR Newswire). Data aggregators (Alpha
Vantage, Financial Modeling Prep, Polygon.io, Tiingo, IEX Cloud) propagate the
numbers with a lag that ranges from **~15 seconds** (premium push feeds) to
**~2-5 minutes** (standard polling endpoints).

### 2.2 Options ranked

| # | Method | Latency | Cost | Reliability |
|---|--------|---------|------|-------------|
| A | **Provider webhook / push** (e.g. Polygon.io flatfile push, FMP webhook) | 5-30s | $50-200/mo | Excellent; single integration point |
| B | **Fast-poll a low-latency endpoint** every 15-30s during earnings windows only | 15-60s | Pay-per-call or low-tier API | Good; works with most providers |
| C | **Company IR RSS / 8-K wire** (SEC EDGAR API RSS) | 30-120s (SEC delay) | Free | Lower reliability; sparse actual numbers |
| D | **Scrape IR page** | 60-300s | Free (fragile) | Fragile, ToS risk |

### 2.3 Recommended design: calendar-armed targeted polling

**Key insight from `data/earnings/earnings.parquet`**: we already know _which_ tickers
report on _which_ date and approximately _when_ (pre-market 06:00-09:30 ET, after-hours
16:00-20:00 ET). This lets us arm **targeted, time-windowed polls** rather than
monitoring hundreds of tickers 24/7.

**Algorithm:**

```
Morning (05:50 ET):
  reporters = todays_reporters(root, today=today, when="pre")  # pre-market reporters
  for ticker in reporters:
    arm_poller(ticker, window_start=06:00, window_end=09:35, interval=20s)

Afternoon (15:50 ET):
  reporters = todays_reporters(root, today=today, when="post")  # after-hours reporters
  for ticker in reporters:
    arm_poller(ticker, window_start=16:00, window_end=20:00, interval=20s)
```

- Outside earnings windows: no polling. Zero cost, zero noise.
- During a window, poll the fast endpoint (option B) every 20 seconds for each armed
  ticker only. A universe of 10 tickers reporting after-hours = 10 calls/20s = 30
  calls/minute — well within any provider's rate limits.
- On fresh data detected (actual EPS is non-null / different from yesterday's store):
  fire the fast-lane pipeline immediately.

**Provider recommendation**: Polygon.io (Option A webhook for Phase-B, Option B polling
for Phase-A) or Financial Modeling Prep v3 earnings calendar endpoint. Both return
`eps_actual`, `eps_estimated`, `revenue_actual`, `revenue_estimated` in a single call.

---

## 3. The fast-lane runtime

### 3.1 Architecture

```
                        ┌─────────────────────────────────────────┐
                        │         EARNINGS FAST-LANE DAEMON        │
                        │       (earnings_fastlane.py)             │
                        │                                          │
  earnings.parquet ──►  │  arm_morning_watchers()                  │
                        │  arm_afternoon_watchers()                │
                        │           │                              │
                        │     poll loop (20s interval,             │
                        │     armed tickers only)                  │
                        │           │                              │
                        │     on fresh release detected:           │
                        │     normalize() ──► render_card() ──►   │
                        │     copywriter_placeholder() ──►         │
                        │     auditor_gate() ──► publisher()       │
                        │                                          │
                        └─────────────────────────────────────────┘
```

### 3.2 Pipeline steps and latency budget

| Step | Function | Budget |
|------|----------|--------|
| Detection (poll fires) | `poll_ticker_release(ticker)` | 0-20s (poll interval) |
| Normalization | `normalize_release(raw)` | <0.1s |
| Card render | `render_earnings_card(...)` | <0.5s |
| Copy generation | `write_copy(ticker, facts)` | <5s (LLM call or template) |
| Auditor gate | `auditor.check(post)` | <5s |
| Publisher | `publish(post, svg)` | <3s |
| **Total** | | **<2 min** |

The dominant variable is the poll cycle (0-20s). With a webhook (Option A), this drops
to <5s end-to-end.

### 3.3 Contrast with the nightly Content Studio

| Dimension | Nightly Content Studio | Earnings Fast-Lane |
|-----------|----------------------|--------------------|
| Trigger | Clock (cron, 22:00 ET) | Event (fresh EPS detected) |
| Latency target | "Ready for next open" | <2 minutes after release |
| Data freshness | Stale by design (signals computed on close data) | Real-time: actual EPS is the data |
| Post volume | ~3-5 posts/day (signal-driven) | 0-N per earnings season |
| Copywriter | Full hook model pipeline | Fast path: template + optional LLM |

**The nightly studio must NOT be repurposed for earnings.** A scheduled 22:00 post about
a 16:05 earnings release is 6 hours late and competes with hundreds of already-published
reactions. The fast-lane daemon is a separate process, always available.

---

## 4. General breaking-event watcher spec

The same poll-detect-render-publish pattern applies to other immediate events:

### 4.1 Event types and source polling

| Event type | Poll target | Interval | Sensitivity |
|-----------|-------------|----------|-------------|
| **Earnings release** | Polygon/FMP earnings endpoint | 20s (window-armed) | Normal |
| **Trump Truth-Social** | Truth.Social RSS / RSSHub mirror | 60s | High (political) |
| **NVDA / AAPL press releases** | GlobeNewswire/BusinessWire RSS | 120s | Normal |
| **CENTCOM / DoD** | defense.gov/news RSS | 60s | High (geopolitical) |
| **Fed statements / FOMC** | federalreserve.gov RSS | 60s (FOMC days only) | High |

### 4.2 Relevance filter (critical for noise reduction)

Not every detected event deserves a post. The relevance filter runs before any LLM call:

1. **Keyword gate**: does the event mention a tracked ticker, sector, or macro theme?
2. **Novelty gate**: is this new? Compare against a recent event store (`data/marketing/events_seen.jsonl`).
3. **Market-hours gate**: is it actionable now? (After 20:00 ET events get a "next-open" tag rather than immediate post.)

Only events that pass all three gates enter the render + copy + audit pipeline.

### 4.3 Auditor path for political content

Truth-Social, CENTCOM, and Fed content routes through an **elevated auditor path**:
- Fact-check: does the stated claim match the source verbatim?
- Jurisdiction check: does this have clear, quantifiable market impact?
- No opinion amplification: the post describes the event and the market-impact vector; it does not editorialize.
- Hard-fail: any post that would read as endorsing a political position is blocked, not published.

The elevated path adds ~10-15s latency. Still well within the 2-minute budget.

---

## 5. The `earnings_fastlane.py` interface sketch

```python
"""engine.marketing.earnings_fastlane — Real-time earnings detection + publishing.

NOT wired to a running daemon yet (Phase-B). This module defines the interface
contracts used by the fast-lane. Phase-A: call build_earnings_post() manually
from the Content Studio on same-day earnings. Phase-B: run run_daemon() as a
launchd service on the Mastermind host.
"""

def arm_reporters(root, *, today=None) -> list[dict]:
    """
    Returns today's reporters from earnings.parquet, split by window.
    Calls todays_reporters() from engine.marketing.earnings_card.
    """
    ...


def poll_ticker_release(ticker: str, provider_client) -> dict | None:
    """
    Query the earnings data provider for ticker's latest actual EPS/rev.
    Returns normalized dict or None if not yet reported.
    {
        "ticker": str,
        "eps_actual": float,
        "eps_est": float,
        "rev_actual": float | None,
        "rev_est": float | None,
        "quarter": str,           # e.g. "Q2 2026"
        "release_ts": str,        # ISO timestamp
    }
    """
    ...


def fast_lane_pipeline(release: dict, root, *, publisher) -> bool:
    """
    Full pipeline: normalize → render card → write copy → audit → publish.
    Returns True if published, False if blocked by auditor or publisher error.
    Latency target: <2 minutes from call to published.
    """
    from engine.marketing.earnings_card import build_earnings_post
    post = build_earnings_post(
        release["ticker"],
        release["company_name"],
        release["eps_actual"],
        release["eps_est"],
        release.get("rev_actual"),
        release.get("rev_est"),
        root,
        quarter=release.get("quarter"),
    )
    if not post["svg"]:
        return False
    # TODO (Phase-B): route through copywriter + auditor before publish
    return publisher.publish(post)


def run_daemon(root, provider_client, publisher, *, poll_interval_s=20):
    """
    Always-on loop. Arms reporters each morning and afternoon, polls during
    earnings windows, fires fast_lane_pipeline on fresh detections.
    Runs as a launchd service on the Mastermind host.
    NOT blocking the nightly pipeline — separate process.
    """
    ...
```

---

## 6. What is buildable now vs. needs the operator

### Phase-A (buildable now — this session)

- [x] `render_earnings_card` — upgraded with logo, quarter, surprise %, EPS-only mode
- [x] `engine/marketing/earnings_card.py` — `todays_reporters` + `build_earnings_post`
- [x] `tests/test_earnings_card.py` — full test coverage
- [ ] Same-day manual call path: operator reads the release numbers, calls
  `build_earnings_post`, posts manually — uses the card renderer immediately

### Phase-B (needs operator + API keys)

- [ ] Provider API key (Polygon.io or FMP) — $50-200/mo for real-time earnings endpoint
- [ ] Always-on host process — launchd service on the Mac Studio (already used for MM bot)
- [ ] `earnings_fastlane.py` daemon wired to provider client
- [ ] Publisher adapter (already exists in Content Studio; reuse)
- [ ] Truth-Social / CENTCOM pollers (free RSS, just needs the loop)

### Phase-C (optional enrichment)

- [ ] Copywriter LLM call for hook generation (Sonnet; replaces placeholder body)
- [ ] Historical surprise percentile ("This is AAPL's biggest beat in 8 quarters")
- [ ] Reaction chart: chart_v2 render of the after-hours price move

---

## 7. Key architectural decisions

**Decision 1: poll, not webhook, for Phase-A.** Webhooks require operator-side infra
(a public endpoint, SSL, retry logic). A targeted 20-second poll during earnings windows
achieves <1-minute latency with zero infra changes. Migrate to webhook when the daemon
is stable.

**Decision 2: calendar-armed windows, not 24/7 monitoring.** Polling every 20 seconds
24/7 across 200+ tickers is expensive and noisy. The parquet calendar tells us exactly
when each ticker reports; arm windows only for those tickers, only during those hours.
Cost: ~$0/day for most days; ~$0.01/day on heavy earnings days.

**Decision 3: separate process, not a cron job.** The fast-lane must react within
seconds. A cron job (minimum 1-minute resolution) adds up to 60 seconds of latency
before even starting. The daemon runs a tight poll loop and reacts immediately. The
nightly cron and the fast-lane daemon are independent processes sharing only the
data/ directory.

**Decision 4: EPS-only is valid.** When revenue data isn't available at time of
detection (some providers deliver EPS first, revenue seconds later), publish the
EPS-only card immediately. If revenue arrives within 5 minutes, a follow-up post
can add it. A timely EPS-only post beats a complete-but-late post.
