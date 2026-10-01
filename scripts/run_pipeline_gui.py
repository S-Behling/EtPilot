"""Interface gráfica estilo Windows 95 para configurar e executar o EtPilot.

Dois pontos de entrada independentes usam o mesmo PilotRunConfig:

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
    AVAILABLE_PLOTS,
    PLOT_EDGE_USAGE,
    PLOT_EDGE_USAGE_BY_INCOME,
    PLOT_EDGE_USAGE_BY_MODE,
    PLOT_EDGE_USAGE_BY_MODE_INCOME,
    PLOT_ROUTES_OSM,
    PLOT_ROUTES_TRANSIT,
    PilotRunConfig,
    SimulationPeriod,
)


WIN95 = {
    "desktop": "#008080",
    "face": "#C0C0C0",
    "highlight": "#FFFFFF",
    "light": "#DFDFDF",
    "shadow": "#808080",
    "dark_shadow": "#404040",
    "title": "#000080",
    "title_text": "#FFFFFF",
    "text": "#000000",
    "field": "#FFFFFF",
    "disabled": "#808080",
}

FONT = ("MS Sans Serif", 9)
FONT_BOLD = ("MS Sans Serif", 9, "bold")
FONT_TITLE = ("MS Sans Serif", 10, "bold")
FONT_SMALL = ("MS Sans Serif", 8)


REGION_MODE_LABELS = {
    "Recorte da análise": "analysis",
    "Somente janela do mapa": "plot_only",
}

SCENARIO_LABELS = {
    "Diferenciado": "differentiated",
    "Baseline": "baseline",
}

PERIOD_UNIT_LABELS = {
    "Horas": "hours",
    "Dias": "days",
}

INCOME_LABELS = {
    IncomeGroup.LOW: "Baixa",
    IncomeGroup.MIDDLE: "Média",
    IncomeGroup.HIGH: "Alta",
}

PLOT_LABELS = {
    PLOT_ROUTES_OSM: "Rotas OSM dos agentes",
    PLOT_ROUTES_TRANSIT: "Rotas de transporte coletivo",
    PLOT_EDGE_USAGE: "Uso geral das redes",
    PLOT_EDGE_USAGE_BY_MODE: "Trechos por modo de viagem",
    PLOT_EDGE_USAGE_BY_INCOME: "Trechos por classe social",
    PLOT_EDGE_USAGE_BY_MODE_INCOME: "Trechos por modo + classe social",
}


class PipelineApp(tk.Tk):
    """Janela principal da configuração do piloto."""

    def __init__(self) -> None:
        super().__init__()

        self.title("EtPilot - Configuração do piloto")
        self.geometry("900x620")
        self.minsize(840, 580)
        self.configure(bg=WIN95["face"])

        self._configure_ttk_style()
        self._load_regions()
        self._build_variables()
        self._build_ui()

    def _configure_ttk_style(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Win95.TCombobox",
            font=FONT,
            foreground=WIN95["text"],
            fieldbackground=WIN95["field"],
            background=WIN95["face"],
            bordercolor=WIN95["shadow"],
            lightcolor=WIN95["highlight"],
            darkcolor=WIN95["dark_shadow"],
            arrowsize=14,
            padding=3,
        )
        style.map(
            "Win95.TCombobox",
            fieldbackground=[
                ("readonly", WIN95["field"]),
            ],
            foreground=[
                ("readonly", WIN95["text"]),
            ],
            background=[
                ("readonly", WIN95["face"]),
            ],
        )

    def _load_regions(self) -> None:
        project_config = load_project_config()
        regions_config = load_regions_config(
            project_config
        )

        definitions = regions_config.get(
            "regions",
            {},
        )

        enabled = [
            (
                definition.get(
                    "op_region_number",
                ),
                definition.get(
                    "label",
                    name,
                ),
                name,
            )
            for name, definition
            in definitions.items()
            if definition.get(
                "enabled",
                False,
            )
        ]

        enabled.sort(
            key=lambda item: (
                item[0] is not None,
                item[0]
                if item[0] is not None
                else -1,
            )
        )

        self.enabled_region_values = {
            label: name
            for _, label, name in enabled
        }

        if not self.enabled_region_values:
            raise ValueError(
                "Nenhuma região está habilitada em config/regions.json."
            )

        default_region = project_config[
            "study_area"
        ][
            "default_region"
        ]

        self.default_region_label = next(
            (
                label
                for label, name
                in self.enabled_region_values.items()
                if name == default_region
            ),
            next(iter(self.enabled_region_values)),
        )

    def _build_variables(self) -> None:
        self.region_var = tk.StringVar(
            value=self.default_region_label
        )
        self.region_mode_var = tk.StringVar(
            value="Recorte da análise"
        )
        self.period_value_var = tk.StringVar(
            value="24"
        )
        self.period_unit_var = tk.StringVar(
            value="Horas"
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
            IncomeGroup.LOW: tk.BooleanVar(value=True),
            IncomeGroup.MIDDLE: tk.BooleanVar(value=True),
            IncomeGroup.HIGH: tk.BooleanVar(value=True),
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

        self.plot_vars = {
            plot_name: tk.BooleanVar(value=True)
            for plot_name in AVAILABLE_PLOTS
        }

        self.status_var = tk.StringVar(
            value="Pronto."
        )

    def _build_ui(self) -> None:
        outer = tk.Frame(
            self,
            bg=WIN95["face"],
            bd=2,
            relief="raised",
        )
        outer.pack(
            fill="both",
            expand=True,
            padx=4,
            pady=4,
        )

        self._build_title_bar(outer)

        notebook = ttk.Notebook(outer)
        notebook.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=(6, 0),
        )

        config_tab = tk.Frame(
            notebook,
            bg=WIN95["face"],
        )
        maps_tab = tk.Frame(
            notebook,
            bg=WIN95["face"],
        )

        notebook.add(
            config_tab,
            text=" Configuração ",
        )
        notebook.add(
            maps_tab,
            text=" Mapas ",
        )

        self._build_config_tab(
            config_tab
        )
        self._build_maps_tab(
            maps_tab
        )

        self._build_footer(
            outer
        )

    def _build_config_tab(
        self,
        parent: tk.Widget,
    ) -> None:
        content = tk.Frame(
            parent,
            bg=WIN95["face"],
            padx=8,
            pady=8,
        )
        content.pack(
            fill="both",
            expand=True,
        )

        content.grid_columnconfigure(
            0,
            weight=1,
            uniform="col",
        )
        content.grid_columnconfigure(
            1,
            weight=1,
            uniform="col",
        )
        content.grid_rowconfigure(
            0,
            weight=1,
        )
        content.grid_rowconfigure(
            1,
            weight=1,
        )

        spatial = self._group(
            content,
            "Recorte espacial",
            row=0,
            column=0,
        )
        self._build_spatial_group(spatial)

        population = self._group(
            content,
            "População sintética",
            row=0,
            column=1,
        )
        self._build_population_group(
            population
        )

        temporal = self._group(
            content,
            "Tempo e comportamento",
            row=1,
            column=0,
        )
        self._build_temporal_group(temporal)

        preparation = self._group(
            content,
            "Preparação",
            row=1,
            column=1,
        )
        self._build_preparation_group(
            preparation
        )

    def _build_maps_tab(
        self,
        parent: tk.Widget,
    ) -> None:
        content = tk.Frame(
            parent,
            bg=WIN95["face"],
            padx=12,
            pady=12,
        )
        content.pack(
            fill="both",
            expand=True,
        )

        selector = tk.LabelFrame(
            content,
            text=" Mapas a gerar ",
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_BOLD,
            bd=2,
            relief="groove",
            padx=12,
            pady=10,
        )
        selector.pack(
            fill="x",
        )

        for row, plot_name in enumerate(
            AVAILABLE_PLOTS
        ):
            tk.Checkbutton(
                selector,
                text=PLOT_LABELS[plot_name],
                variable=self.plot_vars[
                    plot_name
                ],
                bg=WIN95["face"],
                activebackground=WIN95["face"],
                fg=WIN95["text"],
                activeforeground=WIN95["text"],
                selectcolor=WIN95["field"],
                font=FONT,
                bd=0,
                highlightthickness=0,
                anchor="w",
            ).grid(
                row=row,
                column=0,
                sticky="w",
                pady=4,
            )

        buttons = tk.Frame(
            selector,
            bg=WIN95["face"],
        )
        buttons.grid(
            row=len(AVAILABLE_PLOTS),
            column=0,
            sticky="w",
            pady=(10, 0),
        )

        tk.Button(
            buttons,
            text="Selecionar todos",
            command=lambda: self._set_all_plots(
                True
            ),
            bg=WIN95["face"],
            fg=WIN95["text"],
            activebackground=WIN95["light"],
            font=FONT,
            relief="raised",
            bd=2,
            padx=10,
            pady=3,
        ).pack(
            side="left",
        )

        tk.Button(
            buttons,
            text="Limpar seleção",
            command=lambda: self._set_all_plots(
                False
            ),
            bg=WIN95["face"],
            fg=WIN95["text"],
            activebackground=WIN95["light"],
            font=FONT,
            relief="raised",
            bd=2,
            padx=10,
            pady=3,
        ).pack(
            side="left",
            padx=(8, 0),
        )

        legend = tk.LabelFrame(
            content,
            text=" Convenção visual dos mapas ",
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_BOLD,
            bd=2,
            relief="groove",
            padx=12,
            pady=10,
        )
        legend.pack(
            fill="both",
            expand=True,
            pady=(12, 0),
        )

        tk.Label(
            legend,
            text=(
                "Classe social = cor\n"
                "Baixa: Lavender Gray  #CABAD7\n"
                "Média: Eggplant       #4F364B\n"
                "Alta:  Cinnabar       #DB3E1D\n\n"
                "Modo de viagem = tipo de linha\n"
                "Walk: pontilhada\n"
                "Bike: tracejada\n"
                "Carro: contínua\n"
                "Ônibus: contínua com setas\n\n"
                "Fundo dos mapas: Albescant White  #F7E9DE"
            ),
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT,
            justify="left",
            anchor="nw",
        ).pack(
            anchor="nw",
        )

    def _set_all_plots(
        self,
        selected: bool,
    ) -> None:
        for variable in self.plot_vars.values():
            variable.set(selected)

    def _build_title_bar(
        self,
        parent: tk.Widget,
    ) -> None:
        bar = tk.Frame(
            parent,
            bg=WIN95["title"],
            height=28,
        )
        bar.pack(
            fill="x",
            padx=2,
            pady=2,
        )
        bar.pack_propagate(False)

        tk.Label(
            bar,
            text=" EtPilot - Configuração do piloto",
            bg=WIN95["title"],
            fg=WIN95["title_text"],
            font=FONT_TITLE,
            anchor="w",
        ).pack(
            side="left",
            fill="both",
            expand=True,
        )

        tk.Label(
            bar,
            text=" _ ",
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_BOLD,
            bd=2,
            relief="raised",
            padx=4,
        ).pack(
            side="right",
            padx=(2, 0),
            pady=2,
        )

        tk.Label(
            bar,
            text=" □ ",
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_BOLD,
            bd=2,
            relief="raised",
            padx=4,
        ).pack(
            side="right",
            padx=(2, 0),
            pady=2,
        )

    def _group(
        self,
        parent: tk.Widget,
        title: str,
        *,
        row: int,
        column: int,
    ) -> tk.LabelFrame:
        group = tk.LabelFrame(
            parent,
            text=f" {title} ",
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_BOLD,
            bd=2,
            relief="groove",
            padx=10,
            pady=8,
        )
        group.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(
                0 if column == 0 else 6,
                6 if column == 0 else 0,
            ),
            pady=(
                0 if row == 0 else 6,
                6 if row == 0 else 0,
            ),
        )
        group.grid_columnconfigure(
            1,
            weight=1,
        )
        return group

    def _build_spatial_group(
        self,
        parent: tk.LabelFrame,
    ) -> None:
        self._labeled_combobox(
            parent,
            "Região:",
            self.region_var,
            tuple(
                self.enabled_region_values
            ),
            row=0,
        )
        self._labeled_combobox(
            parent,
            "Uso da região:",
            self.region_mode_var,
            tuple(
                REGION_MODE_LABELS
            ),
            row=1,
        )

        tk.Label(
            parent,
            text=(
                "analysis: restringe O/D, agentes, redes e GTFS.\n"
                "plot_only: cidade inteira, recorte apenas no mapa."
            ),
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_SMALL,
            justify="left",
            anchor="w",
            wraplength=330,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(10, 0),
        )

    def _build_population_group(
        self,
        parent: tk.LabelFrame,
    ) -> None:
        tk.Label(
            parent,
            text="Classes sociais:",
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=5,
        )

        classes = tk.Frame(
            parent,
            bg=WIN95["face"],
        )
        classes.grid(
            row=0,
            column=1,
            sticky="w",
            pady=5,
        )

        for index, (
            group,
            variable,
        ) in enumerate(
            self.income_vars.items()
        ):
            tk.Checkbutton(
                classes,
                text=INCOME_LABELS[group],
                variable=variable,
                bg=WIN95["face"],
                activebackground=WIN95["face"],
                fg=WIN95["text"],
                activeforeground=WIN95["text"],
                selectcolor=WIN95["field"],
                font=FONT,
                bd=0,
                highlightthickness=0,
            ).grid(
                row=0,
                column=index,
                sticky="w",
                padx=(0, 10),
            )

        self._labeled_entry(
            parent,
            "Número de agentes:",
            self.n_agents_var,
            row=1,
        )

    def _build_temporal_group(
        self,
        parent: tk.LabelFrame,
    ) -> None:
        self._labeled_entry(
            parent,
            "Período:",
            self.period_value_var,
            row=0,
        )
        self._labeled_combobox(
            parent,
            "Unidade:",
            self.period_unit_var,
            tuple(
                PERIOD_UNIT_LABELS
            ),
            row=1,
        )
        self._labeled_combobox(
            parent,
            "Cenário:",
            self.scenario_var,
            tuple(
                SCENARIO_LABELS
            ),
            row=2,
        )
        self._labeled_entry(
            parent,
            "Seed:",
            self.seed_var,
            row=3,
        )

    def _build_preparation_group(
        self,
        parent: tk.LabelFrame,
    ) -> None:
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
            label,
            variable,
        ) in enumerate(
            options
        ):
            tk.Checkbutton(
                parent,
                text=label,
                variable=variable,
                bg=WIN95["face"],
                activebackground=WIN95["face"],
                fg=WIN95["text"],
                activeforeground=WIN95["text"],
                selectcolor=WIN95["field"],
                font=FONT,
                bd=0,
                highlightthickness=0,
                anchor="w",
            ).grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="w",
                pady=4,
            )

    def _build_footer(
        self,
        parent: tk.Widget,
    ) -> None:
        footer = tk.Frame(
            parent,
            bg=WIN95["face"],
            padx=8,
            pady=8,
        )
        footer.pack(
            fill="x",
        )

        self.run_button = tk.Button(
            footer,
            text="Executar",
            command=self._start_pipeline,
            bg=WIN95["face"],
            fg=WIN95["text"],
            activebackground=WIN95["light"],
            activeforeground=WIN95["text"],
            font=FONT_BOLD,
            relief="raised",
            bd=2,
            padx=20,
            pady=5,
            cursor="hand2",
        )
        self.run_button.pack(
            side="right",
        )

        status_box = tk.Frame(
            footer,
            bg=WIN95["face"],
            bd=2,
            relief="sunken",
        )
        status_box.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8),
        )

        tk.Label(
            status_box,
            textvariable=self.status_var,
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT_SMALL,
            anchor="w",
            padx=6,
            pady=5,
        ).pack(
            fill="x",
        )

    @staticmethod
    def _labeled_entry(
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        *,
        row: int,
    ) -> None:
        tk.Label(
            parent,
            text=label,
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=5,
        )

        tk.Entry(
            parent,
            textvariable=variable,
            bg=WIN95["field"],
            fg=WIN95["text"],
            insertbackground=WIN95["text"],
            font=FONT,
            relief="sunken",
            bd=2,
        ).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=5,
            ipady=2,
        )

    @staticmethod
    def _labeled_combobox(
        parent: tk.Widget,
        label: str,
        variable: tk.StringVar,
        values,
        *,
        row: int,
    ) -> None:
        tk.Label(
            parent,
            text=label,
            bg=WIN95["face"],
            fg=WIN95["text"],
            font=FONT,
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 12),
            pady=5,
        )

        ttk.Combobox(
            parent,
            textvariable=variable,
            values=values,
            state="readonly",
            style="Win95.TCombobox",
        ).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=5,
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
                unit=PERIOD_UNIT_LABELS[
                    self.period_unit_var.get()
                ],
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
            selected_plots=tuple(
                plot_name
                for plot_name, variable
                in self.plot_vars.items()
                if variable.get()
            ),
        )

    def _start_pipeline(
        self,
    ) -> None:
        try:
            run_config = self._build_config()
        except Exception as exc:
            messagebox.showerror(
                "EtPilot",
                str(exc),
            )
            return

        self.run_button.configure(
            state="disabled",
            text="Executando...",
        )
        self.status_var.set(
            "Executando pipeline. Consulte o terminal para detalhes."
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
            text="Executar novamente",
        )
        self.status_var.set(
            "Concluído. Consulte a pasta outputs."
        )
        messagebox.showinfo(
            "EtPilot",
            "Execução concluída.",
        )

    def _execution_failed(
        self,
        message: str,
    ) -> None:
        self.run_button.configure(
            state="normal",
            text="Tentar novamente",
        )
        self.status_var.set(
            "Erro na execução."
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
