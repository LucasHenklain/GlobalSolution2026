"""Medidas analíticas do VigIA (equivalentes a medidas DAX do Power BI, escritas em Python/pandas).

Cada função recebe tabelas do GOLD já filtradas pelo contexto (período, estações, nível de risco) — o mesmo papel
do "contexto de filtro" do DAX — e devolve um número. A docstring traz a medida DAX equivalente; o arquivo
dados/powerbi/medidas.dax reúne todas, para quem quiser montar o mesmo painel no Power BI.
"""

from __future__ import annotations

import pandas as pd

MIN_POR_JANELA = 10
NIVEIS_DE_ALERTA = ("laranja", "vermelho")
JANELA_ANTECEDENCIA = pd.Timedelta(hours=3)


def chuva_acumulada_mm(fato_leitura: pd.DataFrame) -> float:
    """Chuva Acumulada = SUM(fato_leitura[chuva_mm]) — média entre as estações selecionadas."""
    if fato_leitura.empty:
        return 0.0
    return float(fato_leitura.groupby("estacao_id")["chuva_mm"].sum().mean())


def nivel_maximo_pct(fato_leitura: pd.DataFrame) -> float:
    """Nível Máximo % = MAX(fato_leitura[nivel_pct_cota])"""
    return float(fato_leitura["nivel_pct_cota"].max()) if len(fato_leitura) else 0.0


def horas_acima_da_cota_de_alerta(fato_leitura: pd.DataFrame) -> float:
    """Horas em Alerta = DIVIDE(COUNTROWS(FILTER(fato_leitura, [estado_regra] IN {"alerta","transbordo"})) * 10, 60)"""
    return float(fato_leitura["estado_regra"].isin(["alerta", "transbordo"]).sum() * MIN_POR_JANELA / 60)


def eventos_de_transbordo(fato_evento: pd.DataFrame) -> int:
    """Eventos de Transbordo = COUNTROWS(fato_evento)"""
    return int(len(fato_evento))


def alertas_emitidos(fato_alerta: pd.DataFrame, niveis: tuple[str, ...] = NIVEIS_DE_ALERTA) -> int:
    """Alertas Emitidos = CALCULATE(COUNTROWS(fato_alerta), fato_alerta[nivel_risco] IN {"laranja","vermelho"})"""
    return int(fato_alerta["nivel_risco"].isin(niveis).sum()) if len(fato_alerta) else 0


def antecedencia_por_evento(fato_evento: pd.DataFrame, fato_alerta: pd.DataFrame) -> pd.Series:
    """Para cada transbordo, minutos entre o primeiro alerta laranja/vermelho (nas 3 h anteriores) e o início.

    Evento sem alerta anterior recebe 0. É a base das duas medidas seguintes.
    """
    if fato_evento.empty:
        return pd.Series(dtype=float)
    alertas = fato_alerta[fato_alerta["nivel_risco"].isin(NIVEIS_DE_ALERTA)] if len(fato_alerta) else fato_alerta
    minutos = []
    for evento in fato_evento.itertuples():
        antes = (
            alertas[
                (alertas["estacao_id"] == evento.estacao_id)
                & (alertas["emitido_em"] < evento.inicio)
                & (alertas["emitido_em"] >= evento.inicio - JANELA_ANTECEDENCIA)
            ]
            if len(alertas)
            else alertas
        )
        minutos.append((evento.inicio - antes["emitido_em"].min()).total_seconds() / 60 if len(antes) else 0.0)
    return pd.Series(minutos, index=fato_evento.index)


def antecedencia_mediana_min(fato_evento: pd.DataFrame, fato_alerta: pd.DataFrame) -> float:
    """Antecedência Mediana (min) = MEDIANX(fato_evento, DATEDIFF([primeiro_alerta], fato_evento[inicio], MINUTE))"""
    serie = antecedencia_por_evento(fato_evento, fato_alerta)
    return float(serie.median()) if len(serie) else 0.0


def taxa_eventos_avisados_pct(fato_evento: pd.DataFrame, fato_alerta: pd.DataFrame, minimo_min: float = 30) -> float:
    """% Eventos Avisados = DIVIDE(COUNTROWS(FILTER(fato_evento, [antecedencia_min] >= 30)), COUNTROWS(fato_evento))"""
    serie = antecedencia_por_evento(fato_evento, fato_alerta)
    return float((serie >= minimo_min).mean() * 100) if len(serie) else 0.0


