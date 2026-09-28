import numpy as np

from src.domain.agent import Agent
from src.domain.enums import IncomeGroup, TripPurpose


def _calculate_counts(
    n_agents: int,
    probabilities: dict[str, float],
) -> dict[str, int]:
    """
    Converte probabilidades em quantidades inteiras utilizando
    o método dos maiores restos.

    Garante que a soma das quantidades seja exatamente igual
    ao número de agentes.
    """

    purpose_names = list(probabilities.keys())

    expected_counts = np.array(
        [
            probabilities[purpose_name] * n_agents
            for purpose_name in purpose_names
        ],
        dtype=float,
    )

    # Parte inteira de cada quantidade esperada
    counts = np.floor(
        expected_counts
    ).astype(int)

    # Quantos agentes ainda faltam distribuir
    remaining = (
        n_agents
        - counts.sum()
    )

    # Parte decimal de cada quantidade
    fractional_parts = (
        expected_counts
        - counts
    )

    # Ordena pelos maiores restos
    priority = sorted(
        range(len(purpose_names)),
        key=lambda i: fractional_parts[i],
        reverse=True,
    )

    # Distribui os agentes restantes
    for index in priority[:remaining]:
        counts[index] += 1

    return {
        purpose_name: int(count)
        for purpose_name, count
        in zip(
            purpose_names,
            counts,
        )
    }


def assign_purpose(
    agents: list[Agent],
    purpose_probabilities: dict[str, dict[str, float]],
    seed: int = 42,
) -> list[Agent]:
    """
    Atribui motivos de viagem aos agentes de forma
    proporcional e controlada por grupo socioeconômico.

    As probabilidades determinam a composição de motivos
    dentro de cada grupo de renda.

    A aleatoriedade é utilizada apenas para determinar
    quais agentes individuais recebem cada motivo.

    Parameters
    ----------
    agents : list[Agent]
        Lista de agentes sintéticos.

    purpose_probabilities : dict[str, dict[str, float]]
        Probabilidades de motivo por grupo socioeconômico.

        Exemplo:
        {
            "low": {
                "work": 0.45,
                "education": 0.15,
                "shopping": 0.20,
                "health": 0.10,
                "leisure": 0.10
            }
        }

    seed : int, default=42
        Semente utilizada no embaralhamento dos motivos.

    Returns
    -------
    list[Agent]
        Agentes com purpose atribuído.
    """

    # ---------------------------------------------------------
    # 1. Validações básicas
    # ---------------------------------------------------------

    if not agents:
        raise ValueError(
            "A lista de agentes está vazia."
        )

    if not purpose_probabilities:
        raise ValueError(
            "As probabilidades de propósito não foram informadas."
        )

    valid_income_groups = {
        group.value
        for group in IncomeGroup
    }

    valid_purposes = {
        purpose.value
        for purpose in TripPurpose
    }

    # ---------------------------------------------------------
    # 2. Valida configuração
    # ---------------------------------------------------------

    for income_group, probabilities in (
        purpose_probabilities.items()
    ):

        if income_group not in valid_income_groups:
            raise ValueError(
                f"Grupo socioeconômico inválido: "
                f"'{income_group}'."
            )

        if not isinstance(
            probabilities,
            dict,
        ):
            raise TypeError(
                f"As probabilidades de '{income_group}' "
                "devem ser um dicionário."
            )

        for purpose_name, probability in (
            probabilities.items()
        ):

            if purpose_name not in valid_purposes:
                raise ValueError(
                    f"Motivo de viagem inválido: "
                    f"'{purpose_name}'."
                )

            if probability < 0:
                raise ValueError(
                    "As probabilidades não podem ser negativas."
                )

        total_probability = sum(
            probabilities.values()
        )

        if not np.isclose(
            total_probability,
            1.0,
        ):
            raise ValueError(
                f"As probabilidades do grupo "
                f"'{income_group}' devem somar 1. "
                f"Valor atual: {total_probability:.4f}"
            )

    # ---------------------------------------------------------
    # 3. Inicializa gerador aleatório
    # ---------------------------------------------------------

    rng = np.random.default_rng(seed)

    # ---------------------------------------------------------
    # 4. Processa cada grupo socioeconômico
    # ---------------------------------------------------------

    for income_group in IncomeGroup:

        group_name = income_group.value

        group_agents = [
            agent
            for agent in agents
            if agent.income_group == income_group
        ]

        if not group_agents:
            continue

        if group_name not in purpose_probabilities:
            raise ValueError(
                "Não existem probabilidades de propósito "
                f"para o grupo '{group_name}'."
            )

        probabilities = (
            purpose_probabilities[
                group_name
            ]
        )

        # -----------------------------------------------------
        # 5. Calcula quantidades exatas por propósito
        # -----------------------------------------------------

        purpose_counts = _calculate_counts(
            n_agents=len(group_agents),
            probabilities=probabilities,
        )

        # -----------------------------------------------------
        # 6. Cria a lista de propósitos
        # -----------------------------------------------------

        assigned_purposes = []

        for purpose_name, count in (
            purpose_counts.items()
        ):

            assigned_purposes.extend(
                [
                    TripPurpose(
                        purpose_name
                    )
                ]
                * count
            )

        # -----------------------------------------------------
        # 7. Embaralha os propósitos
        # -----------------------------------------------------

        rng.shuffle(
            assigned_purposes
        )

        # -----------------------------------------------------
        # 8. Atribui aos agentes
        # -----------------------------------------------------

        for agent, purpose in zip(
            group_agents,
            assigned_purposes,
        ):

            agent.purpose = purpose

    return agents