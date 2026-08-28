---
key: TX-BODY-SHA-IS-CANONICAL-JSON-NOT-RAW-BYTES
claim: >
  The `body_sha256` that `mastermind.tx-index/v1` advertises for a transcript revision is the
  sha256 of a canonical JSON re-serialization of the parsed payload
  (`json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',',':'))`), not the sha256
  of the raw decompressed `/data/tx/<SYM>/<YYYYQn>.json.gz` body.
falsifier: >
  Fetch https://app.mastermind-x.com/data/tx/COF/2026Q2.json.gz, gunzip it, and compare both hashes
  against the index entry: sha256 of the raw decompressed bytes gives
  7951bd19b13b4879526e6756aab882016348fcc9838f36f3c4e3ee8b68fa92c6 and disagrees, while the
  canonical re-serialization gives e9402d4ea54f02e352806f02a1d5757004a274b2d8d023c528b91108e4af1bcc
  and matches the index. If the raw-bytes hash ever matches for COF/2026Q2, this is wrong.
so_what: >
  Byte-replay gates that hash the raw body report a false SOURCE_REVISION_MISMATCH and can stop a
  wave on a revision that never moved. Most stored files happen to already be in canonical form, so
  a raw-bytes check passes on almost every slot and fails on the rare one - which reads exactly like
  a corrected/republished body. Before declaring a revision moved, re-check with the canonical
  convention and confirm against the index's own co-published attributes (bytes, segment_count,
  speaker list, word_count), which stay consistent with the served object.
kind: data
verified_at: 2026-08-27
verified_by: "research/earnings_intelligence/e3/tfg1_development_separator_falsifier_receipt.json (16/16 canonical replay; 15/16 raw-bytes replay)"
scope:
  - macro
  - engine/company_intelligence/
  - research/earnings_intelligence/e3/
confidence: verified
---

# Detail

TFG-0's own probe (`.github/workflows/tfg0-dev-boundary-gold-spike.yml` on
`sol/tfg0-transcript-format-census-20260827`) defines the convention:

```python
def canon(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()
```

Measured on the 16 frozen TFG-0 development revisions: canonical replay 16/16, raw-decompressed-body
replay 15/16. The single disagreement is `COF/2026Q2`, whose published file is not stored in
canonical form.

Corroboration that the corpus is intact rather than corrected: the live index is byte-identical to
the TFG-0 snapshot (`raw_sha256 58f15ff0540f2aa0228348dda6f0ee34b26ef6d3227582fe59793fd43e0af496`,
same `generated_at`); the served COF object matches every attribute the index publishes for it
(22131 bytes, 133 segments, 15 named speakers, `word_count` 11256, `qa_start` 20); and a 60-record
sample of 2026Q2/2026Q3 index entries agreed 60/60 under the canonical convention.

Related: [[a-sighted-date-is-not-the-artifacts-clock]] — an attribute that merely looks like the
artifact's identity is not its identity until you trace how it is computed.
