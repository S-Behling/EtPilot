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

    # Modo
    mode: TravelMode | None = None

    # Nós efetivamente usados no roteamento, definidos após a escolha modal
    origin_node: int | None = None
    destination_node: int | None = None

    # Trajetória
    route_edges: list[tuple[int, int, int]] = field(default_factory=list)

    # Resultados da viagem
    travel_distance: float | None = None
    travel_time: float | None = None

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

        if mode_name not in self.origin_nodes:
            raise ValueError(
                f"Origem do agente {self.agent_id} não possui nó "
                f"para o modo '{mode_name}'."
            )

        if mode_name not in self.destination_nodes:
            raise ValueError(
                f"Destino do agente {self.agent_id} não possui nó "
                f"para o modo '{mode_name}'."
            )

        self.origin_node = int(
            self.origin_nodes[mode_name]
        )
        self.destination_node = int(
            self.destination_nodes[mode_name]
        )
