"""tests/test_press_run.py — D14 W1 press orchestrator (scripts/run_press.py).

The load-bearing test in this file is
`test_staging_writes_nothing_outside_the_staging_dir`: --staging is the default
mode and the whole safety argument for shipping this lane at all rests on it
touching nothing under content/ or site/.  That is asserted by snapshotting the
tree, not by reading the code.

Everything runs against a synthetic root under tmp_path.  No test makes a
network call — the writer is stubbed at the module boundary.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from engine.press import desk_planner as P  # noqa: E402
from engine.press import writer as W  # noqa: E402
from scripts import run_press as R  # noqa: E402
from tests import press_fixtures as F  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────


def _good_draft(slot, n=0):
    """A draft derived from the SLOT's own facts, so it genuinely passes.

    An invented-number stub fails fact_anchor, which makes every assertion in
    this file vacuous — "passed + quarantined == planned" is just as true when
    nothing ever passes.
    """
    return F.draft_from_slot(slot, n)


def _stub_writer(monkeypatch, *, draft_fn=None, ok=True, reason="stubbed failure"):
    calls = {"n": 0, "single_provider_attempt": []}

    def _write(slot, cfg, *, state=None, attempt=0, prior_failures=None,
               single_provider_attempt=False):
        calls["n"] += 1
        calls["single_provider_attempt"].append(single_provider_attempt)
        if not ok:
            (state or W.RunState()).record_failure()
            return {"ok": False, "draft": None, "reason": reason,
                    "provider": None, "attempt": attempt,
                    "state": (state or W.RunState()).snapshot()}
        draft = dict((draft_fn or _good_draft)(slot, calls["n"] - 1))
        return {"ok": True, "draft": draft, "reason": "", "provider": "stub",
                "model": "stub-model", "attempt": attempt,
                "state": (state or W.RunState()).snapshot()}

    monkeypatch.setattr(R.writer, "write", _write)
    return calls


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def _write_earnings_event(
    root: Path,
    receipt_char: str,
    *,
    title="Corrected call",
    derived_receipt_char: str | None = None,
    write_derived: bool = True,
) -> str:
    from engine.chronicle.earnings_calls import CALL_EVENTS_REL, project_score_row

    source_ref = "defeatbeta:AAPL:2026Q3"
    canonical = project_score_row({
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-26", "source": "terminal_transcript",
        "source_url": "/data/tx/AAPL/2026Q3.json.gz",
        "source_sha256": receipt_char * 64,
        "source_revision_sha256": receipt_char * 64,
        "source_record_id": source_ref,
        "source_updated_at": "2026-07-26T20:00:00Z",
        "scored_at": "2026-07-26T20:05:00Z",
        "model": "fixture", "prompt_version": "fixture-v1",
        "analysis_schema_version": "fixture-v1", "sentiment": 0.2,
        "performance": 6.0, "confidence": 0.8, "tone_word": "confident",
        "summary": "Services demand accelerated after guidance.",
        "positive_highlights": [], "negative_highlights": [], "tags": [],
        "is_context_only": True, "degraded_reason": None,
    })
    canonical_path = root / CALL_EVENTS_REL
    canonical_path.parent.mkdir(parents=True, exist_ok=True)
    canonical_path.write_text(json.dumps(canonical) + "\n", encoding="utf-8")
    derived_char = derived_receipt_char or receipt_char
    event = {
        "id": "cev-earnings-call-aapl",
        "ts": "2026-07-26T00:00:00Z",
        "date": "2026-07-26",
        "source": "earnings_call",
        "source_ref": source_ref,
        "kind": "earnings",
        "title": title,
        "facts": ["Services demand accelerated after guidance."],
        "tickers": ["AAPL"],
        "themes": ["earnings_call"],
        "horizon_hint": "short",
        "weight_hint": 2,
        "links": {
            "site": None,
            "source": "https://app.mastermind-x.com/data/tx/AAPL/2026Q3.json.gz",
            "receipt": "sha256:" + derived_char * 64,
        },
    }
    if write_derived:
        (root / "data" / "chronicle" / "events.jsonl").write_text(
            json.dumps(event) + "\n", encoding="utf-8",
        )
    return f"chronicle:{source_ref}"


def _revision_stage(ref: str, receipt_char: str, *, status="passed") -> dict:
    receipt = "sha256:" + receipt_char * 64
    slot = F.slot(
        id=f"press-brief-{receipt_char}",
        sources=[ref],
        source_revisions={ref: receipt},
        primary_source={
            "kind": "first_party", "name": "Mastermind earnings-call analysis",
            "url": "https://app.mastermind-x.com/data/tx/AAPL/2026Q3.json.gz",
            "ref": ref, "receipt": receipt,
        },
    )
    return {
        "id": slot["id"], "desk": "brief", "publication": "mastermind_news",
        "as_of": "2026-07-26", "status": status, "sources": [ref],
        "source_revisions": {ref: receipt}, "seed_refs": [],
        "slug": "aapl-q3-call", "draft": dict(_good_draft(slot), slug="aapl-q3-call"),
        "slot": slot, "validator_report": {"ok": True},
    }


# ─────────────────────────────────────────────────────────────────────────────
# staging — the safety invariant
# ─────────────────────────────────────────────────────────────────────────────


def test_staging_writes_nothing_outside_the_staging_dir(tmp_path, monkeypatch):
    root = F.fixture_root(tmp_path)
    before = _snapshot(root)
    _stub_writer(monkeypatch)

    summary = R.run_staging(root, P.load_config(root), as_of="2026-07-26",
                            desks=["brief"], max_slots=1)
    assert summary["passed"] == 1, "the passing path must actually be exercised here"

    new = _snapshot(root) - before
    assert new, "the run produced nothing at all"
    assert all(p.startswith("data/press/staging/") for p in new), sorted(new)
    assert not (root / "site").exists()
    assert list((root / "content" / "seo" / "blog").glob("*.md")) == []


def test_staging_writes_one_json_per_slot_plus_a_run_summary(tmp_path, monkeypatch):
    root = F.fixture_root(tmp_path)
    _stub_writer(monkeypatch)
    summary = R.run_staging(root, P.load_config(root), as_of="2026-07-26")

    files = sorted(p.name for p in (root / "data" / "press" / "staging").glob("*.json"))
    assert "_run_summary.json" in files
    assert len(files) == summary["planned"] + 1
    assert summary["passed"] + summary["quarantined"] == summary["planned"]
    # Not vacuous: at least one slot must have made it through the real suite.
    assert summary["passed"] >= 1


def test_a_staged_item_carries_the_whole_audit_trail(tmp_path, monkeypatch):
    root = F.fixture_root(tmp_path)
    _stub_writer(monkeypatch)
    R.run_staging(root, P.load_config(root), as_of="2026-07-26",
                  desks=["brief"], max_slots=1)

    item = json.loads(next(
        p for p in sorted((root / "data" / "press" / "staging").glob("*.json"))
        if not p.name.startswith("_")).read_text(encoding="utf-8"))
    for key in ("id", "desk", "publication", "as_of", "staged_at", "sources",
                "seed_refs", "slot", "attempts", "status"):
        assert key in item
    assert item["status"] == "passed"
    assert item["validator_report"]["ok"] is True
    assert item["validator_report"]["our_value_share"] is not None
    assert item["validator_report"]["our_value_granularity"] == "sentence"
    assert item["validator_report"]["receipts"] >= 5


def test_a_failing_draft_is_regenerated_then_quarantined(tmp_path, monkeypatch):
    """fail -> regenerate <= max_regenerations -> drop with a reason.
    A thin day beats a padded one."""
    root = F.fixture_root(tmp_path)
    cfg = P.load_config(root)
    max_regen = cfg["quarantine"]["max_regenerations"]

    def _bad(slot, n):
        d = _good_draft(slot, n)
        d["body_html"] = F.body("Moreover, this trips the AI-tell rule outright.")
        return d

    calls = _stub_writer(monkeypatch, draft_fn=_bad)
    summary = R.run_staging(root, cfg, as_of="2026-07-26")

    assert summary["passed"] == 0
    assert summary["quarantined"] == summary["planned"]
    assert calls["n"] == summary["planned"] * (max_regen + 1)

    item = json.loads(next(
        p for p in sorted((root / "data" / "press" / "staging").glob("*.json"))
        if not p.name.startswith("_")).read_text(encoding="utf-8"))
    assert len(item["attempts"]) == max_regen + 1
    assert "ai_tells" in item["quarantine_reason"]


def test_a_run_level_stop_does_not_burn_the_regeneration_budget(tmp_path, monkeypatch):
    """no_provider / circuit_open / budget-exhausted are run problems, not draft
    problems — retrying them just spends the outage twice."""
    root = F.fixture_root(tmp_path)
    calls = _stub_writer(monkeypatch, ok=False, reason="no_provider")
    summary = R.run_staging(root, P.load_config(root), as_of="2026-07-26")
    assert summary["passed"] == 0
    assert calls["n"] == summary["planned"]      # one attempt per slot, not three


def test_staging_emits_a_line_start_annotation(tmp_path, monkeypatch, capsys):
    root = F.fixture_root(tmp_path)
    _stub_writer(monkeypatch)
    R.run_staging(root, P.load_config(root), as_of="2026-07-26",
                  desks=["brief"], max_slots=1)
    lines = [l for l in capsys.readouterr().out.splitlines() if "press_staging" in l]
    assert lines
    # House law: a "::notice" behind a logger prefix is not a line start and
    # GitHub silently drops it.
    assert all(l.startswith("::") for l in lines)


def test_admitted_earnings_staging_isolated_and_receipt_bound(tmp_path, monkeypatch):
    """A preverified candidate never reaches planner/reconciliation or generic stage."""
    root = F.fixture_root(tmp_path)
    cfg = P.load_config(root)
    slot = F.slot(id="press-earnings-admitted-20260726")
    receipt = {
        "schema": "earnings.press_admission/v1",
        "packet_id": "storypacket_" + "a" * 32,
        "story_manifest_sha256": "b" * 64,
    }
    destination = tmp_path / "admitted-earnings-stage"
    before = _snapshot(root)
    calls = _stub_writer(
        monkeypatch,
        draft_fn=lambda candidate, n: F.draft_from_slot(candidate, n, extra_filler=-3),
    )
    monkeypatch.setenv("PRESS_RUN_TOKEN_BUDGET", "999999")

    def _unexpected(*_args, **_kwargs):
        raise AssertionError("admitted staging must not touch mutable discovery")

    monkeypatch.setattr(R, "reconcile_earnings_call_revisions", _unexpected)
    monkeypatch.setattr(R.desk_planner, "plan", _unexpected)
    monkeypatch.setattr(R.desk_planner, "published_refs", _unexpected)
    monkeypatch.setattr(R.desk_planner, "staged_refs", _unexpected)
    monkeypatch.setattr(R.desk_planner, "taken_slugs", _unexpected)

    summary = R.run_admitted_earnings_staging(
        root,
        cfg,
        slot=slot,
        admission_receipt=receipt,
        staging_dir=destination,
    )

    assert calls["n"] == 1
    assert calls["single_provider_attempt"] == [True]
    assert summary["planned"] == 1
    assert summary["passed"] == 1
    assert summary["writer_state"]["token_budget"] == 12_000
    assert _snapshot(root) == before
    assert not list((root / "data" / "press" / "staging").glob("*.json"))

    staged = json.loads((destination / f"{slot['id']}.json").read_text(encoding="utf-8"))
    assert staged["provenance"] == {"admission_receipt": receipt}
    assert staged["attempts"] and len(staged["attempts"]) == 1
    assert (destination / "_run_summary.json").exists()


def test_admitted_earnings_staging_never_retries_or_uses_generic_directory(tmp_path, monkeypatch):
    root = F.fixture_root(tmp_path)
    cfg = P.load_config(root)
    slot = F.slot(id="press-earnings-admitted-no-retry")
    receipt = {"schema": "earnings.press_admission/v1", "packet_id": "storypacket_" + "c" * 32}
    calls = _stub_writer(monkeypatch, ok=False, reason="transient_writer_failure")
    generic = root / "data" / "press" / "staging"

    with pytest.raises(ValueError, match="dedicated non-generic"):
        R.run_admitted_earnings_staging(
            root,
            cfg,
            slot=slot,
            admission_receipt=receipt,
            staging_dir=generic,
        )
    assert calls["n"] == 0

    destination = tmp_path / "admitted-no-retry"
    summary = R.run_admitted_earnings_staging(
        root,
        cfg,
        slot=slot,
        admission_receipt=receipt,
        staging_dir=destination,
    )
    assert calls["n"] == 1
    assert summary["quarantined"] == 1
    staged = json.loads((destination / f"{slot['id']}.json").read_text(encoding="utf-8"))
    assert len(staged["attempts"]) == 1
    assert staged["attempts"][0]["attempt"] == 0


def test_admitted_earnings_staging_does_not_follow_the_provider_waterfall(tmp_path, monkeypatch):
    """The envelope's one model-call cap reaches the actual provider rail."""
    import engine.llm_auth as llm_auth

    root = F.fixture_root(tmp_path)
    cfg = P.load_config(root)
    slot = F.slot(id="press-earnings-one-provider-only")
    receipt = {"schema": "earnings.press_admission/v1", "packet_id": "storypacket_one"}
    calls = {"first": 0, "second": 0}
    built = {}

    class _Client:
        def __init__(self, name):
            self.name = name
            self.messages = self

        def create(self, **_kwargs):
            calls[self.name] += 1
            if self.name == "first":
                raise ConnectionError("first provider unavailable")
            return None

    providers = [
        {"name": "admitted-first", "env_var": "ADMITTED_FIRST", "cred": "one",
         "client": _Client("first"), "model": "fake-model"},
        {"name": "admitted-second", "env_var": "ADMITTED_SECOND", "cred": "two",
         "client": _Client("second"), "model": "fake-model"},
    ]

    def _build(provider_cfg, *, opus_model=None, **_kwargs):
        built.update(provider_cfg)
        assert opus_model == "fake-model"
        return providers

    monkeypatch.setattr(R.writer, "_model_id", lambda _key: "fake-model")
    monkeypatch.setattr(llm_auth, "build_providers", _build)

    summary = R.run_admitted_earnings_staging(
        root,
        cfg,
        slot=slot,
        admission_receipt=receipt,
        staging_dir=tmp_path / "one-provider-stage",
    )

    assert built["client_max_retries"] == 0
    assert calls == {"first": 1, "second": 0}
    assert summary["quarantined"] == 1


