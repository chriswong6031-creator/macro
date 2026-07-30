"""tests/test_marketing_selection.py — Content Studio W1 selection layer (Builder B).

Every test here is keyed to a §0 acceptance gate of
`research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md` (operator
directive 2026-07-29, after the 65-post outbox batch was aborted at D1-S15), and
to the B-list of `research/marketing_dockets/CONTENT_STUDIO_W1_BUILD_CONTRACT.md`:

  * cooldown            — LKFN posted yesterday is ineligible today (gate 3c);
                          a |move| >= 4% re-opens it, with the reason threaded
  * reuse budget        — ARES on a 3rd account is refused, and a 2nd SIGNAL
                          account is refused (gate 3b)
  * degenerate stat     — "231 of 231" carries no information and is dropped
                          (gate 3h)
  * shape mixer         — corpus quotas, deterministic, no RNG (gate 4)
  * emit refusal        — a planned-kind item with no model copy does not queue
                          while copywriter.llm.required is on (gate 1)
  * expiry              — a planned item 36h past its slot is quarantined
  * auto-approve scope  — a planned kind waits for the operator; a publish-time
                          mover still clears (masterplan §7)

LANE PURITY. Nothing here imports `anthropic`, opens a socket, or reaches the
network: the writer is a stub injected by monkeypatching
`copywriter.write_posts_llm_v2`, and every ledger read/write happens under
tmp_path. The marketing-engine CI lane installs pytest + pyyaml and nothing
else, which is exactly the environment this file must pass in.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()

# Wed 2026-07-29 is the plan date; Tue 07-28 is "yesterday"; Fri 07-24 is four
# calendar days but only THREE sessions back. Weekday-pinned on purpose — a
# fixture that drifts onto a weekend silently changes what the cooldown means
# (memory: fixture-date-plus-wall-clock-gate-bomb).
_TODAY = "2026-07-29"      # Wednesday
_YESTERDAY = "2026-07-28"  # Tuesday
_FRIDAY = "2026-07-24"     # Friday
_FIXED_NOW = datetime(2026, 7, 29, 6, 0, 0, tzinfo=timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — a synthetic outbox under tmp_path (items.jsonl + status_ledger.jsonl)
# ─────────────────────────────────────────────────────────────────────────────

#: Deeply distinct fixture copy, one line per ticker. A trivially-indexed
#: "$X did something today" bank collides with itself at token-Jaccard 0.7 and
#: enqueue() rejects the second seed as a near-duplicate — the fixture would then
#: be testing the dedup guard instead of the cooldown (same trap
#: tests/test_marketing_outbox.py's _DISTINCT_TEXTS documents).
_SEED_TEXTS: dict[str, str] = {
    "LKFN": "Regional lenders quietly caught a bid while everyone watched semis.",
    "GPI": "Auto retail margins held up better than the sell-side modeled.",
    "CBOE": "Volume records keep printing at the exchanges, nobody cares yet.",
    "ARES": "Private credit spreads tightened again into month end.",
    "FDS": "Data vendors are pricing like software, growing like utilities.",
    "TEL": "Connector demand tracks factory automation, not phone cycles.",
    "AAPL": "Services revenue is the whole story and it did not slow down.",
    "MSFT": "Cloud capex guidance moved more than the earnings line did.",
    "AMD": "Accelerator share gains are real but the base rate is brutal.",
    "PLTR": "Government renewals landed early, which almost never happens.",
    "TSLA": "Energy storage margins outran the auto business for a quarter.",
    "NVDA": "Supply is the constraint, demand has not been the question.",
}

#: Legal walk to a terminal-ish status (TRANSITIONS forbids queued -> posted).
_STATUS_PATH: dict[str, tuple[str, ...]] = {
    "queued": (),
    "approved": ("approved",),
    "posting": ("approved", "posting"),
    "posted": ("approved", "posted"),
    "quarantined": ("quarantined",),
}


def _seed_item(tmp_path: Path, *, ticker: str, as_of: str, kind: str = "watchlist",
               account: str = "flagship", text: str | None = None,
               status: str | None = None, scheduled_at: str = "immediate",
               provenance: str = "content_studio") -> str:
    """Enqueue one outbox item through the CANONICAL path and return its id.

    Written with make_item/enqueue/transition rather than hand-rolled JSONL so
    the fixture exercises the same schema and the same status machine the
    nightly does — a hand-built row that drifts from make_item would make these
    tests pass against a shape that does not exist in production.
    """
    from engine.marketing.outbox import make_item, enqueue, transition
    item = make_item(
        account=account,
        kind=kind,
        text=text or _SEED_TEXTS.get(ticker, f"${ticker} tape note for the fixture."),
        as_of=as_of,
        scheduled_at=scheduled_at,
        slot="D1-S1",
        provenance=provenance,
        source={"ticker": ticker},
        now=_FIXED_NOW,
    )
    assert enqueue(item, root=tmp_path, max_per_account_day=99) == "queued"
    for step in _STATUS_PATH[status or "queued"]:
        assert transition(item["id"], step, actor="test", root=tmp_path,
                          now=_FIXED_NOW), f"illegal fixture walk to {status}"
    return item["id"]


def _plan_item(**over) -> dict:
    """A content-plan queue item with the W1 stamps present by default."""
    base = {
        "id": "post-flagship-001",
        "type": "signal",
        "account": "flagship",
        "cashtag": "$PLTR",
        "ticker": "PLTR",
        "headline": "",
        "body": "PLTR at 120 and I am watching the retest, not chasing it.",
        "provenance": "content_studio",
        "chart_id": None,
        "slot": "D1-S1",
        "status": "drafted",
        "shape": "one_liner",
        "angle": "level_watch",
        "_copy_mode": "llm",
    }
    base.update(over)
    return base


def _plan(*items, as_of: str = _TODAY, copy_mode: str = "llm") -> dict:
    return {
        "as_of": as_of,
        "accounts": [{"id": "flagship", "queue": list(items)}],
        "featured_charts": [],
        "content": {"copy": {"mode": copy_mode}},
    }


#: Emit cfg with the daily cap raised — the authority stays with the sentinel
#: block, never an outbox constant (outbox.effective_cap law).
_CAP_CFG = {"sentinel": {"max_posts_per_account_per_day": 20}}


def _emit_cfg(required: bool | None = True) -> dict:
    cfg = dict(_CAP_CFG)
    if required is None:
        cfg["copywriter"] = {"llm": {}}          # block present, key absent
    else:
        cfg["copywriter"] = {"llm": {"required": required}}
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# 1. Cross-day ticker cooldown (gate 3c — the LKFN/GPI/CBOE fix)
# ─────────────────────────────────────────────────────────────────────────────

def test_lkfn_posted_yesterday_is_ineligible_today(tmp_path):
    """THE NAMED LKFN CASE. $LKFN posted 07-28 must not be planned again 07-29.

    On 2026-07-29 LKFN, GPI and CBOE were all planned the day after they posted,
    because no cross-day cooldown existed anywhere in the pipeline (masterplan
    §1). One session elapsed is inside the 3-session coverage bar and inside the
    5-session signal bar.
    """
    from engine.marketing.content_studio import ticker_exposure, cooled_tickers

    _seed_item(tmp_path, ticker="LKFN", as_of=_YESTERDAY, status="posted")

    exposure = ticker_exposure(tmp_path, as_of=_TODAY)
    assert exposure.get("LKFN") == _YESTERDAY

    assert "LKFN" in cooled_tickers(exposure, as_of=_TODAY, kind="watchlist")
    assert "LKFN" in cooled_tickers(exposure, as_of=_TODAY, kind="chart")
    assert "LKFN" in cooled_tickers(exposure, as_of=_TODAY, kind="signal")


def test_cooldown_clears_after_three_sessions_but_not_for_signal(tmp_path):
    """3 sessions clears coverage; a directional call still waits for 5."""
    from engine.marketing.content_studio import ticker_exposure, cooled_tickers

    # Friday -> Wednesday is 3 trading sessions (Mon, Tue, Wed).
    _seed_item(tmp_path, ticker="GPI", as_of=_FRIDAY, status="posted")
    exposure = ticker_exposure(tmp_path, as_of=_TODAY)

    assert "GPI" not in cooled_tickers(exposure, as_of=_TODAY, kind="watchlist")
    assert "GPI" in cooled_tickers(exposure, as_of=_TODAY, kind="signal")


def test_trading_days_ignore_the_weekend(tmp_path):
    """A calendar cooldown would hand every Friday post a free pass on Monday."""
    from engine.marketing.content_studio import trading_days_since

    assert trading_days_since("2026-07-24", "2026-07-27") == 1   # Fri -> Mon
    assert trading_days_since("2026-07-28", "2026-07-29") == 1   # Tue -> Wed
    assert trading_days_since("2026-07-29", "2026-07-29") == 0
    assert trading_days_since("garbage", "2026-07-29") is None   # fails CLOSED


def test_quarantined_exposure_does_not_cool_a_ticker(tmp_path):
    """A post nobody saw must not lock a name out of tonight's plan."""
    from engine.marketing.content_studio import ticker_exposure

    iid = _seed_item(tmp_path, ticker="CBOE", as_of=_YESTERDAY)
    from engine.marketing.outbox import transition
    transition(iid, "quarantined", actor="test", root=tmp_path, now=_FIXED_NOW)

    assert ticker_exposure(tmp_path, as_of=_TODAY) == {}


