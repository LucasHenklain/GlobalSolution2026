"""Executa localmente os MESMOS passos do pipeline de CI (.github/workflows/ci.yml) e guarda a evidência.

Uso:  python -m devops.ci_local              (qualidade + testes; ~1 min)
      python -m devops.ci_local --com-docker (também faz o build da imagem e o teste da pilha inteira)

Por que existe: enquanto o repositório não está no GitHub, esta é a prova de que o pipeline passa. Os registros
ficam em docs/evidencias/ci_local/ (um arquivo por etapa + resumo.md).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "docs" / "evidencias" / "ci_local"
PY = sys.executable
EVENTO = "dados/referencia/eventos_demo/temporal_2025-01-24.csv"

ETAPAS = [
    ("01_lint_ruff", [PY, "-m", "ruff", "check", "."]),
    ("02_seguranca_bandit", [PY, "-m", "bandit", "-q", "-c", "pyproject.toml", "-r", "comum", "dados", "ia", "mvp", "devops"]),
    ("03_dependencias_pip_audit", [PY, "-m", "pip_audit", "-r", "requirements.txt"]),
    (
        "04_testes_pytest",
        [PY, "-m", "pytest", "--cov=comum", "--cov=dados", "--cov=ia", "--cov=mvp", "--cov-report=term", "-v",
         f"--junitxml={SAIDA / 'relatorio-testes.xml'}"],
    ),
]  # fmt: skip
SERVICOS = ["mosquitto", "app", "gateway", "pipeline", "ia", "dashboard"]
ETAPAS_DOCKER = [
    ("05_docker_build", ["docker", "compose", "build"]),
    ("06_docker_up", ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", "900", *SERVICOS]),
    ("07_docker_ps", ["docker", "compose", "ps"]),
    (
        "08_emulador_replay",
        ["docker", "compose", "run", "--rm", "emulador", "python", "-m", "mvp.iot.emulador", "--modo", "replay",
         "--evento", EVENTO, "--velocidade", "4"],
    ),
    (
        "09_fumaca_ponta_a_ponta",
        ["docker", "compose", "exec", "-T", "app", "python", "-m", "devops.verificar_pilha", "--app", "http://localhost:8000",
         "--dashboard", "http://dashboard:8501", "--esperar-alerta", "120"],
    ),
    ("10_monitor", ["docker", "compose", "exec", "-T", "app", "python", "-m", "devops.monitor", "--uma-vez",
                    "--dashboard", "http://dashboard:8501"]),
    ("11_docker_logs", ["docker", "compose", "logs", "--no-color", "--tail", "25"]),
]  # fmt: skip


def rodar(nome: str, comando: list[str]) -> tuple[bool, float]:
    """Executa uma etapa, grava a saída completa em arquivo e devolve (passou?, segundos)."""
    inicio = time.time()
    ambiente = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    r = subprocess.run(
        comando, cwd=RAIZ, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ambiente
    )  # noqa: S603
    duracao = time.time() - inicio
    texto = f"$ {' '.join(str(c) for c in comando)}\n\n{r.stdout}\n{r.stderr}\n[código de saída {r.returncode} em {duracao:.1f} s]\n"
    (SAIDA / f"{nome}.txt").write_text(texto, encoding="utf-8")
    print(f"{'PASSOU' if r.returncode == 0 else 'FALHOU'}  {nome}  ({duracao:.1f} s)")
    return r.returncode == 0, duracao


def main() -> int:
    parser = argparse.ArgumentParser(description="CI local do VigIA")
    parser.add_argument("--com-docker", action="store_true", help="inclui build da imagem e teste da pilha inteira")
    parser.add_argument("--manter-pilha", action="store_true", help="não derruba os containers ao final")
    args = parser.parse_args()
    SAIDA.mkdir(parents=True, exist_ok=True)
    etapas = ETAPAS + (ETAPAS_DOCKER if args.com_docker else [])
    resultados = []
    for nome, comando in etapas:
        passou, duracao = rodar(nome, comando)
        resultados.append((nome, passou, duracao))
        if not passou and nome.startswith(("05", "06")):
            break  # sem imagem ou sem pilha não adianta seguir
    if args.com_docker and not args.manter_pilha:
        rodar("12_docker_down", ["docker", "compose", "down"])
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True
    ).stdout.strip()  # noqa: S603, S607
    linhas = [
        "# Execução local do pipeline de CI",
        "",
        f"Data: {time.strftime('%d/%m/%Y %H:%M')} · commit `{commit}` · mesmos passos de `.github/workflows/ci.yml`.",
        "",
        "| Etapa | Resultado | Duração |",
        "|---|---|---:|",
        *[f"| {nome} | {'passou' if ok else 'FALHOU'} | {duracao:.1f} s |" for nome, ok, duracao in resultados],
    ]
    (SAIDA / "resumo.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return 0 if all(ok for _, ok, _ in resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
