"""Orquestra o roteamento multimodal do piloto.

Mantém a simulação desacoplada dos detalhes de roteamento: redes OSM são
usadas para walk/bike/car e o roteador temporal GTFS é usado para transit.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.agent import Agent
from src.domain.enums import TravelMode
from src.routing.multimodal_router import route_agent
from src.transit.router import TransitRouter


def route_pilot_agents(
    agents: list[Agent],
    *,
    graphs: Mapping[str, object],
    transit_router: TransitRouter,
    transit_service_date,
    transit_departure_time_s: int,
    weight: str = "length",
    strict: bool = False,
) -> list[Agent]:
    """Roteia todos os agentes conforme o modo escolhido."""

    for agent in agents:
        if agent.mode is TravelMode.TRANSIT:
            _route_transit_agent(
                agent=agent,
                router=transit_router,
                service_date=transit_service_date,
                departure_time_s=transit_departure_time_s,
            )
        else:
            route_agent(
                agent,
                graphs,
                weight=weight,
                strict=strict,
            )

    return agents


def _route_transit_agent(
    *,
    agent: Agent,
    router: TransitRouter,
    service_date,
    departure_time_s: int,
) -> None:
    """Executa uma viagem transit e transfere o resultado para o agente."""

    origin_walk_node = agent.origin_nodes.get(
        TravelMode.WALK.value
    )
    destination_walk_node = agent.destination_nodes.get(
        TravelMode.WALK.value
    )

    if (
        origin_walk_node is None
        or destination_walk_node is None
    ):
        agent.route_status = "missing_node"
        return

    result = router.route(
        origin_walk_node=int(origin_walk_node),
        destination_walk_node=int(destination_walk_node),
        service_date=service_date,
        departure_time_s=int(departure_time_s),
    )

    agent.route_status = result.status
    agent.travel_time = result.total_travel_time_s

    distance_parts = [
        result.access_walk_distance_m,
        result.in_vehicle_distance_m,
        result.egress_walk_distance_m,
    ]
    finite_parts = [
        float(value)
        for value in distance_parts
        if value is not None
    ]
    agent.travel_distance = (
        sum(finite_parts)
        if finite_parts
        else None
    )

    agent.transit_service_date = result.service_date
    agent.transit_departure_time_s = result.departure_time_s
    agent.transit_arrival_time_s = result.arrival_time_s
    agent.transit_access_stop_id = result.access_stop_id
    agent.transit_egress_stop_id = result.egress_stop_id
    agent.transit_access_walk_distance_m = (
        result.access_walk_distance_m
    )
    agent.transit_access_walk_time_s = (
        result.access_walk_time_s
    )
    agent.transit_initial_wait_time_s = (
        result.initial_wait_time_s
    )
    agent.transit_in_vehicle_distance_m = (
        result.in_vehicle_distance_m
    )
    agent.transit_in_vehicle_time_s = (
        result.in_vehicle_time_s
    )
    agent.transit_transfer_and_dwell_time_s = (
        result.transfer_and_dwell_time_s
    )
    agent.transit_n_boardings = result.n_boardings
    agent.transit_n_transfers = result.n_transfers
    agent.transit_egress_walk_distance_m = (
        result.egress_walk_distance_m
    )
    agent.transit_egress_walk_time_s = (
        result.egress_walk_time_s
    )
    agent.transit_access_walk_edges = list(
        result.access_walk_edges
    )
    agent.transit_egress_walk_edges = list(
        result.egress_walk_edges
    )
    agent.transit_connection_ids = list(
        result.transit_connection_ids
    )
    agent.transit_trip_ids = list(
        result.transit_trip_ids
    )
    agent.transit_route_ids = list(
        result.transit_route_ids
    )
