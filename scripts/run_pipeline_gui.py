"""Interface gráfica retro/pixel para configurar e executar o EtPilot.

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
from src.core.config import (
    load_project_config,
    load_regions_config,
)
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

REGION_MODE_LABELS = {
    "Recorte da análise": "analysis",
    "Somente janela do mapa": "plot_only",
}

SCENARIO_LABELS = {
    "Diferenciado": "differentiated",
    "Baseline": "baseline",
}


PALETTE = {
    "grid": "#C7D9F6",
    "grid_line": "#F6F2EE",
    "ink": "#3A2424",
    "peach": "#F7D9BF",
    "cream": "#FFF3DF",
    "teal": "#62C5BF",
    "orange": "#F4A45F",
    "yellow": "#F4CD62",
    "pink": "#ED7594",
    "blue": "#7EA6E8",
    "white": "#FFFFFF",
    "muted": "#8A6B62",
}

FONT = ("Courier New", 10)
FONT_BOLD = ("Courier New", 10, "bold")
FONT_TITLE = ("Courier New", 19, "bold")
FONT_SMALL = ("Courier New", 9)


class PipelineApp(tk.Tk):
    """Janela de configuração do pipeline."""

    def __init__(self) -> None:
        super().__init__()

        self.title("EtPilot — Configuração do piloto")
        self.geometry("820x900")
        self.minsize(760, 820)
        self.configure(
            bg=PALETTE["grid"]
        )

        self._configure_ttk_style()

        project_config = load_project_config()
        regions_config = load_regions_config(
            project_config
        )
        default_region = project_config[
            "study_area"
        ][
            "default_region"
        ]

        self.enabled_region_values = {}
        self.disabled_region_labels = []

        for region_name, definition in (
            regions_config.get(
                "regions",
                {},
            ).items()
        ):
            label = REGION_LABELS.get(
                region_name,
                definition.get(
                    "label",
                    region_name,
                ),
            )

            if definition.get(
                "enabled",
                False,
            ):
                self.enabled_region_values[
                    label
                ] = region_name
            else:
                self.disabled_region_labels.append(
                    label
                )

        if not self.enabled_region_values:
            raise ValueError(
                "Nenhuma região está habilitada em config/regions.json."
            )

        default_label = next(
            (
                label
                for label, value
                in self.enabled_region_values.items()
                if value == default_region
            ),
            next(
                iter(
                    self.enabled_region_values
                )
            ),
        )

        self.region_var = tk.StringVar(
            value=default_label
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
        self.bind(
            "<Configure>",
            self._redraw_grid,
        )

    def _configure_ttk_style(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Retro.TCombobox",
            font=FONT,
            foreground=PALETTE["ink"],
            fieldbackground=PALETTE["cream"],
            background=PALETTE["cream"],
            bordercolor=PALETTE["ink"],
            lightcolor=PALETTE["ink"],
            darkcolor=PALETTE["ink"],
            arrowsize=14,
            padding=4,
        )
        style.map(
            "Retro.TCombobox",
            fieldbackground=[
                ("readonly", PALETTE["cream"])
            ],
            foreground=[
                ("readonly", PALETTE["ink"])
            ],
        )

    def _build_ui(self) -> None:
        self.background = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            bg=PALETTE["grid"],
        )
        self.background.pack(
            fill="both",
            expand=True,
        )

        self.container = tk.Frame(
            self.background,
            bg=PALETTE["grid"],
        )

        self.window_id = self.background.create_window(
            0,
            0,
            anchor="nw",
            window=self.container,
        )

        header = tk.Frame(
            self.container,
            bg=PALETTE["grid"],
        )
        header.pack(
            fill="x",
            padx=24,
            pady=(18, 12),
        )

        tk.Label(
            header,
            text="ETPILOT",
            bg=PALETTE["grid"],
            fg=PALETTE["ink"],
            font=FONT_TITLE,
        ).pack(
            side="left",
        )

        tk.Label(
            header,
            text="  CONFIGURAR EXECUÇÃO",
            bg=PALETTE["ink"],
            fg=PALETTE["cream"],
            font=FONT_BOLD,
            padx=10,
            pady=5,
        ).pack(
            side="left",
            padx=(12, 0),
        )

        spatial = self._panel(
            "RECORTE ESPACIAL",
            accent="teal",
        )

        self._labeled_combobox(
            spatial,
            "Região",
            self.region_var,
            tuple(
                self.enabled_region_values
            ),
            row=0,
        )

        self._labeled_combobox(
            spatial,
            "Uso da região",
            self.region_mode_var,
            tuple(REGION_MODE_LABELS),
            row=1,
        )

        explanation = (
            "Recorte da análise: O/D, agentes, redes e GTFS ficam na região.\n"
            "Somente janela do mapa: simulação municipal, mapa enquadrado na região."
        )

        if self.disabled_region_labels:
            explanation += (
                "\nAinda não configuradas: "
                + ", ".join(
                    self.disabled_region_labels
                )
                + "."
            )

        tk.Label(
            spatial,
            text=explanation,
            justify="left",
            anchor="w",
            wraplength=680,
            bg=PALETTE["peach"],
            fg=PALETTE["muted"],
            font=FONT_SMALL,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(10, 2),
        )

        population = self._panel(
            "POPULAÇÃO SINTÉTICA",
            accent="orange",
        )

        tk.Label(
            population,
            text="Classes sociais",
            bg=PALETTE["peach"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 16),
            pady=6,
        )

        classes = tk.Frame(
            population,
            bg=PALETTE["peach"],
        )
        classes.grid(
            row=0,
            column=1,
            sticky="w",
            pady=6,
        )

        class_accents = {
            IncomeGroup.LOW: PALETTE["teal"],
            IncomeGroup.MIDDLE: PALETTE["yellow"],
            IncomeGroup.HIGH: PALETTE["pink"],
        }

        for index, (
            group,
            variable,
        ) in enumerate(
            self.income_vars.items()
        ):
            tk.Checkbutton(
                classes,
                text=group.value,
                variable=variable,
                bg=PALETTE["peach"],
                activebackground=PALETTE["peach"],
                fg=PALETTE["ink"],
                activeforeground=PALETTE["ink"],
                selectcolor=class_accents[group],
                font=FONT,
                highlightthickness=0,
                bd=0,
            ).grid(
                row=0,
                column=index,
                padx=(0, 14),
                sticky="w",
            )

        self._labeled_entry(
            population,
            "Número de agentes",
            self.n_agents_var,
            row=1,
        )

        temporal = self._panel(
            "TEMPO E COMPORTAMENTO",
            accent="teal",
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

        preparation = self._panel(
            "PREPARAÇÃO",
            accent="orange",
        )

        options = (
            (
                "Preparar/reutilizar redes OSM",
                self.prepare_networks_var,
            ),
            (
                "Preparar cache espacial",
                self.prepare_region_var,
            ),
            (
                "Limpar outputs antes de executar",
                self.clear_outputs_var,
            ),
            (
                "Forçar novo download das redes",
                self.force_network_var,
            ),
        )

        for row, (
            text,
            variable,
        ) in enumerate(
            options
        ):
            tk.Checkbutton(
                preparation,
                text=text,
                variable=variable,
                bg=PALETTE["peach"],
                activebackground=PALETTE["peach"],
                fg=PALETTE["ink"],
                activeforeground=PALETTE["ink"],
                selectcolor=PALETTE["yellow"],
                font=FONT,
                anchor="w",
                highlightthickness=0,
                bd=0,
            ).grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="w",
                pady=3,
            )

        actions = tk.Frame(
            self.container,
            bg=PALETTE["grid"],
        )
        actions.pack(
            fill="x",
            padx=24,
            pady=(14, 6),
        )

        self.run_button = tk.Button(
            actions,
            text="▶ EXECUTAR PIPELINE",
            command=self._start_pipeline,
            font=FONT_BOLD,
            bg=PALETTE["teal"],
            fg=PALETTE["ink"],
            activebackground=PALETTE["yellow"],
            activeforeground=PALETTE["ink"],
            relief="raised",
            bd=3,
            padx=14,
            pady=8,
            cursor="hand2",
        )
        self.run_button.pack(
            side="left",
        )

        tk.Label(
            actions,
            textvariable=self.status_var,
            bg=PALETTE["cream"],
            fg=PALETTE["ink"],
            font=FONT,
            relief="solid",
            bd=1,
            padx=12,
            pady=8,
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(12, 0),
        )

        footer = tk.Frame(
            self.container,
            bg=PALETTE["grid"],
        )
        footer.pack(
            fill="x",
            padx=24,
            pady=(6, 20),
        )

        tk.Label(
            footer,
            text="♥ mapas por modo + classe social são gerados automaticamente",
            bg=PALETTE["grid"],
            fg=PALETTE["ink"],
            font=FONT_SMALL,
        ).pack(
            anchor="w",
        )

        self._redraw_grid()

    def _panel(
        self,
        title: str,
        *,
        accent: str,
    ) -> tk.Frame:
        outer = tk.Frame(
            self.container,
            bg=PALETTE["ink"],
            bd=0,
        )
        outer.pack(
            fill="x",
            padx=24,
            pady=8,
        )

        header = tk.Label(
            outer,
            text=f" {title} ",
            bg=PALETTE[accent],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
            anchor="w",
            padx=8,
            pady=5,
        )
        header.pack(
            fill="x",
            padx=2,
            pady=(2, 0),
        )

        body = tk.Frame(
            outer,
            bg=PALETTE["peach"],
            padx=14,
            pady=12,
        )
        body.pack(
            fill="x",
            padx=2,
            pady=(0, 2),
        )

        body.grid_columnconfigure(
            1,
            weight=1,
        )

        return body

    def _redraw_grid(
        self,
        _event=None,
    ) -> None:
        if not hasattr(
            self,
            "background",
        ):
            return

        width = max(
            self.winfo_width(),
            820,
        )
        height = max(
            self.container.winfo_reqheight(),
            self.winfo_height(),
            900,
        )

        self.background.delete(
            "gridline"
        )

        spacing = 28

        for x in range(
            0,
            width + spacing,
            spacing,
        ):
            self.background.create_line(
                x,
                0,
                x,
                height,
                fill=PALETTE["grid_line"],
                width=1,
                tags="gridline",
            )

        for y in range(
            0,
            height + spacing,
            spacing,
        ):
            self.background.create_line(
                0,
                y,
                width,
                y,
                fill=PALETTE["grid_line"],
                width=1,
                tags="gridline",
            )

        self.background.tag_lower(
            "gridline"
        )

        self.background.itemconfigure(
            self.window_id,
            width=width,
        )
        self.background.configure(
            scrollregion=(
                0,
                0,
                width,
                height,
            )
        )

    @staticmethod
    def _labeled_entry(
        parent,
        label: str,
        variable: tk.StringVar,
        *,
        row: int,
    ) -> None:
        tk.Label(
            parent,
            text=label,
            bg=PALETTE["peach"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 16),
            pady=6,
        )

        tk.Entry(
            parent,
            textvariable=variable,
            width=24,
            font=FONT,
            bg=PALETTE["cream"],
            fg=PALETTE["ink"],
            insertbackground=PALETTE["ink"],
            relief="solid",
            bd=1,
        ).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=6,
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
        tk.Label(
            parent,
            text=label,
            bg=PALETTE["peach"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 16),
            pady=6,
        )

        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            style="Retro.TCombobox",
            width=30,
        ).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=6,
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
            region=self.enabled_region_values[
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
            state="disabled",
            text="⏳ EXECUTANDO...",
            bg=PALETTE["orange"],
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
            state="normal",
            text="▶ EXECUTAR PIPELINE",
            bg=PALETTE["teal"],
        )
        self.status_var.set(
            "✓ Pipeline concluído."
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
            state="normal",
            text="▶ EXECUTAR PIPELINE",
            bg=PALETTE["pink"],
        )
        self.status_var.set(
            "✕ A execução terminou com erro."
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
