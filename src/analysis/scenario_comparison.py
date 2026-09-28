"""Compare baseline e differentiated no mesmo segmento físico.

Faça a comparação de forma pareada por `analysis_segment_id`. Preserve os
segmentos usados em apenas um cenário e calcule diferenças de H_soc somente
quando ambos os cenários possuírem observações válidas no mesmo segmento.

Não interprete o sinal de `delta_H_soc` como melhora ou piora. Use-o apenas
para descrever aumento ou redução da diversidade socioeconômica observada das
trajetórias naquele segmento.
"""

from __future__ import annotations

from collections.abc import Iterable

import geopandas as gpd
import pandas as pd


DEFAULT_FLOW_THRESHOLDS = (
    2,
    3,
    5,
    10,
)


def _require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
) -> None:
    """Exija as colunas necessárias antes de comparar os cenários."""

    missing = (
        set(columns)
        - set(frame.columns)
    )

    if missing:
        raise ValueError(
            "Adicione as colunas obrigatórias antes da comparação: "
            f"{sorted(missing)}"
        )


def _prepare_scenario(
    statistics: pd.DataFrame,
    *,
    scenario_name: str,
    suffix: str,
) -> pd.DataFrame:
    """Selecione um cenário e aplique sufixos às métricas comparadas."""

    scenario = statistics.loc[
        statistics[
            "scenario"
        ]
        == scenario_name
    ].copy()

    if scenario.empty:
        raise ValueError(
            f"Calcule antes as estatísticas do cenário '{scenario_name}'."
        )

    if scenario[
        "analysis_segment_id"
    ].duplicated().any():
        raise ValueError(
            "Preserve uma única linha por analysis_segment_id em cada cenário."
        )

    scenario = scenario.drop(
        columns=[
            "scenario",
        ]
    )

    rename = {
        column: f"{column}_{suffix}"
        for column in scenario.columns
        if column != "analysis_segment_id"
    }

    return scenario.rename(
        columns=rename
    )


