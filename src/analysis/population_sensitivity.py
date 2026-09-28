"""Executa e resume a sensibilidade do piloto ao tamanho da população

Mantém a mesma semente e os mesmos parâmetros entre tamanhos de população
Executa cada N em diretório próprio sem sobrescrever os resultados do piloto
Extrai cobertura, suporte de fluxo, H_soc, delta_H_soc, outliers e tempo
Avalia um critério provisório de estabilidade entre tamanhos consecutivos
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(
    __file__
).resolve().parents[
    2
]

DEFAULT_SIZES = (
    100,
    250,
    500,
    1000,
)
DEFAULT_SEED = 42
DEFAULT_STABILITY_TOLERANCE = 0.05
DEFAULT_MIN_PAIRED_GE_10 = 1


def _parse_args():
    """Lê parâmetros da análise de sensibilidade populacional"""

    parser = argparse.ArgumentParser(
        description=(
            "Executa o piloto para diferentes tamanhos de população "
            "e resume a estabilidade dos indicadores"
        )
    )
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=list(
            DEFAULT_SIZES
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SEED,
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=(
            "outputs/pilot/population_sensitivity"
        ),
    )
    parser.add_argument(
        "--stability-tolerance",
        type=float,
        default=DEFAULT_STABILITY_TOLERANCE,
    )
    parser.add_argument(
        "--min-paired-ge10",
        type=int,
        default=DEFAULT_MIN_PAIRED_GE_10,
    )
    parser.add_argument(
        "--resume",
        action="store_true",
    )

    return parser.parse_args()


def _validate_sizes(
    sizes: list[int],
) -> list[int]:
    """Normaliza os tamanhos de população em ordem crescente"""

    normalized = sorted(
        {
            int(
                value
            )
            for value in sizes
        }
    )

    if not normalized:
        raise ValueError(
            "Informe ao menos um tamanho de população"
        )

    if any(
        value <= 0
        for value in normalized
    ):
        raise ValueError(
            "Todos os tamanhos de população precisam ser maiores que zero"
        )

    return normalized


def _git_commit() -> str:
    """Retorna o commit atual para rastreabilidade da sensibilidade"""

    result = subprocess.run(
        [
            "git",
            "rev-parse",
            "HEAD",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def _run_directory(
    root: Path,
    *,
    n_agents: int,
    seed: int,
) -> Path:
    """Monta o diretório isolado de uma execução"""

    return (
        root
        / f"n_{n_agents:04d}_seed_{seed}"
    )


def _is_complete_run(
    run_dir: Path,
    *,
    n_agents: int,
    seed: int,
) -> bool:
    """Verifica se uma execução anterior possui os produtos mínimos"""

    required = [
        run_dir
        / "run_manifest.json",
        run_dir
        / "agents_baseline.csv",
        run_dir
        / "agents_differentiated.csv",
        run_dir
        / "segment_statistics_baseline.csv",
        run_dir
        / "segment_statistics_differentiated.csv",
        run_dir
        / "segment_scenario_comparison_summary.csv",
        run_dir
        / "outlier_filter_summary.csv",
    ]

    if not all(
        path.exists()
        for path in required
    ):
        return False

    with (
        run_dir
        / "run_manifest.json"
    ).open(
        "r",
        encoding="utf-8",
    ) as file:
        manifest = json.load(
            file
        )

    return (
        int(
            manifest.get(
                "n_agents",
                -1,
            )
        )
        == n_agents
        and int(
            manifest.get(
                "seed",
                -1,
            )
        )
        == seed
    )


def _run_pilot(
    *,
    n_agents: int,
    seed: int,
    run_dir: Path,
) -> float:
    """Executa o piloto em subprocesso e grava o console em arquivo"""

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
        str(
            n_agents
        ),
        "--seed",
        str(
            seed
        ),
        "--output-dir",
        str(
            run_dir
        ),
        "--skip-maps",
        "--skip-metadata",
    ]

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

    elapsed_s = (
        time.perf_counter()
        - start
    )

    if result.returncode != 0:
        raise RuntimeError(
            "A execução da sensibilidade falhou para "
            f"N={n_agents} e seed={seed}. "
            f"Consulte {log_path}"
        )

    return elapsed_s


def _scenario_metrics(
    run_dir: Path,
    scenario_name: str,
) -> dict:
    """Extrai métricas de agentes e segmentos de um cenário"""

    agents = pd.read_csv(
        run_dir
        / f"agents_{scenario_name}.csv"
    )
    statistics = pd.read_csv(
        run_dir
        / f"segment_statistics_{scenario_name}.csv"
    )

    included = (
        agents[
            "analysis_included"
        ].astype(
            bool
        )
        if "analysis_included"
        in agents.columns
        else pd.Series(
            True,
            index=agents.index,
        )
    )

    sufficient = statistics.loc[
        statistics[
            "sufficient_flow"
        ].astype(
            bool
        )
    ]

    result = {
        f"analysis_agents_{scenario_name}": int(
            included.sum()
        ),
        f"segments_used_{scenario_name}": int(
            len(
                statistics
            )
        ),
        f"H_soc_mean_all_{scenario_name}": float(
            statistics[
                "H_soc"
            ].mean()
        ),
        f"H_soc_median_all_{scenario_name}": float(
            statistics[
                "H_soc"
            ].median()
        ),
        f"H_soc_mean_supported_{scenario_name}": (
            float(
                sufficient[
                    "H_soc"
                ].mean()
            )
            if not sufficient.empty
            else np.nan
        ),
        f"H_soc_median_supported_{scenario_name}": (
            float(
                sufficient[
                    "H_soc"
                ].median()
            )
            if not sufficient.empty
            else np.nan
        ),
    }

    for threshold in (
        2,
        3,
        5,
        10,
    ):
        column = (
            f"flow_ge_{threshold}"
        )

        result[
            f"flow_ge_{threshold}_{scenario_name}"
        ] = (
            int(
                statistics[
                    column
                ]
                .astype(
                    bool
                )
                .sum()
            )
            if column in statistics.columns
            else 0
        )

    return result


def _extract_run_metrics(
    run_dir: Path,
    *,
    n_agents: int,
    seed: int,
    runtime_s: float,
    commit: str,
) -> dict:
    """Consolida as métricas principais produzidas por uma execução"""

    row = {
        "n_agents_requested": int(
            n_agents
        ),
        "seed": int(
            seed
        ),
        "runtime_s": float(
            runtime_s
        ),
        "git_commit": commit,
    }

    for scenario_name in (
        "baseline",
        "differentiated",
    ):
        row.update(
            _scenario_metrics(
                run_dir,
                scenario_name,
            )
        )

    paired = pd.read_csv(
        run_dir
        / "segment_scenario_comparison_summary.csv"
    ).iloc[
        0
    ]
    outliers = pd.read_csv(
        run_dir
        / "outlier_filter_summary.csv"
    ).iloc[
        0
    ]

    paired_fields = [
        "segments_union",
        "used_both",
        "baseline_only",
        "differentiated_only",
        "paired_delta_H_soc_mean",
        "paired_delta_H_soc_median",
        "sufficient_flow_both",
        "sufficient_delta_H_soc_mean",
        "sufficient_delta_H_soc_median",
        "flow_ge_2_both",
        "flow_ge_3_both",
        "flow_ge_5_both",
        "flow_ge_10_both",
        "delta_H_soc_mean_ge_2_both",
        "delta_H_soc_mean_ge_3_both",
        "delta_H_soc_mean_ge_5_both",
        "delta_H_soc_mean_ge_10_both",
    ]

    for field in paired_fields:
        row[
            field
        ] = paired.get(
            field,
            np.nan,
        )

    row[
        "direct_outlier_routes"
    ] = int(
        outliers.get(
            "direct_outlier_routes",
            0,
        )
    )
    row[
        "unique_excluded_agents"
    ] = int(
        outliers.get(
            "unique_excluded_agents",
            0,
        )
    )

    row[
        "analysis_retention_pct"
    ] = (
        100.0
        * min(
            row[
                "analysis_agents_baseline"
            ],
            row[
                "analysis_agents_differentiated"
            ],
        )
        / float(
            n_agents
        )
    )

    row[
        "used_both_share_pct"
    ] = (
        100.0
        * float(
            row[
                "used_both"
            ]
        )
        / max(
            float(
                row[
                    "segments_union"
                ]
            ),
            1.0,
        )
    )

    row[
        "flow_ge_5_both_share_pct"
    ] = (
        100.0
        * float(
            row[
                "flow_ge_5_both"
            ]
        )
        / max(
            float(
                row[
                    "used_both"
                ]
            ),
            1.0,
        )
    )

    row[
        "flow_ge_10_both_share_pct"
    ] = (
        100.0
        * float(
            row[
                "flow_ge_10_both"
            ]
        )
        / max(
            float(
                row[
                    "used_both"
                ]
            ),
            1.0,
        )
    )

    return row


def _stability_table(
    summary: pd.DataFrame,
    *,
    tolerance: float,
    min_paired_ge10: int,
) -> pd.DataFrame:
    """Compara cada tamanho com o tamanho imediatamente superior"""

    ordered = summary.sort_values(
        "n_agents_requested"
    ).reset_index(
        drop=True
    )

    rows = []

    metric_columns = [
        "H_soc_mean_supported_baseline",
        "H_soc_mean_supported_differentiated",
        "sufficient_delta_H_soc_mean",
        "paired_delta_H_soc_mean",
    ]

    for index in range(
        len(
            ordered
        )
        - 1
    ):
        current = ordered.iloc[
            index
        ]
        next_row = ordered.iloc[
            index
            + 1
        ]

        changes = {}

        for column in metric_columns:
            current_value = current[
                column
            ]
            next_value = next_row[
                column
            ]

            changes[
                f"abs_change_{column}"
            ] = (
                abs(
                    float(
                        next_value
                    )
                    - float(
                        current_value
                    )
                )
                if pd.notna(
                    current_value
                )
                and pd.notna(
                    next_value
                )
                else np.nan
            )

        finite_changes = [
            value
            for value in changes.values()
            if pd.notna(
                value
            )
        ]

        max_change = (
            max(
                finite_changes
            )
            if finite_changes
            else np.nan
        )

        paired_ge10 = int(
            current.get(
                "flow_ge_10_both",
                0,
            )
        )

        stable_vs_next = (
            pd.notna(
                max_change
            )
            and max_change
            <= tolerance
            and paired_ge10
            >= min_paired_ge10
        )

        rows.append(
            {
                "n_agents": int(
                    current[
                        "n_agents_requested"
                    ]
                ),
                "next_n_agents": int(
                    next_row[
                        "n_agents_requested"
                    ]
                ),
                **changes,
                "max_abs_change_key_metrics": max_change,
                "flow_ge_10_both": paired_ge10,
                "stability_tolerance": float(
                    tolerance
                ),
                "minimum_paired_ge10": int(
                    min_paired_ge10
                ),
                "stable_vs_next": bool(
                    stable_vs_next
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


def _selection_table(
    summary: pd.DataFrame,
    stability: pd.DataFrame,
) -> pd.DataFrame:
    """Seleciona provisoriamente o menor N estável ou mantém o maior como referência"""

    stable_rows = (
        stability.loc[
            stability[
                "stable_vs_next"
            ]
        ]
        if not stability.empty
        else pd.DataFrame()
    )

    if not stable_rows.empty:
        selected_n = int(
            stable_rows.iloc[
                0
            ][
                "n_agents"
            ]
        )
        status = (
            "smallest_n_stable_vs_next"
        )
    else:
        selected_n = int(
            summary[
                "n_agents_requested"
            ].max()
        )
        status = (
            "no_plateau_within_tested_range"
        )

    selected = summary.loc[
        summary[
            "n_agents_requested"
        ]
        == selected_n
    ].iloc[
        0
    ]

    return pd.DataFrame(
        [
            {
                "candidate_operational_n": selected_n,
                "selection_status": status,
                "seed": int(
                    selected[
                        "seed"
                    ]
                ),
                "flow_ge_5_both": int(
                    selected[
                        "flow_ge_5_both"
                    ]
                ),
                "flow_ge_10_both": int(
                    selected[
                        "flow_ge_10_both"
                    ]
                ),
                "H_soc_mean_supported_baseline": selected[
                    "H_soc_mean_supported_baseline"
                ],
                "H_soc_mean_supported_differentiated": selected[
                    "H_soc_mean_supported_differentiated"
                ],
                "sufficient_delta_H_soc_mean": selected[
                    "sufficient_delta_H_soc_mean"
                ],
                "paired_delta_H_soc_mean": selected[
                    "paired_delta_H_soc_mean"
                ],
                "note_pt": (
                    "Seleção técnica provisória baseada em uma única seed "
                    "A escolha final permanece condicionada à inspeção da "
                    "curva de sensibilidade e à etapa posterior de múltiplas seeds"
                ),
            }
        ]
    )


def _write_report(
    root: Path,
    *,
    summary: pd.DataFrame,
    stability: pd.DataFrame,
    selection: pd.DataFrame,
) -> None:
    """Escreve um resumo legível da sensibilidade populacional"""

    selected = selection.iloc[
        0
    ]

    lines = [
        "# Sensibilidade ao tamanho da população",
        "",
        "## Configuração",
        "",
        f"- Seed fixa: {int(summary['seed'].iloc[0])}",
        (
            "- Tamanhos avaliados: "
            + ", ".join(
                str(
                    int(
                        value
                    )
                )
                for value in summary[
                    "n_agents_requested"
                ]
            )
        ),
        "",
        "## Candidato técnico provisório",
        "",
        (
            f"N = {int(selected['candidate_operational_n'])} "
            f"({selected['selection_status']})"
        ),
        "",
        (
            "A indicação é provisória e precisa ser interpretada junto com "
            "a tabela de estabilidade e posteriormente confirmada com múltiplas seeds"
        ),
        "",
        "## Arquivos",
        "",
        "- population_sensitivity_summary.csv",
        "- population_sensitivity_stability.csv",
        "- population_sensitivity_selection.csv",
        "",
    ]

    (
        root
        / "population_sensitivity_report.md"
    ).write_text(
        "\n".join(
            lines
        ),
        encoding="utf-8",
    )


def main() -> None:
    """Executa a sensibilidade populacional e consolida os resultados"""

    args = _parse_args()

    sizes = _validate_sizes(
        args.sizes
    )

    if args.stability_tolerance < 0:
        raise ValueError(
            "--stability-tolerance precisa ser maior ou igual a zero"
        )

    if args.min_paired_ge10 < 0:
        raise ValueError(
            "--min-paired-ge10 precisa ser maior ou igual a zero"
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

    commit = _git_commit()

    print(
        "Sensibilidade ao tamanho da população"
    )
    print(
        "  Tamanhos: "
        + ", ".join(
            str(
                value
            )
            for value in sizes
        )
    )
    print(
        f"  Seed fixa: {args.seed}"
    )
    print(
        f"  Commit: {commit}"
    )

    rows = []

    for n_agents in sizes:
        run_dir = _run_directory(
            root,
            n_agents=n_agents,
            seed=args.seed,
        )

        if (
            args.resume
            and _is_complete_run(
                run_dir,
                n_agents=n_agents,
                seed=args.seed,
            )
        ):
            runtime_s = np.nan
            print(
                f"  N={n_agents}: reutiliza execução existente"
            )
        else:
            print(
                f"  N={n_agents}: executa piloto"
            )
            runtime_s = _run_pilot(
                n_agents=n_agents,
                seed=args.seed,
                run_dir=run_dir,
            )

        row = _extract_run_metrics(
            run_dir,
            n_agents=n_agents,
            seed=args.seed,
            runtime_s=runtime_s,
            commit=commit,
        )
        rows.append(
            row
        )

        print(
            f"    agentes analíticos: "
            f"{row['analysis_agents_baseline']} por cenário | "
            f"segmentos pareados >=5: {int(row['flow_ge_5_both'])} | "
            f">=10: {int(row['flow_ge_10_both'])}"
        )

    summary = (
        pd.DataFrame(
            rows
        )
        .sort_values(
            "n_agents_requested"
        )
        .reset_index(
            drop=True
        )
    )

    stability = _stability_table(
        summary,
        tolerance=float(
            args.stability_tolerance
        ),
        min_paired_ge10=int(
            args.min_paired_ge10
        ),
    )

    selection = _selection_table(
        summary,
        stability,
    )

    summary.to_csv(
        root
        / "population_sensitivity_summary.csv",
        index=False,
        encoding="utf-8",
    )
    stability.to_csv(
        root
        / "population_sensitivity_stability.csv",
        index=False,
        encoding="utf-8",
    )
    selection.to_csv(
        root
        / "population_sensitivity_selection.csv",
        index=False,
        encoding="utf-8",
    )

    _write_report(
        root,
        summary=summary,
        stability=stability,
        selection=selection,
    )

    selected = selection.iloc[
        0
    ]

    print(
        ""
    )
    print(
        "Resumo salvo em:"
    )
    print(
        f"  {root.resolve()}"
    )
    print(
        "Candidato técnico provisório a N operacional: "
        f"{int(selected['candidate_operational_n'])}"
    )
    print(
        "A escolha final permanece condicionada à inspeção dos resultados "
        "e à validação posterior com múltiplas seeds"
    )


if __name__ == "__main__":
    main()
