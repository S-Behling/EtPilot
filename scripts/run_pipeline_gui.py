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

PERIOD_UNIT_LABELS = {
    "Horas": "hours",
    "Dias": "days",
}

INCOME_LABELS = {
    IncomeGroup.LOW: "Baixa",
    IncomeGroup.MIDDLE: "Média",
    IncomeGroup.HIGH: "Alta",
}


def _rounded_polygon(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    *,
    fill: str,
    outline: str | None = None,
    width: int = 1,
    tags=(),
):
    """Desenha um retângulo visualmente arredondado em um Canvas."""

    radius = min(
        radius,
        (x2 - x1) / 2,
        (y2 - y1) / 2,
    )

    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]

    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=36,
        fill=fill,
        outline=outline or fill,
        width=width,
        tags=tags,
    )


class RoundedPanel(tk.Canvas):
    """Container com cantos arredondados que hospeda widgets Tk normais."""

    def __init__(
        self,
        parent,
        *,
        fill: str,
        outline: str | None = None,
        radius: int = 18,
        padding: int = 1,
        background: str | None = None,
        height: int | None = None,
    ) -> None:
        super().__init__(
            parent,
            bg=background or parent.cget("bg"),
            highlightthickness=0,
            bd=0,
            height=height or 1,
        )

        self._fill = fill
        self._outline = outline or fill
        self._radius = radius
        self._padding = padding

        self.body = tk.Frame(
            self,
            bg=fill,
        )
        self._window = self.create_window(
            padding,
            padding,
            anchor="nw",
            window=self.body,
        )

        self.bind(
            "<Configure>",
            self._redraw,
        )

    def _redraw(
        self,
        event,
    ) -> None:
        self.delete(
            "rounded-bg"
        )

        _rounded_polygon(
            self,
            self._padding,
            self._padding,
            max(
                event.width - self._padding,
                self._padding + 2,
            ),
            max(
                event.height - self._padding,
                self._padding + 2,
            ),
            self._radius,
            fill=self._fill,
            outline=self._outline,
            tags=("rounded-bg",),
        )

        self.tag_lower(
            "rounded-bg"
        )

        self.coords(
            self._window,
            self._padding + 1,
            self._padding + 1,
        )
        self.itemconfigure(
            self._window,
            width=max(
                event.width
                - 2 * (self._padding + 1),
                1,
            ),
            height=max(
                event.height
                - 2 * (self._padding + 1),
                1,
            ),
        )


class RoundedButton(tk.Canvas):
    """Botão arredondado desenhado em Canvas."""

    def __init__(
        self,
        parent,
        *,
        text: str,
        command,
        width: int = 190,
        height: int = 42,
        radius: int = 20,
        fill: str,
        hover_fill: str,
        foreground: str,
    ) -> None:
        super().__init__(
            parent,
            width=width,
            height=height,
            bg=parent.cget("bg"),
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

        self._text = text
        self._command = command
        self._fill = fill
        self._hover_fill = hover_fill
        self._foreground = foreground
        self._radius = radius
        self._enabled = True

        self.bind(
            "<Button-1>",
            self._on_click,
        )
        self.bind(
            "<Enter>",
            lambda _event: self._draw(
                self._hover_fill
            ),
        )
        self.bind(
            "<Leave>",
            lambda _event: self._draw(
                self._fill
            ),
        )

        self._draw(
            self._fill
        )

    def _draw(
        self,
        fill: str,
    ) -> None:
        self.delete(
            "all"
        )

        width = int(
            self.cget("width")
        )
        height = int(
            self.cget("height")
        )

        _rounded_polygon(
            self,
            1,
            1,
            width - 1,
            height - 1,
            self._radius,
            fill=fill,
        )

        self.create_text(
            width / 2,
            height / 2,
            text=self._text,
            fill=self._foreground,
            font=FONT_BOLD,
        )

    def _on_click(
        self,
        _event,
    ) -> None:
        if self._enabled:
            self._command()

    def set_state(
        self,
        *,
        enabled: bool,
        text: str | None = None,
        fill: str | None = None,
    ) -> None:
        self._enabled = enabled

        if text is not None:
            self._text = text

        if fill is not None:
            self._fill = fill

        self.configure(
            cursor=(
                "hand2"
                if enabled
                else "arrow"
            )
        )

        self._draw(
            self._fill
        )


class PipelineApp(tk.Tk):
    """Janela principal da configuração do piloto."""

    def __init__(self) -> None:
        super().__init__()

        self.title("EtPilot — Configuração do piloto")
        self.geometry("930x650")
        self.minsize(860, 610)
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
        outer = RoundedPanel(
            parent,
            fill=PALETTE["surface"],
            outline=PALETTE["border"],
            radius=22,
            padding=1,
            background=PALETTE["background"],
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

        card = outer.body
        card.configure(
            padx=16,
            pady=13,
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
                text=INCOME_LABELS[group],
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
            tuple(
                PERIOD_UNIT_LABELS
            ),
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

        self.run_button = RoundedButton(
            footer,
            text="Executar pipeline  →",
            command=self._start_pipeline,
            fill=PALETTE["terracotta"],
            hover_fill=PALETTE["terracotta_dark"],
            foreground=PALETTE["white"],
            width=205,
            height=44,
            radius=22,
        )
        self.run_button.pack(
            side="left",
        )

        status_panel = RoundedPanel(
            footer,
            fill=PALETTE["surface"],
            outline=PALETTE["surface"],
            radius=20,
            padding=0,
            background=PALETTE["background"],
            height=44,
        )
        status_panel.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(12, 0),
        )

        tk.Label(
            status_panel.body,
            textvariable=self.status_var,
            bg=PALETTE["surface"],
            fg=PALETTE["muted"],
            font=FONT_SMALL,
            padx=14,
            pady=10,
            anchor="w",
        ).pack(
            fill="both",
            expand=True,
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

        self.run_button.set_state(
            enabled=False,
            text="Executando...",
            fill=PALETTE["brandy_rose"],
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
        self.run_button.set_state(
            enabled=True,
            text="Executar novamente  →",
            fill=PALETTE["terracotta"],
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
        self.run_button.set_state(
            enabled=True,
            text="Tentar novamente  →",
            fill=PALETTE["terracotta"],
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
