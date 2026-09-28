"""Visualizações espaciais v02 para o artigo.

A v02 preserva integralmente a v01 e prioriza figuras que mostrem o fenômeno:
- trajetórias por classe social;
- todas as classes sobrepostas;
- fluxo agregado por classe;
- trajetos por modo x classe;
- mudança comportamental baseline x differentiated;
- participação modal observada por classe.

Importante
----------
O piloto atual gera uma viagem por agente por realização e usa uma hora fixa
para o roteamento GTFS. Portanto, os mapas chamados de "agregado diário" são
uma proxy espacial do conjunto completo das viagens simuladas, não uma
reconstrução horária de 24 horas. Essa limitação é registrada nos outputs.

Uso
---
python -m src.analysis.article_v02

Apenas se ainda não houver realizações nominais suficientes:
python -m src.analysis.article_v02 --run-core-if-missing
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.analysis.article_v01 import (
    _paired_agents,
    _read_comparison_geodata,
    _resolve_source_dir,
    _safe_bool,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"

INCOME_GROUPS = ("low", "middle", "high")
INCOME_LABELS = {
    "low": "Baixa renda",
    "middle": "Média renda",
    "high": "Alta renda",
}
INCOME_COLORS = {
    "low": "#0072B2",
    "middle": "#E69F00",
    "high": "#D55E00",
}

MODES = ("walk", "bike", "car", "transit")
MODE_LABELS = {
    "walk": "Caminhada",
    "bike": "Bicicleta",
    "car": "Automóvel",
    "transit": "Transporte coletivo",
}
MODE_COLORS = {
    "walk": "#009E73",
    "bike": "#CC79A7",
    "car": "#4D4D4D",
    "transit": "#56B4E9",
}


def _load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _article_config(config: dict) -> dict:
    return (
        config
        .get("analysis", {})
        .get("article_v02", {})
    )


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _parse_args():
    config = _load_config()
    article = _article_config(config)

    parser = argparse.ArgumentParser(
        description=(
            "Gera o pacote visual v02 do artigo sem substituir a v01."
        )
    )
    parser.add_argument(
        "--output-dir",
        default=article.get(
            "output_dir",
            "outputs/v02 artigo",
        ),
    )
    parser.add_argument(
        "--sensitivity-root",
        default=article.get(
            "sensitivity_root",
            "outputs/pilot/final_sensitivity",
        ),
    )
    parser.add_argument(
        "--reference-seed",
        type=int,
        default=int(
            article.get(
                "reference_seed",
                42,
            )
        ),
    )
    parser.add_argument(
        "--min-nominal-seeds",
        type=int,
        default=int(
            article.get(
                "min_nominal_seeds",
                1,
            )
        ),
    )
    parser.add_argument(
        "--run-core-if-missing",
        action="store_true",
        help=(
            "Executa article_v01 --core-only apenas se não houver "
            "realizações nominais suficientes."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(
            config.get(
                "analysis",
                {},
            ).get(
                "final_pilot_sensitivity",
                {},
            ).get(
                "max_parallel_workers",
                2,
            )
        ),
    )
    return parser.parse_args()


def _ensure_dirs(root: Path) -> dict[str, Path]:
    directories = {
        "root": root,
        "bases": root / "01_bases",
        "stats": root / "02_estatisticas",
        "figures": root / "03_figuras",
        "routes": root / "03_figuras" / "rotas_por_classe",
        "mode_class": root / "03_figuras" / "atlas_modo_classe",
        "maps": root / "04_mapas",
        "report": root / "05_relatorio",
    }

    for directory in directories.values():
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    return directories


def _available_runs_path(
    sensitivity_root: Path,
) -> Path | None:
    candidates = [
        sensitivity_root / "final_sensitivity_runs.csv",
        sensitivity_root / "final_sensitivity_runs_partial.csv",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_nominal_runs(
    sensitivity_root: Path,
) -> pd.DataFrame:
    path = _available_runs_path(
        sensitivity_root
    )

    if path is None:
        legacy = (
            PROJECT_ROOT
            / "outputs"
            / "pilot"
            / "population_sensitivity"
            / "n_0100_seed_42"
        )
        if legacy.exists():
            return pd.DataFrame(
                [
                    {
                        "run_id": "legacy_nominal_seed_42",
                        "experiment": "nominal_seed",
                        "seed": 42,
                        "source_dir": str(legacy),
                    }
                ]
            )
        return pd.DataFrame()

    runs = pd.read_csv(path)
    if "experiment" not in runs.columns:
        return pd.DataFrame()

    return (
        runs.loc[
            runs["experiment"]
            == "nominal_seed"
        ]
        .drop_duplicates(
            subset=["seed"],
            keep="last",
        )
        .sort_values("seed")
        .reset_index(drop=True)
    )


def _ensure_nominal_runs(
    *,
    sensitivity_root: Path,
    minimum: int,
    workers: int,
    run_if_missing: bool,
) -> pd.DataFrame:
    runs = _load_nominal_runs(
        sensitivity_root
    )

    if len(runs) >= minimum:
        return runs

    if not run_if_missing:
        raise RuntimeError(
            f"Foram encontradas {len(runs)} realizações nominais, "
            f"mas o mínimo configurado é {minimum}. "
            "Rode com --run-core-if-missing para completar as seeds "
            "ou reduza --min-nominal-seeds para visualizar o que já existe."
        )

    subprocess.run(
        [
            sys.executable,
            "-m",
            "src.analysis.article_v01",
            "--core-only",
            "--workers",
            str(workers),
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    runs = _load_nominal_runs(
        sensitivity_root
    )

    if len(runs) < minimum:
        raise RuntimeError(
            "A execução core terminou, mas ainda não há realizações "
            "nominais suficientes para a v02."
        )

    return runs


def _geometry_lookup(
    run_dir: Path,
) -> gpd.GeoDataFrame:
    comparison = _read_comparison_geodata(
        run_dir
    )

    return (
        comparison[
            [
                "analysis_segment_id",
                "geometry",
            ]
        ]
        .drop_duplicates(
            "analysis_segment_id"
        )
        .assign(
            analysis_segment_id=lambda frame: (
                frame[
                    "analysis_segment_id"
                ].astype(str)
            )
        )
        .reset_index(drop=True)
    )


def _network_extent(
    run_dir: Path,
) -> gpd.GeoDataFrame:
    return _geometry_lookup(
        run_dir
    )


def _load_differentiated_usage(
    *,
    nominal_runs: pd.DataFrame,
    sensitivity_root: Path,
) -> tuple[pd.DataFrame, dict[int, Path]]:
    frames = []
    source_dirs = {}

    for _, row in nominal_runs.iterrows():
        seed = int(row["seed"])
        run_dir = _resolve_source_dir(
            row,
            sensitivity_root=sensitivity_root,
        )
        source_dirs[seed] = run_dir

        path = (
            run_dir
            / "edge_usage_analysis_differentiated.csv"
        )
        if not path.exists():
            raise FileNotFoundError(path)

        usage = pd.read_csv(path)

        required = {
            "agent_id",
            "analysis_segment_id",
            "income_group",
            "mode",
        }
        missing = required - set(
            usage.columns
        )
        if missing:
            raise ValueError(
                "edge_usage_analysis_differentiated.csv "
                f"não possui as colunas: {sorted(missing)}"
            )

        usage["seed"] = seed
        usage["agent_id"] = (
            usage["agent_id"]
            .astype(str)
        )
        usage["analysis_segment_id"] = (
            usage["analysis_segment_id"]
            .astype(str)
        )

        frames.append(
            usage
        )

    return (
        pd.concat(
            frames,
            ignore_index=True,
        ),
        source_dirs,
    )


def _build_flow_bases(
    usage: pd.DataFrame,
    *,
    geometry: gpd.GeoDataFrame,
    n_seeds: int,
    dirs: dict[str, Path],
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
]:
    unique_agent_segment = (
        usage[
            [
                "seed",
                "agent_id",
                "analysis_segment_id",
                "income_group",
                "mode",
            ]
        ]
        .drop_duplicates()
    )

    class_flow = (
        unique_agent_segment
        .groupby(
            [
                "analysis_segment_id",
                "income_group",
            ],
            as_index=False,
        )
        .agg(
            agent_segment_uses=(
                "agent_id",
                "size",
            ),
            seeds_present=(
                "seed",
                "nunique",
            ),
        )
    )
    class_flow[
        "mean_agents_per_seed"
    ] = (
        class_flow[
            "agent_segment_uses"
        ]
        / float(n_seeds)
    )

    class_mode_flow = (
        unique_agent_segment
        .groupby(
            [
                "analysis_segment_id",
                "income_group",
                "mode",
            ],
            as_index=False,
        )
        .agg(
            agent_segment_uses=(
                "agent_id",
                "size",
            ),
            seeds_present=(
                "seed",
                "nunique",
            ),
        )
    )
    class_mode_flow[
        "mean_agents_per_seed"
    ] = (
        class_mode_flow[
            "agent_segment_uses"
        ]
        / float(n_seeds)
    )

    class_flow_geo = gpd.GeoDataFrame(
        class_flow.merge(
            geometry,
            on="analysis_segment_id",
            how="left",
            validate="many_to_one",
        ),
        geometry="geometry",
        crs=geometry.crs,
    )
    class_mode_geo = gpd.GeoDataFrame(
        class_mode_flow.merge(
            geometry,
            on="analysis_segment_id",
            how="left",
            validate="many_to_one",
        ),
        geometry="geometry",
        crs=geometry.crs,
    )

    for name, frame, layer in [
        (
            "base04_fluxo_segmento_classe",
            class_flow_geo,
            "fluxo_classe",
        ),
        (
            "base05_fluxo_segmento_classe_modo",
            class_mode_geo,
            "fluxo_classe_modo",
        ),
    ]:
        frame.drop(
            columns="geometry"
        ).to_csv(
            dirs["bases"]
            / f"{name}.csv",
            index=False,
            encoding="utf-8",
        )

        gpkg = (
            dirs["bases"]
            / f"{name}.gpkg"
        )
        if gpkg.exists():
            gpkg.unlink()

        frame.to_file(
            gpkg,
            layer=layer,
            driver="GPKG",
            engine="pyogrio",
        )

    return (
        class_flow_geo,
        class_mode_geo,
    )


def _reference_route_segments(
    usage: pd.DataFrame,
    *,
    reference_seed: int,
    geometry: gpd.GeoDataFrame,
    dirs: dict[str, Path],
) -> gpd.GeoDataFrame:
    reference = usage.loc[
        usage["seed"]
        == reference_seed
    ].copy()

    if reference.empty:
        available = sorted(
            usage["seed"]
            .astype(int)
            .unique()
            .tolist()
        )
        reference_seed = available[0]
        reference = usage.loc[
            usage["seed"]
            == reference_seed
        ].copy()

    reference = (
        reference[
            [
                "seed",
                "agent_id",
                "income_group",
                "mode",
                "analysis_segment_id",
                *(
                    ["route_position"]
                    if "route_position"
                    in reference.columns
                    else []
                ),
            ]
        ]
        .drop_duplicates()
    )

    result = gpd.GeoDataFrame(
        reference.merge(
            geometry,
            on="analysis_segment_id",
            how="left",
            validate="many_to_one",
        ),
        geometry="geometry",
        crs=geometry.crs,
    )

    gpkg = (
        dirs["bases"]
        / "base07_segmentos_rotas_seed_referencia.gpkg"
    )
    if gpkg.exists():
        gpkg.unlink()

    result.to_file(
        gpkg,
        layer="segmentos_rotas",
        driver="GPKG",
        engine="pyogrio",
    )

    return result


def _paired_behavior_base(
    *,
    nominal_runs: pd.DataFrame,
    source_dirs: dict[int, Path],
    dirs: dict[str, Path],
) -> pd.DataFrame:
    frames = []

    for _, row in nominal_runs.iterrows():
        seed = int(row["seed"])
        run_dir = source_dirs[
            seed
        ]
        comparison = _read_comparison_geodata(
            run_dir
        )
        length_map = (
            comparison[
                [
                    "analysis_segment_id",
                    "length_m",
                ]
            ]
            .drop_duplicates(
                "analysis_segment_id"
            )
            .assign(
                analysis_segment_id=lambda frame: (
                    frame[
                        "analysis_segment_id"
                    ].astype(str)
                )
            )
            .set_index(
                "analysis_segment_id"
            )[
                "length_m"
            ]
            .astype(float)
            .to_dict()
        )

        paired = _paired_agents(
            run_dir,
            seed=seed,
            run_id=str(row["run_id"]),
            length_map=length_map,
        )
        frames.append(
            paired
        )

    behavior = pd.concat(
        frames,
        ignore_index=True,
    )

    selected = [
        column
        for column in [
            "seed",
            "run_id",
            "agent_id_key",
            "income_group",
            "purpose_baseline",
            "purpose_differentiated",
            "mode_baseline",
            "mode_differentiated",
            "destination_id_baseline",
            "destination_id_differentiated",
            "purpose_changed",
            "destination_changed",
            "mode_changed",
            "route_jaccard_segments",
            "route_jaccard_length",
            "delta_od_distance_m",
            "delta_travel_distance_m",
            "delta_travel_time_s",
            "analysis_included_both",
        ]
        if column in behavior.columns
    ]

    behavior[
        selected
    ].to_csv(
        dirs["bases"]
        / "base06_mudanca_comportamental_agente.csv",
        index=False,
        encoding="utf-8",
    )

    return behavior


def _linewidth(
    values,
    *,
    reference_max: float,
    minimum: float = 0.45,
    maximum: float = 4.5,
):
    values = np.asarray(
        values,
        dtype=float,
    )
    if (
        not np.isfinite(reference_max)
        or reference_max <= 0
    ):
        return np.full(
            len(values),
            minimum,
        )

    scaled = np.sqrt(
        np.clip(
            values,
            0,
            None,
        )
        / reference_max
    )
    return (
        minimum
        + scaled
        * (maximum - minimum)
    )


def _base_map(
    network: gpd.GeoDataFrame,
    *,
    figsize=(10, 10),
):
    figure, axis = plt.subplots(
        figsize=figsize
    )
    network.plot(
        ax=axis,
        color="#d9d9d9",
        linewidth=0.22,
        alpha=0.45,
    )
    axis.set_axis_off()
    return figure, axis


def _subtitle_daily_proxy(
    figure,
) -> None:
    figure.text(
        0.5,
        0.015,
        (
            "Proxy diária agregada: conjunto completo das viagens simuladas; "
            "o piloto atual gera uma viagem por agente por realização."
        ),
        ha="center",
        va="bottom",
        fontsize=8,
    )


def _save(
    figure,
    path: Path,
    *,
    dpi: int,
) -> None:
    figure.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(
        figure
    )


def _plot_reference_routes_by_class(
    *,
    routes: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> list[dict]:
    manifest = []

    reference_seed = int(
        routes["seed"].iloc[0]
    )

    for income in INCOME_GROUPS:
        subset = routes.loc[
            routes["income_group"]
            == income
        ].copy()

        figure, axis = _base_map(
            network
        )

        if not subset.empty:
            subset.plot(
                ax=axis,
                color=INCOME_COLORS[
                    income
                ],
                linewidth=0.9,
                alpha=0.12,
            )

        n_agents = int(
            subset["agent_id"]
            .nunique()
        )

        axis.set_title(
            (
                f"Trajetórias individuais — "
                f"{INCOME_LABELS[income]}\n"
                f"seed {reference_seed} | "
                f"{n_agents} agentes"
            )
        )
        _subtitle_daily_proxy(
            figure
        )

        filename = (
            f"v02_rotas_{income}_"
            "proxy_diaria.png"
        )
        _save(
            figure,
            dirs["routes"]
            / filename,
            dpi=dpi,
        )
        manifest.append(
            {
                "figure": filename,
                "group": "rotas_por_classe",
                "income_group": income,
                "mode": "all",
                "seed": reference_seed,
            }
        )

    return manifest


def _plot_all_classes_reference_routes(
    *,
    routes: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> dict:
    figure, axis = _base_map(
        network
    )

    for income in INCOME_GROUPS:
        subset = routes.loc[
            routes["income_group"]
            == income
        ]
        if subset.empty:
            continue

        subset.plot(
            ax=axis,
            color=INCOME_COLORS[
                income
            ],
            linewidth=0.9,
            alpha=0.14,
            label=INCOME_LABELS[
                income
            ],
        )

    axis.set_title(
        "Todas as trajetórias por classe social"
    )

    handles = [
        plt.Line2D(
            [0],
            [0],
            color=INCOME_COLORS[
                income
            ],
            linewidth=3,
            label=INCOME_LABELS[
                income
            ],
        )
        for income in INCOME_GROUPS
    ]
    axis.legend(
        handles=handles,
        loc="lower right",
        frameon=True,
    )
    _subtitle_daily_proxy(
        figure
    )

    filename = (
        "v02_rotas_todas_classes_"
        "proxy_diaria.png"
    )
    _save(
        figure,
        dirs["figures"]
        / filename,
        dpi=dpi,
    )

    return {
        "figure": filename,
        "group": "rotas_todas_classes",
        "income_group": "all",
        "mode": "all",
        "seed": int(
            routes["seed"].iloc[0]
        ),
    }


def _plot_class_flow_maps(
    *,
    class_flow: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> list[dict]:
    manifest = []

    global_max = float(
        pd.to_numeric(
            class_flow[
                "mean_agents_per_seed"
            ],
            errors="coerce",
        ).max()
    )

    for income in INCOME_GROUPS:
        subset = class_flow.loc[
            class_flow[
                "income_group"
            ]
            == income
        ].copy()

        figure, axis = _base_map(
            network
        )

        if not subset.empty:
            subset.plot(
                ax=axis,
                color=INCOME_COLORS[
                    income
                ],
                linewidth=_linewidth(
                    subset[
                        "mean_agents_per_seed"
                    ],
                    reference_max=global_max,
                ),
                alpha=0.82,
            )

        axis.set_title(
            (
                "Fluxo espacial agregado — "
                f"{INCOME_LABELS[income]}"
            )
        )
        _subtitle_daily_proxy(
            figure
        )

        filename = (
            f"v02_fluxo_{income}_"
            "proxy_diaria.png"
        )
        _save(
            figure,
            dirs["figures"]
            / filename,
            dpi=dpi,
        )

        manifest.append(
            {
                "figure": filename,
                "group": "fluxo_por_classe",
                "income_group": income,
                "mode": "all",
                "seed": "multi-seed",
            }
        )

    return manifest


def _plot_class_dominance(
    *,
    class_flow: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> dict:
    pivot = (
        class_flow.pivot_table(
            index="analysis_segment_id",
            columns="income_group",
            values="mean_agents_per_seed",
            aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(
            columns=list(
                INCOME_GROUPS
            ),
            fill_value=0.0,
        )
    )

    total = pivot.sum(
        axis=1
    )
    dominant = pivot.idxmax(
        axis=1
    )
    dominant_share = (
        pivot.max(axis=1)
        / total.replace(
            0,
            np.nan,
        )
    )

    summary = pd.DataFrame(
        {
            "analysis_segment_id": pivot.index.astype(str),
            "dominant_income_group": dominant.to_numpy(),
            "dominant_share": dominant_share.to_numpy(),
            "mean_agents_all_classes": total.to_numpy(),
        }
    )

    geometry = (
        class_flow[
            [
                "analysis_segment_id",
                "geometry",
            ]
        ]
        .drop_duplicates(
            "analysis_segment_id"
        )
    )

    result = gpd.GeoDataFrame(
        summary.merge(
            geometry,
            on="analysis_segment_id",
            how="left",
            validate="one_to_one",
        ),
        geometry="geometry",
        crs=class_flow.crs,
    )

    gpkg = (
        dirs["maps"]
        / "v02_dominancia_classe.gpkg"
    )
    if gpkg.exists():
        gpkg.unlink()
    result.to_file(
        gpkg,
        layer="dominancia_classe",
        driver="GPKG",
        engine="pyogrio",
    )

    figure, axis = _base_map(
        network
    )

    max_flow = float(
        result[
            "mean_agents_all_classes"
        ].max()
    )

    for income in INCOME_GROUPS:
        subset = result.loc[
            result[
                "dominant_income_group"
            ]
            == income
        ]
        if subset.empty:
            continue

        subset.plot(
            ax=axis,
            color=INCOME_COLORS[
                income
            ],
            linewidth=_linewidth(
                subset[
                    "mean_agents_all_classes"
                ],
                reference_max=max_flow,
            ),
            alpha=np.clip(
                0.30
                + 0.70
                * subset[
                    "dominant_share"
                ].to_numpy(),
                0.30,
                1.0,
            ),
        )

    handles = [
        plt.Line2D(
            [0],
            [0],
            color=INCOME_COLORS[
                income
            ],
            linewidth=3,
            label=INCOME_LABELS[
                income
            ],
        )
        for income in INCOME_GROUPS
    ]
    axis.legend(
        handles=handles,
        loc="lower right",
        title="Classe dominante",
    )
    axis.set_title(
        "Classe social dominante no fluxo de cada segmento"
    )
    _subtitle_daily_proxy(
        figure
    )

    filename = (
        "v02_mapa_dominancia_classe.png"
    )
    _save(
        figure,
        dirs["figures"]
        / filename,
        dpi=dpi,
    )

    return {
        "figure": filename,
        "group": "dominancia_classe",
        "income_group": "all",
        "mode": "all",
        "seed": "multi-seed",
    }


def _plot_mode_class_atlas(
    *,
    class_mode: gpd.GeoDataFrame,
    network: gpd.GeoDataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> list[dict]:
    manifest = []

    global_max = float(
        pd.to_numeric(
            class_mode[
                "mean_agents_per_seed"
            ],
            errors="coerce",
        ).max()
    )

    for income in INCOME_GROUPS:
        for mode in MODES:
            subset = class_mode.loc[
                (
                    class_mode[
                        "income_group"
                    ]
                    == income
                )
                & (
                    class_mode[
                        "mode"
                    ]
                    == mode
                )
            ].copy()

            figure, axis = _base_map(
                network
            )

            if not subset.empty:
                subset.plot(
                    ax=axis,
                    color=MODE_COLORS[
                        mode
                    ],
                    linewidth=_linewidth(
                        subset[
                            "mean_agents_per_seed"
                        ],
                        reference_max=global_max,
                    ),
                    alpha=0.86,
                )

            axis.set_title(
                (
                    f"{INCOME_LABELS[income]} — "
                    f"{MODE_LABELS[mode]}"
                )
            )
            _subtitle_daily_proxy(
                figure
            )

            filename = (
                f"v02_{income}_{mode}.png"
            )
            _save(
                figure,
                dirs["mode_class"]
                / filename,
                dpi=dpi,
            )

            manifest.append(
                {
                    "figure": filename,
                    "group": "modo_x_classe_individual",
                    "income_group": income,
                    "mode": mode,
                    "seed": "multi-seed",
                }
            )

    figure, axes = plt.subplots(
        len(INCOME_GROUPS),
        len(MODES),
        figsize=(18, 13),
        sharex=True,
        sharey=True,
    )

    for row_index, income in enumerate(
        INCOME_GROUPS
    ):
        for column_index, mode in enumerate(
            MODES
        ):
            axis = axes[
                row_index,
                column_index,
            ]
            network.plot(
                ax=axis,
                color="#dddddd",
                linewidth=0.18,
                alpha=0.42,
            )

            subset = class_mode.loc[
                (
                    class_mode[
                        "income_group"
                    ]
                    == income
                )
                & (
                    class_mode[
                        "mode"
                    ]
                    == mode
                )
            ]

            if not subset.empty:
                subset.plot(
                    ax=axis,
                    color=MODE_COLORS[
                        mode
                    ],
                    linewidth=_linewidth(
                        subset[
                            "mean_agents_per_seed"
                        ],
                        reference_max=global_max,
                        minimum=0.35,
                        maximum=3.2,
                    ),
                    alpha=0.84,
                )

            axis.set_axis_off()

            if row_index == 0:
                axis.set_title(
                    MODE_LABELS[
                        mode
                    ]
                )
            if column_index == 0:
                axis.text(
                    -0.04,
                    0.5,
                    INCOME_LABELS[
                        income
                    ],
                    transform=axis.transAxes,
                    rotation=90,
                    va="center",
                    ha="right",
                    fontsize=11,
                    fontweight="bold",
                )

    figure.suptitle(
        (
            "Trajetos por modo e classe social "
            "— fluxo médio entre realizações"
        ),
        fontsize=16,
    )
    _subtitle_daily_proxy(
        figure
    )

    filename = (
        "v02_painel_modo_x_classe.png"
    )
    _save(
        figure,
        dirs["figures"]
        / filename,
        dpi=dpi,
    )

    manifest.append(
        {
            "figure": filename,
            "group": "modo_x_classe_painel",
            "income_group": "all",
            "mode": "all",
            "seed": "multi-seed",
        }
    )

    return manifest


def _observed_modal_shares(
    behavior: pd.DataFrame,
) -> pd.DataFrame:
    included = behavior.loc[
        _safe_bool(
            behavior[
                "analysis_included_both"
            ]
        )
    ].copy()

    frames = []
    for scenario in (
        "baseline",
        "differentiated",
    ):
        column = (
            f"mode_{scenario}"
        )
        grouped = (
            included.groupby(
                [
                    "seed",
                    "income_group",
                    column,
                ],
                dropna=False,
            )
            .size()
            .rename("n")
            .reset_index()
            .rename(
                columns={
                    column: "mode",
                }
            )
        )

        totals = (
            grouped.groupby(
                [
                    "seed",
                    "income_group",
                ]
            )[
                "n"
            ]
            .sum()
            .rename(
                "n_total"
            )
            .reset_index()
        )

        grouped = grouped.merge(
            totals,
            on=[
                "seed",
                "income_group",
            ],
            how="left",
        )
        grouped["share"] = (
            grouped["n"]
            / grouped["n_total"]
        )
        grouped["scenario"] = (
            scenario
        )
        frames.append(
            grouped
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def _plot_modal_behavior_change(
    *,
    behavior: pd.DataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> tuple[dict, pd.DataFrame]:
    shares = _observed_modal_shares(
        behavior
    )

    summary = (
        shares.groupby(
            [
                "scenario",
                "income_group",
                "mode",
            ],
            as_index=False,
        )[
            "share"
        ]
        .median()
    )

    summary.to_csv(
        dirs["stats"]
        / "participacao_modal_observada_por_classe.csv",
        index=False,
        encoding="utf-8",
    )

    figure, axes = plt.subplots(
        1,
        len(INCOME_GROUPS),
        figsize=(15, 5),
        sharey=True,
    )

    x = np.arange(
        len(MODES)
    )
    width = 0.36

    for index, income in enumerate(
        INCOME_GROUPS
    ):
        axis = axes[
            index
        ]

        baseline = (
            summary.loc[
                (
                    summary[
                        "scenario"
                    ]
                    == "baseline"
                )
                & (
                    summary[
                        "income_group"
                    ]
                    == income
                )
            ]
            .set_index("mode")[
                "share"
            ]
            .reindex(MODES)
            .fillna(0.0)
        )

        differentiated = (
            summary.loc[
                (
                    summary[
                        "scenario"
                    ]
                    == "differentiated"
                )
                & (
                    summary[
                        "income_group"
                    ]
                    == income
                )
            ]
            .set_index("mode")[
                "share"
            ]
            .reindex(MODES)
            .fillna(0.0)
        )

        axis.bar(
            x - width / 2,
            baseline.to_numpy()
            * 100,
            width=width,
            label="Baseline",
            alpha=0.78,
        )
        axis.bar(
            x + width / 2,
            differentiated.to_numpy()
            * 100,
            width=width,
            label="Com classe social",
            alpha=0.78,
        )

        axis.set_xticks(
            x,
            [
                MODE_LABELS[
                    mode
                ]
                for mode in MODES
            ],
            rotation=35,
            ha="right",
        )
        axis.set_title(
            INCOME_LABELS[
                income
            ]
        )
        axis.grid(
            axis="y",
            alpha=0.18,
        )

        if index == 0:
            axis.set_ylabel(
                "Participação modal observada (%)"
            )

    handles, labels = axes[
        0
    ].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="upper center",
        ncol=2,
        bbox_to_anchor=(
            0.5,
            1.03,
        ),
    )
    figure.suptitle(
        (
            "A introdução de comportamento diferenciado por classe "
            "altera a composição modal"
        ),
        y=1.08,
        fontsize=15,
    )

    filename = (
        "v02_comportamento_modal_"
        "baseline_vs_classe.png"
    )
    _save(
        figure,
        dirs["figures"]
        / filename,
        dpi=dpi,
    )

    return (
        {
            "figure": filename,
            "group": "mudanca_comportamental",
            "income_group": "all",
            "mode": "all",
            "seed": "multi-seed",
        },
        summary,
    )


def _plot_behavior_change_rates(
    *,
    behavior: pd.DataFrame,
    dirs: dict[str, Path],
    dpi: int,
) -> tuple[dict, dict, pd.DataFrame]:
    included = behavior.loc[
        _safe_bool(
            behavior[
                "analysis_included_both"
            ]
        )
    ].copy()

    by_seed = (
        included.groupby(
            [
                "seed",
                "income_group",
            ]
        )
        .agg(
            purpose_changed=(
                "purpose_changed",
                "mean",
            ),
            destination_changed=(
                "destination_changed",
                "mean",
            ),
            mode_changed=(
                "mode_changed",
                "mean",
            ),
            route_jaccard_length=(
                "route_jaccard_length",
                "median",
            ),
        )
        .reset_index()
    )

    by_seed.to_csv(
        dirs["stats"]
        / "mudancas_comportamentais_por_seed_classe.csv",
        index=False,
        encoding="utf-8",
    )

    summary = (
        by_seed.groupby(
            "income_group"
        )[
            [
                "purpose_changed",
                "destination_changed",
                "mode_changed",
                "route_jaccard_length",
            ]
        ]
        .median()
        .reindex(
            list(
                INCOME_GROUPS
            )
        )
    )

    figure, axis = plt.subplots(
        figsize=(9, 5.5)
    )

    x = np.arange(
        len(INCOME_GROUPS)
    )
    width = 0.24

    metrics = [
        (
            "purpose_changed",
            "Propósito",
        ),
        (
            "destination_changed",
            "Destino",
        ),
        (
            "mode_changed",
            "Modo",
        ),
    ]

    for metric_index, (
        column,
        label,
    ) in enumerate(metrics):
        axis.bar(
            x
            + (
                metric_index - 1
            )
            * width,
            summary[
                column
            ].to_numpy()
            * 100,
            width=width,
            label=label,
        )

    axis.set_xticks(
        x,
        [
            INCOME_LABELS[
                income
            ]
            for income in INCOME_GROUPS
        ],
    )
    axis.set_ylabel(
        "Agentes que mudaram (%)"
    )
    axis.set_title(
        (
            "Mudança comportamental após introduzir "
            "regras diferenciadas por classe"
        )
    )
    axis.grid(
        axis="y",
        alpha=0.18,
    )
    axis.legend()

    filename_change = (
        "v02_taxa_mudanca_comportamental_"
        "por_classe.png"
    )
    _save(
        figure,
        dirs["figures"]
        / filename_change,
        dpi=dpi,
    )

    figure, axis = plt.subplots(
        figsize=(7.5, 5)
    )
    route_overlap = (
        summary[
            "route_jaccard_length"
        ]
        .to_numpy()
    )
    axis.bar(
        [
            INCOME_LABELS[
                income
            ]
            for income in INCOME_GROUPS
        ],
        route_overlap
        * 100,
        color=[
            INCOME_COLORS[
                income
            ]
            for income in INCOME_GROUPS
        ],
    )
    axis.set_ylim(
        0,
        100,
    )
    axis.set_ylabel(
        "Sobreposição da rota (%)"
    )
    axis.set_title(
        (
            "Quanto das rotas permanece igual entre "
            "baseline e differentiated"
        )
    )
    axis.grid(
        axis="y",
        alpha=0.18,
    )

    filename_overlap = (
        "v02_sobreposicao_rotas_"
        "por_classe.png"
    )
    _save(
        figure,
        dirs["figures"]
        / filename_overlap,
        dpi=dpi,
    )

    return (
        {
            "figure": filename_change,
            "group": "mudanca_comportamental",
            "income_group": "all",
            "mode": "all",
            "seed": "multi-seed",
        },
        {
            "figure": filename_overlap,
            "group": "sobreposicao_rotas",
            "income_group": "all",
            "mode": "all",
            "seed": "multi-seed",
        },
        by_seed,
    )


def _write_report(
    *,
    dirs: dict[str, Path],
    n_seeds: int,
    reference_seed: int,
    modal_summary: pd.DataFrame,
    behavior_by_seed: pd.DataFrame,
) -> None:
    modal_lines = []

    for income in INCOME_GROUPS:
        subset = modal_summary.loc[
            (
                modal_summary[
                    "scenario"
                ]
                == "differentiated"
            )
            & (
                modal_summary[
                    "income_group"
                ]
                == income
            )
        ]

        if subset.empty:
            continue

        top = subset.sort_values(
            "share",
            ascending=False,
        ).iloc[0]

        modal_lines.append(
            (
                f"- {INCOME_LABELS[income]}: modo mais frequente = "
                f"{MODE_LABELS.get(str(top['mode']), str(top['mode']))} "
                f"({100 * float(top['share']):.1f}%)."
            )
        )

    overlap = (
        behavior_by_seed.groupby(
            "income_group"
        )[
            "route_jaccard_length"
        ]
        .median()
        .reindex(
            list(
                INCOME_GROUPS
            )
        )
    )

    overlap_lines = [
        (
            f"- {INCOME_LABELS[income]}: "
            f"{100 * float(overlap.loc[income]):.1f}%."
        )
        for income in INCOME_GROUPS
        if income in overlap.index
        and pd.notna(
            overlap.loc[
                income
            ]
        )
    ]

    lines = [
        "# Article v02 — leitura visual da mobilidade",
        "",
        "## Escopo",
        "",
        (
            f"As figuras agregam {n_seeds} realização(ões) nominal(is). "
            f"Os mapas de trajetórias individuais usam a seed {reference_seed} "
            "quando disponível."
        ),
        "",
        "## Limitação temporal importante",
        "",
        (
            "O piloto atual não simula uma agenda intradiária completa. "
            "Cada agente realiza uma viagem por realização e o transporte "
            "coletivo usa o horário de partida configurado no piloto. "
            "Assim, os mapas identificados como proxy diária agregam todas "
            "as viagens simuladas e NÃO devem ser descritos como observação "
            "horária de um dia inteiro."
        ),
        "",
        "## Participação modal no cenário diferenciado",
        "",
        *modal_lines,
        "",
        "## Sobreposição mediana das rotas",
        "",
        *overlap_lines,
        "",
        "## Figuras prioritárias",
        "",
        "- trajetórias individuais por classe social;",
        "- todas as classes no mesmo mapa;",
        "- fluxo agregado por classe;",
        "- dominância de classe por segmento;",
        "- comportamento modal baseline × differentiated;",
        "- taxas de mudança de propósito, destino e modo;",
        "- sobreposição das rotas;",
        "- painel 3 × 4 de classe social × modo.",
        "",
    ]

    (
        dirs["report"]
        / "leitura_visual_v02.md"
    ).write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )


def _write_manifest(
    *,
    dirs: dict[str, Path],
    nominal_runs: pd.DataFrame,
    reference_seed: int,
    figure_manifest: pd.DataFrame,
) -> None:
    manifest = {
        "version": "article_v02",
        "preserves": [
            "src/analysis/article_v01.py",
            "outputs/v01 artigo",
        ],
        "nominal_seeds_used": (
            nominal_runs[
                "seed"
            ]
            .astype(int)
            .tolist()
        ),
        "reference_seed_requested": int(
            reference_seed
        ),
        "temporal_scope": (
            "daily_aggregate_proxy_one_trip_per_agent"
        ),
        "temporal_warning": (
            "The current pilot is not a 24-hour activity schedule. "
            "Maps aggregate the complete simulated trip set."
        ),
        "figures_generated": int(
            len(
                figure_manifest
            )
        ),
    }

    with (
        dirs["root"]
        / "00_manifesto_v02.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            manifest,
            file,
            ensure_ascii=False,
            indent=2,
        )


def main() -> None:
    args = _parse_args()
    config = _load_config()
    article = _article_config(
        config
    )

    output_root = _resolve_project_path(
        args.output_dir
    )
    sensitivity_root = (
        _resolve_project_path(
            args.sensitivity_root
        )
    )
    dirs = _ensure_dirs(
        output_root
    )

    nominal_runs = _ensure_nominal_runs(
        sensitivity_root=sensitivity_root,
        minimum=args.min_nominal_seeds,
        workers=args.workers,
        run_if_missing=args.run_core_if_missing,
    )

    print(
        "1/7 - Carregando trajetórias diferenciadas..."
    )
    usage, source_dirs = (
        _load_differentiated_usage(
            nominal_runs=nominal_runs,
            sensitivity_root=sensitivity_root,
        )
    )

    available_seeds = sorted(
        source_dirs
    )
    reference_seed = (
        args.reference_seed
        if args.reference_seed
        in source_dirs
        else available_seeds[
            0
        ]
    )

    geometry = _geometry_lookup(
        source_dirs[
            reference_seed
        ]
    )
    network = _network_extent(
        source_dirs[
            reference_seed
        ]
    )

    print(
        "2/7 - Construindo bases espaciais v02..."
    )
    class_flow, class_mode = (
        _build_flow_bases(
            usage,
            geometry=geometry,
            n_seeds=len(
                nominal_runs
            ),
            dirs=dirs,
        )
    )
    reference_routes = (
        _reference_route_segments(
            usage,
            reference_seed=reference_seed,
            geometry=geometry,
            dirs=dirs,
        )
    )

    print(
        "3/7 - Construindo base comportamental..."
    )
    behavior = _paired_behavior_base(
        nominal_runs=nominal_runs,
        source_dirs=source_dirs,
        dirs=dirs,
    )

    print(
        "4/7 - Gerando mapas de trajetórias por classe..."
    )
    figure_rows = []

    figure_rows.extend(
        _plot_reference_routes_by_class(
            routes=reference_routes,
            network=network,
            dirs=dirs,
            dpi=int(
                article.get(
                    "figure_dpi",
                    300,
                )
            ),
        )
    )

    figure_rows.append(
        _plot_all_classes_reference_routes(
            routes=reference_routes,
            network=network,
            dirs=dirs,
            dpi=int(
                article.get(
                    "figure_dpi",
                    300,
                )
            ),
        )
    )

    figure_rows.extend(
        _plot_class_flow_maps(
            class_flow=class_flow,
            network=network,
            dirs=dirs,
            dpi=int(
                article.get(
                    "figure_dpi",
                    300,
                )
            ),
        )
    )

    figure_rows.append(
        _plot_class_dominance(
            class_flow=class_flow,
            network=network,
            dirs=dirs,
            dpi=int(
                article.get(
                    "figure_dpi",
                    300,
                )
            ),
        )
    )

    print(
        "5/7 - Gerando atlas modo x classe..."
    )
    figure_rows.extend(
        _plot_mode_class_atlas(
            class_mode=class_mode,
            network=network,
            dirs=dirs,
            dpi=int(
                article.get(
                    "figure_dpi",
                    300,
                )
            ),
        )
    )

    print(
        "6/7 - Gerando gráficos de mudança comportamental..."
    )
    modal_figure, modal_summary = (
        _plot_modal_behavior_change(
            behavior=behavior,
            dirs=dirs,
            dpi=int(
                article.get(
                    "figure_dpi",
                    300,
                )
            ),
        )
    )
    figure_rows.append(
        modal_figure
    )

    (
        change_figure,
        overlap_figure,
        behavior_by_seed,
    ) = _plot_behavior_change_rates(
        behavior=behavior,
        dirs=dirs,
        dpi=int(
            article.get(
                "figure_dpi",
                300,
            )
        ),
    )
    figure_rows.extend(
        [
            change_figure,
            overlap_figure,
        ]
    )

    print(
        "7/7 - Gravando manifesto e relatório..."
    )
    figure_manifest = pd.DataFrame(
        figure_rows
    )
    figure_manifest.to_csv(
        dirs["figures"]
        / "manifesto_figuras_v02.csv",
        index=False,
        encoding="utf-8",
    )

    _write_report(
        dirs=dirs,
        n_seeds=len(
            nominal_runs
        ),
        reference_seed=reference_seed,
        modal_summary=modal_summary,
        behavior_by_seed=behavior_by_seed,
    )
    _write_manifest(
        dirs=dirs,
        nominal_runs=nominal_runs,
        reference_seed=reference_seed,
        figure_manifest=figure_manifest,
    )

    print("")
    print(
        "Article v02 concluído em:"
    )
    print(
        output_root.resolve()
    )


if __name__ == "__main__":
    main()