def test_generic_run_staging_keeps_planning_reconciliation_and_retry_contract(tmp_path, monkeypatch):
    """The preplanned helper is an extraction, not a policy change to W1."""
    root = F.fixture_root(tmp_path)
    cfg = P.load_config(root)
    slot = F.slot(id="press-brief-generic-contract")
    seen = {"plan": 0, "reconcile": 0}

    def _reconcile(*_args, **_kwargs):
        seen["reconcile"] += 1
        return {"current_sources": 0, "superseded": 0, "resolved": 0,
                "correction_required": 0, "published_mismatches": 0}

    def _plan(*_args, **_kwargs):
        seen["plan"] += 1
        return [slot]

    calls = _stub_writer(monkeypatch, ok=False, reason="draft_failure")
    monkeypatch.setattr(R, "reconcile_earnings_call_revisions", _reconcile)
    monkeypatch.setattr(R.desk_planner, "plan", _plan)

    summary = R.run_staging(root, cfg, as_of="2026-07-26")
    assert seen == {"plan": 1, "reconcile": 1}
    assert calls["n"] == cfg["quarantine"]["max_regenerations"] + 1
    assert summary["revision_reconciliation"]["current_sources"] == 0
    staged = json.loads((root / "data" / "press" / "staging" / f"{slot['id']}.json").read_text())
    assert len(staged["attempts"]) == cfg["quarantine"]["max_regenerations"] + 1


