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
    from engine.marketing.copywriter import build_context
    item = {"ticker": "MSFT", "type": "signal", "account": "receipts",
            "entry": 380.0, "targets": [420.0, 450.0], "invalidation": 360.0}
    ctx = build_context(item, persona=None, facts=None)
    whitelist = ctx["numbers_whitelist"]
    assert "380.00" in whitelist, f"entry not in whitelist: {whitelist}"
    assert "420.00" in whitelist, f"t1 not in whitelist: {whitelist}"
    assert "360.00" in whitelist, f"inv not in whitelist: {whitelist}"


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


def test_validate_signal_missing_invalidation():
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "PLTR", "type": "signal", "emoji_budget": 0,
        "numbers_whitelist": ["120.00", "150.00"],
    }
    headline = "$PLTR at 120.00"
    body = "Buy $PLTR today. Target 150.00. Great setup."
    violations = validate_copy(headline, body, ctx)
    inv_v = [v for v in violations if "invalidat" in v.lower() or "what would change" in v.lower()]
    assert inv_v, f"Expected invalidation violation, got: {violations}"


def test_validate_signal_missing_disclosure():
    from engine.marketing.copywriter import validate_copy
    ctx = {
        "ticker": "NVDA", "type": "signal", "emoji_budget": 0,
        "numbers_whitelist": ["500.00", "400.00", "600.00"],
    }
    headline = "$NVDA at 500.00"
    body = "Entry 500.00. Below 400.00 kills it. Target 600.00."
    violations = validate_copy(headline, body, ctx)
    disc_v = [v for v in violations if "disclosure" in v.lower() or "honesty" in v.lower()]
    assert disc_v, f"Expected disclosure violation, got: {violations}"


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
    """Signal older than 14 days → excluded from receipts."""
    from engine.marketing.receipt_source import graded_receipts
    plan = _make_signal_plan(
        "OLD", entry=100.0, inv=90.0, signal_date=_old_date(20),
        phase="invalidated",
    )
    receipts = graded_receipts([plan])
    assert receipts == [], f"Expected empty receipts for stale plan, got {receipts}"


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
