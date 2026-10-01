"""Converte rotas dos agentes em registros de uso das redes.

Esta camada normaliza trajetórias de walk, bike, car e transit em uma tabela
longa. Ela não calcula ainda H_soc nem segmentos físicos comuns; sua função é
preservar quem utilizou qual aresta para alimentar as próximas etapas.
"""

from __future__ import annotations

import pandas as pd

from src.domain.enums import TravelMode


OSM_MODES = {
    TravelMode.WALK.value,
    TravelMode.BIKE.value,
    TravelMode.CAR.value,
}


def build_edge_usage(
    agents,
    *,
    transit_connection_to_physical_edge: pd.DataFrame,
) -> pd.DataFrame:
    """Retorna uma linha por agente e aresta efetivamente percorrida."""

    transit_mapping = _prepare_transit_mapping(
        transit_connection_to_physical_edge
    )

    rows: list[dict] = []

    for agent in agents:
        mode = getattr(agent, "mode", None)

        if mode is None:
            continue

        mode_name = (
            mode.value
            if hasattr(mode, "value")
            else str(mode)
        )

        common = {
            "agent_id": agent.agent_id,
            "income_group": (
                agent.income_group.value
                if hasattr(agent.income_group, "value")
                else str(agent.income_group)
            ),
            "trip_mode": mode_name,
        }

        if mode_name in OSM_MODES:
            _append_osm_edges(
                rows,
                common=common,
                route_edges=getattr(
                    agent,
                    "route_edges",
                    [],
                ),
                network_mode=mode_name,
                leg_type="main",
            )
            continue

        if mode_name != TravelMode.TRANSIT.value:
            continue

        _append_osm_edges(
            rows,
            common=common,
            route_edges=getattr(
                agent,
                "transit_access_walk_edges",
                [],
            ),
            network_mode=TravelMode.WALK.value,
            leg_type="transit_access",
        )

        _append_transit_edges(
            rows,
            common=common,
            connection_ids=getattr(
                agent,
                "transit_connection_ids",
                [],
            ),
            transit_mapping=transit_mapping,
        )

        _append_osm_edges(
            rows,
            common=common,
            route_edges=getattr(
                agent,
                "transit_egress_walk_edges",
                [],
            ),
            network_mode=TravelMode.WALK.value,
            leg_type="transit_egress",
        )

    columns = [
        "agent_id",
        "income_group",
        "trip_mode",
        "leg_type",
        "network_mode",
        "edge_id",
        "u",
        "v",
        "key",
        "connection_id",
        "transit_physical_edge_id",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(rows).reindex(
        columns=columns
    )


def aggregate_edge_usage(
    edge_usage: pd.DataFrame,
) -> pd.DataFrame:
    """Agrega fluxos por aresta, grupo de renda, modo e tipo de trecho."""

    if edge_usage.empty:
        return pd.DataFrame(
            columns=[
                "network_mode",
                "edge_id",
                "income_group",
                "trip_mode",
                "leg_type",
                "n_traversals",
                "n_agents",
            ]
        )

    required = {
        "agent_id",
        "income_group",
        "trip_mode",
        "leg_type",
        "network_mode",
        "edge_id",
    }

    missing = required - set(edge_usage.columns)

    if missing:
        raise ValueError(
            "edge_usage não possui as colunas obrigatórias: "
            f"{sorted(missing)}"
        )

    return (
        edge_usage.groupby(
            [
                "network_mode",
                "edge_id",
                "income_group",
                "trip_mode",
                "leg_type",
            ],
            dropna=False,
            as_index=False,
        )
        .agg(
            n_traversals=("agent_id", "size"),
            n_agents=("agent_id", "nunique"),
        )
    )


def _append_osm_edges(
    rows: list[dict],
    *,
    common: dict,
    route_edges,
    network_mode: str,
    leg_type: str,
) -> None:
    for u, v, key in route_edges:
        rows.append(
            {
                **common,
                "leg_type": leg_type,
                "network_mode": network_mode,
                "edge_id": (
                    f"{network_mode}:{int(u)}:"
                    f"{int(v)}:{int(key)}"
                ),
                "u": int(u),
                "v": int(v),
                "key": int(key),
                "connection_id": None,
                "transit_physical_edge_id": None,
            }
        )


def _append_transit_edges(
    rows: list[dict],
    *,
    common: dict,
    connection_ids,
    transit_mapping: pd.DataFrame,
) -> None:
    for connection_id in connection_ids:
        connection_text = str(connection_id)

        mapped = transit_mapping.loc[
            transit_mapping["connection_id"]
            == connection_text
        ]

        for row in mapped.itertuples(index=False):
            physical_id = str(
                row.transit_physical_edge_id
            )

            rows.append(
                {
                    **common,
                    "leg_type": "transit_in_vehicle",
                    "network_mode": TravelMode.TRANSIT.value,
                    "edge_id": (
                        f"transit:{physical_id}"
                    ),
                    "u": None,
                    "v": None,
                    "key": None,
                    "connection_id": connection_text,
                    "transit_physical_edge_id": physical_id,
                }
            )


def _prepare_transit_mapping(
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    required = {
        "connection_id",
        "transit_physical_edge_id",
    }

    missing = required - set(mapping.columns)

    if missing:
        raise ValueError(
            "Mapeamento transit não possui as colunas obrigatórias: "
            f"{sorted(missing)}"
        )

    result = mapping[
        [
            "connection_id",
            "transit_physical_edge_id",
        ]
    ].dropna().copy()

    result["connection_id"] = (
        result["connection_id"].astype(str)
    )
    result["transit_physical_edge_id"] = (
        result["transit_physical_edge_id"].astype(str)
    )

    return result



def edge_composition_summary(
    edge_usage: pd.DataFrame,
) -> pd.DataFrame:
    """Resume quais modos e grupos de renda utilizaram cada aresta modal.

    A unidade ainda é a aresta de cada rede modal. A unificação entre redes
    distintas em um mesmo segmento físico será tratada em etapa posterior.
    """

    if edge_usage.empty:
        return pd.DataFrame(
            columns=[
                "network_mode",
                "edge_id",
                "trip_modes",
                "income_groups",
                "n_trip_modes",
                "n_income_groups",
                "n_traversals",
                "n_agents",
            ]
        )

    required = {
        "network_mode",
        "edge_id",
        "trip_mode",
        "income_group",
        "agent_id",
    }

    missing = required - set(edge_usage.columns)

    if missing:
        raise ValueError(
            "edge_usage não possui as colunas obrigatórias: "
            f"{sorted(missing)}"
        )

    def join_unique(series: pd.Series) -> str:
        values = sorted(
            {
                str(value)
                for value in series.dropna()
            }
        )
        return "|".join(values)

    return (
        edge_usage.groupby(
            [
                "network_mode",
                "edge_id",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            trip_modes=("trip_mode", join_unique),
            income_groups=("income_group", join_unique),
            n_trip_modes=("trip_mode", "nunique"),
            n_income_groups=("income_group", "nunique"),
            n_traversals=("agent_id", "size"),
            n_agents=("agent_id", "nunique"),
        )
    )
