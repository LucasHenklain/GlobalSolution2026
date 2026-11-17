"""Camada SILVER: dado limpo, tipado, validado pelo contrato e sem duplicatas. O que reprova vai para a quarentena."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from comum.config import RAIZ
from comum.estacoes import carregar_estacoes
from comum.log import obter_logger
from dados import camadas

log = obter_logger("dados.silver")
CONTRATO = RAIZ / "dados" / "contratos" / "leitura_sensor.v1.yaml"
COLUNAS_LEITURA = ["estacao_id", "medido_em", "nivel_cm", "chuva_mm", "bateria_pct", "origem", "recebido_em"]


@lru_cache(maxsize=1)
def carregar_contrato() -> dict:
    return yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- INMET (chuva real)


def _ler_csv_inmet(arquivo: Path) -> pd.DataFrame:
    """O CSV do INMET tem 8 linhas de cabeçalho, ';' como separador, vírgula decimal e codificação latin-1."""
    codigo = arquivo.name.split("_")[3]  # INMET_SE_SP_A701_SAO PAULO - MIRANTE_...
    bruto = pd.read_csv(arquivo, sep=";", skiprows=8, encoding="latin1", decimal=",", usecols=[0, 1, 2], dtype=str)
    bruto.columns = ["data", "hora", "chuva"]
    medido_em = pd.to_datetime(bruto["data"] + " " + bruto["hora"].str[:4], format="%Y/%m/%d %H%M", utc=True)
    chuva = pd.to_numeric(bruto["chuva"].str.replace(",", "."), errors="coerce")
    chuva = chuva.where(chuva >= 0)  # o INMET usa -9999 para "sem medição"
    return pd.DataFrame({"estacao_inmet": codigo, "medido_em": medido_em, "chuva_mm": chuva})


def processar_inmet() -> pd.DataFrame:
    """Junta os arquivos anuais, remove duplicatas e marca as horas sem medição (não inventa chuva)."""
    arquivos = sorted(camadas.caminho("bronze", "inmet").glob("*.CSV"))
    if not arquivos:
        raise FileNotFoundError("bronze/inmet vazio: rode a ingestão do INMET antes")
    chuva = pd.concat([_ler_csv_inmet(a) for a in arquivos], ignore_index=True)
    chuva = chuva.drop_duplicates(["estacao_inmet", "medido_em"]).sort_values(["estacao_inmet", "medido_em"])
    chuva["faltante"] = chuva["chuva_mm"].isna()
    camadas.escrever_parquet(chuva, camadas.caminho("silver", "chuva_inmet.parquet"))
    log.info(
        "silver inmet",
        extra={"dados": {"horas": len(chuva), "pct_faltante": round(float(chuva["faltante"].mean()) * 100, 2)}},
    )
    return chuva


# ---------------------------------------------------------------- leituras das estações


def validar_leituras(bruto: pd.DataFrame, agora: datetime | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aplica as regras LEI-01..07 do contrato. Devolve (válidas, rejeitadas com a coluna 'motivo')."""
    campos = carregar_contrato()["campos"]
    agora = agora or datetime.now(UTC)
    df = bruto.copy()
    for coluna in COLUNAS_LEITURA:
        if coluna not in df.columns:
            df[coluna] = None

    df["medido_em"] = pd.to_datetime(df["medido_em"], utc=True, errors="coerce")
    df["recebido_em"] = pd.to_datetime(df["recebido_em"], utc=True, errors="coerce")
    for coluna in ("nivel_cm", "chuva_mm", "bateria_pct"):
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce")

    motivo = pd.Series("", index=df.index)

    def reprovar(mascara: pd.Series, texto: str) -> None:
        """Guarda só o primeiro motivo de cada linha: é o que basta para investigar."""
        motivo.loc[mascara & (motivo == "")] = texto

    reprovar(df["estacao_id"].isna() | df["medido_em"].isna(), "LEI-01 campo obrigatório ausente ou inválido")
    reprovar(df["nivel_cm"].isna() | df["chuva_mm"].isna(), "LEI-01 campo obrigatório ausente ou inválido")
    reprovar(~df["estacao_id"].isin(carregar_estacoes().keys()), "LEI-02 estação fora do catálogo")
    nivel, chuva = campos["nivel_cm"], campos["chuva_mm"]
    reprovar(~df["nivel_cm"].between(nivel["minimo"], nivel["maximo"]), "LEI-03 nível fora da faixa")
    reprovar(~df["chuva_mm"].between(chuva["minimo"], chuva["maximo"]), "LEI-04 chuva fora da faixa")
    reprovar(df["medido_em"] > agora + timedelta(minutes=5), "LEI-05 leitura no futuro")

    # LEI-07: bateria absurda não invalida a leitura de nível; só o campo é anulado.
    df.loc[~df["bateria_pct"].between(0, 100), "bateria_pct"] = None

    rejeitadas = df[motivo != ""].assign(motivo=motivo[motivo != ""])
    validas = df[motivo == ""]
    # LEI-06: mesma estação e mesmo instante → fica a que o gateway recebeu por último.
    validas = validas.sort_values("recebido_em", na_position="first").drop_duplicates(
        ["estacao_id", "medido_em"], keep="last"
    )
    return validas[COLUNAS_LEITURA].sort_values(["estacao_id", "medido_em"]), rejeitadas


def _ler_bronze_sensores() -> pd.DataFrame:
    lotes = sorted(camadas.caminho("bronze", "sensores").glob("data=*/*.jsonl"))
    partes = [pd.read_json(lote, lines=True, dtype=False) for lote in lotes if lote.stat().st_size > 0]
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLUNAS_LEITURA)


def processar_leituras(origem: str) -> pd.DataFrame:
    """origem='sensor' (MQTT ao vivo) ou 'historico' (simulado sobre o INMET): as duas passam pela MESMA validação."""
    if origem == "sensor":
        bruto = _ler_bronze_sensores()
    else:
        arquivos = sorted(camadas.caminho("bronze", "sensores_simulados").glob("estacao=*/*.parquet"))
        bruto = pd.concat([pd.read_parquet(a) for a in arquivos], ignore_index=True)
    validas, rejeitadas = validar_leituras(bruto)
    camadas.escrever_parquet(validas, camadas.caminho("silver", "leituras", f"origem={origem}", "leituras.parquet"))
    if len(rejeitadas):
        rejeitadas = rejeitadas.astype({c: str for c in rejeitadas.columns if rejeitadas[c].dtype == object})
        camadas.escrever_parquet(rejeitadas, camadas.caminho("quarentena", f"leituras_{origem}.parquet"))
    log.info(
        "silver leituras",
        extra={
            "dados": {"origem": origem, "lidas": len(bruto), "validas": len(validas), "quarentena": len(rejeitadas)}
        },
    )
    return validas
