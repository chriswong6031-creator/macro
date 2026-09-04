"""Atomic builder + manifest for Macro & Monetary workspace snapshots (F01 / R1A).

Reads the owner artifact, composes the ``liquidity_regime`` / US snapshot, seals
and validates it against the closed contract, and publishes atomically:

    <out_root>/workspaces/liquidity_regime/US/latest.json
    <out_root>/workspaces/manifest.json

The suite manifest carries the generation identity plus, per published
workspace, the content hash, byte size, availability state, minimum client
contract, and build state. The workspace body is written FIRST (tmp + os.replace)
and the manifest LAST. That ordering bounds the failure window to one
direction only: a concurrent reader can observe an OLD manifest paired with a
NEWER body on disk (the manifest's declared content_sha256 then differs from
the body's actual digest), but never the reverse -- os.replace of the body
always completes before the manifest write begins, so a manifest can never
name a body that is not yet on disk.

This is a property AVAILABLE to a validating reader, not a guarantee this repo
enforces end-to-end today: no consumer shipped in R1A cross-checks the
manifest's declared content_sha256 against the body it names before using it
(``consumer.py`` only self-validates a body's own embedded digest against
itself; it never opens the manifest at all). A reader that wants torn-
generation safety must read the manifest, then the body, then recompute and
compare the body's digest against the manifest's declared content_sha256
itself -- R1B is expected to implement that validating reader.

Pure projection: no owner path is mutated, no mutable service state is created.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from engine.market_os.macro_workspaces import (
    business_activity,
    capital_structure,
    consumer_payments,
    contract,
    financial_conditions,
    growth,
    housing,
    inflation,
    labor,
    liquidity_central_banks,
    liquidity_regime,
    monetary_policy,
    national_debt,
    registry,
)

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT_ROOT = ROOT / "site" / "macrodata"
DEFAULT_REGIME_LATEST = ROOT / "data" / "regime" / "latest.json"
DEFAULT_INFLATION_INTEL = ROOT / "data" / "release_forecast" / "inflation_intelligence.json"
DEFAULT_RATES_COMMAND = ROOT / "data" / "rates_command" / "latest.json"
DEFAULT_INTL_RISK = ROOT / "data" / "intl_risk" / "latest.json"
DEFAULT_GLT_LATEST = ROOT / "site" / "liquiditydata" / "global_liquidity_transmission.json"
DEFAULT_GLT_HISTORY_META = ROOT / "data" / "global_liquidity_transmission" / "state_history_meta.json"
DEFAULT_FRED_DIR = ROOT / "data" / "fred"
DEFAULT_ZORI_NATIONAL = ROOT / "data" / "zori" / "national.parquet"
DEFAULT_CAPITAL_STRUCTURE_PROJECTION = ROOT / "data" / "capital_structure" / "projection.json"
DEFAULT_TREASURY_DIR = ROOT / "data" / "treasury"
DEFAULT_TREASURY_AUCTIONS = ROOT / "data" / "treasury_auctions" / "auctions.parquet"
DEFAULT_BIS_DIR = ROOT / "data" / "bis"
DEFAULT_BONDS_LATEST = ROOT / "data" / "bonds" / "latest.json"
MIN_CLIENT_CONTRACT = f"{contract.CONTRACT_ID}@{contract.CONTRACT_VERSION}"

# Housing core: FRED series id -> the parquet's value column (the column names
# come from the collector config, config.yml fred.series entries).
_HOUSING_FRED_COLUMNS = {
    "MORTGAGE30US": "mortgage_30y",
    "HOUST": "housing_starts",
    "PERMIT": "building_permits",
    "CSUSHPISA": "case_shiller_sa",
}

# Consumer core (F01 R6): same convention. RSAFS/UMCSENT are collected today;
# the config.yml `consumer_household` group ids land on the next nightly keyed
# collect — until then their parquets are absent and the loader hands the
# composer None (typed SOURCE_FAILED, self-healing when the files appear).
_CONSUMER_FRED_COLUMNS = {
    "RSAFS": "retail_sales",
    "UMCSENT": "umich_sentiment",
    "TOTALSL": "consumer_credit_total",
    "REVOLSL": "consumer_credit_revolving",
    "NONREVSL": "consumer_credit_nonrevolving",
    "PSAVERT": "personal_saving_rate",
    "DSPIC96": "real_disposable_income",
    "DRCCLACBS": "cc_delinquency_rate",
    "DRSFRMACBS": "mortgage_delinquency_rate",
}

# National-debt collected lanes: store key -> (filename under its dir, column).
# The _mn suffixes are the unit contract ($ millions, Daily Treasury Statement).
_TREASURY_COLUMNS = {
    "tga": ("tga.parquet", "tga_mn"),
    "net_issuance": ("net_issuance.parquet", "net_issuance_mn"),
    "withheld_taxes": ("withheld_taxes.parquet", "withheld_tax_mn"),
}
# BIS US panels are quarterly, period-END dated, attribution-only rights.
_BIS_US_COLUMNS = {
    "dsr": ("us_dsr.parquet", "dsr"),
    "gap": ("us_gap.parquet", "gap"),
}


def _load_series_rows(path: Path, column: str) -> list | None:
    """Load one series parquet into plain ``[(iso_date, float), ...]`` rows.

    Missing file -> ``None`` (the composer emits its own typed absence).
    A PRESENT-but-unreadable file, or a missing pandas/pyarrow runtime, RAISES:
    laundering either into "source absent" would hide corruption or an
    environment defect behind an honest-looking typed null (same law as
    ``_load_json_or_empty``). pandas is imported lazily so importing this
    module never requires it (the CI suites monkeypatch the loaders)."""
    p = Path(path)
    if not p.exists():
        return None
    import pandas as pd  # noqa: PLC0415 — lazy: only a real build needs it

    frame = pd.read_parquet(p)
    frame.index = pd.to_datetime(frame.index)
    series = frame[column].dropna().sort_index()
    return [(idx.date().isoformat(), float(value)) for idx, value in series.items()]


def _load_auction_rows(path: Path) -> list | None:
    """``data/treasury_auctions/auctions.parquet`` -> plain row dicts holding
    exactly the five columns the national_debt composer consumes, ascending by
    auction_date. Missing file -> ``None``; a present-but-unreadable file
    RAISES (same no-laundering law as ``_load_series_rows``)."""
    p = Path(path)
    if not p.exists():
        return None
    import pandas as pd  # noqa: PLC0415 — lazy: only a real build needs it

    def _num(row, name):
        value = row.get(name)
        return None if value is None or pd.isna(value) else float(value)

    frame = pd.read_parquet(p)
    rows: list[dict] = []
    for _, row in frame.iterrows():
        raw_date = row.get("auction_date")
        if raw_date is None or pd.isna(raw_date):
            continue
        sec_type = row.get("security_type")
        rows.append({
            "auction_date": pd.Timestamp(raw_date).date().isoformat(),
            "security_type": None if sec_type is None or pd.isna(sec_type) else str(sec_type),
            "tenor_years": _num(row, "tenor_years"),
            "bid_to_cover": _num(row, "bid_to_cover"),
            "high_yield": _num(row, "high_yield"),
        })
    rows.sort(key=lambda r: r["auction_date"])
    return rows


def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_json_or_empty(path: Path) -> dict:
    """Missing/unreadable owner artifact -> {} so the composer emits its own
    typed SOURCE_FAILED states instead of the builder crashing. A malformed
    (present but non-JSON) artifact still raises: silence there would launder
    corruption into 'source absent'."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _atomic_write_bytes(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return len(data)


