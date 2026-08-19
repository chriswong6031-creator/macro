"""Research Vault Wave 4 — PR B: nothing becomes "processed" unless it PUBLISHED.

The vault is deliberately fail-soft per document: one unreadable PDF must never
abort a batch of 1,400. Wave 4 draws the line that was missing — fail soft on
DOCUMENTS, fail closed on the PUBLICATION PLANE — and pins it here.

  * **Defect 2 (P0)** — ``catalog.load`` returned ``empty()`` for a missing or
    corrupt catalog so a later ingest could "heal" it. That theory is false under
    receipt idempotency: ~1,400 historical PDFs are SKIPPED, so a run starting
    from empty admits only the new arrivals and republishes count≈2 with a fresh
    ``generated_at`` — storage corruption converted into authoritative data loss.
  * **Defect 5** — the canonical PDF ``put_bytes`` result was discarded, so a
    report could enter the catalog, the corpus and a receipt while its PDF did not
    exist. A Pro reader then gets a 404 from an apparently valid report.
  * **Defect 4** — ``catalog.write`` returned bytes on both the success and the
    failure path, so a failed catalog PUT still flushed receipts and still
    advanced the git mirror. Receipts are the thing that makes a document
    unre-ingestable, so that combination strands documents permanently.
  * **Defect 6** — the CLI was unconditionally never-raise and the workflow then
    discarded the rc it had captured, so an hour in which ingestion accomplished
    nothing concluded green twice over.

Every injected failure below is a STORE-level failure, because that is the layer
that actually fails in production (R2 rejects a put, credentials lapse, the object
vanishes) and the layer whose Boolean results were being dropped.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from engine.research_vault import catalog as catalog_mod
from engine.research_vault import corpus as corpus_mod
from engine.research_vault import ingest as ingest_mod
from engine.research_vault.r2_store import LocalStore

ROOT = Path(__file__).resolve().parents[1]

_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)


@pytest.fixture
def canned_pdftotext(monkeypatch):
    """Deterministic body text — the host's poppler must not decide these tests."""
    monkeypatch.setattr(ingest_mod, "extract_pdf_text",
                        lambda b: "credible pipeline capacity in texas")
    return True


def _seed_pdf(store, key: str, sidecar: dict) -> None:
    store.put_bytes(key, _PDF, "application/pdf")
    store.put_bytes(key[:-4] + ".json",
                    json.dumps(sidecar).encode("utf-8"), "application/json")


def _sidecar(doc_id: str, title: str = "A Report") -> dict:
    return {"id": doc_id, "title": title, "institution": "UBS", "side": "sell",
            "published_at": "2026-07-28T09:00:00Z",
            "summary_points": ["A point worth reading."]}


class FailingPutStore(LocalStore):
    """A LocalStore whose ``put_bytes`` refuses keys matching ``fail_on``.

    Mirrors the real failure shape exactly: R2Store.put_bytes catches its own
    exception and returns False, so a caller that ignores the Boolean sees a
    successful-looking call. Refusing (rather than raising) is what makes these
    tests reproduce the production defect rather than a different one.
    """

    fail_on: tuple = ()

    def put_bytes(self, key, data, content_type="application/octet-stream"):  # noqa: ANN001
        if any(pattern in key for pattern in self.fail_on):
            self.last_put_error = RuntimeError(f"injected put failure for {key}")
            return False
        return super().put_bytes(key, data, content_type)


def _store(tmp_path, fail_on=()) -> FailingPutStore:
    store = FailingPutStore(tmp_path / "store")
    store.fail_on = tuple(fail_on)
    return store


def _receipt_ids(store) -> set[str]:
    return {Path(k).stem for k in store.list_prefix(ingest_mod.PROCESSED_PREFIX)
            if k.endswith(".json")}


def _catalog_ids(store) -> set[str]:
    try:
        cat = catalog_mod.read_strict(store, check_future_clock=False,
                                      check_items=False)
    except catalog_mod.CatalogUnavailable:
        return set()
    # str() every id: one test deliberately plants an unhashable list id, and
    # the helper must observe that row rather than raise on it.
    return {str(it.get("id")) for it in cat.get("items") or []}


# ===========================================================================
# Defect 5 — a failed PDF promotion fails the ITEM, and only the item
# ===========================================================================

