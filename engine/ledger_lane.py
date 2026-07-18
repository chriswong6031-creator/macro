"""engine.ledger_lane — canonical forward-ledger advance gate.

This is the single definition of the forward-ledger advance gate for the two
nightly lanes (US-nightly and HK asia-close).  Every engine and script module
that previously defined a local _ledger_advance_enabled() now imports from
here.

Intentionally a LEAF module: imports os only, nothing from engine or lib.
That keeps the import graph acyclic and makes the gate testable with a bare
env.

NOT unified here:
    The ledger_lane_armed() family used by risk-radar/ignition/market-state
    audits (engine/event_window.py, engine/ignition_audit.py,
    engine/intl_run.py, engine/market_state_audit.py, engine/opex_risk.py,
    and neuralweb equivalents) is a *separate* mechanism, deliberately not
    unified here.  That family gates collect-lane arming per invocation; this
    module gates forward-ledger row appends globally.
"""

import os


def nightly_advance_enabled() -> bool:
    """True only when running in the US nightly engine lane.

    Gate: COLLECT_LANE=nightly — the same sentinel set by daily.yml's
    engine-job env.  US_LANE is accepted as a legacy alias so existing
    tests and callers that set US_LANE=nightly continue to work.

    This is the single definition of the forward-ledger advance gate for the
    US-nightly lane.  The ledger_lane_armed() family in risk-radar/ignition/
    market-state audits is a SEPARATE mechanism, deliberately not unified here.
    """
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


def asia_advance_enabled() -> bool:
    """True only when running in the HK asia-close nightly lane.

    Gate: CN_LANE=asia — set in .github/workflows/asia-close.yml, absent in
    weekly.yml and daily.yml.  Snapshot/display JSON may be produced in any
    lane; only the ledger APPEND (stamp/grade) is gated here.

    This is the single definition of the forward-ledger advance gate for the
    HK asia-close lane.  The ledger_lane_armed() family in risk-radar/ignition/
    market-state audits is a SEPARATE mechanism, deliberately not unified here.
    """
    return os.environ.get("CN_LANE", "").lower() == "asia"
