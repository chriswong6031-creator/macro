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

…and the E1 completion wave (research/MARKETING_CONTENT_STUDIO_LLM_FIRST_
MASTERPLAN_BY_FABLE.md §10):

  * **P2 phrasing is WIRED** — engine/marketing/hot_tape_llm shipped in #3937
    with zero production callers; an AST scan pins the call site, and the
    behaviour tests pin that model copy replaces the template, is stamped for
    telemetry, and falls back on a house-ban hit or an exception.
  * **the earnings calendar read** — pyarrow, never pandas, degrading to an
    empty view rather than an exception.
  * **two-step publish** — a severity>=90 alert earns ONE context brief on a
    LATER tick, on its own desk, with a mechanism or not at all.

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

    def test_a_duplicate_costs_no_render_at_all(self, tmp_path, monkeypatch, capsys):
        """The card is drawn AFTER the copy is known to be publishable.

        The fired ledger stops a re-DETECT, but it cannot help the first time a
        packet is offered against copy the outbox already holds. resolve_chart
        is a Chrome raster plus an R2 upload and it used to run BEFORE enqueue,
        so that first offer paid full price for an image the dedupe guard was
        always going to refuse — charged to a nightly render budget that is law.

        Nothing enqueue rejects on depends on the picture, so the verdict is
        available before the render. Here the fired ledger is deliberately wiped
        so the packet IS re-detected: the only thing standing between it and a
        second raster is the preflight.
        """
        root = _mover_root(tmp_path)
        calls = _stub_chart(monkeypatch)

        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        assert len(OB.read_items(root)) == 1
        assert len(calls) == 1, "the first, legitimate render"
        capsys.readouterr()

        # Wipe the cooldown memory: force the radar to offer the same event again.
        (root / HT.FIRED_REL).unlink()

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        out = capsys.readouterr().out
        assert "hot-tape DETECT" in out, "the packet must actually be re-offered"
        assert len(calls) == 1, (
            "the duplicate was re-rendered — a Chrome raster and an R2 upload "
            "spent on a post the outbox refuses on text alone"
        )
        assert "preflight, no render" in out
        assert len(OB.read_items(root)) == 1, "and nothing extra was queued"

    def test_the_preflight_answers_exactly_what_enqueue_would(self, tmp_path):
        """A preflight that disagrees with the gate is worse than none.

        It would either waste the render it promised to save, or drop a post
        enqueue would have taken. Both callers therefore run the SAME
        `_rejection_reason` over the SAME `_enqueue_ctx`; this pins that they
        agree on every code, not just on the happy path.
        """
        import inspect

        src = inspect.getsource(OB)
        assert src.count("def _rejection_reason") == 1
        # Both paths must go through the one definition.
        assert "_rejection_reason(" in inspect.getsource(OB.preflight_enqueue)
        assert "_rejection_reason(" in inspect.getsource(OB.enqueue)
        assert "_enqueue_ctx(" in inspect.getsource(OB.preflight_enqueue)
        assert "_enqueue_ctx(" in inspect.getsource(OB.enqueue)

        # And it agrees in fact, not only in structure.
        item = OB.make_item(account="mastermind_x", kind="breaking",
                            text="A one-off line about $MU and its tape.",
                            as_of="2026-07-30", provenance="hot_tape")
        assert OB.preflight_enqueue(
            account="mastermind_x", kind="breaking", text=item["text"],
            as_of="2026-07-30", root=tmp_path) == "ok"
        assert OB.enqueue(item, tmp_path) == "queued"
        # Now the same copy is a duplicate to BOTH.
        assert OB.preflight_enqueue(
            account="mastermind_x", kind="breaking", text=item["text"],
            as_of="2026-07-30", root=tmp_path) == "duplicate"
        assert OB.enqueue(item, tmp_path) == "duplicate"

    def test_the_preflight_fails_OPEN_and_can_never_cause_an_outage(self):
        """It may only skip work. It may never be the reason a post is lost."""
        import inspect

        src = inspect.getsource(OB.preflight_enqueue)
        tail = src.split("except Exception")[-1]
        assert 'return "ok"' in tail, (
            "a preflight that cannot read the corpus must assume the post is "
            "fine — at worst that costs one wasted render"
        )

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


class TestRemoteQuotePlane:
    """The VPS live plane is config-driven and must never fire in a bare checkout.

    The radar reads a REMOTE quote source (config.yml ``live.public_quotes_url``)
    because every repo-local artifact is written by a throttled GitHub lane. That
    source is a bonus, never a dependency, and it must not turn a unit test into a
    web request — hence "no config, no remote".
    """

    def test_a_root_without_config_yml_resolves_to_no_remote_source(self, tmp_path):
        RADAR.remote_quote_urls.cache_clear()
        assert RADAR.remote_quote_urls(tmp_path) == ()

    def test_the_shipped_config_arms_the_plane(self):
        RADAR.remote_quote_urls.cache_clear()
        urls = RADAR.remote_quote_urls(REPO_ROOT)
        assert urls and all(u.startswith("https://") for u in urls)

    def test_an_operator_can_disable_it_with_an_empty_value(self, tmp_path):
        (tmp_path / "config.yml").write_text('live:\n  public_quotes_url: ""\n')
        RADAR.remote_quote_urls.cache_clear()
        assert RADAR.remote_quote_urls(tmp_path) == ()

    def test_load_quotes_passes_the_resolved_urls_through(self, tmp_path, monkeypatch):
        """The wiring itself — a resolver nothing calls is the shape that ships dead."""
        (tmp_path / "config.yml").write_text('live:\n  public_quotes_url: "https://vps/q"\n')
        RADAR.remote_quote_urls.cache_clear()
        seen: dict = {}

        def _spy(root, *, remote_urls=None, **kw):
            seen["urls"] = remote_urls
            return {"quotes": {}, "asof": None, "source": "none", "feed_delay_min": 0.0}

        monkeypatch.setattr(RADAR.LV, "load_live_quotes", _spy)
        RADAR.load_quotes(tmp_path, now=NOW, cfg={}, demo=False)
        assert seen["urls"] == ("https://vps/q",)


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

    #: The ONE sanctioned reference from a safety module into this program, and
    #: it points the safe way: ``copywriter`` CALLS the wire desk's numeric gate
    #: to make the filing lanes STRICTER (B4 — the reporting lag is a bare 1-2
    #: digit integer, which is exactly the class validate_copy exempts, so the
    #: one number a disclosure post exists to state honestly was the one number
    #: the model could write freely). Nothing about Hot Tape's own posting path
    #: changes, and `numeric_violations` can only ADD violations: there is no
    #: argument to it that lets a post through that would otherwise be refused.
    #: Scoped to that ONE symbol: any other hot_tape name in a safety module —
    #: the radar, the emit path, a config knob — still fails this test.
    #:
    #: The SECOND sanctioned reference, granted on the same reasoning and
    #: scoped the same way: the publisher's send-time orphan-brief gate imports
    #: ``hot_tape.orphaned_brief_status`` (plus the two identity constants that
    #: say which rows it applies to) and can only ever REFUSE a brief whose
    #: parent alert is no longer posted. There is no argument to it that lets a
    #: post through that would otherwise be refused, which is the whole test of
    #: whether a reach into this program has removed a guard or added one.
    #:
    #: WHY it must live in the publisher at all: the radar re-checks the parent
    #: at dispatch, but that sweep only runs when the radar runs. An operator
    #: recall after the last pass of the day (end of the ET window, a weekend,
    #: the workflow disabled) leaves an already-booked brief on its
    #: scheduled_at and the publisher's scheduled sweep is the only thing left
    #: between it and the network.
    #:
    #: Scoped to those THREE symbols on ONE import line: any other hot_tape
    #: name in the publisher — a posting rule, a cap, a cadence knob — still
    #: fails this test.
    _SANCTIONED_HOT_TAPE_REFS: dict[str, tuple[str, ...]] = {
        "engine/marketing/copywriter.py": ("hot_tape_llm", "numeric_violations"),
        "scripts/marketing_publisher.py": (
            "hot_tape", "LANE", "BRIEF_TRIGGER", "orphaned_brief_status"),
    }

    def test_safety_modules_are_not_edited_by_this_program(self):
        """The stack Hot Tape rides on is READ-ONLY to it (gate 0.5).

        A radar that "fixes" a sentinel rule to get its own post out has removed
        the guard, not passed it. These files are named so an edit shows up as a
        failing test rather than as a quiet diff in an unrelated PR — which is
        what the allowance above is: a reviewed exception, recorded by name,
        rather than a loosened rule.
        """
        for rel in ("engine/marketing/sentinel.py", "engine/marketing/live_verify.py",
                    "engine/marketing/outbox.py", "engine/marketing/copywriter.py",
                    "scripts/marketing_publisher.py", "config/marketing.yml"):
            path = REPO_ROOT / rel
            assert path.exists(), rel
            required = self._SANCTIONED_HOT_TAPE_REFS.get(rel)
            hits = [ln for ln in path.read_text(encoding="utf-8").splitlines()
                    if "hot_tape" in ln]
            if required is None:
                assert not hits, (
                    f"{rel} mentions hot_tape — the safety stack must stay "
                    f"untouched: {hits[:3]}")
                continue
            assert hits, (
                f"{rel} no longer references hot_tape at all; delete its "
                "allowance rather than leaving it as cover for the next edit")
            for line in hits:
                assert all(tok in line for tok in required), (
                    f"{rel} reaches into hot_tape for something other than "
                    f"{'/'.join(required)}: {line.strip()!r}")


# ─────────────────────────────────────────────────────────────────────────────
# 6a — P2 phrasing: the LLM wire desk is WIRED, not merely built (§10 E1)
# ─────────────────────────────────────────────────────────────────────────────

