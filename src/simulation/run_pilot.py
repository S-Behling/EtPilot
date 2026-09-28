"""
Executa o pipeline piloto do EtPilot até a visualização espacial dos cenários

Preserva o mesmo conjunto de agentes e as mesmas origens residenciais nos
dois cenários, remove diferenças comportamentais por renda no baseline e
preserva diferenças de propósito, destino e modo no differentiated

O fluxo:
1. carrega configurações e dados
2. carrega as redes de carro, caminhada e bicicleta
3. gera a população sintética e atribui origens
4. constrói os cenários comportamentais
5. atribui propósito, destino e modo
6. calcula a rota na rede correspondente ao modo
7. harmoniza as arestas modais em segmentos físicos comuns
8. calcula volume, composição social e H_soc por segmento
9. compara baseline e differentiated de forma pareada por segmento
10. gera mapas comparáveis de H_soc e delta_H_soc
11. valida, resume e salva os resultados

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
    build_used_transit_connection_geometries,
    map_transit_connections_to_analysis_segments,
    summarize_transit_spatial_matching,
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
    print("\n" + "=" * 72)
    print(f"CENÁRIO: {scenario_name.upper()}")
    print("=" * 72)

    print("\nDistribuição por renda")
    print(
        summary["income_group"]
        .value_counts()
        .sort_index()
    )

    print("\nDistribuição por propósito")
    print(
        summary["purpose"]
        .value_counts()
        .sort_index()
    )

    print("\nDistribuição por modo")
    print(
        summary["mode"]
        .value_counts()
        .sort_index()
    )

    print("\nRenda x propósito")
    print(
        pd.crosstab(
            summary["income_group"],
            summary["purpose"],
        )
    )

    print("\nRenda x modo")
    print(
        pd.crosstab(
            summary["income_group"],
            summary["mode"],
        )
    )

    print("\nStatus do roteamento")
    print(
        summary["route_status"]
        .value_counts(dropna=False)
        .sort_index()
    )

    successful = summary[
        summary["route_status"].isin(
            SUCCESS_STATUSES
        )
    ]

    if not successful.empty:
        print("\nDistância euclidiana OD por modo (m)")
        print(
            successful
            .groupby("mode")["od_distance_m"]
            .agg(["count", "mean", "median", "min", "max"])
            .round(1)
        )

        print("\nDistância das rotas bem-sucedidas por modo (m)")
        print(
            successful
            .groupby("mode")["travel_distance_m"]
            .agg(["count", "mean", "median", "min", "max"])
            .round(1)
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
    transit_geometry_diagnostics: pd.DataFrame,
    transit_match_diagnostics: pd.DataFrame,
    transit_spatial_summary: dict,
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
        / "transit_connection_to_analysis_segment.csv",
        index=False,
        encoding="utf-8",
    )

    transit_geometry_diagnostics.to_csv(
        OUTPUT_DIR
        / "transit_connection_geometry_diagnostics.csv",
        index=False,
        encoding="utf-8",
    )

    transit_match_diagnostics.to_csv(
        OUTPUT_DIR
        / "transit_connection_match_diagnostics.csv",
        index=False,
        encoding="utf-8",
    )

    pd.DataFrame(
        [
            transit_spatial_summary,
        ]
    ).to_csv(
        OUTPUT_DIR
        / "transit_spatial_match_report.csv",
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
    transit_tolerance_m = float(
        transit_spatial_config[
            "tolerance_m"
        ]
    )
    transit_min_segment_coverage = float(
        transit_spatial_config[
            "min_segment_coverage"
        ]
    )
    transit_max_angle_difference_deg = float(
        transit_spatial_config[
            "max_angle_difference_deg"
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

    transit_connections = pd.read_parquet(
        gtfs_data_dir
        / transit_network_config[
            "routable_connections_file"
        ]
    )

    transit_shapes = gpd.read_file(
        gtfs_data_dir
        / "shapes_processed.gpkg",
        layer="shapes_processed",
        engine="pyogrio",
    )

    print(
        "  transit: "
        f"{_format_int_pt(len(transit_connections))} conexões GTFS roteáveis | "
        f"data de serviço {transit_service_date} | "
        f"partida fixa {transit_departure_time_s / 3600:.2f} h"
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

    print(f"Agentes gerados: {len(base_agents)}")

    print("4/12 - Atribuindo origens residenciais...")

    base_agents = assign_origins(
        agents=base_agents,
        origins=origins,
        population_column="POP",
        seed=SEED,
        modes=implemented_modes,
        node_prefix=node_prefix,
    )

    print(
        "Agentes com origem:",
        sum(
            agent.origin_id is not None
            for agent in base_agents
        ),
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
            implemented_modes=implemented_modes,
        )

        agents = route_agents(
            agents=agents,
            graphs=graphs,
            weight=routing_weight,
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

        edge_usage = build_edge_usage(
            agents=agents,
            graphs=graphs,
            scenario_name=scenario_name,
        )

        edge_usages[scenario_name] = edge_usage

        _print_scenario_summary(
            scenario_name=scenario_name,
            summary=summary,
        )

        print(
            "\nUso das arestas: "
            f"{len(edge_usage):,} passagens agente×aresta | "
            f"{edge_usage['modal_edge_id'].nunique():,} "
            "arestas modais únicas"
        )

    print("\n7/11 - Harmonizando segmentos físicos de análise...")

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
        f"{len(analysis_segments):,}"
    )
    print(
        "Arestas modais harmonizadas: "
        f"{segment_mapping['modal_edge_id'].nunique():,}"
    )

    print("\nMétodos de harmonização — redes completas")
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

    print("\n8/11 - Calculando estatísticas e entropia socioeconômica...")

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
            f"{used_segments:,} segmentos usados"
        )
        print(
            "  H_soc — todos os segmentos usados: "
            f"média={statistics['H_soc'].mean():.3f} | "
            f"mediana={statistics['H_soc'].median():.3f}"
        )
        print(
            "  Segmentos com fluxo suficiente "
            f"(n_agents >= {min_agents_for_interpretation}): "
            f"{len(supported):,}"
        )

        if not supported.empty:
            print(
                "  H_soc — fluxo suficiente: "
                f"média={supported['H_soc'].mean():.3f} | "
                f"mediana={supported['H_soc'].median():.3f}"
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
                f">={threshold}: {count:,}"
                for threshold, count
                in threshold_counts.items()
            )
        )

    print("\n9/11 - Comparando cenários de forma pareada...")

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
        f"{paired_summary['segments_union']:,}"
    )
    print(
        "  Usados nos dois cenários: "
        f"{paired_summary['used_both']:,}"
    )
    print(
        "  Apenas baseline: "
        f"{paired_summary['baseline_only']:,}"
    )
    print(
        "  Apenas differentiated: "
        f"{paired_summary['differentiated_only']:,}"
    )
    print(
        "  Delta H_soc pareado — todos os segmentos usados nos dois: "
        f"média={paired_summary['paired_delta_H_soc_mean']:.3f} | "
        f"mediana={paired_summary['paired_delta_H_soc_median']:.3f}"
    )
    print(
        "  Segmentos com fluxo suficiente nos dois cenários "
        f"(n_agents >= {min_agents_for_interpretation}): "
        f"{paired_summary['sufficient_flow_both']:,}"
    )

    if paired_summary[
        "sufficient_flow_both"
    ] > 0:
        print(
            "  Delta H_soc pareado — fluxo suficiente nos dois: "
            f"média={paired_summary['sufficient_delta_H_soc_mean']:.3f} | "
            f"mediana={paired_summary['sufficient_delta_H_soc_median']:.3f}"
        )

    print(
        "  Sensibilidade pareada por n_agents: "
        + " | ".join(
            (
                f">={threshold}: "
                f"{paired_summary[f'flow_ge_{threshold}_both']:,}"
            )
            for threshold in flow_thresholds
        )
    )

    print("\n10/11 - Gerando mapas espaciais...")

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
            f"{len(map_manifest):,}"
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
                f"{row.n_segments_plotted:,} segmentos destacados"
            )
    else:
        print(
            "  Geração de mapas desativada em analysis.maps.enabled"
        )

    print("\n11/11 - Validando e salvando resultados...")

    _validate_fixed_population(summaries)
    _save_outputs(
        summaries=summaries,
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
        "Modos roteáveis nesta etapa: "
        + ", ".join(implemented_modes)
        + ". Transit possui dados GTFS preparados, mas ainda não entra "
        "no roteamento do run_pilot."
    )
    print(
        f"Roteamento: shortest path por '{routing_weight}'."
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
