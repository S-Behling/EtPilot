"""Interface gráfica opcional para configurar e executar o EtPilot.

A interface monta o mesmo PilotRunConfig usado pelo terminal. Assim, existem
dois pontos de entrada independentes para o mesmo pipeline:

    python scripts/run_pipeline.py
    python scripts/run_pipeline_gui.py
"""

from __future__ import annotations

import threading
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

from _bootstrap import add_project_root_to_path

add_project_root_to_path()

from run_pipeline import run_pipeline
from src.core.config import load_project_config
from src.domain.enums import IncomeGroup
from src.pipeline.config import (
    PilotRunConfig,
    SimulationPeriod,
)


REGION_LABELS = {
    "city": "Cidade inteira",
    "center": "Centro",
    "north": "Norte",
    "south": "Sul",
    "east": "Leste",
}

REGION_VALUES = {
    label: value
    for value, label in REGION_LABELS.items()
}

REGION_MODE_LABELS = {
    "Recorte da análise": "analysis",
    "Somente janela do mapa": "plot_only",
}

SCENARIO_LABELS = {
    "Diferenciado": "differentiated",
    "Baseline": "baseline",
}


class PipelineApp(tk.Tk):
    """Janela de configuração do pipeline."""

    def __init__(self) -> None:
        super().__init__()

        self.title("EtPilot — Configuração do piloto")
        self.minsize(650, 650)

        project_config = load_project_config()
        default_region = project_config[
            "study_area"
        ][
            "default_region"
        ]

        self.region_var = tk.StringVar(
            value=REGION_LABELS.get(
                default_region,
                "Cidade inteira",
            )
        )
        self.region_mode_var = tk.StringVar(
            value="Recorte da análise"
        )
        self.period_value_var = tk.StringVar(
            value="24"
        )
        self.period_unit_var = tk.StringVar(
            value="hours"
        )
        self.n_agents_var = tk.StringVar(
            value="100"
        )
        self.seed_var = tk.StringVar(
            value="42"
        )
        self.scenario_var = tk.StringVar(
            value="Diferenciado"
        )

        self.income_vars = {
            IncomeGroup.LOW: tk.BooleanVar(
                value=True
            ),
            IncomeGroup.MIDDLE: tk.BooleanVar(
                value=True
            ),
            IncomeGroup.HIGH: tk.BooleanVar(
                value=True
            ),
        }

        self.prepare_networks_var = tk.BooleanVar(
            value=True
        )
        self.prepare_region_var = tk.BooleanVar(
            value=True
        )
        self.clear_outputs_var = tk.BooleanVar(
            value=False
        )
        self.force_network_var = tk.BooleanVar(
            value=False
        )

        self.status_var = tk.StringVar(
            value="Pronto para executar."
        )

        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(
            self,
            padding=18,
        )
        container.pack(
            fill="both",
            expand=True,
        )

        title = ttk.Label(
            container,
            text="EtPilot — configurar execução",
            font=(
                "TkDefaultFont",
                15,
                "bold",
            ),
        )
        title.pack(
            anchor="w",
            pady=(0, 14),
        )

        spatial = ttk.LabelFrame(
            container,
            text="Recorte espacial",
            padding=12,
        )
        spatial.pack(
            fill="x",
            pady=6,
        )

        self._labeled_combobox(
            spatial,
            "Região",
            self.region_var,
            tuple(REGION_VALUES),
            row=0,
        )

        self._labeled_combobox(
            spatial,
            "Uso da região",
            self.region_mode_var,
            tuple(REGION_MODE_LABELS),
            row=1,
        )

        ttk.Label(
            spatial,
            text=(
                "Recorte da análise: O/D, agentes, redes e GTFS ficam na região.\n"
                "Somente janela do mapa: a simulação usa a cidade inteira e "
                "o mapa é enquadrado na região."
            ),
            wraplength=560,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 0),
        )

        population = ttk.LabelFrame(
            container,
            text="População sintética",
            padding=12,
        )
        population.pack(
            fill="x",
            pady=6,
        )

        ttk.Label(
            population,
            text="Classes sociais",
        ).grid(
            row=0,
            column=0,
            sticky="nw",
            padx=(0, 14),
        )

        classes = ttk.Frame(
            population
        )
        classes.grid(
            row=0,
            column=1,
            sticky="w",
        )

        for index, (
            group,
            variable,
        ) in enumerate(
            self.income_vars.items()
        ):
            ttk.Checkbutton(
                classes,
                text=group.value,
                variable=variable,
            ).grid(
                row=0,
                column=index,
                padx=(0, 12),
                sticky="w",
            )

        self._labeled_entry(
            population,
            "Número de agentes",
            self.n_agents_var,
            row=1,
        )

        temporal = ttk.LabelFrame(
            container,
            text="Tempo e comportamento",
            padding=12,
        )
        temporal.pack(
            fill="x",
            pady=6,
        )

        self._labeled_entry(
            temporal,
            "Período",
            self.period_value_var,
            row=0,
        )

        self._labeled_combobox(
            temporal,
            "Unidade",
            self.period_unit_var,
            ("hours", "days"),
            row=1,
        )

        self._labeled_combobox(
            temporal,
            "Cenário",
            self.scenario_var,
            tuple(SCENARIO_LABELS),
            row=2,
        )

        self._labeled_entry(
            temporal,
            "Seed",
            self.seed_var,
            row=3,
        )

        preparation = ttk.LabelFrame(
            container,
            text="Preparação",
            padding=12,
        )
        preparation.pack(
            fill="x",
            pady=6,
        )

        ttk.Checkbutton(
            preparation,
            text="Preparar/reutilizar redes OSM",
            variable=self.prepare_networks_var,
        ).pack(
            anchor="w",
        )
        ttk.Checkbutton(
            preparation,
            text="Preparar cache espacial",
            variable=self.prepare_region_var,
        ).pack(
            anchor="w",
        )
        ttk.Checkbutton(
            preparation,
            text="Limpar outputs antes de executar",
            variable=self.clear_outputs_var,
        ).pack(
            anchor="w",
        )
        ttk.Checkbutton(
            preparation,
            text="Forçar novo download das redes",
            variable=self.force_network_var,
        ).pack(
            anchor="w",
        )

        actions = ttk.Frame(
            container
        )
        actions.pack(
            fill="x",
            pady=(16, 4),
        )

        self.run_button = ttk.Button(
            actions,
            text="Executar pipeline",
            command=self._start_pipeline,
        )
        self.run_button.pack(
            side="left",
        )

        ttk.Label(
            actions,
            textvariable=self.status_var,
        ).pack(
            side="left",
            padx=14,
        )

        ttk.Label(
            container,
            text=(
                "Os mapas por modo e por classe social são gerados "
                "automaticamente nos outputs da execução."
            ),
            wraplength=590,
        ).pack(
            anchor="w",
            pady=(8, 0),
        )

    @staticmethod
    def _labeled_entry(
        parent,
        label: str,
        variable: tk.StringVar,
        *,
        row: int,
    ) -> None:
        ttk.Label(
            parent,
            text=label,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 14),
            pady=4,
        )

        ttk.Entry(
            parent,
            textvariable=variable,
            width=22,
        ).grid(
            row=row,
            column=1,
            sticky="w",
            pady=4,
        )

    @staticmethod
    def _labeled_combobox(
        parent,
        label: str,
        variable: tk.StringVar,
        values,
        *,
        row: int,
    ) -> None:
        ttk.Label(
            parent,
            text=label,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 14),
            pady=4,
        )

        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            width=28,
        ).grid(
            row=row,
            column=1,
            sticky="w",
            pady=4,
        )

    def _build_config(
        self,
    ) -> PilotRunConfig:
        selected_groups = tuple(
            group
            for group, variable
            in self.income_vars.items()
            if variable.get()
        )

        return PilotRunConfig(
            region=REGION_VALUES[
                self.region_var.get()
            ],
            region_mode=REGION_MODE_LABELS[
                self.region_mode_var.get()
            ],
            income_groups=selected_groups,
            period=SimulationPeriod(
                value=int(
                    self.period_value_var.get()
                ),
                unit=self.period_unit_var.get(),
            ),
            n_agents=int(
                self.n_agents_var.get()
            ),
            seed=int(
                self.seed_var.get()
            ),
            scenario=SCENARIO_LABELS[
                self.scenario_var.get()
            ],
            prepare_networks=(
                self.prepare_networks_var.get()
            ),
            prepare_region=(
                self.prepare_region_var.get()
            ),
            clear_outputs=(
                self.clear_outputs_var.get()
            ),
            force_network_download=(
                self.force_network_var.get()
            ),
        )

    def _start_pipeline(
        self,
    ) -> None:
        try:
            run_config = self._build_config()
        except Exception as exc:
            messagebox.showerror(
                "Configuração inválida",
                str(exc),
            )
            return

        self.run_button.configure(
            state="disabled"
        )
        self.status_var.set(
            "Executando... acompanhe também o terminal."
        )

        worker = threading.Thread(
            target=self._run_worker,
            args=(run_config,),
            daemon=True,
        )
        worker.start()

    def _run_worker(
        self,
        run_config: PilotRunConfig,
    ) -> None:
        try:
            run_pipeline(
                run_config
            )
        except Exception as exc:
            traceback.print_exc()
            self.after(
                0,
                self._execution_failed,
                str(exc),
            )
            return

        self.after(
            0,
            self._execution_finished,
        )

    def _execution_finished(
        self,
    ) -> None:
        self.run_button.configure(
            state="normal"
        )
        self.status_var.set(
            "Pipeline concluído."
        )
        messagebox.showinfo(
            "EtPilot",
            "Execução concluída. Consulte a pasta outputs.",
        )

    def _execution_failed(
        self,
        message: str,
    ) -> None:
        self.run_button.configure(
            state="normal"
        )
        self.status_var.set(
            "A execução terminou com erro."
        )
        messagebox.showerror(
            "Erro na execução",
            message,
        )


def main() -> None:
    app = PipelineApp()
    app.mainloop()


if __name__ == "__main__":
    main()
