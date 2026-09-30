"""Executa o pipeline piloto regional com roteamento multimodal completo.

Uso:
    python -m src.simulation.run_pilot --region city
    python -m src.simulation.run_pilot --region city --n-agents 100 --seed 42
"""

from __future__ import annotations

import argparse

import numpy as np

from src.core.config import (
    load_agent_config,
    load_project_config,
    project_path,
)
from src.domain.enums import IncomeGroup, TravelMode
from src.plot import (
    plot_agent_routes,
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
from src.spatial.regional_cache import load_regional_cache
from src.transit.regional import (
    load_regional_transit_cache,
    select_representative_service_date,
)
from src.transit.router import TransitRouter


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.n_agents <= 0:
        raise ValueError("--n-agents precisa ser maior que zero.")

    config = load_project_config()
    config_agents = load_agent_config()

    region_name = (
        args.region
        or config["study_area"]["default_region"]
    )

    print("1/10 - Carregando cache regional...")

    regional = load_regional_cache(
        config,
        region_name,
    )

    origins = regional.origins
    destinations = regional.destinations
    graphs = regional.graphs

    print(
        f"Região: {region_name} | "
        f"origens={len(origins):,} | "
        f"destinos={len(destinations):,}"
    )

    print("2/10 - Carregando transporte coletivo regional...")

    regional_transit = load_regional_transit_cache(
        config,
        region_name,
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

    income_shares = {
        IncomeGroup(group_name): group_data["share"]
        for group_name, group_data
        in config["income"]["groups"].items()
    }

    agents = generate_population(
        n_agents=args.n_agents,
        income_shares=income_shares,
        seed=args.seed,
    )

    print(f"Agentes gerados: {len(agents)}")

    print("4/10 - Atribuindo origens multimodais...")

    agents = assign_origins(
        agents=agents,
        origins=origins,
        population_column="POP",
        seed=args.seed,
    )

    print("5/10 - Atribuindo propósitos...")

    agents = assign_purpose(
        agents=agents,
        purpose_probabilities=config_agents["purpose_choice"],
        seed=args.seed,
    )

    print("6/10 - Escolhendo destinos...")

    agents = assign_destinations(
        agents=agents,
        origins=origins,
        destinations=destinations,
        choice_config=config_agents["destination_choice"],
        seed=args.seed,
        max_trip_distance_m=config["analysis"]["max_trip_distance"],
    )

    print("7/10 - Escolhendo modos...")

    rng = np.random.default_rng(args.seed)

    available_modes = {
        TravelMode.WALK,
        TravelMode.BIKE,
        TravelMode.CAR,
        TravelMode.TRANSIT,
    }

    mode_config = config_agents["mode_choice"][args.scenario]

    for agent in agents:
        agent.mode = choose_mode(
            agent=agent,
            config=mode_config,
            rng=rng,
            available_modes=available_modes,
        )
        agent.resolve_routing_nodes()

    print("8/10 - Roteando walk/bike/car/transit...")

    agents = route_pilot_agents(
        agents,
        graphs=graphs,
        transit_router=transit_router,
        transit_service_date=representative_date,
        transit_departure_time_s=int(
            transit_config["pilot_departure_time_s"]
        ),
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

    print("9/10 - Gerando resumos e plots...")

    choice_summary = destination_choice_summary(agents)
    choice_summary["mode"] = [
        agent.mode.value if agent.mode is not None else None
        for agent in agents
    ]

    route_summary = routing_summary(agents)

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
        / args.scenario
        / f"seed_{args.seed}"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    choice_summary.to_csv(
        output_dir / "agent_choices.csv",
        index=False,
    )
    route_summary.to_csv(
        output_dir / "routing_summary.csv",
        index=False,
    )

    fig, _ = plot_agent_routes(
        agents=agents,
        graphs=graphs,
        sample_size=min(100, len(agents)),
        title=(
            f"Rotas OSM — {region_name} — "
            f"{args.scenario}"
        ),
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
            f"{args.scenario}"
        ),
    )
    save_plot(
        fig,
        output_dir / "routes_transit.png",
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

    print(f"\nResultados salvos em: {output_dir}")


if __name__ == "__main__":
    main()