def test_failed_pdf_promotion_omits_the_report_everywhere(tmp_path, canned_pdftotext):
    """No catalog row, no corpus row, no receipt — and the batch keeps going."""
    store = _store(tmp_path, fail_on=("research_vault/bad-",))
    _seed_pdf(store, "research_inbox/bad.pdf", _sidecar("bad-000001"))
    _seed_pdf(store, "research_inbox/good.pdf", _sidecar("good-000002"))

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary["failed"] == 1
    assert summary["ingested"] == 1, "the next PDF in the batch must still process"

    assert "bad-000001" not in _catalog_ids(store)
    assert "good-000002" in _catalog_ids(store)
    assert "bad-000001" not in _receipt_ids(store)
    assert "good-000002" in _receipt_ids(store)
    assert not store.exists("research_vault/bad-000001.pdf")

    conn = corpus_mod.open_db(tmp_path / "corpus.sqlite")
    rows = {r[0] for r in conn.execute("SELECT doc_id FROM documents").fetchall()}
    conn.close()
    assert "bad-000001" not in rows, (
        "a report whose canonical PDF does not exist must not be searchable — that "
        "is the row a Pro reader opens and receives a 404 for"
    )


def test_a_failed_promotion_retries_cleanly_next_run(tmp_path, canned_pdftotext):
    """No receipt was written, so the document is NOT stranded."""
    store = _store(tmp_path, fail_on=("research_vault/bad-",))
    _seed_pdf(store, "research_inbox/bad.pdf", _sidecar("bad-000001"))
    ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert "bad-000001" not in _receipt_ids(store)

    store.fail_on = ()          # the store recovers
    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert summary["ingested"] == 1
    assert "bad-000001" in _catalog_ids(store)
    assert store.exists("research_vault/bad-000001.pdf")


# ===========================================================================
# Defect 4 — the publication commit gates receipts and the repo mirror
# ===========================================================================

def test_catalog_publish_failure_does_not_flush_receipts(tmp_path, canned_pdftotext):
    """PDF ok + corpus ok + catalog FAILED → nothing may be marked processed."""
    store = _store(tmp_path, fail_on=(catalog_mod.CATALOG_KEY,))
    _seed_pdf(store, "research_inbox/a.pdf", _sidecar("a-000001"))

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary["corpus_published"] is True
    assert summary["catalog_published"] is False
    assert summary["error"] == "catalog_publish_failed"
    assert summary["receipts_unflushed"] == 1
    assert _receipt_ids(store) == set(), (
        "a receipt makes a document unre-ingestable; writing one for content that "
        "never published strands it permanently"
    )
    assert store.exists("research_vault/a-000001.pdf"), "the PDF itself did publish"


def test_catalog_publish_failure_is_retried_and_completes_next_run(tmp_path,
                                                                   canned_pdftotext):
    store = _store(tmp_path, fail_on=(catalog_mod.CATALOG_KEY,))
    _seed_pdf(store, "research_inbox/a.pdf", _sidecar("a-000001"))
    ingest_mod.run(store, tmp_path / "corpus.sqlite")

    store.fail_on = ()
    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert summary["catalog_published"] is True
    assert summary["ingested"] == 1, "unreceipted, so it re-ingests cleanly"
    assert "a-000001" in _catalog_ids(store)
    assert "a-000001" in _receipt_ids(store)


def test_corpus_publish_failure_does_not_advance_the_catalog(tmp_path,
                                                             canned_pdftotext):
    """Corpus FAILED → the catalog must not admit rows search cannot answer for."""
    store = _store(tmp_path)
    _seed_pdf(store, "research_inbox/seed.pdf", _sidecar("seed-000001"))
    ingest_mod.run(store, tmp_path / "corpus.sqlite")      # a clean baseline
    store.fail_on = ("research_vault/corpus.sqlite",)      # now break the corpus

    before = _catalog_ids(store)
    _seed_pdf(store, "research_inbox/new.pdf", _sidecar("new-000002"))
    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary["corpus_published"] is False
    assert summary["catalog_published"] is False
    assert summary["error"] == "corpus_publish_failed"
    assert _catalog_ids(store) == before, "the prior catalog stays the authority"
    assert "new-000002" not in _receipt_ids(store)


