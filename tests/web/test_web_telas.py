"""Telas e controle de acesso: páginas públicas, papel (morador × agente), dono da ocorrência, XSS e sirene."""

from __future__ import annotations

from ajudas_web import alerta, cadastrar, criar_agente, entrar, enviar, situacao


def _relatar(cliente, descricao: str, tipo: str = "ponto_de_alagamento"):
    return enviar(cliente, "/ocorrencias/nova", {"tipo": tipo, "descricao": descricao, "estacao_id": "EST-ARI-01"})


def test_inicio_publico_e_leve(cliente, interno):
    cliente.post("/api/interno/situacao", json=[situacao()], headers=interno)
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert 'lang="pt-BR"' in resposta.text
    assert "Córrego Aricanduva" in resposta.text and "Atenção" in resposta.text
    assert "16/11/2026 15:00" in resposta.text  # 18:00 UTC exibido em horário de Brasília
    assert "Sem leitura" in resposta.text  # estações que ainda não mandaram dados
    assert len(resposta.content) < 15_000
    assert "set-cookie" not in resposta.headers  # página pública não cria sessão


def test_status_txt_tem_uma_linha_por_estacao(cliente, interno):
    cliente.post("/api/interno/situacao", json=[situacao()], headers=interno)
    resposta = cliente.get("/status.txt")
    assert resposta.headers["content-type"].startswith("text/plain")
    linhas = resposta.text.strip().splitlines()
    assert len(linhas) == 5  # cabeçalho + 4 estações
    assert "EST-ARI-01" in linhas[1] and "ATENCAO (amarelo)" in linhas[1]
    assert "SEM LEITURA" in linhas[2]


def test_estacoes_lista_e_detalhe_com_grafico(cliente, interno):
    cliente.post("/api/interno/situacao", json=[situacao()], headers=interno)
    assert "Córrego Pirajuçara" in cliente.get("/estacoes").text
    detalhe = cliente.get("/estacoes/EST-ARI-01")
    assert detalhe.status_code == 200
    assert '<svg class="grafico"' in detalhe.text and "transbordo" in detalhe.text
    assert cliente.get("/estacoes/EST-ZZZ-99").status_code == 404


def test_faixa_de_demonstracao_so_no_replay(cliente, interno):
    cliente.post("/api/interno/situacao", json=[situacao()], headers=interno)
    assert "reprodução de um temporal real" not in cliente.get("/").text
    cliente.post("/api/interno/situacao", json=[situacao(origem="replay")], headers=interno)
    assert "Demonstração: reprodução de um temporal real (chuva medida pelo INMET)" in cliente.get("/").text


def test_telas_do_morador_exigem_login(cliente):
    for caminho in ("/minha-area", "/alertas", "/ocorrencias", "/ocorrencias/nova", "/perfil", "/agente"):
        resposta = cliente.get(caminho, follow_redirects=False)
        assert resposta.status_code == 303 and resposta.headers["location"] == "/entrar"


def test_minha_area_mostra_risco_motivos_e_orientacoes(cliente, interno):
    cadastrar(cliente)
    assert "Ainda não recebemos dados" in cliente.get("/minha-area").text
    cliente.post(
        "/api/interno/situacao", json=[situacao(nivel_risco="laranja", prob_transbordo_60min=0.71)], headers=interno
    )
    cliente.post("/api/interno/alertas", json=alerta(), headers=interno)
    pagina = cliente.get("/minha-area").text
    assert "Risco alto" in pagina and "71%" in pagina
    assert "choveu 34 mm na última hora" in pagina  # motivo do último alerta
    assert "Guarde documentos e remédios" in pagina  # orientação do nível laranja
    assert '<svg class="grafico"' in pagina and "Relatar ocorrência" in pagina


def test_alertas_lista_da_area_e_detalhe(cliente, interno):
    cadastrar(cliente, estacao_id="EST-ARI-01")
    cliente.post("/api/interno/alertas", json=alerta(), headers=interno)
    outro = alerta("ALT-20261116-0008", estacao_id="EST-IPI-01", titulo="Perigo no Córrego Ipiranga")
    cliente.post("/api/interno/alertas", json=outro, headers=interno)
    lista = cliente.get("/alertas").text
    assert "Risco alto de enchente no Córrego Aricanduva" in lista
    assert "Perigo no Córrego Ipiranga" not in lista  # morador vê só a própria área
    detalhe = cliente.get("/alertas/ALT-20261116-0007").text
    for trecho in (
        "o nível subiu 40 cm em 30 minutos",
        "Guarde documentos",
        "VigIA RISCO ALTO",
        "inteligência artificial",
    ):
        assert trecho in detalhe
    assert cliente.get("/alertas/ALT-NAO-EXISTE").status_code == 404


def test_morador_nao_acessa_painel_do_agente(cliente, sirene_falsa):
    cadastrar(cliente)
    assert cliente.get("/agente").status_code == 403
    assert enviar(cliente, "/agente/sirene", {"estacao_id": "EST-ARI-01"}, tela="/perfil").status_code == 403
    assert enviar(cliente, "/agente/ocorrencias/1/status", {"status": "resolvida"}, tela="/perfil").status_code == 403
    assert sirene_falsa == []