def test_same_day_exposure_is_not_a_cross_day_cooldown(tmp_path):
    """A governor RE-RUN must not find every ticker cooled by its own first pass."""
    from engine.marketing.content_studio import ticker_exposure

    _seed_item(tmp_path, ticker="ARES", as_of=_TODAY)
    assert ticker_exposure(tmp_path, as_of=_TODAY) == {}


def test_four_percent_move_overrides_the_cooldown_with_a_reason():
    """The override is a NEW FACT CLASS, and the reason travels to the writer.

    Masterplan §5.1: a cooled ticker comes back only when something genuinely
    changed, and the post must LEAD with it — so the override returns prose, not
    a boolean.
    """
    from engine.marketing.content_studio import cooldown_override_reason

    assert cooldown_override_reason("LKFN", pack={"day_move_pct": -5.2}) == (
        "LKFN moved -5.2% today")
    assert cooldown_override_reason("LKFN", pack={"earnings_today": True}) == (
        "LKFN reports today")
    # A 2% day is not a new fact class — the cooldown stands.
    assert cooldown_override_reason("LKFN", pack={"day_move_pct": 2.0}) is None
    assert cooldown_override_reason("LKFN") is None


def test_cooled_ticker_is_not_planned_but_an_override_brings_it_back(tmp_path):
    """End to end through plan_account: the cooldown removes the D1 slot."""
    from engine.marketing.content_studio import plan_account

    account = {"id": "flagship", "voice": "authoritative desk"}
    plans = [{
        "id": "LKFN-BULL", "asset": "LKFN", "direction": "BULL",
        "entry": 60.0, "targets": [70.0], "phase": "triggered_pre_t1",
        "recommended_action": "hold", "management_confidence": 70.0,
        "_signal_date": _YESTERDAY,
    }]

    cooled = plan_account(account, plans, n_days=1, per_day=6,
                          cooled_watch=frozenset({"LKFN"}),
                          cooled_signal=frozenset({"LKFN"}))
    assert not [i for i in cooled if i.ticker == "LKFN"], (
        "a cooled ticker still reached a D1 slot")

    free = plan_account(account, plans, n_days=1, per_day=6)
    assert [i for i in free if i.ticker == "LKFN"], (
        "guard is vacuous — the ticker never appears even uncooled")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fact-reuse budget (gate 3b — the ARES x5 fix)
