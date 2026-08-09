"""The daily ticker allocator — engine/marketing/ticker_allocator.py.

THE DEFECT UNDER TEST. The chart/watchlist lanes drew their subjects from pools
that overlap at the top of the liquidity board plus a `house_picks` lane capped
at 7 names a night, so the network posted the same handful of mega-caps while
2,673 liquid names went untouched. The allocator partitions the liquid universe
across the desks instead. What is pinned here is the PARTITION's promises: zero
cross-account overlap, determinism, per-account cooldowns, the mega-cap quota,
verified long-view history, and fail-soft on a missing pack.

Every synthetic fixture is asserted NON-EMPTY before anything is asserted over
it: a universe that silently built zero rows would make every "no overlap" and
"no duplicate" assertion below vacuously true.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.marketing import ticker_allocator as TA

# A Thursday, a Friday, and the Monday after — chosen so the cooldown arithmetic
# below is in SESSIONS and a weekend cannot silently satisfy it.
THU = "2026-08-06"
FRI = "2026-08-07"
MON = "2026-08-10"

ACCOUNTS = ["alpha", "bravo", "charlie"]


def _sym(i: int) -> str:
    """A distinct 3-letter symbol for index *i* (TAA, TAB, ... TZZ)."""
    return "T" + chr(ord("A") + (i // 26) % 26) + chr(ord("A") + i % 26)


def _pack(root: Path, n: int, *, trade_date: str) -> list[str]:
    """Write a synthetic hot-tape pack of *n* names, adv_rank 1..n. Returns them."""
    tickers = {}
    names = []
    for i in range(n):
        t = _sym(i)
        names.append(t)
        tickers[t] = {
            "adv_rank": i + 1,
            "adv20_dollars": float((n - i) * 1_000_000),
            "last_date": trade_date,
        }
    path = root / "data" / "marketing" / "hot_tape_pack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "trade_date": trade_date,
        "n_tickers": n,
        "tickers": tickers,
    }), encoding="utf-8")
    return names


def _cfg(**over) -> dict:
    """A `ticker_allocator:` config block with small, legible numbers."""
    blk = {
        "enabled": True,
        "universe_depth": 40,
        "per_account_per_day": 4,
        "htf_per_account_per_day": 2,
        "htf_timeframes": ["WEEKLY", "MONTHLY"],
        "megacap_quota_rank": 10,
        "megacap_per_account_per_day": 2,
        "cooldown_days": 3,
        "min_htf_bars": 60,
    }
    blk.update(over)
    return {"ticker_allocator": blk}


def _ledger(rows: list[tuple[str, str, str, str]]) -> dict:
    """A folded outbox state from (id, account, day, ticker) tuples, all posted."""
    items = {i: {"id": i, "account": acct, "as_of": day,
                 "source": {"ticker": tkr}}
             for i, acct, day, tkr in rows}
    return {"items": items, "status": {i: "posted" for i in items}}


@pytest.fixture()
def universe(tmp_path):
    """40 names, dated today, plus the guard that the fixture is real."""
    names = _pack(tmp_path, 40, trade_date=FRI)
    rows = TA.liquid_universe(tmp_path, cfg=_cfg(), as_of=FRI)
    assert len(rows) == 40, f"synthetic universe did not build: {len(rows)} rows"
    assert ACCOUNTS, "no accounts to allocate to"
    return names


@pytest.fixture()
def deep_htf(monkeypatch):
    """Every name has all the long-view history it could need."""
    monkeypatch.setattr(TA, "_htf_bars", lambda t, root, tf, want: 10_000)


# ═════════════════════════════════════════════════════════════════════════════
# The partition
# ═════════════════════════════════════════════════════════════════════════════

class TestPartition:

    def test_one_ticker_reaches_at_most_one_desk(self, tmp_path, universe, deep_htf):
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        drawn = [a.ticker for rows in alloc.values() for a in rows]
        assert len(drawn) == len(ACCOUNTS) * 4, drawn
        assert len(drawn) == len(set(drawn)), \
            "a ticker reached two desks on the same day"

    def test_a_desk_never_carries_the_same_cashtag_twice(
            self, tmp_path, universe, deep_htf):
        """sentinel.max_same_cashtag_per_account_per_day = 3 binds this lane.

        The allocator hands each desk DISTINCT names, so the cap can only ever
        be reached by another lane posting the same name — never by this one.
        """
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        for acct, rows in alloc.items():
            tick = [a.ticker for a in rows]
            assert len(tick) == len(set(tick)), f"{acct} drew a name twice: {tick}"

    def test_share_class_spellings_are_one_listing(self, tmp_path):
        """`BRK.B` and `BRK-B` are one line in two vendor spellings.

        Handing one spelling to one desk and the other to another is the
        cross-account overlap the partition promises not to produce, and no
        reader would call it two names.
        """
        path = tmp_path / "data" / "marketing" / "hot_tape_pack.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "trade_date": FRI,
            "tickers": {
                "BRK.B": {"adv_rank": 1, "adv20_dollars": 9e9, "last_date": FRI},
                "BRK-B": {"adv_rank": 2, "adv20_dollars": 8e9, "last_date": FRI},
                "GOOG": {"adv_rank": 3, "adv20_dollars": 7e9, "last_date": FRI},
                "GOOGL": {"adv_rank": 4, "adv20_dollars": 6e9, "last_date": FRI},
            },
        }), encoding="utf-8")
        got = [r["ticker"] for r in TA.liquid_universe(tmp_path, as_of=FRI)]
        assert got == ["BRK.B", "GOOG", "GOOGL"], got

    def test_every_supply_row_carries_a_truthy_pool(
            self, tmp_path, universe, deep_htf):
        """A row without one ships uncharted and DEFERS FOREVER.

        The featured-chart loop refuses to draw a plan-less item unless it
        carries a `supply_pool`, and a ticker-bearing post with no chart never
        publishes (tests/test_chart_director.py
        ::test_a_supply_sourced_item_is_still_chartable).
        """
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        rows = [r for acct_rows in TA.supply_rows(alloc).values()
                for r in acct_rows]
        assert rows, "no supply rows to check"
        for r in rows:
            assert r["pool"], r
            assert r["ticker"] and r["why"]
            assert "—" not in r["why"], f"em dash in a user-facing why: {r['why']}"


# ═════════════════════════════════════════════════════════════════════════════
# Determinism
# ═════════════════════════════════════════════════════════════════════════════

class TestDeterminism:

    def test_two_calls_on_the_same_inputs_are_identical(
            self, tmp_path, universe, deep_htf):
        a = TA.supply_rows(
            TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg()))
        b = TA.supply_rows(
            TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg()))
        assert a, "nothing was allocated"
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    def test_the_rotation_key_is_stable_across_processes(self):
        """A golden digest, because `hash()` would NOT be stable.

        CPython salts string hashing per process (PYTHONHASHSEED), so a governor
        re-run of the same night would re-shuffle every desk. If this constant
        ever moves, the allocator stopped being reproducible.
        """
        assert TA._rotation_key("2026-08-08", "alpha", "AAA") == \
            15529250016848770139

    def test_a_different_day_is_a_different_draw(
            self, tmp_path, universe, deep_htf):
        fri = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        mon = TA.allocate(tmp_path, as_of=MON, accounts=ACCOUNTS, cfg=_cfg())
        assert {a.ticker for a in fri["alpha"]} != {a.ticker for a in mon["alpha"]}


# ═════════════════════════════════════════════════════════════════════════════
# Cooldowns — PER ACCOUNT, which is the narrower of the two gates
# ═════════════════════════════════════════════════════════════════════════════

class TestCooldowns:

    def test_a_desks_own_name_from_yesterday_is_cooled_for_that_desk_only(
            self, tmp_path, universe):
        """The network-wide cooldown answers a different question.

        `content_studio.ticker_exposure` is ticker → last day ANY desk showed
        it. This gate is per desk: alpha may not re-run its own name, and
        bravo's name yesterday is none of alpha's business.
        """
        state = _ledger([("i1", "alpha", THU, "TAA")])
        cooled = TA.account_cooldowns(
            tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg(), state=state)
        assert "TAA" in cooled["alpha"]
        assert "TAA" not in cooled["bravo"], \
            "another desk's exposure leaked into bravo's cooldown"
        assert "TAA" not in cooled["charlie"]

    def test_a_cooled_name_is_not_drawn_by_that_desk_but_stays_available(
            self, tmp_path, deep_htf):
        """Cooled for one desk is not withdrawn from the night.

        The universe is sized so EVERY name is drawn (3 desks x 4 = 12 of 12),
        which turns "TAA went somewhere else" into a real assertion instead of
        a coincidence of the draw order.
        """
        names = _pack(tmp_path, 12, trade_date=FRI)
        assert len(names) == 12
        cfg = _cfg(universe_depth=12, per_account_per_day=4,
                   megacap_quota_rank=3, megacap_per_account_per_day=1)
        state = _ledger([("i1", "alpha", THU, "TAA")])
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS,
                            cfg=cfg, state=state)
        drawn = {a.ticker for rows in alloc.values() for a in rows}
        assert len(drawn) == 12, f"the whole universe should be drawn: {drawn}"
        assert "TAA" not in {a.ticker for a in alloc["alpha"]}
        assert "TAA" in drawn, "a per-account cooldown withdrew the name entirely"

    def test_a_quarantined_post_does_not_cool_anything(self, tmp_path, universe):
        """A post nobody saw must not lock a name out of tonight's plan."""
        state = _ledger([("i1", "alpha", THU, "TAA")])
        state["status"]["i1"] = "quarantined"
        cooled = TA.account_cooldowns(
            tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg(), state=state)
        assert cooled["alpha"] == frozenset()

    def test_the_cooldown_is_measured_in_sessions_not_calendar_days(
            self, tmp_path, universe):
        """A 3-CALENDAR-day cooldown gives every Friday name a free pass Monday.

        Friday to Monday is ONE session, so a name posted Friday is still cooled
        on Monday under a 3-session budget.
        """
        state = _ledger([("i1", "alpha", FRI, "TAA")])
        cooled = TA.account_cooldowns(
            tmp_path, as_of=MON, accounts=ACCOUNTS, cfg=_cfg(), state=state)
        assert "TAA" in cooled["alpha"]

    def test_todays_own_exposure_does_not_cool_a_rerun(self, tmp_path, universe):
        """STRICTLY EARLIER DAYS ONLY.

        Counting tonight's own emission would mean a governor re-run for the
        same date found every ticker cooled by its own first pass and planned
        an empty night (`content_studio.ticker_exposure`, same law).
        """
        state = _ledger([("i1", "alpha", FRI, "TAA")])
        cooled = TA.account_cooldowns(
            tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg(), state=state)
        assert cooled["alpha"] == frozenset()


