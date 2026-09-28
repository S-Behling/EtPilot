"""Calcula métricas sobre os segmentos físicos de análise do EtPilot"""

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
from .pilot_maps import (
    plot_delta_h_soc,
    plot_h_soc,
    save_pilot_maps,
)

__all__ = [
    "attach_statistics_to_segments",
    "build_segment_statistics",
    "normalized_shannon_entropy",
    "attach_comparison_to_segments",
    "build_scenario_comparison",
    "comparison_summary",
    "plot_delta_h_soc",
    "plot_h_soc",
    "save_pilot_maps",
]
