from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _value_type(value: Any) -> str:
    """Retorna um rótulo simples para o tipo do valor configurado."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _format_value(value: Any) -> str:
    """Converte valores JSON em texto legível para a tabela."""
    if value is None:
        return ""

    if isinstance(value, list):
        if all(
            not isinstance(item, (dict, list))
            for item in value
        ):
            return "; ".join(
                str(item)
                for item in value
            )

        return json.dumps(
            value,
            ensure_ascii=False,
        )

    if isinstance(value, bool):
        return "true" if value else "false"

    return str(value)


def _flatten_config(
    value: Any,
    file_name: str,
    path_parts: list[str] | None = None,
) -> list[dict[str, str]]:
    """
    Transforma uma estrutura JSON aninhada em linhas tabulares.

    Dicionários são percorridos recursivamente. Listas simples são
    mantidas em uma única célula para preservar sua leitura como
    parâmetro configurado.
    """
    path_parts = path_parts or []
    rows: list[dict[str, str]] = []

    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(
                _flatten_config(
                    child,
                    file_name=file_name,
                    path_parts=path_parts + [str(key)],
                )
            )
        return rows

    full_path = ".".join(path_parts)
    section = path_parts[0] if path_parts else ""
    parameter = path_parts[-1] if path_parts else ""

    rows.append(
        {
            "ARQUIVO": file_name,
            "SECAO": section,
            "PARAMETRO": parameter,
            "CAMINHO": full_path,
            "VALOR": _format_value(value),
            "TIPO": _value_type(value),
        }
    )

    return rows


def build_config_summary(
    config_dir: str | Path,
) -> pd.DataFrame:
    """
    Lê automaticamente todos os arquivos *.json da pasta config
    e retorna uma tabela única com seus parâmetros.
    """
    config_dir = Path(config_dir)

    json_files = sorted(
        config_dir.glob("*.json")
    )

    if not json_files:
        raise FileNotFoundError(
            f"Nenhum arquivo JSON encontrado em {config_dir}"
        )

    rows: list[dict[str, str]] = []

    for json_path in json_files:
        with json_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        rows.extend(
            _flatten_config(
                data,
                file_name=json_path.name,
            )
        )

    summary = pd.DataFrame(
        rows,
        columns=[
            "ARQUIVO",
            "SECAO",
            "PARAMETRO",
            "CAMINHO",
            "VALOR",
            "TIPO",
        ],
    )

    return summary.sort_values(
        [
            "ARQUIVO",
            "SECAO",
            "CAMINHO",
        ]
    ).reset_index(drop=True)


def export_config_summary(
    config_dir: str | Path,
    output_dir: str | Path,
) -> dict[str, Path]:
    """
    Exporta um resumo dos JSONs de configuração em CSV e, quando
    xlsxwriter estiver disponível, também em Excel.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary = build_config_summary(
        config_dir=config_dir,
    )

    csv_path = (
        output_dir / "resumo_configuracoes_json.csv"
    )
    xlsx_path = (
        output_dir / "resumo_configuracoes_json.xlsx"
    )

    summary.to_csv(
        csv_path,
        index=False,
        encoding="utf-8-sig",
    )

    generated = {
        "config_summary_csv": csv_path,
    }

    try:
        import xlsxwriter  # noqa: F401
    except ModuleNotFoundError:
        print(
            "[AVISO] Pacote 'xlsxwriter' não instalado. "
            "O resumo das configurações foi gerado em CSV."
        )
    else:
        with pd.ExcelWriter(
            xlsx_path,
            engine="xlsxwriter",
        ) as writer:
            summary.to_excel(
                writer,
                sheet_name="configuracoes",
                index=False,
            )

            workbook = writer.book
            worksheet = writer.sheets[
                "configuracoes"
            ]

            header_format = workbook.add_format(
                {
                    "bold": True,
                    "text_wrap": True,
                    "valign": "top",
                    "border": 1,
                }
            )
            wrap_format = workbook.add_format(
                {
                    "text_wrap": True,
                    "valign": "top",
                }
            )

            worksheet.freeze_panes(
                1,
                0,
            )
            worksheet.autofilter(
                0,
                0,
                len(summary),
                len(summary.columns) - 1,
            )

            widths = {
                "ARQUIVO": 28,
                "SECAO": 24,
                "PARAMETRO": 28,
                "CAMINHO": 52,
                "VALOR": 55,
                "TIPO": 12,
            }

            for col_idx, column in enumerate(
                summary.columns
            ):
                worksheet.write(
                    0,
                    col_idx,
                    column,
                    header_format,
                )
                worksheet.set_column(
                    col_idx,
                    col_idx,
                    widths.get(column, 20),
                    wrap_format,
                )

        generated[
            "config_summary_xlsx"
        ] = xlsx_path

    print(
        f"[TABELA] Resumo das configurações JSON: {csv_path}"
    )

    if "config_summary_xlsx" in generated:
        print(
            f"[TABELA] Excel das configurações: {xlsx_path}"
        )

    return generated
