import json

import pandas as pd

from scripts.build_earnings_scores_from_history import build, main
from scripts.import_equitydesk_full import _dedupe_earnings_rows
from scripts.publish_earnings_r2 import _md5, _refresh_manifest, _remote_md5
from scripts.publish_earnings_r2 import _synth_manifest
from scripts import fetch_earnings_scores as fetch_mod
from scripts import publish_earnings_r2 as publish_mod


def test_latest_call_projection_is_one_row_per_ticker():
    history = pd.DataFrame([
        {
            "document_ticker": "AAA US",
            "call_date": "2026-04-20",
            "fiscal_quarter": 1,
            "fiscal_year": 2026,
            "earnings_call_sent": 12,
            "earnings_call_perf": 0,
            "management_confidence_score": 5,
            "level1_tags": '["old"]',
            "level2_tags": "[]",
            "key_quote": "Old call",
        },
        {
            "document_ticker": "AAA US",
            "call_date": "2026-07-30",
            "fiscal_quarter": 2,
            "fiscal_year": 2026,
            "earnings_call_sent": 24,
            "earnings_call_perf": 6,
            "management_confidence_score": 9,
            "analysis_model": float("nan"),
            "level1_tags": '["Demand Acceleration"]',
            "level2_tags": '["Software"]',
            "key_quote": "Newest call",
        },
    ])

    out = build(history)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["ticker"] == "AAA"
    assert row["quarter"] == "Q2"
    assert row["year"] == 2026
    assert row["call_date"] == "2026-07-30"
    assert row["summary"] == "Newest call"
    assert row["model"] == "equitydesk_model_unavailable"
    assert json.loads(row["tags"]) == ["demand_acceleration", "software"]


def test_latest_projection_quarantines_stale_fiscal_label():
    history = pd.DataFrame([{
        "document_ticker": "GEHC",
        "call_date": "2026-05-12",
        "fiscal_quarter": 1,
        "fiscal_year": 2023,
        "earnings_call_sent": 24,
        "earnings_call_perf": 6,
        "management_confidence_score": 9,
    }])

    row = build(history).iloc[0]

    assert row["quarter"] is None
    assert row["year"] is None


def test_cli_advances_scores_seed_and_manifest_together(tmp_path):
    history = tmp_path / "history.parquet"
    scores = tmp_path / "scores.parquet"
    seed = tmp_path / "seed.parquet"
    manifest = tmp_path / "manifest.json"
    pd.DataFrame([{
        "document_ticker": "AAA US",
        "call_date": "2026-07-31",
        "fiscal_quarter": 2,
        "fiscal_year": 2026,
        "earnings_call_sent": 24,
        "earnings_call_perf": 6,
        "management_confidence_score": 9,
        "level1_tags": '[]',
        "level2_tags": '[]',
        "key_quote": "Current call",
    }]).to_parquet(history, index=False)

    rc = main([
        "--history", str(history),
        "--scores", str(scores),
        "--seed", str(seed),
        "--manifest", str(manifest),
    ])

    assert rc == 0
    assert pd.read_parquet(scores).equals(pd.read_parquet(seed))
    payload = json.loads(manifest.read_text())
    assert payload["schema"] == "earnings_intelligence_manifest.v3"
    assert payload["scores"]["rows"] == 1
    assert payload["history"]["rows"] == 1
    assert payload["scores"]["latest_call_date"] == "2026-07-31"
    generation = payload["generation_id"]
    assert payload["scores"]["key"] == (
        f"earnings_calls/generations/{generation}/scores.parquet"
    )
    assert payload["history"]["key"] == (
        f"earnings_calls/generations/{generation}/history.parquet"
    )


def test_import_dedupe_selects_true_latest_updated_akso_record():
    rows = pd.DataFrame([
        {
            "id": "newest",
            "document_ticker": "AKSO.OL",
            "fiscal_quarter": 4,
            "fiscal_year": 2925,
            "call_date": "2026-02-12",
            "created_at": "2026-04-30T21:59:20Z",
            "updated_at": "2026-04-30T21:59:20Z",
            "earnings_call_combined": 19,
        },
        {
            "id": "array-last-but-older",
            "document_ticker": "AKSO.OL",
            "fiscal_quarter": 4,
            "fiscal_year": 2925,
            "call_date": "2026-02-12",
            "created_at": "2026-04-16T18:28:22Z",
            "updated_at": "2026-04-16T18:28:22Z",
            "earnings_call_combined": 17,
        },
    ])

    out, receipt = _dedupe_earnings_rows(rows)

    assert len(out) == 1
    assert out.iloc[0]["id"] == "newest"
    assert int(out.iloc[0]["earnings_call_combined"]) == 19
    assert receipt["input_rows"] == 2
    assert receipt["output_rows"] == 1
    assert receipt["rejected_rows"] == 1
    assert receipt["duplicate_groups"][0]["selected"]["id"] == "newest"


