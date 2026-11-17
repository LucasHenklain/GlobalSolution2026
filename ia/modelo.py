"""Carrega o modelo treinado e calcula a probabilidade de transbordo em 60 min para linhas do gold."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from threadpoolctl import threadpool_limits

from comum.config import carregar_config
from ia.dataset import preparar_variaveis


def pasta_modelos() -> Path:
    """Pasta do modelo e das métricas (ia/modelos, ou VIGIA_MODELOS no Docker)."""
    return carregar_config().modelos


def arquivo_modelo() -> Path:
    return pasta_modelos() / "modelo_transbordo.joblib"


class ModeloAusenteError(RuntimeError):
    """O modelo ainda não foi treinado (rode: python -m ia.treinar)."""


@lru_cache(maxsize=1)
def _carregar(caminho: str, _modificado_em: float) -> dict:
    # joblib só é seguro com arquivo de origem confiável: este é gerado localmente por ia/treinar.py.
    return joblib.load(caminho)


def carregar_pacote(arquivo: Path | None = None) -> dict:
    """Devolve {'modelo', 'variaveis', 'limiares', ...}. Recarrega sozinho se o arquivo for retreinado."""
    arquivo = arquivo or arquivo_modelo()
    if not arquivo.exists():
        raise ModeloAusenteError(f"modelo não encontrado em {arquivo}; rode `python -m ia.treinar`")
    return _carregar(str(arquivo), arquivo.stat().st_mtime)


def prever_probabilidade(fato: pd.DataFrame, pacote: dict | None = None) -> pd.Series:
    """Probabilidade (0 a 1) de o córrego transbordar nos próximos 60 min, para cada linha do gold."""
    pacote = pacote or carregar_pacote()
    if fato.empty:
        return pd.Series(dtype=float, index=fato.index)
    x = preparar_variaveis(fato)[pacote["variaveis"]]
    # Uma thread basta para prever e evita travar quando a máquina (ou o container) está com a CPU disputada.
    with threadpool_limits(limits=1):
        prob = pacote["modelo"].predict_proba(x)[:, 1]
    return pd.Series(prob, index=fato.index)
