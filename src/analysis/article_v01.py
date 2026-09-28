"""Gera o pacote analítico e gráfico final da versão v01 do artigo.

Este é o ponto único de entrada para reproduzir a análise do artigo.

Fluxo
-----
1. executa/reutiliza a bateria final de sensibilidade com N=100;
2. constrói três bases analíticas finais:
   - agentes pareados;
   - segmentos pareados com geometria;
   - realizações/seeds;
3. calcula o resultado principal sem tratar segmentos como observações
   independentes, usando bootstrap hierárquico de seeds e agentes;
4. extrai a dimensão espacial e uma camada de consenso entre seeds;
5. quantifica mecanismos comportamentais e contribuições exatas para delta_H_soc;
6. gera tabelas automáticas;
7. gera figuras e mapas finais;
8. grava manifesto e relatório em outputs/v01 artigo.

Uso recomendado
---------------
python -m src.analysis.article_v01

Para apenas reconstruir o pacote a partir das simulações existentes:
python -m src.analysis.article_v01 --skip-simulations
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import geopandas as gpd
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm
import numpy as np
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
INCOME_GROUPS = ("low", "middle", "high")
SCENARIOS = ("baseline", "differentiated")


def _load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def _article_config(config: dict) -> dict:
    return config.get("analysis", {}).get("article_v01", {})


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def _parse_args():
    config = _load_config()
    article = _article_config(config)

    parser = argparse.ArgumentParser(
        description="Gera integralmente o pacote analítico v01 do artigo."
    )
    parser.add_argument(
        "--output-dir",
        default=article.get("output_dir", "outputs/v01 artigo"),
    )
    parser.add_argument(
        "--sensitivity-root",
        default=article.get(
            "sensitivity_root",
            "outputs/pilot/final_sensitivity",
        ),
    )
    parser.add_argument(
        "--bootstrap-reps",
        type=int,
        default=int(article.get("bootstrap_reps", 1000)),
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=int(article.get("bootstrap_seed", 20260928)),
    )
    parser.add_argument(
        "--skip-simulations",
        action="store_true",
        help="Não executa a bateria final; usa apenas resultados existentes.",
    )
    parser.add_argument(
        "--force-simulations",
        action="store_true",
        help="Executa a bateria sem --resume.",
    )
    return parser.parse_args()


def _safe_bool(values: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(values):
        return values.fillna(False)
    return (
        values.astype("string")
        .str.strip()
        .str.lower()
        .isin(["true", "1", "yes", "sim"])
    )


def _weighted_mean(values, weights) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not np.any(valid):
        return float("nan")
    return float(
        np.average(
            values[valid],
            weights=weights[valid],
        )
    )


def _entropy_term(probability):
    values = np.asarray(probability, dtype=float)
    out = np.zeros_like(values, dtype=float)
    valid = np.isfinite(values) & (values > 0)
    out[valid] = (
        -values[valid]
        * np.log(values[valid])
        / np.log(len(INCOME_GROUPS))
    )
    out[~np.isfinite(values)] = np.nan
    return out


def _ensure_dirs(root: Path) -> dict[str, Path]:
    dirs = {
        "root": root,
        "bases": root / "01_bases",
        "stats": root / "02_estatisticas",
        "tables": root / "03_tabelas",
        "figures": root / "04_figuras",
        "maps": root / "05_mapas",
        "report": root / "06_relatorio",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def _run_final_sensitivity(
    *,
    force: bool,
) -> None:
    command = [
        sys.executable,
        "-m",
        "src.analysis.final_pilot_sensitivity",
    ]
    if not force:
        command.append("--resume")

    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=True,
    )


def _resolve_source_dir(
    row: pd.Series,
    *,
    sensitivity_root: Path,
) -> Path:
    raw = row.get("source_dir")
    if pd.notna(raw):
        path = Path(str(raw))
        if path.exists():
            return path

    run_id = str(row["run_id"])
    candidate = sensitivity_root / "runs" / run_id
    if candidate.exists():
        return candidate

    if (
        str(row.get("experiment")) == "nominal_seed"
        and int(row.get("seed")) == 42
    ):
        legacy = (
            PROJECT_ROOT
            / "outputs"
            / "pilot"
            / "population_sensitivity"
            / "n_0100_seed_42"
        )
        if legacy.exists():
            return legacy

    raise FileNotFoundError(
        f"Não foi possível localizar a execução '{run_id}'. "
        "Execute a bateria final de sensibilidade antes da análise do artigo."
    )


def _read_comparison_geodata(run_dir: Path) -> gpd.GeoDataFrame:
    path = run_dir / "segment_scenario_comparison.gpkg"
    if not path.exists():
        raise FileNotFoundError(path)

    frame = gpd.read_file(
        path,
        layer="scenario_comparison",
        engine="pyogrio",
    )

    if "length_m" not in frame.columns:
        frame["length_m"] = frame.geometry.length.astype(float)

    return frame


def _add_entropy_contributions(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()

    for group in INCOME_GROUPS:
        baseline = pd.to_numeric(
            result[f"p_{group}_baseline"],
            errors="coerce",
        )
        differentiated = pd.to_numeric(
            result[f"p_{group}_differentiated"],
            errors="coerce",
        )

        result[f"entropy_term_{group}_baseline"] = _entropy_term(
            baseline
        )
        result[f"entropy_term_{group}_differentiated"] = _entropy_term(
            differentiated
        )
        result[f"contrib_delta_H_{group}"] = (
            result[f"entropy_term_{group}_differentiated"]
            - result[f"entropy_term_{group}_baseline"]
        )

    result["delta_H_soc_reconstructed"] = result[
        [f"contrib_delta_H_{group}" for group in INCOME_GROUPS]
    ].sum(axis=1, min_count=len(INCOME_GROUPS))

    result["delta_H_soc_reconstruction_error"] = (
        pd.to_numeric(result["delta_H_soc"], errors="coerce")
        - result["delta_H_soc_reconstructed"]
    )

    return result


def _segment_length_map(
    comparison: gpd.GeoDataFrame,
) -> dict[str, float]:
    return (
        comparison[
            ["analysis_segment_id", "length_m"]
        ]
        .drop_duplicates("analysis_segment_id")
        .assign(
            analysis_segment_id=lambda x: x[
                "analysis_segment_id"
            ].astype(str)
        )
        .set_index("analysis_segment_id")["length_m"]
        .astype(float)
        .to_dict()
    )


def _route_overlap(
    run_dir: Path,
    *,
    length_map: dict[str, float],
) -> pd.DataFrame:
    by_scenario: dict[str, dict[str, set[str]]] = {}

    for scenario in SCENARIOS:
        path = run_dir / f"edge_usage_analysis_{scenario}.csv"
        usage = pd.read_csv(path)
        usage = usage[
            ["agent_id", "analysis_segment_id"]
        ].drop_duplicates()
        usage["agent_id"] = usage["agent_id"].astype(str)
        usage["analysis_segment_id"] = (
            usage["analysis_segment_id"].astype(str)
        )

        by_scenario[scenario] = (
            usage.groupby("agent_id")["analysis_segment_id"]
            .apply(set)
            .to_dict()
        )

    agent_ids = sorted(
        set(by_scenario["baseline"])
        | set(by_scenario["differentiated"])
    )

    rows = []
    for agent_id in agent_ids:
        baseline = by_scenario["baseline"].get(agent_id, set())
        differentiated = by_scenario["differentiated"].get(
            agent_id,
            set(),
        )
        shared = baseline & differentiated
        union = baseline | differentiated

        baseline_length = sum(
            length_map.get(segment_id, 0.0)
            for segment_id in baseline
        )
        differentiated_length = sum(
            length_map.get(segment_id, 0.0)
            for segment_id in differentiated
        )
        shared_length = sum(
            length_map.get(segment_id, 0.0)
            for segment_id in shared
        )
        union_length = sum(
            length_map.get(segment_id, 0.0)
            for segment_id in union
        )

        rows.append(
            {
                "agent_id_key": agent_id,
                "route_segments_baseline": len(baseline),
                "route_segments_differentiated": len(differentiated),
                "route_segments_shared": len(shared),
                "route_segments_union": len(union),
                "route_jaccard_segments": (
                    len(shared) / len(union)
                    if union
                    else np.nan
                ),
                "route_length_baseline_m": baseline_length,
                "route_length_differentiated_m": differentiated_length,
                "route_length_shared_m": shared_length,
                "route_length_union_m": union_length,
                "route_jaccard_length": (
                    shared_length / union_length
                    if union_length > 0
                    else np.nan
                ),
            }
        )

    return pd.DataFrame(rows)


def _paired_agents(
    run_dir: Path,
    *,
    seed: int,
    run_id: str,
    length_map: dict[str, float],
) -> pd.DataFrame:
    baseline = pd.read_csv(run_dir / "agents_baseline.csv")
    differentiated = pd.read_csv(
        run_dir / "agents_differentiated.csv"
    )

    baseline["agent_id_key"] = baseline["agent_id"].astype(str)
    differentiated["agent_id_key"] = (
        differentiated["agent_id"].astype(str)
    )

    fixed_columns = [
        "agent_id_key",
        "agent_id",
        "income_group",
        "origin_id",
    ]

    keep_baseline = fixed_columns + [
        column
        for column in baseline.columns
        if column not in fixed_columns
    ]
    keep_differentiated = fixed_columns + [
        column
        for column in differentiated.columns
        if column not in fixed_columns
    ]

    paired = baseline[keep_baseline].merge(
        differentiated[keep_differentiated],
        on="agent_id_key",
        how="inner",
        suffixes=("_baseline", "_differentiated"),
        validate="one_to_one",
    )

    for fixed in ("income_group", "origin_id"):
        left = f"{fixed}_baseline"
        right = f"{fixed}_differentiated"
        if left in paired.columns and right in paired.columns:
            if not (
                paired[left].astype(str)
                == paired[right].astype(str)
            ).all():
                raise RuntimeError(
                    f"{fixed} mudou entre cenários na seed {seed}."
                )
            paired[fixed] = paired[left]

    def changed(column: str) -> pd.Series:
        left = f"{column}_baseline"
        right = f"{column}_differentiated"
        if left not in paired.columns or right not in paired.columns:
            return pd.Series(False, index=paired.index)
        return (
            paired[left].astype("string")
            != paired[right].astype("string")
        )

    paired["purpose_changed"] = changed("purpose")
    paired["destination_changed"] = changed("destination_id")
    paired["mode_changed"] = changed("mode")

    if {
        "mode_baseline",
        "mode_differentiated",
    }.issubset(paired.columns):
        paired["mode_transition"] = (
            paired["mode_baseline"].astype("string")
            + " → "
            + paired["mode_differentiated"].astype("string")
        )

    if {
        "purpose_baseline",
        "purpose_differentiated",
    }.issubset(paired.columns):
        paired["purpose_transition"] = (
            paired["purpose_baseline"].astype("string")
            + " → "
            + paired["purpose_differentiated"].astype("string")
        )

    numeric_pairs = {
        "od_distance_m": "delta_od_distance_m",
        "travel_distance_m": "delta_travel_distance_m",
        "travel_time_s": "delta_travel_time_s",
    }
    for source, target in numeric_pairs.items():
        left = f"{source}_baseline"
        right = f"{source}_differentiated"
        if left in paired.columns and right in paired.columns:
            paired[target] = (
                pd.to_numeric(paired[right], errors="coerce")
                - pd.to_numeric(paired[left], errors="coerce")
            )

    if {
        "analysis_included_baseline",
        "analysis_included_differentiated",
    }.issubset(paired.columns):
        paired["analysis_included_both"] = (
            _safe_bool(paired["analysis_included_baseline"])
            & _safe_bool(paired["analysis_included_differentiated"])
        )
    else:
        paired["analysis_included_both"] = True

    overlap = _route_overlap(
        run_dir,
        length_map=length_map,
    )
    paired = paired.merge(
        overlap,
        on="agent_id_key",
        how="left",
        validate="one_to_one",
    )

    paired.insert(0, "run_id", run_id)
    paired.insert(0, "seed", int(seed))

    return paired


def _run_spatial_metrics(
    comparison: gpd.GeoDataFrame,
    *,
    threshold: int,
    practical_delta: float,
) -> dict:
    base_n = pd.to_numeric(
        comparison["n_agents_baseline"],
        errors="coerce",
    ).fillna(0)
    diff_n = pd.to_numeric(
        comparison["n_agents_differentiated"],
        errors="coerce",
    ).fillna(0)

    supported = comparison.loc[
        (base_n >= threshold)
        & (diff_n >= threshold)
        & comparison["delta_H_soc"].notna()
    ].copy()

    if supported.empty:
        return {
            "supported_segments": 0,
            "supported_length_m": 0.0,
        }

    length = pd.to_numeric(
        supported["length_m"],
        errors="coerce",
    )
    delta = pd.to_numeric(
        supported["delta_H_soc"],
        errors="coerce",
    )

    result = {
        "supported_segments": int(len(supported)),
        "supported_length_m": float(length.sum()),
        "H_soc_baseline_length_weighted": _weighted_mean(
            supported["H_soc_baseline"],
            length,
        ),
        "H_soc_differentiated_length_weighted": _weighted_mean(
            supported["H_soc_differentiated"],
            length,
        ),
        "delta_H_soc_length_weighted": _weighted_mean(
            delta,
            length,
        ),
        "delta_H_soc_mean": float(delta.mean()),
        "delta_H_soc_median": float(delta.median()),
    }

    total_length = float(length.sum())
    for label, mask in {
        "decrease": delta < -practical_delta,
        "stable": delta.abs() <= practical_delta,
        "increase": delta > practical_delta,
    }.items():
        result[f"length_share_{label}"] = (
            float(length.loc[mask].sum()) / total_length
            if total_length > 0
            else np.nan
        )

    for group in INCOME_GROUPS:
        column = f"contrib_delta_H_{group}"
        if column in supported.columns:
            result[f"contrib_delta_H_{group}_length_weighted"] = (
                _weighted_mean(
                    supported[column],
                    length,
                )
            )

    return result


def _build_final_bases(
    runs: pd.DataFrame,
    *,
    sensitivity_root: Path,
    dirs: dict[str, Path],
    threshold: int,
    practical_delta: float,
) -> tuple[
    pd.DataFrame,
    gpd.GeoDataFrame,
    pd.DataFrame,
    dict[int, Path],
]:
    nominal = runs.loc[
        runs["experiment"] == "nominal_seed"
    ].sort_values("seed")

    if nominal.empty:
        raise RuntimeError(
            "Nenhuma realização nominal foi encontrada."
        )

    agent_frames = []
    segment_frames = []
    seed_rows = []
    source_dirs: dict[int, Path] = {}

    for _, row in nominal.iterrows():
        seed = int(row["seed"])
        run_id = str(row["run_id"])
        run_dir = _resolve_source_dir(
            row,
            sensitivity_root=sensitivity_root,
        )
        source_dirs[seed] = run_dir

        comparison = _read_comparison_geodata(run_dir)
        comparison = _add_entropy_contributions(comparison)
        comparison["seed"] = seed
        comparison["run_id"] = run_id

        used_mask = (
            _safe_bool(comparison["used_baseline"])
            | _safe_bool(comparison["used_differentiated"])
        )
        comparison_used = comparison.loc[used_mask].copy()
        segment_frames.append(comparison_used)

        length_map = _segment_length_map(comparison)
        paired = _paired_agents(
            run_dir,
            seed=seed,
            run_id=run_id,
            length_map=length_map,
        )
        agent_frames.append(paired)

        metrics = _run_spatial_metrics(
            comparison,
            threshold=threshold,
            practical_delta=practical_delta,
        )
        metrics.update(
            {
                "seed": seed,
                "run_id": run_id,
                "source_dir": str(run_dir),
                "analysis_agents": int(
                    paired["analysis_included_both"].sum()
                ),
                "mode_change_share": float(
                    paired.loc[
                        paired["analysis_included_both"],
                        "mode_changed",
                    ].mean()
                ),
                "destination_change_share": float(
                    paired.loc[
                        paired["analysis_included_both"],
                        "destination_changed",
                    ].mean()
                ),
                "purpose_change_share": float(
                    paired.loc[
                        paired["analysis_included_both"],
                        "purpose_changed",
                    ].mean()
                ),
                "route_jaccard_length_median": float(
                    paired.loc[
                        paired["analysis_included_both"],
                        "route_jaccard_length",
                    ].median()
                ),
            }
        )
        seed_rows.append(metrics)

    agents = pd.concat(
        agent_frames,
        ignore_index=True,
    )
    segments = gpd.GeoDataFrame(
        pd.concat(
            segment_frames,
            ignore_index=True,
        ),
        geometry="geometry",
        crs=segment_frames[0].crs,
    )
    seed_base = pd.DataFrame(seed_rows).sort_values("seed")

    reconstruction_error = pd.to_numeric(
        segments["delta_H_soc_reconstruction_error"],
        errors="coerce",
    ).abs().dropna()
    if (
        not reconstruction_error.empty
        and reconstruction_error.max() > 1e-9
    ):
        raise RuntimeError(
            "A decomposição aditiva de H_soc não reconstruiu delta_H_soc "
            "dentro da tolerância numérica."
        )

    agents.to_csv(
        dirs["bases"] / "base01_agentes_pareados.csv",
        index=False,
        encoding="utf-8",
    )
    agents.to_parquet(
        dirs["bases"] / "base01_agentes_pareados.parquet",
        index=False,
    )

    segment_csv = segments.drop(columns="geometry")
    segment_csv.to_parquet(
        dirs["bases"] / "base02_segmentos_pareados.parquet",
        index=False,
    )

    gpkg_path = dirs["bases"] / "base02_segmentos_pareados.gpkg"
    if gpkg_path.exists():
        gpkg_path.unlink()
    segments.to_file(
        gpkg_path,
        layer="segmentos_pareados",
        driver="GPKG",
        engine="pyogrio",
    )

    seed_base.to_csv(
        dirs["bases"] / "base03_realizacoes.csv",
        index=False,
        encoding="utf-8",
    )
    seed_base.to_parquet(
        dirs["bases"] / "base03_realizacoes.parquet",
        index=False,
    )

    return agents, segments, seed_base, source_dirs


def _spatial_consensus(
    segments: gpd.GeoDataFrame,
    *,
    threshold: int,
    min_seeds: int,
    practical_delta: float,
    dirs: dict[str, Path],
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    supported = segments.loc[
        (
            pd.to_numeric(
                segments["n_agents_baseline"],
                errors="coerce",
            )
            >= threshold
        )
        & (
            pd.to_numeric(
                segments["n_agents_differentiated"],
                errors="coerce",
            )
            >= threshold
        )
        & segments["delta_H_soc"].notna()
    ].copy()

    records = []
    for segment_id, group in supported.groupby(
        "analysis_segment_id",
        sort=False,
    ):
        delta = pd.to_numeric(
            group["delta_H_soc"],
            errors="coerce",
        ).dropna()

        record = {
            "analysis_segment_id": segment_id,
            "support_seed_count": int(
                group["seed"].nunique()
            ),
            "delta_H_soc_median": float(delta.median()),
            "delta_H_soc_q1": float(delta.quantile(0.25)),
            "delta_H_soc_q3": float(delta.quantile(0.75)),
            "H_soc_baseline_median": float(
                pd.to_numeric(
                    group["H_soc_baseline"],
                    errors="coerce",
                ).median()
            ),
            "H_soc_differentiated_median": float(
                pd.to_numeric(
                    group["H_soc_differentiated"],
                    errors="coerce",
                ).median()
            ),
            "length_m": float(
                pd.to_numeric(
                    group["length_m"],
                    errors="coerce",
                ).median()
            ),
        }

        nonzero = delta.loc[~np.isclose(delta, 0.0)]
        if nonzero.empty:
            record["delta_sign_consistency"] = np.nan
        else:
            signs = np.sign(nonzero)
            record["delta_sign_consistency"] = float(
                max(
                    (signs > 0).mean(),
                    (signs < 0).mean(),
                )
            )

        for income in INCOME_GROUPS:
            record[
                f"contrib_delta_H_{income}_median"
            ] = float(
                pd.to_numeric(
                    group[
                        f"contrib_delta_H_{income}"
                    ],
                    errors="coerce",
                ).median()
            )

        records.append(record)

    summary = pd.DataFrame(records)
    geometries = (
        segments[
            ["analysis_segment_id", "geometry"]
        ]
        .drop_duplicates("analysis_segment_id")
    )

    consensus = geometries.merge(
        summary,
        on="analysis_segment_id",
        how="inner",
        validate="one_to_one",
    )
    consensus = gpd.GeoDataFrame(
        consensus,
        geometry="geometry",
        crs=segments.crs,
    )

    eligible = consensus["support_seed_count"] >= min_seeds
    delta = consensus["delta_H_soc_median"]

    consensus["spatial_change_class"] = "insufficient_seed_support"
    consensus.loc[
        eligible & (delta < -practical_delta),
        "spatial_change_class",
    ] = "decrease_diversity"
    consensus.loc[
        eligible & (delta.abs() <= practical_delta),
        "spatial_change_class",
    ] = "stable"
    consensus.loc[
        eligible & (delta > practical_delta),
        "spatial_change_class",
    ] = "increase_diversity"

    valid = consensus.loc[eligible].copy()
    total_length = float(valid["length_m"].sum())

    spatial_rows = []
    for change_class in (
        "decrease_diversity",
        "stable",
        "increase_diversity",
    ):
        subset = valid.loc[
            valid["spatial_change_class"] == change_class
        ]
        length_m = float(subset["length_m"].sum())
        spatial_rows.append(
            {
                "spatial_change_class": change_class,
                "segments": int(len(subset)),
                "length_m": length_m,
                "length_share": (
                    length_m / total_length
                    if total_length > 0
                    else np.nan
                ),
            }
        )

    impact = (
        valid["delta_H_soc_median"].abs()
        * valid["length_m"]
    )
    if not impact.empty and impact.sum() > 0:
        n_top = max(1, int(np.ceil(len(valid) * 0.10)))
        top_share = float(
            impact.nlargest(n_top).sum()
            / impact.sum()
        )
    else:
        top_share = np.nan

    spatial_rows.append(
        {
            "spatial_change_class": "top_10pct_abs_change_concentration",
            "segments": int(
                max(1, int(np.ceil(len(valid) * 0.10)))
                if len(valid)
                else 0
            ),
            "length_m": np.nan,
            "length_share": top_share,
        }
    )

    spatial_summary = pd.DataFrame(spatial_rows)

    gpkg = dirs["maps"] / "mapa_consenso_delta_H_soc.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    consensus.to_file(
        gpkg,
        layer="consenso_delta_H_soc",
        driver="GPKG",
        engine="pyogrio",
    )
    consensus.drop(columns="geometry").to_csv(
        dirs["stats"] / "resultado_espacial_segmentos.csv",
        index=False,
        encoding="utf-8",
    )
    spatial_summary.to_csv(
        dirs["stats"] / "resultado_espacial_resumo.csv",
        index=False,
        encoding="utf-8",
    )

    return consensus, spatial_summary


def _bootstrap_input_for_seed(
    run_dir: Path,
    *,
    length_map: dict[str, float],
) -> dict:
    observations = {}

    for scenario in SCENARIOS:
        usage = pd.read_csv(
            run_dir
            / f"edge_usage_analysis_{scenario}.csv"
        )
        required = [
            "agent_id",
            "analysis_segment_id",
            "income_group",
        ]
        usage = usage[required].drop_duplicates()
        usage["agent_id"] = usage["agent_id"].astype(str)
        usage["analysis_segment_id"] = (
            usage["analysis_segment_id"].astype(str)
        )
        observations[scenario] = usage

    common_agents = sorted(
        set(observations["baseline"]["agent_id"])
        & set(observations["differentiated"]["agent_id"])
    )

    for scenario in SCENARIOS:
        observations[scenario] = observations[
            scenario
        ].loc[
            observations[scenario]["agent_id"].isin(
                common_agents
            )
        ].copy()

    return {
        "agents": np.asarray(common_agents, dtype=object),
        "baseline": observations["baseline"],
        "differentiated": observations["differentiated"],
        "length_map": length_map,
    }


def _bootstrap_scenario(
    observations: pd.DataFrame,
    *,
    draw_counts: pd.Series,
) -> pd.DataFrame:
    frame = observations.copy()
    frame["bootstrap_weight"] = (
        frame["agent_id"]
        .map(draw_counts)
        .fillna(0)
        .astype(int)
    )
    frame = frame.loc[
        frame["bootstrap_weight"] > 0
    ]

    counts = (
        frame.groupby(
            ["analysis_segment_id", "income_group"]
        )["bootstrap_weight"]
        .sum()
        .unstack(fill_value=0)
        .reindex(columns=list(INCOME_GROUPS), fill_value=0)
    )

    total = counts.sum(axis=1).astype(float)
    proportions = counts.div(total, axis=0)

    entropy = np.zeros(len(counts), dtype=float)
    for income in INCOME_GROUPS:
        entropy += np.nan_to_num(
            _entropy_term(
                proportions[income].to_numpy()
            ),
            nan=0.0,
        )

    result = pd.DataFrame(
        {
            "n_agents": total,
            "H_soc": entropy,
        },
        index=counts.index,
    )
    for income in INCOME_GROUPS:
        result[f"p_{income}"] = proportions[income]

    return result


def _bootstrap_seed_metric(
    data: dict,
    *,
    rng: np.random.Generator,
    threshold: int,
    practical_delta: float,
) -> dict:
    agents = data["agents"]
    if len(agents) == 0:
        return {}

    sampled = rng.choice(
        agents,
        size=len(agents),
        replace=True,
    )
    draw_counts = pd.Series(sampled).value_counts()

    baseline = _bootstrap_scenario(
        data["baseline"],
        draw_counts=draw_counts,
    )
    differentiated = _bootstrap_scenario(
        data["differentiated"],
        draw_counts=draw_counts,
    )

    comparison = baseline.add_suffix(
        "_baseline"
    ).join(
        differentiated.add_suffix(
            "_differentiated"
        ),
        how="inner",
    )

    supported = comparison.loc[
        (
            comparison["n_agents_baseline"]
            >= threshold
        )
        & (
            comparison["n_agents_differentiated"]
            >= threshold
        )
    ].copy()

    if supported.empty:
        return {}

    supported["delta_H_soc"] = (
        supported["H_soc_differentiated"]
        - supported["H_soc_baseline"]
    )
    supported["length_m"] = (
        supported.index.astype(str)
        .map(data["length_map"])
        .astype(float)
    )
    supported = supported.loc[
        supported["length_m"].notna()
        & (supported["length_m"] > 0)
    ]

    if supported.empty:
        return {}

    length = supported["length_m"]
    delta = supported["delta_H_soc"]

    result = {
        "H_soc_baseline_length_weighted": _weighted_mean(
            supported["H_soc_baseline"],
            length,
        ),
        "H_soc_differentiated_length_weighted": _weighted_mean(
            supported["H_soc_differentiated"],
            length,
        ),
        "delta_H_soc_length_weighted": _weighted_mean(
            delta,
            length,
        ),
        "delta_H_soc_mean": float(delta.mean()),
        "supported_segments": float(len(supported)),
    }

    total_length = float(length.sum())
    result["length_share_decrease"] = float(
        length.loc[
            delta < -practical_delta
        ].sum()
        / total_length
    )
    result["length_share_stable"] = float(
        length.loc[
            delta.abs() <= practical_delta
        ].sum()
        / total_length
    )
    result["length_share_increase"] = float(
        length.loc[
            delta > practical_delta
        ].sum()
        / total_length
    )

    for income in INCOME_GROUPS:
        base_term = _entropy_term(
            supported[f"p_{income}_baseline"]
        )
        diff_term = _entropy_term(
            supported[f"p_{income}_differentiated"]
        )
        contribution = diff_term - base_term
        result[
            f"contrib_delta_H_{income}_length_weighted"
        ] = _weighted_mean(
            contribution,
            length,
        )

    return result


def _hierarchical_bootstrap(
    *,
    source_dirs: dict[int, Path],
    segments: gpd.GeoDataFrame,
    seed_base: pd.DataFrame,
    reps: int,
    bootstrap_seed: int,
    threshold: int,
    practical_delta: float,
    dirs: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if reps < 100:
        raise ValueError(
            "Use ao menos 100 replicações de bootstrap."
        )

    inputs = {}
    for seed, run_dir in source_dirs.items():
        seed_segments = segments.loc[
            segments["seed"] == seed
        ]
        length_map = (
            seed_segments[
                ["analysis_segment_id", "length_m"]
            ]
            .drop_duplicates("analysis_segment_id")
            .assign(
                analysis_segment_id=lambda x: x[
                    "analysis_segment_id"
                ].astype(str)
            )
            .set_index("analysis_segment_id")["length_m"]
            .astype(float)
            .to_dict()
        )
        inputs[seed] = _bootstrap_input_for_seed(
            run_dir,
            length_map=length_map,
        )

    seeds = np.asarray(sorted(inputs), dtype=int)
    rng = np.random.default_rng(bootstrap_seed)

    bootstrap_rows = []
    for replicate in tqdm(
        range(reps),
        desc="Bootstrap hierárquico",
    ):
        sampled_seeds = rng.choice(
            seeds,
            size=len(seeds),
            replace=True,
        )
        seed_metrics = []
        for seed in sampled_seeds:
            metric = _bootstrap_seed_metric(
                inputs[int(seed)],
                rng=rng,
                threshold=threshold,
                practical_delta=practical_delta,
            )
            if metric:
                seed_metrics.append(metric)

        if not seed_metrics:
            continue

        frame = pd.DataFrame(seed_metrics)
        row = {
            "bootstrap_rep": replicate,
        }
        for column in frame.columns:
            row[column] = float(
                pd.to_numeric(
                    frame[column],
                    errors="coerce",
                ).median()
            )
        bootstrap_rows.append(row)

    distribution = pd.DataFrame(bootstrap_rows)
    if distribution.empty:
        raise RuntimeError(
            "O bootstrap não produziu replicações válidas."
        )

    primary_columns = [
        "H_soc_baseline_length_weighted",
        "H_soc_differentiated_length_weighted",
        "delta_H_soc_length_weighted",
        "delta_H_soc_mean",
        "supported_segments",
        "length_share_decrease",
        "length_share_stable",
        "length_share_increase",
        *[
            f"contrib_delta_H_{income}_length_weighted"
            for income in INCOME_GROUPS
        ],
    ]

    summary_rows = []
    for metric in primary_columns:
        if metric not in distribution.columns:
            continue

        values = pd.to_numeric(
            distribution[metric],
            errors="coerce",
        ).dropna()

        if metric in seed_base.columns:
            observed = float(
                pd.to_numeric(
                    seed_base[metric],
                    errors="coerce",
                ).median()
            )
        else:
            observed = np.nan

        seed_sign_consistency = np.nan
        if (
            metric in seed_base.columns
            and "delta" in metric.lower()
            and np.isfinite(observed)
            and not np.isclose(observed, 0.0)
        ):
            seed_values = pd.to_numeric(
                seed_base[metric],
                errors="coerce",
            ).dropna()
            seed_values = seed_values.loc[
                ~np.isclose(seed_values, 0.0)
            ]
            if not seed_values.empty:
                seed_sign_consistency = float(
                    (
                        np.sign(seed_values)
                        == np.sign(observed)
                    ).mean()
                )

        summary_rows.append(
            {
                "metric": metric,
                "point_estimate_seed_median": observed,
                "bootstrap_median": float(values.median()),
                "ci95_low": float(values.quantile(0.025)),
                "ci95_high": float(values.quantile(0.975)),
                "seed_sign_consistency": seed_sign_consistency,
                "bootstrap_reps_valid": int(len(values)),
                "inference_unit": (
                    "hierarchical bootstrap: seed + complete agent trajectory"
                ),
                "segments_treated_as_independent": False,
            }
        )

    summary = pd.DataFrame(summary_rows)

    distribution.to_parquet(
        dirs["stats"]
        / "bootstrap_hierarquico_distribuicao.parquet",
        index=False,
    )
    summary.to_csv(
        dirs["stats"]
        / "resultado_principal_bootstrap.csv",
        index=False,
        encoding="utf-8",
    )

    return distribution, summary


def _behavioral_mechanisms(
    agents: pd.DataFrame,
    *,
    dirs: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    included = agents.loc[
        _safe_bool(
            agents["analysis_included_both"]
        )
    ].copy()

    rows = []
    for (seed, income), group in included.groupby(
        ["seed", "income_group"]
    ):
        rows.append(
            {
                "seed": int(seed),
                "income_group": income,
                "n_agents": int(len(group)),
                "purpose_change_share": float(
                    group["purpose_changed"].mean()
                ),
                "destination_change_share": float(
                    group["destination_changed"].mean()
                ),
                "mode_change_share": float(
                    group["mode_changed"].mean()
                ),
                "route_jaccard_length_median": float(
                    pd.to_numeric(
                        group["route_jaccard_length"],
                        errors="coerce",
                    ).median()
                ),
                "delta_od_distance_m_median": (
                    float(
                        pd.to_numeric(
                            group["delta_od_distance_m"],
                            errors="coerce",
                        ).median()
                    )
                    if "delta_od_distance_m" in group.columns
                    else np.nan
                ),
                "delta_travel_distance_m_median": (
                    float(
                        pd.to_numeric(
                            group["delta_travel_distance_m"],
                            errors="coerce",
                        ).median()
                    )
                    if "delta_travel_distance_m" in group.columns
                    else np.nan
                ),
            }
        )

    by_income_seed = pd.DataFrame(rows)

    transitions = (
        included.groupby(
            [
                "income_group",
                "mode_baseline",
                "mode_differentiated",
            ],
            dropna=False,
        )
        .size()
        .rename("n")
        .reset_index()
    )
    totals = (
        transitions.groupby("income_group")["n"]
        .sum()
        .rename("income_total")
    )
    transitions = transitions.merge(
        totals,
        on="income_group",
        how="left",
    )
    transitions["share_within_income"] = (
        transitions["n"]
        / transitions["income_total"]
    )

    by_income_seed.to_csv(
        dirs["stats"] / "mecanismos_comportamentais_por_seed_renda.csv",
        index=False,
        encoding="utf-8",
    )
    transitions.to_csv(
        dirs["stats"] / "mecanismos_transicoes_modais.csv",
        index=False,
        encoding="utf-8",
    )

    return by_income_seed, transitions


def _metric_from_run_dir(
    run_dir: Path,
    *,
    threshold: int,
    practical_delta: float,
) -> dict:
    comparison = _add_entropy_contributions(
        _read_comparison_geodata(run_dir)
    )
    return _run_spatial_metrics(
        comparison,
        threshold=threshold,
        practical_delta=practical_delta,
    )


def _mode_decomposition(
    runs: pd.DataFrame,
    *,
    sensitivity_root: Path,
    threshold: int,
    practical_delta: float,
    seed_base: pd.DataFrame,
    dirs: dict[str, Path],
) -> pd.DataFrame:
    mechanism_runs = runs.loc[
        runs["experiment"] == "mode_homogenized"
    ]

    rows = []
    for _, row in mechanism_runs.iterrows():
        seed = int(row["seed"])
        run_dir = _resolve_source_dir(
            row,
            sensitivity_root=sensitivity_root,
        )
        no_mode = _metric_from_run_dir(
            run_dir,
            threshold=threshold,
            practical_delta=practical_delta,
        )

        nominal = seed_base.loc[
            seed_base["seed"] == seed
        ]
        if nominal.empty:
            continue

        full_delta = float(
            nominal.iloc[0][
                "delta_H_soc_length_weighted"
            ]
        )
        purpose_destination = float(
            no_mode.get(
                "delta_H_soc_length_weighted",
                np.nan,
            )
        )

        rows.append(
            {
                "seed": seed,
                "total_delta_H_soc": full_delta,
                "purpose_destination_component": purpose_destination,
                "mode_differentiation_component": (
                    full_delta - purpose_destination
                ),
                "decomposition_note": (
                    "Sequencial: baseline -> propósito+destino diferenciados "
                    "com modo homogêneo -> configuração differentiated completa."
                ),
            }
        )

    result = pd.DataFrame(rows)
    result.to_csv(
        dirs["stats"] / "mecanismo_decomposicao_modo.csv",
        index=False,
        encoding="utf-8",
    )
    return result


def _parameter_sensitivity(
    runs: pd.DataFrame,
    *,
    sensitivity_root: Path,
    threshold: int,
    practical_delta: float,
    seed_base: pd.DataFrame,
    dirs: dict[str, Path],
) -> pd.DataFrame:
    perturbations = runs.loc[
        runs["experiment"].isin(
            ["destination_decay", "mode_decay"]
        )
    ]

    rows = []
    for _, row in perturbations.iterrows():
        seed = int(row["seed"])
        run_dir = _resolve_source_dir(
            row,
            sensitivity_root=sensitivity_root,
        )
        metrics = _metric_from_run_dir(
            run_dir,
            threshold=threshold,
            practical_delta=practical_delta,
        )
        nominal = seed_base.loc[
            seed_base["seed"] == seed
        ]
        if nominal.empty:
            continue

        reference = float(
            nominal.iloc[0][
                "delta_H_soc_length_weighted"
            ]
        )
        value = float(
            metrics.get(
                "delta_H_soc_length_weighted",
                np.nan,
            )
        )

        rows.append(
            {
                "run_id": row["run_id"],
                "experiment": row["experiment"],
                "seed": seed,
                "destination_decay_multiplier": float(
                    row["destination_decay_multiplier"]
                ),
                "mode_decay_multiplier": float(
                    row["mode_decay_multiplier"]
                ),
                "delta_H_soc_length_weighted": value,
                "nominal_reference": reference,
                "change_from_nominal": value - reference,
                "same_sign_as_nominal": (
                    bool(np.sign(value) == np.sign(reference))
                    if np.isfinite(value)
                    and np.isfinite(reference)
                    and not np.isclose(reference, 0.0)
                    else np.nan
                ),
            }
        )

    result = pd.DataFrame(rows)
    result.to_csv(
        dirs["stats"] / "sensibilidade_parametros_artigo.csv",
        index=False,
        encoding="utf-8",
    )
    return result


def _direct_article_result(
    *,
    bootstrap_summary: pd.DataFrame,
    seed_base: pd.DataFrame,
    dirs: dict[str, Path],
) -> pd.DataFrame:
    def metric_row(name: str) -> pd.Series:
        rows = bootstrap_summary.loc[
            bootstrap_summary["metric"] == name
        ]
        if rows.empty:
            return pd.Series(dtype=float)
        return rows.iloc[0]

    baseline = metric_row(
        "H_soc_baseline_length_weighted"
    )
    differentiated = metric_row(
        "H_soc_differentiated_length_weighted"
    )
    delta = metric_row(
        "delta_H_soc_length_weighted"
    )

    result = pd.DataFrame(
        [
            {
                "H_soc_baseline_seed_median": baseline.get(
                    "point_estimate_seed_median",
                    np.nan,
                ),
                "H_soc_differentiated_seed_median": differentiated.get(
                    "point_estimate_seed_median",
                    np.nan,
                ),
                "delta_H_soc_seed_median": delta.get(
                    "point_estimate_seed_median",
                    np.nan,
                ),
                "delta_H_soc_ci95_low": delta.get(
                    "ci95_low",
                    np.nan,
                ),
                "delta_H_soc_ci95_high": delta.get(
                    "ci95_high",
                    np.nan,
                ),
                "delta_H_soc_seed_sign_consistency": delta.get(
                    "seed_sign_consistency",
                    np.nan,
                ),
                "supported_segments_seed_median": float(
                    pd.to_numeric(
                        seed_base["supported_segments"],
                        errors="coerce",
                    ).median()
                ),
                "supported_length_km_seed_median": float(
                    pd.to_numeric(
                        seed_base["supported_length_m"],
                        errors="coerce",
                    ).median()
                    / 1000.0
                ),
                "length_share_decrease_seed_median": float(
                    seed_base["length_share_decrease"].median()
                ),
                "length_share_stable_seed_median": float(
                    seed_base["length_share_stable"].median()
                ),
                "length_share_increase_seed_median": float(
                    seed_base["length_share_increase"].median()
                ),
                "inference_unit": (
                    "seeds + paired complete agent trajectories; "
                    "segments are not independent observations"
                ),
            }
        ]
    )

    result.to_csv(
        dirs["stats"] / "resposta_pergunta_artigo.csv",
        index=False,
        encoding="utf-8",
    )
    return result


def _make_tables(
    *,
    bootstrap_summary: pd.DataFrame,
    seed_base: pd.DataFrame,
    mechanism_income: pd.DataFrame,
    mode_decomposition: pd.DataFrame,
    sensitivity: pd.DataFrame,
    spatial_summary: pd.DataFrame,
    dirs: dict[str, Path],
) -> None:
    main_metrics = {
        "H_soc_baseline_length_weighted",
        "H_soc_differentiated_length_weighted",
        "delta_H_soc_length_weighted",
        "length_share_decrease",
        "length_share_stable",
        "length_share_increase",
    }
    table1 = bootstrap_summary.loc[
        bootstrap_summary["metric"].isin(main_metrics)
    ].copy()

    contribution_metrics = {
        f"contrib_delta_H_{income}_length_weighted"
        for income in INCOME_GROUPS
    }
    table2 = bootstrap_summary.loc[
        bootstrap_summary["metric"].isin(
            contribution_metrics
        )
    ].copy()

    if not mode_decomposition.empty:
        decomposition_summary = pd.DataFrame(
            {
                "mechanism": [
                    "purpose_destination_component",
                    "mode_differentiation_component",
                    "total_delta_H_soc",
                ],
                "seed_median": [
                    mode_decomposition[
                        "purpose_destination_component"
                    ].median(),
                    mode_decomposition[
                        "mode_differentiation_component"
                    ].median(),
                    mode_decomposition[
                        "total_delta_H_soc"
                    ].median(),
                ],
                "seed_q1": [
                    mode_decomposition[
                        "purpose_destination_component"
                    ].quantile(0.25),
                    mode_decomposition[
                        "mode_differentiation_component"
                    ].quantile(0.25),
                    mode_decomposition[
                        "total_delta_H_soc"
                    ].quantile(0.25),
                ],
                "seed_q3": [
                    mode_decomposition[
                        "purpose_destination_component"
                    ].quantile(0.75),
                    mode_decomposition[
                        "mode_differentiation_component"
                    ].quantile(0.75),
                    mode_decomposition[
                        "total_delta_H_soc"
                    ].quantile(0.75),
                ],
            }
        )
        table2 = pd.concat(
            [
                table2.assign(section="entropy_composition"),
                decomposition_summary.assign(
                    section="behavioral_decomposition"
                ),
            ],
            ignore_index=True,
            sort=False,
        )

    table3 = sensitivity.copy()

    table1.to_csv(
        dirs["tables"] / "tabela01_resultado_principal.csv",
        index=False,
        encoding="utf-8",
    )
    table2.to_csv(
        dirs["tables"] / "tabela02_mecanismos.csv",
        index=False,
        encoding="utf-8",
    )
    table3.to_csv(
        dirs["tables"] / "tabela03_robustez.csv",
        index=False,
        encoding="utf-8",
    )

    workbook = dirs["tables"] / "tabelas_artigo.xlsx"
    with pd.ExcelWriter(
        workbook,
        engine="xlsxwriter",
    ) as writer:
        table1.to_excel(
            writer,
            sheet_name="Resultado principal",
            index=False,
        )
        table2.to_excel(
            writer,
            sheet_name="Mecanismos",
            index=False,
        )
        table3.to_excel(
            writer,
            sheet_name="Robustez",
            index=False,
        )
        seed_base.to_excel(
            writer,
            sheet_name="Resultados por seed",
            index=False,
        )
        mechanism_income.to_excel(
            writer,
            sheet_name="Mecanismos renda",
            index=False,
        )
        spatial_summary.to_excel(
            writer,
            sheet_name="Espacial",
            index=False,
        )


def _save_figure(
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
    plt.close(figure)


def _plot_map(
    *,
    network: gpd.GeoDataFrame,
    consensus: gpd.GeoDataFrame,
    column: str,
    title: str,
    path: Path,
    dpi: int,
    min_seeds: int,
    diverging: bool,
) -> None:
    figure, axis = plt.subplots(figsize=(10, 10))

    network.plot(
        ax=axis,
        linewidth=0.25,
        color="#d9d9d9",
        alpha=0.45,
    )

    data = consensus.loc[
        consensus["support_seed_count"] >= min_seeds
    ].copy()
    values = pd.to_numeric(
        data[column],
        errors="coerce",
    )
    data = data.loc[values.notna()].copy()
    values = pd.to_numeric(data[column], errors="coerce")

    if not data.empty:
        if diverging:
            max_abs = float(np.nanmax(np.abs(values)))
            if max_abs <= 0:
                max_abs = 1.0
            norm = TwoSlopeNorm(
                vmin=-max_abs,
                vcenter=0.0,
                vmax=max_abs,
            )
            data.plot(
                ax=axis,
                column=column,
                cmap="RdBu",
                norm=norm,
                linewidth=1.2,
                legend=True,
                legend_kwds={
                    "label": column,
                    "shrink": 0.65,
                },
            )
        else:
            data.plot(
                ax=axis,
                column=column,
                cmap="viridis",
                vmin=0,
                vmax=1,
                linewidth=1.2,
                legend=True,
                legend_kwds={
                    "label": column,
                    "shrink": 0.65,
                },
            )

    axis.set_title(title)
    axis.set_axis_off()
    _save_figure(
        figure,
        path,
        dpi=dpi,
    )


def _make_figures(
    *,
    seed_base: pd.DataFrame,
    bootstrap_summary: pd.DataFrame,
    spatial_summary: pd.DataFrame,
    consensus: gpd.GeoDataFrame,
    full_network: gpd.GeoDataFrame,
    mechanism_income: pd.DataFrame,
    mode_decomposition: pd.DataFrame,
    sensitivity: pd.DataFrame,
    dirs: dict[str, Path],
    dpi: int,
    min_seeds: int,
) -> pd.DataFrame:
    manifests = []

    # 1-3. Mapas
    map_specs = [
        (
            "H_soc_baseline_median",
            "H_soc mediana — baseline",
            "fig01_mapa_H_soc_baseline.png",
            False,
        ),
        (
            "H_soc_differentiated_median",
            "H_soc mediana — differentiated",
            "fig02_mapa_H_soc_differentiated.png",
            False,
        ),
        (
            "delta_H_soc_median",
            "ΔH_soc mediano entre seeds",
            "fig03_mapa_delta_H_soc.png",
            True,
        ),
    ]
    for column, title, filename, diverging in map_specs:
        path = dirs["figures"] / filename
        _plot_map(
            network=full_network,
            consensus=consensus,
            column=column,
            title=title,
            path=path,
            dpi=dpi,
            min_seeds=min_seeds,
            diverging=diverging,
        )
        manifests.append(
            {
                "figure": filename,
                "type": "map",
                "message": title,
            }
        )

    # 4. H_soc pareado por seed
    figure, axis = plt.subplots(figsize=(7, 6))
    for _, row in seed_base.iterrows():
        x = [0, 1]
        y = [
            row["H_soc_baseline_length_weighted"],
            row["H_soc_differentiated_length_weighted"],
        ]
        axis.plot(x, y, marker="o", alpha=0.7)
    axis.set_xticks([0, 1], ["Baseline", "Differentiated"])
    axis.set_ylabel("H_soc ponderado pelo comprimento")
    axis.set_title("Diversidade socioeconômica da rede por realização")
    axis.grid(axis="y", alpha=0.2)
    filename = "fig04_H_soc_pareado_por_seed.png"
    _save_figure(
        figure,
        dirs["figures"] / filename,
        dpi=dpi,
    )
    manifests.append(
        {
            "figure": filename,
            "type": "chart",
            "message": "Comparação pareada do H_soc agregado em cada seed.",
        }
    )

    # 5. Delta por seed + IC bootstrap hierárquico
    figure, axis = plt.subplots(figsize=(8, 5))
    values = seed_base[
        "delta_H_soc_length_weighted"
    ].to_numpy(dtype=float)
    seeds = seed_base["seed"].astype(str).tolist()
    axis.scatter(
        np.arange(len(values)),
        values,
        s=55,
        label="Seeds",
    )
    primary = bootstrap_summary.loc[
        bootstrap_summary["metric"]
        == "delta_H_soc_length_weighted"
    ]
    if not primary.empty:
        row = primary.iloc[0]
        x = len(values) + 0.7
        axis.errorbar(
            x,
            row["point_estimate_seed_median"],
            yerr=[
                [
                    row["point_estimate_seed_median"]
                    - row["ci95_low"]
                ],
                [
                    row["ci95_high"]
                    - row["point_estimate_seed_median"]
                ],
            ],
            fmt="o",
            capsize=6,
            label="Mediana + IC95% hierárquico",
        )
        labels = seeds + ["Síntese"]
        axis.set_xticks(
            list(range(len(values))) + [x],
            labels,
        )
    else:
        axis.set_xticks(
            np.arange(len(values)),
            seeds,
        )
    axis.axhline(0, linewidth=1, color="black", alpha=0.5)
    axis.set_ylabel("ΔH_soc ponderado pelo comprimento")
    axis.set_xlabel("Seed")
    axis.set_title("Efeito agregado e incerteza sem independência de segmentos")
    axis.legend()
    axis.grid(axis="y", alpha=0.2)
    filename = "fig05_delta_H_soc_seeds_bootstrap.png"
    _save_figure(
        figure,
        dirs["figures"] / filename,
        dpi=dpi,
    )
    manifests.append(
        {
            "figure": filename,
            "type": "chart",
            "message": (
                "Resultado principal com bootstrap hierárquico de seeds "
                "e trajetórias completas dos agentes."
            ),
        }
    )

    # 6. Extensão espacial
    shares = seed_base[
        [
            "seed",
            "length_share_decrease",
            "length_share_stable",
            "length_share_increase",
        ]
    ].copy()
    figure, axis = plt.subplots(figsize=(9, 5))
    bottom = np.zeros(len(shares))
    for column, label in [
        ("length_share_decrease", "ΔH < -limiar"),
        ("length_share_stable", "|ΔH| ≤ limiar"),
        ("length_share_increase", "ΔH > limiar"),
    ]:
        values = shares[column].to_numpy(dtype=float) * 100
        axis.bar(
            shares["seed"].astype(str),
            values,
            bottom=bottom,
            label=label,
        )
        bottom += values
    axis.set_ylim(0, 100)
    axis.set_ylabel("% do comprimento com suporte")
    axis.set_xlabel("Seed")
    axis.set_title("Extensão espacial da mudança em H_soc")
    axis.legend()
    filename = "fig06_extensao_espacial_delta.png"
    _save_figure(
        figure,
        dirs["figures"] / filename,
        dpi=dpi,
    )
    manifests.append(
        {
            "figure": filename,
            "type": "chart",
            "message": "Proporção do comprimento da rede por direção da mudança.",
        }
    )

    # 7. Contribuições exatas da composição por renda
    contribution_columns = [
        f"contrib_delta_H_{income}_length_weighted"
        for income in INCOME_GROUPS
    ]
    medians = [
        seed_base[column].median()
        for column in contribution_columns
    ]
    q1 = [
        seed_base[column].quantile(0.25)
        for column in contribution_columns
    ]
    q3 = [
        seed_base[column].quantile(0.75)
        for column in contribution_columns
    ]
    figure, axis = plt.subplots(figsize=(7, 5))
    x = np.arange(len(INCOME_GROUPS))
    axis.bar(x, medians)
    axis.errorbar(
        x,
        medians,
        yerr=[
            np.asarray(medians) - np.asarray(q1),
            np.asarray(q3) - np.asarray(medians),
        ],
        fmt="none",
        capsize=5,
        color="black",
    )
    axis.axhline(0, linewidth=1, color="black", alpha=0.5)
    axis.set_xticks(x, ["Baixa", "Média", "Alta"])
    axis.set_ylabel("Contribuição para ΔH_soc")
    axis.set_title("Contribuições exatas da composição socioeconômica")
    filename = "fig07_contribuicoes_entropia_renda.png"
    _save_figure(
        figure,
        dirs["figures"] / filename,
        dpi=dpi,
    )
    manifests.append(
        {
            "figure": filename,
            "type": "chart",
            "message": (
                "Decomposição aditiva exata de ΔH_soc pelos termos "
                "-p log(p) de cada grupo de renda."
            ),
        }
    )

    # 8. Mecanismos comportamentais por renda
    if not mechanism_income.empty:
        grouped = (
            mechanism_income.groupby("income_group")[
                [
                    "purpose_change_share",
                    "destination_change_share",
                    "mode_change_share",
                ]
            ]
            .median()
            .reindex(list(INCOME_GROUPS))
        )
        figure, axis = plt.subplots(figsize=(9, 5))
        x = np.arange(len(grouped))
        width = 0.24
        columns = [
            ("purpose_change_share", "Propósito"),
            ("destination_change_share", "Destino"),
            ("mode_change_share", "Modo"),
        ]
        for index, (column, label) in enumerate(columns):
            axis.bar(
                x + (index - 1) * width,
                grouped[column].to_numpy() * 100,
                width=width,
                label=label,
            )
        axis.set_xticks(
            x,
            ["Baixa", "Média", "Alta"],
        )
        axis.set_ylabel("% de agentes com mudança")
        axis.set_title("Mecanismos comportamentais por grupo de renda")
        axis.legend()
        filename = "fig08_mecanismos_comportamentais_renda.png"
        _save_figure(
            figure,
            dirs["figures"] / filename,
            dpi=dpi,
        )
        manifests.append(
            {
                "figure": filename,
                "type": "chart",
                "message": "Mudanças de propósito, destino e modo entre cenários.",
            }
        )

        route = (
            mechanism_income.groupby("income_group")[
                "route_jaccard_length_median"
            ]
            .median()
            .reindex(list(INCOME_GROUPS))
        )
        figure, axis = plt.subplots(figsize=(7, 5))
        axis.bar(
            ["Baixa", "Média", "Alta"],
            route.to_numpy(),
        )
        axis.set_ylim(0, 1)
        axis.set_ylabel("Jaccard ponderado pelo comprimento")
        axis.set_title("Sobreposição das trajetórias entre cenários")
        filename = "fig09_sobreposicao_trajetorias_renda.png"
        _save_figure(
            figure,
            dirs["figures"] / filename,
            dpi=dpi,
        )
        manifests.append(
            {
                "figure": filename,
                "type": "chart",
                "message": "Sobreposição espacial das rotas por grupo de renda.",
            }
        )

    # 10. Decomposição modo x propósito+destino
    if not mode_decomposition.empty:
        ordered = mode_decomposition.sort_values("seed")
        figure, axis = plt.subplots(figsize=(9, 5))
        x = np.arange(len(ordered))
        width = 0.27
        axis.bar(
            x - width,
            ordered["purpose_destination_component"],
            width=width,
            label="Propósito + destino",
        )
        axis.bar(
            x,
            ordered["mode_differentiation_component"],
            width=width,
            label="Diferenciação modal",
        )
        axis.scatter(
            x + width,
            ordered["total_delta_H_soc"],
            label="ΔH total",
            zorder=3,
        )
        axis.axhline(0, linewidth=1, color="black", alpha=0.5)
        axis.set_xticks(x, ordered["seed"].astype(str))
        axis.set_ylabel("Contribuição para ΔH_soc")
        axis.set_xlabel("Seed")
        axis.set_title("Decomposição comportamental sequencial")
        axis.legend()
        filename = "fig10_decomposicao_comportamental.png"
        _save_figure(
            figure,
            dirs["figures"] / filename,
            dpi=dpi,
        )
        manifests.append(
            {
                "figure": filename,
                "type": "chart",
                "message": (
                    "Separação sequencial do efeito de propósito+destino "
                    "e da diferenciação modal."
                ),
            }
        )

    # 11. Sensibilidade paramétrica
    if not sensitivity.empty:
        labels = []
        for _, row in sensitivity.iterrows():
            if row["experiment"] == "destination_decay":
                label = (
                    "Destino β × "
                    f"{row['destination_decay_multiplier']:.2f}"
                )
            else:
                label = (
                    "Modo β × "
                    f"{row['mode_decay_multiplier']:.2f}"
                )
            labels.append(label)

        figure, axis = plt.subplots(figsize=(8, 5))
        axis.barh(
            labels,
            sensitivity["change_from_nominal"],
        )
        axis.axvline(0, linewidth=1, color="black", alpha=0.5)
        axis.set_xlabel("Mudança em ΔH_soc vs. configuração nominal")
        axis.set_title("Sensibilidade local dos parâmetros comportamentais")
        filename = "fig11_sensibilidade_parametros.png"
        _save_figure(
            figure,
            dirs["figures"] / filename,
            dpi=dpi,
        )
        manifests.append(
            {
                "figure": filename,
                "type": "chart",
                "message": "Perturbações locais de ±25% nos decaimentos.",
            }
        )

    manifest = pd.DataFrame(manifests)
    manifest.to_csv(
        dirs["figures"] / "figuras_manifesto.csv",
        index=False,
        encoding="utf-8",
    )
    return manifest


def _write_report(
    *,
    article: dict,
    seed_base: pd.DataFrame,
    bootstrap_summary: pd.DataFrame,
    spatial_summary: pd.DataFrame,
    mode_decomposition: pd.DataFrame,
    sensitivity: pd.DataFrame,
    dirs: dict[str, Path],
) -> None:
    primary = bootstrap_summary.loc[
        bootstrap_summary["metric"]
        == "delta_H_soc_length_weighted"
    ]

    if primary.empty:
        primary_text = "Resultado principal indisponível."
    else:
        row = primary.iloc[0]
        primary_text = (
            f"Mediana entre seeds = "
            f"{row['point_estimate_seed_median']:.3f}; "
            f"IC95% bootstrap hierárquico "
            f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]."
        )

    spatial = spatial_summary.loc[
        spatial_summary["spatial_change_class"].isin(
            [
                "decrease_diversity",
                "stable",
                "increase_diversity",
            ]
        )
    ].copy()

    spatial_lines = []
    for _, row in spatial.iterrows():
        spatial_lines.append(
            f"- {row['spatial_change_class']}: "
            f"{100 * row['length_share']:.1f}% do comprimento elegível."
        )

    mode_text = (
        "A decomposição modal não está disponível."
        if mode_decomposition.empty
        else (
            "Mediana do componente propósito+destino = "
            f"{mode_decomposition['purpose_destination_component'].median():.3f}; "
            "componente modal = "
            f"{mode_decomposition['mode_differentiation_component'].median():.3f}."
        )
    )

    robustness = (
        "Sensibilidades paramétricas ainda não disponíveis."
        if sensitivity.empty
        else (
            f"Foram avaliadas {len(sensitivity)} perturbações locais "
            "dos parâmetros de distância."
        )
    )

    lines = [
        "# Resultados v01 do artigo",
        "",
        "## Pergunta operacional",
        "",
        article.get(
            "operational_question",
            "Pergunta operacional não configurada.",
        ),
        "",
        "## Resultado principal",
        "",
        primary_text,
        "",
        "A inferência não usa segmentos como observações independentes. "
        "O intervalo é obtido por bootstrap hierárquico: reamostragem de seeds "
        "e, dentro de cada seed, reamostragem pareada de agentes preservando "
        "toda a trajetória de cada agente.",
        "",
        "## Dimensão espacial",
        "",
        *spatial_lines,
        "",
        "## Mecanismos",
        "",
        mode_text,
        "",
        "A contribuição de cada grupo de renda para ΔH_soc também é calculada "
        "exatamente pela diferença entre os termos -p log(p) de baseline e "
        "differentiated; as contribuições somam o ΔH_soc do segmento.",
        "",
        "## Robustez",
        "",
        robustness,
        "",
        "## Bases analíticas finais",
        "",
        "- base01_agentes_pareados",
        "- base02_segmentos_pareados",
        "- base03_realizacoes",
        "",
        "## Observação interpretativa",
        "",
        "ΔH_soc descreve aumento ou redução da diversidade socioeconômica "
        "observada nas trajetórias. O sinal não é tratado como melhora ou piora.",
        "",
    ]

    (
        dirs["report"]
        / "resultados_v01_artigo.md"
    ).write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def _write_manifest(
    *,
    dirs: dict[str, Path],
    article: dict,
    runs: pd.DataFrame,
    bootstrap_reps: int,
    bootstrap_seed: int,
) -> None:
    manifest = {
        "version": "v01 artigo",
        "operational_question": article.get(
            "operational_question"
        ),
        "main_outcome": article.get(
            "main_outcome",
            "length_weighted_mean_delta_H_soc",
        ),
        "primary_flow_threshold": int(
            article.get("primary_flow_threshold", 5)
        ),
        "consensus_min_seeds": int(
            article.get("consensus_min_seeds", 3)
        ),
        "delta_h_practical_threshold": float(
            article.get(
                "delta_h_practical_threshold",
                0.05,
            )
        ),
        "bootstrap_reps": int(bootstrap_reps),
        "bootstrap_seed": int(bootstrap_seed),
        "nominal_seeds": sorted(
            runs.loc[
                runs["experiment"] == "nominal_seed",
                "seed",
            ]
            .astype(int)
            .unique()
            .tolist()
        ),
        "inference": (
            "Hierarchical bootstrap of seeds and paired complete agent "
            "trajectories. Segments are descriptive spatial units, not "
            "independent statistical observations."
        ),
    }

    with (
        dirs["root"]
        / "00_manifesto_analise.json"
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
    article = _article_config(config)

    output_root = _resolve_project_path(args.output_dir)
    sensitivity_root = _resolve_project_path(
        args.sensitivity_root
    )
    dirs = _ensure_dirs(output_root)

    if not args.skip_simulations:
        _run_final_sensitivity(
            force=args.force_simulations,
        )

    runs_path = (
        sensitivity_root
        / "final_sensitivity_runs.csv"
    )
    if not runs_path.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {runs_path}. "
            "Execute sem --skip-simulations."
        )

    runs = pd.read_csv(runs_path)

    threshold = int(
        article.get("primary_flow_threshold", 5)
    )
    practical_delta = float(
        article.get(
            "delta_h_practical_threshold",
            0.05,
        )
    )
    min_seeds = int(
        article.get("consensus_min_seeds", 3)
    )
    dpi = int(
        article.get("figure_dpi", 300)
    )

    print("1/8 - Construindo três bases analíticas finais...")
    agents, segments, seed_base, source_dirs = (
        _build_final_bases(
            runs,
            sensitivity_root=sensitivity_root,
            dirs=dirs,
            threshold=threshold,
            practical_delta=practical_delta,
        )
    )

    print("2/8 - Extraindo dimensão espacial...")
    consensus, spatial_summary = _spatial_consensus(
        segments,
        threshold=threshold,
        min_seeds=min_seeds,
        practical_delta=practical_delta,
        dirs=dirs,
    )

    print(
        "3/8 - Estimando incerteza sem independência de segmentos..."
    )
    bootstrap_distribution, bootstrap_summary = (
        _hierarchical_bootstrap(
            source_dirs=source_dirs,
            segments=segments,
            seed_base=seed_base,
            reps=args.bootstrap_reps,
            bootstrap_seed=args.bootstrap_seed,
            threshold=threshold,
            practical_delta=practical_delta,
            dirs=dirs,
        )
    )

    print("4/8 - Quantificando mecanismos...")
    mechanism_income, transitions = _behavioral_mechanisms(
        agents,
        dirs=dirs,
    )
    mode_decomposition = _mode_decomposition(
        runs,
        sensitivity_root=sensitivity_root,
        threshold=threshold,
        practical_delta=practical_delta,
        seed_base=seed_base,
        dirs=dirs,
    )

    print("5/8 - Consolidando sensibilidades...")
    sensitivity = _parameter_sensitivity(
        runs,
        sensitivity_root=sensitivity_root,
        threshold=threshold,
        practical_delta=practical_delta,
        seed_base=seed_base,
        dirs=dirs,
    )

    direct_result = _direct_article_result(
        bootstrap_summary=bootstrap_summary,
        seed_base=seed_base,
        dirs=dirs,
    )

    print("6/8 - Gerando tabelas do artigo...")
    _make_tables(
        bootstrap_summary=bootstrap_summary,
        seed_base=seed_base,
        mechanism_income=mechanism_income,
        mode_decomposition=mode_decomposition,
        sensitivity=sensitivity,
        spatial_summary=spatial_summary,
        dirs=dirs,
    )

    print("7/8 - Gerando conjunto final de figuras e mapas...")
    first_seed = sorted(source_dirs)[0]
    full_network = _read_comparison_geodata(
        source_dirs[first_seed]
    )[
        ["analysis_segment_id", "geometry"]
    ].copy()

    _make_figures(
        seed_base=seed_base,
        bootstrap_summary=bootstrap_summary,
        spatial_summary=spatial_summary,
        consensus=consensus,
        full_network=full_network,
        mechanism_income=mechanism_income,
        mode_decomposition=mode_decomposition,
        sensitivity=sensitivity,
        dirs=dirs,
        dpi=dpi,
        min_seeds=min_seeds,
    )

    print("8/8 - Gravando relatório e manifesto...")
    _write_report(
        article=article,
        seed_base=seed_base,
        bootstrap_summary=bootstrap_summary,
        spatial_summary=spatial_summary,
        mode_decomposition=mode_decomposition,
        sensitivity=sensitivity,
        dirs=dirs,
    )
    _write_manifest(
        dirs=dirs,
        article=article,
        runs=runs,
        bootstrap_reps=args.bootstrap_reps,
        bootstrap_seed=args.bootstrap_seed,
    )

    print("")
    print("Pacote v01 do artigo concluído em:")
    print(output_root.resolve())


if __name__ == "__main__":
    main()
