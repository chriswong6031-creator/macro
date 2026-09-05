"""Source-backed Intraday Flow snapshot-timing regressions.

Execute the actual template JavaScript and import the real Python engine/builder.
These tests prove snapshot consistency, not persistent first-trigger memory,
source freshness, options predictive edge, or production publication.
"""
from __future__ import annotations

import re
import itertools
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine import intraday_flow as engine
from scripts import build_intraday_flow as builder

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates" / "intraday_flow.html.j2"
STATUSES = (
    "buy_soon", "await_confluence", "watch", "bounce_wait", "buy_now", "partial",
    "hold", "extended", "wait_pullback", "topping", "exit", "avoid", "blocked",
    None, "mystery",
)
FIELDS = (
    "L1_washout_recent", "L2_reclaim", "L3_rvol_elevated", "L4_vol_durable",
    "L5_flow_bid", "L6_upturn_organ", "L7_leader_quality",
)


def _leader(status="buy_soon"):
    return {
        "ticker": "TEST", "prev_close": 60.0,
        "bb_lower_reclaim_days": 2,
        "mtf_upturn_state": "UPTURN_WATCH",
        "failed_breakout_trap": False,
        "vol_squeeze": {"coiled": True},
        "entry_signal": {"status": status, "spot": 60.0, "chase_above": 65.0},
        "options_entry": {"dealer": None},
    }


def _case(status="buy_soon", **updates):
    result = {
        "leader": _leader(status), "now": "2026-09-04T15:00:00Z",
        "quote": {"price": 62.1, "changePct": 1.0},
        "pulse": {"vwap": 63.0, "rvol_tod": 1.5, "vol_durability": 0.8, "bars_today": 3},
    }
    result.update(updates)
    return result


