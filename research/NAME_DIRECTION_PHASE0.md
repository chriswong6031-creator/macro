# Single-Name Direction — Phase-0 (pooled macro-transmission)

Does the validated real-rate edge transmit to single names OOS, as ONE pooled panel (not 1500 per-name fits)? Signal = shrunk(−beta to Δreal10) · the index_direction real_rate leg; shipped lean = b·signal (tilt around each name's own drift), validated as exactly that. Unit of inference = the per-DATE cross-section. A horizon is SCORED only if pooled OOS-R²>0 AND Clark-West BH-q<0.05 AND IC-IR HAC-t>0 AND both date-halves>0 AND it beats a driver-only (no-dispersion) bench AND P(up) is calibrated (recal Brier≥−0.01). GO decided on the PIT panel. DSR/bootstrap are context. Honest prior: this scores little or nothing (Goyal-Welch; Gu-Kelly-Xiu ~0.3–0.4% stock-level OOS-R² ceiling).

## PIT panel — S&P-1500 membership (decision panel)

| horizon | OOS-R² | driver-only | CW p | IC-IR | IC t_HAC | both-halves | recal-Brier | verdict |
|---|--:|--:|--:|--:|--:|:--:|--:|:--:|
| medium | -0.00744 | -0.00638 | 0.9541 | -0.051 | -0.691 | no | -0.002 | display-only |
| long | -0.02556 | -0.02226 | 0.9128 | -0.051 | -0.586 | no | -0.005 | display-only |

## DEEP panel — survivorship-biased (power, optimistic)

| horizon | OOS-R² | driver-only | CW p | IC-IR | IC t_HAC | both-halves | recal-Brier | verdict |
|---|--:|--:|--:|--:|--:|:--:|--:|:--:|
| medium | -0.00036 | -0.00037 | 0.8474 | 0.002 | 0.022 | no | -0.003 | display-only |
| long | -0.00164 | -0.0015 | 0.9119 | -0.057 | -0.623 | no | -0.005 | display-only |

## DEEP ReLU-duration sensitivity (positive-duration names only)

| horizon | OOS-R² | driver-only | CW p | IC-IR | IC t_HAC | both-halves | recal-Brier | verdict |
|---|--:|--:|--:|--:|--:|:--:|--:|:--:|
| medium | -0.00013 | -5e-05 | 0.0535 | 0.019 | 0.247 | no | -0.002 | display-only |
| long | -0.00323 | 9e-05 | 0.103 | -0.035 | -0.394 | no | -0.002 | display-only |

## Decision

Scored horizons (after BH across horizons, on the PIT panel): **NONE — ships as coin-flip**.

Every name defaults to the existing coin-flip; the already-validated risk cone is unaffected. A scored horizon ships a TIGHT (band 0.44–0.58), colored lean labeled a *validated macro-transmission overlay, not per-name alpha*.
