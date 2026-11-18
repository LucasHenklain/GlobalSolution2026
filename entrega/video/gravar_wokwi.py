# ruff: noqa: E501
"""Grava a simulação REAL da estação no Wokwi como sequência de quadros (para o vídeo pitch).

Uso:  python entrega/video/gravar_wokwi.py [--distancia 150] [--espera 170] [--quadros 60] [--porta 9361]

Reaproveita mvp/iot/firmware/capturar_wokwi.py (mesmos passos: carrega sketch + diagrama, instala as bibliotecas,
inicia a simulação) e, com ela rodando, tira um print a cada ~0,4 s. Saída: entrega/video/cenas/wokwi_<nome>/q_0001.png...
Com --distancia 150 o nível fica em 250 cm (acima da cota de alerta): LED vermelho e sirene pela regra local.
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
FIRMWARE = RAIZ / "mvp" / "iot" / "firmware"

spec = importlib.util.spec_from_file_location("capturar_wokwi", FIRMWARE / "capturar_wokwi.py")
cw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cw)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--distancia", type=int, default=None)
    ap.add_argument("--espera", type=int, default=170)
    ap.add_argument("--quadros", type=int, default=60)
    ap.add_argument("--intervalo", type=float, default=0.4)
    ap.add_argument("--porta", type=int, default=9361)
    ap.add_argument("--nome", default="alerta")
    args = ap.parse_args()
    pasta = AQUI / "cenas" / f"wokwi_{args.nome}"
    pasta.mkdir(parents=True, exist_ok=True)
    sketch = (FIRMWARE / "sketch.ino").read_text(encoding="utf-8")
    diagrama = cw.diagrama_com_distancia((FIRMWARE / "diagram.json").read_text(encoding="utf-8"), args.distancia)
    edge = cw.abrir_edge(cw.EDGE, args.porta, False)
    pagina = cw.Pagina(cw.endereco_da_aba(args.porta))
    try:
        pagina.cdp("Page.enable")
        pagina.cdp("Runtime.enable")
        pagina.cdp("Emulation.setDeviceMetricsOverride", width=1920, height=1080, deviceScaleFactor=1, mobile=False)
        cw.carregar_projeto(pagina, sketch, diagrama)
        cw.simular(pagina, args.espera)
        pagina.js(cw.JS_VOLTAR_AO_CODIGO)
        inicio = time.time()
        for i in range(args.quadros):
            png = base64.b64decode(pagina.cdp("Page.captureScreenshot", format="png")["data"])
            (pasta / f"q_{i + 1:04d}.png").write_bytes(png)
            time.sleep(args.intervalo)
        duracao = time.time() - inicio
        (pasta / "info.txt").write_text(f"quadros={args.quadros}\nsegundos={duracao:.1f}\n", encoding="utf-8")
        print(f"{args.quadros} quadros em {duracao:.1f} s -> {pasta}")
    finally:
        try:
            pagina.cdp("Browser.close")  # fecha o Edge inteiro: não deixa a simulação rodando em segundo plano
        except Exception:  # noqa: BLE001, S110
            pass
        pagina.fechar()
        edge.terminate()


if __name__ == "__main__":
    sys.exit(main())
