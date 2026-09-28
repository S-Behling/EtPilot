"""Avalia a qualidade temporal das viagens GTFS processadas

Resume a quantidade de pontos temporais originalmente informados por viagem
Calcula duração programada, duração acumulada entre paradas e conexões de
duração zero
Relaciona a duração das viagens ao comprimento dos shapes quando disponível
Exporta um diagnóstico por trip_id para orientar a reconstrução temporal
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "pilot"
OUTPUT_FILE = "gtfs_trip_temporal_quality.csv"


def _load_config() -> dict:
    """Carrega a configuração principal do projeto"""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


def _format_int_pt(
    value,
) -> str:
    """Formata números inteiros com separador de milhar brasileiro"""

    return f"{int(value):,}".replace(
        ",",
        ".",
    )


def _format_float_pt(
    value,
    *,
    decimals: int = 1,
) -> str:
    """Formata números decimais com vírgula"""

    if pd.isna(
        value
    ):
        return "não disponível"

    formatted = f"{float(value):,.{decimals}f}"

    return (
        formatted
        .replace(
            ",",
            "_",
        )
        .replace(
            ".",
            ",",
        )
        .replace(
            "_",
            ".",
        )
    )


def _format_percentage_pt(
    numerator,
    denominator,
) -> str:
    """Formata uma proporção como percentual com vírgula decimal"""

    denominator_value = float(
        denominator
    )

    if denominator_value <= 0:
        return "0,0%"

    value = (
        100.0
        * float(
            numerator
        )
        / denominator_value
    )

    return (
        f"{value:.1f}%"
        .replace(
            ".",
            ",",
        )
    )


def _load_processed_data(
    *,
    data_dir: Path,
    network_config: dict,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    gpd.GeoDataFrame | None,
]:
    """Carrega as tabelas usadas na avaliação temporal"""

    trips = pd.read_parquet(
        data_dir
        / "trips_processed.parquet"
    )
    stop_times = pd.read_parquet(
        data_dir
        / "stop_times_processed.parquet"
    )
    connections = pd.read_parquet(
        data_dir
        / network_config[
            "connections_file"
        ]
    )

    shapes_path = (
        data_dir
        / "shapes_processed.gpkg"
    )

    shapes = (
        gpd.read_file(
            shapes_path,
            layer="shapes_processed",
            engine="pyogrio",
        )
        if shapes_path.exists()
        else None
    )

    return (
        trips,
        stop_times,
        connections,
        shapes,
    )


def _trip_stop_summary(
    stop_times: pd.DataFrame,
) -> pd.DataFrame:
    """Resume pontos temporais, duração e interpolação em cada viagem"""

    ordered = (
        stop_times
        .sort_values(
            [
                "trip_id",
                "stop_sequence",
            ]
        )
        .reset_index(
            drop=True
        )
        .copy()
    )

    raw_timepoint = ~(
        ordered[
            "arrival_missing_raw"
        ].astype(
            bool
        )
        & ordered[
            "departure_missing_raw"
        ].astype(
            bool
        )
    )

    ordered[
        "_raw_timepoint"
    ] = raw_timepoint

    first_rows = (
        ordered.groupby(
            "trip_id",
            sort=False,
        )
        .head(
            1
        )
        .set_index(
            "trip_id"
        )
    )
    last_rows = (
        ordered.groupby(
            "trip_id",
            sort=False,
        )
        .tail(
            1
        )
        .set_index(
            "trip_id"
        )
    )

    summary = (
        ordered.groupby(
            "trip_id",
            as_index=False,
        )
        .agg(
            n_stops=(
                "stop_id",
                "size",
            ),
            n_raw_timepoints=(
                "_raw_timepoint",
                "sum",
            ),
            n_interpolated_stops=(
                "time_interpolated",
                "sum",
            ),
        )
    )

    summary[
        "trip_start_seconds"
    ] = (
        summary[
            "trip_id"
        ]
        .map(
            first_rows[
                "departure_seconds"
            ]
        )
        .astype(
            "Int64"
        )
    )
    summary[
        "trip_end_seconds"
    ] = (
        summary[
            "trip_id"
        ]
        .map(
            last_rows[
                "arrival_seconds"
            ]
        )
        .astype(
            "Int64"
        )
    )
    summary[
        "scheduled_duration_s"
    ] = (
        summary[
            "trip_end_seconds"
        ]
        - summary[
            "trip_start_seconds"
        ]
    )

    summary[
        "interpolated_stop_share"
    ] = (
        summary[
            "n_interpolated_stops"
        ]
        / summary[
            "n_stops"
        ]
    )

    return summary


def _trip_connection_summary(
    connections: pd.DataFrame,
) -> pd.DataFrame:
    """Resume duração e incidência de conexões de duração zero por viagem"""

    frame = connections.copy()

    frame[
        "_zero_duration"
    ] = (
        frame[
            "in_vehicle_time_s"
        ]
        == 0
    )

    summary = (
        frame.groupby(
            "trip_id",
            as_index=False,
        )
        .agg(
            n_connections=(
                "connection_id",
                "size",
            ),
            total_in_vehicle_time_s=(
                "in_vehicle_time_s",
                "sum",
            ),
            mean_connection_time_s=(
                "in_vehicle_time_s",
                "mean",
            ),
            median_connection_time_s=(
                "in_vehicle_time_s",
                "median",
            ),
            min_connection_time_s=(
                "in_vehicle_time_s",
                "min",
            ),
            max_connection_time_s=(
                "in_vehicle_time_s",
                "max",
            ),
            n_zero_duration_connections=(
                "_zero_duration",
                "sum",
            ),
        )
    )

    summary[
        "zero_duration_connection_share"
    ] = (
        summary[
            "n_zero_duration_connections"
        ]
        / summary[
            "n_connections"
        ]
    )

    return summary


def _shape_summary(
    *,
    trips: pd.DataFrame,
    shapes: gpd.GeoDataFrame | None,
) -> pd.DataFrame:
    """Associa a cada viagem o comprimento total do shape quando disponível"""

    base = trips[
        [
            column
            for column in (
                "trip_id",
                "route_id",
                "service_id",
                "shape_id",
            )
            if column in trips.columns
        ]
    ].copy()

    if (
        shapes is None
        or "shape_id" not in base.columns
    ):
        base[
            "shape_length_m"
        ] = np.nan
        return base

    shape_lengths = (
        shapes[
            [
                "shape_id",
                "geometry",
            ]
        ]
        .copy()
    )
    shape_lengths[
        "shape_length_m"
    ] = shape_lengths.geometry.length.astype(
        float
    )

    return base.merge(
        shape_lengths[
            [
                "shape_id",
                "shape_length_m",
            ]
        ],
        on="shape_id",
        how="left",
        validate="many_to_one",
    )


def _safe_speed_kmh(
    *,
    distance_m: pd.Series,
    duration_s: pd.Series,
) -> np.ndarray:
    """Calcula velocidade em km/h preservando valores ausentes como NaN"""

    distance_values = (
        pd.to_numeric(
            distance_m,
            errors="coerce",
        )
        .astype(
            "Float64"
        )
        .to_numpy(
            dtype=float,
            na_value=np.nan,
        )
    )
    duration_values = (
        pd.to_numeric(
            duration_s,
            errors="coerce",
        )
        .astype(
            "Float64"
        )
        .to_numpy(
            dtype=float,
            na_value=np.nan,
        )
    )

    valid = (
        np.isfinite(
            distance_values
        )
        & np.isfinite(
            duration_values
        )
        & (
            duration_values
            > 0
        )
    )

    speeds = np.full(
        len(
            distance_values
        ),
        np.nan,
        dtype=float,
    )

    speeds[
        valid
    ] = (
        distance_values[
            valid
        ]
        / duration_values[
            valid
        ]
        * 3.6
    )

    return speeds


def build_trip_temporal_quality(
    *,
    trips: pd.DataFrame,
    stop_times: pd.DataFrame,
    connections: pd.DataFrame,
    shapes: gpd.GeoDataFrame | None,
) -> pd.DataFrame:
    """Constrói o diagnóstico temporal por trip_id"""

    stop_summary = _trip_stop_summary(
        stop_times
    )
    connection_summary = (
        _trip_connection_summary(
            connections
        )
    )
    shape_summary = _shape_summary(
        trips=trips,
        shapes=shapes,
    )

    quality = (
        shape_summary
        .merge(
            stop_summary,
            on="trip_id",
            how="left",
            validate="one_to_one",
        )
        .merge(
            connection_summary,
            on="trip_id",
            how="left",
            validate="one_to_one",
        )
    )

    quality[
        "scheduled_duration_min"
    ] = (
        quality[
            "scheduled_duration_s"
        ]
        / 60.0
    )

    quality[
        "implied_shape_speed_kmh"
    ] = _safe_speed_kmh(
        distance_m=quality[
            "shape_length_m"
        ],
        duration_s=quality[
            "scheduled_duration_s"
        ],
    )

    quality[
        "in_vehicle_shape_speed_kmh"
    ] = _safe_speed_kmh(
        distance_m=quality[
            "shape_length_m"
        ],
        duration_s=quality[
            "total_in_vehicle_time_s"
        ],
    )

    quality[
        "has_zero_duration_connections"
    ] = (
        quality[
            "n_zero_duration_connections"
        ]
        .fillna(
            0
        )
        > 0
    )
    quality[
        "nonpositive_scheduled_duration"
    ] = (
        quality[
            "scheduled_duration_s"
        ]
        .fillna(
            0
        )
        <= 0
    )
    quality[
        "two_or_fewer_raw_timepoints"
    ] = (
        quality[
            "n_raw_timepoints"
        ]
        .fillna(
            0
        )
        <= 2
    )

    return quality.sort_values(
        [
            "route_id",
            "trip_id",
        ]
    ).reset_index(
        drop=True
    )


def run_temporal_quality_diagnostics() -> pd.DataFrame:
    """Executa o diagnóstico temporal e salva uma linha por viagem GTFS"""

    config = _load_config()
    gtfs_config = config[
        "transit"
    ][
        "gtfs"
    ]
    network_config = config[
        "transit"
    ][
        "network"
    ]

    data_dir = (
        PROJECT_ROOT
        / gtfs_config[
            "data_dir"
        ]
    )

    (
        trips,
        stop_times,
        connections,
        shapes,
    ) = _load_processed_data(
        data_dir=data_dir,
        network_config=network_config,
    )

    quality = build_trip_temporal_quality(
        trips=trips,
        stop_times=stop_times,
        connections=connections,
        shapes=shapes,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    quality.to_csv(
        OUTPUT_DIR
        / OUTPUT_FILE,
        index=False,
        encoding="utf-8",
    )

    return quality


def main() -> None:
    """Executa e imprime o diagnóstico temporal das viagens GTFS"""

    quality = run_temporal_quality_diagnostics()

    total = len(
        quality
    )
    with_shape_speed = quality[
        "implied_shape_speed_kmh"
    ].dropna()

    print(
        "\n"
        + "="
        * 72
    )
    print(
        "DIAGNÓSTICO DA QUALIDADE TEMPORAL DO GTFS"
    )
    print(
        "="
        * 72
    )

    print(
        "\nEstrutura temporal por viagem"
    )
    print(
        "  Viagens avaliadas: "
        f"{_format_int_pt(total)} viagens"
    )
    print(
        "  Paradas por viagem — mediana: "
        f"{_format_float_pt(quality['n_stops'].median())} paradas"
    )
    print(
        "  Pontos temporais originais por viagem — mediana: "
        f"{_format_float_pt(quality['n_raw_timepoints'].median())} pontos"
    )

    few_timepoints = quality.loc[
        quality[
            "two_or_fewer_raw_timepoints"
        ]
    ]

    print(
        "  Viagens com até 2 pontos temporais originais: "
        f"{_format_int_pt(len(few_timepoints))} viagens "
        f"({_format_percentage_pt(len(few_timepoints), total)})"
    )

    print(
        "\nDuração programada"
    )
    print(
        "  Mediana: "
        f"{_format_float_pt(quality['scheduled_duration_min'].median())} min"
    )
    print(
        "  Percentil 5: "
        f"{_format_float_pt(quality['scheduled_duration_min'].quantile(0.05))} min"
    )
    print(
        "  Percentil 95: "
        f"{_format_float_pt(quality['scheduled_duration_min'].quantile(0.95))} min"
    )

    nonpositive = quality.loc[
        quality[
            "nonpositive_scheduled_duration"
        ]
    ]

    print(
        "  Viagens com duração programada menor ou igual a zero: "
        f"{_format_int_pt(len(nonpositive))} viagens "
        f"({_format_percentage_pt(len(nonpositive), total)})"
    )

    print(
        "\nConexões de duração zero"
    )
    any_zero = quality.loc[
        quality[
            "has_zero_duration_connections"
        ]
    ]

    print(
        "  Viagens com pelo menos uma conexão de duração zero: "
        f"{_format_int_pt(len(any_zero))} viagens "
        f"({_format_percentage_pt(len(any_zero), total)})"
    )
    print(
        "  Participação de conexões zero por viagem — mediana: "
        f"{_format_percentage_pt(quality['zero_duration_connection_share'].median(), 1)}"
    )
    print(
        "  Participação de conexões zero por viagem — percentil 95: "
        f"{_format_percentage_pt(quality['zero_duration_connection_share'].quantile(0.95), 1)}"
    )

    print(
        "\nVelocidade implícita pelo comprimento do shape"
    )

    if with_shape_speed.empty:
        print(
            "  Não há viagens com shape e duração positiva suficientes para o cálculo"
        )
    else:
        print(
            "  Viagens com velocidade calculável: "
            f"{_format_int_pt(len(with_shape_speed))} viagens "
            f"({_format_percentage_pt(len(with_shape_speed), total)})"
        )
        print(
            "  Velocidade implícita — mediana: "
            f"{_format_float_pt(with_shape_speed.median())} km/h"
        )
        print(
            "  Velocidade implícita — percentil 5: "
            f"{_format_float_pt(with_shape_speed.quantile(0.05))} km/h"
        )
        print(
            "  Velocidade implícita — percentil 95: "
            f"{_format_float_pt(with_shape_speed.quantile(0.95))} km/h"
        )
        print(
            "  Velocidade implícita — máxima: "
            f"{_format_float_pt(with_shape_speed.max())} km/h"
        )

        for threshold in (
            30,
            50,
            80,
        ):
            above = int(
                (
                    with_shape_speed
                    > threshold
                ).sum()
            )

            print(
                f"  Acima de {threshold} km/h: "
                f"{_format_int_pt(above)} viagens "
                f"({_format_percentage_pt(above, len(with_shape_speed))})"
            )

    worst_zero = (
        quality.sort_values(
            [
                "zero_duration_connection_share",
                "n_connections",
            ],
            ascending=[
                False,
                False,
            ],
        )
        .head(
            5
        )
    )

    print(
        "\nViagens com maior participação de conexões de duração zero"
    )

    for row in worst_zero.itertuples(
        index=False
    ):
        print(
            "  "
            f"trip_id={row.trip_id} | "
            f"route_id={row.route_id} | "
            f"{_format_percentage_pt(row.zero_duration_connection_share, 1)} zero | "
            f"{_format_int_pt(row.n_connections)} conexões | "
            f"{_format_float_pt(row.scheduled_duration_min)} min"
        )

    print(
        "\nSaída"
    )
    print(
        "  Arquivo: "
        f"{(OUTPUT_DIR / OUTPUT_FILE).resolve()}"
    )

    from src.reporting.exportPilotMetadata import (
        export_pilot_metadata,
    )

    metadata_paths = export_pilot_metadata(
        project_root=PROJECT_ROOT
    )

    print(
        "  Metadados XLSX: "
        f"{metadata_paths['xlsx']}"
    )
    print(
        "  Metadados HTML: "
        f"{metadata_paths['html']}"
    )


if __name__ == "__main__":
    main()
