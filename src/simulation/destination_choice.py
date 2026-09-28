import numpy as np
import pandas as pd

from src.domain.agent import Agent
from src.domain.enums import IncomeGroup


def _calculate_destination_probabilities(
    distances_km,
    attractiveness,
    beta,
    temperature,
    attractiveness_exponent=1.0,
):
    """
    Calcula a probabilidade de escolha de cada destino.

    A escolha combina:

    1. atratividade do destino;
    2. penalização pela distância;
    3. diversidade de escolha do grupo socioeconômico.

    Parameters
    ----------
    distances_km : array-like
        Distâncias entre a origem e os destinos, em quilômetros.

    attractiveness : array-like
        Atratividade relativa dos destinos.

    beta : float
        Sensibilidade à distância.

        Valores maiores tornam destinos distantes
        progressivamente menos prováveis.

    temperature : float
        Controla a dispersão da distribuição de escolha.

        temperature < 1:
            distribuição mais concentrada.

        temperature = 1:
            mantém a distribuição original.

        temperature > 1:
            distribuição mais dispersa.

    attractiveness_exponent : float, default=1.0
        Controla o peso relativo da atratividade.

    Returns
    -------
    np.ndarray
        Probabilidade de escolha de cada destino.
    """

    distances_km = np.asarray(
        distances_km,
        dtype=float,
    )

    attractiveness = np.asarray(
        attractiveness,
        dtype=float,
    )

    if len(distances_km) == 0:
        raise ValueError(
            "Nenhum destino disponível para escolha."
        )

    if len(distances_km) != len(attractiveness):
        raise ValueError(
            "Distâncias e atratividades devem possuir "
            "o mesmo número de elementos."
        )

    if beta < 0:
        raise ValueError(
            "beta não pode ser negativo."
        )

    if temperature <= 0:
        raise ValueError(
            "temperature deve ser maior que zero."
        )

    if attractiveness_exponent < 0:
        raise ValueError(
            "attractiveness_exponent não pode ser negativo."
        )

    # Evita log(0).
    attractiveness = np.maximum(
        attractiveness,
        1e-12,
    )

    # ---------------------------------------------------------
    # Função de utilidade em espaço logarítmico
    #
    # log(W) =
    #
    # alpha * log(A)
    # -
    # beta * distância
    #
    # ---------------------------------------------------------

    log_weights = (
        attractiveness_exponent
        * np.log(attractiveness)
        -
        beta
        * distances_km
    )

    # ---------------------------------------------------------
    # Temperature
    #
    # valores menores que 1 concentram escolhas
    # valores maiores que 1 aumentam diversidade
    # ---------------------------------------------------------

    logits = (
        log_weights
        / temperature
    )

    # Estabilidade numérica
    logits = (
        logits
        - np.max(logits)
    )

    weights = np.exp(
        logits
    )

    total = weights.sum()

    if (
        not np.isfinite(total)
        or total <= 0
    ):
        return (
            np.ones(len(weights))
            / len(weights)
        )

    return (
        weights
        / total
    )


