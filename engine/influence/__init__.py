"""Influence graph — multi-actor affiliation graph for the Signal Intelligence desk.

Generalizes the Trump-only latent-stake graph (engine/trumpflow) into a graph spanning
many important actors — politicians & disclosed congressional traders, founders/execs,
fund managers & activists, market influencers — and the QUALITATIVE ways they affiliate
with investable names: not just trades, but who they TALK_ABOUT, ENDORSE, PARTNER_WITH,
ADVISE, or AFFILIATE_WITH, plus the second/third-order chains those affiliations imply.

  * a curated, provenance-graded seed (data/altdata/influence_seed.json) MERGED with the
    Trump-family seed (data/trumpflow/intel.json), and
  * an optional gated Claude-Opus extractor (engine/influence/extract.py) that proposes
    NEW candidate affiliation edges from news/filings with a verbatim-citation gate.

Deterministic graph queries (actor→theme short paths, label-mismatch repointing, the
per-ticker affiliation roll-up) surface the latent connection; cross-referencing the live
Quiver alt-data corroborates it. The affiliation roll-up becomes a convergence channel so
a qualitative actor→name edge can converge with the hard feeds.
"""
