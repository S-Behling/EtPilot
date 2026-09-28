"""Agrega o uso das trajetórias por segmento físico comum

Conta passagens e agentes separadamente. Usa agentes distintos para calcular
as composições socioeconômica, modal e funcional, evitando que uma
segmentação 1:N ou uma repetição da mesma trajetória aumente artificialmente
o peso de um agente

Calcula `H_soc` com as contagens de agentes distintos por grupo de renda
Mantém o volume observado ao lado da entropia e marca explicitamente os
segmentos com fluxo suficiente para interpretação
"""

from __future__ import annotations

from collections.abc import Iterable

import geopandas as gpd
import pandas as pd

from src.analysis.entropy import normalized_shannon_entropy
from src.domain.enums import IncomeGroup, TravelMode, TripPurpose


DEFAULT_INCOME_GROUPS = tuple(
    group.value
    for group in IncomeGroup
)
DEFAULT_MODES = tuple(
    mode.value
    for mode in TravelMode
)
DEFAULT_PURPOSES = tuple(
    purpose.value
    for purpose in TripPurpose
)
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
    """Exige todas as colunas necessárias antes de agregar os dados"""

    required = set(
        columns
    )
    missing = (
        required
        - set(frame.columns)
    )

    if missing:
        raise ValueError(
            "Adicione as colunas obrigatórias antes de calcular "
            f"as estatísticas: {sorted(missing)}"
        )


def _validate_categories(
    frame: pd.DataFrame,
    *,
    column: str,
    categories: tuple[str, ...],
) -> None:
    """Rejeita categorias inesperadas para preservar comparabilidade"""

    observed = set(
        frame[
            column
        ]
        .dropna()
        .astype(str)
        .unique()
    )
    expected = set(
        categories
    )

    unexpected = (
        observed
        - expected
    )

    if unexpected:
        raise ValueError(
            f"Revise as categorias inesperadas em '{column}': "
            f"{sorted(unexpected)}"
        )


def _validate_agent_income(
    edge_usage: pd.DataFrame,
) -> None:
    """Garante que cada agente mantém um único grupo de renda por cenário"""

    inconsistent = (
        edge_usage
        .groupby(
            [
                "scenario",
                "agent_id",
            ]
        )[
            "income_group"
        ]
        .nunique(
            dropna=False
        )
    )

    inconsistent = inconsistent[
        inconsistent > 1
    ]

    if not inconsistent.empty:
        raise ValueError(
            "Preserve um único income_group por agente dentro de cada cenário."
        )


def _add_category_counts(
    statistics: pd.DataFrame,
    observations: pd.DataFrame,
    *,
    column: str,
    categories: tuple[str, ...],
    prefix: str,
) -> pd.DataFrame:
    """Adiciona contagens de agentes distintos para todas as categorias"""

    counts = pd.crosstab(
        index=[
            observations[
                "scenario"
            ],
            observations[
                "analysis_segment_id"
            ],
        ],
        columns=observations[
            column
        ],
    )

    counts = counts.reindex(
        columns=list(
            categories
        ),
        fill_value=0,
    )

    counts.columns = [
        f"{prefix}_{category}"
        for category in categories
    ]

    counts = (
        counts
        .reset_index()
    )

    return statistics.merge(
        counts,
        on=[
            "scenario",
            "analysis_segment_id",
        ],
        how="left",
        validate="one_to_one",
    )