def test_publish_result_separates_bytes_from_publication(tmp_path):
    """The Defect 4 root cause: a function returning bytes cannot express failure."""
    store = _store(tmp_path, fail_on=(catalog_mod.CATALOG_KEY,))
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, {"id": "x-1", "title": "T",
                                  "published_at": "2026-07-28T09:00:00Z"})
    result = catalog_mod.publish(store, cat)
    assert result.published is False
    assert result.data, "the serialized bytes are still available for inspection"
    assert result.error
    assert not store.exists(catalog_mod.CATALOG_KEY)


# ===========================================================================
# Defect 2 (P0) — a mature vault is never bootstrapped from empty
# ===========================================================================

def _mature_vault(tmp_path, canned=True):
    """A vault with published history: receipts, promoted PDFs, corpus, catalog."""
    store = _store(tmp_path)
    for n in range(3):
        _seed_pdf(store, f"research_inbox/hist{n}.pdf", _sidecar(f"hist-00000{n}"))
    ingest_mod.run(store, tmp_path / "corpus.sqlite")
    assert len(_receipt_ids(store)) == 3
    return store


def test_missing_catalog_over_a_mature_vault_refuses_to_publish(tmp_path,
                                                                canned_pdftotext):
    """THE P0. Storage corruption must not become fresh, published data loss."""
    store = _mature_vault(tmp_path)
    receipts_before = _receipt_ids(store)

    (Path(store.root) / catalog_mod.CATALOG_KEY).unlink()      # catalog disappears
    _seed_pdf(store, "research_inbox/new.pdf", _sidecar("new-000009"))

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary["error"] == "catalog_unavailable"
    assert summary["catalog_state"] == "unavailable"
    assert summary["vault_history"]["has_history"] is True
    assert summary["vault_history"]["receipts"] == 3
    # Nothing published, nothing receipted, nothing lost.
    assert not store.exists(catalog_mod.CATALOG_KEY), (
        "a truncated replacement catalog must NOT have been published"
    )
    assert _receipt_ids(store) == receipts_before, "receipts are untouched"
    assert summary.get("ingested", 0) == 0


@pytest.mark.parametrize("corrupt", [
    b"{not json",
    b"[]",
    b'{"schema": "research_vault.catalog.v2", "generated_at": "2026-07-28T09:00:00Z", "items": []}',
    b'{"schema": "research_vault.catalog.v1", "generated_at": "", "count": 0, "items": []}',
    b'{"schema": "research_vault.catalog.v1", "generated_at": "2026-07-28T09:00:00Z", "count": 0, "items": []}',
])
def test_corrupt_or_empty_catalog_over_a_mature_vault_refuses(tmp_path, corrupt,
                                                              canned_pdftotext):
    """Every input that would start the rebuild from ZERO rows is refused.

    The last case is the subtle one: a catalog that parses perfectly and is
    schema-valid, but carries no items. It clears every structural check and would
    otherwise sail straight into the same truncation the P0 describes.
    """
    store = _mature_vault(tmp_path)
    receipts_before = _receipt_ids(store)
    store.put_bytes(catalog_mod.CATALOG_KEY, corrupt, "application/json")

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary["error"] == "catalog_unavailable"
    assert _receipt_ids(store) == receipts_before
    assert store.get_bytes(catalog_mod.CATALOG_KEY) == corrupt, (
        "the damaged object is left exactly as found — recovery is an operator "
        "action against known-good evidence, never an automatic start-fresh"
    )


def test_a_malformed_ROW_does_not_refuse_the_run(tmp_path, canned_pdftotext):
    """One unidentifiable row truncates nothing, so it must not stop the lane.

    This is the other half of the line: refusing here would recreate the "one bad
    document kills the batch" failure the ingest module exists to avoid. Strict
    per-row validation is a SERVING rule (see catalog.validate).
    """
    store = _mature_vault(tmp_path)
    cat = catalog_mod.read_strict(store, check_future_clock=False, check_items=False)
    cat["items"].append({"id": ["not", "hashable"], "title": "Broken",
                         "published_at": "2026-07-28T09:00:00Z"})
    catalog_mod.publish(store, cat)

    _seed_pdf(store, "research_inbox/new.pdf", _sidecar("new-000009"))
    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary.get("error") is None
    assert summary["ingested"] == 1
    assert summary["catalog_published"] is True
    assert "new-000009" in _catalog_ids(store)


