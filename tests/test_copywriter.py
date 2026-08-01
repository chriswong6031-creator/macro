"""tests/test_copywriter.py — Copywriter module tests.

Test list:
1. verify_signal_live: kills BA case (entry=226.50, last=214 = -5.5%)
2. verify_signal_live: kills runaway (entry=100, last=115 = +15%)
3. verify_signal_live: kills stale signal (> 10 days)
4. verify_signal_live: accepts live, in-range signal
5. verify_signal_live: rejects None closes
6. build_context: top_fact_text present when facts provided
7. build_context: numbers_whitelist includes plan numbers
8. validate_copy: catches missing cashtag on signal post
9. validate_copy: catches too-long copy
10. validate_copy: catches banned vocab (MACD, guaranteed, etc.)
11. validate_copy: catches number not in whitelist
12. validate_copy: catches missing invalidation phrase on signal
13. validate_copy: catches missing disclosure on signal
14. validate_copy: catches duplicate headline within batch
15. write_posts_deterministic: no "Here's the score" or "The chart. That's it."
16. write_posts_deterministic: chart posts contain a digit or %
17. write_posts_deterministic: no duplicate headlines in a full plan (6 accounts × 21 posts)
18. write_posts_deterministic: all signal posts pass validate_copy
19. write_posts_deterministic: deterministic — same contexts → same output
20. write_posts_llm: returns None in test environment (env var not set)
21. graded_receipts: invalidated plan → loss receipt
22. graded_receipts: DONE plan → win receipt
23. graded_receipts: DONE + invalidated → mixed receipt, mixed preferred
24. graded_receipts: freshness gate blocks old signal_date
25. graded_receipts: deduplicate keeps richest (mixed > win > loss)
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fresh_date(days_ago: int = 5) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()


def _old_date(days_ago: int = 30) -> str:
    return (datetime.now(timezone.utc).date() - timedelta(days=days_ago)).isoformat()


def _make_signal_plan(
    ticker: str = "PLTR",
    entry: float = 120.0,
    inv: float = 100.0,
    t1: float = 150.0,
    t2: float = 180.0,
    signal_date: str | None = None,
    phase: str = "triggered_pre_t1",
    profit_plan: list | None = None,
) -> dict:
    return {
        "id": f"{ticker}-BULL",
        "asset": ticker,
        "direction": "BULL",
        "entry": entry,
        "invalidation": inv,
        "targets": [t1, t2],
        "_conviction_score": 90,
        "_signal_date": signal_date or _fresh_date(),
        "phase": phase,
        "recommended_action": "hold",
        "management_confidence": 66.0,
        "what_to_do_now": [],
        "profit_plan": profit_plan or [
            {"level": t1, "label": "T1", "action": "Scale out", "status": "ACTIVE"},
            {"level": t2, "label": "T2", "action": "Close", "status": "PENDING"},
        ],
    }


def _make_closes(last_close: float, n: int = 30) -> tuple[list[str], list[float]]:
    dates = [(datetime.now(timezone.utc).date() - timedelta(days=n - i)).isoformat() for i in range(n)]
    prices = [last_close] * n
    return dates, prices


# ─────────────────────────────────────────────────────────────────────────────
# 1-5: verify_signal_live
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_signal_live_kills_ba_case():
    """BA case: entry 226.50, last 214 = -5.5% underwater."""
    from engine.marketing.copywriter import verify_signal_live
    plan = _make_signal_plan("BA", entry=226.50, inv=200.0, t1=260.0)
    closes = _make_closes(214.0)
    ok, reason = verify_signal_live(plan, closes)
    assert not ok, f"Expected BA underwater case to fail, got ok=True reason={reason}"
    assert "underwater" in reason.lower(), f"Expected 'underwater' in reason: {reason}"


def test_verify_signal_live_kills_runaway():
    """Entry 100, last 115 = +15% runaway — no longer actionable."""
    from engine.marketing.copywriter import verify_signal_live
    plan = _make_signal_plan("TEST", entry=100.0, inv=85.0, t1=120.0)
    closes = _make_closes(115.0)  # 15% above entry > 12% threshold
    ok, reason = verify_signal_live(plan, closes)
    assert not ok, f"Expected runaway to fail, got ok=True reason={reason}"
    assert "ran away" in reason.lower() or "runaway" in reason.lower() or "12" in reason, (
        f"Expected runaway reason: {reason}"
    )


def test_verify_signal_live_kills_stale_signal():
    """Signal older than 10 days → killed."""
    from engine.marketing.copywriter import verify_signal_live
    plan = _make_signal_plan("PLTR", entry=120.0, signal_date=_old_date(15))
    closes = _make_closes(121.0)  # in range
    ok, reason = verify_signal_live(plan, closes)
    assert not ok, f"Expected stale signal to fail, got ok=True reason={reason}"
    assert "old" in reason.lower() or "stale" in reason.lower() or "15" in reason, (
        f"Expected age in reason: {reason}"
    )


def test_verify_signal_live_accepts_valid():
    """Fresh, in-range signal → ok."""
    from engine.marketing.copywriter import verify_signal_live
    plan = _make_signal_plan("NVDA", entry=100.0, signal_date=_fresh_date(3))
    closes = _make_closes(102.0)  # 2% above entry — within range
    ok, reason = verify_signal_live(plan, closes)
    assert ok, f"Expected valid signal to pass, got ok=False reason={reason}"


def test_verify_signal_live_rejects_no_closes():
    """None closes → cannot verify → rejected."""
    from engine.marketing.copywriter import verify_signal_live
    plan = _make_signal_plan("AAPL", entry=200.0)
    ok, reason = verify_signal_live(plan, None)
    assert not ok
    assert "no close" in reason.lower() or "cannot verify" in reason.lower(), reason


# ─────────────────────────────────────────────────────────────────────────────
# 6-7: build_context
# ─────────────────────────────────────────────────────────────────────────────

def test_build_context_includes_top_fact():
    from engine.marketing.copywriter import build_context
    item = {"ticker": "PLTR", "type": "signal", "account": "flagship",
            "entry": 120.0, "targets": [150.0], "invalidation": 100.0}
    facts = {
        "facts": [
            {"id": "new_52w_high", "text": "PLTR hit a new 52-week high", "salience": 10, "numbers": ["142.50"]},
        ],
        "numbers_whitelist": ["142.50"],
    }
    ctx = build_context(item, persona={"name": "The Desk", "emoji_budget": 0}, facts=facts)
    assert ctx["top_fact_text"] == "PLTR hit a new 52-week high"
    assert ctx["ticker"] == "PLTR"
    assert ctx["cashtag"] == "$PLTR"


def test_build_context_whitelist_includes_plan_numbers():
    """Plan numbers reach the whitelist in DISPLAY form (Content Studio W1).

    This test asserted "380.00" until 2026-07-29. The two-decimal form is the
    defect the rounding law closes: the whitelist is the only thing copy may
    quote, so an over-precise whitelist forces an over-precise post ("Entry
    285.10, target 375.91" on a $285 name). Contract §Rounding + masterplan §0
    gate 6 — full precision now lives on `*_exact`, out of the whitelist.
    """
    from engine.marketing.copywriter import build_context
    item = {"ticker": "MSFT", "type": "signal", "account": "receipts",
            "entry": 380.0, "targets": [420.0, 450.0], "invalidation": 360.0}
    ctx = build_context(item, persona=None, facts=None)
    whitelist = ctx["numbers_whitelist"]
    assert "380" in whitelist, f"entry not in whitelist: {whitelist}"
    assert "420" in whitelist, f"t1 not in whitelist: {whitelist}"
    assert "360" in whitelist, f"inv not in whitelist: {whitelist}"
    assert not [w for w in whitelist if w.endswith(".00")], (
        f"full-precision tokens must not reach the whitelist: {whitelist}"
    )
    # ...but they are still available for provenance/grading.
    assert ctx["entry_exact"] == "380.00"


# ─────────────────────────────────────────────────────────────────────────────
# 8-14: validate_copy
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_missing_cashtag():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "PLTR", "type": "signal", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("PLTR setup flagged", "Entry 120. Stop 100.", ctx)
    cashtag_violations = [v for v in violations if "cashtag" in v.lower()]
    assert cashtag_violations, f"Expected cashtag violation, got: {violations}"


def test_validate_cashtag_present_is_clean():
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "PLTR", "type": "signal", "emoji_budget": 0,
        "numbers_whitelist": ["120.00", "100.00", "150.00"],
    }
    # Provide invalidation phrase and disclosure
    headline = "$PLTR setup at 120.00"
    body = "Stop below 100.00. Target 150.00. Size appropriately."
    violations = validate_copy(headline, body, ctx)
    cashtag_violations = [v for v in violations if "cashtag" in v.lower()]
    assert not cashtag_violations, f"Unexpected cashtag violation: {violations}"


def test_validate_too_long():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    long_body = "A" * 300
    violations = validate_copy("Short headline", long_body, ctx)
    length_v = [v for v in violations if "long" in v.lower() or "chars" in v.lower()]
    assert length_v, f"Expected length violation, got: {violations}"


def test_validate_banned_macd():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "SPY", "type": "chart", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("$SPY chart | MACD cross", "RSI is elevated. Watch the MACD.", ctx)
    banned_v = [v for v in violations if "macd" in v.lower() or "rsi" in v.lower() or "banned" in v.lower()]
    assert banned_v, f"Expected banned vocab violation, got: {violations}"


def test_validate_banned_guaranteed():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Buy now — guaranteed gains", "Can't lose on this one.", ctx)
    banned_v = [v for v in violations if "banned" in v.lower() or "guaranteed" in v.lower() or "can't lose" in v.lower()]
    assert banned_v, f"Expected banned vocab violation, got: {violations}"


def test_validate_invented_number():
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "AAPL", "type": "chart", "emoji_budget": 0,
        "numbers_whitelist": ["185.50"],  # 226.50 NOT in whitelist
    }
    violations = validate_copy("$AAPL at 226.50", "Level: 226.50. Watch this.", ctx)
    number_v = [v for v in violations if "226.50" in v or "number" in v.lower()]
    assert number_v, f"Expected number violation for 226.50, got: {violations}"


# These two tests used to pin the OPPOSITE law: that a signal post is REJECTED
# unless it carries an invalidation phrase and an honesty caveat. That mandate is
# what produced the machine voice — "37.1 is my trigger, 30.9 proves me wrong.
# One pattern isn't a guarantee" is what you get when both are compulsory inside
# 275 chars. The operator graded a batch built under it F and quoted both halves
# back ("no human will ever say that"). The mandate is gone; these now pin the
# ban. See memory marketing-voice-fact-plus-cost.


def test_signal_post_without_an_invalidation_phrase_is_fine_now():
    """The mandate is gone: no invalidation line is no longer a violation."""
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "PLTR", "type": "signal", "emoji_budget": 0,
        "numbers_whitelist": ["120.00", "150.00"],
    }
    violations = validate_copy(
        "$PLTR at 120.00",
        "Held 120.00 for three weeks. I passed on this shape last quarter and "
        "regretted it, so I'm not being clever about it twice.",
        ctx,
    )
    inv_v = [v for v in violations if "invalidat" in v.lower() or "what would change" in v.lower()]
    assert not inv_v, f"invalidation mandate should be retired, got: {violations}"


def test_risk_stated_against_the_authors_ego_is_rejected():
    """'I'm wrong below X' / 'proves me wrong' — operator: no human says this."""
    from engine.marketing.copywriter import machine_risk_violations
    for text in (
        "$PLTR held 120.00. I'm wrong below 118.",
        "37.1 is my trigger, 30.9 proves me wrong.",
        "Entry 45. What would prove me wrong: a close under 41.",
    ):
        assert machine_risk_violations(text), f"should be rejected: {text!r}"


def test_boilerplate_caveats_are_rejected():
    """The compliance-desk forms are banned; a caveat that COSTS you passes."""
    from engine.marketing.copywriter import machine_risk_violations
    for text in (
        "$COHR is there now. Historical, not a guarantee.",
        "One pattern isn't a guarantee.",
        "Past performance says otherwise.",
        "Size appropriately.",
    ):
        assert machine_risk_violations(text), f"should be rejected: {text!r}"
    assert machine_risk_violations(
        "If it loses 33.8 the whole thing was noise. I've been early twice already."
    ) == [], "a human caveat that costs the author something must pass"


def test_validate_duplicate_headline():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    headline = "Macro backdrop this week"
    violations = validate_copy(
        headline, "Some body text.",
        ctx,
        batch_headlines=["Macro backdrop this week"],  # exact dup
    )
    dup_v = [v for v in violations if "duplicate" in v.lower()]
    assert dup_v, f"Expected duplicate headline violation, got: {violations}"


# ─────────────────────────────────────────────────────────────────────────────
# 15-19: write_posts_deterministic
# ─────────────────────────────────────────────────────────────────────────────

def _make_contexts(n: int = 6) -> list[dict]:
    """Build a minimal set of contexts for testing."""
    from engine.marketing.copywriter import build_context
    tickers = ["PLTR", "MSFT", "NVDA", "AAPL", "TSLA", "AMZN"]
    types = ["signal", "chart", "education", "macro", "receipt", "watchlist"]
    voices = ["authoritative desk", "dry, receipts-forward", "specialist",
              "educational", "fast, reactive", "pattern/history"]
    contexts = []
    for i in range(n):
        item = {
            "ticker": tickers[i % len(tickers)],
            "type": types[i % len(types)],
            "account": f"acct_{i}",
            "entry": 120.0 + i * 10,
            "targets": [150.0 + i * 10, 180.0 + i * 10],
            "invalidation": 100.0 + i * 5,
            "_signal_date": _fresh_date(),
            "direction": "BULL",
        }
        persona = {"name": "The Desk", "voice_notes": "Emoji budget: 0", "example_lines": []}
        facts = {
            "facts": [
                {
                    "id": "pct_5",
                    "text": f"{item['ticker']} is up +8.3% over the last week",
                    "salience": 1,
                    "numbers": ["+8.3%"],
                },
            ],
            "numbers_whitelist": ["+8.3%", f"{120.0 + i * 10:.2f}",
                                   f"{150.0 + i * 10:.2f}", f"{100.0 + i * 5:.2f}",
                                   f"{180.0 + i * 10:.2f}"],
        }
        ctx = build_context(item, persona=persona, facts=facts)
        ctx["voice"] = voices[i % len(voices)]
        ctx["slot"] = f"D{i + 1}-AM"
        contexts.append(ctx)
    return contexts


def test_deterministic_no_generic_slop():
    """'Here's the score' and 'The chart. That's it.' must not appear anywhere."""
    from engine.marketing.copywriter import write_posts_deterministic
    contexts = _make_contexts(20)
    results = write_posts_deterministic(contexts)
    for r in results:
        full = r["headline"] + " " + r["body"]
        assert "Here's the score" not in full, (
            f"Generic slop found: {full[:120]}"
        )
        assert "The chart. That's it." not in full, (
            f"Generic chart slop found: {full[:120]}"
        )


def test_chart_posts_contain_concrete_fact():
    """Every chart post must contain a digit, %, or x (a concrete fact)."""
    from engine.marketing.copywriter import build_context, write_posts_deterministic
    import re
    contexts = []
    for i in range(4):
        item = {
            "ticker": f"T{i}",
            "type": "chart",
            "account": "test",
            "entry": 100.0 + i * 10,
            "targets": [120.0],
            "invalidation": 90.0,
        }
        facts = {
            "facts": [{
                "id": "pct_5",
                "text": f"T{i} is up +{5 + i}.2% over the last week",
                "salience": 1,
                "numbers": [f"+{5 + i}.2%"],
            }],
            "numbers_whitelist": [f"+{5 + i}.2%", f"{100.0 + i * 10:.2f}", "120.00", "90.00"],
        }
        ctx = build_context(item, persona={"name": "Test", "voice_notes": "Emoji budget: 0",
                                           "example_lines": []}, facts=facts)
        ctx["voice"] = "authoritative desk"
        ctx["slot"] = f"D{i + 1}-AM"
        contexts.append(ctx)

    results = write_posts_deterministic(contexts)
    number_re = re.compile(r"\d")
    for i, r in enumerate(results):
        full = r["headline"] + " " + r["body"]
        assert number_re.search(full), (
            f"Chart post {i} has no concrete number/fact: '{full[:150]}'"
        )


def test_no_duplicate_headlines_per_account():
    """Within a single account's 21-post plan, no headline may repeat.

    The copy_law says 'never repeat a headline across posts in the same plan'.
    A plan is per-account. Cross-account repetition is acceptable (different voice/tilt).

    Non-ticker types (education, macro, watchlist, event) have no ticker so the
    rotation-counter path fires; ticker types hash on ticker+account+slot.
    """
    from engine.marketing.copywriter import build_context, write_posts_deterministic

    _TICKER_TYPES = {"signal", "chart", "receipt"}
    tickers = ["PLTR", "MSFT", "NVDA", "AAPL", "TSLA", "AMZN", "GOOG", "META"]
    types = ["signal", "chart", "education", "macro", "receipt", "watchlist", "event"]
    voices = ["authoritative desk", "dry, receipts-forward", "specialist",
              "educational", "fast, reactive", "pattern/history"]

    for acct_i in range(6):
        voice = voices[acct_i]
        contexts = []
        for slot_i in range(21):
            type_id = types[slot_i % len(types)]
            # Only ticker-bearing types get a ticker; others get empty string
            ticker = tickers[slot_i % len(tickers)] if type_id in _TICKER_TYPES else ""
            entry = 100.0 + slot_i * 5
            item = {
                "ticker": ticker,
                "type": type_id,
                "account": f"acct_{acct_i}",
                "entry": entry if ticker else None,
                "targets": [entry + 20.0, entry + 40.0] if ticker else [],
                "invalidation": entry - 10.0 if ticker else None,
                "_signal_date": _fresh_date(),
                "direction": "BULL",
            }
            wl_items = [f"+{slot_i + 1}.5%"]
            if ticker:
                wl_items += [f"{entry:.2f}", f"{entry + 20.0:.2f}",
                             f"{entry - 10.0:.2f}", f"{entry + 40.0:.2f}"]
            facts = {
                "facts": [{
                    "id": "pct_5",
                    "text": (
                        f"{ticker} is up +{slot_i + 1}.5% this week"
                        if ticker else f"Markets up +{slot_i + 1}.5% this week"
                    ),
                    "salience": 1,
                    "numbers": [f"+{slot_i + 1}.5%"],
                }],
                "numbers_whitelist": wl_items,
            }
            ctx = build_context(item, persona={"name": "Test", "voice_notes": "Emoji budget: 1",
                                               "example_lines": []}, facts=facts)
            ctx["voice"] = voice
            ctx["slot"] = f"A{acct_i}-D{slot_i}-AM"
            contexts.append(ctx)

        results = write_posts_deterministic(contexts)
        headlines = [r["headline"].lower().strip() for r in results]
        assert len(headlines) == len(set(headlines)), (
            f"Account acct_{acct_i} ({voice}): duplicate headlines found. "
            f"Total={len(headlines)}, unique={len(set(headlines))}. "
            f"Dups: {list(set(h for h in headlines if headlines.count(h) > 1))}"
        )


def test_all_signal_posts_pass_validate():
    """Every signal post in a plan should have no violations."""
    from engine.marketing.copywriter import build_context, write_posts_deterministic, validate_copy
    contexts = []
    for i in range(10):
        item = {
            "ticker": f"SIG{i}",
            "type": "signal",
            "account": "flagship",
            "entry": 100.0 + i,
            "targets": [120.0 + i, 140.0 + i],
            "invalidation": 90.0 + i,
            "_signal_date": _fresh_date(),
            "direction": "BULL",
        }
        entry_str = f"{100.0 + i:.2f}"
        t1_str = f"{120.0 + i:.2f}"
        inv_str = f"{90.0 + i:.2f}"
        facts = {
            "facts": [{
                "id": "streak_green",
                "text": f"SIG{i} has closed green 5 sessions in a row",
                "salience": 6,
                "numbers": ["5"],
            }],
            "numbers_whitelist": [entry_str, t1_str, inv_str, f"{140.0 + i:.2f}"],
        }
        ctx = build_context(item, persona={"name": "The Desk",
                                           "voice_notes": "Emoji budget: 1",
                                           "example_lines": []}, facts=facts)
        ctx["voice"] = "authoritative desk"
        ctx["slot"] = f"D{i}-AM"
        contexts.append(ctx)

    results = write_posts_deterministic(contexts)
    all_headlines = [r["headline"] for r in results]

    for i, (r, ctx) in enumerate(zip(results, contexts)):
        violations = validate_copy(
            r["headline"], r["body"], ctx,
            batch_headlines=all_headlines[:i],
        )
        # Filter out the "near-duplicate" violation since we have distinct tickers
        real_violations = [v for v in violations if "near-duplicate" not in v]
        assert not real_violations, (
            f"Signal post {i} has violations: {real_violations}\n"
            f"headline={r['headline']!r}\nbody={r['body']!r}"
        )


def test_write_posts_deterministic_stable():
    """Same contexts → same output every time."""
    from engine.marketing.copywriter import write_posts_deterministic
    contexts = _make_contexts(10)
    out1 = write_posts_deterministic(contexts)
    out2 = write_posts_deterministic(contexts)
    for r1, r2 in zip(out1, out2):
        assert r1["headline"] == r2["headline"], "Non-deterministic headline"
        assert r1["body"] == r2["body"], "Non-deterministic body"


def test_event_variant_rotates_by_calendar_day():
    """A single daily non-ticker post (the event 'read on today's move') must
    land on a DIFFERENT variant each night instead of always slot 0 — the byte-
    identical 2026-07-26/07-27 repeat. Same as_of stays deterministic."""
    from engine.marketing.copywriter import build_context, write_posts_deterministic

    def _event_headline(as_of):
        item = {"ticker": "", "type": "event", "account": "flagship"}
        facts = {"facts": [{"id": "drv", "text": "What's driving today: hawkish repricing.",
                            "salience": 1, "numbers": []}],
                 "numbers_whitelist": []}
        ctx = build_context(item, persona={"name": "Flagship", "voice_notes": "",
                                           "example_lines": []}, facts=facts)
        ctx["type"] = "event"
        ctx["voice"] = "authoritative desk"
        ctx["slot"] = ""
        ctx["as_of"] = as_of
        return write_posts_deterministic([ctx])[0]["headline"]

    # Determinism preserved: same day → same headline.
    assert _event_headline("2026-07-27") == _event_headline("2026-07-27")
    # The exact bug: two adjacent nights must NOT repeat verbatim.
    assert _event_headline("2026-07-26") != _event_headline("2026-07-27")
    # Five consecutive days cycle through all five event variants.
    heads = [_event_headline(f"2026-07-{d:02d}") for d in range(23, 28)]
    assert len(set(heads)) == 5, f"expected 5 distinct daily headlines, got {heads}"


# ─────────────────────────────────────────────────────────────────────────────
# 20: write_posts_llm in test environment
# ─────────────────────────────────────────────────────────────────────────────

def test_write_posts_llm_returns_none_in_tests():
    """In the test environment (no MARKETING_LLM_ENABLED env), llm path returns None."""
    from engine.marketing.copywriter import write_posts_llm
    # Ensure the env var is NOT set
    os.environ.pop("MARKETING_LLM_ENABLED", None)
    cfg = {"llm": {"enabled": True, "model_key": "marketing_copy"}}
    contexts = _make_contexts(3)
    result = write_posts_llm(contexts, cfg)
    assert result is None, f"Expected None in test env, got {type(result)}"


# ─────────────────────────────────────────────────────────────────────────────
# 21-25: graded_receipts
# ─────────────────────────────────────────────────────────────────────────────

def test_graded_receipts_loss_from_invalidated():
    from engine.marketing.receipt_source import graded_receipts
    plan = _make_signal_plan(
        "QCOM", entry=189.2, inv=177.09, signal_date=_fresh_date(3),
        phase="invalidated",
        profit_plan=[
            {"level": 207.36, "label": "T1", "action": "", "status": "PENDING"},
        ],
    )
    receipts = graded_receipts([plan])
    assert len(receipts) == 1
    r = receipts[0]
    assert r["ticker"] == "QCOM"
    assert r["kind"] == "loss"
    assert "loss_pct" in r
    assert r["loss_pct"] < 0  # invalidation is below entry
    assert "loss_pct_str" in r
    assert r["loss_pct_str"].startswith("-")


def test_graded_receipts_win_from_done():
    from engine.marketing.receipt_source import graded_receipts
    plan = _make_signal_plan(
        "NVDA", entry=500.0, inv=460.0, signal_date=_fresh_date(5),
        phase="triggered_pre_t1",
        profit_plan=[
            {"level": 550.0, "label": "T1", "action": "", "status": "DONE"},
            {"level": 600.0, "label": "T2", "action": "", "status": "PENDING"},
        ],
    )
    receipts = graded_receipts([plan])
    assert len(receipts) == 1
    r = receipts[0]
    assert r["ticker"] == "NVDA"
    assert r["kind"] == "win"
    assert r["gain_pct"] > 0
    assert r["gain_pct_str"].startswith("+")
    assert r["target"] == 550.0
    assert r["target_label"] == "T1"


def test_graded_receipts_mixed_from_done_then_invalidated():
    """QCOM real case: T1 DONE at 207.36, then invalidated."""
    from engine.marketing.receipt_source import graded_receipts
    plan = _make_signal_plan(
        "QCOM", entry=189.2, inv=177.09, signal_date=_fresh_date(8),
        phase="invalidated",
        profit_plan=[
            {"level": 207.3632, "label": "T1", "action": "", "status": "DONE"},
            {"level": 225.5264, "label": "T2", "action": "", "status": "PENDING"},
        ],
    )
    receipts = graded_receipts([plan])
    assert len(receipts) == 1
    r = receipts[0]
    assert r["kind"] == "mixed", f"Expected mixed, got {r['kind']}"
    assert "gain_pct" in r
    assert "loss_pct" in r
    assert r["gain_pct"] > 0
    assert r["loss_pct"] < 0


def test_graded_receipts_freshness_gate():
    """Signal older than the configured window → excluded from receipts.

    The window is config-owned (`copywriter.receipt_max_age_days`, widened
    14→30 on 2026-07-31 because resolved plans mature at 21-22 days and a
    14-day window starved the desk to zero forever). Pinning a literal age
    here re-created the starvation bug as a test failure, so the stale
    fixture is derived from the live window instead.
    """
    from engine.marketing.receipt_source import graded_receipts, receipt_max_age_days
    beyond = receipt_max_age_days() + 5
    plan = _make_signal_plan(
        "OLD", entry=100.0, inv=90.0, signal_date=_old_date(beyond),
        phase="invalidated",
    )
    receipts = graded_receipts([plan])
    assert receipts == [], f"Expected empty receipts for stale plan, got {receipts}"
    # And the boundary the other way: inside the window still counts.
    fresh = _make_signal_plan(
        "NEW", entry=100.0, inv=90.0,
        signal_date=_old_date(max(receipt_max_age_days() - 5, 1)),
        phase="invalidated",
    )
    assert graded_receipts([fresh]), "a within-window resolution must produce a receipt"


# ── the window BOUNDARY, and the lanes that were not reading it ─────────────
#
# 2026-07-31 adversarial review, finding 6. `receipt_max_age_days`' docstring
# claimed to be "THE single reader" of `copywriter.receipt_max_age_days`. Three
# lanes call `graded_receipts` and only content_studio threaded a window
# through, so an operator who tightened the knob would have moved the Studio's
# receipt supply while `allies.track_record_stats` (the win rate a kit prints)
# and `sentinel.receipts_context` (the cherry-pick audit window) silently kept
# grading a 30-day book. Two numbers off two windows, both called "the track
# record".

def test_graded_receipts_window_boundary_is_inclusive_at_exactly_max_age():
    """`age > max_age_days` is the gate, so age == max is IN.

    An off-by-one here is invisible in production and expensive: it is one
    day of resolved supply on a desk whose whole supply is six plans.
    """
    from engine.marketing.receipt_source import graded_receipts, receipt_max_age_days
    window = receipt_max_age_days()
    assert window == 30, "boundary fixtures below are written against 30"
    plan = _make_signal_plan(
        "EDGE", entry=100.0, inv=90.0, signal_date=_old_date(window),
        phase="invalidated",
    )
    receipts = graded_receipts([plan])
    assert len(receipts) == 1, f"age == {window} must be inside the window"
    assert receipts[0]["ticker"] == "EDGE"


def test_graded_receipts_window_boundary_excludes_one_day_past_it():
    from engine.marketing.receipt_source import graded_receipts, receipt_max_age_days
    window = receipt_max_age_days()
    plan = _make_signal_plan(
        "EDGE", entry=100.0, inv=90.0, signal_date=_old_date(window + 1),
        phase="invalidated",
    )
    assert graded_receipts([plan]) == [], f"age == {window + 1} must be outside"


def _write_prophet_index(root, plans: list[dict]) -> None:
    """A real site/prophet/index.json under *root*, the way both lanes read it."""
    import json as _json

    d = root / "site" / "prophet"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.json").write_text(_json.dumps({"plans": plans}), encoding="utf-8")


def test_allies_track_record_reads_the_config_window(tmp_path):
    """MUTATION CHECK for the allies half, driven through the real function.

    A plan 20 days old is inside the default 30-day window and outside a
    config-tightened 14-day one. Pre-fix this call site passed no window at all,
    so BOTH configs reported the same single win and the kit's printed win rate
    could not be moved from config.
    """
    from engine.marketing import allies

    _write_prophet_index(tmp_path, [_make_signal_plan(
        "WIN", entry=100.0, inv=90.0, signal_date=_old_date(20),
        phase="triggered_pre_t1",
        profit_plan=[{"level": 120.0, "label": "T1", "status": "DONE", "action": ""}],
    )])

    wide = allies.track_record_stats(tmp_path, cfg={})
    tight = allies.track_record_stats(
        tmp_path, cfg={"copywriter": {"receipt_max_age_days": 14}})

    assert wide["wins"] == 1, wide
    assert wide["graded_n"] == 1, wide
    assert tight["wins"] == 0, tight
    assert tight["graded_n"] == 0, tight


def test_sentinel_receipts_context_reads_the_config_window(tmp_path):
    """MUTATION CHECK for the sentinel half, driven through the real function
    with a real prophet index on disk."""
    from engine.marketing import sentinel

    _write_prophet_index(tmp_path, [_make_signal_plan(
        "WIN", entry=100.0, inv=90.0, signal_date=_old_date(20),
        phase="triggered_pre_t1",
        profit_plan=[{"level": 120.0, "label": "T1", "status": "DONE", "action": ""}],
    )])

    _age, wide = sentinel.receipts_context(tmp_path, cfg={})
    assert wide == [{"ticker": "WIN", "outcome": "win"}], wide

    _age, tight = sentinel.receipts_context(
        tmp_path, cfg={"copywriter": {"receipt_max_age_days": 14}})
    assert tight == [], tight


def test_every_graded_receipts_call_site_threads_a_window():
    """SOURCE-LEVEL PIN, because the defect was a MISSING argument and a missing
    argument is exactly what a runtime test does not see: the call worked, it
    just quietly used a different window.

    The docstring's "THE single reader" claim was the whole reason nobody
    looked, so this asserts the property instead of the prose.
    """
    import inspect

    from engine.marketing import allies, content_studio, sentinel
    from engine.marketing.receipt_source import receipt_max_age_days

    for mod, fn_name in ((allies, "track_record_stats"),
                         (sentinel, "receipts_context")):
        src = inspect.getsource(getattr(mod, fn_name))
        assert "graded_receipts(" in src, (mod.__name__, fn_name)
        assert "max_age_days=" in src, (
            f"{mod.__name__}.{fn_name} calls graded_receipts with no window")
        assert "receipt_max_age_days(" in src, (
            f"{mod.__name__}.{fn_name} does not resolve the config knob")
        assert "cfg" in inspect.signature(getattr(mod, fn_name)).parameters, (
            f"{mod.__name__}.{fn_name} has no cfg to thread")

    # The lane that already did it, kept honest the same way.
    assert "receipt_max_age_days(cfg)" in inspect.getsource(content_studio)
    assert "single reader" not in (receipt_max_age_days.__doc__ or "").split("\n")[0]


def test_graded_receipts_deduplicate_richest():
    """Mixed beats win beats loss when same ticker appears multiple times."""
    from engine.marketing.receipt_source import graded_receipts
    loss_plan = _make_signal_plan(
        "TICKER", entry=100.0, inv=90.0, signal_date=_fresh_date(2),
        phase="invalidated",
        profit_plan=[{"level": 120.0, "label": "T1", "status": "PENDING", "action": ""}],
    )
    win_plan = _make_signal_plan(
        "TICKER", entry=100.0, inv=90.0, signal_date=_fresh_date(4),
        phase="triggered_pre_t1",
        profit_plan=[{"level": 120.0, "label": "T1", "status": "DONE", "action": ""}],
    )
    mixed_plan = _make_signal_plan(
        "TICKER", entry=100.0, inv=90.0, signal_date=_fresh_date(6),
        phase="invalidated",
        profit_plan=[{"level": 120.0, "label": "T1", "status": "DONE", "action": ""}],
    )

    receipts = graded_receipts([loss_plan, win_plan, mixed_plan])
    assert len(receipts) == 1, f"Expected 1 receipt (deduplicated), got {len(receipts)}"
    assert receipts[0]["kind"] == "mixed", (
        f"Expected mixed (richest) to win dedup, got {receipts[0]['kind']}"
    )


def test_graded_receipts_empty_plans():
    from engine.marketing.receipt_source import graded_receipts
    assert graded_receipts([]) == []
    assert graded_receipts(None) == []


# ─────────────────────────────────────────────────────────────────────────────
# Task 1: em-dash and banned-vocab enforcement
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_em_dash_in_headline():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Growth is slowing — watch rates", "Body text here.", ctx)
    em_v = [v for v in violations if "em dash" in v.lower() or "u+2014" in v.lower()]
    assert em_v, f"Expected em-dash violation, got: {violations}"


def test_validate_en_dash_in_body():
    """Bare en dash (U+2013) anywhere in copy must be flagged."""
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Headline", "Growth is strong – but watch rates.", ctx)
    dash_v = [v for v in violations if "en dash" in v.lower() or "u+2013" in v.lower()]
    assert dash_v, f"Expected en-dash violation, got: {violations}"


def test_validate_horizontal_bar_in_body():
    """Horizontal bar (U+2015) anywhere in copy must be flagged."""
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Headline", "Growth ― a clean read.", ctx)
    bar_v = [v for v in violations if "horizontal bar" in v.lower() or "u+2015" in v.lower()]
    assert bar_v, f"Expected horizontal-bar violation, got: {violations}"


def test_validate_hyphen_minus_allowed():
    """Hyphen-minus (ASCII 45) in compounds like '52-week' must NOT be flagged."""
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Headline", "Hit a 52-week low. High-yield pressure.", ctx)
    dash_v = [v for v in violations if "dash" in v.lower() or "bar" in v.lower()]
    assert not dash_v, f"Hyphen-minus should be allowed, got: {dash_v}"


def test_validate_banned_vertical():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "education", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("The vertical shift", "We track the vertical.", ctx)
    assert any("vertical" in v for v in violations), f"Expected banned vocab 'vertical': {violations}"


def test_validate_banned_regime_word_boundary():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    # "regime" standalone → banned; "regimen" must NOT be banned
    violations_regime = validate_copy("New regime here", "The regime is shifting.", ctx)
    assert any("regime" in v for v in violations_regime), f"Expected 'regime' violation: {violations_regime}"

    violations_regimen = validate_copy("Diet regimen", "Following a regimen.", ctx)
    regime_v = [v for v in violations_regimen if "banned vocab: 'regime'" in v]
    assert not regime_v, f"'regimen' should not trigger 'regime' ban: {violations_regimen}"


def test_validate_banned_goldilocks():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Goldilocks scenario", "This is a goldilocks setup.", ctx)
    assert any("goldilocks" in v.lower() for v in violations), f"Expected 'goldilocks' violation: {violations}"


def test_validate_banned_de_rating():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("De-rating risk", "Equity de-rating is in play.", ctx)
    assert any("de-rating" in v.lower() for v in violations), f"Expected 'de-rating' violation: {violations}"


def test_validate_banned_positioning_in():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Positioning in Tech", "Positioning in semis is crowded.", ctx)
    assert any("positioning in" in v.lower() for v in violations), (
        f"Expected 'positioning in' violation: {violations}"
    )


def test_validate_banned_implications_for():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("Implications for rates", "implications for growth here.", ctx)
    assert any("implications for" in v.lower() for v in violations), (
        f"Expected 'implications for' violation: {violations}"
    )


def test_validate_banned_the_backdrop():
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    violations = validate_copy("The backdrop shifts", "Against the backdrop of rising rates.", ctx)
    assert any("the backdrop" in v.lower() for v in violations), (
        f"Expected 'the backdrop' violation: {violations}"
    )


def test_validate_banned_narrative_word_boundary():
    """'narrative' standalone → banned; 'narratives' also caught; 'narrator' is fine."""
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "macro", "emoji_budget": 0, "numbers_whitelist": []}
    violations_narrative = validate_copy("The narrative is shifting", "A key narrative.", ctx)
    assert any("narrative" in v.lower() for v in violations_narrative), (
        f"Expected 'narrative' violation: {violations_narrative}"
    )
    # Verify word-boundary: 'narrator' should NOT fire the 'narrative' ban
    violations_narrator = validate_copy("The narrator speaks", "A skilled narrator.", ctx)
    narrative_v = [v for v in violations_narrator if "banned vocab: 'narrative'" in v]
    assert not narrative_v, f"'narrator' should not trigger 'narrative' ban: {violations_narrator}"


