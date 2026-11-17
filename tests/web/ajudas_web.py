"""Funções de apoio dos testes do app web: preencher formulários como um navegador faria (com o token CSRF)."""

from __future__ import annotations

import re

SENHA = "Senha1234forte"
TELEFONE = "(11) 98765-4321"
DIGITOS_TELEFONE = "11987654321"


def token_csrf(cliente, caminho: str) -> str:
    """Abre a tela e lê o token CSRF escondido no formulário."""
    html = cliente.get(caminho).text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def enviar(cliente, caminho: str, dados: dict, tela: str | None = None, seguir: bool = True):
    """POST de formulário com o token CSRF da tela (por padrão, a própria tela do formulário)."""
    corpo = {**dados, "csrf_token": token_csrf(cliente, tela or caminho)}
    return cliente.post(caminho, data=corpo, follow_redirects=seguir)


def cadastrar(cliente, email: str = "ana@exemplo.com", estacao_id: str = "EST-ARI-01", **outros):
    dados = {
        "nome": "Ana Teste",
        "email": email,
        "senha": SENHA,
        "telefone": TELEFONE,
        "estacao_id": estacao_id,
        "consentimento": "sim",
        **outros,
    }
    return enviar(cliente, "/cadastro", dados)


def entrar(cliente, email: str, senha: str = SENHA):
    return enviar(cliente, "/entrar", {"email": email, "senha": senha})


def sair(cliente):
    return enviar(cliente, "/sair", {}, tela="/perfil")


def criar_agente(app, email: str = "agente@exemplo.com") -> None:
    """Agente não se cadastra pela tela: é criado direto no banco (como faz o seed)."""
    from mvp.web import banco, seguranca

    con = banco.conectar(app.state.cfg.db)
    try:
        banco.criar_usuario(con, "Agente Teste", email, seguranca.gerar_hash_senha(SENHA), None, None, "agente")
    finally:
        con.close()


def situacao(estacao_id: str = "EST-ARI-01", **outros) -> dict:
    """Situação válida conforme o contrato (seção 5)."""
    return {
        "estacao_id": estacao_id,
        "atualizado_em": "2026-11-16T18:00:00Z",
        "nivel_cm": 142.5,
        "nivel_pct_cota": 50.9,
        "chuva_1h": 12.4,
        "chuva_24h": 30.2,
        "delta_nivel_30min": 18.0,
        "prob_transbordo_60min": 0.07,
        "nivel_risco": "amarelo",
        "estado_regra": "normal",
        "bateria_pct": 87,
        "serie": [
            {"t": "2026-11-16T17:40:00Z", "nivel_cm": 120.0, "chuva_mm": 2.0},
            {"t": "2026-11-16T17:50:00Z", "nivel_cm": 131.0, "chuva_mm": 4.5},
            {"t": "2026-11-16T18:00:00Z", "nivel_cm": 142.5, "chuva_mm": 1.2},
        ],
        **outros,
    }


def alerta(alerta_id: str = "ALT-20261116-0007", **outros) -> dict:
    """Alerta válido conforme o contrato (seção 5)."""
    return {
        "alerta_id": alerta_id,
        "estacao_id": "EST-ARI-01",
        "emitido_em": "2026-11-16T18:00:00Z",
        "nivel_risco": "laranja",
        "prob": 0.71,
        "nivel_cm": 201.0,
        "chuva_1h": 34.2,
        "titulo": "Risco alto de enchente no Córrego Aricanduva",
        "mensagem": "O córrego pode transbordar em até 1 hora. Prepare-se.",
        "mensagem_sms": "VigIA RISCO ALTO: Corrego Aricanduva pode transbordar em ate 1h.",
        "motivo": ["choveu 34 mm na última hora", "o nível subiu 40 cm em 30 minutos"],
        "orientacoes": ["Guarde documentos e remédios em lugar alto"],
        "origem_decisao": "ia",
        **outros,
    }
