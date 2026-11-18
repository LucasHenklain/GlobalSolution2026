"""Mostra a quarentena funcionando: envia ao gateway uma leitura válida e três inválidas DE PROPÓSITO e imprime o resultado.

Uso (a partir da raiz):  python docs/ferramentas/exemplo_quarentena.py
Usa uma pasta temporária como data lake: não toca nos dados do projeto.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

AGORA = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
MENSAGENS = [
    ("vigia/sensores/EST-ARI-01/leitura", {"estacao_id": "EST-ARI-01", "medido_em": AGORA, "nivel_cm": 142.5, "chuva_mm": 1.25}),
    ("vigia/sensores/EST-ARI-01/leitura", {"estacao_id": "EST-ARI-01", "medido_em": AGORA, "nivel_cm": 999, "chuva_mm": 0}),
    ("vigia/sensores/EST-PIR-01/leitura", {"estacao_id": "EST-ARI-01", "medido_em": AGORA, "nivel_cm": 80, "chuva_mm": 0}),
    ("vigia/sensores/EST-IPI-01/leitura", {"estacao_id": "EST-IPI-01", "medido_em": "2099-01-01T00:00:00Z", "nivel_cm": 50, "chuva_mm": 0}),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as pasta:
        os.environ["VIGIA_LAKE"] = pasta
        from dados.ingestao.gateway_mqtt import Gateway

        gateway = Gateway()
        print("ENVIADAS AO GATEWAY (1 válida e 3 inválidas de propósito):")
        for topico, corpo in MENSAGENS:
            motivo = gateway.processar(topico, json.dumps(corpo).encode())
            print(f"  {topico}  {json.dumps(corpo)}\n    → {'ACEITA' if motivo is None else 'REJEITADA: ' + motivo}")
        gateway.descarregar()
        print(f"\nCONTADORES: {dict(gateway.contadores)}")
        for rotulo, padrao in (("LANDING (aceitas)", "landing/sensores/*/*.jsonl"), ("QUARENTENA DO GATEWAY", "landing/quarentena_gateway/*/*.jsonl")):
            print(f"\n{rotulo}:")
            for arquivo in sorted(Path(pasta).glob(padrao)):
                for linha in arquivo.read_text(encoding="utf-8").splitlines():
                    print("  " + linha)


if __name__ == "__main__":
    main()
