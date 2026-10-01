"""Configuração de uma execução completa do EtPilot.

A configuração é independente da interface. Hoje ela é preenchida pelo
terminal; futuramente a mesma estrutura poderá ser alimentada por uma GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.enums import IncomeGroup


VALID_PERIOD_UNITS = {"hours", "days"}
VALID_SCENARIOS = {"baseline", "differentiated"}
VALID_REGIONS = {"city", "center", "north", "south", "east"}
VALID_REGION_MODES = {"analysis", "plot_only"}


@dataclass(frozen=True, slots=True)
class SimulationPeriod:
    """Janela temporal solicitada para a execução."""

    value: int = 24
    unit: str = "hours"

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ValueError(
                "O período precisa ser maior que zero."
            )

        if self.unit not in VALID_PERIOD_UNITS:
            raise ValueError(
                f"Unidade temporal inválida: {self.unit!r}. "
                f"Use uma de {sorted(VALID_PERIOD_UNITS)}."
            )

    @property
    def total_hours(self) -> int:
        if self.unit == "days":
            return self.value * 24

        return self.value


@dataclass(frozen=True, slots=True)
class PilotRunConfig:
    """Parâmetros controláveis de uma rodada do piloto."""

    region: str = "city"
    region_mode: str = "analysis"
    income_groups: tuple[IncomeGroup, ...] = field(
        default_factory=lambda: tuple(IncomeGroup)
    )
    period: SimulationPeriod = field(
        default_factory=SimulationPeriod
    )
    n_agents: int = 100
    seed: int = 42
    scenario: str = "differentiated"
    prepare_networks: bool = True
    prepare_region: bool = True
    clear_outputs: bool = False
    force_network_download: bool = False

    def __post_init__(self) -> None:
        if self.region not in VALID_REGIONS:
            raise ValueError(
                f"Região inválida: {self.region!r}. "
                f"Use uma de {sorted(VALID_REGIONS)}."
            )

        if self.region_mode not in VALID_REGION_MODES:
            raise ValueError(
                f"Modo regional inválido: {self.region_mode!r}. "
                f"Use um de {sorted(VALID_REGION_MODES)}."
            )

        if not self.income_groups:
            raise ValueError(
                "Selecione pelo menos uma classe social."
            )

        if self.n_agents <= 0:
            raise ValueError(
                "n_agents precisa ser maior que zero."
            )

        if self.scenario not in VALID_SCENARIOS:
            raise ValueError(
                f"Cenário inválido: {self.scenario!r}."
            )

    @property
    def income_group_names(self) -> tuple[str, ...]:
        return tuple(
            group.value
            for group in self.income_groups
        )