# ─────────────────────────────────────────────────────────────────────────────
# Task 2: year-whitelist regression
# ─────────────────────────────────────────────────────────────────────────────

def test_year_in_fact_text_auto_whitelisted():
    """4-digit year in a fact text must not trigger the numbers validator."""
    from engine.marketing.copywriter import build_context, validate_copy
    item = {"ticker": "SPY", "type": "macro", "account": "flagship"}
    facts = {
        "facts": [{"id": "test", "text": "SPY reached levels not seen since Nov 2024",
                   "salience": 8, "numbers": ["2024"]}],
        "numbers_whitelist": [],
    }
    ctx = build_context(item, facts=facts)
    assert "2024" in ctx["numbers_whitelist"], "Year 2024 should be auto-extracted into whitelist"
    violations = validate_copy("SPY test", "SPY reached levels not seen since Nov 2024", ctx)
    number_v = [v for v in violations if "2024" in v]
    assert not number_v, f"Year '2024' should not be flagged as invented number: {violations}"


def test_year_whitelist_covers_multiple_years():
    """Multiple years in fact texts are all extracted."""
    from engine.marketing.copywriter import build_context
    item = {"ticker": "", "type": "macro", "account": "flagship"}
    facts = {
        "facts": [
            {"id": "a", "text": "First since Jan 2022", "salience": 5},
            {"id": "b", "text": "Similar to the 2023 cycle", "salience": 4},
        ],
        "numbers_whitelist": [],
    }
    ctx = build_context(item, facts=facts)
    wl = ctx["numbers_whitelist"]
    assert "2022" in wl, f"'2022' should be in whitelist: {wl}"
    assert "2023" in wl, f"'2023' should be in whitelist: {wl}"


