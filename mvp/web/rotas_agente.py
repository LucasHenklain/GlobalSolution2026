"""Painel do agente da Defesa Civil: fila de ocorrências, alertas, caixa de saída de SMS e comando da sirene."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from comum.log import obter_logger
from mvp.web import apresentacao, banco, mqtt_saida, validacao
from mvp.web.apoio import Banco, Campo, UsuarioAgente, avisar, redirecionar, renderizar, verificar_csrf

rotas = APIRouter(prefix="/agente")
log = obter_logger("web.agente")


@rotas.get("")
def painel(request: Request, usuario: UsuarioAgente, con: Banco, auto: str = "") -> Response:
    situacoes = banco.listar_situacoes(con)
    return renderizar(
        request,
        "agente.html",
        situacoes=situacoes,
        ocorrencias=banco.fila_ocorrencias(con),
        alertas=banco.listar_alertas(con, limite=8),
        sms=banco.listar_sms(con),
        comandos=banco.listar_comandos_sirene(con),
        faixa_demo=apresentacao.faixa_demonstracao(list(situacoes.values())),
        auto_atualizar=auto == "1",
    )


@rotas.post("/ocorrencias/{ocorrencia_id}/status", dependencies=[Depends(verificar_csrf)])
def mudar_status(
    request: Request,
    ocorrencia_id: int,
    usuario: UsuarioAgente,
    con: Banco,
    status: Campo = "",
) -> Response:
    if not validacao.status_valido(status):
        avisar(request, "Escolha um status válido para a ocorrência.", "erro")
    elif not banco.mudar_status_ocorrencia(con, ocorrencia_id, status):
        raise HTTPException(status_code=404)
    else:
        log.info("status de ocorrência alterado", extra={"dados": {"ocorrencia_id": ocorrencia_id, "status": status}})
        avisar(request, f"Ocorrência nº {ocorrencia_id}: {apresentacao.STATUS_OCORRENCIA[status].lower()}.")
    return redirecionar("/agente#ocorrencias")


@rotas.post("/sirene", dependencies=[Depends(verificar_csrf)])
def acionar_sirene(
    request: Request,
    usuario: UsuarioAgente,
    con: Banco,
    estacao_id: Campo = "",
    acao: Campo = "ligar",
    nivel: Campo = "vermelho",
    segundos: Campo = "30",
) -> Response:
    """Publica o comando do contrato 3.2. Se o broker estiver fora, a tela continua de pé e avisa o agente."""
    dados, erros = validacao.validar_sirene(
        {"estacao_id": estacao_id, "acao": acao, "nivel": nivel, "segundos": segundos}
    )
    if erros:
        avisar(request, " ".join(erros.values()), "erro")
        return redirecionar("/agente#sirenes")
    ultimos = banco.listar_alertas(con, dados["estacao_id"], limite=1)
    comando = {
        "acao": dados["acao"],
        "nivel": dados["nivel"],
        "segundos": dados["segundos"] if dados["acao"] == "ligar" else 0,
        "alerta_id": ultimos[0]["alerta_id"] if ultimos else None,
    }
    # Chamada pelo módulo (mqtt_saida.publicar_sirene) para os testes poderem trocar por um dublê.
    entregue = mqtt_saida.publicar_sirene(request.app.state.cfg, dados["estacao_id"], comando)
    banco.registrar_comando_sirene(con, comando, dados["estacao_id"], entregue)
    request.app.state.metricas.contar("vigia_comandos_sirene_total")
    log.info(
        "comando de sirene",
        extra={"dados": {"estacao_id": dados["estacao_id"], "acao": dados["acao"], "entregue": entregue}},
    )
    if entregue:
        avisar(request, f"Comando enviado para a sirene de {dados['estacao_id']} ({dados['acao']}).")
    else:
        avisar(request, "Não foi possível falar com a sirene agora (sem conexão com o broker). Tente de novo.", "erro")
    return redirecionar("/agente#sirenes")
