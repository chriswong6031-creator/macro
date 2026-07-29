"""tests/test_prophet_live_evaluator.py — Prophet Live P0 gates G0.2, G0.3, G0.5, G0.6.

The */5 lane's job is to say one of six honest things about a name, or say nothing.
This file pins the four ways it could stop being honest:

  G0.2 LEDGER LAW      it writes no ``data/`` path and commits nothing, ever.
  G0.3 DEGRADATION     a stale pack darks the WHOLE artifact; a stale or missing
                       quote darks THAT NAME and leaves the rest live. No path
                       invents a state, and every dark carries a reason.
  G0.5 DEBOUNCE        one pass above a trigger is never a public state; two are;
                       a drop through the buffer fades; a re-cross pays two again.
  G0.6 VOCABULARY      fired / confirmed / refuted / validated / 证伪 appear nowhere
                       in the payload or the module.

EVERY TEST PINS ITS CLOCK. The ET window, the confirm cutoff and the last-completed-
session gate are all wall-clock logic, so a fixture with a bare date literal is a
scheduled red waiting for a Tuesday. ``NOW`` is passed explicitly everywhere and the
session-date fixtures are derived from it, never from ``datetime.now``.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.prophet_live import live_states as LS  # noqa: E402

#: 2026-07-29 is a Wednesday; 14:00Z is 10:00 ET, inside the window and before the
#: 15:30 confirm cutoff. Every other timestamp in this file is derived from it.
NOW = datetime(2026, 7, 29, 14, 0, tzinfo=timezone.utc)
SESSION = "2026-07-29"
#: The last COMPLETED session at NOW — what a fresh pack's as_of must equal.
LAST_SESSION = LS.last_completed_session(NOW)

CFG = LS.live_cfg({"prophet_live": {"debounce_passes": 2, "fade_buffer_pct": 0.5,
                                    "quote_max_age_min": 12,
                                    "confirm_window_start": "15:30"}})


def _at(hh: int, mm: int) -> datetime:
    """NOW's date at hh:mm ET, as UTC."""
    et = LS.et_clock(NOW).replace(hour=hh, minute=mm, second=0, microsecond=0)
    return et.astimezone(timezone.utc)


def near(trigger: float = 100.0, hi: float | None = None) -> dict:
    return {"state": "near", "center_buyable": False, "as_of_close": 95.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": True,
            "trigger_px": trigger, "fade_hi_px": hi}


def buyable(fade: float | None = 90.0, hi: float | None = 110.0) -> dict:
    return {"state": "buyable", "center_buyable": True, "as_of_close": 100.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": True,
            "fade_px": fade, "fade_hi_px": hi}


def dormant() -> dict:
    return {"state": "dormant", "center_buyable": False, "as_of_close": 50.0,
            "bar_date": LAST_SESSION, "probed": True, "buyable_in_band": False}


def pack(names: dict, as_of: str | None = None) -> dict:
    return {"schema": "prophet_live.armed/v1", "as_of": as_of or LAST_SESSION,
            "built_at": "2026-07-28T22:30:00Z", "names": names,
            "meta": {"universe_n": 1742, "probed_n": len(names), "armed_n": len(names),
                     "skipped": {"probe_cap": 1176}}}


def quotes(**px: float) -> dict:
    return {t: {"price": v, "prev_close": v, "change_pct": 0.0, "ts_ms": None,
                "source": "quotes"} for t, v in px.items()}


def _run(p, q, prev=None, *, now=NOW, age=1.0):
    return LS.evaluate(p, q, prev, now=now, cfg=CFG, quote_asof="2026-07-29T13:58:00Z",
                       delay_min=15, quote_age_of=lambda _q: age)


# ─────────────────────────────────────────────────────────────────────────────
# G0.5 — debounce
# ─────────────────────────────────────────────────────────────────────────────