def test_emit_rejects_mutable_admission_allow_emit_claim(tmp_path):
    """A receipt copied into mutable staging never becomes emit authority."""
    root = F.fixture_root(tmp_path)
    slot = F.slot(id="press-earnings-mutable-admission")
    draft = dict(_good_draft(slot), slug="mutable-admission-claim")
    stage_path = root / "data" / "press" / "staging" / "mutable-admission.json"
    stage_path.write_text(json.dumps({
        "id": slot["id"], "desk": slot["desk"],
        "publication": slot["publication"], "status": "passed",
        "sources": slot["sources"], "source_revisions": {}, "seed_refs": [],
        "slug": draft["slug"], "draft": draft, "slot": slot,
        "validator_report": {"ok": True},
        "provenance": {"admission_receipt": {
            "schema": "earnings.press_admission/v1", "allow_emit": True,
        }},
    }), encoding="utf-8")

    result = R.run_emit(root, P.load_config(root))
    assert result["emitted"] == 0
    assert json.loads(stage_path.read_text(encoding="utf-8"))["status"] == "approval_required"


def test_slug_collisions_are_resolved_before_validation(tmp_path):
    slot = F.slot()
    taken = {"risk-radar-moves-to-caution"}
    a = R._unique_slug("Risk Radar Moves To Caution", slot, taken)
    assert a not in taken and a.startswith("risk-radar-moves-to-caution-")
    # Deterministic: the same story always de-collides to the same slug.
    assert a == R._unique_slug("Risk Radar Moves To Caution", slot, taken)


