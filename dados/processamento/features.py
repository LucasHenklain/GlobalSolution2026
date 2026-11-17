"""Variáveis derivadas (features) das leituras, em janelas de 10 minutos.

Esta é a função mais importante da integração: o MESMO código gera as colunas usadas para treinar a IA
(histórico) e as usadas em tempo real (sensores). Assim o modelo nunca recebe em produção algo calculado
de um jeito diferente do que viu no treino.
"""

from __future__ import annotations

import pandas as pd

from comum.estacoes import Estacao

JANELA = "10min"
PASSOS = {"chuva_30min": 3, "chuva_1h": 6, "chuva_3h": 18, "chuva_24h": 144, "chuva_72h": 432}
BURACO_MAXIMO = pd.Timedelta(hours=6)  # acima disso consideramos séries separadas (ex.: outro dia de demonstração)

COLUNAS = [
    "estacao_id",
    "medido_em",
    "nivel_cm",
    "chuva_mm",
    "bateria_pct",
    "nivel_pct_cota",
    *PASSOS.keys(),
    "delta_nivel_10min",
    "delta_nivel_30min",
    "estado_regra",
    "recebido_em",
    "fonte",
]


def _grade_de_10min(trecho: pd.DataFrame) -> pd.DataFrame:
    """Alinha as leituras em janelas fixas de 10 min: último nível da janela, chuva somada."""
    por_janela = trecho.set_index("medido_em").resample(JANELA)
    grade = pd.DataFrame(
        {
            "nivel_cm": por_janela["nivel_cm"].last(),
            "chuva_mm": por_janela["chuva_mm"].sum(),
            "bateria_pct": por_janela["bateria_pct"].last(),
            "recebido_em": por_janela["recebido_em"].max(),
            "fonte": por_janela["origem"].last(),  # de onde veio a leitura: wokwi, emulador, replay ou historico
        }
    )
    # Leitura perdida: repete o último nível por no máximo 30 min; depois disso é "sem dado" e a linha cai.
    grade["nivel_cm"] = grade["nivel_cm"].ffill(limit=3)
    grade["bateria_pct"] = grade["bateria_pct"].ffill(limit=3)
    grade["fonte"] = grade["fonte"].ffill(limit=3)
    return grade.dropna(subset=["nivel_cm"])


def _features_do_trecho(trecho: pd.DataFrame, est: Estacao) -> pd.DataFrame:
    grade = _grade_de_10min(trecho)
    for nome, passos in PASSOS.items():
        grade[nome] = grade["chuva_mm"].rolling(passos, min_periods=1).sum()
    grade["delta_nivel_10min"] = grade["nivel_cm"].diff(1).fillna(0.0)
    grade["delta_nivel_30min"] = grade["nivel_cm"].diff(3).fillna(grade["delta_nivel_10min"])
    grade["nivel_pct_cota"] = grade["nivel_cm"] / est.cota_transbordo_cm * 100
    grade["estado_regra"] = grade["nivel_cm"].map(est.estado_regra)
    grade["estacao_id"] = est.estacao_id
    return grade.reset_index()


def calcular_features(leituras: pd.DataFrame, estacoes: dict[str, Estacao]) -> pd.DataFrame:
    """Recebe leituras do silver (uma ou várias estações) e devolve uma linha por estação × janela de 10 min."""
    if leituras.empty:
        return pd.DataFrame(columns=COLUNAS)
    partes = []
    for estacao_id, da_estacao in leituras.sort_values("medido_em").groupby("estacao_id"):
        # Séries separadas por um buraco grande não podem somar chuva uma da outra.
        trecho_id = (da_estacao["medido_em"].diff() > BURACO_MAXIMO).cumsum()
        for _, trecho in da_estacao.groupby(trecho_id):
            partes.append(_features_do_trecho(trecho, estacoes[estacao_id]))
    resultado = pd.concat(partes, ignore_index=True)
    return resultado[COLUNAS].sort_values(["estacao_id", "medido_em"]).reset_index(drop=True)
