from dataclasses import dataclass, field

from .enums import IncomeGroup, TravelMode, TripPurpose


@dataclass
class Agent:
    """Representa um agente sintético da simulação de mobilidade."""

    agent_id: int
    income_group: IncomeGroup

    origin_id: int | str | None = None
    origin_nodes: dict[str, int] = field(default_factory=dict)

    purpose: TripPurpose | None = None

    destination_id: int | str | None = None
    destination_nodes: dict[str, int] = field(default_factory=dict)
    od_distance_m: float | None = None

    mode: TravelMode | None = None

    origin_node: int | None = None
    destination_node: int | None = None

    route_edges: list[tuple[int, int, int]] = field(default_factory=list)
    route_status: str | None = None

    travel_distance: float | None = None
    travel_time: float | None = None

    def resolve_routing_nodes(self) -> None:
        """Define os nós efetivos conforme o modo escolhido."""

        if self.mode is None:
            raise ValueError(
                f"Agente {self.agent_id} ainda não possui modo de viagem."
            )

        routing_mode = (
            TravelMode.WALK.value
            if self.mode is TravelMode.TRANSIT
            else self.mode.value
        )

        if routing_mode not in self.origin_nodes:
            raise ValueError(
                f"Origem do agente {self.agent_id} não possui nó "
                f"para '{routing_mode}'."
            )

        if routing_mode not in self.destination_nodes:
            raise ValueError(
                f"Destino do agente {self.agent_id} não possui nó "
                f"para '{routing_mode}'."
            )

        self.origin_node = int(
            self.origin_nodes[routing_mode]
        )
        self.destination_node = int(
            self.destination_nodes[routing_mode]
        )
