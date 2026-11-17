"""Serviço da IA: lê o GOLD do pipeline, calcula o risco, emite alertas e entrega ao app e à sirene.

Uso (a partir da raiz do repositório):
    python -m ia.servico                 # laço a cada 2 s
    python -m ia.servico --uma-vez       # um ciclo só (testes e CI)
    python -m ia.servico retroativo      # aplica modelo + agente ao histórico (alimenta o dashboard)

É aqui que as áreas se integram: sensores → pipeline → gold → IA → app do morador → sirene da estação.
"""

from __future__ import annotations

import argparse
import json
import time

import httpx
import pandas as pd

from comum.config import carregar_config
from comum.estacoes import carregar_estacoes
from comum.http_interno import cliente_do_app
from comum.log import obter_logger
from dados import camadas
from ia import agente
from ia.modelo import ModeloAusenteError, carregar_pacote, prever_probabilidade

log = obter_logger("ia.servico")
PONTOS_DA_SERIE = 36  # 6 h de janelas de 10 min enviadas ao app para o gráfico
COLUNAS_ALERTA = [
    "alerta_id", "estacao_id", "emitido_em", "nivel_risco", "prob", "nivel_cm", "chuva_1h",
    "origem_decisao", "titulo", "mensagem_sms", "motivo",
]  # fmt: skip


