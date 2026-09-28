"""Harmoniza as redes modais completas em segmentos físicos comuns

Usa a rede de caminhada como referência inicial. Mapeia bicicleta e carro
primeiro por equivalência OSM exata e, em seguida, por sobreposição
geométrica compatível. Preserva como exclusivos apenas os segmentos que não
puderem ser reconciliados com segurança

Constrói esta camada a partir das redes completas, e não das trajetórias
observadas. Preserva assim o mesmo `analysis_segment_id` quando altere o
número de agentes, a seed ou o cenário experimental
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString


DEFAULT_REFERENCE_MODE = "walk"
DEFAULT_MODE_ORDER = ("walk", "bike", "car")


def _normalize_osmid(value) -> str:
    """Normaliza o osmid para uma assinatura textual estável"""

    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return "|".join(
            sorted(
                str(item)
                for item in value
            )
        )

    return str(value)


def _osmid_set(value) -> frozenset[str]:
    """Converte o osmid para um conjunto imutável de identificadores"""

    if value is None:
        return frozenset()

    if isinstance(value, (list, tuple, set)):
        return frozenset(
            str(item)
            for item in value
        )

    return frozenset(
        {
            str(value),
        }
    )


def _normalize_text(value) -> str:
    """Normaliza um atributo textual para comparação"""

    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return "|".join(
            sorted(
                str(item).strip().lower()
                for item in value
            )
        )

    return str(value).strip().lower()


def _canonical_endpoints(
    u: int,
    v: int,
) -> tuple[int, int]:
    """Ignora a direção e retorna o par canônico de nós"""

    u = int(u)
    v = int(v)

    if u <= v:
        return u, v

    return v, u


def _edge_geometry(
    graph,
    u: int,
    v: int,
    key: int,
    attributes: Mapping | None = None,
):
    """Recupera a geometria e cria uma linha quando a aresta não a possuir"""

    if attributes is None:
        attributes = graph.get_edge_data(
            u,
            v,
            key,
        )

    if attributes is None:
        raise ValueError(
            "Não encontre a aresta no grafo: "
            f"({u}, {v}, {key})."
        )

    geometry = attributes.get(
        "geometry"
    )

    if geometry is not None:
        return geometry

    origin = graph.nodes[
        u
    ]
    destination = graph.nodes[
        v
    ]

    return LineString(
        [
            (
                float(origin["x"]),
                float(origin["y"]),
            ),
            (
                float(destination["x"]),
                float(destination["y"]),
            ),
        ]
    )


def _edge_record(
    *,
    mode: str,
    graph,
    u: int,
    v: int,
    key: int,
    attributes: Mapping,
) -> dict:
    """Converte uma aresta modal em um registro padronizado"""

    u = int(u)
    v = int(v)
    key = int(key)

    a, b = _canonical_endpoints(
        u,
        v,
    )

    osmid = attributes.get(
        "osmid"
    )
    osmid_signature = _normalize_osmid(
        osmid
    )

    geometry = _edge_geometry(
        graph,
        u,
        v,
        key,
        attributes,
    )

    return {
        "mode": mode,
        "u": u,
        "v": v,
        "key": key,
        "modal_edge_id": (
            f"{mode}:{u}:{v}:{key}"
        ),
        "undirected_nodes": (
            f"{a}:{b}"
        ),
        "osmid_signature": (
            osmid_signature
        ),
        "osmid_set": _osmid_set(
            osmid
        ),
        "strict_key": (
            f"{a}:{b}:{osmid_signature}"
        ),
        "name_norm": _normalize_text(
            attributes.get(
                "name"
            )
        ),
        "highway_norm": _normalize_text(
            attributes.get(
                "highway"
            )
        ),
        "length_m": float(
            geometry.length
        ),
        "geometry": geometry,
    }


def extract_all_modal_edges(
    graphs: Mapping[str, object],
    *,
    modes: Iterable[str] | None = None,
) -> gpd.GeoDataFrame:
    """Extrai todas as arestas das redes modais carregadas"""

    if modes is None:
        modes = graphs.keys()

    rows: list[dict] = []
    common_crs = None

    for mode in modes:
        if mode not in graphs:
            raise ValueError(
                f"Carregue a rede correspondente ao modo '{mode}'."
            )

        graph = graphs[
            mode
        ]

        graph_crs = graph.graph.get(
            "crs"
        )

        if graph_crs is None:
            raise ValueError(
                f"Registre um CRS na rede '{mode}'."
            )

        if common_crs is None:
            common_crs = graph_crs

        if str(graph_crs) != str(common_crs):
            raise ValueError(
                "Projete todas as redes para o mesmo CRS antes "
                "de harmonizar os segmentos."
            )

        for (
            u,
            v,
            key,
            attributes,
        ) in graph.edges(
            keys=True,
            data=True,
        ):
            rows.append(
                _edge_record(
                    mode=str(mode),
                    graph=graph,
                    u=int(u),
                    v=int(v),
                    key=int(key),
                    attributes=attributes,
                )
            )

    if not rows:
        raise ValueError(
            "Forneça redes com pelo menos uma aresta."
        )

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=common_crs,
    )


def extract_used_modal_edges(
    edge_usage: pd.DataFrame,
    graphs: Mapping[str, object],
) -> gpd.GeoDataFrame:
    """Extrai apenas as arestas efetivamente usadas pelas trajetórias"""

    required_columns = {
        "mode",
        "u",
        "v",
        "key",
        "modal_edge_id",
    }

    missing = (
        required_columns
        - set(edge_usage.columns)
    )

    if missing:
        raise ValueError(
            "Adicione ao edge_usage as colunas obrigatórias: "
            f"{sorted(missing)}"
        )

    used = (
        edge_usage[
            [
                "mode",
                "u",
                "v",
                "key",
                "modal_edge_id",
            ]
        ]
        .drop_duplicates()
        .reset_index(drop=True)
    )

    rows: list[dict] = []
    common_crs = None

    for row in used.itertuples(
        index=False
    ):
        mode = str(
            row.mode
        )

        if mode not in graphs:
            raise ValueError(
                f"Carregue a rede correspondente ao modo '{mode}'."
            )

        graph = graphs[
            mode
        ]
        graph_crs = graph.graph.get(
            "crs"
        )

        if graph_crs is None:
            raise ValueError(
                f"Registre um CRS na rede '{mode}'."
            )

        if common_crs is None:
            common_crs = graph_crs

        if str(graph_crs) != str(common_crs):
            raise ValueError(
                "Projete todas as redes para o mesmo CRS antes "
                "de harmonizar os segmentos."
            )

        u = int(
            row.u
        )
        v = int(
            row.v
        )
        key = int(
            row.key
        )

        attributes = graph.get_edge_data(
            u,
            v,
            key,
        )

        if attributes is None:
            raise ValueError(
                "Não encontre a aresta registrada no edge_usage: "
                f"{mode}:{u}:{v}:{key}."
            )

        record = _edge_record(
            mode=mode,
            graph=graph,
            u=u,
            v=v,
            key=key,
            attributes=attributes,
        )

        record[
            "modal_edge_id"
        ] = str(
            row.modal_edge_id
        )

        rows.append(
            record
        )

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=common_crs,
    )


def _new_segment_id(
    index: int,
) -> str:
    """Cria um identificador sequencial estável para o segmento"""

    return f"S_{index:07d}"


def _candidate_is_compatible(
    edge: pd.Series,
    segment: pd.Series,
) -> bool:
    """Exige compatibilidade OSM ou textual antes de aceitar o encaixe"""

    edge_osmids = edge[
        "osmid_set"
    ]
    segment_osmids = segment[
        "osmid_set"
    ]

    if edge_osmids and segment_osmids:
        return bool(
            edge_osmids
            & segment_osmids
        )

    edge_name = edge[
        "name_norm"
    ]
    segment_name = segment[
        "name_norm"
    ]

    if edge_name and segment_name:
        return (
            edge_name
            == segment_name
        )

    edge_highway = edge[
        "highway_norm"
    ]
    segment_highway = segment[
        "highway_norm"
    ]

    return bool(
        edge_highway
        and segment_highway
        and edge_highway
        == segment_highway
    )


def _coverage_ratio(
    candidate_geometry,
    edge_geometry,
    tolerance_m: float,
) -> float:
    """Mede quanto do segmento candidato fica coberto pela aresta modal"""

    if candidate_geometry.length <= 0:
        return 0.0

    covered = candidate_geometry.intersection(
        edge_geometry.buffer(
            tolerance_m
        )
    )

    return min(
        1.0,
        float(
            covered.length
        )
        / float(
            candidate_geometry.length
        ),
    )


def _find_geometry_matches(
    edge: pd.Series,
    segments: gpd.GeoDataFrame,
    *,
    tolerance_m: float,
    min_coverage: float,
) -> list[tuple[str, float]]:
    """Seleciona os segmentos compatíveis cobertos pela aresta modal"""

    if segments.empty:
        return []

    search_geometry = edge[
        "geometry"
    ].buffer(
        tolerance_m
    )

    candidate_positions = list(
        segments.sindex.intersection(
            search_geometry.bounds
        )
    )

    matches: list[
        tuple[str, float]
    ] = []

    for position in candidate_positions:
        segment = segments.iloc[
            position
        ]

        if not _candidate_is_compatible(
            edge,
            segment,
        ):
            continue

        coverage = _coverage_ratio(
            segment[
                "geometry"
            ],
            edge[
                "geometry"
            ],
            tolerance_m,
        )

        if coverage < min_coverage:
            continue

        matches.append(
            (
                str(
                    segment[
                        "analysis_segment_id"
                    ]
                ),
                float(
                    coverage
                ),
            )
        )

    return sorted(
        matches,
        key=lambda item: item[0],
    )


def _segments_frame(
    rows: list[dict],
    crs,
) -> gpd.GeoDataFrame:
    """Converte os registros acumulados em um GeoDataFrame"""

    return gpd.GeoDataFrame(
        rows,
        geometry="geometry",
        crs=crs,
    )


def build_analysis_segments(
    modal_edges: gpd.GeoDataFrame,
    *,
    reference_mode: str = DEFAULT_REFERENCE_MODE,
    mode_order: Iterable[str] = DEFAULT_MODE_ORDER,
    tolerance_m: float = 5.0,
    min_coverage: float = 0.80,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Constrói a rede física comum e mapeia todas as arestas modais"""

    if modal_edges.empty:
        raise ValueError(
            "Forneça pelo menos uma aresta modal."
        )

    if modal_edges.crs is None:
        raise ValueError(
            "Defina o CRS projetado das arestas antes da harmonização."
        )

    if not modal_edges.crs.is_projected:
        raise ValueError(
            "Projete as arestas para um CRS métrico antes da harmonização."
        )

    if tolerance_m <= 0:
        raise ValueError(
            "Use tolerance_m maior que zero."
        )

    if not 0 < min_coverage <= 1:
        raise ValueError(
            "Use min_coverage no intervalo (0, 1]."
        )

    modes_present = set(
        modal_edges[
            "mode"
        ].astype(
            str
        )
    )

    if reference_mode not in modes_present:
        raise ValueError(
            f"Inclua o modo de referência '{reference_mode}'."
        )

    ordered_modes = [
        mode
        for mode in mode_order
        if mode in modes_present
    ]

    for mode in sorted(
        modes_present
        - set(ordered_modes)
    ):
        ordered_modes.append(
            mode
        )

    segments_rows: list[dict] = []
    mapping_rows: list[dict] = []
    next_segment_index = 1

    def append_segment(
        edge: pd.Series,
        source_mode: str,
    ) -> str:
        """Adiciona um segmento físico e devolva seu identificador"""

        nonlocal next_segment_index

        segment_id = _new_segment_id(
            next_segment_index
        )
        next_segment_index += 1

        segments_rows.append(
            {
                "analysis_segment_id": segment_id,
                "source_mode": source_mode,
                "source_modal_edge_id": str(
                    edge[
                        "modal_edge_id"
                    ]
                ),
                "strict_key": edge[
                    "strict_key"
                ],
                "osmid_signature": edge[
                    "osmid_signature"
                ],
                "osmid_set": edge[
                    "osmid_set"
                ],
                "name_norm": edge[
                    "name_norm"
                ],
                "highway_norm": edge[
                    "highway_norm"
                ],
                "length_m": float(
                    edge[
                        "geometry"
                    ].length
                ),
                "geometry": edge[
                    "geometry"
                ],
            }
        )

        return segment_id

    reference_edges = (
        modal_edges.loc[
            modal_edges[
                "mode"
            ]
            == reference_mode
        ]
        .sort_values(
            [
                "strict_key",
                "modal_edge_id",
            ]
        )
    )

    for (
        strict_key,
        group,
    ) in reference_edges.groupby(
        "strict_key",
        sort=True,
    ):
        edge = group.iloc[
            0
        ]

        segment_id = append_segment(
            edge,
            reference_mode,
        )

        for modal_edge_id in group[
            "modal_edge_id"
        ].astype(
            str
        ):
            mapping_rows.append(
                {
                    "modal_edge_id": modal_edge_id,
                    "mode": reference_mode,
                    "analysis_segment_id": segment_id,
                    "match_method": "reference",
                    "match_quality": 1.0,
                }
            )

    for mode in ordered_modes:
        if mode == reference_mode:
            continue

        # Congela a camada já harmonizada antes de processar o próximo modo
        segments_snapshot = _segments_frame(
            segments_rows,
            modal_edges.crs,
        )

        # Indexa as chaves exatas uma única vez para evitar buscas repetidas
        strict_lookup = (
            segments_snapshot.groupby(
                "strict_key"
            )[
                "analysis_segment_id"
            ]
            .apply(
                lambda values: [
                    str(value)
                    for value in values
                ]
            )
            .to_dict()
        )

        mode_edges = (
            modal_edges.loc[
                modal_edges[
                    "mode"
                ]
                == mode
            ]
            .sort_values(
                [
                    "strict_key",
                    "modal_edge_id",
                ]
            )
        )

        # Agrupa direções e duplicatas físicas antes de procurar equivalências
        for (
            strict_key,
            group,
        ) in mode_edges.groupby(
            "strict_key",
            sort=True,
        ):
            edge = group.iloc[
                0
            ]

            modal_edge_ids = (
                group[
                    "modal_edge_id"
                ]
                .astype(str)
                .tolist()
            )

            exact_targets = strict_lookup.get(
                strict_key,
                [],
            )

            if exact_targets:
                targets = [
                    (
                        segment_id,
                        "osm_exact",
                        1.0,
                    )
                    for segment_id in exact_targets
                ]
            else:
                geometry_matches = _find_geometry_matches(
                    edge,
                    segments_snapshot,
                    tolerance_m=tolerance_m,
                    min_coverage=min_coverage,
                )

                if geometry_matches:
                    targets = [
                        (
                            segment_id,
                            "geometry",
                            quality,
                        )
                        for (
                            segment_id,
                            quality,
                        ) in geometry_matches
                    ]
                else:
                    segment_id = append_segment(
                        edge,
                        mode,
                    )

                    targets = [
                        (
                            segment_id,
                            "exclusive",
                            1.0,
                        )
                    ]

            # Aplica o mesmo mapeamento a todas as direções da aresta física
            for modal_edge_id in modal_edge_ids:
                for (
                    segment_id,
                    method,
                    quality,
                ) in targets:
                    mapping_rows.append(
                        {
                            "modal_edge_id": modal_edge_id,
                            "mode": mode,
                            "analysis_segment_id": segment_id,
                            "match_method": method,
                            "match_quality": quality,
                        }
                    )

    segments = _segments_frame(
        segments_rows,
        modal_edges.crs,
    )

    mapping = pd.DataFrame(
        mapping_rows
    )

    mapped_count = mapping[
        "modal_edge_id"
    ].nunique()
    source_count = modal_edges[
        "modal_edge_id"
    ].nunique()

    if mapped_count != source_count:
        raise RuntimeError(
            "Mapeie todas as arestas modais antes de concluir "
            f"a harmonização ({mapped_count}/{source_count})."
        )

    return (
        segments,
        mapping,
    )