def test_one_pass_above_the_trigger_is_not_a_public_state():
    art = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    st = art["states"]["AAA"]
    assert st["state"] == "near"                       # NOT forming
    assert st["internal"] == LS.CROSSING_UNCONFIRMED
    assert st["passes"] == 1
    assert st["state"] in LS.PUBLIC_STATES
    kinds = [e["kind"] for e in art["events"]]
    assert kinds == [LS.CROSSING_UNCONFIRMED]


def test_two_consecutive_passes_promote_to_forming():
    first = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    second = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.5), first)
    st = second["states"]["AAA"]
    assert st["state"] == "forming" and st["passes"] == 2 and st["entered"] == "cross"
    assert [e["kind"] for e in second["events"]] == ["forming"]
    ev = second["events"][0]
    for field in ("ticker", "kind", "ts", "price", "quote_age_min", "passes"):
        assert field in ev, field
    assert ev["from"] == "near"


def test_a_drop_through_the_buffer_fades_and_resets_the_counter():
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), a)
    assert b["states"]["AAA"]["state"] == "forming"
    # Inside the 0.5% hysteresis band: still forming, counter preserved.
    c = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.8), b)
    assert c["states"]["AAA"]["state"] == "forming" and c["states"]["AAA"]["passes"] == 2
    assert c["events"] == []
    # Through the buffer: faded, counter cleared.
    d = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.0), c)
    assert d["states"]["AAA"]["state"] == "faded" and d["states"]["AAA"]["passes"] == 0
    assert [e["kind"] for e in d["events"]] == ["faded"]


def test_a_re_cross_pays_two_fresh_passes():
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    b = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0), a)
    faded = _run(pack({"AAA": near(100.0)}), quotes(AAA=99.0), b)
    assert faded["states"]["AAA"]["state"] == "faded"
    one = _run(pack({"AAA": near(100.0)}), quotes(AAA=100.5), faded)
    assert one["states"]["AAA"]["state"] == "near"      # one pass is not enough again
    assert one["states"]["AAA"]["passes"] == 1
    two = _run(pack({"AAA": near(100.0)}), quotes(AAA=100.5), one)
    assert two["states"]["AAA"]["state"] == "forming"


def test_a_new_session_does_not_inherit_yesterdays_debounce():
    a = _run(pack({"AAA": near(100.0)}), quotes(AAA=101.0))
    tomorrow = NOW + timedelta(days=1)
    fresh = _run(pack({"AAA": near(100.0)}, as_of=LS.last_completed_session(tomorrow)),
                 quotes(AAA=101.0), a, now=tomorrow)
    assert fresh["states"]["AAA"]["passes"] == 1        # not 2
    assert fresh["states"]["AAA"]["state"] == "near"
    assert fresh["meta"]["session_et"] != a["meta"]["session_et"]


def test_above_the_upper_edge_is_not_forming():
    """The don't-chase case: past fade_hi the gate tops out, so nothing is forming."""
    a = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=120.0))
    b = _run(pack({"AAA": near(100.0, hi=105.0)}), quotes(AAA=120.0), a)
    assert b["states"]["AAA"]["state"] == "faded" or b["states"]["AAA"]["state"] == "near"
    assert b["states"]["AAA"]["state"] != "forming"


# ─────────────────────────────────────────────────────────────────────────────
# Board members
# ─────────────────────────────────────────────────────────────────────────────

def test_a_board_name_reads_forming_and_needs_no_debounce():
    art = _run(pack({"BBB": buyable()}), quotes(BBB=100.0))
    st = art["states"]["BBB"]
    assert st["state"] == "forming" and st["entered"] == "board" and st["passes"] is None


def test_a_board_name_at_its_fade_level_is_at_risk():
    art = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=89.5))
    assert art["states"]["BBB"]["state"] == "at_risk"
    assert [e["kind"] for e in art["events"]] == ["at_risk"]


def test_dormant_names_produce_no_events():
    art = _run(pack({"CCC": dormant()}), quotes(CCC=50.0))
    assert art["states"]["CCC"]["state"] == "dormant"
    assert art["events"] == []