def pontuar(fato: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Probabilidade (modelo) + nível de risco e alertas (agente) para todas as estações do fato."""
    try:
        pacote = carregar_pacote()
        fato = fato.assign(prob=prever_probabilidade(fato, pacote))
        limiares = pacote["limiares"]
    except ModeloAusenteError:
        # R5: sem modelo, o agente segue só com as regras de nível.
        log.warning("modelo ausente: usando apenas as regras de nível")
        fato, limiares = fato.assign(prob=float("nan")), None
    estacoes = carregar_estacoes()
    partes, alertas = [], []
    for estacao_id, serie in fato.groupby("estacao_id"):
        pontuada, novos = agente.gerar_alertas(serie, estacoes[estacao_id], limiares)
        partes.append(pontuada)
        alertas += novos
    return pd.concat(partes, ignore_index=True), alertas


def gravar_gold(pontuado: pd.DataFrame, alertas: list[dict], origem: str) -> None:
    """A saída da IA também é dado: volta para o gold e aparece no dashboard."""
    risco = pontuado[["estacao_id", "medido_em", "prob", "nivel_risco", "origem_decisao"]].rename(
        columns={"prob": "prob_transbordo_60min"}
    )
    camadas.escrever_parquet(risco, camadas.caminho("gold", "fato_risco", f"origem={origem}", "dados.parquet"))
    tabela = pd.DataFrame(alertas).reindex(columns=COLUNAS_ALERTA)
    tabela["emitido_em"] = pd.to_datetime(tabela["emitido_em"], utc=True)
    tabela["motivo"] = tabela["motivo"].map(lambda m: "; ".join(m) if isinstance(m, list) else m)
    tabela["origem"] = origem
    camadas.escrever_parquet(tabela, camadas.caminho("gold", "fato_alerta", f"origem={origem}", "dados.parquet"))


def montar_situacoes(pontuado: pd.DataFrame) -> list[dict]:
    """Situação atual de cada estação = a janela recebida por último, com as 6 h anteriores para o gráfico."""
    situacoes = []
    for estacao_id, serie in pontuado.groupby("estacao_id"):
        serie = serie.sort_values(["recebido_em", "medido_em"])
        ultima = serie.iloc[-1]
        recentes = serie[
            (serie["medido_em"] <= ultima["medido_em"])
            & (serie["medido_em"] > ultima["medido_em"] - pd.Timedelta(minutes=10 * PONTOS_DA_SERIE))
        ].sort_values("medido_em")
        situacoes.append(
            {
                "estacao_id": estacao_id,
                "atualizado_em": ultima["medido_em"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                "nivel_cm": round(float(ultima["nivel_cm"]), 1),
                "nivel_pct_cota": round(float(ultima["nivel_pct_cota"]), 1),
                "chuva_1h": round(float(ultima["chuva_1h"]), 1),
                "chuva_24h": round(float(ultima["chuva_24h"]), 1),
                "delta_nivel_30min": round(float(ultima["delta_nivel_30min"]), 1),
                "prob_transbordo_60min": None if pd.isna(ultima["prob"]) else round(float(ultima["prob"]), 3),
                "nivel_risco": ultima["nivel_risco"],
                "estado_regra": ultima["estado_regra"],
                "bateria_pct": None if pd.isna(ultima["bateria_pct"]) else float(ultima["bateria_pct"]),
                "origem": ultima["fonte"] if ultima["fonte"] in ("wokwi", "emulador", "replay") else None,
                "serie": [
                    {
                        "t": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "nivel_cm": round(float(n), 1),
                        "chuva_mm": round(float(c), 2),
                    }
                    for t, n, c in zip(recentes["medido_em"], recentes["nivel_cm"], recentes["chuva_mm"], strict=True)
                ],
            }
        )
    return situacoes


def _publicar_sirene(alerta: dict) -> bool:
    """Envia o comando MQTT da sirene. Falha de broker não pode impedir o alerta de chegar ao app."""
    comando = agente.comando_sirene(alerta)
    if comando is None:
        return False
    cfg = carregar_config()
    try:
        import paho.mqtt.publish as publicador

        publicador.single(
            f"{cfg.mqtt_prefixo}/atuadores/{alerta['estacao_id']}/sirene",
            json.dumps(comando),
            qos=1,
            hostname=cfg.mqtt_host,
            port=cfg.mqtt_port,
        )
        return True
    except Exception as erro:  # noqa: BLE001 - qualquer falha de rede aqui é tratada do mesmo jeito
        log.warning("sirene não acionada", extra={"dados": {"erro": type(erro).__name__}})
        return False


def entregar(situacoes: list[dict], alertas: list[dict], estado: dict) -> dict:
    """Entrega ao app pela API interna. O que não for entregue fica para o próximo ciclo."""
    resumo = {"situacoes": 0, "alertas_novos": 0, "sirenes": 0}
    enviados = set(estado.get("alertas_enviados", []))
    app = cliente_do_app()
    try:
        app.post("/api/interno/situacao", json=situacoes).raise_for_status()
        resumo["situacoes"] = len(situacoes)
        for alerta in alertas:
            if alerta["alerta_id"] in enviados:
                continue
            app.post("/api/interno/alertas", json=alerta).raise_for_status()
            enviados.add(alerta["alerta_id"])
            resumo["alertas_novos"] += 1
            resumo["sirenes"] += int(_publicar_sirene(alerta))
    except httpx.HTTPError as erro:
        log.warning("app indisponível", extra={"dados": {"erro": type(erro).__name__}})
    estado["alertas_enviados"] = sorted(enviados)
    return resumo


def ciclo(estado: dict) -> dict | None:
    """Um ciclo: só trabalha se o pipeline gravou um gold novo desde a última vez."""
    gold = camadas.caminho("gold", "fato_leitura", "origem=sensor", "dados.parquet")
    if not gold.exists() or gold.stat().st_mtime == estado.get("gold_lido"):
        return None
    modificado = gold.stat().st_mtime
    fato = camadas.ler_parquet(gold)
    if fato.empty:
        return None
    pontuado, alertas = pontuar(fato)
    gravar_gold(pontuado, alertas, "sensor")
    resumo = entregar(montar_situacoes(pontuado), alertas, estado)
    estado["gold_lido"] = modificado
    return resumo


def rodar(intervalo_s: float, uma_vez: bool) -> None:
    arquivo_estado = camadas.caminho("gold", "_ia_estado.json")
    estado = camadas.ler_json(arquivo_estado, padrao={})
    try:
        carregar_pacote()  # carrega o modelo já na subida: o primeiro alerta não espera a leitura do arquivo
    except ModeloAusenteError:
        log.warning("modelo ausente na subida: rode `python -m ia.treinar`; por ora valem só as regras de nível")
    log.info("serviço de IA iniciado", extra={"dados": {"intervalo_s": intervalo_s}})
    while True:
        try:
            resumo = ciclo(estado)
            if resumo:
                camadas.escrever_json(estado, arquivo_estado)
                if resumo["alertas_novos"]:
                    log.info("alertas emitidos", extra={"dados": resumo})
            camadas.escrever_json(
                {"em": camadas.agora_iso(), **(resumo or {})}, camadas.caminho("gold", "_ia_batimento.json")
            )
        except Exception:  # noqa: BLE001 - um ciclo com erro não derruba o serviço
            log.exception("falha no ciclo da IA")
        if uma_vez:
            return
        time.sleep(intervalo_s)


def rodar_retroativo() -> dict:
    """Aplica o modelo e o agente a todo o histórico: mostra no dashboard como a IA teria alertado."""
    fato = camadas.ler_parquet(camadas.caminho("gold", "fato_leitura", "origem=historico", "dados.parquet"))
    pontuado, alertas = pontuar(fato)
    gravar_gold(pontuado, alertas, "historico")
    resumo = {"janelas": len(pontuado), "alertas": len(alertas)}
    log.info("retroativo pronto", extra={"dados": resumo})
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(description="Serviço de IA do VigIA")
    parser.add_argument("modo", nargs="?", default="tempo-real", choices=["tempo-real", "retroativo"])
    parser.add_argument("--intervalo", type=float, default=2.0)
    parser.add_argument("--uma-vez", action="store_true")
    args = parser.parse_args()
    if args.modo == "retroativo":
        print(rodar_retroativo())
    else:
        rodar(args.intervalo, args.uma_vez)


if __name__ == "__main__":
    main()
