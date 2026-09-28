import unittest

import networkx as nx
import pandas as pd

from src.transit.routeTransit import (
    ROUTE_NO_ACTIVE_SERVICE,
    ROUTE_NO_TRANSIT_PATH,
    ROUTE_OK,
    TransitRouter,
)


class TransitRouterTests(unittest.TestCase):
    def _walk_graph(self):
        # Cria uma rede simples de caminhada com distâncias métricas
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
                100.0,
            ),
            (
                3,
                200.0,
            ),
            (
                4,
                300.0,
            ),
        ]:
            graph.add_node(
                node,
                x=x,
                y=0.0,
            )

        for u, v in [
            (
                1,
                2,
            ),
            (
                2,
                1,
            ),
            (
                2,
                3,
            ),
            (
                3,
                2,
            ),
            (
                3,
                4,
            ),
            (
                4,
                3,
            ),
        ]:
            graph.add_edge(
                u,
                v,
                key=0,
                length=100.0,
            )

        return graph

    def _connectors(self):
        return pd.DataFrame(
            {
                "stop_id": [
                    "A",
                    "B",
                    "C",
                ],
                "node_walk": pd.Series(
                    [
                        2,
                        3,
                        4,
                    ],
                    dtype="Int64",
                ),
                "walk_connector_distance_m": [
                    0.0,
                    0.0,
                    0.0,
                ],
                "walk_connector_time_s": [
                    0.0,
                    0.0,
                    0.0,
                ],
            }
        )

    def _service_dates(self):
        return pd.DataFrame(
            {
                "service_id": [
                    "WK",
                ],
                "service_date": pd.to_datetime(
                    [
                        "2025-09-15",
                    ]
                ),
            }
        )

    def _direct_connections(self):
        return pd.DataFrame(
            {
                "connection_id": [
                    "C1",
                    "C2",
                ],
                "route_id": [
                    "R1",
                    "R1",
                ],
                "service_id": [
                    "WK",
                    "WK",
                ],
                "trip_id": [
                    "T1",
                    "T1",
                ],
                "from_stop_id": [
                    "A",
                    "B",
                ],
                "to_stop_id": [
                    "B",
                    "C",
                ],
                "departure_seconds": pd.Series(
                    [
                        8 * 3600 + 5 * 60,
                        8 * 3600 + 12 * 60,
                    ],
                    dtype="Int64",
                ),
                "arrival_seconds": pd.Series(
                    [
                        8 * 3600 + 10 * 60,
                        8 * 3600 + 20 * 60,
                    ],
                    dtype="Int64",
                ),
                "in_vehicle_time_s": pd.Series(
                    [
                        5 * 60,
                        8 * 60,
                    ],
                    dtype="Int64",
                ),
            }
        )

    def _router(
        self,
        connections,
        *,
        minimum_transfer_time_s=60,
    ):
        return TransitRouter(
            walk_graph=self._walk_graph(),
            connectors=self._connectors(),
            connections=connections,
            service_dates=self._service_dates(),
            walk_speed_m_s=1.0,
            max_access_walk_m=150.0,
            max_egress_walk_m=50.0,
            minimum_transfer_time_s=minimum_transfer_time_s,
            max_total_travel_time_s=7200,
        )

    def test_routes_direct_trip_with_walk_access(self):
        # Calcula uma viagem direta e preserva os trechos de caminhada
        router = self._router(
            self._direct_connections()
        )

        result = router.route(
            origin_walk_node=1,
            destination_walk_node=4,
            service_date="2025-09-15",
            departure_time_s=8 * 3600,
        )

        self.assertEqual(
            result.status,
            ROUTE_OK,
        )
        self.assertEqual(
            result.access_stop_id,
            "A",
        )
        self.assertEqual(
            result.egress_stop_id,
            "C",
        )
        self.assertEqual(
            result.n_boardings,
            1,
        )
        self.assertEqual(
            result.n_transfers,
            0,
        )
        self.assertEqual(
            result.transit_connection_ids,
            [
                "C1",
                "C2",
            ],
        )
        self.assertAlmostEqual(
            result.access_walk_distance_m,
            100.0,
        )
        self.assertAlmostEqual(
            result.egress_walk_distance_m,
            0.0,
        )
        self.assertEqual(
            len(
                result.access_walk_edges
            ),
            1,
        )

    def test_applies_transfer_buffer_between_trips(self):
        # Permite a transferência somente quando o intervalo atende ao buffer
        connections = pd.DataFrame(
            {
                "connection_id": [
                    "C1",
                    "C2",
                ],
                "route_id": [
                    "R1",
                    "R2",
                ],
                "service_id": [
                    "WK",
                    "WK",
                ],
                "trip_id": [
                    "T1",
                    "T2",
                ],
                "from_stop_id": [
                    "A",
                    "B",
                ],
                "to_stop_id": [
                    "B",
                    "C",
                ],
                "departure_seconds": pd.Series(
                    [
                        8 * 3600 + 5 * 60,
                        8 * 3600 + 12 * 60,
                    ],
                    dtype="Int64",
                ),
                "arrival_seconds": pd.Series(
                    [
                        8 * 3600 + 10 * 60,
                        8 * 3600 + 20 * 60,
                    ],
                    dtype="Int64",
                ),
                "in_vehicle_time_s": pd.Series(
                    [
                        5 * 60,
                        8 * 60,
                    ],
                    dtype="Int64",
                ),
            }
        )

        router = self._router(
            connections,
            minimum_transfer_time_s=60,
        )

        result = router.route(
            origin_walk_node=1,
            destination_walk_node=4,
            service_date="2025-09-15",
            departure_time_s=8 * 3600,
        )

        self.assertEqual(
            result.status,
            ROUTE_OK,
        )
        self.assertEqual(
            result.n_boardings,
            2,
        )
        self.assertEqual(
            result.n_transfers,
            1,
        )

    def test_rejects_transfer_below_buffer(self):
        # Rejeita uma conexão que parte antes do tempo mínimo de transferência
        connections = pd.DataFrame(
            {
                "connection_id": [
                    "C1",
                    "C2",
                ],
                "route_id": [
                    "R1",
                    "R2",
                ],
                "service_id": [
                    "WK",
                    "WK",
                ],
                "trip_id": [
                    "T1",
                    "T2",
                ],
                "from_stop_id": [
                    "A",
                    "B",
                ],
                "to_stop_id": [
                    "B",
                    "C",
                ],
                "departure_seconds": pd.Series(
                    [
                        8 * 3600 + 5 * 60,
                        8 * 3600 + 10 * 60 + 30,
                    ],
                    dtype="Int64",
                ),
                "arrival_seconds": pd.Series(
                    [
                        8 * 3600 + 10 * 60,
                        8 * 3600 + 20 * 60,
                    ],
                    dtype="Int64",
                ),
                "in_vehicle_time_s": pd.Series(
                    [
                        5 * 60,
                        9 * 60 + 30,
                    ],
                    dtype="Int64",
                ),
            }
        )

        router = self._router(
            connections,
            minimum_transfer_time_s=60,
        )

        result = router.route(
            origin_walk_node=1,
            destination_walk_node=4,
            service_date="2025-09-15",
            departure_time_s=8 * 3600,
        )

        self.assertEqual(
            result.status,
            ROUTE_NO_TRANSIT_PATH,
        )

    def test_reports_date_without_active_service(self):
        # Identifica quando a data consultada não possui service_id ativo
        router = self._router(
            self._direct_connections()
        )

        result = router.route(
            origin_walk_node=1,
            destination_walk_node=4,
            service_date="2025-09-16",
            departure_time_s=8 * 3600,
        )

        self.assertEqual(
            result.status,
            ROUTE_NO_ACTIVE_SERVICE,
        )


if __name__ == "__main__":
    unittest.main()
