"""Calcula probabilidades modais com ajuste opcional pela distância OD

Parte das probabilidades comportamentais por grupo de renda e aplica uma
penalização exponencial específica por modo antes da normalização

Usa a distância euclidiana origem-destino como impedância pré-roteamento e
mantém a distância real da rede como resultado posterior do roteamento

Trata os parâmetros de distância como parâmetros provisórios de calibração do
piloto e não como coeficientes empíricos definitivos
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np

from src.domain.enums import TravelMode


def _validate_distance_config(
    distance_config: Mapping | None,
) -> None:
    """Valida a estrutura do ajuste modal por distância"""

    if distance_config is None:
        return

    if not bool(
        distance_config.get(
            "enabled",
            False,
        )
    ):
        return

    decay = distance_config.get(
        "decay_per_km"
    )

    if not isinstance(
        decay,
        Mapping,
    ):
        raise ValueError(
            "distance_adjustment.decay_per_km precisa ser um mapeamento"
        )

    maximum = distance_config.get(
        "max_distance_km",
        {},
    )

    if not isinstance(
        maximum,
        Mapping,
    ):
        raise ValueError(
            "distance_adjustment.max_distance_km precisa ser um mapeamento"
        )

    for mode_name, value in decay.items():
        beta = float(
            value
        )

        if beta < 0:
            raise ValueError(
                "Os coeficientes de distância modal precisam ser "
                f"não negativos: {mode_name}={beta}"
            )

    for mode_name, value in maximum.items():
        if value is None:
            continue

        limit = float(
            value
        )

        if limit <= 0:
            raise ValueError(
                "Os limites máximos de distância precisam ser positivos: "
                f"{mode_name}={limit}"
            )


def _distance_factor(
    *,
    mode: TravelMode,
    distance_km: float,
    distance_config: Mapping | None,
) -> float:
    """Calcula o fator multiplicativo de adequação modal à distância"""

    if distance_config is None:
        return 1.0

    if not bool(
        distance_config.get(
            "enabled",
            False,
        )
    ):
        return 1.0

    decay = distance_config.get(
        "decay_per_km",
        {},
    )
    maximum = distance_config.get(
        "max_distance_km",
        {},
    )

    mode_name = mode.value

    max_distance = maximum.get(
        mode_name
    )

    if (
        max_distance is not None
        and distance_km
        > float(
            max_distance
        )
    ):
        return 0.0

    beta = float(
        decay.get(
            mode_name,
            0.0,
        )
    )

    return float(
        np.exp(
            -beta
            * distance_km
        )
    )


def calculate_mode_probabilities(
    *,
    agent,
    config: Mapping,
    available_modes,
    distance_config: Mapping | None = None,
) -> tuple[list[TravelMode], np.ndarray]:
    """Calcula e normaliza as probabilidades dos modos disponíveis"""

    if agent.income_group is None:
        raise ValueError(
            f"Agente {agent.agent_id} não possui grupo de renda"
        )

    group_name = agent.income_group.value

    if group_name not in config:
        raise ValueError(
            f"Não existe configuração modal para o grupo '{group_name}'"
        )

    probabilities = config[
        group_name
    ]

    _validate_distance_config(
        distance_config
    )

    distance_adjustment_enabled = bool(
        distance_config
        and distance_config.get(
            "enabled",
            False,
        )
    )

    if distance_adjustment_enabled:
        if agent.od_distance_m is None:
            raise ValueError(
                f"Agente {agent.agent_id} não possui od_distance_m "
                "para o ajuste modal por distância"
            )

        distance_m = float(
            agent.od_distance_m
        )

        if not np.isfinite(
            distance_m
        ) or distance_m < 0:
            raise ValueError(
                f"Agente {agent.agent_id} possui od_distance_m inválida: "
                f"{distance_m}"
            )

        distance_km = (
            distance_m
            / 1000.0
        )
    else:
        distance_km = 0.0

    modes: list[
        TravelMode
    ] = []
    weights: list[
        float
    ] = []

    for mode_name, probability in probabilities.items():
        mode = TravelMode(
            mode_name
        )

        if mode not in available_modes:
            continue

        base_probability = float(
            probability
        )

        if base_probability < 0:
            raise ValueError(
                f"Probabilidade modal negativa para '{mode_name}': "
                f"{base_probability}"
            )

        factor = _distance_factor(
            mode=mode,
            distance_km=distance_km,
            distance_config=distance_config,
        )

        adjusted_weight = (
            base_probability
            * factor
        )

        modes.append(
            mode
        )
        weights.append(
            adjusted_weight
        )

    if not modes:
        raise ValueError(
            "Nenhum modo configurado está disponível para escolha"
        )

    weights_array = np.asarray(
        weights,
        dtype=float,
    )

    total = float(
        weights_array.sum()
    )

    if not np.isfinite(
        total
    ) or total <= 0:
        raise ValueError(
            "O ajuste pela distância eliminou todos os modos disponíveis "
            f"para o agente {agent.agent_id}"
        )

    weights_array /= total

    return (
        modes,
        weights_array,
    )


def choose_mode(
    agent,
    config,
    rng,
    available_modes,
    distance_config: Mapping | None = None,
):
    """Sorteia o modo a partir das probabilidades ajustadas"""

    modes, weights = (
        calculate_mode_probabilities(
            agent=agent,
            config=config,
            available_modes=available_modes,
            distance_config=distance_config,
        )
    )

    return rng.choice(
        modes,
        p=weights,
    )