def _fake_phraser(monkeypatch, **result):
    """Stand in for engine.marketing.hot_tape_llm.phrase_or_fallback.

    Returns the CALL LOG. The real module is never armed in this suite: no env
    flag, no credential, no provider is constructed anywhere.
    """
    calls: list[dict] = []

    def _fake(packet, trigger, fallback_text, *, link=None, links_allowed=True, cfg=None):
        calls.append({"packet": packet, "trigger": trigger,
                      "fallback": fallback_text, "link": link,
                      "links_allowed": links_allowed, "cfg": cfg})
        out = {"text": fallback_text, "mode": "off", "provider": None,
               "violations": [], "latency_ms": 3}
        out.update(result)
        if out.get("text") is None:
            out["text"] = fallback_text
        return out

    monkeypatch.setattr(RADAR.HL, "phrase_or_fallback", _fake)
    return calls


class TestLLMPhrasing:
    def test_the_emit_path_actually_calls_phrase_or_fallback(self):
        """#3937 built the module and left it with ZERO production callers.

        An AST scan, not a grep: a call inside a docstring or a comment is not a
        caller, and this is exactly the defect E1 exists to close.
        """
        import ast

        tree = ast.parse((REPO_ROOT / "scripts/hot_tape_radar.py").read_text(
            encoding="utf-8"))
        funcs = {n.name: n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)}
        assert "phrase" in funcs and "book_packet" in funcs

        def _called(node) -> set[str]:
            out = set()
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                fn = sub.func
                if isinstance(fn, ast.Attribute):
                    out.add(fn.attr)
                elif isinstance(fn, ast.Name):
                    out.add(fn.id)
            return out

        assert "phrase_or_fallback" in _called(funcs["phrase"])
        # …and the booking path is what calls it, so every composed post goes
        # through the desk rather than only a helper nothing invokes.
        assert "phrase" in _called(funcs["book_packet"])
        assert "compose_wire" in _called(funcs["book_packet"])

    def test_model_copy_replaces_the_template_and_is_stamped(self, tmp_path,
                                                             monkeypatch):
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        model_text = "$MU is down 8.2% at $92.00 right now, a $8.2 billion move."
        calls = _fake_phraser(monkeypatch, text=model_text, mode="llm",
                              provider="oauth", latency_ms=812)

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        item = OB.read_items(root)[0]
        assert item["text"] == model_text
        stamp = item["source"]["llm"]
        assert stamp == {"mode": "llm", "provider": "oauth",
                         "latency_ms": 812, "violations": 0}
        assert len(calls) == 1
        # The deterministic template is what the desk falls back TO, so it must
        # arrive as the fallback argument rather than being thrown away.
        assert calls[0]["fallback"].startswith("$MU")
        assert calls[0]["trigger"] == "mover_drop"
        # Hot Tape posts carry no link (the wire voice bans them).
        assert calls[0]["link"] is None and calls[0]["links_allowed"] is False

    def test_a_disarmed_desk_posts_the_deterministic_template(self, tmp_path,
                                                              monkeypatch):
        """No env flag and no credential: the template is the post, unchanged."""
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        item = OB.read_items(root)[0]
        assert item["source"]["llm"]["mode"] == "off"
        assert item["source"]["llm"]["provider"] is None
        assert item["text"].startswith("$MU")
        assert HW.check_text_numbers(item["text"],
                                     HT.FactPacket(**item["source"]["fact_packet"])) == []

    def test_house_banned_language_in_model_copy_falls_back(self, tmp_path,
                                                            monkeypatch, capsys):
        """hot_tape_llm's call list is NARROWER than this desk's own ban list.

        "accumulate" / "load up" / "calls" / "puts" / "bid" are house-banned
        (gate 0.4) and absent from the LLM module's _CALL_WORDS, so the radar
        re-checks model copy against hot_tape_wire.WIRE_BANNED.
        """
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)
        _fake_phraser(monkeypatch, mode="llm", provider="anthropic",
                      text="$MU is down 8.2% right now. Time to accumulate.")

        RADAR.run(root, now=NOW, fetcher=_no_fetch)

        item = OB.read_items(root)[0]
        assert "accumulate" not in item["text"]
        assert item["text"].startswith("$MU")             # the template posted
        assert item["source"]["llm"]["mode"] == "fallback_validation"
        assert item["source"]["llm"]["violations"] >= 1
        out = capsys.readouterr().out
        assert any(l.startswith("::warning title=hot-tape-llm-banned::")
                   for l in out.splitlines()), out

    def test_a_raising_phraser_still_posts_the_template(self, tmp_path, monkeypatch):
        def _boom(*a, **kw):
            raise RuntimeError("provider exploded")
        monkeypatch.setattr(RADAR.HL, "phrase_or_fallback", _boom)
        root = _mover_root(tmp_path)
        _stub_chart(monkeypatch)

        assert RADAR.run(root, now=NOW, fetcher=_no_fetch) == 0

        item = OB.read_items(root)[0]
        assert item["text"].startswith("$MU")
        assert item["source"]["llm"]["mode"] == "fallback_provider"

    def test_the_llm_packet_carries_the_facts_and_not_the_score(self):
        """Severity is a ranking score, not a claim about the tape.

        Anything reachable in the packet is admissible under gate 0.3, so a
        severity of 87 in there would license the model to write "87".
        """
        packet = FactPacket(
            trigger="sector_rout", key="sector:Semis:down:x",
            fired_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), session="rth",
            ticker=None, name=None, sector="Semiconductors", direction="down",
            severity=87.0,
            facts={"sector": "Semiconductors", "median_pct": -7.85,
                   "leaders": [["SNDK", -14.32], ["MU", -8.94]],
                   "index_ticker": "SPY"},
            provenance={"quote_ts_ms": 1799999999999, "bridge_ok": True})
        out = HW.llm_packet(packet)
        assert out["trigger"] == "sector_rout"
        assert out["facts"]["median_pct"] == -7.85
        assert out["cashtags"] == ["$SNDK", "$MU", "$SPY"]
        assert out["cashtag"] is None                  # breadth post, no primary
        assert "severity" not in json.dumps(out)
        assert "1799999999999" not in json.dumps(out)
        assert out["live_marker"] in ("so far today", "right now")

    def test_the_llm_packet_lists_every_cashtag_the_copy_may_name(self):
        packet = FactPacket(
            trigger="mover_drop", key="mover:MU:down:x:0",
            fired_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), session="rth",
            ticker="MU", name="Micron", sector="Technology", direction="down",
            severity=90.0,
            facts={"ticker": "MU", "pct": -8.2,
                   "peers": [["SNDK", -9.1], ["STX", -8.4]]},
            provenance={})
        out = HW.llm_packet(packet)
        assert out["cashtag"] == "$MU"
        assert out["cashtags"] == ["$MU", "$SNDK", "$STX"]

    def test_the_llm_packet_excludes_the_alert_key_and_the_counters(self):
        """M6. `severity` and `provenance` were kept out BY NAME, so every fact
        key a later detector added walked straight into the admissible set. The
        two-step brief's `alert_key` is the live example: an internal id whose
        digits ("...:2026-07-29T14:05:00Z:0") licensed 2026, 29, 14 and 05 as
        figures the model could write about a stock that moved 8%."""
        from engine.marketing.hot_tape_llm import numeric_violations

        packet = FactPacket(
            trigger="context_brief", key="brief:mover:MU:down:x:0",
            fired_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), session="rth",
            ticker="MU", name="Micron", sector="Technology", direction="down",
            severity=91.0,
            facts={"ticker": "MU", "pct": -8.2, "price": 92.0,
                   "alert_key": "mover:MU:down:2026-07-29T14:05:00Z:0",
                   "alert_trigger": "mover_drop", "subject": "MU",
                   "mechanism": "single_name",
                   "peers": [["SNDK", -0.3], ["STX", -0.4]]},
            provenance={})
        out = HW.llm_packet(packet)

        for key in ("alert_key", "alert_trigger", "subject"):
            assert key not in out["facts"], key
        assert "2026-07-29T14:05:00Z" not in json.dumps(out)
        # ...and the gate that reads this packet now REJECTS those digits.
        assert numeric_violations("$MU is down 14% right now.", out)
        assert numeric_violations("$MU has fallen 05 sessions running.", out)
        # The real number still passes, so this is a narrowing, not a muzzle.
        assert numeric_violations("$MU is down 8.2% at $92.", out) == []
        # Peers stay a cashtag source even though their numbers are not quotable.
        assert out["cashtags"] == ["$MU", "$SNDK", "$STX"]

    def test_the_llm_packet_forwards_every_key_a_clause_renders(self):
        """The allowlist's staleness guard: a new device that reads a new fact
        key must be added to LLM_FACT_KEYS, or the model would be told to phrase
        a fact whose number it is then rejected for using."""
        import re

        src = (REPO_ROOT / "engine" / "marketing" / "hot_tape_wire.py").read_text(
            encoding="utf-8")
        read = set(re.findall(r'(?:f|facts|src)(?:\.get\(|\[)"([a-z_0-9]+)"', src))
        read |= set(re.findall(r'_row_symbols\(f, "([a-z_0-9]+)"\)', src))
        assert read, "the scan found nothing — the regex has rotted"
        missing = sorted(read - HW.LLM_FACT_KEYS)
        assert not missing, (
            f"these fact keys are rendered by a clause but withheld from the "
            f"model that must phrase them: {missing}")

    def test_the_llm_block_comes_from_config_yml_not_the_radar_switch(self, tmp_path):
        """config/hot_tape.yml's top-level `enabled` is the RADAR's switch.

        hot_tape_llm._llm_cfg accepts a bare block and would read that key as
        its OWN arming flag, so handing it the radar config would arm the model
        lane the moment the radar was on. The wrapper resolves unambiguously.
        """
        (tmp_path / "config").mkdir(parents=True, exist_ok=True)
        (tmp_path / "config" / "hot_tape.yml").write_text(
            "enabled: true\n", encoding="utf-8")
        (tmp_path / "config.yml").write_text(
            "hot_tape:\n  llm:\n    enabled: true\n    max_tokens: 222\n",
            encoding="utf-8")

        block = RADAR.llm_config(tmp_path)

        assert block == {"llm": {"enabled": True, "max_tokens": 222}}
        # And the resolver hot_tape_llm actually uses agrees.
        from engine.marketing import hot_tape_llm as HTL
        assert HTL._llm_cfg(block) == {"enabled": True, "max_tokens": 222}
        # The radar's own config must NEVER resolve to an armed block.
        assert HTL._llm_cfg({"llm": {}}) == {}

    def test_an_absent_config_yml_leaves_the_desk_disarmed(self, tmp_path):
        assert RADAR.llm_config(tmp_path) == {"llm": {}}
        (tmp_path / "config.yml").write_text("hot_tape: not-a-dict\n", encoding="utf-8")
        assert RADAR.llm_config(tmp_path) == {"llm": {}}

    def test_the_live_config_ships_the_block_the_workflow_arms(self):
        import yaml as _yaml

        cfg = _yaml.safe_load((REPO_ROOT / "config.yml").read_text(encoding="utf-8"))
        block = (cfg.get("hot_tape") or {}).get("llm") or {}
        assert block.get("enabled") is True
        # CHATGPT-FIRST (operator directive 2026-07-29): codex leads every
        # marketing LLM lane so Claude subscription tokens stay reserved for
        # website-building sessions; the Claude oauth rung is the balanced
        # fallback behind it. Pinned here so a silent re-order is caught.
        assert block.get("provider_order") == ["codex", "oauth", "anthropic", "deepseek"]
        assert block.get("codex_source_model") == "gpt-5.6-terra"
        assert block.get("codex_reasoning_effort") == "low"
        assert block.get("oauth_pool_lane") == "hot-tape-wire"
        assert RADAR.llm_config(REPO_ROOT)["llm"] == block


