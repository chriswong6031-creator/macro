"""tests/test_prophet_live_vps_lane.py — the VPS lane: quote source, transport, gate.

Masterplan §4.2a (the evaluator moves to the VPS) and §4.4a (delivery path). What this
file pins is everything the move ADDS; the state machine itself is unchanged and stays
pinned by tests/test_prophet_live_evaluator.py.

  QUOTE SOURCE   the box's own live plane is read FIRST, the estate merge is the
                 fallback, and every way the local plane can be broken — absent,
                 unreadable, present-but-empty — degrades to the merge instead of
                 darking a universe or raising.
  TRANSPORT      the served copy is written by temp-file-then-rename, is byte-identical
                 to the R2 payload, and a failed pass leaves the PREVIOUS copy whole.
                 Nothing on this path touches data/ (G0.2).
  GATE           /live/prophet_live.json is NOT one of the reviewed public /live/
                 exceptions. It carries per-name trigger levels and pre-publication
                 board membership; #3391 is the standing ruling that the real board is
                 not free content.
  HOST WIRING    the systemd unit is a resource-capped oneshot on the lowest priority
                 tier, its timer covers the ET session in both DST regimes without
                 re-implementing the window, macro-update reconciles it under a narrow
                 allow-list, and it never restarts the oneshot (that would run a pass
                 off-schedule).
  BACKSTOP       prophet-live.yml self-disables while the VPS is primary, and the
                 program kill switch is NOT bypassable by workflow_dispatch.

CLOCK. Same discipline as the sibling file: every timestamp derives from NOW, never
from datetime.now, so nothing here becomes a scheduled red on a Tuesday.
"""
from __future__ import annotations

import ast
import configparser
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.prophet_live_evaluator as E  # noqa: E402
from engine.prophet_live import live_states as LS  # noqa: E402
from engine.prophet_live import r2io  # noqa: E402

#: 2026-07-29 is a Wednesday; 14:00Z is 10:00 ET — inside the window, before the
#: 15:30 confirm cutoff.
NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)
LAST_SESSION = LS.last_completed_session(NOW)

DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-live-prophet.service"
TIMER = DEPLOY / "macro-live-prophet.timer"
UPDATE_SH = (DEPLOY / "update.sh").read_text(encoding="utf-8")
LIVE_SETUP = (DEPLOY / "live-setup.sh").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github" / "workflows" / "prophet-live.yml").read_text(encoding="utf-8")
POLICY = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
EVALUATOR_SRC = (ROOT / "scripts" / "prophet_live_evaluator.py").read_text(encoding="utf-8")

#: The served path the P1 surface fetches (templates/dashboard.html.j2 PLV_URL,
#: 'live/prophet_live.json'). Both halves of the prefix bridge are asserted below.
SERVED_URL_PATH = "/live/prophet_live.json"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def artifact(quotes: dict[str, float], *, asof: str, delayed_min: int | None = 15,
             ts_ms: int | None = None) -> dict:
    """A quote artifact in build_live_quotes shape (what both local files carry)."""
    out: dict = {"asof": asof, "quotes": {}}
    if delayed_min is not None:
        out["meta"] = {"delayed_min": delayed_min, "resolved": len(quotes),
                       "requested": len(quotes)}
    for tkr, px in quotes.items():
        out["quotes"][tkr] = {"price": px, "prevClose": px, "changePct": 0.0,
                              "ts": ts_ms}
    return out


