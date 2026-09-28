import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from src.analysis.pilot_maps import (
    plot_delta_h_soc,
    plot_h_soc,
    save_pilot_maps,
)


class PilotMapsTests(unittest.TestCase):
    def _scenario_geodata(
        self,
        scenario_name,
        h_values,
        sufficient,
    ):
        # Cria uma rede pequena com segmentos observados e não observados
        return gpd.GeoDataFrame(
            [
                {
                    "analysis_segment_id": "S_1",
                    "scenario": scenario_name,
                    "H_soc": h_values[0],
                    "n_agents": 5,
                    "sufficient_flow": sufficient[0],
                    "geometry": LineString(
                        [(0, 0), (1, 0)]
                    ),
                },
                {
                    "analysis_segment_id": "S_2",
                    "scenario": scenario_name,
                    "H_soc": h_values[1],
                    "n_agents": 2,
                    "sufficient_flow": sufficient[1],
                    "geometry": LineString(
                        [(1, 0), (2, 0)]
                    ),
                },
                {
                    "analysis_segment_id": "S_3",
                    "scenario": scenario_name,
                    "H_soc": None,
                    "n_agents": 0,
                    "sufficient_flow": False,
                    "geometry": LineString(
                        [(2, 0), (3, 0)]
                    ),
                },
            ],
            geometry="geometry",
            crs="EPSG:31982",
        )

    def _comparison_geodata(self):
        # Cria uma comparação com um segmento suportado e outro insuficiente
        return gpd.GeoDataFrame(
            [
                {
                    "analysis_segment_id": "S_1",
                    "delta_H_soc": 0.2,
                    "comparable_H_soc": True,
                    "sufficient_flow_both": True,
                    "geometry": LineString(
                        [(0, 0), (1, 0)]
                    ),
                },
                {
                    "analysis_segment_id": "S_2",
                    "delta_H_soc": -0.3,
                    "comparable_H_soc": True,
                    "sufficient_flow_both": False,
                    "geometry": LineString(
                        [(1, 0), (2, 0)]
                    ),
                },
                {
                    "analysis_segment_id": "S_3",
                    "delta_H_soc": None,
                    "comparable_H_soc": False,
                    "sufficient_flow_both": False,
                    "geometry": LineString(
                        [(2, 0), (3, 0)]
                    ),
                },
            ],
            geometry="geometry",
            crs="EPSG:31982",
        )

    def test_plot_h_soc_filters_supported_segments(self):
        geodata = self._scenario_geodata(
            "baseline",
            [0.4, 0.8],
            [True, False],
        )

        figure, _, count = plot_h_soc(
            geodata,
            title="Teste",
            supported_only=True,
        )

        self.assertEqual(
            count,
            1,
        )

        figure.clf()

    def test_plot_delta_h_soc_filters_supported_segments(self):
        comparison = self._comparison_geodata()

        figure, _, count = plot_delta_h_soc(
            comparison,
            title="Teste",
            supported_only=True,
        )

        self.assertEqual(
            count,
            1,
        )

        figure.clf()

    def test_save_pilot_maps_writes_six_maps_and_manifest(self):
        segment_geodata = {
            "baseline": self._scenario_geodata(
                "baseline",
                [0.4, 0.8],
                [True, False],
            ),
            "differentiated": self._scenario_geodata(
                "differentiated",
                [0.6, 0.3],
                [True, False],
            ),
        }

        comparison = self._comparison_geodata()

        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(
                directory
            )

            manifest = save_pilot_maps(
                segment_geodata=segment_geodata,
                scenario_comparison_geodata=comparison,
                output_dir=output_dir,
                dpi=72,
            )

            self.assertEqual(
                len(
                    manifest
                ),
                6,
            )
            self.assertIn(
                "description_pt",
                manifest.columns,
            )
            self.assertTrue(
                manifest[
                    "description_pt"
                ]
                .astype(
                    "string"
                )
                .str.len()
                .gt(
                    0
                )
                .all()
            )

            self.assertTrue(
                (
                    output_dir
                    / "map_manifest.csv"
                ).exists()
            )

            for filename in manifest[
                "filename"
            ]:
                self.assertTrue(
                    (
                        output_dir
                        / filename
                    ).exists()
                )


if __name__ == "__main__":
    unittest.main()
