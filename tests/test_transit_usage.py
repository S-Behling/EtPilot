import unittest

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import LineString

from src.domain.agent import Agent
from src.domain.enums import (
    IncomeGroup,
    TravelMode,
    TripPurpose,
)
from src.network.analysis_segments import (
    apply_analysis_segment_mapping,
)
from src.trajectory.transit_usage import (
    build_transit_edge_usage,
    build_used_transit_connection_geometries,
    map_transit_connections_to_analysis_segments,
)


class TransitUsageTests(unittest.TestCase):
    def _agent(self):
        # Cria um agente de transporte coletivo com acesso e egresso a pé
        agent = Agent(
            agent_id=1,
            income_group=IncomeGroup.LOW,
        )
        agent.origin_id = "O1"
        agent.destination_id = "D1"
        agent.purpose = TripPurpose.WORK
        agent.mode = TravelMode.TRANSIT
        agent.route_status = "ok"
        agent.transit_access_walk_edges = [
            (
                1,
                2,
                0,
            ),
        ]
        agent.transit_connection_ids = [
            "C1",
        ]
        agent.transit_egress_walk_edges = [
            (
                3,
                4,
                0,
            ),
        ]

        return agent

    def _walk_graph(self):
        # Cria arestas simples da rede de caminhada
        graph = nx.MultiDiGraph()
        graph.graph[
            "crs"
        ] = "EPSG:31982"

        for node, x in [
            (
                1,
                0.0,
            ),
            (
                2,
                10.0,
            ),
            (
                3,
                90.0,
            ),
            (
                4,
                100.0,
            ),
        ]:
            graph.add_node(
                node,
                x=x,
                y=0.0,
            )

        graph.add_edge(
            1,
            2,
            key=0,
            length=10.0,
            osmid=1,
            name="Rua A",
            highway="residential",
        )
        graph.add_edge(
            3,
            4,
            key=0,
            length=10.0,
            osmid=2,
            name="Rua B",
            highway="residential",
        )

        return graph

    def _connections(self):
        return pd.DataFrame(
            {
                "connection_id": [
                    "C1",
                ],
                "route_id": [
                    "R1",
                ],
                "service_id": [
                    "WK",
                ],
                "trip_id": [
                    "T1",
                ],
                "shape_id": [
                    "SH1",
                ],
                "from_stop_id": [
                    "S1",
                ],
                "to_stop_id": [
                    "S2",
                ],
                "from_shape_position_m": [
                    0.0,
                ],
                "to_shape_position_m": [
                    100.0,
                ],
                "shape_segment_distance_m": [
                    100.0,
                ],
            }
        )

    def test_transit_agent_uses_walk_nodes_for_routing(self):
        # Resolve o nó efetivo de transit pela rede walk
        agent = self._agent()
        agent.origin_nodes = {
            "walk": 10,
            "car": 20,
        }
        agent.destination_nodes = {
            "walk": 11,
            "car": 21,
        }

        agent.resolve_routing_nodes()

        self.assertEqual(
            agent.origin_node,
            10,
        )
        self.assertEqual(
            agent.destination_node,
            11,
        )

    def test_builds_walk_and_transit_usage_rows(self):
        # Mantém transit como modo principal e walk como modo de mapeamento
        usage = build_transit_edge_usage(
            [
                self._agent(),
            ],
            walk_graph=self._walk_graph(),
            connections=self._connections(),
            scenario_name="baseline",
        )

        self.assertEqual(
            len(
                usage
            ),
            3,
        )
        self.assertTrue(
            (
                usage[
                    "mode"
                ]
                == "transit"
            ).all()
        )
        self.assertEqual(
            usage.loc[
                usage[
                    "transit_leg"
                ]
                == "access_walk",
                "mapping_mode",
            ].iloc[
                0
            ],
            "walk",
        )
        self.assertEqual(
            usage.loc[
                usage[
                    "transit_leg"
                ]
                == "in_vehicle",
                "mapping_mode",
            ].iloc[
                0
            ],
            "transit",
        )

    def test_maps_used_shape_substring_to_analysis_segments(self):
        # Mapeia a conexão GTFS para dois segmentos físicos consecutivos
        usage = build_transit_edge_usage(
            [
                self._agent(),
            ],
            walk_graph=self._walk_graph(),
            connections=self._connections(),
            scenario_name="baseline",
        )

        shapes = gpd.GeoDataFrame(
            {
                "shape_id": [
                    "SH1",
                ],
            },
            geometry=[
                LineString(
                    [
                        (
                            0.0,
                            0.0,
                        ),
                        (
                            100.0,
                            0.0,
                        ),
                    ]
                ),
            ],
            crs="EPSG:31982",
        )

        geometries, diagnostics = (
            build_used_transit_connection_geometries(
                usage,
                connections=self._connections(),
                shapes=shapes,
            )
        )

        segments = gpd.GeoDataFrame(
            {
                "analysis_segment_id": [
                    "S1",
                    "S2",
                ],
            },
            geometry=[
                LineString(
                    [
                        (
                            0.0,
                            0.0,
                        ),
                        (
                            50.0,
                            0.0,
                        ),
                    ]
                ),
                LineString(
                    [
                        (
                            50.0,
                            0.0,
                        ),
                        (
                            100.0,
                            0.0,
                        ),
                    ]
                ),
            ],
            crs="EPSG:31982",
        )

        mapping, match_diagnostics = (
            map_transit_connections_to_analysis_segments(
                geometries,
                analysis_segments=segments,
                tolerance_m=2.0,
                min_segment_coverage=0.9,
                max_angle_difference_deg=10.0,
            )
        )

        self.assertEqual(
            diagnostics.iloc[
                0
            ][
                "geometry_status"
            ],
            "ok",
        )
        self.assertEqual(
            set(
                mapping[
                    "analysis_segment_id"
                ]
            ),
            {
                "S1",
                "S2",
            },
        )
        self.assertEqual(
            match_diagnostics.iloc[
                0
            ][
                "matched_segments"
            ],
            2,
        )

    def test_applies_mapping_mode_without_overwriting_trip_mode(self):
        # Usa walk para harmonização mas preserva transit como modo da viagem
        usage = build_transit_edge_usage(
            [
                self._agent(),
            ],
            walk_graph=self._walk_graph(),
            connections=self._connections(),
            scenario_name="baseline",
        )

        access = usage.loc[
            usage[
                "transit_leg"
            ]
            == "access_walk"
        ].copy()

        mapping = pd.DataFrame(
            {
                "modal_edge_id": [
                    access.iloc[
                        0
                    ][
                        "modal_edge_id"
                    ],
                ],
                "mode": [
                    "walk",
                ],
                "analysis_segment_id": [
                    "S1",
                ],
                "match_method": [
                    "reference",
                ],
                "match_quality": [
                    1.0,
                ],
            }
        )

        harmonized = apply_analysis_segment_mapping(
            access,
            mapping,
        )

        self.assertEqual(
            harmonized.iloc[
                0
            ][
                "mode"
            ],
            "transit",
        )
        self.assertEqual(
            harmonized.iloc[
                0
            ][
                "mapping_mode"
            ],
            "walk",
        )
        self.assertEqual(
            harmonized.iloc[
                0
            ][
                "analysis_segment_id"
            ],
            "S1",
        )


if __name__ == "__main__":
    unittest.main()
