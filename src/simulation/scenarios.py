"""Configuração dos cenários experimentais do piloto.

O cenário ``baseline`` mantém fixa a estrutura residencial dos agentes,
mas remove diferenças comportamentais entre grupos de renda. Para isso,
as probabilidades de propósito, escolha modal e os coeficientes de
decaimento da distância são igualados entre os grupos usando a média
ponderada do cenário ``differentiated`` pelas participações populacionais.

O cenário ``differentiated`` preserva os parâmetros definidos em
``config/config_agents.json``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping


def _group_name(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _normalize_shares(income_shares: Mapping) -> dict[str, float]:
    shares = {
        _group_name(group): float(share)
        for group, share in income_shares.items()
    }

    if not shares:
        raise ValueError("Nenhuma participação de renda foi informada.")

    if any(share < 0 for share in shares.values()):
        raise ValueError("Participações de renda não podem ser negativas.")

    total = sum(shares.values())

    if total <= 0:
        raise ValueError("A soma das participações de renda deve ser positiva.")

    return {
        group: share / total
        for group, share in shares.items()
    }


def _equalize_group_probabilities(
    probabilities_by_group: Mapping[str, Mapping[str, float]],
    income_shares: Mapping,
) -> dict[str, dict[str, float]]:
    """Iguala probabilidades entre grupos preservando a média populacional."""

    shares = _normalize_shares(income_shares)
    groups = list(shares)

    missing_groups = set(groups) - set(probabilities_by_group)
    if missing_groups:
        raise ValueError(
            "Probabilidades ausentes para os grupos: "
            f"{sorted(missing_groups)}"
        )

    categories = list(probabilities_by_group[groups[0]])

    for group in groups:
        group_probabilities = probabilities_by_group[group]

        if set(group_probabilities) != set(categories):
            raise ValueError(
                "Todos os grupos devem possuir as mesmas categorias."
            )

        total = sum(float(value) for value in group_probabilities.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(
                f"As probabilidades do grupo '{group}' devem somar 1. "
                f"Valor atual: {total:.12f}"
            )

    average = {
        category: sum(
            shares[group]
            * float(probabilities_by_group[group][category])
            for group in groups
        )
        for category in categories
    }

    average_total = sum(average.values())
    average = {
        category: value / average_total
        for category, value in average.items()
    }

    return {
        group: dict(average)
        for group in groups
    }


def _equalize_distance_decay(
    distance_decay_per_km: Mapping[str, Mapping[str, float]],
    income_shares: Mapping,
) -> dict[str, dict[str, float]]:
    """Iguala beta entre grupos para cada propósito de viagem."""

    shares = _normalize_shares(income_shares)
    groups = list(shares)

    result: dict[str, dict[str, float]] = {}

    for purpose, values_by_group in distance_decay_per_km.items():
        missing_groups = set(groups) - set(values_by_group)
        if missing_groups:
            raise ValueError(
                f"Betas ausentes para '{purpose}': "
                f"{sorted(missing_groups)}"
            )

        average_beta = sum(
            shares[group] * float(values_by_group[group])
            for group in groups
        )

        result[purpose] = {
            group: average_beta
            for group in groups
        }

    return result


def build_behavior_scenarios(
    config_agents: Mapping,
    income_shares: Mapping,
) -> dict[str, dict]:
    """
    Constrói os dois cenários do experimento.

    Baseline
        Mantém grupos de renda e origens residenciais, mas aplica as mesmas
        regras comportamentais aos três grupos.

    Differentiated
        Mantém as regras socioeconomicamente diferenciadas configuradas.
    """

    purpose_differentiated = deepcopy(
        config_agents["purpose_choice"]
    )
    mode_differentiated = deepcopy(
        config_agents["mode_choice"]["differentiated"]
    )
    mode_distance_adjustment = deepcopy(
        config_agents[
            "mode_choice"
        ].get(
            "distance_adjustment",
            {
                "enabled": False,
            },
        )
    )
    destination_differentiated = deepcopy(
        config_agents["destination_choice"]
    )

    purpose_baseline = _equalize_group_probabilities(
        purpose_differentiated,
        income_shares,
    )
    mode_baseline = _equalize_group_probabilities(
        mode_differentiated,
        income_shares,
    )

    destination_baseline = deepcopy(
        destination_differentiated
    )
    destination_baseline["distance_decay_per_km"] = (
        _equalize_distance_decay(
            destination_differentiated["distance_decay_per_km"],
            income_shares,
        )
    )

    return {
        "baseline": {
            "purpose_choice": purpose_baseline,
            "destination_choice": destination_baseline,
            "mode_choice": mode_baseline,
            "mode_distance_adjustment": deepcopy(
                mode_distance_adjustment
            ),
        },
        "differentiated": {
            "purpose_choice": purpose_differentiated,
            "destination_choice": destination_differentiated,
            "mode_choice": mode_differentiated,
            "mode_distance_adjustment": deepcopy(
                mode_distance_adjustment
            ),
        },
    }
