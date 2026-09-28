import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString

from src.transit.validateGTFSTemporalQuality import (
    build_trip_temporal_quality,
)


class ValidateGTFSTemporalQualityTests(unittest.TestCase):
    def test_builds_trip_level_temporal_quality(self):
        # Resume duração, pontos temporais e conexões zero por viagem
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
                    "A",
                    "B",
                    "C",
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
                        30,
                        60,
                    ],
                    dtype="Int64",
                ),
                "departure_seconds": pd.Series(
                    [
                        0,
                        30,
                        60,
                    ],
                    dtype="Int64",
                ),
                "arrival_missing_raw": [
                    False,
                    True,
                    False,
                ],
                "departure_missing_raw": [
                    False,
                    True,
                    False,
                ],
                "time_interpolated": [
                    False,
                    True,
                    False,
                ],
            }
        )

        connections = pd.DataFrame(
            {
                "connection_id": [
                    "C1",
                    "C2",
                ],
                "trip_id": [
                    "T1",
                    "T1",
                ],
                "in_vehicle_time_s": pd.Series(
                    [
                        0,
                        60,
                    ],
                    dtype="Int64",
                ),
            }
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
                            1000.0,
                            0.0,
                        ),
                    ]
                ),
            ],
            crs="EPSG:31982",
        )

        quality = build_trip_temporal_quality(
            trips=trips,
            stop_times=stop_times,
            connections=connections,
            shapes=shapes,
        )

        row = quality.iloc[
            0
        ]

        self.assertEqual(
            row[
                "n_stops"
            ],
            3,
        )
        self.assertEqual(
            row[
                "n_raw_timepoints"
            ],
            2,
        )
        self.assertEqual(
            row[
                "scheduled_duration_s"
            ],
            60,
        )
        self.assertEqual(
            row[
                "n_zero_duration_connections"
            ],
            1,
        )
        self.assertAlmostEqual(
            row[
                "zero_duration_connection_share"
            ],
            0.5,
        )
        self.assertAlmostEqual(
            row[
                "implied_shape_speed_kmh"
            ],
            60.0,
        )


if __name__ == "__main__":
    unittest.main()
