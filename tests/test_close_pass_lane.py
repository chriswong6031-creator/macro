"""tests/test_close_pass_lane.py — the evening close-pass lane (W-L1a).

Shaped after tests/test_prophet_live_vps_lane.py, which is this estate's richest
guard set for exactly this kind of lane, and replicating the four things it pins:

  LEDGER LAW    the pass writes nothing under data/, names no data/ path, runs no
                git command, and its only filesystem write is the configured
                served path (G0.2, DNR:KILL-INTRADAY-CHRONICLE — the nightly is
                the sole advancer of every forward ledger).
  TRANSPORT     the served copy is written by temp-file-then-rename, is
                byte-identical to the R2 payload, and a failed pass leaves the
                PREVIOUS copy whole.
  GATE          /live/us_board_provisional.json is NOT one of the reviewed public
                /live/ exceptions. It carries pre-publication board membership;
                #3391 is the standing ruling that the real board is not free.
  HOST WIRING   the mirror unit is a resource-capped oneshot on the lowest
                priority tier, its timer covers the evening window in both DST
                regimes without re-implementing it, macro-update reconciles it
                under a narrow allow-list, and it never restarts the oneshot.

Plus the two things this lane has that Prophet Live does not: a SCHEDULE it must
share with the nightly without colliding, and a SCORING DISCLOSURE — three of the
board's five legs are not computable from closes, and the payload has to say so
rather than quietly renormalise the other two up to 100.

CLOCK. Every timestamp derives from NOW, never from datetime.now, so nothing here
becomes a scheduled red on a Tuesday.
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

import scripts.close_pass_mirror as M  # noqa: E402
import scripts.close_pass_publish as P  # noqa: E402
import scripts.close_pass_reconcile as RC  # noqa: E402
from engine import us_board_rank  # noqa: E402
from engine.close_pass import board as CB  # noqa: E402
from engine.close_pass import reconcile as CR  # noqa: E402

#: 2026-08-07 is a Friday and a full NYSE session; 20:20Z is 16:20 ET under EDT —
#: the real fire time of the first cron line.
NOW = datetime(2026, 8, 7, 20, 20, tzinfo=timezone.utc)
SESSION = "2026-08-07"

DEPLOY = ROOT / "app" / "deploy"
SERVICE = DEPLOY / "macro-live-closepass.service"
TIMER = DEPLOY / "macro-live-closepass.timer"
UPDATE_SH = (DEPLOY / "update.sh").read_text(encoding="utf-8")
LIVE_SETUP = (DEPLOY / "live-setup.sh").read_text(encoding="utf-8")
WORKFLOW_SRC = (ROOT / ".github" / "workflows" / "close-pass.yml").read_text(encoding="utf-8")
WORKFLOW = yaml.safe_load(WORKFLOW_SRC)
POLICY = yaml.safe_load((ROOT / "config" / "site_access.yml").read_text(encoding="utf-8"))
PUBLISH_SRC = (ROOT / "scripts" / "close_pass_publish.py").read_text(encoding="utf-8")
MIRROR_SRC = (ROOT / "scripts" / "close_pass_mirror.py").read_text(encoding="utf-8")
RECONCILE_SRC = (ROOT / "scripts" / "close_pass_reconcile.py").read_text(encoding="utf-8")
BOARD_SRC = (ROOT / "engine" / "close_pass" / "board.py").read_text(encoding="utf-8")

SERVED_URL_PATH = "/live/us_board_provisional.json"


def _code(src: str) -> str:
    """Source with docstrings and comments stripped.

    Load-bearing for every "this module must not name X" assertion below: the
    prose necessarily NAMES the things it forbids ("writes no data/ path", "no
    insider, no 13F"), so a grep over the whole file fails on the module's own
    explanation of why it is safe — and the obvious repair, deleting the
    sentence, would make the file worse. ``ast.unparse`` drops comments for
    free and keeps string literals that are actually code.
    """
    tree = ast.parse(src)
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or len(body) < 2:
            continue          # never empty a body — an empty one will not unparse
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            body.pop(0)
    return ast.unparse(tree)


CODE = {name: _code(src) for name, src in (
    ("publish", PUBLISH_SRC), ("mirror", MIRROR_SRC), ("reconcile", RECONCILE_SRC),
    ("board", BOARD_SRC),
    ("engine.reconcile",
     (ROOT / "engine" / "close_pass" / "reconcile.py").read_text(encoding="utf-8")),
)}


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────
def verdict(tier: str = "T2", *, eligible: bool = True, ticks: int = 0) -> dict:
    return {"eligible": eligible, "tier_cascade": tier, "tier_sub": None,
            "ticks": ticks, "provisional": False, "asof": SESSION}


def inputs(names=("AAA", "BBB"), *, ext_z: float = 0.5,
           basis: str = "split_and_dividend_adjusted") -> dict:
    return {
        "verdicts": {n: verdict() for n in names},
        "ext_by": {n: {"ext_z": ext_z} for n in names},
        "adjustment_by": {n: basis for n in names},
        "price_through": {n: SESSION for n in names},
        "universe_n": len(names),
        "skipped": {},
    }


@pytest.fixture
def lane(monkeypatch, tmp_path):
    """A runnable pass with R2 stubbed at the r2io boundary and a tmp live plane.

    Every test drives the SAME entry point the workflow calls (``P.run``) rather
    than a helper that could drift away from it.
    """
    store: dict[str, dict] = {}
    monkeypatch.setattr(P.r2io, "put_json",
                        lambda key, payload, **kw: store.__setitem__(key, payload) or True)
    monkeypatch.setattr(P.r2io, "get_json", lambda key, **kw: store.get(key))

    served_dir = tmp_path / "public" / "live"
    served_dir.mkdir(parents=True)

    class Lane:
        r2 = store
        root = tmp_path
        served = served_dir / "us_board_provisional.json"

        def run(self, *, now: datetime = NOW, dry_run: bool = False,
                force: bool = True, served: str | None = ...,
                data: dict | None = None) -> int:
            return P.run(now=now, dry_run=dry_run, force=force,
                         served=str(self.served) if served is ... else served,
                         collector=lambda session: data or inputs())

    return Lane()


# ─────────────────────────────────────────────────────────────────────────────
# LEDGER LAW — G0.2. The lane writes a file; it must still never write THAT file.
# ─────────────────────────────────────────────────────────────────────────────
def test_the_pass_writes_nothing_under_data(lane, tmp_path):
    assert lane.run() == 0
    assert not (tmp_path / "data").exists()
    # Nothing anywhere in the lane's own modules names a data/ path, and the
    # served target is not under the root it was handed.
    for name, code in CODE.items():
        assert not re.search(r"['\"]data/", code), name
    assert not str(lane.served).startswith(str(tmp_path / "data"))
    assert P.SERVED_PATH.startswith("/var/lib/macro-live/")


def test_the_only_filesystem_write_is_the_configured_served_path():
    """AST, not grep: ``os.replace`` — the call that makes a file visible —
    appears exactly once, inside publish_served, and no other function in the
    publishing module writes at all.

    Matched on the DOTTED name. Bare ``replace`` would also catch ``str.replace``
    and ``datetime.replace``, which mean nothing here — an assertion that fires
    on those is one somebody deletes rather than reads.
    """
    DOTTED = {"os.replace", "os.rename", "os.link", "os.symlink", "os.remove",
              "os.rmdir", "os.mkdir", "os.makedirs", "shutil.copy", "shutil.copyfile",
              "shutil.copyfileobj", "shutil.move"}
    #: Method-style, whatever the receiver is called — ``p.write_bytes(...)`` is
    #: the obvious way to "simplify" the temp-then-rename away, so it must be
    #: caught by NAME, not by receiver.
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
    for fn in ast.walk(ast.parse(PUBLISH_SRC)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if isinstance(node, ast.Call) and (tag := label(node.func)):
                found.setdefault(tag, []).append(fn.name)
                if tag == "unlink":
                    unlink_targets += [getattr(a, "id", "?") for a in node.args]
    assert found.get("os.replace") == ["publish_served"], found
    # ``unlink`` is the temp file's own cleanup and nothing else — a served copy
    # is never deleted, only replaced, so a failed pass can never leave the page
    # with no file at all.
    assert set(found) <= {"os.replace", "unlink"}, f"unexpected write calls: {found}"
    assert all(fns == ["publish_served"] for fns in found.values()), found
    assert unlink_targets == ["tmp_name"], unlink_targets


def test_neither_the_mirror_nor_the_reconciler_writes_on_its_own():
    """The mirror publishes THROUGH publish_served and the reconciler writes
    nothing at all. A second write path is a second thing that can truncate a
    live artifact, and a reconciler that wrote would be grading the record by
    editing it."""
    for src, name in ((MIRROR_SRC, "mirror"), (RECONCILE_SRC, "reconcile")):
        for banned in ("os.replace", "os.rename", "write_text", "write_bytes",
                       "mkdir", "makedirs", "to_parquet", "to_csv"):
            assert banned not in src, f"{name} writes directly: {banned}"


def test_the_lane_runs_no_git_command_and_commits_nothing():
    """closing-bell needs `git checkout -- .` because it CREATES data/ writes to
    discard. This lane creates none, so the correct contract is not to discard
    them but to be unable to make them: contents: read, and no git anywhere."""
    for banned in ("git add", "git commit", "git push", "contents: write"):
        assert banned not in WORKFLOW_SRC, banned
    assert WORKFLOW["permissions"] == {"contents": "read"}
    for name, code in CODE.items():
        for banned in ("subprocess", "os.system", "git "):
            assert banned not in code, f"{name}: {banned}"


def test_the_lane_never_touches_the_prophet_live_store():
    """G0.2's other half and DNR:KILL-INTRADAY-CHRONICLE: an intraday lane may
    not advance a nightly-owned store. The reconciler in particular reads the
    board of record and must never write near it."""
    for name, code in CODE.items():
        assert "prophet_live/" not in code, name
        assert "data/prophet_live" not in code, name
    # It reads the nightly board and writes its receipt to the RUNTIME plane.
    assert RC.NIGHTLY_BOARD == "site/factordata/us_standouts.json"
    assert RC.RECEIPT_KEY.startswith("live_flow/")


# ─────────────────────────────────────────────────────────────────────────────
# The serving gate — /live/us_board_provisional.json is NOT public
# ─────────────────────────────────────────────────────────────────────────────
def _caddy_public_exclusions() -> set[str]:
    import shlex
    caddy = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    match = re.search(r"# PUBLIC-BOUNDARY-START.*?@reg_asset\s*\{\s*not path ([^\n]+)",
                      caddy, flags=re.S)
    assert match, "Caddy public-boundary matcher missing"
    return set(shlex.split(match.group(1)))


def test_the_served_artifact_is_not_public_anywhere():
    """The evening board is the real board, hours early. #3391 regwalled
    /factordata/* for exactly this content; publishing the same names on the
    live plane would route around that ruling rather than honour it."""
    public = POLICY["public"]
    assert SERVED_URL_PATH not in set(public["exact"])
    assert not any(SERVED_URL_PATH.startswith(p) for p in public["prefixes"])
    assert SERVED_URL_PATH not in _caddy_public_exclusions()
    free = POLICY["free_registered"]
    assert SERVED_URL_PATH not in set(free["exact"])
    assert not any(SERVED_URL_PATH.startswith(p) for p in free["prefixes"])


def test_the_public_live_exceptions_are_exactly_the_reviewed_files():
    """A prefix would have swept this artifact in with them. There is no prefix —
    each entry is an individually reviewed file."""
    live_public = sorted(p for p in _caddy_public_exclusions() if p.startswith("/live/"))
    assert live_public == ["/live/breadth.json", "/live/quotes.json",
                           "/live/release_publications.json", "/live/staleness.json"]
    assert not any(p.startswith("/live/") for p in POLICY["public"]["prefixes"])


def test_the_served_path_bridges_the_r2_key_deliberately():
    """Producer key and served path differ by PREFIX only, and both are fixed.
    Renaming the key breaks the mirror; moving the path breaks the surface."""
    assert P.BOARD_KEY == "live_flow/us_board_provisional.json"
    assert Path(P.SERVED_PATH).name == Path(P.BOARD_KEY).name
    assert P.SERVED_PATH.endswith(SERVED_URL_PATH)


# ─────────────────────────────────────────────────────────────────────────────
# Transport
# ─────────────────────────────────────────────────────────────────────────────
def test_the_served_copy_is_byte_identical_to_the_r2_payload(lane):
    """Two planes, one board. A separate serialisation is a way for them to
    disagree, and the confirmation delta grades whichever one it fetched."""
    assert lane.run() == 0
    served = json.loads(lane.served.read_text(encoding="utf-8"))
    assert served == lane.r2[P.BOARD_KEY]
    assert lane.served.read_bytes() == json.dumps(
        lane.r2[P.BOARD_KEY], allow_nan=False, separators=(",", ":")).encode("utf-8")
    assert served["schema"] == CB.SCHEMA
    assert lane.served.stat().st_mode & 0o777 == 0o644     # the edge must read it


def test_the_served_write_is_a_rename_never_an_in_place_truncate(lane, monkeypatch,
                                                                 capsys):
    """A failed pass leaves the PREVIOUS copy whole, not a half-written file.

    Reproduced the only way that matters — kill the write after the temp file
    exists, then assert the live path still parses AND still carries the earlier
    pass's stamp. A stale-but-whole payload is self-describing through its own
    as_of; a truncated one is a parse error on a live page.
    """
    assert lane.run() == 0
    good = lane.served.read_bytes()
    first = json.loads(good)["built_at"]
    capsys.readouterr()

    def _boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(P.os, "replace", _boom)
    assert lane.run(now=NOW.replace(minute=25)) == 0

    # The write was genuinely attempted and genuinely failed — without this the
    # assertions below would also pass on a pass that never tried to write.
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "::warning" in ln and "not written" in ln]
    assert warn and warn[0].startswith("::warning title=close-pass::")
    assert "the previous copy stands" in warn[0]

    assert lane.served.read_bytes() == good
    assert json.loads(lane.served.read_text())["built_at"] == first
    # And no debris beside it: a dot-file left behind accumulates one per pass.
    assert [p.name for p in lane.served.parent.iterdir()] == ["us_board_provisional.json"]


def test_a_payload_that_cannot_serialise_leaves_no_temp_file(lane, capsys):
    """Serialise before mkstemp: the failure must not litter the served dir."""
    assert P.publish_served(lane.served, {"nan": float("nan")}) is False
    assert list(lane.served.parent.iterdir()) == []
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=close-pass::")


def test_no_live_plane_means_no_served_copy_and_no_directory_is_created(lane, capsys):
    """An absent directory means this host is not the VPS. Creating one would
    hand the edge a directory to serve nothing out of."""
    missing = lane.served.parent.parent / "not_installed" / "us_board_provisional.json"
    assert P.publish_served(missing, {"a": 1}) is False
    assert not missing.parent.exists()
    out = [ln for ln in capsys.readouterr().out.splitlines() if "::notice" in ln]
    assert out and out[0].startswith("::notice title=close-pass::")


def test_a_dry_run_publishes_neither_plane(lane):
    assert lane.run(dry_run=True) == 0
    assert lane.r2 == {}
    assert not lane.served.exists()


def test_an_r2_put_failure_still_serves_the_page(lane, monkeypatch, capsys):
    """Independent failure domains: R2 is the pipeline artifact, the file is the
    product path. One hiccuping must not stale the other."""
    monkeypatch.setattr(P.r2io, "put_json", lambda key, payload, **kw: False)
    assert lane.run() == 0
    assert lane.served.is_file()
    assert json.loads(lane.served.read_text())["schema"] == CB.SCHEMA
    assert any("R2 PUT" in ln for ln in capsys.readouterr().out.splitlines())


def test_the_kill_switch_covers_the_served_copy_and_is_not_the_prophet_one(
        lane, monkeypatch, capsys):
    """A stand-down that left the USER-FACING copy writable would invert its own
    purpose. It is a SEPARATE switch from PROPHET_LIVE_NO_PUBLISH on purpose:
    sharing one would mean a Prophet Live rehearsal silently darks the evening
    board, and an operator standing down one lane would dark two."""
    assert lane.run() == 0
    before = lane.served.read_bytes()
    capsys.readouterr()

    monkeypatch.setenv(P.NO_PUBLISH_ENV, "1")
    assert lane.run(now=NOW.replace(minute=30)) == 0
    assert lane.served.read_bytes() == before          # untouched, not truncated
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if P.NO_PUBLISH_ENV in ln]
    assert warn and warn[0].startswith("::warning title=close-pass::")

    # The falsy spellings leave the real path alone.
    for value in ("0", "false", ""):
        monkeypatch.setenv(P.NO_PUBLISH_ENV, value)
        assert lane.run(now=NOW.replace(minute=35)) == 0
        assert lane.served.read_bytes() != before
    assert P.NO_PUBLISH_ENV == "CLOSE_PASS_NO_PUBLISH"
    # And this lane's code never reads the Prophet switch, so standing one lane
    # down can never dark the other by accident.
    assert "PROPHET_LIVE_NO_PUBLISH" not in CODE["publish"]

    # The Prophet switch still guards the R2 PUT, because r2io is shared — that
    # is correct and deliberate, not a leak of this lane's control surface.
    monkeypatch.delenv(P.NO_PUBLISH_ENV, raising=False)
    monkeypatch.setenv("PROPHET_LIVE_NO_PUBLISH", "1")
    assert lane.run(now=NOW.replace(minute=40)) == 0
    assert lane.served.is_file()        # the page still gets its board


def test_the_served_copy_can_be_switched_off(lane):
    """The runner's normal case: publish to R2, leave the plane to the VPS."""
    assert lane.run(served=None) == 0
    assert lane.r2[P.BOARD_KEY]["schema"] == CB.SCHEMA
    assert not lane.served.exists()


# ─────────────────────────────────────────────────────────────────────────────
# The mirror — pure transport
# ─────────────────────────────────────────────────────────────────────────────
def test_the_mirror_copies_the_payload_through_unchanged(lane, monkeypatch):
    """It never computes. The bytes it serves are the bytes the pass published —
    otherwise the board a reader sees and the board the delta grades differ."""
    assert lane.run(served=None) == 0
    published = lane.r2[P.BOARD_KEY]
    monkeypatch.setattr(M.r2io, "get_json", lambda key, **kw: lane.r2.get(key))
    assert M.run(served=str(lane.served)) == 0
    assert json.loads(lane.served.read_text()) == published


def test_the_mirror_rewrites_nothing_once_the_session_is_already_served(
        lane, monkeypatch):
    """~40 ticks a day, one write. Re-writing an unchanged artifact would move
    its mtime and, worse, could move the sentinel's first-fresh-at stamp off the
    pass that actually made the SLA."""
    assert lane.run(served=None) == 0
    monkeypatch.setattr(M.r2io, "get_json", lambda key, **kw: lane.r2.get(key))
    assert M.run(served=str(lane.served)) == 0
    stamp = lane.served.stat().st_mtime_ns
    for _ in range(3):
        assert M.run(served=str(lane.served)) == 0
    assert lane.served.stat().st_mtime_ns == stamp


# ─────────────────────────────────────────────────────────────────────────────
# board_state — the hard interface the W-L1b surface (#5148) consumes
# ─────────────────────────────────────────────────────────────────────────────
def _payload(tickers=("AAA", "BBB")) -> dict:
    return CB.build_board({t: verdict() for t in tickers},
                          {t: {"ext_z": i * 0.5} for i, t in enumerate(tickers)},
                          session=SESSION, built_at=NOW,
                          adjustment_by={t: "split_and_dividend_adjusted"
                                         for t in tickers})


def test_the_board_state_carries_every_field_the_client_refuses_without():
    """The client REFUSES to paint rather than guess, so a missing field is a
    dark stamp, not a lenient one. Each of these is one of those fields."""
    state = CB.board_state(_payload())
    assert state["rel"] == "ahead" and state["note"] == "ahead"
    assert state["generated_at"] == NOW.isoformat().replace("+00:00", "Z")
    assert state["board"]["as_of"] == SESSION and state["board"]["lane"] == "closepass"
    assert datetime.fromisoformat(state["valid_until"].replace("Z", "+00:00")) > NOW


def test_the_ticker_list_is_the_boards_own_display_order():
    """THE safety property, not a convenience. The client compares this against
    the ordered data-ticker values of the cards actually in the grid and paints
    nothing on a mismatch — which is what turns spec gate §0-2 from an intention
    into a property of the code. Sorting or filtering it to look tidier would
    silently disarm the guard.
    """
    # Extension falls with the alphabet here, so the STRONGEST name is last
    # alphabetically: if this list ever comes out sorted, something re-ordered
    # it and the client's grid comparison has been quietly disarmed.
    payload = CB.build_board(
        {t: verdict() for t in ("AAA", "BBB", "CCC")},
        {"AAA": {"ext_z": 1.8}, "BBB": {"ext_z": 1.0}, "CCC": {"ext_z": 0.0}},
        session=SESSION, built_at=NOW,
        adjustment_by={t: "split_and_dividend_adjusted"
                       for t in ("AAA", "BBB", "CCC")})
    state = CB.board_state(payload)
    assert state["board"]["tickers"] == [r["ticker"] for r in payload["names"]]
    assert state["board"]["tickers"] == ["CCC", "BBB", "AAA"]
    assert state["board"]["tickers"] != sorted(state["board"]["tickers"])


def test_a_board_showing_last_nights_cards_can_never_render_tonights_stamp():
    """The gate §0-2 property, stated as the client evaluates it: the tickers
    published are exactly tonight's board, so a grid still holding last night's
    cards mismatches and paints nothing. This is also why the payload's own
    card_complete flag is False — nothing in this lane renders those cards yet.
    """
    tonight = CB.board_state(_payload(("AAA", "BBB")))
    last_night_grid = ["AAA", "ZZZ"]
    assert tonight["board"]["tickers"] != last_night_grid
    # Same names, different ORDER, is also a mismatch — the client compares the
    # ordered list, because a re-ranked board is a different board.
    assert tonight["board"]["tickers"] != list(reversed(tonight["board"]["tickers"]))


def test_the_expiry_is_the_nightlys_landing_and_is_never_optimistic():
    """The producer declares how long its own answer is true for. "Ahead of the
    record" stops being true the moment the record lands, so the expiry is
    anchored on that and not on a comfortable round number."""
    assert CB.NIGHTLY_EXPECTED_BY_UTC.hour == 6
    assert CB.valid_until(NOW) == datetime(2026, 8, 8, 6, 0, tzinfo=timezone.utc)
    # Strictly after, never "now": a pass AT the edge gets the next day's, so a
    # payload can never be born already expired.
    edge = datetime(2026, 8, 7, 6, 0, tzinfo=timezone.utc)
    assert CB.valid_until(edge) == datetime(2026, 8, 8, 6, 0, tzinfo=timezone.utc)
    # daily.yml fires 22:30 UTC; the expiry must sit after it, or the stamp
    # would go dark before the record it is waiting for even starts building.
    assert CB.valid_until(NOW) > NOW.replace(hour=22, minute=30)


def test_the_confirmation_state_is_never_published_from_the_live_plane():
    """State 2 is the nightly render's own SERVER-SIDE receipt and the client
    refuses to paint it from here. A live-plane 'confirmed' would be a second
    producer of the same claim, racing the render that owns it."""
    assert CB.board_state(_payload())["note"] != "confirmed"
    for bad in ("confirmed", "closed", "", None):
        with pytest.raises(ValueError):
            CB.board_state(_payload(), rel=bad)


def test_behind_without_a_date_is_impossible_to_emit():
    """confirmed_label is MANDATORY whenever rel == 'behind' — an undated stale
    board is the exact ambiguity that misleads. This lane never emits 'behind'
    at all (it would need a producer that runs on the evenings this one did NOT
    publish), and the constructor refuses to build a bare one."""
    assert CB.board_state(_payload())["rel"] == "ahead"
    state = CB.board_state(_payload(), rel="behind")
    # Nothing here can supply a last-confirmed date, so the only honest 'behind'
    # this lane could produce is one the client will refuse — which is why the
    # lane does not produce it. Pinned so a later edit has to face the question.
    assert "confirmed_label" not in state


# ─────────────────────────────────────────────────────────────────────────────
# The card rows (W-L1d) — the payload ships FACTS, the client ships WORDS
# ─────────────────────────────────────────────────────────────────────────────
def display(tickers=("AAA", "BBB"), **over) -> dict:
    """Per-name display facts, in the shape close_pass_publish.collect gathers."""
    return {t: dict({"name": f"{t} Corp", "name_zh": f"{t}公司",
                     "sec": "Technology", "sec_zh": "科技",
                     "price": 187.456, "spark": f"<svg data-{t}></svg>"},
                    **over.get(t, {})) for t in tickers}


def _carded(tickers=("AAA", "BBB"), **over) -> dict:
    """A card-complete board whose RANKED order is the reverse of the alphabet.

    Extension is handed out descending, so the runway leg rises as the ticker
    falls: any projection that quietly sorted `cards` or `tickers` would come
    out alphabetical and fail the parallelism tests instead of passing them by
    coincidence. Same technique as test_the_ticker_list_is_the_boards_own_
    display_order, for the same reason.
    """
    return CB.build_board({t: verdict() for t in tickers},
                          {t: {"ext_z": 1.8 - i * 0.8}
                           for i, t in enumerate(tickers)},
                          session=SESSION, built_at=NOW,
                          adjustment_by={t: "split_and_dividend_adjusted"
                                         for t in tickers},
                          display_by=display(tickers, **over))


def test_the_cards_and_the_tickers_are_one_list_projected_twice():
    """THE parallelism gate. The client walks `cards` and `tickers` by INDEX —
    `tickers` arms the identity check and `cards[i]` paints the card it admitted
    — so a length or order drift between them does not degrade the board, it
    mislabels it: every card from the drift point on would carry another name's
    ticker. Pinned at three properties (length, per-index ticker, and that the
    order is the board's own ranked order rather than the alphabet) so a change
    to either producer has to break this test to ship."""
    state = CB.board_state(_carded(("AAA", "BBB", "CCC")))["board"]
    assert state["card_complete"] is True
    assert len(state["cards"]) == len(state["tickers"]) == 3
    assert [c["tk"] for c in state["cards"]] == state["tickers"]
    # Not incidentally equal because both happen to be sorted: extension falls
    # with the alphabet in this fixture, so the ranked order is the reverse of
    # it. A projection that sorted either list would fail here.
    assert state["tickers"] == ["CCC", "BBB", "AAA"] != sorted(state["tickers"])


def test_no_hundred_scale_number_reaches_a_card_row():
    """`edge` is never emitted and neither is any figure on the board's 100-point
    scale. This pass covers 40 of those points; a number beside a card would read
    as the nightly's score and would not be it — and renormalising the 40 up to
    100 would redefine what a point means to make the number look finished."""
    card = CB.board_state(_carded())["board"]["cards"][0]
    assert set(card) == set(CB.CARD_FIELDS)
    for banned in ("edge", "points", "score", "provisional_rank", "rank",
                   "weight_covered", "legs"):
        assert banned not in card
    # Every NUMBER in a card row is a [0,1] leg. price_txt is a formatted price,
    # not a score, so the sweep is over numeric values rather than over strings.
    numbers = {k: v for k, v in card.items() if isinstance(v, (int, float))}
    assert set(numbers) == {"signal", "runway"}
    assert all(0.0 <= v <= 1.0 for v in numbers.values()), numbers


def test_the_weights_are_still_not_renormalised_now_that_cards_ship():
    """The pinned invariant, re-asserted on the card-carrying payload: shipping
    a renderable card is not a reason to make the covered 40 points look like
    100."""
    payload = _carded()
    assert payload["scoring"]["renormalised"] is False
    assert payload["scoring"]["weight_covered"] == 40
    assert payload["scoring"]["weight_total"] == 100
    assert set(payload["scoring"]["legs_omitted"]) == {"entry", "edge", "quality"}


def test_a_card_row_carries_no_words_of_its_own():
    """The split is load-bearing. `verb`, the edge label, every tip and every
    bilingual sentence are DERIVED client-side from signal/runway through the
    client's lexicon. A rendered word here makes a language-neutral payload
    language-specific and stands up a second owner of one vocabulary."""
    card = CB.board_state(_carded())["board"]["cards"][0]
    for word_field in ("verb", "edge_txt", "edge_label_en", "edge_label_zh",
                       "edge_tip_en", "edge_tip_zh", "flag", "flags", "marks",
                       "stage", "stage_key", "trigger", "triage", "featured",
                       "zone_kind", "zone_lo", "zone_hi", "tip_en", "tip_zh"):
        assert word_field not in card, word_field


def test_the_card_href_is_the_nightlys_own_ticker_page_url():
    """Read out of the nightly's pv_card call site, never invented. A second URL
    convention would send the evening board's cards somewhere the morning
    board's cards do not go, and the reader would find it before we did."""
    call_site = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "'href': 'stock.html#' ~ n.ticker, 'tk': n.ticker, 'mkt': 'us'," in call_site
    card = CB.board_state(_carded())["board"]["cards"][0]
    assert card["href"] == f"stock.html#{card['tk']}"
    assert card["mkt"] == "us" and card["sym"] == card["tk"]


def test_the_price_is_formatted_as_the_nightly_formats_it():
    call_site = (ROOT / "templates" / "dashboard.html.j2").read_text(encoding="utf-8")
    assert "'price_txt': ('$' ~ ('%.2f'|format(n.price)))" in call_site
    assert CB.board_state(_carded())["board"]["cards"][0]["price_txt"] == "$187.46"


def test_a_row_that_cannot_fill_a_required_field_leaves_the_board_entirely():
    """W-L1d gate 3 — `card_complete` is a claim about EVERY row that ships, so a
    row missing a required fact is dropped from `cards` AND `tickers` together
    rather than shipped half-filled under a true flag. Parallelism survives the
    drop, which is the property that makes dropping the safe half of the ruling.

    Membership of record is untouched: the name keeps its place in `names`, so
    the reconciler still grades it. Only the client's grid is short, and the
    count says so."""
    payload = _carded(("AAA", "BBB", "CCC"), BBB={"name": "   "})
    contract = payload["consumer_contract"]
    assert contract["card_complete"] is True     # every row that SHIPS is whole
    assert contract["cards_n"] == 2 and contract["cards_dropped_n"] == 1

    state = CB.board_state(payload)["board"]
    assert state["tickers"] == ["CCC", "AAA"]    # BBB is gone from BOTH lists
    assert [c["tk"] for c in state["cards"]] == state["tickers"]
    # ...but not from the board of record.
    assert "BBB" in [r["ticker"] for r in payload["names"]]


def test_an_optional_field_is_null_and_never_guessed():
    """A null with a reason is the correct outcome; an imputed value is the
    failure. A name absent from the committed zh map, or a series too short to
    draw, yields None — and the card still ships, because the card macro guards
    every one of these with .get()."""
    payload = _carded(("AAA",), AAA={"name_zh": None, "sec": None,
                                     "sec_zh": None, "spark": ""})
    card = CB.board_state(payload)["board"]["cards"][0]
    assert card["name_zh"] is None and card["sec"] is None
    assert card["sec_zh"] is None and card["spark"] is None
    # Present-but-null, never absent: a missing KEY would make the row's shape
    # vary and force the client to branch on shape instead of on value.
    assert set(card) == set(CB.CARD_FIELDS)
    assert payload["consumer_contract"]["card_complete"] is True


def test_every_required_field_is_one_the_row_actually_carries():
    assert set(CB.CARD_REQUIRED) <= set(CB.CARD_FIELDS)
    assert set(CB.CARD_FIELDS) == {
        "tk", "sym", "mkt", "href", "date", "name", "name_zh", "sec", "sec_zh",
        "price_txt", "spark", "signal", "runway"}


def test_a_board_with_no_display_inputs_publishes_no_cards_at_all():
    """The degraded shape is the OLD shape: full ticker list, no `cards` key,
    card_complete false — which is exactly what the client already refuses to
    render cards from. A caller that only wants membership and legs (the
    reconciler, a replay) is unaffected by W-L1d."""
    payload = _payload(("AAA", "BBB"))
    state = CB.board_state(payload)["board"]
    assert state["card_complete"] is False
    assert "cards" not in state
    # The FULL admitted list, unfiltered — no card can drop a name when no card
    # was built in the first place.
    assert state["tickers"] == [r["ticker"] for r in payload["names"]]


def test_the_lane_gathers_display_facts_only_for_names_the_gate_admits():
    """~1,660 names in the universe, ~130 on the board. Drawing a sparkline for
    every evaluated name would build ~1,530 SVGs to discard them, on a lane with
    ~30 minutes of the 18:30 SLA to spend."""
    src = (ROOT / "scripts" / "close_pass_publish.py").read_text(encoding="utf-8")
    body = src.split("def collect(")[1].split("\ndef ")[0]
    assert "if signal_gate.is_buyable(verdict):" in body
    guard = body.index("if signal_gate.is_buyable(verdict):")
    assert body.index('"spark": _spark_svg(') > guard
    # The nightly's own window, so the two boards draw the same history.
    assert P.SPARK_BARS == 64
    assert "close.tail(64)" in (ROOT / "scripts" / "build_stock_library.py").read_text(
        encoding="utf-8")


def test_the_mirror_annotates_the_live_strip_with_only_that_one_key(tmp_path):
    """"One artifact, one poll, one client" — but this lane does not own that
    artifact, so it writes exactly one key into it and nothing else."""
    plv = tmp_path / "prophet_live.json"
    original = {"schema": "prophet_live.states/v1", "as_of": SESSION,
                "states": {"AAA": {"state": "buyable"}}, "meta": {"delay_min": 15}}
    plv.write_text(json.dumps(original))

    payload = _payload()
    assert M.annotate_live_strip(plv, payload) is True
    doc = json.loads(plv.read_text())
    assert doc[M.STATE_KEY] == CB.board_state(payload)
    assert {k: v for k, v in doc.items() if k != M.STATE_KEY} == original


def test_the_mirror_never_creates_the_strip_artifact(tmp_path):
    """Before the first evaluator pass of the day, or on a host with no live
    plane. Creating it would hand the surface a prophet artifact with no prophet
    data in it."""
    missing = tmp_path / "prophet_live.json"
    assert M.annotate_live_strip(missing, _payload()) is False
    assert not missing.exists()
    # An unparseable file is left exactly as it is, not repaired into one.
    broken = tmp_path / "broken.json"
    broken.write_text('{"states": ')
    assert M.annotate_live_strip(broken, _payload()) is False
    assert broken.read_text() == '{"states": '


def test_re_annotating_an_unchanged_strip_rewrites_nothing(tmp_path):
    """It ticks every five minutes against an artifact another lane owns. A
    rewrite per tick would move its mtime ~40 times a day and put this lane in a
    write race it does not need to be in."""
    plv = tmp_path / "prophet_live.json"
    plv.write_text(json.dumps({"states": {}}))
    payload = _payload()
    assert M.annotate_live_strip(plv, payload) is True
    stamp = plv.stat().st_mtime_ns
    for _ in range(3):
        assert M.annotate_live_strip(plv, payload) is False
    assert plv.stat().st_mtime_ns == stamp


def test_a_lost_race_with_the_evaluator_goes_dark_and_self_heals(tmp_path):
    """The evaluator rewrites prophet_live.json whole every five minutes. If it
    wins a race the key is gone — and gone means the surface paints NOTHING,
    which is the correct direction. The next tick restores it."""
    plv = tmp_path / "prophet_live.json"
    payload = _payload()
    plv.write_text(json.dumps({"states": {}}))
    assert M.annotate_live_strip(plv, payload) is True

    # The evaluator's next pass: a whole new document, no board_state.
    plv.write_text(json.dumps({"states": {"AAA": {"state": "forming"}}}))
    assert M.STATE_KEY not in json.loads(plv.read_text())
    assert M.annotate_live_strip(plv, payload) is True
    assert json.loads(plv.read_text())[M.STATE_KEY] == CB.board_state(payload)


def test_a_concurrent_rewrite_skips_the_write_instead_of_clobbering(tmp_path,
                                                                    monkeypatch):
    """THE compare-and-swap gate.

    This lane read-modify-writes a key into an artifact the Prophet Live
    evaluator owns and rewrites whole. It shipped on a disjoint-windows argument
    — evaluator ends 16:15 ET, board publishes ~16:25 ET — that the lane's own
    measurement undercuts: observed queue waits reach 71 minutes, which is
    enough to land this pass inside a period the evaluator owns.

    Without the swap the loser of that race does not merely lose its own key: it
    writes back the document it read MINUTES ago plus one key, and the
    evaluator's fresh live states are gone until the evaluator's next pass. The
    swap re-reads immediately before the write and skips on a byte change, so
    the cost of losing is one tick of this lane's own key.

    The concurrent write is injected where it really happens — while
    `board_state` is building the key, between the two reads.
    """
    plv = tmp_path / "prophet_live.json"
    stale = {"schema": "prophet_live.states/v1", "states": {"AAA": {"state": "forming"}}}
    plv.write_text(json.dumps(stale))
    fresh = {"schema": "prophet_live.states/v1",
             "states": {"AAA": {"state": "buyable"}, "ZZZ": {"state": "forming"}},
             "meta": {"delay_min": 15}}

    real = CB.board_state
    def evaluator_wins(payload, **kw):
        plv.write_text(json.dumps(fresh))        # the evaluator's whole rewrite
        return real(payload, **kw)
    monkeypatch.setattr(M.CB, "board_state", evaluator_wins)

    payload = _payload()
    assert M.annotate_live_strip(plv, payload) is False
    # The evaluator's document is intact — not the stale one this pass had read.
    landed = json.loads(plv.read_text())
    assert landed == fresh
    assert M.STATE_KEY not in landed

    # And it self-heals: the next tick, with no concurrent write, annotates the
    # NEW document rather than resurrecting the stale one.
    monkeypatch.setattr(M.CB, "board_state", real)
    assert M.annotate_live_strip(plv, payload) is True
    healed = json.loads(plv.read_text())
    assert healed[M.STATE_KEY] == CB.board_state(payload)
    assert {k: v for k, v in healed.items() if k != M.STATE_KEY} == fresh


def test_the_swap_compares_bytes_rather_than_the_parsed_object(tmp_path,
                                                               monkeypatch):
    """A digest over the parse would call a real rewrite "unchanged" whenever the
    evaluator re-emitted equal data with different spacing or key order — the
    exact case where the stale document this pass holds is still wrong."""
    plv = tmp_path / "prophet_live.json"
    doc = {"states": {"AAA": {"state": "forming"}}, "schema": "x"}
    plv.write_text(json.dumps(doc, separators=(",", ":")))

    real = CB.board_state
    def reserialise(payload, **kw):
        # Same object, different bytes: indented, keys in the other order.
        plv.write_text(json.dumps(dict(reversed(list(doc.items()))), indent=2))
        return real(payload, **kw)
    monkeypatch.setattr(M.CB, "board_state", reserialise)

    assert M.annotate_live_strip(plv, _payload()) is False
    assert M.STATE_KEY not in json.loads(plv.read_text())


def test_the_strip_annotation_is_independent_of_the_full_board_copy(tmp_path,
                                                                    monkeypatch):
    """The surface reads only the key. A mirror that skipped the annotation
    because the big file was already current would leave the page unstamped
    after any single-sided failure."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    payload = _payload()
    served.write_text(json.dumps(payload))       # full copy already current
    plv.write_text(json.dumps({"states": {}}))   # strip is not

    assert M.run(served=str(served), plv=str(plv),
                 fetch=lambda key, **kw: payload) == 0
    assert json.loads(plv.read_text())[M.STATE_KEY]["rel"] == "ahead"


def test_the_strip_annotation_can_be_switched_off():
    assert M.PLV_SERVED_PATH.endswith("/live/prophet_live.json")
    assert M.STATE_KEY == "board_state"


def test_an_empty_plane_is_a_notice_not_an_alarm(monkeypatch, tmp_path, capsys):
    """Absent is the ORDINARY state before the evening pass runs. An alarm that
    fires forty times a day trains the operator to ignore the channel."""
    monkeypatch.setattr(M.r2io, "get_json", lambda key, **kw: None)
    assert M.run(served=str(tmp_path / "x.json")) == 0
    out = capsys.readouterr().out
    assert "::notice title=close-pass::" in out and "::warning" not in out


# ─────────────────────────────────────────────────────────────────────────────
# Lane semantics
# ─────────────────────────────────────────────────────────────────────────────
def test_a_non_session_day_publishes_nothing(lane, capsys):
    """2026-08-08 is a Saturday. A skip is a notice, never an alarm."""
    saturday = datetime(2026, 8, 8, 20, 20, tzinfo=timezone.utc)
    assert lane.run(now=saturday) == 0
    assert lane.r2 == {} and not lane.served.exists()
    assert "::notice title=close-pass::" in capsys.readouterr().out


def test_the_session_is_todays_ET_date_not_the_last_completed_one():
    """The freshness-gate adaptation closing-bell.yml documents: this lane fires
    BEFORE the 17:00 ET settle buffer, so expected_last_session() still resolves
    to YESTERDAY and would stamp every evening board with the wrong session."""
    from lib import nyse_calendar
    assert P.session_date(NOW) == SESSION
    assert nyse_calendar.expected_last_session(NOW).isoformat() != SESSION


def test_the_dedup_skips_the_off_season_dst_line(lane, capsys):
    """Both cron lines fire year-round; one always lands at the wrong ET hour.
    Recomputing over the same closes and republishing would reset the artifact
    and move the SLA stamp off the pass that made it."""
    assert lane.run() == 0
    capsys.readouterr()
    assert P.run(now=NOW.replace(hour=21), force=False, served=None,
                 collector=lambda s: inputs(),
                 published=lambda s: True) == 0
    assert "already published" in capsys.readouterr().out


def test_a_name_without_todays_close_is_never_carried_at_yesterdays_price():
    """At 16:20 ET a thin name legitimately has no bar yet. Carrying it at the
    previous close would publish a mixed-vintage board — the exact defect W-L0
    gate 3 exists to stop. It is skipped and COUNTED, so coverage degrades
    visibly instead of truth degrading silently."""
    data = inputs(("AAA",))
    data["price_through"]["AAA"] = "2026-08-06"
    data["skipped"] = {"no_todays_bar": 1}
    payload = CB.build_board(data["verdicts"], data["ext_by"], session=SESSION,
                             built_at=NOW, adjustment_by=data["adjustment_by"],
                             price_through=data["price_through"],
                             universe_n=1, skipped=data["skipped"])
    assert payload["meta"]["skipped"]["no_todays_bar"] == 1
    # The pass itself does the skipping — this pins that the counter reaches the
    # payload, where a reader of the artifact can see the coverage it had.


def test_an_empty_evaluation_publishes_nothing(lane, capsys):
    """Zero evaluable names is a broken store, not an empty market. An empty
    board reads on the page as "nothing qualifies tonight" — a claim this pass
    has no evidence for."""
    empty = {"verdicts": {}, "ext_by": {}, "adjustment_by": {},
             "price_through": {}, "universe_n": 0, "skipped": {"no_close": 4000}}
    assert lane.run(data=empty) == 0
    assert lane.r2 == {} and not lane.served.exists()
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=close-pass::")


def test_every_annotation_is_a_bare_print_that_starts_the_line():
    """A GitHub annotation emitted through a logger becomes ``WARNING ::warning``
    and GitHub silently drops it — the call reviews as an alarm, runs clean and
    produces nothing in the Actions summary. Five lanes shipped that defect
    before #3587 swept 69 sites.

    Checked by AST, not by grep: every ``::``-carrying string literal must be an
    argument to a bare ``print`` (never a logger method), must be the FIRST thing
    on the printed line, and the call must set ``flush`` — stdout is
    block-buffered when piped in CI, so an unflushed annotation can be lost with
    the process.
    """
    for name, code in CODE.items():
        for node in ast.walk(ast.parse(code)):
            if not isinstance(node, ast.Call):
                continue
            literals = [n.value for n in ast.walk(node)
                        if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            joined = "".join(literals)
            if "::warning" not in joined and "::notice" not in joined \
                    and "::error" not in joined:
                continue
            assert getattr(node.func, "id", None) == "print", \
                f"{name}: annotation not emitted by a bare print()"
            first = literals[0] if literals else ""
            assert first.startswith("::"), \
                f"{name}: annotation does not start the line ({first!r})"
            assert any(kw.arg == "flush" for kw in node.keywords), \
                f"{name}: annotation is not flushed"


# ─────────────────────────────────────────────────────────────────────────────
# Scoring honesty — the masterplan's "100% price-derived" premise was measured
# false, and the payload has to carry that rather than hide it.
# ─────────────────────────────────────────────────────────────────────────────
def test_only_the_close_derived_legs_are_computed():
    assert CB.CLOSE_DERIVED_LEGS == ("signal", "runway")
    assert set(CB.OMITTED_LEGS) == {"entry", "edge", "quality"}
    assert set(CB.CLOSE_DERIVED_LEGS) | set(CB.OMITTED_LEGS) \
        == set(us_board_rank.SCORE_WEIGHTS)


def test_the_omitted_legs_are_disclosed_with_the_input_that_blocks_them():
    """"Omitted and disclosed, never imputed." A bare list of leg names is not a
    disclosure — the reader of the artifact has to be able to see WHY, or the
    omission is indistinguishable from a bug."""
    payload = CB.build_board(inputs()["verdicts"], inputs()["ext_by"],
                             session=SESSION, built_at=NOW,
                             adjustment_by=inputs()["adjustment_by"])
    scoring = payload["scoring"]
    assert set(scoring["legs_omitted"]) == {"entry", "edge", "quality"}
    assert all(len(why) > 20 for why in scoring["legs_omitted"].values())
    assert "sector" in scoring["legs_omitted"]["edge"]
    assert "sector" in scoring["legs_omitted"]["quality"]
    assert "macro" in scoring["legs_omitted"]["entry"]


def test_the_weights_are_never_renormalised_over_the_surviving_legs():
    """Renormalising would silently redefine what a point means and produce a
    number that LOOKS like the nightly's score and is not it. 40 points of
    evidence honestly labelled beats a fabricated 100."""
    assert CB.WEIGHT_COVERED == 40.0
    payload = CB.build_board(inputs()["verdicts"], inputs()["ext_by"],
                             session=SESSION, built_at=NOW,
                             adjustment_by=inputs()["adjustment_by"])
    scoring = payload["scoring"]
    assert scoring["weight_covered"] == 40.0
    assert scoring["weight_total"] == 100.0
    assert scoring["renormalised"] is False
    # A perfect row on both surviving legs scores 40, not 100.
    best = CB.build_board({"AAA": verdict("T2")}, {"AAA": {"ext_z": -1.0}},
                          session=SESSION, built_at=NOW,
                          adjustment_by={"AAA": "split_and_dividend_adjusted"})
    assert best["names"][0]["points"] == 40.0


def test_the_legs_are_scored_by_the_boards_own_functions(monkeypatch):
    """A local copy of either leg is a second definition of the board's scoring
    language. signal_value in particular documents a deliberately FROZEN
    non-monotone shape that a reimplementation would "fix" and thereby disagree
    with the nightly on."""
    monkeypatch.setattr(us_board_rank, "signal_value", lambda v: 0.25)
    monkeypatch.setattr(us_board_rank, "runway_value", lambda r: 0.5)
    legs = CB.close_legs(verdict(), {"ext_z": 0.0})
    assert legs == {"signal": 0.25, "runway": 0.5}


def test_the_antichase_threshold_is_the_boards_own_constant():
    """The flag is derived here (a close-pass row has not been through the
    builder pass that stamps it), so it must be derived from the SAME number —
    EXT_Z_FULL, PARABOLIC_Z and the builder's threshold are all 2.0 and must not
    be re-typed as a literal that can drift away from them."""
    assert us_board_rank.EXT_Z_FULL == 2.0
    assert CB.close_legs(verdict(), {"ext_z": 2.4})["runway"] == 0.0
    assert CB.close_legs(verdict(), {"ext_z": 1.0})["runway"] == 0.5
    assert CB.close_legs(verdict(), {"ext_z": None})["runway"] == 0.0   # fail-closed


def test_no_zero_score_authority_input_is_read():
    """Gate 3: no FINRA / OI / fundamental / SUE / insider / 13F anywhere. Each
    is already at zero weight in the nightly; a close pass must not reintroduce
    one through a side door."""
    for name in us_board_rank.ZERO_SCORE_AUTHORITY:
        assert name not in CODE["board"], name
    assert CB.build_board(inputs()["verdicts"], inputs()["ext_by"], session=SESSION,
                          built_at=NOW, adjustment_by=inputs()["adjustment_by"]
                          )["authority_tier"] == "display"


def test_a_name_with_no_declared_price_basis_is_dropped_not_assumed():
    """W-L0 gate 3 — name the adjustment at every seam. universe() genuinely
    returns a mixed population (the deep stocks group is adjusted, the four
    breadth caches are raw vendor prints), so a default would be false for
    whichever family it did not describe."""
    payload = CB.build_board({"AAA": verdict(), "BBB": verdict()},
                             {"AAA": {"ext_z": 0.0}, "BBB": {"ext_z": 0.0}},
                             session=SESSION, built_at=NOW,
                             adjustment_by={"AAA": "split_and_dividend_adjusted"})
    assert [r["ticker"] for r in payload["names"]] == ["AAA"]
    assert payload["meta"]["skipped"]["no_price_basis"] == 1
    assert payload["price_basis"]["bases"] == ["split_and_dividend_adjusted"]


def test_a_mixed_basis_population_says_so_per_name():
    payload = CB.build_board({"AAA": verdict(), "BBB": verdict()},
                             {"AAA": {"ext_z": 0.0}, "BBB": {"ext_z": 0.0}},
                             session=SESSION, built_at=NOW,
                             adjustment_by={"AAA": "split_and_dividend_adjusted",
                                            "BBB": "unadjusted_vendor_print"})
    assert payload["price_basis"]["mixed"] is True
    assert {r["ticker"]: r["price_basis"] for r in payload["names"]} == {
        "AAA": "split_and_dividend_adjusted", "BBB": "unadjusted_vendor_print"}


def test_the_ordering_never_re_admits_or_drops_a_name():
    """us_board_rank: "the buy lane's membership is decided by the confluence
    admission gate alone and is unchanged by this ranking". The provisional
    ordering is a DISPLAY order over 40 points and carries no such power."""
    verdicts = {"AAA": verdict("T2"), "BBB": verdict("T1"),
                "CCC": verdict(None, eligible=False), "DDD": verdict("T4")}
    payload = CB.build_board(verdicts, {t: {"ext_z": 0.0} for t in verdicts},
                             session=SESSION, built_at=NOW,
                             adjustment_by={t: "split_and_dividend_adjusted"
                                            for t in verdicts})
    from engine import signal_gate
    assert {r["ticker"] for r in payload["names"]} == {
        t for t, v in verdicts.items() if signal_gate.is_buyable(v)}
    assert "CCC" not in {r["ticker"] for r in payload["names"]}    # not eligible
    assert "DDD" not in {r["ticker"] for r in payload["names"]}    # T4 is not buyable
    # Every evaluated name survives in `evaluated`, so a dropped card is
    # explicable rather than merely absent.
    assert {r["ticker"] for r in payload["evaluated"]} == set(verdicts)


def test_the_payload_declares_whether_it_can_populate_a_card():
    """Spec §7's invariant is "rel == 'ahead' ONLY when the rendered cards came
    from the evening board", so the payload declares in the DATA whether it can
    populate one — a comment cannot be checked by a consumer.

    The flag is COMPUTED, never asserted, and W-L1d changed the fact rather than
    the standard: given display inputs the pass now fills the card contract and
    says so; without them it still carries board identity and the two close-only
    legs and nothing that could paint a card, and still says so. What must never
    happen is the third case — a true flag over rows that cannot render, which
    `test_a_row_that_cannot_fill_a_required_field_leaves_the_board_entirely`
    pins from the other side."""
    bare = CB.build_board(inputs()["verdicts"], inputs()["ext_by"],
                          session=SESSION, built_at=NOW,
                          adjustment_by=inputs()["adjustment_by"])
    assert bare["consumer_contract"]["card_complete"] is False
    assert bare["consumer_contract"]["cards_n"] == 0
    assert not any("card" in r for r in bare["names"])
    assert "ticker" in bare["consumer_contract"]["row_fields"]
    assert bare["provisional"] is True and bare["lane"] == "closepass"

    carded = _carded(("AAA", "BBB"))
    assert carded["consumer_contract"]["card_complete"] is True
    assert carded["consumer_contract"]["cards_n"] == len(carded["names"])
    assert carded["provisional"] is True and carded["lane"] == "closepass"


# ─────────────────────────────────────────────────────────────────────────────
# The confirmation delta — the integrity metric
# ─────────────────────────────────────────────────────────────────────────────
def _provisional(tickers: dict[str, str]) -> dict:
    return {"as_of": SESSION, "built_at": NOW.isoformat(),
            "names": [{"ticker": t, "tier_cascade": tier}
                      for t, tier in tickers.items()]}


def _nightly(tickers: dict[str, str]) -> dict:
    return {"as_of": SESSION,
            "buy": [{"ticker": t, "signal": {"tier_cascade": tier}}
                    for t, tier in tickers.items()]}


def test_the_delta_reconciles_and_names_every_lane():
    receipt = CR.confirmation_receipt(
        _provisional({"AAA": "T2", "BBB": "T1", "CCC": "T2"}),
        _nightly({"AAA": "T2", "BBB": "T3", "DDD": "T1"}),
        built_at=NOW)
    assert receipt["n_total"] == 3
    assert (receipt["confirmed"], receipt["adjusted"], receipt["dropped"]) == (
        ["AAA"], ["BBB"], ["CCC"])
    assert receipt["n_confirmed"] + receipt["n_adjusted"] + receipt["n_dropped"] \
        == receipt["n_total"]
    assert receipt["detail"]["tier_moves"] == {"BBB": {"from": "T1", "to": "T3"}}
    # Additions ride BESIDE the identity, never inside it — folding them in
    # would break the one invariant the surface is allowed to trust.
    assert receipt["detail"]["n_added"] == 1 and receipt["detail"]["added"] == ["DDD"]


@pytest.mark.parametrize("provisional,nightly,why", [
    (None, _nightly({"AAA": "T2"}), "no evening board at all"),
    (_provisional({"AAA": "T2"}), None, "no board of record"),
    ({"as_of": "2026-08-06", "names": [{"ticker": "AAA", "tier_cascade": "T2"}]},
     _nightly({"AAA": "T2"}), "the two describe different sessions"),
])
def test_no_receipt_is_published_when_an_honest_one_is_impossible(provisional,
                                                                 nightly, why):
    """Spec §7: if the numbers do not reconcile, emit NO receipt rather than a
    wrong one. The session mismatch is the spec's "no receipt after a behind
    night" — diffing against an older board would report last night's names as
    tonight's drops."""
    assert CR.confirmation_receipt(provisional, nightly, built_at=NOW) is None, why


def test_a_duplicate_ticker_yields_no_receipt():
    """A duplicate is not a merge candidate: it means one board is malformed,
    and every count over it is wrong in a way the arithmetic check cannot see —
    the totals still add up."""
    dup = {"as_of": SESSION, "names": [{"ticker": "AAA", "tier_cascade": "T2"},
                                       {"ticker": "AAA", "tier_cascade": "T1"}]}
    assert CR.confirmation_receipt(dup, _nightly({"AAA": "T2"}), built_at=NOW) is None


def test_the_receipt_grades_the_gate_verdict_not_the_partial_score():
    """The provisional board scores 40 of 100 points, so a rank diff would mark
    almost every name "adjusted" and mean nothing. What both boards compute the
    same way is the admission gate's tier."""
    receipt = CR.confirmation_receipt(_provisional({"AAA": "T2"}),
                                      _nightly({"AAA": "T2"}), built_at=NOW)
    assert receipt["n_confirmed"] == 1
    assert "tier" in receipt["detail"]["basis"]


def test_the_reconciler_publishes_nothing_when_there_is_no_pair(tmp_path, capsys):
    board = tmp_path / RC.NIGHTLY_BOARD
    board.parent.mkdir(parents=True)
    board.write_text(json.dumps(_nightly({"AAA": "T2"})))
    published: dict = {}
    assert RC.run(tmp_path, now=NOW, fetch=lambda key, **kw: None,
                  publish=lambda k, v: published.setdefault(k, v) or True) == 0
    assert published == {}
    assert "::notice title=close-pass::" in capsys.readouterr().out


def test_the_reconciler_publishes_the_receipt_to_the_runtime_plane(tmp_path):
    board = tmp_path / RC.NIGHTLY_BOARD
    board.parent.mkdir(parents=True)
    board.write_text(json.dumps(_nightly({"AAA": "T2", "BBB": "T3"})))
    published: dict = {}
    assert RC.run(tmp_path, now=NOW,
                  fetch=lambda key, **kw: _provisional({"AAA": "T2", "CCC": "T1"}),
                  publish=lambda k, v: published.setdefault(k, v) or True) == 0
    receipt = published[RC.RECEIPT_KEY]
    assert receipt["schema"] == CR.RECEIPT_SCHEMA
    assert (receipt["n_confirmed"], receipt["n_dropped"]) == (1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Schedule — both DST regimes, one window, and no collision with the nightly
# ─────────────────────────────────────────────────────────────────────────────
def _crons() -> list[str]:
    return [entry["cron"] for entry in WORKFLOW[True]["schedule"]]


def test_the_timer_covers_the_session_in_both_dst_regimes_without_a_second_window():
    """The UTC span covers the evening publish window under EDT AND EST, and the
    ET trimming is done by the pass itself (session_date → lib.nyse_calendar), so
    "when is the market open" has exactly one definition in this lane."""
    cal = _unit(TIMER)["Timer"]["OnCalendar"]
    m = re.fullmatch(r"Mon\.\.Fri \*-\*-\* (\d+)\.\.(\d+):(\d+)/(\d+):00 UTC", cal)
    assert m, cal
    lo, hi, offset, step = (int(g) for g in m.groups())
    assert step == 5 and 0 <= offset < 5
    # EDT 16:15 ET = 20:15Z ... EST 18:30 ET (the SLA deadline) = 23:30Z.
    assert lo <= 20 and hi >= 23
    assert _unit(TIMER)["Timer"]["Persistent"] == "false"   # never replay a miss
    assert _unit(TIMER)["Timer"]["Unit"] == "macro-live-closepass.service"
    # No second window definition anywhere in the unit files: no ET literal, no
    # duplicated deadline, nothing the pass and the timer could disagree about.
    body = TIMER.read_text(encoding="utf-8").split("[Timer]")[1]
    assert "16:15" not in body and "18:30" not in body


def test_the_cron_pair_fires_at_the_window_start_in_both_regimes():
    """One line per regime, both firing 16:25 ET — the START of the window. The
    off-season line self-skips: under EST the 20:25Z line is 15:25 ET (pre-close,
    the session guard) and under EDT the 21:25Z line is 17:25 ET (already
    published, the dedup)."""
    assert sorted(_crons()) == ["25 20 * * 1-5", "25 21 * * 1-5"]
    for cron in _crons():
        minute, hour = cron.split()[0], int(cron.split()[1])
        assert minute == "25"
        # EDT = UTC-4, EST = UTC-5; each line is 16:25 ET in exactly one regime.
        assert (hour - 4) % 24 == 16 or (hour - 5) % 24 == 16


def _cron_field(spec: str, lo: int, hi: int) -> set[int]:
    """One cron field → the set of values it fires on.

    Written out rather than approximated because the approximation ALREADY got
    this wrong once: a naive split on ``[,/]`` reads ``*/2`` as {*, 2} and
    reports that hour 20 does not match, which cleared minute :20 as free when
    codex-research.yml (``20 */2 * * *``, on the same two physical hosts) fires
    there every other hour. A collision detector that cannot see the collision
    it was written for is worse than none.
    """
    out: set[int] = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, _, raw = part.partition("/")
            step = int(raw)
        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            a, _, b = part.partition("-")
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        out |= set(range(start, end + 1, step))
    return out


@pytest.mark.parametrize("field,lo,hi,expected", [
    ("*/2", 0, 23, {0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22}),   # codex-research
    ("13-23/2", 0, 23, {13, 15, 17, 19, 21, 23}),                  # smart-money-filings
    ("7,37", 0, 59, {7, 37}),                                      # 13f-census
    ("*", 0, 23, set(range(24))),
    ("25", 0, 59, {25}),
])
def test_the_cron_expander_reads_every_form_in_this_repo(field, lo, hi, expected):
    assert _cron_field(field, lo, hi) == expected


def test_the_minute_avoids_the_other_crons_on_the_two_host_pool():
    """MEASURED 2026-08-09: plain `macstudio` is TWO live physical hosts
    (mac-builder-1/2, which also serve the `codex` and `theta-m1` labels), and
    closing-bell holds one of them for the whole window every weekday. So the
    minute is not cosmetic — it decides whether this lane starts or queues
    behind another job on the one remaining slot.

    Derived from the live workflow files rather than a hardcoded list, so a lane
    that later moves ONTO this minute reds here instead of silently contending.
    ``macstudio-light`` is deliberately NOT counted: it is a different single
    host (mac-builder-3) that shares no capacity with this pool.
    """
    ours = {int(c.split()[0]) for c in _crons()}
    assert ours == {25}
    #: The labels mac-builder-1/2 actually carry. EXACT match, never substring:
    #: `macstudio-light` is a different host, and matching it would flag lanes
    #: that share no capacity at all.
    POOL = {"macstudio", "codex", "theta-m1"}
    clashes: list[str] = []
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        if path.name == "close-pass.yml":
            continue
        try:
            spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        # Read the resolved LABELS, not the file's text. A regex over the line
        # matched `runs-on: ubuntu-latest  # never the macstudio pool` on three
        # lanes — the comment saying they are off this pool made them look like
        # they were on it.
        labels: set[str] = set()
        for job in ((spec or {}).get("jobs") or {}).values():
            runs_on = (job or {}).get("runs-on")
            labels |= ({runs_on} if isinstance(runs_on, str)
                       else set(runs_on or ()) if isinstance(runs_on, list) else set())
        if not (labels & POOL):
            continue
        for entry in ((spec or {}).get(True) or {}).get("schedule") or ():
            fields = str(entry.get("cron", "")).split()
            if len(fields) != 5:
                continue
            minutes, hours, _, _, dow = fields
            if dow not in ("*", "1-5") or not (ours & _cron_field(minutes, 0, 59)):
                continue
            if _cron_field(hours, 0, 23) & {20, 21}:
                clashes.append(f"{path.name}: {entry['cron']}")
    assert not clashes, f"same-minute contention on the macstudio pool: {clashes}"


def test_the_schedule_never_collides_with_the_nightly():
    """The close pass clears the earliest member of daily's DST cron pair.

    The nightly fires at 22:30 UTC under EDT and 23:30 UTC under EST.  Pin both
    production crons, then prove the bounded close-pass lane finishes before the
    earlier one; clearing that edge necessarily clears the later one too.
    """
    daily = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8"))
    nightly = [e["cron"] for e in daily[True]["schedule"]]
    assert nightly == ["30 22 * * *", "30 23 * * *"]
    nightly_min = min(
        int(cron.split()[1]) * 60 + int(cron.split()[0]) for cron in nightly
    )
    for cron in _crons():
        fire = int(cron.split()[1]) * 60 + int(cron.split()[0])
        # The pass is capped at 45 minutes, so the latest it can still be running.
        assert fire + WORKFLOW["jobs"]["publish"]["timeout-minutes"] <= nightly_min, cron


def test_the_lane_has_its_own_concurrency_group():
    """It must never share with pipeline-daily, pipeline-closingbell or
    pipeline-render, and a running pass must always finish — a cancelled pass is
    a missed SLA session in the sentinel's record."""
    group = WORKFLOW["concurrency"]["group"]
    assert "closepass" in group
    for foreign in ("pipeline-daily", "pipeline-closingbell", "pipeline-render"):
        assert foreign not in group
    assert WORKFLOW["concurrency"]["cancel-in-progress"] is False


def test_the_lane_is_not_bolted_onto_the_closing_bell_spine():
    """closing-bell runs a MEASURED 109 minutes behind an 81-minute spine and
    lands ~17:55 ET against an 18:30 SLA. A step at the end of that spine would
    spend the entire 35-minute margin — and closing-bell deliberately excludes
    build_prophet, so it does not compute this board in the first place."""
    closing_bell = (ROOT / ".github" / "workflows" / "closing-bell.yml").read_text(
        encoding="utf-8")
    assert "close_pass" not in closing_bell
    assert WORKFLOW["jobs"]["publish"]["runs-on"] == ["self-hosted", "macstudio"]
    # The receipt job is off the mac pool entirely — it reads two JSON documents.
    assert WORKFLOW["jobs"]["reconcile"]["runs-on"] == "ubuntu-latest"


# ─────────────────────────────────────────────────────────────────────────────
# Host wiring — the mirror unit
# ─────────────────────────────────────────────────────────────────────────────
def _unit(path: Path) -> configparser.ConfigParser:
    # interpolation=None is load-bearing: `CPUQuota=60%` is a ConfigParser
    # interpolation syntax error, and a unit file is not an ini template.
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    cp.read_string(path.read_text(encoding="utf-8"))
    return cp


def test_the_service_is_a_capped_oneshot_on_the_lowest_priority_tier():
    """This lane CONSUMES what the quote lanes publish, so it must always lose a
    scheduling contest with them."""
    svc = _unit(SERVICE)["Service"]
    assert svc["Type"] == "oneshot"
    assert svc["ExecStart"].endswith("-m scripts.close_pass_mirror")
    assert svc["WorkingDirectory"] == "/opt/macro"
    assert svc["EnvironmentFile"] == "-/etc/macro-live.env"

    prophet = _unit(DEPLOY / "macro-live-prophet.service")["Service"]
    bars = _unit(DEPLOY / "macro-live-bars.service")["Service"]
    assert int(svc["CPUQuota"].rstrip("%")) <= int(prophet["CPUQuota"].rstrip("%"))
    assert svc["MemoryMax"] == "512M" and svc["MemoryHigh"] == "256M"
    assert int(svc["Nice"]) >= int(bars["Nice"])
    assert int(svc["CPUWeight"]) <= int(bars["CPUWeight"])
    assert int(svc["IOWeight"]) <= int(bars["IOWeight"])
    # Bounded well inside the 300 s timer period: two passes can never overlap.
    assert int(svc["TimeoutStartSec"]) <= 300
    assert svc["NoNewPrivileges"] == "true" and svc["PrivateTmp"] == "true"


def test_no_unit_directive_runs_a_git_command_or_touches_the_served_tree():
    for path in (SERVICE, TIMER):
        unit = _unit(path)
        for section in unit.sections():
            for key, value in unit[section].items():
                for banned in ("git ", "data/", "site.served", "/opt/macro/site"):
                    assert banned not in value, f"{path.name}: {key}={value}"


def test_macro_update_reconciles_the_closepass_units_under_a_narrow_allow_list():
    """Go-live is a repo commit: the reconciler installs, arms and heals the unit.
    The trigger is DERIVED, not eyeballed — the regex from update.sh is applied to
    the two paths it must match and to paths it must not."""
    m = re.search(r"grep -qE '(\^app/deploy/macro-live-closepass[^']+)'", UPDATE_SH)
    assert m, "no close-pass unit trigger in update.sh"
    trigger = re.compile(m.group(1))
    for path in ("app/deploy/macro-live-closepass.service",
                 "app/deploy/macro-live-closepass.timer"):
        assert trigger.search(path), path
    for path in ("app/deploy/macro-live-prophet.service", "scripts/close_pass_mirror.py",
                 "app/deploy/macro-live-closepass.service.bak", "config.yml"):
        assert not trigger.search(path), path

    block = UPDATE_SH.split("# CLOSE-PASS MIRROR lane")[1]
    assert "systemd-analyze verify" in block      # a broken unit never installs
    assert "cmp -s" in block                      # installing twice is a no-op
    assert "systemctl enable --now macro-live-closepass.timer" in block
    assert "is-enabled macro-live-fast.timer" in block   # only where the plane is
    assert "[ ! -f /etc/systemd/system/macro-live-closepass.timer ]" in block


def test_macro_update_never_restarts_the_closepass_oneshot():
    """`systemctl restart` on a oneshot RUNS it — off-schedule, and on a mirror
    that means writing whatever R2 happens to hold at that moment."""
    assert "restart macro-live-closepass.service" not in UPDATE_SH
    assert "start macro-live-closepass.service" not in UPDATE_SH
    # The prophet block must not have been widened to sweep this unit in either.
    prophet_block = UPDATE_SH.split("# PROPHET LIVE evaluator lane")[1].split(
        "# CLOSE-PASS MIRROR lane")[0]
    assert "closepass" not in prophet_block


def test_live_setup_installs_and_arms_the_mirror():
    """A fresh provision must not need a second manual step to arm the lane."""
    assert "macro-live-closepass.service macro-live-closepass.timer" in LIVE_SETUP
    assert "macro-live-closepass.timer >/dev/null" in LIVE_SETUP
