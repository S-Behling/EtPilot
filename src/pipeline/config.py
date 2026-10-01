"""Configuração de uma execução completa do EtPilot.

A configuração é independente da interface. Hoje ela é preenchida pelo
terminal; futuramente a mesma estrutura poderá ser alimentada por uma GUI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.domain.enums import IncomeGroup


VALID_PERIOD_UNITS = {"hours", "days"}
VALID_SCENARIOS = {"baseline", "differentiated"}
VALID_REGION_MODES = {"analysis", "plot_only"}

PLOT_MODE_ALL_INCOMES = "mode_all_incomes"
PLOT_BIKE_BY_INCOME = "bike_by_income"
PLOT_WALK_BY_INCOME = "walk_by_income"
PLOT_CAR_BY_INCOME = "car_by_income"
PLOT_TRANSIT_BY_INCOME = "transit_by_income"
PLOT_CENSUS_INCOME = "census_income"
PLOT_CENSUS_ALL_MODES = "census_all_modes"
PLOT_ALL_NETWORKS = "all_networks"
PLOT_AGENT_UNIQUE = "agent_unique"
PLOT_MODE_FREQUENCY_BY_INCOME = "mode_frequency_by_income"
PLOT_SELECTED_STREET_USAGE = "selected_street_usage"

# Somente estes produtos aparecem na GUI e podem ser gerados pelo piloto.
# Alguns itens produzem mais de um arquivo (por exemplo, um por modo ou por
# classe social), mas a seleção na interface é feita por grupo lógico.
AVAILABLE_PLOTS = (
    PLOT_MODE_ALL_INCOMES,
    PLOT_BIKE_BY_INCOME,
    PLOT_WALK_BY_INCOME,
    PLOT_CAR_BY_INCOME,
    PLOT_TRANSIT_BY_INCOME,
    PLOT_CENSUS_INCOME,
    PLOT_CENSUS_ALL_MODES,
    PLOT_ALL_NETWORKS,
    PLOT_AGENT_UNIQUE,
    PLOT_MODE_FREQUENCY_BY_INCOME,
    PLOT_SELECTED_STREET_USAGE,
)


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
    selected_plots: tuple[str, ...] = field(
        default_factory=lambda: AVAILABLE_PLOTS
    )
    selected_street: str | None = None

    def __post_init__(self) -> None:
        if not self.region.strip():
            raise ValueError(
                "A região não pode ser vazia."
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

        invalid_plots = (
            set(self.selected_plots)
            - set(AVAILABLE_PLOTS)
        )

        if invalid_plots:
            raise ValueError(
                "Mapas inválidos selecionados: "
                + ", ".join(
                    sorted(invalid_plots)
                )
            )

        if (
            PLOT_SELECTED_STREET_USAGE
            in self.selected_plots
            and not (
                self.selected_street
                and self.selected_street.strip()
            )
        ):
            raise ValueError(
                "Selecione uma rua para gerar o mapa de uso por rua."
            )

    @property
    def income_group_names(self) -> tuple[str, ...]:
        return tuple(
            group.value
            for group in self.income_groups
        )