# ─────────────────────────────────────────────────────────────────────────────
# The confirm window
# ─────────────────────────────────────────────────────────────────────────────

def test_confirming_into_close_only_from_the_cutoff_and_only_while_conditions_hold():
    early = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 0))
    assert "confirming_into_close" not in early["states"]["BBB"]
    late = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 45))
    assert late["states"]["BBB"]["confirming_into_close"] is True
    assert "confirming_into_close" in [e["kind"] for e in late["events"]]
    # Conditions no longer met => no flag, however late it is.
    broken = _run(pack({"BBB": buyable(fade=90.0)}), quotes(BBB=80.0), now=_at(15, 45))
    assert "confirming_into_close" not in broken["states"]["BBB"]


def test_the_flag_fires_once_not_on_every_later_pass():
    a = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), now=_at(15, 35))
    b = _run(pack({"BBB": buyable()}), quotes(BBB=100.0), a, now=_at(15, 40))
    assert "confirming_into_close" in [e["kind"] for e in a["events"]]
    assert "confirming_into_close" not in [e["kind"] for e in b["events"]]


# ─────────────────────────────────────────────────────────────────────────────
# G0.3 — honest degradation
# ─────────────────────────────────────────────────────────────────────────────

def test_a_stale_pack_darks_the_whole_artifact():
    """Yesterday's triggers are NEVER evaluated against today's tape."""
    old = (datetime.fromisoformat(LAST_SESSION) - timedelta(days=7)).date().isoformat()
    art = _run(pack({"AAA": near(100.0)}, as_of=old), quotes(AAA=101.0))
    assert art["status"] == "dark" and art["reason"] == "stale_pack"
    assert art["states"] == {}
    assert art["meta"]["pack_as_of"] == old
    assert art["meta"]["expected_session"] == LAST_SESSION
    assert old in art["meta"]["detail"] and LAST_SESSION in art["meta"]["detail"]


def test_a_missing_pack_darks_the_whole_artifact():
    for empty in (None, {}, {"as_of": LAST_SESSION}):
        art = _run(empty, quotes(AAA=101.0))
        assert art["status"] == "dark" and art["reason"] == "no_pack"
        assert art["states"] == {}


def test_one_stale_quote_darks_that_name_only():
    p = pack({"AAA": near(100.0), "BBB": buyable()})
    ages = {"AAA": 45.0, "BBB": 2.0}
    art = LS.evaluate(p, quotes(AAA=101.0, BBB=100.0), None, now=NOW, cfg=CFG,
                      quote_asof="x", delay_min=15,
                      quote_age_of=lambda q: ages[  # keyed off the price we set
                          "AAA" if q["price"] == 101.0 else "BBB"])
    assert art["status"] == "live"
    assert art["states"]["AAA"] == {"state": "dark", "reason": "stale_quote",
                                    "quote_age_min": 45.0}
    assert art["states"]["BBB"]["state"] == "forming"
    assert art["meta"]["dark_counts"] == {"stale_quote": 1}


def test_a_missing_quote_darks_that_name_with_a_reason():
    art = _run(pack({"AAA": near(100.0), "BBB": buyable()}), quotes(BBB=100.0))
    assert art["states"]["AAA"] == {"state": "dark", "reason": "no_quote"}
    assert art["states"]["BBB"]["state"] == "forming"
    assert art["meta"]["dark_counts"] == {"no_quote": 1}


def test_an_unknown_quote_age_is_stale_not_fresh():
    art = LS.evaluate(pack({"AAA": near(100.0)}), quotes(AAA=101.0), None, now=NOW,
                      cfg=CFG, quote_asof=None, delay_min=15, quote_age_of=lambda q: None)
    assert art["states"]["AAA"]["state"] == "dark"
    assert art["states"]["AAA"]["reason"] == "stale_quote"


