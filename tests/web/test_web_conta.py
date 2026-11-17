"""Conta e segurança: cadastro, login, logout, senha, bloqueio de tentativas, CSRF, telefone cifrado e LGPD."""

from __future__ import annotations

import logging
import sqlite3

from ajudas_web import DIGITOS_TELEFONE, SENHA, alerta, cadastrar, entrar, enviar, sair, token_csrf


def _linha_usuario(app, email: str):
    con = sqlite3.connect(app.state.cfg.db)
    try:
        return con.execute(
            "SELECT nome, senha_hash, telefone_cifrado FROM usuarios WHERE email = ?", (email,)
        ).fetchone()
    finally:
        con.close()


def test_cadastro_login_e_logout(cliente):
    resposta = cadastrar(cliente)
    assert resposta.status_code == 200
    assert resposta.url.path == "/minha-area"  # cadastro já entra na conta
    assert "Córrego Aricanduva" in resposta.text

    assert sair(cliente).url.path == "/"
    assert cliente.get("/minha-area", follow_redirects=False).headers["location"] == "/entrar"

    resposta = entrar(cliente, "ana@exemplo.com")
    assert resposta.url.path == "/minha-area"


def test_senha_fraca_e_recusada(cliente, app):
    for senha in ("curta1", "somenteletras", "1234567890"):
        resposta = cadastrar(cliente, senha=senha)
        assert resposta.status_code == 422
        assert "A senha precisa" in resposta.text
    assert _linha_usuario(app, "ana@exemplo.com") is None


def test_cadastro_exige_consentimento_e_dados_validos(cliente):
    resposta = cadastrar(cliente, consentimento="", email="sem-arroba", telefone="123", estacao_id="EST-XXX-99")
    assert resposta.status_code == 422
    for trecho in ("precisa concordar", "e-mail válido", "celular com DDD", "Escolha na lista"):
        assert trecho in resposta.text


def test_senha_guardada_com_bcrypt(cliente, app):
    cadastrar(cliente)
    senha_hash = _linha_usuario(app, "ana@exemplo.com")[1]
    assert senha_hash.startswith("$2") and SENHA not in senha_hash


def test_login_errado_tem_mensagem_generica(cliente):
    cadastrar(cliente)
    sair(cliente)
    senha_errada = entrar(cliente, "ana@exemplo.com", "Errada12345")
    email_inexistente = entrar(cliente, "ninguem@exemplo.com", "Errada12345")
    assert senha_errada.status_code == email_inexistente.status_code == 401
    # A mesma frase nos dois casos: a tela não revela se o e-mail tem cadastro.
    assert "E-mail ou senha inválidos." in senha_errada.text
    assert "E-mail ou senha inválidos." in email_inexistente.text


def test_bloqueio_apos_cinco_falhas(cliente, outro_cliente):
    cadastrar(cliente)
    sair(cliente)
    for _ in range(5):
        assert entrar(cliente, "ana@exemplo.com", "Errada12345").status_code == 401
    bloqueada = entrar(cliente, "ana@exemplo.com")  # agora nem a senha certa entra
    assert bloqueada.status_code == 429
    assert "Muitas tentativas" in bloqueada.text
    assert cliente.get("/minha-area", follow_redirects=False).status_code == 303
    # O bloqueio é por e-mail + IP: outra conta não é afetada.
    cadastrar(outro_cliente, email="bia@exemplo.com")
    assert outro_cliente.get("/minha-area").status_code == 200


def test_injecao_sql_no_login_nao_autentica(cliente, app):
    cadastrar(cliente)
    sair(cliente)
    for email in ("' OR '1'='1' --", "ana@exemplo.com' --", "ana@exemplo.com"):
        resposta = entrar(cliente, email, "' OR '1'='1")
        assert resposta.status_code == 401
    assert cliente.get("/minha-area", follow_redirects=False).status_code == 303
    assert _linha_usuario(app, "ana@exemplo.com") is not None  # a tabela continua inteira


def test_post_sem_csrf_da_403(cliente):
    dados = {
        "nome": "Ana",
        "email": "ana@exemplo.com",
        "senha": SENHA,
        "estacao_id": "EST-ARI-01",
        "consentimento": "sim",
    }
    assert cliente.post("/cadastro", data=dados).status_code == 403
    assert cliente.post("/entrar", data={"email": "ana@exemplo.com", "senha": SENHA}).status_code == 403
    token_csrf(cliente, "/cadastro")  # agora a sessão tem um token, mas o formulário manda outro
    assert cliente.post("/cadastro", data={**dados, "csrf_token": "token-errado"}).status_code == 403

    cadastrar(cliente)
    assert cliente.post("/ocorrencias/nova", data={"tipo": "outro", "descricao": "teste de csrf"}).status_code == 403
    assert cliente.post("/perfil/excluir", data={"senha": SENHA}).status_code == 403
    assert cliente.post("/sair").status_code == 403


def test_sessao_regenerada_no_login_e_invalida_apos_sair(cliente, outro_cliente):
    cadastrar(cliente)
    token_antes = token_csrf(cliente, "/perfil")
    cookie_roubado = cliente.cookies.get("vigia_sessao")
    sair(cliente)
    # Quem copiou o cookie antes do logout não entra mais com ele.
    outro_cliente.cookies.set("vigia_sessao", cookie_roubado)
    assert outro_cliente.get("/perfil", follow_redirects=False).status_code == 303
    entrar(cliente, "ana@exemplo.com")
    assert token_csrf(cliente, "/perfil") != token_antes


