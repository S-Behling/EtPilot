"""Carregamento centralizado das configurações do EtPilot.

Evita que notebooks e módulos reimplementem resolução de caminhos e leitura
de JSON. Todos os caminhos relativos são resolvidos a partir da raiz do
projeto.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_json(path: str | Path) -> dict[str, Any]:
    """Carrega um arquivo JSON e retorna um dicionário."""

    resolved = project_path(path)

    if not resolved.exists():
        raise FileNotFoundError(
            f"Arquivo de configuração não encontrado: {resolved}"
        )

    with resolved.open("r", encoding="utf-8") as file:
        return json.load(file)


def project_path(path: str | Path) -> Path:
    """Resolve um caminho em relação à raiz do projeto."""

    candidate = Path(path)

    if candidate.is_absolute():
        return candidate

    return PROJECT_ROOT / candidate


def load_project_config() -> dict[str, Any]:
    """Carrega a configuração principal do projeto."""

    return load_json(CONFIG_DIR / "config.json")


def load_agent_config() -> dict[str, Any]:
    """Carrega a configuração comportamental dos agentes."""

    return load_json(CONFIG_DIR / "config_agents.json")


def load_regions_config(
    project_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Carrega as definições territoriais configuradas."""

    config = (
        project_config
        if project_config is not None
        else load_project_config()
    )

    relative_path = config["study_area"].get(
        "regions_file",
        "config/regions.json",
    )

    return load_json(relative_path)
