"""
Executa o pipeline piloto do EtPilot até a escolha modal, comparando
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
2. gera a população sintética;
3. atribui origens residenciais;
4. constrói os cenários comportamentais;
5. executa baseline e differentiated;
6. valida atributos;
7. salva e compara os resultados.

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
from src.simulation.destination_choice import (
    assign_destinations,
    destination_choice_summary,
)
from src.simulation.mode_choice import choose_mode
from src.simulation.origin_assignment import assign_origins
from src.simulation.population import generate_population
from src.simulation.purpose_choice import assign_purpose
from src.simulation.scenarios import build_behavior_scenarios


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


def _validate_fixed_population(
    summaries: dict[str, pd.DataFrame],
) -> None:
    """
    Garante que população e residência sejam idênticas entre cenários.

    Propósito, destino e modo podem variar. Identidade, renda e origem não.
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

    origins_path = (
        PROJECT_ROOT
        / config["paths"]["origins_income"]
    )
    destinations_path = (
        PROJECT_ROOT
        / config["paths"]["destinations"]
    )

    print("1/6 - Carregando dados...")

    origins = gpd.read_file(origins_path)

    destinations = gpd.read_file(
        destinations_path,
        layer="destinations",
    )

    print("2/6 - Gerando população sintética...")

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

    print("3/6 - Atribuindo origens residenciais...")

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

    print("4/6 - Construindo cenários experimentais...")

    behavior_scenarios = build_behavior_scenarios(
        config_agents=config_agents,
        income_shares=income_shares,
    )

    summaries: dict[str, pd.DataFrame] = {}

    print("5/6 - Executando cenários...")

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

        missing = _validate_agents(agents)

        if any(missing.values()):
            raise RuntimeError(
                f"Cenário '{scenario_name}' possui "
                f"atributos ausentes: {missing}"
            )

        summary = _build_summary(
            agents=agents,
            scenario_name=scenario_name,
        )

        summaries[scenario_name] = summary

        _print_scenario_summary(
            scenario_name=scenario_name,
            summary=summary,
        )

    print("\n6/6 - Validando e salvando resultados...")

    _validate_fixed_population(summaries)
    _save_outputs(summaries)

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
    print(f"Resultados salvos em: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
