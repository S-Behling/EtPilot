import unittest

import networkx as nx

from src.domain.agent import Agent
from src.domain.enums import (
    IncomeGroup,
    TravelMode,
)
from src.routing.pilot_router import route_pilot_agents
from src.transit.routeTransit import TransitRouteResult


class _FakeTransitRouter:
    def route(
        self,
        *,
        origin_walk_node,
        destination_walk_node,
        service_date,
        departure_time_s,
    ):
        # Retorna uma rota temporal sintética para validar a integração
        return TransitRouteResult(
            status="ok",
            service_date=str(
                service_date
            ),
            departure_time_s=int(
                departure_time_s
            ),
            arrival_time_s=departure_time_s + 900,
            total_travel_time_s=900.0,
            access_stop_id="S1",
            egress_stop_id="S2",
            access_walk_distance_m=100.0,
            access_walk_time_s=80.0,
            initial_wait_time_s=120.0,
            in_vehicle_distance_m=2000.0,
            in_vehicle_time_s=600.0,
            transfer_and_dwell_time_s=0.0,
            n_boardings=1,
            n_transfers=0,
            egress_walk_distance_m=150.0,
            egress_walk_time_s=100.0,
            access_walk_edges=[
                (
                    1,
                    2,
                    0,
                ),
            ],
            egress_walk_edges=[
                (
                    3,
                    4,
                    0,
                ),
            ],
            transit_connection_ids=[
                "C1",
            ],
            transit_trip_ids=[
                "T1",
            ],
            transit_route_ids=[
                "R1",
            ],
        )


class PilotRouterTests(unittest.TestCase):
    def test_routes_transit_agent_and_persists_components(self):
        # Persiste distância, tempo e identificadores da rota GTFS no agente
        agent = Agent(
            agent_id=1,
            income_group=IncomeGroup.LOW,
        )
        agent.mode = TravelMode.TRANSIT
        agent.origin_node = 1
        agent.destination_node = 4

        routed = route_pilot_agents(
            [
                agent,
            ],
            graphs={},
            transit_router=_FakeTransitRouter(),
            transit_service_date="2025-09-12",
            transit_departure_time_s=8 * 3600,
        )[
            0
        ]

        self.assertEqual(
            routed.route_status,
            "ok",
        )
        self.assertAlmostEqual(
            routed.travel_time,
            900.0,
        )
        self.assertAlmostEqual(
            routed.travel_distance,
            2250.0,
        )
        self.assertEqual(
            routed.transit_connection_ids,
            [
                "C1",
            ],
        )
        self.assertEqual(
            routed.transit_n_transfers,
            0,
        )

    def test_routes_road_agent_with_existing_router(self):
        # Mantém o comportamento do roteamento viário para modos OSM
        graph = nx.MultiDiGraph()
        graph.add_node(
            1
        )
        graph.add_node(
            2
        )
        graph.add_edge(
            1,
            2,
            key=0,
            length=50.0,
        )

        agent = Agent(
            agent_id=2,
            income_group=IncomeGroup.MIDDLE,
        )
        agent.mode = TravelMode.WALK
        agent.origin_node = 1
        agent.destination_node = 2

        routed = route_pilot_agents(
            [
                agent,
            ],
            graphs={
                "walk": graph,
            },
            transit_router=_FakeTransitRouter(),
            transit_service_date="2025-09-12",
            transit_departure_time_s=8 * 3600,
        )[
            0
        ]

        self.assertEqual(
            routed.route_status,
            "ok",
        )
        self.assertEqual(
            routed.route_edges,
            [
                (
                    1,
                    2,
                    0,
                ),
            ],
        )
        self.assertAlmostEqual(
            routed.travel_distance,
            50.0,
        )


if __name__ == "__main__":
    unittest.main()
