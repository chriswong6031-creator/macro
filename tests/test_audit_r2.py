"""R2 data-plane freshness probe. Definitive server responses (stale Last-Modified,
404-everywhere, 403, old asof) FAIL; network-layer errors degrade to warnings. Pure
function, deterministic `now`, injected fetcher."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from urllib.error import URLError

from scripts.audit_r2 import probe

NOW = datetime(2026, 7, 2, 14, 30, tzinfo=timezone.utc)
BASE = "https://r2.example"


def _lm(hours_ago: float) -> dict:
    return {"Last-Modified": format_datetime(NOW - timedelta(hours=hours_ago), usegmt=True)}


def _spy(asof_days_ago: int) -> bytes:
    return json.dumps({"ticker": "SPY", "asof": (NOW.date() - timedelta(days=asof_days_ago)).isoformat()}).encode()


def _fetcher(objects: dict):
    """key -> (status, headers, body) | Exception. Missing keys 404."""
    def fetch(url: str, method: str = "HEAD", timeout: float = 0):
        v = objects.get(url.removeprefix(BASE + "/"))
        if v is None:
            return 404, {}, None
        if isinstance(v, Exception):
            raise v
        st, hdrs, body = v
        return st, hdrs, (body if method == "GET" else None)
    return fetch


def _probe(objects, **kw):
    kw.setdefault("anchors", ["stockdata", "chinastockdata"])
    kw.setdefault("retries", 0)
    return probe(NOW, base=BASE, fetch=_fetcher(objects), **kw)


FRESH = {
    "stockdata/_manifest.json": (200, _lm(6), None),
    "chinastockdata/_manifest.json": (200, _lm(5), None),
    "stockdata/SPY.json": (200, {}, _spy(1)),
}


def test_fresh_plane_is_ok():
    r = _probe(FRESH)
    assert r["ok"] is True and not r["fail_reasons"] and not r["warnings"]
    assert r["anchors"]["stockdata"]["age_hours"] == 6.0


def test_stale_manifest_fails():
    r = _probe({**FRESH, "stockdata/_manifest.json": (200, _lm(31), None)})
    assert r["ok"] is False
    assert any("R2 STALE: stockdata" in f for f in r["fail_reasons"])


def test_manifest_404_falls_back_to_fresh_index():
    # transition state: manifest rollout hasn't reached a lane yet — index carries it
    objs = dict(FRESH)
    del objs["chinastockdata/_manifest.json"]
    objs["chinastockdata/index.json"] = (200, _lm(7), None)
    r = _probe(objs)
    assert r["ok"] is True
    assert r["anchors"]["chinastockdata"]["anchor"] == "chinastockdata/index.json"


def test_freshest_candidate_wins():
    # a clobbered-but-recent manifest must not hide a fresher index (and vice versa)
    objs = {**FRESH, "stockdata/_manifest.json": (200, _lm(30), None),
            "stockdata/index.json": (200, _lm(8), None)}
    r = _probe(objs)
    assert r["ok"] is True
    assert r["anchors"]["stockdata"]["anchor"] == "stockdata/index.json"


def test_dark_dir_fails():
    objs = {k: v for k, v in FRESH.items() if not k.startswith("chinastockdata")}
    r = _probe(objs)
    assert r["ok"] is False
    assert any("R2 DARK: chinastockdata" in f for f in r["fail_reasons"])


def test_forbidden_fails():
    r = _probe({**FRESH, "stockdata/_manifest.json": (403, {}, None),
                "stockdata/index.json": (403, {}, None)})
    assert r["ok"] is False
    assert any("R2 FORBIDDEN" in f for f in r["fail_reasons"])
    # 403 is the failure — no double-fail as DARK on the same dir
    assert not any("R2 DARK: stockdata" in f for f in r["fail_reasons"])


def test_network_errors_warn_but_never_fail():
    boom = URLError("dns down")
    r = _probe({k: boom for k in FRESH} | {"chinastockdata/index.json": boom,
                                           "stockdata/index.json": boom})
    assert r["ok"] is True and not r["fail_reasons"]
    assert any("R2 UNREACHABLE" in w for w in r["warnings"])


def test_stale_asof_fails_content_probe():
    r = _probe({**FRESH, "stockdata/SPY.json": (200, {}, _spy(10))})
    assert r["ok"] is False
    assert any("R2 CONTENT STALE" in f for f in r["fail_reasons"])


def test_weekend_asof_within_limit_is_ok():
    r = _probe({**FRESH, "stockdata/SPY.json": (200, {}, _spy(4))})  # Fri close seen on Tue
    assert r["ok"] is True


def test_missing_asof_anchor_fails():
    objs = dict(FRESH)
    del objs["stockdata/SPY.json"]
    r = _probe(objs)
    assert r["ok"] is False
    assert any("R2 CONTENT PROBE" in f for f in r["fail_reasons"])


def test_asof_probe_skipped_when_stockdata_not_anchored():
    r = _probe({"chinastockdata/_manifest.json": (200, _lm(5), None)},
               anchors=["chinastockdata"])
    assert r["ok"] is True and not r["warnings"]


# --- data-dir coverage probe (2026-07-03 massive_stock_day incident) ---------

def _msd_manifest(max_run: int, latest_days_ago: int) -> bytes:
    """A publish_r2 file-list manifest with the embedded collector manifest."""
    latest = (NOW.date() - timedelta(days=latest_days_ago)).isoformat()
    return json.dumps({
        "dir": "massive_stock_day", "count": 14906, "files": ["SPY.parquet"],
        "store": {"store": "massive_stock_day", "latest_date": latest,
                  "coverage": {"first_day": "2021-07-06", "last_day": latest,
                               "max_missing_run_weekdays": max_run},
                  "anchor": {"ticker": "SPY", "last": latest}},
    }).encode()


def _msd(objects=None, max_run=0, latest_days_ago=1, **kw):
    objs = {**FRESH,
            "massive_stock_day/_manifest.json":
                (200, _lm(4), _msd_manifest(max_run, latest_days_ago))}
    objs.update(objects or {})
    kw.setdefault("anchors", ["stockdata", "chinastockdata", "massive_stock_day"])
    return _probe(objs, **kw)


def test_continuous_covered_store_is_ok():
    r = _msd()
    assert r["ok"] is True and not r["warnings"]
    assert r["anchors"]["massive_stock_day/coverage"]["max_missing_run_weekdays"] == 0


def test_interior_coverage_hole_fails_despite_fresh_manifest():
    # The incident: manifest object fresh (Last-Modified 4h) but the store content
    # reports a 75-business-day missing run. Freshness alone cannot see this.
    r = _msd(max_run=75)
    assert r["ok"] is False
    assert any("R2 COVERAGE HOLE" in f for f in r["fail_reasons"])


def test_stale_store_content_fails():
    r = _msd(latest_days_ago=10)
    assert r["ok"] is False
    assert any("R2 CONTENT STALE: massive_stock_day" in f for f in r["fail_reasons"])


def test_pre_coverage_manifest_warns_only():
    legacy = json.dumps({"dir": "massive_stock_day", "count": 2,
                         "files": ["_manifest.json"]}).encode()
    r = _msd({"massive_stock_day/_manifest.json": (200, _lm(4), legacy)})
    assert r["ok"] is True
    assert any("no store coverage yet" in w for w in r["warnings"])


def test_coverage_probe_skipped_when_not_anchored():
    # Default anchors exclude massive_stock_day (never published as of 2026-07-03):
    # the probe must not fire, so an unpublished store cannot red-flag the heartbeat.
    r = _probe(FRESH)
    assert r["ok"] is True and not r["warnings"]
    assert "massive_stock_day/coverage" not in r["anchors"]


# --- coverage probe must not DEREFERENCE a shape it hasn't checked -----------
# Every data-dir collector writes a local _manifest.json whose own top-level "store"
# is the store NAME (a string): backfill_thetadata_eod._write_manifest and
# massive_stock_day._write_manifest both do. The publish-side doc's "store" is the
# embedded collector DICT. Until 2026-07-30 publish_r2's delta pass could leave the raw
# collector doc at the publish-side key, and `store.get("coverage")` on a str raises
# AttributeError — caught by neither except in probe(). That is not a loud crash:
# healthcheck.check_r2_freshness wraps run() in `except Exception -> {"ok": True}`, so
# it would have silently voided the ENTIRE R2 tripwire, every anchor included.

def _raw_collector_doc(name: str = "massive_stock_day") -> bytes:
    """What _write_manifest actually emits — note "store" is a STRING."""
    return json.dumps({"store": name, "n_roots": 47, "per_root": {"SPY": {"n_years": 14}},
                       "updated_at": "2026-07-30T05:00:00+00:00"}).encode()


def test_raw_collector_manifest_warns_and_never_raises():
    r = _msd({"massive_stock_day/_manifest.json": (200, _lm(4), _raw_collector_doc())})
    assert r["ok"] is True                       # not a definitive data-plane verdict
    assert any("RAW collector manifest" in w for w in r["warnings"])
    assert "massive_stock_day/coverage" not in r["anchors"]


def test_absent_store_block_keeps_its_own_softer_warning():
    """A pre-coverage PUBLISHER doc (no "store" at all) is a different situation from the
    raw collector doc sitting at the key — the two must not collapse into one message."""
    legacy = json.dumps({"dir": "massive_stock_day", "count": 2, "files": []}).encode()
    r = _msd({"massive_stock_day/_manifest.json": (200, _lm(4), legacy)})
    assert any("no store coverage yet" in w for w in r["warnings"])
    assert not any("RAW collector manifest" in w for w in r["warnings"])


def test_non_object_manifest_warns():
    r = _msd({"massive_stock_day/_manifest.json": (200, _lm(4), b'["not", "an", "object"]')})
    assert r["ok"] is True
    assert any("not an object" in w for w in r["warnings"])


def test_malformed_coverage_run_warns_instead_of_raising():
    doc = json.dumps({"dir": "massive_stock_day", "count": 1, "files": [],
                      "store": {"coverage": {"max_missing_run_weekdays": "lots"},
                                "anchor": {"last": "2026-07-01"}}}).encode()
    r = _msd({"massive_stock_day/_manifest.json": (200, _lm(4), doc)})
    assert any("bad max_missing_run_weekdays" in w for w in r["warnings"])
    assert not any("COVERAGE HOLE" in f for f in r["fail_reasons"])


def test_non_dict_coverage_and_anchor_blocks_do_not_raise():
    doc = json.dumps({"dir": "massive_stock_day", "count": 1, "files": [],
                      "store": {"coverage": "none", "anchor": ["SPY"]}}).encode()
    r = _msd({"massive_stock_day/_manifest.json": (200, _lm(4), doc)})
    assert any("no store coverage yet" in w for w in r["warnings"])


# --- thetadata_eod: the store's only offsite backup gets a freshness anchor --
# ~60 GB / ~13k parquets; per ops/THETADATA_R2_SYNC_RUNBOOK.md the store "exists only on
# the ops Mac", so this R2 copy is its SOLE offsite backup — and until 2026-07-30 it had
# no anchor in DEFAULT_ANCHORS or COVERAGE_ANCHORS, which is why a 3-night manifest
# freeze went unnoticed until a human read the log. Published by launchd at 22:00 PT
# (~05:00 UTC) daily; at the 14:30 UTC heartbeat a healthy manifest is ~9.5h old and the
# first missed night reads ~33.5h, so the shared 26h budget trips on that first miss.

THETA_KEY = "thetadata_eod/_manifest.json"


def _theta(objects=None, **kw):
    objs = {**FRESH, THETA_KEY: (200, _lm(9.5), None)}
    objs.update(objects or {})
    kw.setdefault("anchors", ["stockdata", "chinastockdata", "thetadata_eod"])
    return _probe(objs, **kw)


def test_thetadata_eod_is_a_live_config_anchor():
    """config.yml's r2_data_plane.anchors REPLACES DEFAULT_ANCHORS wholesale (see
    audit_r2.run), so an anchor added only to the module default is inert. Pin both."""
    from lib import config
    from scripts.audit_r2 import DEFAULT_ANCHORS
    assert "thetadata_eod" in DEFAULT_ANCHORS
    assert "thetadata_eod" in config.load()["r2_data_plane"]["anchors"], (
        "thetadata_eod dropped from config r2_data_plane.anchors — the ThetaData store's "
        "only offsite backup would go untripwired again")


def test_healthy_thetadata_manifest_passes():
    r = _theta()
    assert r["ok"] is True and not r["warnings"]
    assert r["anchors"]["thetadata_eod"]["age_hours"] == 9.5


def test_first_missed_thetadata_night_trips_the_26h_budget():
    """The detection this whole change exists for: one skipped 22:00 PT sync puts the
    manifest at ~33.5h by the next heartbeat."""
    r = _theta({THETA_KEY: (200, _lm(33.5), None)}, max_age_hours=26.0)
    assert r["ok"] is False
    assert any("R2 STALE: thetadata_eod" in f for f in r["fail_reasons"])


def test_healthy_thetadata_night_is_not_a_false_alarm_at_26h():
    assert _theta(max_age_hours=26.0)["ok"] is True


def test_dark_thetadata_store_fails():
    """No manifest object at all — never published, or the bucket/prefix moved."""
    objs = {k: v for k, v in FRESH.items()}
    r = _probe(objs, anchors=["stockdata", "chinastockdata", "thetadata_eod"])
    assert r["ok"] is False
    assert any("R2 DARK: thetadata_eod" in f for f in r["fail_reasons"])


def test_thetadata_eod_has_no_index_json_candidate():
    """Only the *stockdata search libraries carry index.json; probing one here would
    log a spurious 404 note on every run."""
    from scripts.audit_r2 import _candidates
    assert _candidates("thetadata_eod") == [THETA_KEY]


def test_thetadata_eod_deliberately_carries_no_coverage_probe():
    """backfill_thetadata_eod._write_manifest emits store/n_roots/per_root/updated_at and
    NO coverage/anchor/latest_date, so a coverage probe could only ever emit the
    'no store coverage yet' warning — a permanent nag with zero signal. If this goes red
    because thetadata_eod was added to COVERAGE_ANCHORS, teach _write_manifest to emit
    the blocks first (per-root year continuity), then update this test."""
    from scripts.audit_r2 import COVERAGE_ANCHORS
    assert "thetadata_eod" not in COVERAGE_ANCHORS
    r = _theta()
    assert not any("thetadata_eod" in w for w in r["warnings"])
