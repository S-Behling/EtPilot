import numpy as np

from src.domain.agent import Agent
from src.domain.enums import IncomeGroup


def generate_population(
    n_agents: int,
    income_shares: dict[IncomeGroup, float],
    seed: int = 42
) -> list[Agent]:
    """
    Gera uma população sintética de agentes respeitando
    as proporções socioeconômicas informadas.

    Parameters
    ----------
    n_agents : int
        Número total de agentes sintéticos.

    income_shares : dict[IncomeGroup, float]
        Proporção de cada grupo socioeconômico.
        As proporções devem somar 1.

    seed : int
        Semente utilizada para embaralhar os agentes
        de forma reproduzível.

    Returns
    -------
    list[Agent]
        Lista de agentes sintéticos.
    """

    if n_agents <= 0:
        raise ValueError(
            "n_agents deve ser maior que zero."
        )

    total_share = sum(
        income_shares.values()
    )

    if not np.isclose(
        total_share,
        1.0
    ):
        raise ValueError(
            "As proporções de renda devem somar 1."
        )

    # ---------------------------------------------------------
    # 1. Calcula a quantidade ideal de agentes por grupo
    # ---------------------------------------------------------

    expected_counts = {
        group: share * n_agents
        for group, share in income_shares.items()
    }

    # Parte inteira inicial
    counts = {
        group: int(np.floor(value))
        for group, value in expected_counts.items()
    }

    # ---------------------------------------------------------
    # 2. Distribui os agentes restantes
    # ---------------------------------------------------------

    remaining = (
        n_agents
        - sum(counts.values())
    )

    remainders = sorted(
        expected_counts.keys(),
        key=lambda group:
            expected_counts[group]
            - counts[group],
        reverse=True
    )

    for group in remainders[:remaining]:
        counts[group] += 1

    # ---------------------------------------------------------
    # 3. Cria os grupos
    # ---------------------------------------------------------

    population_groups = []

    for group, count in counts.items():

        population_groups.extend(
            [group] * count
        )

    # ---------------------------------------------------------
    # 4. Embaralha de forma reproduzível
    # ---------------------------------------------------------

    rng = np.random.default_rng(seed)

    rng.shuffle(
        population_groups
    )

    # ---------------------------------------------------------
    # 5. Cria os agentes
    # ---------------------------------------------------------

    agents = [
        Agent(
            agent_id=i,
            income_group=group
        )
        for i, group in enumerate(
            population_groups,
            start=1
        )
    ]

    return agents