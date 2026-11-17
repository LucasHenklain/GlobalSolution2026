"""Features de 10 min: a mesma função alimenta o treino da IA e o tempo real."""

import pandas as pd

from comum.estacoes import carregar_estacoes
from dados.processamento.features import calcular_features


def _serie(niveis, chuvas, inicio="2026-01-10T12:00:00Z", estacao="EST-ARI-01", passo="10min"):
    instantes = pd.date_range(inicio, periods=len(niveis), freq=passo, tz="UTC")
    return pd.DataFrame(
        {
            "estacao_id": estacao,
            "medido_em": instantes,
            "nivel_cm": niveis,
            "chuva_mm": chuvas,
            "bateria_pct": 90.0,
            "origem": "emulador",
            "recebido_em": instantes,
        }
    )


def test_acumulados_de_chuva_e_variacao_de_nivel():
    f = calcular_features(_serie([40, 50, 70, 100, 140, 150, 150], [0, 2, 4, 6, 8, 0, 0]), carregar_estacoes())
    ultima = f.iloc[-1]
    assert ultima["chuva_30min"] == 8  # 8 + 0 + 0
    assert ultima["chuva_1h"] == 20  # 2+4+6+8+0+0
    assert f.iloc[4]["delta_nivel_10min"] == 40
    assert f.iloc[4]["delta_nivel_30min"] == 90  # 140 - 50


def test_percentual_da_cota_e_estado_pela_regra():
    f = calcular_features(_serie([100, 160, 230, 290], [0, 0, 0, 0]), carregar_estacoes())
    assert list(f["estado_regra"]) == ["normal", "atencao", "alerta", "transbordo"]
    assert round(f.iloc[-1]["nivel_pct_cota"], 1) == round(290 / 280 * 100, 1)


def test_varias_leituras_na_mesma_janela_viram_uma_linha():
    # Sensor publicando a cada 2 min: a janela de 10 min soma a chuva e guarda o último nível.
    f = calcular_features(_serie([50, 52, 54, 56, 58], [1, 1, 1, 1, 1], passo="2min"), carregar_estacoes())
    assert len(f) == 1
    assert f.iloc[0]["chuva_mm"] == 5 and f.iloc[0]["nivel_cm"] == 58


def test_buraco_curto_repete_o_ultimo_nivel():
    serie = _serie([50, 60, 70, 80], [0, 0, 0, 0]).drop(index=[1, 2])  # 20 min sem leitura
    f = calcular_features(serie, carregar_estacoes())
    assert len(f) == 4 and list(f["nivel_cm"]) == [50, 50, 50, 80]


def test_series_distantes_nao_somam_chuva_uma_da_outra():
    ontem = _serie([50, 50], [30, 30], inicio="2026-01-09T12:00:00Z")
    hoje = _serie([50, 50], [1, 1], inicio="2026-01-10T12:00:00Z")
    f = calcular_features(pd.concat([ontem, hoje]), carregar_estacoes())
    assert f.iloc[-1]["chuva_24h"] == 2  # não enxerga os 60 mm da véspera: são séries separadas (buraco > 6 h)


def test_sem_leituras_devolve_tabela_vazia():
    assert calcular_features(_serie([], []), carregar_estacoes()).empty