# ─────────────────────────────────────────────────────────────────────────────
# 6b — the earnings calendar read (pyarrow, never pandas)
# ─────────────────────────────────────────────────────────────────────────────

class _FakeTable:
    def __init__(self, columns: dict):
        self._columns = columns

    @property
    def column_names(self) -> list[str]:
        return list(self._columns)

    def to_pydict(self) -> dict:
        return dict(self._columns)


def _fake_pyarrow(monkeypatch, columns: dict):
    """Inject a pyarrow.parquet stand-in so the REAL parsing path runs.

    The thin CI lane has no pyarrow (pytest+pyyaml+jinja2), and an
    importorskip here would let this test go dark — the unrun-suite rot class.
    Everything below the read is our code, and it is what runs.
    """
    import sys
    import types

    module = types.ModuleType("pyarrow.parquet")
    module.read_table = lambda path: _FakeTable(columns)   # noqa: ARG005
    parent = types.ModuleType("pyarrow")
    parent.parquet = module
    monkeypatch.setitem(sys.modules, "pyarrow", parent)
    monkeypatch.setitem(sys.modules, "pyarrow.parquet", module)


class TestEarningsLoader:
    def _root(self, tmp_path: Path) -> Path:
        (tmp_path / "data" / "earnings").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data" / "earnings" / "earnings.parquet").write_bytes(b"stub")
        return tmp_path

    def test_an_absent_calendar_is_an_empty_view(self, tmp_path):
        assert RADAR.load_earnings(tmp_path) == {"asof": None, "tickers": {}}

    def test_rows_are_parsed_with_their_surprise_history(self, tmp_path, monkeypatch):
        root = self._root(tmp_path)
        _fake_pyarrow(monkeypatch, {
            "ticker": ["aapl", "NVDA", ""],
            "next_date": ["2026-07-30", "nan", "2026-08-01"],
            "next_time": ["time-after-hours", "time-not-supplied", None],
            "eps_forecast": [1.88, None, 3.0],
            "surprises_json": ['[{"reported": "4/30/2026", "eps": 2.01}]', "", None],
            "as_of": ["2026-07-28T03:00:00+00:00", "2026-06-19T02:00:00+00:00", None],
        })

        view = RADAR.load_earnings(root)

        assert set(view["tickers"]) == {"AAPL", "NVDA"}     # blank symbol dropped
        aapl = view["tickers"]["AAPL"]
        assert aapl["next_date"] == "2026-07-30"
        assert aapl["next_time"] == "time-after-hours"
        assert aapl["eps_forecast"] == 1.88
        assert aapl["surprises"] == [{"reported": "4/30/2026", "eps": 2.01}]
        assert view["tickers"]["NVDA"]["next_date"] is None   # "nan" is not a date
        assert view["tickers"]["NVDA"]["surprises"] == []
        assert view["asof"] == "2026-07-28T03:00:00+00:00"    # the MAX as_of

    def test_a_broken_calendar_is_an_empty_view(self, tmp_path, monkeypatch):
        root = self._root(tmp_path)
        _fake_pyarrow(monkeypatch, {"nope": [1]})
        assert RADAR.load_earnings(root) == {"asof": None, "tickers": {}}

    def test_a_stale_calendar_says_so_at_the_start_of_the_line(self, capsys):
        """Degraded must not ship confident: a dark detector is visible."""
        old = (NOW - timedelta(days=120)).date().isoformat()
        RADAR._warn_stale_earnings(
            {"asof": old, "tickers": {"AAPL": {"as_of": old}}},
            now=NOW, cfg=HT.DEFAULTS)
        lines = capsys.readouterr().out.splitlines()
        assert any(l.startswith("::warning title=hot-tape-earnings::") for l in lines), lines

    def test_the_check_is_per_row_not_per_file(self, capsys):
        """The shipped parquet on 2026-07-29: 3 fresh rows, 1,361 forty days old.

        A whole-file max(as_of) called that calendar healthy while the detector
        could see 0.2% of it — the vacuous-green presence-vs-coverage class.
        """
        fresh = NOW.date().isoformat()
        old = (NOW - timedelta(days=40)).date().isoformat()
        rows = {f"T{i}": {"as_of": old} for i in range(20)}
        rows["AAPL"] = {"as_of": fresh}
        RADAR._warn_stale_earnings({"asof": fresh, "tickers": rows},
                                   now=NOW, cfg=HT.DEFAULTS)
        out = capsys.readouterr().out
        assert "only 1/21 earnings calendar rows" in out, out

    def test_a_fresh_calendar_is_silent(self, capsys):
        fresh = NOW.date().isoformat()
        RADAR._warn_stale_earnings(
            {"asof": fresh, "tickers": {"AAPL": {"as_of": fresh}}},
            now=NOW, cfg=HT.DEFAULTS)
        assert capsys.readouterr().out == ""

    def test_rows_inherit_the_view_asof_when_they_carry_none(self, capsys):
        RADAR._warn_stale_earnings(
            {"asof": NOW.date().isoformat(), "tickers": {"AAPL": {}}},
            now=NOW, cfg=HT.DEFAULTS)
        assert capsys.readouterr().out == ""


# ─────────────────────────────────────────────────────────────────────────────
# 6c — two-step publish: the context brief (codex law, §10 E1)
# ─────────────────────────────────────────────────────────────────────────────

_BRIEF_SYMS = ("MU", "SNDK", "STX", "NVDA", "AMD")

#: An S&P mega-cap: the attention boost is what lifts a -8.2% mover over the
#: two-step floor (90). Without it the same tape scores 70 and earns no brief,
#: which is the intended behaviour, not a fixture accident.
_BIG_NAME = {"sp500": True, "adv_rank": 50, "mcap_usd": 200_000_000_000}


def _brief_root(tmp_path: Path, *, peer_pct: float = -0.3, peers: bool = True,
                **kw) -> Path:
    """One brief-eligible mover plus four live peers, so a mechanism exists."""
    quotes = {"MU": _quote(-8.2, 92.0, 100.2)}
    tiles = [_tile("MU", "Technology", "Semiconductors", -8.2)]
    if peers:
        for sym in _BRIEF_SYMS[1:]:
            quotes[sym] = _quote(peer_pct, 50.0, 50.15)
            tiles.append(_tile(sym, "Technology", "Semiconductors", peer_pct))
    return _write_root(tmp_path, quotes=quotes, tiles=tiles,
                       pack_tickers={"MU": _pack_rec(**_BIG_NAME)}, **kw)


def _brief_items(root: Path) -> list[dict]:
    return [i for i in OB.read_items(root)
            if (i.get("source") or {}).get("trigger") == HT.BRIEF_TRIGGER]


def _post_alert(root: Path, *, now=NOW) -> str:
    """Walk the pass's alert to `posted` the way the publisher would.

    M2: a brief requires its alert to have POSTED, not merely to be sitting in
    the queue. A brief is the second half of a two-step publish ("here is why
    the thing you just saw matters"), so an alert still waiting on the
    publisher's gates has no first half yet, and one that is quarantined there
    never will. Every fixture below that expects a brief therefore has to post
    its alert first, and the ones that expect NO brief post it too, so the
    reason under test (floor, age, mechanism, demo) is the reason that fires.
    """
    item = next(i for i in OB.read_items(root)
                if (i.get("source") or {}).get("trigger") != HT.BRIEF_TRIGGER)
    OB.transition(item["id"], "approved", actor="test", root=root, now=now)
    OB.transition(item["id"], "posted", actor="test", root=root, now=now)
    return item["id"]