def _snapshot_bytes(snapshot: Mapping[str, Any]) -> bytes:
    # Human-diffable published form (indented). The digest is computed from the
    # canonical form inside contract.py and is independent of this layout.
    return (json.dumps(snapshot, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def build_liquidity_regime(
    *,
    regime_latest_path: Path | str = DEFAULT_REGIME_LATEST,
    out_root: Path | str = DEFAULT_OUT_ROOT,
    built_at: str,
    prior_snapshot_path: Path | str | None = None,
    code_version: str | None = None,
    write: bool = True,
) -> dict:
    """Compose, seal, validate, and (optionally) publish the US liquidity-regime
    snapshot. Returns a receipt dict with the sealed snapshot, digest, byte size,
    manifest, and written paths (paths are None when ``write`` is False)."""
    regime_latest = _load_json(Path(regime_latest_path))
    prior = _load_json(Path(prior_snapshot_path)) if prior_snapshot_path else None

    body = liquidity_regime.compose(
        regime_latest, built_at=built_at, prior_snapshot=prior, code_version=code_version
    )
    snapshot = contract.finalize(body)
    contract.validate(snapshot)  # raises ContractError on any violation

    payload = _snapshot_bytes(snapshot)
    digest = snapshot["generation"]["content_sha256"]
    entry = registry.entry("liquidity_regime")

    workspace_rel = Path("workspaces") / "liquidity_regime" / "US" / "latest.json"
    manifest_rel = Path("workspaces") / "manifest.json"
    ws_path = Path(out_root) / workspace_rel
    manifest_path = Path(out_root) / manifest_rel

    manifest = {
        "schema": "mastermind.macro_workspace_manifest.v1",
        "generated_at": built_at,
        "min_client_contract": MIN_CLIENT_CONTRACT,
        "workspaces": {
            "liquidity_regime/US": {
                "workspace": "liquidity_regime",
                "region": "US",
                "path": str(workspace_rel).replace(os.sep, "/"),
                "content_sha256": digest,
                "bytes": len(payload),
                "availability_state": snapshot["availability"]["state"],
                "headline_state": snapshot["headline"]["state_id"],
                "build_state": entry["build_state"],
                "generation_id": snapshot["generation"]["generation_id"],
                "built_at": built_at,
            }
        },
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

    written = {"workspace": None, "manifest": None}
    if write:
        _atomic_write_bytes(ws_path, payload)          # body first ...
        _atomic_write_bytes(manifest_path, manifest_bytes)  # ... manifest last
        written = {"workspace": str(ws_path), "manifest": str(manifest_path)}

    return {
        "snapshot": snapshot,
        "digest": digest,
        "bytes": len(payload),
        "manifest": manifest,
        "paths": written,
    }


def _compose_workspace(workspace_id: str, *, regime_latest: dict,
                       inflation_intel: dict, rates_command: dict,
                       intl_risk: dict, glt_latest: dict,
                       glt_history_meta: dict,
                       housing_fred_frames: dict,
                       housing_zori_rows: list | None,
                       capital_structure_projection: dict,
                       consumer_fred_frames: dict,
                       treasury_frames: dict,
                       auction_rows: list | None,
                       bis_frames: dict,
                       bonds_latest: dict | None,
                       built_at: str,
                       prior_snapshot: dict | None,
                       code_version: str | None) -> dict:
    """Route one BUILT workspace to its composer with its owner-native inputs.

    Every composer degrades typed (SOURCE_FAILED / ABSENT) when its owner block
    is missing; the builder never fabricates an input.
    """
    if workspace_id == "liquidity_regime":
        return liquidity_regime.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "growth_real_economy":
        return growth.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "business_activity":
        return business_activity.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "labor_markets":
        return labor.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "financial_conditions":
        return financial_conditions.compose(
            regime_latest, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "inflation_system":
        return inflation.compose(
            inflation_intel, built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "monetary_policy":
        return monetary_policy.compose(
            rates_command,
            (intl_risk.get("cb_desk") or {}),
            (regime_latest.get("rate_inflation_transmission") or {}),
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "liquidity_central_banks":
        return liquidity_central_banks.compose(
            glt_latest,
            (intl_risk.get("cb_desk") or {}),
            glt_history_meta,
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "housing_real_estate":
        return housing.compose(
            housing_fred_frames, housing_zori_rows,
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "capital_structure":
        return capital_structure.compose(
            capital_structure_projection,
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "consumer_payments":
        return consumer_payments.compose(
            consumer_fred_frames,
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    if workspace_id == "national_debt_liabilities":
        return national_debt.compose(
            treasury_frames, auction_rows, bis_frames, bonds_latest,
            built_at=built_at,
            prior_snapshot=prior_snapshot, code_version=code_version)
    raise ValueError(f"no builder route for workspace id: {workspace_id!r}")


def build_all(*, out_root: Path | str = DEFAULT_OUT_ROOT,
              regime_latest_path: Path | str = DEFAULT_REGIME_LATEST,
              inflation_intel_path: Path | str = DEFAULT_INFLATION_INTEL,
              rates_command_path: Path | str = DEFAULT_RATES_COMMAND,
              intl_risk_path: Path | str = DEFAULT_INTL_RISK,
              glt_latest_path: Path | str = DEFAULT_GLT_LATEST,
              glt_history_meta_path: Path | str = DEFAULT_GLT_HISTORY_META,
              fred_dir: Path | str = DEFAULT_FRED_DIR,
              zori_path: Path | str = DEFAULT_ZORI_NATIONAL,
              capital_structure_projection_path: Path | str = DEFAULT_CAPITAL_STRUCTURE_PROJECTION,
              treasury_dir: Path | str = DEFAULT_TREASURY_DIR,
              treasury_auctions_path: Path | str = DEFAULT_TREASURY_AUCTIONS,
              bis_dir: Path | str = DEFAULT_BIS_DIR,
              bonds_latest_path: Path | str = DEFAULT_BONDS_LATEST,
              built_at: str, code_version: str | None = None,
              prior_snapshot_path: Path | str | None = None,
              write: bool = True) -> dict:
    """Build every ``BUILT`` workspace (registry-driven) for region US.

    All workspace bodies are written FIRST (each tmp + os.replace), then ONE
    combined manifest covering every published workspace is written LAST — the
    same one-directional torn-generation bound documented in the module
    docstring, now suite-wide. ``prior_snapshot_path`` applies only to
    liquidity_regime (R1A compatibility); other workspaces WARMUP on first
    print and pick up their own priors once a publication history exists.
    """
    regime_latest = _load_json(Path(regime_latest_path))
    inflation_intel = _load_json_or_empty(Path(inflation_intel_path))
    rates_command = _load_json_or_empty(Path(rates_command_path))
    intl_risk = _load_json_or_empty(Path(intl_risk_path))
    glt_latest = _load_json_or_empty(Path(glt_latest_path))
    glt_history_meta = _load_json_or_empty(Path(glt_history_meta_path))
    housing_fred_frames = {
        sid: _load_series_rows(Path(fred_dir) / f"{sid}.parquet", column)
        for sid, column in _HOUSING_FRED_COLUMNS.items()
    }
    housing_zori_rows = _load_series_rows(Path(zori_path), "zori")
    capital_structure_projection = _load_json_or_empty(Path(capital_structure_projection_path))
    consumer_fred_frames = {
        sid: _load_series_rows(Path(fred_dir) / f"{sid}.parquet", column)
        for sid, column in _CONSUMER_FRED_COLUMNS.items()
    }
    treasury_frames = {
        key: _load_series_rows(Path(treasury_dir) / fname, column)
        for key, (fname, column) in _TREASURY_COLUMNS.items()
    }
    auction_rows = _load_auction_rows(Path(treasury_auctions_path))
    bis_frames = {
        key: _load_series_rows(Path(bis_dir) / fname, column)
        for key, (fname, column) in _BIS_US_COLUMNS.items()
    }
    # The national_debt composer's contract is dict-or-None (an owner artifact
    # that is absent is None, never {}): normalize the empty-load sentinel.
    bonds_latest = _load_json_or_empty(Path(bonds_latest_path)) or None

    out = Path(out_root)
    manifest_entries: dict[str, dict] = {}
    receipts: dict[str, dict] = {}
    pending_bodies: list[tuple[Path, bytes]] = []

    for wid in registry.built_ids():
        prior = None
        if wid == "liquidity_regime" and prior_snapshot_path:
            prior = _load_json(Path(prior_snapshot_path))
        else:
            # Self-prior: the previously published artifact, when present and
            # loadable, is this build's prior print (WARMUP otherwise).
            prior_path = out / "workspaces" / wid / "US" / "latest.json"
            if prior_path.exists():
                try:
                    prior = _load_json(prior_path)
                except Exception:
                    prior = None

        body = _compose_workspace(
            wid, regime_latest=regime_latest, inflation_intel=inflation_intel,
            rates_command=rates_command, intl_risk=intl_risk,
            glt_latest=glt_latest, glt_history_meta=glt_history_meta,
            housing_fred_frames=housing_fred_frames,
            housing_zori_rows=housing_zori_rows,
            capital_structure_projection=capital_structure_projection,
            consumer_fred_frames=consumer_fred_frames,
            treasury_frames=treasury_frames,
            auction_rows=auction_rows,
            bis_frames=bis_frames,
            bonds_latest=bonds_latest,
            built_at=built_at,
            prior_snapshot=prior, code_version=code_version)
        snapshot = contract.finalize(body)
        contract.validate(snapshot)

        payload = _snapshot_bytes(snapshot)
        digest = snapshot["generation"]["content_sha256"]
        workspace_rel = Path("workspaces") / wid / "US" / "latest.json"
        ws_path = out / workspace_rel

        manifest_entries[f"{wid}/US"] = {
            "workspace": wid,
            "region": "US",
            "path": str(workspace_rel).replace(os.sep, "/"),
            "content_sha256": digest,
            "bytes": len(payload),
            "availability_state": snapshot["availability"]["state"],
            "headline_state": snapshot["headline"]["state_id"],
            "build_state": registry.entry(wid)["build_state"],
            "generation_id": snapshot["generation"]["generation_id"],
            "built_at": built_at,
        }
        receipts[f"{wid}/US"] = {
            "snapshot": snapshot,
            "digest": digest,
            "bytes": len(payload),
            "paths": {"workspace": str(ws_path) if write else None, "manifest": None},
        }
        pending_bodies.append((ws_path, payload))

    manifest = {
        "schema": "mastermind.macro_workspace_manifest.v1",
        "generated_at": built_at,
        "min_client_contract": MIN_CLIENT_CONTRACT,
        "workspaces": manifest_entries,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = out / "workspaces" / "manifest.json"

    if write:
        for ws_path, payload in pending_bodies:   # every body first ...
            _atomic_write_bytes(ws_path, payload)
        _atomic_write_bytes(manifest_path, manifest_bytes)  # ... manifest last
        for key in receipts:
            receipts[key]["paths"]["manifest"] = str(manifest_path)

    receipts["_manifest"] = {"manifest": manifest, "path": str(manifest_path) if write else None}
    return receipts