def test_genuine_first_bootstrap_is_still_allowed(tmp_path, canned_pdftotext):
    """An empty start is legitimate when the store can PROVE it never published."""
    store = _store(tmp_path)
    _seed_pdf(store, "research_inbox/first.pdf", _sidecar("first-000001"))

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")

    assert summary.get("error") is None
    assert summary["catalog_state"] == "bootstrap"
    assert summary["ingested"] == 1
    assert "first-000001" in _catalog_ids(store)
    assert "first-000001" in _receipt_ids(store)


def test_history_probe_failure_counts_as_history(tmp_path, canned_pdftotext):
    """Fail CLOSED: an unlistable store cannot prove it is virgin."""

    class UnlistableStore(FailingPutStore):
        def list_prefix(self, prefix):  # noqa: ANN001, ANN201
            if prefix == ingest_mod.PROCESSED_PREFIX:
                raise ConnectionError("listing unavailable")
            return super().list_prefix(prefix)

    store = UnlistableStore(tmp_path / "store")
    store.fail_on = ()
    _seed_pdf(store, "research_inbox/first.pdf", _sidecar("first-000001"))

    summary = ingest_mod.run(store, tmp_path / "corpus.sqlite")
    # The receipt probe raises, so we cannot prove this store is virgin.
    assert summary["error"] == "catalog_unavailable"
    assert summary["vault_history"]["probe_failed"] is True
    assert not store.exists(catalog_mod.CATALOG_KEY)


# ===========================================================================
# Defect 6 — plane failures exit non-zero; document failures do not
# ===========================================================================

def _run_cli(tmp_path, store_root: Path, *extra: str) -> subprocess.CompletedProcess:
    """Run the real CLI as a subprocess, with its repo snapshots redirected.

    --repo-dir is NOT optional hygiene here. Without it a scratch-store run
    snapshots its two-document vault straight over the committed
    data/research_vault/catalog.json — which is exactly how writing these tests
    truncated the live 1,402-row mirror to 1 row.
    """
    return subprocess.run(
        [sys.executable, "-m", "scripts.ingest_research", "--local", str(store_root),
         "--corpus", str(tmp_path / "cli_corpus.sqlite"),
         "--repo-dir", str(tmp_path / "repo_snapshot"), *extra],
        cwd=ROOT, capture_output=True, text=True, timeout=180,
    )


def test_cli_exits_zero_when_only_a_DOCUMENT_failed(tmp_path):
    """One unusable PDF must never red the hourly lane."""
    store = LocalStore(tmp_path / "store")
    store.put_bytes("research_inbox/broken.pdf", b"not a pdf at all", "application/pdf")
    store.put_bytes("research_inbox/broken.json", b"{bad json", "application/json")

    proc = _run_cli(tmp_path, Path(store.root))
    assert proc.returncode == 0, proc.stderr[-2000:]


def test_cli_exits_nonzero_when_the_catalog_publish_failed(tmp_path, monkeypatch):
    """The plane failed, so the lane must be red even though documents were fine."""
    store = LocalStore(tmp_path / "store")
    _seed_pdf(store, "research_inbox/a.pdf", _sidecar("a-000001"))
    # Make the catalog key unwritable: a directory cannot be replaced by a file.
    (Path(store.root) / catalog_mod.CATALOG_KEY).mkdir(parents=True, exist_ok=True)

    proc = _run_cli(tmp_path, Path(store.root))
    assert proc.returncode == 1, (
        f"expected a plane failure to exit 1\nstdout={proc.stdout[-2000:]}\n"
        f"stderr={proc.stderr[-2000:]}"
    )
    assert "publication plane FAILED" in proc.stdout


def test_cli_exits_nonzero_with_require_store_and_no_store(tmp_path, monkeypatch):
    """On the scheduled run, 'no store' means the secrets never arrived."""
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ingest_research", "--require-store"],
        cwd=ROOT, capture_output=True, text=True, timeout=180, env=env,
    )
    assert proc.returncode == 1
    assert "no research store configured" in proc.stdout


def test_cli_exits_zero_without_require_store_and_no_store(tmp_path):
    """A developer box genuinely has nothing to do — unchanged behavior."""
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.ingest_research"],
        cwd=ROOT, capture_output=True, text=True, timeout=180, env=env,
    )
    assert proc.returncode == 0