def test_publish_refreshes_stale_manifest_when_either_store_advances(tmp_path):
    scores = tmp_path / "scores.parquet"
    history = tmp_path / "history.parquet"
    manifest = tmp_path / "manifest.json"
    pd.DataFrame([{"ticker": "AAA", "call_date": "2026-07-31"}]).to_parquet(
        scores, index=False
    )
    pd.DataFrame([
        {"document_ticker": "AAA", "call_date": "2026-04-30"},
        {"document_ticker": "AAA", "call_date": "2026-07-31"},
    ]).to_parquet(history, index=False)
    manifest.write_text(json.dumps({
        "schema": "earnings_intelligence_manifest.v2",
        "scores": {"md5": "stale"},
        "history": {"md5": "stale"},
    }))

    assert _refresh_manifest(manifest, scores, history) is True

    payload = json.loads(manifest.read_text())
    assert payload["scores"]["md5"] == _md5(scores)
    assert payload["scores"]["rows"] == 1
    assert payload["history"]["md5"] == _md5(history)
    assert payload["history"]["rows"] == 2


def test_score_only_publisher_preserves_prior_history_metadata(tmp_path):
    scores = tmp_path / "scores.parquet"
    history = tmp_path / "history.parquet"
    manifest = tmp_path / "manifest.json"
    pd.DataFrame([{"ticker": "AAA", "call_date": "2026-07-31"}]).to_parquet(
        scores, index=False
    )
    prior_history = {
        "rows": 50982,
        "tickers": 3529,
        "md5": "remote-history-md5",
        "bytes": 123456,
        "key": "earnings_calls/generations/prior-generation/history.parquet",
    }

    assert _refresh_manifest(
        manifest,
        scores,
        history,
        prior={
            "schema": "earnings_intelligence_manifest.v2",
            "scores": {"md5": "old-score-md5"},
            "history": prior_history,
        },
    ) is True

    payload = json.loads(manifest.read_text())
    assert payload["history"] == prior_history
    assert payload["scores"]["md5"] == _md5(scores)


def test_publish_leaves_current_manifest_untouched(tmp_path):
    scores = tmp_path / "scores.parquet"
    history = tmp_path / "history.parquet"
    manifest = tmp_path / "manifest.json"
    pd.DataFrame([{"ticker": "AAA", "call_date": "2026-07-31"}]).to_parquet(
        scores, index=False
    )
    pd.DataFrame([
        {"document_ticker": "AAA", "call_date": "2026-07-31"},
    ]).to_parquet(history, index=False)

    assert _refresh_manifest(manifest, scores, history) is True
    before = manifest.read_bytes()
    assert _refresh_manifest(manifest, scores, history) is False
    assert manifest.read_bytes() == before


def test_remote_md5_uses_manifest_for_legacy_multipart_object():
    class S3:
        @staticmethod
        def head_object(**_kwargs):
            return {"ETag": '"multipart-etag-5"', "Metadata": {}}

    assert _remote_md5(
        S3(),
        "bucket",
        "earnings_calls/history.parquet",
        filename="history.parquet",
        manifest={"history": {"md5": "content-hash"}},
    ) == "content-hash"


def test_remote_md5_prefers_explicit_metadata_for_multipart_object():
    class S3:
        @staticmethod
        def head_object(**_kwargs):
            return {
                "ETag": '"multipart-etag-5"',
                "Metadata": {"content-md5": "metadata-hash"},
            }

    assert _remote_md5(
        S3(),
        "bucket",
        "earnings_calls/history.parquet",
        filename="history.parquet",
        manifest={"history": {"md5": "manifest-hash"}},
    ) == "metadata-hash"


