"""Sobe o VigIA inteiro nesta máquina, SEM Docker, e reproduz um temporal real para demonstrar o fluxo completo.

Uso:  python -m devops.demo                         (app em :8000, painel em :8501, replay do temporal de 24/01/2025)
      python -m devops.demo --velocidade 0.2        (replay mais lento: 1 janela de 10 min a cada 5 s)
      python -m devops.demo --broker localhost      (leituras passam por um broker MQTT de verdade)
      python -m devops.demo --porta-app 8010 --porta-painel 8511   (se as portas padrão estiverem ocupadas)

Sem --broker, as leituras do evento são entregues direto ao gateway (mesma validação, mesmo micro-lote), sem MQTT:
serve para demonstrar em qualquer computador que só tenha Python. Com Docker, prefira `docker compose up --build`,
que usa o broker Mosquitto de verdade. Ctrl+C encerra tudo.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import time

from comum.config import RAIZ, carregar_config
from comum.log import obter_logger

log = obter_logger("devops.demo")
EVENTO_PADRAO = RAIZ / "dados" / "referencia" / "eventos_demo" / "temporal_2025-01-24.csv"


def _iniciar(nome: str, comando: list[str], ambiente: dict) -> subprocess.Popen:
    log.info(f"iniciando {nome}")
    return subprocess.Popen(comando, cwd=RAIZ, env=ambiente)  # noqa: S603  # nosec B603 - comandos fixos deste arquivo


def _replay_sem_broker(evento, velocidade: float) -> None:
    """Entrega cada janela do evento direto ao gateway, no ritmo pedido (faz o papel do emulador + broker)."""
    from dados.ingestao.gateway_mqtt import Gateway

    gateway = Gateway()
    with open(evento, encoding="utf-8", newline="") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    janelas = sorted({linha["medido_em"] for linha in linhas})
    for instante in janelas:
        for linha in (item for item in linhas if item["medido_em"] == instante):
            leitura = {
                "estacao_id": linha["estacao_id"],
                "medido_em": linha["medido_em"],
                "nivel_cm": float(linha["nivel_cm"]),
                "chuva_mm": float(linha["chuva_mm"]),
                "bateria_pct": 90,
                "origem": "replay",
            }
            gateway.processar(f"vigia/sensores/{linha['estacao_id']}/leitura", json.dumps(leitura).encode())
        gateway.descarregar()
        time.sleep(1 / velocidade)
    log.info("replay concluído", extra={"dados": {"janelas": len(janelas)}})


def limpar_estado_ao_vivo() -> None:
    """Remove só o que a demonstração ao vivo gerou (leituras de sensor, alertas, banco do app). O histórico fica."""
    cfg = carregar_config()
    lake = cfg.lake
    alvos = [lake / "landing", lake / "bronze" / "sensores", lake / "bronze" / "ocorrencias",
             lake / "silver" / "leituras" / "origem=sensor", lake / "gold" / "_ia_estado.json",
             lake / "gold" / "fato_ocorrencia.parquet", cfg.db]  # fmt: skip
    alvos += list((lake / "gold").glob("*/origem=sensor"))
    for alvo in alvos:
        if alvo.is_dir():
            shutil.rmtree(alvo, ignore_errors=True)
        elif alvo.exists():
            alvo.unlink()
    log.info("estado ao vivo apagado")


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstração local do VigIA (sem Docker)")
    parser.add_argument("--evento", default=str(EVENTO_PADRAO))
    parser.add_argument("--velocidade", type=float, default=0.5, help="janelas de 10 min por segundo")
    parser.add_argument("--broker", default="", help="host de um broker MQTT; vazio = sem broker")
    parser.add_argument("--porta-broker", type=int, default=1883)
    parser.add_argument("--porta-app", type=int, default=8000)
    parser.add_argument("--porta-painel", type=int, default=8501)
    parser.add_argument("--sem-replay", action="store_true", help="só sobe os serviços")
    parser.add_argument("--limpar", action="store_true", help="apaga o estado ao vivo antes (repetir a demonstração do zero)")
    args = parser.parse_args()
    if args.limpar:
        limpar_estado_ao_vivo()

    py = sys.executable
    ambiente = {**os.environ, "PYTHONUTF8": "1", "VIGIA_APP_URL": f"http://127.0.0.1:{args.porta_app}"}
    if args.broker:
        ambiente |= {"MQTT_HOST": args.broker, "MQTT_PORT": str(args.porta_broker)}
    os.environ.update(ambiente)

    subprocess.run([py, "-m", "devops.preparar"], cwd=RAIZ, env=ambiente, check=True)  # noqa: S603  # nosec B603
    processos = [
        _iniciar("app", [py, "-m", "uvicorn", "mvp.web.app:app", "--port", str(args.porta_app), "--log-level", "warning"], ambiente),
        _iniciar("pipeline", [py, "-m", "dados.pipeline", "tempo-real", "--intervalo", "1"], ambiente),
        _iniciar("IA", [py, "-m", "ia.servico", "--intervalo", "1"], ambiente),
        _iniciar(
            "painel",
            [py, "-m", "streamlit", "run", "dados/dashboard/app.py", "--server.port", str(args.porta_painel),
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            ambiente,
        ),
    ]  # fmt: skip
    if args.broker:
        processos.append(_iniciar("gateway MQTT", [py, "-m", "dados.ingestao.gateway_mqtt", "--janela-s", "1"], ambiente))
    try:
        time.sleep(12)  # tempo para o app e a IA subirem antes das primeiras leituras
        print(f"\n  App do morador ......... http://localhost:{args.porta_app}")
        print(f"  Painel da Defesa Civil . http://localhost:{args.porta_painel}  (fonte: 'Sensores ao vivo')")
        print("  Usuários de demonstração: veja mvp/web/README.md\n")
        if not args.sem_replay:
            if args.broker:
                emulador = [py, "-m", "mvp.iot.emulador", "--modo", "replay", "--evento", args.evento,
                            "--velocidade", str(args.velocidade)]  # fmt: skip
                subprocess.run(emulador, cwd=RAIZ, env=ambiente, check=False)  # noqa: S603  # nosec B603
            else:
                _replay_sem_broker(args.evento, args.velocidade)
        print("\nServiços no ar. Ctrl+C para encerrar.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for processo in processos:
            processo.terminate()
        log.info("demonstração encerrada")


if __name__ == "__main__":
    main()
