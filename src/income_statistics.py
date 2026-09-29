from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _format_brl(value: float) -> str:
    """Formata um valor numérico em padrão monetário brasileiro."""
    formatted = f"{value:,.2f}"
    formatted = (
        formatted.replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )
    return f"R$ {formatted}"


def assign_sectors_to_neighborhoods(
    sector_neighborhood_fragments,
) -> pd.DataFrame:
    """
    Atribui cada setor censitário a um único bairro.

    Quando um setor intersecta mais de um bairro, ele é associado ao
    bairro que contém a maior área do setor. Isso evita dupla contagem
    nas estatísticas agregadas por bairro.
    """
    required = {
        "CD_SETOR",
        "CD_BAIRRO",
        "NM_BAIRRO",
        "RENDA_MED_SETOR",
        "AREA_FRAG_M2",
    }

    missing = required - set(
        sector_neighborhood_fragments.columns
    )

    if missing:
        raise KeyError(
            "Colunas ausentes para agregação por bairro: "
            f"{sorted(missing)}"
        )

    base = sector_neighborhood_fragments[
        [
            "CD_SETOR",
            "CD_BAIRRO",
            "NM_BAIRRO",
            "RENDA_MED_SETOR",
            "AREA_FRAG_M2",
        ]
    ].copy()

    base["CD_SETOR"] = (
        base["CD_SETOR"]
        .astype("string")
        .str.strip()
    )
    base["CD_BAIRRO"] = (
        base["CD_BAIRRO"]
        .astype("string")
        .str.strip()
    )
    base["RENDA_MED_SETOR"] = pd.to_numeric(
        base["RENDA_MED_SETOR"],
        errors="coerce",
    )
    base["AREA_FRAG_M2"] = pd.to_numeric(
        base["AREA_FRAG_M2"],
        errors="coerce",
    )

    # Maior interseção espacial = bairro atribuído ao setor.
    # CD_BAIRRO serve apenas como critério determinístico em caso de empate.
    base = (
        base.sort_values(
            [
                "CD_SETOR",
                "AREA_FRAG_M2",
                "CD_BAIRRO",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .drop_duplicates(
            subset="CD_SETOR",
            keep="first",
        )
        .reset_index(drop=True)
    )

    return base


def build_neighborhood_income_tables(
    sector_neighborhood_fragments,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Gera:
    1. resumo estatístico por bairro;
    2. detalhe por setor censitário.

    A média e o desvio padrão descrevem a distribuição dos valores de
    RENDA_MED_SETOR entre os setores associados a cada bairro.

    Um setor é marcado como FORA_1_DESVIO_PADRAO quando sua renda setorial
    está abaixo de média - 1 DP ou acima de média + 1 DP do bairro.
    """
    detail = assign_sectors_to_neighborhoods(
        sector_neighborhood_fragments
    )

    group_keys = [
        "CD_BAIRRO",
        "NM_BAIRRO",
    ]

    total_counts = (
        detail.groupby(
            group_keys,
            dropna=False,
        )["CD_SETOR"]
        .nunique()
        .rename("N_SETORES")
        .reset_index()
    )

    valid = detail.dropna(
        subset=["RENDA_MED_SETOR"]
    ).copy()

    stats = (
        valid.groupby(
            group_keys,
            dropna=False,
        )["RENDA_MED_SETOR"]
        .agg(
            N_SETORES_COM_RENDA="count",
            MEDIA_RENDA_SETOR="mean",
            DESVIO_PADRAO_RENDA="std",
            MIN_RENDA_SETOR="min",
            MAX_RENDA_SETOR="max",
        )
        .reset_index()
    )

    summary = total_counts.merge(
        stats,
        on=group_keys,
        how="left",
        validate="one_to_one",
    )

    summary["LIMITE_INFERIOR_1DP"] = (
        summary["MEDIA_RENDA_SETOR"]
        - summary["DESVIO_PADRAO_RENDA"]
    )
    summary["LIMITE_SUPERIOR_1DP"] = (
        summary["MEDIA_RENDA_SETOR"]
        + summary["DESVIO_PADRAO_RENDA"]
    )

    detail = detail.merge(
        summary[
            group_keys
            + [
                "MEDIA_RENDA_SETOR",
                "DESVIO_PADRAO_RENDA",
                "LIMITE_INFERIOR_1DP",
                "LIMITE_SUPERIOR_1DP",
            ]
        ],
        on=group_keys,
        how="left",
        validate="many_to_one",
    )

    detail["DESVIO_DA_MEDIA"] = (
        detail["RENDA_MED_SETOR"]
        - detail["MEDIA_RENDA_SETOR"]
    )

    detail["Z_SCORE_BAIRRO"] = np.where(
        detail["DESVIO_PADRAO_RENDA"].gt(0),
        detail["DESVIO_DA_MEDIA"]
        / detail["DESVIO_PADRAO_RENDA"],
        np.nan,
    )

    detail["ABAIXO_1_DESVIO_PADRAO"] = (
        detail["RENDA_MED_SETOR"].notna()
        & detail["DESVIO_PADRAO_RENDA"].notna()
        & detail["RENDA_MED_SETOR"].lt(
            detail["LIMITE_INFERIOR_1DP"]
        )
    )

    detail["ACIMA_1_DESVIO_PADRAO"] = (
        detail["RENDA_MED_SETOR"].notna()
        & detail["DESVIO_PADRAO_RENDA"].notna()
        & detail["RENDA_MED_SETOR"].gt(
            detail["LIMITE_SUPERIOR_1DP"]
        )
    )

    detail["FORA_1_DESVIO_PADRAO"] = (
        detail["ABAIXO_1_DESVIO_PADRAO"]
        | detail["ACIMA_1_DESVIO_PADRAO"]
    )

    conditions = [
        detail["RENDA_MED_SETOR"].isna(),
        detail["DESVIO_PADRAO_RENDA"].isna(),
        detail["ABAIXO_1_DESVIO_PADRAO"],
        detail["ACIMA_1_DESVIO_PADRAO"],
    ]
    choices = [
        "sem renda",
        "desvio padrão indisponível",
        "abaixo de -1 DP",
        "acima de +1 DP",
    ]

    detail["CLASSE_DESVIO"] = np.select(
        conditions,
        choices,
        default="dentro de ±1 DP",
    )

    list_rows = []

    for keys, group in detail.groupby(
        group_keys,
        dropna=False,
        sort=True,
    ):
        if not isinstance(keys, tuple):
            keys = (keys,)

        outliers = group.loc[
            group["FORA_1_DESVIO_PADRAO"]
        ].sort_values(
            "RENDA_MED_SETOR"
        )

        below = group.loc[
            group["ABAIXO_1_DESVIO_PADRAO"]
        ].sort_values(
            "RENDA_MED_SETOR"
        )

        above = group.loc[
            group["ACIMA_1_DESVIO_PADRAO"]
        ].sort_values(
            "RENDA_MED_SETOR"
        )

        sector_codes = (
            group["CD_SETOR"]
            .dropna()
            .astype(str)
            .sort_values()
            .unique()
            .tolist()
        )

        def sector_list(frame: pd.DataFrame) -> str:
            return "; ".join(
                frame["CD_SETOR"]
                .dropna()
                .astype(str)
                .sort_values()
                .tolist()
            )

        def income_list(frame: pd.DataFrame) -> str:
            return "; ".join(
                (
                    f"{row.CD_SETOR}: "
                    f"{_format_brl(row.RENDA_MED_SETOR)}"
                )
                for row in frame.itertuples()
                if pd.notna(row.RENDA_MED_SETOR)
            )

        list_rows.append(
            {
                "CD_BAIRRO": keys[0],
                "NM_BAIRRO": keys[1],
                "SETORES_CENSITARIOS": "; ".join(
                    sector_codes
                ),
                "N_SETORES_FORA_1DP": int(
                    len(outliers)
                ),
                "SETORES_FORA_1DP": sector_list(
                    outliers
                ),
                "RENDAS_FORA_1DP": income_list(
                    outliers
                ),
                "N_SETORES_ABAIXO_1DP": int(
                    len(below)
                ),
                "SETORES_ABAIXO_1DP": sector_list(
                    below
                ),
                "RENDAS_ABAIXO_1DP": income_list(
                    below
                ),
                "N_SETORES_ACIMA_1DP": int(
                    len(above)
                ),
                "SETORES_ACIMA_1DP": sector_list(
                    above
                ),
                "RENDAS_ACIMA_1DP": income_list(
                    above
                ),
            }
        )

    lists = pd.DataFrame(list_rows)

    summary = summary.merge(
        lists,
        on=group_keys,
        how="left",
        validate="one_to_one",
    )

    ordered_summary_columns = [
        "CD_BAIRRO",
        "NM_BAIRRO",
        "N_SETORES",
        "N_SETORES_COM_RENDA",
        "SETORES_CENSITARIOS",
        "MEDIA_RENDA_SETOR",
        "DESVIO_PADRAO_RENDA",
        "MIN_RENDA_SETOR",
        "MAX_RENDA_SETOR",
        "LIMITE_INFERIOR_1DP",
        "LIMITE_SUPERIOR_1DP",
        "N_SETORES_FORA_1DP",
        "SETORES_FORA_1DP",
        "RENDAS_FORA_1DP",
        "N_SETORES_ABAIXO_1DP",
        "SETORES_ABAIXO_1DP",
        "RENDAS_ABAIXO_1DP",
        "N_SETORES_ACIMA_1DP",
        "SETORES_ACIMA_1DP",
        "RENDAS_ACIMA_1DP",
    ]

    summary = summary[
        ordered_summary_columns
    ].sort_values(
        ["NM_BAIRRO", "CD_BAIRRO"]
    ).reset_index(drop=True)

    ordered_detail_columns = [
        "CD_BAIRRO",
        "NM_BAIRRO",
        "CD_SETOR",
        "RENDA_MED_SETOR",
        "MEDIA_RENDA_SETOR",
        "DESVIO_PADRAO_RENDA",
        "DESVIO_DA_MEDIA",
        "Z_SCORE_BAIRRO",
        "LIMITE_INFERIOR_1DP",
        "LIMITE_SUPERIOR_1DP",
        "ABAIXO_1_DESVIO_PADRAO",
        "ACIMA_1_DESVIO_PADRAO",
        "FORA_1_DESVIO_PADRAO",
        "CLASSE_DESVIO",
    ]

    detail = detail[
        ordered_detail_columns
    ].sort_values(
        ["NM_BAIRRO", "CD_SETOR"]
    ).reset_index(drop=True)

    return summary, detail


def export_neighborhood_income_tables(
    sector_neighborhood_fragments,
    output_dir: str | Path,
) -> dict[str, Path]:
    """
    Exporta o resumo e o detalhe em CSV e em um arquivo XLSX.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary, detail = build_neighborhood_income_tables(
        sector_neighborhood_fragments
    )

    summary_csv = (
        output_dir / "resumo_renda_bairros_setores.csv"
    )
    detail_csv = (
        output_dir / "renda_setores_por_bairro_detalhe.csv"
    )
    xlsx_path = (
        output_dir / "renda_bairros_setores_estatisticas.xlsx"
    )

    summary.to_csv(
        summary_csv,
        index=False,
        encoding="utf-8-sig",
    )
    detail.to_csv(
        detail_csv,
        index=False,
        encoding="utf-8-sig",
    )

    with pd.ExcelWriter(
        xlsx_path,
        engine="xlsxwriter",
    ) as writer:
        summary.to_excel(
            writer,
            sheet_name="resumo_bairros",
            index=False,
        )
        detail.to_excel(
            writer,
            sheet_name="setores_detalhe",
            index=False,
        )

        workbook = writer.book

        currency_format = workbook.add_format(
            {"num_format": 'R$ #,##0.00'}
        )
        decimal_format = workbook.add_format(
            {"num_format": "0.00"}
        )
        wrap_format = workbook.add_format(
            {
                "text_wrap": True,
                "valign": "top",
            }
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "text_wrap": True,
                "valign": "top",
                "border": 1,
            }
        )

        for sheet_name, dataframe in [
            ("resumo_bairros", summary),
            ("setores_detalhe", detail),
        ]:
            worksheet = writer.sheets[sheet_name]
            worksheet.freeze_panes(1, 0)
            worksheet.autofilter(
                0,
                0,
                len(dataframe),
                len(dataframe.columns) - 1,
            )

            for col_idx, column in enumerate(
                dataframe.columns
            ):
                worksheet.write(
                    0,
                    col_idx,
                    column,
                    header_format,
                )

                if column in {
                    "MEDIA_RENDA_SETOR",
                    "DESVIO_PADRAO_RENDA",
                    "MIN_RENDA_SETOR",
                    "MAX_RENDA_SETOR",
                    "LIMITE_INFERIOR_1DP",
                    "LIMITE_SUPERIOR_1DP",
                    "RENDA_MED_SETOR",
                    "DESVIO_DA_MEDIA",
                }:
                    worksheet.set_column(
                        col_idx,
                        col_idx,
                        18,
                        currency_format,
                    )
                elif column == "Z_SCORE_BAIRRO":
                    worksheet.set_column(
                        col_idx,
                        col_idx,
                        14,
                        decimal_format,
                    )
                elif column in {
                    "SETORES_CENSITARIOS",
                    "SETORES_FORA_1DP",
                    "RENDAS_FORA_1DP",
                    "SETORES_ABAIXO_1DP",
                    "RENDAS_ABAIXO_1DP",
                    "SETORES_ACIMA_1DP",
                    "RENDAS_ACIMA_1DP",
                }:
                    worksheet.set_column(
                        col_idx,
                        col_idx,
                        45,
                        wrap_format,
                    )
                elif column == "NM_BAIRRO":
                    worksheet.set_column(
                        col_idx,
                        col_idx,
                        24,
                    )
                else:
                    worksheet.set_column(
                        col_idx,
                        col_idx,
                        18,
                    )

    print(
        f"[TABELA] Resumo por bairro: {summary_csv}"
    )
    print(
        f"[TABELA] Detalhe por setor: {detail_csv}"
    )
    print(
        f"[TABELA] Excel: {xlsx_path}"
    )

    return {
        "summary_csv": summary_csv,
        "detail_csv": detail_csv,
        "xlsx": xlsx_path,
    }
