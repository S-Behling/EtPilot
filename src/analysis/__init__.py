"""Calcule métricas sobre os segmentos físicos de análise do EtPilot."""

from .edge_statistics import (
    attach_statistics_to_segments,
    build_segment_statistics,
)
from .entropy import (
    normalized_shannon_entropy,
)

__all__ = [
    "attach_statistics_to_segments",
    "build_segment_statistics",
    "normalized_shannon_entropy",
]
