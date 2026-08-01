from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pandas as pd

from engine import earnings_transcript_intake as eti


_WORKER_PATH = Path(__file__).resolve().parents[1] / "tools" / "earnings_worker" / "run_worker.py"
_SPEC = importlib.util.spec_from_file_location("earnings_worker_run", _WORKER_PATH)
assert _SPEC and _SPEC.loader
worker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(worker)


def _write_terminal_archive(
    root: Path,
    *,
    text: str = "Revenue increased 12%",
    call_date: str = "2026-07-30",
) -> None:
    body = {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q3",
        "period": "Q3 FY2026",
        "date": call_date,
        "title": "AAPL Earnings Call Q3 FY2026",
        "segments": [
            {"speaker": "Tim Cook", "role": "CEO", "text": text},
        ],
    }
    symbol_dir = root / "AAPL"
    symbol_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(symbol_dir / "2026Q3.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(body, handle)
    pair = "AAPL/2026Q3"
    (root / "index.json").write_text(
        json.dumps(
            {
                "schema": eti.INDEX_SCHEMA,
                "generated_at": "2026-08-01T12:00:00+00:00",
                "body_count": 1,
                "symbol_count": 1,
                "symbols": {"AAPL": ["2026Q3"]},
                "revisions": {pair: eti.canonical_body_sha256(body)},
                "dates": {pair: call_date},
            }
        ),
        encoding="utf-8",
    )


def test_terminal_first_run_seeds_without_historical_replay(tmp_path: Path):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root)
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"
    n = worker.run_terminal(
        repo_root=repo_root,
        provider_cfg={"provider_order": ["openai_compat"]},
        limit=64,
        do_publish=False,
        base_url="unused",
        tx_root=tx_root,
        state_path=state_path,
        bootstrap_since=None,
        seed_existing=False,
    )
    assert n == 0
    state = eti.load_state(state_path, source=f"local:{tx_root.resolve()}")
    assert state["initialized"] is True
    assert state["pending"] == []
    assert "AAPL/2026Q3" in state["known"]


def test_terminal_bootstrap_scores_and_acks_success(monkeypatch, tmp_path: Path):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root)
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"

    from engine import earnings_qual as eq

    def fake_score(text, ticker, quarter, year, provider_cfg=None, **kwargs):
        return {
            "ticker": ticker,
            "quarter": quarter,
            "year": year,
            "call_date": kwargs.get("call_date"),
            "source": kwargs.get("source"),
            "model": "qwen-test",
            "sentiment": 0.5,
            "performance": 7.0,
            "confidence": 0.8,
            "tone_word": "steady",
            "positive_highlights": ["Revenue increased 12%"],
            "negative_highlights": [],
            "tags": ["demand_acceleration"],
            "source_sha256": eq.source_sha256(text),
            "scored_at": "2026-08-01T12:01:00+00:00",
            "source_record_id": kwargs.get("source_record_id"),
            "source_updated_at": kwargs.get("source_updated_at"),
            "source_url": kwargs.get("source_url"),
            "source_revision_sha256": kwargs.get("source_revision_sha256"),
            "prompt_version": "test-v1",
            "analysis_schema_version": "test/v1",
            "summary": "Revenue increased.",
            "is_context_only": True,
            "degraded_reason": None,
        }

    monkeypatch.setattr(eq, "score_text", fake_score)
    n = worker.run_terminal(
        repo_root=repo_root,
        provider_cfg={"provider_order": ["openai_compat"]},
        limit=64,
        do_publish=False,
        base_url="unused",
        tx_root=tx_root,
        state_path=state_path,
        bootstrap_since="2026-07-24",
        seed_existing=False,
    )
    assert n == 1
    state = eti.load_state(state_path, source=f"local:{tx_root.resolve()}")
    assert state["pending"] == []
    scores = eq.load_scores(repo_root)
    assert len(scores) == 1
    assert scores.iloc[0]["source_record_id"] == "defeatbeta:AAPL:2026Q3"
    assert scores.iloc[0]["source_url"] == (
        "https://app.mastermind-x.com/data/tx/AAPL/2026Q3.json.gz"
    )
    assert scores.iloc[0]["source_revision_sha256"]
    assert scores.iloc[0]["degraded_reason"] is None


def test_degraded_model_row_remains_retryable(monkeypatch, tmp_path: Path):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root)
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"

    from engine import earnings_qual as eq

    original = eq.score_text

    def degraded(text, ticker, quarter, year, provider_cfg=None, **kwargs):
        row = original("", ticker, quarter, year, provider_cfg=provider_cfg, **kwargs)
        row["source_sha256"] = eq.source_sha256(text)
        row["degraded_reason"] = "openai_compat_error"
        return row

    monkeypatch.setattr(eq, "score_text", degraded)
    assert worker.run_terminal(
        repo_root=repo_root,
        provider_cfg={"provider_order": ["openai_compat"]},
        limit=64,
        do_publish=False,
        base_url="unused",
        tx_root=tx_root,
        state_path=state_path,
        bootstrap_since="2026-07-24",
        seed_existing=False,
    ) == 0
    state = eti.load_state(state_path, source=f"local:{tx_root.resolve()}")
    assert [eti.ref_from_pending(item).pair for item in state["pending"]] == [
        "AAPL/2026Q3"
    ]
    revision = eti.ref_from_pending(state["pending"][0]).revision_key
    assert state["retry"][revision]["attempts"] == 1
    assert state["retry"][revision]["last_error"] == "model:openai_compat_error"
    assert eq._seen_shas(repo_root) == set()