def build_scenario_comparison(
    statistics: pd.DataFrame,
    *,
    baseline_name: str = "baseline",
    differentiated_name: str = "differentiated",
    min_agents_for_interpretation: int = 5,
    flow_thresholds: Iterable[int] = DEFAULT_FLOW_THRESHOLDS,
) -> pd.DataFrame:
    """
    Compare os cenários de forma pareada nos mesmos segmentos físicos.

    Preserve a união dos segmentos usados nos dois cenários. Marque o estado
    de uso como `used_both`, `baseline_only` ou `differentiated_only`.
    Calcule `delta_H_soc = H_soc_differentiated - H_soc_baseline` somente
    quando ambos os valores existirem no mesmo segmento.

    Marque `sufficient_flow_both` quando o mesmo segmento atingir o fluxo
    mínimo nos dois cenários. Crie também flags de sensibilidade pareadas para
    todos os limiares solicitados.
    """

    _require_columns(
        statistics,
        [
            "scenario",
            "analysis_segment_id",
            "n_passages",
            "n_agents",
            "H_soc",
            "n_low",
            "n_middle",
            "n_high",
            "p_low",
            "p_middle",
            "p_high",
        ],
    )

    if min_agents_for_interpretation < 1:
        raise ValueError(
            "Use min_agents_for_interpretation maior ou igual a 1."
        )

    thresholds = tuple(
        sorted(
            {
                int(value)
                for value in flow_thresholds
            }
        )
    )

    if any(
        threshold < 1
        for threshold in thresholds
    ):
        raise ValueError(
            "Use somente limiares de fluxo maiores ou iguais a 1."
        )

    baseline = _prepare_scenario(
        statistics,
        scenario_name=baseline_name,
        suffix="baseline",
    )

    differentiated = _prepare_scenario(
        statistics,
        scenario_name=differentiated_name,
        suffix="differentiated",
    )

    comparison = baseline.merge(
        differentiated,
        on="analysis_segment_id",
        how="outer",
        validate="one_to_one",
        indicator=True,
    )

    comparison[
        "used_baseline"
    ] = comparison[
        "_merge"
    ].isin(
        [
            "left_only",
            "both",
        ]
    )

    comparison[
        "used_differentiated"
    ] = comparison[
        "_merge"
    ].isin(
        [
            "right_only",
            "both",
        ]
    )

    comparison[
        "used_both"
    ] = (
        comparison[
            "used_baseline"
        ]
        & comparison[
            "used_differentiated"
        ]
    )

    comparison[
        "usage_status"
    ] = (
        comparison[
            "_merge"
        ]
        .map(
            {
                "left_only": "baseline_only",
                "right_only": "differentiated_only",
                "both": "used_both",
            }
        )
        .astype(
            "object"
        )
    )

    comparison = comparison.drop(
        columns=[
            "_merge",
        ]
    )

    for column in [
        "n_passages",
        "n_agents",
        "n_low",
        "n_middle",
        "n_high",
    ]:
        baseline_column = f"{column}_baseline"
        differentiated_column = f"{column}_differentiated"

        if baseline_column in comparison.columns:
            comparison[
                baseline_column
            ] = comparison[
                baseline_column
            ].fillna(
                0
            ).astype(
                int
            )

        if differentiated_column in comparison.columns:
            comparison[
                differentiated_column
            ] = comparison[
                differentiated_column
            ].fillna(
                0
            ).astype(
                int
            )

    comparison[
        "delta_n_agents"
    ] = (
        comparison[
            "n_agents_differentiated"
        ]
        - comparison[
            "n_agents_baseline"
        ]
    )

    comparison[
        "delta_n_passages"
    ] = (
        comparison[
            "n_passages_differentiated"
        ]
        - comparison[
            "n_passages_baseline"
        ]
    )

    comparable_h = (
        comparison[
            "H_soc_baseline"
        ].notna()
        & comparison[
            "H_soc_differentiated"
        ].notna()
    )

    comparison[
        "comparable_H_soc"
    ] = comparable_h

    comparison[
        "delta_H_soc"
    ] = (
        comparison[
            "H_soc_differentiated"
        ]
        - comparison[
            "H_soc_baseline"
        ]
    ).where(
        comparable_h
    )

    comparison[
        "abs_delta_H_soc"
    ] = comparison[
        "delta_H_soc"
    ].abs()

    for group in (
        "low",
        "middle",
        "high",
    ):
        p_baseline = f"p_{group}_baseline"
        p_differentiated = f"p_{group}_differentiated"

        comparison[
            f"delta_p_{group}"
        ] = (
            comparison[
                p_differentiated
            ]
            - comparison[
                p_baseline
            ]
        ).where(
            comparison[
                p_baseline
            ].notna()
            & comparison[
                p_differentiated
            ].notna()
        )

    comparison[
        "sufficient_flow_both"
    ] = (
        comparison[
            "n_agents_baseline"
        ]
        >= min_agents_for_interpretation
    ) & (
        comparison[
            "n_agents_differentiated"
        ]
        >= min_agents_for_interpretation
    )

    for threshold in thresholds:
        comparison[
            f"flow_ge_{threshold}_both"
        ] = (
            comparison[
                "n_agents_baseline"
            ]
            >= threshold
        ) & (
            comparison[
                "n_agents_differentiated"
            ]
            >= threshold
        )

    core_columns = [
        "analysis_segment_id",
        "usage_status",
        "used_baseline",
        "used_differentiated",
        "used_both",
        "n_agents_baseline",
        "n_agents_differentiated",
        "delta_n_agents",
        "n_passages_baseline",
        "n_passages_differentiated",
        "delta_n_passages",
        "H_soc_baseline",
        "H_soc_differentiated",
        "delta_H_soc",
        "abs_delta_H_soc",
        "comparable_H_soc",
        "sufficient_flow_both",
        *[
            f"flow_ge_{threshold}_both"
            for threshold in thresholds
        ],
        "n_low_baseline",
        "n_low_differentiated",
        "n_middle_baseline",
        "n_middle_differentiated",
        "n_high_baseline",
        "n_high_differentiated",
        "p_low_baseline",
        "p_low_differentiated",
        "delta_p_low",
        "p_middle_baseline",
        "p_middle_differentiated",
        "delta_p_middle",
        "p_high_baseline",
        "p_high_differentiated",
        "delta_p_high",
    ]

    additional_columns = [
        column
        for column in comparison.columns
        if column not in core_columns
    ]

    return (
        comparison[
            core_columns
            + additional_columns
        ]
        .sort_values(
            "analysis_segment_id"
        )
        .reset_index(
            drop=True
        )
    )


