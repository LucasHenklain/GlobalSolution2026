"""Conta do usuário: cadastro, entrar, sair e perfil (preferências, exportar dados e excluir conta — LGPD)."""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from comum.log import obter_logger
from mvp.web import banco, seguranca, validacao
from mvp.web.apoio import (
    Banco,
    Campo,
    UsuarioLogado,
    UsuarioOpcional,
    avisar,
    iniciar_sessao,
    redirecionar,
    renderizar,
    verificar_csrf,
)

rotas = APIRouter()
log = obter_logger("web.conta")

ERRO_LOGIN = "E-mail ou senha inválidos."  # sempre a mesma frase: não revela se o e-mail tem cadastro
ERRO_BLOQUEIO = "Muitas tentativas seguidas. Espere 15 minutos e tente de novo."


def _inicio_de(usuario: sqlite3.Row) -> str:
    return "/agente" if usuario["papel"] == "agente" else "/minha-area"


# ---------- cadastro ----------


@rotas.get("/cadastro")
def tela_cadastro(request: Request, usuario: UsuarioOpcional) -> Response:
    if usuario:
        return redirecionar(_inicio_de(usuario))
    return renderizar(request, "cadastro.html", valores={}, erros={})


@rotas.post("/cadastro", dependencies=[Depends(verificar_csrf)])
def cadastrar(
    request: Request,
    usuario: UsuarioOpcional,
    con: Banco,
    nome: Campo = "",
    email: Campo = "",
    senha: Campo = "",
    telefone: Campo = "",
    estacao_id: Campo = "",
    consentimento: Campo = "",
) -> Response:
    form = {"nome": nome, "email": email, "senha": senha, "telefone": telefone, "estacao_id": estacao_id}
    dados, erros = validacao.validar_cadastro({**form, "consentimento": consentimento})
    if not erros and banco.usuario_por_email(con, dados["email"]):
        erros["email"] = "Não foi possível usar este e-mail. Se você já tem conta, use a opção Entrar."
    if erros:
        valores = {**form, "senha": ""}  # a senha nunca volta para a tela
        return renderizar(request, "cadastro.html", status=422, valores=valores, erros=erros)
    cifrado = seguranca.cifrar_telefone(dados["telefone"]) if dados["telefone"] else None
    usuario_id = banco.criar_usuario(
        con, dados["nome"], dados["email"], seguranca.gerar_hash_senha(senha), cifrado, dados["estacao_id"]
    )
    request.app.state.metricas.contar("vigia_cadastros_total")
    log.info("conta criada", extra={"dados": {"usuario_id": usuario_id}})  # sem nome, e-mail ou telefone no log
    iniciar_sessao(request, banco.usuario_por_id(con, usuario_id))
    avisar(request, "Conta criada. Você vai receber os alertas da sua área.")
    return redirecionar("/minha-area")


# ---------- entrar e sair ----------


@rotas.get("/entrar")
def tela_entrar(request: Request, usuario: UsuarioOpcional) -> Response:
    if usuario:
        return redirecionar(_inicio_de(usuario))
    return renderizar(request, "entrar.html", email="", erro=None)


@rotas.post("/entrar", dependencies=[Depends(verificar_csrf)])
def entrar(request: Request, con: Banco, email: Campo = "", senha: Campo = "") -> Response:
    email = email.strip().lower()[:254]
    limite: seguranca.LimiteLogin = request.app.state.limite_login
    chave = f"{email}|{request.client.host if request.client else '-'}"
    metricas = request.app.state.metricas
    if limite.bloqueado(chave):
        metricas.contar("vigia_logins_falhos_total")
        log.warning("login bloqueado por excesso de tentativas")
        return renderizar(request, "entrar.html", status=429, email=email, erro=ERRO_BLOQUEIO)
    usuario = banco.usuario_por_email(con, email)
    if not seguranca.conferir_senha(senha, usuario["senha_hash"] if usuario else None):
        limite.registrar_falha(chave)
        metricas.contar("vigia_logins_falhos_total")
        log.warning("login recusado")
        return renderizar(request, "entrar.html", status=401, email=email, erro=ERRO_LOGIN)
    limite.limpar(chave)
    iniciar_sessao(request, usuario)
    metricas.contar("vigia_logins_ok_total")
    log.info("login ok", extra={"dados": {"usuario_id": usuario["id"], "papel": usuario["papel"]}})
    return redirecionar(_inicio_de(usuario))


@rotas.post("/sair", dependencies=[Depends(verificar_csrf)])
def sair(request: Request, usuario: UsuarioOpcional, con: Banco) -> Response:
    if usuario:
        banco.encerrar_sessoes(con, usuario["id"])  # o cookie antigo deixa de valer mesmo se alguém o copiou
    request.session.clear()
    avisar(request, "Você saiu da sua conta.")
    return redirecionar("/")


# ---------- perfil ----------