def write_artifact(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def pack(names: dict, as_of: str | None = None) -> dict:
    return {"schema": "prophet_live.armed/v1", "as_of": as_of or LAST_SESSION,
            "built_at": "2026-07-28T22:30:00Z", "names": names,
            "meta": {"universe_n": 1742, "probed_n": len(names), "armed_n": len(names),
                     "skipped": {"probe_cap": 1176}}}


def buyable(px: float = 100.0) -> dict:
    return {"state": "buyable", "center_buyable": True, "as_of_close": px,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": True,
            "fade_px": px * 0.9, "fade_hi_px": px * 1.1,
            "band_lo_px": px * 0.85, "band_hi_px": px * 1.15}


@pytest.fixture
def lane(monkeypatch, tmp_path):
    """A runnable pass: R2 stubbed at the r2io boundary, quotes/served paths in tmp.

    Returns a small handle so each test drives the SAME entry point the timer calls
    (``E.run``) rather than a helper that could drift away from it.
    """
    store: dict[str, dict] = {}
    state = {"pack": pack({"AAA": buyable()}), "s3": object()}

    monkeypatch.setattr(E.r2io, "client", lambda: state["s3"])
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        state["pack"] if key == r2io.PACK_KEY else store.get(key))
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: store.__setitem__(key, payload) or True)
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))

    local = tmp_path / "plane"
    served_dir = tmp_path / "public" / "live"
    served_dir.mkdir(parents=True)

    class Lane:
        r2 = store
        s = state
        local_dir = local
        served = served_dir / "prophet_live.json"

        def cfg(self, *, paths: list | None = None, served: str | None = ...) -> dict:
            block: dict = {}
            if paths is not None:
                block["local_quote_paths"] = paths
            block["served_path"] = str(self.served) if served is ... else served
            return {"live": {"delayed_min": 15}, "prophet_live": block}

        def run(self, *, paths: list | None = None, served: str | None = ...,
                now: datetime = NOW, dry_run: bool = False) -> int:
            return E.run(tmp_path, now=now, dry_run=dry_run,
                         cfg=self.cfg(paths=paths, served=served))

    return Lane()


# ─────────────────────────────────────────────────────────────────────────────
# Quote source — the local plane is tried first, and every failure falls back
# ─────────────────────────────────────────────────────────────────────────────

def test_the_local_plane_is_preferred_over_the_estate_merge(lane, monkeypatch):
    """The whole point of §4.2a: read the box's own disk, not a throttled git branch.

    The merge is stubbed to a DIFFERENT price so the assertion cannot pass by accident
    if the local read silently returned nothing.
    """
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 55.0, "ts_ms": None, "source": "quotes"}},
        "asof": "2026-07-29T12:18:07Z", "source": "snapshot", "feed_delay_min": 15.0})
    local = write_artifact(lane.local_dir / "quotes_full.json",
                           artifact({"AAA": 100.0}, asof="2026-07-29T13:59:30Z"))

    assert lane.run(paths=[str(local)]) == 0
    art = lane.r2[r2io.LIVE_KEY]
    assert art["meta"]["quote_source"] == E.LOCAL_SOURCE == "vps_local"
    assert art["meta"]["quote_asof"] == "2026-07-29T13:59:30Z"
    assert art["states"]["AAA"]["state"] == "forming"        # the LOCAL price, not 55.0


def test_an_absent_local_plane_falls_back_to_the_merge_untouched(lane, monkeypatch):
    """Every GitHub runner and every dev checkout is this case. It is not a fault."""
    seen: list[Path] = []

    def _merge(root):
        seen.append(root)
        return {"quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
                "asof": "2026-07-29T13:58:00Z", "source": "heatmap+display",
                "feed_delay_min": 15.0}

    monkeypatch.setattr(E.LV, "load_live_quotes", _merge)
    assert lane.run(paths=[str(lane.local_dir / "nothing_here.json")]) == 0
    assert seen, "the merge fallback was never reached"
    assert lane.r2[r2io.LIVE_KEY]["meta"]["quote_source"] == "heatmap+display"


def test_a_corrupt_local_file_warns_and_falls_back(lane, monkeypatch, capsys):
    """An unreadable file on a box that HAS a live plane is a fault worth saying so.

    Fail-soft in both directions (the brief's word): it degrades to the merge, and it
    says why with a bare line-start annotation — never through a logger, which prefixes
    the line and makes GitHub drop it.
    """
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    bad = lane.local_dir / "quotes_full.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text('{"quotes": {"AAA": ', encoding="utf-8")     # truncated mid-write

    assert lane.run(paths=[str(bad)]) == 0
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "::warning" in ln and "unreadable" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")
    assert lane.r2[r2io.LIVE_KEY]["meta"]["quote_source"] == "snapshot"


