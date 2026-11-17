"""A régua do 'antes × depois': antecedência por evento e alarmes falsos."""

import pandas as pd

from comum.estacoes import carregar_estacoes
from dados.processamento.features import calcular_features
from ia import avaliacao, dataset


def _gold(niveis):
    instantes = pd.date_range("2025-01-24T12:00:00Z", periods=len(niveis), freq="10min", tz="UTC")
    leituras = pd.DataFrame(
        {"estacao_id": "EST-ARI-01", "medido_em": instantes, "nivel_cm": niveis, "chuva_mm": 0.0, "bateria_pct": 90.0,
         "origem": "historico", "recebido_em": pd.NaT}
    )  # fmt: skip
    return dataset.rotular(calcular_features(leituras, carregar_estacoes()))


# 12 janelas calmas, sobe, transborda (>= 280) por 3 janelas, volta ao normal.
NIVEIS = [50] * 12 + [100, 160, 230, 260, 290, 300, 285, 200, 100] + [50] * 12
INICIO = 16  # posição da primeira janela acima da cota


def test_rotulo_marca_a_hora_anterior_ao_transbordo():
    gold = _gold(NIVEIS)
    assert list(gold.index[gold["alvo"] == 1]) == list(range(INICIO - 6, INICIO))
    assert gold["ja_transbordando"].sum() == 3


def test_regra_de_limiar_avisa_em_cima_da_hora():
    gold = _gold(NIVEIS)
    m = avaliacao.avaliar_politica(gold, avaliacao.alerta_da_regra(gold))
    assert m["eventos"] == 1
    assert m["antecedencia_mediana_min"] == 20  # só passa da cota de alerta (220) duas janelas antes


def test_alerta_antecipado_ganha_antecedencia_sem_alarme_falso():
    gold = _gold(NIVEIS)
    alerta = pd.Series(False, index=gold.index)
    alerta.iloc[INICIO - 5 : INICIO] = True
    m = avaliacao.avaliar_politica(gold, alerta)
    assert m["antecedencia_mediana_min"] == 50 and m["avisados_30min_pct"] == 100.0
    assert m["alarmes_falsos"] == 0 and m["precisao"] == 1.0


def test_alerta_sem_transbordo_conta_como_alarme_falso():
    gold = _gold(NIVEIS)
    alerta = pd.Series(False, index=gold.index)
    alerta.iloc[2:4] = True  # tocou no meio da calmaria
    m = avaliacao.avaliar_politica(gold, alerta)
    assert m["alarmes_falsos"] == 1 and m["antecedencia_mediana_min"] == 0


def test_treino_em_dados_sinteticos_aprende_o_padrao():
    from ia.treinar import treinar_modelo

    gold = pd.concat([_gold(NIVEIS).assign(medido_em=lambda d, k=k: d["medido_em"] + pd.Timedelta(days=k)) for k in range(40)])
    modelo = treinar_modelo(gold.reset_index(drop=True))
    prob = modelo.predict_proba(dataset.preparar_variaveis(_gold(NIVEIS)))[:, 1]
    assert prob[INICIO - 2] > 0.5 > prob[2]  # alto logo antes do transbordo, baixo na calmaria
