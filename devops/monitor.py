"""Monitoramento do VigIA: saúde do app e do dashboard e batimento do gateway, do pipeline e da IA.

Uso:  python -m devops.monitor              (uma linha de status a cada 10 s)
      python -m devops.monitor --uma-vez    (uma checagem; código de saída 1 se algo estiver fora do ar)

Cada serviço em segundo plano grava um arquivo de "batimento" a cada ciclo; se o arquivo envelhece, o serviço parou.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime

import httpx
import pandas as pd

from comum.config import carregar_config
from comum.log import obter_logger
from dados import camadas

log = obter_logger("devops.monitor")
IDADE_MAXIMA_S = 60


def _http(url: str) -> str:
    try:
        return "ok" if httpx.get(url, timeout=3).status_code == 200 else "erro"
    except httpx.HTTPError:
        return "fora do ar"


def _batimento(arquivo) -> str:
    dados = camadas.ler_json(arquivo)
    if not dados:
        return "sem sinal"
    carimbo = dados.get("em") or dados.get("atualizado_em")  # o gateway chama o campo de atualizado_em
    idade = (datetime.now(UTC) - pd.Timestamp(carimbo).to_pydatetime()).total_seconds()
    return "ok" if idade <= IDADE_MAXIMA_S else f"parado há {idade:.0f} s"


def checar(dashboard_url: str) -> dict:
    cfg = carregar_config()
    lake = cfg.lake
    return {
        "app": _http(f"{cfg.app_url}/health"),
        "dashboard": _http(f"{dashboard_url}/_stcore/health"),
        "gateway_mqtt": _batimento(lake / "landing" / "_gateway_batimento.json"),
        "pipeline": _batimento(lake / "gold" / "_pipeline_batimento.json"),
        "ia": _batimento(lake / "gold" / "_ia_batimento.json"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor do VigIA")
    parser.add_argument("--dashboard", default="http://localhost:8501")
    parser.add_argument("--intervalo", type=float, default=10.0)
    parser.add_argument("--uma-vez", action="store_true")
    args = parser.parse_args()
    while True:
        estado = checar(args.dashboard)
        saudavel = all(v == "ok" for v in estado.values())
        (log.info if saudavel else log.warning)("saúde", extra={"dados": {**estado, "saudavel": saudavel}})
        if args.uma_vez:
            return 0 if saudavel else 1
        time.sleep(args.intervalo)


if __name__ == "__main__":
    sys.exit(main())
