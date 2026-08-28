"""tests/test_experiments_registry.py — compute() must normalize BOTH seed keysets.

Newer entries in data/experiments/registry_seed.json (hazard-live-reliability-*,
w5a-reversal-rederive, hkca-*, w3*-…) were authored with title/hypothesis/registered_on
instead of name/what/started. compute() must fall back across the alternate keyset so
the emitted site/marketdata/experiments.json never carries name=null / what=null — the
admin Experiments tab (admin/static/app.js) renders those fields directly.

Also covers the 2026-07-25 staleness class: an entry whose `hook` names no reader in
_HOOKS keeps its hand-authored seed `state` forever, with nothing in the panel saying so
(radar-ic advertised "n_matured=0, ic_all=null" for a month after its read matured to
n=2,456 / IC=-0.29). Every state line must now be either LIVE-read or date-labelled.
"""
from __future__ import annotations

import json

import pytest

from engine import experiments_registry


def _compute_with_seed(monkeypatch, entries: list[dict]) -> list[dict]:
    """Run compute() against a synthetic seed; all other reads (hooks) return None."""
    seed = {"experiments": entries}
    monkeypatch.setattr(
        experiments_registry, "_read_json",
        lambda rel: seed if rel == experiments_registry.SEED else None)
    return experiments_registry.compute()["experiments"]


def test_every_real_seed_entry_emits_name_and_what():
    """Regression: every entry in the real seed must produce non-null name AND what."""
    payload = experiments_registry.compute()
    assert payload["n"] > 0
    no_name = [r["id"] for r in payload["experiments"] if not r.get("name")]
    no_what = [r["id"] for r in payload["experiments"] if not r.get("what")]
    assert not no_name, f"seed entries emitted with name=null: {no_name}"
    assert not no_what, f"seed entries emitted with what=null: {no_what}"


def test_alternate_keyset_normalized(monkeypatch):
    rec = _compute_with_seed(monkeypatch, [{
        "id": "alt-1", "title": "Alt title", "kind": "phase0_backtest",
        "hypothesis": "Alt hypothesis", "status": "accruing",
        "program": "hk_canada_stocks", "wave": "W3", "channel": "C5", "phase": "phase-0",
        "registered_on": "2026-07-03", "come_back_on": "2099-01-15",
        "come_back_note": "note", "pr": "w3(c5-collector-fix)",
        "verdict": "NO-GO", "result": "x" * 600,
    }])[0]
    assert rec["name"] == "Alt title"
    assert rec["what"] == "Alt hypothesis"
    assert rec["started"] == "2026-07-03"
    assert rec["source"] == "w3(c5-collector-fix)"
    assert rec["phase_hint"] == "hk_canada_stocks · W3 · C5 · phase-0"
    assert rec["state"].startswith("verdict=NO-GO")
    assert len(rec["state"]) <= 400  # paragraph-length verdicts/results are capped


def test_alternate_keyset_skips_na_segments(monkeypatch):
    rec = _compute_with_seed(monkeypatch, [{
        "id": "alt-2", "title": "T", "hypothesis": "H",
        "program": "hk_canada_stocks", "wave": "N/A", "channel": "C2", "phase": "ACCRUE",
    }])[0]
    assert rec["phase_hint"] == "hk_canada_stocks · C2 · ACCRUE"
    assert rec["state"] is None  # no verdict/result → no fabricated state


def test_track_record_hook_ready_only_on_graded_verdict(monkeypatch):
    """Fix 2026-07-12: verdict='measuring' (rows matured, significance gate not yet
    callable — subsector_track_record vocabulary) must NOT flag ready; it lit
    subsector-rotation 'ready' 44 days before its callable-verdict date. A graded
    verdict (validated / a printed null) still must flag ready — nulls are printed."""
    monkeypatch.setattr(experiments_registry, "_jsonl_dates", lambda rel: (11, 2948))
    for verdict, expect in [("accruing", None), ("measuring", None),
                            ("validated", True), ("null", True)]:
        monkeypatch.setattr(
            experiments_registry, "_read_json",
            lambda rel, v=verdict: {"verdict": v, "horizons": {}})
        out = experiments_registry._refresh_track_record(
            {"storage": "data/x/snapshots.jsonl", "track_json": "data/x/track_record.json"})
        assert out.get("ready") is expect, (verdict, out)


