"""Apoio comum às rotas: conexão por requisição, usuário da sessão, controle de acesso, CSRF e renderização."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from comum.estacoes import carregar_estacoes
from mvp.web import apresentacao, banco, seguranca

PASTA = Path(__file__).resolve().parent

# autoescape=True: todo dado mostrado nas telas é escapado (defesa contra XSS). Não usamos |safe em dado de usuário.
_ambiente_jinja = Environment(loader=FileSystemLoader(PASTA / "templates"), autoescape=True)
_ambiente_jinja.filters.update(apresentacao.FILTROS)
_ambiente_jinja.globals.update(
    RISCOS=apresentacao.RISCOS,
    TIPOS_OCORRENCIA=apresentacao.TIPOS_OCORRENCIA,
    STATUS_OCORRENCIA=apresentacao.STATUS_OCORRENCIA,
    # Muda quando o CSS muda: o navegador pode guardar o arquivo em cache sem mostrar versão velha.
    versao_estaticos=lambda: int((PASTA / "static" / "estilo.css").stat().st_mtime),
)
MODELOS = Jinja2Templates(env=_ambiente_jinja)


class LoginNecessario(Exception):
    """Levantada quando a tela exige login; o app responde redirecionando para /entrar."""


def obter_banco(request: Request) -> Iterator[sqlite3.Connection]:
    """Uma conexão por requisição, fechada ao final mesmo se der erro."""
    con = banco.conectar(request.app.state.cfg.db)
    try:
        yield con
    finally:
        con.close()


# Apelidos usados nas assinaturas das rotas: o FastAPI lê o Annotated e injeta a dependência.
Banco = Annotated[sqlite3.Connection, Depends(obter_banco)]
Campo = Annotated[str, Form()]  # campo de formulário (texto); o valor padrão "" evita erro 422 cru do framework


def usuario_da_sessao(request: Request, con: sqlite3.Connection) -> sqlite3.Row | None:
    """Lê o usuário do cookie assinado e confere se a sessão ainda vale (não saiu, não foi excluído)."""
    usuario_id = request.session.get("uid")
    if usuario_id is None:
        return None
    usuario = banco.usuario_por_id(con, usuario_id)
    if usuario is None or usuario["versao_sessao"] != request.session.get("v"):
        request.session.clear()
        return None
    return usuario


def usuario_opcional(request: Request, con: Banco) -> sqlite3.Row | None:
    """Para telas públicas: identifica o usuário, se houver, só para montar o menu."""
    request.state.usuario = usuario_da_sessao(request, con)
    return request.state.usuario


UsuarioOpcional = Annotated[sqlite3.Row | None, Depends(usuario_opcional)]


def exigir_login(usuario: UsuarioOpcional) -> sqlite3.Row:
    if usuario is None:
        raise LoginNecessario()
    return usuario


UsuarioLogado = Annotated[sqlite3.Row, Depends(exigir_login)]


def exigir_agente(usuario: UsuarioLogado) -> sqlite3.Row:
    """Controle de acesso por papel: morador recebe 403 nas telas do agente."""
    if usuario["papel"] != "agente":
        raise HTTPException(status_code=403, detail="Esta área é só para agentes da Defesa Civil.")
    return usuario


UsuarioAgente = Annotated[sqlite3.Row, Depends(exigir_agente)]


def iniciar_sessao(request: Request, usuario: sqlite3.Row) -> None:
    """Login: descarta a sessão anterior inteira e cria outra (novo token CSRF), contra fixação de sessão."""
    request.session.clear()
    request.session["uid"] = usuario["id"]
    request.session["v"] = usuario["versao_sessao"]
    request.session["csrf"] = seguranca.novo_token()


def token_csrf(request: Request) -> str:
    """Um token aleatório por sessão, colocado em todo formulário."""
    if "csrf" not in request.session:
        request.session["csrf"] = seguranca.novo_token()
    return request.session["csrf"]


def verificar_csrf(request: Request, csrf_token: Annotated[str | None, Form()] = None) -> None:
    """Todo POST de formulário precisa trazer o token da sessão; sem ele, 403."""
    esperado = request.session.get("csrf", "")
    if not esperado or not seguranca.iguais(esperado, csrf_token or ""):
        raise HTTPException(
            status_code=403, detail="Formulário expirado ou inválido. Volte, atualize a página e tente de novo."
        )


def avisar(request: Request, texto: str, tipo: str = "ok") -> None:
    """Guarda um aviso na sessão para aparecer uma única vez na próxima tela."""
    request.session["aviso"] = {"texto": texto, "tipo": tipo}


def redirecionar(url: str) -> RedirectResponse:
    """303: depois de um POST o navegador faz GET na nova tela (recarregar não reenvia o formulário)."""
    return RedirectResponse(url, status_code=303)


def _classes_do_corpo(usuario: sqlite3.Row | None) -> str:
    """Preferências de acessibilidade do perfil viram classes CSS no <body>."""
    if usuario is None:
        return ""
    classes = [
        nome
        for nome, coluna in (("fonte-grande", "fonte_grande"), ("alto-contraste", "alto_contraste"))
        if usuario[coluna]
    ]
    return " ".join(classes)


def renderizar(request: Request, modelo: str, status: int = 200, **contexto) -> Response:
    """Monta a tela com o que toda página precisa: usuário, token CSRF, aviso pendente e catálogo de estações."""
    usuario = getattr(request.state, "usuario", None)
    contexto.update(
        usuario=usuario,
        csrf=lambda: token_csrf(request),  # só cria o token (e o cookie) nas telas que têm formulário
        aviso=request.session.pop("aviso", None),
        classes_corpo=_classes_do_corpo(usuario),
        estacoes=carregar_estacoes(),
    )
    return MODELOS.TemplateResponse(request, modelo, contexto, status_code=status)
