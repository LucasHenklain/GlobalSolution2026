"""API interna (contrato técnico, seção 5): por onde o pipeline e o agente de alerta entregam dados ao app."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import AwareDatetime

from comum.estacoes import carregar_estacoes
from comum.log import obter_logger
from mvp.web import avisos, banco, seguranca
from mvp.web.apoio import Banco
from mvp.web.modelos import Alerta, Situacao, para_iso

log = obter_logger("web.interno")


def exigir_token_interno(request: Request, x_token_interno: Annotated[str | None, Header()] = None) -> None:
    """Só quem conhece o VIGIA_TOKEN_INTERNO entra; a comparação é em tempo constante."""
    esperado = request.app.state.cfg.token_interno
    # Token vazio na configuração nunca vale: senão uma requisição sem cabeçalho passaria.
    if not esperado or not seguranca.iguais(x_token_interno or "", esperado):
        raise HTTPException(status_code=401, detail="Token interno ausente ou inválido.")


def _exigir_estacao_do_catalogo(estacao_id: str) -> None:
    if estacao_id not in carregar_estacoes():
        raise HTTPException(status_code=422, detail=f"Estação fora do catálogo: {estacao_id}")


rotas = APIRouter(prefix="/api/interno", dependencies=[Depends(exigir_token_interno)])


@rotas.post("/situacao")
def receber_situacao(request: Request, situacoes: list[Situacao], con: Banco) -> dict:
    """Substitui a situação atual das estações recebidas."""
    if len(situacoes) > 50:
        raise HTTPException(status_code=422, detail="Lote grande demais (máximo de 50 situações).")
    for situacao in situacoes:
        _exigir_estacao_do_catalogo(situacao.estacao_id)
    atualizadas = banco.salvar_situacoes(con, [s.para_banco() for s in situacoes])
    request.app.state.metricas.contar("vigia_situacoes_recebidas_total", atualizadas)
    return {"atualizadas": atualizadas}


@rotas.post("/alertas")
def receber_alerta(request: Request, alerta: Alerta, con: Banco) -> dict:
    """Idempotente por alerta_id: reenviar o mesmo alerta não duplica o registro nem os SMS."""
    _exigir_estacao_do_catalogo(alerta.estacao_id)
    novo, enfileirados = avisos.receber_alerta(con, alerta.para_banco())
    if novo:
        metricas = request.app.state.metricas
        metricas.contar("vigia_alertas_recebidos_total")
        metricas.contar("vigia_sms_enfileirados_total", enfileirados)
        dados = {"alerta_id": alerta.alerta_id, "nivel_risco": alerta.nivel_risco, "sms": enfileirados}
        log.info("alerta recebido", extra={"dados": dados})
    return {"alerta_id": alerta.alerta_id, "novo": novo, "sms_enfileirados": enfileirados}


@rotas.get("/ocorrencias")
def listar_ocorrencias(con: Banco, desde: AwareDatetime | None = None) -> dict:
    """Ocorrências criadas ou alteradas desde a data, sem nenhum dado pessoal de quem relatou."""
    return {"ocorrencias": banco.ocorrencias_desde(con, para_iso(desde) if desde else None)}