def test_track_record_ready_clears_once_seed_acknowledges_the_verdict(monkeypatch):
    """Fix 2026-08-26 audit: a terminal verdict used to set ready=True forever, pinning
    the panel long after the result was read (index-leadership sat 'ready' for weeks
    after its audit). A seed whose `status` already records the artifact's verdict has
    acknowledged the read → no flag; a verdict that CHANGES after acknowledgment
    (validated → no_go) must re-flag."""
    monkeypatch.setattr(experiments_registry, "_jsonl_dates", lambda rel: (11, 2948))
    monkeypatch.setattr(
        experiments_registry, "_read_json",
        lambda rel: {"verdict": "validated", "horizons": {}})
    base = {"storage": "data/x/snapshots.jsonl", "track_json": "data/x/track_record.json"}
    acked = experiments_registry._refresh_track_record({**base, "status": "validated"})
    assert acked.get("ready") is None, acked
    changed = experiments_registry._refresh_track_record({**base, "status": "no_go"})
    assert changed.get("ready") is True, changed


def test_panel_done_set_stays_in_step_with_the_engine():
    """admin/experiments.py re-derives `ready` with its own _DONE set; a status the
    engine considers concluded but the panel does not re-flags daily forever
    (2026-08-26 audit: the no_go cortex hypotheses). Pin the two sets together."""
    from admin import experiments as admin_experiments
    assert admin_experiments._DONE == experiments_registry._DONE


# ---------------------------------------------------------------------------
# desk-schema ledgers (ai_desk / thematic_desk / demand_chain)
# ---------------------------------------------------------------------------

_DESK_TR = {"schema": "ai_desk_track_record.v1", "as_of": "2026-07-21", "scored_total": 13,
            "open": 32, "overall": {"n": 13, "hits": 11, "misses": 2,
                                    "hit_rate": 0.846, "dir_accuracy": 0.846}}


def test_desk_ledger_is_not_read_as_zero_matured(monkeypatch):
    """A desk ledger carries no `horizons` block and keys its rows on scored_at/check_by,
    not date/snapshot_date. Read through the snapshot-ledger path it graded as
    '13 calls · 0 days logged · 0 matured' while all 13 calls were in fact scored."""
    monkeypatch.setattr(experiments_registry, "_read_json", lambda rel: _DESK_TR)
    monkeypatch.setattr(experiments_registry, "_jsonl_dates", lambda rel: (12, 13))
    out = experiments_registry._refresh_track_record(
        {"storage": "data/ai_desk/scored.jsonl", "track_json": "data/ai_desk/track_record.json"})
    assert "0 matured" not in out["state"]
    assert "13 scored" in out["state"] and "32 open" in out["state"]
    assert "84.6%" in out["state"]
    assert out["state_as_of"] == "2026-07-21"   # the ledger's own as_of, not build day
    assert out["status"] == "measuring"         # rows graded, no verdict published
    assert "ready" not in out                   # a desk publishes no verdict → never self-flags


def test_desk_ledger_with_nothing_scored_stays_accruing(monkeypatch):
    """demand-chain: 43 open, 0 scored. Must read as accruing and must not fake a hit-rate."""
    monkeypatch.setattr(experiments_registry, "_read_json", lambda rel: {
        "as_of": "2026-07-21", "scored_total": 0, "open": 43,
        "overall": {"n": 0, "hits": 0, "hit_rate": None, "dir_accuracy": None}})
    monkeypatch.setattr(experiments_registry, "_jsonl_dates", lambda rel: (0, 0))
    out = experiments_registry._refresh_track_record({"track_json": "x.json"})
    assert out["status"] == "accruing"
    assert "0 scored" in out["state"] and "43 open" in out["state"]
    assert "%" not in out["state"]              # a null hit-rate prints as a null, never 0%


