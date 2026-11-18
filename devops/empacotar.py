"""Monta o .zip da entrega com os arquivos versionados no Git (nada de cache, banco local ou data lake gerado).

Uso:  python -m devops.empacotar
Saída: entrega/GS2026-2_CitizenTech_Grupo14.zip

Confere antes de fechar: README, PDF e .txt na raiz, e avisa se o link do vídeo ainda não foi preenchido.
"""

from __future__ import annotations

import subprocess  # nosec B404
import sys
import zipfile

from comum.config import RAIZ

DESTINO = RAIZ / "entrega" / "GS2026-2_CitizenTech_Grupo14.zip"
OBRIGATORIOS = ["README.md", "VigIA_Grupo14_Entregaveis.pdf", "Grupo14_integrantes.txt"]
FORA_DO_ZIP = ("referencias/", "entrega/", "PLANO.md", ".github/ISSUE")  # material de trabalho, não é entregável
MARCA_PENDENTE = "[A PREENCHER"


def arquivos_versionados() -> list[str]:
    saida = subprocess.run(  # noqa: S603  # nosec B603 B607
        ["git", "ls-files"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,  # noqa: S607
    ).stdout
    return [linha for linha in saida.splitlines() if linha and not linha.startswith(FORA_DO_ZIP)]


def main() -> int:
    arquivos = arquivos_versionados()
    faltando = [nome for nome in OBRIGATORIOS if nome not in arquivos or not (RAIZ / nome).exists()]
    if faltando:
        print(f"ERRO: faltam na raiz (e no Git): {faltando}")
        return 1
    DESTINO.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(DESTINO, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as pacote:
        for nome in arquivos:
            pacote.write(RAIZ / nome, nome)
    print(f"ZIP: {DESTINO} · {len(arquivos)} arquivos · {DESTINO.stat().st_size / 1e6:.1f} MB")
    pendentes = [
        n for n in ("README.md", "Grupo14_integrantes.txt") if MARCA_PENDENTE in (RAIZ / n).read_text(encoding="utf-8")
    ]
    if pendentes:
        print(f"ATENÇÃO: link do vídeo ainda não preenchido em {pendentes}. Preencha, gere o PDF e empacote de novo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