class TestTwoStepBrief:
    def test_the_brief_follows_on_a_LATER_tick_never_the_alert_pass(
            self, tmp_path, monkeypatch, capsys):
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)

        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        alerts = OB.read_items(root)
        assert len(alerts) == 1
        assert alerts[0]["source"]["severity"] >= 90
        assert _brief_items(root) == []            # not in the alert's own pass
        _post_alert(root)
        capsys.readouterr()

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        briefs = _brief_items(root)
        assert len(briefs) == 1, [i["text"] for i in OB.read_items(root)]
        brief = briefs[0]
        assert brief["kind"] == "breaking"
        assert brief["scheduled_at"] == "immediate"
        assert brief["provenance"] == "hot_tape"
        assert brief["source"]["fact_packet"]["facts"]["alert_key"] == \
            alerts[0]["source"]["fact_packet"]["key"]
        # The mechanism is the whole reason a brief exists (codex).
        assert "not following" in brief["text"] or "group move" in brief["text"]
        assert "mechanism_clause" in brief["source"]["devices"]
        # A ticker post carries a chart, brief or not (operator law).
        assert brief["media"] and brief["media"][0]["media_url"].startswith("https://")
        out = capsys.readouterr().out
        assert any(l.startswith("hot-tape BRIEF ") for l in out.splitlines()), out

    def test_one_brief_per_event_forever(self, tmp_path, monkeypatch):
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)
        assert len(_brief_items(root)) == 1

        RADAR.run(root, now=NOW + timedelta(minutes=10), fetcher=_no_fetch)
        RADAR.run(root, now=NOW + timedelta(minutes=15), fetcher=_no_fetch)

        assert len(_brief_items(root)) == 1

    def test_an_event_under_the_floor_never_earns_a_brief(self, tmp_path,
                                                          monkeypatch):
        root = _brief_root(tmp_path,
                           hot_tape_cfg="two_step:\n  min_severity: 101\n")
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)
        assert _brief_items(root) == []

    def test_a_brief_ages_out_of_its_window(self, tmp_path, monkeypatch):
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)

        RADAR.run(root, now=NOW + timedelta(minutes=90), fetcher=_no_fetch)

        assert _brief_items(root) == []

    def test_the_brief_lands_on_the_alerts_own_desk(self, tmp_path, monkeypatch):
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        alert = OB.read_items(root)[0]
        assert alert["account"] == "flagship"       # severity >= 85 mirrors
        _post_alert(root)

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        # A brief on a different desk than its alert is an orphan, and the
        # flagship per-run mirror budget is about NEW stories, not follow-ups.
        assert _brief_items(root)[0]["account"] == "flagship"

    def test_a_group_wide_tape_says_group_move(self, tmp_path, monkeypatch):
        root = _brief_root(tmp_path, peer_pct=-7.5)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)
        briefs = _brief_items(root)
        assert briefs, "no brief filed"
        assert "This is a group move" in briefs[0]["text"]

    def test_no_peers_no_brief(self, tmp_path, monkeypatch, capsys):
        """Gate 0.2 for the brief: no mechanism, no post."""
        root = _brief_root(tmp_path, peers=False)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        capsys.readouterr()

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        assert _brief_items(root) == []
        assert "BRIEF-REFUSE" in capsys.readouterr().out

    def test_a_demo_pass_files_no_brief(self, tmp_path, monkeypatch):
        """A demo is bounded to ONE post (reviewer M5)."""
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        assert RADAR.pending_briefs(
            root, fired_today=HT.load_fired(root, DAY),
            live={"quotes": {}}, pack=None, heatmap=None,
            now=NOW + timedelta(minutes=5), cfg=HT.load_config(root),
            demo=True) == []

    def test_a_dead_alert_gets_no_brief(self, tmp_path, monkeypatch):
        """A brief explaining a quarantined post is an orphan."""
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        item_id = OB.read_items(root)[0]["id"]
        assert OB.transition(item_id, "quarantined", actor="test", root=root,
                             note="fixture", now=NOW)

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        assert _brief_items(root) == []

    def test_the_brief_is_phrased_through_the_same_desk(self, tmp_path, monkeypatch):
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        calls = _fake_phraser(monkeypatch)

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        triggers = [c["trigger"] for c in calls]
        assert HT.BRIEF_TRIGGER in triggers, triggers

    def test_an_alert_that_never_POSTED_earns_no_brief(self, tmp_path, monkeypatch):
        """M2. `queued` is not `posted`: the publisher has not run yet, and its
        gates (copy, cap, tape, kill switch) can still quarantine the alert. A
        brief filed against a queued alert is a "why this matters" for a post
        that may never exist."""
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        alert = OB.read_items(root)[0]
        assert alert["status"] == "queued" if "status" in alert else True

        # No walk to `posted` this time: the alert sits in the queue.
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)
        assert _brief_items(root) == []

        # ...and the moment it posts, the same pass produces the brief, so this
        # is a WAIT, not a kill.
        _post_alert(root)
        RADAR.run(root, now=NOW + timedelta(minutes=10), fetcher=_no_fetch)
        assert len(_brief_items(root)) == 1

    def test_an_approved_but_unposted_alert_earns_no_brief(self, tmp_path,
                                                           monkeypatch):
        """The near-miss spelling: `approved` reads like a green light and is
        not one. The item is cleared to post and has not posted."""
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        alert = OB.read_items(root)[0]
        OB.transition(alert["id"], "approved", actor="test", root=root, now=NOW)

        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        assert _brief_items(root) == []

    def test_an_alert_outranks_a_brief_in_the_queue(self, tmp_path, monkeypatch):
        """M2, second half. The publisher considers items by (priority,
        scheduled_at, id). At equal priority an older brief would be picked up
        ahead of a fresh alert purely on its timestamp, which inverts the whole
        point of an intraday wire."""
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)

        alerts = [i for i in OB.read_items(root)
                  if (i.get("source") or {}).get("trigger") != HT.BRIEF_TRIGGER]
        briefs = _brief_items(root)
        assert alerts and briefs
        assert all(i["priority"] == 1 for i in alerts), [i["priority"] for i in alerts]
        assert all(i["priority"] == 2 for i in briefs), [i["priority"] for i in briefs]
        assert briefs[0]["priority"] > alerts[0]["priority"]

    def test_briefs_have_their_own_budget_and_never_steal_an_alert_slot(self):
        """An alert is time-critical; a brief must not cost it a slot."""
        cfg = HT.load_config(REPO_ROOT)
        assert cfg["two_step"]["max_per_run"] == 1
        assert cfg["emit"]["max_per_run"] >= 1
        assert cfg["two_step"]["delay_min"] > 0     # never the alert's own pass


