"""Teste de fumaça da pilha no ar: confere a saúde dos serviços e, opcionalmente, espera um alerta chegar ao app.

Uso:  python -m devops.verificar_pilha [--app URL] [--dashboard URL] [--esperar-alerta SEGUNDOS]

É o que a CI executa depois do `docker compose up`: prova que sensor → pipeline → IA → app funcionou de ponta a ponta.
Sai com código 0 se tudo estiver bem e 1 se algo falhar.
"""

from __future__ import annotations

import argparse
import sys
import time

import httpx

from comum.config import carregar_config


def _checar(nome: str, url: str, valida) -> bool:
    try:
        resposta = httpx.get(url, timeout=5)
        ok = resposta.status_code == 200 and valida(resposta)
    except httpx.HTTPError as erro:
        print(f"[FALHOU] {nome}: {type(erro).__name__}")
        return False
    print(f"[{'OK' if ok else 'FALHOU'}] {nome}: HTTP {resposta.status_code}")
    return ok


def alertas_recebidos(app: str) -> int:
    """Lê do /metrics do app o contador de alertas recebidos da IA."""
    for linha in httpx.get(f"{app}/metrics", timeout=5).text.splitlines():
        if linha.startswith("vigia_alertas_recebidos_total"):
            return int(float(linha.split()[-1]))
    return 0


def esperar_alerta(app: str, segundos: int) -> bool:
    """Aguarda a IA entregar ao menos um alerta ao app (sensor → gateway → pipeline → IA → app)."""
    limite = time.time() + segundos
    while time.time() < limite:
        total = alertas_recebidos(app)
        if total > 0:
            print(f"[OK] fluxo de ponta a ponta: {total} alerta(s) da IA chegaram ao app")
            return True
        time.sleep(3)
    print(f"[FALHOU] nenhum alerta chegou ao app em {segundos} s")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Teste de fumaça da pilha do VigIA")
    parser.add_argument("--app", default=carregar_config().app_url)
    parser.add_argument("--dashboard", default="http://localhost:8501")
    parser.add_argument("--esperar-alerta", type=int, default=0, metavar="SEGUNDOS")
    args = parser.parse_args()
    resultados = [
        _checar("app /health", f"{args.app}/health", lambda r: r.json().get("status") == "ok"),
        _checar("app /status.txt", f"{args.app}/status.txt", lambda r: len(r.text) > 0),
        _checar("app /metrics", f"{args.app}/metrics", lambda r: "vigia_" in r.text),
        _checar("dashboard", f"{args.dashboard}/_stcore/health", lambda r: r.text.strip() == "ok"),
    ]
    if args.esperar_alerta:
        resultados.append(esperar_alerta(args.app, args.esperar_alerta))
    return 0 if all(resultados) else 1


if __name__ == "__main__":
    sys.exit(main())
