"""CT-20 — fluxo completo, sem rede: leituras de um temporal → gateway → bronze/silver/gold → IA → app do morador.

O broker MQTT e o HTTP são substituídos por chamadas diretas; todo o resto é o código de produção.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import joblib
import pandas as pd
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from comum.config import RAIZ
from dados import camadas, pipeline
from dados.ingestao.gateway_mqtt import Gateway
from ia import dataset, servico
from ia.modelo import arquivo_modelo
from ia.treinar import treinar_modelo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
import ajudas_web  # noqa: E402 - ajudantes dos testes do app (cadastro, login)

EVENTO = RAIZ / "dados" / "referencia" / "eventos_demo" / "temporal_2025-01-24.csv"
TOKEN = "token-do-teste-de-integracao"


@pytest.fixture
def app_cliente(monkeypatch):
    """App real (banco temporário) acessado por um cliente de teste no lugar do HTTP."""
    monkeypatch.setenv("VIGIA_SECRET_KEY", "chave-de-sessao-so-para-os-testes-0123456789")
    monkeypatch.setenv("VIGIA_CHAVE_DADOS", Fernet.generate_key().decode())
    monkeypatch.setenv("VIGIA_TOKEN_INTERNO", TOKEN)
    from mvp.web.app import criar_app

    app = criar_app()
    with TestClient(app) as navegador, TestClient(app, headers={"X-Token-Interno": TOKEN}) as interno:
        # O pipeline e a IA falam com o app por este cliente, como se fosse a rede.
        monkeypatch.setattr("ia.servico.cliente_do_app", lambda: interno)
        monkeypatch.setattr("dados.processamento.bronze.cliente_do_app", lambda: interno)
        monkeypatch.setattr(
            "ia.servico._publicar_sirene", lambda alerta: alerta["nivel_risco"] in ("laranja", "vermelho")
        )
        yield navegador


def _publicar_evento_no_gateway() -> int:
    """Faz o papel do emulador + broker: entrega cada linha do evento ao gateway como mensagem MQTT."""
    gateway = Gateway()
    with open(EVENTO, encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    for linha in linhas:
        leitura = {
            "estacao_id": linha["estacao_id"],
            "medido_em": linha["medido_em"],
            "nivel_cm": float(linha["nivel_cm"]),
            "chuva_mm": float(linha["chuva_mm"]),
            "bateria_pct": 90,
            "origem": "replay",
        }
        motivo = gateway.processar(f"vigia/sensores/{linha['estacao_id']}/leitura", json.dumps(leitura).encode())
        assert motivo is None, motivo
    gateway.descarregar()
    return len(linhas)


def _treinar_modelo_pequeno() -> None:
    """Treina um modelo só com o próprio evento (rápido): o teste verifica o encanamento, não a qualidade da IA."""
    fato = dataset.rotular(
        camadas.ler_parquet(camadas.caminho("gold", "fato_leitura", "origem=sensor", "dados.parquet"))
    )
    repetido = pd.concat([fato] * 5, ignore_index=True)
    arquivo_modelo().parent.mkdir(parents=True, exist_ok=True)
    pacote = {
        "modelo": treinar_modelo(repetido),
        "variaveis": dataset.VARIAVEIS,
        "limiares": {"amarelo": 0.07, "laranja": 0.2, "vermelho": 0.6},
    }
    joblib.dump(pacote, arquivo_modelo())


def test_do_sensor_ao_alerta_no_celular_do_morador(app_cliente):
    # 1) Uma moradora do Aricanduva se cadastra (com telefone, para receber SMS).
    assert ajudas_web.cadastrar(app_cliente, email="maria@exemplo.com", estacao_id="EST-ARI-01").status_code == 200

    # 2) As estações publicam o temporal de 24/01/2025; o gateway valida e grava os micro-lotes.
    n_leituras = _publicar_evento_no_gateway()

    # 3) Pipeline: landing → bronze → silver → gold.
    resumo = pipeline.ciclo_tempo_real()
    assert resumo["lotes_novos"] >= 1 and resumo["linhas_gold_sensor"] == n_leituras
    assert not (camadas.raiz_lake() / "quarentena" / "leituras_sensor.parquet").exists()

    # 4) IA: probabilidade de transbordo + agente de alerta → entrega ao app e aciona a sirene.
    _treinar_modelo_pequeno()
    entrega = servico.ciclo({})
    assert entrega["situacoes"] == 4
    assert entrega["alertas_novos"] >= 2 and entrega["sirenes"] >= 1

    # 5) A saída da IA voltou ao gold (o dashboard lê daqui).
    alertas = camadas.ler_parquet(camadas.caminho("gold", "fato_alerta", "origem=sensor", "dados.parquet"))
    do_aricanduva = alertas[alertas["estacao_id"] == "EST-ARI-01"]
    assert {"laranja", "vermelho"} & set(do_aricanduva["nivel_risco"])

    # 6) A moradora vê o alerta da área dela no app, com o motivo.
    pagina = app_cliente.get("/alertas")
    assert pagina.status_code == 200 and "Aricanduva" in pagina.text
    assert app_cliente.get("/minha-area").status_code == 200

    # 7) O SMS foi para a fila e a métrica do app registrou os alertas recebidos.
    metricas = app_cliente.get("/metrics").text
    assert "vigia_alertas_recebidos_total 0" not in metricas
    assert "vigia_sms_enfileirados_total 0" not in metricas

    # 8) Reprocessar os mesmos dados não duplica alertas (idempotência de ponta a ponta).
    total_antes = _contador(app_cliente, "vigia_sms_enfileirados_total")
    servico.ciclo({"gold_lido": None})
    assert _contador(app_cliente, "vigia_sms_enfileirados_total") == total_antes


def _contador(cliente, nome: str) -> float:
    for linha in cliente.get("/metrics").text.splitlines():
        if linha.startswith(nome + " "):
            return float(linha.split()[-1])
    raise AssertionError(f"métrica {nome} não encontrada")


def test_ocorrencia_do_morador_chega_ao_data_lake(app_cliente):
    ajudas_web.cadastrar(app_cliente, email="jose@exemplo.com", estacao_id="EST-PIR-01")
    resposta = ajudas_web.enviar(
        app_cliente,
        "/ocorrencias/nova",
        {"tipo": "bueiro_entupido", "descricao": "Bueiro entupido na esquina", "estacao_id": "EST-PIR-01"},
    )
    assert resposta.status_code == 200
    pipeline.ciclo_tempo_real()
    ocorrencias = camadas.ler_parquet(camadas.caminho("gold", "fato_ocorrencia.parquet"))
    assert list(ocorrencias["tipo"]) == ["bueiro_entupido"] and ocorrencias.iloc[0]["status"] == "aberta"
    assert "descricao" not in ocorrencias.columns  # texto livre do morador não entra no gold
