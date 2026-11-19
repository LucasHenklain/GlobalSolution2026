"""Gera o PDF de entregáveis do VigIA a partir das evidências reais do repositório.

Uso (a partir da raiz):  python docs/pdf/gerar_pdf.py
Saída: VigIA_Grupo14_Entregaveis.pdf (na raiz do projeto)  (e docs/pdf/_work/entregaveis.html, para conferir no navegador)

O conteúdo fixo está em docs/pdf/secoes.py; números, tabelas e registros são lidos dos arquivos gerados pelo
próprio projeto (ia/modelos/metricas.json, docs/evidencias/...). A seção de validação com pessoas reais vem de
docs/pdf/conteudo/validacao.md, que a equipe preenche.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))
AQUI = Path(__file__).resolve().parent
TRABALHO = AQUI / "_work"
SAIDA = RAIZ / "VigIA_Grupo14_Entregaveis.pdf"


# ------------------------------------------------------------------ ajudantes usados pelas seções


def esc(texto: str) -> str:
    return html.escape(texto, quote=False)


def ler(caminho: str, padrao: str = "") -> str:
    arquivo = RAIZ / caminho
    return arquivo.read_text(encoding="utf-8", errors="replace") if arquivo.exists() else padrao


def bloco(texto: str, claro: bool = False, max_linhas: int | None = None) -> str:
    """Texto de terminal ou código, exatamente como foi gerado."""
    linhas = texto.rstrip().splitlines()
    if max_linhas and len(linhas) > max_linhas:
        linhas = linhas[:max_linhas] + [f"[... {len(linhas) - max_linhas} linhas omitidas; íntegra no repositório ...]"]
    return f'<pre class="{"claro" if claro else ""}">{esc(chr(10).join(linhas))}</pre>'


def br(valor) -> str:
    """Número no padrão brasileiro: vírgula decimal e ponto de milhar."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return str(valor)
    if isinstance(valor, int):
        return f"{valor:,}".replace(",", ".")
    return f"{valor:,}".replace(",", "#").replace(".", ",").replace("#", ".")


def _recortar(arquivo: Path, proporcao: float) -> Path:
    """Guarda só o topo de um print muito alto (altura = largura × proporção), para ele ficar legível na página."""
    from PIL import Image

    with Image.open(arquivo) as imagem:
        altura = int(imagem.width * proporcao)
        if imagem.height <= altura:
            return arquivo
        destino = TRABALHO / "cortes" / arquivo.name
        destino.parent.mkdir(parents=True, exist_ok=True)
        imagem.crop((0, 0, imagem.width, altura)).save(destino)
    return destino


def figura(caminho: str, legenda: str, classe: str = "", recorte: float | None = None) -> str:
    arquivo = RAIZ / caminho
    if not arquivo.exists():
        return f'<div class="pendente">Imagem ainda não gerada: <code>{esc(caminho)}</code></div>'
    if recorte:
        arquivo = _recortar(arquivo, recorte)
    return f'<figure class="{classe}"><img src="{arquivo.as_uri()}"><figcaption>{legenda}</figcaption></figure>'


def tabela(cabecalho: list[str], linhas: list[list], numericas: tuple[int, ...] = ()) -> str:
    th = "".join(f'<th class="{"n" if i in numericas else ""}">{c}</th>' for i, c in enumerate(cabecalho))
    corpo = ""
    for linha in linhas:
        corpo += "<tr>" + "".join(f'<td class="{"n" if i in numericas else ""}">{c}</td>' for i, c in enumerate(linha)) + "</tr>"
    return f"<table><tr>{th}</tr>{corpo}</table>"


def rubrica(texto: str) -> str:
    return f'<div class="rubrica">{texto}</div>'


def markdown_simples(texto: str) -> str:
    """Converte o mínimo de Markdown (títulos ###, listas com -, parágrafos, **negrito**) para a seção da equipe."""
    saida, lista = [], False
    for linha in texto.splitlines():
        linha = esc(linha.rstrip())
        linha = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", linha)
        linha = re.sub(r"`([^`]+)`", r"<code>\1</code>", linha)
        if linha.startswith("- "):
            saida.append(("" if lista else "<ul>") + f"<li>{linha[2:]}</li>")
            lista = True
            continue
        if lista:
            saida.append("</ul>")
            lista = False
        if linha.startswith("### "):
            saida.append(f"<h3>{linha[4:]}</h3>")
        elif linha.startswith("&gt; "):
            saida.append(f'<div class="aviso">{linha[5:]}</div>')
        elif linha.strip():
            saida.append(f"<p>{linha}</p>")
    return "\n".join(saida) + ("</ul>" if lista else "")


def metricas() -> dict:
    return json.loads(ler("ia/modelos/metricas.json", "{}") or "{}")


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip()


# ------------------------------------------------------------------ montagem e impressão


def montar_html() -> str:
    from docs.pdf import secoes

    corpo = "\n".join(secao() for secao in secoes.ORDEM)
    css = (AQUI / "estilo.css").read_text(encoding="utf-8")
    return f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>VigIA — entregáveis</title><style>{css}</style></head><body>{corpo}</body></html>'


def imprimir_pdf(arquivo_html: Path, destino: Path) -> None:
    """Imprime o HTML em PDF A4 com o Edge sem interface (via Playwright; ver docs/ferramentas/navegador.py)."""
    from docs.ferramentas.navegador import abrir

    destino.parent.mkdir(parents=True, exist_ok=True)
    with abrir(1240, 1754) as (_, pagina):
        pagina.goto(arquivo_html.as_uri(), wait_until="load")
        pagina.wait_for_timeout(1500)  # tempo para todas as imagens locais decodificarem
        rodape = (
            '<div style="font-size:7.5px;width:100%;text-align:center;color:#7a8794;font-family:Segoe UI,Arial">'
            'VigIA · Grupo 14 · Global Solution 2026/2 · página <span class="pageNumber"></span> de <span class="totalPages"></span></div>'
        )
        pagina.pdf(
            path=str(destino), format="A4", print_background=True, prefer_css_page_size=True,
            display_header_footer=True, header_template="<div></div>", footer_template=rodape,
        )  # fmt: skip
    if not destino.exists():
        raise SystemExit("o navegador não gerou o PDF; abra docs/pdf/_work/entregaveis.html e imprima em PDF manualmente")


def main() -> None:
    TRABALHO.mkdir(exist_ok=True)
    arquivo_html = TRABALHO / "entregaveis.html"
    arquivo_html.write_text(montar_html(), encoding="utf-8")
    imprimir_pdf(arquivo_html, SAIDA)
    print(f"PDF gerado: {SAIDA} ({SAIDA.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
