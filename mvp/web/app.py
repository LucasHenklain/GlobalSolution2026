"""App web do VigIA (FastAPI + Jinja2). Rodar da raiz do repositório: python -m uvicorn mvp.web.app:app --port 8000"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as ErroHTTP
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from comum.config import carregar_config
from comum.log import obter_logger
from mvp.web import apoio, banco, rotas_agente, rotas_conta, rotas_interno, rotas_morador, rotas_publicas, seguranca
from mvp.web.metricas import Metricas

log = obter_logger("web.app")

LIMITE_CORPO_BYTES = 256 * 1024  # nenhum formulário ou lote do pipeline chega perto disso
DURACAO_SESSAO_S = 7 * 24 * 3600

# Sem script (nem inline, nem de fora) e sem recursos de outros sites: reduz muito o estrago de um XSS.
CSP = (
    "default-src 'self'; script-src 'none'; style-src 'self'; img-src 'self' data:; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)
CABECALHOS_SEGURANCA = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}

TITULOS_ERRO = {403: "Acesso não permitido", 404: "Página não encontrada", 422: "Endereço inválido"}


async def _cabecalhos_e_metricas(request: Request, chamar_proximo) -> Response:
    """Passa por toda requisição: recusa corpo gigante, conta a requisição e põe os cabeçalhos de segurança."""
    metricas: Metricas = request.app.state.metricas
    tamanho = request.headers.get("content-length", "0")
    if not tamanho.isdecimal() or int(tamanho) > LIMITE_CORPO_BYTES:
        return PlainTextResponse("Requisição grande demais.", status_code=413)
    resposta = await chamar_proximo(request)
    metricas.contar("vigia_requisicoes_total")
    if resposta.status_code >= 500:
        metricas.contar("vigia_respostas_erro_total")
    for nome, valor in CABECALHOS_SEGURANCA.items():
        resposta.headers[nome] = valor
    # Arquivos estáticos ficam em cache (economiza dados do morador); telas nunca, pois podem ter dado pessoal.
    estatico = request.url.path.startswith("/static/")
    resposta.headers["Cache-Control"] = "public, max-age=86400" if estatico else "no-store"
    return resposta


def _pagina_de_erro(request: Request, status: int, detalhe: str) -> Response:
    """Tela de erro amigável, com o menu do usuário quando ele está logado."""
    if not hasattr(request.state, "usuario"):
        con = banco.conectar(request.app.state.cfg.db)
        try:
            request.state.usuario = apoio.usuario_da_sessao(request, con)
        finally:
            con.close()
    titulo = TITULOS_ERRO.get(status, "Algo deu errado")
    return apoio.renderizar(request, "erro.html", status=status, codigo=status, titulo_erro=titulo, detalhe=detalhe)


async def _tratar_login_necessario(request: Request, erro: apoio.LoginNecessario) -> Response:
    apoio.avisar(request, "Entre na sua conta para continuar.", "info")
    return apoio.redirecionar("/entrar")


async def _tratar_erro_http(request: Request, erro: ErroHTTP) -> Response:
    """A API interna responde JSON; as telas respondem uma página de erro em linguagem simples."""
    if request.url.path.startswith("/api/"):
        return await http_exception_handler(request, erro)
    detalhe = erro.detail if erro.status_code == 403 else ""
    return _pagina_de_erro(request, erro.status_code, str(detalhe))


async def _tratar_erro_validacao(request: Request, erro: RequestValidationError) -> Response:
    if request.url.path.startswith("/api/"):
        return await request_validation_exception_handler(request, erro)
    return _pagina_de_erro(request, 422, "")


def criar_app() -> FastAPI:
    """Monta o app com a configuração do ambiente atual (os testes chamam de novo com banco temporário)."""
    cfg = carregar_config()
    banco.criar_tabelas(cfg.db)
    # Documentação automática desligada: a API é interna e as páginas /docs dependeriam de scripts externos.
    app = FastAPI(title="VigIA", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.cfg = cfg
    app.state.metricas = Metricas()
    app.state.limite_login = seguranca.LimiteLogin()

    # Sessão em cookie assinado: httponly (o Starlette sempre põe), SameSite=Lax e Secure em produção.
    app.add_middleware(
        SessionMiddleware,
        secret_key=seguranca.chave_de_sessao(cfg),
        session_cookie="vigia_sessao",
        max_age=DURACAO_SESSAO_S,
        same_site="lax",
        https_only=cfg.ambiente == "prod",
    )
    app.middleware("http")(_cabecalhos_e_metricas)
    app.add_middleware(GZipMiddleware, minimum_size=500)  # páginas menores na rede do morador

    app.mount("/static", StaticFiles(directory=apoio.PASTA / "static"), name="static")
    for modulo in (rotas_publicas, rotas_conta, rotas_morador, rotas_agente, rotas_interno):
        app.include_router(modulo.rotas)

    app.add_exception_handler(apoio.LoginNecessario, _tratar_login_necessario)
    app.add_exception_handler(ErroHTTP, _tratar_erro_http)
    app.add_exception_handler(RequestValidationError, _tratar_erro_validacao)
    log.info("app pronto", extra={"dados": {"ambiente": cfg.ambiente}})
    return app


app = criar_app()
