"""The China Special Situations tier gate — the split IS the boundary.

Sibling of tests/test_special_situations_gate.py, same two layers:

* the SPLIT LOGIC is proven hermetically (fake rows, real templates + the real
  builder split), so the contract holds even before a render lane has rebaked
  the desk;
* the SHIPPED BYTES are then checked against the same invariant — no named row
  that the paid payload carries may also sit in the free shell.

The second layer skips (loudly) until the desk has been rebaked in the gated
shape, because the baked page on main lags a template change by one render.

The line this desk draws is different from the US one and is worth stating: Free
keeps the whole OVERHANG READ (every plane's state, glance line, status chip and
count) plus a preview slice of the two newest-first queues; the NAMES behind it
are Insider+. See docs/TIER_PREVIEW_PATTERN.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "site" / "china_special_situations.html"
PAYLOAD = ROOT / "site" / "premiumdata" / "china_special_situations.json"
PAGE = "/china_special_situations.html"
SNAPSHOT = "/chinaspecialdata/special.json"

# Every named row on this desk, whatever its plane, wears the ticker pill.
TICKER_RE = re.compile(r'<span class="ssx-tkr"[^>]*>([^<]+)</span>')

# The pill is not the row's IDENTITY, though: a name can hold several distinct
# situations, within one plane or across planes (301308.SZ and 002368.SZ each
# carried two locked rows on 2026-07-25). A ticker seen on both sides of the wall
# is not a leak — a shared ROW is. Card planes open a row with a ssx-row div,
# table planes with a tr; header rows carry <th> and are not situations.
ROW_SPLIT_RE = re.compile(r'<div class="ssx-row">|<tr\b[^>]*>')


def _row_keys(html: str) -> list[str]:
    """Whitespace-normalised identity of every named row in `html`."""
    keys = []
    for chunk in ROW_SPLIT_RE.split(html)[1:]:
        if "<th" in chunk.split("</tr>")[0]:
            continue                        # table header, not a situation
        key = " ".join(chunk.split())
        if "ssx-tkr" in key:                # only named rows are paid content
            keys.append(key)
    return keys


def _env():
    from jinja2 import Environment, FileSystemLoader

    # autoescape=False mirrors scripts/build_china_special_situations.py exactly —
    # this page's t()/tw() macros assume it.
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    env.globals.update(td=lambda en: en, tr=lambda en: en,
                       t=lambda en, zh=None: en)
    return env


# ------------------------------------------------------------------ fixtures


def _unlock(tkr: str, days: int) -> dict:
    return {"ticker": tkr, "name": f"{tkr} Co", "note": {"en": f"{tkr} unlock", "zh": "解禁"},
            "large_flag": True, "lock_type": "限售", "float_pct": 7.5,
            "unlock_date": "2026-08-01", "days_to": days}


def _letter(code: str, day: int) -> dict:
    return {"secCode": code, "secName": f"{code} Co", "has_reply": False,
            "note": {"en": f"{code} was asked", "zh": "问询"}, "title": "问询函",
            "pdf_url": "/x.pdf", "date": f"2026-07-{day:02d}"}


def _named(tkr: str) -> dict:
    """A row shape that satisfies every ranked board on the desk."""
    return {"ticker": tkr, "name": f"{tkr} Co", "plan_amt_yi": 12.0, "done_amt_yi": 6.0,
            "progress": "实施中", "pledge_ratio": 61.0, "pledge_mktcap_yi": 30.0,
            "type": "预增", "pct_change": 42.0, "quarter": "2026Q2", "pct_chg": 3.1,
            "avg_premium_pct": 4.2, "block_amt_yi": 1.5, "n_blocks": 3,
            "last_date": "2026-07-24"}


def _snapshot(n_unlock: int = 6, n_letter: int = 6, n_board: int = 4) -> dict:
    ok = {"asof": "2026-07-25", "status": "ok",
          "glance": {"level": "active", "en": "some", "zh": "一些"}}
    return {
        "schema": "china_special_sits.v1", "asof": "2026-07-25",
        "generated_utc": "2026-07-25T00:00:00",
        "hero": {"state": "active", "n_elevated": 1, "n_active": 2, "n_planes": 7,
                 "segments": [], "notable": None, "stance": {"en": "x", "zh": "x"}},
        "unlocks": {**ok, "events": [_unlock(f"U{i}.SZ", i) for i in range(n_unlock)],
                    "weekly_strip": [], "n_events_30d": 120, "n_large": n_unlock},
        "inquiry": {**ok, "letters": [_letter(f"6004{i:02d}", 20 + i) for i in range(n_letter)],
                    "n_letters": 99, "n_replies": 3},
        "preannounce": {**ok, "by_type": {"预增": 1616},
                        "top_movers": [_named(f"M{i}.SS") for i in range(n_board)],
                        "n_total": 5312},
        "buyback": {**ok, "top": [_named(f"B{i}.SS") for i in range(n_board)], "n_active": 286},
        "pledge": {**ok, "top": [_named(f"P{i}.SS") for i in range(n_board)],
                   "n_high": 10, "quarter": "2025-12-31"},
        "st": {**ok, "count": 100, "additions": [_named(f"A{i}.SS") for i in range(n_board)],
               "removals": [], "top_current": [_named(f"S{i}.SS") for i in range(n_board)],
               "history_note": None},
        "block_trades": {**ok, "top_premium": [_named(f"K{i}.SS") for i in range(n_board)],
                         "top_discount": [_named(f"D{i}.SS") for i in range(n_board)],
                         "n_names": 382},
        "goodwill": {**ok, "annual_rows": []},
        "by_ticker": {"B0.SS": {"buyback": True}},
        "track": {"en": "tracked", "zh": "跟踪"},
        "disclaimer": "Context only", "disclaimer_zh": "仅作背景",
    }


# ---------------------------------------------------------------- policy shape


def _policy() -> dict:
    return yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())


def test_payload_prefix_is_enforced_ahead_of_the_launch_switch():
    early = _policy()["premium"]["enforced_early"]
    assert "/premiumdata/" in early["prefixes"], (
        "the paid payload lane must be gated regardless of PAYWALL_ENABLED — "
        "otherwise the desk is open to every registered account"
    )


def test_raw_snapshot_is_gated_too():
    """The page gate is theatre if the same rows stay readable as raw JSON.

    site/chinaspecialdata/special.json carries every named row plus the by_ticker
    rollup. Only server-side readers touch it (engine/china_intel_hub.py,
    scripts/build_china_altdata.py read it off disk), so gating the URL costs
    nothing and closes the direct-link leak.
    """
    early = _policy()["premium"]["enforced_early"]
    assert SNAPSHOT in early["exact"] or any(
        SNAPSHOT.startswith(p) for p in early["prefixes"])


def test_preview_shell_is_anonymously_public_not_premium():
    """The page URL must stay reachable WITHOUT a session, or there is no preview
    at all — and since W1a (research/SEO_SUPERCHARGE_MASTERPLAN_BY_FABLE.md) no
    crawl either: the registration wall 302s Googlebot, which never has a session,
    into /?signin=1. Promoted free_registered → public on 2026-08-02. Every named
    row still lives in the payload and the raw snapshot the tests above keep gated
    — this page carries state, totals and the wall, and no names.
    """
    pol = _policy()
    assert PAGE in pol["public"]["exact"]
    assert PAGE not in pol["free_registered"]["exact"], (
        "one class only — a path left in both lists serves as public while the "
        "policy file documents it as gated"
    )
    assert PAGE not in pol["deny"]["exact"]


def test_neither_payload_nor_snapshot_is_public():
    pol = _policy()
    assert "/premiumdata/" not in pol["public"]["prefixes"]
    assert not any(p.startswith("/premiumdata/") for p in pol["public"]["exact"])
    assert SNAPSHOT not in pol["public"]["exact"]
    assert not any(SNAPSHOT.startswith(p) for p in pol["public"]["prefixes"])


def test_gate_switch_and_preview_size_are_config_driven():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text())["china_special_situations"]
    assert cfg["gated"] is True
    assert isinstance(cfg["preview_rows"], int) and 1 <= cfg["preview_rows"] <= 10


# ------------------------------------------------------------- split mechanics


def test_row_partial_renders_only_the_rows_it_is_handed():
    r = _env().get_template("_china_special_situations_rows.html.j2").module
    html = str(r.unlock_rows([_unlock("AAA.SZ", 1), _unlock("BBB.SZ", 2)]))
    assert set(TICKER_RE.findall(html)) == {"AAA.SZ", "BBB.SZ"}
    assert "CCC" not in html
    assert str(r.buyback_body({"status": "ok", "top": []})) .strip() != ""   # honest empty state
    assert set(TICKER_RE.findall(str(r.pledge_body(
        {"status": "ok", "top": [_named("ZZZ.SS")]})))) == {"ZZZ.SS"}


def test_builder_split_withholds_every_named_row_beyond_the_preview():
    from scripts.build_china_special_situations import _split

    snap = _snapshot()
    shell, locked, gate = _split(snap, 3)

    assert gate["tier"] == "essential"
    assert gate["payload"] == "/premiumdata/china_special_situations.json"
    assert gate["preview"] == 3
    # 3 unlocks + 3 letters stay; all seven populated ranked boards are withheld
    assert gate["locked"] == (6 - 3) + (6 - 3) + 4 * 7
    assert shell["unlocks"]["events"] == snap["unlocks"]["events"][:3]
    assert shell["inquiry"]["letters"] == snap["inquiry"]["letters"][:3]
    for blk, key in (("preannounce", "top_movers"), ("buyback", "top"), ("pledge", "top"),
                     ("st", "top_current"), ("st", "additions"),
                     ("block_trades", "top_premium"), ("block_trades", "top_discount")):
        assert shell[blk][key] == [], f"{blk}.{key} leaked into the free shell"
    # totals survive the split — Free is short of names, never of honesty
    assert shell["unlocks"]["n_events_30d"] == 120
    assert shell["inquiry"]["n_letters"] == 99
    assert shell["buyback"]["n_active"] == 286
    assert shell["st"]["count"] == 100
    # the per-name rollup is not shipped to the shell either
    assert "by_ticker" not in shell
    # and the ORIGINAL snapshot is untouched (the payload renders from it)
    assert len(snap["buyback"]["top"]) == 4


def test_split_returns_no_gate_when_nothing_is_withheld():
    """A desk with nothing beyond the preview must not grow a wall over nothing."""
    from scripts.build_china_special_situations import _split

    snap = _snapshot(n_unlock=2, n_letter=2, n_board=0)
    shell, locked, gate = _split(snap, 3)
    assert gate is None and locked == {} and shell is snap


def test_gated_shell_omits_every_locked_row_and_shows_the_wall():
    from scripts.build_china_special_situations import _split

    snap = _snapshot()
    shell, locked, gate = _split(snap, 3)
    html = _env().get_template("china_special_situations.html.j2").render(
        special=shell, gate=gate)

    assert set(TICKER_RE.findall(html)) == {"U0.SZ", "U1.SZ", "U2.SZ",
                                            "600400", "600401", "600402"}
    # not one withheld row's identity survives anywhere in the shipped bytes
    for rows in locked.values():
        for row in rows:
            ident = row.get("ticker") or row.get("secCode")
            assert ident not in html, f"{ident} leaked into the free shell"

    # Full class attributes, never bare selector substrings: this page's own CSS
    # names every skeleton class, so `"ssx-ghrow" in html` is vacuously true.
    assert 'id="cssx-wall"' in html
    assert 'id="cssx-gnote"' in html
    assert 'class="ssx-ghrow" data-gate-ghost' in html
    assert 'class="ssx-gpill" data-gate-pill' in html
    assert 'data-gate-key="buyback_html"' in html
    assert 'data-gate-key="unlocks_html" data-gate-mode="append"' in html
    # …and the shell asks the SERVER for the rest rather than deciding locally
    assert "/premiumdata/china_special_situations.json" in html
    assert "plans.html" in html


def test_ungated_shell_keeps_every_row_and_no_wall():
    snap = _snapshot()
    html = _env().get_template("china_special_situations.html.j2").render(
        special=snap, gate=None)

    assert len(TICKER_RE.findall(html)) == 6 + 6 + 4 * 7
    assert 'id="cssx-wall"' not in html
    assert 'class="ssx-ghrow" data-gate-ghost' not in html
    assert 'class="ssx-gpill" data-gate-pill' not in html
    assert "var GATE = null" in html


def test_payload_renders_the_locked_rows_from_the_same_partial(tmp_path):
    """One source, rendered twice: the hydrated board must match the shell's idiom."""
    import scripts.build_china_special_situations as b

    snap = _snapshot()
    shell, locked, gate = b._split(snap, 3)
    env = _env()
    (tmp_path / "premiumdata").mkdir()
    orig, b._site_dir = b._site_dir, lambda: tmp_path
    try:
        b._write_premium_payload(env, gate, snap, locked)
    finally:
        b._site_dir = orig
    doc = json.loads((tmp_path / "premiumdata" / b.PAYLOAD_NAME).read_text())

    assert doc["schema"] == "tier_payload.v1"
    assert doc["gated"] is True and doc["required_tier"] == "essential"
    paid = set()
    for k, v in doc.items():
        if k.endswith("_html"):
            paid |= set(TICKER_RE.findall(v))
    assert paid == {f"U{i}.SZ" for i in (3, 4, 5)} | {f"6004{i:02d}" for i in (3, 4, 5)} | {
        f"{p}{i}.SS" for p in "MBPASKD" for i in range(4)}
    assert len(paid) == doc["locked"]