# ── Double-period regression (_render_template) ──────────────────────────────

def test_render_template_fact_ending_period_plus_template_period_collapses():
    """fact ends in '.' + template '{top_fact}. Next.' → body has single periods only."""
    from engine.marketing.copywriter import _render_template
    ctx = {
        "top_fact_text": "AMD fell 6.2% today.",  # already ends with period
        "voice": "authoritative desk",
        "type": "mover",
        "cashtag": "$AMD",
        "ticker": "AMD",
        "entry_str": "",
        "t1_str": "",
        "t2_str": "",
        "inv_str": "",
        "direction": "BEAR",
        "gain_pct_str": "",
        "loss_pct_str": "",
        "stop_str": "",
        "target_label": "T1",
        "win_rate_str": "",
        "cashtag_list": "",
        "theme_name": "",
        "theme_direction": "",
        "theme_agg_pct": "",
        "theme_question": "",
        "mover_pct": "",
    }
    result = _render_template("{top_fact}. Watching, not chasing.", ctx)
    assert ".." not in result, f"Double period found in: {result!r}"
    assert "AMD fell 6.2% today. Watching" in result, f"Unexpected result: {result!r}"


def test_render_template_fact_without_period_gets_period_no_double():
    """fact without terminal '.' gets one appended; template '{top_fact} Next.' is clean."""
    from engine.marketing.copywriter import _render_template
    ctx = {
        "top_fact_text": "AMD fell 6.2% today",  # no trailing period
        "voice": "authoritative desk",
        "type": "mover",
        "cashtag": "$AMD",
        "ticker": "AMD",
        "entry_str": "",
        "t1_str": "",
        "t2_str": "",
        "inv_str": "",
        "direction": "BEAR",
        "gain_pct_str": "",
        "loss_pct_str": "",
        "stop_str": "",
        "target_label": "T1",
        "win_rate_str": "",
        "cashtag_list": "",
        "theme_name": "",
        "theme_direction": "",
        "theme_agg_pct": "",
        "theme_question": "",
        "mover_pct": "",
    }
    result = _render_template("{top_fact} Watching, not chasing.", ctx)
    assert ".." not in result, f"Double period found in: {result!r}"
    assert "today." in result, f"Period not appended: {result!r}"


