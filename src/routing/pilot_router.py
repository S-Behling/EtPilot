"""Integra o roteamento viário e o roteamento temporal do piloto

Mantém carro, bicicleta e caminhada nas redes OSM correspondentes
Usa node_walk como acesso espacial ao roteador GTFS quando o modo é transit
Persiste no agente os componentes temporais e espaciais necessários à análise
"""

from __future__ import annotations

from src.domain.enums import TravelMode
from src.routing.multimodal_router import route_agent
from src.transit.routeTransit import (
    ROUTE_OK as TRANSIT_ROUTE_OK,
    TransitRouter,
)


def _reset_transit_results(
    agent,
) -> None:
    """Limpa resultados específicos de transporte coletivo antes do roteamento"""

    agent.transit_service_date = None
    agent.transit_departure_time_s = None
    agent.transit_arrival_time_s = None
    agent.transit_access_stop_id = None
    agent.transit_egress_stop_id = None
    agent.transit_access_walk_distance_m = None
    agent.transit_access_walk_time_s = None
    agent.transit_initial_wait_time_s = None
    agent.transit_in_vehicle_distance_m = None
    agent.transit_in_vehicle_time_s = None
    agent.transit_transfer_and_dwell_time_s = None
    agent.transit_n_boardings = 0
    agent.transit_n_transfers = 0
    agent.transit_egress_walk_distance_m = None
    agent.transit_egress_walk_time_s = None
    agent.transit_access_walk_edges = []
    agent.transit_egress_walk_edges = []
    agent.transit_connection_ids = []
    agent.transit_trip_ids = []
    agent.transit_route_ids = []


def _apply_transit_result(
    agent,
    result,
) -> None:
    """Transfere o resultado temporal do roteador GTFS para o agente"""

    agent.route_edges = []
    agent.route_status = result.status

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
    agent.transit_n_boardings = int(
        result.n_boardings
    )
    agent.transit_n_transfers = int(
        result.n_transfers
    )
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

    if result.status != TRANSIT_ROUTE_OK:
        agent.travel_distance = None
        agent.travel_time = None
        return

    access_distance = float(
        result.access_walk_distance_m
        or 0.0
    )
    in_vehicle_distance = float(
        result.in_vehicle_distance_m
        or 0.0
    )
    egress_distance = float(
        result.egress_walk_distance_m
        or 0.0
    )

    agent.travel_distance = (
        access_distance
        + in_vehicle_distance
        + egress_distance
    )
    agent.travel_time = (
        float(
            result.total_travel_time_s
        )
        if result.total_travel_time_s is not None
        else None
    )


def route_pilot_agents(
    agents,
    *,
    graphs,
    transit_router: TransitRouter,
    transit_service_date: str,
    transit_departure_time_s: int,
    road_weight: str = "length",
    strict: bool = False,
):
    """Roteia todos os agentes usando a arquitetura correspondente ao modo"""

    for agent in agents:
        _reset_transit_results(
            agent
        )

        if agent.mode is TravelMode.TRANSIT:
            if (
                agent.origin_node is None
                or agent.destination_node is None
            ):
                agent.route_edges = []
                agent.route_status = "missing_node"
                agent.travel_distance = None
                agent.travel_time = None
                continue

            result = transit_router.route(
                origin_walk_node=int(
                    agent.origin_node
                ),
                destination_walk_node=int(
                    agent.destination_node
                ),
                service_date=transit_service_date,
                departure_time_s=int(
                    transit_departure_time_s
                ),
            )

            _apply_transit_result(
                agent,
                result,
            )
            continue

        route_agent(
            agent,
            graphs,
            weight=road_weight,
            strict=strict,
        )

    return agents
