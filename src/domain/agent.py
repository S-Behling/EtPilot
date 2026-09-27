from dataclasses import dataclass, field
from typing import Optional
from .enums import IncomeGroup, TravelMode, TripPurpose


@dataclass
class Agent:
    agent_id: int
    income_group: IncomeGroup

    origin_node: Optional[int] = None
    purpose: Optional[TripPurpose] = None
    destination_id: Optional[int] = None
    destination_node: Optional[int] = None
    mode: Optional[TravelMode] = None

    route_edges: list[tuple[int, int, int]] = field(default_factory=list)

    travel_time: Optional[float] = None
    travel_distance: Optional[float] = None