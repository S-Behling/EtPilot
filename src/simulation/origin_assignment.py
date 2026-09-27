import numpy as np
import pandas as pd

from src.domain.agent import Agent


def assign_origins(
    agents: list[Agent],
    origins,
    population_column: str = "POP",
    seed: int = 42,
) -> list[Agent]:
    """
    Atribui uma origem residencial a cada agente sintético

    A origem é selecionada somente entre pontos pertencentes
    ao mesmo grupo socioeconômico do agente. A probabilidade
    de seleção de cada origem é proporcional à população
    associada ao ponto.

    Parameters
    ----------
    agents : list[Agent]
        Lista de agentes sintéticos.

    origins
        GeoDataFrame contendo as origens disponíveis.

    population_column : str, default="POP"
        Coluna utilizada como peso populacional.

    seed : int, default=42
        Semente aleatória para garantir reprodutibilidade.

    Returns
    -------
    list[Agent]
        Lista de agentes com origin_id e origin_node atribuídos.

    -------
    
    Agent
    │
    ├── income_group = LOW
    │
    ▼
    filtra origens:
    income_group == "low"
    │
    ▼
    remove:
    POP <= 0
    node ausente
    grupo ausente
    │
    ▼
    calcula peso
    POP da origem / POP total do grupo
    │
    ▼
    sorteio
    │
    ▼
    origin_id
    origin_node
    """

    # ---------------------------------------------------------
    # 1. Validações básicas
    # ---------------------------------------------------------

    if not agents:
        raise ValueError(
            "A lista de agentes está vazia."
        )

    required_columns = {
        "origin_id",
        "node",
        "income_group",
        population_column,
    }

    missing_columns = (
        required_columns
        - set(origins.columns)
    )

    if missing_columns:
        raise ValueError(
            "Colunas ausentes na base de origens: "
            f"{sorted(missing_columns)}"
        )

    # Trabalhamos sobre uma cópia para não alterar
    # o GeoDataFrame original.
    origins = origins.copy()

    # ---------------------------------------------------------
    # 2. Padroniza os dados
    # ---------------------------------------------------------

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

    origins["node"] = pd.to_numeric(
        origins["node"],
        errors="coerce",
    )

    # ---------------------------------------------------------
    # 3. Remove origens que não podem participar do sorteio
    # ---------------------------------------------------------

    valid_origins = origins[
        origins["income_group"].notna()
        & origins["node"].notna()
        & origins[population_column].notna()
        & (origins[population_column] > 0)
    ].copy()

    if valid_origins.empty:
        raise ValueError(
            "Nenhuma origem válida disponível."
        )

    # ---------------------------------------------------------
    # 4. Gerador aleatório reproduzível
    # ---------------------------------------------------------

    rng = np.random.default_rng(seed)

    # ---------------------------------------------------------
    # 5. Separa os agentes por grupo de renda
    # ---------------------------------------------------------

    agents_by_group = {}

    for agent in agents:

        group = agent.income_group.value

        agents_by_group.setdefault(
            group,
            []
        ).append(agent)

    # ---------------------------------------------------------
    # 6. Sorteia as origens de cada grupo
    # ---------------------------------------------------------

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

        # Peso relativo de cada origem dentro do grupo.
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

        # -----------------------------------------------------
        # 7. Atualiza os agentes
        # -----------------------------------------------------

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

            agent.origin_node = int(
                selected_origin["node"]
            )

    return agents

