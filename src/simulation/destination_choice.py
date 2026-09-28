"""
Escolha de destinos para os agentes sintéticos do EtPilot.

A probabilidade de um agente escolher um destino j é proporcional a:

    P_ij ∝ A_j^alpha * exp(-beta_gp * d_ij)

onde:
- A_j é a atratividade do destino (`destination_weight`);
- alpha controla a importância da atratividade;
- d_ij é a distância euclidiana origem-destino, em quilômetros;
- beta_gp é a sensibilidade à distância para o grupo de renda g
  e o propósito de viagem p.

Nesta primeira versão, diferenças socioeconômicas na diversidade espacial
dos destinos são representadas por beta:
- beta maior -> distribuição espacial mais localizada;
- beta menor -> destinos distantes sofrem menor penalização.

Os valores de beta devem ser tratados como parâmetros de calibração do piloto,
não como coeficientes empíricos definitivos.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from src.domain.agent import Agent
from src.domain.enums import IncomeGroup


def _enum_value(value) -> str:
    """Retorna `.value` para Enum ou a própria representação textual."""
    return value.value if hasattr(value, "value") else str(value)


def _calculate_destination_probabilities(
    distances_km,
    attractiveness,
    beta: float,
    attractiveness_exponent: float = 1.0,
) -> np.ndarray:
    """
    Calcula probabilidades de escolha de destino.

    Parameters
    ----------
    distances_km
        Distâncias origem-destino em quilômetros.
    attractiveness
        Pesos de atratividade dos destinos.
    beta
        Coeficiente de decaimento da distância, em 1/km.
    attractiveness_exponent
        Expoente aplicado à atratividade.

    Returns
    -------
    np.ndarray
        Vetor de probabilidades somando 1.
    """

    distances_km = np.asarray(distances_km, dtype=float)
    attractiveness = np.asarray(attractiveness, dtype=float)

    if distances_km.ndim != 1 or attractiveness.ndim != 1:
        raise ValueError(
            "Distâncias e atratividades devem ser vetores unidimensionais."
        )

    if len(distances_km) == 0:
        raise ValueError("Nenhum destino disponível para escolha.")

    if len(distances_km) != len(attractiveness):
        raise ValueError(
            "Distâncias e atratividades devem possuir o mesmo número "
            "de elementos."
        )

    if np.any(~np.isfinite(distances_km)):
        raise ValueError("Há distâncias inválidas na escolha de destinos.")

    if np.any(distances_km < 0):
        raise ValueError("Distâncias não podem ser negativas.")

    if beta < 0:
        raise ValueError("beta não pode ser negativo.")

    if attractiveness_exponent < 0:
        raise ValueError(
            "attractiveness_exponent não pode ser negativo."
        )

    attractiveness = np.where(
        np.isfinite(attractiveness) & (attractiveness > 0),
        attractiveness,
        0.0,
    )

    if attractiveness.sum() <= 0:
        raise ValueError(
            "Todos os destinos candidatos possuem atratividade inválida."
        )

    log_weights = np.full(
        len(attractiveness),
        -np.inf,
        dtype=float,
    )

    valid = attractiveness > 0

    log_weights[valid] = (
        attractiveness_exponent
        * np.log(attractiveness[valid])
        - beta * distances_km[valid]
    )

    max_log_weight = np.max(log_weights[valid])

    weights = np.zeros(
        len(log_weights),
        dtype=float,
    )

    weights[valid] = np.exp(
        log_weights[valid] - max_log_weight
    )

    total = weights.sum()

    if not np.isfinite(total) or total <= 0:
        raise ValueError(
            "Não foi possível construir uma distribuição válida "
            "de probabilidades."
        )

    return weights / total


def _validate_choice_config(
    choice_config: Mapping,
    purposes_used: set[str],
) -> None:
    """Valida a estrutura de `destination_choice` do config_agents.json."""

    required_keys = {
        "distance_decay_per_km",
        "purpose_categories",
    }

    missing = required_keys - set(choice_config)

    if missing:
        raise ValueError(
            "Chaves ausentes em destination_choice: "
            f"{sorted(missing)}"
        )

    beta_config = choice_config["distance_decay_per_km"]
    purpose_categories = choice_config["purpose_categories"]

    income_groups = {
        income_group.value
        for income_group in IncomeGroup
    }

    for purpose_name in purposes_used:
        if purpose_name not in purpose_categories:
            raise ValueError(
                "purpose_categories não possui configuração para "
                f"'{purpose_name}'."
            )

        categories = purpose_categories[purpose_name]

        if not categories:
            raise ValueError(
                f"Nenhuma categoria foi definida para '{purpose_name}'."
            )

        if purpose_name not in beta_config:
            raise ValueError(
                "distance_decay_per_km não possui configuração para "
                f"'{purpose_name}'."
            )

        purpose_betas = beta_config[purpose_name]

        missing_groups = (
            income_groups
            - set(purpose_betas)
        )

        if missing_groups:
            raise ValueError(
                f"Betas ausentes para '{purpose_name}': "
                f"{sorted(missing_groups)}"
            )

        for group_name, beta in purpose_betas.items():
            try:
                beta_value = float(beta)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Beta inválido para {purpose_name}/{group_name}: {beta}"
                ) from exc

            if beta_value < 0:
                raise ValueError(
                    f"Beta negativo para {purpose_name}/{group_name}: "
                    f"{beta_value}"
                )


def _prepare_destinations(
    destinations,
    modes: tuple[str, ...] | list[str],
    node_prefix: str,
):
    """Valida e prepara a base final de destinos CNEFE."""

    node_columns = {
        mode: f"{node_prefix}{mode}"
        for mode in modes
    }

    required_columns = {
        "destination_id",
        "category",
        "destination_weight",
        "geometry",
        *node_columns.values(),
    }

    missing = required_columns - set(destinations.columns)

    if missing:
        raise ValueError(
            "Colunas ausentes nos destinos: "
            f"{sorted(missing)}"
        )

    result = destinations.copy()

    result["category"] = (
        result["category"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    result["destination_weight"] = pd.to_numeric(
        result["destination_weight"],
        errors="coerce",
    )

    for column in node_columns.values():
        result[column] = pd.to_numeric(
            result[column],
            errors="coerce",
        )

    valid_mask = (
        result["geometry"].notna()
        & result["category"].notna()
        & result["destination_weight"].notna()
        & (result["destination_weight"] > 0)
    )

    for column in node_columns.values():
        valid_mask &= result[column].notna()

    result = result[
        valid_mask
    ].copy()

    if result.empty:
        raise ValueError(
            "Nenhum destino válido permaneceu após a preparação."
        )

    return result


def assign_destinations(
    agents: list[Agent],
    origins,
    destinations,
    choice_config: dict,
    seed: int = 42,
    max_trip_distance_m: float | None = None,
    modes: tuple[str, ...] | list[str] = ("walk", "bike", "car"),
    node_prefix: str = "node_",
) -> list[Agent]:
    """
    Atribui um destino a cada agente.

    Parameters
    ----------
    agents
        Agentes com `origin_id`, `income_group` e `purpose` já atribuídos.
    origins
        GeoDataFrame com, no mínimo, `origin_id` e `geometry`.
    destinations
        GeoDataFrame final produzido por destinationsCNEFE.py.
    choice_config
        Conteúdo de `config_agents["destination_choice"]`.
    seed
        Semente para reprodutibilidade.
    max_trip_distance_m
        Distância euclidiana máxima opcional para os candidatos, em metros.
        Pode receber diretamente `config["analysis"]["max_trip_distance"]`.
        Se None, não aplica limite máximo.

    Returns
    -------
    list[Agent]
        Os próprios agentes, com `destination_id` e os nós por modo
        armazenados em `destination_nodes`. O `destination_node`
        efetivo é definido somente depois da escolha modal.

    Notes
    -----
    A distância usada nesta etapa é euclidiana no CRS projetado.
    A distância real da viagem deve ser calculada posteriormente pelo
    módulo de roteamento e não é gravada em `agent.travel_distance`.
    """

    if not agents:
        raise ValueError("A lista de agentes está vazia.")

    required_origin_columns = {
        "origin_id",
        "geometry",
    }

    missing_origins = (
        required_origin_columns
        - set(origins.columns)
    )

    if missing_origins:
        raise ValueError(
            "Colunas ausentes nas origens: "
            f"{sorted(missing_origins)}"
        )

    if origins.crs is None or destinations.crs is None:
        raise ValueError(
        "Origens e destinos precisam possuir CRS."
        )

    # Padroniza as origens no mesmo CRS dos destinos.
    # A base CNEFE final utiliza EPSG:31982
    if origins.crs != destinations.crs:
        origins = origins.to_crs(destinations.crs)

    if not destinations.crs.is_projected:
        raise ValueError(
            "O cálculo de distância requer um CRS projetado."
        )

    if max_trip_distance_m is not None:
        max_trip_distance_m = float(max_trip_distance_m)

        if max_trip_distance_m <= 0:
            raise ValueError(
                "max_trip_distance_m deve ser maior que zero."
            )

    destinations = _prepare_destinations(
        destinations,
        modes=modes,
        node_prefix=node_prefix,
    )

    attractiveness_exponent = float(
        choice_config.get(
            "attractiveness_exponent",
            1.0,
        )
    )

    if attractiveness_exponent < 0:
        raise ValueError(
            "attractiveness_exponent não pode ser negativo."
        )

    beta_config = (
        choice_config["distance_decay_per_km"]
    )

    purpose_categories = (
        choice_config["purpose_categories"]
    )

    purposes_used: set[str] = set()

    origin_geometry = (
        origins
        .drop_duplicates(
            subset="origin_id",
            keep="first",
        )
        .set_index("origin_id")
        .geometry
        .to_dict()
    )

    for agent in agents:
        if agent.origin_id is None:
            raise ValueError(
                f"Agente {agent.agent_id} não possui origem."
            )

        if agent.purpose is None:
            raise ValueError(
                f"Agente {agent.agent_id} não possui motivo de viagem."
            )

        if agent.income_group is None:
            raise ValueError(
                f"Agente {agent.agent_id} não possui grupo de renda."
            )

        if agent.origin_id not in origin_geometry:
            raise ValueError(
                f"Origem {agent.origin_id} do agente "
                f"{agent.agent_id} não foi encontrada."
            )

        purposes_used.add(
            _enum_value(agent.purpose)
        )

    _validate_choice_config(
        choice_config,
        purposes_used,
    )

    destination_pools: dict[str, pd.DataFrame] = {}

    for purpose_name in purposes_used:
        categories = [
            str(category).strip().lower()
            for category
            in purpose_categories[purpose_name]
        ]

        pool = destinations[
            destinations["category"].isin(
                categories
            )
        ].reset_index(drop=True)

        if pool.empty:
            raise ValueError(
                f"Nenhum destino disponível para '{purpose_name}'. "
                f"Categorias procuradas: {categories}"
            )

        destination_pools[
            purpose_name
        ] = pool

    rng = np.random.default_rng(seed)

    probability_cache: dict[
        tuple[object, str, str],
        tuple[
            pd.DataFrame,
            np.ndarray,
            np.ndarray,
        ],
    ] = {}

    for agent in agents:
        group_name = _enum_value(
            agent.income_group
        )

        purpose_name = _enum_value(
            agent.purpose
        )

        cache_key = (
            agent.origin_id,
            group_name,
            purpose_name,
        )

        if cache_key not in probability_cache:
            full_pool = (
                destination_pools[
                    purpose_name
                ]
            )

            origin_geom = (
                origin_geometry[
                    agent.origin_id
                ]
            )

            distances_m = (
                full_pool.geometry
                .distance(origin_geom)
                .to_numpy(dtype=float)
            )

            if max_trip_distance_m is not None:
                within_limit = (
                    distances_m
                    <= max_trip_distance_m
                )

                if not np.any(within_limit):
                    nearest_distance = float(
                        np.min(distances_m)
                    )

                    raise ValueError(
                        "Nenhum destino dentro do limite de distância "
                        f"para o agente {agent.agent_id}: "
                        f"origem={agent.origin_id}, "
                        f"purpose={purpose_name}, "
                        f"limite={max_trip_distance_m:.0f} m, "
                        f"destino mais próximo={nearest_distance:.0f} m."
                    )

                candidates = (
                    full_pool.loc[
                        within_limit
                    ]
                    .reset_index(drop=True)
                )

                distances_m = (
                    distances_m[
                        within_limit
                    ]
                )
            else:
                candidates = full_pool

            distances_km = (
                distances_m / 1000.0
            )

            attractiveness = (
                candidates[
                    "destination_weight"
                ]
                .to_numpy(dtype=float)
            )

            try:
                beta = float(
                    beta_config[
                        purpose_name
                    ][
                        group_name
                    ]
                )
            except KeyError as exc:
                raise ValueError(
                    "Parâmetro beta ausente para "
                    f"purpose='{purpose_name}', "
                    f"income_group='{group_name}'."
                ) from exc

            probabilities = (
                _calculate_destination_probabilities(
                    distances_km=distances_km,
                    attractiveness=attractiveness,
                    beta=beta,
                    attractiveness_exponent=(
                        attractiveness_exponent
                    ),
                )
            )

            probability_cache[
                cache_key
            ] = (
                candidates,
                distances_m,
                probabilities,
            )

        candidates, distances_m, probabilities = (
            probability_cache[
                cache_key
            ]
        )

        position = int(
            rng.choice(
                len(candidates),
                p=probabilities,
            )
        )

        selected_destination = (
            candidates.iloc[position]
        )

        agent.destination_id = (
            selected_destination[
                "destination_id"
            ]
        )

        agent.destination_nodes = {
            mode: int(
                selected_destination[
                    f"{node_prefix}{mode}"
                ]
            )
            for mode in modes
        }

        # Registra a distância euclidiana usada como impedância pré-roteamento
        agent.od_distance_m = float(
            distances_m[
                position
            ]
        )

        # Mantém o nó efetivo indefinido até a escolha modal
        agent.destination_node = None

    return agents


def destination_choice_summary(
    agents: list[Agent],
) -> pd.DataFrame:
    """
    Retorna um resumo simples das escolhas realizadas.
    """

    rows = []

    for agent in agents:
        rows.append(
            {
                "agent_id": agent.agent_id,
                "income_group": _enum_value(
                    agent.income_group
                ),
                "purpose": (
                    _enum_value(agent.purpose)
                    if agent.purpose is not None
                    else None
                ),
                "origin_id": agent.origin_id,
                "destination_id": (
                    agent.destination_id
                ),
                "od_distance_m": (
                    agent.od_distance_m
                ),
                "destination_node": (
                    agent.destination_node
                ),
            }
        )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(
        "destination_choice.py é um módulo da simulação. "
        "Execute o pipeline principal e chame assign_destinations(...)."
    )
