"""Modelos Pydantic da API interna (contrato técnico, seção 5): tudo que chega é validado antes de tocar o banco."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

NivelRisco = Literal["verde", "amarelo", "laranja", "vermelho"]
EstadoRegra = Literal["normal", "atencao", "alerta", "transbordo"]
Origem = Literal["wokwi", "emulador", "replay"]
OrigemDecisao = Literal["ia", "regra_local"]
TipoOcorrencia = Literal["bueiro_entupido", "lixo_no_corrego", "ponto_de_alagamento", "sirene_com_defeito", "outro"]
StatusOcorrencia = Literal["aberta", "em_atendimento", "resolvida"]

EstacaoId = Annotated[str, StringConstraints(pattern=r"^EST-[A-Z]{3}-\d{2}$")]
AlertaId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{3,64}$")]
Frase = Annotated[str, StringConstraints(min_length=1, max_length=200, strip_whitespace=True)]


def para_iso(momento: datetime) -> str:
    """Guarda toda data no formato do contrato (UTC, ISO 8601 com Z), para ordenar e comparar como texto."""
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PontoSerie(BaseModel):
    t: AwareDatetime
    nivel_cm: float = Field(ge=0, le=1000)
    chuva_mm: float = Field(ge=0, le=200)


class Situacao(BaseModel):
    estacao_id: EstacaoId
    atualizado_em: AwareDatetime
    nivel_cm: float = Field(ge=0, le=1000)
    nivel_pct_cota: float = Field(ge=0, le=500)
    chuva_1h: float = Field(ge=0, le=400)
    chuva_24h: float | None = Field(default=None, ge=0, le=2000)
    delta_nivel_30min: float | None = Field(default=None, ge=-1000, le=1000)
    prob_transbordo_60min: float | None = Field(default=None, ge=0, le=1)
    nivel_risco: NivelRisco
    estado_regra: EstadoRegra | None = None
    bateria_pct: float | None = Field(default=None, ge=0, le=100)
    origem: Origem | None = None
    serie: list[PontoSerie] = Field(default_factory=list, max_length=36)

    def para_banco(self) -> dict:
        dados = self.model_dump(exclude={"atualizado_em", "serie"})
        dados["atualizado_em"] = para_iso(self.atualizado_em)
        dados["serie"] = [{"t": para_iso(p.t), "nivel_cm": p.nivel_cm, "chuva_mm": p.chuva_mm} for p in self.serie]
        return dados


class Alerta(BaseModel):
    alerta_id: AlertaId
    estacao_id: EstacaoId
    emitido_em: AwareDatetime
    nivel_risco: NivelRisco
    prob: float | None = Field(default=None, ge=0, le=1)
    nivel_cm: float | None = Field(default=None, ge=0, le=1000)
    chuva_1h: float | None = Field(default=None, ge=0, le=400)
    titulo: Annotated[str, StringConstraints(min_length=1, max_length=140, strip_whitespace=True)]
    mensagem: Annotated[str, StringConstraints(min_length=1, max_length=1000, strip_whitespace=True)]
    mensagem_sms: Annotated[str, StringConstraints(min_length=1, max_length=160, strip_whitespace=True)]
    motivo: list[Frase] = Field(default_factory=list, max_length=10)
    orientacoes: list[Frase] = Field(default_factory=list, max_length=10)
    origem_decisao: OrigemDecisao

    def para_banco(self) -> dict:
        dados = self.model_dump(exclude={"emitido_em"})
        dados["emitido_em"] = para_iso(self.emitido_em)
        return dados
