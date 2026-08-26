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
import gzip
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

#: Marker identifying the nightly's us-board ``pv_card`` call site.
_NIGHTLY_CARD_MARKER = "'href': 'stock.html#' ~ n.ticker, 'tk': n.ticker, 'mkt': 'us',"


def _nightly_card_call_site() -> Path:
    """The ONE template holding the nightly's us-board ``pv_card`` call.

    Resolved by search rather than hardcoded, because it has already moved once:
    the call site left ``dashboard.html.j2`` for ``_us_board_cards.html.j2`` when
    the us_stocks board gained its server-side tier split
    (docs/TIER_PREVIEW_PATTERN.md — the free shell and the /premiumdata/ payload
    render cards from one source so they cannot drift). A hardcoded path turns
    the next such move into a confusing "literal missing" failure that reads like
    the convention was deleted, instead of naming the relocation.

    Exactly one owner is the property the two tests below exist to protect: a
    second call site is a second URL/price convention, which is the drift the
    evening board must never introduce.
    """
    owners = sorted(p for p in (ROOT / "templates").glob("*.j2")
                    if _NIGHTLY_CARD_MARKER in p.read_text(encoding="utf-8"))
    assert len(owners) == 1, (
        "expected exactly ONE template to own the nightly's us-board pv_card "
        f"call site; found {[p.name for p in owners]}"
    )
    return owners[0]

import scripts.close_pass_mirror as M  # noqa: E402
import scripts.close_pass_publish as P  # noqa: E402
import scripts.close_pass_reconcile as RC  # noqa: E402
from scripts.workflow_run_source import resolved_workflow_text  # noqa: E402
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
    # PR-A. `massive_close` reaches the network on the lane's behalf, which makes
    # it the newest way this lane could acquire a `data/` write, a git call or a
    # dropped annotation — so it joins the AST sweep rather than being trusted
    # because it is new.
    ("massive_close",
     (ROOT / "engine" / "close_pass" / "massive_close.py").read_text(encoding="utf-8")),
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


def test_the_lane_commits_nothing_and_cannot():
    """CORRECTED 2026-08-13. This used to be
    `test_the_lane_runs_no_git_command_and_commits_nothing`, and its docstring said
    closing-bell needs a discard "because it CREATES data/ writes; this lane creates
    none, so the correct contract is not to discard them but to be unable to make
    them: contents: read, and no git anywhere."

    The premise was false the day it was written. The workflow's `--heal` prefetch
    refreshes the price store into data/yahoo/*.parquet, so the lane's own proof
    step failed on EVERY run from 2026-08-09 until the discard was added — the lane
    was never once green, while the board it publishes to R2 landed fine throughout.
    A test whose reasoning is wrong can still pass; this one did, because it only
    ever checked for `git add`/`git commit`/`git push`, none of which the prefetch
    uses.

    What is actually load-bearing survives and is asserted below: the lane cannot
    COMMIT or PUSH, and it holds `contents: read` so nothing it does can reach main.
    Discarding is now permitted — and required, see the test that follows."""
    for banned in ("git add", "git commit", "git push", "contents: write"):
        assert banned not in WORKFLOW_SRC, banned
    assert WORKFLOW["permissions"] == {"contents": "read"}
    for name, code in CODE.items():
        for banned in ("subprocess", "os.system", "git "):
            assert banned not in code, f"{name}: {banned}"


