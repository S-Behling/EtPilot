import numpy as np
import pandas as pd

from src.domain.agent import Agent


def assign_origins(
    agents: list[Agent],
    origins,
    population_column: str = "POP",
    seed: int = 42,
    modes: tuple[str, ...] | list[str] = ("walk", "bike", "car"),
    node_prefix: str = "node_",
) -> list[Agent]:
    """Atribui origens e preserva os nós específicos por modo."""

    if not agents:
        raise ValueError("A lista de agentes está vazia.")

    node_columns = {
        mode: f"{node_prefix}{mode}"
        for mode in modes
    }

    required_columns = {
        "origin_id",
        "income_group",
        population_column,
        *node_columns.values(),
    }

    missing = required_columns - set(origins.columns)

    if missing:
        raise ValueError(
            "Colunas ausentes na base de origens: "
            f"{sorted(missing)}"
        )

    origins = origins.copy()

    origins["income_group"] = (
        origins["income_group"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    origins[population_column] = pd.to_numeric(
        origins[population_column],
        errors="coerce",
    )

    valid = (
        origins["income_group"].notna()
        & origins[population_column].notna()
        & (origins[population_column] > 0)
    )

    for column in node_columns.values():
        origins[column] = pd.to_numeric(
            origins[column],
            errors="coerce",
        )
        valid &= origins[column].notna()

    valid_origins = origins.loc[valid].copy()

    if valid_origins.empty:
        raise ValueError("Nenhuma origem válida disponível.")

    rng = np.random.default_rng(seed)
    agents_by_group: dict[str, list[Agent]] = {}

    for agent in agents:
        agents_by_group.setdefault(
            agent.income_group.value,
            [],
        ).append(agent)

    for group, group_agents in agents_by_group.items():
        group_origins = valid_origins.loc[
            valid_origins["income_group"] == group
        ].reset_index(drop=True)

        if group_origins.empty:
            raise ValueError(
                f"Nenhuma origem válida encontrada para '{group}'."
            )

        weights = (
            group_origins[population_column]
            / group_origins[population_column].sum()
        )

        selected = rng.choice(
            len(group_origins),
            size=len(group_agents),
            replace=True,
            p=weights.to_numpy(),
        )

        for agent, position in zip(group_agents, selected):
            row = group_origins.iloc[position]

            agent.origin_id = row["origin_id"]
            agent.origin_nodes = {
                mode: int(row[column])
                for mode, column in node_columns.items()
            }
            agent.origin_node = None

    return agents
