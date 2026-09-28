import unittest

import networkx as nx

from src.domain.agent import Agent
from src.domain.enums import IncomeGroup, TravelMode
from src.routing.multimodal_router import (
    ROUTE_NO_PATH,
    ROUTE_OK,
    ROUTE_SAME_NODE,
    route_agent,
)


class MultimodalRouterTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.MultiDiGraph()

        # Duas arestas paralelas entre 1 e 2.
        # O roteador deve selecionar key=1, que é a mais curta.
        self.graph.add_edge(
            1,
            2,
            key=0,
            length=100.0,
        )
        self.graph.add_edge(
            1,
            2,
            key=1,
            length=50.0,
        )
        self.graph.add_edge(
            2,
            3,
            key=0,
            length=70.0,
        )

        self.graph.add_node(4)

        self.graphs = {
            "car": self.graph,
        }

    def _agent(
        self,
        origin: int,
        destination: int,
    ) -> Agent:
        agent = Agent(
            agent_id=1,
            income_group=IncomeGroup.LOW,
        )
        agent.mode = TravelMode.CAR
        agent.origin_node = origin
        agent.destination_node = destination
        return agent

    def test_shortest_route_preserves_edge_keys(self):
        agent = self._agent(
            1,
            3,
        )

        route_agent(
            agent,
            self.graphs,
        )

        self.assertEqual(
            agent.route_status,
            ROUTE_OK,
        )
        self.assertEqual(
            agent.route_edges,
            [
                (1, 2, 1),
                (2, 3, 0),
            ],
        )
        self.assertAlmostEqual(
            agent.travel_distance,
            120.0,
        )

    def test_same_origin_and_destination(self):
        agent = self._agent(
            1,
            1,
        )

        route_agent(
            agent,
            self.graphs,
        )

        self.assertEqual(
            agent.route_status,
            ROUTE_SAME_NODE,
        )
        self.assertEqual(
            agent.route_edges,
            [],
        )
        self.assertEqual(
            agent.travel_distance,
            0.0,
        )

    def test_no_path_is_recorded_without_stopping_simulation(self):
        agent = self._agent(
            1,
            4,
        )

        route_agent(
            agent,
            self.graphs,
        )

        self.assertEqual(
            agent.route_status,
            ROUTE_NO_PATH,
        )
        self.assertEqual(
            agent.route_edges,
            [],
        )
        self.assertIsNone(
            agent.travel_distance,
        )


if __name__ == "__main__":
    unittest.main()