def test_an_unprobed_name_is_counted_as_coverage_not_evaluated():
    """The pack never swept it, so the tape cannot settle it — and it is not "dormant"."""
    p = pack({"UNP": {"state": "dormant", "center_buyable": False, "as_of_close": 10.0,
                      "probed": False, "skip": "probe_cap"},
              "STL": {"state": "dormant", "center_buyable": False, "as_of_close": 10.0,
                      "probed": False, "skip": "stale_series"},
              "AAA": near(100.0)})
    art = _run(p, quotes(UNP=10.0, STL=10.0, AAA=101.0))
    assert "UNP" not in art["states"] and "STL" not in art["states"]
    assert set(art["states"]) == {"AAA"}
    assert art["meta"]["unprobed"] == {"probe_cap": 1, "stale_series": 1}
    assert art["meta"]["unprobed_n"] == 2
    assert art["meta"]["evaluated_n"] == 1


def test_an_irregular_gate_darks_the_name_with_its_own_reason():
    """Non-single-interval structure ships no threshold, so no state can be inferred."""
    p = pack({"IRR": {"state": "irregular", "center_buyable": True, "as_of_close": 10.0,
                      "probed": True, "buyable_in_band": None}})
    art = _run(p, quotes(IRR=10.0))
    assert art["states"]["IRR"] == {"state": "dark", "reason": "irregular_gate"}
    assert art["meta"]["dark_counts"] == {"irregular_gate": 1}


def test_every_dark_state_carries_a_reason_and_no_price():
    p = pack({"A": near(100.0), "B": buyable(), "C": dormant()})
    art = _run(p, {})                     # no quotes at all
    assert art["meta"]["dark_counts"] == {"no_quote": 3}
    for tkr, st in art["states"].items():
        assert st["state"] == "dark"
        assert st.get("reason"), tkr
        assert "price" not in st, tkr     # a dark row never carries a number


def test_the_freshness_stamp_and_delay_ride_on_every_payload():
    art = _run(pack({"BBB": buyable()}), quotes(BBB=100.0))
    m = art["meta"]
    assert m["quote_asof"] == "2026-07-29T13:58:00Z"
    assert m["delay_min"] == 15          # house delayMin convention: the VENDOR floor
    assert m["pass_ts"].endswith("Z") and m["session_et"] == SESSION
    assert m["pack_as_of"] == LAST_SESSION and m["expected_session"] == LAST_SESSION
    assert art["states"]["BBB"]["quote_age_min"] == 1.0    # measured, per name


# ─────────────────────────────────────────────────────────────────────────────
# Window + clock
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hh,mm,inside", [
    (9, 20, False), (9, 25, True), (10, 0, True), (16, 15, True),
    (16, 24, True),     # inside the cron-drift grace
    (16, 40, False), (8, 25, False), (17, 30, False)])
def test_window_is_evaluated_on_the_eastern_clock(hh, mm, inside):
    assert LS.in_window(_at(hh, mm), CFG) is inside


def test_the_window_means_the_same_thing_in_both_dst_regimes():
    """A UTC-pinned window would be an hour wrong for half the year."""
    for month in (1, 7):     # EST and EDT
        et = datetime(2026, month, 15, 10, 0, tzinfo=LS._ET)   # 10:00 ET, a weekday
        assert LS.in_window(et.astimezone(timezone.utc), CFG), month
        pre = datetime(2026, month, 15, 8, 30, tzinfo=LS._ET)
        assert not LS.in_window(pre.astimezone(timezone.utc), CFG), month


def test_weekends_stand_the_lane_down():
    sat = datetime(2026, 8, 1, 14, 0, tzinfo=timezone.utc)     # Saturday
    assert LS.et_clock(sat).weekday() == 5
    assert LS.in_window(sat, CFG) is False