def test_an_empty_local_file_does_not_blank_the_tape(lane, monkeypatch):
    """A quote file with no quotes must not beat a merge that has some.

    Returning an empty view instead of falling back would publish `no_quote` for the
    whole universe — a tape-wide dark caused by a file that parsed fine.
    """
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    empty = write_artifact(lane.local_dir / "quotes_full.json",
                           artifact({}, asof="2026-07-29T13:59:00Z"))

    assert lane.run(paths=[str(empty)]) == 0
    art = lane.r2[r2io.LIVE_KEY]
    assert art["meta"]["quote_source"] == "snapshot"
    assert art["states"]["AAA"]["state"] == "forming"


def test_both_local_files_are_read_and_the_fresher_quote_wins():
    """Why the default is a LIST, not the served quotes.json alone.

    Measured 2026-07-30: /var/lib/macro-live/public/live/quotes.json carries 34 symbols
    (index/ETF/macro only) while state/quotes_full.json carries ~2,100. Reading the
    served file alone would be fresher and empty — ~0 of ~1,700 armed names evaluable.
    So both are read and merged through live_verify's own freshest-wins rule.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        full = write_artifact(d / "quotes_full.json",
                              artifact({"AAA": 10.0, "BBB": 20.0},
                                       asof="2026-07-29T13:50:00Z",
                                       ts_ms=1785419400000))
        disp = write_artifact(d / "quotes.json",
                              artifact({"AAA": 11.0}, asof="2026-07-29T13:59:00Z",
                                       ts_ms=1785419940000))
        live = E.load_local_quotes({"local_quote_paths": [str(full), str(disp)]})

    assert live is not None
    assert set(live["quotes"]) == {"AAA", "BBB"}          # coverage from the full file
    assert live["quotes"]["AAA"]["price"] == 11.0          # freshness from the display file
    assert live["source"] == E.LOCAL_SOURCE
    assert live["asof"] == "2026-07-29T13:59:00Z"          # the NEWEST artifact's asof
    assert live["feed_delay_min"] == 15.0
    assert live["local_files"] == ["quotes_full.json", "quotes.json"]


def test_an_empty_config_list_disables_the_local_plane_without_a_code_change(lane,
                                                                            monkeypatch):
    """The config-only rollback lever: back to the merge path exactly as before."""
    reads: list[Path] = []
    monkeypatch.setattr(E, "_read_local_json", lambda p: reads.append(p) or None)
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})

    assert lane.run(paths=[]) == 0
    assert reads == []
    assert lane.r2[r2io.LIVE_KEY]["meta"]["quote_source"] == "snapshot"


def test_the_default_paths_are_the_vps_live_plane():
    """No config block at all still reads the box's plane — the unit ships no --flags."""
    assert E.local_quote_paths({}) == [Path(p) for p in E.LOCAL_QUOTE_PATHS]
    assert E.LOCAL_QUOTE_PATHS == (
        "/var/lib/macro-live/state/quotes_full.json",
        "/var/lib/macro-live/public/live/quotes.json")
    # And config.yml ships the same two, so the deployed lane and the in-code default
    # cannot drift apart silently.
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    assert [str(p) for p in E.local_quote_paths(cfg["prophet_live"])] \
        == list(E.LOCAL_QUOTE_PATHS)


def test_a_ceiling_below_the_feeds_own_delay_is_announced(lane, monkeypatch, capsys):
    """The unsatisfiable-gate tripwire (measured 2026-07-30).

    Per-quote age is (polling gap) + (feed delay), and the US single-name feed is
    contractually ~15-min delayed, so a 12-minute ceiling darks every name at ANY
    cadence — on the freshest plane there is. The lane does not move either number;
    it refuses to dark a universe silently.
    """
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 15.0})
    cfg = lane.cfg(paths=[])
    cfg["prophet_live"]["quote_max_age_min"] = 12
    assert E.run(lane.served.parent, now=NOW, cfg=cfg) == 0
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "::warning" in ln and "quote_max_age_min" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")
    assert "12m" in warn[0] and "15m" in warn[0]

    # A ceiling that clears the floor says nothing.
    cfg["prophet_live"]["quote_max_age_min"] = 25
    assert E.run(lane.served.parent, now=NOW, cfg=cfg) == 0
    assert not [ln for ln in capsys.readouterr().out.splitlines()
                if "quote_max_age_min" in ln]


