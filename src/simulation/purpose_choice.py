import numpy as np

from src.domain.agent import Agent
from src.domain.enums import TripPurpose


def assign_purpose(
    agents: list[Agent],
    purpose_probabilities: dict[TripPurpose, float],
    seed: int = 42,
) -> list[Agent]:
    """
    Atribui um motivo de viagem a cada agente sintético.

    A escolha é probabilística e utiliza as probabilidades
    fornecidas externamente ao modelo.

    Parameters
    ----------
    agents : list[Agent]
        Lista de agentes sintéticos.

    purpose_probabilities : dict[TripPurpose, float]
        Probabilidade de cada motivo de viagem.
        As probabilidades devem somar 1.

    seed : int, default=42
        Semente aleatória para garantir reprodutibilidade.

    Returns
    -------
    list[Agent]
        Lista de agentes com o atributo purpose preenchido.
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
            "Nenhuma probabilidade de motivo foi informada."
        )

    # ---------------------------------------------------------
    # 2. Valida os motivos e probabilidades
    # ---------------------------------------------------------

    for purpose, probability in purpose_probabilities.items():

        if not isinstance(
            purpose,
            TripPurpose,
        ):
            raise TypeError(
                f"{purpose!r} não é um TripPurpose válido."
            )

        if probability < 0:
            raise ValueError(
                "As probabilidades não podem ser negativas."
            )

    total_probability = sum(
        purpose_probabilities.values()
    )

    if not np.isclose(
        total_probability,
        1.0,
    ):
        raise ValueError(
            "As probabilidades dos motivos devem somar 1."
        )

    # ---------------------------------------------------------
    # 3. Prepara o sorteio
    # ---------------------------------------------------------

    purposes = list(
        purpose_probabilities.keys()
    )

    probabilities = np.array(
        [
            purpose_probabilities[purpose]
            for purpose in purposes
        ],
        dtype=float,
    )

    rng = np.random.default_rng(seed)

    # Sorteamos índices, e não diretamente os enums.
    # Assim garantimos que agent.purpose continue sendo
    # um objeto TripPurpose.
    selected_indices = rng.choice(
        len(purposes),
        size=len(agents),
        replace=True,
        p=probabilities,
    )

    # ---------------------------------------------------------
    # 4. Atribui o motivo aos agentes
    # ---------------------------------------------------------

    for agent, index in zip(
        agents,
        selected_indices,
    ):
        agent.purpose = purposes[index]

    return agents