def test_jsonl_dates_reads_desk_row_date_keys(tmp_path, monkeypatch):
    """Row-level dates: snapshot ledgers use date/snapshot_date, desk ledgers scored_at."""
    p = tmp_path / "data" / "ai_desk"
    p.mkdir(parents=True)
    (p / "scored.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"id": "1", "check_by": "2026-06-24", "scored_at": "2026-06-24T09:04:55+00:00"},
        {"id": "2", "check_by": "2026-06-25", "scored_at": "2026-06-25T09:04:55+00:00"},
        {"id": "3", "check_by": "2026-06-25", "scored_at": "2026-06-25T10:00:00+00:00"},
    ]))
    monkeypatch.setattr(experiments_registry, "_root", lambda: tmp_path)
    assert experiments_registry._jsonl_dates("data/ai_desk/scored.jsonl") == (2, 3)


def test_jsonl_dates_reads_the_forward_log_asof_key(tmp_path, monkeypatch):
    """FORWARD LOGS stamp `asof` — no underscore — and the reader used to miss it.

    engine/risk_radar_audit.py and ~9 sibling ledgers write `asof`; with only `as_of` in
    _ROW_DATE_KEYS every one of them published "0 days logged" on the Experiments surface
    while data/governance/grading_closure.json held the true counts (risk_radar forward_log:
    25 logged, 7 graded — surfaced as 0). Reading a key no writer emits is indistinguishable
    from an empty ledger, which is why the whole suite stayed green on it: every other test
    here monkeypatches _jsonl_dates away. This one must hit the real reader.
    """
    p = tmp_path / "data" / "risk_radar"
    p.mkdir(parents=True)
    (p / "forward_log.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"asof": "2026-07-28", "state": "elevated", "alert": True},
        {"asof": "2026-07-29", "state": "caution", "alert": False},
        {"asof": "2026-07-29", "state": "caution", "alert": False},   # same day, one date
    ]))
    monkeypatch.setattr(experiments_registry, "_root", lambda: tmp_path)
    assert experiments_registry._jsonl_dates("data/risk_radar/forward_log.jsonl") == (2, 3), (
        "a forward log keyed on `asof` must not read as an empty ledger")


def test_jsonl_dates_key_preference_survives_the_asof_addition(tmp_path, monkeypatch):
    """`date` still wins over `asof` when a row carries both — the key order is a contract."""
    p = tmp_path / "data" / "mixed"
    p.mkdir(parents=True)
    (p / "log.jsonl").write_text(json.dumps({"date": "2026-07-01", "asof": "2026-07-31"}) + "\n")
    monkeypatch.setattr(experiments_registry, "_root", lambda: tmp_path)
    assert experiments_registry._jsonl_dates("data/mixed/log.jsonl") == (1, 1)
    assert experiments_registry._ROW_DATE_KEYS.index("date") < \
        experiments_registry._ROW_DATE_KEYS.index("asof")


# ---------------------------------------------------------------------------
# the newly-wired live readers
# ---------------------------------------------------------------------------

def test_radar_ic_hook_reads_the_persisted_grade(monkeypatch):
    """radar-ic reads data/radar/radar_ic.json (scripts.build_radar_ic) — NOT
    radar_ic.compute_ic(), which re-reads a price parquet per matured snapshot (~50s)."""
    monkeypatch.setattr(experiments_registry, "_read_json", lambda rel: {
        "as_of": "2026-07-25", "horizon_d": 21, "n_snapshots": 6548, "n_matured": 2456,
        "ic_all": -0.2905, "ic_rolling_90": 0.0944,
        "by_horizon": {"21": {"ic_daily_hac": {"mean_ic": -0.2202, "t_hac": -4.02, "n": 13}}}})
    out = experiments_registry._refresh_radar_ic({})
    assert "6,548 snapshots" in out["state"] and "2,456 matured @21d" in out["state"]
    assert "IC_all=-0.2905" in out["state"]
    assert "t=-4.02" in out["state"] and "n=13 days" in out["state"]  # the HAC gate, not pooled
    assert out["state_as_of"] == "2026-07-25"
    assert out["status"] == "measuring"


def test_radar_ic_hook_falls_back_to_seed_when_artifact_absent(monkeypatch):
    monkeypatch.setattr(experiments_registry, "_read_json", lambda rel: None)
    assert experiments_registry._refresh_radar_ic({}) == {}


