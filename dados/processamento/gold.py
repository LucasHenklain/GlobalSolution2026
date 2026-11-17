"""Camada GOLD: tabelas prontas para decidir — consumidas pelo dashboard e pela IA."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd

from comum.estacoes import carregar_estacoes
from comum.log import obter_logger
from dados import camadas
from dados.processamento.features import calcular_features

log = obter_logger("dados.gold")
INTERVALO_ENTRE_EVENTOS = pd.Timedelta(hours=2)


def gerar_dim_estacao() -> pd.DataFrame:
    dim = pd.DataFrame([asdict(e) for e in carregar_estacoes().values()])
    camadas.escrever_parquet(dim, camadas.caminho("gold", "dim_estacao.parquet"))
    return dim


def gerar_fato_leitura(origem: str) -> pd.DataFrame:
    """Lê o silver e grava as features de 10 min. É a tabela que a IA lê para treinar e para prever."""
    silver = camadas.caminho("silver", "leituras", f"origem={origem}", "leituras.parquet")
    leituras = camadas.ler_parquet(silver)
    fato = calcular_features(leituras, carregar_estacoes())
    fato["origem"] = origem
    camadas.escrever_parquet(fato, camadas.caminho("gold", "fato_leitura", f"origem={origem}", "dados.parquet"))
    log.info("gold fato_leitura", extra={"dados": {"origem": origem, "linhas": len(fato)}})
    return fato


def detectar_eventos(fato: pd.DataFrame) -> pd.DataFrame:
    """Um evento de transbordo = período contínuo acima da cota (buracos de até 2 h contam como o mesmo evento)."""
    acima = fato[fato["estado_regra"] == "transbordo"].sort_values(["estacao_id", "medido_em"])
    if acima.empty:
        return pd.DataFrame(columns=["estacao_id", "inicio", "fim", "pico_cm", "duracao_min", "origem"])
    novo_evento = (acima.groupby("estacao_id")["medido_em"].diff() > INTERVALO_ENTRE_EVENTOS) | (
        acima["estacao_id"] != acima["estacao_id"].shift()
    )
    acima = acima.assign(evento=novo_evento.cumsum())
    eventos = acima.groupby("evento").agg(
        estacao_id=("estacao_id", "first"),
        inicio=("medido_em", "min"),
        fim=("medido_em", "max"),
        pico_cm=("nivel_cm", "max"),
        origem=("origem", "first"),
    )
    eventos["duracao_min"] = (eventos["fim"] - eventos["inicio"]).dt.total_seconds() / 60 + 10
    return eventos.reset_index(drop=True)


def gerar_fato_evento(fato: pd.DataFrame, origem: str) -> pd.DataFrame:
    eventos = detectar_eventos(fato)
    camadas.escrever_parquet(eventos, camadas.caminho("gold", "fato_evento", f"origem={origem}", "dados.parquet"))
    return eventos


def gerar_agregado_diario(fato: pd.DataFrame, origem: str) -> pd.DataFrame:
    """Resumo por estação e dia (dia de Brasília): base dos indicadores do dashboard."""
    if fato.empty:
        return pd.DataFrame()
    df = fato.assign(dia=(fato["medido_em"] - pd.Timedelta(hours=3)).dt.date)
    diario = df.groupby(["estacao_id", "dia"]).agg(
        chuva_dia_mm=("chuva_mm", "sum"),
        chuva_max_1h_mm=("chuva_1h", "max"),
        nivel_max_cm=("nivel_cm", "max"),
        nivel_max_pct_cota=("nivel_pct_cota", "max"),
        janelas_com_dado=("nivel_cm", "count"),
        min_em_atencao=("estado_regra", lambda s: int((s != "normal").sum()) * 10),
        min_em_transbordo=("estado_regra", lambda s: int((s == "transbordo").sum()) * 10),
        bateria_min_pct=("bateria_pct", "min"),
    )
    diario["disponibilidade_pct"] = (diario["janelas_com_dado"] / 144 * 100).clip(upper=100).round(1)
    diario = diario.reset_index()
    diario["dia"] = pd.to_datetime(diario["dia"])
    diario["origem"] = origem
    camadas.escrever_parquet(diario, camadas.caminho("gold", "agg_diario", f"origem={origem}", "dados.parquet"))
    return diario


def gerar_fato_ocorrencia() -> pd.DataFrame | None:
    """Ocorrências relatadas pelos moradores no app (bueiro entupido etc.), já sem dados pessoais."""
    extrato = camadas.ler_json(camadas.caminho("bronze", "ocorrencias", "extrato.json"))
    if extrato is None:
        return None
    colunas = ["ocorrencia_id", "estacao_id", "tipo", "status", "criada_em", "atualizada_em", "encerrada_em"]
    fato = pd.DataFrame(extrato["ocorrencias"]).reindex(columns=colunas)
    for coluna in ("criada_em", "atualizada_em", "encerrada_em"):
        fato[coluna] = pd.to_datetime(fato[coluna], utc=True, errors="coerce")
    camadas.escrever_parquet(fato, camadas.caminho("gold", "fato_ocorrencia.parquet"))
    return fato
