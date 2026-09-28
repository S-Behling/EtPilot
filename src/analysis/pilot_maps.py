"""Gera mapas estáticos das métricas espaciais do piloto

Mantém a mesma extensão espacial entre os cenários e usa escalas fixas para
permitir comparação visual direta entre baseline e differentiated

Representa H_soc no intervalo fixo [0, 1] e delta_H_soc no intervalo fixo
[-1, 1] com centro em zero

Mantém a rede física completa como referência visual em cinza claro e destaca
somente os segmentos válidos para cada mapa
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import Normalize, TwoSlopeNorm
from matplotlib.lines import Line2D


H_SOC_CMAP = "viridis"
DELTA_H_SOC_CMAP = "coolwarm"
NETWORK_COLOR = "#d9d9d9"
OBSERVED_INSUFFICIENT_COLOR = "#969696"


def _require_columns(
    frame: gpd.GeoDataFrame,
    columns: list[str] | tuple[str, ...],
) -> None:
    """Exige as colunas necessárias antes da geração do mapa"""

    missing = (
        set(columns)
        - set(frame.columns)
    )

    if missing:
        raise ValueError(
            "Adiciona as colunas obrigatórias antes da visualização: "
            f"{sorted(missing)}"
        )


def _set_common_extent(
    axes,
    bounds,
    *,
    margin_ratio: float = 0.02,
) -> None:
    """Aplica a mesma extensão espacial e acrescenta uma margem proporcional"""

    min_x, min_y, max_x, max_y = bounds

    width = max(
        max_x - min_x,
        1.0,
    )
    height = max(
        max_y - min_y,
        1.0,
    )

    margin_x = (
        width
        * margin_ratio
    )
    margin_y = (
        height
        * margin_ratio
    )

    axes.set_xlim(
        min_x - margin_x,
        max_x + margin_x,
    )
    axes.set_ylim(
        min_y - margin_y,
        max_y + margin_y,
    )


def _plot_network_background(
    axes,
    geodata: gpd.GeoDataFrame,
    *,
    linewidth: float,
) -> None:
    """Desenha a rede física completa como referência visual"""

    geodata.plot(
        ax=axes,
        color=NETWORK_COLOR,
        linewidth=linewidth,
        alpha=0.55,
    )


def _finalize_map(
    figure,
    axes,
    *,
    title: str,
    bounds,
) -> None:
    """Finaliza título, enquadramento e aparência do mapa"""

    _set_common_extent(
        axes,
        bounds,
    )

    axes.set_title(
        title,
        fontsize=14,
        pad=12,
    )
    axes.set_axis_off()
    figure.tight_layout()


def plot_h_soc(
    geodata: gpd.GeoDataFrame,
    *,
    title: str,
    supported_only: bool = False,
    figsize: tuple[float, float] = (11.0, 11.0),
    background_linewidth: float = 0.25,
    metric_linewidth: float = 1.25,
):
    """Plota H_soc com escala fixa entre zero e um"""

    _require_columns(
        geodata,
        [
            "geometry",
            "H_soc",
            "n_agents",
            "sufficient_flow",
        ],
    )

    figure, axes = plt.subplots(
        figsize=figsize,
    )

    _plot_network_background(
        axes,
        geodata,
        linewidth=background_linewidth,
    )

    observed = geodata.loc[
        geodata[
            "H_soc"
        ].notna()
    ]

    if supported_only:
        insufficient = observed.loc[
            ~observed[
                "sufficient_flow"
            ]
        ]

        if not insufficient.empty:
            insufficient.plot(
                ax=axes,
                color=OBSERVED_INSUFFICIENT_COLOR,
                linewidth=metric_linewidth * 0.65,
                alpha=0.45,
            )

        plotted = observed.loc[
            observed[
                "sufficient_flow"
            ]
        ]
    else:
        plotted = observed

    if not plotted.empty:
        plotted.plot(
            ax=axes,
            column="H_soc",
            cmap=H_SOC_CMAP,
            norm=Normalize(
                vmin=0.0,
                vmax=1.0,
            ),
            linewidth=metric_linewidth,
            legend=True,
            legend_kwds={
                "label": "H_soc",
                "shrink": 0.72,
            },
        )
    else:
        axes.text(
            0.5,
            0.5,
            "Sem segmentos válidos para este filtro",
            transform=axes.transAxes,
            ha="center",
            va="center",
        )

    if supported_only:
        axes.legend(
            handles=[
                Line2D(
                    [0],
                    [0],
                    color=OBSERVED_INSUFFICIENT_COLOR,
                    linewidth=2,
                    alpha=0.55,
                    label="Uso observado com fluxo insuficiente",
                )
            ],
            loc="lower left",
            frameon=False,
        )

    _finalize_map(
        figure,
        axes,
        title=title,
        bounds=geodata.total_bounds,
    )

    return (
        figure,
        axes,
        int(
            len(
                plotted
            )
        ),
    )


def plot_delta_h_soc(
    comparison: gpd.GeoDataFrame,
    *,
    title: str,
    supported_only: bool = False,
    figsize: tuple[float, float] = (11.0, 11.0),
    background_linewidth: float = 0.25,
    metric_linewidth: float = 1.25,
):
    """Plota delta_H_soc com escala divergente fixa e centro em zero"""

    _require_columns(
        comparison,
        [
            "geometry",
            "delta_H_soc",
            "comparable_H_soc",
            "sufficient_flow_both",
        ],
    )

    figure, axes = plt.subplots(
        figsize=figsize,
    )

    _plot_network_background(
        axes,
        comparison,
        linewidth=background_linewidth,
    )

    comparable = comparison.loc[
        comparison[
            "comparable_H_soc"
        ]
        & comparison[
            "delta_H_soc"
        ].notna()
    ]

    if supported_only:
        insufficient = comparable.loc[
            ~comparable[
                "sufficient_flow_both"
            ]
        ]

        if not insufficient.empty:
            insufficient.plot(
                ax=axes,
                color=OBSERVED_INSUFFICIENT_COLOR,
                linewidth=metric_linewidth * 0.65,
                alpha=0.45,
            )

        plotted = comparable.loc[
            comparable[
                "sufficient_flow_both"
            ]
        ]
    else:
        plotted = comparable

    if not plotted.empty:
        plotted.plot(
            ax=axes,
            column="delta_H_soc",
            cmap=DELTA_H_SOC_CMAP,
            norm=TwoSlopeNorm(
                vmin=-1.0,
                vcenter=0.0,
                vmax=1.0,
            ),
            linewidth=metric_linewidth,
            legend=True,
            legend_kwds={
                "label": "ΔH_soc = differentiated − baseline",
                "shrink": 0.72,
            },
        )
    else:
        axes.text(
            0.5,
            0.5,
            "Sem segmentos válidos para este filtro",
            transform=axes.transAxes,
            ha="center",
            va="center",
        )

    if supported_only:
        axes.legend(
            handles=[
                Line2D(
                    [0],
                    [0],
                    color=OBSERVED_INSUFFICIENT_COLOR,
                    linewidth=2,
                    alpha=0.55,
                    label="Comparável com fluxo insuficiente",
                )
            ],
            loc="lower left",
            frameon=False,
        )

    _finalize_map(
        figure,
        axes,
        title=title,
        bounds=comparison.total_bounds,
    )

    return (
        figure,
        axes,
        int(
            len(
                plotted
            )
        ),
    )


def save_pilot_maps(
    *,
    segment_geodata: dict[str, gpd.GeoDataFrame],
    scenario_comparison_geodata: gpd.GeoDataFrame,
    output_dir: Path,
    dpi: int = 220,
) -> pd.DataFrame:
    """Salva os mapas principais do piloto e retorna um manifesto tabular"""

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    required_scenarios = {
        "baseline",
        "differentiated",
    }

    missing_scenarios = (
        required_scenarios
        - set(
            segment_geodata
        )
    )

    if missing_scenarios:
        raise ValueError(
            "Inclui os cenários necessários antes de gerar os mapas: "
            f"{sorted(missing_scenarios)}"
        )

    jobs = [
        {
            "map_id": "h_soc_baseline_all",
            "kind": "h_soc",
            "scenario": "baseline",
            "supported_only": False,
            "title": "H_soc — baseline — todos os segmentos observados",
            "description_pt": (
                "Mostra a diversidade socioeconômica das trajetórias no cenário "
                "baseline para todos os segmentos com H_soc calculável"
            ),
        },
        {
            "map_id": "h_soc_baseline_supported",
            "kind": "h_soc",
            "scenario": "baseline",
            "supported_only": True,
            "title": "H_soc — baseline — fluxo suficiente",
            "description_pt": (
                "Mostra o H_soc no cenário baseline apenas nos segmentos que "
                "atingem o fluxo mínimo de agentes definido para interpretação"
            ),
        },
        {
            "map_id": "h_soc_differentiated_all",
            "kind": "h_soc",
            "scenario": "differentiated",
            "supported_only": False,
            "title": "H_soc — differentiated — todos os segmentos observados",
            "description_pt": (
                "Mostra a diversidade socioeconômica das trajetórias no cenário "
                "differentiated para todos os segmentos com H_soc calculável"
            ),
        },
        {
            "map_id": "h_soc_differentiated_supported",
            "kind": "h_soc",
            "scenario": "differentiated",
            "supported_only": True,
            "title": "H_soc — differentiated — fluxo suficiente",
            "description_pt": (
                "Mostra o H_soc no cenário differentiated apenas nos segmentos "
                "que atingem o fluxo mínimo de agentes definido para interpretação"
            ),
        },
        {
            "map_id": "delta_h_soc_all",
            "kind": "delta_h_soc",
            "scenario": "paired",
            "supported_only": False,
            "title": "ΔH_soc — differentiated − baseline — segmentos comparáveis",
            "description_pt": (
                "Mostra a diferença pareada de H_soc entre differentiated e "
                "baseline nos mesmos segmentos físicos observados nos dois cenários"
            ),
        },
        {
            "map_id": "delta_h_soc_supported",
            "kind": "delta_h_soc",
            "scenario": "paired",
            "supported_only": True,
            "title": "ΔH_soc — differentiated − baseline — fluxo suficiente nos dois",
            "description_pt": (
                "Mostra a diferença pareada de H_soc somente nos segmentos que "
                "atingem o fluxo mínimo de agentes em ambos os cenários"
            ),
        },
    ]

    manifest_rows: list[dict] = []

    for job in jobs:
        if job[
            "kind"
        ] == "h_soc":
            figure, _, n_plotted = plot_h_soc(
                segment_geodata[
                    job[
                        "scenario"
                    ]
                ],
                title=job[
                    "title"
                ],
                supported_only=job[
                    "supported_only"
                ],
            )
        else:
            figure, _, n_plotted = plot_delta_h_soc(
                scenario_comparison_geodata,
                title=job[
                    "title"
                ],
                supported_only=job[
                    "supported_only"
                ],
            )

        filename = (
            f"{job['map_id']}.png"
        )
        path = (
            output_dir
            / filename
        )

        figure.savefig(
            path,
            dpi=dpi,
            bbox_inches="tight",
        )
        plt.close(
            figure
        )

        manifest_rows.append(
            {
                "map_id": job[
                    "map_id"
                ],
                "metric": job[
                    "kind"
                ],
                "scenario": job[
                    "scenario"
                ],
                "supported_only": job[
                    "supported_only"
                ],
                "n_segments_plotted": n_plotted,
                "description_pt": job[
                    "description_pt"
                ],
                "filename": filename,
            }
        )

    manifest = pd.DataFrame(
        manifest_rows
    )

    manifest.to_csv(
        output_dir
        / "map_manifest.csv",
        index=False,
        encoding="utf-8",
    )

    return manifest
