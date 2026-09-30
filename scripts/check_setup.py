"""Valida se os insumos necessários ao pipeline regional estão disponíveis.

Uso:
    python scripts/check_setup.py
"""

from __future__ import annotations

from src.core.config import load_project_config, project_path
from src.network.multimodal import SUPPORTED_MODES, graph_path_for_mode


def main() -> None:
    config = load_project_config()

    required_files = {
        "bairros": project_path(config["paths"]["neighborhoods"]),
        "origens": project_path(config["paths"]["origins_income"]),
        "destinos": project_path(config["paths"]["destinations"]),
    }

    transit_dir = project_path(config["transit"]["data_dir"])
    for key, filename in config["transit"]["files"].items():
        required_files[f"gtfs:{key}"] = transit_dir / filename

    missing = []

    for label, path in required_files.items():
        status = "ok" if path.exists() else "missing"
        print(f"[{status}] {label}: {path}")

        if not path.exists():
            missing.append(path)

    for mode in SUPPORTED_MODES:
        path = graph_path_for_mode(config, mode)
        status = "ok" if path.exists() else "missing"
        print(f"[{status}] rede:{mode}: {path}")

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