def test_render_template_ellipsis_preserved():
    """'...' ellipsis in fact text must survive unchanged (not collapsed to '.')."""
    from engine.marketing.copywriter import _render_template
    ctx = {
        "top_fact_text": "AMD fell 6.2%...",  # ends with ellipsis
        "voice": "authoritative desk",
        "type": "mover",
        "cashtag": "$AMD",
        "ticker": "AMD",
        "entry_str": "",
        "t1_str": "",
        "t2_str": "",
        "inv_str": "",
        "direction": "BEAR",
        "gain_pct_str": "",
        "loss_pct_str": "",
        "stop_str": "",
        "target_label": "T1",
        "win_rate_str": "",
        "cashtag_list": "",
        "theme_name": "",
        "theme_direction": "",
        "theme_agg_pct": "",
        "theme_question": "",
        "mover_pct": "",
    }
    result = _render_template("{top_fact} Watching.", ctx)
    assert "..." in result, f"Ellipsis was collapsed: {result!r}"
    # The ellipsis itself is 3 periods and should remain untouched
    assert result.count("...") >= 1, f"Ellipsis count changed: {result!r}"


# ── LLM copy lane (mocked — never a live call in tests) ──────────────────────

def _llm_ctx():
    from engine.marketing.copywriter import build_context
    c = build_context(
        {"type": "mover", "ticker": "ISRG", "cashtag": "$ISRG", "account": "research_b"},
        persona={"name": "The Tape Reader", "voice_notes": "fast, clipped", "example_lines": ["$X up 4% 👀"]},
        facts={"facts": [{"text": "ISRG crashed -14.2% today (Healthcare), the biggest single-stock move in the index."}],
               "numbers_whitelist": ["-14.2%"]},
        extra=None,
    )
    c["voice"] = "fast, reactive"; c["type"] = "mover"
    return c