def _run_js(cases, page=TEMPLATE):
    node = shutil.which("node")
    assert node, "Node is required: do not treat unexecuted browser logic as a pass"
    text = page.read_text(encoding="utf-8")
    start = text.index("function _etMinutes(")
    end = text.index("function fmtNum(", start)
    code = "var WASHOUT_LB=10,RVOL_CONFIRM=1.30,DUR_MIN=.60;\n" + text[start:end]
    harness = r"""
const vm = require('vm');
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const result = input.cases.map(c => {
  const RealDate = Date;
  class FixedDate extends RealDate {
    constructor(...a) { super(...(a.length ? a : [c.now || '2026-09-04T15:00:00Z'])); }
    static now() { return new RealDate(c.now || '2026-09-04T15:00:00Z').valueOf(); }
  }
  const ctx = vm.createContext({Date:FixedDate, Intl, console});
  vm.runInContext(input.code, ctx);
  ctx.quotesStatus = c.quotesStatus || 'live';
  ctx.pulseStatus = c.pulseStatus || 'live';
  ctx.c = c;
  return vm.runInContext(`(() => {
    if (c.operation === 'timing') return classifyEntryTiming(c.status,c.price,c.chase);
    if (c.operation === 'clock') return {live:isMarketHours(),phase:sessionPhase()};
    const conf=c.conf || computeLegs(c.leader,c.quote||null,c.pulse||null,c.flow||null);
    return {conf,stance:computeStance(c.leader,c.quote||null,c.pulse||null,c.flow||null,conf)};
  })()`, ctx);
});
process.stdout.write(JSON.stringify(result));
"""
    proc = subprocess.run(
        [node, "-e", harness], input=json.dumps({"code": code, "cases": cases}),
        text=True, capture_output=True, timeout=30, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@pytest.mark.parametrize("status,expected", [
    ("buy_soon", "get_ready"), ("buy_now", "watch"), ("partial", "watch"),
    ("hold", "watch"), ("extended", "watch"), ("blocked", "stand_aside"),
    (None, "stand_aside"), ("mystery", "stand_aside"),
])
def test_template_respects_canonical_snapshot_timing(status, expected):
    out = _run_js([_case(status)])[0]["stance"]
    assert out["key"] == expected
    assert out["reason_en"] and out["reason_zh"]
    assert "timing_state" in out and "timing_reason" in out


def test_asts_recorded_shape_cannot_manufacture_washout():
    # Recorded-shape fixture, NOT a live quote or an observed HOLD/anti-chase breach.
    case = _case("bounce_wait", quote=None, pulse=None, now="2026-09-05T02:30:26Z")
    case["leader"].update(ticker="ASTS", bb_lower_reclaim_days=None,
                          drawdown_21d_pct=None, recovery_begun=None,
                          mtf_upturn_state=None, failed_breakout_trap=None)
    result = _run_js([case])[0]
    assert result["conf"]["legs"][0] is None
    assert result["stance"]["key"] == "stand_aside"


@pytest.mark.parametrize("status", ["buy_now", "buy_soon", "bounce_wait", "washout", "reclaim"])
def test_status_words_do_not_supply_precursor_evidence(status):
    c = _case(status)
    c["leader"].update(bb_lower_reclaim_days=None, drawdown_21d_pct=None, recovery_begun=None)
    assert _run_js([c])[0]["conf"]["legs"][0] is None


def test_known_trap_remains_a_blocking_quality_fact():
    c = _case("buy_now")
    c["leader"]["failed_breakout_trap"] = True
    c["pulse"]["vwap"] = 62.0
    out = _run_js([c])[0]
    assert out["conf"]["legs"][6] is False
    assert out["stance"]["key"] != "act"


@pytest.mark.parametrize("now,live,phase", [
    ("2026-09-04T13:29:00Z", False, "pre"),
    ("2026-09-04T13:30:00Z", True, "live"),
    ("2026-09-04T20:00:00Z", False, "post"),
    ("2026-09-05T15:00:00Z", False, "closed"),
    ("2026-09-06T15:00:00Z", False, "closed"),
])
def test_ordinary_session_boundaries(now, live, phase):
    # Holidays and early-close integration remain a separately disclosed requirement.
    assert _run_js([{"operation": "clock", "now": now}])[0] == {"live": live, "phase": phase}


def test_leftover_bars_do_not_make_weekend_actionable():
    c = _case("buy_now", now="2026-09-05T15:00:00Z")
    c["pulse"]["vwap"] = 62.0
    assert _run_js([c])[0]["stance"]["key"] == "watch"


@pytest.mark.parametrize("field", ["quotesStatus", "pulseStatus"])
def test_unavailable_feed_cannot_emit_action(field):
    c = _case("buy_now", **{field: "unavailable"})
    c["pulse"]["vwap"] = 62.0
    assert _run_js([c])[0]["stance"]["key"] != "act"


@pytest.mark.parametrize("status", STATUSES)
def test_boolean_leg_snapshot_parity(status):
    cases = []
    for live in (True, False):
        for values in itertools.product((False, True), repeat=7):
            c = _case(status)
            c["pulse"]["vwap"] = 62.0
            c["conf"] = {"legs": list(values), "K": sum(values)}
            if not live:
                c["now"] = "2026-09-05T15:00:00Z"
            cases.append(c)
    for c, actual in zip(cases, _run_js(cases)):
        legs = engine.ConfluenceLegs(**dict(zip(FIELDS, c["conf"]["legs"])))
        expected = engine.stance(
            legs=legs, K=legs.K, entry_status=status, current_price=62.1, chase_above=65.0,
            vwap_delta_pct=(62.1 / 62.0 - 1) * 100, price_up_on_day=True,
            squeeze_coiled=True, live_present=c["now"] == "2026-09-04T15:00:00Z",
        )
        for field in ("key", "timing_state", "timing_reason", "already_started"):
            assert actual["stance"][field] == expected[field], (status, c["conf"], field)


@pytest.mark.parametrize("bad", ["0x42", "0b1000010", "6_6", "", True, False, [], {}])
def test_numeric_guard_parity(bad):
    py = engine.classify_entry_timing(entry_status="buy_soon", current_price=bad, chase_above=65)
    js = _run_js([{"operation": "timing", "status": "buy_soon", "price": bad, "chase": 65}])[0]
    assert py == js
    assert py["state"] == "forming"


@pytest.mark.parametrize("value,expected", [(65.25, 65.25), (None, None), (True, None),
                                            (0, None), (-1, None), ("0x42", None)])
def test_builder_carries_only_valid_existing_boundary(value, expected):
    context = builder._extract_stockdata_context({"entry_signal": {
        "status": "buy_soon", "chase_above": value, "buy_zone": {"high": 99}, "atr_pct": 5,
    }})
    assert context["entry_signal"]["chase_above"] == expected


@pytest.mark.parametrize("status,expected", [("buy_soon", "get_ready"), ("hold", "watch"),
                                             ("blocked", "stand_aside")])
def test_real_nightly_caller_records_categorical_stance(monkeypatch, tmp_path, status, expected):
    rows = []
    monkeypatch.setattr(builder, "_ledger_enabled", lambda: True)
    def capture(new_rows, data_root):
        rows.extend(new_rows)
        return len(new_rows)
    # The single persistence boundary is isolated; real row formation and stance execute.
    monkeypatch.setattr(builder, "_append_ledger_rows", capture)
    builder._advance_ledger([_leader(status)], tmp_path, tmp_path, "2026-09-05T02:30:26Z")
    assert len(rows) == 1 and rows[0]["stance"] == expected
    assert isinstance(rows[0]["stance"], str)
    assert rows[0]["cum_ncp"] is None and rows[0]["rvol_tod_close"] is None


def test_complete_inline_script_is_syntactically_valid():
    node = shutil.which("node")
    assert node, "Node is required to parse the complete consumer script"
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("(function(){\n'use strict';")
    end = text.index("</script>", start)
    # Render expressions are literals in this script. Replace only those tokens;
    # every production function, including those outside the extraction, is parsed.
    script = re.sub(r"{{.*?}}", "{}", text[start:end], flags=re.S)
    proc = subprocess.run([node, "--check"], input=script, text=True,
                          capture_output=True, timeout=15, check=False)
    assert proc.returncode == 0, proc.stderr
