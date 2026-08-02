"""BioCatalyst-owned source collectors."""

from .clinicaltrials_v2 import (
    ClinicalTrialsV2Collector,
    ClinicalTrialsV2Config,
    CollectionError,
    PublicationResult,
)

__all__ = [
    "ClinicalTrialsV2Collector",
    "ClinicalTrialsV2Config",
    "CollectionError",
    "PublicationResult",
]
