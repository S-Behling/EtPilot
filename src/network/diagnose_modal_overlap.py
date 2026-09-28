"""Diagnóstico de equivalência entre as redes modais do EtPilot.

Este módulo NÃO cria ainda o analysis_segment_id definitivo. Ele mede quanto
das redes de carro, bicicleta e caminhada pode ser reconciliado diretamente
por identificadores OSM antes de escolhermos a estratégia de harmonização.

Uso
---
    python -m src.network.diagnose_modal_overlap
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import osmnx as ox
import pandas as pd

from src.network.multimodal import load_mode_graphs


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def load_config() -> dict:
    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def _normalize_osmid(value) -> str:
    """Normaliza osmid escalar/lista para comparação entre grafos."""

    if isinstance(value, (list, tuple, set)):
        values = sorted(
            str(item)
            for item in value
        )
        return "|".join(values)

    if value is None:
        return ""

    return str(value)


def _canonical_endpoints(
    u: int,
    v: int,
) -> tuple[int, int]:
    """Ignora direção para representar a ligação física entre dois nós."""

    u = int(u)
    v = int(v)

    return (
        (u, v)
        if u <= v
        else (v, u)
    )


def graph_edge_keys(
    graph,
    mode: str,
) -> pd.DataFrame:
    """
    Cria chaves candidatas de equivalência física para as arestas.

    A chave mais estrita usa:
    - par de nós sem direção;
    - osmid normalizado.

    Também preservamos uma chave somente por par de nós para diagnóstico.
    """

    edges = ox.graph_to_gdfs(
        graph,
        nodes=False,
        edges=True,
        fill_edge_geometry=True,
    ).reset_index()

    rows: list[dict] = []

    for row in edges.itertuples(
        index=False
    ):
        a, b = _canonical_endpoints(
            row.u,
            row.v,
        )

        osmid = _normalize_osmid(
            getattr(
                row,
                "osmid",
                None,
            )
        )

        rows.append(
            {
                "mode": mode,
                "u": int(row.u),
                "v": int(row.v),
                "key": int(row.key),
                "undirected_nodes": f"{a}:{b}",
                "osmid_signature": osmid,
                "strict_key": f"{a}:{b}:{osmid}",
            }
        )

    result = pd.DataFrame(
        rows
    )

    # Uma rua bidirecional costuma aparecer duas vezes no MultiDiGraph.
    # Para o diagnóstico físico, deduplicamos por chave.
    return result.drop_duplicates(
        subset=[
            "strict_key",
        ]
    ).reset_index(drop=True)


def _pairwise_report(
    left_name: str,
    left: pd.DataFrame,
    right_name: str,
    right: pd.DataFrame,
) -> dict:
    left_strict = set(
        left["strict_key"]
    )
    right_strict = set(
        right["strict_key"]
    )

    left_nodes = set(
        left["undirected_nodes"]
    )
    right_nodes = set(
        right["undirected_nodes"]
    )

    strict_intersection = (
        left_strict
        & right_strict
    )
    node_intersection = (
        left_nodes
        & right_nodes
    )

    return {
        "pair": f"{left_name} × {right_name}",
        "strict_shared": len(
            strict_intersection
        ),
        f"{left_name}_strict_share_pct": (
            100.0
            * len(strict_intersection)
            / len(left_strict)
            if left_strict
            else 0.0
        ),
        f"{right_name}_strict_share_pct": (
            100.0
            * len(strict_intersection)
            / len(right_strict)
            if right_strict
            else 0.0
        ),
        "node_pair_shared": len(
            node_intersection
        ),
    }


def main() -> None:
    config = load_config()

    modes = list(
        config["routing"]["implemented_modes"]
    )

    print(
        "Carregando redes:",
        ", ".join(modes),
    )

    graphs = load_mode_graphs(
        config=config,
        project_root=PROJECT_ROOT,
        modes=modes,
    )

    tables: dict[str, pd.DataFrame] = {}

    print("\nArestas físicas candidatas por modo")

    for mode in modes:
        table = graph_edge_keys(
            graphs[mode],
            mode,
        )
        tables[mode] = table

        print(
            f"  {mode:>4}: "
            f"{len(table):,} chaves físicas candidatas"
        )

    print(
        "\nSobreposição direta entre redes "
        "(par de nós sem direção + osmid)"
    )

    reports = []

    for left_name, right_name in combinations(
        modes,
        2,
    ):
        report = _pairwise_report(
            left_name,
            tables[left_name],
            right_name,
            tables[right_name],
        )
        reports.append(
            report
        )

        print(
            f"\n{report['pair']}"
        )
        print(
            "  chaves estritas compartilhadas: "
            f"{report['strict_shared']:,}"
        )
        print(
            f"  % de {left_name} coberto diretamente: "
            f"{report[f'{left_name}_strict_share_pct']:.1f}%"
        )
        print(
            f"  % de {right_name} coberto diretamente: "
            f"{report[f'{right_name}_strict_share_pct']:.1f}%"
        )
        print(
            "  pares de nós compartilhados "
            "(ignorando osmid): "
            f"{report['node_pair_shared']:,}"
        )

    output_dir = (
        PROJECT_ROOT
        / "outputs"
        / "pilot"
    )
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_df = pd.DataFrame(
        reports
    )

    report_path = (
        output_dir
        / "modal_network_overlap.csv"
    )

    report_df.to_csv(
        report_path,
        index=False,
        encoding="utf-8",
    )

    print(
        "\nDiagnóstico salvo em:",
        report_path.resolve(),
    )

    print(
        "\nInterpretação: cobertura alta indica que podemos usar "
        "identificadores OSM diretamente para boa parte da harmonização. "
        "Cobertura baixa indica que será necessário reconciliar geometrias "
        "e segmentações antes de definir analysis_segment_id."
    )


if __name__ == "__main__":
    main()
