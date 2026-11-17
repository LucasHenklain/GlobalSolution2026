"""Como medimos se um jeito de alertar é bom: por EVENTO de transbordo, não só por linha.

Para o morador importam três perguntas:
  1. Fui avisado antes de a água subir? (eventos avisados)
  2. Com quanto tempo de antecedência? (minutos entre o início do alerta e o transbordo)
  3. Quantas vezes o alerta tocou à toa? (alarmes falsos — alerta demais faz as pessoas pararem de confiar)
A mesma régua é aplicada à regra de limiar fixo ("antes") e à IA ("depois").
"""

from __future__ import annotations

import numpy as np
import pandas as pd

PASSO_MIN = 10
JANELA_MAXIMA = 18  # só conta antecedência de até 3 h
TOLERANCIA_BURACO = 1  # o alerta pode "piscar" por uma janela sem ser considerado encerrado
SEPARACAO_EVENTOS = 12  # transbordos a menos de 2 h um do outro são o mesmo evento
JUNTAR_EPISODIOS = 3  # alertas a menos de 30 min um do outro são o mesmo episódio
FOLGA_APOS_EPISODIO = 6  # o alerta foi correto se o transbordo veio até 60 min depois dele


def _inicios_de_evento(acima: np.ndarray) -> list[int]:
    """Posições em que começa um transbordo novo (sem transbordo nas 2 h anteriores)."""
    inicios = []
    for i in np.flatnonzero(acima & ~np.r_[False, acima[:-1]]):
        if not acima[max(0, i - SEPARACAO_EVENTOS) : i].any():
            inicios.append(int(i))
    return inicios


def _antecedencia(alerta: np.ndarray, inicio: int) -> int:
    """Minutos de alerta contínuo imediatamente antes do transbordo (0 = o morador não foi avisado antes)."""
    primeiro, buracos = None, 0
    i = inicio - 1
    while i >= 0 and inicio - i <= JANELA_MAXIMA:
        if alerta[i]:
            primeiro, buracos = i, 0
        else:
            buracos += 1
            if buracos > TOLERANCIA_BURACO:
                break
        i -= 1
    return 0 if primeiro is None else (inicio - primeiro) * PASSO_MIN


def _episodios_de_alerta(alerta: np.ndarray, acima: np.ndarray) -> tuple[int, int]:
    """Conta os episódios de alerta fora de transbordo e quantos deles foram falsos."""
    posicoes = np.flatnonzero(alerta & ~acima)
    if len(posicoes) == 0:
        return 0, 0
    episodios = np.split(posicoes, np.flatnonzero(np.diff(posicoes) > JUNTAR_EPISODIOS) + 1)
    falsos = sum(1 for ep in episodios if not acima[ep[0] : ep[-1] + FOLGA_APOS_EPISODIO + 1].any())
    return len(episodios), falsos


def avaliar_politica(fato: pd.DataFrame, alerta: pd.Series) -> dict:
    """fato: gold rotulado (ia.dataset.rotular); alerta: True onde a política manteria o alerta ligado."""
    dados = fato.assign(_alerta=alerta.to_numpy(dtype=bool))
    antecedencias, episodios, falsos = [], 0, 0
    for _, serie in dados.groupby("estacao_id", sort=True):
        serie = serie.sort_values("medido_em")
        acima = serie["ja_transbordando"].to_numpy(dtype=bool)
        ligado = serie["_alerta"].to_numpy(dtype=bool)
        antecedencias += [_antecedencia(ligado, i) for i in _inicios_de_evento(acima)]
        n, f = _episodios_de_alerta(ligado, acima)
        episodios, falsos = episodios + n, falsos + f

    antecedencias = np.array(antecedencias)
    anos = (dados["medido_em"].max() - dados["medido_em"].min()).days / 365.25
    estacoes = dados["estacao_id"].nunique()

    # Métricas clássicas por linha (janela de 10 min), fora dos momentos em que já está transbordando.
    util = dados[~dados["ja_transbordando"]]
    vp = int((util["_alerta"] & (util["alvo"] == 1)).sum())
    fp = int((util["_alerta"] & (util["alvo"] == 0)).sum())
    fn = int((~util["_alerta"] & (util["alvo"] == 1)).sum())
    precisao = vp / (vp + fp) if vp + fp else 0.0
    recall = vp / (vp + fn) if vp + fn else 0.0

    return {
        "eventos": int(len(antecedencias)),
        "avisados_pct": round(float((antecedencias >= 10).mean() * 100), 1) if len(antecedencias) else 0.0,
        "avisados_30min_pct": round(float((antecedencias >= 30).mean() * 100), 1) if len(antecedencias) else 0.0,
        "antecedencia_mediana_min": float(np.median(antecedencias)) if len(antecedencias) else 0.0,
        "antecedencia_media_min": round(float(antecedencias.mean()), 1) if len(antecedencias) else 0.0,
        "episodios_de_alerta": int(episodios),
        "alarmes_falsos": int(falsos),
        "alarmes_falsos_por_estacao_ano": round(falsos / max(anos * estacoes, 1e-9), 1),
        "precisao": round(precisao, 3),
        "recall": round(recall, 3),
        "f1": round(2 * precisao * recall / (precisao + recall), 3) if precisao + recall else 0.0,
    }


def alerta_da_regra(fato: pd.DataFrame) -> pd.Series:
    """O 'antes': alerta ligado quando o nível passa da cota de alerta (a regra fixa que roda na estação)."""
    return fato["estado_regra"].isin(["alerta", "transbordo"])