def test_llm_lane_disabled_without_env(monkeypatch):
    """Default (no MARKETING_LLM_ENABLED) → None, so tests/local never call out."""
    from engine.marketing.copywriter import write_posts_llm
    monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
    assert write_posts_llm([_llm_ctx()], {"llm": {"enabled": True}}) is None


def test_llm_lane_good_output_ships_as_llm(monkeypatch):
    import json as _j
    import engine.llm_auth as la
    from engine.marketing import copywriter as cw
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(la, "build_providers", lambda *a, **k: [{"name": "mock"}])
    good = _j.dumps([{"headline": "$ISRG just got smoked",
                      "body": "$ISRG cratered -14.2% today, worst move in the whole index. Overreaction? 👀"}])
    monkeypatch.setattr(la, "make_call", lambda p, d, context="": (good, None, "mock"))
    out = cw.write_posts_llm([_llm_ctx()], {"llm": {"enabled": True, "model_key": "marketing_copy"},
                                            "personas": {}, "copy_laws": []})
    assert out and out[0]["mode"] == "llm"
    assert "-14.2%" in out[0]["body"]


def test_llm_lane_bad_output_falls_back(monkeypatch):
    """Invented number + banned vocab → validator rejects → deterministic fallback."""
    import json as _j
    import engine.llm_auth as la
    from engine.marketing import copywriter as cw
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(la, "build_providers", lambda *a, **k: [{"name": "mock"}])
    bad = _j.dumps([{"headline": "$ISRG down 99%", "body": "buy now, guaranteed rebound $ISRG"}])
    monkeypatch.setattr(la, "make_call", lambda p, d, context="": (bad, None, "mock"))
    out = cw.write_posts_llm([_llm_ctx()], {"llm": {"enabled": True, "model_key": "marketing_copy"},
                                            "personas": {}, "copy_laws": []})
    assert out and out[0]["mode"] == "llm_fallback"


def test_llm_lane_no_provider_returns_none(monkeypatch):
    import engine.llm_auth as la
    from engine.marketing import copywriter as cw
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(la, "build_providers", lambda *a, **k: [])
    assert cw.write_posts_llm([_llm_ctx()], {"llm": {"enabled": True, "model_key": "marketing_copy"}}) is None


# ─────────────────────────────────────────────────────────────────────────────
# Clarity gate (2026-07-26 $AAPL incident)
# ─────────────────────────────────────────────────────────────────────────────
#
# The post below shipped on the flagship account and passed every gate the desk
# had. It is reproduced verbatim as the fixture so these tests cannot drift away
# from the actual defect:
#
#     Four up, near highs, VWAP holds
#     $AAPL -0.6% off the 52-week high at 334.99 and up four weeks straight.
#     That Jun 26 anchored VWAP has held for 20 sessions. I'm watching a close
#     below it, not chasing.
#
# Operator, on seeing it: "it doesn't even make sense. wtf is four up?"

_AAPL_HL = "Four up, near highs, VWAP holds"
_AAPL_BODY = (
    "$AAPL -0.6% off the 52-week high at 334.99 and up four weeks straight. "
    "That Jun 26 anchored VWAP has held for 20 sessions. I'm watching a close "
    "below it, not chasing."
)


def _aapl_ctx():
    return {
        "ticker": "AAPL", "type": "watchlist", "emoji_budget": 0,
        "numbers_whitelist": ["-0.6%", "334.99", "20", "26"],
    }


def test_the_incident_post_is_now_rejected():
    """Whole post, verbatim, through the real validator. Three separate defects."""
    from engine.marketing.copywriter import validate_copy
    violations = validate_copy(_AAPL_HL, _AAPL_BODY, _aapl_ctx())

    assert any("headless count" in v for v in violations), (
        f"'Four up' has no noun and nothing caught it: {violations}")
    assert any("vwap" in v.lower() for v in violations), (
        f"'VWAP' is a study name in public copy: {violations}")
    assert any("pronoun" in v for v in violations), (
        f"'a close below it' names no price: {violations}")


def test_study_names_are_banned_in_public_copy():
    """The M2 families, which the old ban list predated."""
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "", "type": "chart", "emoji_budget": 0, "numbers_whitelist": []}
    for term in ("VWAP holds", "anchored VWAP", "the POC", "point of control",
                 "value area low", "volume profile"):
        violations = validate_copy(f"Chart note: {term}", "Watching.", ctx)
        assert any("banned vocab" in v for v in violations), (
            f"{term!r} shipped clean: {violations}")


def test_plain_language_rewrite_of_the_incident_is_clean():
    """The gate must ACCEPT the honest version, or it just blocks the lane.

    Same facts, same stance, same terseness. The only difference is that a
    stranger can read it: the count has its noun, the level has its price, and
    the line is described instead of named.
    """
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "AAPL", "type": "watchlist", "emoji_budget": 0,
        "numbers_whitelist": ["-0.6%", "334.99", "328.40", "20", "26"],
    }
    headline = "$AAPL is still holding the line"
    body = (
        "$AAPL is -0.6% off its 52-week high and up four weeks straight. It has "
        "stayed above 328.40, the average price paid since the Jun 26 volume "
        "spike, for 20 sessions. A close under that changes my mind."
    )
    assert validate_copy(headline, body, ctx) == []


def test_house_voice_survives_the_clarity_gate():
    """The exemplars in the prompt and copy_laws must not be self-rejecting."""
    from engine.marketing.copywriter import validate_copy
    ctx = {"ticker": "ISRG", "type": "mover", "emoji_budget": 0,
           "numbers_whitelist": ["-14.2%"]}
    violations = validate_copy(
        "$ISRG down 14.2% today",
        "The dip buyers get to find out who was early. Watching for a bottom "
        "setup, not catching it yet.",
        ctx)
    clarity = [v for v in violations if "headless" in v or "pronoun" in v]
    assert not clarity, f"the gate rejects the house exemplar: {clarity}"


