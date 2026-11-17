"""Monta a base de aprendizado da IA a partir do GOLD do pipeline (a IA não tem dado próprio: usa o do data lake)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from comum.estacoes import Estacao, carregar_estacoes
from dados import camadas

HORIZONTE_PASSOS = 6  # 6 janelas de 10 min = 60 minutos à frente

# Variáveis que o modelo enxerga. Todas saem de dados/processamento/features.py (mesmas no treino e ao vivo).
VARIAVEIS = [
    "nivel_pct_cota",  # nível atual em % da cota de transbordo
    "subida_10min_pct",  # quanto o nível subiu em 10 min (em pontos % da cota)
    "subida_30min_pct",  # idem em 30 min
    "projecao_30min_pct",  # onde o nível estará em 30 min se continuar subindo no mesmo ritmo
    "chuva_mm",  # chuva na janela atual de 10 min
    "chuva_30min",
    "chuva_1h",
    "chuva_3h",
    "chuva_24h",  # solo encharcado escoa mais
    "chuva_72h",
    "estacao_codigo",  # cada córrego responde num ritmo próprio
]


def codigo_da_estacao(estacao_id: str, estacoes: dict[str, Estacao]) -> int:
    """Número estável por estação (posição no catálogo ordenado)."""
    return sorted(estacoes).index(estacao_id)


def preparar_variaveis(fato: pd.DataFrame, estacoes: dict[str, Estacao] | None = None) -> pd.DataFrame:
    """Converte linhas do gold (fato_leitura) nas colunas de entrada do modelo."""
    estacoes = estacoes or carregar_estacoes()
    cota = fato["estacao_id"].map({k: e.cota_transbordo_cm for k, e in estacoes.items()})
    x = pd.DataFrame(index=fato.index)
    x["nivel_pct_cota"] = fato["nivel_pct_cota"]
    x["subida_10min_pct"] = fato["delta_nivel_10min"] / cota * 100
    x["subida_30min_pct"] = fato["delta_nivel_30min"] / cota * 100
    x["projecao_30min_pct"] = x["nivel_pct_cota"] + 3 * x["subida_10min_pct"].clip(lower=0)
    for coluna in ("chuva_mm", "chuva_30min", "chuva_1h", "chuva_3h", "chuva_24h", "chuva_72h"):
        x[coluna] = fato[coluna]
    x["estacao_codigo"] = fato["estacao_id"].map({k: codigo_da_estacao(k, estacoes) for k in estacoes})
    return x[VARIAVEIS]


def rotular(fato: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta o alvo: 'vai transbordar nos próximos 60 min?' (1/0) e 'já está transbordando?'."""
    fato = fato.sort_values(["estacao_id", "medido_em"]).reset_index(drop=True)
    acima = fato["estado_regra"] == "transbordo"
    por_estacao = acima.groupby(fato["estacao_id"])
    # Olha as 6 janelas seguintes da mesma estação: alguma está acima da cota?
    futuro = pd.concat([por_estacao.shift(-k) for k in range(1, HORIZONTE_PASSOS + 1)], axis=1).fillna(False)
    fato["ja_transbordando"] = acima
    fato["alvo"] = (futuro.any(axis=1) & ~acima).astype(int)
    return fato


def carregar_historico() -> pd.DataFrame:
    """Lê o gold histórico (chuva real INMET + nível simulado) já rotulado."""
    fato = camadas.ler_parquet(camadas.caminho("gold", "fato_leitura", "origem=historico", "dados.parquet"))
    return rotular(fato)


def separar_por_tempo(fato: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Treino 2019–2022, validação 2023 (escolha do limiar), teste 2024–2025 (números reportados).

    Separar por TEMPO, e não ao acaso, é o que impede o modelo de "colar" olhando o futuro.
    """
    ano = fato["medido_em"].dt.year
    return fato[ano <= 2022], fato[ano == 2023], fato[ano >= 2024]


def amostra_de_treino(treino: pd.DataFrame, semente: int = 42) -> pd.DataFrame:
    """Mais de 99% das janelas são de tempo seco. Mantemos todas as com chuva/nível alto e 3% das demais."""
    rng = np.random.default_rng(semente)
    relevante = (treino["chuva_3h"] > 0) | (treino["nivel_pct_cota"] > 35) | (rng.random(len(treino)) < 0.03)
    return treino[relevante & ~treino["ja_transbordando"]]
