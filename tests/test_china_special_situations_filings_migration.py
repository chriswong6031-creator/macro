"""Tests for W4 special-sits → filings spine migration.

Three areas:
1. _inquiry_block() reads filings.parquet (category='inquiry_letter') and produces
   the SAME block shape as before (same output keys — block-shape preservation).
2. Claim dedup survives the source switch — event registered from the legacy store
   (sidecar with inq_{secCode}_{date}) is NOT re-registered when the same event
   arrives via filings.parquet (same claim key by construction).
3. bus.briefing() analogs block: present when analogs.json exists, None when absent
   (degrade-safe).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd
import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_parquet(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def _filings_row(
    sec_code: str,
    sec_name: str,
    title: str,
    publish_ts: str,
    kind: str = "letter",
    adjunct_url: str = "/x/PDF.pdf",
    announcement_type_raw: str = "问询函",
    announcement_id: str = "test-001",
) -> dict:
    """Construct a minimal filings.parquet row matching the schema from china_filings.py."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    return {
        "announcementId": announcement_id,
        "sec_code": sec_code,
        "sec_name": sec_name,
        "org_id": "",
        "title": title,
        "publish_ts": publish_ts,
        "exchange": "szse",
        "category": "inquiry_letter",
        "kind": kind,
        "announcement_type_raw": announcement_type_raw,
        "adjunct_url": adjunct_url,
        "adjunct_type": "PDF",
        "_collected_at": now,
    }


# ── 1. Block-shape preservation: filings.parquet source ──────────────────────

