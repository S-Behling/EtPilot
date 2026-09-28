"""Calcule métricas sobre os segmentos físicos de análise do EtPilot."""

from .edge_statistics import (
    attach_statistics_to_segments,
    build_segment_statistics,
)
from .entropy import (
    normalized_shannon_entropy,
)
from .scenario_comparison import (
    attach_comparison_to_segments,
    build_scenario_comparison,
    comparison_summary,
)

__all__ = [
    "attach_statistics_to_segments",
    "build_segment_statistics",
    "normalized_shannon_entropy",
    "attach_comparison_to_segments",
    "build_scenario_comparison",
    "comparison_summary",
]