def test_pending_earnings_draft_is_superseded_when_receipt_changes(tmp_path):
    root = F.fixture_root(tmp_path)
    ref = _write_earnings_event(root, "b")
    path = root / "data" / "press" / "staging" / "old.json"
    path.write_text(json.dumps(_revision_stage(ref, "a")), encoding="utf-8")

    result = R.reconcile_earnings_call_revisions(root, P.load_config(root))
    assert result["superseded"] == 1
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["status"] == "superseded"
    assert item["revision_state"]["recorded"][ref] == "sha256:" + "a" * 64
    assert item["revision_state"]["current"][ref] == "sha256:" + "b" * 64
    blocked, slugs = P.staged_refs(root)
    assert ref not in blocked and "aapl-q3-call" not in slugs


@pytest.mark.parametrize("derived", ["stale", "missing"])
def test_reconciliation_uses_canonical_ledger_when_derived_view_diverges(
    tmp_path, derived,
):
    root = F.fixture_root(tmp_path)
    ref = _write_earnings_event(
        root,
        "b",
        derived_receipt_char="a",
        write_derived=derived != "missing",
    )
    path = root / "data" / "press" / "staging" / "old.json"
    path.write_text(json.dumps(_revision_stage(ref, "a")), encoding="utf-8")

    result = R.reconcile_earnings_call_revisions(root, P.load_config(root))

    assert result["superseded"] == 1
    item = json.loads(path.read_text(encoding="utf-8"))
    assert item["status"] == "superseded"
    assert item["revision_state"]["current"][ref] == "sha256:" + "b" * 64
    assert R.run_emit(root, P.load_config(root))["emitted"] == 0


def test_published_revision_change_creates_non_emittable_correction_state(tmp_path):
    ref = "chronicle:defeatbeta:AAPL:2026Q3"
    published_receipt = "sha256:" + "a" * 64
    root = F.fixture_root(tmp_path, ledger_rows=[{
        "id": "published-a", "ts": "2026-07-26T12:00:00Z", "desk": "brief",
        "publication": "mastermind_news", "slug": "aapl-q3-call",
        "url": "https://www.mastermind-x.com/blog/aapl-q3-call.html",
        "sources": [ref], "source_revisions": {ref: published_receipt},
        "seed_refs": [], "validator_report": {"ok": True}, "urls": [],
    }])
    _write_earnings_event(root, "b")

    first = R.reconcile_earnings_call_revisions(root, P.load_config(root))
    assert first["correction_required"] == 1
    corrections = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (root / "data" / "press" / "staging").glob("*.json")
        if not path.name.startswith("_")
    ]
    assert len(corrections) == 1
    correction = corrections[0]
    assert correction["status"] == "correction_required"
    assert correction["draft"] is None
    assert correction["correction"]["auto_emit_allowed"] is False
    assert correction["correction"]["published"]["receipt"] == published_receipt
    assert correction["correction"]["current"]["receipt"] == "sha256:" + "b" * 64

    second = R.reconcile_earnings_call_revisions(root, P.load_config(root))
    assert second["correction_required"] == 0
    assert R.run_emit(root, P.load_config(root))["emitted"] == 0
    assert list((root / "content" / "seo" / "blog").glob("*.md")) == []


def test_legacy_published_call_without_receipt_fails_closed_to_correction_state(tmp_path):
    ref = "chronicle:defeatbeta:AAPL:2026Q3"
    root = F.fixture_root(tmp_path, ledger_rows=[{
        "id": "legacy-published", "ts": "2026-07-26T12:00:00Z", "desk": "brief",
        "publication": "mastermind_news", "slug": "legacy-aapl-call",
        "url": "https://www.mastermind-x.com/blog/legacy-aapl-call.html",
        "sources": [ref], "seed_refs": [], "validator_report": {"ok": True},
        "urls": [],
    }])
    _write_earnings_event(root, "b")

    result = R.reconcile_earnings_call_revisions(root, P.load_config(root))
    assert result["published_mismatches"] == 1
    correction = json.loads(next(
        path for path in (root / "data" / "press" / "staging").glob("*.json")
        if not path.name.startswith("_")
    ).read_text(encoding="utf-8"))
    assert correction["status"] == "correction_required"
    assert correction["correction"]["published"]["receipt"] is None
    assert correction["correction"]["auto_emit_allowed"] is False


def test_emit_rechecks_receipt_and_refuses_stale_passing_draft(tmp_path):
    root = F.fixture_root(tmp_path)
    ref = _write_earnings_event(root, "b")
    path = root / "data" / "press" / "staging" / "old.json"
    path.write_text(json.dumps(_revision_stage(ref, "a")), encoding="utf-8")

    out = R.run_emit(root, P.load_config(root))
    assert out["emitted"] == 0
    assert json.loads(path.read_text(encoding="utf-8"))["status"] == "superseded"
    assert (root / "data" / "press" / "published.jsonl").read_text() == ""
    assert list((root / "content" / "seo" / "blog").glob("*.md")) == []