def test_last_completed_session_is_the_prior_session_during_rth():
    """During RTH today's bar does not exist yet — the pack is armed on yesterday."""
    assert LS.last_completed_session(NOW) == "2026-07-28"
    # After the close-plus-settle buffer the same day counts.
    assert LS.last_completed_session(_at(18, 0)) == "2026-07-29"
    # A Monday morning reaches back over the weekend.
    monday = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)
    assert LS.last_completed_session(monday) == "2026-07-31"


# ─────────────────────────────────────────────────────────────────────────────
# G0.6 — vocabulary law
# ─────────────────────────────────────────────────────────────────────────────

#: Word-boundary matched, so the internal ``crossing_unconfirmed`` marker survives:
#: saying we have NOT confirmed something is the honest form, and it is spool-only
#: telemetry that never reaches a public ``state``. Claiming a confirmation is what
#: is banned — only the nightly build confirms anything.
FORBIDDEN_WORDS = ("fired", "confirmed", "refuted", "validated", "thesis")
FORBIDDEN_SUBSTRINGS = ("falsif", "证伪")


def test_public_states_are_the_agreed_six():
    assert LS.PUBLIC_STATES == ("dormant", "near", "forming", "faded", "at_risk", "dark")
    assert LS.CROSSING_UNCONFIRMED not in LS.PUBLIC_STATES


def test_no_forbidden_vocabulary_in_a_payload():
    p = pack({"AAA": near(100.0), "BBB": buyable(), "CCC": dormant()})
    a = _run(p, quotes(AAA=101.0, BBB=89.0, CCC=50.0), now=_at(15, 45))
    b = _run(p, quotes(AAA=101.0, BBB=89.0, CCC=50.0), a, now=_at(15, 50))
    blob = (json.dumps(a) + json.dumps(b)).lower()
    for word in FORBIDDEN_WORDS:
        assert not re.search(rf"\b{word}\b", blob), word
    for sub in FORBIDDEN_SUBSTRINGS:
        assert sub not in blob, sub
    # `confirming_into_close` is the sanctioned form — a projection window, not a verdict.
    assert "confirming_into_close" in json.dumps(a)
    assert LS.CROSSING_UNCONFIRMED in blob      # internal marker, deliberately kept


