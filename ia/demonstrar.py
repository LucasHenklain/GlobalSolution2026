"""Demonstração da IA com entrada e saída, no terminal.

Uso:  python -m ia.demonstrar                      (momento em que a IA avisa, no temporal de 24/01/2025)
      python -m ia.demonstrar --nivel 60 --chuva-1h 45 --subida-30min 20   (cenário digitado na hora)

Entrada: uma janela de 10 min de uma estação (as mesmas colunas do gold). Saída: probabilidade de transbordo
em 60 min, nível de risco, quem decidiu (IA ou regra), o alerta completo e o SMS.
"""

from __future__ import annotations

import argparse
import json

import pandas as pd

from comum.estacoes import carregar_estacoes
from dados import camadas
from ia import agente
from ia.modelo import carregar_pacote, prever_probabilidade

ENTRADA = ["estacao_id", "medido_em", "nivel_cm", "nivel_pct_cota", "chuva_mm", "chuva_30min", "chuva_1h",
           "chuva_3h", "chuva_24h", "chuva_72h", "delta_nivel_10min", "delta_nivel_30min", "estado_regra"]  # fmt: skip


def janela_do_historico() -> pd.DataFrame:
    """A janela real em que a IA dispara o primeiro alerta do Aricanduva no temporal de 24/01/2025."""
    fato = camadas.ler_parquet(camadas.caminho("gold", "fato_leitura", "origem=historico", "dados.parquet"))
    return fato[(fato["estacao_id"] == "EST-ARI-01") & (fato["medido_em"] == pd.Timestamp("2025-01-24T19:20:00Z"))]


def janela_digitada(
    estacao_id: str, nivel: float, chuva_1h: float, subida_30min: float, chuva_24h: float
) -> pd.DataFrame:
    """Monta uma janela a partir dos números passados na linha de comando."""
    est = carregar_estacoes()[estacao_id]
    return pd.DataFrame(
        [
            {
                "estacao_id": estacao_id,
                "medido_em": pd.Timestamp.now(tz="UTC").floor("10min"),
                "nivel_cm": nivel,
                "nivel_pct_cota": nivel / est.cota_transbordo_cm * 100,
                "chuva_mm": chuva_1h / 6,
                "chuva_30min": chuva_1h / 2,
                "chuva_1h": chuva_1h,
                "chuva_3h": chuva_1h,
                "chuva_24h": max(chuva_24h, chuva_1h),
                "chuva_72h": max(chuva_24h, chuva_1h),
                "delta_nivel_10min": subida_30min / 3,
                "delta_nivel_30min": subida_30min,
                "estado_regra": est.estado_regra(nivel),
            }
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Demonstração da IA do VigIA (entrada → saída)")
    parser.add_argument("--estacao", default="EST-ARI-01", choices=sorted(carregar_estacoes()))
    parser.add_argument("--nivel", type=float, help="nível do córrego em cm")
    parser.add_argument("--chuva-1h", type=float, default=0.0, help="chuva na última hora (mm)")
    parser.add_argument("--subida-30min", type=float, default=0.0, help="quanto o nível subiu em 30 min (cm)")
    parser.add_argument("--chuva-24h", type=float, default=0.0, help="chuva nas últimas 24 h (mm)")
    args = parser.parse_args()

    if args.nivel is None:
        janela = janela_do_historico()
    else:
        janela = janela_digitada(args.estacao, args.nivel, args.chuva_1h, args.subida_30min, args.chuva_24h)
    pacote = carregar_pacote()
    est = carregar_estacoes()[janela.iloc[0]["estacao_id"]]
    prob = float(prever_probabilidade(janela, pacote).iloc[0])
    _, alertas = agente.gerar_alertas(janela.assign(prob=prob), est, pacote["limiares"])
    nivel, origem = agente.classificar_risco(janela.iloc[0].to_dict(), prob, est, pacote["limiares"])

    print("=== ENTRADA (uma janela de 10 min do gold) ===")
    print(
        json.dumps(
            json.loads(janela[ENTRADA].to_json(orient="records", date_format="iso"))[0], indent=2, ensure_ascii=False
        )
    )
    print(f"\ncotas de {est.nome}: atenção {est.cota_atencao_cm:.0f} cm · alerta {est.cota_alerta_cm:.0f} cm"
          f" · transbordo {est.cota_transbordo_cm:.0f} cm")  # fmt: skip
    print("\n=== SAÍDA ===")
    print(f"probabilidade de transbordo em 60 min: {prob:.1%}   (limiares: {pacote['limiares']})")
    print(f"nível de risco: {nivel.upper()}   decidido por: {'IA' if origem == 'ia' else 'regra de nível'}")
    print(f"regra de limiar fixo (o 'antes') diria: {janela.iloc[0]['estado_regra']}")
    if alertas:
        print("\nalerta emitido pelo agente:")
        print(json.dumps(alertas[0], indent=2, ensure_ascii=False))
        print("\ncomando para a sirene:", json.dumps(agente.comando_sirene(alertas[0])))
    else:
        print("\nnenhum alerta emitido (risco verde).")


if __name__ == "__main__":
    main()
