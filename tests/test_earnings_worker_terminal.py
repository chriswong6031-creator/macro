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


def _write_terminal_archive(root: Path, *, text: str = "Revenue increased 12%") -> None:
    body = {
        "schema": "mastermind.tx/v1",
        "ticker": "AAPL",
        "id": "2026Q3",
        "period": "Q3 FY2026",
        "date": "2026-07-30",
        "title": "AAPL Earnings Call Q3 FY2026",
        "segments": [
            {"speaker": "Tim Cook", "role": "CEO", "text": text},
        ],
    }
    symbol_dir = root / "AAPL"
    symbol_dir.mkdir(parents=True)
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
                "dates": {pair: "2026-07-30"},
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
    assert scores.iloc[0]["source_url"] == "/data/tx/AAPL/2026Q3.json.gz"
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
    assert eq._seen_shas(repo_root) == set()


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
    monkeypatch.setattr(worker, "_fetch_remote_first", lambda root: True)
    published: list[Path] = []
    monkeypatch.setattr(worker, "_publish", lambda root: published.append(root) or True)

    assert worker.run_terminal(
        repo_root=repo_root, provider_cfg={}, limit=64, do_publish=True,
        base_url="unused", tx_root=tx_root, state_path=state_path,
        bootstrap_since=None, seed_existing=False,
    ) == 0
    assert published == [repo_root]


def test_r2_hydration_merges_unpublished_local_rows(monkeypatch, tmp_path: Path):
    from engine import earnings_qual as eq
    from scripts import fetch_earnings_scores as fetcher

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
    monkeypatch.setattr(fetcher, "_remote_manifest", lambda client, bucket: manifest)
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
    assert worker._fetch_remote_first(repo_root) is True
    stored = eq._load_scores_unvalidated(repo_root)
    assert set(stored["ticker"]) == {"AAPL", "MSFT"}
    assert not (eq.store_path(repo_root).parent / "manifest.json").exists()
