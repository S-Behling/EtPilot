from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def assign_sectors_to_neighborhoods(
    sector_neighborhood_fragments,
) -> pd.DataFrame:
    """
    Atribui cada setor censitário a um único bairro.

    Quando um setor intersecta mais de um bairro, ele é associado ao
    bairro que contém a maior área do setor. Isso evita dupla contagem
    nas estatísticas por bairro.
    """
    required = {
        "CD_SETOR",
        "CD_BAIRRO",
        "NM_BAIRRO",
        "RENDA_MED_SETOR",
        "AREA_FRAG_M2",
    }

    missing = required - set(sector_neighborhood_fragments.columns)

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

    base["CD_SETOR"] = base["CD_SETOR"].astype("string")
    base["CD_BAIRRO"] = base["CD_BAIRRO"].astype("string")
    base["RENDA_MED_SETOR"] = pd.to_numeric(
        base["RENDA_MED_SETOR"],
        errors="coerce",
    )

    # Maior interseção espacial = bairro atribuído ao setor.
    base = (
        base.sort_values(
            ["CD_SETOR", "AREA_FRAG_M2"],
            ascending=[True, False],
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
    Gera duas tabelas:
    1. resumo por bairro;
    2. detalhe por setor censitário.

    O desvio padrão é calculado entre os valores de RENDA_MED_SETOR dos
    setores atribuídos a cada bairro. Setores com renda fora do intervalo
    média ± 1 desvio padrão são sinalizados.
    """
    detail = assign_sectors_to_neighborhoods(
        sector_neighborhood_fragments
    )

    valid = detail.dropna(
        subset=["RENDA_MED_SETOR"]
    ).copy()

    stats = (
        valid.groupby(
            ["CD_BAIRRO", "NM_BAIRRO"],
            dropna=False,
        )["RENDA_MED_SETOR"]
        .agg(
            N_SETORES="count",
            MEDIA_RENDA_SETOR="mean",
            DESVIO_PADRAO_RENDA="std",
            MIN_RENDA_SETOR="min",
            MAX_RENDA_SETOR="max",
        )
        .reset_index()
    )

    stats["LIMITE_INFERIOR_1DP"] = (
        stats["MEDIA_RENDA_SETOR"]
        - stats["DESVIO_PADRAO_RENDA"]
    )
    stats["LIMITE_SUPERIOR_1DP"] = (
        stats["MEDIA_RENDA_SETOR"]
        + stats["DESVIO_PADRAO_RENDA"]
    )

    detail = detail.merge(
        stats[
            [
                "CD_BAIRRO",
                "NM_BAIRRO",
                "MEDIA_RENDA_SETOR",
                "DESVIO_PADRAO_RENDA",
                "LIMITE_INFERIOR_1DP",
                "LIMITE_SUPERIOR_1DP",
            ]
        ],
        on=["CD_BAIRRO", "NM_BAIRRO"],
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

    detail["FORA_1_DESVIO_PADRAO"] = (
        detail["RENDA_MED_SETOR"].lt(
            detail["LIMITE_INFERIOR_1DP"]
        )
        | detail["RENDA_MED_SETOR"].gt(
            detail["LIMITE_SUPERIOR_1DP"]
        )
    )

    def join_sectors(group: pd.DataFrame) -> str:
        return "; ".join(
            sorted(
                group["CD_SETOR"]
                .dropna()
                .astype(str)
                .unique()
            )
        )

    def join_outlier_sectors(group: pd.DataFrame) -> str:
        outliers = group.loc[
            group["FORA_1_DESVIO_PADRAO"]
        ]

        if outliers.empty:
            return ""

        return "; ".join(
            outliers["CD_SETOR"]
            .dropna()
            .astype(str)
            .sort_values()
            .tolist()
        )

    def join_outlier_incomes(group: pd.DataFrame) -> str:
        outliers = group.loc[
            group["FORA_1_DESVIO_PADRAO"]
            & group["RENDA_MED_SETOR"].notna()
        ].sort_values("RENDA_MED_SETOR")

        if outliers.empty:
            return ""

        return "; ".join(
            f"{row.CD_SETOR}: R$ {row.RENDA_MED_SETOR:,.2f}"
            for row in outliers.itertuples()
        )

    grouped = (
        detail.groupby(
            ["CD_BAIRRO", "NM_BAIRRO"],
            dropna=False,
            sort=True,
        )
    )

    lists = grouped.apply(
        lambda group: pd.Series(
            {
                "SETORES_CENSITARIOS": join_sectors(group),
                "N_SETORES_FORA_1DP": int(
                    group["FORA_1_DESVIO_PADRAO"].sum()
                ),
                "SETORES_FORA_1DP": join_outlier_sectors(group),
                "RENDAS_FORA_1DP": join_outlier_incomes(group),
            }
        ),
        include_groups=False,
    ).reset_index()

    summary = stats.merge(
        lists,
        on=["CD_BAIRRO", "NM_BAIRRO"],
        how="outer",
        validate="one_to_one",
    )

    ordered_summary_columns = [
        "CD_BAIRRO",
        "NM_BAIRRO",
        "N_SETORES",
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
        "FORA_1_DESVIO_PADRAO",
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
    Exporta resumo e detalhe em CSV e em um único arquivo XLSX.
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
            {"text_wrap": True, "valign": "top"}
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