# ─────────────────────────────────────────────────────────────────────────────
# Transport — the served copy (§4.4a)
# ─────────────────────────────────────────────────────────────────────────────

def test_the_served_copy_is_byte_identical_to_the_r2_payload(lane, monkeypatch):
    """Two planes, one tape. A separate serialisation is a way for them to disagree."""
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    assert lane.run(paths=[]) == 0

    served = json.loads(lane.served.read_text(encoding="utf-8"))
    assert served == lane.r2[r2io.LIVE_KEY]
    assert lane.served.read_bytes() == json.dumps(
        lane.r2[r2io.LIVE_KEY], allow_nan=False, separators=(",", ":")).encode("utf-8")
    assert served["schema"] == LS.SCHEMA
    assert lane.served.stat().st_mode & 0o777 == 0o644      # Caddy must be able to read it


def test_the_served_write_is_a_rename_never_an_in_place_truncate(lane, monkeypatch,
                                                                 capsys):
    """G4: a failed pass leaves the PREVIOUS copy whole, not a half-written file.

    Reproduced the only way that matters — kill the write after the temp file exists
    and assert the live path still parses AND still carries the earlier pass's stamp.
    A stale-but-whole payload is self-describing through its own meta.pass_ts; a
    truncated one is a parse error on a live page.
    """
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    assert lane.run(paths=[]) == 0
    good = lane.served.read_bytes()
    first_pass = json.loads(good)["meta"]["pass_ts"]
    capsys.readouterr()

    def _boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(E.os, "replace", _boom)
    assert lane.run(paths=[], now=NOW.replace(minute=5)) == 0

    # The write was genuinely attempted and genuinely failed — without this the two
    # assertions below would also pass on a pass that never tried to write at all.
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "::warning" in ln and "not written" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")
    assert "the previous copy stands" in warn[0]

    assert lane.served.read_bytes() == good
    assert json.loads(lane.served.read_text())["meta"]["pass_ts"] == first_pass
    # And no debris beside it: a dot-file left behind would accumulate one per pass.
    assert [p.name for p in lane.served.parent.iterdir()] == ["prophet_live.json"]


def test_a_payload_that_cannot_serialise_leaves_no_temp_file(lane, monkeypatch, capsys):
    """Serialise before mkstemp: the failure must not litter the served directory."""
    assert E.publish_served(lane.served, {"nan": float("nan")}) is False
    assert list(lane.served.parent.iterdir()) == []
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")


def test_no_live_plane_means_no_served_copy_and_no_directory_is_created(lane, capsys):
    """An absent directory means this host is not the VPS. Creating one would hand
    Caddy a directory to serve nothing out of."""
    missing = lane.served.parent.parent / "not_installed" / "prophet_live.json"
    assert E.publish_served(missing, {"a": 1}) is False
    assert not missing.parent.exists()
    out = [ln for ln in capsys.readouterr().out.splitlines() if "::notice" in ln]
    assert out and out[0].startswith("::notice title=prophet-live::")


def test_a_dry_run_writes_neither_plane(lane, monkeypatch):
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    assert lane.run(paths=[], dry_run=True) == 0
    assert lane.r2 == {}
    assert not lane.served.exists()


def test_without_r2_credentials_nothing_is_served(lane, monkeypatch):
    """No credentials means no `prev`, and `prev` is where the debounce lives.

    Every pass would restart its counters: a cross could never bank its second pass and
    the P1 SINCE column would re-stamp on every tick. Publishing that to a page is a
    worse lie than publishing nothing, so the served copy waits for the credentials.
    """
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    lane.s["s3"] = None
    assert lane.run(paths=[]) == 0
    assert not lane.served.exists()
    assert lane.r2 == {}


def test_an_r2_put_failure_still_serves_the_page(lane, monkeypatch, capsys):
    """Independent failure domains: R2 is the pipeline artifact, the file is the
    product path. One hiccuping must not stale the other."""
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    monkeypatch.setattr(E.r2io, "put_json", lambda key, payload, **kw: False)
    assert lane.run(paths=[]) == 0
    assert lane.served.is_file()
    assert json.loads(lane.served.read_text())["schema"] == LS.SCHEMA
    assert any("PUT failed" in ln for ln in capsys.readouterr().out.splitlines())


