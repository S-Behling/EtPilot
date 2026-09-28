"""Roteamento das redes OSM usadas pelo piloto EtPilot

Este módulo calcula caminhos para carro, caminhada e bicicleta em seus
MultiDiGraph OSM correspondentes usando comprimento como peso por padrão
O transporte coletivo usa o roteador GTFS separado e é integrado ao piloto
por src.routing.pilot_router

A rota OSM de cada agente é armazenada como sequência de arestas
(u, v, key) preservando a estrutura MultiDiGraph do OSMnx
"""

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
    """Retorna o valor textual de um Enum ou a própria representação."""

    return value.value if hasattr(value, "value") else str(value)


def _edge_numeric_value(
    attributes: Mapping,
    attribute: str,
) -> float:
    """Obtém um atributo numérico de uma aresta."""

    value = attributes.get(attribute)

    if value is None:
        raise ValueError(
            f"Aresta sem atributo obrigatório '{attribute}'."
        )

    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Valor inválido para '{attribute}': {value!r}"
        ) from exc

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
    """
    Seleciona a aresta paralela de menor peso entre dois nós consecutivos.

    `networkx.shortest_path` retorna uma sequência de nós. Em um
    MultiDiGraph podem existir várias arestas entre `u` e `v`; esta função
    recupera a `key` que corresponde ao menor peso usado pelo roteamento.
    """

    edge_bundle = graph.get_edge_data(u, v)

    if not edge_bundle:
        raise ValueError(
            f"A rota contém o par ({u}, {v}), "
            "mas nenhuma aresta foi encontrada no grafo."
        )

    candidates: list[tuple[float, int, Mapping]] = []

    for key, attributes in edge_bundle.items():
        try:
            edge_weight = _edge_numeric_value(
                attributes,
                weight,
            )
        except ValueError:
            continue

        candidates.append(
            (
                edge_weight,
                key,
                attributes,
            )
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

    return key, attributes


def node_path_to_edges(
    graph,
    node_path: list[int],
    *,
    weight: str = "length",
) -> tuple[list[tuple[int, int, int]], float]:
    """
    Converte uma rota em nós para arestas exatas de um MultiDiGraph.

    Returns
    -------
    tuple
        `(route_edges, route_weight)`, onde `route_edges` é uma lista de
        `(u, v, key)` e `route_weight` é a soma do atributo `weight`.
    """

    if len(node_path) < 2:
        return [], 0.0

    route_edges: list[tuple[int, int, int]] = []
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
            (
                int(u),
                int(v),
                int(key),
            )
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
    """
    Calcula a rota de um agente na rede correspondente ao modo escolhido.

    Em modo não estrito, problemas de conectividade são registrados em
    `agent.route_status` e a simulação continua. Em modo estrito, erros
    inesperados de roteamento são propagados.
    """

    agent.route_edges = []
    agent.travel_distance = None
    agent.travel_time = None
    agent.route_status = None

    if agent.mode is None:
        agent.route_status = ROUTE_MISSING_MODE
        return agent

    mode_name = _enum_value(
        agent.mode
    )

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

    origin = int(
        agent.origin_node
    )
    destination = int(
        agent.destination_node
    )

    if (
        origin not in graph
        or destination not in graph
    ):
        agent.route_status = ROUTE_INVALID_NODE
        return agent

    if origin == destination:
        agent.route_edges = []
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

        route_edges, route_weight = (
            node_path_to_edges(
                graph,
                list(node_path),
                weight=weight,
            )
        )

        agent.route_edges = route_edges

        # Nesta fase, `length` é a impedância e corresponde à distância.
        # Se outro peso for usado futuramente, travel_distance deverá ser
        # calculada separadamente a partir do atributo length.
        if weight == "length":
            agent.travel_distance = (
                float(route_weight)
            )

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
    """Calcula as rotas de todos os agentes."""

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
    """Retorna uma tabela de diagnóstico do roteamento."""

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
                "destination_node": (
                    agent.destination_node
                ),
                "route_status": (
                    agent.route_status
                ),
                "n_route_edges": len(
                    agent.route_edges
                ),
                "travel_distance_m": (
                    agent.travel_distance
                ),
            }
        )

    return pd.DataFrame(rows)
