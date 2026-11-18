"""O dashboard abre sem erro: vazio (antes do pipeline) e com dados de sensores no gold."""

import csv
import json

from streamlit.testing.v1 import AppTest

from comum.config import RAIZ
from dados import pipeline
from dados.ingestao.gateway_mqtt import Gateway
from ia import servico

PAINEL = str(RAIZ / "dados" / "dashboard" / "app.py")
EVENTO = RAIZ / "dados" / "referencia" / "eventos_demo" / "temporal_2025-01-24.csv"


def test_painel_sem_dados_orienta_o_usuario():
    painel = AppTest.from_file(PAINEL, default_timeout=120).run()
    assert not painel.exception
    assert any("Ainda não há dados" in aviso.value for aviso in painel.info)


def _gold_de_sensores() -> None:
    """Passa o evento de demonstração pelo gateway, pelo pipeline e pelo agente (sem modelo: regras de nível)."""
    gateway = Gateway()
    with open(EVENTO, encoding="utf-8", newline="") as arquivo:
        for linha in csv.DictReader(arquivo):
            leitura = {**linha, "nivel_cm": float(linha["nivel_cm"]), "chuva_mm": float(linha["chuva_mm"])}
            gateway.processar(f"vigia/sensores/{linha['estacao_id']}/leitura", json.dumps(leitura).encode())
    gateway.descarregar()
    pipeline.ciclo_tempo_real(buscar_ocorrencias=False)
    servico.ciclo({})


def test_painel_ao_vivo_mostra_indicadores_e_abas():
    _gold_de_sensores()
    painel = AppTest.from_file(PAINEL, default_timeout=120).run()
    painel.sidebar.radio[0].set_value("Sensores ao vivo").run()
    assert not painel.exception
    indicadores = {m.label: m.value for m in painel.metric}
    assert indicadores["Transbordos"] == "2"
    assert indicadores["Chuva acumulada"].endswith("mm")
    assert [aba.label for aba in painel.tabs] == [
        "Visão geral",
        "Alertas e ocorrências",
        "IA: antes × depois",
        "Dados e monitoramento",
    ]
