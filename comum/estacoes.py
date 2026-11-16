"""Catálogo das estações de monitoramento (dados/referencia/estacoes.csv), usado por todas as áreas."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from comum.config import RAIZ

ARQUIVO = RAIZ / "dados" / "referencia" / "estacoes.csv"


@dataclass(frozen=True)
class Estacao:
    estacao_id: str
    nome: str
    bairro: str
    zona: str
    inmet: str
    altura_sensor_cm: float
    cota_atencao_cm: float
    cota_alerta_cm: float
    cota_transbordo_cm: float
    moradores_area: int
    lat: float
    lon: float

    def estado_regra(self, nivel_cm: float) -> str:
        """Regra de limiar fixo (a mesma que roda no firmware): é o 'antes' com que a IA é comparada."""
        if nivel_cm >= self.cota_transbordo_cm:
            return "transbordo"
        if nivel_cm >= self.cota_alerta_cm:
            return "alerta"
        if nivel_cm >= self.cota_atencao_cm:
            return "atencao"
        return "normal"


@lru_cache(maxsize=4)
def _ler(caminho: str) -> dict[str, Estacao]:
    with open(caminho, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    estacoes = {}
    for linha in linhas:
        estacoes[linha["estacao_id"]] = Estacao(
            estacao_id=linha["estacao_id"],
            nome=linha["nome"],
            bairro=linha["bairro"],
            zona=linha["zona"],
            inmet=linha["inmet"],
            altura_sensor_cm=float(linha["altura_sensor_cm"]),
            cota_atencao_cm=float(linha["cota_atencao_cm"]),
            cota_alerta_cm=float(linha["cota_alerta_cm"]),
            cota_transbordo_cm=float(linha["cota_transbordo_cm"]),
            moradores_area=int(linha["moradores_area"]),
            lat=float(linha["lat"]),
            lon=float(linha["lon"]),
        )
    return estacoes


def carregar_estacoes(caminho: Path | None = None) -> dict[str, Estacao]:
    """Devolve {estacao_id: Estacao}. O resultado fica em cache porque o catálogo não muda em execução."""
    return _ler(str(caminho or ARQUIVO))