def test_emit_persists_generic_source_revision_receipt_in_ledger(
    tmp_path, monkeypatch,
):
    """The earnings hold must not erase the generic receipt-ledger contract."""
    root = F.fixture_root(tmp_path, cutover=False)
    ref = "chronicle:risk_radar_forward_log#2026-07-26"
    stage = _revision_stage(ref, "a")
    (root / "data" / "press" / "staging" / "current.json").write_text(
        json.dumps(stage), encoding="utf-8",
    )
    monkeypatch.setattr(
        R, "reconcile_earnings_call_revisions",
        lambda _root, _cfg: {
            "superseded": 0, "resolved": 0, "correction_required": 0,
            "published_mismatches": 0,
        },
    )
    monkeypatch.setattr(R, "_render_blog_subtree", lambda _root: ([], []))

    out = R.run_emit(root, P.load_config(root))
    assert out["emitted"] == 1
    row = out["items"][0]
    assert row["source_revisions"] == {ref: "sha256:" + "a" * 64}
    committed = json.loads(
        (root / "data" / "press" / "published.jsonl")
        .read_text(encoding="utf-8").splitlines()[-1]
    )
    assert committed["source_revisions"] == row["source_revisions"]


# ─────────────────────────────────────────────────────────────────────────────
# ledger
# ─────────────────────────────────────────────────────────────────────────────


def test_ledger_rows_carry_the_full_shape(tmp_path):
    """The row shape run_emit writes today.

    W1.5 added two fields, both additive and both on EVERY new row regardless of
    cutover: `url` (where this piece was actually published) and `title`. `url`
    is what makes the cutover migration-free — a row states its own URL, so
    pre-cutover rows keep pointing at /blog/ and nothing is ever rewritten.
    Rows written BEFORE this change carry neither, which is legal: the ledger is
    append-only and every consumer reads it with .get().
    """
    path = tmp_path / "published.jsonl"
    row = {"id": "press-brief-1", "ts": "2026-07-26T13:20:00Z", "desk": "brief",
           "publication": "mastermind_news", "slug": "a-slug",
           "title": "A slug of a note", "url": "https://x/blog/a-slug.html",
           "sources": ["chronicle:x"], "seed_refs": ["artifact:y"],
           "validator_report": {"ok": True}, "urls": ["https://x/blog/a-slug.html"]}
    assert R.append_ledger(path, [row]) == 1
    assert R.append_ledger(path, [dict(row, id="press-brief-2")]) == 1

    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert [r["id"] for r in rows] == ["press-brief-1", "press-brief-2"]
    for r in rows:
        assert set(r) == {"id", "ts", "desk", "publication", "slug", "title", "url",
                          "sources", "seed_refs", "validator_report", "urls"}
        assert r["publication"], "every ledger row must carry its publication"


def test_a_pre_w1_5_ledger_row_is_still_readable(tmp_path):
    """No migration, ever.  A row written before `url`/`title` existed must stay
    consumable — engine/press/desk_planner.published_refs and
    engine/press/properties.iter_publication_articles both read it."""
    root = F.fixture_root(tmp_path, ledger_rows=[{
        "id": "press-brief-old", "ts": "2026-07-01T13:20:00Z", "desk": "brief",
        "publication": "mastermind_news", "slug": "old-slug",
        "sources": ["chronicle:x"], "seed_refs": [], "validator_report": {"ok": True},
        "urls": ["https://www.mastermind-x.com/blog/old-slug.html"],
    }])
    refs, slugs = P.published_refs(root, P.load_config(root))
    assert "old-slug" in slugs and "chronicle:x" in refs


def test_append_ledger_never_rewrites_history(tmp_path):
    path = tmp_path / "published.jsonl"
    path.write_text('{"id":"pre-existing"}\n', encoding="utf-8")
    R.append_ledger(path, [{"id": "new"}])
    assert path.read_text(encoding="utf-8").splitlines()[0] == '{"id":"pre-existing"}'


def test_append_ledger_of_nothing_is_a_no_op(tmp_path):
    path = tmp_path / "published.jsonl"
    assert R.append_ledger(path, []) == 0
    assert not path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# emit
# ─────────────────────────────────────────────────────────────────────────────


def test_emit_ignores_quarantined_items(tmp_path):
    root = F.fixture_root(tmp_path, staged={"q.json": {
        "id": "press-brief-q", "desk": "brief", "publication": "mastermind_news",
        "status": "quarantined", "quarantine_reason": "ai_tells", "draft": None,
        "sources": [], "seed_refs": [],
    }})
    out = R.run_emit(root, P.load_config(root))
    assert out["emitted"] == 0
    assert list((root / "content" / "seo" / "blog").glob("*.md")) == []
    assert (root / "data" / "press" / "staging" / "q.json").exists()


def test_emit_with_an_empty_staging_dir_is_a_clean_no_op(tmp_path):
    root = F.fixture_root(tmp_path)
    assert R.run_emit(root, P.load_config(root))["emitted"] == 0


def test_emit_refuses_source_ready_canonical_story(tmp_path):
    root = F.fixture_root(tmp_path)
    slot = F.slot(
        canonical_story_id="story_" + "a" * 32,
        canonical_story_revision_id="storyrev_" + "b" * 32,
        canonical_story_status="source_ready",
        canonical_emit_allowed=False,
    )
    draft = dict(_good_draft(slot), slug="canonical-source-ready")
    stage_path = root / "data" / "press" / "staging" / "canonical.json"
    stage_path.write_text(json.dumps({
        "id": slot["id"], "desk": slot["desk"],
        "publication": slot["publication"], "status": "passed",
        "sources": slot["sources"], "source_revisions": {}, "seed_refs": [],
        "slug": draft["slug"], "draft": draft, "slot": slot,
        "validator_report": {"ok": True},
    }), encoding="utf-8")
    result = R.run_emit(root, P.load_config(root))
    assert result["emitted"] == 0
    staged = json.loads(stage_path.read_text(encoding="utf-8"))
    assert staged["status"] == "approval_required"
    assert "verified-approval compiler" in staged["quarantine_reason"]
    assert not list((root / "content" / "seo" / "blog").glob("*.md"))