def test_no_forbidden_vocabulary_in_any_emittable_string():
    """AST sweep of the STRING LITERALS that can reach a payload.

    Docstrings and comments are excluded on purpose — the module docstring names the
    banned words precisely because it states the law. What must never carry them is a
    literal the code can emit, which is the one copy-paste away from a P1 surface.
    """
    import ast
    for rel in ("engine/prophet_live/live_states.py",
                "scripts/prophet_live_evaluator.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        # Docstring NODES, not their cleaned text: ast.get_docstring() dedents, so
        # comparing values would never match and the whole sweep would fail on the
        # module docstring that states this very law.
        docs: set[int] = set()
        for n in ast.walk(tree):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and n.body:
                first = n.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                        and isinstance(first.value.value, str):
                    docs.add(id(first.value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in docs:
                continue
            low = node.value.lower()
            for word in FORBIDDEN_WORDS:
                assert not re.search(rf"\b{word}\b", low), \
                    f"{rel}:{node.lineno} {word!r} in {node.value!r}"
            for sub in FORBIDDEN_SUBSTRINGS:
                assert sub not in low, f"{rel}:{node.lineno} {sub!r} in {node.value!r}"


# ─────────────────────────────────────────────────────────────────────────────
# G0.2 — ledger law
# ─────────────────────────────────────────────────────────────────────────────

WORKFLOW = ROOT / ".github" / "workflows" / "prophet-live.yml"


def test_the_workflow_cannot_commit_anything():
    text = WORKFLOW.read_text(encoding="utf-8")
    for banned in ("git add", "git commit", "git push", "contents: write",
                   "actions: write", "HEAD:main"):
        assert banned not in text, banned
    assert "contents: read" in text


def test_the_workflow_runs_off_the_render_pool_and_is_kill_switched():
    text = WORKFLOW.read_text(encoding="utf-8")
    runners = [ln.split("runs-on:")[1].split("#")[0].strip() for ln in text.splitlines()
               if "runs-on:" in ln]
    # ~80 runs a day on the self-hosted pool would eat the nightly's render budget.
    assert runners == ["ubuntu-latest"], runners
    assert "vars.PROPHET_LIVE_DISABLED != 'true'" in text
    assert "group: prophet-live" in text and "cancel-in-progress: false" in text


def test_the_workflow_installs_no_pandas():
    """~80 runs a day cannot pay a 40s pandas install, and nothing here needs it."""
    line = next(ln for ln in WORKFLOW.read_text(encoding="utf-8").splitlines()
                if "pip install" in ln)
    assert "pandas" not in line and "numpy" not in line
    assert "pyyaml" in line and "boto3" in line


def test_the_workflow_crons_span_both_dst_regimes():
    crons = re.findall(r'- cron: "([^"]+)"', WORKFLOW.read_text(encoding="utf-8"))
    hours: set[int] = set()
    for c in crons:
        assert c.endswith("* * 1-5"), c
        for part in c.split()[1].split(","):
            if part.startswith("*/"):
                continue
            if "-" in part:
                lo, hi = (int(x) for x in part.split("-"))
                hours.update(range(lo, hi + 1))
            else:
                hours.add(int(part))
    # 13:25Z-21:15Z covers 09:25-16:15 ET under BOTH EDT and EST.
    assert min(hours) == 13 and max(hours) == 21


def test_the_evaluator_module_imports_no_data_writer():
    """G0.2 at the AST level: no write call and no ledger/store module in the closure."""
    import ast
    banned_calls = {"to_parquet", "to_csv", "write_text", "write_bytes", "open",
                    "mkdir", "enqueue", "append_jsonl"}
    banned_modules = {"pandas", "numpy", "pyarrow",
                      "engine.grading", "engine.marketing.outbox",
                      "scripts.build_stock_library", "engine.prophet_live.armed_pack"}
    for rel in ("scripts/prophet_live_evaluator.py",
                "engine/prophet_live/live_states.py"):
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                assert name not in banned_calls, f"{rel}:{node.lineno} calls {name}()"
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name not in banned_modules, f"{rel}: imports {a.name}"
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                assert mod not in banned_modules, f"{rel}: imports from {mod}"
                for a in node.names:
                    full = f"{mod}.{a.name}"
                    assert full not in banned_modules, f"{rel}: imports {full}"
    # live_states reads the interval contract from the stdlib-only sibling, NOT from
    # armed_pack — the latter imports pandas, which this lane does not install.
    src = (ROOT / "engine" / "prophet_live" / "live_states.py").read_text(encoding="utf-8")
    assert "from engine.prophet_live.interval import interval_contains, lower_edge" in src


def test_the_evaluator_imports_with_pandas_blocked():
    """The workflow installs pyyaml+boto3 only, so the closure must survive without
    pandas. An importorskip-shaped hole here would disarm the whole file silently;
    this runs the real import in a clean interpreter with pandas/numpy/pyarrow made
    unimportable, which is what the runner actually looks like.
    """
    probe = ROOT / "tests" / "fixtures" / "prophet_live" / "import_probe.py"
    r = subprocess.run([sys.executable, str(probe)], cwd=ROOT,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "prophet-live thin import OK" in r.stdout, r.stdout + r.stderr


def test_the_evaluator_publishes_only_the_two_runtime_keys(monkeypatch, tmp_path, capsys):
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    p = pack({"AAA": near(100.0)})
    puts: list[str] = []
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json",
                        lambda key, **kw: p if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: puts.append(key) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": None,
                                      "source": "test"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))

    assert E.run(tmp_path, now=NOW, cfg={"prophet_live": {}}) == 0
    assert puts[0] == r2io.LIVE_KEY
    assert len(puts) == 2 and puts[1].startswith(r2io.EVENTS_PREFIX + "/" + SESSION + "/")
    assert puts[1].endswith(".json")
    # Nothing was created under the repo root it was handed.
    assert not (tmp_path / "data").exists()


def test_the_events_spool_is_one_object_per_pass_never_read_modify_write():
    from engine.prophet_live import r2io
    a = r2io.events_key("2026-07-29", "100005")
    b = r2io.events_key("2026-07-29", "100505")
    assert a != b
    assert a == "live_flow/prophet_live_events/2026-07-29/100005.json"


def test_an_eventless_pass_publishes_the_state_map_but_no_spool_object(monkeypatch, tmp_path):
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    puts: list[str] = []
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json",
                        lambda key, **kw: pack({"CCC": dormant()}) if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json", lambda key, payload, **kw: puts.append(key) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(CCC=50.0), "asof": None, "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))
    assert E.run(tmp_path, now=NOW, cfg={"prophet_live": {}}) == 0
    assert puts == [r2io.LIVE_KEY]