def test_cookie_de_sessao_e_cabecalhos_de_seguranca(cliente):
    resposta = cliente.get("/entrar")
    cookie = resposta.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "script-src 'none'" in resposta.headers["content-security-policy"]
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["x-frame-options"] == "DENY"
    assert resposta.headers["referrer-policy"] == "same-origin"
    assert "<script" not in resposta.text


def test_telefone_cifrado_no_banco_e_mascarado_na_tela(cliente, app):
    cadastrar(cliente)
    cifrado = _linha_usuario(app, "ana@exemplo.com")[2]
    assert cifrado and DIGITOS_TELEFONE not in cifrado
    # Lendo o arquivo do SQLite byte a byte, o número não aparece em lugar nenhum.
    conteudo = b"".join(caminho.read_bytes() for caminho in app.state.cfg.db.parent.glob("vigia_teste.db*"))
    assert DIGITOS_TELEFONE.encode() not in conteudo
    assert b"98765-4321" not in conteudo

    perfil = cliente.get("/perfil").text
    assert "(11) *****-4321" in perfil
    assert DIGITOS_TELEFONE not in perfil and "98765" not in perfil


def test_perfil_salva_preferencias_e_aplica_classes(cliente):
    cadastrar(cliente)
    dados = {"nome": "Ana Maria", "estacao_id": "EST-IPI-01", "fonte_grande": "sim", "alto_contraste": "sim"}
    resposta = enviar(cliente, "/perfil", dados)
    assert "Seus dados foram salvos." in resposta.text
    assert '<body class="fonte-grande alto-contraste">' in resposta.text
    assert "Córrego Ipiranga" in cliente.get("/minha-area").text

    resposta = enviar(cliente, "/perfil", {"nome": "A", "estacao_id": "EST-IPI-01", "telefone": "abc"})
    assert resposta.status_code == 422
    assert "Escreva seu nome" in resposta.text and "celular com DDD" in resposta.text


def test_exportar_meus_dados(cliente):
    cadastrar(cliente)
    enviar(
        cliente,
        "/ocorrencias/nova",
        {"tipo": "bueiro_entupido", "descricao": "Bueiro da esquina", "estacao_id": "EST-ARI-01"},
    )
    resposta = enviar(cliente, "/perfil/exportar", {}, tela="/perfil")
    assert resposta.headers["content-type"].startswith("application/json")
    assert "attachment" in resposta.headers["content-disposition"]
    dados = resposta.json()
    assert dados["conta"]["email"] == "ana@exemplo.com"
    assert dados["conta"]["telefone"] == DIGITOS_TELEFONE  # o titular recebe o próprio dado completo
    assert dados["ocorrencias"][0]["descricao"] == "Bueiro da esquina"
    assert "senha_hash" not in resposta.text


def test_excluir_conta_remove_dados_pessoais(cliente, app, interno):
    cadastrar(cliente)
    enviar(
        cliente,
        "/ocorrencias/nova",
        {"tipo": "outro", "descricao": "Moro na casa 12, me chamo Ana", "estacao_id": "EST-ARI-01"},
    )
    cliente.post("/api/interno/alertas", json=alerta(), headers=interno)

    recusada = enviar(cliente, "/perfil/excluir", {"senha": "SenhaErrada99"}, tela="/perfil")
    assert recusada.status_code == 401 and "não foi excluída" in recusada.text
    assert _linha_usuario(app, "ana@exemplo.com") is not None

    resposta = enviar(cliente, "/perfil/excluir", {"senha": SENHA}, tela="/perfil")
    assert resposta.url.path == "/" and "foram apagados" in resposta.text
    assert _linha_usuario(app, "ana@exemplo.com") is None
    con = sqlite3.connect(app.state.cfg.db)
    try:
        assert con.execute("SELECT COUNT(*) FROM sms_saida").fetchone()[0] == 0
        ocorrencia = con.execute("SELECT usuario_id, descricao FROM ocorrencias").fetchone()
    finally:
        con.close()
    assert ocorrencia[0] is None and "Ana" not in ocorrencia[1]
    assert cliente.get("/minha-area", follow_redirects=False).status_code == 303
    assert entrar(cliente, "ana@exemplo.com").status_code == 401


def test_logs_nao_tem_dados_pessoais(cliente):
    registros = []

    class Coletor(logging.Handler):
        def emit(self, registro):
            registros.append(f"{registro.getMessage()} {getattr(registro, 'dados', '')}")

    coletor = Coletor()
    logger = logging.getLogger("web.conta")
    logger.addHandler(coletor)
    try:
        cadastrar(cliente)
        sair(cliente)
        entrar(cliente, "ana@exemplo.com", "Errada12345")
        entrar(cliente, "ana@exemplo.com")
    finally:
        logger.removeHandler(coletor)
    texto = " ".join(registros)
    assert "conta criada" in texto and "login recusado" in texto and "login ok" in texto
    for dado_pessoal in ("ana@exemplo.com", "Ana Teste", DIGITOS_TELEFONE, SENHA):
        assert dado_pessoal not in texto