def test_publish_never_promotes_manifest_after_payload_failure(monkeypatch, tmp_path):
    earnings = tmp_path / "data" / "earnings_calls"
    earnings.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "AAA", "call_date": "2026-07-31",
    }]).to_parquet(earnings / "scores.parquet", index=False)
    pd.DataFrame([{
        "document_ticker": "AAA", "call_date": "2026-07-31",
    }]).to_parquet(earnings / "history.parquet", index=False)

    class S3:
        def __init__(self):
            self.uploaded: list[str] = []
            self.put_args: dict | None = None

        @staticmethod
        def get_object(**_kwargs):
            raise KeyError("no prior manifest")

        @staticmethod
        def head_object(**_kwargs):
            raise KeyError("object absent")

        def upload_file(self, _path, _bucket, key, ExtraArgs=None):  # noqa: N803
            self.uploaded.append(key)
            if key.endswith("history.parquet"):
                raise RuntimeError("simulated multipart upload failure")

    s3 = S3()
    monkeypatch.setattr(publish_mod, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert publish_mod.publish(data_dir=tmp_path / "data") == 1
    assert len(s3.uploaded) == 2
    assert s3.uploaded[0].endswith("/scores.parquet")
    assert s3.uploaded[1].endswith("/history.parquet")
    assert all("/generations/" in key for key in s3.uploaded)
    assert "earnings_calls/manifest.json" not in s3.uploaded


def test_publish_promotes_manifest_last_after_immutable_payloads(monkeypatch, tmp_path):
    earnings = tmp_path / "data" / "earnings_calls"
    earnings.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "AAA", "call_date": "2026-07-31",
    }]).to_parquet(earnings / "scores.parquet", index=False)
    pd.DataFrame([{
        "document_ticker": "AAA", "call_date": "2026-07-31",
    }]).to_parquet(earnings / "history.parquet", index=False)

    class S3:
        def __init__(self):
            self.uploaded: list[str] = []
            self.put_args: dict | None = None

        @staticmethod
        def get_object(**_kwargs):
            raise KeyError("no prior manifest")

        @staticmethod
        def head_object(**_kwargs):
            raise KeyError("object absent")

        def upload_file(self, _path, _bucket, key, ExtraArgs=None):  # noqa: N803
            self.uploaded.append(key)

        def put_object(self, **kwargs):
            self.put_args = kwargs
            self.uploaded.append(kwargs["Key"])

    s3 = S3()
    monkeypatch.setattr(publish_mod, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert publish_mod.publish(data_dir=tmp_path / "data") == 0
    assert s3.uploaded[-1] == "earnings_calls/manifest.json"
    assert all("/generations/" in key for key in s3.uploaded[:-1])
    assert [key.rsplit("/", 1)[-1] for key in s3.uploaded[:-1]] == [
        "scores.parquet", "history.parquet",
    ]
    assert s3.put_args is not None
    assert s3.put_args["IfNoneMatch"] == "*"
    assert "IfMatch" not in s3.put_args


def test_publish_manifest_cas_conflict_is_retryable(monkeypatch, tmp_path):
    earnings = tmp_path / "data" / "earnings_calls"
    earnings.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "AAA", "call_date": "2026-07-31",
    }]).to_parquet(earnings / "scores.parquet", index=False)

    class PreconditionFailed(RuntimeError):
        response = {
            "Error": {"Code": "PreconditionFailed"},
            "ResponseMetadata": {"HTTPStatusCode": 412},
        }

    class S3:
        def __init__(self):
            self.put_args: dict | None = None

        @staticmethod
        def get_object(**_kwargs):
            raise KeyError("no prior manifest")

        @staticmethod
        def head_object(**_kwargs):
            raise KeyError("object absent")

        @staticmethod
        def upload_file(*_args, **_kwargs):
            return None

        def put_object(self, **kwargs):
            self.put_args = kwargs
            raise PreconditionFailed("another producer promoted first")

    s3 = S3()
    monkeypatch.setattr(publish_mod, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert publish_mod.publish(data_dir=tmp_path / "data") == (
        publish_mod.PUBLISH_CONFLICT
    )
    assert s3.put_args is not None
    assert s3.put_args["IfNoneMatch"] == "*"


def test_publish_manifest_uses_hydrated_parent_etag_for_cas(monkeypatch, tmp_path):
    earnings = tmp_path / "data" / "earnings_calls"
    earnings.mkdir(parents=True)
    pd.DataFrame([{
        "ticker": "AAA", "call_date": "2026-07-31",
    }]).to_parquet(earnings / "scores.parquet", index=False)

    class S3:
        def __init__(self):
            self.put_args: dict | None = None

        @staticmethod
        def get_object(**_kwargs):
            return {
                "Body": _Body(json.dumps({
                    "schema": "earnings_intelligence_manifest.v3",
                    "generation_id": "prior",
                    "scores": {"md5": "prior"},
                    "history": None,
                }).encode()),
                "ETag": '"opaque-etag"',
            }

        @staticmethod
        def head_object(**_kwargs):
            raise KeyError("object absent")

        @staticmethod
        def upload_file(*_args, **_kwargs):
            return None

        def put_object(self, **kwargs):
            self.put_args = kwargs

    s3 = S3()
    monkeypatch.setattr(publish_mod, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert publish_mod.publish(
        data_dir=tmp_path / "data",
        expected_manifest_etag='"hydrated-parent-etag"',
    ) == 0
    assert s3.put_args is not None
    assert s3.put_args["IfMatch"] == '"hydrated-parent-etag"'
    assert "IfNoneMatch" not in s3.put_args


class _Body:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload


class _FetchS3:
    def __init__(self, manifest: dict, objects: dict[str, bytes]):
        self.manifest = manifest
        self.objects = objects
        self.downloads: list[str] = []

    def get_object(self, *, Bucket, Key):  # noqa: N803
        assert Bucket == "bucket"
        assert Key == "earnings_calls/manifest.json"
        return {"Body": _Body(json.dumps(self.manifest).encode())}

    def download_file(self, bucket, key, target):
        assert bucket == "bucket"
        self.downloads.append(key)
        with open(target, "wb") as handle:
            handle.write(self.objects[key])


def _write_generation(directory, ticker, history_rows=2):
    directory.mkdir(parents=True, exist_ok=True)
    scores = directory / "scores.parquet"
    history = directory / "history.parquet"
    pd.DataFrame([{
        "ticker": ticker,
        "call_date": "2026-07-31",
    }]).to_parquet(scores, index=False)
    pd.DataFrame([{
        "document_ticker": ticker,
        "call_date": f"2026-0{quarter}-15",
    } for quarter in range(1, history_rows + 1)]).to_parquet(history, index=False)
    manifest = _synth_manifest(scores, history)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_fetch_rejects_mixed_generation_without_touching_current(monkeypatch, tmp_path):
    local_dir = tmp_path / "data" / "earnings_calls"
    old_manifest = _write_generation(local_dir, "OLD")
    old_scores = (local_dir / "scores.parquet").read_bytes()
    old_history = (local_dir / "history.parquet").read_bytes()
    old_manifest_bytes = (local_dir / "manifest.json").read_bytes()

    remote_dir = tmp_path / "remote"
    remote_manifest = _write_generation(remote_dir, "NEW")
    corrupt_history = tmp_path / "corrupt-history.parquet"
    pd.DataFrame([{
        "document_ticker": "WRONG",
        "call_date": "2026-07-31",
    }]).to_parquet(corrupt_history, index=False)
    s3 = _FetchS3(remote_manifest, {
        remote_manifest["scores"]["key"]: (remote_dir / "scores.parquet").read_bytes(),
        remote_manifest["history"]["key"]: corrupt_history.read_bytes(),
    })
    monkeypatch.setattr(fetch_mod, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert fetch_mod.fetch(data_dir=tmp_path / "data") == 0
    assert (local_dir / "scores.parquet").read_bytes() == old_scores
    assert (local_dir / "history.parquet").read_bytes() == old_history
    assert (local_dir / "manifest.json").read_bytes() == old_manifest_bytes
    assert old_manifest["generation_id"] != remote_manifest["generation_id"]


def test_fetch_uses_manifest_hash_and_never_redownloads_multipart_etag(
    monkeypatch, tmp_path,
):
    local_dir = tmp_path / "data" / "earnings_calls"
    manifest = _write_generation(local_dir, "CURRENT")
    # No head_object/ETag method exists on this fake. A regression to ETag-based
    # freshness (which fails for multipart history) would crash or download.
    s3 = _FetchS3(manifest, {})
    monkeypatch.setattr(fetch_mod, "_client", lambda: s3)
    monkeypatch.setenv("R2_BUCKET", "bucket")

    assert fetch_mod.fetch(data_dir=tmp_path / "data") == 0
    assert s3.downloads == []
