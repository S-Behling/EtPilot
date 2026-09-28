import tempfile
import unittest
from pathlib import Path
import zipfile

import geopandas as gpd
import pandas as pd

from src.transit.processGTFS import process_gtfs_zip


class ProcessGTFSTests(unittest.TestCase):
    def _write_feed(
        self,
        directory: Path,
        *,
        include_calendar: bool = True,
        include_calendar_dates: bool = True,
        invalid_stop_reference: bool = False,
    ) -> Path:
        # Cria um GTFS sintético mínimo para validar o processamento
        tables = {
            "agency.txt": (
                "agency_id,agency_name,agency_url,agency_timezone\n"
                "A1,Agencia Teste,https://example.com,America/Sao_Paulo\n"
            ),
            "stops.txt": (
                "stop_id,stop_name,stop_lat,stop_lon\n"
                "S1,Parada 1,-30.0300,-51.2300\n"
                "S2,Parada 2,-30.0250,-51.2250\n"
                "S3,Parada 3,-30.0200,-51.2200\n"
            ),
            "routes.txt": (
                "route_id,agency_id,route_short_name,route_type\n"
                "R1,A1,1,3\n"
            ),
            "trips.txt": (
                "route_id,service_id,trip_id,shape_id\n"
                "R1,WK,T1,SH1\n"
            ),
            "stop_times.txt": (
                "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                "T1,23:50:00,23:50:00,S1,1\n"
                "T1,,,S2,2\n"
                f"T1,25:10:00,25:10:00,"
                f"{'SX' if invalid_stop_reference else 'S3'},3\n"
            ),
            "shapes.txt": (
                "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                "SH1,-30.0300,-51.2300,1\n"
                "SH1,-30.0250,-51.2250,2\n"
                "SH1,-30.0200,-51.2200,3\n"
            ),
        }

        if include_calendar:
            tables[
                "calendar.txt"
            ] = (
                "service_id,monday,tuesday,wednesday,thursday,friday,"
                "saturday,sunday,start_date,end_date\n"
                "WK,1,1,1,1,1,0,0,20260928,20261002\n"
            )

        if include_calendar_dates:
            tables[
                "calendar_dates.txt"
            ] = (
                "service_id,date,exception_type\n"
                "WK,20260930,2\n"
                "WK,20261003,1\n"
            )

        zip_path = (
            directory
            / "gtfs_test.zip"
        )

        with zipfile.ZipFile(
            zip_path,
            "w",
        ) as archive:
            for filename, content in tables.items():
                archive.writestr(
                    filename,
                    content,
                )

        return zip_path

    def test_processes_feed_and_preserves_times_after_midnight(self):
        # Verifica a leitura do feed e a conversão de horários acima de 24 horas
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )
            zip_path = self._write_feed(
                root
            )
            output_dir = (
                root
                / "gtfs"
            )

            summary = process_gtfs_zip(
                zip_path=zip_path,
                output_dir=output_dir,
                projected_crs="EPSG:31982",
            )

            stop_times = pd.read_parquet(
                output_dir
                / "stop_times_processed.parquet"
            )
            service_dates = pd.read_parquet(
                output_dir
                / "service_dates_processed.parquet"
            )
            stops = gpd.read_file(
                output_dir
                / "stops_processed.gpkg",
                layer="stops_processed",
            )

            middle_stop = stop_times.loc[
                stop_times[
                    "stop_sequence"
                ]
                == 2
            ].iloc[
                0
            ]
            last_stop = stop_times.loc[
                stop_times[
                    "stop_sequence"
                ]
                == 3
            ].iloc[
                0
            ]

            self.assertEqual(
                middle_stop[
                    "arrival_seconds"
                ],
                24
                * 3600
                + 30
                * 60,
            )
            self.assertTrue(
                middle_stop[
                    "time_interpolated"
                ]
            )
            self.assertEqual(
                middle_stop[
                    "time_interpolation_method"
                ],
                "shape_geometry",
            )
            self.assertEqual(
                last_stop[
                    "arrival_seconds"
                ],
                25
                * 3600
                + 10
                * 60,
            )
            self.assertEqual(
                summary[
                    "n_stops"
                ],
                3,
            )
            self.assertEqual(
                summary[
                    "stop_times_interpolated"
                ],
                1,
            )
            self.assertEqual(
                summary[
                    "stop_times_interpolated_shape_geometry"
                ],
                1,
            )
            self.assertEqual(
                summary[
                    "stop_times_interpolated_stop_sequence"
                ],
                0,
            )
            self.assertEqual(
                summary[
                    "n_routes"
                ],
                1,
            )
            self.assertEqual(
                summary[
                    "n_trips"
                ],
                1,
            )
            self.assertEqual(
                len(
                    service_dates
                ),
                5,
            )
            self.assertEqual(
                str(
                    stops.crs
                ),
                "EPSG:31982",
            )
            self.assertTrue(
                (
                    output_dir
                    / "shapes_processed.gpkg"
                ).exists()
            )
            self.assertTrue(
                (
                    output_dir
                    / "gtfs_processed_inventory.csv"
                ).exists()
            )
            self.assertTrue(
                (
                    output_dir
                    / "gtfs_processed_summary.csv"
                ).exists()
            )

    def test_accepts_calendar_dates_without_calendar(self):
        # Aceita feeds que definem todo o serviço apenas em calendar_dates
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )
            zip_path = self._write_feed(
                root,
                include_calendar=False,
                include_calendar_dates=True,
            )

            summary = process_gtfs_zip(
                zip_path=zip_path,
                output_dir=(
                    root
                    / "gtfs"
                ),
                projected_crs="EPSG:31982",
            )

            self.assertEqual(
                summary[
                    "n_service_dates"
                ],
                1,
            )

    def test_requires_calendar_or_calendar_dates(self):
        # Rejeita feeds sem definição de datas de serviço
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )
            zip_path = self._write_feed(
                root,
                include_calendar=False,
                include_calendar_dates=False,
            )

            with self.assertRaises(
                ValueError
            ):
                process_gtfs_zip(
                    zip_path=zip_path,
                    output_dir=(
                        root
                        / "gtfs"
                    ),
                    projected_crs="EPSG:31982",
                )

    def test_rejects_stop_times_with_unknown_stop(self):
        # Rejeita referências a paradas inexistentes antes da construção da rede
        with tempfile.TemporaryDirectory() as directory:
            root = Path(
                directory
            )
            zip_path = self._write_feed(
                root,
                invalid_stop_reference=True,
            )

            with self.assertRaises(
                ValueError
            ):
                process_gtfs_zip(
                    zip_path=zip_path,
                    output_dir=(
                        root
                        / "gtfs"
                    ),
                    projected_crs="EPSG:31982",
                )


if __name__ == "__main__":
    unittest.main()
