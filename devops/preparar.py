"""Prepara o VigIA para rodar: histórico do data lake, modelo de IA, alertas retroativos e usuários de demonstração.

Uso:  python -m devops.preparar          (pula o que já existe; leva ~3 min na primeira vez)
      python -m devops.preparar --refazer (refaz tudo)

É o primeiro passo do README e o serviço "preparo" do docker-compose: depois dele, cada área roda sozinha.
"""

from __future__ import annotations

import argparse
import subprocess  # nosec B404
import sys
import time

from comum.log import obter_logger
from dados import camadas, pipeline
from ia import servico, treinar
from ia.modelo import arquivo_modelo

log = obter_logger("devops.preparar")


def _etapa(nome: str, pular: bool, funcao) -> None:
    if pular:
        log.info(f"{nome}: já existe, pulando")
        return
    inicio = time.time()
    funcao()
    log.info(f"{nome}: pronto", extra={"dados": {"segundos": round(time.time() - inicio, 1)}})


def main() -> None:
    parser = argparse.ArgumentParser(description="Preparação do VigIA")
    parser.add_argument("--refazer", action="store_true", help="refaz o histórico e o modelo mesmo que já existam")
    args = parser.parse_args()
    gold = camadas.raiz_lake() / "gold"
    tem_historico = (gold / "fato_leitura" / "origem=historico" / "dados.parquet").exists()
    tem_retroativo = (gold / "fato_alerta" / "origem=historico" / "dados.parquet").exists()

    _etapa(
        "1/4 data lake histórico (INMET → bronze → silver → gold)",
        tem_historico and not args.refazer,
        pipeline.rodar_historico,
    )
    _etapa("2/4 treino e avaliação da IA", arquivo_modelo().exists() and not args.refazer, treinar.main)
    _etapa("3/4 alertas retroativos para o dashboard", tem_retroativo and not args.refazer, servico.rodar_retroativo)

    # O seed do app é idempotente: cria as tabelas e os usuários de demonstração só se faltarem.
    _etapa(
        "4/4 banco do app e usuários de demonstração",
        False,
        lambda: subprocess.run([sys.executable, "-m", "mvp.web.seed"], check=True),  # noqa: S603 - comando fixo # nosec B603
    )
    log.info("VigIA preparado")


if __name__ == "__main__":
    main()