def assign_destinations(
    agents: list[Agent],
    origins,
    destinations,
    choice_config: dict,
    seed: int = 42,
) -> list[Agent]:
    """
    Atribui destinos aos agentes sintéticos.

    A escolha depende de:

    - motivo da viagem;
    - localização da origem;
    - atratividade do destino;
    - distância origem-destino;
    - grupo socioeconômico.

    Grupos socioeconômicos podem apresentar diferentes
    sensibilidades à distância e diferentes níveis de
    diversidade de escolha.

    Parameters
    ----------
    agents : list[Agent]
        Agentes com origem e propósito já atribuídos.

    origins : GeoDataFrame
        Origens contendo pelo menos:

        origin_id
        geometry

    destinations : GeoDataFrame
        Destinos contendo pelo menos:

        destination_id
        category
        node
        destination_weight
        geometry

    choice_config : dict
        Configuração da escolha de destinos.

    seed : int, default=42
        Semente para garantir reprodutibilidade.

    Returns
    -------
    list[Agent]
        Lista de agentes com destination_id
        e destination_node atribuídos.
    """

    # ---------------------------------------------------------
    # 1. Validações
    # ---------------------------------------------------------

    if not agents:
        raise ValueError(
            "A lista de agentes está vazia."
        )

    required_origin_columns = {
        "origin_id",
        "geometry",
    }

    required_destination_columns = {
        "destination_id",
        "category",
        "node",
        "destination_weight",
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

    missing_destinations = (
        required_destination_columns
        - set(destinations.columns)
    )

    if missing_destinations:
        raise ValueError(
            "Colunas ausentes nos destinos: "
            f"{sorted(missing_destinations)}"
        )

    if (
        origins.crs is None
        or destinations.crs is None
    ):
        raise ValueError(
            "Origens e destinos precisam possuir CRS."
        )

    if origins.crs != destinations.crs:
        raise ValueError(
            "Origens e destinos devem possuir o mesmo CRS."
        )

    if not origins.crs.is_projected:
        raise ValueError(
            "O cálculo de distância requer um CRS projetado."
        )

    # ---------------------------------------------------------
    # 2. Configuração
    # ---------------------------------------------------------

    beta_config = (
        choice_config[
            "distance_decay_per_km"
        ]
    )

    temperature_config = (
        choice_config[
            "diversity_temperature"
        ]
    )

    attractiveness_exponent = (
        choice_config.get(
            "attractiveness_exponent",
            1.0,
        )
    )

    purpose_categories = (
        choice_config.get(
            "purpose_categories",
            {},
        )
    )

    for income_group in IncomeGroup:

        group_name = (
            income_group.value
        )

        if group_name not in beta_config:
            raise ValueError(
                "Parâmetro de distância ausente "
                f"para '{group_name}'."
            )

        if group_name not in temperature_config:
            raise ValueError(
                "Parâmetro de diversidade ausente "
                f"para '{group_name}'."
            )

    # ---------------------------------------------------------
    # 3. Prepara destinos
    # ---------------------------------------------------------

    destinations = (
        destinations.copy()
    )

    destinations["category"] = (
        destinations["category"]
        .astype("string")
        .str.strip()
        .str.lower()
    )

    destinations["destination_weight"] = (
        pd.to_numeric(
            destinations[
                "destination_weight"
            ],
            errors="coerce",
        )
    )

    destinations["node"] = (
        pd.to_numeric(
            destinations["node"],
            errors="coerce",
        )
    )

    destinations = destinations[
        destinations["geometry"].notna()
        & destinations["node"].notna()
        & destinations[
            "destination_weight"
        ].notna()
        & (
            destinations[
                "destination_weight"
            ]
            > 0
        )
    ].copy()

    if destinations.empty:
        raise ValueError(
            "Nenhum destino válido disponível."
        )

    # ---------------------------------------------------------
    # 4. Índice das origens
    # ---------------------------------------------------------

    origin_geometry = (
        origins
        .drop_duplicates(
            subset="origin_id"
        )
        .set_index("origin_id")
        .geometry
        .to_dict()
    )

    # ---------------------------------------------------------
    # 5. Verifica agentes
    # ---------------------------------------------------------

    for agent in agents:

        if agent.origin_id is None:
            raise ValueError(
                f"Agente {agent.agent_id} "
                "não possui origem."
            )

        if agent.purpose is None:
            raise ValueError(
                f"Agente {agent.agent_id} "
                "não possui motivo de viagem."
            )

        if (
            agent.origin_id
            not in origin_geometry
        ):
            raise ValueError(
                "Origem não encontrada para "
                f"o agente {agent.agent_id}: "
                f"{agent.origin_id}"
            )

    # ---------------------------------------------------------
    # 6. Constrói pools por motivo
    # ---------------------------------------------------------

    destination_pools = {}

    purposes_used = {
        agent.purpose.value
        for agent in agents
    }

    for purpose_name in purposes_used:

        categories = (
            purpose_categories.get(
                purpose_name,
                [purpose_name],
            )
        )

        if not categories:
            raise ValueError(
                "Nenhuma categoria de destino "
                f"foi definida para o motivo "
                f"'{purpose_name}'."
            )

        pool = destinations[
            destinations[
                "category"
            ].isin(categories)
        ].reset_index(
            drop=True
        )

        if pool.empty:
            raise ValueError(
                "Nenhum destino disponível para "
                f"o motivo '{purpose_name}'. "
                f"Categorias procuradas: "
                f"{categories}"
            )

        destination_pools[
            purpose_name
        ] = pool

    # ---------------------------------------------------------
    # 7. Gerador aleatório
    # ---------------------------------------------------------

    rng = np.random.default_rng(
        seed
    )

    # ---------------------------------------------------------
    # 8. Cache
    #
    # Agentes com mesma:
    #
    # origem
    # renda
    # propósito
    #
    # possuem a mesma distribuição de probabilidades.
    #
    # ---------------------------------------------------------

    probability_cache = {}

    # ---------------------------------------------------------
    # 9. Escolha dos destinos
    # ---------------------------------------------------------

    for agent in agents:

        group_name = (
            agent.income_group.value
        )

        purpose_name = (
            agent.purpose.value
        )

        cache_key = (
            agent.origin_id,
            group_name,
            purpose_name,
        )

        if (
            cache_key
            not in probability_cache
        ):

            candidates = (
                destination_pools[
                    purpose_name
                ]
            )

            origin_geom = (
                origin_geometry[
                    agent.origin_id
                ]
            )

            # EPSG:31982 -> distância em metros
            distances_km = (
                candidates.geometry
                .distance(origin_geom)
                .to_numpy()
                / 1000.0
            )

            attractiveness = (
                candidates[
                    "destination_weight"
                ]
                .to_numpy(
                    dtype=float
                )
            )

            probabilities = (
                _calculate_destination_probabilities(
                    distances_km=distances_km,
                    attractiveness=attractiveness,
                    beta=beta_config[
                        group_name
                    ],
                    temperature=(
                        temperature_config[
                            group_name
                        ]
                    ),
                    attractiveness_exponent=(
                        attractiveness_exponent
                    ),
                )
            )

            probability_cache[
                cache_key
            ] = (
                candidates,
                probabilities,
            )

        candidates, probabilities = (
            probability_cache[
                cache_key
            ]
        )

        position = rng.choice(
            len(candidates),
            p=probabilities,
        )

        selected_destination = (
            candidates.iloc[
                position
            ]
        )

        agent.destination_id = (
            selected_destination[
                "destination_id"
            ]
        )

        agent.destination_node = int(
            selected_destination[
                "node"
            ]
        )

    return agents