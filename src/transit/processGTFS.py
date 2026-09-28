"""Processa o GTFS estático do piloto e prepara tabelas para o roteamento

Lê o ZIP original diretamente de data/gtfs sem criar uma pasta raw adicional
Mantém os produtos processados no mesmo diretório e explicita o estado
processado no nome de cada arquivo

Valida as relações básicas entre rotas, viagens, serviços, paradas e horários
Converte horários GTFS para segundos desde o início do dia de serviço
Expande as datas de serviço em service_dates_processed.parquet
Projeta as paradas para o CRS do estudo e constrói geometrias de shapes quando
o feed fornece shapes.txt

Trata o feed configurado atualmente como transporte coletivo por ônibus
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"

CORE_FILES = (
    "agency.txt",
    "stops.txt",
    "routes.txt",
    "trips.txt",
    "stop_times.txt",
)

OPTIONAL_FILES = (
    "calendar.txt",
    "calendar_dates.txt",
    "shapes.txt",
    "frequencies.txt",
    "transfers.txt",
    "feed_info.txt",
)

WEEKDAY_COLUMNS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

PROCESSED_TABLE_FILES = {
    "agency": "agency_processed.parquet",
    "routes": "routes_processed.parquet",
    "trips": "trips_processed.parquet",
    "stop_times": "stop_times_processed.parquet",
    "calendar": "calendar_processed.parquet",
    "calendar_dates": "calendar_dates_processed.parquet",
    "frequencies": "frequencies_processed.parquet",
    "transfers": "transfers_processed.parquet",
    "feed_info": "feed_info_processed.parquet",
    "service_dates": "service_dates_processed.parquet",
}

STOPS_GPKG = "stops_processed.gpkg"
SHAPES_GPKG = "shapes_processed.gpkg"
SUMMARY_CSV = "gtfs_processed_summary.csv"
INVENTORY_CSV = "gtfs_processed_inventory.csv"


def _load_config() -> dict:
    """Carrega a configuração principal do projeto"""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


def _member_map(
    archive: zipfile.ZipFile,
) -> dict[str, str]:
    """Mapeia o nome base dos arquivos GTFS para o membro real do ZIP"""

    result: dict[
        str,
        str,
    ] = {}

    for member in archive.namelist():
        if member.endswith(
            "/"
        ):
            continue

        basename = Path(
            member
        ).name.lower()

        if basename in result:
            raise ValueError(
                "O ZIP contém nomes GTFS duplicados em diretórios diferentes: "
                f"{basename}"
            )

        result[
            basename
        ] = member

    return result


def _read_table(
    archive: zipfile.ZipFile,
    members: dict[str, str],
    filename: str,
) -> pd.DataFrame:
    """Lê uma tabela GTFS como strings preservando identificadores"""

    key = filename.lower()

    if key not in members:
        raise KeyError(
            filename
        )

    with archive.open(
        members[
            key
        ]
    ) as file:
        frame = pd.read_csv(
            file,
            dtype="string",
            keep_default_na=False,
            encoding="utf-8-sig",
            low_memory=False,
        )

    frame.columns = [
        str(
            column
        ).strip()
        for column in frame.columns
    ]

    for column in frame.columns:
        if pd.api.types.is_string_dtype(
            frame[
                column
            ].dtype
        ):
            frame[
                column
            ] = frame[
                column
            ].str.strip()

    return frame


def _require_columns(
    frame: pd.DataFrame,
    table_name: str,
    required: tuple[str, ...] | list[str],
) -> None:
    """Exige as colunas necessárias para o processamento"""

    missing = (
        set(
            required
        )
        - set(
            frame.columns
        )
    )

    if missing:
        raise ValueError(
            f"{table_name} não possui as colunas obrigatórias: "
            f"{sorted(missing)}"
        )


def _require_unique(
    frame: pd.DataFrame,
    table_name: str,
    columns: tuple[str, ...] | list[str],
) -> None:
    """Exige unicidade na chave lógica da tabela"""

    duplicated = frame.duplicated(
        subset=list(
            columns
        ),
        keep=False,
    )

    if duplicated.any():
        sample = (
            frame.loc[
                duplicated,
                list(
                    columns
                ),
            ]
            .head(
                5
            )
            .to_dict(
                orient="records"
            )
        )

        raise ValueError(
            f"{table_name} possui chaves duplicadas em {list(columns)}: "
            f"{sample}"
        )


def _require_nonempty(
    frame: pd.DataFrame,
    table_name: str,
    columns: tuple[str, ...] | list[str],
) -> None:
    """Exige valores não vazios nos campos usados pelo piloto"""

    for column in columns:
        invalid = (
            frame[
                column
            ]
            .astype(
                "string"
            )
            .str.strip()
            .eq(
                ""
            )
        )

        if invalid.any():
            raise ValueError(
                f"{table_name} possui {int(invalid.sum())} valores vazios "
                f"em '{column}'"
            )


def _to_numeric(
    frame: pd.DataFrame,
    table_name: str,
    column: str,
    *,
    integer: bool = False,
    nullable: bool = False,
) -> None:
    """Converte uma coluna para tipo numérico e valida valores inválidos"""

    original = frame[
        column
    ].astype(
        "string"
    )

    values = pd.to_numeric(
        original.replace(
            "",
            pd.NA,
        ),
        errors="coerce",
    )

    invalid = (
        original.ne(
            ""
        )
        & values.isna()
    )

    if invalid.any():
        sample = (
            original.loc[
                invalid
            ]
            .head(
                5
            )
            .tolist()
        )

        raise ValueError(
            f"{table_name}.{column} contém valores numéricos inválidos: "
            f"{sample}"
        )

    if not nullable and values.isna().any():
        raise ValueError(
            f"{table_name}.{column} contém valores ausentes"
        )

    frame[
        column
    ] = (
        values.astype(
            "Int64"
        )
        if integer
        else values.astype(
            "Float64"
        )
    )


def _parse_gtfs_time(
    value,
) -> int | object:
    """Converte HH:MM:SS GTFS para segundos desde o início do dia de serviço"""

    if pd.isna(
        value
    ):
        return pd.NA

    text = str(
        value
    ).strip()

    if not text:
        return pd.NA

    parts = text.split(
        ":"
    )

    if len(
        parts
    ) != 3:
        raise ValueError(
            f"Horário GTFS inválido: {text!r}"
        )

    try:
        hours, minutes, seconds = (
            int(
                part
            )
            for part in parts
        )
    except ValueError as error:
        raise ValueError(
            f"Horário GTFS inválido: {text!r}"
        ) from error

    if (
        hours < 0
        or minutes < 0
        or minutes > 59
        or seconds < 0
        or seconds > 59
    ):
        raise ValueError(
            f"Horário GTFS inválido: {text!r}"
        )

    return (
        hours
        * 3600
        + minutes
        * 60
        + seconds
    )


def _add_time_seconds(
    frame: pd.DataFrame,
    source_column: str,
    target_column: str,
) -> None:
    """Adiciona uma coluna em segundos preservando horários após 24 horas"""

    if source_column not in frame.columns:
        frame[
            target_column
        ] = pd.Series(
            pd.NA,
            index=frame.index,
            dtype="Int64",
        )
        return

    parsed = frame[
        source_column
    ].map(
        _parse_gtfs_time
    )

    frame[
        target_column
    ] = pd.Series(
        parsed,
        index=frame.index,
        dtype="Int64",
    )


def _interpolate_stop_time_events(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    """Interpola horários ausentes entre pontos temporais conhecidos"""

    result = frame.copy()

    raw_arrival_missing = (
        result[
            "arrival_seconds"
        ].isna()
    )
    raw_departure_missing = (
        result[
            "departure_seconds"
        ].isna()
    )

    result[
        "time_interpolated"
    ] = False
    result[
        "time_filled_from_pair"
    ] = (
        raw_arrival_missing
        ^ raw_departure_missing
    )
    result[
        "time_interpolation_method"
    ] = "provided"

    grouped_indices = result.groupby(
        "trip_id",
        sort=False,
    ).indices

    for trip_id, positions in grouped_indices.items():
        positions = np.asarray(
            positions,
            dtype=int,
        )

        arrivals = (
            result.iloc[
                positions
            ][
                "arrival_seconds"
            ]
            .astype(
                "Float64"
            )
            .to_numpy(
                dtype=float,
                na_value=np.nan,
            )
        )
        departures = (
            result.iloc[
                positions
            ][
                "departure_seconds"
            ]
            .astype(
                "Float64"
            )
            .to_numpy(
                dtype=float,
                na_value=np.nan,
            )
        )

        event_seconds = np.where(
            np.isfinite(
                departures
            ),
            departures,
            arrivals,
        )
        known = np.isfinite(
            event_seconds
        )

        if (
            not known[
                0
            ]
            or not known[
                -1
            ]
        ):
            raise ValueError(
                "stop_times.txt possui viagem sem horário no primeiro "
                f"ou último ponto: trip_id={trip_id}"
            )

        missing = ~known

        if missing.any():
            sequence = (
                result.iloc[
                    positions
                ][
                    "stop_sequence"
                ]
                .astype(
                    float
                )
                .to_numpy()
            )

            basis = sequence
            method = "stop_sequence"

            if (
                "shape_dist_traveled"
                in result.columns
            ):
                shape_distance = (
                    result.iloc[
                        positions
                    ][
                        "shape_dist_traveled"
                    ]
                    .astype(
                        "Float64"
                    )
                    .to_numpy(
                        dtype=float,
                        na_value=np.nan,
                    )
                )

                valid_shape_distance = (
                    np.isfinite(
                        shape_distance
                    ).all()
                    and np.all(
                        np.diff(
                            shape_distance
                        )
                        >= 0
                    )
                    and np.unique(
                        shape_distance[
                            known
                        ]
                    ).size
                    >= 2
                )

                if valid_shape_distance:
                    basis = shape_distance
                    method = "shape_dist_traveled"

            known_basis = basis[
                known
            ]

            if np.unique(
                known_basis
            ).size < 2:
                raise ValueError(
                    "stop_times.txt não possui base suficiente para "
                    f"interpolar trip_id={trip_id}"
                )

            interpolated = np.interp(
                basis[
                    missing
                ],
                known_basis,
                event_seconds[
                    known
                ],
            )

            event_seconds[
                missing
            ] = np.rint(
                interpolated
            )

            missing_positions = positions[
                missing
            ]

            result.loc[
                missing_positions,
                "time_interpolated",
            ] = True
            result.loc[
                missing_positions,
                "time_interpolation_method",
            ] = method

        arrival_values = (
            result.iloc[
                positions
            ][
                "arrival_seconds"
            ]
            .astype(
                "Float64"
            )
            .to_numpy(
                dtype=float,
                na_value=np.nan,
            )
        )
        departure_values = (
            result.iloc[
                positions
            ][
                "departure_seconds"
            ]
            .astype(
                "Float64"
            )
            .to_numpy(
                dtype=float,
                na_value=np.nan,
            )
        )

        arrival_values = np.where(
            np.isfinite(
                arrival_values
            ),
            arrival_values,
            event_seconds,
        )
        departure_values = np.where(
            np.isfinite(
                departure_values
            ),
            departure_values,
            event_seconds,
        )

        result.loc[
            positions,
            "arrival_seconds",
        ] = pd.array(
            np.rint(
                arrival_values
            ),
            dtype="Int64",
        )
        result.loc[
            positions,
            "departure_seconds",
        ] = pd.array(
            np.rint(
                departure_values
            ),
            dtype="Int64",
        )

    return result


def _parse_gtfs_date_series(
    values: pd.Series,
    *,
    table_name: str,
    column: str,
) -> pd.Series:
    """Converte datas GTFS YYYYMMDD para datetime normalizado"""

    normalized = (
        values
        .astype(
            "string"
        )
        .str.strip()
    )

    empty = normalized.eq(
        ""
    )

    parsed = pd.to_datetime(
        normalized.mask(
            empty
        ),
        format="%Y%m%d",
        errors="coerce",
    )

    invalid = (
        ~empty
        & parsed.isna()
    )

    if invalid.any():
        sample = (
            normalized.loc[
                invalid
            ]
            .head(
                5
            )
            .tolist()
        )

        raise ValueError(
            f"{table_name}.{column} contém datas GTFS inválidas: {sample}"
        )

    return parsed


def _process_agency(
    agency: pd.DataFrame,
) -> pd.DataFrame:
    """Valida os dados básicos da operadora"""

    _require_columns(
        agency,
        "agency.txt",
        [
            "agency_name",
            "agency_url",
            "agency_timezone",
        ],
    )

    _require_nonempty(
        agency,
        "agency.txt",
        [
            "agency_name",
            "agency_timezone",
        ],
    )

    if "agency_id" in agency.columns:
        nonempty = agency[
            "agency_id"
        ].ne(
            ""
        )

        if nonempty.any():
            _require_unique(
                agency.loc[
                    nonempty
                ],
                "agency.txt",
                [
                    "agency_id",
                ],
            )

    return agency


def _process_stops(
    stops: pd.DataFrame,
    *,
    projected_crs: str,
) -> gpd.GeoDataFrame:
    """Valida as paradas e cria a camada espacial projetada"""

    _require_columns(
        stops,
        "stops.txt",
        [
            "stop_id",
            "stop_lat",
            "stop_lon",
        ],
    )
    _require_nonempty(
        stops,
        "stops.txt",
        [
            "stop_id",
            "stop_lat",
            "stop_lon",
        ],
    )
    _require_unique(
        stops,
        "stops.txt",
        [
            "stop_id",
        ],
    )

    _to_numeric(
        stops,
        "stops.txt",
        "stop_lat",
    )
    _to_numeric(
        stops,
        "stops.txt",
        "stop_lon",
    )

    invalid_lat = (
        stops[
            "stop_lat"
        ].lt(
            -90
        )
        | stops[
            "stop_lat"
        ].gt(
            90
        )
    )
    invalid_lon = (
        stops[
            "stop_lon"
        ].lt(
            -180
        )
        | stops[
            "stop_lon"
        ].gt(
            180
        )
    )

    if (
        invalid_lat.any()
        or invalid_lon.any()
    ):
        raise ValueError(
            "stops.txt possui coordenadas fora dos limites geográficos válidos"
        )

    geographic = gpd.GeoDataFrame(
        stops.copy(),
        geometry=gpd.points_from_xy(
            stops[
                "stop_lon"
            ].astype(
                float
            ),
            stops[
                "stop_lat"
            ].astype(
                float
            ),
        ),
        crs="EPSG:4326",
    )

    return geographic.to_crs(
        projected_crs
    )


def _process_routes(
    routes: pd.DataFrame,
) -> pd.DataFrame:
    """Valida as linhas do feed"""

    _require_columns(
        routes,
        "routes.txt",
        [
            "route_id",
            "route_type",
        ],
    )
    _require_nonempty(
        routes,
        "routes.txt",
        [
            "route_id",
            "route_type",
        ],
    )
    _require_unique(
        routes,
        "routes.txt",
        [
            "route_id",
        ],
    )

    _to_numeric(
        routes,
        "routes.txt",
        "route_type",
        integer=True,
    )

    return routes


def _process_trips(
    trips: pd.DataFrame,
) -> pd.DataFrame:
    """Valida as viagens programadas"""

    _require_columns(
        trips,
        "trips.txt",
        [
            "route_id",
            "service_id",
            "trip_id",
        ],
    )
    _require_nonempty(
        trips,
        "trips.txt",
        [
            "route_id",
            "service_id",
            "trip_id",
        ],
    )
    _require_unique(
        trips,
        "trips.txt",
        [
            "trip_id",
        ],
    )

    return trips


def _process_stop_times(
    stop_times: pd.DataFrame,
) -> pd.DataFrame:
    """Valida a sequência de paradas e prepara os horários de cada viagem"""

    _require_columns(
        stop_times,
        "stop_times.txt",
        [
            "trip_id",
            "stop_id",
            "stop_sequence",
        ],
    )
    _require_nonempty(
        stop_times,
        "stop_times.txt",
        [
            "trip_id",
            "stop_id",
            "stop_sequence",
        ],
    )
    _require_unique(
        stop_times,
        "stop_times.txt",
        [
            "trip_id",
            "stop_sequence",
        ],
    )

    _to_numeric(
        stop_times,
        "stop_times.txt",
        "stop_sequence",
        integer=True,
    )

    if (
        "shape_dist_traveled"
        in stop_times.columns
    ):
        _to_numeric(
            stop_times,
            "stop_times.txt",
            "shape_dist_traveled",
            nullable=True,
        )

    _add_time_seconds(
        stop_times,
        "arrival_time",
        "arrival_seconds",
    )
    _add_time_seconds(
        stop_times,
        "departure_time",
        "departure_seconds",
    )

    stop_times[
        "arrival_missing_raw"
    ] = stop_times[
        "arrival_seconds"
    ].isna()
    stop_times[
        "departure_missing_raw"
    ] = stop_times[
        "departure_seconds"
    ].isna()

    invalid_dwell = (
        stop_times[
            "arrival_seconds"
        ].notna()
        & stop_times[
            "departure_seconds"
        ].notna()
        & (
            stop_times[
                "departure_seconds"
            ]
            < stop_times[
                "arrival_seconds"
            ]
        )
    )

    if invalid_dwell.any():
        raise ValueError(
            "stop_times.txt possui departure_time anterior a arrival_time"
        )

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
    )

    stop_counts = ordered.groupby(
        "trip_id"
    ).size()

    invalid_trips = stop_counts.loc[
        stop_counts
        < 2
    ]

    if not invalid_trips.empty:
        raise ValueError(
            "stop_times.txt possui viagens com menos de duas paradas: "
            f"{invalid_trips.index.astype(str).tolist()[:5]}"
        )

    ordered = _interpolate_stop_time_events(
        ordered
    )

    invalid_dwell_after = (
        ordered[
            "departure_seconds"
        ]
        < ordered[
            "arrival_seconds"
        ]
    )

    if invalid_dwell_after.any():
        raise ValueError(
            "stop_times.txt possui departure_time anterior a arrival_time "
            "após o preenchimento temporal"
        )

    previous_departure = ordered.groupby(
        "trip_id"
    )[
        "departure_seconds"
    ].shift(
        1
    )

    invalid_sequence = (
        previous_departure.notna()
        & (
            ordered[
                "arrival_seconds"
            ]
            < previous_departure
        )
    )

    if invalid_sequence.any():
        raise ValueError(
            "stop_times.txt possui horários decrescentes dentro de uma viagem"
        )

    return ordered

def _process_calendar(
    calendar: pd.DataFrame,
) -> pd.DataFrame:
    """Valida o calendário semanal de operação"""

    _require_columns(
        calendar,
        "calendar.txt",
        [
            "service_id",
            *WEEKDAY_COLUMNS,
            "start_date",
            "end_date",
        ],
    )
    _require_nonempty(
        calendar,
        "calendar.txt",
        [
            "service_id",
            "start_date",
            "end_date",
        ],
    )
    _require_unique(
        calendar,
        "calendar.txt",
        [
            "service_id",
        ],
    )

    for column in WEEKDAY_COLUMNS:
        _to_numeric(
            calendar,
            "calendar.txt",
            column,
            integer=True,
        )

        invalid = ~calendar[
            column
        ].isin(
            [
                0,
                1,
            ]
        )

        if invalid.any():
            raise ValueError(
                f"calendar.txt.{column} aceita somente 0 ou 1"
            )

    calendar[
        "start_date"
    ] = _parse_gtfs_date_series(
        calendar[
            "start_date"
        ],
        table_name="calendar.txt",
        column="start_date",
    )
    calendar[
        "end_date"
    ] = _parse_gtfs_date_series(
        calendar[
            "end_date"
        ],
        table_name="calendar.txt",
        column="end_date",
    )

    invalid_range = (
        calendar[
            "end_date"
        ]
        < calendar[
            "start_date"
        ]
    )

    if invalid_range.any():
        raise ValueError(
            "calendar.txt possui end_date anterior a start_date"
        )

    return calendar


def _process_calendar_dates(
    calendar_dates: pd.DataFrame,
) -> pd.DataFrame:
    """Valida as exceções explícitas do calendário"""

    _require_columns(
        calendar_dates,
        "calendar_dates.txt",
        [
            "service_id",
            "date",
            "exception_type",
        ],
    )
    _require_nonempty(
        calendar_dates,
        "calendar_dates.txt",
        [
            "service_id",
            "date",
            "exception_type",
        ],
    )
    _require_unique(
        calendar_dates,
        "calendar_dates.txt",
        [
            "service_id",
            "date",
        ],
    )

    calendar_dates[
        "date"
    ] = _parse_gtfs_date_series(
        calendar_dates[
            "date"
        ],
        table_name="calendar_dates.txt",
        column="date",
    )

    _to_numeric(
        calendar_dates,
        "calendar_dates.txt",
        "exception_type",
        integer=True,
    )

    invalid = ~calendar_dates[
        "exception_type"
    ].isin(
        [
            1,
            2,
        ]
    )

    if invalid.any():
        raise ValueError(
            "calendar_dates.txt.exception_type aceita somente 1 ou 2"
        )

    return calendar_dates


def _build_service_dates(
    calendar: pd.DataFrame | None,
    calendar_dates: pd.DataFrame | None,
) -> pd.DataFrame:
    """Expande o calendário para uma linha por service_id e data ativa"""

    active: set[
        tuple[
            str,
            pd.Timestamp,
        ]
    ] = set()

    if calendar is not None:
        for row in calendar.itertuples(
            index=False
        ):
            date_range = pd.date_range(
                start=row.start_date,
                end=row.end_date,
                freq="D",
            )

            service_id = str(
                row.service_id
            )

            weekday_flags = {
                index: int(
                    getattr(
                        row,
                        column,
                    )
                )
                for index, column
                in enumerate(
                    WEEKDAY_COLUMNS
                )
            }

            for service_date in date_range:
                if weekday_flags[
                    service_date.weekday()
                ] == 1:
                    active.add(
                        (
                            service_id,
                            pd.Timestamp(
                                service_date
                            ).normalize(),
                        )
                    )

    if calendar_dates is not None:
        for row in calendar_dates.itertuples(
            index=False
        ):
            key = (
                str(
                    row.service_id
                ),
                pd.Timestamp(
                    row.date
                ).normalize(),
            )

            if int(
                row.exception_type
            ) == 1:
                active.add(
                    key
                )
            else:
                active.discard(
                    key
                )

    rows = [
        {
            "service_id": service_id,
            "service_date": service_date,
        }
        for service_id, service_date
        in sorted(
            active,
            key=lambda item: (
                item[
                    1
                ],
                item[
                    0
                ],
            ),
        )
    ]

    result = pd.DataFrame(
        rows,
        columns=[
            "service_id",
            "service_date",
        ],
    )

    if result.empty:
        raise ValueError(
            "O calendário processado não possui nenhuma data de serviço ativa"
        )

    return result


def _process_shapes(
    shapes: pd.DataFrame,
    *,
    projected_crs: str,
) -> gpd.GeoDataFrame:
    """Agrupa os pontos de shapes.txt em geometrias LineString projetadas"""

    _require_columns(
        shapes,
        "shapes.txt",
        [
            "shape_id",
            "shape_pt_lat",
            "shape_pt_lon",
            "shape_pt_sequence",
        ],
    )
    _require_nonempty(
        shapes,
        "shapes.txt",
        [
            "shape_id",
            "shape_pt_lat",
            "shape_pt_lon",
            "shape_pt_sequence",
        ],
    )

    _to_numeric(
        shapes,
        "shapes.txt",
        "shape_pt_lat",
    )
    _to_numeric(
        shapes,
        "shapes.txt",
        "shape_pt_lon",
    )
    _to_numeric(
        shapes,
        "shapes.txt",
        "shape_pt_sequence",
        integer=True,
    )

    _require_unique(
        shapes,
        "shapes.txt",
        [
            "shape_id",
            "shape_pt_sequence",
        ],
    )

    rows: list[
        dict
    ] = []

    for shape_id, group in shapes.groupby(
        "shape_id",
        sort=True,
    ):
        ordered = group.sort_values(
            "shape_pt_sequence"
        )

        coordinates = list(
            zip(
                ordered[
                    "shape_pt_lon"
                ].astype(
                    float
                ),
                ordered[
                    "shape_pt_lat"
                ].astype(
                    float
                ),
            )
        )

        if len(
            coordinates
        ) < 2:
            continue

        rows.append(
            {
                "shape_id": str(
                    shape_id
                ),
                "n_points": len(
                    coordinates
                ),
                "geometry": LineString(
                    coordinates
                ),
            }
        )

    if not rows:
        raise ValueError(
            "shapes.txt não possui shapes com pelo menos dois pontos"
        )

    geographic = gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs="EPSG:4326",
    )

    return geographic.to_crs(
        projected_crs
    )


def _refine_stop_times_with_shape_geometry(
    stop_times: pd.DataFrame,
    *,
    trips: pd.DataFrame,
    stops: gpd.GeoDataFrame,
    shapes: gpd.GeoDataFrame | None,
) -> pd.DataFrame:
    """Refina horários interpolados pela posição das paradas ao longo do shape"""

    result = stop_times.copy()

    if (
        shapes is None
        or "shape_id" not in trips.columns
    ):
        result[
            "shape_position_m"
        ] = pd.Series(
            pd.NA,
            index=result.index,
            dtype="Float64",
        )
        return result

    trip_shapes = (
        trips[
            [
                "trip_id",
                "shape_id",
            ]
        ]
        .copy()
    )

    trip_shapes[
        "shape_id"
    ] = (
        trip_shapes[
            "shape_id"
        ]
        .astype(
            "string"
        )
        .str.strip()
    )

    result = result.merge(
        trip_shapes,
        on="trip_id",
        how="left",
        validate="many_to_one",
    )

    stop_geometry = (
        stops[
            [
                "stop_id",
                "geometry",
            ]
        ]
        .drop_duplicates(
            subset="stop_id"
        )
        .set_index(
            "stop_id"
        )[
            "geometry"
        ]
        .to_dict()
    )

    shape_geometry = (
        shapes[
            [
                "shape_id",
                "geometry",
            ]
        ]
        .drop_duplicates(
            subset="shape_id"
        )
        .set_index(
            "shape_id"
        )[
            "geometry"
        ]
        .to_dict()
    )

    pairs = (
        result.loc[
            result[
                "shape_id"
            ]
            .notna()
            & result[
                "shape_id"
            ]
            .ne(
                ""
            ),
            [
                "shape_id",
                "stop_id",
            ],
        ]
        .drop_duplicates()
    )

    position_lookup: dict[
        tuple[
            str,
            str,
        ],
        float,
    ] = {}

    for row in pairs.itertuples(
        index=False
    ):
        shape_id = str(
            row.shape_id
        )
        stop_id = str(
            row.stop_id
        )

        line = shape_geometry.get(
            shape_id
        )
        point = stop_geometry.get(
            stop_id
        )

        if (
            line is None
            or point is None
            or line.is_empty
            or point.is_empty
        ):
            continue

        position_lookup[
            (
                shape_id,
                stop_id,
            )
        ] = float(
            line.project(
                point
            )
        )

    result[
        "shape_position_m"
    ] = pd.array(
        [
            position_lookup.get(
                (
                    str(
                        shape_id
                    ),
                    str(
                        stop_id
                    ),
                ),
                pd.NA,
            )
            if pd.notna(
                shape_id
            )
            and str(
                shape_id
            ).strip()
            else pd.NA
            for shape_id, stop_id
            in zip(
                result[
                    "shape_id"
                ],
                result[
                    "stop_id"
                ],
                strict=True,
            )
        ],
        dtype="Float64",
    )

    grouped_indices = result.groupby(
        "trip_id",
        sort=False,
    ).indices

    for _, positions in grouped_indices.items():
        positions = np.asarray(
            positions,
            dtype=int,
        )

        group = result.iloc[
            positions
        ]

        interpolation_mask = (
            group[
                "time_interpolated"
            ]
            .fillna(
                False
            )
            .to_numpy(
                dtype=bool
            )
        )

        if not interpolation_mask.any():
            continue

        shape_positions = (
            group[
                "shape_position_m"
            ]
            .astype(
                "Float64"
            )
            .to_numpy(
                dtype=float,
                na_value=np.nan,
            )
        )

        if not np.isfinite(
            shape_positions
        ).all():
            continue

        if np.any(
            np.diff(
                shape_positions
            )
            < -1e-6
        ):
            continue

        raw_anchor_mask = ~(
            group[
                "arrival_missing_raw"
            ].to_numpy(
                dtype=bool
            )
            & group[
                "departure_missing_raw"
            ].to_numpy(
                dtype=bool
            )
        )

        anchor_positions = shape_positions[
            raw_anchor_mask
        ]

        if (
            len(
                anchor_positions
            )
            < 2
            or np.any(
                np.diff(
                    anchor_positions
                )
                <= 0
            )
        ):
            continue

        anchor_seconds = (
            group[
                "departure_seconds"
            ]
            .where(
                raw_anchor_mask
            )
            .fillna(
                group[
                    "arrival_seconds"
                ]
                .where(
                    raw_anchor_mask
                )
            )
            .astype(
                "Float64"
            )
            .to_numpy(
                dtype=float,
                na_value=np.nan,
            )[
                raw_anchor_mask
            ]
        )

        if not np.isfinite(
            anchor_seconds
        ).all():
            continue

        target_positions = shape_positions[
            interpolation_mask
        ]

        interpolated = np.rint(
            np.interp(
                target_positions,
                anchor_positions,
                anchor_seconds,
            )
        ).astype(
            int
        )

        target_indices = positions[
            interpolation_mask
        ]

        result.loc[
            target_indices,
            "arrival_seconds",
        ] = pd.array(
            interpolated,
            dtype="Int64",
        )
        result.loc[
            target_indices,
            "departure_seconds",
        ] = pd.array(
            interpolated,
            dtype="Int64",
        )
        result.loc[
            target_indices,
            "time_interpolation_method",
        ] = "shape_geometry"

    return result


def _allocate_positive_intervals(
    *,
    total_seconds: int,
    weights: np.ndarray,
    minimum_interval_s: int,
) -> np.ndarray | None:
    """Distribui segundos inteiros preservando um mínimo por intervalo"""

    if minimum_interval_s < 0:
        raise ValueError(
            "minimum_interval_s não pode ser negativo"
        )

    weights = np.asarray(
        weights,
        dtype=float,
    )

    n_intervals = len(
        weights
    )

    if n_intervals == 0:
        return np.asarray(
            [],
            dtype=int,
        )

    minimum_total = (
        n_intervals
        * minimum_interval_s
    )

    if total_seconds < minimum_total:
        return None

    valid_weights = (
        np.isfinite(
            weights
        )
        & (
            weights
            > 0
        )
    )

    if not valid_weights.all():
        weights = np.ones(
            n_intervals,
            dtype=float,
        )

    remaining = (
        int(
            total_seconds
        )
        - minimum_total
    )

    weighted = (
        weights
        / weights.sum()
        * remaining
    )

    base = (
        np.floor(
            weighted
        ).astype(
            int
        )
        + minimum_interval_s
    )

    remainder = (
        int(
            total_seconds
        )
        - int(
            base.sum()
        )
    )

    if remainder > 0:
        fractions = (
            weighted
            - np.floor(
                weighted
            )
        )
        order = np.argsort(
            -fractions,
            kind="stable",
        )
        base[
            order[
                :remainder
            ]
        ] += 1

    return base


def _regularize_interpolated_stop_times(
    stop_times: pd.DataFrame,
    *,
    minimum_interval_s: int,
) -> pd.DataFrame:
    """Reconstrói horários intermediários preservando os pontos temporais originais"""

    result = stop_times.copy()

    result[
        "time_regularized"
    ] = False
    result[
        "time_regularization_method"
    ] = "not_applied"
    result[
        "temporal_regularization_feasible"
    ] = True

    grouped_indices = result.groupby(
        "trip_id",
        sort=False,
    ).indices

    for _, positions in grouped_indices.items():
        positions = np.asarray(
            positions,
            dtype=int,
        )

        group = result.iloc[
            positions
        ]

        raw_anchor_mask = ~(
            group[
                "arrival_missing_raw"
            ].to_numpy(
                dtype=bool
            )
            & group[
                "departure_missing_raw"
            ].to_numpy(
                dtype=bool
            )
        )

        anchor_indices = np.flatnonzero(
            raw_anchor_mask
        )

        if len(
            anchor_indices
        ) < 2:
            result.loc[
                positions,
                "temporal_regularization_feasible",
            ] = False
            continue

        trip_feasible = True

        for start_local, end_local in zip(
            anchor_indices[
                :-1
            ],
            anchor_indices[
                1:
            ],
            strict=True,
        ):
            start_row = group.iloc[
                int(
                    start_local
                )
            ]
            end_row = group.iloc[
                int(
                    end_local
                )
            ]

            start_seconds = (
                start_row[
                    "departure_seconds"
                ]
                if pd.notna(
                    start_row[
                        "departure_seconds"
                    ]
                )
                else start_row[
                    "arrival_seconds"
                ]
            )
            end_seconds = (
                end_row[
                    "arrival_seconds"
                ]
                if pd.notna(
                    end_row[
                        "arrival_seconds"
                    ]
                )
                else end_row[
                    "departure_seconds"
                ]
            )

            if (
                pd.isna(
                    start_seconds
                )
                or pd.isna(
                    end_seconds
                )
            ):
                trip_feasible = False
                continue

            total_seconds = (
                int(
                    end_seconds
                )
                - int(
                    start_seconds
                )
            )
            n_intervals = (
                int(
                    end_local
                )
                - int(
                    start_local
                )
            )

            if n_intervals <= 0:
                continue

            span = group.iloc[
                int(
                    start_local
                ):
                int(
                    end_local
                )
                + 1
            ]

            shape_positions = (
                span[
                    "shape_position_m"
                ]
                .astype(
                    "Float64"
                )
                .to_numpy(
                    dtype=float,
                    na_value=np.nan,
                )
                if "shape_position_m"
                in span.columns
                else np.full(
                    n_intervals
                    + 1,
                    np.nan,
                    dtype=float,
                )
            )

            shape_differences = np.diff(
                shape_positions
            )

            use_shape = bool(
                np.isfinite(
                    shape_positions
                ).all()
                and (
                    shape_differences
                    > 1e-6
                ).all()
            )

            weights = (
                shape_differences
                if use_shape
                else np.ones(
                    n_intervals,
                    dtype=float,
                )
            )
            method = (
                "shape_geometry_positive"
                if use_shape
                else "stop_sequence_positive"
            )

            allocated = _allocate_positive_intervals(
                total_seconds=total_seconds,
                weights=weights,
                minimum_interval_s=minimum_interval_s,
            )

            if allocated is None:
                trip_feasible = False
                continue

            if n_intervals == 1:
                continue

            cumulative = (
                int(
                    start_seconds
                )
                + np.cumsum(
                    allocated
                )[
                    :-1
                ]
            )

            target_local = np.arange(
                int(
                    start_local
                )
                + 1,
                int(
                    end_local
                ),
                dtype=int,
            )
            target_positions = positions[
                target_local
            ]

            if len(
                target_positions
            ) != len(
                cumulative
            ):
                raise RuntimeError(
                    "A reconstrução temporal produziu tamanhos incompatíveis"
                )

            result.loc[
                target_positions,
                "arrival_seconds",
            ] = pd.array(
                cumulative,
                dtype="Int64",
            )
            result.loc[
                target_positions,
                "departure_seconds",
            ] = pd.array(
                cumulative,
                dtype="Int64",
            )
            result.loc[
                target_positions,
                "time_regularized",
            ] = True
            result.loc[
                target_positions,
                "time_regularization_method",
            ] = method

        if not trip_feasible:
            result.loc[
                positions,
                "temporal_regularization_feasible",
            ] = False

    previous_departure = result.groupby(
        "trip_id"
    )[
        "departure_seconds"
    ].shift(
        1
    )

    invalid_sequence = (
        previous_departure.notna()
        & result[
            "arrival_seconds"
        ].notna()
        & (
            result[
                "arrival_seconds"
            ]
            < previous_departure
        )
    )

    if invalid_sequence.any():
        raise ValueError(
            "A reconstrução temporal produziu horários decrescentes"
        )

    return result


def _process_frequencies(
    frequencies: pd.DataFrame,
) -> pd.DataFrame:
    """Prepara frequências quando o feed fornece viagens por headway"""

    _require_columns(
        frequencies,
        "frequencies.txt",
        [
            "trip_id",
            "start_time",
            "end_time",
            "headway_secs",
        ],
    )

    _add_time_seconds(
        frequencies,
        "start_time",
        "start_seconds",
    )
    _add_time_seconds(
        frequencies,
        "end_time",
        "end_seconds",
    )
    _to_numeric(
        frequencies,
        "frequencies.txt",
        "headway_secs",
        integer=True,
    )

    invalid_headway = (
        frequencies[
            "headway_secs"
        ]
        <= 0
    )

    if invalid_headway.any():
        raise ValueError(
            "frequencies.txt possui headway_secs menor ou igual a zero"
        )

    invalid_window = (
        frequencies[
            "start_seconds"
        ].notna()
        & frequencies[
            "end_seconds"
        ].notna()
        & (
            frequencies[
                "end_seconds"
            ]
            <= frequencies[
                "start_seconds"
            ]
        )
    )

    if invalid_window.any():
        raise ValueError(
            "frequencies.txt possui end_time menor ou igual a start_time"
        )

    return frequencies


def _process_transfers(
    transfers: pd.DataFrame,
) -> pd.DataFrame:
    """Preserva e tipa os campos principais de transferências"""

    if "transfer_type" in transfers.columns:
        _to_numeric(
            transfers,
            "transfers.txt",
            "transfer_type",
            integer=True,
            nullable=True,
        )

    if "min_transfer_time" in transfers.columns:
        _to_numeric(
            transfers,
            "transfers.txt",
            "min_transfer_time",
            integer=True,
            nullable=True,
        )

    return transfers


def _validate_foreign_keys(
    *,
    stops: gpd.GeoDataFrame,
    routes: pd.DataFrame,
    trips: pd.DataFrame,
    stop_times: pd.DataFrame,
    service_dates: pd.DataFrame,
    shapes: gpd.GeoDataFrame | None,
) -> None:
    """Valida as referências usadas no futuro roteamento"""

    missing_routes = (
        set(
            trips[
                "route_id"
            ]
        )
        - set(
            routes[
                "route_id"
            ]
        )
    )

    if missing_routes:
        raise ValueError(
            "trips.txt referencia route_id ausente em routes.txt: "
            f"{sorted(list(missing_routes))[:5]}"
        )

    missing_services = (
        set(
            trips[
                "service_id"
            ]
        )
        - set(
            service_dates[
                "service_id"
            ]
        )
    )

    if missing_services:
        raise ValueError(
            "trips.txt referencia service_id sem data ativa processada: "
            f"{sorted(list(missing_services))[:5]}"
        )

    missing_trips = (
        set(
            stop_times[
                "trip_id"
            ]
        )
        - set(
            trips[
                "trip_id"
            ]
        )
    )

    if missing_trips:
        raise ValueError(
            "stop_times.txt referencia trip_id ausente em trips.txt: "
            f"{sorted(list(missing_trips))[:5]}"
        )

    missing_stops = (
        set(
            stop_times[
                "stop_id"
            ]
        )
        - set(
            stops[
                "stop_id"
            ]
        )
    )

    if missing_stops:
        raise ValueError(
            "stop_times.txt referencia stop_id ausente em stops.txt: "
            f"{sorted(list(missing_stops))[:5]}"
        )

    if (
        "shape_id" in trips.columns
        and trips[
            "shape_id"
        ].ne(
            ""
        ).any()
    ):
        if shapes is None:
            raise ValueError(
                "trips.txt referencia shape_id mas shapes.txt não está disponível"
            )

        referenced_shapes = set(
            trips.loc[
                trips[
                    "shape_id"
                ].ne(
                    ""
                ),
                "shape_id",
            ]
        )

        missing_shapes = (
            referenced_shapes
            - set(
                shapes[
                    "shape_id"
                ]
            )
        )

        if missing_shapes:
            raise ValueError(
                "trips.txt referencia shape_id ausente em shapes.txt: "
                f"{sorted(list(missing_shapes))[:5]}"
            )


def _inventory_row(
    filename: str,
    frame: pd.DataFrame | gpd.GeoDataFrame | None,
    *,
    present: bool,
) -> dict:
    """Cria uma linha de inventário para a tabela processada"""

    return {
        "source_file": filename,
        "present": bool(
            present
        ),
        "rows": (
            int(
                len(
                    frame
                )
            )
            if frame is not None
            else 0
        ),
        "columns": (
            "|".join(
                str(
                    column
                )
                for column in frame.columns
                if column != "geometry"
            )
            if frame is not None
            else ""
        ),
    }


def _write_parquet(
    frame: pd.DataFrame,
    output_dir: Path,
    key: str,
) -> Path:
    """Salva uma tabela processada em Parquet"""

    path = (
        output_dir
        / PROCESSED_TABLE_FILES[
            key
        ]
    )

    frame.to_parquet(
        path,
        index=False,
    )

    return path


def process_gtfs_zip(
    *,
    zip_path: Path,
    output_dir: Path,
    projected_crs: str,
    temporal_reconstruction_enabled: bool = True,
    minimum_interval_s: int = 1,
) -> dict:
    """Processa um ZIP GTFS e retorna o resumo da versão processada"""

    zip_path = Path(
        zip_path
    )
    output_dir = Path(
        output_dir
    )

    if not zip_path.exists():
        raise FileNotFoundError(
            f"Arquivo GTFS não encontrado: {zip_path}"
        )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with zipfile.ZipFile(
        zip_path,
        "r",
    ) as archive:
        members = _member_map(
            archive
        )

        missing_core = [
            filename
            for filename in CORE_FILES
            if filename not in members
        ]

        if missing_core:
            raise ValueError(
                "O GTFS não possui os arquivos necessários para o piloto: "
                f"{missing_core}"
            )

        if (
            "calendar.txt" not in members
            and "calendar_dates.txt" not in members
        ):
            raise ValueError(
                "O GTFS precisa fornecer calendar.txt, calendar_dates.txt ou ambos"
            )

        raw_agency = _read_table(
            archive,
            members,
            "agency.txt",
        )
        raw_stops = _read_table(
            archive,
            members,
            "stops.txt",
        )
        raw_routes = _read_table(
            archive,
            members,
            "routes.txt",
        )
        raw_trips = _read_table(
            archive,
            members,
            "trips.txt",
        )
        raw_stop_times = _read_table(
            archive,
            members,
            "stop_times.txt",
        )

        raw_calendar = (
            _read_table(
                archive,
                members,
                "calendar.txt",
            )
            if "calendar.txt" in members
            else None
        )
        raw_calendar_dates = (
            _read_table(
                archive,
                members,
                "calendar_dates.txt",
            )
            if "calendar_dates.txt" in members
            else None
        )
        raw_shapes = (
            _read_table(
                archive,
                members,
                "shapes.txt",
            )
            if "shapes.txt" in members
            else None
        )
        raw_frequencies = (
            _read_table(
                archive,
                members,
                "frequencies.txt",
            )
            if "frequencies.txt" in members
            else None
        )
        raw_transfers = (
            _read_table(
                archive,
                members,
                "transfers.txt",
            )
            if "transfers.txt" in members
            else None
        )
        raw_feed_info = (
            _read_table(
                archive,
                members,
                "feed_info.txt",
            )
            if "feed_info.txt" in members
            else None
        )

    agency = _process_agency(
        raw_agency
    )
    stops = _process_stops(
        raw_stops,
        projected_crs=projected_crs,
    )
    routes = _process_routes(
        raw_routes
    )
    trips = _process_trips(
        raw_trips
    )
    stop_times = _process_stop_times(
        raw_stop_times
    )

    calendar = (
        _process_calendar(
            raw_calendar
        )
        if raw_calendar is not None
        else None
    )
    calendar_dates = (
        _process_calendar_dates(
            raw_calendar_dates
        )
        if raw_calendar_dates is not None
        else None
    )

    service_dates = _build_service_dates(
        calendar,
        calendar_dates,
    )

    shapes = (
        _process_shapes(
            raw_shapes,
            projected_crs=projected_crs,
        )
        if raw_shapes is not None
        else None
    )

    stop_times = _refine_stop_times_with_shape_geometry(
        stop_times,
        trips=trips,
        stops=stops,
        shapes=shapes,
    )

    if temporal_reconstruction_enabled:
        stop_times = _regularize_interpolated_stop_times(
            stop_times,
            minimum_interval_s=minimum_interval_s,
        )
    else:
        stop_times[
            "time_regularized"
        ] = False
        stop_times[
            "time_regularization_method"
        ] = "disabled"
        stop_times[
            "temporal_regularization_feasible"
        ] = True

    frequencies = (
        _process_frequencies(
            raw_frequencies
        )
        if raw_frequencies is not None
        else None
    )
    transfers = (
        _process_transfers(
            raw_transfers
        )
        if raw_transfers is not None
        else None
    )
    feed_info = (
        raw_feed_info.copy()
        if raw_feed_info is not None
        else None
    )

    _validate_foreign_keys(
        stops=stops,
        routes=routes,
        trips=trips,
        stop_times=stop_times,
        service_dates=service_dates,
        shapes=shapes,
    )

    processed_paths = [
        output_dir
        / filename
        for filename in (
            *PROCESSED_TABLE_FILES.values(),
            STOPS_GPKG,
            SHAPES_GPKG,
            SUMMARY_CSV,
            INVENTORY_CSV,
        )
    ]

    for processed_path in processed_paths:
        if processed_path.exists():
            processed_path.unlink()

    _write_parquet(
        agency,
        output_dir,
        "agency",
    )
    _write_parquet(
        routes,
        output_dir,
        "routes",
    )
    _write_parquet(
        trips,
        output_dir,
        "trips",
    )
    _write_parquet(
        stop_times,
        output_dir,
        "stop_times",
    )
    _write_parquet(
        service_dates,
        output_dir,
        "service_dates",
    )

    if calendar is not None:
        _write_parquet(
            calendar,
            output_dir,
            "calendar",
        )

    if calendar_dates is not None:
        _write_parquet(
            calendar_dates,
            output_dir,
            "calendar_dates",
        )

    if frequencies is not None:
        _write_parquet(
            frequencies,
            output_dir,
            "frequencies",
        )

    if transfers is not None:
        _write_parquet(
            transfers,
            output_dir,
            "transfers",
        )

    if feed_info is not None:
        _write_parquet(
            feed_info,
            output_dir,
            "feed_info",
        )

    stops_path = (
        output_dir
        / STOPS_GPKG
    )

    if stops_path.exists():
        stops_path.unlink()

    stops.to_file(
        stops_path,
        layer="stops_processed",
        driver="GPKG",
        engine="pyogrio",
    )

    if shapes is not None:
        shapes_path = (
            output_dir
            / SHAPES_GPKG
        )

        if shapes_path.exists():
            shapes_path.unlink()

        shapes.to_file(
            shapes_path,
            layer="shapes_processed",
            driver="GPKG",
            engine="pyogrio",
        )

    inventory_rows = [
        _inventory_row(
            "agency.txt",
            agency,
            present=True,
        ),
        _inventory_row(
            "stops.txt",
            stops,
            present=True,
        ),
        _inventory_row(
            "routes.txt",
            routes,
            present=True,
        ),
        _inventory_row(
            "trips.txt",
            trips,
            present=True,
        ),
        _inventory_row(
            "stop_times.txt",
            stop_times,
            present=True,
        ),
        _inventory_row(
            "calendar.txt",
            calendar,
            present=calendar is not None,
        ),
        _inventory_row(
            "calendar_dates.txt",
            calendar_dates,
            present=calendar_dates is not None,
        ),
        _inventory_row(
            "shapes.txt",
            shapes,
            present=shapes is not None,
        ),
        _inventory_row(
            "frequencies.txt",
            frequencies,
            present=frequencies is not None,
        ),
        _inventory_row(
            "transfers.txt",
            transfers,
            present=transfers is not None,
        ),
        _inventory_row(
            "feed_info.txt",
            feed_info,
            present=feed_info is not None,
        ),
    ]

    inventory = pd.DataFrame(
        inventory_rows
    )

    inventory.to_csv(
        output_dir
        / INVENTORY_CSV,
        index=False,
        encoding="utf-8",
    )

    route_types = (
        routes[
            "route_type"
        ]
        .dropna()
        .astype(
            int
        )
        .value_counts()
        .sort_index()
    )

    service_start = service_dates[
        "service_date"
    ].min()
    service_end = service_dates[
        "service_date"
    ].max()

    summary = {
        "processed_at_utc": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        ),
        "source_zip": zip_path.name,
        "projected_crs": projected_crs,
        "n_agencies": int(
            len(
                agency
            )
        ),
        "n_stops": int(
            len(
                stops
            )
        ),
        "n_routes": int(
            len(
                routes
            )
        ),
        "n_trips": int(
            len(
                trips
            )
        ),
        "n_stop_times": int(
            len(
                stop_times
            )
        ),
        "n_service_ids": int(
            service_dates[
                "service_id"
            ].nunique()
        ),
        "n_service_dates": int(
            len(
                service_dates
            )
        ),
        "service_start_date": (
            pd.Timestamp(
                service_start
            )
            .date()
            .isoformat()
        ),
        "service_end_date": (
            pd.Timestamp(
                service_end
            )
            .date()
            .isoformat()
        ),
        "service_period_expired_at_processing": bool(
            pd.Timestamp(
                service_end
            ).date()
            < datetime.now(
                timezone.utc
            ).date()
        ),
        "n_shapes": (
            int(
                len(
                    shapes
                )
            )
            if shapes is not None
            else 0
        ),
        "n_frequencies": (
            int(
                len(
                    frequencies
                )
            )
            if frequencies is not None
            else 0
        ),
        "n_transfers": (
            int(
                len(
                    transfers
                )
            )
            if transfers is not None
            else 0
        ),
        "route_types": (
            "|".join(
                f"{route_type}:{count}"
                for route_type, count
                in route_types.items()
            )
        ),
        "stop_times_missing_arrival_raw": int(
            stop_times[
                "arrival_missing_raw"
            ].sum()
        ),
        "stop_times_missing_departure_raw": int(
            stop_times[
                "departure_missing_raw"
            ].sum()
        ),
        "stop_times_interpolated": int(
            stop_times[
                "time_interpolated"
            ].sum()
        ),
        "stop_times_interpolated_shape_distance": int(
            (
                stop_times[
                    "time_interpolation_method"
                ]
                == "shape_dist_traveled"
            ).sum()
        ),
        "stop_times_interpolated_shape_geometry": int(
            (
                stop_times[
                    "time_interpolation_method"
                ]
                == "shape_geometry"
            ).sum()
        ),
        "stop_times_interpolated_stop_sequence": int(
            (
                stop_times[
                    "time_interpolation_method"
                ]
                == "stop_sequence"
            ).sum()
        ),
        "stop_times_filled_from_pair": int(
            stop_times[
                "time_filled_from_pair"
            ].sum()
        ),
        "stop_times_regularized": int(
            stop_times[
                "time_regularized"
            ].sum()
        ),
        "stop_times_regularized_shape_geometry": int(
            (
                stop_times[
                    "time_regularization_method"
                ]
                == "shape_geometry_positive"
            ).sum()
        ),
        "stop_times_regularized_stop_sequence": int(
            (
                stop_times[
                    "time_regularization_method"
                ]
                == "stop_sequence_positive"
            ).sum()
        ),
        "trips_temporal_regularization_infeasible": int(
            stop_times.loc[
                ~stop_times[
                    "temporal_regularization_feasible"
                ].astype(
                    bool
                ),
                "trip_id",
            ].nunique()
        ),
        "stop_times_missing_arrival_processed": int(
            stop_times[
                "arrival_seconds"
            ].isna().sum()
        ),
        "stop_times_missing_departure_processed": int(
            stop_times[
                "departure_seconds"
            ].isna().sum()
        ),
        "mode_scope": "bus_gtfs_eptc",
    }

    pd.DataFrame(
        [
            summary
        ]
    ).to_csv(
        output_dir
        / SUMMARY_CSV,
        index=False,
        encoding="utf-8",
    )

    return summary


def _format_int_pt(
    value,
) -> str:
    """Formata números inteiros com separador de milhar no padrão brasileiro"""

    return f"{int(value):,}".replace(
        ",",
        ".",
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

    percentage = (
        100.0
        * float(
            numerator
        )
        / denominator_value
    )

    return (
        f"{percentage:.1f}%"
        .replace(
            ".",
            ",",
        )
    )


def _format_date_pt(
    value,
) -> str:
    """Formata uma data ISO no padrão dia/mês/ano"""

    return pd.Timestamp(
        value
    ).strftime(
        "%d/%m/%Y"
    )


def _format_route_types(
    value: str,
) -> str:
    """Formata os tipos de rota GTFS com quantidade e unidade"""

    if not value:
        return "não informado"

    labels = {
        0: "bonde ou VLT",
        1: "metrô",
        2: "trem",
        3: "ônibus",
        4: "balsa",
        5: "bonde por cabo",
        6: "teleférico",
        7: "funicular",
        11: "trólebus",
        12: "monotrilho",
    }

    formatted: list[
        str
    ] = []

    for item in str(
        value
    ).split(
        "|"
    ):
        route_type, count = item.split(
            ":",
            maxsplit=1,
        )
        route_type_int = int(
            route_type
        )
        label = labels.get(
            route_type_int,
            "tipo não classificado",
        )

        formatted.append(
            f"{route_type_int} ({label}): "
            f"{_format_int_pt(count)} rotas"
        )

    return "; ".join(
        formatted
    )


def process_configured_gtfs() -> dict:
    """Processa o GTFS definido no config.json"""

    config = _load_config()
    gtfs_config = config[
        "transit"
    ][
        "gtfs"
    ]

    data_dir = (
        PROJECT_ROOT
        / gtfs_config[
            "data_dir"
        ]
    )
    zip_path = (
        data_dir
        / gtfs_config[
            "zip_file"
        ]
    )
    projected_crs = str(
        config[
            "study_area"
        ][
            "crs"
        ]
    )

    print(
        "\n"
        + "="
        * 72
    )
    print(
        "PROCESSAMENTO DO GTFS"
    )
    print(
        "="
        * 72
    )
    print(
        "Arquivo de origem: "
        f"{zip_path}"
    )

    reconstruction_config = gtfs_config.get(
        "temporal_reconstruction",
        {}
    )
    reconstruction_enabled = bool(
        reconstruction_config.get(
            "enabled",
            True,
        )
    )
    minimum_interval_s = int(
        reconstruction_config.get(
            "minimum_interval_s",
            1,
        )
    )

    summary = process_gtfs_zip(
        zip_path=zip_path,
        output_dir=data_dir,
        projected_crs=projected_crs,
        temporal_reconstruction_enabled=reconstruction_enabled,
        minimum_interval_s=minimum_interval_s,
    )

    service_start = pd.Timestamp(
        summary[
            "service_start_date"
        ]
    )
    service_end = pd.Timestamp(
        summary[
            "service_end_date"
        ]
    )
    service_days = (
        service_end
        - service_start
    ).days + 1

    n_stop_times = int(
        summary[
            "n_stop_times"
        ]
    )
    n_interpolated = int(
        summary[
            "stop_times_interpolated"
        ]
    )

    print(
        "\nResumo da oferta GTFS"
    )
    print(
        f"  Paradas: {_format_int_pt(summary['n_stops'])} unidades"
    )
    print(
        f"  Rotas: {_format_int_pt(summary['n_routes'])} unidades"
    )
    print(
        f"  Viagens programadas: {_format_int_pt(summary['n_trips'])} viagens"
    )
    print(
        "  Registros em stop_times: "
        f"{_format_int_pt(n_stop_times)} registros de parada"
    )
    print(
        f"  Shapes: {_format_int_pt(summary['n_shapes'])} geometrias"
    )
    print(
        "  Registros em frequencies: "
        f"{_format_int_pt(summary['n_frequencies'])} registros"
    )
    print(
        "  Registros em transfers: "
        f"{_format_int_pt(summary['n_transfers'])} registros"
    )
    print(
        "  Tipos de rota: "
        f"{_format_route_types(summary['route_types'])}"
    )

    print(
        "\nPeríodo de serviço"
    )
    print(
        "  Início: "
        f"{_format_date_pt(summary['service_start_date'])}"
    )
    print(
        "  Fim: "
        f"{_format_date_pt(summary['service_end_date'])}"
    )
    print(
        f"  Duração do período: {_format_int_pt(service_days)} dias"
    )

    print(
        "\nQualidade e preenchimento dos horários"
    )
    print(
        "  Chegadas ausentes no GTFS original: "
        f"{_format_int_pt(summary['stop_times_missing_arrival_raw'])} "
        "registros de parada "
        f"({_format_percentage_pt(summary['stop_times_missing_arrival_raw'], n_stop_times)})"
    )
    print(
        "  Partidas ausentes no GTFS original: "
        f"{_format_int_pt(summary['stop_times_missing_departure_raw'])} "
        "registros de parada "
        f"({_format_percentage_pt(summary['stop_times_missing_departure_raw'], n_stop_times)})"
    )
    print(
        "  Horários interpolados: "
        f"{_format_int_pt(n_interpolated)} registros de parada "
        f"({_format_percentage_pt(n_interpolated, n_stop_times)})"
    )
    print(
        "    por shape_dist_traveled: "
        f"{_format_int_pt(summary['stop_times_interpolated_shape_distance'])} "
        "registros "
        f"({_format_percentage_pt(summary['stop_times_interpolated_shape_distance'], n_interpolated)})"
    )
    print(
        "    pela geometria do shape: "
        f"{_format_int_pt(summary['stop_times_interpolated_shape_geometry'])} "
        "registros "
        f"({_format_percentage_pt(summary['stop_times_interpolated_shape_geometry'], n_interpolated)})"
    )
    print(
        "    por stop_sequence: "
        f"{_format_int_pt(summary['stop_times_interpolated_stop_sequence'])} "
        "registros "
        f"({_format_percentage_pt(summary['stop_times_interpolated_stop_sequence'], n_interpolated)})"
    )
    print(
        "  Horários preenchidos pelo par chegada/partida: "
        f"{_format_int_pt(summary['stop_times_filled_from_pair'])} registros"
    )
    print(
        "  Horários intermediários regularizados: "
        f"{_format_int_pt(summary['stop_times_regularized'])} registros"
    )
    print(
        "    pela geometria do shape com intervalo positivo: "
        f"{_format_int_pt(summary['stop_times_regularized_shape_geometry'])} registros"
    )
    print(
        "    por stop_sequence com intervalo positivo: "
        f"{_format_int_pt(summary['stop_times_regularized_stop_sequence'])} registros"
    )
    print(
        "  Viagens sem alocação temporal positiva possível: "
        f"{_format_int_pt(summary['trips_temporal_regularization_infeasible'])} viagens"
    )
    print(
        "  Chegadas ausentes após processamento: "
        f"{_format_int_pt(summary['stop_times_missing_arrival_processed'])} "
        "registros de parada"
    )
    print(
        "  Partidas ausentes após processamento: "
        f"{_format_int_pt(summary['stop_times_missing_departure_processed'])} "
        "registros de parada"
    )

    if summary[
        "service_period_expired_at_processing"
    ]:
        print(
            "\nAVISO"
        )
        print(
            "  O período de serviço termina antes da data de processamento"
        )
        print(
            "  O GTFS é tratado como referência histórica da oferta de ônibus"
        )

    print(
        "\nSaída"
    )
    print(
        "  CRS dos dados espaciais processados: "
        f"{summary['projected_crs']}"
    )
    print(
        "  Diretório dos produtos processados: "
        f"{data_dir}"
    )

    return summary


if __name__ == "__main__":
    process_configured_gtfs()