# ─────────────────────────────────────────────────────────────────────────────

def _row(account: str, *items: dict) -> dict:
    return {"id": account, "queue": [dict(i, account=account) for i in items]}


def test_ares_on_a_third_account_is_refused(tmp_path):
    """THE NAMED ARES CASE. One fact reached FIVE desks on 2026-07-29.

    Two desks covering a name is coverage; five is the text-similarity
    fingerprint the cross-account near-dup bar exists to deny, arriving by a
    route that bar cannot see (five different wordings of one fact).
    """
    from engine.marketing.content_studio import apply_reuse_budget

    rows = [
        _row("flagship", _plan_item(id="a1", ticker="ARES", type="watchlist")),
        _row("receipts", _plan_item(id="a2", ticker="ARES", type="watchlist")),
        _row("theme_desk", _plan_item(id="a3", ticker="ARES", type="watchlist")),
        _row("research_a", _plan_item(id="a4", ticker="ARES", type="watchlist")),
        _row("research_b", _plan_item(id="a5", ticker="ARES", type="watchlist")),
    ]
    counts = apply_reuse_budget(rows, cfg=None, day_prefix="D1")

    survivors = [i for r in rows for i in r["queue"]]
    assert len(survivors) == 2, f"budget kept {len(survivors)} desks on one fact"
    assert counts["dropped_ticker_budget"] == 3
    # ...and the two survivors carry DISJOINT angles (contract §Selection).
    angles = {i["angle"] for i in survivors}
    assert len(angles) == 2, f"two desks on one fact shared an angle: {angles}"


def test_second_signal_account_for_one_ticker_is_refused(tmp_path):
    """A signal post carries entry/stop numbers: one desk's call or nobody's."""
    from engine.marketing.content_studio import apply_reuse_budget

    rows = [
        _row("flagship", _plan_item(id="s1", ticker="ARES", type="signal")),
        _row("receipts", _plan_item(id="s2", ticker="ARES", type="signal")),
    ]
    apply_reuse_budget(rows, cfg=None, day_prefix="D1")

    survivors = [i for r in rows for i in r["queue"]]
    assert len(survivors) == 1, "two desks published the same entry/stop"
    assert survivors[0]["account"] == "flagship"


def test_budget_only_touches_the_emitted_day(tmp_path):
    """D2-D7 are never emitted, so budgeting them would delete unsendable posts."""
    from engine.marketing.content_studio import apply_reuse_budget

    rows = [
        _row("flagship", _plan_item(id="d1", ticker="ARES", type="watchlist", slot="D2-S1")),
        _row("receipts", _plan_item(id="d2", ticker="ARES", type="watchlist", slot="D2-S1")),
        _row("theme_desk", _plan_item(id="d3", ticker="ARES", type="watchlist", slot="D2-S1")),
    ]
    apply_reuse_budget(rows, cfg=None, day_prefix="D1")
    assert len([i for r in rows for i in r["queue"]]) == 3


