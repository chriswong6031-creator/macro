"""TrumpFlow — latent-stake entity graph for Trump-family / administration investments.

Catches the value chains Quiver's structured feeds structurally CANNOT see: private
equity-for-stake deals (the ABTC -> Hut 8 case), family vehicles, pre-IPO/SPAC stakes.
A hand-curated, provenance-labelled graph (data/trumpflow/intel.json) + an optional
gated LLM extractor that proposes new candidate edges from news/filings. Deterministic
graph queries (short-path, label-mismatch) surface the latent thesis; cross-referencing
the live Quiver alt-data corroborates it. Display/context-only.
"""
