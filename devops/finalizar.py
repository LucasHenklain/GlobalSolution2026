"""Fecha a entrega em um comando, quando chegarem o link do vídeo e as respostas da validação.

Uso:  python -m devops.finalizar --video https://youtu.be/XXXXXXXX
      python -m devops.finalizar                    (só reconsolida a validação, regera o PDF e o ZIP)

O que faz, nesta ordem:
  1. grava o link do vídeo no README.md e no Grupo14_integrantes.txt (e confere se ele abre sem login);
  2. consolida docs/validacao/respostas.csv na seção 10 do PDF (sem respostas, a seção continua PENDENTE);
  3. regera o PDF de entregáveis;
  4. faz o commit;
  5. monta o ZIP da entrega e diz o que falta.
Não envia nada para fora: o `git push` e o envio na plataforma continuam sendo passos da equipe.
"""

from __future__ import annotations

import argparse
import os
import re
import ssl
import subprocess  # nosec B404
import sys
from urllib.parse import quote, urlparse

import certifi
import httpx

from comum.config import RAIZ

README = RAIZ / "README.md"
INTEGRANTES = RAIZ / "Grupo14_integrantes.txt"
# Linha do link em cada arquivo: tudo depois do rótulo é substituído (serve também para trocar um link já gravado).
LINHAS_DO_LINK = {
    README: re.compile(r"^(\*\*Vídeo pitch \(3 min\):\*\*) .*$", re.M),
    INTEGRANTES: re.compile(r"^(Link do video pitch:) .*$", re.M),
}
DOMINIOS_ACEITOS = ("youtube.com", "youtu.be", "drive.google.com", "vimeo.com")  # os três serviços do enunciado


def validar_url(url: str) -> str:
    """Aceita só http(s) de YouTube, Google Drive ou Vimeo — o que o enunciado permite."""
    partes = urlparse(url.strip())
    dominio = partes.netloc.lower().removeprefix("www.").removeprefix("m.")
    if partes.scheme not in ("http", "https") or not any(
        dominio == d or dominio.endswith("." + d) for d in DOMINIOS_ACEITOS
    ):
        raise ValueError(f"link não aceito: {url!r} (use YouTube, Google Drive ou Vimeo, começando com https://)")
    return url.strip()


def gravar_link(url: str) -> list[str]:
    """Troca a linha do link nos dois arquivos. Devolve os nomes dos arquivos alterados."""
    alterados = []
    for arquivo, padrao in LINHAS_DO_LINK.items():
        texto = arquivo.read_text(encoding="utf-8")
        novo, trocas = padrao.subn(lambda m: f"{m.group(1)} {url}", texto, count=1)
        if trocas != 1:
            raise RuntimeError(f"não achei a linha do link do vídeo em {arquivo.name}")
        if novo != texto:
            arquivo.write_text(novo, encoding="utf-8")
            alterados.append(arquivo.name)
    return alterados


def _tls():
    """Certificados para a conferência. Em rede com inspeção TLS, VIGIA_CA_EXTRA aponta para a cadeia da empresa."""
    extra = os.environ.get("VIGIA_CA_EXTRA", "")
    if not extra or not os.path.exists(extra):
        return True
    contexto = ssl.create_default_context(cafile=certifi.where())
    contexto.load_verify_locations(cafile=extra)
    return contexto


def conferir_acesso_publico(url: str) -> tuple[bool | None, str]:
    """Tenta abrir o link sem login, como uma aba anônima. None = não deu para conferir daqui (rede, proxy)."""
    try:
        if "youtu" in url:
            # O oEmbed do YouTube responde 200 para vídeo público ou não listado e 401/403 para privado.
            r = httpx.get(f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json", timeout=15, verify=_tls())
            return (
                (True, f"YouTube: “{r.json().get('title', '')}”")
                if r.status_code == 200
                else (False, f"YouTube respondeu {r.status_code}: o vídeo parece privado ou inexistente")
            )
        r = httpx.get(url, timeout=15, follow_redirects=True, verify=_tls())
        if "accounts.google.com" in str(r.url) or "ServiceLogin" in str(r.url):
            return False, "o Google pediu login: o arquivo não está com acesso para qualquer pessoa com o link"
        return (r.status_code == 200), f"HTTP {r.status_code}"
    except (httpx.HTTPError, ValueError) as erro:
        return None, f"não foi possível conferir daqui ({type(erro).__name__}); teste numa aba anônima"


def _rodar(*comando: str) -> None:
    subprocess.run(comando, cwd=RAIZ, check=True)  # noqa: S603  # nosec B603 - comandos fixos deste arquivo


def main() -> int:
    parser = argparse.ArgumentParser(description="Fechamento da entrega do VigIA")
    parser.add_argument("--video", help="link público do vídeo pitch (YouTube, Drive ou Vimeo)")
    parser.add_argument("--sem-commit", action="store_true", help="não faz o commit (só arquivos e ZIP)")
    args = parser.parse_args()

    if args.video:
        url = validar_url(args.video)
        ok, detalhe = conferir_acesso_publico(url)
        print(f"link do vídeo: {'abre sem login' if ok else 'ATENÇÃO' if ok is False else 'não conferido'} — {detalhe}")
        if ok is False:
            print(
                "O enunciado não avalia pitch com link privado ou quebrado. Corrija o compartilhamento e rode de novo."
            )
            return 1
        print("link gravado em:", ", ".join(gravar_link(url)) or "(já estava gravado)")

    _rodar(sys.executable, "docs/validacao/consolidar.py")
    _rodar(sys.executable, "docs/pdf/gerar_pdf.py")
    if not args.sem_commit:
        _rodar("git", "add", "-A")  # noqa: S607
        pendente = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=RAIZ, check=False).returncode  # noqa: S603, S607  # nosec
        if pendente:
            _rodar("git", "commit", "-q", "-m", "Fechamento da entrega: link do video, validacao e PDF")  # noqa: S607
    _rodar(sys.executable, "-m", "devops.empacotar")

    falta = []
    if "[A PREENCHER" in README.read_text(encoding="utf-8"):
        falta.append("link do vídeo (rode de novo com --video URL)")
    if "PENDENTE" in (RAIZ / "docs" / "pdf" / "conteudo" / "validacao.md").read_text(encoding="utf-8"):
        falta.append("validação com pessoas reais (preencha docs/validacao/respostas.csv e rode de novo)")
    print("\nFalta:", "; ".join(falta) if falta else "nada — agora é `git push` e enviar o ZIP na plataforma.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