def test_out_of_window_stands_down_with_a_line_start_notice(capsys, tmp_path):
    import scripts.prophet_live_evaluator as E
    assert E.run(tmp_path, now=_at(3, 0), cfg={"prophet_live": {}}) == 0
    out = [ln for ln in capsys.readouterr().out.splitlines() if "::" in ln]
    assert out and out[0].startswith("::notice title=prophet-live::")
    assert "standing down" in out[0]


def test_a_stale_pack_annotation_is_a_bare_line_start_warning(monkeypatch, capsys, tmp_path):
    """The logger-prefix trap: ``log.warning("::warning …")`` is silently dropped."""
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    old = (datetime.fromisoformat(LAST_SESSION) - timedelta(days=7)).date().isoformat()
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        pack({"AAA": near(100.0)}, as_of=old) if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json", lambda key, payload, **kw: True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": None, "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))
    assert E.run(tmp_path, now=NOW, cfg={"prophet_live": {}}) == 0
    warn = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert warn and warn[0].startswith("::warning title=prophet-live::")
    assert "stale_pack" in warn[0]


def test_coverage_is_disclosed_every_pass(monkeypatch, tmp_path):
    import scripts.prophet_live_evaluator as E
    from engine.prophet_live import r2io

    published: list[dict] = []
    monkeypatch.setattr(E.r2io, "client", lambda: object())
    monkeypatch.setattr(E.r2io, "get_json", lambda key, **kw:
                        pack({"AAA": near(100.0)}) if key == r2io.PACK_KEY else None)
    monkeypatch.setattr(E.r2io, "put_json",
                        lambda key, payload, **kw: published.append(payload) or True)
    monkeypatch.setattr(E.LV, "load_live_quotes",
                        lambda root: {"quotes": quotes(AAA=101.0), "asof": None, "source": "t"})
    monkeypatch.setattr(E, "quote_ager", lambda live, now: (lambda q: 1.0))
    E.run(tmp_path, now=NOW, cfg={"prophet_live": {}})
    cov = published[0]["meta"]["coverage"]
    assert cov["pack_universe_n"] == 1742 and cov["unprobed_n"] == 1741
    assert cov["pack_skipped"] == {"probe_cap": 1176}


def test_config_block_defaults_resolve_from_config_yml():
    import yaml
    cfg = yaml.safe_load((ROOT / "config.yml").read_text(encoding="utf-8"))
    block = cfg["prophet_live"]
    resolved = LS.live_cfg(cfg)
    assert resolved["debounce_passes"] == block["debounce_passes"] == 2
    assert resolved["quote_max_age_min"] == block["quote_max_age_min"] == 12
    assert resolved["window_et"] == {"start": "09:25", "end": "16:15"}
    assert resolved["confirm_window_start"] == "15:30"
    # A partial override must not drop the sibling keys of a nested block.
    part = LS.live_cfg({"prophet_live": {"window_et": {"end": "16:00"}}})
    assert part["window_et"] == {"start": "09:25", "end": "16:00"}