class TestABriefNeverOutlivesItsAlert:
    """The residual ordering hole behind M2's build-time gate (#3960 minor).

    ``pending_briefs`` requires the alert to be ``posted`` when the brief is
    BUILT. That is a snapshot. A booked brief that does not post on its own
    dispatch (a lost push race, a superseded publisher run) sits queued and
    every later pass inside ``CARRYOVER_MAX_AGE_MIN`` re-dispatches it -- and a
    dispatch is ``post_now``, which skips schedule gating entirely. Recall the
    alert in that gap and the second half of a two-step publish goes out
    explaining a post nobody ever saw, which is precisely what M2 existed to
    prevent.
    """

    @staticmethod
    def _brief_and_alert(root: Path) -> tuple[dict, dict]:
        briefs = _brief_items(root)
        alerts = [i for i in OB.read_items(root)
                  if (i.get("source") or {}).get("trigger") != HT.BRIEF_TRIGGER]
        assert briefs and alerts
        return briefs[0], alerts[0]

    def _booked_brief(self, tmp_path, monkeypatch) -> tuple[Path, dict, dict]:
        """A posted alert plus its queued brief -- the state the hole opens in."""
        root = _brief_root(tmp_path)
        _stub_chart(monkeypatch)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        _post_alert(root)
        RADAR.run(root, now=NOW + timedelta(minutes=5), fetcher=_no_fetch)
        brief, alert = self._brief_and_alert(root)
        return root, brief, alert

    def test_a_recalled_alert_stops_its_queued_brief_from_being_dispatched(
            self, tmp_path, monkeypatch, capsys):
        root, brief, alert = self._booked_brief(tmp_path, monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))
        # The operator kills the alert AFTER it was accepted (scripts/marketing_
        # _recall.py's transition): `posted` -> `recalled`.
        assert OB.transition(alert["id"], "recalled", actor="test", root=root,
                             note="fixture recall", now=NOW) is True
        capsys.readouterr()

        RADAR.run(root, now=NOW + timedelta(minutes=10), fetcher=_no_fetch)

        dispatched = out_file.read_text(encoding="utf-8") if out_file.exists() else ""
        assert brief["id"] not in dispatched, dispatched
        # And it is DEAD, not deferred: the scheduled publish sweep must not
        # send it either.
        assert OB.fold_state(root)["status"][brief["id"]] == "quarantined"
        warn = [l for l in capsys.readouterr().out.splitlines()
                if l.startswith("::warning title=hot-tape-orphan-brief::")]
        assert len(warn) == 1 and brief["id"] in warn[0], warn

    def test_a_still_posted_alert_lets_its_brief_ride_the_next_dispatch(
            self, tmp_path, monkeypatch):
        """The control. The gate must not eat a legitimate carryover brief."""
        root, brief, _alert = self._booked_brief(tmp_path, monkeypatch)
        out_file = tmp_path / "gh_output.txt"
        monkeypatch.setenv("GITHUB_OUTPUT", str(out_file))

        ids = RADAR.dispatch_ids(root, [], fired_today=HT.load_fired(root, DAY),
                                 now=NOW + timedelta(minutes=8))

        assert brief["id"] in ids
        assert OB.fold_state(root)["status"][brief["id"]] == "queued"

    def test_a_quarantined_alert_stops_its_queued_brief(self, tmp_path,
                                                        monkeypatch, capsys):
        """The quarantined spelling of the same hole, at the dispatch seam.

        ``posted -> quarantined`` is not a legal outbox transition, so this state
        is reached the way production would reach it if the ledger ever carried
        it: the gate must key on "is the parent posted", never on "is the parent
        absent from a known-dead list".
        """
        root, brief, alert = self._booked_brief(tmp_path, monkeypatch)
        rows = HT.load_fired(root, DAY)
        statuses = {alert["id"]: "quarantined", brief["id"]: "queued"}
        monkeypatch.setattr(OB, "fold_state", lambda *_a, **_k: {"status": statuses})
        capsys.readouterr()

        ids = RADAR.dispatch_ids(root, [], fired_today=rows,
                                 now=NOW + timedelta(minutes=8))

        assert brief["id"] not in ids
        assert "::warning title=hot-tape-orphan-brief::" in capsys.readouterr().out

    def test_an_unresolvable_parent_withholds_the_brief_without_killing_it(
            self, tmp_path, monkeypatch, capsys):
        """Fail closed, but do not DESTROY on missing evidence.

        A brief whose alert row cannot be found is withheld from the fast lane
        and ages out of the carryover window on its own. Quarantine is reserved
        for positive proof the alert is dead, so a fold hiccup cannot cost a
        legitimate brief its life.
        """
        root, brief, _alert = self._booked_brief(tmp_path, monkeypatch)
        rows = [r for r in HT.load_fired(root, DAY)
                if str(r.get("trigger") or "") == HT.BRIEF_TRIGGER]
        assert rows, "no brief row in the fired ledger"
        capsys.readouterr()

        ids = RADAR.dispatch_ids(root, [], fired_today=rows,
                                 now=NOW + timedelta(minutes=8))

        assert brief["id"] not in ids
        assert OB.fold_state(root)["status"][brief["id"]] == "queued"
        assert "unresolved" in capsys.readouterr().out

    def test_the_brief_key_round_trips_to_its_alert(self):
        """The dispatch gate can only re-check what it can resolve."""
        assert HT.parent_alert_key(HT.brief_key("mover:MU:down:2026-09-08:0")) == \
            "mover:MU:down:2026-09-08:0"
        assert HT.parent_alert_key("mover:MU:down:2026-09-08:0") is None
        assert HT.parent_alert_key("") is None
        assert HT.parent_alert_key("brief:") is None


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
        # anthropic joined for the P2 wire desk (§10 E1): engine/llm_auth builds
        # every provider on anthropic.Anthropic, DeepSeek included, so an armed
        # lane without it is mute by construction. pandas is still barred.
        #
        # boto3 joined 2026-07-31 and it is NOT optional decoration: the step
        # below is handed four R2 secrets, and without the client
        # media_publish.publish_chart_png returns None on every card, so
        # resolve_chart reports `no-media-url` and book_packet DROPS the post
        # rather than ship it bare. That is a whole day of single-name posts
        # deleted by a missing package, at full green — 2026-07-30 rendered
        # 8,081 cards and hosted none of them.
        installs = [l for l in text.splitlines() if l.strip().startswith("run: pip install")]
        assert installs == [
            "        run: pip install --quiet pyyaml requests pyarrow anthropic boto3"], installs
        # The two halves of that line stated as rules, so a future edit reads
        # WHY the string is what it is rather than just re-pinning it.
        assert "pandas" not in installs[0], "pandas is barred from the intraday path"
        assert "boto3" in installs[0], (
            "without boto3 this lane holds R2 credentials it cannot spend and "
            "every ticker post it detects is dropped for a missing picture"
        )

    def test_the_radar_step_carries_the_llm_arming_and_credential_block(self):
        """An armed lane with no visible credential is MUTE, not off (§10 E1).

        hot_tape_llm only builds a provider when BOTH the config block and
        MARKETING_LLM_ENABLED say so, and engine/llm_auth walks oauth pool ->
        anthropic -> deepseek. Missing any of those env names would make the
        lane print its "armed but mute" ::warning and post the deterministic
        template on every single event — the 2026-07-26 silent-mute shape,
        which is invisible unless someone reads the Actions log.
        """
        import yaml as _yaml

        wf = _yaml.safe_load(
            (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
                encoding="utf-8"))
        step = [s for s in wf["jobs"]["radar"]["steps"]
                if s.get("id") == "radar"]
        assert len(step) == 1
        env = step[0]["env"]
        assert env["MARKETING_LLM_ENABLED"] == "1"

        expected = ["ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN"]
        expected += [f"CLAUDE_CODE_OAUTH_TOKEN_{i}" for i in range(1, 8)]
        for name in expected:
            assert name in env, name
            # Every one is a SECRET reference, never a literal.
            assert f"secrets.{name}" in str(env[name]), (name, env[name])

        # The same block daily.yml's governor step passes — one waterfall, one
        # credential surface. A drift here is a lane quietly on fewer keys.
        daily = (REPO_ROOT / ".github/workflows/daily.yml").read_text(encoding="utf-8")
        for name in expected:
            assert f"{name}: ${{{{ secrets.{name} }}}}" in daily, name

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
            "app", "engine", "scripts", "lib", "config",
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

    def test_the_earnings_and_two_step_knobs_ship_and_mirror_the_defaults(self):
        cfg = HT.load_config(REPO_ROOT)
        earnings = cfg["detectors"]["earnings"]
        assert earnings == HT.DEFAULTS["detectors"]["earnings"]
        assert earnings["min_abs_pct"] == cfg["detectors"]["mover"]["min_abs_pct"]
        assert earnings["cooldown_min"] == cfg["detectors"]["mover"]["cooldown_min"]

        two_step = cfg["two_step"]
        assert two_step == HT.DEFAULTS["two_step"]
        # A brief is a bigger commitment than a flagship mirror, so its floor
        # sits ABOVE the mirror floor, and it never files on the alert's own
        # pass (delay_min > 0 is the "NEXT tick" rule).
        assert two_step["min_severity"] > cfg["emit"]["flagship_severity_floor"]
        assert two_step["delay_min"] > 0
        assert two_step["max_age_min"] > two_step["delay_min"]
        assert cfg["demo"]["earnings_min_abs_pct"] < earnings["min_abs_pct"]

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


# ─────────────────────────────────────────────────────────────────────────────
# The live tape the radar acts on
#
# On 2026-07-29 this lane fired ZERO events. Two stacked causes, both pinned here:
#
#   F1  the feed was stale. live-quotes.yml's 5-min tick has been gated off since
#       2026-07-27T22:50Z (VPS_LIVE_PRIMARY=true), leaving a */15 tape-gate tick
#       that GitHub's schedule starvation then delivered ~1.4x/hour — 11 of 128
#       ticks in the 8h RTH window, two of those dying at 8m06s in `git fetch`.
#       Measured merged-view ages tracked the last successful push exactly:
#       49.72m at 15:48Z vs a 14:58:23Z push, 21.92m at 18:08Z vs 17:46:53Z.
#
#   F2  the gate could not have passed anyway. A quote's ts is Yahoo's
#       regularMarketTime, a constant ~15.0m behind wall clock for equities
#       (measured 2026-07-30T03:46Z on names trading at the time), against a
#       12-minute ceiling.
#
# Fixing either alone leaves the lane dark, so both are pinned: the radar fetches
# its own tape when the shared one is behind, and the ceiling allows for the delay
# the feed declares while the book-collapse gate keeps a real-time crypto tick
# from certifying a stale equity book.
# ─────────────────────────────────────────────────────────────────────────────

def _aged_quote(minutes: float, pct: float = -8.2, price: float = 92.0,
                prev: float = 100.2) -> dict:
    """A snapshot-shaped quote whose ts is `minutes` behind the fixture clock."""
    return {"price": price, "prevClose": prev, "changePct": pct,
            "ts": int((NOW - timedelta(minutes=minutes)).timestamp() * 1000)}


