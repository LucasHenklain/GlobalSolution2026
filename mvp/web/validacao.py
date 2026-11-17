"""Validação dos formulários no servidor. Cada função devolve (dados limpos, erros por campo) com mensagens simples."""

from __future__ import annotations

import re

from comum.estacoes import carregar_estacoes
from mvp.web import seguranca
from mvp.web.apresentacao import STATUS_OCORRENCIA, TIPOS_OCORRENCIA

FORMATO_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MAX_DESCRICAO = 500
NIVEIS_SIRENE = ("amarelo", "laranja", "vermelho")


def _nome(texto: str, erros: dict) -> str:
    nome = " ".join(texto.split())  # tira espaços repetidos e quebras de linha
    if not 2 <= len(nome) <= 80:
        erros["nome"] = "Escreva seu nome (de 2 a 80 letras)."
    return nome


def _email(texto: str, erros: dict) -> str:
    email = texto.strip().lower()
    if len(email) > 254 or not FORMATO_EMAIL.fullmatch(email):
        erros["email"] = "Escreva um e-mail válido, como nome@exemplo.com."
    return email


def _telefone(texto: str, erros: dict) -> str | None:
    """Telefone é opcional; se veio preenchido, precisa ser um celular com DDD."""
    if not texto.strip():
        return None
    digitos = seguranca.normalizar_telefone(texto)
    if digitos is None:
        erros["telefone"] = "Escreva o celular com DDD, como (11) 91234-5678, ou deixe em branco."
    return digitos


def _estacao(estacao_id: str, erros: dict, obrigatoria: bool = True) -> str | None:
    if not estacao_id and not obrigatoria:
        return None
    if estacao_id not in carregar_estacoes():
        erros["estacao_id"] = "Escolha na lista o córrego mais perto da sua casa."
        return None
    return estacao_id


def validar_cadastro(form: dict) -> tuple[dict, dict]:
    erros: dict[str, str] = {}
    dados = {
        "nome": _nome(form["nome"], erros),
        "email": _email(form["email"], erros),
        "telefone": _telefone(form["telefone"], erros),
        "estacao_id": _estacao(form["estacao_id"], erros),
    }
    erro_senha = seguranca.problemas_da_senha(form["senha"])
    if erro_senha:
        erros["senha"] = erro_senha
    if form["consentimento"] != "sim":
        erros["consentimento"] = "Para criar a conta, você precisa concordar com o uso dos seus dados."
    return dados, erros


def validar_perfil(form: dict, estacao_obrigatoria: bool) -> tuple[dict, dict]:
    erros: dict[str, str] = {}
    dados = {
        "nome": _nome(form["nome"], erros),
        "telefone": _telefone(form["telefone"], erros),
        "estacao_id": _estacao(form["estacao_id"], erros, obrigatoria=estacao_obrigatoria),
        "remover_telefone": form["remover_telefone"] == "sim",
        "receber_sms": form["receber_sms"] == "sim",
        "fonte_grande": form["fonte_grande"] == "sim",
        "alto_contraste": form["alto_contraste"] == "sim",
    }
    return dados, erros


def validar_ocorrencia(form: dict) -> tuple[dict, dict]:
    erros: dict[str, str] = {}
    descricao = form["descricao"].strip()
    if form["tipo"] not in TIPOS_OCORRENCIA:
        erros["tipo"] = "Escolha o tipo de problema."
    if len(descricao) > MAX_DESCRICAO:
        erros["descricao"] = f"A descrição pode ter até {MAX_DESCRICAO} caracteres (a sua tem {len(descricao)})."
    elif form["tipo"] == "outro" and len(descricao) < 5:
        erros["descricao"] = "Conte em poucas palavras qual é o problema."
    dados = {"tipo": form["tipo"], "descricao": descricao, "estacao_id": _estacao(form["estacao_id"], erros)}
    return dados, erros


def status_valido(status: str) -> bool:
    return status in STATUS_OCORRENCIA


def validar_sirene(form: dict) -> tuple[dict, dict]:
    """Comando manual do agente, nos limites do contrato MQTT (seção 3.2)."""
    erros: dict[str, str] = {}
    if form["estacao_id"] not in carregar_estacoes():
        erros["estacao_id"] = "Estação desconhecida."
    if form["acao"] not in ("ligar", "desligar"):
        erros["acao"] = "Ação inválida."
    if form["nivel"] not in NIVEIS_SIRENE:
        erros["nivel"] = "Nível inválido."
    segundos = int(form["segundos"]) if form["segundos"].isdecimal() else 0
    if form["acao"] == "ligar" and not 5 <= segundos <= 120:
        erros["segundos"] = "A sirene pode tocar de 5 a 120 segundos."
    dados = {"estacao_id": form["estacao_id"], "acao": form["acao"], "nivel": form["nivel"], "segundos": segundos}
    return dados, erros