def test_hydration_failure_cannot_initialize_forward_only_cursor(
    monkeypatch, tmp_path: Path,
):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root)
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"
    monkeypatch.setattr(worker, "_fetch_remote_first", lambda _root: False)

    assert worker.run_terminal(
        repo_root=repo_root, provider_cfg={}, limit=64, do_publish=False,
        base_url="unused", tx_root=tx_root, state_path=state_path,
        bootstrap_since="2026-07-24", seed_existing=False,
    ) == -1
    assert not state_path.exists()

    monkeypatch.setattr(worker, "run_terminal", lambda **_kwargs: -1)
    assert worker.main([
        "--terminal-auto",
        "--terminal-tx-root", str(tx_root),
        "--repo-root", str(repo_root),
        "--terminal-state", str(state_path),
        "--bootstrap-since", "2026-07-24",
        "--no-publish",
    ]) == 1


def test_metadata_only_correction_replaces_same_record(monkeypatch, tmp_path: Path):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root, call_date="2026-07-30")
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"

    from engine import earnings_qual as eq

    calls: list[str] = []

    def fake_score(text, ticker, quarter, year, **kwargs):
        calls.append(str(kwargs.get("call_date")))
        return {
            "ticker": ticker, "quarter": quarter, "year": year,
            "call_date": kwargs.get("call_date"), "source": "transcript",
            "model": "test", "sentiment": 0.2, "performance": 6.0,
            "confidence": 0.8, "tone_word": "steady",
            "positive_highlights": [], "negative_highlights": [], "tags": [],
            "source_sha256": eq.source_sha256(text),
            "source_revision_sha256": kwargs.get("source_revision_sha256"),
            "source_record_id": kwargs.get("source_record_id"),
            "source_updated_at": kwargs.get("source_updated_at"),
            "source_url": kwargs.get("source_url"),
            "scored_at": f"2026-08-01T00:0{len(calls)}:00Z",
            "is_context_only": True, "degraded_reason": None,
        }

    monkeypatch.setattr(eq, "score_text", fake_score)
    kwargs = dict(
        repo_root=repo_root, provider_cfg={}, limit=64, do_publish=False,
        base_url="unused", tx_root=tx_root, state_path=state_path,
        seed_existing=False,
    )
    assert worker.run_terminal(bootstrap_since="2026-07-24", **kwargs) == 1

    # The rendered transcript text is identical; only upstream metadata changes.
    _write_terminal_archive(tx_root, call_date="2026-07-31")
    assert worker.run_terminal(bootstrap_since=None, **kwargs) == 1
    assert calls == ["2026-07-30", "2026-07-31"]
    stored = eq.load_scores(repo_root)
    assert len(stored) == 1
    assert stored.iloc[0]["call_date"] == "2026-07-31"


def test_remote_generation_is_hydrated_before_first_upsert(monkeypatch, tmp_path: Path):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root)
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"
    events: list[str] = []

    from engine import earnings_qual as eq

    monkeypatch.setattr(worker, "_fetch_remote_first", lambda root: events.append("fetch") or True)
    original_upsert = eq.upsert_scores

    def tracked_upsert(rows, root=None):
        events.append("upsert")
        return original_upsert(rows, root=root)

    monkeypatch.setattr(eq, "upsert_scores", tracked_upsert)
    monkeypatch.setattr(
        eq,
        "score_text",
        lambda text, ticker, quarter, year, **kwargs: {
            "ticker": ticker, "quarter": quarter, "year": year,
            "call_date": kwargs.get("call_date"), "source": "transcript",
            "model": "test", "sentiment": 0.2, "performance": 6.0,
            "confidence": 0.8, "tone_word": "steady",
            "positive_highlights": [], "negative_highlights": [], "tags": [],
            "source_sha256": eq.source_sha256(text),
            "source_record_id": kwargs.get("source_record_id"),
            "source_updated_at": kwargs.get("source_updated_at"),
            "source_revision_sha256": kwargs.get("source_revision_sha256"),
            "scored_at": "2026-08-01T00:00:00Z", "is_context_only": True,
            "degraded_reason": None,
        },
    )
    assert worker.run_terminal(
        repo_root=repo_root, provider_cfg={}, limit=64, do_publish=False,
        base_url="unused", tx_root=tx_root, state_path=state_path,
        bootstrap_since="2026-07-24", seed_existing=False,
    ) == 1
    assert events[:2] == ["fetch", "upsert"]


