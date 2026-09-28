import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from src.reporting.exportPilotMetadata import export_pilot_metadata


class ExportPilotMetadataTests(unittest.TestCase):
    def test_exports_required_metadata_sections(self):
        # Cria uma estrutura mínima de projeto para validar o XML
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )
            config_dir = (
                root
                / "config"
            )
            config_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            config = {
                "study_area": {
                    "crs": "EPSG:31982",
                },
                "analysis": {
                    "max_trip_distance": 30000,
                    "analysis_segments": {
                        "geometry_tolerance_m": 5,
                        "min_geometry_coverage": 0.8,
                    },
                    "segment_statistics": {
                        "min_agents_for_interpretation": 5,
                        "flow_thresholds": [
                            2,
                            3,
                            5,
                            10,
                        ],
                    },
                },
                "routing": {
                    "implemented_modes": [
                        "walk",
                        "bike",
                        "car",
                    ],
                },
                "income": {
                    "groups": {},
                },
                "transit": {
                    "network": {
                        "walk_speed_m_s": 1.4,
                        "service_date_strategy": "max_scheduled_trips",
                    },
                },
            }
            config_agents = {
                "mode_choice": {
                    "distance_adjustment": {
                        "decay_per_km": {},
                        "max_distance_km": {},
                    },
                    "differentiated": {},
                },
                "destination_choice": {
                    "distance_decay_per_km": {},
                },
                "purpose_choice": {},
            }

            with (
                config_dir
                / "config.json"
            ).open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    config,
                    file,
                )

            with (
                config_dir
                / "config_agents.json"
            ).open(
                "w",
                encoding="utf-8",
            ) as file:
                json.dump(
                    config_agents,
                    file,
                )

            output_path = export_pilot_metadata(
                project_root=root
            )

            tree = ET.parse(
                output_path
            )
            xml_root = tree.getroot()

            self.assertEqual(
                xml_root.tag,
                "metadados_piloto",
            )
            self.assertIsNotNone(
                xml_root.find(
                    "variaveis_principais"
                )
            )
            self.assertIsNotNone(
                xml_root.find(
                    "metodos_analise"
                )
            )
            self.assertIsNotNone(
                xml_root.find(
                    "estatisticas"
                )
            )
            self.assertIsNotNone(
                xml_root.find(
                    "metodos_limpeza"
                )
            )
            self.assertIsNotNone(
                xml_root.find(
                    "arquivos_gerados"
                )
            )

            descriptions = [
                element.text
                for element in xml_root.findall(
                    ".//descricao"
                )
                if element.text
            ]

            self.assertGreater(
                len(
                    descriptions
                ),
                20,
            )
            self.assertTrue(
                output_path.exists()
            )


if __name__ == "__main__":
    unittest.main()