def test_inquiry_block_from_filings_same_shape(tmp_path, monkeypatch):
    """_inquiry_block() reading filings.parquet produces the EXACT same output keys
    as the old china_inquiry path (block-shape preservation — additive-only law).

    Required output keys: asof, status, letters, n_letters, n_replies.
    Each letter dict: secCode, secName, title, date, pdf_url, has_reply, type_name.
    NO 'kind' key on letter dicts.
    """
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    css._REGIME_HISTORY_CACHE.clear()

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    yesterday = (pd.Timestamp.today() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    rows = [
        _filings_row("000001", "平安银行", "关于问询函的回复", f"{today}T09:00:00+08:00",
                     kind="letter", announcement_id="A001"),
        _filings_row("000001", "平安银行", "关于上交所问询函的回复", f"{today}T10:00:00+08:00",
                     kind="reply", announcement_id="A002"),
        # An attachment — must be excluded from letters list
        _filings_row("000002", "万科A", "专项核查意见", f"{yesterday}T09:00:00+08:00",
                     kind="attachment", announcement_id="A003"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    inq = snap.get("inquiry") or {}

    # --- required top-level keys ---
    assert "asof" in inq
    assert "status" in inq
    assert "letters" in inq
    assert "n_letters" in inq
    assert "n_replies" in inq

    # --- counts ---
    assert inq["n_letters"] == 1    # only letter kind (not reply or attachment)
    assert inq["n_replies"] == 1    # one reply in window

    # --- letter dict shape ---
    letter = inq["letters"][0]
    for key in ("secCode", "secName", "title", "date", "pdf_url", "has_reply", "type_name"):
        assert key in letter, f"Missing key '{key}' in letter dict"
    # NO 'kind' key
    assert "kind" not in letter, "'kind' key must NOT appear in letter dicts (register_claims contract)"

    # --- values ---
    assert letter["secCode"] == "000001"
    assert letter["has_reply"] is True   # secCode 000001 has a reply
    assert letter["date"] == today       # publish_ts[:10] = today


def test_inquiry_block_from_filings_claim_keys_preserved(tmp_path, monkeypatch):
    """Claim key inq_{secCode}_{date} is identical whether reading filings or legacy.

    Proof: secCode comes from sec_code; date comes from publish_ts[:10].
    Both map to the same claim key as the legacy path.
    """
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    css._REGIME_HISTORY_CACHE.clear()

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    rows = [
        _filings_row("000099", "测试公司", "关注函", f"{today}T08:00:00+08:00",
                     kind="letter", announcement_id="KEYTEST-001"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    inq = snap.get("inquiry") or {}
    letters = inq.get("letters") or []
    assert len(letters) == 1
    letter = letters[0]

    # Reconstruct the claim key exactly as register_claims() would
    sec_code = str(letter.get("secCode") or "")
    announce_date = str(letter.get("date") or today)[:10]
    event_key = f"inq_{sec_code}_{announce_date}"

    assert event_key == f"inq_000099_{today}", (
        f"Claim key mismatch: got {event_key!r}"
    )


# ── 2. Claim dedup across source switch ──────────────────────────────────────

def test_claim_dedup_survives_source_switch(tmp_path, monkeypatch):
    """An event registered from the legacy store (sidecar entry) is NOT re-registered
    when the same event appears in filings.parquet.

    Mechanism: claim key = inq_{secCode}_{date}. Both old and new sources produce
    the same secCode (sec_code) and the same date (publish_ts[:10] == announcementTime).
    So the sidecar dedup gate fires even after the source switch.
    """
    monkeypatch.setenv("CN_LANE", "asia")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    import engine.china_special_situations as css
    import engine.qledger as ql_mod
    css._REGIME_HISTORY_CACHE.clear()

    registered_batches: list[list] = []

    def fake_make(**kw):
        return {"_claim": True, **kw}

    def fake_batch(claims, **kw):
        registered_batches.append(list(claims))
        return [{"status": "new"} for _ in claims]

    monkeypatch.setattr(ql_mod, "make_claim", fake_make)
    monkeypatch.setattr(ql_mod, "register_batch", fake_batch)

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    sec_code = "000111"

    # Pre-populate sidecar: event was registered from the LEGACY source
    sidecar_path = tmp_path / "data" / "china_special_sits" / "claims_registered.parquet"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"event_key": f"inq_{sec_code}_{today}", "first_registered": today}
    ]).to_parquet(sidecar_path, index=False)

    # Write filings.parquet with the SAME event (same secCode, same date)
    rows = [
        _filings_row(sec_code, "测试银行", "关注函", f"{today}T08:00:00+08:00",
                     kind="letter", announcement_id="DEDUP-001"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    n = css.register_claims(snap)

    assert n == 0, (
        f"Expected 0 new claims (sidecar dedup after source switch), got {n}. "
        f"registered_batches={registered_batches}"
    )


def test_claim_dedup_both_sources_fixture(tmp_path, monkeypatch):
    """Fixture: a row is present in both old and new planes → registered exactly once.

    Steps:
    1. Write same event to legacy inquiry.parquet AND filings.parquet.
    2. First run (filings source): registers the claim → sidecar written.
    3. Second run (same filings): sidecar dedup fires → 0 new claims.
    """
    monkeypatch.setenv("CN_LANE", "asia")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    import engine.china_special_situations as css
    import engine.qledger as ql_mod
    css._REGIME_HISTORY_CACHE.clear()

    total_registered = []

    def fake_make(**kw):
        return {"_claim": True, **kw}

    def fake_batch(claims, **kw):
        total_registered.extend(claims)
        return [{"status": "new"} for _ in claims]

    monkeypatch.setattr(ql_mod, "make_claim", fake_make)
    monkeypatch.setattr(ql_mod, "register_batch", fake_batch)

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    sec_code = "000222"

    # Write legacy inquiry.parquet (same event)
    _make_parquet(tmp_path / "data" / "china_inquiry" / "inquiry.parquet", [
        {"secCode": sec_code, "secName": "旧格式", "announcementTitle": "关注函",
         "announcementTime": today, "adjunctUrl": "/x/old.pdf",
         "announcementTypeName": "问询函", "kind": "letter", "asof": today},
    ])

    # Write filings.parquet (same event, new format)
    rows = [
        _filings_row(sec_code, "新格式", "关注函", f"{today}T09:00:00+08:00",
                     kind="letter", announcement_id="BOTH-001"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    # Run 1: filings source is preferred → registers 1 claim
    snap1 = css.scan()
    n1 = css.register_claims(snap1)
    assert n1 == 1, f"First run should register 1 claim, got {n1}"

    # Run 2: same filings.parquet → sidecar fires → 0 new claims
    n2 = css.register_claims(snap1)
    assert n2 == 0, f"Second run must be 0 (sidecar dedup), got {n2}"

    # Total registered across both runs: exactly 1
    assert len(total_registered) == 1


# ── 3. Fallback to legacy when filings absent ─────────────────────────────────

def test_inquiry_block_falls_back_to_legacy(tmp_path, monkeypatch):
    """When filings.parquet is absent, _inquiry_block falls back to legacy inquiry.parquet."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    css._REGIME_HISTORY_CACHE.clear()

    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    # Only legacy present — no filings.parquet
    _make_parquet(tmp_path / "data" / "china_inquiry" / "inquiry.parquet", [
        {"secCode": "888001", "secName": "旧来源", "announcementTitle": "监管函",
         "announcementTime": today, "adjunctUrl": "/x/legacy.pdf",
         "announcementTypeName": "监管函", "kind": "letter", "asof": today},
    ])

    snap = css.scan()
    inq = snap.get("inquiry") or {}
    assert inq.get("n_letters") == 1
    assert inq["letters"][0]["secCode"] == "888001"
    assert "kind" not in inq["letters"][0]


# ── 4. bus.briefing() analogs block: degrade-safe ────────────────────────────

def test_bus_analogs_block_absent(monkeypatch):
    """analogs block is None when analogs.json does not exist."""
    from engine import china_intel_bus as bus
    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    b = bus.briefing(asof="2026-07-06")
    assert "analogs" in b
    assert b["analogs"] is None


def test_bus_analogs_block_present(monkeypatch):
    """analogs block is populated when analogs.json exists with correct schema."""
    from engine import china_intel_bus as bus

    fixture = {
        "schema": "china_intel.analogs.v1",
        "as_of": "2026-07-06",
        "coverage": {"start": "2010-01-01", "end": "2026-07-06", "n_candidate_days": 3500},
        "query": {
            "date": "2026-07-06",
            "quad": "Q2",
            "quad_name": "Reflation",
            "liquidity": "expanding",
            "cycle": "mid",
            "growth_z": 0.42,
            "inflation_z": -0.18,
        },
        "analogs": [
            {"date": "2015-06-01", "distance": 0.21, "quad": "Q2", "quad_name": "Reflation",
             "liquidity": "expanding", "cycle": "mid",
             "fwd_shcomp": {"h20": 0.04, "h60": 0.07, "h120": None},
             "fwd_csi300": None},
        ],
        "fan": {
            "h20": {"p25": 0.01, "median": 0.03, "p75": 0.06, "n": 12},
            "h60": {"p25": -0.01, "median": 0.05, "p75": 0.10, "n": 12},
            "h120": {"p25": None, "median": None, "p75": None, "n": 0},
        },
        "method_note": "Euclidean nearest-neighbor on z-scored macro fingerprint.",
        "disclaimer_en": "Descriptive fan only — not a forecast.",
        "disclaimer_zh": "仅描述性分布——非预测。",
    }

    def _mock_read_json(rel: str):
        if "analogs" in rel:
            return fixture
        return None

    monkeypatch.setattr(bus, "_read_json", _mock_read_json)
    b = bus.briefing(asof="2026-07-06")

    assert b["analogs"] is not None
    an = b["analogs"]
    assert an["as_of"] == "2026-07-06"
    assert an["n_analogs"] == 1
    assert an["query"]["quad"] == "Q2"
    assert an["fan"]["h20"]["median"] == pytest.approx(0.03, abs=1e-6)
    assert an["method_note"] != ""


def test_bus_analogs_block_wrong_schema(monkeypatch):
    """analogs.json with wrong schema → block returns None (degrade-safe)."""
    from engine import china_intel_bus as bus

    fixture = {
        "schema": "china_intel.analogs.v99",  # wrong version
        "as_of": "2026-07-06",
        "query": {"quad": "Q2"},
        "fan": {},
        "analogs": [],
    }

    def _mock_read_json(rel: str):
        if "analogs" in rel:
            return fixture
        return None

    monkeypatch.setattr(bus, "_read_json", _mock_read_json)
    result = bus._analogs_block()
    assert result is None, "Wrong schema version should return None"


def test_bus_analogs_block_empty_fan(monkeypatch):
    """analogs.json with no fan → block returns None (missing required field)."""
    from engine import china_intel_bus as bus

    fixture = {
        "schema": "china_intel.analogs.v1",
        "as_of": "2026-07-06",
        "query": {"quad": "Q2"},
        # fan missing — required
        "analogs": [{"date": "2015-06-01"}],
    }

    def _mock_read_json(rel: str):
        if "analogs" in rel:
            return fixture
        return None

    monkeypatch.setattr(bus, "_read_json", _mock_read_json)
    result = bus._analogs_block()
    assert result is None, "Missing 'fan' key should return None"


def test_bus_briefing_analogs_not_in_surfaces_present(monkeypatch):
    """analogs is NOT included in surfaces_present even when non-None.

    By bus design: analogs is a degrade-safe add-on, not a primary surface.
    """
    from engine import china_intel_bus as bus

    fixture = {
        "schema": "china_intel.analogs.v1",
        "as_of": "2026-07-06",
        "coverage": {},
        "query": {"quad": "Q1", "quad_name": "Goldilocks", "liquidity": "expanding",
                  "cycle": "early", "growth_z": 0.5, "inflation_z": -0.1},
        "analogs": [{"date": "2010-06-01", "distance": 0.3, "quad": "Q1",
                     "fwd_shcomp": {"h20": 0.02, "h60": 0.05, "h120": 0.08}}],
        "fan": {"h20": {"p25": 0.01, "median": 0.03, "p75": 0.05, "n": 5},
                "h60": {"p25": 0.02, "median": 0.05, "p75": 0.09, "n": 5},
                "h120": {"p25": 0.03, "median": 0.08, "p75": 0.12, "n": 5}},
        "method_note": "test",
        "disclaimer_en": "test en",
        "disclaimer_zh": "test zh",
    }

    def _mock_read_json(rel: str):
        if "analogs" in rel:
            return fixture
        return None

    monkeypatch.setattr(bus, "_read_json", _mock_read_json)
    b = bus.briefing(asof="2026-07-06")

    assert b["analogs"] is not None
    # analogs is NOT a primary surface
    assert "analogs" not in b["surfaces_present"], (
        "analogs must NOT appear in surfaces_present per bus design"
    )


# ── 5. Template render: analogs card present/absent ──────────────────────────

def test_template_analogs_card_present(tmp_path, monkeypatch):
    """Template renders the analogs card (K4) when b.analogs is populated."""
    from jinja2 import Environment, FileSystemLoader
    from engine import china_intel_bus as bus
    from lib import config

    fixture_analogs = {
        "schema": "china_intel.analogs.v1",
        "as_of": "2026-07-06",
        "coverage": {"start": "2010-01-01", "end": "2026-07-06", "n_candidate_days": 3500},
        "query": {
            "date": "2026-07-06", "quad": "Q2", "quad_name": "Reflation",
            "liquidity": "expanding", "cycle": "mid",
            "growth_z": 0.42, "inflation_z": -0.18,
        },
        "analogs": [
            {"date": "2015-06-01", "distance": 0.21, "quad": "Q2",
             "quad_name": "Reflation", "liquidity": "expanding", "cycle": "mid",
             "fwd_shcomp": {"h20": 0.04, "h60": 0.07, "h120": None},
             "fwd_csi300": None},
        ],
        "fan": {
            "h20": {"p25": 0.01, "median": 0.03, "p75": 0.06, "n": 1},
            "h60": {"p25": -0.01, "median": 0.05, "p75": 0.10, "n": 1},
            "h120": {"p25": None, "median": None, "p75": None, "n": 0},
        },
        "method_note": "Euclidean nearest-neighbor.",
        "disclaimer_en": "Descriptive fan only.",
        "disclaimer_zh": "仅描述性分布。",
        "n_analogs": 1,
    }

    def _mock_read_json(rel: str):
        if "analogs" in rel:
            return fixture_analogs
        return None

    monkeypatch.setattr(bus, "_read_json", _mock_read_json)
    b = bus.briefing(asof="2026-07-06")
    assert b["analogs"] is not None

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:
        env.globals.update(td=lambda k, zh="": k, tr=lambda k, zh="": k,
                           t=lambda k, zh="": k)

    html = env.get_template("china_intel.html.j2").render(b=b, cmd_full=None)

    # K4 must be present
    assert "Cycle Context" in html or "周期背景" in html, \
        "Analogs card header (K4) not found in rendered HTML"
    assert "2015-06-01" in html, "Analog date not rendered"
    assert "Reflation" in html or "Q2" in html, "Query quad not rendered"


def test_template_analogs_card_absent(monkeypatch):
    """Template does NOT render the analogs card when b.analogs is None."""
    from jinja2 import Environment, FileSystemLoader
    from engine import china_intel_bus as bus
    from lib import config

    monkeypatch.setattr(bus, "_read_json", lambda rel: None)
    b = bus.briefing(asof="2026-07-06")
    assert b["analogs"] is None

    env = Environment(
        loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=False)
    try:
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:
        env.globals.update(td=lambda k, zh="": k, tr=lambda k, zh="": k,
                           t=lambda k, zh="": k)

    html = env.get_template("china_intel.html.j2").render(b=b, cmd_full=None)

    # K4 must be ABSENT when analogs is None.
    # Note: .analogs-card CSS rule appears in the <style> block regardless —
    # the guard is whether the <div class="analogs-card"> DOM element appears.
    assert '<div class="analogs-card">' not in html, \
        "analogs-card div element found even when b.analogs is None — card is not properly gated"


# ── 6. Inquiry block: empty window ───────────────────────────────────────────

def test_inquiry_block_filings_no_rows_in_window(tmp_path, monkeypatch):
    """Filings.parquet exists but all inquiry_letter rows are older than 14d → empty letters."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    css._REGIME_HISTORY_CACHE.clear()

    # Old date, outside 14d window
    old_date = "2026-01-01"
    rows = [
        _filings_row("000001", "平安银行", "关注函", f"{old_date}T09:00:00+08:00",
                     kind="letter", announcement_id="OLD-001"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    inq = snap.get("inquiry") or {}
    assert inq.get("n_letters") == 0
    assert inq.get("letters") == []


# ── 7. Filings plane: non-inquiry categories excluded ─────────────────────────

def test_inquiry_block_excludes_non_inquiry_categories(tmp_path, monkeypatch):
    """Filings rows with category != 'inquiry_letter' are excluded."""
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    css._REGIME_HISTORY_CACHE.clear()

    today = pd.Timestamp.today().strftime("%Y-%m-%d")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    rows = [
        {   # This is inquiry_letter — should appear
            "announcementId": "INQ-001",
            "sec_code": "000001", "sec_name": "平安银行", "org_id": "",
            "title": "关注函", "publish_ts": f"{today}T08:00:00+08:00",
            "exchange": "szse", "category": "inquiry_letter", "kind": "letter",
            "announcement_type_raw": "问询函", "adjunct_url": "/x.pdf",
            "adjunct_type": "PDF", "_collected_at": now,
        },
        {   # This is buyback — should NOT appear in inquiry block
            "announcementId": "BB-001",
            "sec_code": "000002", "sec_name": "万科A", "org_id": "",
            "title": "回购方案", "publish_ts": f"{today}T08:00:00+08:00",
            "exchange": "szse", "category": "buyback", "kind": None,
            "announcement_type_raw": "回购", "adjunct_url": "/y.pdf",
            "adjunct_type": "PDF", "_collected_at": now,
        },
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    inq = snap.get("inquiry") or {}
    assert inq.get("n_letters") == 1
    assert inq["letters"][0]["secCode"] == "000001"


# ── 8. 复函 reply classification — both code paths agree ──────────────────────

def test_fuhan_kind_reply_filings_path(tmp_path, monkeypatch):
    """复函 title from filings.parquet → kind='reply' → parent letter has_reply=True,
    复函 row excluded from letters display list.

    This tests the FILINGS code path: filings.parquet with a 'letter' row for stock
    000001 and a 'reply' row whose kind was derived from a 复函 title.
    Both must agree: the letter's has_reply=True, and the reply is NOT in the letters list.
    """
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    import collectors.china_filings as cf
    css._REGIME_HISTORY_CACHE.clear()

    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    # The classify_kind function must map 复函 → 'reply'
    assert cf.classify_kind("股票交易异常波动问询函的复函-郁敏珺") == "reply", \
        "classify_kind must return 'reply' for 复函 title"

    rows = [
        # The exchange-issued letter
        _filings_row("000001", "平安银行", "关于股票交易异常波动的问询函",
                     f"{today}T09:00:00+08:00", kind="letter", announcement_id="LTR-001"),
        # The company's 复函 reply (kind should be 'reply' from classify_kind)
        _filings_row("000001", "平安银行", "股票交易异常波动问询函的复函-郁敏珺",
                     f"{today}T15:00:00+08:00", kind="reply", announcement_id="REP-001"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    inq = snap.get("inquiry") or {}

    # Only the letter appears in the display list; the reply does NOT
    assert inq.get("n_letters") == 1, f"Expected 1 letter, got {inq.get('n_letters')}"
    assert inq.get("n_replies") == 1, f"Expected 1 reply count, got {inq.get('n_replies')}"

    letter = inq["letters"][0]
    assert letter["secCode"] == "000001"
    assert letter["has_reply"] is True, "Letter must show has_reply=True when a 复函 reply exists"
    # The reply row must NOT appear in the letters list
    for ltr in inq["letters"]:
        assert "复函" not in ltr.get("title", ""), \
            "复函 reply title must NOT appear in the letters display list"


def test_fuhan_kind_reply_legacy_path(tmp_path, monkeypatch):
    """复函 reply via the legacy inquiry.parquet path → has_reply=True, reply excluded.

    Tests the LEGACY code path: legacy inquiry.parquet with kind='reply' for the 复函 row.
    Both code paths (legacy + filings) must agree on the reply classification.
    """
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    from engine import china_special_situations as css
    css._REGIME_HISTORY_CACHE.clear()

    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    # No filings.parquet → legacy path is used
    _make_parquet(tmp_path / "data" / "china_inquiry" / "inquiry.parquet", [
        {"secCode": "000555", "secName": "老格式银行", "announcementTitle": "关于问询函的说明",
         "announcementTime": today, "adjunctUrl": "/x/letter.pdf",
         "announcementTypeName": "问询函", "kind": "letter", "asof": today},
        {"secCode": "000555", "secName": "老格式银行",
         "announcementTitle": "股票交易异常波动问询函的复函-张三",
         "announcementTime": today, "adjunctUrl": "/x/fuhan.pdf",
         "announcementTypeName": "问询函回函", "kind": "reply", "asof": today},
    ])

    snap = css.scan()
    inq = snap.get("inquiry") or {}

    assert inq.get("n_letters") == 1, f"Legacy path: expected 1 letter, got {inq.get('n_letters')}"
    letter = inq["letters"][0]
    assert letter["secCode"] == "000555"
    assert letter["has_reply"] is True, "Legacy path: has_reply must be True for 复函 reply row"


# ── 9. CST skew fixture — claim not double-registered across source switch ─────

def test_cst_skew_legacy_first_filings_no_reregister(tmp_path, monkeypatch):
    """Skew fixture (forward direction): letter timestamped 07:30 CST.

    Legacy path stored UTC date (D-1 = previous calendar day).
    Filings path stores CST date (D).

    Step 1: Legacy registers claim with key inq_{code}_{D-1}.
    Step 2: Filings path MUST NOT re-register (canonical key inq_{code}_{D},
            but utc_variant_key inq_{code}_{D-1} is already in sidecar → skipped).

    Implements the reviewer's skew fixture.
    """
    monkeypatch.setenv("CN_LANE", "asia")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    import engine.china_special_situations as css
    import engine.qledger as ql_mod
    css._REGIME_HISTORY_CACHE.clear()

    registered_calls: list[list] = []

    def fake_make(**kw):
        return {"_claim": True, **kw}

    def fake_batch(claims, **kw):
        registered_calls.append(list(claims))
        return [{"status": "new"} for _ in claims]

    monkeypatch.setattr(ql_mod, "make_claim", fake_make)
    monkeypatch.setattr(ql_mod, "register_batch", fake_batch)

    import datetime
    # Letter at 07:30 CST = 23:30 UTC on D-1.
    # CST date = D, UTC date = D-1.
    today = pd.Timestamp.today()
    cst_date = today.strftime("%Y-%m-%d")          # D (canonical CST date)
    utc_date = (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # D-1 (legacy UTC date)

    sec_code = "000333"

    # Step 1: Pre-populate sidecar as if LEGACY registered with the UTC date (D-1).
    sidecar_path = tmp_path / "data" / "china_special_sits" / "claims_registered.parquet"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"event_key": f"inq_{sec_code}_{utc_date}", "first_registered": utc_date}
    ]).to_parquet(sidecar_path, index=False)

    # Step 2: Filings.parquet stores CST date (D) for the same event.
    rows = [
        _filings_row(sec_code, "跨时区测试", "关注函说明",
                     f"{cst_date}T07:30:00+08:00",   # 07:30 CST = previous UTC day
                     kind="letter", announcement_id="SKEW-001"),
    ]
    _make_parquet(tmp_path / "data" / "china_filings" / "filings.parquet", rows)

    snap = css.scan()
    n = css.register_claims(snap)

    assert n == 0, (
        f"CST-skew fixture (legacy-first): filings path must NOT re-register a claim "
        f"already registered by legacy (utc_date={utc_date}, cst_date={cst_date}). "
        f"Got n={n}, registered_calls={registered_calls}"
    )


def test_cst_skew_filings_first_legacy_no_reregister(tmp_path, monkeypatch):
    """Skew fixture (reverse direction): letter timestamped 07:30 CST.

    Filings path registers claim first with canonical key inq_{code}_{D} (CST date).
    Legacy path then arrives with date D-1 (UTC date).
    The canonical for legacy (D-1+1 = D) is already registered → must be skipped.

    We simulate this by: (1) registering via filings (canonical key D written to sidecar),
    (2) then building a snap whose inquiry date is D-1 (as legacy would report) and
    calling register_claims again — must return 0.
    """
    monkeypatch.setenv("CN_LANE", "asia")
    import lib.config as cfg
    monkeypatch.setattr(cfg, "data_dir", lambda: tmp_path / "data")
    monkeypatch.setattr(cfg, "load", lambda: {"storage": {"site_dir": str(tmp_path / "site")}})
    monkeypatch.setattr(cfg, "ROOT", tmp_path)

    import engine.china_special_situations as css
    import engine.qledger as ql_mod
    css._REGIME_HISTORY_CACHE.clear()

    all_registered: list = []

    def fake_make(**kw):
        return {"_claim": True, **kw}

    def fake_batch(claims, **kw):
        all_registered.extend(claims)
        return [{"status": "new"} for _ in claims]

    monkeypatch.setattr(ql_mod, "make_claim", fake_make)
    monkeypatch.setattr(ql_mod, "register_batch", fake_batch)

    today = pd.Timestamp.today()
    cst_date = today.strftime("%Y-%m-%d")          # D
    utc_date = (today - pd.Timedelta(days=1)).strftime("%Y-%m-%d")  # D-1

    sec_code = "000444"

    # Step 1: Pre-populate sidecar as if FILINGS already registered with canonical key (D).
    sidecar_path = tmp_path / "data" / "china_special_sits" / "claims_registered.parquet"
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {"event_key": f"inq_{sec_code}_{cst_date}", "first_registered": cst_date}
    ]).to_parquet(sidecar_path, index=False)

    # Step 2: Build a snap that looks like the LEGACY source — date = D-1 (UTC date).
    # The utc_variant_key for D-1 is (D-1)-1 = D-2 (NOT in sidecar).
    # BUT: the canonical key for D-1 would be inq_{code}_{D-1}, which is NOT in sidecar.
    # The real dedup path: canonical=D-1, utc_variant=D-2 → neither matches → would register.
    #
    # The correct dedup for reverse-order requires that when the legacy date is D-1,
    # we also check if D-1+1 = D is in the sidecar. This is the "check both date and
    # date+1day variants for legacy-dated rows" ruling.
    # Implementation: _cst_claim_keys(sec_code, D-1) returns:
    #   canonical_key = inq_{code}_{D-1}
    #   utc_variant_key = inq_{code}_{D-2}
    # Neither is in sidecar (sidecar has D). So we need a separate "forward check"
    # for legacy: also check date+1 as the canonical variant.
    #
    # Per the ruling: "check both `date` and `date+1day` variants for legacy-dated rows".
    # The snap letter has date=D-1; we also check inq_{code}_{D} (date+1).
    # That key IS in sidecar → skip.
    #
    # We simulate legacy snap by injecting a letter with date=D-1 directly.
    snap_legacy = {
        "inquiry": {
            "letters": [
                {
                    "secCode": sec_code,
                    "secName": "逆序测试",
                    "title": "关注函说明",
                    "date": utc_date,   # legacy UTC date = D-1
                    "pdf_url": "/x.pdf",
                    "has_reply": False,
                    "type_name": "问询函",
                }
            ],
            "n_letters": 1,
            "n_replies": 0,
        },
        "unlocks": None,
    }

    n = css.register_claims(snap_legacy)
    assert n == 0, (
        f"CST-skew fixture (filings-first): legacy path (date=D-1={utc_date}) must NOT "
        f"re-register when filings already registered canonical key (D={cst_date}). "
        f"Got n={n}. Check that register_claims tests date+1 variant for legacy rows."
    )