def apply_analysis_segment_mapping(
    edge_usage: pd.DataFrame,
    mapping: pd.DataFrame,
) -> pd.DataFrame:
    """Aplica o mapeamento 1:N às passagens registradas no edge_usage"""

    result = edge_usage.merge(
        mapping,
        on=[
            "modal_edge_id",
            "mode",
        ],
        how="left",
        validate="many_to_many",
    )

    if result[
        "analysis_segment_id"
    ].isna().any():
        missing = (
            result.loc[
                result[
                    "analysis_segment_id"
                ].isna(),
                "modal_edge_id",
            ]
            .drop_duplicates()
            .tolist()
        )

        raise RuntimeError(
            "Mapeie antes de continuar as arestas: "
            f"{missing[:10]}"
        )

    return result


def segment_match_report(
    mapping: pd.DataFrame,
    *,
    modal_edge_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Resume os métodos usados para harmonizar as arestas modais"""

    selected = mapping

    if modal_edge_ids is not None:
        selected_ids = {
            str(value)
            for value in modal_edge_ids
        }

        selected = mapping.loc[
            mapping[
                "modal_edge_id"
            ].astype(str).isin(
                selected_ids
            )
        ]

    if selected.empty:
        return pd.DataFrame(
            columns=[
                "mode",
                "match_method",
                "mapping_rows",
                "modal_edges",
                "analysis_segments",
                "mean_match_quality",
                "mode_modal_edges",
                "modal_edge_share_pct",
            ]
        )

    report = (
        selected
        .groupby(
            [
                "mode",
                "match_method",
            ],
            as_index=False,
        )
        .agg(
            mapping_rows=(
                "analysis_segment_id",
                "size",
            ),
            modal_edges=(
                "modal_edge_id",
                "nunique",
            ),
            analysis_segments=(
                "analysis_segment_id",
                "nunique",
            ),
            mean_match_quality=(
                "match_quality",
                "mean",
            ),
        )
    )

    mode_totals = (
        selected
        .groupby(
            "mode"
        )[
            "modal_edge_id"
        ]
        .nunique()
        .rename(
            "mode_modal_edges"
        )
    )

    report = report.merge(
        mode_totals,
        on="mode",
        how="left",
    )

    report[
        "modal_edge_share_pct"
    ] = (
        100.0
        * report[
            "modal_edges"
        ]
        / report[
            "mode_modal_edges"
        ]
    )

    return report.sort_values(
        [
            "mode",
            "match_method",
        ]
    ).reset_index(
        drop=True
    )
