"""ONE-SHOT branch patcher for D12. Deleted by the apply workflow after use."""
from pathlib import Path

p = Path("scripts/build_prophet_live_pack.py")
s = p.read_text()

old = (
    "from engine.prophet_live import armed_pack as AP  # noqa: E402\n"
    "from engine.prophet_live import r2io  # noqa: E402\n"
)
new = (
    "from engine.prophet_live import armed_pack as AP  # noqa: E402\n"
    "from engine.prophet_live import live_states as LS  # noqa: E402\n"
    "from engine.prophet_live import r2io  # noqa: E402\n"
)
assert s.count(old) == 1
s = s.replace(old, new, 1)

# Replace the three US publication assembly call sites before defining the wrapper.
assert s.count("AP.name_entry(") == 3
s = s.replace("AP.name_entry(", "_name_entry(")

marker = """def build(*, cfg: dict[str, Any] | None = None, now: datetime | None = None,
          workers: int | None = None, limit: int | None = None) -> dict[str, Any]:
"""
assert s.count(marker) == 1
helpers = '''def _split_completed_series(series: dict[str, Any], *, completed_through: str
                            ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Partition US close series by whether their LAST bar is a completed NYSE session.

    D12 was a one-name-to-whole-pack contagion: ``AP.as_of_date`` intentionally reports
    the raw maximum store tip, and ``AP.session_lag`` intentionally treats a bar at or
    ahead of that tip as current. A Saturday/future/same-session-before-close row could
    therefore stamp the whole pack and also enter the gate itself. US admission must
    reject that NAME before either operation. We do not trim the bad row: doing so would
    make this pack probe a series different from the board owner's series.

    This law is US-only. ``armed_pack`` is shared with China, so its raw ``as_of_date``
    semantics remain unchanged and the NYSE calendar stays here at the US pack owner.
    """
    from datetime import date as _date  # noqa: PLC0415
    from lib.nyse_calendar import is_session  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    bound = _date.fromisoformat(str(completed_through)[:10])
    valid: dict[str, Any] = {}
    invalid: dict[str, Any] = {}
    for tkr, close in series.items():
        try:
            day = pd.Timestamp(close.index[-1]).date()
        except Exception:  # noqa: BLE001 — malformed tip is not admissible evidence
            invalid[tkr] = close
            continue
        if day > bound or not is_session(day):
            invalid[tkr] = close
        else:
            valid[tkr] = close
    return valid, invalid


def _name_entry(rec: dict[str, Any], probe: dict[str, Any] | None) -> dict[str, Any]:
    """US publication wrapper for D12's explicit invalid-tip non-verdict."""
    entry = AP.name_entry(rec, probe)
    if rec.get("skip") == "invalid_series_tip":
        # No gate ran. ``dormant`` would falsely say the name was evaluated and nothing
        # was forming. Keep the shared AP vocabulary unchanged for CN; the US-specific
        # invalid-tip state is projected here by the owner that minted the skip reason.
        entry["state"] = "stale"
    return entry


'''
s = s.replace(marker, helpers + marker, 1)

old = '''        series[tkr] = s
    tip = AP.as_of_date(series.values())
    print(f"prophet-live pack: universe={len(uni)} usable={len(series)} tip={tip} "
          f"load={time.time() - t0:.1f}s", flush=True)

    max_lag = int(c["max_lag_sessions"])
    fresh: list[str] = []
    recs: dict[str, dict[str, Any]] = {}
    import pandas as pd  # noqa: PLC0415
    for tkr, s in series.items():
'''
new = '''        series[tkr] = s
    usable_n = len(series)
    completed_through = LS.last_completed_session(now)
    series, invalid_series = _split_completed_series(
        series, completed_through=completed_through)
    tip = AP.as_of_date(series.values())
    if invalid_series:
        skipped["invalid_series_tip"] = len(invalid_series)
    print(f"prophet-live pack: universe={len(uni)} usable={usable_n} "
          f"admitted={len(series)} invalid_tip={len(invalid_series)} "
          f"completed_through={completed_through} tip={tip} "
          f"load={time.time() - t0:.1f}s", flush=True)

    max_lag = int(c["max_lag_sessions"])
    fresh: list[str] = []
    recs: dict[str, dict[str, Any]] = {}
    for tkr, s in invalid_series.items():
        recs[tkr] = AP.stale_record(tkr, s, 0)
        recs[tkr]["skip"] = "invalid_series_tip"
    import pandas as pd  # noqa: PLC0415
    for tkr, s in series.items():
'''
assert s.count(old) == 1
s = s.replace(old, new, 1)

p.write_text(s)
