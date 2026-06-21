"""Concept-drift detectors — the early-warning channel for a decaying signal (P2).

A signal's edge fades silently: its rolling information coefficient drifts toward zero long
before the track record formally fails. These online detectors flag that drift so a leg can be
auto-demoted (conviction dropped) and routed to the gate for re-validation, instead of quietly
rotting. Two complementary, well-known detectors, pure-stdlib:

  * PageHinkley — cumulative-deviation test for a change in a stream's MEAN (abrupt or gradual);
    O(1)/update. Default direction='down' (catch a DEGRADING IC).
  * ADWIN — ADaptive WINdowing (Bifet & Gavaldà 2007): keeps the largest recent window whose
    sub-windows agree; when two sub-windows differ beyond a variance-aware Hoeffding bound it
    drops the stale part and flags drift, so `mean`/`width` track the CURRENT regime.

Display-only / advisory: a drift flag is a circuit breaker that routes to the gate, never an
auto-action on its own.
"""
from __future__ import annotations

import math


class PageHinkley:
    """Page-Hinkley change detector on a stream's mean. `delta` = allowed slack (tolerance),
    `threshold` (λ) = alarm level, `direction` = 'down' to catch a decrease, 'up' an increase."""

    def __init__(self, delta: float = 0.005, threshold: float = 0.05, direction: str = "down") -> None:
        self.delta = float(delta)
        self.threshold = float(threshold)
        self.direction = direction
        self.reset()

    def reset(self) -> None:
        self.n = 0
        self.mean = 0.0
        self.cum = 0.0
        self.extreme = 0.0
        self.drift = False

    def update(self, x: float) -> bool:
        x = float(x)
        self.n += 1
        self.mean += (x - self.mean) / self.n
        if self.direction == "down":
            self.cum += (x - self.mean + self.delta)
            self.extreme = self.cum if self.n == 1 else max(self.extreme, self.cum)
            ph = self.extreme - self.cum
        else:
            self.cum += (x - self.mean - self.delta)
            self.extreme = self.cum if self.n == 1 else min(self.extreme, self.cum)
            ph = self.cum - self.extreme
        self.drift = ph > self.threshold
        return self.drift


class ADWIN:
    """ADaptive WINdowing (ADWIN0 with the variance-aware cut). `delta` = confidence (smaller =
    fewer false alarms). On each update it appends a value and, while some split of the window
    shows a significant mean difference, drops the OLDER sub-window and flags drift."""

    def __init__(self, delta: float = 0.002) -> None:
        self.delta = float(delta)
        self.window: list[float] = []
        self.drift = False

    @property
    def width(self) -> int:
        return len(self.window)

    @property
    def mean(self) -> float:
        return sum(self.window) / len(self.window) if self.window else 0.0

    def update(self, x: float) -> bool:
        self.window.append(float(x))
        self.drift = False
        changed = True
        while changed and len(self.window) >= 2:
            changed = False
            w = self.window
            n = len(w)
            total = sum(w)
            mean_all = total / n
            var = sum((v - mean_all) ** 2 for v in w) / n
            ln = math.log(2.0 * n / self.delta)             # delta' scaled by window length
            prefix = 0.0
            for i in range(1, n):
                prefix += w[i - 1]
                n0, n1 = i, n - i
                u0 = prefix / n0
                u1 = (total - prefix) / n1
                m = 1.0 / (1.0 / n0 + 1.0 / n1)              # harmonic mean of the sub-window sizes
                eps = math.sqrt(2.0 / m * var * ln) + 2.0 / (3.0 * m) * ln
                if abs(u0 - u1) > eps:
                    self.window = w[i:]                      # drop the stale older part
                    self.drift = True
                    changed = True
                    break
        return self.drift


def rolling_ic_drift(values, *, delta: float = 0.005, threshold: float = 0.05,
                     direction: str = "down") -> dict:
    """Run Page-Hinkley + ADWIN over a rolling-IC (or any metric) stream. Returns the first
    drift index from each detector and ADWIN's current (post-drift) window mean/width — the
    convenience the drift bus calls per signal leg. Degrades to no-drift on empty/short input."""
    seq = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    out = {"n": len(seq), "ph_drift_index": None, "adwin_drift_index": None,
           "current_mean": None, "current_width": 0, "drift": False}
    if len(seq) < 4:
        return out
    ph = PageHinkley(delta=delta, threshold=threshold, direction=direction)
    ad = ADWIN()
    for i, x in enumerate(seq):
        if ph.update(x) and out["ph_drift_index"] is None:
            out["ph_drift_index"] = i
        if ad.update(x) and out["adwin_drift_index"] is None:
            out["adwin_drift_index"] = i
    out["current_mean"] = round(ad.mean, 6)
    out["current_width"] = ad.width
    out["drift"] = out["ph_drift_index"] is not None or out["adwin_drift_index"] is not None
    return out


__all__ = ["PageHinkley", "ADWIN", "rolling_ic_drift"]