def test_llm_lane_unreadable_output_falls_back(monkeypatch):
    """End to end: the incident copy comes back from the model and the lane
    drops it for the deterministic floor instead of posting it."""
    import json as _j
    import engine.llm_auth as la
    from engine.marketing import copywriter as cw
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(la, "build_providers", lambda *a, **k: [{"name": "mock"}])
    bad = _j.dumps([{"headline": "Four up, near highs, VWAP holds",
                     "body": "$ISRG has held it for 20 sessions. Watching a "
                             "close below it, not chasing."}])
    monkeypatch.setattr(la, "make_call", lambda p, d, context="": (bad, None, "mock"))
    out = cw.write_posts_llm(
        [_llm_ctx()], {"llm": {"enabled": True, "model_key": "marketing_copy"},
                       "personas": {}, "copy_laws": []})
    assert out and out[0]["mode"] == "llm_fallback"


def test_clarity_law_reaches_the_model(monkeypatch):
    """A rule the writer is never told is a rule it will keep breaking. Assert
    the cold-read law and the worked example are actually in the system prompt."""
    import json as _j
    import engine.llm_auth as la
    from engine.marketing import copywriter as cw
    seen: dict = {}
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(la, "build_providers", lambda *a, **k: [{"name": "mock"}])

    class _Resp:
        content = []
        stop_reason = None

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                seen.update(kw)
                return _Resp()

    def _make_call(providers, do_call, context=""):
        return do_call(_Client(), "mock-model")

    monkeypatch.setattr(la, "make_call", _make_call)
    cw.write_posts_llm([_llm_ctx()],
                       {"llm": {"enabled": True, "model_key": "marketing_copy"},
                        "personas": {}, "copy_laws": []})
    prompt = seen.get("system", "")
    assert "COLD-READ TEST" in prompt
    assert "Four up" in prompt, "the worked negative example is missing"
    assert "A level with no number is not a level" in prompt


def test_determiner_this_is_not_a_dangling_level():
    """"walk through this chart" is a noun phrase, not a level reference. Found
    by auditing the template library, which is what rejected posts fall back to."""
    from engine.marketing.copywriter import dangling_levels
    assert dangling_levels("$AAPL, walk through this chart with me") == []
    assert dangling_levels("A break below that level someday") == []
    # Still fires when the pronoun really is bare.
    assert dangling_levels("A close under that changes my mind")
    assert dangling_levels("Watching a close below it")


def test_every_fallback_template_survives_the_clarity_gate():
    """THE GATE MUST NEVER REJECT BOTH SIDES.

    A clarity violation drops the post to the deterministic floor, so if the
    floor itself could trip the gate, a rejected post would have nowhere to land
    and the lane would go quiet. Every template in the copywriter's variant
    library is rendered and checked, so adding an unreadable template fails here
    rather than in production.
    """
    import re as _re
    from engine.marketing.copywriter import (
        _BANNED_SUBSTRINGS, _BANNED_VOCAB, _TEMPLATES,
        dangling_levels, headless_counts,
    )
    subs = {
        "{cashtag}": "$AAPL", "{ticker}": "AAPL", "{entry}": "328.40",
        "{t1}": "350.00", "{inv}": "310.00", "{stop}": "310.00",
        "{win_rate}": "78%", "{mover_pct}": "-14.2%", "{gain_pct}": "+6.2%",
        "{loss_pct}": "-3.1%", "{theme_name}": "solar",
        "{cashtag_list}": "$A $B $C $D",
        "{top_fact}": ("AAPL has held 307.03, the average price paid since the "
                       "Jun 26 volume spike, for 20 straight sessions"),
    }
    checked, bad = 0, []

    def walk(node):
        nonlocal checked
        if isinstance(node, str):
            t = node
            for k, val in subs.items():
                t = t.replace(k, val)
            t = _re.sub(r"\{[a-z_0-9]+\}", "300.00", t)   # any remaining slot
            checked += 1
            for clause in headless_counts(t):
                bad.append(f"headless {clause!r} in {node[:60]!r}")
            for sent in dangling_levels(t):
                bad.append(f"dangling {sent[:50]!r} in {node[:60]!r}")
            low = t.lower()
            for w in _BANNED_VOCAB:
                if _re.search(rf"\b{_re.escape(w)}\b", low):
                    bad.append(f"vocab {w!r} in {node[:60]!r}")
            for p in _BANNED_SUBSTRINGS:
                if p in low:
                    bad.append(f"phrase {p!r} in {node[:60]!r}")
        elif isinstance(node, (list, tuple)):
            for y in node:
                walk(y)
        elif isinstance(node, dict):
            for y in node.values():
                walk(y)

    walk(_TEMPLATES)
    # content_studio keeps its OWN per-voice library, separate from the one
    # above. Auditing only copywriter's missed two false positives in it.
    from engine.marketing.content_studio import _COPY_TEMPLATES
    walk(_COPY_TEMPLATES)
    assert checked > 100, f"only {checked} templates walked — guard is vacuous"
    assert not bad, "deterministic fallback copy trips the gate:\n" + "\n".join(bad)


def test_weekend_levels_floor_survives_the_clarity_gate():
    """Same contract for the weekend lane, which has its own floor library."""
    from engine.marketing.copywriter import dangling_levels, headless_counts
    from engine.marketing.weekend_levels import _FRAMES, _HEADLINES, _TAILS

    checked, bad = 0, []
    frames = [f.replace("{wk}", "up 3% on the week")
               .replace("{wk_cap}", "Up 3% on the week")
               .replace("{s20}", "328.40").replace("{s50}", "310.25")
               .replace("{lo}", "204.10").replace("{px}", "334.99")
              for pool in _FRAMES.values() for f in pool]
    heads = [h.replace("$T", "$AAPL") for pool in _HEADLINES.values() for h in pool]
    for t in frames + heads + list(_TAILS):
        checked += 1
        for clause in headless_counts(t):
            bad.append(f"headless {clause!r} in {t[:60]!r}")
        for sent in dangling_levels(t):
            bad.append(f"dangling {sent[:50]!r} in {t[:60]!r}")
    assert checked > 50, f"only {checked} floor strings walked — guard is vacuous"
    assert not bad, "weekend floor copy trips the gate:\n" + "\n".join(bad)


# ─────────────────────────────────────────────────────────────────────────────
# Clarity gate on the copy that NEVER reaches validate_copy
#
# Two marketing lanes build their post text inline and ship it as written:
#
#   - confluence signal posts — content_studio's copywriter pass matches
#     `source == "confluence"` and `continue`s before any check runs, so
#     win_rate_hook's output is the shipped copy verbatim.
#   - mover / theme_list posts — the pass does call validate_copy on them, but
#     only records the result on the item (`_copy_violations`) and ships the
#     copy anyway; the call also sits inside a bare `except` that turns any
#     failure into "no violations".
#
# Neither lane can be broken by the gate, so nothing stops a future edit from
# reintroducing the 2026-07-26 $AAPL defect class (an unreadable stat, a level
# named only by pronoun) on the flagship account. These guards apply the gate's
# content checks to that copy in CI instead.
# ─────────────────────────────────────────────────────────────────────────────

def _clarity_gate_violations(text: str) -> list[str]:
    """The content checks validate_copy applies, run directly against `text`.

    The same four the PR #3744 template guards walk: headless counts, dangling
    levels, banned vocab (word-boundary) and banned substrings. Structural
    checks (length, cashtag rules, whitelist) are deliberately not here — they
    depend on a build_context() the inline lanes never construct.
    """
    import re as _re
    from engine.marketing.copywriter import (
        _BANNED_SUBSTRINGS, _BANNED_VOCAB, dangling_levels, headless_counts,
    )
    out: list[str] = []
    for clause in headless_counts(text):
        out.append(f"headless count {clause!r}")
    for sentence in dangling_levels(text):
        out.append(f"level named only by pronoun: {sentence[:60]!r}")
    low = text.lower()
    for word in _BANNED_VOCAB:
        if _re.search(rf"\b{_re.escape(word)}\b", low):
            out.append(f"banned vocab {word!r}")
    for phrase in _BANNED_SUBSTRINGS:
        if phrase in low:
            out.append(f"banned phrase {phrase!r}")
    return out


def test_clarity_gate_helper_actually_fires():
    """The helper both guards below depend on must be able to FAIL.

    A checker that silently returns [] would make every assertion under it
    vacuous while still reading green, so pin one string per check.
    """
    assert _clarity_gate_violations("Four up. Nothing else to say.")
    assert _clarity_gate_violations("It has held for 20 sessions. Watching a close below it.")
    assert _clarity_gate_violations("VWAP holds and the trend is intact.")      # _BANNED_VOCAB
    assert _clarity_gate_violations("The signal stack lit up again today.")     # _BANNED_SUBSTRINGS
    # And it must stay quiet on copy that is actually clean.
    assert _clarity_gate_violations(
        "$AAPL has held 307.03 for 20 straight sessions. A close under that changes my mind."
    ) == []


def _confluence_hook_signals() -> list[dict]:
    """Fired-combo dicts covering every branch of win_rate_hook's f-strings.

    Shape matches fired_combo_signals() output. The forks are the observation
    span ("over the past N years" / "over the past year" / "across its
    history", including the unparsable-date fallback), the side (higher /
    lower) and the optional "N in the last 3 years" clause.
    """
    from itertools import product
    spans = (
        ("2019-03-04", "2026-07-24"),   # multi-year span
        ("2025-08-12", "2026-07-24"),   # ~1 year
        ("2026-07-01", "2026-07-24"),   # under a year → "across its history"
        ("", ""),                       # unparsable → "across its history"
    )
    tickers = ("VST", "BKR", "NVDA", "GE")
    out: list[dict] = []
    for i, ((first, last), side, fires3y) in enumerate(
        product(spans, ("long", "short"), (0, 7))
    ):
        out.append({
            "ticker": tickers[i % len(tickers)],
            "combo_id": f"L{i:04d}",
            "combo_name": "MACD Stack + Golden Cross",   # internal only, never in copy
            "win_rate": 86.5 - i,
            "edge": 29.6,
            "n_fires": 107,
            "fires_last3y": fires3y,
            "last_fire": last,
            "first_fire": first,
            "legs_plain": ["Golden Cross (7/35)", "RSI Stack (7/14/21)"],
            "leg_families": ["ma_crosses"],
            "side": side,
            "n_test": 25,
            "months_test": 17,
            "_score": 0.5,
        })
    return out


