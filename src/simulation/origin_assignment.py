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
    """
    Atribui uma origem residencial a cada agente sintético.

    A origem é selecionada somente entre pontos pertencentes ao mesmo grupo
    socioeconômico do agente. A probabilidade de seleção é proporcional à
    população associada ao ponto.

    Os nós não são mais tratados como universais. Cada origem deve possuir
    uma coluna por modo, por exemplo: ``node_car``, ``node_walk`` e
    ``node_bike``. Esses valores são armazenados em
    ``agent.origin_nodes``. O ``agent.origin_node`` só é definido
    posteriormente, depois da escolha do modo.
    """

    if not agents:
        raise ValueError(
            "A lista de agentes está vazia."
        )

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

    missing_columns = (
        required_columns
        - set(origins.columns)
    )

    if missing_columns:
        raise ValueError(
            "Colunas ausentes na base de origens: "
            f"{sorted(missing_columns)}. "
            "Recalcule os nós multimodais antes de executar o piloto."
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

    for column in node_columns.values():
        origins[column] = pd.to_numeric(
            origins[column],
            errors="coerce",
        )

    valid_mask = (
        origins["income_group"].notna()
        & origins[population_column].notna()
        & (origins[population_column] > 0)
    )

    for column in node_columns.values():
        valid_mask &= origins[column].notna()

    valid_origins = origins[
        valid_mask
    ].copy()

    if valid_origins.empty:
        raise ValueError(
            "Nenhuma origem válida disponível."
        )

    rng = np.random.default_rng(seed)

    agents_by_group: dict[str, list[Agent]] = {}

    for agent in agents:
        group = agent.income_group.value

        agents_by_group.setdefault(
            group,
            [],
        ).append(agent)

    for group, group_agents in agents_by_group.items():
        group_origins = valid_origins[
            valid_origins["income_group"]
            == group
        ].reset_index(drop=True)

        if group_origins.empty:
            raise ValueError(
                "Nenhuma origem válida encontrada "
                f"para o grupo '{group}'."
            )

        weights = (
            group_origins[population_column]
            / group_origins[population_column].sum()
        )

        selected_positions = rng.choice(
            len(group_origins),
            size=len(group_agents),
            replace=True,
            p=weights.to_numpy(),
        )

        for agent, position in zip(
            group_agents,
            selected_positions,
        ):
            selected_origin = (
                group_origins.iloc[position]
            )

            agent.origin_id = (
                selected_origin["origin_id"]
            )

            agent.origin_nodes = {
                mode: int(
                    selected_origin[column]
                )
                for mode, column
                in node_columns.items()
            }

            # Só será definido após a escolha modal.
            agent.origin_node = None

    return agents