def _tela_perfil(request: Request, usuario: sqlite3.Row, status: int = 200, **extra) -> Response:
    telefone = seguranca.mascarar_telefone(seguranca.decifrar_telefone(usuario["telefone_cifrado"]))
    campos = ("nome", "estacao_id", "receber_sms", "fonte_grande", "alto_contraste")
    valores = {**{c: usuario[c] for c in campos}, "telefone": ""}
    contexto = {"valores": valores, "erros": {}, "erro_exclusao": None, **extra}
    return renderizar(request, "perfil.html", status=status, telefone_mascarado=telefone, **contexto)


@rotas.get("/perfil")
def tela_perfil(request: Request, usuario: UsuarioLogado) -> Response:
    return _tela_perfil(request, usuario)


@rotas.post("/perfil", dependencies=[Depends(verificar_csrf)])
def salvar_perfil(
    request: Request,
    usuario: UsuarioLogado,
    con: Banco,
    nome: Campo = "",
    telefone: Campo = "",
    remover_telefone: Campo = "",
    estacao_id: Campo = "",
    receber_sms: Campo = "",
    fonte_grande: Campo = "",
    alto_contraste: Campo = "",
) -> Response:
    form = {
        "nome": nome,
        "telefone": telefone,
        "remover_telefone": remover_telefone,
        "estacao_id": estacao_id,
        "receber_sms": receber_sms,
        "fonte_grande": fonte_grande,
        "alto_contraste": alto_contraste,
    }
    dados, erros = validacao.validar_perfil(form, estacao_obrigatoria=usuario["papel"] == "morador")
    if erros:
        return _tela_perfil(request, usuario, status=422, valores={**dados, "telefone": telefone}, erros=erros)
    # Telefone: em branco mantém o atual; preenchido troca; "remover" apaga.
    dados["telefone_cifrado"] = usuario["telefone_cifrado"]
    if dados["remover_telefone"]:
        dados["telefone_cifrado"] = None
    elif dados["telefone"]:
        dados["telefone_cifrado"] = seguranca.cifrar_telefone(dados["telefone"])
    banco.atualizar_perfil(con, usuario["id"], dados)
    avisar(request, "Seus dados foram salvos.")
    return redirecionar("/perfil")


@rotas.post("/perfil/exportar", dependencies=[Depends(verificar_csrf)])
def exportar_dados(usuario: UsuarioLogado, con: Banco) -> Response:
    """LGPD (acesso e portabilidade): tudo o que guardamos sobre a pessoa, num arquivo JSON."""
    campos_ocorrencia = (
        "id",
        "estacao_id",
        "tipo",
        "status",
        "descricao",
        "criada_em",
        "atualizada_em",
        "encerrada_em",
    )
    dados = {
        "conta": {
            "nome": usuario["nome"],
            "email": usuario["email"],
            "telefone": seguranca.decifrar_telefone(usuario["telefone_cifrado"]),
            "estacao_id": usuario["estacao_id"],
            "papel": usuario["papel"],
            "receber_sms": bool(usuario["receber_sms"]),
            "fonte_grande": bool(usuario["fonte_grande"]),
            "alto_contraste": bool(usuario["alto_contraste"]),
            "consentimento_em": usuario["consentimento_em"],
            "criado_em": usuario["criado_em"],
        },
        "ocorrencias": [{c: o[c] for c in campos_ocorrencia} for o in banco.ocorrencias_do_usuario(con, usuario["id"])],
        "sms_enviados": [dict(s) for s in banco.sms_do_usuario(con, usuario["id"])],
        "exportado_em": banco.agora_iso(),
    }
    corpo = json.dumps(dados, ensure_ascii=False, indent=2)
    cabecalhos = {"Content-Disposition": 'attachment; filename="meus-dados-vigia.json"'}
    return Response(corpo, media_type="application/json", headers=cabecalhos)


@rotas.post("/perfil/excluir", dependencies=[Depends(verificar_csrf)])
def excluir_conta(request: Request, usuario: UsuarioLogado, con: Banco, senha: Campo = "") -> Response:
    """LGPD (eliminação): exige a senha de novo, para ninguém apagar a conta num celular esquecido aberto."""
    limite: seguranca.LimiteLogin = request.app.state.limite_login
    chave = f"excluir|{usuario['id']}"
    if limite.bloqueado(chave):
        return _tela_perfil(request, usuario, status=429, erro_exclusao=ERRO_BLOQUEIO)
    if not seguranca.conferir_senha(senha, usuario["senha_hash"]):
        limite.registrar_falha(chave)
        return _tela_perfil(request, usuario, status=401, erro_exclusao="Senha incorreta. A conta não foi excluída.")
    banco.excluir_usuario(con, usuario["id"])
    log.info("conta excluída a pedido do titular", extra={"dados": {"usuario_id": usuario["id"]}})
    request.session.clear()
    avisar(request, "Sua conta e seus dados pessoais foram apagados.")
    return redirecionar("/")
