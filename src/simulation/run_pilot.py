"""
Executa o pipeline piloto do EtPilot até a visualização espacial dos cenários

Preserva o mesmo conjunto de agentes e as mesmas origens residenciais nos
dois cenários, remove diferenças comportamentais por renda no baseline e
preserva diferenças de propósito, destino e modo no differentiated

O fluxo:
1. carrega configurações e dados
2. carrega as redes OSM e a rede temporal GTFS roteável
3. gera a população sintética
4. atribui origens residenciais
5. constrói os cenários comportamentais
6. atribui propósito, destino e modo e roteia walk, bike, car e transit
7. integra as redes OSM e a rede física GTFS completa em segmentos físicos comuns
8. calcula volume, composição social e H_soc por segmento
9. compara baseline e differentiated de forma pareada por segmento
10. gera mapas comparáveis de H_soc e delta_H_soc
11. valida, resume e salva os resultados
12. atualiza a documentação metodológica XLSX e HTML

A execução ocorre com:
    python -m src.simulation.run_pilot
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.analysis.trip_outliers import (
    apply_paired_transit_outlier_filter,
)
from src.analysis.edge_statistics import (
    attach_statistics_to_segments,
    build_segment_statistics,
)
from src.analysis.scenario_comparison import (
    attach_comparison_to_segments,
    build_scenario_comparison,
    comparison_summary,
)
from src.domain.enums import IncomeGroup, TravelMode
from src.network.analysis_segments import (
    apply_analysis_segment_mapping,
    build_analysis_segments,
    extract_all_modal_edges,
    segment_match_report,
)
from src.network.multimodal import load_mode_graphs
from src.routing.multimodal_router import (
    SUCCESS_STATUSES,
)
from src.routing.pilot_router import route_pilot_agents
from src.simulation.destination_choice import (
    assign_destinations,
    destination_choice_summary,
)
from src.simulation.mode_choice import choose_mode
from src.simulation.origin_assignment import assign_origins
from src.simulation.population import generate_population
from src.simulation.purpose_choice import assign_purpose
from src.simulation.scenarios import build_behavior_scenarios
from src.trajectory.edge_usage import build_edge_usage
from src.trajectory.transit_usage import (
    build_transit_edge_usage,
)
from src.transit.physicalNetwork import (
    integrate_transit_physical_network,
    summarize_transit_physical_integration,
)
from src.transit.routeTransit import TransitRouter


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
CONFIG_AGENTS_PATH = PROJECT_ROOT / "config" / "config_agents.json"

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "pilot"

N_AGENTS = 100
SEED = 42
SCENARIOS = ("baseline", "differentiated")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _format_int_pt(
    value,
) -> str:
    """Formata inteiros com separador de milhar brasileiro"""

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

    if value is None or pd.isna(
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
    """Formata uma razão como percentual"""

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


def _assign_modes(
    agents,
    mode_config: dict,
    distance_config: dict | None,
    seed: int,
    available_mode_names: list[str] | tuple[str, ...],
) -> None:
    rng = np.random.default_rng(seed)

    available_modes = {
        TravelMode(
            mode
        )
        for mode in available_mode_names
    }

    for agent in agents:
        agent.mode = choose_mode(
            agent=agent,
            config=mode_config,
            rng=rng,
            available_modes=available_modes,
            distance_config=distance_config,
        )

        agent.resolve_routing_nodes()


def _validate_agents(agents) -> dict[str, int]:
    return {
        "origem": sum(agent.origin_id is None for agent in agents),
        "origin_node": sum(agent.origin_node is None for agent in agents),
        "propósito": sum(agent.purpose is None for agent in agents),
        "destino": sum(agent.destination_id is None for agent in agents),
        "od_distance_m": sum(
            agent.od_distance_m is None
            for agent in agents
        ),
        "destination_node": sum(
            agent.destination_node is None for agent in agents
        ),
        "modo": sum(agent.mode is None for agent in agents),
        "route_status": sum(
            agent.route_status is None for agent in agents
        ),
    }


def _build_summary(
    agents,
    scenario_name: str,
) -> pd.DataFrame:
    summary = destination_choice_summary(agents)

    summary["origin_node"] = [
        agent.origin_node
        for agent in agents
    ]

    summary["mode"] = [
        agent.mode.value if agent.mode is not None else None
        for agent in agents
    ]

    summary["route_status"] = [
        agent.route_status
        for agent in agents
    ]

    summary["n_route_edges"] = [
        len(agent.route_edges)
        for agent in agents
    ]

    summary["travel_distance_m"] = [
        agent.travel_distance
        for agent in agents
    ]

    summary["travel_time_s"] = [
        agent.travel_time
        for agent in agents
    ]

    summary["transit_service_date"] = [
        agent.transit_service_date
        for agent in agents
    ]
    summary["transit_departure_time_s"] = [
        agent.transit_departure_time_s
        for agent in agents
    ]
    summary["transit_arrival_time_s"] = [
        agent.transit_arrival_time_s
        for agent in agents
    ]
    summary["transit_access_stop_id"] = [
        agent.transit_access_stop_id
        for agent in agents
    ]
    summary["transit_egress_stop_id"] = [
        agent.transit_egress_stop_id
        for agent in agents
    ]
    summary["transit_access_walk_distance_m"] = [
        agent.transit_access_walk_distance_m
        for agent in agents
    ]
    summary["transit_initial_wait_time_s"] = [
        agent.transit_initial_wait_time_s
        for agent in agents
    ]
    summary["transit_in_vehicle_distance_m"] = [
        agent.transit_in_vehicle_distance_m
        for agent in agents
    ]
    summary["transit_in_vehicle_time_s"] = [
        agent.transit_in_vehicle_time_s
        for agent in agents
    ]
    summary["transit_n_boardings"] = [
        agent.transit_n_boardings
        for agent in agents
    ]
    summary["transit_n_transfers"] = [
        agent.transit_n_transfers
        for agent in agents
    ]
    summary["transit_egress_walk_distance_m"] = [
        agent.transit_egress_walk_distance_m
        for agent in agents
    ]
    summary["n_transit_connections"] = [
        len(
            agent.transit_connection_ids
        )
        for agent in agents
    ]

    # Persiste as arestas e conexões para inspecionar e reconstruir o uso da rede
    summary["route_edges"] = [
        json.dumps(
            agent.route_edges
        )
        for agent in agents
    ]
    summary["transit_connection_ids"] = [
        json.dumps(
            agent.transit_connection_ids
        )
        for agent in agents
    ]
    summary["transit_trip_ids"] = [
        json.dumps(
            agent.transit_trip_ids
        )
        for agent in agents
    ]
    summary["transit_route_ids"] = [
        json.dumps(
            agent.transit_route_ids
        )
        for agent in agents
    ]

    summary.insert(0, "scenario", scenario_name)

    return summary


def _print_scenario_summary(
    scenario_name: str,
    summary: pd.DataFrame,
) -> None:
    """Imprime a composição e o desempenho das viagens com unidades explícitas"""

    print(
        "\n"
        + "="
        * 72
    )
    print(
        f"CENÁRIO: {scenario_name.upper()}"
    )
    print(
        "="
        * 72
    )

    total_agents = len(
        summary
    )

    for title, column in [
        (
            "Distribuição por renda",
            "income_group",
        ),
        (
            "Distribuição por propósito",
            "purpose",
        ),
        (
            "Distribuição por modo",
            "mode",
        ),
    ]:
        print(
            f"\n{title}"
        )

        counts = (
            summary[
                column
            ]
            .value_counts(
                dropna=False
            )
            .sort_index()
        )

        for category, count in counts.items():
            print(
                f"  {category}: "
                f"{_format_int_pt(count)} agentes "
                f"({_format_percentage_pt(count, total_agents)})"
            )

    print(
        "\nRenda × propósito — agentes"
    )
    print(
        pd.crosstab(
            summary[
                "income_group"
            ],
            summary[
                "purpose"
            ],
        ).to_string()
    )

    print(
        "\nRenda × modo — agentes"
    )
    print(
        pd.crosstab(
            summary[
                "income_group"
            ],
            summary[
                "mode"
            ],
        ).to_string()
    )

    print(
        "\nStatus do roteamento"
    )

    route_counts = (
        summary[
            "route_status"
        ]
        .value_counts(
            dropna=False
        )
        .sort_index()
    )

    for status, count in route_counts.items():
        print(
            f"  {status}: "
            f"{_format_int_pt(count)} viagens "
            f"({_format_percentage_pt(count, total_agents)})"
        )

    transit_selected = summary.loc[
        summary[
            "mode"
        ]
        == TravelMode.TRANSIT.value
    ]

    if not transit_selected.empty:
        transit_success_count = int(
            transit_selected[
                "route_status"
            ].isin(
                SUCCESS_STATUSES
            ).sum()
        )

        print(
            "\nCobertura do roteamento transit"
        )
        print(
            "  Agentes que escolheram transit: "
            f"{_format_int_pt(len(transit_selected))} agentes"
        )
        print(
            "  Rotas transit bem-sucedidas: "
            f"{_format_int_pt(transit_success_count)} viagens "
            f"({_format_percentage_pt(transit_success_count, len(transit_selected))})"
        )

    successful = summary.loc[
        summary[
            "route_status"
        ].isin(
            SUCCESS_STATUSES
        )
    ]

    if successful.empty:
        return

    print(
        "\nDistâncias das viagens bem-sucedidas"
    )

    for mode, group in successful.groupby(
        "mode"
    ):
        od = group[
            "od_distance_m"
        ].dropna()
        routed = group[
            "travel_distance_m"
        ].dropna()

        print(
            f"  {mode}: {_format_int_pt(len(group))} viagens"
        )

        if not od.empty:
            print(
                "    OD euclidiana — "
                f"média {_format_float_pt(od.mean())} m | "
                f"mediana {_format_float_pt(od.median())} m | "
                f"mínima {_format_float_pt(od.min())} m | "
                f"máxima {_format_float_pt(od.max())} m"
            )

        if not routed.empty:
            print(
                "    rota — "
                f"média {_format_float_pt(routed.mean())} m | "
                f"mediana {_format_float_pt(routed.median())} m | "
                f"mínima {_format_float_pt(routed.min())} m | "
                f"máxima {_format_float_pt(routed.max())} m"
            )

    transit_success = successful.loc[
        successful[
            "mode"
        ]
        == TravelMode.TRANSIT.value
    ]

    if not transit_success.empty:
        print(
            "\nDesempenho das viagens transit bem-sucedidas"
        )

        travel_time = (
            transit_success[
                "travel_time_s"
            ]
            .dropna()
            / 60.0
        )
        access = transit_success[
            "transit_access_walk_distance_m"
        ].dropna()
        egress = transit_success[
            "transit_egress_walk_distance_m"
        ].dropna()
        wait = (
            transit_success[
                "transit_initial_wait_time_s"
            ]
            .dropna()
            / 60.0
        )
        in_vehicle = (
            transit_success[
                "transit_in_vehicle_time_s"
            ]
            .dropna()
            / 60.0
        )
        transfers = transit_success[
            "transit_n_transfers"
        ].dropna()

        if not travel_time.empty:
            print(
                "  Tempo total — "
                f"média {_format_float_pt(travel_time.mean())} min | "
                f"mediana {_format_float_pt(travel_time.median())} min"
            )

        if not access.empty:
            print(
                "  Caminhada de acesso — "
                f"média {_format_float_pt(access.mean())} m"
            )

        if not egress.empty:
            print(
                "  Caminhada de egresso — "
                f"média {_format_float_pt(egress.mean())} m"
            )

        if not wait.empty:
            print(
                "  Espera inicial — "
                f"média {_format_float_pt(wait.mean())} min"
            )

        if not in_vehicle.empty:
            print(
                "  Tempo dentro do veículo — "
                f"média {_format_float_pt(in_vehicle.mean())} min"
            )

        if not transfers.empty:
            print(
                "  Transferências — "
                f"média {_format_float_pt(transfers.mean(), decimals=2)} "
                "transferências/viagem | "
                f"máxima {_format_int_pt(transfers.max())} transferências"
            )

def _validate_fixed_population(
    summaries: dict[str, pd.DataFrame],
) -> None:
    """
    Garante que população e residência sejam idênticas entre cenários

    Permite variar propósito, destino, modo e rota
    Preserva identidade, renda e origem residencial
    """

    fixed_columns = [
        "agent_id",
        "income_group",
        "origin_id",
    ]

    reference = (
        summaries[SCENARIOS[0]][fixed_columns]
        .sort_values("agent_id")
        .reset_index(drop=True)
    )

    for scenario_name in SCENARIOS[1:]:
        comparison = (
            summaries[scenario_name][fixed_columns]
            .sort_values("agent_id")
            .reset_index(drop=True)
        )

        if not reference.equals(comparison):
            raise RuntimeError(
                "Os cenários não estão usando exatamente a mesma "
                "população e as mesmas origens residenciais."
            )


def _save_outputs(
    summaries: dict[str, pd.DataFrame],
    routed_edge_usages: dict[str, pd.DataFrame],
    edge_usages: dict[str, pd.DataFrame],
    harmonized_edge_usages: dict[str, pd.DataFrame],
    analysis_segments: gpd.GeoDataFrame,
    segment_mapping: pd.DataFrame,
    match_report: pd.DataFrame,
    used_match_report: pd.DataFrame,
    segment_statistics: dict[str, pd.DataFrame],
    segment_geodata: dict[str, gpd.GeoDataFrame],
    scenario_comparison: pd.DataFrame,
    scenario_comparison_geodata: gpd.GeoDataFrame,
    scenario_comparison_summary: dict,
    transit_mapping: pd.DataFrame,
    transit_match_diagnostics: pd.DataFrame,
    transit_physical_summary: dict,
) -> None:
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for scenario_name, summary in summaries.items():
        summary.to_csv(
            OUTPUT_DIR / f"agents_{scenario_name}.csv",
            index=False,
            encoding="utf-8",
        )

    comparison = pd.concat(
        summaries.values(),
        ignore_index=True,
    )

    comparison.to_csv(
        OUTPUT_DIR / "agents_all_scenarios.csv",
        index=False,
        encoding="utf-8",
    )

    for scenario_name, edge_usage in routed_edge_usages.items():
        edge_usage.to_csv(
            OUTPUT_DIR
            / f"edge_usage_routed_{scenario_name}.csv",
            index=False,
            encoding="utf-8",
        )

    routed_all = pd.concat(
        routed_edge_usages.values(),
        ignore_index=True,
    )

    routed_all.to_csv(
        OUTPUT_DIR
        / "edge_usage_routed_all_scenarios.csv",
        index=False,
        encoding="utf-8",
    )

    for scenario_name, edge_usage in edge_usages.items():
        edge_usage.to_csv(
            OUTPUT_DIR / f"edge_usage_{scenario_name}.csv",
            index=False,
            encoding="utf-8",
        )

    edge_usage_all = pd.concat(
        edge_usages.values(),
        ignore_index=True,
    )

    edge_usage_all.to_csv(
        OUTPUT_DIR / "edge_usage_all_scenarios.csv",
        index=False,
        encoding="utf-8",
    )

    for scenario_name, edge_usage in harmonized_edge_usages.items():
        edge_usage.to_csv(
            OUTPUT_DIR / f"edge_usage_analysis_{scenario_name}.csv",
            index=False,
            encoding="utf-8",
        )

    harmonized_all = pd.concat(
        harmonized_edge_usages.values(),
        ignore_index=True,
    )

    harmonized_all.to_csv(
        OUTPUT_DIR / "edge_usage_analysis_all_scenarios.csv",
        index=False,
        encoding="utf-8",
    )

    segment_mapping.to_csv(
        OUTPUT_DIR / "modal_edge_to_analysis_segment.csv",
        index=False,
        encoding="utf-8",
    )

    match_report.to_csv(
        OUTPUT_DIR / "analysis_segment_match_report.csv",
        index=False,
        encoding="utf-8",
    )

    used_match_report.to_csv(
        OUTPUT_DIR / "analysis_segment_used_match_report.csv",
        index=False,
        encoding="utf-8",
    )

    transit_mapping.to_csv(
        OUTPUT_DIR
        / "transit_physical_edge_to_analysis_segment.csv",
        index=False,
        encoding="utf-8",
    )

    transit_match_diagnostics.to_csv(
        OUTPUT_DIR
        / "transit_physical_match_diagnostics.csv",
        index=False,
        encoding="utf-8",
    )

    pd.DataFrame(
        [
            transit_physical_summary,
        ]
    ).to_csv(
        OUTPUT_DIR
        / "transit_physical_network_summary.csv",
        index=False,
        encoding="utf-8",
    )

    for scenario_name, statistics in segment_statistics.items():
        statistics.to_csv(
            OUTPUT_DIR / f"segment_statistics_{scenario_name}.csv",
            index=False,
            encoding="utf-8",
        )

    statistics_all = pd.concat(
        segment_statistics.values(),
        ignore_index=True,
    )

    statistics_all.to_csv(
        OUTPUT_DIR / "segment_statistics_all_scenarios.csv",
        index=False,
        encoding="utf-8",
    )


    scenario_comparison.to_csv(
        OUTPUT_DIR / "segment_scenario_comparison.csv",
        index=False,
        encoding="utf-8",
    )


    pd.DataFrame(
        [
            scenario_comparison_summary,
        ]
    ).to_csv(
        OUTPUT_DIR / "segment_scenario_comparison_summary.csv",
        index=False,
        encoding="utf-8",
    )

    comparison_to_save = scenario_comparison_geodata.drop(
        columns=[
            "osmid_set",
        ],
        errors="ignore",
    )

    comparison_path = (
        OUTPUT_DIR
        / "segment_scenario_comparison.gpkg"
    )

    if comparison_path.exists():
        comparison_path.unlink()

    comparison_to_save.to_file(
        comparison_path,
        layer="scenario_comparison",
        driver="GPKG",
        engine="pyogrio",
    )

    for scenario_name, geodata in segment_geodata.items():
        geodata_to_save = geodata.drop(
            columns=[
                "osmid_set",
            ],
            errors="ignore",
        )

        metrics_path = (
            OUTPUT_DIR
            / f"segment_metrics_{scenario_name}.gpkg"
        )

        if metrics_path.exists():
            metrics_path.unlink()

        geodata_to_save.to_file(
            metrics_path,
            layer="segment_metrics",
            driver="GPKG",
            engine="pyogrio",
        )

    # Remove estruturas Python que o GeoPackage não consegue serializar
    segments_to_save = analysis_segments.drop(
        columns=[
            "osmid_set",
        ],
        errors="ignore",
    )

    segment_path = (
        OUTPUT_DIR
        / "analysis_segments.gpkg"
    )

    if segment_path.exists():
        segment_path.unlink()

    segments_to_save.to_file(
        segment_path,
        layer="analysis_segments",
        driver="GPKG",
        engine="pyogrio",
    )


def main() -> None:
    config = load_json(CONFIG_PATH)
    config_agents = load_json(CONFIG_AGENTS_PATH)

    implemented_modes = list(
        config["routing"]["implemented_modes"]
    )
    choice_modes = list(
        config[
            "routing"
        ].get(
            "choice_modes",
            [
                *implemented_modes,
                TravelMode.TRANSIT.value,
            ],
        )
    )
    node_prefix = config["routing"].get(
        "node_column_prefix",
        "node_",
    )
    routing_weight = config["routing"].get(
        "weight",
        "length",
    )
    routing_strict = bool(
        config["routing"].get(
            "strict",
            False,
        )
    )

    transit_config = config[
        "transit"
    ]
    transit_network_config = transit_config[
        "network"
    ]
    transit_routing_config = transit_config[
        "routing"
    ]
    transit_spatial_config = transit_config[
        "spatial_mapping"
    ]

    transit_departure_time_s = int(
        transit_routing_config[
            "pilot_departure_time_s"
        ]
    )
    transit_primary_spatial_config = (
        transit_spatial_config[
            "primary"
        ]
    )
    transit_fallback_spatial_config = (
        transit_spatial_config[
            "fallback"
        ]
    )

    segment_config = config[
        "analysis"
    ][
        "analysis_segments"
    ]

    segment_reference_mode = (
        segment_config[
            "reference_mode"
        ]
    )
    segment_mode_order = tuple(
        segment_config[
            "mode_order"
        ]
    )
    segment_tolerance_m = float(
        segment_config[
            "geometry_tolerance_m"
        ]
    )
    segment_min_coverage = float(
        segment_config[
            "min_geometry_coverage"
        ]
    )

    statistics_config = config[
        "analysis"
    ][
        "segment_statistics"
    ]
    outlier_config = config[
        "analysis"
    ].get(
        "trip_outliers",
        {},
    )

    min_agents_for_interpretation = int(
        statistics_config[
            "min_agents_for_interpretation"
        ]
    )
    flow_thresholds = tuple(
        int(value)
        for value in statistics_config[
            "flow_thresholds"
        ]
    )

    maps_config = config[
        "analysis"
    ].get(
        "maps",
        {},
    )
    maps_enabled = bool(
        maps_config.get(
            "enabled",
            True,
        )
    )
    maps_dpi = int(
        maps_config.get(
            "dpi",
            220,
        )
    )

    origins_path = (
        PROJECT_ROOT
        / config["paths"]["origins_income"]
    )
    destinations_path = (
        PROJECT_ROOT
        / config["paths"]["destinations"]
    )

    print("1/12 - Carregando dados...")

    origins = gpd.read_file(origins_path)

    destinations = gpd.read_file(
        destinations_path,
        layer="destinations",
    )

    print("2/12 - Carregando redes modais...")

    graphs = load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
        modes=implemented_modes,
    )

    for mode, graph in graphs.items():
        print(
            f"  {mode}: "
            f"{_format_int_pt(len(graph.nodes))} nós | "
            f"{_format_int_pt(len(graph.edges))} arestas"
        )

    gtfs_data_dir = (
        PROJECT_ROOT
        / transit_config[
            "gtfs"
        ][
            "data_dir"
        ]
    )
    transit_summary_path = (
        gtfs_data_dir
        / transit_network_config[
            "summary_file"
        ]
    )

    if not transit_summary_path.exists():
        raise FileNotFoundError(
            "Execute antes python -m src.transit.buildTransitNetwork "
            "para gerar a rede temporal roteável"
        )

    transit_network_summary = pd.read_csv(
        transit_summary_path
    )

    if (
        transit_network_summary.empty
        or "representative_service_date"
        not in transit_network_summary.columns
    ):
        raise ValueError(
            "transit_network_summary.csv não possui representative_service_date"
        )

    transit_service_date = str(
        transit_network_summary.iloc[
            0
        ][
            "representative_service_date"
        ]
    )

    transit_router = TransitRouter.from_project(
        project_root=PROJECT_ROOT,
        config=config,
        walk_graph=graphs[
            TravelMode.WALK.value
        ],
    )

    transit_connections = (
        transit_router.connections
    )

    transit_physical_edges_path = (
        gtfs_data_dir
        / transit_network_config[
            "transit_physical_edges_file"
        ]
    )

    if not transit_physical_edges_path.exists():
        raise FileNotFoundError(
            "Execute novamente python -m src.transit.buildTransitNetwork "
            "para gerar a rede física completa de transit"
        )

    transit_physical_edges = gpd.read_file(
        transit_physical_edges_path,
        layer="transit_physical_edges_processed",
        engine="pyogrio",
    )

    print(
        "  transit: "
        f"{_format_int_pt(len(transit_connections))} conexões GTFS roteáveis | "
        f"{_format_int_pt(len(transit_physical_edges))} trechos físicos | "
        f"data de serviço {transit_service_date} | "
        "partida fixa "
        f"{_format_float_pt(transit_departure_time_s / 3600, decimals=2)} h"
    )

    print("3/12 - Gerando população sintética...")

    income_shares = {
        IncomeGroup(group_name): group_data["share"]
        for group_name, group_data
        in config["income"]["groups"].items()
    }

    base_agents = generate_population(
        n_agents=N_AGENTS,
        income_shares=income_shares,
        seed=SEED,
    )

    print(
        "Agentes gerados: "
        f"{_format_int_pt(len(base_agents))} agentes"
    )

    print("4/12 - Atribuindo origens residenciais...")

    base_agents = assign_origins(
        agents=base_agents,
        origins=origins,
        population_column="POP",
        seed=SEED,
        modes=implemented_modes,
        node_prefix=node_prefix,
    )

    agents_with_origin = sum(
        agent.origin_id is not None
        for agent in base_agents
    )

    print(
        "Agentes com origem: "
        f"{_format_int_pt(agents_with_origin)} agentes "
        f"({_format_percentage_pt(agents_with_origin, len(base_agents))})"
    )

    print("5/12 - Construindo cenários experimentais...")

    behavior_scenarios = build_behavior_scenarios(
        config_agents=config_agents,
        income_shares=income_shares,
    )

    summaries: dict[str, pd.DataFrame] = {}
    edge_usages: dict[str, pd.DataFrame] = {}

    print("6/12 - Executando cenários e roteamento...")

    for scenario_name in SCENARIOS:
        print(f"\n--- {scenario_name} ---")

        agents = deepcopy(base_agents)

        scenario_config = (
            behavior_scenarios[scenario_name]
        )

        agents = assign_purpose(
            agents=agents,
            purpose_probabilities=(
                scenario_config["purpose_choice"]
            ),
            seed=SEED,
        )

        agents = assign_destinations(
            agents=agents,
            origins=origins,
            destinations=destinations,
            choice_config=(
                scenario_config["destination_choice"]
            ),
            seed=SEED,
            max_trip_distance_m=(
                config["analysis"]["max_trip_distance"]
            ),
            modes=implemented_modes,
            node_prefix=node_prefix,
        )

        _assign_modes(
            agents=agents,
            mode_config=(
                scenario_config["mode_choice"]
            ),
            distance_config=(
                scenario_config[
                    "mode_distance_adjustment"
                ]
            ),
            seed=SEED,
            available_mode_names=choice_modes,
        )

        agents = route_pilot_agents(
            agents,
            graphs=graphs,
            transit_router=transit_router,
            transit_service_date=transit_service_date,
            transit_departure_time_s=transit_departure_time_s,
            road_weight=routing_weight,
            strict=routing_strict,
        )

        missing = _validate_agents(agents)

        if any(missing.values()):
            raise RuntimeError(
                f"Cenário '{scenario_name}' possui "
                f"atributos ausentes: {missing}"
            )

        successful_routes = sum(
            agent.route_status in SUCCESS_STATUSES
            for agent in agents
        )

        if successful_routes == 0:
            raise RuntimeError(
                f"Nenhuma rota foi calculada no cenário '{scenario_name}'."
            )

        summary = _build_summary(
            agents=agents,
            scenario_name=scenario_name,
        )

        summaries[scenario_name] = summary

        road_agents = [
            agent
            for agent in agents
            if agent.mode is not TravelMode.TRANSIT
        ]

        road_edge_usage = build_edge_usage(
            agents=road_agents,
            graphs=graphs,
            scenario_name=scenario_name,
        )

        transit_edge_usage = build_transit_edge_usage(
            agents,
            walk_graph=graphs[
                TravelMode.WALK.value
            ],
            connections=transit_connections,
            scenario_name=scenario_name,
        )

        edge_usage = pd.concat(
            [
                road_edge_usage,
                transit_edge_usage,
            ],
            ignore_index=True,
            sort=False,
        )

        edge_usages[scenario_name] = edge_usage

        _print_scenario_summary(
            scenario_name=scenario_name,
            summary=summary,
        )

        print(
            "\nUso das arestas: "
            f"{_format_int_pt(len(edge_usage))} passagens agente×aresta | "
            f"{_format_int_pt(edge_usage['modal_edge_id'].nunique())} "
            "arestas modais únicas"
        )

    routed_edge_usages = {
        scenario_name: edge_usage.copy()
        for scenario_name, edge_usage
        in edge_usages.items()
    }

    (
        summaries,
        outlier_exclusions,
        outlier_filter_summary,
    ) = apply_paired_transit_outlier_filter(
        summaries,
        config=outlier_config,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    outlier_exclusions.to_csv(
        OUTPUT_DIR
        / outlier_config.get(
            "exclusions_file",
            "outlier_exclusions.csv",
        ),
        index=False,
        encoding="utf-8",
    )
    outlier_filter_summary.to_csv(
        OUTPUT_DIR
        / outlier_config.get(
            "summary_file",
            "outlier_filter_summary.csv",
        ),
        index=False,
        encoding="utf-8",
    )

    filter_row = outlier_filter_summary.iloc[
        0
    ]

    print(
        "\nControle de outliers das viagens transit"
    )
    print(
        "  Método: "
        f"{filter_row['method']}"
    )
    print(
        "  Rotas transit elegíveis: "
        f"{_format_int_pt(filter_row['eligible_transit_routes'])} viagens"
    )

    if bool(
        filter_row[
            "sample_size_sufficient"
        ]
    ):
        print(
            "  Cerca externa da distância roteada: "
            f"{_format_float_pt(filter_row['route_distance_upper_fence_m'])} m"
        )
        print(
            "  Cerca externa da razão rota/OD: "
            f"{_format_float_pt(filter_row['circuity_upper_fence'], decimals=2)}"
        )

    print(
        "  Outliers diretos identificados: "
        f"{_format_int_pt(filter_row['direct_outlier_routes'])} viagens"
    )
    print(
        "  Agentes excluídos da análise pareada: "
        f"{_format_int_pt(filter_row['unique_excluded_agents'])} agentes"
    )
    print(
        "  Registros de exclusão salvos: "
        f"{_format_int_pt(filter_row['excluded_scenario_rows'])} linhas"
    )

    for scenario_name in SCENARIOS:
        included_agent_ids = set(
            summaries[
                scenario_name
            ].loc[
                summaries[
                    scenario_name
                ][
                    "analysis_included"
                ],
                "agent_id",
            ]
        )

        before_rows = len(
            edge_usages[
                scenario_name
            ]
        )

        edge_usages[
            scenario_name
        ] = (
            edge_usages[
                scenario_name
            ].loc[
                edge_usages[
                    scenario_name
                ][
                    "agent_id"
                ].isin(
                    included_agent_ids
                )
            ]
            .copy()
            .reset_index(
                drop=True
            )
        )

        after_rows = len(
            edge_usages[
                scenario_name
            ]
        )

        included_agents = int(
            summaries[
                scenario_name
            ][
                "analysis_included"
            ].sum()
        )

        print(
            f"  {scenario_name}: "
            f"{_format_int_pt(included_agents)} agentes mantidos | "
            f"{_format_int_pt(before_rows - after_rows)} passagens removidas | "
            f"{_format_int_pt(after_rows)} passagens mantidas"
        )

    print("\n7/12 - Harmonizando segmentos físicos de análise...")

    edge_usage_all = pd.concat(
        edge_usages.values(),
        ignore_index=True,
    )

    # Constrói a camada física com as redes completas, e não com a amostra
    modal_edges = extract_all_modal_edges(
        graphs=graphs,
        modes=segment_mode_order,
    )

    analysis_segments, segment_mapping = (
        build_analysis_segments(
            modal_edges=modal_edges,
            reference_mode=segment_reference_mode,
            mode_order=segment_mode_order,
            tolerance_m=segment_tolerance_m,
            min_coverage=segment_min_coverage,
        )
    )

    segment_mapping[
        "mapping_scope"
    ] = "full_road_active_network"

    road_analysis_segment_count = len(
        analysis_segments
    )

    (
        analysis_segments,
        segment_mapping,
        transit_mapping,
        transit_match_diagnostics,
    ) = integrate_transit_physical_network(
        analysis_segments,
        segment_mapping,
        transit_physical_edges,
        primary_config=(
            transit_primary_spatial_config
        ),
        fallback_config=(
            transit_fallback_spatial_config
        ),
    )

    transit_physical_summary = (
        summarize_transit_physical_integration(
            transit_physical_edges,
            transit_mapping,
            transit_match_diagnostics,
        )
    )

    used_transit_modal_edges = set(
        edge_usage_all.loc[
            edge_usage_all[
                "mapping_mode"
            ]
            == TravelMode.TRANSIT.value,
            "modal_edge_id",
        ]
        .dropna()
        .astype(
            str
        )
    )
    mapped_transit_modal_edges = set(
        transit_mapping[
            "modal_edge_id"
        ]
        .dropna()
        .astype(
            str
        )
    )

    missing_used_transit_edges = (
        used_transit_modal_edges
        - mapped_transit_modal_edges
    )

    if missing_used_transit_edges:
        sample_ids = sorted(
            missing_used_transit_edges
        )[
            :10
        ]

        raise RuntimeError(
            "A rede física transit completa não cobre todos os trechos "
            "usados pelos agentes: "
            f"{_format_int_pt(len(missing_used_transit_edges))} trechos | "
            f"amostra={sample_ids}"
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    legacy_transit_outputs = [
        "transit_connection_to_analysis_segment.csv",
        "transit_connection_geometry_diagnostics.csv",
        "transit_connection_match_diagnostics.csv",
        "transit_spatial_match_report.csv",
        "transit_spatial_exclusions.csv",
        "transit_spatial_exclusion_summary.csv",
    ]

    for filename in legacy_transit_outputs:
        legacy_path = (
            OUTPUT_DIR
            / filename
        )

        if legacy_path.exists():
            legacy_path.unlink()

    transit_mapping.to_csv(
        OUTPUT_DIR
        / transit_spatial_config.get(
            "transit_physical_mapping_file",
            "transit_physical_edge_to_analysis_segment.csv",
        ),
        index=False,
        encoding="utf-8",
    )
    transit_match_diagnostics.to_csv(
        OUTPUT_DIR
        / "transit_physical_match_diagnostics.csv",
        index=False,
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            transit_physical_summary,
        ]
    ).to_csv(
        OUTPUT_DIR
        / transit_spatial_config.get(
            "transit_physical_summary_file",
            "transit_physical_network_summary.csv",
        ),
        index=False,
        encoding="utf-8",
    )

    print(
        "\nIntegração da rede física completa do transporte coletivo"
    )
    print(
        "  Segmentos físicos OSM antes de transit: "
        f"{_format_int_pt(road_analysis_segment_count)} segmentos"
    )
    print(
        "  Trechos físicos GTFS processados: "
        f"{_format_int_pt(transit_physical_summary['transit_physical_edges'])} trechos"
    )
    print(
        "  Trechos associados na etapa primária car-supported: "
        f"{_format_int_pt(transit_physical_summary['primary_matches'])} trechos"
    )
    print(
        "  Trechos associados na etapa de fallback: "
        f"{_format_int_pt(transit_physical_summary['fallback_matches'])} trechos"
    )
    print(
        "  Trechos GTFS representados pela rede exclusiva transit: "
        f"{_format_int_pt(transit_physical_summary['exclusive_transit_edges'])} trechos"
    )
    print(
        "  Novos analysis_segment_id exclusivos transit: "
        f"{_format_int_pt(transit_physical_summary['exclusive_transit_segments'])} segmentos"
    )
    print(
        "  Trechos físicos transit mapeados: "
        f"{_format_int_pt(transit_physical_summary['mapped_transit_physical_edges'])} trechos "
        f"({_format_percentage_pt(transit_physical_summary['mapped_transit_physical_edges'], max(transit_physical_summary['transit_physical_edges'], 1))})"
    )
    print(
        "  Trechos transit efetivamente usados no N=100: "
        f"{_format_int_pt(len(used_transit_modal_edges))} trechos"
    )
    print(
        "  Trechos usados sem analysis_segment_id: "
        f"{_format_int_pt(len(missing_used_transit_edges))} trechos"
    )
    print(
        "  Segmentos físicos totais após integrar transit: "
        f"{_format_int_pt(len(analysis_segments))} segmentos"
    )

    harmonized_edge_usages: dict[
        str,
        pd.DataFrame,
    ] = {}

    for scenario_name, edge_usage in edge_usages.items():
        harmonized_edge_usages[
            scenario_name
        ] = apply_analysis_segment_mapping(
            edge_usage=edge_usage,
            mapping=segment_mapping,
        )

    match_report = segment_match_report(
        segment_mapping
    )

    used_match_report = segment_match_report(
        segment_mapping,
        modal_edge_ids=(
            edge_usage_all[
                "modal_edge_id"
            ]
            .drop_duplicates()
            .astype(str)
            .tolist()
        ),
    )

    print(
        "\nSegmentos físicos de análise: "
        f"{_format_int_pt(len(analysis_segments))} segmentos"
    )
    print(
        "Arestas modais harmonizadas: "
        f"{_format_int_pt(segment_mapping['modal_edge_id'].nunique())} arestas"
    )

    print("\nMétodos de harmonização — redes físicas completas")
    print(
        match_report[
            [
                "mode",
                "match_method",
                "modal_edges",
                "analysis_segments",
                "modal_edge_share_pct",
                "mean_match_quality",
            ]
        ]
        .round(
            {
                "modal_edge_share_pct": 1,
                "mean_match_quality": 3,
            }
        )
        .to_string(index=False)
    )

    print("\nMétodos de harmonização — arestas efetivamente usadas")
    print(
        used_match_report[
            [
                "mode",
                "match_method",
                "modal_edges",
                "analysis_segments",
                "modal_edge_share_pct",
                "mean_match_quality",
            ]
        ]
        .round(
            {
                "modal_edge_share_pct": 1,
                "mean_match_quality": 3,
            }
        )
        .to_string(index=False)
    )

    print("\n8/12 - Calculando estatísticas e entropia socioeconômica...")

    segment_statistics: dict[
        str,
        pd.DataFrame,
    ] = {}
    segment_geodata: dict[
        str,
        gpd.GeoDataFrame,
    ] = {}

    for scenario_name, edge_usage in harmonized_edge_usages.items():
        statistics = build_segment_statistics(
            edge_usage=edge_usage,
            min_agents_for_interpretation=(
                min_agents_for_interpretation
            ),
            flow_thresholds=flow_thresholds,
        )

        segment_statistics[
            scenario_name
        ] = statistics

        segment_geodata[
            scenario_name
        ] = attach_statistics_to_segments(
            analysis_segments=analysis_segments,
            statistics=statistics,
            scenario_name=scenario_name,
            flow_thresholds=flow_thresholds,
        )

        used_segments = len(
            statistics
        )
        supported = statistics.loc[
            statistics[
                "sufficient_flow"
            ]
        ]

        print(
            f"\n{scenario_name}: "
            f"{_format_int_pt(used_segments)} segmentos usados"
        )
        print(
            "  H_soc — todos os segmentos usados: "
            "média="
            f"{_format_float_pt(statistics['H_soc'].mean(), decimals=3)} | "
            "mediana="
            f"{_format_float_pt(statistics['H_soc'].median(), decimals=3)}"
        )
        print(
            "  Segmentos com fluxo suficiente "
            f"(n_agents >= {min_agents_for_interpretation}): "
            f"{_format_int_pt(len(supported))} segmentos"
        )

        if not supported.empty:
            print(
                "  H_soc — fluxo suficiente: "
                "média="
                f"{_format_float_pt(supported['H_soc'].mean(), decimals=3)} | "
                "mediana="
                f"{_format_float_pt(supported['H_soc'].median(), decimals=3)}"
            )

        threshold_counts = {
            threshold: int(
                (
                    statistics[
                        "n_agents"
                    ]
                    >= threshold
                ).sum()
            )
            for threshold in flow_thresholds
        }

        print(
            "  Sensibilidade por n_agents: "
            + " | ".join(
                f">={threshold}: {_format_int_pt(count)} segmentos"
                for threshold, count
                in threshold_counts.items()
            )
        )

    print("\n9/12 - Comparando cenários de forma pareada...")

    statistics_all = pd.concat(
        segment_statistics.values(),
        ignore_index=True,
    )

    paired_comparison = build_scenario_comparison(
        statistics=statistics_all,
        baseline_name=SCENARIOS[0],
        differentiated_name=SCENARIOS[1],
        min_agents_for_interpretation=(
            min_agents_for_interpretation
        ),
        flow_thresholds=flow_thresholds,
    )

    paired_comparison_geodata = attach_comparison_to_segments(
        analysis_segments=analysis_segments,
        comparison=paired_comparison,
    )

    paired_summary = comparison_summary(
        paired_comparison,
        min_agents_for_interpretation=(
            min_agents_for_interpretation
        ),
        flow_thresholds=flow_thresholds,
    )

    print(
        "\nComparabilidade espacial entre cenários"
    )
    print(
        "  Segmentos usados em pelo menos um cenário: "
        f"{_format_int_pt(paired_summary['segments_union'])} segmentos"
    )
    print(
        "  Usados nos dois cenários: "
        f"{_format_int_pt(paired_summary['used_both'])} segmentos"
    )
    print(
        "  Apenas baseline: "
        f"{_format_int_pt(paired_summary['baseline_only'])} segmentos"
    )
    print(
        "  Apenas differentiated: "
        f"{_format_int_pt(paired_summary['differentiated_only'])} segmentos"
    )
    print(
        "  Delta H_soc pareado — todos os segmentos usados nos dois: "
        "média="
        f"{_format_float_pt(paired_summary['paired_delta_H_soc_mean'], decimals=3)} | "
        "mediana="
        f"{_format_float_pt(paired_summary['paired_delta_H_soc_median'], decimals=3)}"
    )
    print(
        "  Segmentos com fluxo suficiente nos dois cenários "
        f"(n_agents >= {min_agents_for_interpretation}): "
        f"{_format_int_pt(paired_summary['sufficient_flow_both'])} segmentos"
    )

    if paired_summary[
        "sufficient_flow_both"
    ] > 0:
        print(
            "  Delta H_soc pareado — fluxo suficiente nos dois: "
            "média="
            f"{_format_float_pt(paired_summary['sufficient_delta_H_soc_mean'], decimals=3)} | "
            "mediana="
            f"{_format_float_pt(paired_summary['sufficient_delta_H_soc_median'], decimals=3)}"
        )

    print(
        "  Sensibilidade pareada por n_agents: "
        + " | ".join(
            (
                f">={threshold}: "
                f"{_format_int_pt(paired_summary[f'flow_ge_{threshold}_both'])} segmentos"
            )
            for threshold in flow_thresholds
        )
    )

    print("\n10/12 - Gerando mapas espaciais...")

    if maps_enabled:
        try:
            from src.analysis.pilot_maps import save_pilot_maps
        except ModuleNotFoundError as error:
            if error.name == "matplotlib":
                raise RuntimeError(
                    "Instala a dependência matplotlib no ambiente virtual "
                    "com 'python -m pip install matplotlib' ou executa "
                    "'python -m pip install -r requirements.txt'"
                ) from error

            raise

        map_manifest = save_pilot_maps(
            segment_geodata=segment_geodata,
            scenario_comparison_geodata=(
                paired_comparison_geodata
            ),
            output_dir=(
                OUTPUT_DIR
                / "maps"
            ),
            dpi=maps_dpi,
        )

        print(
            "  Mapas gerados: "
            f"{_format_int_pt(len(map_manifest))} mapas"
        )
        print(
            "  Diretório: "
            f"{(OUTPUT_DIR / 'maps').resolve()}"
        )

        for row in map_manifest.itertuples(
            index=False
        ):
            print(
                f"  {row.map_id}: "
                f"{_format_int_pt(row.n_segments_plotted)} segmentos destacados"
            )
    else:
        print(
            "  Geração de mapas desativada em analysis.maps.enabled"
        )

    print("\n11/12 - Validando e salvando resultados...")

    _validate_fixed_population(summaries)
    _save_outputs(
        summaries=summaries,
        routed_edge_usages=(
            routed_edge_usages
        ),
        edge_usages=edge_usages,
        harmonized_edge_usages=harmonized_edge_usages,
        analysis_segments=analysis_segments,
        segment_mapping=segment_mapping,
        match_report=match_report,
        used_match_report=used_match_report,
        segment_statistics=segment_statistics,
        segment_geodata=segment_geodata,
        scenario_comparison=paired_comparison,
        scenario_comparison_geodata=paired_comparison_geodata,
        scenario_comparison_summary=paired_summary,
        transit_mapping=transit_mapping,
        transit_match_diagnostics=(
            transit_match_diagnostics
        ),
        transit_physical_summary=(
            transit_physical_summary
        ),
    )

    print("\n=== TESTE FINAL ===")
    print(
        "OK: baseline e differentiated usam os mesmos agentes, "
        "grupos de renda e origens residenciais."
    )
    print(
        "As diferenças entre cenários são introduzidas apenas "
        "nas regras de propósito, destino e modo."
    )
    print(
        "Modos disponíveis na escolha modal: "
        + ", ".join(
            choice_modes
        )
    )
    print(
        "Roteamento viário: shortest path por "
        f"'{routing_weight}' para walk, bike e car"
    )
    print(
        "Roteamento transit: GTFS temporal com acesso e egresso pela rede "
        f"walk na data {transit_service_date} e partida fixa em "
        f"{_format_float_pt(transit_departure_time_s / 3600, decimals=2)} h"
    )
    print(
        "Rede física transit: construída a partir de todo o GTFS espacialmente "
        "roteável antes da amostra de agentes; trechos sem correspondência OSM "
        "recebem analysis_segment_id exclusivo"
    )
    print(
        "H_soc: entropia de Shannon normalizada da composição "
        "dos agentes por grupo de renda."
    )
    print(
        "Interprete H_soc junto com n_agents e sufficient_flow; "
        "não trate ausência de fluxo como H_soc=0."
    )
    print(
        "Compare os cenários pelo mesmo analysis_segment_id; "
        "não compare médias de subconjuntos espaciais diferentes como se "
        "fossem uma diferença pareada."
    )
    print(
        "Interprete delta_H_soc apenas como mudança de diversidade "
        "socioeconômica observada, sem atribuir melhora ou piora."
    )
    print(
        "A escolha modal aplica resposta provisória à distância OD "
        "antes do roteamento e mantém os mesmos parâmetros nos dois cenários."
    )

    print(
        "\n12/12 - Atualizando documentação metodológica..."
    )

    from src.reporting.exportPilotMetadata import (
        export_pilot_metadata,
    )

    metadata_paths = export_pilot_metadata(
        project_root=PROJECT_ROOT
    )

    print(
        "Metadados do piloto salvos em:"
    )
    print(
        "  XLSX: "
        f"{metadata_paths['xlsx']}"
    )
    print(
        "  HTML: "
        f"{metadata_paths['html']}"
    )
    print(
        f"Resultados salvos em: {OUTPUT_DIR.resolve()}"
    )


if __name__ == "__main__":
    main()