def test_budget_knobs_are_read_from_config(tmp_path):
    """A config key nothing reads is a lie in a config file."""
    from engine.marketing.content_studio import apply_reuse_budget

    rows = [
        _row("flagship", _plan_item(id="c1", ticker="ARES", type="watchlist")),
        _row("receipts", _plan_item(id="c2", ticker="ARES", type="watchlist")),
    ]
    apply_reuse_budget(rows, cfg={"selection": {"max_accounts_per_ticker_day": 1}},
                       day_prefix="D1")
    assert len([i for r in rows for i in r["queue"]]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. Degenerate-stat gate (gate 3h)
# ─────────────────────────────────────────────────────────────────────────────

def test_231_of_231_names_bullish_is_dropped():
    """THE NAMED 231/231 CASE. A count that saturates its universe is a definition.

    It shipped TWICE in the 2026-07-29 batch. The gate is on the RATIO, not on a
    phrase list, because the next degenerate stat is always a different sentence.
    """
    from engine.marketing.content_studio import drop_degenerate_facts

    facts = {"facts": [
        {"id": "f1", "text": "231 of 231 names on the list are bullish."},
        {"id": "f2", "text": "18 of 30 industry groups are higher today."},
    ], "numbers_whitelist": ["231", "18", "30"]}

    out, dropped = drop_degenerate_facts(facts)
    assert dropped == 1
    assert [f["id"] for f in out["facts"]] == ["f2"]
    # Never mutates its argument (the caller keeps using the original blob).
    assert len(facts["facts"]) == 2


def test_degenerate_gate_reads_structured_fields_too():
    """market_facts is migrating counts to structured fields — both forms gated."""
    from engine.marketing.content_studio import (
        drop_degenerate_facts, is_degenerate_count)

    facts = {"facts": [{"id": "s1", "text": "Breadth is broad.",
                        "n_moving": 231, "n_tracked": 231}]}
    _out, dropped = drop_degenerate_facts(facts)
    assert dropped == 1

    assert is_degenerate_count(231, 231) is True
    assert is_degenerate_count(1, 231) is True        # <= 5% is degenerate too
    assert is_degenerate_count(18, 30) is False
    assert is_degenerate_count(5, 0) is False         # unknown denominator != degenerate


def test_degenerate_band_is_configurable():
    from engine.marketing.content_studio import selection_cfg, drop_degenerate_facts

    band = selection_cfg({"selection": {"degenerate_stat_band": [0.2, 0.8]}})[
        "degenerate_stat_band"]
    assert band == (0.2, 0.8)
    facts = {"facts": [{"id": "x", "text": "25 of 30 names are green."}]}
    assert drop_degenerate_facts(facts, band=band)[1] == 1
    assert drop_degenerate_facts(facts)[1] == 0       # inside the default band


# ─────────────────────────────────────────────────────────────────────────────
# 4. Shape mixer (gate 4)
# ─────────────────────────────────────────────────────────────────────────────

def test_shape_quotas_hold_and_the_two_line_skeleton_is_capped():
    """65/65 of the aborted batch was one shape. The corpus rate for it is 2.8%."""
    from engine.marketing.content_studio import shape_plan

    for n in (4, 8, 12, 20, 28):
        shapes = shape_plan(n, account="flagship", as_of=_TODAY)
        assert len(shapes) == n
        one = shapes.count("one_liner")
        two = shapes.count("two_part")
        assert one >= int(n * 0.25), f"n={n}: one_liner {one} under the 25% floor"
        assert two <= int(n * 0.30), f"n={n}: two_part {two} over the 30% ceiling"
        assert shapes.count("stack") >= 1, f"n={n}: no stack in the day"
        assert max(shapes.count(s) for s in set(shapes)) <= int(n * 0.55), (
            f"n={n}: one shape dominates the day: {shapes}")


def test_shape_mixer_is_deterministic_and_account_scoped():
    """Date-seeded rotation, NO RNG — the same plan re-built is byte-identical."""
    from engine.marketing.content_studio import shape_plan

    a1 = shape_plan(12, account="flagship", as_of=_TODAY)
    a2 = shape_plan(12, account="flagship", as_of=_TODAY)
    assert a1 == a2, "shape assignment is not reproducible"

    other_desk = shape_plan(12, account="receipts", as_of=_TODAY)
    other_day = shape_plan(12, account="flagship", as_of="2026-07-30")
    assert a1 != other_desk or a1 != other_day, (
        "the rotation never varies by (account, day) — two desks would twin")


def test_caption_shape_only_lands_on_a_chart_bearing_item():
    """A caption with no image is a post with no content (contract §Shapes)."""
    from engine.marketing.content_studio import assign_shapes

    queue = [_plan_item(id=f"p{i}", type="watchlist", slot="D1-S1",
                        chart_id=("chart-001" if i % 2 == 0 else None), shape=None)
             for i in range(10)]
    assign_shapes(queue, account="flagship", as_of=_TODAY)

    for item in queue:
        if item["shape"] == "caption":
            assert item["chart_id"], "caption shape on an item with no media"


def test_shape_ledger_is_written_only_by_the_nightly(tmp_path):
    """Nightly is the sole advancer — a plan build must not roll the window."""
    from engine.marketing.content_studio import (
        record_shape_ledger, load_shape_ledger, shape_ledger_prior_mix)

    assert load_shape_ledger(tmp_path) == {}
    record_shape_ledger(tmp_path, as_of=_TODAY,
                        mix_by_account={"flagship": {"one_liner": 5, "stack": 2}})
    led = load_shape_ledger(tmp_path)
    assert led["days"][-1]["as_of"] == _TODAY
    assert shape_ledger_prior_mix(led, "flagship")["one_liner"] == 5

    # Same day twice replaces rather than duplicates; the window is bounded.
    for i in range(20):
        record_shape_ledger(tmp_path, as_of=f"2026-07-{i + 1:02d}",
                            mix_by_account={"flagship": {"list": 1}})
    assert len(load_shape_ledger(tmp_path)["days"]) <= 14


# ─────────────────────────────────────────────────────────────────────────────
# 5. Emit refusal — no template prose on a planned kind (gate 1)
# ─────────────────────────────────────────────────────────────────────────────

def test_emit_refuses_a_planned_item_with_no_model_copy(tmp_path, capsys):
    """THE §0 GATE 1 REFUSAL. This is the test that fails on the OLD behavior.

    Before W1 a deterministic-template `signal` queued and posted like any other
    item — which is how 65 template posts reached the outbox on 2026-07-29.
    """
    from engine.marketing.outbox import emit_from_content_plan, read_items

    plan = _plan(
        _plan_item(id="p1", _copy_mode="deterministic"),
        _plan_item(id="p2", ticker="NVDA", cashtag="$NVDA", slot="D1-S2",
                   body="NVDA held the line into the close and I am still long.",
                   _copy_mode="llm"),
        copy_mode="llm",
    )
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_emit_cfg(True),
                                    day_prefix="D1", now=_FIXED_NOW)

    assert result["skipped_not_llm"] == 1, result
    assert result["emitted"] == 1, "the model-written post must still ship"
    kinds = [(i["kind"], (i.get("source") or {}).get("copy_mode"))
             for i in read_items(tmp_path)]
    assert kinds == [("signal", "llm")]

    # ONE annotation, and it must START the line or GitHub drops it silently.
    err = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert len(err) == 1, f"expected exactly one ::error, got {err}"
    assert err[0].startswith("::error title=marketing_copy_not_llm::"), err[0]


def test_the_same_plan_emits_when_the_law_is_disarmed(tmp_path):
    """Proves the refusal is the NEW behavior, not an unrelated skip."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _plan(_plan_item(id="p1", _copy_mode="deterministic"))
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_emit_cfg(False),
                                    day_prefix="D1", now=_FIXED_NOW)
    assert result["emitted"] == 1
    assert result["skipped_not_llm"] == 0


def test_required_defaults_true_when_the_llm_block_exists(tmp_path):
    """Deleting the KEY cannot disarm the gate; shipping no copywriter cfg can."""
    from engine.marketing.content_studio import llm_required
    from engine.marketing.outbox import emit_from_content_plan

    assert llm_required({"copywriter": {"llm": {}}}) is True
    assert llm_required({"copywriter": {"llm": {"required": "false"}}}) is False
    assert llm_required({}) is False, (
        "a caller with no copywriter config is not running the writer lane")

    plan = _plan(_plan_item(id="p1", _copy_mode="deterministic"))
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_emit_cfg(None),
                                    day_prefix="D1", now=_FIXED_NOW)
    assert result["skipped_not_llm"] == 1


def test_wire_kinds_are_never_refused(tmp_path):
    """The fallback dies for diary register only — wire copy survives templating."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _plan(
        _plan_item(id="m1", type="mover", ticker="TSLA", cashtag="$TSLA",
                   body="TSLA ripped 6% today on the biggest volume since March.",
                   _copy_mode="movers_desk"),
        copy_mode="llm",
    )
    result = emit_from_content_plan(plan, root=tmp_path, cfg=_emit_cfg(True),
                                    day_prefix="D1", now=_FIXED_NOW)
    assert result["emitted"] == 1
    assert result["skipped_not_llm"] == 0


