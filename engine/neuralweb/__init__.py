"""
engine.neuralweb — Neural Web package namespace.

The Neural Web is the signal-bus governance layer for the Macro Dashboard engine.
It provides:
  - synapse.py  : registry loader, validator, and artifact helpers (W0)
  (future waves will add envelope stamper, read-gate, conductor, etc.)

W0 is passive: this package ships the registry + integrity gate only.
No behavior change to any engine; no envelope stamping; no read-gate yet.
"""
