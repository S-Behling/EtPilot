import unittest

import geopandas as gpd
import networkx as nx
import pandas as pd
from shapely.geometry import Point

from src.transit.buildTransitNetwork import (
    _build_routing_quality_filter,
    _build_scheduled_connections,
    _build_service_day_profile,
    _connect_stops_to_walk_network,
)


class BuildTransitNetworkTests(unittest.TestCase):
    def test_connects_stops_to_nearest_walk_nodes(self):
        # Cria uma rede projetada mínima para validar os conectores
        graph = nx.MultiDiGraph()
        graph.graph[
            "crs"
        ] = "EPSG:31982"
        graph.add_node(
            1,
            x=0.0,
            y=0.0,
        )
        graph.add_node(
            2,
            x=100.0,
            y=0.0,
        )

        stops = gpd.GeoDataFrame(
            {
                "stop_id": [
                    "S1",
                    "S2",
                ],
            },
            geometry=[
                Point(
                    3.0,
                    4.0,
                ),
                Point(
                    96.0,
                    0.0,
                ),
            ],
            crs="EPSG:31982",
        )

        connected, connectors = (
            _connect_stops_to_walk_network(
                stops,
                graph,
                walk_speed_m_s=1.0,
            )
        )

        self.assertEqual(
            connected.loc[
                0,
                "node_walk",
            ],
            1,
        )
        self.assertEqual(
            connected.loc[
                1,
                "node_walk",
            ],
            2,
        )
        self.assertAlmostEqual(
            connectors.loc[
                0,
                "walk_connector_distance_m",
            ],
            5.0,
        )
        self.assertAlmostEqual(
            connectors.loc[
                1,
                "walk_connector_time_s",
            ],
            4.0,
        )

    def test_builds_connections_between_consecutive_stops(self):
        # Cria duas conexões temporais a partir de uma viagem com três paradas
        trips = pd.DataFrame(
            {
                "trip_id": [
                    "T1",
                ],
                "route_id": [
                    "R1",
                ],
                "service_id": [
                    "WK",
                ],
                "shape_id": [
                    "SH1",
                ],
            }
        )

        stop_times = pd.DataFrame(
            {
                "trip_id": [
                    "T1",
                    "T1",
                    "T1",
                ],
                "stop_id": [
                    "S1",
                    "S2",
                    "S3",
                ],
                "stop_sequence": pd.Series(
                    [
                        1,
                        2,
                        3,
                    ],
                    dtype="Int64",
                ),
                "arrival_seconds": pd.Series(
                    [
                        0,
                        100,
                        220,
                    ],
                    dtype="Int64",
                ),
                "departure_seconds": pd.Series(
                    [
                        0,
                        100,
                        220,
                    ],
                    dtype="Int64",
                ),
                "time_interpolated": [
                    False,
                    True,
                    False,
                ],
                "time_interpolation_method": [
                    "provided",
                    "shape_geometry",
                    "provided",
                ],
                "shape_position_m": pd.Series(
                    [
                        0.0,
                        500.0,
                        1100.0,
                    ],
                    dtype="Float64",
                ),
            }
        )

        connections = _build_scheduled_connections(
            trips=trips,
            stop_times=stop_times,
        )

        self.assertEqual(
            len(
                connections
            ),
            2,
        )
        self.assertEqual(
            connections.loc[
                0,
                "from_stop_id",
            ],
            "S1",
        )
        self.assertEqual(
            connections.loc[
                0,
                "to_stop_id",
            ],
            "S2",
        )
        self.assertEqual(
            connections.loc[
                0,
                "in_vehicle_time_s",
            ],
            100,
        )
        self.assertTrue(
            connections.loc[
                0,
                "uses_interpolated_time",
            ]
        )
        self.assertAlmostEqual(
            connections.loc[
                1,
                "shape_segment_distance_m",
            ],
            600.0,
        )

    def test_builds_daily_service_profile(self):
        # Soma as viagens dos service_ids ativos em cada data
        trips = pd.DataFrame(
            {
                "trip_id": [
                    "T1",
                    "T2",
                    "T3",
                ],
                "service_id": [
                    "WK",
                    "WK",
                    "WE",
                ],
            }
        )
        service_dates = pd.DataFrame(
            {
                "service_id": [
                    "WK",
                    "WK",
                    "WE",
                ],
                "service_date": pd.to_datetime(
                    [
                        "2025-09-15",
                        "2025-09-16",
                        "2025-09-14",
                    ]
                ),
            }
        )

        profile = _build_service_day_profile(
            trips=trips,
            service_dates=service_dates,
        )

        self.assertEqual(
            profile.iloc[
                0
            ][
                "n_scheduled_trips"
            ],
            2,
        )
        self.assertEqual(
            profile.iloc[
                0
            ][
                "weekday"
            ],
            "segunda-feira",
        )

    def test_filters_temporally_invalid_trips_for_routing(self):
        # Mantém a tabela completa e marca somente as viagens aptas ao roteamento
        quality = pd.DataFrame(
            {
                "trip_id": [
                    "OK",
                    "ZERO",
                    "FAST",
                    "MISSING",
                    "INFEASIBLE",
                ],
                "missing_stop_time_summary": [
                    False,
                    False,
                    False,
                    True,
                    False,
                ],
                "missing_connection_summary": [
                    False,
                    False,
                    False,
                    True,
                    False,
                ],
                "nonpositive_scheduled_duration": [
                    False,
                    True,
                    False,
                    False,
                    False,
                ],
                "infeasible_temporal_regularization": [
                    False,
                    True,
                    False,
                    True,
                    True,
                ],
                "implied_shape_speed_kmh": [
                    22.0,
                    pd.NA,
                    120.0,
                    pd.NA,
                    20.0,
                ],
            }
        )

        filtered = _build_routing_quality_filter(
            quality,
            quality_config={
                "exclude_missing_temporal_summary": True,
                "exclude_nonpositive_duration": True,
                "exclude_infeasible_regularization": True,
                "max_implied_shape_speed_kmh": 80,
            },
        )

        routable = set(
            filtered.loc[
                filtered[
                    "routable_for_transit"
                ],
                "trip_id",
            ]
        )

        self.assertEqual(
            routable,
            {
                "OK",
            },
        )

        fast = filtered.loc[
            filtered[
                "trip_id"
            ]
            == "FAST"
        ].iloc[
            0
        ]

        self.assertTrue(
            fast[
                "routing_excluded_implied_speed"
            ]
        )
        self.assertEqual(
            fast[
                "routing_quality_status"
            ],
            "implied_speed_above_limit",
        )


if __name__ == "__main__":
    unittest.main()
