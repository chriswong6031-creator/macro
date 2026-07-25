"""tests/test_transmission_publish.py — TXI W4 site-publication adapter (deliverable A).

engine.transmission_publish.derive_display_subset() projects the canonical
transmission_chains.v1 artifact into the site/transmission_chains.json display subset.
These lock:
  - the published subset schema + every field the brief names, with bilingual labels
  - blast channels keep names + numeric cuts + the unevaluable bucket (a client rebuilds
    membership client-side); a dropped/proxy channel keeps its bilingual note
  - the one-render-lag note is stamped (build_site runs before the chains step)
  - display_only=True; the word "validated" never appears
  - ABSENT / empty / malformed input degrades to an empty chains list (never raises), so
    the build_site emit publishes nothing at all
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

FIX = Path(__file__).resolve().parent / "fixtures" / "transmission" / "chain_state.json"


@pytest.fixture()
def chain_state() -> dict:
    return json.loads(FIX.read_text(encoding="utf-8"))


def _subset(cs: dict) -> dict:
    from engine.transmission_publish import derive_display_subset
    return derive_display_subset(cs)


# ---------------------------------------------------------------------------
# Schema + bilingual labels
# ---------------------------------------------------------------------------
def test_subset_top_level_shape(chain_state):
    sub = _subset(chain_state)
    assert sub["schema"] == "transmission_chains_display.v1"
    assert sub["display_only"] is True
    assert sub["asof"] == chain_state["asof"]
    # substrate_asof passes through the {min,max} stamp
    assert sub["substrate_asof"] == chain_state["substrate"]["substrate_asof"]
    # lag_note is bilingual and non-empty (build_site publishes BEFORE the chains step)
    assert sub["lag_note"]["en"] and sub["lag_note"]["zh"]
    assert isinstance(sub["chains"], list) and len(sub["chains"]) == 4


def test_chain_fields_and_bilingual_labels(chain_state):
    sub = _subset(chain_state)
    ids = {c["id"] for c in sub["chains"]}
    assert "dollar_spike_em_multinational" in ids
    for c in sub["chains"]:
        assert set(("id", "label", "state", "tier", "hops", "blast", "caveats")).issubset(c)
        assert c["label"]["en"] and c["label"]["zh"], c["id"]
        assert c["tier"] == "hypothesis"
        assert c["state"] in ("dormant", "arming", "propagating", "expressed", "failed", "expired")
        assert isinstance(c["caveats"], list) and c["caveats"]


def test_hop_subset_bilingual_and_confirmed_dates(chain_state):
    sub = _subset(chain_state)
    dollar = next(c for c in sub["chains"] if c["id"] == "dollar_spike_em_multinational")
    assert len(dollar["hops"]) == 2
    h0, h1 = dollar["hops"]
    assert h0["confirmed"] is True and h0["asof"] == "2026-07-21"
    assert h1["confirmed"] is False and h1["asof"] is None
    for h in dollar["hops"]:
        assert set(("id", "label", "confirmed", "asof")).issubset(h)
        assert h["label"]["en"] and h["label"]["zh"]
        # the machine value receipts are NOT published in the subset
        assert "value_receipt" not in h


def test_blast_channels_keep_names_cuts_unevaluable_and_notes(chain_state):
    sub = _subset(chain_state)
    dollar = next(c for c in sub["chains"] if c["id"] == "dollar_spike_em_multinational")
    proxy = dollar["blast"]["em_commodity_sector_proxy"]
    assert proxy["n"] == 163
    assert proxy["unevaluable"] == 12               # missing-field bucket always carried
    assert "NVDA" in proxy["names"]                 # full ticker array preserved
    assert proxy["label"]["en"] and proxy["label"]["zh"]
    assert proxy["note"]["en"] and proxy["note"]["zh"]  # proxy note passes through bilingual
    # a channel with a printed numeric cut keeps it (client rebuilds membership from it)
    debt = dollar["blast"]["dollar_debt_burden"]
    assert debt["cuts"].get("financials.debt_to_assets") == 0.61
    # a dropped channel (resolved:false in the source) still emits, with its note
    credit = next(c for c in sub["chains"] if c["id"] == "credit_spreads_refinancing")
    dropped = credit["blast"]["floating_rate_debt"]
    assert dropped["n"] == 0 and dropped["unevaluable"] == 1615
    assert dropped["note"]["en"].startswith("DROPPED")


def test_dormant_chain_has_empty_blast(chain_state):
    sub = _subset(chain_state)
    vol = next(c for c in sub["chains"] if c["id"] == "vol_regime_deleveraging")
    assert vol["state"] == "dormant"
    assert vol["blast"] == {}


# ---------------------------------------------------------------------------
# Banned-vocab (CI-enforced elsewhere; belt-and-suspenders here)
# ---------------------------------------------------------------------------
def test_no_validated_claim_in_subset(chain_state):
    sub = _subset(chain_state)
    blob = json.dumps(sub, ensure_ascii=False).lower()
    assert "validated" not in blob


# ---------------------------------------------------------------------------
# Fail-open — absent / empty / malformed input never raises
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad", [{}, None, {"chains": None}, {"chains": "junk"}, 42, []])
def test_degrades_on_bad_input(bad):
    sub = _subset(bad)
    assert sub["display_only"] is True
    assert sub["chains"] == []
    assert sub["schema"] == "transmission_chains_display.v1"


def test_missing_hop_label_falls_back_to_hop_id():
    """A pre-W4 chain whose hops carry no `label` still publishes a non-blank label
    (the hop id), never invented copy."""
    cs = {
        "asof": "2026-07-23", "caveats": [],
        "chains": [{
            "chain": "legacy", "title": {"en": "Legacy", "zh": "旧链"},
            "state": "arming", "tier": "hypothesis",
            "hops": [{"id": "a->b", "from": "a", "to": "b", "confirmed": True, "asof": "2026-07-20"}],
            "blast": {},
        }],
    }
    sub = _subset(cs)
    h = sub["chains"][0]["hops"][0]
    assert h["label"] == {"en": "a->b", "zh": "a->b"}


# ---------------------------------------------------------------------------
# build_site emit path: absent artifact publishes NOTHING (no file, no error)
# ---------------------------------------------------------------------------
def test_build_site_skips_when_artifact_absent(tmp_path):
    """Mirror the build_site guard: when data/transmission/chain_state.json is absent,
    no site/transmission_chains.json is written and nothing raises."""
    site = tmp_path / "site"
    site.mkdir()
    data_dir = tmp_path / "data"
    cs_path = data_dir / "transmission" / "chain_state.json"
    # replicate the exact guard used in scripts/build_site.py
    wrote = False
    try:
        if cs_path.exists():
            from engine.transmission_publish import derive_display_subset
            _cs = json.loads(cs_path.read_text(encoding="utf-8"))
            _subset = derive_display_subset(_cs)
            if _subset.get("chains"):
                (site / "transmission_chains.json").write_text(json.dumps(_subset))
                wrote = True
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"emit path raised on absent artifact: {e}")
    assert wrote is False
    assert not (site / "transmission_chains.json").exists()


def test_build_site_emit_writes_valid_json_when_present(tmp_path, chain_state):
    """With the artifact present, the emit writes parseable JSON with chains."""
    site = tmp_path / "site"; site.mkdir()
    data_dir = tmp_path / "data" / "transmission"; data_dir.mkdir(parents=True)
    (data_dir / "chain_state.json").write_text(json.dumps(chain_state), encoding="utf-8")
    from engine.transmission_publish import derive_display_subset
    cs = json.loads((data_dir / "chain_state.json").read_text(encoding="utf-8"))
    subset = derive_display_subset(cs)
    (site / "transmission_chains.json").write_text(
        json.dumps(subset, ensure_ascii=False), encoding="utf-8")
    reloaded = json.loads((site / "transmission_chains.json").read_text(encoding="utf-8"))
    assert reloaded["schema"] == "transmission_chains_display.v1"
    assert len(reloaded["chains"]) == 4
