"""<region>basketdata/baskets.json must carry the sector_pulse merge — intl / hk / canada.

engine.sector_pulse.merge_pulse_into_theme_intel() mutates theme_intel IN PLACE, adding six
keys to every theme row (pulse_heat, pulse_heat_grade, pulse_rank_delta_1d/5d/20d,
pulse_score_delta_5d). All three regional builders wrote site/<X>basketdata/baskets.json
BEFORE that merge, so the on-disk artifact froze a pre-merge theme_intel while the rendered
page — which inlines the same in-memory dict AFTER the merge — looked fine. Measured on intl
2026-08-02: 0 of the 6 pulse keys across 17 themes on disk.

The JSON is a real data product, not a render leftover: engine/conviction_accrual.py:46-48,
engine/neuralweb/brain_gateway.py:1305-1310 (Mastermind ticker grounding) and
engine/sector_legs_hk.py:98 all fetch it FROM DISK. Same defect class already fixed for US
(scripts/build_baskets.py) and China.

Covers, per market:
 - COMPLETENESS  — every theme on disk carries all six pulse keys, and the payload still has
                   the chart matrix (the write stays ahead of `chart = data.pop("chart")`).
 - AGREEMENT     — the disk artifact and the payload inlined into the rendered page are the
                   same theme_intel state; a divergence means one of them is a stale snapshot.
 - FAIL-SAFETY   — a sector_pulse crash still ships today's baskets.json (the write is an
                   unconditional top-level statement AFTER the guarded block, never inside it).
 - ORDERING PINS — the source order itself, so a refactor that moves the write back above the
                   merge fails even when the functional stubs happen to agree.

The functional tests drive the REAL main() against a throwaway config.ROOT with only the
engine boundaries stubbed; engine.sector_pulse runs for real. With an empty tmp archive the
deltas all resolve to None — the contract under test is that the KEYS are present, not their
values. sector_pulse_<region>.json is deliberately not asserted on (write_pulse may legitimately
no-op against an empty archive).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Written by engine.sector_pulse.merge_pulse_into_theme_intel onto every theme row.
_PULSE_KEYS = ("pulse_heat", "pulse_heat_grade", "pulse_rank_delta_1d",
               "pulse_rank_delta_5d", "pulse_rank_delta_20d", "pulse_score_delta_5d")

# Mirrors the `const BASKETS = … / const CHART = …` pair every baskets_*.html.j2 emits, so the
# inlined payload is parseable. Extra render vars (ignition_json, radar_json, …) are ignored.
_STUB_TEMPLATE = ("<html><head></head><body><script>\n"
                  "const BASKETS = {{ baskets_json|safe }};\n"
                  "const CHART = {{ chart_json|safe }};\n"
                  "</script></body></html>\n")

# builder module / engine module / compute entry point / region slug / artifact dir / template.
# `helpers` are builder-module functions stubbed out because they reach real parquet + ledgers;
# `refresh_inputs` (intl only) rebuilds the composite benchmark and breadth tape on disk;
# `freeze` (hk + canada only) appends the PIT freeze store.
_MARKETS = {
    "intl": {
        "module": "scripts.build_baskets_intl",
        "engine": "engine.baskets_intl",
        "compute": "compute_intl_baskets",
        "region": "intl",
        "fdir": "intlbasketdata",
        "template": "baskets_intl.html.j2",
        "page": "baskets_intl.html",
        "helpers": (),
        "refresh_inputs": True,
        "freeze": False,
    },
    "hk": {
        "module": "scripts.build_baskets_hk",
        "engine": "engine.baskets_hk",
        "compute": "compute_hk_baskets",
        "region": "hk",
        "fdir": "hkbasketdata",
        "template": "baskets_hk.html.j2",
        "page": "baskets_hk.html",
        "helpers": ("_persist_hk_levels", "_hk_ignition", "_hk_provenance",
                    "_hk_freshness", "_hk_radar"),
        "refresh_inputs": False,
        "freeze": True,
    },
    "canada": {
        "module": "scripts.build_baskets_canada",
        "engine": "engine.baskets_canada",
        "compute": "compute_canada_baskets",
        "region": "canada",
        "fdir": "canadabasketdata",
        "template": "baskets_canada.html.j2",
        "page": "baskets_canada.html",
        "helpers": ("_persist_ca_levels", "_ca_overlay", "_ca_ignition", "_ca_provenance",
                    "_ca_freshness", "_ca_radar"),
        "refresh_inputs": False,
        "freeze": True,
    },
}

_MARKET_IDS = tuple(_MARKETS)


class _InjectedFault(RuntimeError):
    """Fault injected by a test to stand in for the sector_pulse organ blowing up."""


# ---------------------------------------------------------------------------
# Synthetic engine payloads
# ---------------------------------------------------------------------------

def _synth_baskets_payload(px: str) -> dict:
    """A minimal but structurally faithful engine.baskets_<region> payload.

    Two baskets sharing 2 of 3 members, and a 60-row chart matrix so the pre-chart-pop
    assertion has something to see.
    """
    n = 60
    dates = [f"2026-05-{1 + i % 28:02d}" for i in range(n)]

    def _basket(bid, name, name_zh, symbols):
        return {"id": bid, "name": name, "name_zh": name_zh, "category": "Tech",
                "category_zh": "科技", "n_members": len(symbols),
                "members": [{"symbol": s, "name": s} for s in symbols],
                "perf": {"20d": {"ret": 0.05, "rel": 0.01}}}

    return {
        "as_of": "2026-08-01",
        "benchmark_label": "Bench", "benchmark_label_zh": "基准",
        "categories": ["Tech"], "categories_zh": ["科技"],
        "baskets": [
            _basket(f"{px}_a", "Alpha", "甲", ["AAA", "BBB", "CCC"]),
            _basket(f"{px}_b", "Beta", "乙", ["AAA", "BBB", "DDD"]),
        ],
        "chart": {"dates": dates, "bench": [100.0] * n,
                  "baskets": {f"{px}_a": [100.0] * n, f"{px}_b": [100.0] * n}},
        "story": {}, "construction": {}, "history_note": "", "note": "",
    }


def _synth_theme_intel(px: str) -> dict:
    """A fresh theme_intel dict per call — merge_pulse_into_theme_intel mutates it in place,
    so a shared module-level literal would leak pulse keys across tests."""
    return {"as_of": "2026-08-01", "themes": [
        {"id": f"{px}_a", "name": "Alpha", "score": 70, "rank": 1, "label": "dominant",
         "label_zh": "主导", "reco": "accumulate", "reco_zh": "加仓", "textures": {}},
        {"id": f"{px}_b", "name": "Beta", "score": 30, "rank": 2, "label": "fading",
         "label_zh": "退潮", "reco": "avoid", "reco_zh": "回避", "textures": {}},
    ]}


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

def _drive_full_build(market, tmp_path, monkeypatch, *, pulse_raises=False):
    """Run the REAL builder main() for `market` against a throwaway ROOT. Returns the site dir.

    Only the engine boundaries are stubbed — the regional inputs (membership.json, the
    <region>_search close caches, the benchmark stores) exist on neither a dev box nor the CI
    packs. Everything the ordering contract is about stays the module's own code: the
    sector_pulse hook, the baskets.json write, the chart pop and the render all run for real,
    so a re-order shows up here.
    """
    spec = _MARKETS[market]
    px = spec["region"]
    bmod = importlib.import_module(spec["module"])
    emod = importlib.import_module(spec["engine"])

    from engine import narrative_emergence as _e_ne
    from engine import sector_pulse as _e_sp
    from engine import theme_alerts as _e_ta
    from engine import theme_scoring as _e_ts
    from scripts import build_theme_detail as _s_btd

    (tmp_path / "templates").mkdir(parents=True, exist_ok=True)
    (tmp_path / "templates" / spec["template"]).write_text(_STUB_TEMPLATE)
    site = tmp_path / "site"
    site.mkdir(parents=True, exist_ok=True)

    # Prime lib.config's lru_cached load() off the REAL config.yml before ROOT moves, so
    # data_dir()/site_dir() resolve under tmp_path instead of raising into a fail-soft except.
    bmod.config.load()
    monkeypatch.setattr(bmod.config, "ROOT", tmp_path)

    monkeypatch.setattr(emod, spec["compute"], lambda: _synth_baskets_payload(px))
    if spec["refresh_inputs"]:
        monkeypatch.setattr(emod, "refresh_inputs", lambda: True)
    for helper in spec["helpers"]:
        monkeypatch.setattr(bmod, helper, lambda *a, **k: {})
    if spec["freeze"]:
        from engine import basket_freeze as _e_bf
        monkeypatch.setattr(_e_bf, "freeze_domain", lambda *a, **k: "test-noop")

    monkeypatch.setattr(_e_ts, "compute_theme_intel", lambda region: _synth_theme_intel(px))
    monkeypatch.setattr(_e_ta, "rebuild", lambda *a, **k: None)
    monkeypatch.setattr(_e_ne, "compute_emergence", lambda region: None)
    monkeypatch.setattr(_s_btd, "build_detail_pages", lambda *a, **k: None)

    if pulse_raises:
        def _boom(*a, **k):
            raise _InjectedFault("sector_pulse write_pulse down")
        monkeypatch.setattr(_e_sp, "write_pulse", _boom)

    assert bmod.main() == 0
    return site


def _read_baskets_json(site, market):
    return json.loads((site / _MARKETS[market]["fdir"] / "baskets.json").read_text())


def _inlined_baskets(site, market):
    """Parse the BASKETS payload back out of the rendered page."""
    html = (site / _MARKETS[market]["page"]).read_text()
    body = html.split("const BASKETS = ", 1)[1].rsplit(";\nconst CHART", 1)[0]
    return json.loads(body)


def _themes(payload):
    return (payload.get("theme_intel") or {}).get("themes") or []


# ---------------------------------------------------------------------------
# Functional — the artifact on disk
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("market", _MARKET_IDS)
def test_baskets_json_carries_pulse_keys(market, tmp_path, monkeypatch):
    """Every theme in the fetched JSON carries the six sector_pulse velocity/heat keys.

    merge_pulse_into_theme_intel setdefaults them onto theme_intel IN PLACE; a snapshot taken
    before that merge freezes them out of the artifact forever. The disk copy is what
    conviction_accrual, the brain_gateway ticker grounding and sector_legs_hk read.
    """
    site = _drive_full_build(market, tmp_path, monkeypatch)
    payload = _read_baskets_json(site, market)
    themes = _themes(payload)
    assert themes, f"[{market}] theme_intel.themes missing from baskets.json"
    for th in themes:
        missing = [k for k in _PULSE_KEYS if k not in th]
        assert not missing, (
            f"[{market}] theme {th.get('id')} lost pulse keys {missing} on the way to disk — "
            "baskets.json was written before merge_pulse_into_theme_intel()")
    # the write must stay ahead of `chart = data.pop("chart")`: disk consumers take
    # BASKETS and CHART from this one file.
    assert payload.get("chart", {}).get("dates"), (
        f"[{market}] chart matrix absent — the write slipped past the chart pop")
    ids = {b["id"] for b in payload.get("baskets") or []}
    assert ids == {f"{_MARKETS[market]['region']}_a", f"{_MARKETS[market]['region']}_b"}, \
        f"[{market}] unexpected basket ids on disk: {sorted(ids)}"


@pytest.mark.parametrize("market", _MARKET_IDS)
def test_disk_and_inlined_payloads_agree(market, tmp_path, monkeypatch):
    """The JSON on disk and the payload inlined into the rendered page are the same state.

    The page inlines the in-memory dict AFTER the pulse merge, which is exactly why the bug
    was invisible on the rendered surface. Both delivery paths must show one theme_intel.
    """
    site = _drive_full_build(market, tmp_path, monkeypatch)
    disk = _read_baskets_json(site, market)
    inline = _inlined_baskets(site, market)

    assert _themes(inline), f"[{market}] rendered page carries no theme_intel"
    assert all(k in _themes(inline)[0] for k in _PULSE_KEYS), \
        f"[{market}] the inlined payload itself lost the pulse keys"
    assert disk.get("theme_intel") == inline.get("theme_intel"), (
        f"[{market}] fetched JSON and inlined page payload disagree on theme_intel — "
        "one of the two is a stale snapshot")
    # the chart is popped before the render, so it rides the disk artifact only
    assert "chart" in disk and "chart" not in inline, \
        f"[{market}] chart matrix must be on disk and popped from the inlined payload"


@pytest.mark.parametrize("market", _MARKET_IDS)
def test_baskets_json_survives_sector_pulse_failure(market, tmp_path, monkeypatch):
    """A sector_pulse crash still ships today's artifact — just without the pulse keys.

    Pins that the write is an UNCONDITIONAL top-level statement placed AFTER the guarded
    block, not tucked inside it: whatever the pulse organ does, the page never finds a MISSING
    or stale-from-yesterday JSON. The missing pulse keys also prove the failure path really
    ran, so this is not a vacuous pass.
    """
    site = _drive_full_build(market, tmp_path, monkeypatch, pulse_raises=True)
    payload = _read_baskets_json(site, market)
    assert len(payload.get("baskets") or []) == 2, \
        f"[{market}] baskets.json lost its rows when sector_pulse failed"
    assert payload.get("chart", {}).get("dates"), \
        f"[{market}] baskets.json lost the chart matrix when sector_pulse failed"
    themes = _themes(payload)
    assert themes, f"[{market}] baskets.json lost theme_intel when sector_pulse failed"
    for th in themes:
        present = [k for k in _PULSE_KEYS if k in th]
        assert not present, (
            f"[{market}] theme {th.get('id')} carries {present} although write_pulse raised "
            "before the merge — the fault was not actually injected")


# ---------------------------------------------------------------------------
# Source-level ordering pins
#
# The functional tests above prove the payload flows through the ordering that exists. These
# pin the ORDERING ITSELF, so a later refactor that quietly moves the write back above the
# merge fails even if its own stubs happen to agree.
# ---------------------------------------------------------------------------

_WRITE_MARKER = '(fdir / "baskets.json").write_text('
_POP_MARKER = 'chart = data.pop("chart")'


def _src(market) -> str:
    return (_REPO_ROOT / (_MARKETS[market]["module"].replace(".", "/") + ".py")).read_text()


def _src_at(src, needle, market):
    i = src.find(needle)
    assert i != -1, f"[{market}] ordering marker vanished from the builder: {needle!r}"
    return i


@pytest.mark.parametrize("market", _MARKET_IDS)
def test_single_baskets_json_write(market):
    """Exactly one direct baskets.json payload write — two writes means one is a snapshot."""
    src = _src(market)
    assert src.count(_WRITE_MARKER) == 1, (
        f"[{market}] expected exactly 1 `{_WRITE_MARKER}` in the builder, "
        f"found {src.count(_WRITE_MARKER)}")


@pytest.mark.parametrize("market", _MARKET_IDS)
def test_write_is_post_pulse_merge_and_pre_chart_pop(market):
    """The write sits AFTER merge_pulse_into_theme_intel and BEFORE the chart pop."""
    src = _src(market)
    region = _MARKETS[market]["region"]
    i_merge = _src_at(src, f'_sp.merge_pulse_into_theme_intel(data["theme_intel"], "{region}")',
                      market)
    i_write = _src_at(src, _WRITE_MARKER, market)
    i_pop = _src_at(src, _POP_MARKER, market)
    assert i_merge < i_write, (
        f"[{market}] baskets.json is written before the pulse merge — the disk artifact "
        "freezes a pre-merge theme_intel and carries 0 pulse_* keys")
    assert i_write < i_pop, (
        f"[{market}] baskets.json is written after the chart pop — disk consumers lose CHART")


@pytest.mark.parametrize("market", _MARKET_IDS)
def test_write_is_unconditional_top_level(market):
    """The write is a top-level statement of main(): 4-space indent, no try/if above it.

    A sector_pulse failure is already caught by the block's own except, so keeping the write
    outside means the artifact can never go missing on an organ failure.
    """
    src = _src(market)
    i_write = _src_at(src, _WRITE_MARKER, market)
    line = src[src.rfind("\n", 0, i_write) + 1:src.find("\n", i_write)]
    assert line.startswith("    (") and not line.startswith("     "), (
        f"[{market}] the baskets.json write is nested (line: {line!r}) — it must run "
        "whatever else fails")