def test_the_no_publish_kill_switch_covers_the_served_copy_too(lane, monkeypatch,
                                                               capsys):
    """The switch that keeps a rehearsal out of the ledger must also keep it off the
    page. It guards the R2 PUTs (r2io.put_json); leaving the user-facing copy writable
    would invert its purpose — and on the VPS this is the stand-down that needs no unit
    change at all."""
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    assert lane.run(paths=[]) == 0
    before = lane.served.read_bytes()
    capsys.readouterr()

    monkeypatch.setenv("PROPHET_LIVE_NO_PUBLISH", "1")
    assert lane.run(paths=[], now=NOW.replace(minute=10)) == 0
    assert lane.served.read_bytes() == before            # untouched, not truncated
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "PROPHET_LIVE_NO_PUBLISH" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")

    # The falsy spellings leave the real path alone.
    for value in ("0", "false", ""):
        monkeypatch.setenv("PROPHET_LIVE_NO_PUBLISH", value)
        assert lane.run(paths=[], now=NOW.replace(minute=15)) == 0
        assert lane.served.read_bytes() != before


def test_the_served_path_bridges_the_r2_key_deliberately():
    """The producer key and the served path differ by PREFIX only, and both are fixed.

    Renaming the R2 key would break the reconciler and the spool prefix; moving the
    served path would break the P1 consumer. The bridge belongs here (§4.4a).
    """
    assert r2io.LIVE_KEY == "live_flow/prophet_live.json"
    assert E.SERVED_PATH == "/var/lib/macro-live/public/live/prophet_live.json"
    assert Path(E.SERVED_PATH).name == Path(r2io.LIVE_KEY).name
    assert E.SERVED_PATH.endswith(SERVED_URL_PATH)
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    assert str(E.served_path(cfg["prophet_live"])) == E.SERVED_PATH


def test_the_served_copy_can_be_switched_off(lane, monkeypatch):
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    assert lane.run(paths=[], served="") == 0
    assert lane.r2[r2io.LIVE_KEY]["schema"] == LS.SCHEMA
    assert not lane.served.exists()


# ─────────────────────────────────────────────────────────────────────────────
# G0.2 — the new write path is still no ledger path
# ─────────────────────────────────────────────────────────────────────────────

def test_the_pass_writes_nothing_under_data(lane, monkeypatch, tmp_path):
    """The lane now writes a file. It must still never write THAT file."""
    monkeypatch.setattr(E.LV, "load_live_quotes", lambda root: {
        "quotes": {"AAA": {"price": 100.0, "ts_ms": None, "source": "quotes"}},
        "asof": "x", "source": "snapshot", "feed_delay_min": 0.0})
    assert lane.run(paths=[]) == 0
    assert not (tmp_path / "data").exists()
    # Nothing anywhere in the module names a data/ path, and the served target is not
    # under the repo root it was handed.
    assert not re.search(r"['\"]data/", EVALUATOR_SRC)
    assert not str(lane.served).startswith(str(tmp_path / "data"))
    assert E.SERVED_PATH.startswith("/var/lib/macro-live/")


