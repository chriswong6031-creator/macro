"""Research Vault Wave 4 — PR A: the catalog is TRUTHFUL about its own freshness.

Three defects are pinned here, all of the same shape: a successful operation was
being read as evidence of a healthy, current catalog.

  * **Defect 1** — a successful store read of an ARBITRARILY OLD object was
    healthy, because the only staleness signal was "did the refresh throw". The
    browser then printed "This week · Updated hourly" over a catalog of any age.
    Freshness now comes from the producer clock (``generated_at``), which the
    hourly ingest rewrites every run even when it admits no new report — so it is
    the only field that ticks once an hour whether or not the vault changed.
  * **Defect 3** — ``catalog.load`` degrades a MISSING or CORRUPT catalog to
    ``empty()``, and the serving tier could not tell that apart from a vault that
    legitimately holds zero reports. ``read_strict`` fails closed instead, using
    the existing ``get_bytes_strict`` boundary where ``None`` means only "the
    backing service authoritatively reported this key absent".
  * the **visibility invariant** — the catalog is the publication commit, and the
    corpus is published BEFORE it, so a corpus row can legitimately run ahead of
    the public inventory. Every tier's search is now filtered to catalog-admitted
    ids; before this wave only the non-Pro branch was.

The boundary cases matter more than the happy path here: a legitimately EMPTY
vault (valid schema, recent clock, ``items: []``) must stay FRESH, or this whole
contract would have converted an honest empty state into a false outage.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from engine.research_vault import catalog as catalog_mod
from engine.research_vault.r2_store import LocalStore

ROOT = Path(__file__).resolve().parents[1]

_NOW = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


def _cat(generated_at: str, items: list | None = None, schema: str = catalog_mod.SCHEMA) -> dict:
    """A catalog document with an explicitly controlled producer clock."""
    items = [] if items is None else items
    return {
        "schema": schema,
        "generated_at": generated_at,
        "count": len(items),
        "institutions": [],
        "items": items,
    }


def _item(doc_id: str = "desk-2026-08-19-note") -> dict:
    return {"id": doc_id, "title": "A Note", "institution": "Desk",
            "side": "sell", "published_at": "2026-08-19T09:00:00Z"}


def _iso(delta: timedelta) -> str:
    return (_NOW + delta).isoformat()


# ===========================================================================
# validate() — the structural + producer-clock contract
# ===========================================================================

def test_fresh_nonempty_catalog_validates():
    cat = _cat(_iso(timedelta(minutes=-5)), [_item()])
    assert catalog_mod.validate(cat, now=_NOW) is cat


def test_legitimate_zero_report_vault_is_valid_and_fresh():
    """A real empty vault is a VALID FRESH state, not a failure.

    This is the case the strict contract most easily gets wrong: the whole point
    of Defect 3 is that corruption used to look like emptiness, and an
    over-eager fix would make emptiness look like corruption instead. A vault
    with a recent clock and no reports is honest, and must serve as fresh.
    """
    cat = _cat(_iso(timedelta(minutes=-1)), [])
    assert catalog_mod.validate(cat, now=_NOW) is cat
    health = catalog_mod.health(cat, now=_NOW)
    assert health["state"] == catalog_mod.STATE_FRESH
    assert cat["count"] == 0


@pytest.mark.parametrize("bad_schema", ["research_vault.catalog.v2", "", None, "nope"])
def test_wrong_schema_is_unavailable(bad_schema):
    cat = _cat(_iso(timedelta(minutes=-5)), [_item()], schema=bad_schema)
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.validate(cat, now=_NOW)
    assert exc.value.reason == "schema_mismatch"


@pytest.mark.parametrize("items", [
    "not-a-list",
    {"id": "x"},
    None,
    42,
])
def test_items_must_be_a_list(items):
    cat = _cat(_iso(timedelta(minutes=-5)))
    cat["items"] = items
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.validate(cat, now=_NOW)
    assert exc.value.reason == "malformed_items"


@pytest.mark.parametrize("bad_item", [
    "a string row",
    None,
    ["nested"],
    {"title": "no id at all"},
    {"id": ""},
    {"id": "   "},
    {"id": 17},
    {"id": ["list-id"]},
])
def test_malformed_item_invalidates_the_catalog(bad_item):
    """One unusable row invalidates the whole answer — it is not skipped.

    The catalog's only job at the serving tier is to say WHICH ids are admitted.
    A row we cannot identify means the admitted set is unknown, and silently
    dropping it would publish a smaller inventory while reporting success.
    """
    cat = _cat(_iso(timedelta(minutes=-5)), [_item(), bad_item])
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.validate(cat, now=_NOW)
    assert exc.value.reason == "malformed_items"


def test_derived_count_drift_does_not_invalidate():
    """A stale derived `count` is a cosmetic nit, never an outage.

    ``_reindex`` rewrites count/institutions on every publish, so a disagreement
    is not evidence the item set is untrustworthy — and the serving tier reads
    the items themselves. Raising here would turn drift into a 503.
    """
    cat = _cat(_iso(timedelta(minutes=-5)), [_item()])
    cat["count"] = 999
    cat.pop("institutions")
    assert catalog_mod.validate(cat, now=_NOW) is cat


def test_blank_generated_at_is_unavailable():
    """The signature of a published `empty()` — the Defect 2 fault, seen from the API."""
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.validate(_cat("", [_item()]), now=_NOW)
    assert exc.value.reason == "blank_generated_at"


@pytest.mark.parametrize("raw", ["   ", None, 12345, [], "not-a-date", "2026-13-45T99:99:99Z"])
def test_unparseable_generated_at_is_unavailable(raw):
    cat = _cat(_iso(timedelta(minutes=-5)), [_item()])
    cat["generated_at"] = raw
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.validate(cat, now=_NOW)
    assert exc.value.reason in {"blank_generated_at", "unparseable_generated_at"}


def test_materially_future_producer_clock_is_unavailable():
    cat = _cat(_iso(timedelta(minutes=30)), [_item()])
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.validate(cat, now=_NOW)
    assert exc.value.reason == "future_generated_at"


def test_benign_clock_skew_inside_tolerance_is_accepted():
    """Producer and server hosts differ by seconds; that must not be an outage."""
    cat = _cat(_iso(timedelta(minutes=2)), [_item()])
    assert catalog_mod.validate(cat, now=_NOW) is cat
    assert catalog_mod.health(cat, now=_NOW)["state"] == catalog_mod.STATE_FRESH


# ===========================================================================
# health() — the fresh / stale split
# ===========================================================================

@pytest.mark.parametrize("age,expected", [
    (timedelta(minutes=1), catalog_mod.STATE_FRESH),
    (timedelta(minutes=30), catalog_mod.STATE_FRESH),
    (timedelta(hours=1, minutes=59), catalog_mod.STATE_FRESH),
    (timedelta(hours=2), catalog_mod.STATE_FRESH),            # boundary: inclusive
    (timedelta(hours=2, seconds=1), catalog_mod.STATE_STALE),  # first stale second
    (timedelta(hours=3), catalog_mod.STATE_STALE),
    (timedelta(days=9), catalog_mod.STATE_STALE),
])
def test_freshness_is_read_from_the_producer_clock(age, expected):
    cat = _cat(_iso(-age), [_item()])
    health = catalog_mod.health(cat, now=_NOW)
    assert health["state"] == expected
    assert health["age_seconds"] == int(age.total_seconds())
    assert (health["reason"] == "") is (expected == catalog_mod.STATE_FRESH)


def test_freshness_ignores_the_newest_item_published_at():
    """A nine-day-old REPORT in a catalog rebuilt one minute ago is FRESH.

    The producer rewrites the catalog hourly regardless of new arrivals, so the
    newest ``published_at`` measures the desks' output, not our pipeline's
    liveness. Keying freshness on it would red a correctly-running vault during
    any quiet week.
    """
    old_report = _item()
    old_report["published_at"] = (_NOW - timedelta(days=9)).isoformat()
    cat = _cat(_iso(timedelta(minutes=-1)), [old_report])
    assert catalog_mod.health(cat, now=_NOW)["state"] == catalog_mod.STATE_FRESH


def test_explicit_reason_forces_stale_however_young_the_copy():
    """A copy we could not re-verify is never presentable as live."""
    cat = _cat(_iso(timedelta(seconds=-30)), [_item()])
    health = catalog_mod.health(cat, now=_NOW, reason="store_error")
    assert health["state"] == catalog_mod.STATE_STALE
    assert health["reason"] == "store_error"


# ===========================================================================
# read_strict() — unavailable is never absence
# ===========================================================================

def test_read_strict_round_trips_a_published_catalog(tmp_path):
    store = LocalStore(tmp_path / "store")
    cat = catalog_mod.empty()
    catalog_mod.upsert_item(cat, _item())
    catalog_mod.publish(store, cat)
    loaded = catalog_mod.read_strict(store)
    assert [it["id"] for it in loaded["items"]] == [_item()["id"]]


def test_authoritative_miss_raises_missing_not_empty(tmp_path):
    """The exact case ``load()`` degrades to ``empty()``."""
    store = LocalStore(tmp_path / "store")
    assert catalog_mod.load(store) == catalog_mod.empty()      # documented old behavior
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.read_strict(store)
    assert exc.value.reason == "missing"


def test_malformed_json_raises_rather_than_starting_fresh(tmp_path):
    store = LocalStore(tmp_path / "store")
    store.put_bytes(catalog_mod.CATALOG_KEY, b"{not json at all", "application/json")
    assert catalog_mod.load(store) == catalog_mod.empty()      # documented old behavior
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.read_strict(store)
    assert exc.value.reason == "malformed_json"


def test_store_operational_failure_is_not_a_miss(tmp_path):
    """A timeout/credential failure must NOT read as 'the catalog does not exist'."""

    class BrokenStore(LocalStore):
        def get_bytes_strict(self, key):  # noqa: ANN001, ANN201
            raise TimeoutError("R2 read timed out")

    store = BrokenStore(tmp_path / "store")
    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.read_strict(store)
    assert exc.value.reason == "store_error"
    assert "TimeoutError" in exc.value.detail


def test_store_without_strict_reads_fails_closed():
    """No strict primitive → we cannot tell absence from outage → refuse."""

    class FailOpenOnly:
        def get_bytes(self, key):  # noqa: ANN001, ANN201
            return None

    with pytest.raises(catalog_mod.CatalogUnavailable) as exc:
        catalog_mod.read_strict(FailOpenOnly())
    assert exc.value.reason == "store_unavailable"


def test_none_store_fails_closed():
    with pytest.raises(catalog_mod.CatalogUnavailable):
        catalog_mod.read_strict(None)


# ===========================================================================
# the real published catalog must survive the new validator
# ===========================================================================

def test_committed_repo_mirror_validates():
    """The live 1,400-row mirror must pass — a validator that reds production is
    worse than the defect it fixes. Skipped on a sparse checkout, where the
    omitted ``data/`` tree has no bytes on disk to read."""
    mirror = ROOT / "data" / "research_vault" / "catalog.json"
    if not mirror.is_file():
        pytest.skip("sparse checkout — data/ not materialized")
    obj = json.loads(mirror.read_text(encoding="utf-8"))
    generated = catalog_mod.parse_generated_at(obj.get("generated_at"))
    # Validate against the mirror's OWN clock: the committed snapshot ages with
    # the repo, so asserting it is fresh today would rot within two hours.
    catalog_mod.validate(obj, now=generated)
    assert obj["items"], "the committed mirror should not be empty"
