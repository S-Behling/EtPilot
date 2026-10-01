"""Valida se os insumos necessários ao pipeline regional estão disponíveis.

Uso:
    python scripts/check_setup.py
"""

from __future__ import annotations

from _bootstrap import add_project_root_to_path

add_project_root_to_path()

import geopandas as gpd

from src.core.config import (
    load_project_config,
    load_regions_config,
    project_path,
)
from src.network.multimodal import (
    SUPPORTED_MODES,
    graph_path_for_mode,
)
from src.spatial.regions import (
    resolve_neighborhood_name_field,
)


def main() -> None:
    config = load_project_config()
    regions_config = load_regions_config(
        config
    )

    required_files = {
        "bairros": project_path(
            config["paths"]["neighborhoods"]
        ),
        "origens": project_path(
            config["paths"]["origins_income"]
        ),
        "destinos": project_path(
            config["paths"]["destinations"]
        ),
    }

    transit_dir = project_path(
        config["transit"]["data_dir"]
    )

    for key, filename in config[
        "transit"
    ][
        "files"
    ].items():
        required_files[
            f"gtfs:{key}"
        ] = transit_dir / filename

    missing = []

    for label, path in required_files.items():
        status = (
            "ok"
            if path.exists()
            else "missing"
        )
        print(
            f"[{status}] {label}: {path}"
        )

        if not path.exists():
            missing.append(
                path
            )

    neighborhoods_path = required_files[
        "bairros"
    ]

    if neighborhoods_path.exists():
        neighborhoods = gpd.read_file(
            neighborhoods_path,
            engine="pyogrio",
        )

        requested_field = regions_config.get(
            "name_field",
            "NM_BAIRRO",
        )

        resolved_field = (
            resolve_neighborhood_name_field(
                neighborhoods,
                requested_field=requested_field,
            )
        )

        print(
            "[ok] bairros: coluna de nome resolvida "
            f"como '{resolved_field}'"
        )
        print(
            "[info] bairros: colunas disponíveis = "
            + ", ".join(
                str(column)
                for column in neighborhoods.columns
            )
        )

    for mode in SUPPORTED_MODES:
        path = graph_path_for_mode(
            config,
            mode,
        )
        status = (
            "ok"
            if path.exists()
            else "missing"
        )
        print(
            f"[{status}] rede:{mode}: {path}"
        )

    if missing:
        raise SystemExit(
            "\nExistem insumos obrigatórios ausentes. "
            "Corrija os itens marcados como [missing]."
        )

    print(
        "\nInsumos principais encontrados. "
        "Redes OSM ausentes podem ser criadas por "
        "scripts/prepare_city_networks.py."
    )


if __name__ == "__main__":
    main()