def test_ungated_build_writes_an_empty_payload(tmp_path):
    """Flipping `gated` off must not leave a stale full board at the payload URL."""
    import scripts.build_china_special_situations as b

    (tmp_path / "premiumdata").mkdir()
    orig, b._site_dir = b._site_dir, lambda: tmp_path
    try:
        b._write_premium_payload(_env(), None, _snapshot(), {})
    finally:
        b._site_dir = orig
    doc = json.loads((tmp_path / "premiumdata" / b.PAYLOAD_NAME).read_text())
    assert doc["gated"] is False
    assert not any(k.endswith("_html") for k in doc)


def test_row_identity_separates_two_situations_on_one_ticker():
    """One name can hold several situations, so only a repeated ROW is a leak."""
    pledge = ('<div class="ssx-row"><div class="rlead">'
              '<span class="ssx-tkr">301308.SZ</span></div>'
              '<div class="rbody">founders have pledged 81%</div></div>')
    buyback = ('<div class="ssx-row"><div class="rlead">'
               '<span class="ssx-tkr">301308.SZ</span></div>'
               '<div class="rbody">buyback completed</div></div>')
    assert TICKER_RE.findall(pledge) == TICKER_RE.findall(buyback) == ["301308.SZ"]
    assert not set(_row_keys(pledge)) & set(_row_keys(buyback))   # different rows
    assert set(_row_keys(pledge)) & set(_row_keys(pledge))        # a repeat IS caught