def test_emit_refuses_a_canonical_stage_that_self_attests_approval(tmp_path):
    """Mutable status/allowed flags cannot downgrade source-ready evidence."""
    root = F.fixture_root(tmp_path)
    slot = F.slot(
        id="press-earnings-" + "a" * 32,
        canonical_story_id="story_" + "b" * 32,
        canonical_story_revision_id="storyrev_" + "c" * 32,
        canonical_story_status="approved",
        canonical_emit_allowed=True,
        approved_claim_ids=["claim_" + "d" * 32],
        article_derivative_id="der_" + "e" * 32,
    )
    draft = dict(_good_draft(slot), slug="canonical-self-attested")
    stage_path = root / "data" / "press" / "staging" / "canonical-self-attested.json"
    stage_path.write_text(json.dumps({
        "id": slot["id"], "desk": slot["desk"],
        "publication": slot["publication"], "status": "passed",
        "sources": ["chronicle:defeatbeta:AAPL:2026Q1"],
        "source_revisions": {}, "seed_refs": ["earnings-evidence:claim_" + "d" * 32],
        "slug": draft["slug"], "draft": draft, "slot": slot,
        "validator_report": {"ok": True},
    }), encoding="utf-8")

    result = R.run_emit(root, P.load_config(root))
    assert result["emitted"] == 0
    staged = json.loads(stage_path.read_text(encoding="utf-8"))
    assert staged["status"] == "approval_required"
    assert "verified-approval compiler" in staged["quarantine_reason"]
    assert not list((root / "content" / "seo" / "blog").glob("*.md"))


def test_emit_canonical_detection_survives_stripped_slot_flags(tmp_path):
    """Outer id and source/evidence trails independently preserve the block."""
    root = F.fixture_root(tmp_path)
    slot = F.slot(id="press-earnings-" + "f" * 32)
    draft = dict(_good_draft(slot), slug="canonical-identity-trail")
    stage_path = root / "data" / "press" / "staging" / "canonical-identity-trail.json"
    stage_path.write_text(json.dumps({
        "id": slot["id"], "desk": slot["desk"],
        "publication": slot["publication"], "status": "passed",
        "sources": ["chronicle:defeatbeta:AAPL:2026Q1"],
        "source_revisions": {}, "seed_refs": ["earnings-evidence:claim_" + "a" * 32],
        "slug": draft["slug"], "draft": draft,
        # All nested canonical markers have been stripped from the staged JSON.
        "slot": F.slot(id="press-brief-lookalike"),
        "validator_report": {"ok": True},
    }), encoding="utf-8")

    result = R.run_emit(root, P.load_config(root))
    assert result["emitted"] == 0
    assert json.loads(stage_path.read_text(encoding="utf-8"))["status"] == "approval_required"


@pytest.mark.parametrize(
    ("sources", "seed_refs"),
    [
        ([], ["earnings-evidence:claim_" + "a" * 32]),
        (["chronicle:defeatbeta:AAPL:2026Q1"], []),
    ],
)
def test_emit_earnings_detection_survives_either_remaining_identity_trail(
    tmp_path, sources, seed_refs,
):
    """Neither half of mutable provenance may be removed to regain emit.

    A bare DefeatBeta receipt is indistinguishable from the legacy earnings
    planner, so that older article lane is held too until immutable approval
    ingress exists.  Earnings evidence remains available to product surfaces.
    """
    root = F.fixture_root(tmp_path)
    slot = F.slot(id="press-brief-lookalike")
    draft = dict(_good_draft(slot), slug="earnings-single-trail")
    stage_path = root / "data" / "press" / "staging" / "earnings-single-trail.json"
    stage_path.write_text(json.dumps({
        "id": slot["id"], "desk": slot["desk"],
        "publication": slot["publication"], "status": "passed",
        "sources": sources, "source_revisions": {}, "seed_refs": seed_refs,
        "slug": draft["slug"], "draft": draft, "slot": slot,
        "validator_report": {"ok": True},
    }), encoding="utf-8")

    result = R.run_emit(root, P.load_config(root))
    assert result["emitted"] == 0
    staged = json.loads(stage_path.read_text(encoding="utf-8"))
    assert staged["status"] == "approval_required"
    assert "immutable ingress" in staged["quarantine_reason"]
    assert not list((root / "content" / "seo" / "blog").glob("*.md"))


def test_frontmatter_written_by_emit_matches_the_estate_contract(tmp_path):
    pytest.importorskip("yaml")
    import yaml

    slot = F.slot()
    draft = _good_draft(slot)
    md = R._frontmatter_md(draft, slot, F.config())
    assert md.startswith("---\n")
    fm = yaml.safe_load(md.split("---", 2)[1])
    assert fm["slug"] == draft["slug"] == "a-first-party-read-of-the-session"
    assert fm["family"] == "article"
    assert 120 <= len(fm["description"]) <= 155
    assert str(fm["published"]) == "2026-07-26"
    # No date prefix on the stem: slug == filename stem is the estate contract.
    assert not fm["slug"][:1].isdigit()


def test_emit_helpers_it_borrows_from_the_estate_builder_still_exist():
    """--emit replays the render lane's sweeps through build_free_content's own
    helpers so what lands in site/blog/ is the post-image `--check` compares
    against.  A rename upstream must fail HERE, loudly, not quietly ship raw
    pages that turn the estate drift check red on somebody else's PR."""
    pytest.importorskip("jinja2")
    import scripts.build_free_content as B

    for name in ("render_all", "_seed_hashable_assets", "_normalize_like_render_lane"):
        assert callable(getattr(B, name, None)), f"build_free_content.{name} is gone"