# ═════════════════════════════════════════════════════════════════════════════
# The mega-cap quota
# ═════════════════════════════════════════════════════════════════════════════

class TestMegacapQuota:

    def test_every_desk_gets_its_quota_before_the_long_tail(
            self, tmp_path, universe, deep_htf):
        cfg = _cfg()
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=cfg)
        assert alloc, "nothing was allocated"
        for acct, rows in alloc.items():
            assert rows, f"{acct} drew nothing"
            megas = [a for a in rows if a.adv_rank <= 10]
            assert len(megas) >= 2, f"{acct} missed the quota: {megas}"

    def test_the_quota_rotates_across_days(self, tmp_path, universe, deep_htf):
        """Rotation is what stops one desk owning NVDA every night.

        Deterministic, not statistical: `_rotation_key` is a fixed digest, so
        these five days always produce these five draws.
        """
        seen = set()
        for day in ("2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06",
                    "2026-08-07"):
            alloc = TA.allocate(tmp_path, as_of=day, accounts=ACCOUNTS,
                                cfg=_cfg())
            seen.add(frozenset(a.ticker for a in alloc["alpha"]
                               if a.adv_rank <= 10))
        assert len(seen) > 1, f"alpha's mega-caps never moved: {seen}"

    def test_the_tail_is_reached_at_all(self, tmp_path, universe, deep_htf):
        """The whole point: subjects past the top of the liquidity board."""
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        tail = [a for rows in alloc.values() for a in rows if a.adv_rank > 10]
        assert len(tail) == len(ACCOUNTS) * 2, [a.ticker for a in tail]


