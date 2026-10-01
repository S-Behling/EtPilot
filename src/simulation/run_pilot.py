"""Executa o pipeline piloto regional com roteamento multimodal completo.

Uso:
    python -m src.simulation.run_pilot --region city
    python -m src.simulation.run_pilot --region city --n-agents 100 --seed 42
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.core.config import (
    load_agent_config,
    load_project_config,
    project_path,
)
from src.domain.enums import IncomeGroup, TravelMode
from src.pipeline.config import (
    PilotRunConfig,
    SimulationPeriod,
)
from src.plot import (
    plot_agent_routes,
    plot_edge_usage,
    plot_edge_usage_by_category,
    plot_transit_agent_routes,
    save_plot,
)
from src.routing.multimodal_router import routing_summary
from src.routing.pilot_router import route_pilot_agents
from src.simulation.destination_choice import (
    assign_destinations,
    destination_choice_summary,
)
from src.simulation.mode_choice import choose_mode
from src.simulation.origin_assignment import assign_origins
from src.simulation.population import generate_population
from src.simulation.purpose_choice import assign_purpose
from src.spatial.area_loader import load_study_area
from src.spatial.regional_cache import load_regional_cache
from src.transit.regional import (
    load_regional_transit_cache,
    select_representative_service_date,
)
from src.transit.router import TransitRouter
from src.trajectory.edge_usage import (
    aggregate_edge_usage,
    build_edge_usage,
    edge_composition_summary,
)


DEFAULT_N_AGENTS = 100
DEFAULT_SEED = 42
DEFAULT_MODE_SCENARIO = "differentiated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa o piloto regional do EtPilot."
    )
    parser.add_argument(
        "--region",
        default=None,
        help="Região já preparada em cache/regions.",
    )
    parser.add_argument(
        "--region-mode",
        choices=("analysis", "plot_only"),
        default="analysis",
        help=(
            "analysis restringe O/D/agentes/redes à região; "
            "plot_only usa dados municipais e limita apenas os mapas."
        ),
    )
    parser.add_argument(
        "--n-agents",
        type=int,
        default=DEFAULT_N_AGENTS,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
    )
    parser.add_argument(
        "--scenario",
        default=DEFAULT_MODE_SCENARIO,
        choices=("baseline", "differentiated"),
    )
    parser.add_argument(
        "--income",
        nargs="+",
        default=["low", "middle", "high"],
        choices=("low", "middle", "high"),
        help="Classes sociais incluídas na população sintética.",
    )
    parser.add_argument(
        "--period-value",
        type=int,
        default=24,
        help="Duração da janela temporal.",
    )
    parser.add_argument(
        "--period-unit",
        choices=("hours", "days"),
        default="hours",
        help="Unidade da janela temporal.",
    )
    return parser.parse_args()


def _income_shares_for_selection(
    config: dict,
    selected_groups: tuple[IncomeGroup, ...],
) -> dict[IncomeGroup, float]:
    raw = {
        group: float(
            config["income"]["groups"][group.value]["share"]
        )
        for group in selected_groups
    }

    total = sum(raw.values())

    if total <= 0:
        raise ValueError(
            "As classes sociais selecionadas não possuem participação válida."
        )

    return {
        group: share / total
        for group, share in raw.items()
    }


def _build_transit_departures(
    *,
    agents,
    start_date,
    start_time_s: int,
    total_hours: int,
    seed: int,
) -> dict[int, tuple[pd.Timestamp, int]]:
    rng = np.random.default_rng(seed)
    horizon_s = int(total_hours * 3600)

    offsets = rng.integers(
        low=0,
        high=max(horizon_s, 1),
        size=len(agents),
    )

    schedule = {}

    for agent, offset_s in zip(agents, offsets):
        absolute_s = int(start_time_s) + int(offset_s)
        day_offset, departure_s = divmod(
            absolute_s,
            24 * 3600,
        )

        service_date = (
            pd.Timestamp(start_date).normalize()
            + pd.Timedelta(days=int(day_offset))
        )

        schedule[agent.agent_id] = (
            service_date,
            int(departure_s),
        )

    return schedule


def run_pilot(run_config: PilotRunConfig) -> None:
    config = load_project_config()
    config_agents = load_agent_config()

    region_name = run_config.region
    data_region_name = (
        region_name
        if run_config.region_mode == "analysis"
        else "city"
    )
    view_area = load_study_area(
        region_name,
        config=config,
    )

    print("1/10 - Carregando cache espacial...")

    regional = load_regional_cache(
        config,
        data_region_name,
    )

    origins = regional.origins
    destinations = regional.destinations
    graphs = regional.graphs

    print(
        f"Região selecionada: {region_name} | "
        f"modo={run_config.region_mode} | "
        f"dados={data_region_name} | "
        f"origens={len(origins):,} | "
        f"destinos={len(destinations):,}"
    )

    print("2/10 - Carregando transporte coletivo regional...")

    regional_transit = load_regional_transit_cache(
        config,
        data_region_name,
    )

    representative_date = (
        select_representative_service_date(
            regional_transit
        )
    )

    transit_config = config["transit"]["routing"]

    transit_router = TransitRouter(
        walk_graph=graphs["walk"],
        connectors=regional_transit.connectors,
        connections=regional_transit.connections,
        service_dates=regional_transit.service_dates,
        walk_speed_m_s=float(
            transit_config["walk_speed_m_s"]
        ),
        max_access_walk_m=float(
            transit_config["max_access_walk_m"]
        ),
        max_egress_walk_m=float(
            transit_config["max_egress_walk_m"]
        ),
        minimum_transfer_time_s=int(
            transit_config["minimum_transfer_time_s"]
        ),
        max_total_travel_time_s=int(
            transit_config["max_total_travel_time_s"]
        ),
    )

    print(
        "Data GTFS representativa:",
        representative_date.date().isoformat(),
    )

    print("3/10 - Gerando população...")

    income_shares = _income_shares_for_selection(
        config,
        run_config.income_groups,
    )

    agents = generate_population(
        n_agents=run_config.n_agents,
        income_shares=income_shares,
        seed=run_config.seed,
    )

    print(f"Agentes gerados: {len(agents)}")

    print("4/10 - Atribuindo origens multimodais...")

    agents = assign_origins(
        agents=agents,
        origins=origins,
        population_column="POP",
        seed=run_config.seed,
    )

    print("5/10 - Atribuindo propósitos...")

    agents = assign_purpose(
        agents=agents,
        purpose_probabilities=config_agents["purpose_choice"],
        seed=run_config.seed,
    )

    print("6/10 - Escolhendo destinos...")

    agents = assign_destinations(
        agents=agents,
        origins=origins,
        destinations=destinations,
        choice_config=config_agents["destination_choice"],
        seed=run_config.seed,
        max_trip_distance_m=config["analysis"]["max_trip_distance"],
    )

    print("7/10 - Escolhendo modos...")

    rng = np.random.default_rng(run_config.seed)

    available_modes = {
        TravelMode.WALK,
        TravelMode.BIKE,
        TravelMode.CAR,
        TravelMode.TRANSIT,
    }

    mode_config = config_agents["mode_choice"][run_config.scenario]

    for agent in agents:
        agent.mode = choose_mode(
            agent=agent,
            config=mode_config,
            rng=rng,
            available_modes=available_modes,
        )
        agent.resolve_routing_nodes()

    print("8/10 - Roteando walk/bike/car/transit...")

    transit_departures = _build_transit_departures(
        agents=agents,
        start_date=representative_date,
        start_time_s=int(
            transit_config["pilot_departure_time_s"]
        ),
        total_hours=run_config.period.total_hours,
        seed=run_config.seed,
    )

    agents = route_pilot_agents(
        agents,
        graphs=graphs,
        transit_router=transit_router,
        transit_departures=transit_departures,
        weight=config["routing"].get(
            "weight",
            "length",
        ),
        strict=bool(
            config["routing"].get(
                "strict",
                False,
            )
        ),
    )

    print("9/10 - Gerando uso de arestas, resumos e plots...")

    choice_summary = destination_choice_summary(agents)
    choice_summary["mode"] = [
        agent.mode.value if agent.mode is not None else None
        for agent in agents
    ]

    route_summary = routing_summary(agents)

    edge_usage = build_edge_usage(
        agents,
        transit_connection_to_physical_edge=(
            regional_transit.connection_to_physical_edge
        ),
    )
    edge_usage_summary = aggregate_edge_usage(
        edge_usage
    )
    edge_composition = edge_composition_summary(
        edge_usage
    )

    transit_by_agent = {
        agent.agent_id: agent
        for agent in agents
    }

    route_summary["travel_time_s"] = route_summary[
        "agent_id"
    ].map(
        lambda agent_id: transit_by_agent[
            agent_id
        ].travel_time
    )
    route_summary["transit_n_transfers"] = route_summary[
        "agent_id"
    ].map(
        lambda agent_id: transit_by_agent[
            agent_id
        ].transit_n_transfers
    )
    route_summary["transit_access_stop_id"] = route_summary[
        "agent_id"
    ].map(
        lambda agent_id: transit_by_agent[
            agent_id
        ].transit_access_stop_id
    )
    route_summary["transit_egress_stop_id"] = route_summary[
        "agent_id"
    ].map(
        lambda agent_id: transit_by_agent[
            agent_id
        ].transit_egress_stop_id
    )

    output_dir = (
        project_path(config["paths"]["outputs"])
        / "pilot"
        / region_name
        / run_config.region_mode
        / run_config.scenario
        / f"seed_{run_config.seed}"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    choice_summary.to_csv(
        output_dir / "agent_choices.csv",
        index=False,
    )

    metadata = {
        "region": run_config.region,
        "region_mode": run_config.region_mode,
        "data_region": data_region_name,
        "income_groups": list(
            run_config.income_group_names
        ),
        "period": {
            "value": run_config.period.value,
            "unit": run_config.period.unit,
            "total_hours": run_config.period.total_hours,
        },
        "n_agents": run_config.n_agents,
        "seed": run_config.seed,
        "scenario": run_config.scenario,
        "gtfs_start_date": (
            representative_date.date().isoformat()
        ),
        "pilot_departure_time_s": int(
            transit_config["pilot_departure_time_s"]
        ),
    }

    with (
        output_dir / "run_config.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            indent=2,
            ensure_ascii=False,
        )
    route_summary.to_csv(
        output_dir / "routing_summary.csv",
        index=False,
    )
    edge_usage.to_csv(
        output_dir / "edge_usage.csv",
        index=False,
    )
    edge_usage_summary.to_csv(
        output_dir / "edge_usage_summary.csv",
        index=False,
    )
    edge_composition.to_csv(
        output_dir / "edge_composition.csv",
        index=False,
    )

    fig, _ = plot_agent_routes(
        agents=agents,
        graphs=graphs,
        sample_size=min(100, len(agents)),
        title=(
            f"Rotas OSM — {region_name} — "
            f"{run_config.region_mode} — "
            f"{run_config.scenario}"
        ),
        study_area=view_area,
    )
    save_plot(
        fig,
        output_dir / "routes_osm.png",
    )

    fig, _ = plot_transit_agent_routes(
        agents=agents,
        walk_graph=graphs["walk"],
        physical_edges=regional_transit.physical_edges,
        connection_to_physical_edge=(
            regional_transit.connection_to_physical_edge
        ),
        sample_size=min(50, len(agents)),
        title=(
            f"Rotas transit — {region_name} — "
            f"{run_config.region_mode} — "
            f"{run_config.scenario}"
        ),
        study_area=view_area,
    )
    save_plot(
        fig,
        output_dir / "routes_transit.png",
    )

    if not edge_usage.empty:
        fig, _ = plot_edge_usage(
            edge_usage=edge_usage,
            graphs=graphs,
            transit_physical_edges=(
                regional_transit.physical_edges
            ),
            title=(
                f"Uso das redes — {region_name} — "
                f"{run_config.region_mode} — "
                f"{run_config.scenario}"
            ),
            study_area=view_area,
        )
        save_plot(
            fig,
            output_dir / "edge_usage.png",
        )

        fig, _ = plot_edge_usage_by_category(
            edge_usage=edge_usage,
            graphs=graphs,
            transit_physical_edges=(
                regional_transit.physical_edges
            ),
            category="trip_mode",
            study_area=view_area,
            title=(
                f"Trechos por modo de viagem — {region_name} — "
                f"{run_config.region_mode}"
            ),
        )
        save_plot(
            fig,
            output_dir / "edge_usage_by_mode.png",
        )

        fig, _ = plot_edge_usage_by_category(
            edge_usage=edge_usage,
            graphs=graphs,
            transit_physical_edges=(
                regional_transit.physical_edges
            ),
            category="income_group",
            study_area=view_area,
            title=(
                f"Trechos por classe social — {region_name} — "
                f"{run_config.region_mode}"
            ),
        )
        save_plot(
            fig,
            output_dir / "edge_usage_by_income.png",
        )

        edge_usage_mode_income = edge_usage.copy()
        edge_usage_mode_income["mode_income"] = (
            edge_usage_mode_income["trip_mode"].astype(str)
            + " | "
            + edge_usage_mode_income["income_group"].astype(str)
        )

        fig, _ = plot_edge_usage_by_category(
            edge_usage=edge_usage_mode_income,
            graphs=graphs,
            transit_physical_edges=(
                regional_transit.physical_edges
            ),
            category="mode_income",
            study_area=view_area,
            title=(
                f"Trechos por modo e classe social — {region_name} — "
                f"{run_config.region_mode}"
            ),
        )
        save_plot(
            fig,
            output_dir / "edge_usage_by_mode_income.png",
        )

    print("10/10 - Resumo final...")

    print("\n=== DISTRIBUIÇÃO POR RENDA ===")
    print(
        choice_summary["income_group"]
        .value_counts()
        .sort_index()
    )

    print("\n=== DISTRIBUIÇÃO POR PROPÓSITO ===")
    print(
        choice_summary["purpose"]
        .value_counts()
        .sort_index()
    )

    print("\n=== DISTRIBUIÇÃO POR MODO ===")
    print(
        choice_summary["mode"]
        .value_counts()
        .sort_index()
    )

    print("\n=== STATUS DO ROTEAMENTO ===")
    print(
        route_summary["route_status"]
        .value_counts(dropna=False)
        .sort_index()
    )

    transit_mask = (
        route_summary["mode"] == TravelMode.TRANSIT.value
    )

    if transit_mask.any():
        print("\n=== STATUS TRANSIT ===")
        print(
            route_summary.loc[
                transit_mask,
                "route_status",
            ]
            .value_counts(dropna=False)
            .sort_index()
        )

    print(
        "\nRegistros de uso de arestas:",
        len(edge_usage),
    )
    print(f"\nResultados salvos em: {output_dir}")


def main() -> None:
    args = parse_args()

    run_config = PilotRunConfig(
        region=(
            args.region
            or load_project_config()["study_area"]["default_region"]
        ),
        region_mode=args.region_mode,
        income_groups=tuple(
            IncomeGroup(value)
            for value in args.income
        ),
        period=SimulationPeriod(
            value=args.period_value,
            unit=args.period_unit,
        ),
        n_agents=args.n_agents,
        seed=args.seed,
        scenario=args.scenario,
        prepare_networks=False,
        prepare_region=False,
    )

    run_pilot(run_config)


if __name__ == "__main__":
    main()
