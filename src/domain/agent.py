from dataclasses import dataclass, field
from typing import Optional
from .enums import IncomeGroup, TravelMode, TripPurpose


@dataclass
class Agent:
    """
    Representa um agente sintético da simulação de mobilidade

    Cada agente pertence a um grupo socioeconômico e,
    ao longo da simulação, recebe uma origem, um motivo
    de viagem, um destino, um modo de transporte e uma rota.

    # primeira versao
    origin_node: Optional[int] = None
    purpose: Optional[TripPurpose] = None
    destination_id: Optional[int] = None
    destination_node: Optional[int] = None
    mode: Optional[TravelMode] = None

    route_edges: list[tuple[int, int, int]] = field(default_factory=list)

    travel_time: Optional[float] = None
    travel_distance: Optional[float] = None

    """

    agent_id: int
    income_group: IncomeGroup

    # Origem
    origin_id: int | str | None = None
    origin_node: int | None = None

    # Viagem
    purpose: TripPurpose | None = None

    # Destino
    destination_id: int | str | None = None
    destination_node: int | None = None

    # Modo
    mode: TravelMode | None = None

    # Trajetória
    route_edges: list[tuple[int, int, int]] = field(default_factory=list)

    # Resultados da viagem
    travel_distance: float | None = None
    travel_time: float | None = None


    """
    Observações:
    Por que route_edges é uma lista de (u, v, key)? Porque a rede é um MultiDiGraph
    Então uma rota não será armazenada apenas como:[10, 20, 30, 40]
    mas como:
    [(10, 20, 0),
     (20, 30, 0),
     (30, 40, 1)]
    """