def attach_comparison_to_segments(
    analysis_segments: gpd.GeoDataFrame,
    comparison: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """
    Anexe a comparação à rede física completa.

    Preserve segmentos não usados em nenhum cenário. Preencha apenas flags e
    volumes com valores neutros; mantenha H_soc e deltas como NaN quando não
    houver uma comparação observável.
    """

    _require_columns(
        analysis_segments,
        [
            "analysis_segment_id",
            "geometry",
        ],
    )
    _require_columns(
        comparison,
        [
            "analysis_segment_id",
            "used_baseline",
            "used_differentiated",
            "used_both",
            "n_agents_baseline",
            "n_agents_differentiated",
            "n_passages_baseline",
            "n_passages_differentiated",
            "delta_n_agents",
            "delta_n_passages",
            "comparable_H_soc",
            "sufficient_flow_both",
        ],
    )

    if analysis_segments[
        "analysis_segment_id"
    ].duplicated().any():
        raise ValueError(
            "Preserve analysis_segment_id único na camada física."
        )

    result = analysis_segments.merge(
        comparison,
        on="analysis_segment_id",
        how="left",
        validate="one_to_one",
    )

    boolean_columns = [
        column
        for column in result.columns
        if (
            column.startswith(
                "flow_ge_"
            )
            and column.endswith(
                "_both"
            )
        )
    ] + [
        "used_baseline",
        "used_differentiated",
        "used_both",
        "comparable_H_soc",
        "sufficient_flow_both",
    ]

    for column in boolean_columns:
        if column in result.columns:
            result[
                column
            ] = result[
                column
            ].fillna(
                False
            ).astype(
                bool
            )

    integer_columns = [
        "n_agents_baseline",
        "n_agents_differentiated",
        "delta_n_agents",
        "n_passages_baseline",
        "n_passages_differentiated",
        "delta_n_passages",
        "n_low_baseline",
        "n_low_differentiated",
        "n_middle_baseline",
        "n_middle_differentiated",
        "n_high_baseline",
        "n_high_differentiated",
    ]

    for column in integer_columns:
        if column in result.columns:
            result[
                column
            ] = result[
                column
            ].fillna(
                0
            ).astype(
                int
            )

    result[
        "usage_status"
    ] = result[
        "usage_status"
    ].fillna(
        "unused_both"
    )

    return gpd.GeoDataFrame(
        result,
        geometry="geometry",
        crs=analysis_segments.crs,
    )


def comparison_summary(
    comparison: pd.DataFrame,
    *,
    min_agents_for_interpretation: int = 5,
    flow_thresholds: Iterable[int] = DEFAULT_FLOW_THRESHOLDS,
) -> dict:
    """Resuma a comparabilidade espacial dos dois cenários."""

    _require_columns(
        comparison,
        [
            "usage_status",
            "used_both",
            "delta_H_soc",
            "sufficient_flow_both",
            "n_agents_baseline",
            "n_agents_differentiated",
        ],
    )

    thresholds = tuple(
        sorted(
            {
                int(value)
                for value in flow_thresholds
            }
        )
    )

    paired = comparison.loc[
        comparison[
            "used_both"
        ]
    ]

    supported = comparison.loc[
        comparison[
            "sufficient_flow_both"
        ]
    ]

    result = {
        "segments_union": int(
            len(
                comparison
            )
        ),
        "used_both": int(
            (
                comparison[
                    "usage_status"
                ]
                == "used_both"
            ).sum()
        ),
        "baseline_only": int(
            (
                comparison[
                    "usage_status"
                ]
                == "baseline_only"
            ).sum()
        ),
        "differentiated_only": int(
            (
                comparison[
                    "usage_status"
                ]
                == "differentiated_only"
            ).sum()
        ),
        "paired_delta_H_soc_mean": float(
            paired[
                "delta_H_soc"
            ].mean()
        ) if not paired.empty else float(
            "nan"
        ),
        "paired_delta_H_soc_median": float(
            paired[
                "delta_H_soc"
            ].median()
        ) if not paired.empty else float(
            "nan"
        ),
        "sufficient_flow_both": int(
            len(
                supported
            )
        ),
        "sufficient_flow_min_agents": int(
            min_agents_for_interpretation
        ),
        "sufficient_delta_H_soc_mean": float(
            supported[
                "delta_H_soc"
            ].mean()
        ) if not supported.empty else float(
            "nan"
        ),
        "sufficient_delta_H_soc_median": float(
            supported[
                "delta_H_soc"
            ].median()
        ) if not supported.empty else float(
            "nan"
        ),
    }

    for threshold in thresholds:
        column = f"flow_ge_{threshold}_both"

        result[
            column
        ] = int(
            comparison[
                column
            ].sum()
        ) if column in comparison.columns else 0

    return result
