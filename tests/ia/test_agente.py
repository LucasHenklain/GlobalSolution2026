"""Regras do agente de alerta (R1 a R10) e textos das mensagens."""

import pandas as pd

from comum.estacoes import carregar_estacoes
from ia import agente, mensagens

EST = carregar_estacoes()["EST-ARI-01"]  # cotas: atenção 150, alerta 220, transbordo 280
LIMIARES = {"amarelo": 0.07, "laranja": 0.20, "vermelho": 0.60}


def _linha(nivel=50.0, chuva_1h=0.0, **extra) -> dict:
    return {"nivel_cm": nivel, "chuva_1h": chuva_1h, "chuva_24h": 0.0, "delta_nivel_30min": 0.0, "nivel_pct_cota": nivel / 280 * 100, **extra}


def _serie(niveis, probs, inicio="2025-01-24T18:00:00Z"):
    instantes = pd.date_range(inicio, periods=len(niveis), freq="10min", tz="UTC")
    return pd.DataFrame(
        {
            "estacao_id": EST.estacao_id,
            "medido_em": instantes,
            "nivel_cm": niveis,
            "nivel_pct_cota": [n / 280 * 100 for n in niveis],
            "chuva_1h": 0.0,
            "chuva_24h": 0.0,
            "delta_nivel_30min": 0.0,
            "prob": probs,
        }
    )


def test_r1_transbordo_e_vermelho_mesmo_com_probabilidade_baixa():
    assert agente.classificar_risco(_linha(nivel=285), 0.01, EST, LIMIARES) == ("vermelho", "regra_local")


def test_r1_r2_r3_a_ia_antecipa_com_nivel_ainda_normal():
    assert agente.classificar_risco(_linha(), 0.70, EST, LIMIARES) == ("vermelho", "ia")
    assert agente.classificar_risco(_linha(), 0.25, EST, LIMIARES) == ("laranja", "ia")
    assert agente.classificar_risco(_linha(), 0.10, EST, LIMIARES) == ("amarelo", "ia")
    assert agente.classificar_risco(_linha(), 0.01, EST, LIMIARES) == ("verde", "regra_local")


def test_r2_cota_de_alerta_e_rede_de_seguranca_da_ia():
    assert agente.classificar_risco(_linha(nivel=230), 0.01, EST, LIMIARES) == ("laranja", "regra_local")


def test_r3_chuva_forte_gera_atencao():
    assert agente.classificar_risco(_linha(chuva_1h=18), 0.0, EST, LIMIARES)[0] == "amarelo"


def test_r5_sem_modelo_valem_as_regras_de_nivel():
    assert agente.classificar_risco(_linha(nivel=160), None, EST, None) == ("amarelo", "regra_local")
    assert agente.classificar_risco(_linha(nivel=230), None, EST, None) == ("laranja", "regra_local")


def test_r6_r8_alerta_so_quando_o_risco_sobe():
    # verde, laranja por 3 janelas, vermelho: 2 alertas (um por subida), sem repetir o mesmo nível.
    _, alertas = agente.gerar_alertas(_serie([50] * 5, [0.0, 0.3, 0.3, 0.3, 0.8]), EST, LIMIARES)
    assert [a["nivel_risco"] for a in alertas] == ["laranja", "vermelho"]


def test_r7_lembrete_a_cada_60_minutos_enquanto_o_risco_dura():
    _, alertas = agente.gerar_alertas(_serie([50] * 14, [0.3] * 14), EST, LIMIARES)
    assert [a["emitido_em"][11:16] for a in alertas] == ["18:00", "19:00", "20:00"]


def test_r9_avisa_quando_a_situacao_normaliza():
    _, alertas = agente.gerar_alertas(_serie([50] * 6, [0.3, 0.3, 0.0, 0.0, 0.0, 0.0]), EST, LIMIARES)
    assert [a["nivel_risco"] for a in alertas] == ["laranja", "verde"]
    assert alertas[-1]["emitido_em"][11:16] == "18:40"  # terceira janela seguida em verde


def test_identificador_do_alerta_e_deterministico():
    serie = _serie([50, 50], [0.0, 0.9])
    _, primeira = agente.gerar_alertas(serie, EST, LIMIARES)
    _, segunda = agente.gerar_alertas(serie, EST, LIMIARES)
    assert primeira[0]["alerta_id"] == segunda[0]["alerta_id"] == "ALT-ARI-202501241810-VRM"


def test_r10_sirene_so_para_laranja_e_vermelho():
    assert agente.comando_sirene({"nivel_risco": "amarelo", "alerta_id": "x"}) is None
    comando = agente.comando_sirene({"nivel_risco": "vermelho", "alerta_id": "ALT-1"})
    assert comando == {"acao": "ligar", "nivel": "vermelho", "segundos": 60, "alerta_id": "ALT-1"}


def test_sms_cabe_em_160_caracteres_e_nao_tem_acento():
    for est in carregar_estacoes().values():
        for nivel in mensagens.SMS:
            sms = mensagens.montar_textos(nivel, est)["mensagem_sms"]
            assert len(sms) <= 160, (est.estacao_id, nivel, len(sms))
            assert sms.isascii()


def test_motivos_explicam_o_alerta_com_os_dados():
    linha = _linha(nivel=200, chuva_1h=34, delta_nivel_30min=40)
    motivos = mensagens.explicar_motivos(linha, 0.71, EST, "ia", "laranja")
    assert "choveu 34 mm na última hora" in motivos
    assert any("71%" in m for m in motivos)