def disponibilidade_sensores_pct(fato_leitura: pd.DataFrame) -> float:
    """Disponibilidade % = DIVIDE(COUNTROWS(fato_leitura), [Janelas Esperadas])

    Janelas esperadas = uma a cada 10 min, por estação, entre a primeira e a última leitura do contexto.
    """
    if fato_leitura.empty:
        return 0.0
    por_estacao = fato_leitura.groupby("estacao_id")["medido_em"].agg(["min", "max", "count"])
    esperadas = ((por_estacao["max"] - por_estacao["min"]).dt.total_seconds() / 600 + 1).sum()
    return float(min(por_estacao["count"].sum() / esperadas * 100, 100.0))


def moradores_em_area_de_risco(situacao_por_estacao: pd.DataFrame) -> int:
    """Moradores em Risco = SUMX(FILTER(dim_estacao, [risco_atual] IN {"laranja","vermelho"}), [moradores_area])"""
    em_risco = situacao_por_estacao[situacao_por_estacao["nivel_risco"].isin(NIVEIS_DE_ALERTA)]
    return int(em_risco["moradores_area"].sum())


def ocorrencias_abertas(fato_ocorrencia: pd.DataFrame) -> int:
    """Ocorrências Abertas = CALCULATE(COUNTROWS(fato_ocorrencia), fato_ocorrencia[status] <> "resolvida")"""
    return int((fato_ocorrencia["status"] != "resolvida").sum()) if len(fato_ocorrencia) else 0


def variacao_pct(atual: float, anterior: float) -> float | None:
    """Variação % = DIVIDE([Medida] - [Medida Período Anterior], [Medida Período Anterior])

    No DAX o período anterior sai de CALCULATE([Medida], DATEADD(dim_data[data], -N, DAY)).
    """
    if not anterior:
        return None
    return (atual - anterior) / anterior * 100


def indice_de_prioridade(prob_maxima: float, nivel_max_pct: float, n_ocorrencias_abertas: int) -> float:
    """Índice de Prioridade (0–100): onde a Defesa Civil deve agir primeiro.

    Prioridade = 60 * [Prob Máxima IA] + 0.30 * MIN([Nível Máximo %], 100) + 2 * MIN([Ocorrências Abertas], 5)
    Pesos: a previsão da IA vale mais (antecipa), o nível confirma, e bueiro entupido agrava.
    """
    prob = 0.0 if pd.isna(prob_maxima) else float(prob_maxima)
    return round(60 * prob + 0.30 * min(float(nivel_max_pct), 100.0) + 2 * min(int(n_ocorrencias_abertas), 5), 1)


def tabela_de_prioridade(
    fato_leitura: pd.DataFrame, fato_risco: pd.DataFrame, fato_ocorrencia: pd.DataFrame, dim_estacao: pd.DataFrame
) -> pd.DataFrame:
    """Uma linha por estação com os componentes e o índice de prioridade, da mais urgente para a menos."""
    nivel = fato_leitura.groupby("estacao_id")["nivel_pct_cota"].max().rename("nivel_max_pct")
    chuva = fato_leitura.groupby("estacao_id")["chuva_mm"].sum().rename("chuva_mm")
    prob = fato_risco.groupby("estacao_id")["prob_transbordo_60min"].max().rename("prob_maxima")
    abertas = (
        fato_ocorrencia[fato_ocorrencia["status"] != "resolvida"]
        .groupby("estacao_id")
        .size()
        .rename("ocorrencias_abertas")
        if len(fato_ocorrencia)
        else pd.Series(dtype=int, name="ocorrencias_abertas")
    )
    tabela = dim_estacao.set_index("estacao_id")[["nome", "bairro", "moradores_area"]].join(
        [nivel, chuva, prob, abertas]
    )
    tabela = tabela.dropna(subset=["nivel_max_pct"]).fillna({"ocorrencias_abertas": 0, "prob_maxima": 0.0})
    tabela["prioridade"] = [
        indice_de_prioridade(p, n, o)
        for p, n, o in zip(tabela["prob_maxima"], tabela["nivel_max_pct"], tabela["ocorrencias_abertas"], strict=True)
    ]
    return tabela.sort_values("prioridade", ascending=False).reset_index()