def test_row_identity_reads_table_planes_and_skips_their_headers():
    """movers/st/blocks render a table, not cards — identity must cover them."""
    table = ('<table class="ssx-t"><thead><tr><th>Name</th><th>Move</th></tr></thead>'
             '<tbody>'
             '<tr><td><span class="ssx-tkr">002368.SZ</span></td><td>+9%</td></tr>'
             '<tr><td><span class="ssx-tkr">002466.SZ</span></td><td>-4%</td></tr>'
             '</tbody></table>')
    assert len(_row_keys(table)) == 2


# ------------------------------------------------------------ shipped artifacts


def test_shipped_shell_leaks_no_paid_row():
    if not PAYLOAD.exists():
        pytest.skip("desk not yet rebaked in the gated shape "
                    "(render.yml scope=china / asia-close emits site/premiumdata/)")
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    if not payload.get("gated"):
        pytest.skip("desk is running ungated (config.yml china_special_situations.gated=false)")
    shell = SHELL.read_text(encoding="utf-8")
    locked = []
    for k, v in payload.items():
        if k.endswith("_html") and isinstance(v, str):
            locked += _row_keys(v)
    assert locked, "a gated payload with no rows is a vacuous pass"
    assert len(locked) == payload["locked"], (
        "row identities must cover every plane's rows or this check is "
        f"vacuous: keyed {len(locked)} of {payload['locked']} locked rows")
    shell_rows = _row_keys(shell)
    leaked = sorted(set(locked) & set(shell_rows))
    assert leaked == [], ("paid rows readable in the free shell: "
                          f"{[k[:120] for k in leaked[:3]]}")
    # the shell holds at most the preview slice of the two previewed queues
    assert len(shell_rows) <= payload["preview"] * 2


def test_shipped_payload_declares_the_required_tier():
    if not PAYLOAD.exists():
        pytest.skip("desk not yet rebaked in the gated shape")
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert payload["schema"] == "tier_payload.v1"
    if payload.get("gated"):
        assert payload["required_tier"] == "essential"
        assert payload["locked"] > 0
