from dataclasses import dataclass, field

from .enums import IncomeGroup, TravelMode, TripPurpose


@dataclass
class Agent:
    """
    Representa um agente sintético da simulação de mobilidade.

    A origem e o destino são entidades espaciais independentes da rede.
    Como cada modo usa uma rede própria, o agente guarda os nós candidatos
    por modo em ``origin_nodes`` e ``destination_nodes``.

    Depois que o modo é escolhido, ``origin_node`` e
    ``destination_node`` passam a representar somente os nós efetivamente
    usados no roteamento daquela viagem.
    """

    agent_id: int
    income_group: IncomeGroup

    # Origem espacial
    origin_id: int | str | None = None
    origin_nodes: dict[str, int] = field(default_factory=dict)

    # Viagem
    purpose: TripPurpose | None = None

    # Destino espacial
    destination_id: int | str | None = None
    destination_nodes: dict[str, int] = field(default_factory=dict)
    od_distance_m: float | None = None

    # Modo
    mode: TravelMode | None = None

    # Nós efetivamente usados no roteamento, definidos após a escolha modal
    origin_node: int | None = None
    destination_node: int | None = None

    # Trajetória
    route_edges: list[tuple[int, int, int]] = field(default_factory=list)
    route_status: str | None = None

    # Resultados da viagem
    travel_distance: float | None = None
    travel_time: float | None = None

    # Resultados específicos do transporte coletivo
    transit_service_date: str | None = None
    transit_departure_time_s: int | None = None
    transit_arrival_time_s: int | None = None
    transit_access_stop_id: str | None = None
    transit_egress_stop_id: str | None = None
    transit_access_walk_distance_m: float | None = None
    transit_access_walk_time_s: float | None = None
    transit_initial_wait_time_s: float | None = None
    transit_in_vehicle_distance_m: float | None = None
    transit_in_vehicle_time_s: float | None = None
    transit_transfer_and_dwell_time_s: float | None = None
    transit_n_boardings: int = 0
    transit_n_transfers: int = 0
    transit_egress_walk_distance_m: float | None = None
    transit_egress_walk_time_s: float | None = None
    transit_access_walk_edges: list[
        tuple[
            int,
            int,
            int,
        ]
    ] = field(
        default_factory=list
    )
    transit_egress_walk_edges: list[
        tuple[
            int,
            int,
            int,
        ]
    ] = field(
        default_factory=list
    )
    transit_connection_ids: list[str] = field(
        default_factory=list
    )
    transit_trip_ids: list[str] = field(
        default_factory=list
    )
    transit_route_ids: list[str] = field(
        default_factory=list
    )

    def resolve_routing_nodes(self) -> None:
        """
        Define os nós de origem e destino correspondentes ao modo escolhido.

        Raises
        ------
        ValueError
            Se o modo ainda não foi definido ou se faltarem nós para o modo.
        """

        if self.mode is None:
            raise ValueError(
                f"Agente {self.agent_id} ainda não possui modo de viagem."
            )

        mode_name = self.mode.value
        routing_mode_name = (
            TravelMode.WALK.value
            if self.mode is TravelMode.TRANSIT
            else mode_name
        )

        if routing_mode_name not in self.origin_nodes:
            raise ValueError(
                f"Origem do agente {self.agent_id} não possui nó "
                f"para o modo de roteamento '{routing_mode_name}'."
            )

        if routing_mode_name not in self.destination_nodes:
            raise ValueError(
                f"Destino do agente {self.agent_id} não possui nó "
                f"para o modo de roteamento '{routing_mode_name}'."
            )

        self.origin_node = int(
            self.origin_nodes[
                routing_mode_name
            ]
        )
        self.destination_node = int(
            self.destination_nodes[
                routing_mode_name
            ]
        )
