"""Consultas do dashboard ao GOLD. O DuckDB lê os Parquet direto do disco e já aplica os filtros (período, estações)."""

from __future__ import annotations

from datetime import datetime

import duckdb
import pandas as pd

from dados import camadas

ORIGENS = {"Histórico (2019–2025)": "historico", "Sensores ao vivo": "sensor"}


def _gold(tabela: str, origem: str | None = None) -> str | None:
    """Caminho do Parquet da tabela (None se ainda não foi gerado)."""
    partes = (tabela, f"origem={origem}", "dados.parquet") if origem else (f"{tabela}.parquet",)
    arquivo = camadas.raiz_lake().joinpath("gold", *partes)
    return arquivo.as_posix() if arquivo.exists() else None


def _consultar(sql: str, parametros: list) -> pd.DataFrame:
    with duckdb.connect() as con:
        con.execute("SET TimeZone='UTC'")
        return con.execute(sql, parametros).df()


def _filtrar(
    tabela: str, origem: str, coluna_tempo: str, de: datetime, ate: datetime, estacoes: list[str], extra: str = ""
) -> pd.DataFrame:
    """SELECT * da tabela do gold limitado ao período e às estações escolhidas nos filtros."""
    arquivo = _gold(tabela, origem)
    if arquivo is None or not estacoes:
        return pd.DataFrame()
    marcadores = ", ".join("?" for _ in estacoes)
    # O caminho vem de camadas (não do usuário) e os filtros entram como parâmetros: sem risco de injeção.
    sql = (
        f"SELECT * FROM read_parquet('{arquivo}') "  # noqa: S608
        f"WHERE {coluna_tempo} >= ? AND {coluna_tempo} < ? AND estacao_id IN ({marcadores}) {extra} "
        f"ORDER BY {coluna_tempo}"
    )
    return _consultar(sql, [de, ate, *estacoes])


def periodo_disponivel(origem: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    arquivo = _gold("fato_leitura", origem)
    if arquivo is None:
        return None
    linha = _consultar(f"SELECT min(medido_em) AS de, max(medido_em) AS ate FROM read_parquet('{arquivo}')", [])  # noqa: S608
    if linha.empty or pd.isna(linha.loc[0, "de"]):
        return None
    return linha.loc[0, "de"], linha.loc[0, "ate"]


def leituras(origem: str, de: datetime, ate: datetime, estacoes: list[str]) -> pd.DataFrame:
    return _filtrar("fato_leitura", origem, "medido_em", de, ate, estacoes)


def risco(origem: str, de: datetime, ate: datetime, estacoes: list[str]) -> pd.DataFrame:
    return _filtrar("fato_risco", origem, "medido_em", de, ate, estacoes)


def eventos(origem: str, de: datetime, ate: datetime, estacoes: list[str]) -> pd.DataFrame:
    return _filtrar("fato_evento", origem, "inicio", de, ate, estacoes)


def alertas(origem: str, de: datetime, ate: datetime, estacoes: list[str]) -> pd.DataFrame:
    return _filtrar("fato_alerta", origem, "emitido_em", de, ate, estacoes)


def dim_estacao() -> pd.DataFrame:
    arquivo = _gold("dim_estacao")
    return pd.read_parquet(arquivo) if arquivo else pd.DataFrame()


def ocorrencias(estacoes: list[str]) -> pd.DataFrame:
    arquivo = _gold("fato_ocorrencia")
    if arquivo is None:
        return pd.DataFrame(columns=["ocorrencia_id", "estacao_id", "tipo", "status", "criada_em"])
    tabela = pd.read_parquet(arquivo)
    return tabela[tabela["estacao_id"].isin(estacoes)]


def saude_do_pipeline() -> dict:
    """Batimentos gravados pelo gateway, pelo pipeline e pela IA: base do painel de monitoramento."""
    raiz = camadas.raiz_lake()
    return {
        "gateway MQTT": camadas.ler_json(raiz / "landing" / "_gateway_batimento.json"),
        "pipeline": camadas.ler_json(raiz / "gold" / "_pipeline_batimento.json"),
        "IA": camadas.ler_json(raiz / "gold" / "_ia_batimento.json"),
    }


def volumes_por_camada() -> pd.DataFrame:
    """Arquivos e tamanho por camada do lake: mostra o caminho do dado da coleta ao gold."""
    raiz = camadas.raiz_lake()
    linhas = []
    for camada in camadas.CAMADAS:
        arquivos = [a for a in (raiz / camada).rglob("*") if a.is_file() and not a.name.startswith("_")]
        linhas.append(
            {
                "camada": camada,
                "arquivos": len(arquivos),
                "tamanho_MB": round(sum(a.stat().st_size for a in arquivos) / 1e6, 2),
            }
        )
    return pd.DataFrame(linhas)


def quarentena() -> pd.DataFrame:
    """Leituras reprovadas pelo contrato, com o motivo."""
    partes = [pd.read_parquet(a).assign(arquivo=a.name) for a in (camadas.raiz_lake() / "quarentena").glob("*.parquet")]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
