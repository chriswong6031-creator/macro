"""
engine.neuralweb — Neural Web package namespace.

The Neural Web is the signal-bus governance layer for the Macro Dashboard engine.
It provides:
  - synapse.py   : registry loader, validator, and artifact helpers (W0 PR1)
  - envelope.py  : provenance-stamp helper — in-place sibling keys, hash-ex-envelope,
                   byte-identity fast-path, parquet/JSONL sidecars (W0 PR2)
  (future waves will add read-gate, conductor, etc.)

WHAT THE ENVELOPE IS
--------------------
Every registered artifact carries five sibling keys — schema_version, produced_by,
produced_at, inputs_hash, tier — added at the TOP LEVEL of the artifact dict.

WHY IN-PLACE SIBLINGS, NEVER A WRAPPER
---------------------------------------
scripts/build_feeds.py extracts the risk_radar sub-object and writes it directly::

    rr = latest.get("risk_radar")
    _write_json(out, "risk_radar.json", rr)

A wrapper ({"envelope": {...}, "data": rr}) would make rr.get("state") return None —
exactly the 2026-07-02 semis incident.  Sibling keys on rr are preserved verbatim
in site/feeds/risk_radar.json and consumers read them at the top level.

ADOPTION RECIPE (two lines per producer)
-----------------------------------------
::

    from engine.neuralweb.envelope import stamp
    payload = stamp(payload, artifact_id="regime-latest")

To suppress produced_at churn when the payload has not changed::

    from engine.neuralweb.envelope import stamp_if_changed
    payload = stamp_if_changed(payload, prev_payload, artifact_id="regime-latest")

For parquet / JSONL artifacts::

    from engine.neuralweb.envelope import write_sidecar
    write_sidecar(Path("data/qbus/items.parquet"), artifact_id="qbus-items")

W0 PR2 ships the helper only — no producer is stamped yet.
Adoption happens per-producer in later PRs, one at a time.
"""