def test_the_only_filesystem_write_is_the_configured_served_path():
    """AST, not grep: `os.replace` — the call that makes a file visible — appears
    exactly once, inside publish_served, and no other function writes at all.

    Matched on the DOTTED name. Bare ``replace`` would also catch ``str.replace`` and
    ``datetime.replace``, which are all over this module and mean nothing here — an
    assertion that fires on those is one somebody deletes rather than reads.
    """
    tree = ast.parse(EVALUATOR_SRC)
    #: Module-qualified: only these spellings write. `replace` on its own is
    #: str.replace/datetime.replace all over this file and means nothing here.
    DOTTED = {"os.replace", "os.rename", "os.link", "os.symlink", "os.remove",
              "os.rmdir", "os.mkdir", "os.makedirs", "shutil.copy", "shutil.copyfile",
              "shutil.copyfileobj", "shutil.move"}
    #: Method-style, whatever the receiver is called — `p.write_bytes(...)` is the
    #: obvious way to "simplify" the temp-then-rename away, so it must be caught by
    #: NAME, not by receiver.
    METHODS = {"write_text", "write_bytes", "writelines", "touch", "unlink", "mkdir",
               "makedirs", "rmdir", "to_parquet", "to_csv"}

    def label(func: ast.AST) -> str | None:
        if isinstance(func, ast.Attribute):
            base = func.value
            dotted = (f"{base.id}.{func.attr}" if isinstance(base, ast.Name)
                      else func.attr)
            if dotted in DOTTED:
                return dotted
            return func.attr if func.attr in METHODS else None
        name = getattr(func, "id", "")
        return name if name in METHODS or name == "open" else None

    found: dict[str, list[str]] = {}
    unlink_targets: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and (tag := label(node.func)):
                found.setdefault(tag, []).append(fn.name)
                if tag == "unlink":
                    unlink_targets += [getattr(a, "id", "?") for a in node.args]
    assert found.get("os.replace") == ["publish_served"], found
    # `unlink` is the temp file's own cleanup, nothing else — a served copy is never
    # deleted, only replaced, so a failed pass can never leave the page with no file.
    assert set(found) <= {"os.replace", "unlink"}, f"unexpected write calls: {found}"
    assert all(fns == ["publish_served"] for fns in found.values()), found
    assert unlink_targets == ["tmp_name"], unlink_targets


# ─────────────────────────────────────────────────────────────────────────────
# The serving gate (G1) — /live/prophet_live.json is NOT public
# ─────────────────────────────────────────────────────────────────────────────

def _caddy_public_exclusions() -> set[str]:
    import shlex
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    match = re.search(r"# PUBLIC-BOUNDARY-START.*?@reg_asset\s*\{\s*not path ([^\n]+)",
                      caddy, flags=re.S)
    assert match, "Caddy public-boundary matcher missing"
    return set(shlex.split(match.group(1)))


def test_the_served_artifact_is_not_public_anywhere():
    """G1, at the policy layer. The live anonymous curl is in the PR body; this is the
    tripwire that keeps it true after the next boundary edit.

    Checked against the YAML directly rather than by importing app.paywall: the CI packs
    install minimal deps, and an importorskip here would disarm the whole assertion.
    """
    public = POLICY["public"]
    assert SERVED_URL_PATH not in set(public["exact"])
    assert not any(SERVED_URL_PATH.startswith(p) for p in public["prefixes"])
    assert SERVED_URL_PATH not in _caddy_public_exclusions()
    # Not free_registered either: it inherits premium.default_tier, the same tier as the
    # board artifact it overlays (#3391 — the real board is not free content).
    free = POLICY["free_registered"]
    assert SERVED_URL_PATH not in set(free["exact"])
    assert not any(SERVED_URL_PATH.startswith(p) for p in free["prefixes"])
    assert POLICY["premium"]["default_tier"] == "insider"


def test_the_public_live_exceptions_are_exactly_the_three_reviewed_files():
    """A prefix would have swept prophet_live.json in with them. There is no prefix."""
    live_public = sorted(p for p in _caddy_public_exclusions() if p.startswith("/live/"))
    assert live_public == ["/live/breadth.json", "/live/quotes.json",
                           "/live/release_publications.json"]
    assert not any(p.startswith("/live/") for p in POLICY["public"]["prefixes"])


# ─────────────────────────────────────────────────────────────────────────────
# Host wiring — the systemd unit
# ─────────────────────────────────────────────────────────────────────────────

def _unit(path: Path) -> configparser.ConfigParser:
    # interpolation=None is load-bearing: `CPUQuota=60%` is a ConfigParser
    # interpolation syntax error, and a unit file is not an ini template.
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(path.read_text(encoding="utf-8"))
    return cp


