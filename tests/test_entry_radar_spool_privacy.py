"""W4.2 / LER-C1 — the private evidence-spool boundary contract.

``DSC:RADAR-SPOOL-PUBLIC-R2`` proved the canonical Radar evidence spool
(``live_flow/entry_radar_events/**``) anonymously readable on the public R2
dev host: the shared ``$R2_BUCKET`` bucket is exposed bucket-wide, so ANY
evidence key written through the shared client is world-readable regardless
of classification.  The structural repair (masterplan §3.4) routes raw
evidence keys through a DEDICATED private store (``ENTRY_RADAR_R2_*`` — the
same four-name shape as the accepted BioCatalyst/13F dedicated-store
precedents) resolved by the module's ONE client builder, and REFUSES the
shared bucket for evidence writes when the dedicated store is unconfigured.

The RED regression here is the commission's step 3: Radar raw evidence can
never route through an explicitly public delivery classification —
neither in code (the write path) nor in the delivery-plane registry (the
classification owner).
"""
from __future__ import annotations

import json

import pytest

from engine.entry_radar import spool as sp

_SHARED_ENV = {
    "R2_ENDPOINT": "https://shared.example.invalid",
    "R2_ACCESS_KEY_ID": "shared-key",
    "R2_SECRET_ACCESS_KEY": "shared-secret",
    "R2_BUCKET": "mastermindx",
}
_EVIDENCE_ENV = {
    "ENTRY_RADAR_R2_ENDPOINT": "https://evidence.example.invalid",
    "ENTRY_RADAR_R2_ACCESS_KEY_ID": "evidence-key",
    "ENTRY_RADAR_R2_SECRET_ACCESS_KEY": "evidence-secret",
    "ENTRY_RADAR_R2_BUCKET": "entry-radar-evidence",
}

EVENT_KEY = "live_flow/entry_radar_events/2026-08-28/120000-entry_radar_live.json"
NOMINATION_KEY = "live_flow/entry_radar_nominations/2026-08-28/120000-pass.json"


class _RecordingS3:
    """Plain-method fake, same convention as ``ExplodingR2`` in the W4 lane."""

    def __init__(self) -> None:
        self.puts: list[tuple[str, str]] = []

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_kw) -> None:
        self.puts.append((Bucket, Key))


def _set_env(monkeypatch, mapping: dict[str, str]) -> None:
    for name in {**_SHARED_ENV, **_EVIDENCE_ENV}:
        monkeypatch.delenv(name, raising=False)
    for name, value in mapping.items():
        monkeypatch.setenv(name, value)


# =============================================================================
# key classification
# =============================================================================
def test_both_raw_evidence_prefixes_are_evidence_keys():
    assert sp.is_evidence_key(EVENT_KEY)
    assert sp.is_evidence_key(NOMINATION_KEY)
    assert sp.is_evidence_key("live_flow/entry_radar_events")
    # A sibling live_flow product key is NOT evidence — the boundary is exact.
    assert not sp.is_evidence_key("live_flow/feed_current.json")
    assert not sp.is_evidence_key("live_flow/entry_radar_events_other/x.json")


# =============================================================================
# RED regression — the write path refuses the shared public-classified bucket
# =============================================================================
def test_evidence_write_refuses_shared_bucket_when_store_unconfigured(
        monkeypatch, tmp_path, capsys):
    """Shared creds present, dedicated store absent: the R2 leg is REFUSED
    (never a shared-bucket put — no client is even built) and the write falls
    to the local spool, with the refusal printed at line start."""
    _set_env(monkeypatch, _SHARED_ENV)
    monkeypatch.setenv("ENTRY_RADAR_SPOOL_DIR", str(tmp_path))

    def _forbidden(*_a, **_k):  # pragma: no cover - failure branch
        raise AssertionError("a client must never be built for a refused evidence write")

    monkeypatch.setattr(sp, "_build_client", _forbidden)
    spool = sp.NominationSpool(prefix="live_flow/entry_radar_events")
    assert spool._put(EVENT_KEY, {"schema": "x"}) is True
    assert (tmp_path / EVENT_KEY).is_file()
    out = capsys.readouterr().out
    assert any(line.startswith("::warning") and "refusing" in line
               for line in out.splitlines())


def test_evidence_write_withheld_not_shared_when_no_local_fallback(
        monkeypatch, capsys):
    _set_env(monkeypatch, _SHARED_ENV)
    monkeypatch.delenv("ENTRY_RADAR_SPOOL_DIR", raising=False)
    monkeypatch.setattr(sp, "_build_client",
                        lambda *a, **k: pytest.fail("no client may be built"))
    spool = sp.NominationSpool(local_dir=None, prefix="live_flow/entry_radar_events")
    assert spool._put(EVENT_KEY, {"schema": "x"}) is False
    out = capsys.readouterr().out
    assert "ENTRY_RADAR_R2_*" in out and "NOT spooled" in out


def test_partial_dedicated_config_counts_as_absent(monkeypatch):
    partial = {**_EVIDENCE_ENV}
    partial.pop("ENTRY_RADAR_R2_BUCKET")
    _set_env(monkeypatch, {**_SHARED_ENV, **partial})
    assert sp.evidence_credentials_present() is False
    assert sp.evidence_bucket_name() is None


# =============================================================================
# the dedicated store is used when configured — writer success
# =============================================================================
def test_evidence_write_uses_dedicated_bucket_and_credentials(monkeypatch):
    _set_env(monkeypatch, {**_SHARED_ENV, **_EVIDENCE_ENV})
    fake = _RecordingS3()
    built_with: list[str] = []

    def _capture(ep, ak, sk):
        built_with.append(ep)
        return fake

    monkeypatch.setattr(sp, "_build_client", _capture)
    spool = sp.NominationSpool(prefix="live_flow/entry_radar_events")
    assert spool._put(EVENT_KEY, {"schema": "x"}) is True
    assert fake.puts == [("entry-radar-evidence", EVENT_KEY)]
    assert built_with == ["https://evidence.example.invalid"]


