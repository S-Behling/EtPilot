import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point

from src.transit.physicalNetwork import (
    build_transit_physical_network,
    integrate_transit_physical_network,
)


class TransitPhysicalNetworkTests(unittest.TestCase):
    def _shapes(self):
        # Cria um shape simples em CRS métrico
        return gpd.GeoDataFrame(
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

    def _stops(self):
        # Cria duas paradas alinhadas ao shape
        return gpd.GeoDataFrame(
            {
                "stop_id": [
                    "S1",
                    "S2",
                ],
            },
            geometry=[
                Point(
                    0.0,
                    0.0,
                ),
                Point(
                    100.0,
                    0.0,
                ),
            ],
            crs="EPSG:31982",
        )

    def _connections(self):
        # Cria duas viagens que compartilham o mesmo trecho físico
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
                    "T2",
                ],
                "shape_id": [
                    "SH1",
                    "SH1",
                ],
                "from_stop_id": [
                    "S1",
                    "S1",
                ],
                "to_stop_id": [
                    "S2",
                    "S2",
                ],
                "from_stop_sequence": pd.Series(
                    [
                        1,
                        1,
                    ],
                    dtype="Int64",
                ),
                "to_stop_sequence": pd.Series(
                    [
                        2,
                        2,
                    ],
                    dtype="Int64",
                ),
                "departure_seconds": pd.Series(
                    [
                        8 * 3600,
                        9 * 3600,
                    ],
                    dtype="Int64",
                ),
                "arrival_seconds": pd.Series(
                    [
                        8 * 3600 + 60,
                        9 * 3600 + 60,
                    ],
                    dtype="Int64",
                ),
                "in_vehicle_time_s": pd.Series(
                    [
                        60,
                        60,
                    ],
                    dtype="Int64",
                ),
                "from_time_interpolated": [
                    False,
                    False,
                ],
                "to_time_interpolated": [
                    False,
                    False,
                ],
                "uses_interpolated_time": [
                    False,
                    False,
                ],
                "from_time_interpolation_method": [
                    "provided",
                    "provided",
                ],
                "to_time_interpolation_method": [
                    "provided",
                    "provided",
                ],
                "from_shape_position_m": [
                    0.0,
                    0.0,
                ],
                "to_shape_position_m": [
                    100.0,
                    100.0,
                ],
                "shape_segment_distance_m": [
                    100.0,
                    100.0,
                ],
            }
        )

    def test_groups_repeated_connections_into_stable_physical_edge(self):
        # Agrupa horários diferentes quando a geometria física é a mesma
        (
            spatial_connections,
            physical_edges,
            connection_map,
            diagnostics,
        ) = build_transit_physical_network(
            self._connections(),
            shapes=self._shapes(),
            stops=self._stops(),
        )

        self.assertEqual(
            len(
                physical_edges
            ),
            1,
        )
        self.assertEqual(
            physical_edges.iloc[
                0
            ][
                "transit_physical_edge_id"
            ],
            "T_0000001",
        )
        self.assertEqual(
            physical_edges.iloc[
                0
            ][
                "n_connections"
            ],
            2,
        )
        self.assertEqual(
            spatial_connections[
                "transit_physical_edge_id"
            ].nunique(),
            1,
        )
        self.assertTrue(
            connection_map[
                "spatial_geometry_valid"
            ].all()
        )
        self.assertTrue(
            diagnostics[
                "geometry_status"
            ]
            .astype(
                str
            )
            .str.startswith(
                "ok"
            )
            .all()
        )

    def test_creates_exclusive_analysis_segment_for_unmatched_transit_edge(self):
        # Acrescenta um segmento transit quando nenhuma rua existente representa o trecho
        transit_edges = gpd.GeoDataFrame(
            {
                "transit_physical_edge_id": [
                    "T_0000001",
                ],
                "modal_edge_id": [
                    "transit:T_0000001",
                ],
                "shape_id": [
                    "SH1",
                ],
            },
            geometry=[
                LineString(
                    [
                        (
                            0.0,
                            100.0,
                        ),
                        (
                            100.0,
                            100.0,
                        ),
                    ]
                ),
            ],
            crs="EPSG:31982",
        )

        analysis_segments = gpd.GeoDataFrame(
            {
                "analysis_segment_id": [
                    "S_0000001",
                ],
                "source_mode": [
                    "walk",
                ],
                "source_modal_edge_id": [
                    "walk:1:2:0",
                ],
                "strict_key": [
                    "1:2:1",
                ],
                "osmid_signature": [
                    "1",
                ],
                "osmid_set": [
                    frozenset(
                        {
                            "1",
                        }
                    ),
                ],
                "name_norm": [
                    "rua a",
                ],
                "highway_norm": [
                    "residential",
                ],
                "length_m": [
                    100.0,
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

        road_mapping = pd.DataFrame(
            {
                "modal_edge_id": [
                    "car:1:2:0",
                ],
                "mode": [
                    "car",
                ],
                "analysis_segment_id": [
                    "S_0000001",
                ],
                "match_method": [
                    "osm_exact",
                ],
                "match_quality": [
                    1.0,
                ],
            }
        )

        (
            integrated_segments,
            integrated_mapping,
            transit_mapping,
            diagnostics,
        ) = integrate_transit_physical_network(
            analysis_segments,
            road_mapping,
            transit_edges,
            primary_config={
                "tolerance_m": 5.0,
                "min_coverage": 0.5,
                "max_angle_difference_deg": 45.0,
                "candidate_scope": "car_supported",
            },
            fallback_config={
                "enabled": True,
                "tolerance_m": 10.0,
                "min_coverage": 0.35,
                "max_angle_difference_deg": 60.0,
                "candidate_scope": "full_analysis_network",
            },
        )

        self.assertEqual(
            len(
                integrated_segments
            ),
            2,
        )
        self.assertEqual(
            transit_mapping.iloc[
                0
            ][
                "match_method"
            ],
            "gtfs_exclusive",
        )
        self.assertEqual(
            transit_mapping.iloc[
                0
            ][
                "analysis_segment_id"
            ],
            "S_0000002",
        )
        self.assertIn(
            "transit:T_0000001",
            set(
                integrated_mapping[
                    "modal_edge_id"
                ]
            ),
        )
        self.assertEqual(
            diagnostics.iloc[
                0
            ][
                "final_match_stage"
            ],
            "exclusive",
        )

    def test_shared_exclusive_corridor_uses_same_analysis_segment(self):
        # Consolida trechos GTFS coincidentes antes de criar segmentos exclusivos
        transit_edges = gpd.GeoDataFrame(
            {
                "transit_physical_edge_id": [
                    "T_0000001",
                    "T_0000002",
                ],
                "modal_edge_id": [
                    "transit:T_0000001",
                    "transit:T_0000002",
                ],
                "shape_id": [
                    "SH1",
                    "SH2",
                ],
            },
            geometry=[
                LineString(
                    [
                        (
                            0.0,
                            100.0,
                        ),
                        (
                            100.0,
                            100.0,
                        ),
                    ]
                ),
                LineString(
                    [
                        (
                            100.0,
                            100.0,
                        ),
                        (
                            0.0,
                            100.0,
                        ),
                    ]
                ),
            ],
            crs="EPSG:31982",
        )

        analysis_segments = gpd.GeoDataFrame(
            {
                "analysis_segment_id": [
                    "S_0000001",
                ],
                "source_mode": [
                    "walk",
                ],
                "source_modal_edge_id": [
                    "walk:1:2:0",
                ],
                "strict_key": [
                    "1:2:1",
                ],
                "osmid_signature": [
                    "1",
                ],
                "osmid_set": [
                    frozenset(
                        {
                            "1",
                        }
                    ),
                ],
                "name_norm": [
                    "rua a",
                ],
                "highway_norm": [
                    "residential",
                ],
                "length_m": [
                    100.0,
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

        road_mapping = pd.DataFrame(
            {
                "modal_edge_id": [
                    "car:1:2:0",
                ],
                "mode": [
                    "car",
                ],
                "analysis_segment_id": [
                    "S_0000001",
                ],
                "match_method": [
                    "osm_exact",
                ],
                "match_quality": [
                    1.0,
                ],
            }
        )

        (
            integrated_segments,
            _,
            transit_mapping,
            _,
        ) = integrate_transit_physical_network(
            analysis_segments,
            road_mapping,
            transit_edges,
            primary_config={
                "tolerance_m": 5.0,
                "min_coverage": 0.5,
                "max_angle_difference_deg": 45.0,
                "candidate_scope": "car_supported",
            },
            fallback_config={
                "enabled": True,
                "tolerance_m": 10.0,
                "min_coverage": 0.35,
                "max_angle_difference_deg": 60.0,
                "candidate_scope": "full_analysis_network",
            },
        )

        exclusive = transit_mapping.loc[
            transit_mapping[
                "match_stage"
            ]
            == "exclusive"
        ]

        self.assertEqual(
            len(
                integrated_segments
            ),
            2,
        )
        self.assertEqual(
            exclusive[
                "analysis_segment_id"
            ].nunique(),
            1,
        )
        self.assertEqual(
            exclusive[
                "modal_edge_id"
            ].nunique(),
            2,
        )


if __name__ == "__main__":
    unittest.main()
