"""Telas do morador (com login): minha área, alertas e ocorrências."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from comum.estacoes import carregar_estacoes
from comum.log import obter_logger
from mvp.web import apresentacao, banco, grafico, validacao
from mvp.web.apoio import Banco, Campo, UsuarioLogado, avisar, redirecionar, renderizar, verificar_csrf

rotas = APIRouter()
log = obter_logger("web.morador")


@rotas.get("/minha-area")
def minha_area(request: Request, usuario: UsuarioLogado, con: Banco, auto: str = "") -> Response:
    """Painel do morador: risco da área dele, o porquê, a previsão, o gráfico e o que fazer."""
    estacao = carregar_estacoes().get(usuario["estacao_id"] or "")
    if estacao is None:  # agente não tem área de moradia: o painel dele é outro
        return redirecionar("/agente" if usuario["papel"] == "agente" else "/perfil")
    situacao = banco.buscar_situacao(con, estacao.estacao_id)
    alertas = banco.listar_alertas(con, estacao.estacao_id, limite=1)
    ultimo_alerta = alertas[0] if alertas else None
    nivel = situacao["nivel_risco"] if situacao else "sem_dados"
    # "Por quê": os motivos do último alerta valem enquanto o risco é o mesmo; senão, os números da situação.
    if ultimo_alerta and ultimo_alerta["motivo"] and ultimo_alerta["nivel_risco"] == nivel:
        motivos = ultimo_alerta["motivo"]
    else:
        motivos = apresentacao.motivos_da_situacao(situacao) if situacao else []
    serie = situacao["serie"] if situacao else []
    return renderizar(
        request,
        "minha_area.html",
        estacao=estacao,
        situacao=situacao,
        nivel=nivel,
        motivos=motivos,
        orientacoes=apresentacao.ORIENTACOES[nivel],
        ultimo_alerta=ultimo_alerta,
        dado_velho=apresentacao.dado_velho(situacao),
        grafico=grafico.grafico_nivel(serie, estacao),
        tabela=grafico.tabela_da_serie(serie),
        faixa_demo=apresentacao.faixa_demonstracao([situacao]),
        auto_atualizar=auto == "1",
    )


# ---------- alertas ----------


@rotas.get("/alertas")
def lista_alertas(request: Request, usuario: UsuarioLogado, con: Banco) -> Response:
    """Morador vê os alertas da própria área; agente vê os de todas."""
    filtro = None if usuario["papel"] == "agente" else usuario["estacao_id"]
    return renderizar(request, "alertas.html", alertas=banco.listar_alertas(con, filtro), todas=filtro is None)


@rotas.get("/alertas/{alerta_id}")
def detalhe_alerta(request: Request, alerta_id: str, usuario: UsuarioLogado, con: Banco) -> Response:
    alerta = banco.buscar_alerta(con, alerta_id)
    if alerta is None:
        raise HTTPException(status_code=404)
    origem = apresentacao.ORIGENS_DECISAO.get(alerta["origem_decisao"], alerta["origem_decisao"])
    return renderizar(request, "alerta_detalhe.html", alerta=alerta, origem_texto=origem)


# ---------- ocorrências ----------


@rotas.get("/ocorrencias")
def minhas_ocorrencias(request: Request, usuario: UsuarioLogado, con: Banco) -> Response:
    """Só as ocorrências do próprio usuário (o filtro por dono é feito no SQL)."""
    return renderizar(request, "ocorrencias.html", ocorrencias=banco.ocorrencias_do_usuario(con, usuario["id"]))


@rotas.get("/ocorrencias/nova")
def tela_nova_ocorrencia(request: Request, usuario: UsuarioLogado) -> Response:
    valores = {"tipo": "", "descricao": "", "estacao_id": usuario["estacao_id"] or ""}
    return renderizar(request, "ocorrencia_nova.html", valores=valores, erros={}, max_descricao=validacao.MAX_DESCRICAO)


@rotas.post("/ocorrencias/nova", dependencies=[Depends(verificar_csrf)])
def criar_ocorrencia(
    request: Request,
    usuario: UsuarioLogado,
    con: Banco,
    tipo: Campo = "",
    descricao: Campo = "",
    estacao_id: Campo = "",
) -> Response:
    form = {"tipo": tipo, "descricao": descricao, "estacao_id": estacao_id}
    dados, erros = validacao.validar_ocorrencia(form)
    if erros:
        return renderizar(
            request,
            "ocorrencia_nova.html",
            status=422,
            valores=form,
            erros=erros,
            max_descricao=validacao.MAX_DESCRICAO,
        )
    ocorrencia_id = banco.criar_ocorrencia(con, usuario["id"], dados["estacao_id"], dados["tipo"], dados["descricao"])
    request.app.state.metricas.contar("vigia_ocorrencias_criadas_total")
    log.info("ocorrência criada", extra={"dados": {"ocorrencia_id": ocorrencia_id, "tipo": dados["tipo"]}})
    avisar(request, "Ocorrência enviada. A Defesa Civil vai ver o seu relato.")
    return redirecionar("/ocorrencias")
