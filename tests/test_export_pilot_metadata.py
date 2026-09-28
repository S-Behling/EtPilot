import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from src.reporting.exportPilotMetadata import export_pilot_metadata


class ExportPilotMetadataTests(unittest.TestCase):
    def test_exports_required_metadata_formats(self):
        # Cria uma estrutura mínima de projeto para validar XLSX e HTML
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

            paths = export_pilot_metadata(
                project_root=root
            )

            xlsx_path = paths[
                "xlsx"
            ]
            html_path = paths[
                "html"
            ]

            self.assertTrue(
                xlsx_path.exists()
            )
            self.assertTrue(
                html_path.exists()
            )
            self.assertFalse(
                (
                    root
                    / "outputs"
                    / "metadados_piloto.xml"
                ).exists()
            )

            with zipfile.ZipFile(
                xlsx_path,
                "r",
            ) as archive:
                names = set(
                    archive.namelist()
                )

            self.assertIn(
                "xl/workbook.xml",
                names,
            )
            self.assertIn(
                "xl/worksheets/sheet1.xml",
                names,
            )

            html = html_path.read_text(
                encoding="utf-8"
            )

            self.assertIn(
                "Variáveis principais",
                html,
            )
            self.assertIn(
                "Métodos de análise",
                html,
            )
            self.assertIn(
                "Estatísticas",
                html,
            )
            self.assertIn(
                "Métodos de limpeza e validação",
                html,
            )
            self.assertIn(
                "Arquivos gerados",
                html,
            )
            self.assertIn(
                "português",
                html,
            )


if __name__ == "__main__":
    unittest.main()