def test_mute_lane_annotation_names_the_mute(tmp_path, capsys):
    """The operator has to know WHICH failure this is: mute lane vs failed copy."""
    from engine.marketing.outbox import emit_from_content_plan

    plan = _plan(_plan_item(id="p1", _copy_mode="deterministic"),
                 copy_mode="deterministic")
    emit_from_content_plan(plan, root=tmp_path, cfg=_emit_cfg(True),
                           day_prefix="D1", now=_FIXED_NOW)
    err = [ln for ln in capsys.readouterr().out.splitlines() if "::error" in ln]
    assert len(err) == 1
    assert err[0].startswith("::error title=marketing_copy_lane_mute::"), err[0]
    assert "MARKETING_LLM_ENABLED" in err[0]


def test_emit_carries_shape_angle_and_mode_into_item_provenance(tmp_path):
    """Telemetry seam: the learning lane joins engagement onto these decisions."""
    from engine.marketing.outbox import emit_from_content_plan, read_items

    plan = _plan(_plan_item(id="p1", shape="stack", angle="risk_frame",
                            _copy_mode="llm_repair"))
    emit_from_content_plan(plan, root=tmp_path, cfg=_emit_cfg(True),
                           day_prefix="D1", now=_FIXED_NOW)
    src = read_items(tmp_path)[0]["source"]
    assert src["shape"] == "stack"
    assert src["angle"] == "risk_frame"
    assert src["copy_mode"] == "llm_repair"


# ─────────────────────────────────────────────────────────────────────────────
# 6. Stale-queued expiry
# ─────────────────────────────────────────────────────────────────────────────

def _sched(hours_ago: float) -> str:
    return (_FIXED_NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_planned_item_36h_past_its_slot_is_quarantined(tmp_path):
    """A post written against a two-night-old close must not still be pending."""
    from engine.marketing.outbox import expire_stale_planned, fold_state

    stale = _seed_item(tmp_path, ticker="FDS", as_of=_YESTERDAY,
                       scheduled_at=_sched(48))
    fresh = _seed_item(tmp_path, ticker="TEL", as_of=_YESTERDAY,
                       scheduled_at=_sched(2))

    out = expire_stale_planned(tmp_path, now=_FIXED_NOW)
    assert out["expired"] == 1 and out["ids"] == [stale]

    state = fold_state(tmp_path)
    assert state["status"][stale] == "quarantined"
    assert state["status"][fresh] == "queued"
    row = state["last"][stale]
    assert row["actor"] == "nightly_expiry"
    assert row["note"] == "expired: superseded by tonight's plan"


def test_expiry_leaves_immediate_and_foreign_lanes_alone(tmp_path):
    """No slot to be late for; and the wire lanes retire their own items."""
    from engine.marketing.outbox import expire_stale_planned, fold_state

    imm = _seed_item(tmp_path, ticker="AAPL", as_of=_YESTERDAY,
                     scheduled_at="immediate")
    wire = _seed_item(tmp_path, ticker="MSFT", as_of=_YESTERDAY, kind="breaking",
                      provenance="press_lane", scheduled_at=_sched(48))
    weekend = _seed_item(tmp_path, ticker="AMD", as_of=_YESTERDAY,
                         provenance="weekend_levels", scheduled_at=_sched(48))

    assert expire_stale_planned(tmp_path, now=_FIXED_NOW)["expired"] == 0
    status = fold_state(tmp_path)["status"]
    assert status[imm] == status[wire] == status[weekend] == "queued"


def test_emit_runs_the_expiry_pass_first(tmp_path):
    """It is tonight's plan that supersedes them, so emit is where it belongs."""
    from engine.marketing.outbox import emit_from_content_plan, fold_state

    stale = _seed_item(tmp_path, ticker="FDS", as_of=_YESTERDAY,
                       scheduled_at=_sched(48))
    result = emit_from_content_plan(
        _plan(_plan_item(id="p1")), root=tmp_path, cfg=_emit_cfg(True),
        day_prefix="D1", now=_FIXED_NOW)

    assert result["expired"] == 1
    assert fold_state(tmp_path)["status"][stale] == "quarantined"


# ─────────────────────────────────────────────────────────────────────────────
# 7. Kind-scoped auto-approve (masterplan §7)
# ─────────────────────────────────────────────────────────────────────────────

def _write_scope_cfg(tmp_path: Path, *, scope: str) -> None:
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "marketing.yml").write_text(
        "sentinel:\n"
        "  max_posts_per_account_per_day: 20\n"
        "publish:\n"
        "  backend: buffer\n"
        "  require_approval: true\n"
        "  auto_approve: true\n"
        f"  auto_approve_scope: {scope}\n"
        "  auto_approve_kinds: [mover, theme_list]\n"
        "  channels:\n"
        "    flagship: \"buf-chan-123\"\n"
        "  links_allowed:\n"
        "    flagship: true\n",
        encoding="utf-8",
    )