def test_the_service_is_a_capped_oneshot_on_the_lowest_priority_tier():
    """Caps are evidence-based (see the unit's own header) and no looser than the
    smallest sibling. The tier matters: this lane CONSUMES what the quote lanes
    publish, so it must always lose a scheduling contest with them."""
    svc = _unit(SERVICE)["Service"]
    assert svc["Type"] == "oneshot"
    assert svc["ExecStart"].endswith("-m scripts.prophet_live_evaluator")
    assert svc["WorkingDirectory"] == "/opt/macro"
    assert svc["EnvironmentFile"] == "-/etc/macro-live.env"

    assert int(svc["CPUQuota"].rstrip("%")) <= 90          # <= the snapshot/bars lanes
    assert svc["MemoryMax"] == "512M" and svc["MemoryHigh"] == "256M"
    bars = _unit(DEPLOY / "macro-live-bars.service")["Service"]
    assert int(svc["Nice"]) >= int(bars["Nice"])
    assert int(svc["CPUWeight"]) <= int(bars["CPUWeight"])
    assert int(svc["IOWeight"]) <= int(bars["IOWeight"])
    # Bounded well inside the 300s timer period: two passes can never overlap.
    assert int(svc["TimeoutStartSec"]) <= 300
    assert svc["NoNewPrivileges"] == "true" and svc["PrivateTmp"] == "true"


def test_the_timer_covers_the_session_in_both_dst_regimes_without_a_second_window():
    """The UTC span covers 09:25-16:25 ET under EDT AND EST; the ET trimming is done by
    in_window, so "when is the market open" has exactly one definition."""
    cal = _unit(TIMER)["Timer"]["OnCalendar"]
    m = re.fullmatch(r"Mon\.\.Fri \*-\*-\* (\d+)\.\.(\d+):(\d+)/(\d+):00 UTC", cal)
    assert m, cal
    lo, hi, offset, step = (int(g) for g in m.groups())
    assert step == 5 and 0 <= offset < 5
    # EDT 09:25 ET = 13:25Z ... EST 16:25 ET (window end + grace) = 21:25Z.
    assert lo <= 13 and hi >= 21
    assert _unit(TIMER)["Timer"]["Persistent"] == "false"   # never replay a missed pass
    assert _unit(TIMER)["Timer"]["Unit"] == "macro-live-prophet.service"
    # No second window definition anywhere in the unit files.
    assert "09:25" not in TIMER.read_text(encoding="utf-8").split("[Timer]")[1]

    # And the pass really does stand down on the ET edges of that span.
    et = LS.et_clock(NOW)
    for hh, mm, inside in ((8, 30, False), (9, 30, True), (16, 20, True), (17, 0, False)):
        stamp = et.replace(hour=hh, minute=mm, second=0, microsecond=0)
        assert LS.in_window(stamp.astimezone(timezone.utc)) is inside, (hh, mm)


def test_no_unit_directive_runs_a_git_command_or_touches_the_served_tree():
    """Directives only — the header comments necessarily NAME the things they forbid."""
    for path in (SERVICE, TIMER):
        for section in _unit(path).sections():
            for key, value in _unit(path)[section].items():
                for banned in ("git ", "data/", "site.served", "/opt/macro/site"):
                    assert banned not in value, f"{path.name}: {key}={value}"


# ─────────────────────────────────────────────────────────────────────────────
# Host wiring — macro-update reconciliation
# ─────────────────────────────────────────────────────────────────────────────

def test_macro_update_reconciles_the_prophet_units_under_a_narrow_allow_list():
    """Go-live is a repo commit: the reconciler installs, arms and heals the unit.

    The trigger is derived, not eyeballed — the regex from update.sh is applied to the
    two paths it must match and to paths it must NOT.
    """
    m = re.search(r"grep -qE '(\^app/deploy/macro-live-prophet[^']+)'", UPDATE_SH)
    assert m, "no prophet unit trigger in update.sh"
    trigger = re.compile(m.group(1).replace(r"\.", r"\."))
    for path in ("app/deploy/macro-live-prophet.service",
                 "app/deploy/macro-live-prophet.timer"):
        assert trigger.search(path), path
    for path in ("app/deploy/macro-live-fast.service", "scripts/prophet_live_evaluator.py",
                 "app/deploy/macro-live-prophet.service.bak", "config.yml"):
        assert not trigger.search(path), path

    block = UPDATE_SH.split("# PROPHET LIVE evaluator lane")[1]
    assert "systemd-analyze verify" in block          # a broken unit never installs
    assert "cmp -s" in block                          # installing twice is a no-op
    assert "systemctl enable --now macro-live-prophet.timer" in block
    assert "is-enabled macro-live-fast.timer" in block   # only where the plane exists
    assert "[ ! -f /etc/systemd/system/macro-live-prophet.timer ]" in block