def test_idle_run_retries_publish(monkeypatch, tmp_path: Path):
    tx_root = tmp_path / "tx"
    _write_terminal_archive(tx_root)
    repo_root = tmp_path / "repo"
    state_path = repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"

    from engine import earnings_qual as eq

    eq.upsert_scores([{
        "ticker": "AAPL", "quarter": "Q3", "year": 2026,
        "call_date": "2026-07-30", "source": "transcript", "model": "test",
        "sentiment": 0.2, "performance": 6.0, "confidence": 0.8,
        "tone_word": "steady", "positive_highlights": [],
        "negative_highlights": [], "tags": [], "source_sha256": "existing",
        "scored_at": "2026-08-01T00:00:00Z", "is_context_only": True,
        "degraded_reason": None,
    }], root=repo_root)
    monkeypatch.setattr(worker, "_fetch_remote_first", lambda root: '"base-etag"')
    published: list[tuple[Path, str | None]] = []
    monkeypatch.setattr(
        worker,
        "_publish",
        lambda root, expected_manifest_etag=None: (
            published.append((root, expected_manifest_etag)) or True
        ),
    )

    assert worker.run_terminal(
        repo_root=repo_root, provider_cfg={}, limit=64, do_publish=True,
        base_url="unused", tx_root=tx_root, state_path=state_path,
        bootstrap_since=None, seed_existing=False,
    ) == 0
    assert published == [(repo_root, '"base-etag"')]


def test_r2_hydration_merges_unpublished_local_rows(monkeypatch, tmp_path: Path):
    from engine import earnings_qual as eq
    from scripts import fetch_earnings_scores as fetcher
    from scripts import publish_earnings_r2 as publisher

    repo_root = tmp_path / "repo"
    base = {
        "quarter": "Q3", "year": 2026, "call_date": "2026-07-30",
        "source": "transcript", "model": "test", "sentiment": 0.2,
        "performance": 6.0, "confidence": 0.8, "tone_word": "steady",
        "positive_highlights": [], "negative_highlights": [], "tags": [],
        "scored_at": "2026-08-01T00:00:00Z", "is_context_only": True,
        "degraded_reason": None,
    }
    local = dict(
        base, ticker="AAPL", source_sha256="local-ahead",
        source_record_id="defeatbeta:AAPL:2026Q3",
    )
    remote = dict(
        base, ticker="MSFT", source_sha256="remote-current",
        source_record_id="defeatbeta:MSFT:2026Q3",
    )
    eq.upsert_scores([local], root=repo_root)

    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.setenv(name, "configured")
    fetched = {"done": False}
    manifest = {"schema": "test", "generation_id": "remote-generation"}
    monkeypatch.setattr(fetcher, "_client", lambda: object())
    monkeypatch.setattr(
        publisher,
        "_remote_manifest_snapshot",
        lambda client, bucket: (manifest, '"remote-etag"'),
    )
    monkeypatch.setattr(fetcher, "_manifest_contract", lambda value: (True, None))
    monkeypatch.setattr(
        fetcher,
        "_local_generation_current",
        lambda earnings_dir, value: fetched["done"],
    )

    def fake_fetch(data_dir=None, dry_run=False):
        scores = eq.store_path(repo_root)
        scores.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [eq._row_to_store(remote)], columns=eq._STORE_COLUMNS,
        ).to_parquet(scores, index=False)
        (scores.parent / "manifest.json").write_text("{}", encoding="utf-8")
        fetched["done"] = True
        return 0

    monkeypatch.setattr(fetcher, "fetch", fake_fetch)
    assert worker._fetch_remote_first(repo_root) == '"remote-etag"'
    stored = eq._load_scores_unvalidated(repo_root)
    assert set(stored["ticker"]) == {"AAPL", "MSFT"}
    assert not (eq.store_path(repo_root).parent / "manifest.json").exists()


def test_publish_rebases_and_retries_manifest_conflict(monkeypatch, tmp_path: Path):
    from scripts import publish_earnings_r2 as publisher

    outcomes = iter([publisher.PUBLISH_CONFLICT, 0])
    publishes: list[tuple[Path, str | None]] = []
    rebases: list[Path] = []

    def fake_publish(*, data_dir, expected_manifest_etag=None):
        publishes.append((data_dir, expected_manifest_etag))
        return next(outcomes)

    monkeypatch.setattr(publisher, "publish", fake_publish)
    monkeypatch.setattr(
        worker,
        "_fetch_remote_first",
        lambda root: rebases.append(root) or '"second-etag"',
    )
    assert worker._publish(
        tmp_path,
        expected_manifest_etag='"first-etag"',
    ) is True
    assert publishes == [
        (tmp_path / "data", '"first-etag"'),
        (tmp_path / "data", '"second-etag"'),
    ]
    assert rebases == [tmp_path]
