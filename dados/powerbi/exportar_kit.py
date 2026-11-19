"""Exporta um kit para montar as medidas no Power BI sem precisar rodar o projeto (nem Docker, nem Python).

Uso (a partir da raiz, depois de `python -m devops.preparar`):  python -m dados.powerbi.exportar_kit
Saída: entrega/powerbi_kit/  (arquivos Parquet do gold, medidas.dax, LEIA-ME) e entrega/VigIA_kit_powerbi.zip

Recorta o período de teste da IA (2024–2025) para o arquivo ficar leve, e grava as datas já no horário de Brasília,
sem fuso, que é como o Power BI trabalha melhor.
"""

from __future__ import annotations

import shutil
import zipfile

import pandas as pd

from comum.config import RAIZ
from dados import camadas, medidas

DESTINO = RAIZ / "entrega" / "powerbi_kit"
PACOTE = RAIZ / "entrega" / "VigIA_kit_powerbi.zip"
INICIO, FIM = "2024-01-01", "2026-01-01"
FUSO = "America/Sao_Paulo"
EXEMPLO = ("2025-01-24", "2025-01-26")  # período usado para conferir as medidas (o temporal da demonstração)


def _local(serie: pd.Series) -> pd.Series:
    """Converte UTC para o horário de Brasília e tira o fuso (o Power BI não lida bem com fuso nas relações)."""
    return serie.dt.tz_convert(FUSO).dt.tz_localize(None)


def _gold(tabela: str) -> pd.DataFrame:
    return camadas.ler_parquet(camadas.caminho("gold", tabela, "origem=historico", "dados.parquet"))


def exportar() -> dict:
    DESTINO.mkdir(parents=True, exist_ok=True)
    tabelas = {}

    leitura = _gold("fato_leitura")
    leitura = leitura[(leitura["medido_em"] >= INICIO) & (leitura["medido_em"] < FIM)].drop(
        columns=["recebido_em", "fonte", "origem"]
    )
    leitura["medido_em"] = _local(leitura["medido_em"])
    leitura["data"] = leitura["medido_em"].dt.normalize()
    tabelas["fato_leitura"] = leitura

    risco = _gold("fato_risco")
    risco = risco[(risco["medido_em"] >= INICIO) & (risco["medido_em"] < FIM)].drop(columns=["origem_decisao"])
    risco["medido_em"] = _local(risco["medido_em"])
    risco["data"] = risco["medido_em"].dt.normalize()
    tabelas["fato_risco"] = risco

    alerta = _gold("fato_alerta")
    alerta = alerta[(alerta["emitido_em"] >= INICIO) & (alerta["emitido_em"] < FIM)].drop(columns=["origem"])
    alerta["emitido_em"] = _local(alerta["emitido_em"])
    alerta["data"] = alerta["emitido_em"].dt.normalize()
    tabelas["fato_alerta"] = alerta

    evento = _gold("fato_evento")
    evento = evento[(evento["inicio"] >= INICIO) & (evento["inicio"] < FIM)].drop(columns=["origem"])
    for coluna in ("inicio", "fim"):
        evento[coluna] = _local(evento[coluna])
    evento["data"] = evento["inicio"].dt.normalize()
    tabelas["fato_evento"] = evento

    tabelas["dim_estacao"] = camadas.ler_parquet(camadas.caminho("gold", "dim_estacao.parquet"))
    datas = pd.date_range(INICIO, pd.Timestamp(FIM) - pd.Timedelta(days=1), freq="D")
    tabelas["dim_data"] = pd.DataFrame(
        {
            "data": datas,
            "ano": datas.year,
            "mes": datas.month,
            "ano_mes": datas.strftime("%Y-%m"),
            "dia_da_semana": datas.dayofweek + 1,
        }
    )

    for nome, tabela in tabelas.items():
        tabela.to_parquet(DESTINO / f"{nome}.parquet", index=False)
    shutil.copy2(RAIZ / "dados" / "powerbi" / "medidas.dax", DESTINO / "medidas.dax")
    shutil.copy2(RAIZ / "dados" / "powerbi" / "LEIA-ME_PowerBI.md", DESTINO / "LEIA-ME_PowerBI.md")
    return tabelas


def valores_de_conferencia(tabelas: dict) -> dict:
    """Calcula em Python, no período de exemplo, os mesmos números que as medidas DAX devem mostrar no Power BI."""
    de, ate = pd.Timestamp(EXEMPLO[0]), pd.Timestamp(EXEMPLO[1])
    leitura = tabelas["fato_leitura"][tabelas["fato_leitura"]["data"].between(de, ate - pd.Timedelta(days=1))]
    evento = tabelas["fato_evento"][tabelas["fato_evento"]["data"].between(de, ate - pd.Timedelta(days=1))]
    alerta = tabelas["fato_alerta"][tabelas["fato_alerta"]["data"].between(de, ate - pd.Timedelta(days=1))]
    return {
        "periodo": f"{EXEMPLO[0]} a {(ate - pd.Timedelta(days=1)).date()} (todas as estações)",
        "Chuva Acumulada (mm)": round(medidas.chuva_acumulada_mm(leitura), 1),
        "Nível Máximo (% da cota)": round(medidas.nivel_maximo_pct(leitura), 1),
        "Horas em Alerta": round(medidas.horas_acima_da_cota_de_alerta(leitura), 2),
        "Eventos de Transbordo": medidas.eventos_de_transbordo(evento),
        "Alertas Emitidos": medidas.alertas_emitidos(alerta),
    }


def main() -> None:
    tabelas = exportar()
    conferencia = valores_de_conferencia(tabelas)
    linhas = ["VALORES PARA CONFERIR NO POWER BI", f"Filtro: dim_data[data] de {conferencia.pop('periodo')}", ""]
    linhas += [f"{nome}: {valor}" for nome, valor in conferencia.items()]
    (DESTINO / "valores_para_conferir.txt").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    with zipfile.ZipFile(PACOTE, "w", zipfile.ZIP_DEFLATED) as pacote:
        for arquivo in sorted(DESTINO.iterdir()):
            pacote.write(arquivo, f"VigIA_kit_powerbi/{arquivo.name}")
    for nome, tabela in tabelas.items():
        print(f"{nome:14s} {len(tabela):>8,d} linhas".replace(",", "."))
    print("\n".join(linhas[1:]))
    print(f"\nKit: {PACOTE} ({PACOTE.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