def test_non_evidence_key_still_uses_shared_ladder(monkeypatch):
    _set_env(monkeypatch, {**_SHARED_ENV, **_EVIDENCE_ENV})
    fake = _RecordingS3()
    built_with: list[str] = []

    def _capture(ep, ak, sk):
        built_with.append(ep)
        return fake

    monkeypatch.setattr(sp, "_build_client", _capture)
    spool = sp.NominationSpool(prefix="live_flow/other_family")
    assert spool._put("live_flow/other_family/2026-08-28/x.json", {"schema": "x"})
    assert fake.puts == [("mastermindx", "live_flow/other_family/2026-08-28/x.json")]
    assert built_with == ["https://shared.example.invalid"]


# =============================================================================
# read seam — Lab and W5 resolve the same private destination
# =============================================================================
def test_read_seam_resolves_dedicated_store_for_evidence_prefix(monkeypatch):
    _set_env(monkeypatch, {**_SHARED_ENV, **_EVIDENCE_ENV})
    assert sp.r2_bucket_name("live_flow/entry_radar_events") == "entry-radar-evidence"
    assert sp.r2_bucket_name() == "mastermindx"
    assert sp.r2_credentials_present("live_flow/entry_radar_events") is True

    built_with: list[str] = []
    monkeypatch.setattr(sp, "_build_client",
                        lambda ep, ak, sk: built_with.append(ep) or _RecordingS3())
    sp.r2_client_for_read("live_flow/entry_radar_events")
    assert built_with == ["https://evidence.example.invalid"]


def test_read_seam_legacy_shared_fallback_is_authenticated_reads_only(monkeypatch):
    """With the dedicated store unconfigured, an evidence READ may still use
    the shared authenticated client (historical envelopes live there) — the
    compatibility path the contract requires — while the WRITE path above
    refuses.  Never an anonymous fallback: it is the same boto3 credential
    seam either way."""
    _set_env(monkeypatch, _SHARED_ENV)
    assert sp.r2_credentials_present("live_flow/entry_radar_events") is True
    assert sp.r2_bucket_name("live_flow/entry_radar_events") == "mastermindx"


def test_lab_resolver_reports_the_dedicated_bucket(monkeypatch):
    from engine.prophet_lab import sources as src

    _set_env(monkeypatch, {**_SHARED_ENV, **_EVIDENCE_ENV})

    class _EmptyList:
        def list_objects_v2(self, **_kw):
            return {"Contents": [], "IsTruncated": False}

    result = src.resolve_radar_spool(None, s3=_EmptyList())
    assert result.backend == "r2"
    assert result.bucket == "entry-radar-evidence"
    assert result.error is None


def test_w5_read_seam_consumes_a_private_destination_envelope(monkeypatch, tmp_path):
    """W5's ``read_spool_events`` validates the identical envelope fetched
    back from the dedicated store — identity preserved through the private
    destination (the C3 production transport rebind is a separate wave; this
    pins the seam)."""
    from scripts import reconcile_entry_radar as rec

    _set_env(monkeypatch, {**_SHARED_ENV, **_EVIDENCE_ENV})

    stored: dict[str, bytes] = {}

    class _Store:
        def put_object(self, *, Bucket, Key, Body, **_kw):
            assert Bucket == "entry-radar-evidence"
            stored[Key] = Body

        def get_object(self, *, Bucket, Key):
            assert Bucket == "entry-radar-evidence"
            return {"Body": stored[Key]}

    store = _Store()
    monkeypatch.setattr(sp, "_build_client", lambda *a, **k: store)
    envelope = {
        "schema": "entry_radar.events/v1",
        "pass_ts": "2026-08-28T14:00:00Z",
        "pass_id": "pass-1",
        "events": [],
        "transitions": [],
    }
    spool = sp.NominationSpool(prefix="live_flow/entry_radar_events")
    assert spool._put(EVENT_KEY, envelope) is True

    raw = sp.get_r2_object_bytes(store, EVENT_KEY,
                                 bucket=sp.r2_bucket_name(EVENT_KEY))
    assert json.loads(raw) == envelope
    target = tmp_path / "live_flow" / "entry_radar_events" / "2026-08-28"
    target.mkdir(parents=True)
    (target / "120000-entry_radar_live.json").write_bytes(raw)
    events = rec.read_spool_events(target.parent)
    assert events == []  # empty envelope: validated, zero events, no crash


# =============================================================================
# the classification owner governs — registry half of the RED regression
# =============================================================================
def test_registry_classifies_every_evidence_prefix_private():
    registry = json.load(open("config/r2_delivery_plane_classification.v1.json"))
    fams = registry["families"]
    row = next(f for f in fams if f["id"] == "entry_radar_evidence_spool")
    assert row["classification"] == "PRIVATE_OPERATIONAL"
    assert row["required_tier"] == "PRIVATE_SERVICE"
    assert row["safe_public_schema"] == "None"
    for prefix in sp.EVIDENCE_PREFIXES:
        tail = prefix.removeprefix("live_flow/")
        assert f"{tail}/**" in row["key_family"], (prefix, row["key_family"])
        # No OTHER positive family may claim an evidence prefix — a public
        # reclassification would have to fight this pin in review.
        for other in fams:
            if other["id"] == row["id"] or "DEFAULT_DENY" in other["key_family"]:
                continue
            assert tail not in other["key_family"], (prefix, other["id"])
