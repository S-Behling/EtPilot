"""
Executa o pipeline piloto do EtPilot até o roteamento, comparando
dois cenários experimentais.

Desenho do experimento
----------------------
- A população sintética e as origens residenciais são geradas uma única vez.
- Os mesmos agentes e as mesmas origens são usados nos dois cenários.
- baseline:
    remove diferenças comportamentais entre grupos de renda;
- differentiated:
    preserva diferenças por renda em propósito, escolha de destino e modo.

Fluxo:
1. carrega configurações e dados;
2. carrega as redes de carro, caminhada e bicicleta;
3. gera a população sintética e atribui origens;
4. constrói os cenários comportamentais;
5. atribui propósito, destino e modo;
6. calcula a rota na rede correspondente ao modo;
7. valida, resume e salva os resultados.

Uso:
    python -m src.simulation.run_pilot
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from src.domain.enums import IncomeGroup, TravelMode
from src.network.multimodal import load_mode_graphs
from src.routing.multimodal_router import (
    SUCCESS_STATUSES,
    route_agents,
)
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


def _assign_modes(
    agents,
    mode_config: dict,
    seed: int,
    implemented_modes: list[str] | tuple[str, ...],
) -> None:
    rng = np.random.default_rng(seed)

    available_modes = {
        TravelMode(mode)
        for mode in implemented_modes
    }

    for agent in agents:
        agent.mode = choose_mode(
            agent=agent,
            config=mode_config,
            rng=rng,
            available_modes=available_modes,
        )

        agent.resolve_routing_nodes()


def _validate_agents(agents) -> dict[str, int]:
    return {
        "origem": sum(agent.origin_id is None for agent in agents),
        "origin_node": sum(agent.origin_node is None for agent in agents),
        "propósito": sum(agent.purpose is None for agent in agents),
        "destino": sum(agent.destination_id is None for agent in agents),
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

    # Persistência simples para inspeção e futura reconstrução do edge usage.
    summary["route_edges"] = [
        json.dumps(agent.route_edges)
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
    Garante que população e residência sejam idênticas entre cenários.

    Propósito, destino, modo e rota podem variar.
    Identidade, renda e origem residencial não.
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


def main() -> None:
    config = load_json(CONFIG_PATH)
    config_agents = load_json(CONFIG_AGENTS_PATH)

    implemented_modes = list(
        config["routing"]["implemented_modes"]
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

    origins_path = (
        PROJECT_ROOT
        / config["paths"]["origins_income"]
    )
    destinations_path = (
        PROJECT_ROOT
        / config["paths"]["destinations"]
    )

    print("1/7 - Carregando dados...")

    origins = gpd.read_file(origins_path)

    destinations = gpd.read_file(
        destinations_path,
        layer="destinations",
    )

    print("2/7 - Carregando redes modais...")

    graphs = load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
        modes=implemented_modes,
    )

    for mode, graph in graphs.items():
        print(
            f"  {mode}: "
            f"{len(graph.nodes):,} nós | "
            f"{len(graph.edges):,} arestas"
        )

    print("3/7 - Gerando população sintética...")

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

    print("4/7 - Atribuindo origens residenciais...")

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

    print("5/7 - Construindo cenários experimentais...")

    behavior_scenarios = build_behavior_scenarios(
        config_agents=config_agents,
        income_shares=income_shares,
    )

    summaries: dict[str, pd.DataFrame] = {}
    edge_usages: dict[str, pd.DataFrame] = {}

    print("6/7 - Executando cenários e roteamento...")

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

    print("\n7/7 - Validando e salvando resultados...")

    _validate_fixed_population(summaries)
    _save_outputs(
        summaries,
        edge_usages,
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
        + ". Transit permanece planejado para GTFS."
    )
    print(
        f"Roteamento: shortest path por '{routing_weight}'."
    )
    print(f"Resultados salvos em: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
