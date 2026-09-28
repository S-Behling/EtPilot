import unittest

import networkx as nx

from src.domain.agent import Agent
from src.domain.enums import (
    IncomeGroup,
    TravelMode,
    TripPurpose,
)
from src.routing.multimodal_router import ROUTE_OK
from src.trajectory.edge_usage import build_edge_usage


class EdgeUsageTests(unittest.TestCase):
    def test_build_edge_usage(self):
        graph = nx.MultiDiGraph()
        graph.add_edge(
            1,
            2,
            key=0,
            length=50.0,
            osmid=123,
            name="Rua A",
            highway="residential",
        )
        graph.add_edge(
            2,
            3,
            key=1,
            length=75.0,
            osmid=456,
            name="Rua B",
            highway="secondary",
        )

        agent = Agent(
            agent_id=7,
            income_group=IncomeGroup.LOW,
        )
        agent.purpose = TripPurpose.WORK
        agent.mode = TravelMode.CAR
        agent.origin_id = "O_1"
        agent.destination_id = "D_1"
        agent.route_status = ROUTE_OK
        agent.route_edges = [
            (1, 2, 0),
            (2, 3, 1),
        ]

        result = build_edge_usage(
            agents=[agent],
            graphs={"car": graph},
            scenario_name="baseline",
        )

        self.assertEqual(
            len(result),
            2,
        )
        self.assertEqual(
            result["modal_edge_id"].tolist(),
            [
                "car:1:2:0",
                "car:2:3:1",
            ],
        )
        self.assertEqual(
            result["route_position"].tolist(),
            [0, 1],
        )
        self.assertEqual(
            result["edge_length_m"].tolist(),
            [50.0, 75.0],
        )
        self.assertTrue(
            (result["income_group"] == "low").all()
        )
        self.assertTrue(
            (result["purpose"] == "work").all()
        )


if __name__ == "__main__":
    unittest.main()