def test_calibration_hub_hook_reports_live_vs_cold(monkeypatch):
    monkeypatch.setattr(experiments_registry, "_read_json", lambda rel: {
        "as_of": "2026-07-21", "loops": {"total": 6, "live": 2, "cold": 4},
        "desks": [{"name": "AI Desk", "scored": 13, "hit_rate": 0.846, "health": "calibrated"},
                  {"name": "Stock Desk", "scored": 31, "hit_rate": 0.774, "health": "calibrated"},
                  {"name": "Policy Intent", "scored": 0, "hit_rate": None, "health": "cold"}]})
    out = experiments_registry._refresh_calibration_hub({"storage": "data/calibration/summary.json"})
    assert "live=2/cold=4" in out["state"]
    assert "AI Desk calibrated (n=13, hit 84.6%)" in out["state"]
    assert "Stock Desk calibrated (n=31, hit 77.4%)" in out["state"]
    assert "Policy Intent" not in out["state"]     # cold desks are the remainder, not a list
    assert out["status"] == "measuring" and out["state_as_of"] == "2026-07-21"


def test_calibration_hub_hook_ignores_a_non_calibration_doc(monkeypatch):
    monkeypatch.setattr(experiments_registry, "_read_json", lambda rel: {"schema": "other.v1"})
    assert experiments_registry._refresh_calibration_hub({"storage": "x.json"}) == {}


def test_vol_shock_hook_reports_resolved_and_hit_rate(monkeypatch):
    from engine import vol_shock_scorecard
    monkeypatch.setattr(vol_shock_scorecard, "track_record", lambda *a, **k: {
        "n": 10, "hit_rate": 0.0, "avg_score": 48.0, "by_band": {"elevated": {"n": 10}}})
    monkeypatch.setattr(experiments_registry, "_jsonl_dates", lambda rel: (17, 17))
    out = experiments_registry._refresh_vol_shock({"storage": "data/vol_shock/log.jsonl"})
    assert "17 firings logged" in out["state"] and "10 resolved" in out["state"]
    assert "hit 0.0%" in out["state"]              # a real zero prints; it is not a null
    assert out["status"] == "measuring"


def test_parquet_ledger_hook_counts_rows_and_vintages(tmp_path, monkeypatch):
    pd = pytest.importorskip("pandas")
    store = tmp_path / "data" / "clinicaltrials"
    store.mkdir(parents=True)
    pd.DataFrame({"ticker": ["A", "A", "B"], "first_post": ["2026-06-01", "2026-06-01", "2026-07-23"],
                  "is_halt": [True, False, True], "title": ["x", "y", "z"]}
                 ).to_parquet(store / "trials.parquet")
    monkeypatch.setattr(experiments_registry, "_root", lambda: tmp_path)
    out = experiments_registry._refresh_parquet_ledger({
        "storage": "data/clinicaltrials/trials.parquet",
        "parquet_counts": {"distinct": ["first_post", "ticker"], "flags": ["is_halt"],
                           "latest": "first_post"}})
    assert "3 rows" in out["state"]
    assert "2 first_post values" in out["state"] and "2 ticker values" in out["state"]
    assert "2 is_halt" in out["state"] and "latest first_post 2026-07-23" in out["state"]


def test_parquet_ledger_hook_falls_back_when_store_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(experiments_registry, "_root", lambda: tmp_path)
    assert experiments_registry._refresh_parquet_ledger({"storage": "data/nope/x.parquet"}) == {}
    assert experiments_registry._refresh_parquet_ledger({"storage": "prose, not a path"}) == {}


# ---------------------------------------------------------------------------
# state provenance — a frozen seed string must never read as current
# ---------------------------------------------------------------------------

def test_seed_state_is_labelled_with_the_audit_date(monkeypatch):
    """No live reader → the panel gets an explicit 'as of <seed audit date>' cue."""
    seed = {"audited": "2026-06-30", "experiments": [
        {"id": "frozen", "name": "n", "what": "w", "hook": "static", "state": "hand-authored"}]}
    monkeypatch.setattr(experiments_registry, "_read_json",
                        lambda rel: seed if rel == experiments_registry.SEED else None)
    rec = experiments_registry.compute()["experiments"][0]
    assert rec["state"] == "hand-authored"
    assert rec["state_live"] is False
    assert rec["state_as_of"] == "2026-06-30"


