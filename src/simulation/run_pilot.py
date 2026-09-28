"""
Executa o pipeline piloto do EtPilot até a escolha modal

Fluxo:
1. carrega configurações;
2. carrega origens e destinos;
3. gera população sintética;
4. atribui origens;
5. atribui razão de deslocamento (proposito);
6. atribui destinos;
7. atribui modo de transporte;
8. imprime um resumo.

Uso:
    python -m src.simulation.run_pilot
"""

from __future__ import annotations

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


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
CONFIG_AGENTS_PATH = PROJECT_ROOT / "config" / "config_agents.json"

N_AGENTS = 100
SEED = 42
MODE_SCENARIO = "differentiated"


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    config = load_json(CONFIG_PATH)
    config_agents = load_json(CONFIG_AGENTS_PATH)

    origins_path = PROJECT_ROOT / config["paths"]["origins_income"]
    destinations_path = PROJECT_ROOT / config["paths"]["destinations"]

    print("1/7 - Carregando dados...")

    origins = gpd.read_file(origins_path)

    destinations = gpd.read_file(
        destinations_path,
        layer="destinations",
    )

    print("2/7 - Gerando população...")

    income_shares = {
        IncomeGroup(group_name): group_data["share"]
        for group_name, group_data
        in config["income"]["groups"].items()
    }

    agents = generate_population(
        n_agents=N_AGENTS,
        income_shares=income_shares,
        seed=SEED,
    )

    print(f"Agentes gerados: {len(agents)}")

    print("3/7 - Atribuindo origens...")

    agents = assign_origins(
        agents=agents,
        origins=origins,
        population_column="POP",
        seed=SEED,
    )

    print(
        "Agentes com origem:",
        sum(agent.origin_id is not None for agent in agents),
    )

    print(
        "Agentes com origin_node:",
        sum(agent.origin_node is not None for agent in agents),
    )

    print("4/7 - Atribuindo propósitos...")

    agents = assign_purpose(
        agents=agents,
        purpose_probabilities=config_agents["purpose_choice"],
        seed=SEED,
    )

    print(
        "Agentes com propósito:",
        sum(agent.purpose is not None for agent in agents),
    )

    print("5/7 - Escolhendo destinos...")

    agents = assign_destinations(
        agents=agents,
        origins=origins,
        destinations=destinations,
        choice_config=config_agents["destination_choice"],
        seed=SEED,
        max_trip_distance_m=config["analysis"]["max_trip_distance"],
    )

    print(
        "Agentes com destino:",
        sum(agent.destination_id is not None for agent in agents),
    )

    print(
        "Agentes com destination_node:",
        sum(agent.destination_node is not None for agent in agents),
    )

    print("6/7 - Escolhendo modos...")

    rng = np.random.default_rng(SEED)

    available_modes = {
        TravelMode.WALK,
        TravelMode.BIKE,
        TravelMode.TRANSIT,
        TravelMode.CAR,
    }

    mode_config = config_agents["mode_choice"][MODE_SCENARIO]

    for agent in agents:
        agent.mode = choose_mode(
            agent=agent,
            config=mode_config,
            rng=rng,
            available_modes=available_modes,
        )

    print(
        "Agentes com modo:",
        sum(agent.mode is not None for agent in agents),
    )

    print("7/7 - Resumo...")

    summary = destination_choice_summary(agents)

    summary["mode"] = [
        agent.mode.value if agent.mode is not None else None
        for agent in agents
    ]

    print("\n=== DISTRIBUIÇÃO POR RENDA ===")
    print(
        summary["income_group"]
        .value_counts()
        .sort_index()
    )

    print("\n=== DISTRIBUIÇÃO POR PROPÓSITO ===")
    print(
        summary["purpose"]
        .value_counts()
        .sort_index()
    )

    print("\n=== DISTRIBUIÇÃO POR MODO ===")
    print(
        summary["mode"]
        .value_counts()
        .sort_index()
    )

    print("\n=== RENDA x PROPÓSITO ===")
    print(
        pd.crosstab(
            summary["income_group"],
            summary["purpose"],
        )
    )

    print("\n=== RENDA x MODO ===")
    print(
        pd.crosstab(
            summary["income_group"],
            summary["mode"],
        )
    )

    print("\n=== PRIMEIROS 10 AGENTES ===")
    print(
        summary.head(10).to_string(index=False)
    )

    missing = {
        "origem": sum(agent.origin_id is None for agent in agents),
        "origin_node": sum(agent.origin_node is None for agent in agents),
        "propósito": sum(agent.purpose is None for agent in agents),
        "destino": sum(agent.destination_id is None for agent in agents),
        "destination_node": sum(
            agent.destination_node is None for agent in agents
        ),
        "modo": sum(agent.mode is None for agent in agents),
    }

    print("\n=== TESTE FINAL ===")

    if all(value == 0 for value in missing.values()):
        print(
            f"OK: os {len(agents)} agentes receberam "
            "origem, propósito, destino e modo."
        )
    else:
        print("ATENÇÃO: existem atributos ausentes:")
        for key, value in missing.items():
            if value:
                print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