def test_a_data_writing_step_is_followed_by_a_discard_before_the_proof():
    """The bug that kept this lane red for its whole life, pinned so it cannot
    return: any step that can dirty data/ must be discarded BEFORE the proof step,
    or the proof fails on the lane's own prefetch.

    Order is the contract — a discard placed after the proof would read as a fix and
    change nothing."""
    steps = [s.get("name", "") for job in WORKFLOW["jobs"].values()
             for s in job.get("steps", [])]
    heal = next(i for i, n in enumerate(steps) if "freshness prefetch" in n)
    discard = next(i for i, n in enumerate(steps) if "discard" in n.lower())
    proof = next(i for i, n in enumerate(steps) if "wrote no data/ path" in n)
    assert heal < discard < proof, steps
    body = "\n".join(
        s.get("run", "") for job in WORKFLOW["jobs"].values()
        for s in job.get("steps", []) if "discard" in s.get("name", "").lower())
    assert "git checkout -- data/" in body, body
    assert "git clean -fdq data/" in body, body


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
    # flow_pulse.json and intraday_quotes.json were added to the Caddyfile by
    # #6105 "Restore Intraday Flow live transport truth" (2026-08-20), which
    # deliberately made both anonymously fetchable so the Intraday Flow surface
    # could read them — but that PR never updated this reviewed-inventory list or
    # its twin in tests/test_entry_radar_w4_lane.py, so BOTH have been red on main
    # ever since. CI's path scoping hid it: this suite only runs when the
    # close-pass / entry-radar lanes are touched, so main's routine data pushes
    # never triggered it. Recorded here as reviewed rather than re-litigated —
    # the exposure was the intent of a merged PR, not an accident.
    assert live_public == ["/live/breadth.json", "/live/flow_pulse.json",
                           "/live/intraday_quotes.json", "/live/quotes.json",
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
    """Per-name display facts, exactly as close_pass_publish.collect gathers them.

    `name_zh` and `spark` are None because THE LANE ships them None (2026-08-09
    rulings — see test_the_lane_publishes_no_sparkline_and_no_chinese_company_
    name). This fixture tracks the lane rather than the schema, so a test using
    it sees what a reader sees.
    """
    return {t: dict({"name": f"{t} Corp", "name_zh": None,
                     "sec": "Technology", "sec_zh": "科技",
                     "price": 187.456, "spark": None},
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
    call_site = _nightly_card_call_site().read_text(encoding="utf-8")
    assert "'href': 'stock.html#' ~ n.ticker, 'tk': n.ticker, 'mkt': 'us'," in call_site
    card = CB.board_state(_carded())["board"]["cards"][0]
    assert card["href"] == f"stock.html#{card['tk']}"
    assert card["mkt"] == "us" and card["sym"] == card["tk"]


def test_the_price_is_formatted_as_the_nightly_formats_it():
    call_site = _nightly_card_call_site().read_text(encoding="utf-8")
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
    failure. An unclassified name, or an empty string where a value was
    expected, yields None — and the card still ships, because the card macro
    guards every one of these with .get()."""
    payload = _carded(("AAA",), AAA={"sec": None, "sec_zh": "  "})
    card = CB.board_state(payload)["board"]["cards"][0]
    assert card["name_zh"] is None and card["sec"] is None
    assert card["sec_zh"] is None and card["spark"] is None
    # Present-but-null, never absent: a missing KEY would make the row's shape
    # vary and force the client to branch on shape instead of on value.
    assert set(card) == set(CB.CARD_FIELDS)
    assert payload["consumer_contract"]["card_complete"] is True


def test_an_unmeasured_runway_ships_null_and_never_a_zero():
    """`runway_value` returns 0.0 for THREE different facts — no extension
    reading, an antichase-blocked row, and a genuinely extended one. That
    collapse is correct for a SCORE and false for a DISPLAY: the client reads a
    low runway as thin room, so a 0.0 here would tell a reader a name is
    stretched when nobody measured it. ~5 of 79 live rows.

    The unmeasured forms are all of them — absent, None, NaN, inf and garbage —
    because `_finite_float` is the one predicate both sides use.
    """
    for ext in ({}, {"ext_z": None}, {"ext_z": float("nan")},
                {"ext_z": float("inf")}, {"ext_z": "n/a"}, {"ext_z": True}):
        legs = CB.close_legs(verdict(), ext)
        assert legs["runway"] is None, ext
        # ...and it reaches the card as null, not as a dropped row: the name is
        # still on the board, it just says it was not checked.
        payload = CB.build_board({"AAA": verdict()}, {"AAA": ext},
                                 session=SESSION, built_at=NOW,
                                 adjustment_by={"AAA": "split_and_dividend_adjusted"},
                                 display_by=display(("AAA",)))
        card = CB.board_state(payload)["board"]["cards"][0]
        assert card["tk"] == "AAA" and card["runway"] is None, ext


def test_a_genuinely_extended_name_still_ships_a_real_zero():
    """The other half, and the reason the fix cannot be "null everything low":
    a name WITH an extension reading that says it is fully extended has a
    measured 0.0 runway, and 0.0 is the true display value — there really is no
    room left. Null there would hide a fact the pass actually established.
    """
    fully = CB.close_legs(verdict(), {"ext_z": us_board_rank.EXT_Z_FULL})
    assert fully["runway"] == 0.0
    beyond = CB.close_legs(verdict(), {"ext_z": us_board_rank.EXT_Z_FULL + 3.0})
    assert beyond["runway"] == 0.0
    # Unextended and mid-range still score normally.
    assert CB.close_legs(verdict(), {"ext_z": 0.0})["runway"] == 1.0
    assert 0.0 < CB.close_legs(verdict(), {"ext_z": 1.0})["runway"] < 1.0


def test_the_antichase_case_is_not_a_third_fact_in_this_lane():
    """The lane does not READ an antichase flag, it DERIVES one as
    `ext_z > EXT_Z_FULL` — so it is true exactly when the name is genuinely
    extended, which is the case that honestly means "no room left". It gets
    0.0, not null, and this test is the record of that ruling.

    If a real upstream antichase signal is ever fed in, it becomes a genuinely
    third fact and this test should fail loudly enough to force a re-decision.
    """
    src = (ROOT / "engine" / "close_pass" / "board.py").read_text(encoding="utf-8")
    body = src.split("def close_legs(")[1].split("\ndef ")[0]
    assert 'bool(ext_z > us_board_rank.EXT_Z_FULL)' in body
    # Derived, never read off the ext row.
    assert 'ext.get("antichase_shadow_blocked")' not in body
    blocked = CB.close_legs(verdict(), {"ext_z": us_board_rank.EXT_Z_FULL + 1.0})
    assert blocked["runway"] == 0.0 and blocked["runway"] is not None


def test_the_display_null_does_not_move_the_score_by_one_bit():
    """THE invariance gate. `points` and `provisional_rank` must be exactly what
    they were before `close_legs` learned to say "unmeasured" — a null DISPLAY
    leg still scores 0.0. Checked against `us_board_rank`'s own functions on the
    same rows, which still collapse all three cases to 0.0, so this compares the
    published score against the pre-change arithmetic rather than against a
    number copied out of the new implementation.
    """
    ext_by = {"AAA": {"ext_z": 0.2},                  # measured, lots of room
              "BBB": {},                              # UNMEASURED -> null display
              "CCC": {"ext_z": 9.0},                  # measured, fully extended
              "DDD": {"ext_z": float("nan")}}         # UNMEASURED -> null display
    tickers = tuple(ext_by)
    payload = CB.build_board(
        {t: verdict() for t in tickers}, ext_by, session=SESSION, built_at=NOW,
        adjustment_by={t: "split_and_dividend_adjusted" for t in tickers})

    for row in payload["names"]:
        raw = {"ext_z": ext_by[row["ticker"]].get("ext_z")}
        raw["antichase_shadow_blocked"] = None
        expected = round(
            us_board_rank.SCORE_WEIGHTS["signal"] * us_board_rank.signal_value(verdict())
            + us_board_rank.SCORE_WEIGHTS["runway"] * us_board_rank.runway_value(raw), 4)
        assert row["points"] == expected, row["ticker"]

    # The unmeasured names score 0 on runway and therefore rank BELOW the
    # measured one that has room — unchanged, and the null never floated them up.
    ranked = [(r["ticker"], r["provisional_rank"]) for r in payload["names"]]
    assert ranked[0] == ("AAA", 1)
    assert [t for t, _ in ranked] == ["AAA", "BBB", "CCC", "DDD"]
    assert [r["legs"]["runway"] for r in payload["names"]] == [0.9, None, 0.0, None]


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
    """~1,660 names in the universe, ~130 on the board. Gathering display facts
    for every evaluated name would be ~1,530 lookups built to be discarded, on a
    lane with ~30 minutes of the 18:30 SLA to spend."""
    src = (ROOT / "scripts" / "close_pass_publish.py").read_text(encoding="utf-8")
    body = src.split("def collect(")[1].split("\ndef ")[0]
    assert "if signal_gate.is_buyable(verdict):" in body
    guard = body.index("if signal_gate.is_buyable(verdict):")
    assert body.index("display[ticker] = {") > guard


def test_the_lane_publishes_no_sparkline_and_no_chinese_company_name():
    """Both are REACHABLE and both ship null, by ruling rather than by accident
    — so both are pinned here, because "we could easily fill this" is exactly
    the argument that would refill them.

    spark: charts are 86% of the payload (~1,700 B/card against ~281 B for the
    twelve other fields combined) on an artifact polled every 120 s to detect a
    key that changes once a day — and the evening chart renders BANDLESS,
    because its buy-zone band comes from the omitted `entry` leg. Paying 86% of
    the payload for a degraded copy of the morning chart inverts the trade.

    name_zh: a committed 1,583-ticker map exists and this lane could read it,
    but the nightly's US cards pass no `name_zh`, so filling it here would flip
    a company's NAME between languages overnight. A surface whose whole job is
    "which board am I looking at" cannot also change what things are called.
    """
    body = (ROOT / "scripts" / "close_pass_publish.py").read_text(
        encoding="utf-8").split("def collect(")[1].split("\ndef ")[0]
    assert '"spark": None,' in body and '"name_zh": None,' in body
    # Nothing is imported to build either one — a live import beside a nulled
    # field is how a ruling quietly decays into a one-line revert. Checked
    # against the CODE only: the comments naming both sources are the record of
    # why they are null, and must stay free to say so.
    code = "\n".join(ln for ln in body.splitlines()
                     if not ln.lstrip().startswith("#"))
    assert "_spark_svg" not in code and "us_names_zh" not in code
    # sec_zh is NOT nulled: it is the same `tr` call the nightly template makes,
    # so it carries no evening/morning inconsistency.
    assert '"sec_zh": tr(sector) if sector else None,' in body

    card = CB.board_state(_carded())["board"]["cards"][0]
    assert card["spark"] is None and card["name_zh"] is None
    assert set(card) == set(CB.CARD_FIELDS)    # present-but-null, never absent

    # The null is the LANE's ruling, not an engine limitation: handed the
    # values, `card_row` carries them. Stated so a future reader knows the
    # decision lives in `collect`, and so "the engine can't do it" never
    # becomes the remembered reason.
    fed = CB.card_row({"ticker": "AAA", "signal_asof": SESSION,
                       "legs": {"signal": 0.5, "runway": 0.5}},
                      {"name": "AAA Corp", "name_zh": "苹果", "price": 1.0,
                       "spark": "<svg/>"})
    assert fed["name_zh"] == "苹果" and fed["spark"] == "<svg/>"


def test_the_board_state_key_stays_small_enough_for_a_120s_poll():
    """The SCHEMA-width size guard, at the real board width.

    This key rides prophet_live.json, which every dashboard reader polls every
    120 s, and it changes ONCE A DAY. Measured at 131 rows: 33,358 B raw /
    4,432 B gzip as shipped, against 260,774 / 36,746 with per-card sparklines.
    The ceilings sit between, so any per-row field fat enough to matter — an SVG,
    a tip string, an embedded chart — fails here rather than in production.

    WHAT THIS DOES *NOT* CATCH, deliberately: this test supplies its own display
    facts, so it cannot see the lane re-enabling sparklines in `collect`. That is
    `test_the_lane_publishes_no_sparkline_and_no_chinese_company_name`'s job.
    Two different defects, two guards; neither is the other's backstop.

    RAW IS THE BINDING BOUND. These synthetic rows repeat one sector and a
    sequential ticker, so they gzip far better than real ones (2,993 B here vs
    4,432 B measured on real names); the gzip assertion is a loose backstop and
    the raw ceiling is what actually bites.
    """
    n = 131                                    # the lane's measured board width
    tickers = tuple(f"T{i:03d}" for i in range(n))
    display_by = {t: {"name": f"{t} Holdings Incorporated", "name_zh": None,
                      "sec": "Consumer Discretionary", "sec_zh": "非必需消费品",
                      "price": 187.456 + i, "spark": None}
                  for i, t in enumerate(tickers)}
    payload = CB.build_board(
        {t: verdict() for t in tickers},
        {t: {"ext_z": 1.8 - i * 0.02} for i, t in enumerate(tickers)},
        session=SESSION, built_at=NOW,
        adjustment_by={t: "split_and_dividend_adjusted" for t in tickers},
        display_by=display_by)
    state = CB.board_state(payload)
    assert len(state["board"]["cards"]) == n

    raw = json.dumps(state, separators=(",", ":"), allow_nan=False).encode()
    assert len(raw) < 60_000, f"{len(raw)} B raw — did per-card SVG come back?"
    assert len(gzip.compress(raw, 6)) < 12_000, "gzip ceiling breached"


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


# ─────────────────────────────────────────────────────────────────────────────
# run()'s material/benign classification (FROZEN SPEC Part B). Before this fix
# run() called annotate_live_strip and discarded its boolean outright, so an
# absent served target — the exact shape of the 27-day 2026-07-30→08-26 US
# Prophet Live freeze — produced the SAME silence as every benign reason to
# write nothing. These pin the caller, not the CAS mechanics (already covered
# above by the annotate_live_strip-level tests, unchanged).
# ─────────────────────────────────────────────────────────────────────────────
def _warnings(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if "::warning" in ln]


def test_run_emits_a_loud_annotation_when_the_target_is_absent(tmp_path, capsys):
    """Area 7. The served target never existing at all — literally the shape of
    the incident this fix closes."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"          # never created
    payload = _payload()
    served.write_text(json.dumps(payload))
    assert M.run(served=str(served), plv=str(plv),
                 fetch=lambda key, **kw: payload) == 0
    warn = _warnings(capsys.readouterr().out)
    assert warn, "a material failure must not stay silent"
    assert warn[0].startswith("::warning title=close-pass::")
    assert "absent" in warn[0]
    assert not plv.exists()          # still never creates the artifact


def test_run_emits_a_loud_annotation_when_the_target_is_unparseable(tmp_path, capsys):
    """Area 8. A half-written file, an error shell — malformed JSON is just as
    material as the file not existing at all."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    plv.write_text('{"states": ')                  # broken JSON
    payload = _payload()
    served.write_text(json.dumps(payload))
    assert M.run(served=str(served), plv=str(plv),
                 fetch=lambda key, **kw: payload) == 0
    warn = _warnings(capsys.readouterr().out)
    assert warn and "unparseable" in warn[0]
    assert plv.read_text() == '{"states": '        # left exactly as it is, not repaired


def test_run_emits_a_loud_annotation_when_publish_served_fails(tmp_path, monkeypatch,
                                                                capsys):
    """Area 9. The read/CAS half succeeds; the write itself fails."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    plv.write_text(json.dumps({"states": {}}))
    payload = _payload()
    served.write_text(json.dumps(payload))
    monkeypatch.setattr(M, "publish_served", lambda *a, **kw: False)
    assert M.run(served=str(served), plv=str(plv),
                 fetch=lambda key, **kw: payload) == 0
    warn = _warnings(capsys.readouterr().out)
    assert warn and "publish_served" in warn[0]


def test_run_stays_silent_when_the_strip_is_already_annotated(tmp_path, capsys):
    """Area 10. The common tick — ~40 passes a day, one write. Must never page."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    payload = _payload()
    served.write_text(json.dumps(payload))
    plv.write_text(json.dumps({"states": {}}))
    assert M.run(served=str(served), plv=str(plv), fetch=lambda key, **kw: payload) == 0
    capsys.readouterr()  # the first pass writes the key — discard its output
    assert M.run(served=str(served), plv=str(plv), fetch=lambda key, **kw: payload) == 0
    assert _warnings(capsys.readouterr().out) == []


def test_run_dry_run_never_emits_a_material_warning(tmp_path, capsys):
    """Area 11. dry-run prints its own plain notice, never a ::warning."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    payload = _payload()
    served.write_text(json.dumps(payload))
    plv.write_text(json.dumps({"states": {}}))
    assert M.run(served=str(served), plv=str(plv), dry_run=True,
                 fetch=lambda key, **kw: payload) == 0
    out = capsys.readouterr().out
    assert _warnings(out) == []
    assert "dry-run: would annotate" in out


def test_run_stays_silent_on_a_cas_skip_and_does_not_clobber(tmp_path, monkeypatch,
                                                              capsys):
    """Area 12. The concurrent-rewrite skip is CORRECT behaviour, not a failure —
    paging on it would be exactly the false-alarm factory the falsifier law
    forbids. The evaluator's fresh document must also survive untouched."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    stale = {"schema": "prophet_live.states/v1", "states": {"AAA": {"state": "forming"}}}
    plv.write_text(json.dumps(stale))
    fresh = {"schema": "prophet_live.states/v1",
             "states": {"AAA": {"state": "buyable"}}}

    real = CB.board_state
    def evaluator_wins(payload, **kw):
        plv.write_text(json.dumps(fresh))           # the evaluator's whole rewrite
        return real(payload, **kw)
    monkeypatch.setattr(M.CB, "board_state", evaluator_wins)

    payload = _payload()
    served.write_text(json.dumps(payload))
    assert M.run(served=str(served), plv=str(plv), fetch=lambda key, **kw: payload) == 0
    out = capsys.readouterr().out
    assert _warnings(out) == []
    landed = json.loads(plv.read_text())
    assert landed == fresh                # the evaluator's document, untouched
    assert M.STATE_KEY not in landed


def test_run_success_writes_board_state_and_emits_no_warning(tmp_path, capsys):
    """Area 13. The ordinary evening pass: a healthy annotate must never trip
    the material-failure path, and the write itself is unchanged."""
    served = tmp_path / "us_board_provisional.json"
    plv = tmp_path / "prophet_live.json"
    payload = _payload()
    served.write_text(json.dumps(payload))
    plv.write_text(json.dumps({"states": {}}))
    assert M.run(served=str(served), plv=str(plv), fetch=lambda key, **kw: payload) == 0
    out = capsys.readouterr().out
    assert _warnings(out) == []
    assert json.loads(plv.read_text())[M.STATE_KEY] == CB.board_state(payload)


def test_the_outcome_helper_is_the_single_source_of_truth_for_both_callers(tmp_path):
    """The classification split (Part B) reads off the SAME single read/CAS
    pass annotate_live_strip always performed — never a second read — proven
    directly against the private helper both the public wrapper and run() now
    share, and that its outcome vocabulary matches MATERIAL_ANNOTATE_OUTCOMES."""
    plv = tmp_path / "prophet_live.json"
    plv.write_text(json.dumps({"states": {}}))
    payload = _payload()

    wrote, outcome = M._annotate_live_strip_outcome(plv, payload)
    assert wrote is True and outcome == M.ANNOTATE_OUTCOME_ANNOTATED
    assert json.loads(plv.read_text())[M.STATE_KEY] == CB.board_state(payload)
    # The public wrapper agrees — same call, same file, same result.
    assert M.annotate_live_strip(plv, payload) is False   # already annotated now

    # Second pass, unchanged document: benign, no write, outcome says why.
    wrote2, outcome2 = M._annotate_live_strip_outcome(plv, payload)
    assert wrote2 is False and outcome2 == M.ANNOTATE_OUTCOME_ALREADY_ANNOTATED

    # Absent and unparseable are both MATERIAL, and distinguishably so.
    missing = tmp_path / "missing.json"
    wrote3, outcome3 = M._annotate_live_strip_outcome(missing, payload)
    assert wrote3 is False and outcome3 == M.ANNOTATE_OUTCOME_ABSENT
    broken = tmp_path / "broken.json"
    broken.write_text('{"states": ')
    wrote4, outcome4 = M._annotate_live_strip_outcome(broken, payload)
    assert wrote4 is False and outcome4 == M.ANNOTATE_OUTCOME_UNPARSEABLE
    assert M.MATERIAL_ANNOTATE_OUTCOMES == {
        M.ANNOTATE_OUTCOME_ABSENT, M.ANNOTATE_OUTCOME_UNPARSEABLE,
        M.ANNOTATE_OUTCOME_PUBLISH_FAILED,
    }


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
    # FAIL-CLOSED IS A PROPERTY OF THE SCORE, AND IT STILL HOLDS. An unmeasured
    # extension earns zero points, exactly as before; what changed is that the
    # DISPLAY leg no longer states "no room" about a name nobody measured — see
    # test_an_unmeasured_runway_ships_null_and_never_a_zero. The assertion moved
    # from the leg to the points because that is where the rule actually lives.
    unmeasured = CB.close_legs(verdict(), {"ext_z": None})
    assert unmeasured["runway"] is None
    # Scores identically to an explicit 0.0, and contributes nothing but the
    # signal leg — an unmeasured extension earns zero, never the best case.
    assert CB._points(unmeasured) == CB._points({**unmeasured, "runway": 0.0})
    assert CB._points(unmeasured) == round(
        us_board_rank.SCORE_WEIGHTS["signal"] * unmeasured["signal"], 4)


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
    ("5,35", 0, 59, {5, 35}),                                      # live-breadth
    ("*", 0, 23, set(range(24))),
    ("25", 0, 59, {25}),
])
def test_the_cron_expander_reads_every_form_in_this_repo(field, lo, hi, expected):
    assert _cron_field(field, lo, hi) == expected


def test_the_minute_avoids_the_other_crons_on_the_two_host_pool():
    """RE-MEASURED 2026-08-17 against `gh api repos/{owner}/{repo}/actions/runners`:
    plain `macstudio` is TWO live hosts — mac-builder-5 (`macstudio,parked`) and
    mac-builder-light (`macstudio,render-heavy`) — and closing-bell holds one of
    them for the whole window every weekday. So the minute is not cosmetic; it
    decides whether this lane starts or queues behind another job on the one
    remaining slot.

    SUPERSEDED MODEL, kept as the warning it earned. This test used to say the
    pool was mac-builder-1/2 "which also serve the `codex` and `theta-m1`
    labels". Those are the retired M1 host's runners, deregistered ~2026-08-15.
    `codex` now has NO live runner at all, and `theta-m1` was restored onto
    mac-builder-3 — which carries `macstudio-light`, NOT `macstudio`, so
    theta-m1 jobs no longer contend with this lane. A stale pool model is not
    cosmetic either: the same orphaned-label class froze every Prophet board
    2026-08-14→17 (research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md,
    DSC:QUEUED-JOB-HOSTAGE-HOLDS-THE-NIGHTLY-CRON-GROUP). The checked-in model
    this comment now defers to is `.github/runner-policy.yml` `label_registry`.

    Derived from the live workflow files rather than a hardcoded list, so a lane
    that later moves ONTO this minute reds here instead of silently contending.
    ``macstudio-light`` is deliberately NOT counted: it is a different single
    host (mac-builder-3) that shares no capacity with this pool.
    """
    ours = {int(c.split()[0]) for c in _crons()}
    assert ours == {25}
    #: Labels that route onto a runner ALSO carrying `macstudio` — i.e. whose
    #: jobs consume a slot this lane could otherwise have. EXACT match, never
    #: substring: `macstudio-light` is a different host (mac-builder-3) and
    #: matching it would flag lanes that share no capacity at all.
    #: `render-heavy` → mac-builder-light and `parked` → mac-builder-5 are both
    #: macstudio-carrying hosts; neither is on a cron today, so both are inert
    #: now and load-bearing the moment one is.
    POOL = {"macstudio", "render-heavy", "parked"}
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


def test_the_receipt_is_graded_inside_the_nightly_not_after_it():
    """This lane publishes the EVENING board and nothing else.

    It used to carry a second `reconcile` job on `workflow_run: [daily]
    completed`. That trigger is off the nightly's critical path — and also,
    unavoidably, after the nightly RENDER, which is the receipt's only consumer.
    The receipt for session N therefore could not exist until session N's page
    had already shipped without it, so the surface (#5148) sat wired and
    permanently dark, and any future reader of the published key would have
    printed session N-1's arithmetic under session N's cards.

    The grading now runs inside daily.yml's engine job, after the board of
    record is built. Two lanes writing one receipt key on two different clocks
    is exactly the disagreement "no receipt is better than a wrong one" exists
    to prevent, so the old job is DELETED rather than left armed.
    """
    assert set(WORKFLOW["jobs"]) == {"publish"}
    assert "workflow_run" not in WORKFLOW[True]  # yaml parses bare `on:` as True
    assert "workflow_run" not in WORKFLOW_SRC.split("jobs:")[1]

    daily_src = resolved_workflow_text(
        ROOT / ".github" / "workflows" / "daily.yml", ROOT)
    engine = daily_src.split("\n  engine:\n", 1)[1]
    assert "python -m scripts.close_pass_reconcile" in engine

    # ORDER IS THE WHOLE POINT: the board of record does not exist on disk until
    # build_site has run (it calls build_stock_library, which writes
    # us_standouts.json), so a reconcile placed ahead of it would grade LAST
    # night's board and — by its own session check — publish nothing, forever.
    build = engine.index("run_py \"regime engine")
    assert build < engine.index("python -m scripts.close_pass_reconcile")


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
    # Assert the lane is inside the `systemctl enable --now` batch, NOT that its
    # line happens to be the one carrying the trailing `>/dev/null`. The original
    # assertion pinned that redirect, which only ever sat on the LAST timer in the
    # batch, so it silently broke the moment macro-live-breadth.timer was appended
    # after closepass — testing list order, not the arming it means to guarantee.
    enable_block = LIVE_SETUP.split("systemctl enable --now", 1)[1].split("\n\n", 1)[0]
    assert "macro-live-closepass.timer" in enable_block


# ─────────────────────────────────────────────────────────────────────────────
# THE CLOCK SWAP (Breathing PR-B, 2026-08-15)
#
# The workflow above is no longer the product clock; `com.macro.closepass` on the
# Mac Studio is. Measured Friday 2026-08-14 on this very lane: the 20:25 UTC line's
# run was CREATED at 20:52 (27 min of scheduler drift), its DST sibling at 21:47
# then sat 95 minutes in the queue, and the board published ~19:20 ET against a
# 16:15 ET product target. Estate-wide the instrument measures worse — cron gaps of
# 90 min to 3h12m, agentos/decisions/DEC-LER-LIVE-LANE-VPS-5MIN-REST.md.
#
# Everything above this line still holds: the schedule, both DST regimes, the pool
# measurement and the minute choice are UNCHANGED and still pinned. What is added
# here is the demotion contract — stand down when the primary landed, fail open on
# every failure, and say so out loud when the backstop had to publish.
# ─────────────────────────────────────────────────────────────────────────────
import os                                                        # noqa: E402
import platform                                                  # noqa: E402
import plistlib                                                  # noqa: E402
import subprocess                                                # noqa: E402
import textwrap                                                  # noqa: E402

PLIST = ROOT / "ops" / "launchd" / "com.macro.closepass.plist"
INSTALLER = ROOT / "scripts" / "install_closepass_launchd.sh"
HOST_RUNNER = ROOT / "scripts" / "close_pass_host_runner.py"

STEPS = WORKFLOW["jobs"]["publish"]["steps"]
GUARD = "steps.standdown.outputs.stand_down != '1'"


def _step_index(needle: str) -> int:
    for i, step in enumerate(STEPS):
        if needle in (step.get("name") or ""):
            return i
    raise AssertionError(f"no step named ~{needle!r}: "
                         f"{[s.get('name') for s in STEPS]}")


def test_the_fast_exit_runs_before_anything_it_could_save():
    """The stand-down is worth ~20 minutes of a two-host pool, and only if it
    happens BEFORE the venv, the pip install and the price-store heal. A check
    placed after them saves nothing and is therefore not a backstop discipline,
    just a log line."""
    fast = _step_index("backstop fast-exit")
    assert fast == 1, [s.get("name") or s.get("uses") for s in STEPS]
    assert STEPS[0]["uses"].startswith("actions/checkout")   # sys.path needs it
    assert STEPS[fast]["id"] == "standdown"
    assert fast < _step_index("python 3.12")
    assert fast < _step_index("freshness prefetch")
    assert fast < _step_index("publish the provisional board")


def test_every_step_after_the_fast_exit_is_guarded_by_it():
    """GitHub has no early-exit, so "stand down" can only mean "every later step
    is skipped". One unguarded step and the job still spends the pool."""
    for step in STEPS[2:]:
        assert step.get("if") == GUARD, step.get("name") or step.get("run")


def test_the_fast_exit_fails_open_structurally_not_by_promise():
    """`continue-on-error` is the load-bearing half. A step that dies outright
    leaves its outputs EMPTY, which is `!= '1'`, which PROCEEDS — so a broken
    stand-down check can never stand the backstop down. The in-script fail-open
    paths are the belt; this is the braces."""
    assert STEPS[_step_index("backstop fast-exit")]["continue-on-error"] is True
    body = STEPS[_step_index("backstop fast-exit")]["run"]
    assert "stand_down=0" in body
    assert "fail-open" in body
    # Keyless: the cheap check must not need the secrets the expensive step does.
    assert "secrets." not in body
    assert "curl -fsS" in body and "|| : >" in body
    # The session is computed with the SAME discipline as the pass, from the
    # same module — not a second definition of "when is the market open".
    assert "from lib.nyse_calendar import ET, is_session" in body
    # Comment lines stripped for the same reason CODE exists at the top of this
    # file: the step's own comment NAMES the call it deliberately does not make,
    # and deleting that sentence to satisfy a grep would make the step worse.
    live = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
    assert "expected_last_session" not in live


def _run_fast_exit(tmp_path, *, board, is_session_returns: bool,
                   public_base="") -> dict:
    """Execute the REAL step body, hermetically.

    Not a paraphrase of it: the body is read out of the workflow and run by
    bash, because the two defects this step can have are both shell-level. One
    already happened here — `printf … | python3 - <<'PY'` looks like it pipes
    the board in, and does not: the heredoc IS stdin, so the piped body was
    silently discarded and the check read every board as unreadable. A test that
    re-implemented the logic in Python would have passed on that.

    `lib.nyse_calendar` is stubbed in the sandbox cwd (the step does
    `sys.path.insert(0, ".")`) so the outcome never depends on today's date.
    """
    (tmp_path / "lib").mkdir(exist_ok=True)
    (tmp_path / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "lib" / "nyse_calendar.py").write_text(textwrap.dedent(f"""
        from datetime import timedelta, timezone
        ET = timezone(timedelta(hours=-4))          # fixed: no DST arithmetic here
        def is_session(d):
            return {is_session_returns!r}
    """), encoding="utf-8")

    base_dir = tmp_path / "mirror"
    (base_dir / "live_flow").mkdir(parents=True, exist_ok=True)
    if board is not None:
        (base_dir / "live_flow" / "us_board_provisional.json").write_text(
            board, encoding="utf-8")
    if public_base == "":
        public_base = f"file://{base_dir}"
    config = "" if public_base is None else (
        f'r2_data_plane:\n  public_base: "{public_base}"\n  anchors: [live_flow]\n')
    (tmp_path / "config.yml").write_text(f"other: 1\n{config}", encoding="utf-8")

    out_file = tmp_path / "gh_output.txt"
    out_file.write_text("", encoding="utf-8")
    env = dict(os.environ, GITHUB_OUTPUT=str(out_file), RUNNER_TEMP=str(tmp_path))
    proc = subprocess.run(
        ["bash", "-e", "-c", STEPS[_step_index("backstop fast-exit")]["run"]],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    parsed = dict(line.split("=", 1) for line in
                  out_file.read_text(encoding="utf-8").splitlines() if "=" in line)
    parsed["_rc"] = str(proc.returncode)
    parsed["_stdout"] = proc.stdout
    return parsed


def _stub_session() -> str:
    """Today's date in the stub's fixed ET, as the step will compute it."""
    from datetime import timedelta
    return datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=-4))).date().isoformat()


def test_the_backstop_stands_down_when_the_primary_already_landed(tmp_path):
    before = _stub_session()
    got = _run_fast_exit(tmp_path, board=json.dumps({"as_of": before}),
                         is_session_returns=True)
    if before != _stub_session():
        pytest.skip("the ET date rolled mid-test")
    assert got["stand_down"] == "1", got
    assert "primary already landed" in got["reason"]
    assert "backstop standing down" in got["_stdout"]
    assert got["_stdout"].startswith("::notice title=close-pass::")


def test_a_stale_published_board_does_NOT_stand_the_backstop_down(tmp_path):
    """The whole point. Yesterday's board on the mirror means the primary did
    not fire today, which is precisely when the backstop has to run."""
    got = _run_fast_exit(tmp_path, board=json.dumps({"as_of": "1999-01-04"}),
                         is_session_returns=True)
    assert got["stand_down"] == "0", got
    assert "1999-01-04" in got["reason"]


@pytest.mark.parametrize("board,base,why", [
    (None, "", "an unreadable public mirror"),
    ("not json at all", "", "an unparseable board"),
    ("", None, "an unreadable config.yml"),
])
def test_every_failure_path_proceeds(tmp_path, board, base, why):
    """A backstop that stands itself down on its own failure is not a backstop.
    The pass's own dedup is the second net underneath: republishing a session
    that is already up is a no-op notice, not a fault."""
    got = _run_fast_exit(tmp_path, board=board, is_session_returns=True,
                         public_base=base)
    assert got["stand_down"] == "0", f"{why}: {got}"
    assert got["_rc"] == "0", got


def test_a_non_session_day_stands_the_backstop_down_too(tmp_path):
    """Not a session means the pass would no-op anyway, so this saves the whole
    job on the ~9 full-day closures a year. It is a POSITIVE reading, which is
    the only kind allowed to stand this lane down."""
    got = _run_fast_exit(tmp_path, board=None, is_session_returns=False)
    assert got["stand_down"] == "1"
    assert "not a NYSE session day" in got["reason"]


def test_a_backstop_publish_announces_itself():
    """A backstop that publishes silently is indistinguishable from a primary
    that is working — and a primary that quietly stopped firing leaves no other
    trace at all. So the swap is announced as a ::warning, and the harmless
    shape (the pass deduped seconds after the fast-exit read) is a ::notice
    rather than a second cry of wolf."""
    step = STEPS[_step_index("announce a backstop publish")]
    assert step["if"] == GUARD
    assert _step_index("announce a backstop publish") > \
        _step_index("publish the provisional board")
    body = step["run"]
    assert "::warning title=close-pass::BACKSTOP publish" in body
    assert "the host-native primary missed this session" in body
    assert "board already published" in body            # the publisher's dedup line
    # And the annotation starts its line — echo, not a logger, per the house law.
    for line in body.splitlines():
        stripped = line.strip()
        if "::warning" in stripped or "::notice" in stripped:
            assert stripped.startswith('echo "::'), stripped

    # The dedup line it greps for is the publisher's REAL wording, not a guess.
    assert "already published" in PUBLISH_SRC


def test_the_publish_step_cannot_go_green_through_the_tee():
    """`| tee` makes the pipeline's status tee's, so a failed pass would ship as
    a green step and the announcement would fire on nothing. pipefail is the fix
    and it is asserted rather than trusted (memory: a pipe swallows a nonzero
    exit in chained ship commands)."""
    body = STEPS[_step_index("publish the provisional board")]["run"]
    assert "set -o pipefail" in body
    assert "| tee" in body
    assert body.index("set -o pipefail") < body.index("| tee")


def test_the_header_names_the_primary_and_keeps_the_old_reasoning():
    """The demotion is documented where the next reader of this file will be: at
    the top of it. And the paragraphs that made the schedule what it is stay —
    they are still correct, they now describe a rescue lane."""
    head = WORKFLOW_SRC.split("\non:", 1)[0]
    assert "com.macro.closepass" in head
    assert "close_pass_host_runner.py" in head
    assert "BOUNDED BACKSTOP" in head
    assert "20:52" in head and "95 minutes" in head        # the measurement
    assert "DEC-LER-LIVE-LANE-VPS-5MIN-REST" in head
    # Still the only definition of the window in this file — re-measured
    # 2026-08-17 (label registry: .github/runner-policy.yml label_registry),
    # not rewritten.
    assert "MEASURED POOL CAPACITY (2026-08-09, pool re-measured 2026-08-17)" in WORKFLOW_SRC
    assert "SCHEDULE — DST pair, one window" in WORKFLOW_SRC


# ─────────────────────────────────────────────────────────────────────────────
# The primary clock's host wiring
# ─────────────────────────────────────────────────────────────────────────────
def _plist() -> dict:
    return plistlib.loads(PLIST.read_bytes())


@pytest.mark.skipif(platform.system() != "Darwin", reason="plutil is macOS-only")
def test_the_plist_is_a_valid_property_list():
    """launchd rejects a malformed plist with a log line nobody reads, so the
    lane would simply never fire. `plutil -lint` is the same check the installer
    runs before bootstrapping."""
    proc = subprocess.run(["plutil", "-lint", str(PLIST)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_schedule_is_thirteen_hundred_pacific_on_weekdays():
    """13:00 PT is 16:00 ET in BOTH DST regimes, because PT and ET flip on the
    same instant and the offset between them is a constant -3h:

        PDT (Mar-Nov)  13:00 PT = 20:00 UTC = 16:00 EDT
        PST (Nov-Mar)  13:00 PT = 21:00 UTC = 16:00 EST

    That is why a LOCAL calendar entry needs no DST pair while the UTC cron
    above does — and why there is no off-season line here to self-skip."""
    entries = _plist()["StartCalendarInterval"]
    assert len(entries) == 5
    assert sorted(e["Weekday"] for e in entries) == [1, 2, 3, 4, 5]
    assert {e["Hour"] for e in entries} == {13}
    assert {e["Minute"] for e in entries} == {0}
    # The arithmetic above, computed rather than asserted in prose.
    from zoneinfo import ZoneInfo
    pt, et = ZoneInfo("America/Los_Angeles"), ZoneInfo("America/New_York")
    for day in (datetime(2026, 8, 14), datetime(2026, 12, 14)):     # EDT then EST
        local = day.replace(hour=13, tzinfo=pt)
        assert local.astimezone(et).hour == 16, day
        assert local.astimezone(timezone.utc).hour in (20, 21), day


def test_the_plist_carries_no_secret_and_no_repo_exec_path():
    """Two host facts, both learned the hard way:

    A plist is world-readable, so the R2 credentials stay in the primary's
    chmod-600 .env and the runner sources them into the subprocess environment.

    launchd cannot exec out of ~/Documents at all (the wall
    ops/launchd/com.macro.chainheat.plist documents), so the runner is COPIED to
    Application Support at install time and the plist points there."""
    plist = _plist()
    body = PLIST.read_text(encoding="utf-8")
    for secret in ("R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "MASSIVE_API_KEY",
                   "R2_ENDPOINT"):
        assert secret not in body, secret
    assert plist["EnvironmentVariables"] == {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"}
    argv = plist["ProgramArguments"]
    assert argv[0] == "/usr/bin/python3"
    assert argv[1] == "__SUPPORT_DIR__/close_pass_host_runner.py"
    assert "Documents" not in argv[1]
    # Bootstrapping the agent at 11:00 must not fire a close pass at 11:00.
    assert plist["RunAtLoad"] is False
    assert plist["Label"] == "com.macro.closepass"


def test_the_installer_is_syntactically_valid_and_operator_run():
    """It is never run by a session. Arming a scheduled publisher on a host is
    an operator act — ordering the design (Chairman directive 2026-08-15) is a
    different act from arming the host, and the installer says so."""
    proc = subprocess.run(["bash", "-n", str(INSTALLER)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    body = INSTALLER.read_text(encoding="utf-8")
    assert "OPERATOR-RUN" in body
    assert "NOTHING INSTALLS THIS AUTOMATICALLY" in body
    assert "set -euo pipefail" in body
    # The prophet-rescue idiom, verbatim-adapted: template + sed, bootout then
    # bootstrap, a kickstart hint, and the one-time TCC grant.
    for expected in ("launchctl bootout", "launchctl bootstrap",
                     "launchctl kickstart", "plutil -lint",
                     # The TCC note is carried verbatim-adapted from
                     # install_prophet_rescue_launchd.sh, where it wraps across
                     # three echo lines — hence "Full Disk" rather than the
                     # whole phrase.
                     "NOTE (macOS TCC)", "Privacy & Security", "Full Disk",
                     "/usr/bin/python3",
                     "Library/Application Support/macro-closepass",
                     "Library/Logs/macro_closepass", "worktree remove"):
        assert expected in body, expected
    # It reports on the .env; it never reads a value out of it.
    assert "stat -f" in body
    assert "cat " not in body and "grep " not in body


def test_the_installed_runner_is_plumbing_and_the_lane_is_the_policy():
    """The copy under Application Support is frozen at install time — which is
    fine, and is the same contract scripts/prophet_rescue_launchd.py carries:
    the wrapper is plumbing, the POLICY it launches always comes from
    origin/main."""
    runner = HOST_RUNNER.read_text(encoding="utf-8").replace("'", '"')
    assert '"reset", "--hard", "origin/main"' in runner
    assert "bootstrap" in runner and "code_sha" in runner
    assert "re-run this installer" in INSTALLER.read_text(encoding="utf-8").lower()


def test_the_freeze_is_disclosed_every_run_because_merging_deploys_nothing():
    """THE COST OF THE FREEZE IS PAID BY THE RECEIPT, not by a self-update.

    Freezing the snapshot at install time is correct — a mid-day push to main
    must not change what the clock executes mid-session — but it means a merged
    fix is not a deployed fix, and on 2026-08-18 that gap was invisible in every
    instrument the estate owns: PR #5862 merged as af416e4a1066 while the host
    kept running the Aug-15 bytes, and its receipts read perfectly because
    `code_sha` (the lane's HEAD) is reset to origin/main every single run.

    So the runner GRADES its own executing bytes against origin/main's copy and
    says so out loud, the report fails on it, and the installer still owns the
    only act that deploys the file.
    """
    runner = HOST_RUNNER.read_text(encoding="utf-8")
    # It reads origin/main's copy of ITSELF out of the lane the reset just made.
    assert "compare_bootstrap_to_main" in runner and "RUNNER_REPO_REL" in runner
    # ...and the finding carries the only remedy there is.
    assert "bash scripts/install_closepass_launchd.sh" in runner
    assert "::error" in runner.replace("f\"", "\"")
    # The report is the second instrument, off the launchd log entirely.
    report = (ROOT / "scripts" / "close_pass_slo_report.py").read_text(encoding="utf-8")
    assert "bootstrap_verdict" in report and "install_closepass_launchd.sh" in report

    installer = INSTALLER.read_text(encoding="utf-8")
    # THE FREEZE ITSELF IS UNCHANGED: exactly one copy of the runner into the
    # support dir, at install time, by the operator. Nothing else may deploy it.
    assert installer.count('cp "$REPO_SRC/scripts/close_pass_host_runner.py"') == 1
    assert "shasum -a 256" in installer          # says what the install moved


def test_the_primary_and_the_backstop_publish_the_same_artifact_the_same_way():
    """One board, one key, one mirror. The host lane forces the same R2-only
    contract the workflow sets in its publish step, so whichever clock fires,
    app/deploy/macro-live-closepass pulls the identical object."""
    runner = HOST_RUNNER.read_text(encoding="utf-8")
    assert 'env["CLOSE_PASS_SERVED_PATH"] = ""' in runner
    assert 'env["RENDER_NO_DRIP"] = "1"' in runner
    assert 'env.pop("COLLECT_LANE", None)' in runner
    assert "scripts.close_pass_publish" in runner
    publish = STEPS[_step_index("publish the provisional board")]
    assert publish["env"]["CLOSE_PASS_SERVED_PATH"] == ""
    assert WORKFLOW["jobs"]["publish"]["env"]["RENDER_NO_DRIP"] == "1"
    # ...and the host lane never NAMES the served path in code — it belongs to
    # the VPS. Docstrings stripped (_code) because the runner's own explanation
    # of why it does not write there necessarily says where "there" is.
    assert "/var/lib/macro-live" not in _code(runner)