# ═════════════════════════════════════════════════════════════════════════════
# The long view
# ═════════════════════════════════════════════════════════════════════════════

class TestLongView:

    def test_the_long_view_count_is_within_budget(
            self, tmp_path, universe, deep_htf):
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        for acct, rows in alloc.items():
            htf = [a for a in rows if a.timeframe != "DAILY"]
            assert 1 <= len(htf) <= 2, f"{acct}: {[(a.ticker, a.timeframe) for a in rows]}"
            assert all(a.timeframe in ("WEEKLY", "MONTHLY") for a in htf)
            assert all(a.copy_shape == TA.SHAPE_LONG_VIEW for a in htf)
            assert all(a.pool == TA.POOL_LONG_VIEW for a in htf)
            assert all(a.copy_shape == TA.SHAPE_TAPE
                       for a in rows if a.timeframe == "DAILY")

    def test_a_short_series_is_refused_a_long_view_and_kept_as_daily(
            self, tmp_path, universe, monkeypatch):
        """Refuse the VARIANT, not the name.

        A name without five years of history is still a perfectly good daily
        subject; dropping it would cost the desk a rung to buy nothing. What it
        must never do is promise a monthly chart it can only draw as a stub.
        """
        monkeypatch.setattr(TA, "_htf_bars", lambda t, root, tf, want: 10_000)
        rich = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        promised = [a for a in rich["alpha"] if a.timeframe != "DAILY"]
        assert promised, "the fixture produced no long-view subject to refuse"
        target = promised[0].ticker

        monkeypatch.setattr(TA, "_htf_bars",
                            lambda t, root, tf, want: 0 if t == target else 10_000)
        thin = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        rows = {a.ticker: a for a in thin["alpha"]}
        assert target in rows, "the refusal dropped the subject instead of the variant"
        assert rows[target].timeframe == "DAILY"
        assert rows[target].copy_shape == TA.SHAPE_TAPE
        assert len(thin["alpha"]) == len(rich["alpha"])

    def test_no_history_anywhere_means_every_subject_is_daily(
            self, tmp_path, universe, monkeypatch):
        monkeypatch.setattr(TA, "_htf_bars", lambda t, root, tf, want: 0)
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        rows = [a for acct_rows in alloc.values() for a in acct_rows]
        assert len(rows) == len(ACCOUNTS) * 4
        assert all(a.timeframe == "DAILY" for a in rows)


