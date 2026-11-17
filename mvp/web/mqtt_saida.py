"""Saída MQTT do app: o único ponto que fala com o broker (comando manual da sirene, contrato 3.2)."""

from __future__ import annotations

import json

import paho.mqtt.client as mqtt

from comum.config import Config
from comum.log import obter_logger

log = obter_logger("web.mqtt")

ESPERA_S = 3  # tempo curto: a tela do agente não pode travar se o broker estiver fora


def publicar_sirene(cfg: Config, estacao_id: str, comando: dict) -> bool:
    """Publica o comando em <prefixo>/atuadores/<estacao_id>/sirene (QoS 1). Devolve False se o broker não respondeu."""
    topico = f"{cfg.mqtt_prefixo}/atuadores/{estacao_id}/sirene"
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    cliente.connect_timeout = ESPERA_S
    try:
        cliente.connect(cfg.mqtt_host, cfg.mqtt_port, keepalive=10)
        cliente.loop_start()
        envio = cliente.publish(topico, json.dumps(comando), qos=1)
        envio.wait_for_publish(timeout=ESPERA_S)
        entregue = envio.is_published()
    except (OSError, ValueError, RuntimeError) as erro:
        # Broker fora do ar não derruba a página: registra e avisa o agente.
        log.warning(
            "broker MQTT indisponível", extra={"dados": {"estacao_id": estacao_id, "erro": type(erro).__name__}}
        )
        return False
    finally:
        cliente.loop_stop()
        cliente.disconnect()
    if not entregue:
        log.warning("comando de sirene sem confirmação do broker", extra={"dados": {"estacao_id": estacao_id}})
    return entregue
