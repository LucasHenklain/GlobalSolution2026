"""Caminhos e utilitários de leitura/escrita das camadas do data lake (bronze, silver, gold, quarentena)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from comum.config import carregar_config

CAMADAS = ("landing", "bronze", "silver", "gold", "quarentena")


def raiz_lake() -> Path:
    return carregar_config().lake


def caminho(camada: str, *partes: str) -> Path:
    """Monta um caminho dentro de uma camada, criando a pasta-mãe se preciso."""
    if camada not in CAMADAS:
        raise ValueError(f"camada desconhecida: {camada}")
    p = raiz_lake().joinpath(camada, *partes)
    (p if not p.suffix else p.parent).mkdir(parents=True, exist_ok=True)
    return p


def agora_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def substituir_atomico(temporario: Path, destino: Path, tentativas: int = 20) -> None:
    """Troca o arquivo de uma vez só. No Windows a troca falha se outro processo estiver lendo: tenta de novo."""
    for i in range(tentativas):
        try:
            os.replace(temporario, destino)
            return
        except PermissionError:
            if i == tentativas - 1:
                raise
            time.sleep(0.15)


def escrever_parquet(df: pd.DataFrame, destino: Path) -> Path:
    """Grava Parquet de forma atômica: quem lê (dashboard, IA) nunca enxerga um arquivo pela metade."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    df.to_parquet(temporario, index=False)
    substituir_atomico(temporario, destino)
    return destino


def ler_parquet(destino: Path, tentativas: int = 20) -> pd.DataFrame:
    """Lê um Parquet tolerando a janela em que o arquivo está sendo trocado por outro processo."""
    for i in range(tentativas):
        try:
            return pd.read_parquet(destino)
        except (PermissionError, OSError):
            if i == tentativas - 1:
                raise
            time.sleep(0.15)
    raise RuntimeError("inalcançável")


def escrever_json(dados: dict | list, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    substituir_atomico(temporario, destino)
    return destino


def ler_json(destino: Path, padrao=None):
    if not destino.exists():
        return padrao
    return json.loads(destino.read_text(encoding="utf-8"))


def sha256_arquivo(arquivo: Path) -> str:
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def registrar_manifesto(pasta: Path, entradas: list[dict]) -> None:
    """O bronze é imutável; o manifesto guarda de onde veio cada arquivo, o hash e quando entrou (linhagem)."""
    if not entradas:
        return
    arquivo = pasta / "_manifesto.json"
    atual = ler_json(arquivo, padrao=[])
    conhecidos = {e["arquivo"] for e in atual}
    atual.extend(e for e in entradas if e["arquivo"] not in conhecidos)
    escrever_json(atual, arquivo)
