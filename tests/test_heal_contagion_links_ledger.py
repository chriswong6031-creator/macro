"""Tests for scripts/heal_contagion_links_ledger.py — the data-plane session
restamp + duplicate quarantine heal (forward-ledger calendar-asof audit
2026-08-05).

Pins the executable spec of the rule:

  asof IS a session for that market            -> HONEST, left byte-for-byte alone
  asof is not                                  -> true session = latest index date
                                                  <= asof; restamp in place
  true session already taken for that market   -> QUARANTINE the row (never delete)

and the fail-closed law: a market with an empty session index, or a row with no
index date at or before its stamp, aborts the ENTIRE heal — all twelve ledgers,
not just the offending one — before a single byte is written.

Session indices are PINNED FIXTURES injected through ``session_index_fn``; the
real store is never read, and no date here comes from a clock.  Note that a
market's session index is its OWN — 2026-07-22 is a session for `us` and not for
`ca` below, which is exactly why one calendar stamp across 11 markets was never
honest.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.heal_contagion_links_ledger as heal_mod
from scripts.heal_contagion_links_ledger import HealAbort, heal, main

# ── pinned session indices (weekday literals; 07-18/07-19 are the weekend) ─────

_SESSIONS = {
    "us": {"2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22"},
    # ca is shut on 2026-07-22 in this fixture — a market holiday, not a weekend.
    "ca": {"2026-07-17", "2026-07-20", "2026-07-21"},
}


def _index_fn(overrides: dict[str, set[str]] | None = None):
    """Injectable session-index loader over the pinned fixture."""
    table = dict(_SESSIONS)
    table.update(overrides or {})

    def _fn(mkt: str) -> set[str]:
        return set(table.get(mkt, set()))

    return _fn


# ── fixture ledgers ───────────────────────────────────────────────────────────

def _hist_row(mkt: str, asof: str) -> dict:
    return {"asof": asof, "market": mkt, "p_raw": 0.21, "pct": 0.83,
            "level": "moderate", "top_exporter": "cn"}


def _fwd_row(mkt: str, asof: str) -> dict:
    return {"asof": asof, "market": mkt, "state": "caution",
            "incumbent_state": "caution", "pressure_pct": 0.83,
            "escalated": False, "top_score": None,
            "dominant_scare": "incumbent:caution",
            "graded": None, "bench_path": None}


def _write(p: Path, rows: list[dict]) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _hist_path(root: Path) -> Path:
    return root / "data" / "contagion_links" / "history.jsonl"


def _us_path(root: Path) -> Path:
    return root / "data" / "risk_radar" / "forward_log_contagion.jsonl"


def _ca_path(root: Path) -> Path:
    return root / "data" / "risk_radar_intl" / "ca_forward_log_contagion.jsonl"


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _seed(root: Path) -> None:
    """history (2 markets) + the us and ca shadow forward logs.

    us fwd:  07-17 honest | 07-18 dup | 07-19 dup | 07-20 honest | 07-23 restamp->07-22
    ca fwd:  07-17 honest | 07-18 dup | 07-22 restamp->07-21 (ca is shut on 07-22)
    history: the same shapes, keyed per (market, asof)
    """
    _write(_hist_path(root), [
        _hist_row("us", "2026-07-17"),   # honest
        _hist_row("ca", "2026-07-17"),   # honest
        _hist_row("us", "2026-07-18"),   # Saturday -> dup of us/07-17
        _hist_row("ca", "2026-07-18"),   # Saturday -> dup of ca/07-17
        _hist_row("us", "2026-07-23"),   # drifted  -> restamp to us/07-22
        _hist_row("ca", "2026-07-22"),   # ca shut  -> restamp to ca/07-21
    ])
    _write(_us_path(root), [
        _fwd_row("us", "2026-07-17"),
        _fwd_row("us", "2026-07-18"),
        _fwd_row("us", "2026-07-19"),
        _fwd_row("us", "2026-07-20"),
        _fwd_row("us", "2026-07-23"),
    ])
    _write(_ca_path(root), [
        _fwd_row("ca", "2026-07-17"),
        _fwd_row("ca", "2026-07-18"),
        _fwd_row("ca", "2026-07-22"),
    ])


def _quar(p: Path) -> Path:
    return p.with_name(f"{p.stem}_quarantine{p.suffix}")


# ── honest rows / restamp / quarantine ────────────────────────────────────────

def test_heal_leaves_honest_rows_untouched(tmp_path):
    _seed(tmp_path)
    heal(tmp_path, session_index_fn=_index_fn())

    honest = [r for r in _read(_us_path(tmp_path)) if r["asof"] == "2026-07-17"]
    assert len(honest) == 1
    assert honest[0] == _fwd_row("us", "2026-07-17"), (
        "an honest row was rewritten — the tape vouches for it, leave it alone"
    )


def test_heal_restamps_a_mislabeled_row_to_its_true_session(tmp_path):
    _seed(tmp_path)
    summary = heal(tmp_path, session_index_fn=_index_fn())

    us = _read(_us_path(tmp_path))
    restamped = [r for r in us if r.get("session_inferred")]
    assert len(restamped) == 1
    r = restamped[0]
    assert r["asof"] == "2026-07-22"
    assert r["data_session"] == "2026-07-22"
    assert r["original_asof"] == "2026-07-23"
    assert r["session_source"] == "bench"
    # grading state and signal fields are not this script's business
    assert r["graded"] is None and r["bench_path"] is None
    assert r["pressure_pct"] == 0.83 and r["state"] == "caution"

    # ca is shut on 07-22, so ITS drifted row lands a session earlier — the
    # per-market index is what decides, never one shared calendar.
    ca_restamped = [r for r in _read(_ca_path(tmp_path)) if r.get("session_inferred")]
    assert [r["asof"] for r in ca_restamped] == ["2026-07-21"]

    us_summary = next(f for f in summary["files"]
                      if f["file"] == "risk_radar/forward_log_contagion.jsonl")
    assert us_summary["n_restamped"] == 1
    assert us_summary["n_quarantined_now"] == 2
    assert us_summary["n_survivors"] == 3


def test_heal_quarantines_dupes_with_reason_and_kept_row_pointer(tmp_path):
    _seed(tmp_path)
    heal(tmp_path, session_index_fn=_index_fn())

    quar = _read(_quar(_us_path(tmp_path)))
    assert [q["asof"] for q in quar] == ["2026-07-18", "2026-07-19"]
    for q in quar:
        assert "duplicate re-description" in q["quarantine_reason"]
        assert q["quarantined_kept_row"] == {"market": "us", "asof": "2026-07-17"}
        assert q["quarantined_at"]
        # the quarantined row keeps its original stamp — it is the evidence
        assert q["asof"] in ("2026-07-18", "2026-07-19")

    # history quarantines are keyed per market, not per file
    hq = _read(_quar(_hist_path(tmp_path)))
    assert {(q["market"], q["asof"]) for q in hq} == {
        ("us", "2026-07-18"), ("ca", "2026-07-18"),
    }


def test_heal_deletes_nothing(tmp_path):
    """survivors + quarantine == input count, for every file and in total."""
    _seed(tmp_path)
    before = {p: len(_read(p)) for p in
              (_hist_path(tmp_path), _us_path(tmp_path), _ca_path(tmp_path))}

    summary = heal(tmp_path, session_index_fn=_index_fn())

    for p, n_in in before.items():
        n_out = len(_read(p)) + len(_read(_quar(p)))
        assert n_out == n_in, f"{p.name}: {n_in} rows in, {n_out} accounted for"

    assert summary["n_survivors"] + summary["n_quarantined_now"] == summary["n_rows_in"]
    assert summary["n_rows_in"] == sum(before.values())


def test_heal_writes_meta_provenance(tmp_path):
    _seed(tmp_path)
    heal(tmp_path, session_index_fn=_index_fn())

    meta = json.loads((tmp_path / "data" / "contagion_links" / "ledger_meta.json")
                      .read_text(encoding="utf-8"))
    q = meta["quarantine"]
    assert q["healed_by"] == "scripts/heal_contagion_links_ledger.py"
    assert q["last_heal"]
    assert q["n_rows"] == 5            # 2 history + 2 us + 1 ca
    pointed = {f["ledger"] for f in q["files"]}
    assert pointed == {
        "contagion_links/history.jsonl",
        "risk_radar/forward_log_contagion.jsonl",
        "risk_radar_intl/ca_forward_log_contagion.jsonl",
    }

    gaps = {g["session"]: g for g in meta["known_gaps"]}
    # one entry per distinct ORIGINAL stamp, weekend or drifted alike
    assert set(gaps) == {"2026-07-18", "2026-07-19", "2026-07-22", "2026-07-23"}
    assert all("not evidence about that session" in g["reason"] for g in gaps.values())
    # attribution is per market: 07-22 is a real session for us and not for ca,
    # so only ca may be named against it — a bare date list would over-claim.
    assert gaps["2026-07-22"]["markets"] == ["ca"]
    assert gaps["2026-07-23"]["markets"] == ["us"]
    assert gaps["2026-07-18"]["markets"] == ["ca", "us"]
    assert gaps["2026-07-19"]["markets"] == ["us"]


# ── idempotency ───────────────────────────────────────────────────────────────

def test_heal_rerun_is_a_no_op(tmp_path):
    _seed(tmp_path)
    heal(tmp_path, session_index_fn=_index_fn())
    after_first = {p: p.read_text(encoding="utf-8") for p in
                   (_hist_path(tmp_path), _us_path(tmp_path), _ca_path(tmp_path))}
    quar_first = _quar(_us_path(tmp_path)).read_text(encoding="utf-8")

    second = heal(tmp_path, session_index_fn=_index_fn())

    assert second["n_restamped"] == 0
    assert second["n_quarantined_now"] == 0
    assert second.get("note") == "already healed — nothing to do"
    for p, text in after_first.items():
        assert p.read_text(encoding="utf-8") == text, f"{p.name} changed on re-run"
    assert _quar(_us_path(tmp_path)).read_text(encoding="utf-8") == quar_first, (
        "quarantine file was re-appended on re-run"
    )


def test_heal_dry_run_writes_nothing(tmp_path):
    _seed(tmp_path)
    before = {p: p.read_text(encoding="utf-8") for p in
              (_hist_path(tmp_path), _us_path(tmp_path), _ca_path(tmp_path))}

    summary = heal(tmp_path, dry_run=True, session_index_fn=_index_fn())

    assert summary["dry_run"] is True
    assert summary["n_quarantined_now"] == 5   # 2 history + 2 us + 1 ca
    assert summary["n_restamped"] == 4         # 2 history + 1 us + 1 ca
    for p, text in before.items():
        assert p.read_text(encoding="utf-8") == text
        assert not _quar(p).exists()
    assert not (tmp_path / "data" / "contagion_links" / "ledger_meta.json").exists()


# ── fail-closed ───────────────────────────────────────────────────────────────

def test_heal_aborts_on_an_empty_session_index_and_writes_nothing(tmp_path):
    """An unreadable/empty index means the true session is unknowable → abort."""
    _seed(tmp_path)
    before = {p: p.read_text(encoding="utf-8") for p in
              (_hist_path(tmp_path), _us_path(tmp_path), _ca_path(tmp_path))}

    with pytest.raises(HealAbort, match="empty session index"):
        heal(tmp_path, session_index_fn=_index_fn({"ca": set()}))

    for p, text in before.items():
        assert p.read_text(encoding="utf-8") == text, f"{p.name} was written despite abort"
        assert not _quar(p).exists()
    assert not (tmp_path / "data" / "contagion_links" / "ledger_meta.json").exists()


def test_heal_aborts_when_a_row_predates_every_session_and_writes_nothing(tmp_path):
    """The abort is GLOBAL: a bad row in the LAST file leaves the first two intact.

    history.jsonl and the us log classify cleanly and would have been rewritten;
    the ca log's pre-index row must still stop every write.
    """
    _seed(tmp_path)
    _write(_ca_path(tmp_path), _read(_ca_path(tmp_path)) + [_fwd_row("ca", "2026-07-01")])
    before = {p: p.read_text(encoding="utf-8") for p in
              (_hist_path(tmp_path), _us_path(tmp_path), _ca_path(tmp_path))}

    with pytest.raises(HealAbort, match="no bench bar at or before its stamp"):
        heal(tmp_path, session_index_fn=_index_fn())

    for p, text in before.items():
        assert p.read_text(encoding="utf-8") == text, f"{p.name} was written despite abort"
        assert not _quar(p).exists()
    assert not (tmp_path / "data" / "contagion_links" / "ledger_meta.json").exists()


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_main_reports_an_abort_and_exits_nonzero(tmp_path, monkeypatch, capsys):
    """A fail-closed abort must exit 1 AND emit a line-starting GH annotation.

    The annotation is asserted through capsys and pinned to column 0: this repo's
    logging format prefixes every record, so an annotation emitted through a
    logger reviews as an alarm, runs clean, and produces nothing in the Actions
    summary.
    """
    _seed(tmp_path)
    monkeypatch.setattr(heal_mod, "default_session_index", _index_fn({"ca": set()}))

    rc = main(["--root", str(tmp_path)])
    assert rc == 1

    out = capsys.readouterr().out
    annotations = [ln for ln in out.splitlines() if "::error" in ln]
    assert annotations, f"no GitHub annotation emitted; stdout was:\n{out}"
    assert annotations[0].startswith("::error title=contagion-heal-aborted::"), (
        f"annotation does not start the line: {annotations[0]!r}"
    )
    assert json.loads(out[:out.index("::error")])["aborted"] is True

    # and still nothing written
    assert not _quar(_us_path(tmp_path)).exists()
    assert not (tmp_path / "data" / "contagion_links" / "ledger_meta.json").exists()


def test_main_dry_run_exits_zero(tmp_path, monkeypatch, capsys):
    _seed(tmp_path)
    monkeypatch.setattr(heal_mod, "default_session_index", _index_fn())

    rc = main(["--root", str(tmp_path), "--dry-run"])
    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["dry_run"] is True
    assert summary["n_quarantined_now"] == 5


# ── inventory ─────────────────────────────────────────────────────────────────

def test_heal_covers_all_twelve_ledgers(tmp_path):
    """history.jsonl + the us log + the 10 intl logs; absent files are reported."""
    _seed(tmp_path)
    summary = heal(tmp_path, dry_run=True, session_index_fn=_index_fn())

    assert summary["n_files"] == 12
    labels = [f["file"] for f in summary["files"]]
    assert labels[0] == "contagion_links/history.jsonl"
    assert "risk_radar/forward_log_contagion.jsonl" in labels
    for mkt in ("cn", "hk", "ca", "kr", "jp", "tw", "in", "au", "gb", "ez"):
        assert f"risk_radar_intl/{mkt}_forward_log_contagion.jsonl" in labels
    missing = [f["file"] for f in summary["files"] if f.get("missing")]
    assert len(missing) == 9  # only history + us + ca were seeded