def test_confluence_hook_copy_survives_the_clarity_gate():
    """The confluence lane ships win_rate_hook's copy with NO gate in front of it.

    content_studio appends the ContentItem straight to the queue and the
    copywriter pass skips it by source, so whatever this function returns is
    what posts. Every branch of its f-strings is rendered here and checked, so
    an unreadable edit fails in CI rather than on the flagship account.
    """
    from engine.marketing.confluence_source import win_rate_hook

    checked, bad = 0, []
    spans_seen, directions_seen = set(), set()
    for sig in _confluence_hook_signals():
        headline, body = win_rate_hook(sig)
        assert headline and body, f"hook returned empty copy for {sig['combo_id']}"
        checked += 1
        for v in _clarity_gate_violations(f"{headline} {body}"):
            bad.append(f"{v} in {sig['combo_id']} ({sig['side']}): {headline!r} {body!r}")
        for phrase in ("over the past", "across its history"):
            if phrase in body:
                spans_seen.add(phrase)
        for word in ("higher", "lower"):
            if word in body:
                directions_seen.add(word)

    assert checked >= 16, f"only {checked} hooks rendered — guard is vacuous"
    assert spans_seen == {"over the past", "across its history"}, (
        f"span branches not all exercised: {spans_seen}"
    )
    assert directions_seen == {"higher", "lower"}, (
        f"both sides must be exercised, saw {directions_seen}"
    )
    assert not bad, "unvalidated confluence copy trips the gate:\n" + "\n".join(bad)


# Two heatmap tapes. Between them the mover branch renders both of its stance
# forks (down = flush-watch, up = respect) over all three mover_facts verbs that
# survive the |pct| >= 3 eligibility floor (crashed <= -5, fell, surged), and the
# theme branch renders both tones with a question from each pool.
_MOVER_TAPES: tuple[tuple[list, list], ...] = (
    (
        [("NVDA", -14.2), ("AVGO", 12.6), ("MU", -3.4), ("AMD", 4.1)],
        [("Artificial Intelligence", {"AIA": -6.2, "AIB": -5.1, "AIC": -4.4, "AID": -3.9, "AIE": -1.2}),
         ("Quantum Computing", {"QCA": 7.8, "QCB": 6.4, "QCC": 5.1, "QCD": 4.0, "QCE": 2.2})],
    ),
    (
        [("XOM", -4.1), ("SMCI", 3.6), ("KO", -3.1)],
        [("Nuclear Renaissance", {"NRA": 4.4, "NRB": 3.9, "NRC": 3.1, "NRD": 2.8}),
         ("Regional Banks", {"RBA": -3.3, "RBB": -2.9, "RBC": -2.4, "RBD": -1.8})],
    ),
)


def _movers_desk_items(monkeypatch, tmp_path, tiles, themes) -> list[dict]:
    """Run content_plan over one heatmap tape and return its movers_desk items.

    The real content_plan is driven end-to-end so the assertions land on the
    f-strings content_studio actually ships, not on a copy of them. The
    watchlist card is stubbed: render_watchlist_card resolves member logos over
    the network, which a test must never do (~0.7s per member, and flaky).
    """
    import json
    import engine.marketing.chart_render as cr

    monkeypatch.setattr(cr, "render_watchlist_card", lambda *a, **k: "<svg></svg>")

    md = tmp_path / "site" / "marketdata"
    md.mkdir(parents=True, exist_ok=True)
    # asof is a PINNED LITERAL. It used to read date.today() with a comment
    # claiming "the mover lane's session-staleness law refuses to build 'today'
    # claims from a non-today session". THAT LAW IS NOT ON THIS PATH — it is the
    # publish-time lane's (publish_time_content._tape_stale / _cand_session,
    # which this fixture never enters). The nightly content_studio movers block
    # reads the heatmap and builds; nothing in it compares `asof` to a clock.
    # Mutation-checked: pinning the date leaves every assertion below green, so
    # the comment was describing a gate that does not exist and the wall-clock
    # read was a nondeterminism the fixture did not need.
    #
    # The real load-bearing facts about this fixture are stated at the cfg below
    # (two desks, so the reach items find free D1 rungs) and at the closes_loader
    # (a mover cannot be seated without a card).
    (md / "sp500_heatmap.json").write_text(json.dumps({
        "asof": "2026-07-31",
        "tiles": [{"t": t, "name": t, "sector": "Information Technology",
                   "perf": {"1D": pct}} for t, pct in tiles],
    }), encoding="utf-8")
    (md / "themes_heatmap.json").write_text(json.dumps({
        "tiles": [{"t": name[:3].upper(), "name": name, "sector": name,
                   "perf": {"1D": 0.0},
                   "members": [{"t": t, "perf": {"1D": p}} for t, p in members.items()]}
                  for name, members in themes],
    }), encoding="utf-8")

    from engine.marketing.content_studio import content_plan
    # Two desks, not one: reach items seat on REAL free D1 rungs since the
    # 2026-07-31 slot fix, and a single desk carrying an entire day's planned
    # queue legitimately exhausts its ladder (drop is designed + counted as
    # content.movers.unseated). Production runs 6+ desks; two is the smallest
    # fixture that seats all four stance/tone forks this test asserts on.
    cfg = {"desk_network": {"stage": "A", "accounts": [
        {"id": "flagship", "kind": "branded", "beat": "What changed",
         "voice": "authoritative desk"},
        {"id": "founder", "kind": "personal", "beat": "Conviction and cost",
         "voice": "dry, receipts-forward"},
    ]}}
    # A MOVER WITHOUT A CARD IS NOT A POST. `mover` is a bare-cashtag kind, so a
    # chartless one is terminally quarantined at dispatch — content_studio's
    # card-less unseat pass (2026-07-31) therefore drops it from the queue before
    # the plan is returned. `closes_loader=None` means no mover card can render,
    # which means ZERO mover items come back and the `len(movers) >= 4` assertion
    # below would be testing the absence of the lane. Synthetic bars are the
    # cheapest way to let the card path complete.
    def _closes(_ticker: str):
        return ([f"2026-06-{d:02d}" for d in range(1, 31)],
                [100.0 + i * 0.5 for i in range(30)])

    plan = content_plan(cfg, [], closes_loader=_closes, root=tmp_path)
    return [it for row in plan["accounts"] for it in row["queue"]
            if isinstance(it, dict) and it.get("provenance") == "movers_desk"]


def test_mover_and_theme_copy_survives_the_clarity_gate(monkeypatch, tmp_path):
    """The mover/theme lane's copy is recorded against the gate, never blocked by it.

    content_studio builds these headlines and bodies inline from f-strings plus
    movers_source facts, then keeps them whatever validate_copy says. Driving
    content_plan over two heatmap tapes renders the real strings for both
    stance forks and both tones, so an unreadable edit to that block fails
    here.
    """
    items: list[dict] = []
    for i, (tiles, themes) in enumerate(_MOVER_TAPES):
        items += _movers_desk_items(monkeypatch, tmp_path / f"tape{i}", tiles, themes)

    bad = []
    for it in items:
        text = f"{it.get('headline', '')} {it.get('body', '')}"
        for v in _clarity_gate_violations(text):
            bad.append(f"{v} in {it.get('slot', '?')}: {text!r}")

    movers = [it for it in items if it.get("type") == "mover"]
    themes_out = [it for it in items if it.get("type") == "theme_list"]
    assert len(items) >= 8, f"only {len(items)} movers_desk posts built — guard is vacuous"
    assert len(movers) >= 4, f"only {len(movers)} mover posts built — guard is vacuous"
    assert len(themes_out) >= 4, f"only {len(themes_out)} theme posts built — guard is vacuous"
    # Both stance forks of the mover body, and both tones of the theme headline.
    assert {(it["_mover_data"]["pct"] < 0) for it in movers} == {True, False}, (
        "both mover stance forks (down/up) must be exercised"
    )
    assert {it["_theme_data"]["direction"] for it in themes_out} == {"down", "up"}, (
        "both theme directions must be exercised"
    )
    assert not bad, "unvalidated mover/theme copy trips the gate:\n" + "\n".join(bad)


def test_every_movers_desk_question_survives_the_clarity_gate():
    """Both reply-bait pools land verbatim in theme bodies — walk all of them.

    A single content_plan run only reaches the tails its theme names hash to,
    so the pools are walked directly to cover the ones the tapes miss.

    Renamed from _QUESTION_* to _TAIL_* on 2026-07-31, when the reply-bait
    pools were replaced by stance / watch-condition tails (see movers_source:
    a question aimed at the READER costs the author nothing). The clarity gate
    is unchanged and every line still has to pass it.
    """
    from engine.marketing.movers_source import _TAIL_DOWN, _TAIL_UP

    pools = list(_TAIL_DOWN) + list(_TAIL_UP)
    bad = [f"{v} in {q!r}" for q in pools for v in _clarity_gate_violations(q)]
    assert len(pools) >= 8, f"only {len(pools)} tails walked — guard is vacuous"
    assert not bad, "movers-desk tails trip the gate:\n" + "\n".join(bad)