def test_seed_entry_may_date_its_own_state(monkeypatch):
    """Entries authored after the last full audit carry their own state_as_of."""
    seed = {"audited": "2026-06-30", "experiments": [
        {"id": "later", "name": "n", "what": "w", "state": "Registered 2026-07-08",
         "state_as_of": "2026-07-08"}]}
    monkeypatch.setattr(experiments_registry, "_read_json",
                        lambda rel: seed if rel == experiments_registry.SEED else None)
    assert experiments_registry.compute()["experiments"][0]["state_as_of"] == "2026-07-08"


def test_live_hook_state_is_flagged_live(monkeypatch):
    seed = {"experiments": [{"id": "live-1", "name": "n", "what": "w", "hook": "radar_ic",
                             "state": "stale seed line"}]}
    monkeypatch.setattr(
        experiments_registry, "_read_json",
        lambda rel: seed if rel == experiments_registry.SEED else {
            "as_of": "2026-07-25", "n_snapshots": 10, "n_matured": 5, "ic_all": -0.3})
    rec = experiments_registry.compute()["experiments"][0]
    assert rec["state_live"] is True
    assert rec["state"] != "stale seed line"
    assert rec["state_as_of"] == "2026-07-25"


def test_a_raising_hook_keeps_the_seed_state_and_labels_it(monkeypatch):
    """Fail-open: one bad reader never aborts the manifest — and never silently
    passes its seed string off as a live read."""
    seed = {"audited": "2026-06-30", "experiments": [
        {"id": "boom", "name": "n", "what": "w", "hook": "radar_ic", "state": "seed line"}]}
    monkeypatch.setattr(experiments_registry, "_read_json",
                        lambda rel: seed if rel == experiments_registry.SEED else None)
    monkeypatch.setitem(experiments_registry._HOOKS, "radar_ic",
                        lambda e: (_ for _ in ()).throw(RuntimeError("reader down")))
    rec = experiments_registry.compute()["experiments"][0]
    assert rec["state"] == "seed line"
    assert rec["state_live"] is False and rec["state_as_of"] == "2026-06-30"


def test_no_state_means_no_provenance_fields(monkeypatch):
    seed = {"experiments": [{"id": "bare", "name": "n", "what": "w"}]}
    monkeypatch.setattr(experiments_registry, "_read_json",
                        lambda rel: seed if rel == experiments_registry.SEED else None)
    rec = experiments_registry.compute()["experiments"][0]
    assert rec["state"] is None
    assert "state_as_of" not in rec and "state_live" not in rec


# ---------------------------------------------------------------------------
# real-seed regression: the panel's ready list is what the owner acts on
# ---------------------------------------------------------------------------

def test_real_seed_every_state_is_live_or_dated():
    """Whatever the seed says, no record may present a state with no provenance at all."""
    payload = experiments_registry.compute()
    naked = [r["id"] for r in payload["experiments"]
             if r.get("state") and not r.get("state_as_of")]
    assert not naked, f"state lines with no live read and no 'as of' cue: {naked}"


@pytest.mark.parametrize("exp_id", ["radar-ic", "calibration-hub", "thematic-desk",
                                    "vol-shock-scorecard", "clinicaltrials-phase3",
                                    "ai-desk-tracker", "demand-chain"])
def test_real_seed_wired_experiments_read_live(exp_id):
    """These have live readers in-repo; a `static`/absent hook silently froze them at the
    2026-06-30 seed audit. Regression: they must resolve through _HOOKS, not the seed."""
    rec = next(r for r in experiments_registry.compute()["experiments"] if r["id"] == exp_id)
    assert rec.get("state_live") is True, f"{exp_id} fell back to the seed state: {rec.get('state')}"


def test_canonical_keyset_takes_precedence(monkeypatch):
    rec = _compute_with_seed(monkeypatch, [{
        "id": "canon-1", "name": "Canon name", "what": "Canon what",
        "started": "2026-06-30", "source": "engine/x.py",
        "phase_hint": "existing hint", "state": "existing state",
        # alternate keys present too — must NOT override the canonical values
        "title": "loser", "hypothesis": "loser", "registered_on": "1999-01-01",
        "pr": "loser", "program": "loser", "verdict": "loser",
    }])[0]
    assert rec["name"] == "Canon name"
    assert rec["what"] == "Canon what"
    assert rec["started"] == "2026-06-30"
    assert rec["source"] == "engine/x.py"
    assert rec["phase_hint"] == "existing hint"
    assert rec["state"] == "existing state"