def _seed_for_scope(tmp_path: Path) -> tuple[str, str]:
    planned = _seed_item(
        tmp_path, ticker="PLTR", as_of=_TODAY, kind="signal",
        text="PLTR reclaimed 120 and I am watching the retest, not chasing.",
        provenance="content_studio")
    mover = _seed_item(
        tmp_path, ticker="TSLA", as_of=_TODAY, kind="mover",
        text="TSLA ripped 6% today, one of the bigger moves in the index.",
        provenance="publisher_live_movers")
    return planned, mover


def test_planned_kind_waits_for_the_operator_while_a_mover_clears(tmp_path):
    """THE §7 SCOPING. auto_approve: true no longer clears the nightly's own copy.

    On 2026-07-29 the blanket auto-approved 61 posts the operator aborted
    reviewing. This is the test that fails on the OLD behavior — before the
    scope, the content_studio signal below auto-approved too.
    """
    import scripts.marketing_publisher as pub

    _write_scope_cfg(tmp_path, scope="kinds")
    planned, mover = _seed_for_scope(tmp_path)

    rep = pub.dry_run_report(root=tmp_path, now=_FIXED_NOW)
    assert rep["ok"] is True, rep
    would = {r["id"] for r in rep["would_auto_approve"]}
    assert mover in would, "the publish-time tape lane must stay automatic"
    assert planned not in would, "a nightly planned-kind post auto-approved"


def test_scope_all_restores_the_old_blanket(tmp_path):
    """The operator's one-line reversal really reverses it."""
    import scripts.marketing_publisher as pub

    _write_scope_cfg(tmp_path, scope="all")
    planned, mover = _seed_for_scope(tmp_path)

    rep = pub.dry_run_report(root=tmp_path, now=_FIXED_NOW)
    would = {r["id"] for r in rep["would_auto_approve"]}
    assert planned in would and mover in would


def test_auto_approve_scope_parses_strictly():
    """A typo here would publish unreviewed copy — fail CLOSED to 'kinds'."""
    import scripts.marketing_publisher as pub

    assert pub._auto_approve_scope_cfg({}) == "kinds"
    assert pub._auto_approve_scope_cfg({"auto_approve_scope": "all"}) == "all"
    assert pub._auto_approve_scope_cfg({"auto_approve_scope": "ALL"}) == "all"
    assert pub._auto_approve_scope_cfg({"auto_approve_scope": "everything"}) == "kinds"
    assert pub._auto_approve_scope_cfg({"auto_approve_scope": None}) == "kinds"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Plan build with a STUB writer — the no-fallback drop + the report counters
# ─────────────────────────────────────────────────────────────────────────────

_STUB_ACCOUNTS = [
    {"id": "flagship", "kind": "branded", "beat": "What changed",
     "voice": "authoritative desk"},
    {"id": "receipts", "kind": "branded", "beat": "Receipt",
     "voice": "dry, receipts-forward"},
]

_STUB_PLANS = [
    {"id": "PLTR-BULL", "asset": "PLTR", "direction": "BULL", "entry": 120.0,
     "invalidation": 100.0, "targets": [150.0, 180.0], "trigger": 125.0,
     "phase": "triggered_pre_t1", "recommended_action": "hold",
     "management_confidence": 66.0, "_signal_date": _YESTERDAY},
    {"id": "SBUX-BULL", "asset": "SBUX", "direction": "BULL", "entry": 82.0,
     "invalidation": 75.0, "targets": [95.0], "trigger": 84.0,
     "phase": "triggered_pre_t1", "recommended_action": "hold",
     "management_confidence": 61.0, "_signal_date": _YESTERDAY},
]


def _arm_stub_writer(monkeypatch, *, drop_ticker: str | None = None):
    """Inject a fake per-post writer. NO anthropic import, no network."""
    from engine.marketing import copywriter as cw

    def _stub(contexts, cfg, **_kw):   # **_kw: the writer now also takes root=
        out = []
        for ctx in contexts:
            if drop_ticker and str(ctx.get("ticker") or "") == drop_ticker:
                out.append({"mode": "dropped", "reasons": ["bot_tell"],
                            "stage": "critic"})
                continue
            text = f"Model copy for {ctx.get('ticker') or ctx.get('type')}, " \
                   f"shape={ctx.get('shape')} angle={ctx.get('angle')}."
            out.append({"text": text, "headline": "", "body": text,
                        "mode": "llm", "violations": [],
                        "critic": {"verdict": "pass", "reasons": []}})
        return out

    monkeypatch.setattr(cw, "write_posts_llm_v2", _stub, raising=False)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")


def _stub_cfg() -> dict:
    return {
        "desk_network": {"stage": "A", "accounts": _STUB_ACCOUNTS},
        "copywriter": {"llm": {"enabled": True, "required": True}},
    }


def test_dropped_posts_leave_the_queue_and_are_never_template_filled(
        monkeypatch, tmp_path):
    """§0 gate 1 on the PLAN side: a drop is a drop, not a fallback."""
    from engine.marketing.content_studio import content_plan

    _arm_stub_writer(monkeypatch, drop_ticker="SBUX")
    plan = content_plan(_stub_cfg(), _STUB_PLANS, closes_loader=None, root=tmp_path)

    d1 = [i for a in plan["accounts"] for i in a["queue"]
          if str(i.get("slot", "")).startswith("D1-")]
    assert d1, "guard is vacuous — no D1 items were planned at all"
    assert not [i for i in d1 if i.get("ticker") == "SBUX"], (
        "a dropped post survived in the queue")
    assert plan["content"]["copy"]["dropped"].get("critic", 0) > 0
    assert plan["content"]["copy"]["modes"].get("llm", 0) > 0
    for item in d1:
        if item.get("type") in ("signal", "chart", "watchlist", "macro",
                                "education", "receipt", "event"):
            assert item.get("_copy_mode") == "llm", item.get("_copy_mode")