def test_through_is_not_treated_as_a_level_preposition():
    """"walk you through this" and "followed through this time" are phrasal, not
    level references. Both were false positives in content_studio's template
    library, which is a separate library from the copywriter's."""
    from engine.marketing.copywriter import dangling_levels
    assert dangling_levels("$AAPL, let me walk you through this") == []
    assert dangling_levels("Here's whether it followed through this time") == []
    assert dangling_levels("We'll see it through") == []
    # The prepositions that really do introduce a price still fire.
    assert dangling_levels("Watching a close below it")
    assert dangling_levels("A close under that changes my mind")
    assert dangling_levels("It has to get back above that first")


# ─────────────────────────────────────────────────────────────────────────────
# Ticker-free watchlist floor + the headline fragment screen
#
# The defect: a planner-scheduled watchlist post is a NON-ticker content type
# (content_studio gives it breadth + sector facts and ticker ""), but every
# watchlist template variant was written around {cashtag}. _render_template
# substituted the empty string and the fragments shipped — "is close",
# "Circling", "Radar check on", "close to going", "on my radar this week",
# "watching, not acting" — each queued with _copy_violations: [], because
# validate_copy's cashtag law is gated on `if ticker:` and nothing else looked
# at the SHAPE of a headline.
#
# Two independent guards, so neither half can rot alone:
#   - _variant_allowed partitions each bank by ticker-dependency, derived from
#     the template text (a new variant cannot forget to declare it);
#   - headline_fragments screens the rendered result, so any OTHER route to a
#     fragment (an LLM line, a future empty slot) is caught at validate time.
# ─────────────────────────────────────────────────────────────────────────────

_WATCHLIST_VOICES = (
    "authoritative desk", "dry, receipts-forward", "specialist",
    "educational", "fast, reactive", "pattern/history",
)

# The observed queue damage, verbatim from data/marketing/content_plan.json.
_SHIPPED_FRAGMENTS = (
    "is close",
    "Circling",
    "Radar check on",
    "close to going",
    "on my radar this week",
    "watching, not acting",
)

# Per-voice watchlist bank size BEFORE the ticker-free lines were appended.
# Pinned so that adding a ticker-free variant without teaching _variant_allowed
# about it fails here instead of silently enlarging the ticker-bearing pool and
# reshuffling every hash-assigned publish-time post.
_WATCHLIST_TICKER_POOL_SIZES = {
    "authoritative desk": 5,
    "dry, receipts-forward": 4,
    "specialist": 4,
    "educational": 4,
    "fast, reactive": 4,
    "pattern/history": 4,
}


def _breadth_facts() -> dict:
    """The fact shape content_studio attaches to a no-ticker watchlist item."""
    return {
        "facts": [{
            "id": "breadth",
            "text": ("62 of 500 names in the S&P universe are showing bullish "
                     "momentum setups right now."),
            "salience": 1,
            "numbers": ["62", "500"],
        }],
        "numbers_whitelist": ["62", "500"],
    }


def _no_ticker_watchlist_ctx(voice: str, as_of: str = "2026-07-28") -> dict:
    """A planner-scheduled watchlist context: breadth facts, ticker ""."""
    from engine.marketing.copywriter import build_context
    item = {"ticker": "", "type": "watchlist", "account": "acct_w", "as_of": as_of}
    ctx = build_context(
        item,
        persona={"name": "The Desk", "voice_notes": "Emoji budget: 0", "example_lines": []},
        facts=_breadth_facts(),
    )
    ctx["type"] = "watchlist"
    ctx["voice"] = voice
    ctx["as_of"] = as_of
    return ctx


def _uses_ticker_token(variant: tuple) -> bool:
    """The exact token rule _variant_allowed applies, re-derived from its data."""
    from engine.marketing.copywriter import _TICKER_DEPENDENT_TOKENS
    return any(tok in variant[0] or tok in variant[1]
               for tok in _TICKER_DEPENDENT_TOKENS)


def test_no_ticker_watchlist_renders_a_whole_sentence_in_every_voice():
    """THE REGRESSION. A watchlist post with no ticker must render complete copy.

    Three consecutive dates per voice so the day-ordinal rotation reaches every
    ticker-free variant in the bank, not just the one today happens to land on.
    """
    from engine.marketing.copywriter import write_posts_deterministic

    seen: set[str] = set()
    for voice in _WATCHLIST_VOICES:
        for as_of in ("2026-07-27", "2026-07-28", "2026-07-29"):
            ctx = _no_ticker_watchlist_ctx(voice, as_of)
            post = write_posts_deterministic([ctx])[0]
            hl, body = post["headline"], post["body"]
            seen.add(hl)
            assert len(hl.split()) >= 2, f"{voice} {as_of}: fragment headline {hl!r}"
            assert not ("a" <= hl[:1] <= "z"), (
                f"{voice} {as_of}: headline opens lowercase (empty leading slot): {hl!r}"
            )
            assert "{" not in hl and "{" not in body, (
                f"{voice} {as_of}: unrendered slot in {hl!r} / {body!r}"
            )
            assert post["violations"] == [], (
                f"{voice} {as_of}: {post['violations']} on {hl!r}"
            )
    # 6 voices x 3 ticker-free variants, all distinct — a rotation that collapsed
    # onto one variant would still satisfy every assertion above.
    assert len(seen) == 18, f"expected 18 distinct headlines, got {len(seen)}: {sorted(seen)}"


def test_headline_fragments_catches_every_shipped_fragment():
    """Each of the six headlines that actually queued must now be rejected."""
    from engine.marketing.copywriter import headline_fragments
    for hl in _SHIPPED_FRAGMENTS:
        assert headline_fragments(hl), f"fragment not caught: {hl!r}"
    assert headline_fragments("") and headline_fragments("   ")


def test_headline_fragments_clean_on_the_whole_curated_bank():
    """THE GATE MUST NEVER REJECT THE FLOOR.

    A fragment violation drops the post to the deterministic floor, so a floor
    headline that trips the screen would leave a rejected post with nowhere to
    land. Every variant in every bank is rendered with a fully-populated context
    and must come back clean — this is what pins the tail-word list's exclusions
    (terminal "this"/"that", stranded "to"/"in") to real house copy.
    """
    from engine.marketing.copywriter import (
        _TEMPLATES, _render_template, headline_fragments,
    )
    ctx = {
        "cashtag": "$AAPL", "ticker": "AAPL", "entry_str": "328.40",
        "t1_str": "350.00", "t2_str": "365.00", "inv_str": "310.00",
        "stop_str": "310.00", "gain_pct_str": "+6.2%", "loss_pct_str": "-3.1%",
        "win_rate_str": "78%", "target_label": "T1", "direction": "BULL",
        "top_fact_text": "AAPL has held 307.03 for 20 straight sessions",
        "cashtag_list": "$NVDA $AMD $SMCI $ON",
        "theme_name": "Artificial Intelligence", "theme_direction": "down",
        "theme_agg_pct": "-3.4%", "theme_question": "Which one holds?",
        "mover_pct": "-14.2%", "voice": "authoritative desk", "type": "chart",
    }
    checked, bad = 0, []
    for key, bank in _TEMPLATES.items():
        for variant in bank:
            checked += 1
            rendered = _render_template(variant[0], ctx)
            for f in headline_fragments(rendered):
                bad.append(f"{key} {variant[0]!r} -> {rendered!r}: {f}")
    assert checked > 100, f"only {checked} headlines walked — guard is vacuous"
    assert not bad, "curated headlines trip the fragment screen:\n" + "\n".join(bad)


def test_variant_allowed_partitions_watchlist_banks_by_ticker():
    """No-ticker contexts get only ticker-free lines; ticker contexts get only
    the pre-change bank, so no hash-assigned post moves."""
    from engine.marketing.copywriter import _TEMPLATES, _variant_allowed

    for voice in _WATCHLIST_VOICES:
        bank = _TEMPLATES[("watchlist", voice)]

        free_pool = [v for v in bank if _variant_allowed(v, _no_ticker_watchlist_ctx(voice))]
        assert free_pool, f"{voice}: no-ticker pool is empty"
        assert all(not _uses_ticker_token(v) for v in free_pool), (
            f"{voice}: ticker-dependent variant offered to a no-ticker context: "
            f"{[v[0] for v in free_pool if _uses_ticker_token(v)]}"
        )

        ticker_ctx = {"type": "watchlist", "ticker": "AAPL", "voice": voice}
        ticker_pool = [v for v in bank if _variant_allowed(v, ticker_ctx)]
        assert ticker_pool == [v for v in bank if _uses_ticker_token(v)], (
            f"{voice}: ticker pool is not exactly the pre-change bank"
        )
        assert len(ticker_pool) == _WATCHLIST_TICKER_POOL_SIZES[voice], (
            f"{voice}: ticker pool moved from "
            f"{_WATCHLIST_TICKER_POOL_SIZES[voice]} to {len(ticker_pool)} — "
            "every hash-assigned publish-time watchlist post just reshuffled"
        )
        # The two pools partition the bank: nothing is orphaned, nothing doubled.
        assert len(free_pool) + len(ticker_pool) == len(bank)


def test_every_no_ticker_planning_type_has_a_ticker_free_floor():
    """Types the planner schedules WITHOUT a ticker need real lines to fall back
    on. Three is the floor: fewer and the day-ordinal rotation starts repeating
    the same headline inside a week."""
    from engine.marketing.copywriter import _TEMPLATES

    thin = []
    for (type_id, voice), bank in _TEMPLATES.items():
        if type_id not in ("watchlist", "education", "macro", "event"):
            continue
        free = [v for v in bank if not _uses_ticker_token(v)]
        if len(free) < 3:
            thin.append(f"{type_id}/{voice}: only {len(free)} ticker-free of {len(bank)}")
    assert not thin, "no-ticker planning banks below the floor:\n" + "\n".join(thin)


def test_validate_copy_flags_a_fragment_headline():
    """End to end: the exact shipped pair now comes back with a violation."""
    from engine.marketing.copywriter import validate_copy
    violations = validate_copy(
        "is close",
        "Near the level I care about.",
        _no_ticker_watchlist_ctx("authoritative desk"),
    )
    assert any("fragment" in v for v in violations), violations
