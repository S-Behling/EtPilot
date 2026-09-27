from pathlib import Path
import zipfile
import requests

# ============================================================
# 2. FUNÇÃO DE DOWNLOAD
# ============================================================

# Função reutilizável para baixar arquivos grandes

def baixar_arquivo(url, destino, chunk_size=1024 * 1024):

    destino = Path(destino)

    # Eu evito baixar novamente arquivos
    # que já existem no projeto.
    if destino.exists():

        print(
            f"Arquivo já existe: {destino.name}"
        )

        return destino


    print(
        f"Baixando: {destino.name}"
    )


    resposta = requests.get(
        url,
        stream=True,
        timeout=120
    )

    resposta.raise_for_status()


    tamanho_total = int(
        resposta.headers.get(
            "content-length",
            0
        )
    )


    baixado = 0


    with open(destino, "wb") as arquivo:

        for bloco in resposta.iter_content(
            chunk_size=chunk_size
        ):

            if not bloco:
                continue

            arquivo.write(
                bloco
            )

            baixado += len(bloco)


            if tamanho_total > 0:

                percentual = (
                    baixado
                    / tamanho_total
                    * 100
                )

                print(
                    f"\r{percentual:6.2f}%",
                    end=""
                )


    print(
        f"\nConcluído: {destino}"
    )

    return destino