def test_render_replay_is_idempotent_against_the_committed_estate():
    """A press emit with no new article must write NOTHING under site/blog/.

    This is the property that stops the lane rewriting pages it does not own.
    Two render-lane sweeps cannot be replayed here — daily.yml's wh_banner tag
    and the `?v=` stamps whose hashes track shared assets — so a raw byte
    comparison reports every already-committed article as "changed" and strips
    the banner off six of them on the way past.  `build_free_content --check`
    normalises exactly those two things away, so the damage is invisible to it:
    caught once by hand, pinned here so it stays caught.

    Self-healing: if the property ever breaks, the snapshot is restored before
    the assertion fires, so a red test never leaves a dirty tree behind.
    """
    pytest.importorskip("jinja2")
    site_blog = _REPO / "site" / "blog"
    if not site_blog.exists():
        pytest.skip("no committed site/blog to compare against")

    before = {p: p.read_bytes() for p in site_blog.rglob("*") if p.is_file()}
    try:
        copied, unowned = R._render_blog_subtree(_REPO)
    finally:
        # Restore modified files AND remove any the render created — a restore
        # that only rewrites known paths leaves new ones behind, which is how a
        # "self-healing" test quietly pollutes the tree it was protecting.
        for path in list(site_blog.rglob("*")):
            if not path.is_file():
                continue
            if path in before:
                if path.read_bytes() != before[path]:
                    path.write_bytes(before[path])
            else:
                path.unlink()
    assert copied == [], f"press emit rewrote pages it does not own: {copied}"
    assert unowned == [], f"press emit minted assets outside its git-add scope: {unowned}"