# ═════════════════════════════════════════════════════════════════════════════
# Fail-soft
# ═════════════════════════════════════════════════════════════════════════════

class TestFailSoft:

    def test_a_missing_pack_returns_an_empty_allocation(self, tmp_path, capsys):
        assert TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg()) == {}
        out = capsys.readouterr().out
        annotations = [ln for ln in out.splitlines() if "::warning" in ln]
        assert annotations, out
        assert all(ln.startswith("::") for ln in annotations), \
            "an annotation that does not START the line is dropped by Actions"

    def test_a_stale_pack_returns_an_empty_allocation(self, tmp_path):
        """Freshness is the dollar-volume pool's own law, not a second copy."""
        _pack(tmp_path, 40, trade_date="2026-06-01")
        assert TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg()) == {}

    def test_an_unreadable_ledger_leaves_the_allocation_standing(
            self, tmp_path, universe, deep_htf, monkeypatch):
        """A missing ops file degrades this gate; it does not zero the night."""
        def _boom(*a, **k):
            raise OSError("ledger gone")

        monkeypatch.setattr("engine.marketing.outbox.fold_state", _boom)
        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        assert sum(len(v) for v in alloc.values()) == len(ACCOUNTS) * 4

    def test_a_disabled_block_allocates_nothing(self, tmp_path, universe):
        assert TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS,
                           cfg=_cfg(enabled=False)) == {}

    def test_no_accounts_allocates_nothing(self, tmp_path, universe):
        assert TA.allocate(tmp_path, as_of=FRI, accounts=[], cfg=_cfg()) == {}

    def test_junk_config_falls_back_instead_of_raising(self):
        resolved = TA.allocator_cfg({"ticker_allocator": {
            "universe_depth": "wide", "htf_timeframes": ["HOURLY"],
            "per_account_per_day": None,
        }})
        assert resolved["universe_depth"] == TA.ALLOCATOR_DEFAULTS["universe_depth"]
        assert resolved["per_account_per_day"] == \
            TA.ALLOCATOR_DEFAULTS["per_account_per_day"]
        assert resolved["htf_timeframes"] == \
            tuple(TA.ALLOCATOR_DEFAULTS["htf_timeframes"])

    def test_a_config_less_checkout_uses_the_code_defaults(self):
        assert TA.allocator_cfg(None)["per_account_per_day"] == 12
        assert TA.allocator_cfg({})["megacap_quota_rank"] == 100
        assert TA.allocator_cfg({})["cooldown_days"] == 3
        assert TA.allocator_cfg({})["min_htf_bars"] == 60


# ═════════════════════════════════════════════════════════════════════════════
# The supply-row handshake with plan_account
# ═════════════════════════════════════════════════════════════════════════════

class TestSupplyRows:

    def test_a_row_drives_plan_account_exactly_like_an_attention_row(
            self, tmp_path, universe, deep_htf):
        """The rows must be walkable by the EXISTING seam, unchanged.

        `plan_account` reads `row["pool"]` with a bare subscript and stamps it
        onto the item as provenance; anything the allocator adds rides along
        without the planner knowing about it.
        """
        from engine.marketing import content_studio as CS  # noqa: PLC0415

        alloc = TA.allocate(tmp_path, as_of=FRI, accounts=ACCOUNTS, cfg=_cfg())
        rows = TA.supply_rows(alloc)["alpha"]
        assert rows, "no rows for alpha"
        items = CS.plan_account(
            {"id": "alpha", "voice": "authoritative desk"}, [],
            n_days=1, per_day=8, tilt={"watchlist": 1.0}, ticker_supply=rows)
        drawn = [i for i in items if i.supply_pool]
        assert [i.ticker for i in drawn] == [r["ticker"] for r in rows][:len(drawn)]
        assert all(i.supply_pool.startswith("allocator_") for i in drawn)
        assert all(i.supply_why for i in drawn)
