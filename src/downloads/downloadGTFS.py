"""Baixa o arquivo GTFS oficial de Porto Alegre para data/gtfs

Lê a URL e os caminhos a partir de config/config.json
Mantém o arquivo compactado diretamente em data/gtfs
Registra metadados básicos do download para apoiar a reprodutibilidade
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


def _load_config() -> dict:
    """Carrega a configuração principal do projeto"""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(
            file
        )


def _sha256(path: Path) -> str:
    """Calcula o hash SHA-256 do arquivo baixado"""

    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as file:
        for chunk in iter(
            lambda: file.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def download_gtfs(
    *,
    overwrite: bool = False,
) -> Path:
    """Baixa o GTFS configurado e retorna o caminho do ZIP"""

    config = _load_config()
    gtfs_config = config[
        "transit"
    ][
        "gtfs"
    ]

    source_url = str(
        gtfs_config[
            "source_url"
        ]
    )
    data_dir = (
        PROJECT_ROOT
        / gtfs_config[
            "data_dir"
        ]
    )
    zip_path = (
        data_dir
        / gtfs_config[
            "zip_file"
        ]
    )

    data_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if (
        zip_path.exists()
        and not overwrite
    ):
        print(
            "GTFS já existe em "
            f"{zip_path}"
        )
        print(
            "Usa overwrite=True para substituir o arquivo"
        )
        return zip_path

    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "EtPilot/1.0 "
                "(research; GTFS download)"
            )
        },
    )

    temporary_path = zip_path.with_suffix(
        ".zip.part"
    )

    with urlopen(
        request,
        timeout=120,
    ) as response:
        with temporary_path.open(
            "wb"
        ) as output:
            shutil.copyfileobj(
                response,
                output,
            )

    temporary_path.replace(
        zip_path
    )

    metadata = {
        "provider": gtfs_config.get(
            "provider"
        ),
        "city": gtfs_config.get(
            "city"
        ),
        "source_page": gtfs_config.get(
            "source_page"
        ),
        "source_url": source_url,
        "downloaded_at_utc": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        ),
        "filename": zip_path.name,
        "size_bytes": zip_path.stat().st_size,
        "sha256": _sha256(
            zip_path
        ),
    }

    metadata_path = (
        data_dir
        / "gtfs_download_metadata.json"
    )

    with metadata_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            metadata,
            file,
            ensure_ascii=False,
            indent=4,
        )

    print(
        "GTFS salvo em "
        f"{zip_path}"
    )
    print(
        "Metadados salvos em "
        f"{metadata_path}"
    )

    return zip_path


if __name__ == "__main__":
    download_gtfs()