def test_macro_update_never_restarts_the_prophet_oneshot():
    """`systemctl restart` on a oneshot RUNS it — off-schedule, outside the ET window,
    against whatever debounce predecessor the last real tick left."""
    assert "restart macro-live-prophet.service" not in UPDATE_SH
    assert "start macro-live-prophet.service" not in UPDATE_SH
    # The sibling block must not have been widened to sweep this unit in either.
    live_block = UPDATE_SH.split("# Live-plane systemd definitions")[1].split(
        "# PROPHET LIVE evaluator lane")[0]
    assert "prophet" not in live_block


def test_live_setup_installs_arms_and_funds_the_prophet_lane():
    """A fresh provision must not need a second manual step to arm the lane, and the
    lane's one extra dependency must be in the venv it runs from."""
    assert "macro-live-prophet.service macro-live-prophet.timer" in LIVE_SETUP
    assert "macro-live-prophet.timer >/dev/null" in LIVE_SETUP
    pip = next(ln for ln in LIVE_SETUP.splitlines() if "pip\" install -q pandas" in ln)
    assert "boto3" in pip


# ─────────────────────────────────────────────────────────────────────────────
# The GitHub backstop
# ─────────────────────────────────────────────────────────────────────────────

def test_the_backstop_self_disables_while_the_vps_is_primary():
    job = yaml.safe_load(WORKFLOW)["jobs"]["evaluate"]["if"]
    assert "vars.VPS_LIVE_PRIMARY != 'true'" in job
    assert "github.event_name == 'workflow_dispatch'" in job
    # The estate idiom, byte-comparable with its siblings.
    sibling = (ROOT / ".github" / "workflows" / "intraday-fastpath.yml").read_text()
    assert "vars.VPS_LIVE_PRIMARY != 'true'" in sibling


def test_the_program_kill_switch_is_not_bypassable_by_dispatch():
    """PROPHET_LIVE_DISABLED binds ALWAYS; only the host gate has a dispatch bypass.

    Evaluated for real, not read: the four combinations are substituted into the
    expression the way GitHub evaluates it.
    """
    job = yaml.safe_load(WORKFLOW)["jobs"]["evaluate"]["if"]
    expr = job.strip()[3:-2].strip() if job.strip().startswith("${{") else job

    def evaluate(*, disabled: str, primary: str, event: str) -> bool:
        py = (expr.replace("vars.PROPHET_LIVE_DISABLED", repr(disabled))
                  .replace("vars.VPS_LIVE_PRIMARY", repr(primary))
                  .replace("github.event_name", repr(event))
                  .replace("&&", "and").replace("||", "or").replace("!=", "!="))
        return bool(eval(py))                                   # noqa: S307

    assert evaluate(disabled="", primary="", event="schedule") is True
    assert evaluate(disabled="", primary="true", event="schedule") is False
    assert evaluate(disabled="", primary="true", event="workflow_dispatch") is True
    assert evaluate(disabled="true", primary="true", event="workflow_dispatch") is False
    assert evaluate(disabled="true", primary="", event="workflow_dispatch") is False


def test_the_workflow_header_no_longer_sells_a_five_minute_product_cadence():
    """The header is the first thing the next reader believes. It said "every 5
    minutes" while GitHub was delivering ~90; now it says what it is."""
    header = WORKFLOW.split("on:")[0]
    assert "BACKSTOP" in header
    assert "not the product cadence" in header
    assert "macro-live-prophet" in header
    assert "Every 5 minutes from 09:25 to 16:15" not in header


def test_the_backstop_still_commits_nothing():
    """Unchanged by the move, and the reason it can stay armed."""
    for banned in ("git add", "git commit", "git push", "contents: write"):
        assert banned not in WORKFLOW, banned
    assert "contents: read" in WORKFLOW
