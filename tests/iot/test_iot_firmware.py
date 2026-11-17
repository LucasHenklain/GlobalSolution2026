"""Firmware do Wokwi: não dá para compilar aqui; os testes conferem a coerência entre sketch, circuito e contrato."""

from __future__ import annotations

import json
import re

from comum.config import RAIZ
from comum.estacoes import carregar_estacoes
from dados.ingestao import gateway_mqtt
from mvp.iot.firmware.capturar_wokwi import diagrama_com_distancia

FIRMWARE = RAIZ / "mvp" / "iot" / "firmware"
SKETCH = (FIRMWARE / "sketch.ino").read_text(encoding="utf-8")
DIAGRAMA = json.loads((FIRMWARE / "diagram.json").read_text(encoding="utf-8"))
PINOS_ADC1 = set(range(32, 40))  # o ADC2 do ESP32 não funciona com o Wi-Fi ligado


def constante(nome: str) -> float:
    return float(re.search(rf"\b{nome}\s*=\s*([\d.]+)f?;", SKETCH).group(1))


def pinos_do_sketch() -> dict[str, int]:
    return {nome: int(numero) for nome, numero in re.findall(r"const int (PINO_\w+)\s*=\s*(\d+);", SKETCH)}


def test_cotas_do_sketch_iguais_as_do_catalogo():
    est = carregar_estacoes()["EST-ARI-01"]
    assert '"EST-ARI-01"' in SKETCH
    assert constante("ALTURA_SENSOR_CM") == est.altura_sensor_cm
    assert constante("COTA_ATENCAO_CM") == est.cota_atencao_cm
    assert constante("COTA_ALERTA_CM") == est.cota_alerta_cm
    assert constante("COTA_TRANSBORDO_CM") == est.cota_transbordo_cm
    assert constante("MM_POR_BASCULADA") == 0.25


def test_payload_do_sketch_tem_exatamente_as_chaves_do_contrato():
    funcao = SKETCH[SKETCH.index("bool publicarLeitura") : SKETCH.index("void reenviarPendentes")]
    chaves = re.findall(r'doc\["(\w+)"\]', funcao)
    assert chaves == list(gateway_mqtt.OBRIGATORIOS + gateway_mqtt.OPCIONAIS)
    assert re.search(r'ORIGEM\s*=\s*"wokwi"', SKETCH) and re.search(r'FW_VERSAO\s*=\s*"1\.0\.0"', SKETCH)


def test_topicos_do_sketch_seguem_o_contrato():
    for sufixo in ("%s/sensores/%s/leitura", "%s/sensores/%s/status", "%s/atuadores/%s/sirene", "%s/estado"):
        assert sufixo in SKETCH


def test_cada_pino_do_sketch_esta_ligado_no_diagrama():
    ligados = {ponta.split(":")[1] for conexao in DIAGRAMA["connections"] for ponta in conexao[:2] if "esp:" in ponta}
    pinos = pinos_do_sketch()
    assert len(pinos) == 9 and len(set(pinos.values())) == 9  # nenhum pino usado duas vezes
    for nome, numero in pinos.items():
        assert str(numero) in ligados, f"{nome} (GPIO {numero}) não aparece no diagram.json"
    assert pinos["PINO_BATERIA"] in PINOS_ADC1


def test_conexoes_do_diagrama_apontam_para_pecas_existentes():
    pecas = {peca["id"]: peca["type"] for peca in DIAGRAMA["parts"]}
    for origem, destino, *_ in DIAGRAMA["connections"]:
        for ponta in (origem, destino):
            peca = ponta.split(":")[0]
            assert peca in pecas or peca == "$serialMonitor", ponta
    tipos = set(pecas.values())
    assert {"wokwi-hc-sr04", "wokwi-pushbutton", "wokwi-slide-switch", "wokwi-potentiometer", "wokwi-buzzer"} <= tipos
    cores = sorted(peca["attrs"]["color"] for peca in DIAGRAMA["parts"] if peca["type"] == "wokwi-led")
    assert cores == ["green", "red", "yellow"]


def test_bibliotecas_declaradas_sao_as_que_o_sketch_inclui():
    bibliotecas = (FIRMWARE / "libraries.txt").read_text(encoding="utf-8")
    assert "PubSubClient" in bibliotecas and "ArduinoJson" in bibliotecas
    assert "#include <PubSubClient.h>" in SKETCH and "#include <ArduinoJson.h>" in SKETCH


def test_sketch_tem_chaves_e_parenteses_balanceados():
    sem_comentarios = re.sub(r"/\*.*?\*/|//[^\n]*", "", SKETCH, flags=re.S)
    sem_textos = re.sub(r'"(\\.|[^"\\])*"|\'(\\.|[^\'\\])*\'', "", sem_comentarios)
    assert sem_textos.count("{") == sem_textos.count("}")
    assert sem_textos.count("(") == sem_textos.count(")")


def test_capturar_wokwi_troca_so_a_distancia_do_ultrassom():
    original = (FIRMWARE / "diagram.json").read_text(encoding="utf-8")
    assert diagrama_com_distancia(original, None) == original
    alterado = json.loads(diagrama_com_distancia(original, 150))
    sonar = next(peca for peca in alterado["parts"] if peca["type"] == "wokwi-hc-sr04")
    assert sonar["attrs"]["distance"] == "150"
    sonar["attrs"]["distance"] = "300"
    assert alterado == DIAGRAMA