def test_plan_report_prints_the_selection_funnel(monkeypatch, tmp_path):
    """Supply-honest volume is only auditable if the plan prints what it threw away."""
    from engine.marketing.content_studio import content_plan

    _arm_stub_writer(monkeypatch)
    plan = content_plan(_stub_cfg(), _STUB_PLANS, closes_loader=None, root=tmp_path)

    sel = plan["content"]["selection"]
    for key in ("supply", "after_cooldown", "after_budget", "cooled_tickers",
                "cooldown_overrides", "dropped_ticker_budget",
                "dropped_signal_budget", "degenerate_stats_dropped"):
        assert key in sel, f"plan report is missing {key}"

    copy = plan["content"]["copy"]
    for key in ("written", "modes", "dropped", "shape_mix", "llm_required"):
        assert key in copy, f"copy report is missing {key}"
    assert copy["written"] > 0
    assert copy["llm_required"] is True
    assert sum(copy["shape_mix"].values()) > 0


def test_sibling_texts_reach_later_desks(monkeypatch, tmp_path):
    """Account 2 must see what account 1 already said about the same name."""
    from engine.marketing import copywriter as cw
    from engine.marketing.content_studio import content_plan

    seen: list[list[str]] = []

    def _stub(contexts, cfg, **_kw):   # **_kw: the writer now also takes root=
        out = []
        for ctx in contexts:
            if str(ctx.get("ticker") or "") == "PLTR":
                seen.append(list(ctx.get("sibling_texts") or []))
            text = f"Model copy about {ctx.get('ticker') or ctx.get('type')} number {len(out)}."
            out.append({"text": text, "headline": "", "body": text, "mode": "llm",
                        "violations": [], "critic": {"verdict": "pass", "reasons": []}})
        return out

    monkeypatch.setattr(cw, "write_posts_llm_v2", _stub, raising=False)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    content_plan(_stub_cfg(), _STUB_PLANS, closes_loader=None, root=tmp_path)

    assert seen, "no PLTR context reached the writer"
    assert any(s for s in seen), (
        "sibling_texts was empty for every desk — the second desk never saw the first")


def test_shapes_and_angles_are_stamped_on_planned_items(monkeypatch, tmp_path):
    from engine.marketing.content_studio import content_plan, SHAPES, ANGLES

    _arm_stub_writer(monkeypatch)
    plan = content_plan(_stub_cfg(), _STUB_PLANS, closes_loader=None, root=tmp_path)

    planned = [i for a in plan["accounts"] for i in a["queue"]
               if str(i.get("slot", "")).startswith("D1-")
               and i.get("type") in ("signal", "chart", "watchlist", "macro",
                                     "education", "receipt", "event")]
    assert planned
    for item in planned:
        assert item.get("shape") in SHAPES, item
        # Ticker-less planned kinds (macro/education/event) get the kind's
        # default angle — the writer and the emit provenance both read it.
        assert item.get("angle") in ANGLES, item


# ─────────────────────────────────────────────────────────────────────────────
# 9. The LIVE config arms the laws (a code default cannot be the whole story)
# ─────────────────────────────────────────────────────────────────────────────

def test_live_config_arms_the_w1_laws():
    """config/marketing.yml is the operator surface — pin what it must say.

    `llm_required({})` is False by design (a caller shipping no copywriter block
    is not running the writer lane), so the ONLY thing standing between the
    nightly and template prose is this key being present and true. Same for the
    auto-approve scope: the code default is 'kinds', but a config that said
    'all' would quietly restore the blanket the operator rejected.
    """
    import yaml
    from engine.marketing.content_studio import llm_required, selection_cfg

    cfg = yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))

    assert llm_required(cfg) is True, (
        "config/marketing.yml no longer arms copywriter.llm.required — planned "
        "kinds would ship template prose again")
    assert cfg["publish"]["auto_approve_scope"] == "kinds"
    assert cfg["copywriter"]["llm"]["critic"]["enabled"] is True

    sel = selection_cfg(cfg)
    assert sel["ticker_cooldown_days"] >= 3
    assert sel["signal_cooldown_days"] >= sel["ticker_cooldown_days"]
    assert sel["max_accounts_per_ticker_day"] <= 2
    assert sel["max_signal_accounts_per_day"] == 1


def test_no_llm_import_at_module_top():
    """Lane purity: the marketing-engine CI lane has no anthropic installed."""
    for rel in ("engine/marketing/content_studio.py", "engine/marketing/outbox.py",
                "scripts/marketing_publisher.py"):
        src = (ROOT / rel).read_text(encoding="utf-8")
        head = src.split("\ndef ", 1)[0]
        assert "import anthropic" not in head, f"{rel} imports anthropic at module top"
        assert "\nfrom anthropic" not in head, f"{rel} imports anthropic at module top"


def test_shapes_literal_never_drifts_between_the_two_modules():
    """content_studio and copywriter each carry a SHAPES literal (no import
    coupling by design — the emit side must survive a broken writer import).
    A drift between them would route the mixer's assignment into a validator
    that calls it an unknown shape, so the two literals are pinned equal."""
    from engine.marketing import content_studio as cs
    from engine.marketing import copywriter as cw
    assert tuple(cs.SHAPES) == tuple(cw.SHAPES)


