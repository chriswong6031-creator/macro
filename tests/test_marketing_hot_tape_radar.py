"""Hot Tape radar thin lane — the emit loop, the chart law, routing, CI wiring.

Pins the integration half of research/MARKETING_HOT_TAPE_MASTERPLAN.md §0:

  0.5  the existing safety stack is untouched AND exercised (kill switch off by
       default, outbox transition legality, enqueue dedupe on a second pass)
  0.6  EVERY TICKER POST CARRIES A CHART — a single-name event whose card cannot
       be drawn and hosted is DROPPED, never enqueued bare; sector/contrarian
       breadth posts ship text-only in P1
  0.7  every new suite is named in a run line in the lane it belongs to, plus
       ci.yml trigger paths for every new file — a suite that ships dark is the
       unrun-suite rot class, so this suite PINS ITS OWN WIRING (below)

THIS FILE MUST NOT IMPORT PANDAS — not directly, not through importorskip. The
radar runs on a shallow ubuntu checkout with pyyaml+requests+pyarrow and this
lane's minimal env IS that contract. Every fixture date is derived from today,
never written as a literal (the 2026-07-28 date-bomb class).

Run: .venv/bin/python -m pytest tests/test_marketing_hot_tape_radar.py -q
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.marketing import hot_tape as HT
from engine.marketing import hot_tape_wire as HW
from engine.marketing import outbox as OB
from engine.marketing import sentinel as SEN
from engine.marketing.hot_tape import FactPacket

from scripts import hot_tape_radar as RADAR

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Relative-date fixtures (no literal calendar dates anywhere)
# ─────────────────────────────────────────────────────────────────────────────

def _weekday_now(hour: int = 15, minute: int = 10) -> datetime:
    """A deterministic weekday timestamp inside the 13:25-20:05Z window."""
    d = date.today()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)


def _prev_weekday(d: date) -> date:
    x = d - timedelta(days=1)
    while x.weekday() >= 5:
        x -= timedelta(days=1)
    return x


NOW = _weekday_now()
DAY = NOW.date().isoformat()
TRADE_DATE = _prev_weekday(NOW.date()).isoformat()


def _quote(pct: float, price: float, prev: float) -> dict:
    return {"price": price, "prevClose": prev, "changePct": pct,
            "ts": int(NOW.timestamp() * 1000)}


def _tile(sym: str, sector: str, industry: str, pct: float) -> dict:
    return {"t": sym, "name": sym, "sector": sector, "industry": industry,
            "size": 0.5, "perf": {"1D": pct}}


def _pack_rec(**over) -> dict:
    """A pack record whose ONLY live device is the dollar translation.

    ath / streak / rsi / biggest-move fields are deliberately left empty so the
    composed copy is deterministic (one mover variant can render), and the round
    levels sit far from the fixture price so no threshold event fires by accident.
    """
    rec = {
        "last_date": TRADE_DATE,
        "last_close": 100.0,
        "prev_close": 101.0,
        "streak": {"dir": "flat", "len": 0, "last_run_ge": {}},
        "ath": None, "ath_date": None,
        "pct_from_ath": None,
        "rsi14": None, "rsi_avg_gain": None, "rsi_avg_loss": None,
        "last_rsi_le_30": None, "last_rsi_ge_70": None,
        "max_up_1d": None, "max_dn_1d": None,
        "round_above": 400.0, "round_below": 10.0,
        "px_correction": None, "px_bear": None,
        "adv20_dollars": 400_000_000.0, "adv_rank": 150,
        "mcap_usd": 50_000_000_000, "shares_est": None,
        "sector": "Technology", "sp500": False,
        "earn_next_date": None, "earn_next_time": None,
        "window_start": (NOW.date() - timedelta(days=1800)).isoformat(),
        "suspect": False,
    }
    rec.update(over)
    return rec


def _write_root(
    tmp_path: Path,
    *,
    quotes: dict,
    tiles: list[dict],
    pack_tickers: dict | None = None,
    hot_tape_cfg: str | None = None,
) -> Path:
    """A tmp repo root carrying exactly the artifacts the radar reads."""
    root = tmp_path
    (root / "data" / "marketing").mkdir(parents=True, exist_ok=True)
    (root / "site" / "marketdata").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)

    (root / "data" / "marketing" / "live_quotes_snapshot.json").write_text(
        json.dumps({"asof": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "quotes": quotes}),
        encoding="utf-8")
    (root / "site" / "marketdata" / "sp500_heatmap.json").write_text(
        json.dumps({"asof": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "tiles": tiles}),
        encoding="utf-8")
    if pack_tickers is not None:
        (root / "data" / "marketing" / "hot_tape_pack.json").write_text(
            json.dumps({"schema": "marketing.hot_tape_pack/v1",
                        "built_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "trade_date": TRADE_DATE,
                        "n_tickers": len(pack_tickers),
                        "sources": {}, "tickers": pack_tickers}),
            encoding="utf-8")
    # Production posture: the daily cap is unlimited (autonomous cadence), so a
    # cap rejection here would be a fixture artefact rather than a radar rule.
    (root / "config" / "marketing.yml").write_text(
        "sentinel:\n  max_posts_per_account_per_day: -1\n", encoding="utf-8")
    if hot_tape_cfg is not None:
        (root / "config" / "hot_tape.yml").write_text(hot_tape_cfg, encoding="utf-8")
    return root


def _mover_root(tmp_path: Path, **kw) -> Path:
    """One big single-name drop, nothing else firing."""
    return _write_root(
        tmp_path,
        quotes={"MU": _quote(-8.2, 92.0, 100.2), "XYZ": _quote(0.4, 50.0, 49.8)},
        tiles=[_tile("MU", "Technology", "Semiconductors", -8.2),
               _tile("XYZ", "Utilities", "Utilities - Regulated", 0.4)],
        pack_tickers={"MU": _pack_rec()},
        **kw,
    )


def _sector_root(tmp_path: Path, **kw) -> Path:
    """An industry-wide slide too small for the mover threshold (4%).

    Tickers are LETTERS ONLY on purpose: the wire's cashtag regex stops at the
    first digit, so a `$SM0` would leave a bare "0" for the numeric-consistency
    gate to reject and the whole post would (correctly) refuse.
    """
    syms = [f"SM{c}" for c in "ABCDEFGH"]
    quotes = {s: _quote(-3.0 - i * 0.1, 90.0, 92.8) for i, s in enumerate(syms)}
    tiles = [_tile(s, "Technology", "Semiconductors", -3.0 - i * 0.1)
             for i, s in enumerate(syms)]
    return _write_root(tmp_path, quotes=quotes, tiles=tiles, pack_tickers={}, **kw)


def _no_fetch(url: str, dest: Path) -> bool:
    """Fetcher seam wired shut — this suite never touches the network."""
    return False


def _fired_rows(root: Path) -> list[dict]:
    path = root / "data/marketing/hot_tape_fired.jsonl"
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _stub_chart(monkeypatch, *, media_url: str = "https://pub-test.r2.dev/c/hot.png") -> list[dict]:
    """Stand in for the Chrome raster + R2 upload with the shape they return.

    Returns the CALL LOG: rendering a card is a Chrome raster plus an R2 upload,
    so "was this drawn again?" is a real question a test needs to ask (M10).
    """
    calls: list[dict] = []

    def _fake(packet, *, root, marketing_cfg, as_of, now, fetcher=None, **kw):
        calls.append({"ticker": packet.ticker, "key": packet.key, **kw})
        chart_id = f"hottape-{packet.trigger}-{str(packet.ticker).lower()}-{now.strftime('%H%M')}Z"
        return {
            "media": {"kind": "chart_svg",
                      "path": f"data/marketing/outbox/media/{as_of}/{chart_id}.svg",
                      "chart_id": chart_id, "ticker": packet.ticker,
                      "media_url": media_url,
                      "media_png_path": f"data/marketing/outbox/media/{as_of}/{chart_id}.png"},
            "published": {"chart_id": chart_id, "media_url": media_url,
                          "media_png_path": f"data/marketing/outbox/media/{as_of}/{chart_id}.png"},
            "reason": "ok",
        }
    monkeypatch.setattr(RADAR, "resolve_chart", _fake)
    return calls


@pytest.fixture(autouse=True)
def _dark_publisher(monkeypatch):
    """Every test runs with the kill switch OFF, like a fresh CI env."""
    monkeypatch.delenv("MARKETING_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("HOT_TAPE_DEMO", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)


# ─────────────────────────────────────────────────────────────────────────────
# 1 — the emit loop, end to end
# ─────────────────────────────────────────────────────────────────────────────

class TestEmitEndToEnd:
    def test_mover_event_books_a_charted_breaking_item(self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)

        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0

        items = OB.read_items(root)
        assert len(items) == 1, items
        item = items[0]
        assert item["kind"] == "breaking"
        assert item["scheduled_at"] == "immediate"
        assert item["provenance"] == "hot_tape"
        assert item["priority"] == 1
        assert item["slot"] == f"HOT-{NOW.strftime('%H%M')}Z"
        assert item["as_of"] == RADAR._et_day(NOW)
        assert "$MU" in item["text"]

        source = item["source"]
        assert source["lane"] == "hot_tape"
        assert source["trigger"] == "mover_drop"
        assert source["ticker"] == "MU"
        assert source["fact_packet"]["facts"]["pct"] == -8.2
        assert source["baseline_pct"] == -8.2
        assert source["story_key"]                       # the one-owner lock binds
        assert source["media_url"].startswith("https://")

        assert len(item["media"]) == 1
        media = item["media"][0]
        assert media["kind"] == "chart_svg"
        assert media["media_url"].startswith("https://")
        assert media["chart_id"].startswith("hottape-mover_drop-mu-")

        fired = [json.loads(x) for x in
                 (root / "data/marketing/hot_tape_fired.jsonl").read_text().splitlines() if x]
        assert len(fired) == 1
        assert fired[0]["item_id"] == item["id"]
        assert fired[0]["trigger"] == "mover_drop"
        assert fired[0]["day"] == DAY

        out = capsys.readouterr().out.splitlines()
        assert any(l.startswith("hot-tape DETECT mover_drop MU down sev=") for l in out), out
        booked = [l for l in out if l.startswith("hot-tape BOOKED ")]
        assert len(booked) == 1 and f"id={item['id']}" in booked[0]
        assert any(l.startswith(f"hot-tape DISPATCH ids={item['id']}") for l in out), out

    def test_ring_is_appended_on_an_eventless_pass(self, tmp_path):
        """The snapshot ring is the intraday history — it advances every pass."""
        root = _write_root(tmp_path, quotes={"XYZ": _quote(0.2, 50.0, 49.9)},
                           tiles=[_tile("XYZ", "Utilities", "Utilities - Regulated", 0.2)],
                           pack_tickers={})
        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0
        assert OB.read_items(root) == []
        ring = HT.load_ring(root)
        assert len(ring) == 1
        assert ring[0]["day"] == DAY and ring[0]["n_events"] == 0
        assert ring[0]["n_quotes"] >= 1

    def test_github_output_carries_the_booked_ids(self, tmp_path, monkeypatch):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        item_id = OB.read_items(root)[0]["id"]
        assert out_file.read_text(encoding="utf-8").strip() == f"post_now_ids={item_id}"


# ─────────────────────────────────────────────────────────────────────────────
# 2 + 3 — the chart law
# ─────────────────────────────────────────────────────────────────────────────

class TestChartLaw:
    def test_chartless_single_name_event_is_dropped_not_enqueued(self, tmp_path, capsys):
        """Operator law: every ticker post carries a chart.

        The publisher's defer queue is NOT a parking lot, and `breaking` is
        outside its chart-bearing gate anyway — so a card we cannot draw means
        the post does not exist, not that it ships bare.
        """
        root = _mover_root(tmp_path)          # no price parquet anywhere, no network

        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0

        assert OB.read_items(root) == []
        assert not (root / "data/marketing/hot_tape_fired.jsonl").exists()
        out = capsys.readouterr().out
        assert re.search(r"^hot-tape DROP mover:MU:down:\S+ no-bars$", out, re.M), out
        assert "hot-tape BOOKED" not in out

    def test_no_media_url_drops_the_post(self, tmp_path, monkeypatch, capsys):
        """A card rendered but never hosted is no card at all (Buffer needs a URL)."""
        def _hostless(packet, *, root, marketing_cfg, as_of, now, fetcher=None, **kw):
            return {"media": None, "published": {"chart_id": "x"}, "reason": "no-media-url"}
        monkeypatch.setattr(RADAR, "resolve_chart", _hostless)
        root = _mover_root(tmp_path)

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        assert OB.read_items(root) == []
        assert "no-media-url" in capsys.readouterr().out

    def test_sector_event_ships_text_only(self, tmp_path, capsys):
        """A breadth post is about a GROUP — lawful without a card in P1."""
        root = _sector_root(tmp_path)

        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0

        items = OB.read_items(root)
        assert len(items) == 1, items
        assert items[0]["kind"] == "breaking"
        assert items[0]["media"] == []
        assert items[0]["source"]["trigger"] in ("sector_rout", "sector_rip")
        assert items[0]["source"]["ticker"] is None
        # One story, one post: the industry and its parent sector both qualify
        # here and the detector emits only the more extreme of the pair.
        assert "Technology" in items[0]["text"]
        assert "hot-tape DROP" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# 4 — dedupe across passes
# ─────────────────────────────────────────────────────────────────────────────

class TestDedupe:
    def test_second_pass_on_the_same_tape_books_nothing(self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)

        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        first = OB.read_items(root)
        assert len(first) == 1
        capsys.readouterr()

        # Same tape five minutes later: the fired ledger holds the cooldown.
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        assert [i["id"] for i in OB.read_items(root)] == [first[0]["id"]]
        out = capsys.readouterr().out
        assert "hot-tape BOOKED" not in out
        assert len(HT.load_ring(root)) == 2       # the ring still advances

    def test_sector_event_fires_once_per_direction_per_day(self, tmp_path, capsys):
        # Regression pin for the granularity flip-flop: the fired-key filter in
        # _detect_group_moves must run AFTER the industry/parent overlap
        # suppression, or a fired group's rival (the same names at the other
        # granularity) re-emits on the next pass as a "new" story.
        root = _sector_root(tmp_path)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        capsys.readouterr()

        RADAR.run(root, now=NOW + timedelta(minutes=10), fetcher=_no_fetch)

        assert len(OB.read_items(root)) == 1
        assert "hot-tape DETECT" not in capsys.readouterr().out


# ─────────────────────────────────────────────────────────────────────────────
# 5 — the schedule guard
# ─────────────────────────────────────────────────────────────────────────────

class TestWindowGuard:
    def test_outside_the_window_is_a_quiet_no_op(self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)

        assert RADAR.run(root, now=NOW.replace(hour=6, minute=0), fetcher=_no_fetch) == 0

        assert OB.read_items(root) == []
        assert HT.load_ring(root) == []
        notices = [l for l in capsys.readouterr().out.splitlines() if l.startswith("::")]
        assert len(notices) == 1 and notices[0].startswith("::notice title=hot-tape::"), notices

    def test_weekend_is_a_quiet_no_op(self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        saturday = NOW + timedelta(days=(5 - NOW.weekday()) % 7 or 7)
        assert saturday.weekday() == 5

        assert RADAR.run(root, now=saturday, fetcher=_no_fetch) == 0

        assert OB.read_items(root) == []
        assert [l for l in capsys.readouterr().out.splitlines() if l.startswith("::")]

    def test_demo_proceeds_outside_the_window_and_stamps_the_item(
            self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)

        assert RADAR.run(root, now=NOW.replace(hour=6, minute=0), demo=True,
                         fetcher=_no_fetch) == 0

        items = OB.read_items(root)
        assert len(items) == 1
        assert items[0]["source"]["demo"] is True
        assert items[0]["source"]["fact_packet"]["provenance"]["demo"] is True
        assert "hot-tape BOOKED" in capsys.readouterr().out

    def test_dry_run_writes_nothing(self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)

        assert RADAR.run(root, now=NOW, dry_run=True, fetcher=_no_fetch) == 0

        assert OB.read_items(root) == []
        assert HT.load_ring(root) == []
        assert not (root / "data/marketing/hot_tape_fired.jsonl").exists()
        out = capsys.readouterr().out
        assert "hot-tape DETECT mover_drop MU down" in out
        # No local bars: the simulation refuses the card exactly as the live path would.
        assert "hot-tape DROP" in out and "hot-tape BOOKED" not in out


# ─────────────────────────────────────────────────────────────────────────────
# Routing — flagship mirrors the BIGGEST events only (operator 2026-07-28)
# ─────────────────────────────────────────────────────────────────────────────

_ROUTING_CFG = (
    "hot_tape:\n"
    "  emit:\n"
    "    flagship_severity_floor: 85\n"
    "    flagship_max_per_run: 1\n"
)


def _sector_packet(label: str, median: float, severity: float, leaders: list,
                   *, members: int, down: int) -> FactPacket:
    return FactPacket(
        trigger="sector_rout",
        key=f"sector:{label}:down:{DAY}",
        fired_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        session="rth",
        ticker=None, name=None, sector=label,
        direction="down",
        severity=severity,
        facts={"sector": label, "group_kind": "industry", "median_pct": median,
               "breadth_pct": round(down / members * 100.0, 2),
               "n_members": members, "n_down": down,
               "leaders": leaders, "dollar_moved_usd": None, "index_pct": None},
        provenance={"demo": False, "bridge_ok": True},
    )


# Three real groups off the 2026-07-28 tape. Member counts differ as well as
# names and numbers: three routs whose copy agrees on too many tokens are
# genuinely near-duplicates and outbox.enqueue's cross-account radar (0.50) will
# refuse the third — correctly. See test_a_near_identical_rout_is_refused.
_P_TOP = _sector_packet("Computer Hardware", -6.91, 90.0,
                        [["AAA", -9.1], ["BBB", -8.4], ["CCC", -7.2]],
                        members=9, down=8)
_P_MID = _sector_packet("Semiconductor Equipment", -6.18, 90.0,
                        [["DDD", -8.8], ["EEE", -7.9], ["FFF", -6.6]],
                        members=24, down=21)
_P_LOW = _sector_packet("Drug Manufacturers", -3.70, 87.0,
                        [["GGG", -5.2], ["HHH", -4.8], ["III", -4.1]],
                        members=41, down=33)


def _emit_three(root: Path, packets: list) -> list[str]:
    cfg = HT.load_config(root)
    return RADAR.emit(
        packets, root=root, cfg=cfg,
        marketing_cfg=RADAR._load_marketing_cfg(root),
        fired_today=[], now=NOW, as_of=DAY, demo=False, dry_run=False,
        fetcher=_no_fetch,
    )


class TestFlagshipBudget:
    def test_only_the_top_event_mirrors_to_flagship(self, tmp_path):
        """Three routs clear the floor in one sweep; exactly one may mirror.

        Group routs carry base severity 80-90, so a floor alone routes EVERY
        routine rout to the flagship and leaves the wire desk dark — measured on
        the 2026-07-28 tape, three industry routs in one sweep.
        """
        root = _write_root(tmp_path, quotes={}, tiles=[], pack_tickers={},
                           hot_tape_cfg=_ROUTING_CFG)
        cfg = HT.load_config(root)
        assert cfg["emit"]["flagship_severity_floor"] == 85
        # All three are flagship-ELIGIBLE by severity alone …
        for packet in (_P_TOP, _P_MID, _P_LOW):
            assert HT.severity_account(packet, cfg) == "flagship"

        booked = _emit_three(root, [_P_TOP, _P_MID, _P_LOW])

        assert len(booked) == 3
        by_id = {i["id"]: i for i in OB.read_items(root)}
        accounts = [by_id[i]["account"] for i in booked]
        assert accounts == ["flagship", "mastermind_news", "mastermind_news"], accounts

    def test_a_deduped_flagship_event_does_not_burn_the_budget(self, tmp_path):
        """The budget is spent on a POST, not on an attempt."""
        root = _write_root(tmp_path, quotes={}, tiles=[], pack_tickers={},
                           hot_tape_cfg=_ROUTING_CFG)
        cfg = HT.load_config(root)
        mcfg = RADAR._load_marketing_cfg(root)
        # Pre-seed the exact item the top event would build, so its enqueue
        # comes back "duplicate" (a re-run of the same pass).
        text = HW.compose_wire(_P_TOP, cfg=cfg)["text"]
        seed = OB.make_item(account="flagship", kind="breaking", text=text, as_of=DAY,
                            media=[], scheduled_at="immediate", slot="HOT-SEED",
                            priority=1, provenance="hot_tape", source={"lane": "hot_tape"})
        assert OB.enqueue(seed, root, cfg=mcfg) == "queued"

        booked = _emit_three(root, [_P_TOP, _P_MID, _P_LOW])

        by_id = {i["id"]: i for i in OB.read_items(root)}
        accounts = [by_id[i]["account"] for i in booked]
        assert accounts == ["flagship", "mastermind_news"], accounts
        # The refused event is remembered WITHOUT an item_id: the suppression
        # held, so it must not consume the day's emit budget either.
        fired = [json.loads(x) for x in
                 (root / "data/marketing/hot_tape_fired.jsonl").read_text().splitlines() if x]
        assert [f["item_id"] for f in fired].count(None) == 1

    def test_run_cap_stops_at_three(self, tmp_path):
        root = _write_root(tmp_path, quotes={}, tiles=[], pack_tickers={},
                           hot_tape_cfg=_ROUTING_CFG)
        extra = _sector_packet("Oil & Gas Midstream", -2.90, 86.0,
                               [["JJJ", -4.2], ["KKK", -3.8], ["LLL", -3.1]],
                               members=17, down=15)
        booked = _emit_three(root, [_P_TOP, _P_MID, _P_LOW, extra])
        assert len(booked) == 3

    def test_a_near_identical_rout_is_refused_by_the_existing_guard(self, tmp_path):
        """Gate 0.5, unchanged and load-bearing for this lane.

        Two desks posting the same sentence about different groups is the
        coordination signal the cross-account near-dup radar exists to deny. The
        radar does not get an exemption: it logs the skip, records the fire with
        NO item_id, and the day's emit budget is untouched.
        """
        root = _write_root(tmp_path, quotes={}, tiles=[], pack_tickers={},
                           hot_tape_cfg=_ROUTING_CFG)
        twin = _sector_packet("Semiconductors", -6.90, 88.0,
                              [["AAA", -9.1], ["BBB", -8.4], ["CCC", -7.2]],
                              members=9, down=8)
        booked = _emit_three(root, [_P_TOP, twin])
        assert len(booked) == 1
        fired = _fired_rows(root)
        # M10: the refusal is a TERMINAL verdict on that text today, so it is
        # remembered — otherwise the same event is re-detected, re-rendered (a
        # Chrome raster + an R2 upload) and re-refused every five minutes.
        assert [f["item_id"] for f in fired] == [booked[0], None]
        assert fired[1]["sector"] == "Semiconductors"


class TestDemoBlastRadius:
    """M5 — demo relaxes EVERY threshold at once, and with the publisher armed
    those are real posts. One item, wire desk, never the flagship."""

    def test_two_flagship_events_in_demo_book_one_wire_post(self, tmp_path):
        root = _write_root(tmp_path, quotes={}, tiles=[], pack_tickers={},
                           hot_tape_cfg=_ROUTING_CFG)
        cfg = HT.load_config(root)
        # Both are flagship-eligible by severity alone …
        for packet in (_P_TOP, _P_MID):
            assert HT.severity_account(packet, cfg) == "flagship"

        booked = RADAR.emit([_P_TOP, _P_MID], root=root, cfg=cfg,
                            marketing_cfg=RADAR._load_marketing_cfg(root),
                            fired_today=[], now=NOW, as_of=DAY, demo=True,
                            dry_run=False, fetcher=_no_fetch)

        assert len(booked) == 1
        items = OB.read_items(root)
        assert len(items) == 1
        assert items[0]["account"] == "mastermind_news"

    def test_the_same_events_outside_demo_keep_the_normal_budget(self, tmp_path):
        root = _write_root(tmp_path, quotes={}, tiles=[], pack_tickers={},
                           hot_tape_cfg=_ROUTING_CFG)
        booked = _emit_three(root, [_P_TOP, _P_MID])
        by_id = {i["id"]: i for i in OB.read_items(root)}
        assert [by_id[i]["account"] for i in booked] == ["flagship", "mastermind_news"]


class TestTerminalEnqueueVerdicts:
    """M10 — a guard's final NO must be remembered, or the radar re-offers the
    same event (and re-pays for its card) every five minutes."""

    def test_a_cross_account_duplicate_is_recorded_and_never_redrawn(
            self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        calls = _stub_chart(monkeypatch)
        monkeypatch.setattr(RADAR.OB, "enqueue",
                            lambda *a, **k: "cross_account_duplicate")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        assert len(calls) == 1                      # one raster + upload paid for
        fired = _fired_rows(root)
        assert len(fired) == 1
        assert fired[0]["item_id"] is None and fired[0]["ticker"] == "MU"
        assert OB.read_items(root) == []
        capsys.readouterr()

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        out = capsys.readouterr().out
        assert "hot-tape DETECT" not in out         # the cooldown holds …
        assert len(calls) == 1                      # … so nothing is re-rendered
        assert len(_fired_rows(root)) == 1

    def test_a_cap_rejection_is_recorded_too(self, tmp_path, monkeypatch):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        monkeypatch.setattr(RADAR.OB, "enqueue", lambda *a, **k: "cap_exceeded")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        assert [f["item_id"] for f in _fired_rows(root)] == [None]

    def test_an_invalid_item_is_not_recorded_and_shouts(
            self, tmp_path, monkeypatch, capsys):
        """OUR bug, not a guard doing its job: it must recur loudly, not be
        quietly absorbed into the cooldown memory."""
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        monkeypatch.setattr(RADAR.OB, "enqueue", lambda *a, **k: "invalid:text too long")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        assert _fired_rows(root) == []
        out = capsys.readouterr().out
        warn = [l for l in out.splitlines()
                if l.startswith("::warning title=hot-tape-invalid-item::")]
        assert len(warn) == 1, out


class TestCarryoverDispatch:
    """M4 — the dispatch is a ONE-SHOT API call the workflow only makes when
    this pass booked something, so an item whose own dispatch was lost sat in
    the queue until the next scheduled sweep — exactly the latency the program
    exists to beat."""

    @staticmethod
    def _seed_queued(root: Path, *, text: str, minutes_ago: int, ticker: str) -> str:
        when = NOW - timedelta(minutes=minutes_ago)
        item = OB.make_item(
            account="mastermind_news", kind="breaking", text=text, as_of=DAY,
            media=[], scheduled_at="immediate", slot="HOT-SEED", priority=1,
            provenance="hot_tape", source={"lane": "hot_tape"}, now=when)
        assert OB.enqueue(item, root, cfg=RADAR._load_marketing_cfg(root)) == "queued"
        HT.append_fired(root, {
            "key": f"mover:{ticker}:down:{DAY}:0", "trigger": "mover_drop",
            "ticker": ticker, "direction": "down", "magnitude": -6.0,
            "fired_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "item_id": item["id"], "account": "mastermind_news"})
        return item["id"]

    def test_a_recent_unposted_item_rides_the_next_dispatch(
            self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        carried = self._seed_queued(
            root, ticker="OLD", minutes_ago=6,
            text="Consumer Defensive: 18 of 21 names higher today, median 1.4%.")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        fresh = [i["id"] for i in OB.read_items(root) if i["id"] != carried]
        assert len(fresh) == 1
        # Oldest first: the carried item has been waiting longer.
        assert out_file.read_text(encoding="utf-8").strip() == \
            f"post_now_ids={carried},{fresh[0]}"
        assert f"hot-tape DISPATCH ids={carried},{fresh[0]}" in capsys.readouterr().out

    def test_an_item_past_the_carryover_window_is_warned_not_dispatched(
            self, tmp_path, monkeypatch, capsys):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        stale = self._seed_queued(
            root, ticker="OLD", minutes_ago=25,
            text="Consumer Defensive: 18 of 21 names higher today, median 1.4%.")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        fresh = [i["id"] for i in OB.read_items(root) if i["id"] != stale]
        assert out_file.read_text(encoding="utf-8").strip() == f"post_now_ids={fresh[0]}"
        warn = [l for l in capsys.readouterr().out.splitlines()
                if l.startswith("::warning title=hot-tape-unposted::")]
        assert len(warn) == 1 and stale in warn[0], warn

    def test_a_posted_item_is_never_re_dispatched(self, tmp_path, monkeypatch):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        done = self._seed_queued(
            root, ticker="OLD", minutes_ago=6,
            text="Consumer Defensive: 18 of 21 names higher today, median 1.4%.")
        assert OB.transition(done, "approved", actor="test", root=root) is True
        assert OB.transition(done, "posted", actor="test", root=root) is True

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        fresh = [i["id"] for i in OB.read_items(root) if i["id"] != done]
        assert out_file.read_text(encoding="utf-8").strip() == f"post_now_ids={fresh[0]}"

    def test_an_eventless_pass_still_carries_a_pending_item(
            self, tmp_path, monkeypatch):
        """The dispatch is no longer conditional on THIS pass booking."""
        root = _write_root(tmp_path, quotes={"XYZ": _quote(0.2, 50.0, 49.9)},
                           tiles=[_tile("XYZ", "Utilities", "Utilities - Regulated", 0.2)],
                           pack_tickers={})
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        carried = self._seed_queued(
            root, ticker="OLD", minutes_ago=6,
            text="Consumer Defensive: 18 of 21 names higher today, median 1.4%.")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        assert out_file.read_text(encoding="utf-8").strip() == f"post_now_ids={carried}"


class TestSuspectHistoryCard:
    """M13 — the detectors refuse a split-suspect's FACTS; the PICTURE has to go
    with them when the only bars available come from the un-adjusted store."""

    def test_a_suspect_name_on_massive_only_bars_is_dropped(self, tmp_path, capsys):
        root = _write_root(
            tmp_path,
            quotes={"MU": _quote(-8.2, 92.0, 100.2)},
            tiles=[_tile("MU", "Technology", "Semiconductors", -8.2)],
            pack_tickers={"MU": _pack_rec(suspect=True)})

        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0

        assert OB.read_items(root) == []
        out = capsys.readouterr().out
        assert re.search(r"^hot-tape DROP mover:MU:down:\S+ suspect-history$", out, re.M), out

    def test_a_clean_name_refuses_for_the_ordinary_reason(self, tmp_path, capsys):
        root = _mover_root(tmp_path)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        out = capsys.readouterr().out
        assert "suspect-history" not in out
        assert re.search(r"^hot-tape DROP mover:MU:down:\S+ no-bars$", out, re.M), out

    def test_massive_only_detection(self, tmp_path):
        (tmp_path / "data" / RADAR.HYDRATE_SUBDIR.split("/")[-1]).mkdir(parents=True)
        assert RADAR._is_massive_only("MU", tmp_path) is True     # nothing local yet
        (tmp_path / RADAR.HYDRATE_SUBDIR / "MU.parquet").write_bytes(b"")
        assert RADAR._is_massive_only("MU", tmp_path) is True
        curated = tmp_path / "data" / "stocks"
        curated.mkdir(parents=True, exist_ok=True)
        (curated / "MU.parquet").write_bytes(b"")
        assert RADAR._is_massive_only("MU", tmp_path) is False

    def test_a_suspect_name_with_curated_bars_is_not_pre_refused(self, tmp_path, capsys):
        """The gate is about the STORE, not the ticker: a curated tree is
        split-adjusted, so a suspect name renders from it normally."""
        root = _write_root(
            tmp_path,
            quotes={"MU": _quote(-8.2, 92.0, 100.2)},
            tiles=[_tile("MU", "Technology", "Semiconductors", -8.2)],
            pack_tickers={"MU": _pack_rec(suspect=True)})
        curated = root / "data" / "stocks"
        curated.mkdir(parents=True, exist_ok=True)
        (curated / "MU.parquet").write_bytes(b"")     # unreadable, but present

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        out = capsys.readouterr().out
        assert "suspect-history" not in out
        assert "hot-tape DROP" in out                 # refused later, on the bars


class TestPerQuoteStaleness:
    """m4 — the freshness gate reads the FRESHEST quote, so a merge that passes
    still carries entries hours old, and a detector cannot tell them apart."""

    def test_a_three_hour_old_quote_never_reaches_the_detectors(
            self, tmp_path, monkeypatch, capsys):
        old_ts = int((NOW - timedelta(hours=3)).timestamp() * 1000)
        root = _write_root(
            tmp_path,
            quotes={"MU": _quote(-8.2, 92.0, 100.2),
                    "STALE": {"price": 40.0, "prevClose": 50.0,
                              "changePct": -20.0, "ts": old_ts}},
            tiles=[_tile("MU", "Technology", "Semiconductors", -8.2)],
            pack_tickers={"MU": _pack_rec(), "STALE": _pack_rec()})
        _stub_chart(monkeypatch)

        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0

        out = capsys.readouterr().out
        assert "hot-tape DETECT mover_drop MU down" in out
        assert "STALE" not in out
        assert [i["source"]["ticker"] for i in OB.read_items(root)] == ["MU"]
        assert re.search(r"^hot-tape quote-age kept=\d+ dropped=1 ", out, re.M), out

    def test_a_fresh_merge_is_passed_through_untouched(self, tmp_path):
        root = _mover_root(tmp_path)
        live, fresh, _ = RADAR.load_quotes(root, now=NOW, cfg=HT.load_config(root),
                                           demo=False)
        assert fresh
        assert set(live["quotes"]) >= {"MU", "XYZ"}

    def test_demo_keeps_its_relaxed_ceiling(self, tmp_path):
        """Demo's huge ceiling is the whole point: it runs off yesterday's close."""
        old_ts = int((NOW - timedelta(hours=3)).timestamp() * 1000)
        root = _write_root(
            tmp_path,
            quotes={"MU": _quote(-8.2, 92.0, 100.2),
                    "STALE": {"price": 40.0, "prevClose": 50.0,
                              "changePct": -20.0, "ts": old_ts}},
            tiles=[], pack_tickers={})
        live, fresh, _ = RADAR.load_quotes(root, now=NOW, cfg=HT.load_config(root),
                                           demo=True)
        assert fresh and set(live["quotes"]) == {"MU", "STALE"}


# ─────────────────────────────────────────────────────────────────────────────
# 6 — the safety stack is untouched AND exercised (gate 0.5)
# ─────────────────────────────────────────────────────────────────────────────

class TestSafetyStack:
    def test_kill_switch_is_off_by_default(self):
        """Nothing this lane queues can post while the switch is dark."""
        assert SEN.publish_enabled() is False

    def test_transition_legality_holds_for_a_hot_tape_item(self, tmp_path, monkeypatch):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        item_id = OB.read_items(root)[0]["id"]

        # The illegal shortcut stays illegal for a breaking item too.
        assert OB.transition(item_id, "posted", actor="test", root=root) is False
        assert OB.transition(item_id, "approved", actor="test", root=root) is True
        assert OB.transition(item_id, "posted", actor="test", root=root) is True
        # …and the recall edge — the other half of the kill switch — is open.
        assert OB.transition(item_id, "recalled", actor="test", root=root) is True
        assert OB.transition(item_id, "approved", actor="test", root=root) is False
        assert OB.current_statuses(root)[item_id] == "recalled"

    def test_safety_modules_are_not_edited_by_this_program(self):
        """The stack Hot Tape rides on is READ-ONLY to it (gate 0.5).

        A radar that "fixes" a sentinel rule to get its own post out has removed
        the guard, not passed it. These files are named so an edit shows up as a
        failing test rather than as a quiet diff in an unrelated PR.
        """
        for rel in ("engine/marketing/sentinel.py", "engine/marketing/live_verify.py",
                    "engine/marketing/outbox.py", "engine/marketing/copywriter.py",
                    "scripts/marketing_publisher.py", "config/marketing.yml"):
            path = REPO_ROOT / rel
            assert path.exists(), rel
            assert "hot_tape" not in path.read_text(encoding="utf-8"), (
                f"{rel} mentions hot_tape — the safety stack must stay untouched")


# ─────────────────────────────────────────────────────────────────────────────
# 7 — the suite pins its own CI wiring (unrun-suite rot dies here)
# ─────────────────────────────────────────────────────────────────────────────

_HOT_TAPE_SUITES = (
    "tests/test_marketing_hot_tape.py",
    "tests/test_marketing_hot_tape_pack.py",
    "tests/test_marketing_hot_tape_radar.py",
)


class TestCIWiring:
    def test_every_suite_is_named_in_a_pytest_run_line(self):
        text = (REPO_ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
        run_lines = [l for l in text.splitlines() if "python -m pytest" in l]
        assert run_lines
        for suite in _HOT_TAPE_SUITES:
            assert any(suite in l for l in run_lines), f"{suite} runs in NO job"

    def test_thin_and_fat_lanes_get_the_right_suites(self):
        """The split is the contract: no pandas in the radar's own lane."""
        text = (REPO_ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
        thin = [l for l in text.splitlines()
                if "python -m pytest" in l and "tests/test_marketing_engine.py" in l]
        fat = [l for l in text.splitlines()
               if "python -m pytest" in l and "tests/test_marketing_chart_coverage.py" in l
               and "-rs" in l]
        assert len(thin) == 1 and len(fat) == 1
        assert "tests/test_marketing_hot_tape.py" in thin[0]
        assert "tests/test_marketing_hot_tape_radar.py" in thin[0]
        assert "tests/test_marketing_hot_tape_pack.py" in fat[0]
        assert "tests/test_marketing_hot_tape_pack.py" not in thin[0]

    def test_ci_trigger_paths_cover_every_new_file(self):
        text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        entries = set(re.findall(r'^\s*-\s*"([^"]+)"\s*$', text, re.M))
        for rel in _HOT_TAPE_SUITES + ("scripts/hot_tape_radar.py", "config/hot_tape.yml"):
            assert rel in entries, f"{rel} is not a ci.yml trigger path"

    def test_the_radar_workflow_is_wired_to_its_own_schedule(self):
        """The crons span BOTH DST regimes; the ET guard trims the edges (M6).

        A single UTC pair is right for one half of the year: 09:25-16:05 ET is
        13:25-20:05Z under EDT and 14:25-21:05Z under EST, so the old
        13:25-20:05Z schedule would have gone dark for the last hour of every
        session from the November clock change.
        """
        text = (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
            encoding="utf-8")
        for cron in ('- cron: "25,30,35,40,45,50,55 13 * * 1-5"',
                     '- cron: "*/5 14-20 * * 1-5"',
                     '- cron: "0,5 21 * * 1-5"'):
            assert cron in text, cron
        assert '"*/5 14-19 * * 1-5"' not in text     # the EDT-only schedule
        assert "cancel-in-progress: false" in text
        assert "python -m scripts.hot_tape_radar" in text
        # NO pandas on the intraday path — the install line IS the contract.
        installs = [l for l in text.splitlines() if l.strip().startswith("run: pip install")]
        assert installs == ["        run: pip install --quiet pyyaml requests pyarrow"], installs

    def test_the_checkout_cone_covers_every_path_the_radar_reads(self):
        """M11 — 81 runs a day on a 12m budget cannot pay for a 2.8GB tree.

        The cone is the radar's exact read+write surface. Anything the radar
        opens that is NOT in it comes back missing at runtime, which for the
        curated price trees would mean every card fell back to the R2-hydrated
        massive store and got refused as "chart-stale".
        """
        import yaml as _yaml

        wf = _yaml.safe_load(
            (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
                encoding="utf-8"))
        checkout = [s for s in wf["jobs"]["radar"]["steps"]
                    if str(s.get("uses", "")).startswith("actions/checkout")]
        assert len(checkout) == 1
        with_ = checkout[0]["with"]
        assert with_["fetch-depth"] == 1
        assert with_["filter"] == "blob:none"
        cone = {line.strip() for line in str(with_["sparse-checkout"]).splitlines()
                if line.strip()}
        assert cone == {
            "engine", "scripts", "lib", "config",
            "data/marketing", "data/earnings",
            "data/baskets/ohlcv", "data/stocks",
            "site/marketdata", "site/live",
        }, cone
        # Every path the commit step stages must be inside the cone, or the
        # radar would write outside its own checkout.
        staged = set(re.findall(
            r"^\s*git add (\S+)",
            (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
                encoding="utf-8"), re.M))
        assert all(any(p == c or p.startswith(c + "/") for c in cone) for p in staged), staged

    def test_the_wide_price_order_is_the_radar_alone(self):
        """M13 — the radar's tuple and chart_render's opt-in tuple cannot drift."""
        from engine.marketing import chart_render as CR

        assert RADAR.PRICE_SUBDIRS == CR.HOT_TAPE_PRICE_SUBDIRS
        assert CR._PRICE_SUBDIRS == ("data/baskets/ohlcv", "data/stocks")

    def test_the_radar_lane_never_writes_a_forward_ledger(self):
        """Ledger law: outbox + the two hot-tape ledgers, nothing else."""
        text = (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
            encoding="utf-8")
        staged = set(re.findall(r"^\s*git add (\S+)", text, re.M))
        assert staged == {"data/marketing/outbox",
                          "data/marketing/hot_tape_ring.jsonl",
                          "data/marketing/hot_tape_fired.jsonl"}, staged

    def test_the_append_only_ledgers_carry_union_merge(self):
        text = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
        assert "data/marketing/hot_tape_ring.jsonl merge=union" in text
        assert "data/marketing/hot_tape_fired.jsonl merge=union" in text


# ─────────────────────────────────────────────────────────────────────────────
# The operator's tuning surface
# ─────────────────────────────────────────────────────────────────────────────

class TestShippedConfig:
    def test_config_is_loadable_and_carries_the_load_bearing_knobs(self):
        cfg = HT.load_config(REPO_ROOT)
        assert cfg["enabled"] is True
        # EASTERN, not UTC (M6): the same window in both DST regimes.
        assert cfg["window_et"] == {"start": "09:25", "end": "16:05"}
        assert "window_utc" not in cfg
        assert cfg["window_grace_min"] == HT.DEFAULTS["window_grace_min"] == 10
        assert cfg["wire"]["max_chars"] == HW.MAX_CHARS
        assert cfg["universe"]["workers"] == 4
        assert cfg["universe"]["budget_s"] == 240
        assert cfg["universe"]["max_lag_weekdays"] == 10
        assert cfg["emit"]["flagship_max_per_run"] == 1
        # Routs start at severity 80, so a floor below ~85 mirrors every routine
        # rout to the flagship (operator 2026-07-28). The tuning surface and the
        # in-code default must not drift apart on this one.
        assert cfg["emit"]["flagship_severity_floor"] == 85
        assert HT.DEFAULTS["emit"]["flagship_severity_floor"] == 85

    def test_config_only_overrides_keys_the_engine_knows(self):
        """A typo in the tuning surface is a dead knob — catch it here."""
        known_extras = {"enabled", "universe.workers", "universe.budget_s",
                        "wire.max_chars", "emit.flagship_max_per_run"}

        def _flat(node, prefix=""):
            out = {}
            for k, v in node.items():
                path = f"{prefix}.{k}" if prefix else k
                out.update(_flat(v, path) if isinstance(v, dict) else {path: v})
            return out

        shipped = set(_flat(HT.load_config(REPO_ROOT)))
        defaults = set(_flat(HT.DEFAULTS))
        assert shipped - defaults == known_extras, shipped - defaults
