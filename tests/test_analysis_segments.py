import unittest

import networkx as nx
import pandas as pd
from shapely.geometry import LineString

from src.network.analysis_segments import (
    apply_analysis_segment_mapping,
    build_analysis_segments,
    extract_all_modal_edges,
)


class AnalysisSegmentsTests(unittest.TestCase):
    def _graph(self):
        # Crie um grafo projetado simples para testar a harmonização.
        graph = nx.MultiDiGraph()
        graph.graph["crs"] = "EPSG:31982"

        # Registre coordenadas suficientes para reconstruir geometrias.
        graph.add_node(1, x=0.0, y=0.0)
        graph.add_node(2, x=10.0, y=0.0)
        graph.add_node(3, x=20.0, y=0.0)
        graph.add_node(4, x=0.0, y=100.0)
        graph.add_node(5, x=20.0, y=100.0)

        return graph

    def test_map_long_car_edge_to_two_walk_segments(self):
        walk = self._graph()
        car = self._graph()

        # Divida a referência de caminhada em dois segmentos.
        walk.add_edge(
            1,
            2,
            key=0,
            osmid=10,
            length=10.0,
            geometry=LineString(
                [(0.0, 0.0), (10.0, 0.0)]
            ),
        )
        walk.add_edge(
            2,
            3,
            key=0,
            osmid=10,
            length=10.0,
            geometry=LineString(
                [(10.0, 0.0), (20.0, 0.0)]
            ),
        )

        # Represente no carro a mesma rua como uma única aresta longa.
        car.add_edge(
            1,
            3,
            key=0,
            osmid=10,
            length=20.0,
            geometry=LineString(
                [(0.0, 0.0), (20.0, 0.0)]
            ),
        )

        modal_edges = extract_all_modal_edges(
            {
                "walk": walk,
                "car": car,
            },
            modes=("walk", "car"),
        )

        segments, mapping = build_analysis_segments(
            modal_edges,
            reference_mode="walk",
            mode_order=("walk", "car"),
            tolerance_m=1.0,
            min_coverage=0.95,
        )

        car_mapping = mapping[
            mapping["modal_edge_id"]
            == "car:1:3:0"
        ]

        self.assertEqual(
            len(segments),
            2,
        )
        self.assertEqual(
            len(car_mapping),
            2,
        )
        self.assertTrue(
            (
                car_mapping["match_method"]
                == "geometry"
            ).all()
        )

    def test_preserve_unmatched_car_edge_as_exclusive(self):
        walk = self._graph()
        car = self._graph()

        walk.add_edge(
            1,
            2,
            key=0,
            osmid=10,
            length=10.0,
            geometry=LineString(
                [(0.0, 0.0), (10.0, 0.0)]
            ),
        )
        car.add_edge(
            4,
            5,
            key=0,
            osmid=99,
            length=20.0,
            geometry=LineString(
                [(0.0, 100.0), (20.0, 100.0)]
            ),
        )

        modal_edges = extract_all_modal_edges(
            {
                "walk": walk,
                "car": car,
            },
            modes=("walk", "car"),
        )

        segments, mapping = build_analysis_segments(
            modal_edges,
            reference_mode="walk",
            mode_order=("walk", "car"),
            tolerance_m=1.0,
            min_coverage=0.95,
        )

        car_mapping = mapping[
            mapping["modal_edge_id"]
            == "car:4:5:0"
        ]

        self.assertEqual(
            len(segments),
            2,
        )
        self.assertEqual(
            car_mapping.iloc[0]["match_method"],
            "exclusive",
        )

    def test_use_complete_network_even_when_reference_edge_is_not_observed(self):
        walk = self._graph()
        car = self._graph()

        # Inclua na rede completa um trecho de caminhada que não apareça na amostra.
        walk.add_edge(
            1,
            2,
            key=0,
            osmid=10,
            length=10.0,
            geometry=LineString(
                [(0.0, 0.0), (10.0, 0.0)]
            ),
        )

        # Faça o carro usar exatamente o mesmo trecho físico.
        car.add_edge(
            1,
            2,
            key=0,
            osmid=10,
            length=10.0,
            geometry=LineString(
                [(0.0, 0.0), (10.0, 0.0)]
            ),
        )

        modal_edges = extract_all_modal_edges(
            {
                "walk": walk,
                "car": car,
            },
            modes=("walk", "car"),
        )

        _, mapping = build_analysis_segments(
            modal_edges,
            reference_mode="walk",
            mode_order=("walk", "car"),
            tolerance_m=1.0,
            min_coverage=0.95,
        )

        walk_segment = mapping.loc[
            mapping["modal_edge_id"]
            == "walk:1:2:0",
            "analysis_segment_id",
        ].iloc[0]

        car_row = mapping.loc[
            mapping["modal_edge_id"]
            == "car:1:2:0"
        ].iloc[0]

        self.assertEqual(
            car_row["analysis_segment_id"],
            walk_segment,
        )
        self.assertEqual(
            car_row["match_method"],
            "osm_exact",
        )

    def test_explode_edge_usage_when_mapping_is_one_to_many(self):
        edge_usage = pd.DataFrame(
            [
                {
                    "scenario": "baseline",
                    "agent_id": 1,
                    "mode": "car",
                    "modal_edge_id": "car:1:3:0",
                }
            ]
        )

        mapping = pd.DataFrame(
            [
                {
                    "modal_edge_id": "car:1:3:0",
                    "mode": "car",
                    "analysis_segment_id": "S_0000001",
                    "match_method": "geometry",
                    "match_quality": 1.0,
                },
                {
                    "modal_edge_id": "car:1:3:0",
                    "mode": "car",
                    "analysis_segment_id": "S_0000002",
                    "match_method": "geometry",
                    "match_quality": 1.0,
                },
            ]
        )

        result = apply_analysis_segment_mapping(
            edge_usage,
            mapping,
        )

        self.assertEqual(
            len(result),
            2,
        )
        self.assertEqual(
            set(
                result[
                    "analysis_segment_id"
                ]
            ),
            {
                "S_0000001",
                "S_0000002",
            },
        )


if __name__ == "__main__":
    unittest.main()
