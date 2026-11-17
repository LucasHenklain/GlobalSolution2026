"""API interna (contrato, seção 5), /health e /metrics."""

from __future__ import annotations

import sqlite3

from ajudas_web import alerta, cadastrar, enviar, situacao


def _contar(app, tabela_sms_ou_alertas: str) -> int:
    consultas = {"sms": "SELECT COUNT(*) FROM sms_saida", "alertas": "SELECT COUNT(*) FROM alertas"}
    con = sqlite3.connect(app.state.cfg.db)
    try:
        return con.execute(consultas[tabela_sms_ou_alertas]).fetchone()[0]
    finally:
        con.close()


def test_health_ok(cliente, interno):
    assert cliente.get("/health").json() == {"status": "ok", "banco": "ok", "ultima_situacao_em": None}
    cliente.post("/api/interno/situacao", json=[situacao()], headers=interno)
    assert cliente.get("/health").json()["ultima_situacao_em"] == "2026-11-16T18:00:00Z"


def test_api_interna_sem_token_da_401(cliente):
    assert cliente.post("/api/interno/situacao", json=[situacao()]).status_code == 401
    assert cliente.post("/api/interno/alertas", json=alerta()).status_code == 401
    assert cliente.get("/api/interno/ocorrencias").status_code == 401
    errado = {"X-Token-Interno": "token-errado"}
    assert cliente.post("/api/interno/situacao", json=[situacao()], headers=errado).status_code == 401
    assert (
        cliente.post("/api/interno/situacao", json={"lixo": 1}, headers=errado).status_code == 401
    )  # token antes do corpo
    assert cliente.get("/health").json()["ultima_situacao_em"] is None


def test_situacao_com_token_substitui_a_atual(cliente, interno):
    lote = [situacao(), situacao("EST-IPI-01", nivel_risco="vermelho")]
    assert cliente.post("/api/interno/situacao", json=lote, headers=interno).json() == {"atualizadas": 2}
    nova = situacao(nivel_risco="verde", nivel_pct_cota=20.0, atualizado_em="2026-11-16T15:10:00-03:00")
    assert cliente.post("/api/interno/situacao", json=[nova], headers=interno).json() == {"atualizadas": 1}
    pagina = cliente.get("/status.txt").text
    assert "EST-ARI-01 Corrego Aricanduva: NORMAL (verde) | nivel 20% da cota" in pagina
    assert "EST-IPI-01 Corrego Ipiranga: PERIGO (vermelho)" in pagina
    assert cliente.get("/health").json()["ultima_situacao_em"] == "2026-11-16T18:10:00Z"  # guardado em UTC


def test_alerta_e_idempotente_e_gera_sms_uma_vez(cliente, outro_cliente, app, interno):
    cadastrar(cliente, email="ana@exemplo.com")  # mora na área, tem telefone e aceita SMS
    cadastrar(outro_cliente, email="bia@exemplo.com", telefone="")  # sem telefone: não recebe
    primeira = cliente.post("/api/interno/alertas", json=alerta(), headers=interno)
    assert primeira.json() == {"alerta_id": "ALT-20261116-0007", "novo": True, "sms_enfileirados": 1}
    repetida = cliente.post("/api/interno/alertas", json=alerta(), headers=interno)
    assert repetida.json() == {"alerta_id": "ALT-20261116-0007", "novo": False, "sms_enfileirados": 0}
    assert _contar(app, "alertas") == 1 and _contar(app, "sms") == 1


def test_sms_so_para_laranja_e_vermelho_e_para_quem_aceita(cliente, outro_cliente, app, interno):
    cadastrar(cliente)
    amarelo = cliente.post("/api/interno/alertas", json=alerta("ALT-1", nivel_risco="amarelo"), headers=interno)
    assert amarelo.json()["sms_enfileirados"] == 0
    outra_area = cliente.post("/api/interno/alertas", json=alerta("ALT-2", estacao_id="EST-IPI-01"), headers=interno)
    assert outra_area.json()["sms_enfileirados"] == 0
    enviar(cliente, "/perfil", {"nome": "Ana Teste", "estacao_id": "EST-ARI-01"})  # desmarca "receber SMS"
    vermelho = cliente.post("/api/interno/alertas", json=alerta("ALT-3", nivel_risco="vermelho"), headers=interno)
    assert vermelho.json() == {"alerta_id": "ALT-3", "novo": True, "sms_enfileirados": 0}
    assert _contar(app, "sms") == 0


