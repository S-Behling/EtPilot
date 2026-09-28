"""Bateria final de sensibilidade do piloto EtPilot.

A configuração operacional usa N=100 agentes por realização e múltiplas seeds.
A bateria executa:
1. cinco realizações nominais independentes;
2. sensibilidade do decaimento da escolha de destino (0,75 e 1,25);
3. sensibilidade da resposta modal à distância (0,75 e 1,25);
4. decomposição com probabilidades modais homogenizadas no cenário differentiated na seed de referência.

O objetivo é avaliar robustez sem tratar N=100 como tamanho populacional convergido.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pandas as pd

from src.analysis.population_sensitivity import (
    _extract_run_metrics,
    _is_complete_run,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"
LEGACY_N100_SEED42 = (
    PROJECT_ROOT
    / "outputs"
    / "pilot"
    / "population_sensitivity"
    / "n_0100_seed_42"
)

KEY_METRICS = (
    "analysis_retention_pct",
    "used_both_share_pct",
    "flow_ge_5_both",
    "flow_ge_10_both",
    "H_soc_mean_supported_baseline",
    "H_soc_mean_supported_differentiated",
    "sufficient_delta_H_soc_mean",
    "paired_delta_H_soc_mean",
)


def _load_defaults() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = json.load(file)

    return (
        config
        .get("analysis", {})
        .get("final_pilot_sensitivity", {})
    )


def _parse_args():
    defaults = _load_defaults()

    parser = argparse.ArgumentParser(
        description=(
            "Executa a bateria final de sensibilidade do piloto com "
            "N operacional fixo e múltiplas seeds."
        )
    )
    parser.add_argument(
        "--n-agents",
        type=int,
        default=int(defaults.get("n_agents", 100)),
    )
    parser.add_argument(
        "--seeds",
        nargs="+",
        type=int,
        default=defaults.get(
            "seeds",
            [11, 23, 42, 73, 101],
        ),
    )
    parser.add_argument(
        "--reference-seed",
        type=int,
        default=int(defaults.get("reference_seed", 42)),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=defaults.get(
            "output_dir",
            "outputs/pilot/final_sensitivity",
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Reutiliza execuções completas já existentes.",
    )
    parser.add_argument(
        "--no-legacy-reuse",
        action="store_true",
        help=(
            "Não reutiliza a execução histórica N=100, seed=42 "
            "como referência nominal."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=int(
            defaults.get(
                "max_parallel_workers",
                2,
            )
        ),
        help=(
            "Número máximo de execuções independentes em paralelo. "
            "Use 1 se a máquina tiver pouca memória."
        ),
    )
    parser.add_argument(
        "--experiments",
        nargs="+",
        choices=[
            "nominal_seed",
            "destination_decay",
            "mode_decay",
            "mode_homogenized",
        ],
        default=None,
        help=(
            "Executa apenas os tipos informados. Útil para produzir "
            "primeiro os resultados centrais do artigo."
        ),
    )

    return parser.parse_args()


def _validate_seeds(
    seeds: list[int],
    *,
    reference_seed: int,
) -> list[int]:
    normalized = list(
        dict.fromkeys(
            int(value)
            for value in seeds
        )
    )

    if not normalized:
        raise ValueError(
            "Informe ao menos uma seed."
        )

    if reference_seed not in normalized:
        raise ValueError(
            "A reference_seed precisa estar incluída na lista de seeds."
        )

    return normalized


def _build_sensitivity_plan(
    *,
    seeds: list[int],
    reference_seed: int,
    destination_multipliers: list[float],
    mode_multipliers: list[float],
    include_mode_homogenized: bool,
) -> pd.DataFrame:
    rows: list[dict] = []

    for seed in seeds:
        rows.append(
            {
                "run_id": f"nominal_seed_{seed}",
                "experiment": "nominal_seed",
                "seed": int(seed),
                "destination_decay_multiplier": 1.0,
                "mode_decay_multiplier": 1.0,
                "homogenize_differentiated_mode": False,
            }
        )

    for multiplier in destination_multipliers:
        multiplier = float(multiplier)

        if np.isclose(multiplier, 1.0):
            continue

        suffix = str(multiplier).replace(".", "p")
        rows.append(
            {
                "run_id": f"destination_decay_{suffix}",
                "experiment": "destination_decay",
                "seed": int(reference_seed),
                "destination_decay_multiplier": multiplier,
                "mode_decay_multiplier": 1.0,
                "homogenize_differentiated_mode": False,
            }
        )

    for multiplier in mode_multipliers:
        multiplier = float(multiplier)

        if np.isclose(multiplier, 1.0):
            continue

        suffix = str(multiplier).replace(".", "p")
        rows.append(
            {
                "run_id": f"mode_decay_{suffix}",
                "experiment": "mode_decay",
                "seed": int(reference_seed),
                "destination_decay_multiplier": 1.0,
                "mode_decay_multiplier": multiplier,
                "homogenize_differentiated_mode": False,
            }
        )

    if include_mode_homogenized:
        rows.append(
            {
                "run_id": (
                    f"mode_homogenized_seed_{reference_seed}"
                ),
                "experiment": "mode_homogenized",
                "seed": int(reference_seed),
                "destination_decay_multiplier": 1.0,
                "mode_decay_multiplier": 1.0,
                "homogenize_differentiated_mode": True,
            }
        )

    return pd.DataFrame(rows)


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _runtime_from_run(
    run_dir: Path,
) -> float:
    meta = (
        run_dir
        / "sensitivity_run_meta.json"
    )

    if not meta.exists():
        return np.nan

    with meta.open(
        "r",
        encoding="utf-8",
    ) as file:
        return float(
            json.load(file).get(
                "runtime_s",
                np.nan,
            )
        )


def _run_pilot(
    *,
    n_agents: int,
    row: pd.Series,
    run_dir: Path,
) -> float:
    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    log_path = (
        run_dir
        / "run.log"
    )

    command = [
        sys.executable,
        "-m",
        "src.simulation.run_pilot",
        "--n-agents",
        str(n_agents),
        "--seed",
        str(int(row["seed"])),
        "--output-dir",
        str(run_dir),
        "--destination-decay-multiplier",
        str(
            float(
                row[
                    "destination_decay_multiplier"
                ]
            )
        ),
        "--mode-decay-multiplier",
        str(
            float(
                row[
                    "mode_decay_multiplier"
                ]
            )
        ),
        "--skip-maps",
        "--skip-metadata",
    ]

    if bool(
        row[
            "homogenize_differentiated_mode"
        ]
    ):
        command.append(
            "--homogenize-differentiated-mode"
        )

    start = time.perf_counter()

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as log_file:
        result = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )

    runtime_s = (
        time.perf_counter()
        - start
    )

    if result.returncode != 0:
        raise RuntimeError(
            "A execução falhou para "
            f"{row['run_id']}. "
            f"Consulte {log_path}"
        )

    with (
        run_dir
        / "sensitivity_run_meta.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            {
                "n_agents": int(n_agents),
                "seed": int(row["seed"]),
                "runtime_s": float(runtime_s),
                "experiment": str(
                    row["experiment"]
                ),
                "destination_decay_multiplier": float(
                    row[
                        "destination_decay_multiplier"
                    ]
                ),
                "mode_decay_multiplier": float(
                    row[
                        "mode_decay_multiplier"
                    ]
                ),
                "homogenize_differentiated_mode": bool(
                    row[
                        "homogenize_differentiated_mode"
                    ]
                ),
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    return runtime_s


def _execute_plan_row(
    plan_row: dict,
    *,
    n_agents: int,
    root: Path,
    commit: str,
    resume: bool,
    no_legacy_reuse: bool,
    reuse_legacy_seed42: bool,
) -> dict:
    """Executa ou reutiliza uma realização independente e extrai suas métricas."""

    run_id = str(
        plan_row["run_id"]
    )
    seed = int(
        plan_row["seed"]
    )
    run_dir = (
        root
        / "runs"
        / run_id
    )

    use_legacy = (
        not no_legacy_reuse
        and reuse_legacy_seed42
        and plan_row[
            "experiment"
        ]
        == "nominal_seed"
        and seed == 42
        and int(n_agents) == 100
        and _is_complete_run(
            LEGACY_N100_SEED42,
            n_agents=100,
            seed=42,
        )
    )

    if use_legacy:
        source_dir = LEGACY_N100_SEED42
        runtime_s = _runtime_from_run(
            source_dir
        )
        source_status = (
            "legacy_n100_seed42_reused"
        )
        source_commit = (
            "legacy_population_sensitivity"
        )
    elif (
        resume
        and _is_complete_run(
            run_dir,
            n_agents=n_agents,
            seed=seed,
        )
    ):
        source_dir = run_dir
        runtime_s = _runtime_from_run(
            source_dir
        )
        source_status = (
            "existing_run_reused"
        )
        source_commit = commit
    else:
        runtime_s = _run_pilot(
            n_agents=n_agents,
            row=pd.Series(
                plan_row
            ),
            run_dir=run_dir,
        )
        source_dir = run_dir
        source_status = (
            "executed"
        )
        source_commit = commit

    metrics = _extract_run_metrics(
        source_dir,
        n_agents=n_agents,
        seed=seed,
        runtime_s=runtime_s,
        commit=source_commit,
    )

    metrics.update(
        {
            "run_id": run_id,
            "experiment": plan_row[
                "experiment"
            ],
            "destination_decay_multiplier": float(
                plan_row[
                    "destination_decay_multiplier"
                ]
            ),
            "mode_decay_multiplier": float(
                plan_row[
                    "mode_decay_multiplier"
                ]
            ),
            "homogenize_differentiated_mode": bool(
                plan_row[
                    "homogenize_differentiated_mode"
                ]
            ),
            "source_status": source_status,
            "source_dir": str(
                source_dir
            ),
        }
    )

    return metrics


def _ordered_runs(
    rows: list[dict],
    *,
    plan: pd.DataFrame,
) -> pd.DataFrame:
    """Ordena o checkpoint conforme o plano, mesmo com execução paralela."""

    if not rows:
        return pd.DataFrame()

    runs = pd.DataFrame(
        rows
    )
    order = {
        run_id: index
        for index, run_id
        in enumerate(
            plan["run_id"].astype(str)
        )
    }
    runs["_plan_order"] = (
        runs["run_id"]
        .astype(str)
        .map(order)
    )
    runs = (
        runs.sort_values(
            "_plan_order"
        )
        .drop(
            columns="_plan_order"
        )
        .reset_index(
            drop=True
        )
    )

    ordered_front = [
        "run_id",
        "experiment",
        "seed",
        "n_agents_requested",
        "destination_decay_multiplier",
        "mode_decay_multiplier",
        "homogenize_differentiated_mode",
        "source_status",
        "source_dir",
    ]

    return runs[
        ordered_front
        + [
            column
            for column in runs.columns
            if column
            not in ordered_front
        ]
    ]


def _write_checkpoint(
    root: Path,
    *,
    rows: list[dict],
    plan: pd.DataFrame,
) -> None:
    """Salva resultados disponíveis imediatamente após cada realização."""

    runs = _ordered_runs(
        rows,
        plan=plan,
    )
    if runs.empty:
        return

    runs.to_csv(
        root
        / "final_sensitivity_runs_partial.csv",
        index=False,
        encoding="utf-8",
    )

    progress = {
        "completed": int(
            len(runs)
        ),
        "planned": int(
            len(plan)
        ),
        "remaining": int(
            len(plan)
            - len(runs)
        ),
        "completed_run_ids": runs[
            "run_id"
        ].astype(str).tolist(),
    }

    with (
        root
        / "progress.json"
    ).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            progress,
            file,
            ensure_ascii=False,
            indent=2,
        )


def _nominal_seed_stability(
    runs: pd.DataFrame,
) -> pd.DataFrame:
    nominal = runs.loc[
        runs["experiment"]
        == "nominal_seed"
    ]

    rows: list[dict] = []

    for metric in KEY_METRICS:
        values = pd.to_numeric(
            nominal[metric],
            errors="coerce",
        ).dropna()

        if values.empty:
            continue

        median = float(
            values.median()
        )

        row = {
            "metric": metric,
            "n_valid_seeds": int(
                len(values)
            ),
            "mean": float(
                values.mean()
            ),
            "median": median,
            "q1": float(
                values.quantile(0.25)
            ),
            "q3": float(
                values.quantile(0.75)
            ),
            "iqr": float(
                values.quantile(0.75)
                - values.quantile(0.25)
            ),
            "min": float(
                values.min()
            ),
            "max": float(
                values.max()
            ),
        }

        if (
            "delta_H_soc" in metric
            and not np.isclose(
                median,
                0.0,
            )
        ):
            median_sign = np.sign(
                median
            )
            row[
                "same_sign_as_median_share"
            ] = float(
                (
                    np.sign(values)
                    == median_sign
                ).mean()
            )
        else:
            row[
                "same_sign_as_median_share"
            ] = np.nan

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )


def _parameter_comparison(
    runs: pd.DataFrame,
    *,
    reference_seed: int,
) -> pd.DataFrame:
    """Compara perturbações com a referência nominal apropriada.

    Perturbações locais de parâmetros usam a seed de referência configurada.
    A decomposição mode_homogenized usa a execução nominal da mesma seed,
    preservando a comparação pareada entre realizações.
    """

    nominal = runs.loc[
        runs["experiment"]
        == "nominal_seed"
    ].copy()

    reference_rows = nominal.loc[
        nominal["seed"]
        == reference_seed
    ]

    if len(reference_rows) != 1:
        raise ValueError(
            "A execução nominal da reference_seed "
            "precisa existir exatamente uma vez."
        )

    sensitivity = runs.loc[
        runs["experiment"]
        != "nominal_seed"
    ].copy()

    rows: list[dict] = []

    for _, current in sensitivity.iterrows():
        if (
            current["experiment"]
            == "mode_homogenized"
        ):
            current_reference = nominal.loc[
                nominal["seed"]
                == int(
                    current["seed"]
                )
            ]

            if len(current_reference) != 1:
                raise ValueError(
                    "Cada execução mode_homogenized precisa de uma "
                    "execução nominal com a mesma seed."
                )

            reference = current_reference.iloc[
                0
            ]
            reference_kind = (
                "same_seed_nominal"
            )
        else:
            reference = reference_rows.iloc[
                0
            ]
            reference_kind = (
                "configured_reference_seed"
            )

        row = {
            "run_id": current["run_id"],
            "experiment": current[
                "experiment"
            ],
            "seed": int(
                current["seed"]
            ),
            "reference_seed": int(
                reference["seed"]
            ),
            "reference_kind": reference_kind,
            "destination_decay_multiplier": float(
                current[
                    "destination_decay_multiplier"
                ]
            ),
            "mode_decay_multiplier": float(
                current[
                    "mode_decay_multiplier"
                ]
            ),
            "homogenize_differentiated_mode": bool(
                current[
                    "homogenize_differentiated_mode"
                ]
            ),
        }

        for metric in KEY_METRICS:
            current_value = current.get(
                metric,
                np.nan,
            )
            reference_value = reference.get(
                metric,
                np.nan,
            )

            row[
                f"value_{metric}"
            ] = current_value
            row[
                f"reference_{metric}"
            ] = reference_value

            if (
                pd.notna(current_value)
                and pd.notna(reference_value)
            ):
                row[
                    f"change_{metric}"
                ] = (
                    float(current_value)
                    - float(reference_value)
                )
            else:
                row[
                    f"change_{metric}"
                ] = np.nan

        for metric in (
            "sufficient_delta_H_soc_mean",
            "paired_delta_H_soc_mean",
        ):
            current_value = current.get(
                metric,
                np.nan,
            )
            reference_value = reference.get(
                metric,
                np.nan,
            )

            if (
                pd.notna(current_value)
                and pd.notna(reference_value)
                and not np.isclose(
                    reference_value,
                    0.0,
                )
            ):
                row[
                    f"same_sign_{metric}"
                ] = bool(
                    np.sign(current_value)
                    == np.sign(reference_value)
                )
            else:
                row[
                    f"same_sign_{metric}"
                ] = np.nan

        rows.append(
            row
        )

    return pd.DataFrame(
        rows
    )


def _write_report(
    root: Path,
    *,
    n_agents: int,
    seeds: list[int],
    reference_seed: int,
    plan: pd.DataFrame,
    runs: pd.DataFrame,
    seed_stability: pd.DataFrame,
    parameter_comparison: pd.DataFrame,
) -> None:
    lines = [
        "# Bateria final de sensibilidade do piloto",
        "",
        "## Configuração operacional",
        "",
        f"- Agentes por realização: {n_agents}",
        (
            "- Seeds nominais: "
            + ", ".join(
                str(seed)
                for seed in seeds
            )
        ),
        f"- Seed de referência para perturbações: {reference_seed}",
        "- Limiar principal de suporte: n_agents >= 5",
        "- Limiar >= 10 é diagnóstico e não requisito para N=100",
        "",
        "N=100 é uma escolha operacional do piloto por custo computacional, não uma evidência de convergência populacional.",
        "",
        "## Bateria",
        "",
        f"- Execuções planejadas: {len(plan)}",
        f"- Execuções consolidadas: {len(runs)}",
        "- Sensibilidade de destino: multiplicadores 0,75 e 1,25",
        "- Sensibilidade modal à distância: multiplicadores 0,75 e 1,25",
        "- Decomposição: modo homogenizado no cenário differentiated",
        "",
        "## Produtos",
        "",
        "- final_sensitivity_plan.csv",
        "- final_sensitivity_runs.csv",
        "- final_sensitivity_seed_stability.csv",
        "- final_sensitivity_parameter_comparison.csv",
        "",
        "A configuração comportamental só deve ser marcada como final após a inspeção dos resultados entre seeds e das perturbações locais.",
        "",
    ]

    (
        root
        / "final_sensitivity_report.md"
    ).write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    args = _parse_args()
    defaults = _load_defaults()

    if args.n_agents <= 0:
        raise ValueError(
            "--n-agents precisa ser maior que zero."
        )

    seeds = _validate_seeds(
        args.seeds,
        reference_seed=args.reference_seed,
    )

    destination_multipliers = [
        float(value)
        for value in defaults.get(
            "destination_decay_multipliers",
            [0.75, 1.0, 1.25],
        )
    ]
    mode_multipliers = [
        float(value)
        for value in defaults.get(
            "mode_decay_multipliers",
            [0.75, 1.0, 1.25],
        )
    ]
    include_mode_homogenized = bool(
        defaults.get(
            "include_mode_homogenized_decomposition",
            True,
        )
    )

    plan = _build_sensitivity_plan(
        seeds=seeds,
        reference_seed=args.reference_seed,
        destination_multipliers=destination_multipliers,
        mode_multipliers=mode_multipliers,
        include_mode_homogenized=include_mode_homogenized,
    )

    if args.experiments:
        plan = (
            plan.loc[
                plan["experiment"].isin(
                    args.experiments
                )
            ]
            .reset_index(
                drop=True
            )
        )

    if plan.empty:
        raise ValueError(
            "O filtro de experimentos não deixou nenhuma execução no plano."
        )

    if args.workers < 1:
        raise ValueError(
            "--workers precisa ser maior ou igual a 1."
        )

    root = Path(
        args.output_dir
    )

    if not root.is_absolute():
        root = (
            PROJECT_ROOT
            / root
        )

    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    runs_root = (
        root
        / "runs"
    )
    runs_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    plan.to_csv(
        root
        / "final_sensitivity_plan.csv",
        index=False,
        encoding="utf-8",
    )

    commit = _git_commit()
    rows: list[dict] = []

    print(
        f"Execuções planejadas: {len(plan)} | "
        f"workers={args.workers}"
    )

    plan_rows = [
        row._asdict()
        for row in plan.itertuples(
            index=False
        )
    ]

    with ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:
        futures = {
            executor.submit(
                _execute_plan_row,
                plan_row,
                n_agents=args.n_agents,
                root=root,
                commit=commit,
                resume=args.resume,
                no_legacy_reuse=args.no_legacy_reuse,
                reuse_legacy_seed42=bool(
                    defaults.get(
                        "reuse_legacy_seed42",
                        True,
                    )
                ),
            ): plan_row
            for plan_row in plan_rows
        }

        for future in as_completed(
            futures
        ):
            plan_row = futures[
                future
            ]
            metrics = future.result()
            rows.append(
                metrics
            )

            _write_checkpoint(
                root,
                rows=rows,
                plan=plan,
            )

            print(
                f"[{len(rows)}/{len(plan)}] "
                f"{plan_row['run_id']}: "
                f"flow>=5 pareado="
                f"{int(metrics['flow_ge_5_both'])} | "
                "delta H_soc suportado="
                f"{metrics['sufficient_delta_H_soc_mean']}"
            )

    runs = _ordered_runs(
        rows,
        plan=plan,
    )

    seed_stability = _nominal_seed_stability(
        runs
    )

    has_reference_nominal = (
        (
            runs["experiment"]
            == "nominal_seed"
        )
        & (
            runs["seed"]
            == args.reference_seed
        )
    ).any()

    if has_reference_nominal:
        parameter_comparison = _parameter_comparison(
            runs,
            reference_seed=args.reference_seed,
        )
    else:
        parameter_comparison = pd.DataFrame()

    runs.to_csv(
        root
        / "final_sensitivity_runs.csv",
        index=False,
        encoding="utf-8",
    )
    seed_stability.to_csv(
        root
        / "final_sensitivity_seed_stability.csv",
        index=False,
        encoding="utf-8",
    )
    parameter_comparison.to_csv(
        root
        / "final_sensitivity_parameter_comparison.csv",
        index=False,
        encoding="utf-8",
    )

    _write_report(
        root,
        n_agents=args.n_agents,
        seeds=seeds,
        reference_seed=args.reference_seed,
        plan=plan,
        runs=runs,
        seed_stability=seed_stability,
        parameter_comparison=parameter_comparison,
    )

    print("")
    print(
        "Bateria final consolidada em:"
    )
    print(
        root.resolve()
    )


if __name__ == "__main__":
    main()
