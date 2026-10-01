"""Interface gráfica compacta para configurar e executar o EtPilot.

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
    PilotRunConfig,
    SimulationPeriod,
)


PALETTE = {
    "background": "#F6F5EC",
    "surface": "#EFE7DA",
    "surface_alt": "#E6DACB",
    "brandy_rose": "#B29079",
    "terracotta": "#A6533D",
    "terracotta_dark": "#7F3D30",
    "red_soft": "#C87568",
    "red_pale": "#E7B8AE",
    "ink": "#2F2724",
    "muted": "#75655E",
    "white": "#FFFFFF",
    "border": "#D6C8BB",
}

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_TITLE = ("Segoe UI", 22, "bold")
FONT_SUBTITLE = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)


REGION_MODE_LABELS = {
    "Recorte da análise": "analysis",
    "Somente janela do mapa": "plot_only",
}

SCENARIO_LABELS = {
    "Diferenciado": "differentiated",
    "Baseline": "baseline",
}


class PipelineApp(tk.Tk):
    """Janela principal da configuração do piloto."""

    def __init__(self) -> None:
        super().__init__()

        self.title("EtPilot — Configuração do piloto")
        self.geometry("930x690")
        self.minsize(860, 640)
        self.configure(
            bg=PALETTE["background"]
        )

        self._configure_styles()
        self._load_regions()
        self._build_variables()
        self._build_ui()

    def _configure_styles(self) -> None:
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Modern.TCombobox",
            font=FONT,
            foreground=PALETTE["ink"],
            fieldbackground=PALETTE["white"],
            background=PALETTE["white"],
            bordercolor=PALETTE["border"],
            lightcolor=PALETTE["border"],
            darkcolor=PALETTE["border"],
            arrowsize=15,
            padding=5,
        )
        style.map(
            "Modern.TCombobox",
            fieldbackground=[
                ("readonly", PALETTE["white"])
            ],
            foreground=[
                ("readonly", PALETTE["ink"])
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
            next(
                iter(
                    self.enabled_region_values
                )
            ),
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

    def _build_ui(self) -> None:
        shell = tk.Frame(
            self,
            bg=PALETTE["background"],
            padx=24,
            pady=18,
        )
        shell.pack(
            fill="both",
            expand=True,
        )

        self._build_header(
            shell
        )

        content = tk.Frame(
            shell,
            bg=PALETTE["background"],
        )
        content.pack(
            fill="both",
            expand=True,
            pady=(12, 10),
        )

        content.grid_columnconfigure(
            0,
            weight=1,
            uniform="column",
        )
        content.grid_columnconfigure(
            1,
            weight=1,
            uniform="column",
        )
        content.grid_rowconfigure(
            0,
            weight=1,
        )
        content.grid_rowconfigure(
            1,
            weight=1,
        )

        spatial = self._card(
            content,
            title="Recorte espacial",
            subtitle=(
                "Escolha a região oficial do Orçamento Participativo "
                "e como ela participa da análise."
            ),
            row=0,
            column=0,
            accent="terracotta",
        )
        self._build_spatial_card(
            spatial
        )

        population = self._card(
            content,
            title="População sintética",
            subtitle=(
                "Defina classes sociais e tamanho da população simulada."
            ),
            row=0,
            column=1,
            accent="brandy_rose",
        )
        self._build_population_card(
            population
        )

        temporal = self._card(
            content,
            title="Tempo e comportamento",
            subtitle=(
                "Configure duração, unidade temporal, cenário e seed."
            ),
            row=1,
            column=0,
            accent="red_soft",
        )
        self._build_temporal_card(
            temporal
        )

        preparation = self._card(
            content,
            title="Preparação",
            subtitle=(
                "Controle o que será preparado ou reutilizado nesta rodada."
            ),
            row=1,
            column=1,
            accent="terracotta_dark",
        )
        self._build_preparation_card(
            preparation
        )

        self._build_footer(
            shell
        )

    def _build_header(
        self,
        parent: tk.Widget,
    ) -> None:
        header = tk.Frame(
            parent,
            bg=PALETTE["background"],
        )
        header.pack(
            fill="x",
        )

        title_block = tk.Frame(
            header,
            bg=PALETTE["background"],
        )
        title_block.pack(
            side="left",
            anchor="w",
        )

        tk.Label(
            title_block,
            text="EtPilot",
            bg=PALETTE["background"],
            fg=PALETTE["ink"],
            font=FONT_TITLE,
        ).pack(
            anchor="w",
        )

        tk.Label(
            title_block,
            text=(
                "Configuração da simulação de mobilidade e segregação"
            ),
            bg=PALETTE["background"],
            fg=PALETTE["muted"],
            font=FONT_SUBTITLE,
        ).pack(
            anchor="w",
            pady=(2, 0),
        )

        badge = tk.Label(
            header,
            text="PILOTO CONFIGURÁVEL",
            bg=PALETTE["red_pale"],
            fg=PALETTE["terracotta_dark"],
            font=FONT_BOLD,
            padx=12,
            pady=7,
        )
        badge.pack(
            side="right",
            anchor="n",
        )

    def _card(
        self,
        parent: tk.Widget,
        *,
        title: str,
        subtitle: str,
        row: int,
        column: int,
        accent: str,
    ) -> tk.Frame:
        outer = tk.Frame(
            parent,
            bg=PALETTE["border"],
        )
        outer.grid(
            row=row,
            column=column,
            sticky="nsew",
            padx=(
                0 if column == 0 else 8,
                8 if column == 0 else 0,
            ),
            pady=(
                0 if row == 0 else 8,
                8 if row == 0 else 0,
            ),
        )

        card = tk.Frame(
            outer,
            bg=PALETTE["surface"],
            padx=16,
            pady=13,
        )
        card.pack(
            fill="both",
            expand=True,
            padx=1,
            pady=1,
        )

        top = tk.Frame(
            card,
            bg=PALETTE["surface"],
        )
        top.pack(
            fill="x",
            pady=(0, 10),
        )

        marker = tk.Frame(
            top,
            bg=PALETTE[accent],
            width=8,
            height=38,
        )
        marker.pack(
            side="left",
            padx=(0, 10),
        )
        marker.pack_propagate(
            False
        )

        heading = tk.Frame(
            top,
            bg=PALETTE["surface"],
        )
        heading.pack(
            side="left",
            fill="x",
            expand=True,
        )

        tk.Label(
            heading,
            text=title,
            bg=PALETTE["surface"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
        ).pack(
            anchor="w",
        )

        tk.Label(
            heading,
            text=subtitle,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=FONT_SMALL,
            justify="left",
            wraplength=340,
        ).pack(
            anchor="w",
            pady=(2, 0),
        )

        body = tk.Frame(
            card,
            bg=PALETTE["surface"],
        )
        body.pack(
            fill="both",
            expand=True,
        )
        body.grid_columnconfigure(
            1,
            weight=1,
        )

        return body

    def _build_spatial_card(
        self,
        parent: tk.Frame,
    ) -> None:
        self._labeled_combobox(
            parent,
            "Região",
            self.region_var,
            tuple(
                self.enabled_region_values
            ),
            row=0,
        )
        self._labeled_combobox(
            parent,
            "Uso da região",
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
                "plot_only: mantém a cidade inteira e recorta apenas o mapa."
            ),
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=FONT_SMALL,
            justify="left",
            wraplength=350,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(8, 0),
        )

    def _build_population_card(
        self,
        parent: tk.Frame,
    ) -> None:
        tk.Label(
            parent,
            text="Classes sociais",
            bg=PALETTE["surface"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            pady=5,
        )

        classes = tk.Frame(
            parent,
            bg=PALETTE["surface"],
        )
        classes.grid(
            row=0,
            column=1,
            sticky="w",
            pady=5,
        )

        class_colors = {
            IncomeGroup.LOW: PALETTE["red_pale"],
            IncomeGroup.MIDDLE: PALETTE["brandy_rose"],
            IncomeGroup.HIGH: PALETTE["terracotta"],
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
                bg=PALETTE["surface"],
                activebackground=PALETTE["surface"],
                fg=PALETTE["ink"],
                activeforeground=PALETTE["ink"],
                selectcolor=class_colors[group],
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
            "Número de agentes",
            self.n_agents_var,
            row=1,
        )

    def _build_temporal_card(
        self,
        parent: tk.Frame,
    ) -> None:
        self._labeled_entry(
            parent,
            "Período",
            self.period_value_var,
            row=0,
        )
        self._labeled_combobox(
            parent,
            "Unidade",
            self.period_unit_var,
            ("hours", "days"),
            row=1,
        )
        self._labeled_combobox(
            parent,
            "Cenário",
            self.scenario_var,
            tuple(
                SCENARIO_LABELS
            ),
            row=2,
        )
        self._labeled_entry(
            parent,
            "Seed",
            self.seed_var,
            row=3,
        )

    def _build_preparation_card(
        self,
        parent: tk.Frame,
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
                bg=PALETTE["surface"],
                activebackground=PALETTE["surface"],
                fg=PALETTE["ink"],
                activeforeground=PALETTE["ink"],
                selectcolor=PALETTE["red_pale"],
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
            bg=PALETTE["background"],
        )
        footer.pack(
            fill="x",
            pady=(4, 0),
        )

        self.run_button = tk.Button(
            footer,
            text="Executar pipeline  →",
            command=self._start_pipeline,
            bg=PALETTE["terracotta"],
            fg=PALETTE["white"],
            activebackground=PALETTE["terracotta_dark"],
            activeforeground=PALETTE["white"],
            font=FONT_BOLD,
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            cursor="hand2",
        )
        self.run_button.pack(
            side="left",
        )

        status = tk.Label(
            footer,
            textvariable=self.status_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=FONT_SMALL,
            padx=12,
            pady=10,
            anchor="w",
        )
        status.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(12, 0),
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
            bg=PALETTE["surface"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
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
            bg=PALETTE["white"],
            fg=PALETTE["ink"],
            insertbackground=PALETTE["ink"],
            font=FONT,
            relief="solid",
            bd=1,
        ).grid(
            row=row,
            column=1,
            sticky="ew",
            pady=5,
            ipady=4,
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
            bg=PALETTE["surface"],
            fg=PALETTE["ink"],
            font=FONT_BOLD,
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
            style="Modern.TCombobox",
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
            text="Executando...",
            bg=PALETTE["brandy_rose"],
        )
        self.status_var.set(
            "Executando. O progresso detalhado continua disponível no terminal."
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
            text="Executar novamente  →",
            bg=PALETTE["terracotta"],
        )
        self.status_var.set(
            "Pipeline concluído. Consulte a pasta outputs."
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
            text="Tentar novamente  →",
            bg=PALETTE["terracotta"],
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
