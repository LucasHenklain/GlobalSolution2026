"""Camada BRONZE: o dado bruto, exatamente como chegou, com manifesto de linhagem (origem, hash, data de entrada)."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pandas as pd

from comum.config import RAIZ, carregar_config
from comum.estacoes import carregar_estacoes
from comum.log import obter_logger
from dados import camadas
from dados.simulacao.hidrologia import simular_estacao

log = obter_logger("dados.bronze")
FONTE_INMET = RAIZ / "dados" / "fontes" / "inmet"
URL_INMET = "https://portal.inmet.gov.br/dadoshistoricos"


def ingerir_inmet() -> int:
    """Copia os CSV originais do INMET para bronze/inmet sem alterar um byte."""
    destino = camadas.caminho("bronze", "inmet")
    novos = []
    for origem in sorted(FONTE_INMET.glob("*.CSV")):
        alvo = destino / origem.name
        if alvo.exists():
            continue
        shutil.copy2(origem, alvo)
        novos.append(
            {
                "arquivo": origem.name,
                "fonte": URL_INMET,
                "sha256": camadas.sha256_arquivo(alvo),
                "bytes": alvo.stat().st_size,
                "ingerido_em": camadas.agora_iso(),
            }
        )
    camadas.registrar_manifesto(destino, novos)
    log.info("bronze inmet", extra={"dados": {"arquivos_novos": len(novos)}})
    return len(novos)


def gerar_sensores_simulados(chuva_inmet: pd.DataFrame) -> int:
    """Gera o histórico das estações (nível simulado sobre chuva real) e grava como se tivesse chegado dos sensores."""
    total = 0
    for est in carregar_estacoes().values():
        serie = chuva_inmet[chuva_inmet["estacao_inmet"] == est.inmet].set_index("medido_em")["chuva_mm"]
        leituras = simular_estacao(serie, est)
        leituras["origem"] = "historico"
        for ano, parte in leituras.groupby(leituras["medido_em"].dt.year):
            camadas.escrever_parquet(
                parte,
                camadas.caminho("bronze", "sensores_simulados", f"estacao={est.estacao_id}", f"ano={ano}.parquet"),
            )
        total += len(leituras)
    log.info("bronze sensores simulados", extra={"dados": {"leituras": total}})
    return total


def ingerir_sensores() -> list[Path]:
    """Move os micro-lotes do gateway (landing) para o bronze. Mover, e não copiar, evita ingerir duas vezes."""
    landing = camadas.caminho("landing", "sensores")
    novos, entradas = [], []
    for lote in sorted(landing.glob("*/*.jsonl")):
        alvo = camadas.caminho("bronze", "sensores", f"data={lote.parent.name}", lote.name)
        try:
            camadas.substituir_atomico(lote, alvo, tentativas=3)
        except PermissionError:
            continue  # o gateway ainda está com o arquivo aberto: fica para o próximo ciclo
        novos.append(alvo)
        entradas.append(
            {
                "arquivo": f"data={lote.parent.name}/{lote.name}",
                "fonte": "gateway_mqtt",
                "sha256": camadas.sha256_arquivo(alvo),
                "bytes": alvo.stat().st_size,
                "ingerido_em": camadas.agora_iso(),
            }
        )
    camadas.registrar_manifesto(camadas.caminho("bronze", "sensores"), entradas)
    return novos


def ingerir_ocorrencias() -> int | None:
    """Busca no app as ocorrências relatadas pelos moradores (sem dados pessoais) e guarda o extrato bruto."""
    cfg = carregar_config()
    try:
        resposta = httpx.get(
            f"{cfg.app_url}/api/interno/ocorrencias",
            params={"desde": "2000-01-01T00:00:00Z"},
            headers={"X-Token-Interno": cfg.token_interno},
            timeout=5,
        )
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        # Sem o app no ar o pipeline segue: os sensores não podem depender do site.
        log.warning("app indisponível para ocorrências", extra={"dados": {"erro": type(erro).__name__}})
        return None
    dados = resposta.json()
    ocorrencias = dados["ocorrencias"] if isinstance(dados, dict) else dados
    camadas.escrever_json(
        {"extraido_em": camadas.agora_iso(), "ocorrencias": ocorrencias},
        camadas.caminho("bronze", "ocorrencias", "extrato.json"),
    )
    return len(ocorrencias)
