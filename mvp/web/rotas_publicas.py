"""Telas públicas (sem login): início, estações, status em texto puro, saúde e métricas."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from comum.estacoes import carregar_estacoes
from mvp.web import apresentacao, banco, grafico
from mvp.web.apoio import Banco, UsuarioOpcional, renderizar

rotas = APIRouter()


@rotas.get("/")
def inicio(request: Request, usuario: UsuarioOpcional, con: Banco, auto: str = "") -> Response:
    """Situação atual de cada estação, sem login e com poucos KB."""
    situacoes = banco.listar_situacoes(con)
    return renderizar(
        request,
        "inicio.html",
        situacoes=situacoes,
        faixa_demo=apresentacao.faixa_demonstracao(list(situacoes.values())),
        auto_atualizar=auto == "1",
    )


# Números nacionais de emergência (gratuitos) e o 156 da Prefeitura de São Paulo para o que não é urgente.
TELEFONES_DE_EMERGENCIA = [
    {"numero": "199", "nome": "Defesa Civil", "quando": "Enchente, alagamento, deslizamento ou casa em risco."},
    {"numero": "193", "nome": "Bombeiros", "quando": "Alguém ilhado, preso ou em perigo na água."},
    {"numero": "192", "nome": "SAMU", "quando": "Alguém ferido ou passando mal."},
    {"numero": "190", "nome": "Polícia Militar", "quando": "Risco à segurança durante a emergência."},
    {"numero": "156", "nome": "Prefeitura de São Paulo", "quando": "Sem urgência: bueiro entupido, lixo no córrego."},
]


@rotas.get("/emergencia")
def emergencia(request: Request, usuario: UsuarioOpcional) -> Response:
    """Telefones de emergência num lugar só — tela pedida numa conversa de validação com pessoas reais."""
    return renderizar(request, "emergencia.html", telefones=TELEFONES_DE_EMERGENCIA)


@rotas.get("/estacoes")
def lista_estacoes(request: Request, usuario: UsuarioOpcional, con: Banco) -> Response:
    situacoes = banco.listar_situacoes(con)
    faixa = apresentacao.faixa_demonstracao(list(situacoes.values()))
    return renderizar(request, "estacoes.html", situacoes=situacoes, faixa_demo=faixa)


@rotas.get("/estacoes/{estacao_id}")
def detalhe_estacao(request: Request, estacao_id: str, usuario: UsuarioOpcional, con: Banco) -> Response:
    estacao = carregar_estacoes().get(estacao_id)
    if estacao is None:
        raise HTTPException(status_code=404)
    situacao = banco.buscar_situacao(con, estacao_id)
    serie = situacao["serie"] if situacao else []
    return renderizar(
        request,
        "estacao_detalhe.html",
        estacao=estacao,
        situacao=situacao,
        dado_velho=apresentacao.dado_velho(situacao),
        grafico=grafico.grafico_nivel(serie, estacao),
        tabela=grafico.tabela_da_serie(serie),
        alertas=banco.listar_alertas(con, estacao_id, limite=5),
        faixa_demo=apresentacao.faixa_demonstracao([situacao]),
    )


def _linha_de_status(estacao, situacao: dict | None) -> str:
    nome = apresentacao.sem_acento(estacao.nome)
    if situacao is None:
        return f"{estacao.estacao_id} {nome}: SEM LEITURA"
    rotulo = apresentacao.sem_acento(apresentacao.RISCOS[situacao["nivel_risco"]]["rotulo"]).upper()
    return (
        f"{estacao.estacao_id} {nome}: {rotulo} ({situacao['nivel_risco']})"
        f" | nivel {situacao['nivel_pct_cota']:.0f}% da cota"
        f" | chuva 1h {situacao['chuva_1h']:.1f} mm | leitura {apresentacao.data_hora(situacao['atualizado_em'])}"
    )


@rotas.get("/status.txt")
def status_texto(con: Banco) -> PlainTextResponse:
    """Uma linha por estação, em texto puro sem acento: abre até em conexão muito ruim."""
    situacoes = banco.listar_situacoes(con)
    linhas = ["VigIA - situacao das estacoes (horario de Brasilia). Emergencia: 199 Defesa Civil, 193 Bombeiros"]
    linhas += [_linha_de_status(est, situacoes.get(est.estacao_id)) for est in carregar_estacoes().values()]
    return PlainTextResponse("\n".join(linhas) + "\n")


@rotas.get("/health")
def saude(con: Banco) -> JSONResponse:
    """Usado pelo Docker e pelo monitoramento: o app responde e o banco está acessível?"""
    try:
        ultima = banco.ultima_situacao_em(con)
    except sqlite3.Error:
        return JSONResponse({"status": "erro", "banco": "erro", "ultima_situacao_em": None}, status_code=503)
    return JSONResponse({"status": "ok", "banco": "ok", "ultima_situacao_em": ultima})


@rotas.get("/metrics")
def metricas(request: Request) -> PlainTextResponse:
    return PlainTextResponse(request.app.state.metricas.texto(), media_type="text/plain; version=0.0.4")
