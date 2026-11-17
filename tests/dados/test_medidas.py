"""Medidas analíticas (estilo DAX) usadas nos indicadores do dashboard."""

import pandas as pd

from dados import medidas


def _t(texto):
    return pd.Timestamp(texto, tz="UTC")


EVENTOS = pd.DataFrame(
    {"estacao_id": ["EST-ARI-01", "EST-PIR-01"], "inicio": [_t("2025-01-24 20:00"), _t("2025-01-24 21:00")]}
)
ALERTAS = pd.DataFrame(
    {
        "estacao_id": ["EST-ARI-01", "EST-ARI-01", "EST-PIR-01"],
        "emitido_em": [_t("2025-01-24 19:10"), _t("2025-01-24 19:40"), _t("2025-01-24 21:30")],
        "nivel_risco": ["laranja", "vermelho", "vermelho"],
    }
)


def test_antecedencia_usa_o_primeiro_alerta_antes_do_transbordo():
    minutos = medidas.antecedencia_por_evento(EVENTOS, ALERTAS)
    assert list(minutos) == [50.0, 0.0]  # no segundo evento o alerta só veio depois
    assert medidas.antecedencia_mediana_min(EVENTOS, ALERTAS) == 25.0
    assert medidas.taxa_eventos_avisados_pct(EVENTOS, ALERTAS) == 50.0


def test_alertas_emitidos_conta_so_risco_alto_e_perigo():
    com_amarelo = pd.concat([ALERTAS, ALERTAS.assign(nivel_risco="amarelo")])
    assert medidas.alertas_emitidos(com_amarelo) == 3


def test_disponibilidade_considera_janelas_esperadas():
    instantes = pd.date_range("2025-01-01", periods=10, freq="10min", tz="UTC").delete([3, 4])
    leituras = pd.DataFrame({"estacao_id": "EST-ARI-01", "medido_em": instantes})
    assert medidas.disponibilidade_sensores_pct(leituras) == 80.0


def test_indice_de_prioridade_pesa_ia_nivel_e_ocorrencias():
    assert medidas.indice_de_prioridade(1.0, 100, 5) == 100.0
    assert medidas.indice_de_prioridade(0.5, 50, 1) == 47.0
    assert medidas.indice_de_prioridade(float("nan"), 150, 99) == 40.0  # nível limitado a 100, ocorrências a 5


def test_variacao_percentual_sem_base_devolve_nulo():
    assert medidas.variacao_pct(10, 0) is None
    assert medidas.variacao_pct(150, 100) == 50.0
