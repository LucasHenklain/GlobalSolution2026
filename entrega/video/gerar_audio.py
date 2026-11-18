"""Narração do vídeo pitch com voz neural pt-BR (edge-tts). Lê roteiro.json e grava audio/<id>.mp3.

Uso:  python entrega/video/gerar_audio.py [--so 04_ia]
Adaptado do gerador usado pela equipe no projeto AgroSmart (FIAP 2026).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import ssl
import sys
import tempfile
from pathlib import Path

# Rede corporativa com inspeção TLS: soma a cadeia da empresa (se existir) ao pacote público de certificados.
_corp = os.path.expanduser("~/.claude/certs/corporate-ca-chain.pem")
if os.path.exists(_corp):
    import certifi

    _bundle = os.path.join(tempfile.gettempdir(), "ca-bundle-edge-tts.pem")
    with open(_bundle, "wb") as f:
        f.write(open(certifi.where(), "rb").read() + b"\n" + open(_corp, "rb").read())
    _original = ssl.create_default_context
    ssl.create_default_context = lambda *a, **k: _original(*a, **{**k, "cafile": _bundle})

try:
    import edge_tts
except ImportError:
    sys.exit("instale: python -m pip install edge-tts")

AQUI = Path(__file__).resolve().parent


async def gerar(so: str) -> None:
    roteiro = json.loads((AQUI / "roteiro.json").read_text(encoding="utf-8"))
    (AQUI / "audio").mkdir(exist_ok=True)
    for cena in roteiro["cenas"]:
        if so and cena["id"] != so:
            continue
        saida = AQUI / "audio" / f"{cena['id']}.mp3"
        await edge_tts.Communicate(cena["narracao"], roteiro["voz"], rate=roteiro["velocidade"]).save(str(saida))
        print(cena["id"], saida.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--so", default="")
    asyncio.run(gerar(ap.parse_args().so))
