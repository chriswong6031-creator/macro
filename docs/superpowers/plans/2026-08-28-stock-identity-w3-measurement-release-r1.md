# Stock Identity W3 Measurement Release — Plan R1 Interface Amendment

**Status:** Binding clarification to `docs/superpowers/plans/2026-08-28-stock-identity-w3-measurement-release.md`. This amendment changes no scientific architecture, wave boundary, evidence law, or authority. It closes four implementation ambiguities found during Sol self-review before COO dispatch.

## 1. `EstimabilityFloors` is a concrete immutable interface

Task 4 must define this in `engine/stock_identity/estimability.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class EstimabilityFloors:
    min_episode_n: int
    min_calendar_cluster_n: int
    max_largest3_cluster_share: float
    min_feature_coverage: float
```

Values are loaded from the W3 estimability registration/spec artifact and are never caller-tuned from outcomes. Construction validates `min_episode_n >= 1`, `min_calendar_cluster_n >= 1`, `0.0 <= max_largest3_cluster_share <= 1.0`, and `0.0 <= min_feature_coverage <= 1.0`.

`build_estimability_census(..., floors: EstimabilityFloors) -> pd.DataFrame` is therefore the exact Task-4 signature.

## 2. W3S owner/receipt types are concrete immutable interfaces

Task 5 must define these in `engine/stock_identity/dead_control.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HistoryOwnerCandidate:
    owner_id: str
    source_path: Path
    price_plane_id: str
    adjustment_mode: str
    rights_basis: str
    correction_policy: str


@dataclass(frozen=True)
class DeadInstrumentReceipt:
    ticker: str
    instrument_identity: str
    terminated_reason: str
    terminated_date: str
    first_date: str
    last_date: str
    n_rows: int
    source_owner_id: str
    source_path: str
    price_plane_id: str
    adjustment_mode: str
    rights_basis: str
    correction_policy: str
    reused_ticker_hygiene: str
    logical_sha256: str
```

`validate_terminated_instrument(...)` refuses missing/empty fields, nonpositive row count, unacknowledged ticker reuse, terminal date earlier than last valid tape date unless the owner contract explicitly explains the lag, and any plane that cannot satisfy existing Stock Identity fingerprint/episode inputs.

## 3. Stable W3 return path

The Task-6 placeholder path is superseded. The exact Agent OS return file is:

`agentos/handoffs/STOCK-IDENTITY-W3-MEASUREMENT-RELEASE.md`

The file body itself records the exact actual return date/time, operation key, PR/head and receipts. Do not mint date-variant duplicate handoff files for this W3 release.

## 4. Precedence

For W3 execution, read in this order:

1. current Chairman/Sol instruction;
2. current protected Skillpack;
3. `research/stock_identity/STOCK_IDENTITY_COMPLETE_MASTERPLAN_2026-08-28.md`;
4. `docs/superpowers/plans/2026-08-28-stock-identity-w3-measurement-release.md`;
5. **this R1 amendment** for the four clarified interfaces/path above;
6. original Stock Identity masterplan/W1/W2 registrations and current owner source law.

If a newer accepted source conflicts materially with this amendment, stop the affected lane and return to Sol rather than inventing another type/path.
