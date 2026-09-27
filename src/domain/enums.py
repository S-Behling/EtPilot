from enum import Enum

class IncomeGroup(Enum):
    LOW = "low"
    MIDDLE = "middle"
    HIGH = "high"


class TravelMode(Enum):
    WALK = "walk"
    BIKE = "bike"
    CAR = "car"
    TRANSIT = "transit"


class TripPurpose(Enum):
    WORK = "work"
    EDUCATION = "education"
    HEALTH = "health"
    SHOPPING = "shopping"
    LEISURE = "leisure"