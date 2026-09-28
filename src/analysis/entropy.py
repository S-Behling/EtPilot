"""Calcule a entropia normalizada da composição socioeconômica.

Use a entropia de Shannon para medir a diversidade dos grupos de renda que
utilizam cada segmento físico. Normalize o valor pelo máximo teórico definido
pelo número total de grupos considerados.

Interprete o resultado no intervalo [0, 1]:
- use 0 quando apenas um grupo estiver representado;
- aproxime-se de 1 quando os grupos aparecerem em proporções semelhantes;
- retorne NaN quando não houver observações no segmento.

Não interprete a entropia isoladamente. Acompanhe-a sempre pelo número de
agentes e de passagens observados no segmento.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np


def normalized_shannon_entropy(
    counts: Iterable[int | float],
    *,
    n_categories: int | None = None,
) -> float:
    """
    Calcule a entropia de Shannon normalizada para uma composição.

    Use somente contagens não negativas. Ignore categorias com probabilidade
    zero no somatório e normalize pelo máximo teórico `ln(K)`, em que `K`
    representa o número total de categorias possíveis no experimento.

    Retorne NaN quando a soma das contagens for zero. Não converta ausência de
    observação em entropia zero, pois zero deve representar composição
    observada por um único grupo.
    """

    values = np.asarray(
        list(counts),
        dtype=float,
    )

    if values.ndim != 1:
        raise ValueError(
            "Forneça as contagens em um vetor unidimensional."
        )

    if values.size == 0:
        raise ValueError(
            "Forneça pelo menos uma categoria para calcular a entropia."
        )

    if np.isnan(values).any():
        raise ValueError(
            "Remova valores ausentes das contagens antes de calcular a entropia."
        )

    if (values < 0).any():
        raise ValueError(
            "Use somente contagens não negativas."
        )

    if n_categories is None:
        n_categories = int(
            values.size
        )

    if n_categories < 2:
        raise ValueError(
            "Use pelo menos duas categorias possíveis para normalizar a entropia."
        )

    if n_categories < values.size:
        raise ValueError(
            "Defina n_categories maior ou igual ao número de contagens fornecidas."
        )

    total = float(
        values.sum()
    )

    if total == 0:
        return float(
            "nan"
        )

    probabilities = (
        values
        / total
    )

    positive = probabilities[
        probabilities > 0
    ]

    entropy = -float(
        np.sum(
            positive
            * np.log(
                positive
            )
        )
    )

    maximum = float(
        np.log(
            n_categories
        )
    )

    normalized = (
        entropy
        / maximum
    )

    # Limite pequenos erros numéricos sem mascarar resultados fora do domínio.
    if -1e-12 <= normalized < 0:
        normalized = 0.0

    if 1 < normalized <= 1 + 1e-12:
        normalized = 1.0

    if not 0 <= normalized <= 1:
        raise RuntimeError(
            f"Obtenha uma entropia normalizada em [0, 1], não {normalized}."
        )

    return float(
        normalized
    )
