"""Recebimento de um alerta: grava e, se o risco for alto, enfileira o SMS (simulado) dos moradores da área."""

from __future__ import annotations

import sqlite3

from mvp.web import banco, seguranca

NIVEIS_COM_SMS = ("laranja", "vermelho")  # amarelo e verde aparecem só no app, para não cansar o morador


def _destinatarios(con: sqlite3.Connection, estacao_id: str) -> list[tuple[int, str]]:
    """(usuario_id, telefone mascarado) de quem mora na área, aceitou SMS e informou telefone."""
    destinatarios = []
    for morador in banco.moradores_para_sms(con, estacao_id):
        telefone = seguranca.decifrar_telefone(morador["telefone_cifrado"])
        if telefone:
            # A caixa de saída guarda só a máscara: um envio real leria o número do cadastro na hora de enviar.
            destinatarios.append((morador["id"], seguranca.mascarar_telefone(telefone)))
    return destinatarios


def receber_alerta(con: sqlite3.Connection, alerta: dict) -> tuple[bool, int]:
    """Devolve (novo, sms_enfileirados). Alerta repetido não grava nem gera SMS de novo (idempotente)."""
    destinatarios = []
    if alerta["nivel_risco"] in NIVEIS_COM_SMS:
        destinatarios = _destinatarios(con, alerta["estacao_id"])
    novo = banco.salvar_alerta(con, alerta, destinatarios)
    return novo, len(destinatarios) if novo else 0