def test_cli_does_not_advance_the_repo_mirror_on_a_plane_failure(tmp_path,
                                                                 monkeypatch):
    """Freeze §B: the git mirror may never be independently newer than R2."""
    import scripts.ingest_research as cli

    mirror = tmp_path / "repo" / "catalog.json"
    mirror.parent.mkdir(parents=True)
    mirror.write_bytes(b'{"schema": "research_vault.catalog.v1", "sentinel": true}\n')
    monkeypatch.setattr(ingest_mod, "extract_pdf_text", lambda b: "body text here")

    store = _store(tmp_path, fail_on=(catalog_mod.CATALOG_KEY,))
    _seed_pdf(store, "research_inbox/a.pdf", _sidecar("a-000001"))
    monkeypatch.setattr(sys, "argv", ["ingest_research", "--local", str(store.root),
                                      "--corpus", str(tmp_path / "c.sqlite"),
                                      "--repo-dir", str(mirror.parent)])
    # --local builds a plain LocalStore, so point the CLI at our failing one.
    monkeypatch.setattr("engine.research_vault.r2_store.build_store",
                        lambda local_dir=None: store)

    rc = cli.main()
    assert rc == 1
    assert json.loads(mirror.read_text())["sentinel"] is True, (
        "the mirror must still hold the last FULLY PUBLISHED generation"
    )


def test_cli_advances_the_repo_mirror_on_success(tmp_path, monkeypatch):
    import scripts.ingest_research as cli

    mirror = tmp_path / "repo" / "catalog.json"
    mirror.parent.mkdir(parents=True)
    mirror.write_bytes(b'{"sentinel": true}\n')
    monkeypatch.setattr(ingest_mod, "extract_pdf_text", lambda b: "body text here")

    store = _store(tmp_path)
    _seed_pdf(store, "research_inbox/a.pdf", _sidecar("a-000001"))
    monkeypatch.setattr(sys, "argv", ["ingest_research", "--local", str(store.root),
                                      "--corpus", str(tmp_path / "c.sqlite"),
                                      "--repo-dir", str(mirror.parent)])
    monkeypatch.setattr("engine.research_vault.r2_store.build_store",
                        lambda local_dir=None: store)

    rc = cli.main()
    assert rc == 0
    written = json.loads(mirror.read_text())
    assert [it["id"] for it in written["items"]] == ["a-000001"]


# ===========================================================================
# the workflow re-emits the rc it captured
# ===========================================================================

