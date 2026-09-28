"""Executa um diagnóstico amostral do roteamento temporal por ônibus

Usa origens residenciais e destinos CNEFE já preparados com node_walk
Seleciona uma amostra reprodutível de pares origem-destino
Aplica a data de serviço representativa construída a partir do GTFS
Resume cobertura, tempos, distâncias de acesso e quantidade de transferências
Salva os resultados em outputs/pilot/transit_routing_diagnostics.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.network.multimodal import load_mode_graphs
from src.transit.routeTransit import (
    ROUTE_OK,
    TransitRouter,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "pilot"


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


def _format_time_hhmm(
    seconds: int,
) -> str:
    """Formata segundos desde o início do dia de serviço em HH:MM"""

    hours = int(
        seconds
    ) // 3600
    minutes = (
        int(
            seconds
        )
        % 3600
    ) // 60

    return f"{hours:02d}:{minutes:02d}"


def _load_representative_service_date(
    *,
    data_dir: Path,
    summary_file: str,
) -> str:
    """Lê a data de serviço representativa calculada na etapa anterior"""

    path = (
        data_dir
        / summary_file
    )

    if not path.exists():
        raise FileNotFoundError(
            "Resumo da rede de transporte coletivo não encontrado: "
            f"{path}"
        )

    summary = pd.read_csv(
        path
    )

    if (
        summary.empty
        or "representative_service_date"
        not in summary.columns
    ):
        raise ValueError(
            "transit_network_summary.csv não possui "
            "representative_service_date"
        )

    return str(
        summary.iloc[
            0
        ][
            "representative_service_date"
        ]
    )


def _prepare_od_sample(
    *,
    origins: gpd.GeoDataFrame,
    destinations: gpd.GeoDataFrame,
    sample_size: int,
    seed: int,
) -> pd.DataFrame:
    """Seleciona pares origem-destino válidos para o diagnóstico"""

    if sample_size <= 0:
        raise ValueError(
            "sample_size precisa ser maior que zero"
        )

    required_origin = {
        "origin_id",
        "node_walk",
    }
    required_destination = {
        "destination_id",
        "node_walk",
    }

    missing_origin = (
        required_origin
        - set(
            origins.columns
        )
    )
    missing_destination = (
        required_destination
        - set(
            destinations.columns
        )
    )

    if missing_origin:
        raise ValueError(
            "A base de origens não possui: "
            f"{sorted(missing_origin)}"
        )

    if missing_destination:
        raise ValueError(
            "A base de destinos não possui: "
            f"{sorted(missing_destination)}"
        )

    valid_origins = origins.dropna(
        subset=[
            "origin_id",
            "node_walk",
        ]
    ).copy()
    valid_destinations = destinations.dropna(
        subset=[
            "destination_id",
            "node_walk",
        ]
    ).copy()

    if valid_origins.empty:
        raise ValueError(
            "A base de origens não possui node_walk válido"
        )

    if valid_destinations.empty:
        raise ValueError(
            "A base de destinos não possui node_walk válido"
        )

    rng = np.random.default_rng(
        seed
    )

    origin_indices = rng.integers(
        0,
        len(
            valid_origins
        ),
        size=sample_size,
    )
    destination_indices = rng.integers(
        0,
        len(
            valid_destinations
        ),
        size=sample_size,
    )

    rows = []

    for sample_index, (
        origin_index,
        destination_index,
    ) in enumerate(
        zip(
            origin_indices,
            destination_indices,
            strict=True,
        ),
        start=1,
    ):
        origin = valid_origins.iloc[
            int(
                origin_index
            )
        ]
        destination = valid_destinations.iloc[
            int(
                destination_index
            )
        ]

        rows.append(
            {
                "sample_id": sample_index,
                "origin_id": origin[
                    "origin_id"
                ],
                "destination_id": destination[
                    "destination_id"
                ],
                "origin_walk_node": int(
                    origin[
                        "node_walk"
                    ]
                ),
                "destination_walk_node": int(
                    destination[
                        "node_walk"
                    ]
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def _result_row(
    *,
    pair,
    result,
) -> dict:
    """Converte o resultado de uma consulta de trânsito em uma linha tabular"""

    return {
        "sample_id": pair.sample_id,
        "origin_id": pair.origin_id,
        "destination_id": pair.destination_id,
        "origin_walk_node": pair.origin_walk_node,
        "destination_walk_node": pair.destination_walk_node,
        "status": result.status,
        "service_date": result.service_date,
        "departure_time_s": result.departure_time_s,
        "arrival_time_s": result.arrival_time_s,
        "total_travel_time_s": result.total_travel_time_s,
        "access_stop_id": result.access_stop_id,
        "egress_stop_id": result.egress_stop_id,
        "access_walk_distance_m": result.access_walk_distance_m,
        "access_walk_time_s": result.access_walk_time_s,
        "initial_wait_time_s": result.initial_wait_time_s,
        "in_vehicle_time_s": result.in_vehicle_time_s,
        "transfer_and_dwell_time_s": (
            result.transfer_and_dwell_time_s
        ),
        "n_boardings": result.n_boardings,
        "n_transfers": result.n_transfers,
        "egress_walk_distance_m": result.egress_walk_distance_m,
        "egress_walk_time_s": result.egress_walk_time_s,
        "n_access_walk_edges": len(
            result.access_walk_edges
        ),
        "n_egress_walk_edges": len(
            result.egress_walk_edges
        ),
        "n_transit_connections": len(
            result.transit_connection_ids
        ),
        "transit_connection_ids": "|".join(
            result.transit_connection_ids
        ),
        "transit_trip_ids": "|".join(
            result.transit_trip_ids
        ),
        "transit_route_ids": "|".join(
            result.transit_route_ids
        ),
    }


def run_diagnostics() -> pd.DataFrame:
    """Executa as consultas amostrais e retorna a tabela de resultados"""

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
    routing_config = config[
        "transit"
    ][
        "routing"
    ]
    diagnostics_config = routing_config[
        "diagnostics"
    ]

    data_dir = (
        PROJECT_ROOT
        / gtfs_config[
            "data_dir"
        ]
    )

    service_date = _load_representative_service_date(
        data_dir=data_dir,
        summary_file=network_config[
            "summary_file"
        ],
    )

    sample_size = int(
        diagnostics_config[
            "sample_size"
        ]
    )
    departure_time_s = int(
        diagnostics_config[
            "departure_time_s"
        ]
    )
    seed = int(
        diagnostics_config[
            "seed"
        ]
    )

    origins = gpd.read_file(
        PROJECT_ROOT
        / config[
            "paths"
        ][
            "origins_income"
        ],
        engine="pyogrio",
    )
    destinations = gpd.read_file(
        PROJECT_ROOT
        / config[
            "paths"
        ][
            "destinations"
        ],
        layer="destinations",
        engine="pyogrio",
    )

    pairs = _prepare_od_sample(
        origins=origins,
        destinations=destinations,
        sample_size=sample_size,
        seed=seed,
    )

    walk_graph = load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
        modes=[
            "walk",
        ],
    )[
        "walk"
    ]

    router = TransitRouter.from_project(
        project_root=PROJECT_ROOT,
        config=config,
        walk_graph=walk_graph,
    )

    rows = []

    for pair in pairs.itertuples(
        index=False
    ):
        result = router.route(
            origin_walk_node=int(
                pair.origin_walk_node
            ),
            destination_walk_node=int(
                pair.destination_walk_node
            ),
            service_date=service_date,
            departure_time_s=departure_time_s,
        )

        rows.append(
            _result_row(
                pair=pair,
                result=result,
            )
        )

    result_frame = pd.DataFrame(
        rows
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        OUTPUT_DIR
        / "transit_routing_diagnostics.csv"
    )

    result_frame.to_csv(
        output_path,
        index=False,
        encoding="utf-8",
    )

    return result_frame


def main() -> None:
    """Executa e imprime o diagnóstico amostral do roteamento temporal"""

    config = _load_config()
    diagnostics_config = config[
        "transit"
    ][
        "routing"
    ][
        "diagnostics"
    ]

    result = run_diagnostics()

    total = len(
        result
    )
    successful = result.loc[
        result[
            "status"
        ]
        == ROUTE_OK
    ]

    print(
        "\n"
        + "="
        * 72
    )
    print(
        "DIAGNÓSTICO DO ROTEAMENTO TEMPORAL DE ÔNIBUS"
    )
    print(
        "="
        * 72
    )

    print(
        "\nConfiguração"
    )
    print(
        "  Consultas amostradas: "
        f"{_format_int_pt(total)} viagens OD"
    )
    print(
        "  Horário de partida: "
        f"{_format_time_hhmm(int(diagnostics_config['departure_time_s']))}"
    )
    print(
        "  Semente da amostra: "
        f"{_format_int_pt(diagnostics_config['seed'])}"
    )

    print(
        "\nStatus das consultas"
    )

    status_counts = (
        result[
            "status"
        ]
        .value_counts(
            dropna=False
        )
    )

    for status, count in status_counts.items():
        print(
            f"  {status}: "
            f"{_format_int_pt(count)} viagens "
            f"({_format_percentage_pt(count, total)})"
        )

    print(
        "\nCobertura"
    )
    print(
        "  Rotas de transporte coletivo encontradas: "
        f"{_format_int_pt(len(successful))} viagens "
        f"({_format_percentage_pt(len(successful), total)})"
    )

    if not successful.empty:
        print(
            "\nTempos das rotas bem-sucedidas"
        )
        print(
            "  Tempo total — média: "
            f"{_format_float_pt(successful['total_travel_time_s'].mean())} s"
        )
        print(
            "  Tempo total — mediana: "
            f"{_format_float_pt(successful['total_travel_time_s'].median())} s"
        )
        print(
            "  Caminhada de acesso — média: "
            f"{_format_float_pt(successful['access_walk_distance_m'].mean())} m"
        )
        print(
            "  Caminhada de egresso — média: "
            f"{_format_float_pt(successful['egress_walk_distance_m'].mean())} m"
        )
        print(
            "  Espera inicial — média: "
            f"{_format_float_pt(successful['initial_wait_time_s'].mean())} s"
        )
        print(
            "  Tempo dentro do veículo — média: "
            f"{_format_float_pt(successful['in_vehicle_time_s'].mean())} s"
        )
        print(
            "  Transferências — média: "
            f"{_format_float_pt(successful['n_transfers'].mean(), decimals=2)} "
            "transferências por viagem"
        )

    print(
        "\nSaída"
    )
    print(
        "  Arquivo: "
        f"{(OUTPUT_DIR / 'transit_routing_diagnostics.csv').resolve()}"
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