def build_segment_statistics(
    edge_usage: pd.DataFrame,
    *,
    income_groups: Iterable[str] = DEFAULT_INCOME_GROUPS,
    modes: Iterable[str] = DEFAULT_MODES,
    purposes: Iterable[str] = DEFAULT_PURPOSES,
    min_agents_for_interpretation: int = 5,
    flow_thresholds: Iterable[int] = DEFAULT_FLOW_THRESHOLDS,
) -> pd.DataFrame:
    """
    Calcula volume, composição e entropia para cada segmento usado

    Conta `n_passages` a partir de todas as linhas harmonizadas. Conta
    `n_agents` e as composições a partir de pares únicos
    agente × segmento. Calcula `H_soc` com agentes distintos por grupo de
    renda para representar a diversidade das trajetórias que alcançam o
    segmento, e não o número de registros produzido pela harmonização
    """

    _require_columns(
        edge_usage,
        [
            "scenario",
            "analysis_segment_id",
            "agent_id",
            "income_group",
            "mode",
            "purpose",
            "modal_edge_id",
        ],
    )

    if edge_usage.empty:
        raise ValueError(
            "Forneça pelo menos uma passagem harmonizada."
        )

    if min_agents_for_interpretation < 1:
        raise ValueError(
            "Use min_agents_for_interpretation maior ou igual a 1."
        )

    income_groups = tuple(
        str(value)
        for value in income_groups
    )
    modes = tuple(
        str(value)
        for value in modes
    )
    purposes = tuple(
        str(value)
        for value in purposes
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

    _validate_categories(
        edge_usage,
        column="income_group",
        categories=income_groups,
    )
    _validate_categories(
        edge_usage,
        column="mode",
        categories=modes,
    )
    _validate_categories(
        edge_usage,
        column="purpose",
        categories=purposes,
    )
    _validate_agent_income(
        edge_usage
    )

    # Conta todas as passagens registradas depois da harmonização 1:N
    volume = (
        edge_usage
        .groupby(
            [
                "scenario",
                "analysis_segment_id",
            ],
            as_index=False,
        )
        .agg(
            n_passages=(
                "agent_id",
                "size",
            ),
            n_modal_edges=(
                "modal_edge_id",
                "nunique",
            ),
        )
    )

    # Preserva somente uma observação por agente em cada segmento físico
    agent_segment = (
        edge_usage[
            [
                "scenario",
                "analysis_segment_id",
                "agent_id",
                "income_group",
                "mode",
                "purpose",
            ]
        ]
        .drop_duplicates(
            subset=[
                "scenario",
                "analysis_segment_id",
                "agent_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    agents = (
        agent_segment
        .groupby(
            [
                "scenario",
                "analysis_segment_id",
            ],
            as_index=False,
        )
        .agg(
            n_agents=(
                "agent_id",
                "nunique",
            )
        )
    )

    statistics = volume.merge(
        agents,
        on=[
            "scenario",
            "analysis_segment_id",
        ],
        how="inner",
        validate="one_to_one",
    )

    statistics = _add_category_counts(
        statistics,
        agent_segment,
        column="income_group",
        categories=income_groups,
        prefix="n",
    )

    statistics = _add_category_counts(
        statistics,
        agent_segment,
        column="mode",
        categories=modes,
        prefix="n_mode",
    )

    statistics = _add_category_counts(
        statistics,
        agent_segment,
        column="purpose",
        categories=purposes,
        prefix="n_purpose",
    )

    income_count_columns = [
        f"n_{group}"
        for group in income_groups
    ]

    statistics[
        income_count_columns
    ] = statistics[
        income_count_columns
    ].fillna(
        0
    ).astype(
        int
    )

    for group in income_groups:
        statistics[
            f"p_{group}"
        ] = (
            statistics[
                f"n_{group}"
            ]
            / statistics[
                "n_agents"
            ]
        )

    statistics[
        "income_groups_present"
    ] = (
        statistics[
            income_count_columns
        ]
        .gt(
            0
        )
        .sum(
            axis=1
        )
        .astype(
            int
        )
    )

    statistics[
        "H_soc"
    ] = statistics[
        income_count_columns
    ].apply(
        lambda row: normalized_shannon_entropy(
            row.to_numpy(),
            n_categories=len(
                income_groups
            ),
        ),
        axis=1,
    )

    statistics[
        "sufficient_flow"
    ] = (
        statistics[
            "n_agents"
        ]
        >= min_agents_for_interpretation
    )

    for threshold in thresholds:
        statistics[
            f"flow_ge_{threshold}"
        ] = (
            statistics[
                "n_agents"
            ]
            >= threshold
        )

    mode_columns = [
        f"n_mode_{mode}"
        for mode in modes
    ]
    purpose_columns = [
        f"n_purpose_{purpose}"
        for purpose in purposes
    ]

    statistics[
        mode_columns
        + purpose_columns
    ] = statistics[
        mode_columns
        + purpose_columns
    ].fillna(
        0
    ).astype(
        int
    )

    statistics[
        "modes_present"
    ] = (
        statistics[
            mode_columns
        ]
        .gt(
            0
        )
        .sum(
            axis=1
        )
        .astype(
            int
        )
    )

    statistics[
        "purposes_present"
    ] = (
        statistics[
            purpose_columns
        ]
        .gt(
            0
        )
        .sum(
            axis=1
        )
        .astype(
            int
        )
    )

    ordered_columns = [
        "scenario",
        "analysis_segment_id",
        "n_passages",
        "n_agents",
        "n_modal_edges",
        *income_count_columns,
        *[
            f"p_{group}"
            for group in income_groups
        ],
        "income_groups_present",
        "H_soc",
        "sufficient_flow",
        *[
            f"flow_ge_{threshold}"
            for threshold in thresholds
        ],
        *mode_columns,
        "modes_present",
        *purpose_columns,
        "purposes_present",
    ]

    return (
        statistics[
            ordered_columns
        ]
        .sort_values(
            [
                "scenario",
                "analysis_segment_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


def attach_statistics_to_segments(
    analysis_segments: gpd.GeoDataFrame,
    statistics: pd.DataFrame,
    *,
    scenario_name: str,
    income_groups: Iterable[str] = DEFAULT_INCOME_GROUPS,
    modes: Iterable[str] = DEFAULT_MODES,
    purposes: Iterable[str] = DEFAULT_PURPOSES,
    flow_thresholds: Iterable[int] = DEFAULT_FLOW_THRESHOLDS,
) -> gpd.GeoDataFrame:
    """
    Anexe as métricas a toda a rede física e preserva segmentos sem uso

    Preenche contagens ausentes com zero. Preserva `H_soc` e proporções como
    NaN em segmentos não observados para diferenciar ausência de fluxo de
    composição homogênea
    """

    _require_columns(
        analysis_segments,
        [
            "analysis_segment_id",
            "geometry",
        ],
    )

    if analysis_segments[
        "analysis_segment_id"
    ].duplicated().any():
        raise ValueError(
            "Preserve analysis_segment_id único na camada física."
        )

    scenario_statistics = statistics.loc[
        statistics[
            "scenario"
        ]
        == scenario_name
    ].copy()

    if scenario_statistics.empty:
        raise ValueError(
            f"Calcule antes as estatísticas do cenário '{scenario_name}'."
        )

    result = analysis_segments.merge(
        scenario_statistics.drop(
            columns=[
                "scenario",
            ]
        ),
        on="analysis_segment_id",
        how="left",
        validate="one_to_one",
    )

    result.insert(
        1,
        "scenario",
        scenario_name,
    )

    income_groups = tuple(
        str(value)
        for value in income_groups
    )
    modes = tuple(
        str(value)
        for value in modes
    )
    purposes = tuple(
        str(value)
        for value in purposes
    )
    thresholds = tuple(
        sorted(
            {
                int(value)
                for value in flow_thresholds
            }
        )
    )

    count_columns = [
        "n_passages",
        "n_agents",
        "n_modal_edges",
        *[
            f"n_{group}"
            for group in income_groups
        ],
        "income_groups_present",
        *[
            f"n_mode_{mode}"
            for mode in modes
        ],
        "modes_present",
        *[
            f"n_purpose_{purpose}"
            for purpose in purposes
        ],
        "purposes_present",
    ]

    for column in count_columns:
        if column in result.columns:
            result[
                column
            ] = (
                result[
                    column
                ]
                .fillna(
                    0
                )
                .astype(
                    int
                )
            )

    result[
        "used"
    ] = (
        result[
            "n_agents"
        ]
        > 0
    )

    if "sufficient_flow" in result.columns:
        result[
            "sufficient_flow"
        ] = (
            result[
                "sufficient_flow"
            ]
            .fillna(
                False
            )
            .astype(
                bool
            )
        )

    for threshold in thresholds:
        column = f"flow_ge_{threshold}"

        if column in result.columns:
            result[
                column
            ] = (
                result[
                    column
                ]
                .fillna(
                    False
                )
                .astype(
                    bool
                )
            )

    return gpd.GeoDataFrame(
        result,
        geometry="geometry",
        crs=analysis_segments.crs,
    )
