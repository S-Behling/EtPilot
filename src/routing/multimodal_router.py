"""Roteamento nas redes OSM de caminhada, bicicleta e carro."""

from __future__ import annotations

from collections.abc import Mapping

import networkx as nx
import pandas as pd

from src.domain.agent import Agent


ROUTE_OK = "ok"
ROUTE_SAME_NODE = "same_node"
ROUTE_NO_PATH = "no_path"
ROUTE_INVALID_NODE = "invalid_node"
ROUTE_MISSING_NODE = "missing_node"
ROUTE_MISSING_MODE = "missing_mode"
ROUTE_UNSUPPORTED_MODE = "unsupported_mode"
ROUTE_ERROR = "error"

SUCCESS_STATUSES = {
    ROUTE_OK,
    ROUTE_SAME_NODE,
}


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _edge_numeric_value(
    attributes: Mapping,
    attribute: str,
) -> float:
    value = attributes.get(attribute)

    if value is None:
        raise ValueError(
            f"Aresta sem atributo obrigatório '{attribute}'."
        )

    result = float(value)

    if result < 0:
        raise ValueError(
            f"Valor negativo para '{attribute}': {result}"
        )

    return result


def _select_parallel_edge(
    graph,
    u: int,
    v: int,
    *,
    weight: str,
) -> tuple[int, Mapping]:
    edge_bundle = graph.get_edge_data(u, v)

    if not edge_bundle:
        raise ValueError(
            f"Nenhuma aresta encontrada entre ({u}, {v})."
        )

    candidates = []

    for key, attributes in edge_bundle.items():
        try:
            edge_weight = _edge_numeric_value(
                attributes,
                weight,
            )
        except (TypeError, ValueError):
            continue

        candidates.append(
            (edge_weight, key, attributes)
        )

    if not candidates:
        raise ValueError(
            f"Nenhuma aresta entre ({u}, {v}) possui "
            f"peso válido em '{weight}'."
        )

    _, key, attributes = min(
        candidates,
        key=lambda item: item[0],
    )

    return int(key), attributes


def node_path_to_edges(
    graph,
    node_path: list[int],
    *,
    weight: str = "length",
) -> tuple[list[tuple[int, int, int]], float]:
    """Converte uma sequência de nós em arestas exatas do MultiDiGraph."""

    if len(node_path) < 2:
        return [], 0.0

    route_edges = []
    total_weight = 0.0

    for u, v in zip(
        node_path[:-1],
        node_path[1:],
    ):
        key, attributes = _select_parallel_edge(
            graph,
            u,
            v,
            weight=weight,
        )

        route_edges.append(
            (int(u), int(v), int(key))
        )
        total_weight += _edge_numeric_value(
            attributes,
            weight,
        )

    return route_edges, total_weight


def route_agent(
    agent: Agent,
    graphs: Mapping[str, object],
    *,
    weight: str = "length",
    strict: bool = False,
) -> Agent:
    """Calcula a rota OSM do agente no grafo correspondente ao modo."""

    agent.route_edges = []
    agent.travel_distance = None
    agent.travel_time = None
    agent.route_status = None

    if agent.mode is None:
        agent.route_status = ROUTE_MISSING_MODE
        return agent

    mode_name = _enum_value(agent.mode)

    if mode_name not in graphs:
        agent.route_status = ROUTE_UNSUPPORTED_MODE
        return agent

    if (
        agent.origin_node is None
        or agent.destination_node is None
    ):
        agent.route_status = ROUTE_MISSING_NODE
        return agent

    graph = graphs[mode_name]
    origin = int(agent.origin_node)
    destination = int(agent.destination_node)

    if origin not in graph or destination not in graph:
        agent.route_status = ROUTE_INVALID_NODE
        return agent

    if origin == destination:
        agent.travel_distance = 0.0
        agent.route_status = ROUTE_SAME_NODE
        return agent

    try:
        node_path = nx.shortest_path(
            graph,
            source=origin,
            target=destination,
            weight=weight,
            method="dijkstra",
        )

        route_edges, route_weight = node_path_to_edges(
            graph,
            list(node_path),
            weight=weight,
        )

        agent.route_edges = route_edges

        if weight == "length":
            agent.travel_distance = float(route_weight)

        agent.route_status = ROUTE_OK

    except nx.NetworkXNoPath:
        agent.route_status = ROUTE_NO_PATH

    except nx.NodeNotFound:
        agent.route_status = ROUTE_INVALID_NODE

    except Exception:
        agent.route_status = ROUTE_ERROR

        if strict:
            raise

    return agent


def route_agents(
    agents: list[Agent],
    graphs: Mapping[str, object],
    *,
    weight: str = "length",
    strict: bool = False,
) -> list[Agent]:
    """Calcula rotas para todos os agentes suportados pelas redes OSM."""

    for agent in agents:
        route_agent(
            agent,
            graphs,
            weight=weight,
            strict=strict,
        )

    return agents


def routing_summary(
    agents: list[Agent],
) -> pd.DataFrame:
    rows = []

    for agent in agents:
        rows.append(
            {
                "agent_id": agent.agent_id,
                "income_group": _enum_value(
                    agent.income_group
                ),
                "mode": (
                    _enum_value(agent.mode)
                    if agent.mode is not None
                    else None
                ),
                "origin_node": agent.origin_node,
                "destination_node": agent.destination_node,
                "route_status": agent.route_status,
                "n_route_edges": len(agent.route_edges),
                "travel_distance_m": agent.travel_distance,
            }
        )

    return pd.DataFrame(rows)
