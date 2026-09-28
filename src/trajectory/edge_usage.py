"""Converte trajetórias dos agentes em observações de uso das arestas

Cada linha representa a passagem de um agente por uma aresta da rede modal
Como carro, bicicleta e caminhada usam grafos diferentes, a identidade da
aresta inclui obrigatoriamente o modo

Esta tabela ainda NÃO representa a unidade espacial comum de análise entre
modos. Essa harmonização será realizada em uma etapa posterior
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from src.domain.agent import Agent
from src.routing.multimodal_router import SUCCESS_STATUSES


def _enum_value(value) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _edge_attributes(
    graph,
    u: int,
    v: int,
    key: int,
) -> Mapping:
    """Retorna os atributos da aresta exata usada na rota"""

    attributes = graph.get_edge_data(
        u,
        v,
        key,
    )

    if attributes is None:
        raise ValueError(
            "Aresta da rota não encontrada no grafo: "
            f"({u}, {v}, {key})."
        )

    return attributes


def _safe_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stringify_osm_value(value) -> str | None:
    """Converte atributos OSM heterogêneos em texto estável para CSV"""

    if value is None:
        return None

    if isinstance(value, (list, tuple, set)):
        return "|".join(
            str(item)
            for item in value
        )

    return str(value)


def build_edge_usage(
    agents: list[Agent],
    graphs: Mapping[str, object],
    *,
    scenario_name: str,
) -> pd.DataFrame:
    """
    Explode as trajetórias em uma linha por agente × aresta

    Parameters
    ----------
    agents
        Agentes já roteados
    graphs
        Dicionário modo -> MultiDiGraph
    scenario_name
        Nome do cenário experimental

    Returns
    -------
    pandas.DataFrame
        Tabela pronta para agregações por renda, modo, propósito e aresta
    """

    rows: list[dict] = []

    for agent in agents:
        if agent.route_status not in SUCCESS_STATUSES:
            continue

        mode = _enum_value(
            agent.mode
        )

        if mode is None:
            continue

        if mode not in graphs:
            raise ValueError(
                f"Rede ausente para o modo '{mode}'."
            )

        graph = graphs[mode]

        total_edges = len(
            agent.route_edges
        )

        for position, (
            u,
            v,
            key,
        ) in enumerate(
            agent.route_edges
        ):
            attributes = _edge_attributes(
                graph,
                int(u),
                int(v),
                int(key),
            )

            rows.append(
                {
                    "scenario": scenario_name,
                    "agent_id": agent.agent_id,
                    "income_group": _enum_value(
                        agent.income_group
                    ),
                    "purpose": _enum_value(
                        agent.purpose
                    ),
                    "mode": mode,
                    "mapping_mode": mode,
                    "leg_mode": mode,
                    "origin_id": agent.origin_id,
                    "destination_id": (
                        agent.destination_id
                    ),
                    "route_position": position,
                    "route_edge_count": total_edges,
                    "u": int(u),
                    "v": int(v),
                    "key": int(key),
                    "modal_edge_id": (
                        f"{mode}:{int(u)}:{int(v)}:{int(key)}"
                    ),
                    "edge_length_m": _safe_float(
                        attributes.get("length")
                    ),
                    "osmid": _stringify_osm_value(
                        attributes.get("osmid")
                    ),
                    "name": _stringify_osm_value(
                        attributes.get("name")
                    ),
                    "highway": _stringify_osm_value(
                        attributes.get("highway")
                    ),
                }
            )

    columns = [
        "scenario",
        "agent_id",
        "income_group",
        "purpose",
        "mode",
        "mapping_mode",
        "leg_mode",
        "origin_id",
        "destination_id",
        "route_position",
        "route_edge_count",
        "u",
        "v",
        "key",
        "modal_edge_id",
        "edge_length_m",
        "osmid",
        "name",
        "highway",
    ]

    return pd.DataFrame(
        rows,
        columns=columns,
    )