def test_morador_nao_ve_ocorrencia_de_outro(cliente, outro_cliente):
    cadastrar(cliente, email="ana@exemplo.com")
    cadastrar(outro_cliente, email="bia@exemplo.com")
    _relatar(cliente, "Relato secreto da Ana")
    _relatar(outro_cliente, "Relato da Bia")
    assert "Relato secreto da Ana" in cliente.get("/ocorrencias").text
    pagina_da_bia = outro_cliente.get("/ocorrencias").text
    assert "Relato da Bia" in pagina_da_bia and "Relato secreto da Ana" not in pagina_da_bia


def test_ocorrencia_valida_entrada(cliente):
    cadastrar(cliente)
    resposta = enviar(cliente, "/ocorrencias/nova", {"tipo": "invalido", "descricao": "x" * 501, "estacao_id": "nada"})
    assert resposta.status_code == 422
    for trecho in ("Escolha o tipo de problema", "até 500 caracteres", "Escolha na lista"):
        assert trecho in resposta.text
    assert "Você ainda não relatou" in cliente.get("/ocorrencias").text


def test_xss_na_descricao_aparece_escapado(cliente, outro_cliente, app):
    ataque = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    cadastrar(cliente)
    _relatar(cliente, ataque)
    criar_agente(app)
    entrar(outro_cliente, "agente@exemplo.com")
    for pagina in (cliente.get("/ocorrencias").text, outro_cliente.get("/agente").text):
        assert "<script>alert" not in pagina and "<img src=x" not in pagina
        assert "&lt;script&gt;alert(&#34;xss&#34;)&lt;/script&gt;" in pagina


def test_agente_ve_fila_muda_status_e_ve_todos_os_alertas(cliente, outro_cliente, app, interno):
    cadastrar(cliente)
    _relatar(cliente, "Água subindo na rua de baixo")
    criar_agente(app)
    entrar(outro_cliente, "agente@exemplo.com")
    cliente.post("/api/interno/alertas", json=alerta(), headers=interno)
    cliente.post(
        "/api/interno/alertas",
        json=alerta("ALT-20261116-0008", estacao_id="EST-IPI-01", titulo="Outro"),
        headers=interno,
    )

    painel = outro_cliente.get("/agente").text
    assert "Água subindo na rua de baixo" in painel
    assert "(11) *****-4321" in painel and "98765" not in painel  # caixa de SMS só com telefone mascarado
    assert "ana@exemplo.com" not in painel and "Ana Teste" not in painel
    assert outro_cliente.get("/alertas").text.count("/alertas/ALT-") == 2

    resposta = enviar(outro_cliente, "/agente/ocorrencias/1/status", {"status": "resolvida"}, tela="/agente")
    assert "Ocorrência nº 1: resolvida." in resposta.text
    assert "Resolvida" in cliente.get("/ocorrencias").text
    assert (
        enviar(outro_cliente, "/agente/ocorrencias/999/status", {"status": "resolvida"}, tela="/agente").status_code
        == 404
    )


def test_agente_aciona_sirene_com_comando_do_contrato(outro_cliente, app, sirene_falsa):
    criar_agente(app)
    entrar(outro_cliente, "agente@exemplo.com")
    dados = {"estacao_id": "EST-ARI-01", "acao": "ligar", "nivel": "vermelho", "segundos": "30"}
    resposta = enviar(outro_cliente, "/agente/sirene", dados, tela="/agente")
    assert "Comando enviado para a sirene" in resposta.text
    assert sirene_falsa == [("EST-ARI-01", {"acao": "ligar", "nivel": "vermelho", "segundos": 30, "alerta_id": None})]

    invalido = enviar(
        outro_cliente, "/agente/sirene", {**dados, "estacao_id": "EST-ZZZ-99", "segundos": "9999"}, tela="/agente"
    )
    assert "Estação desconhecida" in invalido.text
    assert len(sirene_falsa) == 1


def test_broker_fora_do_ar_nao_derruba_o_painel(outro_cliente, app, monkeypatch):
    from mvp.web import mqtt_saida

    monkeypatch.setattr(mqtt_saida, "publicar_sirene", lambda cfg, estacao_id, comando: False)
    criar_agente(app)
    entrar(outro_cliente, "agente@exemplo.com")
    dados = {"estacao_id": "EST-ARI-01", "acao": "ligar", "nivel": "laranja", "segundos": "30"}
    resposta = enviar(outro_cliente, "/agente/sirene", dados, tela="/agente")
    assert resposta.status_code == 200
    assert "Não foi possível falar com a sirene" in resposta.text and "não entregue" in resposta.text


def test_pagina_inexistente_da_404_amigavel(cliente):
    resposta = cliente.get("/nao-existe")
    assert resposta.status_code == 404 and "Página não encontrada" in resposta.text


def test_emergencia_e_publica_e_tem_os_telefones_para_ligar(cliente):
    resposta = cliente.get("/emergencia")
    assert resposta.status_code == 200
    for numero in ("199", "193", "192", "190"):
        assert f'href="tel:{numero}"' in resposta.text
    assert "set-cookie" not in resposta.headers  # pública: não cria sessão
    assert 'href="/emergencia"' in cliente.get("/").text  # está no menu e no rodapé