# ─────────────────────────────────────────────────────────────────────────────
# Perishability (operator 2026-07-30)
# The planner books a SEVEN-day forward queue. Copy claiming something about the
# current tape is false by the time a D5 slot arrives, so the publisher's
# live-tape gate refused it and logged `tape_skipped` — that counter fired on
# every sweep of 2026-07-29 and is why ZERO posts went out that day. The gate
# was right; pre-writing perishable copy a week ahead was the bug.
# ─────────────────────────────────────────────────────────────────────────────
class TestPerishableForwardBookings:
    def _rows(self):
        return [{"id": "flagship", "queue": [
            {"id": "a", "type": "signal",    "slot": "D1-S1"},
            {"id": "b", "type": "signal",    "slot": "D4-S3"},
            {"id": "c", "type": "watchlist", "slot": "D6-S2"},
            {"id": "d", "type": "education", "slot": "D7-S9"},
            {"id": "e", "type": "macro",     "slot": "D2-S1"},
            {"id": "f", "type": "receipt",   "slot": "D5-S4"},
        ]}]

    def test_perishable_kinds_are_dropped_past_day_one(self):
        from engine.marketing.content_studio import drop_stale_forward_bookings
        rows = self._rows()
        counts = drop_stale_forward_bookings(rows, cfg=None)
        assert counts["dropped_perishable_forward"] == 2
        assert counts["by_kind"] == {"signal": 1, "macro": 1}

    def test_evergreen_kinds_keep_the_full_horizon(self):
        """A level that has held 23 sessions still reads true on Friday."""
        from engine.marketing.content_studio import drop_stale_forward_bookings
        rows = self._rows()
        drop_stale_forward_bookings(rows, cfg=None)
        kept = [i["id"] for i in rows[0]["queue"]]
        assert "c" in kept and "d" in kept and "f" in kept   # watchlist/education/receipt

    def test_day_one_perishable_survives(self):
        from engine.marketing.content_studio import drop_stale_forward_bookings
        rows = self._rows()
        drop_stale_forward_bookings(rows, cfg=None)
        assert "a" in [i["id"] for i in rows[0]["queue"]]

    def test_an_unparseable_slot_is_never_dropped(self):
        """Fail OPEN on a slot-format change: dropping on a parse failure would
        silently empty the whole queue if the ladder label ever moved."""
        from engine.marketing.content_studio import drop_stale_forward_bookings
        rows = [{"id": "x", "queue": [
            {"id": "n", "type": "signal", "slot": None},
            {"id": "m", "type": "signal", "slot": "weird-format"},
        ]}]
        counts = drop_stale_forward_bookings(rows, cfg=None)
        assert counts["dropped_perishable_forward"] == 0
        assert len(rows[0]["queue"]) == 2

    def test_config_drives_the_rule(self):
        from engine.marketing.content_studio import (
            drop_stale_forward_bookings, perishable_kinds, perishable_max_day)
        cfg = {"selection": {"perishable_kinds": ["watchlist"], "perishable_max_day": 2}}
        assert perishable_kinds(cfg) == frozenset({"watchlist"})
        assert perishable_max_day(cfg) == 2
        rows = self._rows()
        counts = drop_stale_forward_bookings(rows, cfg=cfg)
        # only the D6 watchlist now; signals/macro are evergreen under this cfg
        assert counts["by_kind"] == {"watchlist": 1}

    def test_shipped_config_is_the_d1_only_rule(self):
        import yaml, pathlib
        from engine.marketing.content_studio import perishable_kinds, perishable_max_day
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        assert perishable_max_day(cfg) == 1
        assert {"signal", "chart", "macro", "event"} <= perishable_kinds(cfg)
        # evergreen kinds must NOT be in the perishable set
        assert not ({"watchlist", "education", "receipt"} & perishable_kinds(cfg))


# ─────────────────────────────────────────────────────────────────────────────
# Failed-signal disposal (operator 2026-07-30)
# A planned signal whose entry the live gate cannot stand behind used to be
# RE-TYPED into a watchlist post. Measured on the live plan: 168 of 335
# watchlist posts were demoted signals (39 of 57 on the shipping day) and 125
# had failed for AGE alone. They all wore the same proximity copy, which is
# where the batch auditor's "mechanically uniform" verdict came from.
# ─────────────────────────────────────────────────────────────────────────────
class TestFailedSignalDisposal:
    def test_the_shipped_rule_demotes_only_real_states(self):
        import yaml, pathlib
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        allowed = set((cfg.get("selection") or {}).get("demotable_gate_reasons") or [])
        assert allowed == {"runaway", "underwater"}, (
            "stale and unverified must NOT demote — there is nothing honest to "
            "post about a three-week-old idea or a name we cannot price")

    def test_gate_reasons_classify_as_expected(self):
        """The disposal rule keys on this classifier; pin its buckets."""
        from engine.marketing.copywriter import watch_reason_from_gate
        assert watch_reason_from_gate("signal is 13d old (max 10d)") == "stale"
        assert watch_reason_from_gate(
            "ran away +14.9% — no longer actionable (last=283.87, entry=247.10)") == "runaway"
        assert watch_reason_from_gate(
            "underwater -2.2% (last=393.35, entry=402.30)") == "underwater"
        assert watch_reason_from_gate("no close data — cannot verify") == "unverified"

    def test_unrecognised_prose_falls_to_stale_and_is_therefore_dropped(self):
        """Fail-safe direction: an unknown failure drops rather than becoming
        filler, because we cannot say what would be true about it."""
        import yaml, pathlib
        from engine.marketing.copywriter import watch_reason_from_gate
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        allowed = set((cfg.get("selection") or {}).get("demotable_gate_reasons") or [])
        assert watch_reason_from_gate("something nobody has seen before") == "stale"
        assert "stale" not in allowed

    def test_the_report_records_what_was_dropped_and_why(self):
        """Supply-honest volume is only auditable if the plan prints the loss."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        assert '"signals_dropped_not_demoted"' in src
        assert '"signals_dropped_by_reason"' in src
        assert '"demotable_gate_reasons"' in src

    def test_dropped_signals_never_reach_the_writer(self):
        """A dead idea must not cost a model call: the drop happens after the
        gate and before Phase 2 builds a context."""
        import inspect
        from engine.marketing import content_studio
        src = inspect.getsource(content_studio)
        drop_at = src.index("_stale_dropped = [d for d in queue")
        phase2_at = src.index("# Phase 2: build all contexts")
        assert drop_at < phase2_at, "the drop must precede context building"
