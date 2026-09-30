"""Executa o fluxo completo e configurável do EtPilot.

Este é o ponto de entrada recomendado para o piloto.

Exemplos:
    python scripts/run_pipeline.py
    python scripts/run_pipeline.py --region city --income low middle
    python scripts/run_pipeline.py --period-value 3 --period-unit days
    python scripts/run_pipeline.py --region south --income low high --n-agents 500

A configuração foi separada da interface para permitir, futuramente, uma
janela gráfica que preencha PilotRunConfig sem alterar o pipeline.
"""

from __future__ import annotations

import argparse

from _bootstrap import add_project_root_to_path

add_project_root_to_path()

from prepare_city_networks import prepare_city_networks
from prepare_region import prepare_region

from scripts.clear_outputs import clear_output_files
from src.core.config import load_project_config
from src.domain.enums import IncomeGroup
from src.pipeline.config import (
    PilotRunConfig,
    SimulationPeriod,
)
from src.simulation.run_pilot import run_pilot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa todo o pipeline configurável do EtPilot."
    )

    parser.add_argument(
        "--region",
        default=None,
        choices=("city", "center", "north", "south", "east"),
        help=(
            "Região da análise. As regiões precisam estar habilitadas "
            "em config/regions.json."
        ),
    )
    parser.add_argument(
        "--income",
        nargs="+",
        default=["low", "middle", "high"],
        choices=("low", "middle", "high"),
        help=(
            "Classes sociais incluídas. Pode informar uma, duas ou três."
        ),
    )
    parser.add_argument(
        "--period-value",
        type=int,
        default=24,
        help="Tamanho da janela temporal.",
    )
    parser.add_argument(
        "--period-unit",
        choices=("hours", "days"),
        default="hours",
        help="Unidade da janela temporal.",
    )
    parser.add_argument(
        "--n-agents",
        type=int,
        default=100,
        help="Número total de agentes sintéticos.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semente de reprodutibilidade.",
    )
    parser.add_argument(
        "--scenario",
        choices=("baseline", "differentiated"),
        default="differentiated",
        help="Cenário de escolha modal.",
    )
    parser.add_argument(
        "--clear-outputs",
        action="store_true",
        help="Limpa outputs antes da execução.",
    )
    parser.add_argument(
        "--skip-network-preparation",
        action="store_true",
        help="Não verifica/baixa as redes OSM da cidade.",
    )
    parser.add_argument(
        "--skip-region-preparation",
        action="store_true",
        help="Reutiliza o cache regional existente.",
    )
    parser.add_argument(
        "--force-network-download",
        action="store_true",
        help="Força novo download das redes OSM.",
    )

    return parser.parse_args()


def build_run_config(
    args: argparse.Namespace,
) -> PilotRunConfig:
    """Converte os argumentos da interface em configuração de domínio."""

    project_config = load_project_config()

    region = (
        args.region
        or project_config["study_area"]["default_region"]
    )

    income_groups = tuple(
        IncomeGroup(value)
        for value in dict.fromkeys(args.income)
    )

    return PilotRunConfig(
        region=region,
        income_groups=income_groups,
        period=SimulationPeriod(
            value=args.period_value,
            unit=args.period_unit,
        ),
        n_agents=args.n_agents,
        seed=args.seed,
        scenario=args.scenario,
        prepare_networks=not args.skip_network_preparation,
        prepare_region=not args.skip_region_preparation,
        clear_outputs=args.clear_outputs,
        force_network_download=args.force_network_download,
    )


def print_configuration(
    run_config: PilotRunConfig,
) -> None:
    """Mostra de forma compacta a configuração antes da execução."""

    print("\n" + "=" * 70)
    print("ETPILOT — CONFIGURAÇÃO DA EXECUÇÃO")
    print("=" * 70)
    print(f"Região: {run_config.region}")
    print(
        "Classes sociais:",
        ", ".join(run_config.income_group_names),
    )
    print(
        "Período:",
        f"{run_config.period.value} {run_config.period.unit}",
        f"({run_config.period.total_hours} h)",
    )
    print(f"Agentes: {run_config.n_agents}")
    print(f"Seed: {run_config.seed}")
    print(f"Cenário: {run_config.scenario}")
    print(
        "Preparar redes:",
        "sim" if run_config.prepare_networks else "não",
    )
    print(
        "Preparar região:",
        "sim" if run_config.prepare_region else "não",
    )
    print("=" * 70 + "\n")


def run_pipeline(
    run_config: PilotRunConfig,
) -> None:
    """Executa todas as etapas do fluxo na ordem correta."""

    print_configuration(run_config)

    if run_config.clear_outputs:
        print("[1] Limpando outputs...")
        removed = clear_output_files()
        print(f"[ok] {removed} arquivo(s) removido(s).")
    else:
        print("[1] Limpeza de outputs ignorada.")

    if run_config.prepare_networks:
        print("\n[2] Preparando redes OSM multimodais...")
        prepare_city_networks(
            force=run_config.force_network_download,
        )
    else:
        print("\n[2] Preparação das redes ignorada.")

    if run_config.prepare_region:
        print("\n[3] Preparando recorte regional...")
        prepare_region(
            region_name=run_config.region,
        )
    else:
        print("\n[3] Preparação regional ignorada; usando cache existente.")

    print("\n[4] Executando simulação e roteamento...")
    run_pilot(run_config)

    print("\n" + "=" * 70)
    print("PIPELINE CONCLUÍDO")
    print("=" * 70)


def main() -> None:
    args = parse_args()
    run_config = build_run_config(args)
    run_pipeline(run_config)


if __name__ == "__main__":
    main()