def test_payload_invalido_da_422(cliente, interno, app):
    invalidos = [
        [situacao(nivel_risco="roxo")],  # enum
        [situacao(nivel_cm=-5)],  # faixa
        [situacao(prob_transbordo_60min=1.5)],  # faixa
        [situacao(estacao_id="ARI")],  # formato do id
        [situacao(estacao_id="EST-ZZZ-99")],  # fora do catálogo
        [situacao(atualizado_em="ontem")],  # data
        [situacao(origem="satelite")],  # enum de origem
        [situacao(serie=[{"t": "2026-11-16T18:00:00Z", "nivel_cm": 1, "chuva_mm": 0}] * 37)],  # série longa demais
        {"estacao_id": "EST-ARI-01"},  # não é lista
    ]
    for corpo in invalidos:
        assert cliente.post("/api/interno/situacao", json=corpo, headers=interno).status_code == 422, corpo
    alertas_invalidos = [
        alerta(nivel_risco="azul"),
        alerta(mensagem_sms="x" * 161),
        alerta(origem_decisao="palpite"),
        alerta(alerta_id="id com espaço/../"),
        alerta(titulo=""),
        alerta(estacao_id="EST-ZZZ-99"),
        {k: v for k, v in alerta().items() if k != "mensagem"},
    ]
    for corpo in alertas_invalidos:
        assert cliente.post("/api/interno/alertas", json=corpo, headers=interno).status_code == 422, corpo
    assert cliente.get("/api/interno/ocorrencias?desde=amanha", headers=interno).status_code == 422
    assert _contar(app, "alertas") == 0 and cliente.get("/health").json()["ultima_situacao_em"] is None


def test_ocorrencias_para_o_pipeline_sem_dados_pessoais(cliente, interno):
    cadastrar(cliente)
    enviar(
        cliente,
        "/ocorrencias/nova",
        {"tipo": "bueiro_entupido", "descricao": "Bueiro cheio de lixo", "estacao_id": "EST-ARI-01"},
    )
    resposta = cliente.get("/api/interno/ocorrencias", params={"desde": "2000-01-01T00:00:00Z"}, headers=interno)
    ocorrencias = resposta.json()["ocorrencias"]
    assert len(ocorrencias) == 1
    campos = {
        "ocorrencia_id",
        "estacao_id",
        "tipo",
        "status",
        "descricao",
        "criada_em",
        "atualizada_em",
        "encerrada_em",
    }
    assert set(ocorrencias[0]) == campos  # exatamente o contrato: nada de usuario_id, nome, e-mail ou telefone
    assert ocorrencias[0]["status"] == "aberta" and ocorrencias[0]["encerrada_em"] is None
    for dado_pessoal in ("ana@exemplo.com", "Ana Teste", "98765"):
        assert dado_pessoal not in resposta.text
    futuro = cliente.get("/api/interno/ocorrencias", params={"desde": "2999-01-01T00:00:00Z"}, headers=interno)
    assert futuro.json() == {"ocorrencias": []}


def test_metrics_conta_eventos(cliente, interno):
    cadastrar(cliente)
    enviar(cliente, "/ocorrencias/nova", {"tipo": "bueiro_entupido", "descricao": "", "estacao_id": "EST-ARI-01"})
    cliente.post("/api/interno/alertas", json=alerta(), headers=interno)
    cliente.post("/api/interno/alertas", json=alerta(), headers=interno)  # repetido não conta
    resposta = cliente.get("/metrics")
    assert resposta.headers["content-type"].startswith("text/plain")
    linhas = resposta.text.splitlines()
    assert "# TYPE vigia_requisicoes_total counter" in linhas
    for esperado in (
        "vigia_alertas_recebidos_total 1",
        "vigia_sms_enfileirados_total 1",
        "vigia_ocorrencias_criadas_total 1",
        "vigia_cadastros_total 1",
        "vigia_logins_falhos_total 0",
    ):
        assert esperado in linhas


def test_corpo_gigante_e_recusado(cliente, interno):
    resposta = cliente.post("/api/interno/alertas", content=b"x" * 300_000, headers=interno)
    assert resposta.status_code == 413


def test_token_interno_vazio_na_configuracao_nao_abre_a_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from mvp.web.app import criar_app

    monkeypatch.setenv("VIGIA_DB", str(tmp_path / "vigia_teste.db"))
    monkeypatch.setenv("VIGIA_AMBIENTE", "teste")
    monkeypatch.setenv("VIGIA_SECRET_KEY", "chave-de-sessao-so-para-os-testes-0123456789")
    monkeypatch.setenv("VIGIA_TOKEN_INTERNO", "")
    cliente = TestClient(criar_app())
    assert cliente.get("/api/interno/ocorrencias").status_code == 401
    assert cliente.get("/api/interno/ocorrencias", headers={"X-Token-Interno": ""}).status_code == 401
