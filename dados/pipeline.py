"""Orquestração do pipeline de dados do VigIA (coleta → bronze → silver → gold).

Uso (a partir da raiz do repositório):
    python -m dados.pipeline historico              # chuva real do INMET + nível simulado → gold (base de treino da IA)
    python -m dados.pipeline tempo-real             # laço: micro-lotes do gateway MQTT → gold, a cada 5 s
    python -m dados.pipeline tempo-real --uma-vez   # um ciclo só (útil em testes e na CI)
    python -m dados.pipeline eventos-demo           # recorta temporais reais do histórico para o emulador reproduzir
    python -m dados.pipeline status                 # o que existe em cada camada
"""

from __future__ import annotations

import argparse
import time

import pandas as pd

from comum.config import RAIZ
from comum.log import obter_logger
from dados import camadas
from dados.processamento import bronze, gold, silver

log = obter_logger("dados.pipeline")
PASTA_EVENTOS = RAIZ / "dados" / "referencia" / "eventos_demo"


def rodar_historico() -> dict:
    """Constrói o histórico completo. Leva cerca de um minuto; só precisa rodar uma vez."""
    inicio = time.time()
    bronze.ingerir_inmet()
    chuva = silver.processar_inmet()
    bronze.gerar_sensores_simulados(chuva)
    silver.processar_leituras("historico")
    gold.gerar_dim_estacao()
    fato = gold.gerar_fato_leitura("historico")
    eventos = gold.gerar_fato_evento(fato, "historico")
    gold.gerar_agregado_diario(fato, "historico")
    resumo = {"linhas_gold": len(fato), "eventos_transbordo": len(eventos), "segundos": round(time.time() - inicio, 1)}
    log.info("histórico pronto", extra={"dados": resumo})
    return resumo


def ciclo_tempo_real() -> dict:
    """Um ciclo: o que o gateway deixou na landing vira bronze, silver e gold. Idempotente."""
    novos = bronze.ingerir_sensores()
    n_ocorrencias = bronze.ingerir_ocorrencias()
    gold.gerar_dim_estacao()
    resumo = {"lotes_novos": len(novos), "ocorrencias": n_ocorrencias}
    tem_bronze = any(camadas.caminho("bronze", "sensores").glob("data=*/*.jsonl"))
    saida = camadas.caminho("gold", "fato_leitura", "origem=sensor", "dados.parquet")
    if tem_bronze and (novos or not saida.exists()):
        silver.processar_leituras("sensor")
        fato = gold.gerar_fato_leitura("sensor")
        gold.gerar_fato_evento(fato, "sensor")
        gold.gerar_agregado_diario(fato, "sensor")
        resumo["linhas_gold_sensor"] = len(fato)
    if n_ocorrencias is not None:
        gold.gerar_fato_ocorrencia()
    # Batimento: o monitoramento usa este arquivo para saber se o pipeline está vivo.
    camadas.escrever_json({"em": camadas.agora_iso(), **resumo}, camadas.caminho("gold", "_pipeline_batimento.json"))
    return resumo


def rodar_tempo_real(intervalo_s: float, uma_vez: bool) -> None:
    log.info("pipeline em tempo real iniciado", extra={"dados": {"intervalo_s": intervalo_s}})
    while True:
        try:
            resumo = ciclo_tempo_real()
            if resumo["lotes_novos"]:
                log.info("ciclo", extra={"dados": resumo})
        except Exception:  # noqa: BLE001 - um ciclo com erro não pode derrubar o serviço; o próximo tenta de novo
            log.exception("falha no ciclo")
        if uma_vez:
            return
        time.sleep(intervalo_s)


def gerar_eventos_demo(quantidade: int = 3, horas_antes: int = 8, horas_depois: int = 4) -> list[str]:
    """Recorta do histórico os maiores temporais do período de TESTE da IA (2024+), para o emulador reproduzir."""
    leituras = camadas.ler_parquet(camadas.caminho("silver", "leituras", "origem=historico", "leituras.parquet"))
    eventos = camadas.ler_parquet(camadas.caminho("gold", "fato_evento", "origem=historico", "dados.parquet"))
    eventos = eventos[eventos["inicio"] >= "2024-01-01"]
    # Dias em que mais estações transbordaram: rendem a demonstração mais completa.
    por_dia = (
        eventos.assign(dia=eventos["inicio"].dt.date)
        .groupby("dia")
        .agg(estacoes=("estacao_id", "nunique"), inicio=("inicio", "min"), pico=("pico_cm", "max"))
    )
    escolhidos = por_dia.sort_values(["estacoes", "pico"], ascending=False).head(quantidade)
    PASTA_EVENTOS.mkdir(parents=True, exist_ok=True)
    arquivos = []
    for dia, linha in escolhidos.iterrows():
        de = linha["inicio"] - pd.Timedelta(hours=horas_antes)
        ate = linha["inicio"] + pd.Timedelta(hours=horas_depois)
        recorte = leituras[leituras["medido_em"].between(de, ate)][["estacao_id", "medido_em", "nivel_cm", "chuva_mm"]]
        recorte = recorte.sort_values(["medido_em", "estacao_id"])
        recorte["medido_em"] = recorte["medido_em"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        arquivo = PASTA_EVENTOS / f"temporal_{dia}.csv"
        recorte.to_csv(arquivo, index=False)
        arquivos.append(arquivo.name)
    log.info("eventos de demonstração", extra={"dados": {"arquivos": arquivos}})
    return arquivos


def mostrar_status() -> None:
    """Lista arquivos e linhas por camada: evidência rápida de que o dado percorreu o caminho todo."""
    raiz = camadas.raiz_lake()
    print(f"Data lake: {raiz}")
    for camada in camadas.CAMADAS:
        pasta = raiz / camada
        arquivos = [a for a in pasta.rglob("*") if a.is_file()] if pasta.exists() else []
        tamanho = sum(a.stat().st_size for a in arquivos) / 1e6
        print(f"\n[{camada}] {len(arquivos)} arquivo(s), {tamanho:.1f} MB")
        for parquet in sorted(a for a in arquivos if a.suffix == ".parquet"):
            linhas = len(pd.read_parquet(parquet, columns=[pd.read_parquet(parquet).columns[0]]))
            print(f"  {parquet.relative_to(raiz).as_posix():70s} {linhas:>9,d} linhas".replace(",", "."))


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de dados do VigIA")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("historico")
    tempo_real = sub.add_parser("tempo-real")
    tempo_real.add_argument("--intervalo", type=float, default=5.0)
    tempo_real.add_argument("--uma-vez", action="store_true")
    sub.add_parser("eventos-demo")
    sub.add_parser("status")
    args = parser.parse_args()
    if args.comando == "historico":
        print(rodar_historico())
    elif args.comando == "tempo-real":
        rodar_tempo_real(args.intervalo, args.uma_vez)
    elif args.comando == "eventos-demo":
        print(gerar_eventos_demo())
    else:
        mostrar_status()


if __name__ == "__main__":
    main()