def test_workflow_fails_the_lane_on_a_nonzero_ingest_rc():
    """Exercised as CONTROL FLOW, not as a grep for `exit 1`.

    The pre-Wave-4 workflow already captured the rc into a step output and then
    never read it, which is exactly the shape a naive grep would have called
    healthy. So this test runs the guard step's real shell body under both rcs.
    """
    import re
    wf = (ROOT / ".github" / "workflows" / "research-ingest.yml").read_text(
        encoding="utf-8")

    # The salvage step must still run regardless of the ingest outcome...
    assert re.search(r"name: commit catalog snapshot \(salvage-push\)\s*\n\s*if: always\(\)",
                     wf), "salvage must remain if: always()"
    # ...and the failure step must come AFTER it, also always().
    assert wf.index("commit catalog snapshot (salvage-push)") < \
        wf.index("fail the lane if ingestion failed"), (
        "the lane may only fail AFTER salvage has had its chance to push"
    )

    body = wf.split("fail the lane if ingestion failed", 1)[1]
    body = body.split("run: |", 1)[1]
    script = "\n".join(line[10:] for line in body.splitlines() if line.strip())

    for rc, expected in (("0", 0), ("1", 1), ("", 1)):
        proc = subprocess.run(
            ["bash", "-c", script.replace("${{ steps.ingest.outputs.rc }}", rc)],
            capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == expected, (
            f"rc={rc!r} should exit {expected}; got {proc.returncode}\n{proc.stdout}"
        )


def test_workflow_passes_require_store_on_the_scheduled_run():
    wf = (ROOT / ".github" / "workflows" / "research-ingest.yml").read_text(
        encoding="utf-8")
    assert "python -m scripts.ingest_research --require-store" in wf


def test_repo_snapshot_dir_is_overridable_and_defaults_to_the_committed_mirror(
        tmp_path, monkeypatch):
    """The guard that keeps a scratch run out of the live mirror.

    Writing this file's CLI tests truncated data/research_vault/catalog.json from
    1,402 rows to 1, because a `--local` subprocess snapshotted its two-document
    scratch vault over the real path. A store override without a matching snapshot
    override is a footgun; this pins that the override exists and wins.
    """
    import scripts.ingest_research as cli

    monkeypatch.delenv("RESEARCH_REPO_SNAPSHOT_DIR", raising=False)
    assert cli._repo_snapshot_dir() == cli._REPO_SNAPSHOT_DIR
    assert cli._repo_snapshot_dir().parts[-2:] == ("data", "research_vault")

    monkeypatch.setenv("RESEARCH_REPO_SNAPSHOT_DIR", str(tmp_path / "env"))
    assert cli._repo_snapshot_dir() == tmp_path / "env"
    # An explicit flag beats the environment.
    assert cli._repo_snapshot_dir(str(tmp_path / "flag")) == tmp_path / "flag"


def test_committed_mirror_is_not_written_by_the_cli_tests():
    """Belt: the live mirror must still hold a real vault after this module runs."""
    mirror = ROOT / "data" / "research_vault" / "catalog.json"
    if not mirror.is_file():
        pytest.skip("sparse checkout — data/ not materialized")
    obj = json.loads(mirror.read_text(encoding="utf-8"))
    assert obj.get("count", 0) > 100, (
        f"the committed mirror holds {obj.get('count')} rows — a test wrote its "
        f"scratch vault over the real catalog (use --repo-dir)"
    )


# ===========================================================================
# the correction-audit census (read-only)
# ===========================================================================

def test_census_reports_every_mismatch_direction_and_never_mutates(tmp_path,
                                                                    canned_pdftotext,
                                                                    monkeypatch):
    """The audit must CLASSIFY mismatches, not force the sets equal — and it must
    be provably read-only, because it runs against the live production vault."""
    import scripts.research_vault_census as census

    store = _store(tmp_path)
    for n in range(3):
        _seed_pdf(store, f"research_inbox/d{n}.pdf", _sidecar(f"desk-00000{n}"))
    ingest_mod.run(store, tmp_path / "corpus.sqlite")

    # Manufacture one of each direction.
    (Path(store.root) / "research_vault" / "desk-000000.pdf").unlink()
    cat = catalog_mod.read_strict(store, check_future_clock=False, check_items=False)
    cat["items"] = [it for it in cat["items"] if it["id"] != "desk-000001"]
    catalog_mod.publish(store, cat)

    before = {k: store.get_bytes(k) for k in store.list_prefix("")}

    out = tmp_path / "census.json"
    # --repo-dir travels with --local: comparing a scratch store against the REAL
    # committed mirror prints a nonsense lag and can raise a false freeze-§B alarm.
    monkeypatch.setattr(sys, "argv", ["census", "--local", str(store.root),
                                      "--repo-dir", str(tmp_path / "no_mirror"),
                                      "--json", str(out)])
    monkeypatch.setattr("engine.research_vault.r2_store.build_store",
                        lambda local_dir=None: store)
    assert census.main() == 0

    report = json.loads(out.read_text())
    mm = report["mismatches"]
    assert mm["catalog_minus_pdf"] == ["desk-000000"]
    assert mm["receipt_minus_catalog"] == ["desk-000001"]
    assert mm["corpus_minus_catalog"] == ["desk-000001"]
    assert mm["pdf_minus_catalog"] == ["desk-000001"]
    # The receipt's source key is what makes a stranded row deterministically
    # recoverable instead of a guess.
    assert report["recovery_sources"]["desk-000001"] == "research_inbox/d1.pdf"
    assert report["repo_mirror"] == {"present": False}, (
        "an absent --repo-dir mirror must read as absent, never fall back to the "
        "real committed one"
    )

    after = {k: store.get_bytes(k) for k in store.list_prefix("")}
    assert after == before, "the census must not mutate a single object"


def test_census_refuses_rather_than_auditing_an_unreadable_catalog(tmp_path,
                                                                   monkeypatch):
    import scripts.research_vault_census as census

    store = _store(tmp_path)
    store.put_bytes(catalog_mod.CATALOG_KEY, b"{broken", "application/json")
    monkeypatch.setattr(sys, "argv", ["census", "--local", str(store.root)])
    monkeypatch.setattr("engine.research_vault.r2_store.build_store",
                        lambda local_dir=None: store)
    assert census.main() == 1
