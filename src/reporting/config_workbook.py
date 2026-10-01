"""Exportação das configurações de uma rodada para Excel.

O objetivo deste módulo é criar um registro auditável dos parâmetros usados
em cada execução do EtPilot. O workbook reúne:

- os parâmetros específicos da rodada (PilotRunConfig);
- config/config.json;
- config/config_agents.json;
- config/regions.json;
- config/road_classification.json.

Cada fonte fica em uma aba separada, como solicitado. Estruturas JSON
aninhadas são achatadas em linhas `caminho -> valor`, o que mantém pesos,
probabilidades, faixas de renda e demais parâmetros explícitos sem perder a
hierarquia original.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import xlsxwriter

from src.core.config import CONFIG_DIR


CONFIG_FILES = (
    ("config", "config.json"),
    ("config_agents", "config_agents.json"),
    ("regions", "regions.json"),
    ("road_classification", "road_classification.json"),
)


def export_run_configuration_workbook(
    *,
    output_path: str | Path,
    run_metadata: Mapping[str, Any],
) -> Path:
    """Exporta todas as configurações relevantes para um único XLSX.

    Parameters
    ----------
    output_path:
        Caminho final do arquivo .xlsx.
    run_metadata:
        Dicionário com os parâmetros efetivamente usados na rodada. É o mesmo
        conteúdo registrado em run_config.json, acrescido posteriormente de
        informações sobre os arquivos gerados.

    Returns
    -------
    pathlib.Path
        Caminho do workbook produzido.
    """

    output = Path(output_path)
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    workbook = xlsxwriter.Workbook(
        output
    )

    # Formatos simples e neutros: o arquivo é um artefato técnico/auditável,
    # portanto a prioridade é leitura rápida e consistência.
    header_format = workbook.add_format(
        {
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#4F364B",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )
    path_format = workbook.add_format(
        {
            "font_color": "#4F364B",
            "text_wrap": True,
            "valign": "top",
        }
    )
    value_format = workbook.add_format(
        {
            "text_wrap": True,
            "valign": "top",
        }
    )
    numeric_format = workbook.add_format(
        {
            "num_format": "0.0000",
            "valign": "top",
        }
    )

    _write_flat_config_sheet(
        workbook=workbook,
        sheet_name="run_config",
        source_name="Parâmetros efetivos da rodada",
        data=dict(run_metadata),
        header_format=header_format,
        path_format=path_format,
        value_format=value_format,
        numeric_format=numeric_format,
    )

    for sheet_name, filename in CONFIG_FILES:
        path = CONFIG_DIR / filename

        if not path.exists():
            # A planilha deve continuar sendo gerada mesmo que uma configuração
            # opcional futura seja removida. Nesse caso a aba registra a ausência.
            data: dict[str, Any] = {
                "status": "arquivo não encontrado",
                "arquivo": str(path),
            }
        else:
            with path.open(
                "r",
                encoding="utf-8",
            ) as file:
                data = json.load(
                    file
                )

        _write_flat_config_sheet(
            workbook=workbook,
            sheet_name=sheet_name,
            source_name=filename,
            data=data,
            header_format=header_format,
            path_format=path_format,
            value_format=value_format,
            numeric_format=numeric_format,
        )


    # Além das abas brutas, esta visão resume em uma única tabela os parâmetros
    # sociais mais usados na interpretação do experimento: faixa de renda,
    # participação populacional, pesos de propósito, escolha modal e
    # decaimento de distância por classe.
    _write_social_class_summary(
        workbook=workbook,
        header_format=header_format,
        numeric_format=numeric_format,
    )

    workbook.close()

    return output


def _write_flat_config_sheet(
    *,
    workbook,
    sheet_name: str,
    source_name: str,
    data: Any,
    header_format,
    path_format,
    value_format,
    numeric_format,
) -> None:
    """Escreve uma configuração aninhada em formato tabular legível."""

    worksheet = workbook.add_worksheet(
        sheet_name[:31]
    )

    worksheet.write(
        0,
        0,
        "Fonte",
        header_format,
    )
    worksheet.write(
        0,
        1,
        "Caminho da configuração",
        header_format,
    )
    worksheet.write(
        0,
        2,
        "Valor",
        header_format,
    )

    rows = list(
        _flatten_config(
            data
        )
    )

    if not rows:
        rows = [
            ("", "")
        ]

    for row_index, (
        key_path,
        value,
    ) in enumerate(
        rows,
        start=1,
    ):
        worksheet.write(
            row_index,
            0,
            source_name,
            value_format,
        )
        worksheet.write(
            row_index,
            1,
            key_path,
            path_format,
        )

        if isinstance(
            value,
            bool,
        ):
            worksheet.write_boolean(
                row_index,
                2,
                value,
                value_format,
            )
        elif isinstance(
            value,
            (int, float),
        ) and not isinstance(
            value,
            bool,
        ):
            worksheet.write_number(
                row_index,
                2,
                float(value),
                numeric_format,
            )
        elif value is None:
            worksheet.write(
                row_index,
                2,
                "",
                value_format,
            )
        else:
            worksheet.write(
                row_index,
                2,
                str(value),
                value_format,
            )

    worksheet.freeze_panes(
        1,
        0,
    )
    worksheet.autofilter(
        0,
        0,
        len(rows),
        2,
    )

    # Larguras fixas evitam colunas gigantes quando algum caminho contém listas
    # extensas, especialmente na aba de regiões.
    worksheet.set_column(
        "A:A",
        28,
    )
    worksheet.set_column(
        "B:B",
        58,
    )
    worksheet.set_column(
        "C:C",
        42,
    )


def _flatten_config(
    value: Any,
    prefix: str = "",
):
    """Transforma dict/list recursivo em pares de caminho e valor.

    Exemplos:
    `mode_choice.differentiated.low.transit -> 0.55`
    `income.groups.low.max -> 4800`

    Dessa forma pesos e faixas de renda ficam explícitos sem criar uma lógica
    diferente para cada arquivo JSON.
    """

    if isinstance(
        value,
        Mapping,
    ):
        for key, child in value.items():
            child_prefix = (
                f"{prefix}.{key}"
                if prefix
                else str(key)
            )
            yield from _flatten_config(
                child,
                child_prefix,
            )
        return

    if isinstance(
        value,
        list,
    ):
        if not value:
            yield prefix, ""
            return

        # Listas simples são mantidas em uma única célula para tornar a planilha
        # compacta (ex.: lista de bairros ou categorias de destino).
        if all(
            not isinstance(
                item,
                (Mapping, list),
            )
            for item in value
        ):
            yield (
                prefix,
                "; ".join(
                    str(item)
                    for item in value
                ),
            )
            return

        for index, child in enumerate(
            value
        ):
            yield from _flatten_config(
                child,
                f"{prefix}[{index}]",
            )
        return

    yield prefix, value


def _write_social_class_summary(
    *,
    workbook,
    header_format,
    numeric_format,
) -> None:
    """Cria uma visão comparativa dos pesos e faixas por classe social."""

    project_path = CONFIG_DIR / "config.json"
    agents_path = CONFIG_DIR / "config_agents.json"

    if (
        not project_path.exists()
        or not agents_path.exists()
    ):
        return

    with project_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        project_config = json.load(
            file
        )

    with agents_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        agent_config = json.load(
            file
        )

    sheet = workbook.add_worksheet(
        "resumo_classes"
    )

    purposes = [
        "work",
        "education",
        "shopping",
        "health",
        "leisure",
    ]
    modes = [
        "walk",
        "bike",
        "transit",
        "car",
    ]

    headers = [
        "classe",
        "renda_min",
        "renda_max",
        "participacao",
        *[
            f"proposito_{purpose}"
            for purpose in purposes
        ],
        *[
            f"baseline_{mode}"
            for mode in modes
        ],
        *[
            f"diferenciado_{mode}"
            for mode in modes
        ],
        *[
            f"decaimento_{purpose}"
            for purpose in purposes
        ],
    ]

    for column, header in enumerate(
        headers
    ):
        sheet.write(
            0,
            column,
            header,
            header_format,
        )

    income_groups = project_config.get(
        "income",
        {},
    ).get(
        "groups",
        {},
    )
    purpose_choice = agent_config.get(
        "purpose_choice",
        {},
    )
    mode_choice = agent_config.get(
        "mode_choice",
        {},
    )
    distance_decay = (
        agent_config.get(
            "destination_choice",
            {},
        )
        .get(
            "distance_decay_per_km",
            {},
        )
    )

    for row, income_group in enumerate(
        (
            "low",
            "middle",
            "high",
        ),
        start=1,
    ):
        income = income_groups.get(
            income_group,
            {},
        )

        values = [
            income_group,
            income.get("min"),
            income.get("max"),
            income.get("share"),
        ]

        values.extend(
            purpose_choice.get(
                income_group,
                {},
            ).get(
                purpose,
                None,
            )
            for purpose in purposes
        )

        for scenario in (
            "baseline",
            "differentiated",
        ):
            scenario_config = (
                mode_choice.get(
                    scenario,
                    {},
                ).get(
                    income_group,
                    {},
                )
            )
            values.extend(
                scenario_config.get(
                    mode,
                    None,
                )
                for mode in modes
            )

        values.extend(
            distance_decay.get(
                purpose,
                {},
            ).get(
                income_group,
                None,
            )
            for purpose in purposes
        )

        for column, value in enumerate(
            values
        ):
            if value is None:
                sheet.write(
                    row,
                    column,
                    "",
                )
            elif isinstance(
                value,
                (int, float),
            ):
                sheet.write_number(
                    row,
                    column,
                    float(value),
                    numeric_format,
                )
            else:
                sheet.write(
                    row,
                    column,
                    str(value),
                )

    sheet.freeze_panes(
        1,
        1,
    )
    sheet.autofilter(
        0,
        0,
        3,
        len(headers) - 1,
    )
    sheet.set_column(
        0,
        0,
        14,
    )
    sheet.set_column(
        1,
        len(headers) - 1,
        16,
    )
