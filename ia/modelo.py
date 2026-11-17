"""Carrega o modelo treinado e calcula a probabilidade de transbordo em 60 min para linhas do gold."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd

from comum.config import RAIZ
from ia.dataset import preparar_variaveis

PASTA_MODELOS = RAIZ / "ia" / "modelos"
ARQUIVO_MODELO = PASTA_MODELOS / "modelo_transbordo.joblib"


class ModeloAusenteError(RuntimeError):
    """O modelo ainda não foi treinado (rode: python -m ia.treinar)."""


@lru_cache(maxsize=1)
def _carregar(caminho: str, _modificado_em: float) -> dict:
    # joblib só é seguro com arquivo de origem confiável: este é gerado localmente por ia/treinar.py.
    return joblib.load(caminho)


def carregar_pacote(arquivo: Path = ARQUIVO_MODELO) -> dict:
    """Devolve {'modelo', 'variaveis', 'limiares', ...}. Recarrega sozinho se o arquivo for retreinado."""
    if not arquivo.exists():
        raise ModeloAusenteError(f"modelo não encontrado em {arquivo}; rode `python -m ia.treinar`")
    return _carregar(str(arquivo), arquivo.stat().st_mtime)


def prever_probabilidade(fato: pd.DataFrame, pacote: dict | None = None) -> pd.Series:
    """Probabilidade (0 a 1) de o córrego transbordar nos próximos 60 min, para cada linha do gold."""
    pacote = pacote or carregar_pacote()
    if fato.empty:
        return pd.Series(dtype=float, index=fato.index)
    x = preparar_variaveis(fato)[pacote["variaveis"]]
    return pd.Series(pacote["modelo"].predict_proba(x)[:, 1], index=fato.index)