def test_emit_never_writes_the_sitemap(tmp_path, monkeypatch):
    """The nightly owns site/sitemap.xml.  run_emit raises rather than fight it."""
    root = F.fixture_root(tmp_path)
    (root / "site").mkdir(parents=True, exist_ok=True)
    sitemap = root / "site" / "sitemap.xml"
    sitemap.write_text("<urlset/>", encoding="utf-8")

    staged = {
        "id": "press-brief-x", "desk": "brief", "publication": "mastermind_news",
        "as_of": "2026-07-26", "status": "passed", "sources": ["chronicle:x"],
        "seed_refs": [], "slug": "emit-smoke-note",
        "draft": dict(_good_draft(F.slot()), slug="emit-smoke-note"),
        "slot": F.slot(), "validator_report": {"ok": True},
    }
    (root / "data" / "press" / "staging" / "x.json").write_text(
        json.dumps(staged), encoding="utf-8")

    # Stub the render so the test does not need the full template tree; the
    # sitemap assertion is what this test is for.
    monkeypatch.setattr(R, "_render_blog_subtree", lambda r: ([], []))
    out = R.run_emit(root, P.load_config(root))

    assert out["emitted"] == 1
    assert sitemap.read_text(encoding="utf-8") == "<urlset/>"

    # Asserted through the ROUTER, not against a hardcoded estate path: the
    # target moves at cutover, and a literal here would make this test fail on
    # the cutover PR for a reason that has nothing to do with the sitemap.
    cfg = P.load_config(root)
    route = R._emit_route(cfg, root, R._paths(cfg, root),
                          {"desk": "brief", "publication": "mastermind_news"},
                          "emit-smoke-note")
    assert (route["md_dir"] / "emit-smoke-note.md").exists()

    rows = [json.loads(l) for l in
            (root / "data" / "press" / "published.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[-1]["slug"] == "emit-smoke-note"
    assert rows[-1]["publication"] == "mastermind_news"
    # W1.5 additive fields. `urls` and `url` always agree, and both are whatever
    # the route says — pre-cutover that is the flagship /blog/ URL, byte-identical
    # to what `urls` has carried since W1.
    assert rows[-1]["url"] == route["url"]
    assert rows[-1]["urls"] == [route["url"]]
    assert rows[-1]["title"] == "A first-party read of the session"
    # A consumed staged item leaves staging; it now lives in the ledger.
    assert not (root / "data" / "press" / "staging" / "x.json").exists()


def _staged_passing(root, name="x.json", slug="emit-smoke-note"):
    (root / "data" / "press" / "staging" / name).write_text(json.dumps({
        "id": f"press-brief-{slug}", "desk": "brief",
        "publication": "mastermind_news", "as_of": "2026-07-26",
        "status": "passed", "sources": ["chronicle:x"], "seed_refs": [],
        "slug": slug, "draft": dict(_good_draft(F.slot()), slug=slug),
        "slot": F.slot(), "validator_report": {"ok": True},
    }), encoding="utf-8")


def test_a_failed_render_rolls_the_tree_back(tmp_path, monkeypatch):
    """ATOMICITY. --emit writes every .md BEFORE it renders. A raise in the
    render used to leave .md files with no matching site/ pages — the
    render-clobber class: `build_free_content --check` reports the missing
    pages and the NEXT PR inherits a red estate it did not cause.

    Pinned to `cutover=False` deliberately: this is a test of the ESTATE render
    branch, which still exists after the cutover (any publication without a
    property_tree uses it). Left on the shipped flag it would silently stop
    testing anything the day the switch moved — the estate render is skipped for
    a routed emit, so the injected failure would never fire and the test would
    pass by not running. The routed branch's rollback is covered in
    tests/test_press_properties.py.
    """
    root = F.fixture_root(tmp_path, cutover=False)
    (root / "site" / "blog").mkdir(parents=True)
    existing = root / "site" / "blog" / "index.html"
    existing.write_text("<html>original</html>", encoding="utf-8")
    _staged_passing(root)

    def _boom(_root):
        # Simulate a render that got partway: a new page, a mutated page, then
        # a raise. All three must be undone.
        (root / "site" / "blog" / "new-page.html").write_text("x", encoding="utf-8")
        existing.write_text("<html>CLOBBERED</html>", encoding="utf-8")
        raise RuntimeError("render exploded")

    monkeypatch.setattr(R, "_render_blog_subtree", _boom)
    with pytest.raises(RuntimeError, match="render exploded"):
        R.run_emit(root, P.load_config(root))

    assert list((root / "content" / "seo" / "blog").glob("*.md")) == [], \
        "a .md with no rendered page is the defect this rollback exists for"
    assert existing.read_text(encoding="utf-8") == "<html>original</html>"
    assert not (root / "site" / "blog" / "new-page.html").exists()
    assert (root / "data" / "press" / "published.jsonl").read_text() == ""


def test_a_failed_ledger_append_rolls_the_tree_back(tmp_path, monkeypatch):
    """Published content with no ledger row is an unrecorded publication."""
    root = F.fixture_root(tmp_path)
    (root / "site" / "blog").mkdir(parents=True)
    _staged_passing(root)
    monkeypatch.setattr(R, "_render_blog_subtree", lambda r: ([], []))
    monkeypatch.setattr(R, "append_ledger",
                        lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        R.run_emit(root, P.load_config(root))
    assert list((root / "content" / "seo" / "blog").glob("*.md")) == []


def test_rollback_annotation_starts_its_line(tmp_path, monkeypatch, capsys):
    # cutover=False for the same reason as the test above: the injected failure
    # is in the estate render, which a routed emit skips.
    root = F.fixture_root(tmp_path, cutover=False)
    (root / "site" / "blog").mkdir(parents=True)
    _staged_passing(root)
    monkeypatch.setattr(R, "_render_blog_subtree",
                        lambda r: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        R.run_emit(root, P.load_config(root))
    line = next(l for l in capsys.readouterr().out.splitlines()
                if "press_emit_rollback" in l)
    assert line.startswith("::error title=press_emit_rollback::")


def test_quarantine_reason_is_never_a_bare_prefix():
    """`"validators: " + ""` is TRUTHY, so the old `or` chain could not reach
    its own fallback: an attempt-less slot was quarantined with the reason
    "validators: " — a blank explanation in the one field the operator reads."""
    item = R._stage_item(F.slot(), None, [], "2026-07-26")
    assert item["quarantine_reason"] == "no draft produced"

    item = R._stage_item(F.slot(), None, [{"attempt": 0, "ok": False, "failed": []}],
                         "2026-07-26")
    assert item["quarantine_reason"] == "no draft produced"

    item = R._stage_item(F.slot(), None,
                         [{"attempt": 0, "ok": False, "failed": ["our_value"]}],
                         "2026-07-26")
    assert item["quarantine_reason"] == "validators: our_value"


def test_emit_quarantines_a_slug_that_was_taken_since_staging(tmp_path, monkeypatch):
    root = F.fixture_root(tmp_path)
    # The occupied file is placed at the ROUTED target, so this keeps testing
    # collision detection on both sides of the cutover rather than testing the
    # estate path on one side and nothing on the other.
    cfg = P.load_config(root)
    taken_dir = R._emit_route(cfg, root, R._paths(cfg, root),
                              {"desk": "brief", "publication": "mastermind_news"},
                              "taken-slug")["md_dir"]
    taken_dir.mkdir(parents=True, exist_ok=True)
    (taken_dir / "taken-slug.md").write_text("x", encoding="utf-8")
    (root / "data" / "press" / "staging" / "x.json").write_text(json.dumps({
        "id": "press-brief-x", "desk": "brief", "publication": "mastermind_news",
        "status": "passed", "sources": [], "seed_refs": [], "slug": "taken-slug",
        "draft": dict(_good_draft(F.slot()), slug="taken-slug"),
        "slot": F.slot(), "validator_report": {"ok": True},
    }), encoding="utf-8")
    monkeypatch.setattr(R, "_render_blog_subtree", lambda r: ([], []))

    out = R.run_emit(root, P.load_config(root))
    assert out["emitted"] == 0
    item = json.loads((root / "data" / "press" / "staging" / "x.json").read_text())
    assert item["status"] == "quarantined"
    assert "slug collision" in item["quarantine_reason"]
    assert (taken_dir / "taken-slug.md").read_text() == "x", \
        "the occupying file must survive untouched"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def test_cli_defaults_to_staging(tmp_path, monkeypatch, capsys):
    root = F.fixture_root(tmp_path)
    seen = {}
    monkeypatch.setattr(R, "run_staging",
                        lambda r, c, **kw: seen.update(kw, mode="staging") or {"ok": 1})
    monkeypatch.setattr(R, "run_emit", lambda r, c: pytest.fail("emit must not run"))
    assert R.main(["--root", str(root)]) == 0
    assert seen["mode"] == "staging"
    capsys.readouterr()


def test_cli_env_overrides_the_spend_guards(tmp_path, monkeypatch):
    monkeypatch.setenv("PRESS_RUN_TOKEN_BUDGET", "1234")
    assert R._env_int("PRESS_RUN_TOKEN_BUDGET", 999) == 1234
    monkeypatch.setenv("PRESS_RUN_TOKEN_BUDGET", "not-a-number")
    assert R._env_int("PRESS_RUN_TOKEN_BUDGET", 999) == 999
    monkeypatch.delenv("PRESS_RUN_TOKEN_BUDGET")
    assert R._env_int("PRESS_RUN_TOKEN_BUDGET", 999) == 999


def test_cli_reports_a_missing_config_rather_than_running_blind(tmp_path, capsys):
    assert R.main(["--root", str(tmp_path)]) == 1
    assert "::error title=press_config::" in capsys.readouterr().out