def _write_snapshot(root: Path, quotes: dict, *, asof_min_ago: float = 0.0,
                    delayed_min: int | None = None) -> None:
    """Overwrite the merge's snapshot artifact, optionally declaring a feed delay."""
    obj: dict = {
        "asof": (NOW - timedelta(minutes=asof_min_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "quotes": quotes,
    }
    if delayed_min is not None:
        obj["meta"] = {"delayed_min": delayed_min, "realtime": delayed_min == 0}
    (root / RADAR.SNAPSHOT_REL).write_text(json.dumps(obj), encoding="utf-8")


def _date_stamped_heatmap(root: Path) -> None:
    """Re-stamp the heatmap's asof DATE-ONLY, the way production writes it.

    site/marketdata/sp500_heatmap.json carries `"asof": "YYYY-MM-DD"`, which
    _artifact_ms resolves to MIDNIGHT UTC — so intraday its tiles are hours old
    and the merge's per-ticker freshness rule lets a snapshot quote win. The
    suite's default fixture stamps a full timestamp instead, which makes every
    tile permanently fresh and hides exactly the interaction under test here.
    """
    path = root / "site" / "marketdata" / "sp500_heatmap.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    obj["asof"] = NOW.date().isoformat()
    path.write_text(json.dumps(obj), encoding="utf-8")


class TestDelayAwareFreshness:
    """F2: the 12-minute budget vs a feed that is contractually 15 minutes late."""

    def test_a_just_fetched_equity_book_is_actionable(self, tmp_path):
        """15.0m-old equities + a declared 15m delay = a fresh tape, not a stale one.

        This is the state immediately after a successful fetch, and before this
        fix it was indistinguishable from a dead feed.
        """
        root = _mover_root(tmp_path)
        _write_snapshot(root, {"MU": _aged_quote(15.0), "XYZ": _aged_quote(15.1, 0.4, 50.0, 49.8)},
                        delayed_min=15)
        live, fresh, age = RADAR.load_quotes(root, now=NOW, cfg=HT.load_config(root),
                                             demo=False)
        assert fresh, f"a just-fetched tape read as stale at {age}m"
        assert set(live["quotes"]) >= {"MU", "XYZ"}, (
            "the equity book must survive its own feed's declared delay")

    def test_a_real_time_tick_cannot_certify_a_stale_equity_book(self, tmp_path):
        """The 2026-07-29T18:08Z shape: FX at 21.92m over equities at ~37m.

        quotes_fresh gates on min(age), so one live FX print passes a merge whose
        every equity is half an hour behind. Detecting on what survives the drop
        would be worse than standing down, because nothing in the log would say
        the book had been emptied.
        """
        root = _mover_root(tmp_path)
        _date_stamped_heatmap(root)
        _write_snapshot(root, {
            "EURUSD=X": _aged_quote(21.92, 0.1, 1.14, 1.139),   # real-time leg
            "MU": _aged_quote(37.0),                            # 15m delay + 22m lag
            "XYZ": _aged_quote(37.0, 0.4, 50.0, 49.8),
        }, delayed_min=15)
        _, fresh, _ = RADAR.load_quotes(root, now=NOW, cfg=HT.load_config(root),
                                        demo=False)
        assert not fresh, (
            "a merge whose equity book collapses under the ceiling must stand the "
            "pass down, not detect on the surviving FX print")

    def test_the_stand_down_names_the_writer_lane(self, tmp_path, capsys):
        root = _mover_root(tmp_path)
        _date_stamped_heatmap(root)
        _write_snapshot(root, {"EURUSD=X": _aged_quote(21.92, 0.1, 1.14, 1.139),
                               "MU": _aged_quote(37.0),
                               "XYZ": _aged_quote(37.0, 0.4, 50.0, 49.8)},
                        delayed_min=15)
        RADAR.load_quotes(root, now=NOW, cfg=HT.load_config(root), demo=False)
        out = capsys.readouterr().out
        warn = [ln for ln in out.splitlines() if ln.startswith("::warning")]
        assert warn, out
        assert "book collapsed" in warn[0]
        assert "WRITER-LANE fault" in warn[0], (
            "the operator must be told this is a feed fault, not a knob to turn")


class TestRadarUniverse:
    """The symbol set a self-fetch covers: what the detectors can actually act on."""

    def test_heatmap_tiles_and_liquid_pack_names_are_in(self):
        heatmap = {"tiles": [_tile("MU", "Technology", "Semiconductors", -8.2),
                             _tile("XYZ", "Utilities", "Utilities - Regulated", 0.4)]}
        pack = {"tickers": {"AAPL": {"adv_rank": 3}, "MU": {"adv_rank": 40}}}
        got = RADAR.radar_universe(pack, heatmap, cfg=HT.DEFAULTS)
        assert {"MU", "XYZ", "AAPL"} <= set(got)
        assert got[:2] == ["MU", "XYZ"], "heatmap tiles lead so the cap never cuts them"

    def test_names_outside_adv_rank_max_are_left_out(self):
        pack = {"tickers": {"THIN": {"adv_rank": 2999}, "THICK": {"adv_rank": 12}}}
        got = RADAR.radar_universe(pack, {"tiles": []}, cfg=HT.DEFAULTS)
        assert "THICK" in got and "THIN" not in got

    def test_the_contrarian_index_proxy_is_always_fetched(self):
        got = RADAR.radar_universe(None, None, cfg=HT.DEFAULTS)
        assert got == ["SPY"], got

    def test_earnings_and_signal_names_join(self):
        got = RADAR.radar_universe(
            None, None,
            signals=[{"source": {"ticker": "NVDA"}}],
            earnings={"tickers": {"CRM": {}}},
            cfg=HT.DEFAULTS)
        assert {"NVDA", "CRM"} <= set(got)

    def test_a_junk_shaped_input_degrades_instead_of_raising(self):
        assert RADAR.radar_universe({"tickers": "nope"}, {"tiles": "nope"},
                                    cfg=HT.DEFAULTS) == ["SPY"]

    def test_the_universe_is_capped(self):
        pack = {"tickers": {f"T{i}": {"adv_rank": 1} for i in range(2000)}}
        got = RADAR.radar_universe(pack, {"tiles": []}, cfg=HT.DEFAULTS)
        assert len(got) == RADAR.MAX_SELF_FETCH_SYMBOLS


class TestSelfFetch:
    """F1: the radar refuses to inherit another lane's cadence."""

    @staticmethod
    def _snap(quotes: dict) -> dict:
        return {"asof": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "ts": 0,
                "source": "snapshot", "quotes": quotes,
                "meta": {"delayed_min": 15, "realtime": False}}

    def test_a_good_fetch_is_written_where_the_merge_reads(self, tmp_path):
        root = _mover_root(tmp_path)
        built = self._snap({"MU": _aged_quote(15.0), "XYZ": _aged_quote(15.0)})
        assert RADAR.refresh_live_snapshot(
            root, universe=["MU", "XYZ"], builder=lambda syms: built)
        on_disk = json.loads((root / RADAR.SNAPSHOT_REL).read_text(encoding="utf-8"))
        assert set(on_disk["quotes"]) == {"MU", "XYZ"}
        assert on_disk["meta"]["delayed_min"] == 15, (
            "the declared delay must reach the artifact or the ceiling loses it")

    def test_a_thin_fetch_is_discarded_rather_than_written(self, tmp_path):
        """Coverage floor: a fresh-but-empty snapshot is worse than a stale full one.

        The names that drop out lose their price entirely and fall back to the
        heatmap's pct-only tiles, which the price-gated detectors cannot use.
        """
        root = _mover_root(tmp_path)
        before = (root / RADAR.SNAPSHOT_REL).read_text(encoding="utf-8")
        assert not RADAR.refresh_live_snapshot(
            root, universe=[f"T{i}" for i in range(100)],
            builder=lambda syms: self._snap({"T1": _aged_quote(15.0)}))
        assert (root / RADAR.SNAPSHOT_REL).read_text(encoding="utf-8") == before

    def test_a_raising_builder_leaves_the_committed_snapshot_alone(self, tmp_path):
        root = _mover_root(tmp_path)
        before = (root / RADAR.SNAPSHOT_REL).read_text(encoding="utf-8")

        def _boom(syms):
            raise RuntimeError("yahoo said no")

        assert not RADAR.refresh_live_snapshot(root, universe=["MU"], builder=_boom)
        assert (root / RADAR.SNAPSHOT_REL).read_text(encoding="utf-8") == before

    def test_an_empty_universe_never_calls_the_builder(self, tmp_path):
        def _never(syms):
            raise AssertionError("builder must not be called for an empty universe")

        assert not RADAR.refresh_live_snapshot(tmp_path, universe=[], builder=_never)

    def test_the_opt_out_is_announced_not_silent(self, tmp_path, monkeypatch, capsys):
        """A lane that stopped fetching without saying so is the mute failure shape."""
        monkeypatch.setenv("HOT_TAPE_NO_LIVE_FETCH", "1")

        def _never(syms):
            raise AssertionError("opt-out must short-circuit the builder")

        assert not RADAR.refresh_live_snapshot(tmp_path, universe=["MU"],
                                               builder=_never)
        assert "self-fetch disabled" in capsys.readouterr().out


class TestRunSelfFetchesAStaleTape:
    """End to end: a stale shared tape is refreshed, not surrendered to."""

    def test_a_stale_shared_tape_is_refetched_and_the_pass_proceeds(self, tmp_path,
                                                                    capsys):
        root = _mover_root(tmp_path)
        # The 2026-07-29 state: the committed snapshot is ~50 minutes behind.
        _write_snapshot(root, {"MU": _aged_quote(50.0), "XYZ": _aged_quote(50.0, 0.4, 50.0, 49.8)},
                        asof_min_ago=50.0, delayed_min=15)

        calls: list[list[str]] = []

        def _builder(syms: list[str]) -> dict:
            calls.append(list(syms))
            return {"asof": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"), "ts": 0,
                    "source": "snapshot",
                    "meta": {"delayed_min": 15, "realtime": False},
                    "quotes": {s: _aged_quote(
                        15.0, *(( -8.2, 92.0, 100.2) if s == "MU" else (0.4, 50.0, 49.8)))
                        for s in syms}}

        RADAR.run(root, now=NOW, fetcher=_no_fetch, quote_builder=_builder)
        out = capsys.readouterr().out
        assert calls, "a stale shared tape must trigger a self-fetch"
        assert {"MU", "XYZ"} <= set(calls[0])
        assert "self-fetch wrote" in out, out
        assert "no events this pass" not in out, (
            "after a successful refetch the pass must proceed to detection")

    def test_a_healthy_shared_tape_costs_no_fetch(self, tmp_path):
        """The cheap common case: live-quotes.yml just pushed, so we spend nothing."""
        root = _mover_root(tmp_path)

        def _never(syms):
            raise AssertionError("a fresh shared tape must not trigger a fetch")

        RADAR.run(root, now=NOW, fetcher=_no_fetch, quote_builder=_never)

    def test_a_failed_refetch_stands_the_pass_down_with_the_reason(self, tmp_path,
                                                                   capsys):
        root = _mover_root(tmp_path)
        _write_snapshot(root, {"MU": _aged_quote(50.0)}, asof_min_ago=50.0,
                        delayed_min=15)
        assert RADAR.run(root, now=NOW, fetcher=_no_fetch,
                         quote_builder=lambda syms: {}) == 0
        out = capsys.readouterr().out
        assert "no events this pass" in out
        assert "WRITER-LANE fault" in out, (
            "a dark lane must say whose fault it is, in the log, on the pass")

    def test_demo_never_spends_a_live_fetch(self, tmp_path):
        """Demo exists to run on a quiet tape; its relaxed ceiling already admits it."""
        root = _mover_root(tmp_path)
        _write_snapshot(root, {"MU": _aged_quote(50.0)}, asof_min_ago=50.0,
                        delayed_min=15)

        def _never(syms):
            raise AssertionError("demo must not fetch")

        RADAR.run(root, now=NOW.replace(hour=6, minute=0), demo=True,
                  fetcher=_no_fetch, quote_builder=_never)


class TestSessionCadence:
    """One delivered tick must cover the whole session — GitHub will not deliver */5.

    Measured 2026-07-29, the 8h RTH window: GitHub created 104 scheduled runs
    across ALL 46 scheduled workflows in this repo, of which this lane got 6 of its
    ~92 ticks (6.5%) — ~1.4 passes an hour against a ~43-minute mean detection gap,
    while gate 0.1 asks for booked-at-Buffer inside 20 minutes. Starvation is
    GitHub-side and per-lane, so the lever is not depending on delivery: one
    bootstrap tick runs a session-long poller at a real 5-minute cadence. Runner
    minutes are free on this public repo, so the trade is runner time for latency.
    """

    @staticmethod
    def _wf() -> dict:
        import yaml as _yaml

        return _yaml.safe_load(
            (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
                encoding="utf-8"))

    @classmethod
    def _radar_step(cls) -> dict:
        step = [s for s in cls._wf()["jobs"]["radar"]["steps"] if s.get("id") == "radar"]
        assert len(step) == 1, "the radar step lost its id"
        return step[0]

    def test_the_session_is_covered_by_serialized_halves(self):
        """A job caps at 6h; the ET window is 6h50m. Two halves, strictly ordered."""
        job = self._wf()["jobs"]["radar"]
        strat = job["strategy"]
        assert strat["max-parallel"] == 1, (
            "the halves would run CONCURRENTLY — two radar passes racing the same "
            "fired ledger is the double-book this lane's concurrency group exists "
            "to prevent")
        assert strat["fail-fast"] is False, (
            "fail-fast would cancel the second half when the first dies, so a crash "
            "at 14:00Z would leave the rest of the session dark")
        assert len(strat["matrix"]["half"]) == 2, strat["matrix"]

    def test_two_halves_cover_the_whole_et_window(self):
        """The arithmetic that would otherwise rot silently."""
        import yaml as _yaml

        job = self._wf()["jobs"]["radar"]
        env = self._radar_step()["env"]
        budget_s = int(env["JOB_BUDGET_S"])
        timeout_s = int(job["timeout-minutes"]) * 60
        assert budget_s < timeout_s, (
            f"budget {budget_s}s exceeds the {timeout_s}s job timeout — the half "
            "would be killed mid-pass instead of handing over")
        assert timeout_s < 6 * 3600, (
            f"timeout {timeout_s}s is at or past GitHub's 6h job cap")

        cfg = _yaml.safe_load((REPO_ROOT / "config/hot_tape.yml").read_text(
            encoding="utf-8"))
        h1, m1 = (int(x) for x in str(cfg["window_et"]["start"]).split(":"))
        h2, m2 = (int(x) for x in str(cfg["window_et"]["end"]).split(":"))
        window_s = ((h2 * 60 + m2) - (h1 * 60 + m1) + int(cfg["window_grace_min"])) * 60
        halves = len(self._wf()["jobs"]["radar"]["strategy"]["matrix"]["half"])
        assert halves * budget_s >= window_s, (
            f"{halves} halves x {budget_s}s = {halves * budget_s}s cannot cover a "
            f"{window_s}s window — the close would go uncovered")

    def test_the_backstop_bounds_every_iteration_not_just_passes(self):
        """A pre-open WAIT must consume the backstop too.

        An earlier draft decremented the counter on a wait ("a wait is not a
        pass"), which made the cap unreachable: a stuck `--window-status` would
        spin the loop for the whole budget. Verified by simulation before shipping.
        """
        body = self._radar_step()["run"]
        assert "iter=$(( iter + 1 ))" in body, "the loop no longer counts iterations"
        assert "pass=$(( pass - 1 ))" not in body, (
            "the counter is decremented again — the backstop is unreachable")
        # The cap must allow a full session plus some pre-open waiting.
        env = self._radar_step()["env"]
        need = int(env["JOB_BUDGET_S"]) // int(env["PASS_INTERVAL_S"])
        assert int(env["MAX_PASSES"]) > need, (
            f"backstop {env['MAX_PASSES']} is below the {need} passes a full half "
            "performs — it would cut the session short")

    def test_the_loop_asks_the_radar_for_the_window(self):
        """No second implementation of the DST reasoning in bash."""
        body = self._radar_step()["run"]
        assert "--window-status" in body, (
            "the loop derives the window itself again; a UTC re-derivation in bash "
            "is how the shipped crons came to describe the wrong window")
        for token in ("IN_WINDOW=", "WINDOW_END_EPOCH="):
            assert token in body, token

    def test_pre_open_waits_and_closed_exits(self):
        """Three states, and pre-open is not closed.

        A run bootstrapped before the bell must wait for it. Treating pre-open as
        closed would throw away the bootstrap and leave the session uncovered.
        """
        body = self._radar_step()["run"]
        assert "pre-open" in body, "the pre-open wait is gone"
        assert "window closed" in body, "the closed-window exit is gone"

    def test_every_pass_commits_and_dispatches_on_its_own(self):
        """Latency is the whole point: a pass must not wait for the session to end.

        A 10:04 cross detected on one pass has to reach Buffer at ~10:07, not when
        the half finishes hours later. So the commit and the dispatch live INSIDE
        the loop — which also means the old post-loop `commit`/`dispatch` steps
        must be gone, not merely bypassed.
        """
        names = [str(s.get("name") or "") for s in self._wf()["jobs"]["radar"]["steps"]]
        assert not [n for n in names if n.startswith("commit radar state")], names
        assert not [n for n in names if n.startswith("dispatch the publisher")], names

        body = self._radar_step()["run"]
        head, _, inside = body.partition("while :; do")
        assert inside, "the session loop is gone"
        for token in ("python -m scripts.hot_tape_radar", "commit_and_push",
                      "gh workflow run marketing-publish.yml"):
            assert token in inside, f"{token} moved out of the per-pass loop"
        for fn in ("refresh_shared_tape()", "commit_and_push()", "window_status()"):
            assert fn in head, f"{fn} is used in the loop but defined after it"

    def test_a_booked_pass_that_cannot_push_never_dispatches(self):
        """The publisher folds items.jsonl from main, so push-then-dispatch."""
        body = self._radar_step()["run"]
        assert body.index("if commit_and_push; then") < body.index(
            "gh workflow run marketing-publish.yml"), (
            "the dispatch is no longer gated on the push landing — the publisher "
            "would look for item ids that are not on main yet and post nothing")

    def test_the_ids_channel_is_per_pass_not_github_output(self):
        """GITHUB_OUTPUT is append-only and collapses to one value per step."""
        env = self._radar_step()["env"]
        assert env.get("HOT_TAPE_IDS_FILE"), "no per-pass ids channel"
        body = self._radar_step()["run"]
        assert ': > "${HOT_TAPE_IDS_FILE}"' in body, (
            "the ids file is not truncated before the pass — a pass that books "
            "nothing would re-dispatch the previous pass's ids")
        assert "HOT_TAPE_IDS_FILE" in (
            REPO_ROOT / "scripts/hot_tape_radar.py").read_text(encoding="utf-8"), (
            "the workflow reads an ids file the script never writes")


class TestWindowStatusSeam:
    """`--window-status` is the loop's only source of truth about the session."""

    def test_it_reports_closed_outside_the_window(self, capsys):
        assert RADAR.main(["--window-status", "--root", str(REPO_ROOT)]) == 0
        out = capsys.readouterr().out
        # 06:00Z on a weekday is 02:00 ET — unambiguously outside any session.
        assert "IN_WINDOW=" in out and "WINDOW_END_EPOCH=" in out, out

    def test_demo_reports_open_with_a_far_deadline(self, capsys):
        assert RADAR.main(["--window-status", "--demo", "--root", str(REPO_ROOT)]) == 0
        out = capsys.readouterr().out
        assert "IN_WINDOW=1" in out, out
        end = int([l for l in out.splitlines()
                   if l.startswith("WINDOW_END_EPOCH=")][0].split("=")[1])
        assert end > datetime.now(timezone.utc).timestamp() + 3600, (
            "a demo loop must not stop at the real window end — demo exists to run "
            "on a closed tape")

    def test_the_deadline_is_the_configured_close_plus_grace(self):
        import yaml as _yaml

        cfg = _yaml.safe_load((REPO_ROOT / "config/hot_tape.yml").read_text(
            encoding="utf-8"))
        end_h, end_m = (int(x) for x in str(cfg["window_et"]["end"]).split(":"))
        grace = int(cfg["window_grace_min"])
        epoch = RADAR.window_end_epoch(REPO_ROOT, now=NOW)
        got = datetime.fromtimestamp(epoch, timezone.utc)
        et = HT._et_clock(got)
        assert (et.hour * 60 + et.minute) == end_h * 60 + end_m + grace, (
            f"deadline {et} is not {end_h:02d}:{end_m:02d} ET + {grace}m grace")

    def test_a_broken_config_keeps_the_loop_and_the_gate_agreeing(self, tmp_path):
        """The invariant is AGREEMENT, not fail-closed.

        `_parse_hhmm` falls back to the same 16:05 default `in_window` uses, so an
        unparseable `window_et.end` leaves the loop's deadline and the gate's window
        describing the same session. That is the property worth having: a loop that
        stopped at a different time than the gate opens/closes would either drop the
        close or spin past it. (A genuine exception — an unreadable config — still
        returns `now`, which stops the loop after one pass rather than holding a
        runner for the full budget.)
        """
        (tmp_path / "config").mkdir()
        (tmp_path / "config" / "hot_tape.yml").write_text(
            "window_et:\n  end: nonsense\n", encoding="utf-8")
        epoch = RADAR.window_end_epoch(tmp_path, now=NOW)
        cfg = HT.load_config(tmp_path)
        # One minute inside the deadline the gate must still be open; one minute
        # past it, shut. Same session, both sides.
        before = datetime.fromtimestamp(epoch - 60, timezone.utc)
        after = datetime.fromtimestamp(epoch + 60, timezone.utc)
        assert HT.in_window(before, cfg), (
            "the loop would keep passing after the gate had closed")
        assert not HT.in_window(after, cfg), (
            "the loop would stop while the gate was still open — dropping the close")


class TestSelfFetchImportsResolveInTheCone:
    """The self-fetch's import graph must fit the sparse checkout it runs in.

    `refresh_live_snapshot` imports `scripts.build_live_quotes` lazily, and that
    module does `from app.tape_symbols import TAPE_SYMBOLS` at MODULE scope. `app`
    was not in the radar's cone when the self-fetch shipped: the import raised
    ModuleNotFoundError, the fail-soft handler swallowed it into a ::warning, and
    the radar stood down exactly as it had before — a dead primary fix that passed
    every test, because tests run in a full checkout. Caught by materializing the
    cone and importing inside it.

    Structural on purpose: it derives the requirement from the source's actual
    imports, so the NEXT first-party import added to build_live_quotes fails this
    test instead of dying quietly in production.
    """

    #: Top-level dirs that are first-party packages rather than stdlib/site-packages.
    _FIRST_PARTY = {"app", "engine", "lib", "scripts", "collectors", "admin"}

    @staticmethod
    def _cone() -> set[str]:
        import yaml as _yaml

        wf = _yaml.safe_load(
            (REPO_ROOT / ".github/workflows/marketing-hot-tape.yml").read_text(
                encoding="utf-8"))
        checkout = [s for s in wf["jobs"]["radar"]["steps"]
                    if str(s.get("uses", "")).startswith("actions/checkout")][0]
        return {line.strip()
                for line in str(checkout["with"]["sparse-checkout"]).splitlines()
                if line.strip()}

    def _module_scope_first_party_imports(self, rel: str) -> set[str]:
        import ast

        tree = ast.parse((REPO_ROOT / rel).read_text(encoding="utf-8"))
        roots: set[str] = set()
        for node in tree.body:            # MODULE SCOPE ONLY — lazy imports are fine
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                if root in self._FIRST_PARTY:
                    roots.add(root)
        return roots

    def test_the_quote_builder_module_graph_is_inside_the_cone(self):
        cone = self._cone()
        # The chain the self-fetch actually walks: build_live_quotes -> live_quotes.
        for rel in ("scripts/build_live_quotes.py", "engine/live_quotes.py"):
            for root in self._module_scope_first_party_imports(rel):
                assert root in cone, (
                    f"{rel} imports `{root}` at module scope but `{root}` is not in "
                    f"the radar's sparse cone — the self-fetch would raise "
                    f"ModuleNotFoundError and fail soft into a warning")

    def test_the_radar_module_graph_is_inside_the_cone(self):
        cone = self._cone()
        for root in self._module_scope_first_party_imports("scripts/hot_tape_radar.py"):
            assert root in cone, f"hot_tape_radar imports `{root}`, absent from the cone"

    def test_live_quotes_lane_cone_covers_its_own_graph_too(self):
        """The same trap, the same day, in the sibling lane this PR also sparsened."""
        import yaml as _yaml

        wf = _yaml.safe_load(
            (REPO_ROOT / ".github/workflows/live-quotes.yml").read_text(
                encoding="utf-8"))
        checkout = [s for s in wf["jobs"]["snapshot"]["steps"]
                    if str(s.get("uses", "")).startswith("actions/checkout")][0]
        cone = {line.strip()
                for line in str(checkout["with"]["sparse-checkout"]).splitlines()
                if line.strip()}
        for rel in ("scripts/build_live_quotes.py", "engine/live_quotes.py"):
            for root in self._module_scope_first_party_imports(rel):
                assert root in cone, f"{rel} imports `{root}`, absent from the cone"


class TestTheLogReportsTheCeilingItApplied:
    """A log line must not misreport the threshold it used.

    Observed in run 30529411662 (the PR's own live verification): a demo pass
    printed `ceiling=27m` while the gate had actually judged against 100015m,
    because the summary line resolved the ceiling from the raw config and the gate
    resolved it from the demo-aware one. Harmless to the decision, corrosive to
    every future diagnosis — this defect took a day to find precisely because the
    numbers on screen had to be hand-correlated against another lane's push times.
    """

    def test_demo_prints_the_relaxed_ceiling_not_the_strict_one(self, tmp_path,
                                                               capsys):
        root = _mover_root(tmp_path)
        _date_stamped_heatmap(root)
        # Old enough that only the demo ceiling can admit it.
        _write_snapshot(root, {"MU": _aged_quote(600.0), "XYZ": _aged_quote(600.0, 0.4, 50.0, 49.8)},
                        asof_min_ago=600.0, delayed_min=15)
        RADAR.run(root, now=NOW.replace(hour=6, minute=0), demo=True,
                  fetcher=_no_fetch, quote_builder=lambda syms: {})
        line = [l for l in capsys.readouterr().out.splitlines()
                if l.startswith("hot-tape quotes ")]
        assert line, "no quote summary line"
        assert "demo=1" in line[0]
        assert "ceiling=27m" not in line[0], (
            f"demo printed the STRICT ceiling while applying the relaxed one: {line[0]}")
        assert "budget=100000m" in line[0], line[0]

    def test_a_normal_pass_prints_the_delay_aware_ceiling(self, tmp_path, capsys):
        root = _mover_root(tmp_path)
        _write_snapshot(root, {"MU": _aged_quote(15.0), "XYZ": _aged_quote(15.0, 0.4, 50.0, 49.8)},
                        delayed_min=15)
        RADAR.run(root, now=NOW, fetcher=_no_fetch)
        line = [l for l in capsys.readouterr().out.splitlines()
                if l.startswith("hot-tape quotes ")]
        assert line and "ceiling=27m" in line[0], line
        assert "budget=12m" in line[0] and "feed_delay=15m" in line[0], line[0]

    def test_the_gate_and_the_log_share_one_resolution(self):
        """Structural: both must go through freshness_cfg, so they cannot drift."""
        body = (REPO_ROOT / "scripts/hot_tape_radar.py").read_text(encoding="utf-8")
        assert body.count("freshness_cfg(cfg, demo=demo)") >= 2, (
            "the gate and the log no longer share one ceiling resolution")
        assert "effective_max_quote_age_min(live, cfg)" not in body, (
            "a raw-config ceiling resolution is back — in demo it prints a "
            "threshold the gate never applied")


# ─────────────────────────────────────────────────────────────────────────────
# The render litter.
#
# This lane renders a card for EVERY candidate it evaluates, BEFORE it knows
# whether the post will ship, on every intraday sweep. In one day that wrote
# 8,068 hottape-*.svg into data/marketing/outbox/media/<date>/ -- a directory
# that is COMMITTED, because the nightly chart-NNN.svg snapshots there feed the
# admin console preview. Result: 420 MB in the media tree, ~8k new TRACKED files
# per day, and a git that had begun printing "too many unreachable loose
# objects" on every command in the repo.
#
# Two halves to the fix. .gitignore now excludes hottape-*.svg specifically
# (chart-NNN.svg stays committed, deliberately). This is the other half: without
# a sweep the files still pile up on the runner's disk forever.
# ─────────────────────────────────────────────────────────────────────────────
class TestHotTapeRenderSweep:
    def _tree(self, tmp_path, days):
        base = tmp_path / "data" / "marketing" / "outbox" / "media"
        for day, n in days.items():
            d = base / day
            d.mkdir(parents=True, exist_ok=True)
            for i in range(n):
                (d / f"hottape-mover_pop-aaa{i}-1400Z.svg").write_text("<svg/>")
            # A nightly snapshot in the same directory, which must SURVIVE.
            (d / "chart-001.svg").write_text("<svg/>")
        return base

    def _sweep(self, root, now):
        from scripts.hot_tape_radar import sweep_hot_tape_renders
        return sweep_hot_tape_renders(root, now=now)

    def test_stale_render_litter_is_removed(self, tmp_path):
        from datetime import datetime, timezone
        base = self._tree(tmp_path, {"2026-07-20": 40, "2026-07-21": 5})
        n = self._sweep(tmp_path, datetime(2026, 7, 30, tzinfo=timezone.utc))
        assert n == 45, n
        assert not list(base.rglob("hottape-*"))

    def test_the_committed_nightly_snapshots_are_never_touched(self, tmp_path):
        """chart-NNN.svg feeds the admin preview and is committed ON PURPOSE."""
        from datetime import datetime, timezone
        base = self._tree(tmp_path, {"2026-07-20": 10, "2026-07-21": 10})
        self._sweep(tmp_path, datetime(2026, 7, 30, tzinfo=timezone.utc))
        survivors = sorted(p.name for p in base.rglob("chart-*.svg"))
        assert survivors == ["chart-001.svg", "chart-001.svg"], survivors

    def test_recent_days_are_retained(self, tmp_path):
        """Today and yesterday stay readable for an operator in the console."""
        from datetime import datetime, timezone
        base = self._tree(tmp_path, {"2026-07-29": 7, "2026-07-30": 9})
        n = self._sweep(tmp_path, datetime(2026, 7, 30, 20, 0, tzinfo=timezone.utc))
        assert n == 0, f"swept {n} files inside the retention window"
        assert len(list(base.rglob("hottape-*"))) == 16

    def test_a_non_date_directory_is_left_alone(self, tmp_path):
        """An unparseable name must not be treated as infinitely old."""
        from datetime import datetime, timezone
        base = tmp_path / "data" / "marketing" / "outbox" / "media" / "scratch"
        base.mkdir(parents=True)
        (base / "hottape-x-y-0000Z.svg").write_text("<svg/>")
        assert self._sweep(tmp_path, datetime(2026, 7, 30, tzinfo=timezone.utc)) == 0
        assert (base / "hottape-x-y-0000Z.svg").exists()

    def test_a_missing_tree_is_not_an_error(self, tmp_path):
        from datetime import datetime, timezone
        assert self._sweep(tmp_path, datetime(2026, 7, 30, tzinfo=timezone.utc)) == 0

    def test_the_radar_actually_calls_the_sweep(self):
        """A helper nothing invokes is the leak with extra steps."""
        import inspect
        import scripts.hot_tape_radar as htr
        assert "sweep_hot_tape_renders(root, now=ts)" in inspect.getsource(htr.run)

    def test_the_gitignore_is_hottape_scoped(self):
        """It must NOT swallow the nightly snapshots the console renders from."""
        from pathlib import Path
        rules = Path(".gitignore").read_text(encoding="utf-8")
        assert "data/marketing/outbox/media/**/hottape-*.svg" in rules
        assert "data/marketing/outbox/media/**/*.svg" not in rules, (
            "a blanket .svg ignore would silently stop committing the chart "
            "snapshots the admin console previews from"
        )
