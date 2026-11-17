"""Testes das funções pequenas: segurança, formatação, gráfico SVG e seed."""

from __future__ import annotations

import time

from ajudas_web import situacao

from comum.estacoes import carregar_estacoes


def test_telefone_normaliza_e_mascara(app):
    from mvp.web import seguranca

    for texto in ("(11) 98765-4321", "11987654321", "+55 11 98765-4321"):
        assert seguranca.normalizar_telefone(texto) == "11987654321"
    for invalido in ("123", "1133334444", "(11) 8765-4321", "abc", "00987654321"):
        assert seguranca.normalizar_telefone(invalido) is None
    assert seguranca.mascarar_telefone("11987654321") == "(11) *****-4321"
    assert seguranca.mascarar_telefone(None) == ""


def test_telefone_cifra_e_decifra(app):
    from mvp.web import seguranca

    cifrado = seguranca.cifrar_telefone("11987654321")
    assert "11987654321" not in cifrado
    assert cifrado != seguranca.cifrar_telefone("11987654321")  # cada cifragem sai diferente
    assert seguranca.decifrar_telefone(cifrado) == "11987654321"
    assert seguranca.decifrar_telefone("texto-que-nao-e-cifra") is None


def test_senha_hash_e_conferencia(app):
    from mvp.web import seguranca

    senha_hash = seguranca.gerar_hash_senha("Senha1234forte")
    assert seguranca.conferir_senha("Senha1234forte", senha_hash)
    assert not seguranca.conferir_senha("senha1234forte", senha_hash)
    assert not seguranca.conferir_senha("Senha1234forte", None)  # usuário inexistente nunca confere
    assert not seguranca.conferir_senha("x" * 100, senha_hash)
    assert seguranca.problemas_da_senha("Senha1234forte") is None


def test_limite_de_login_bloqueia_e_expira(app):
    from mvp.web.seguranca import LimiteLogin

    limite = LimiteLogin(max_falhas=3, janela_s=0.05)
    for _ in range(3):
        assert not limite.bloqueado("a@exemplo.com|1.2.3.4")
        limite.registrar_falha("a@exemplo.com|1.2.3.4")
    assert limite.bloqueado("a@exemplo.com|1.2.3.4")
    assert not limite.bloqueado("a@exemplo.com|9.9.9.9")
    time.sleep(0.06)
    assert not limite.bloqueado("a@exemplo.com|1.2.3.4")  # o bloqueio é temporário


def test_datas_em_horario_de_brasilia(app):
    from mvp.web import apresentacao

    assert apresentacao.data_hora("2026-11-16T18:00:00Z") == "16/11/2026 15:00"
    assert apresentacao.data_hora("2026-01-01T01:30:00Z") == "31/12/2025 22:30"
    assert apresentacao.data_hora(None) == "—"
    assert apresentacao.ha_quanto("2000-01-01T00:00:00Z").endswith("dias")
    assert apresentacao.numero(12.44, 1) == "12,4"
    assert apresentacao.porcento(0.071) == "7%"


def test_grafico_svg_tem_cotas_linha_e_chuva(app):
    from mvp.web import grafico

    estacao = carregar_estacoes()["EST-ARI-01"]
    serie = situacao()["serie"]
    svg = str(grafico.grafico_nivel(serie, estacao))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    for trecho in (
        "g-cota-atencao",
        "g-cota-alerta",
        "g-cota-transbordo",
        "g-linha",
        "g-chuva",
        "agora: 142 cm",
        "<desc>",
    ):
        assert trecho in svg
    assert "<script" not in svg and "style=" not in svg  # compatível com a CSP
    assert grafico.grafico_nivel(serie[:1], estacao) is None
    assert grafico.tabela_da_serie(serie)[0] == {"hora": "15:00", "nivel_cm": 142.5, "chuva_mm": 7.7}


def test_seed_e_idempotente_e_nao_apaga_dado_do_pipeline(app, cliente, interno):
    from mvp.web import banco, seed

    cliente.post("/api/interno/situacao", json=[situacao()], headers=interno)
    con = banco.conectar(app.state.cfg.db)
    try:
        assert seed.criar_usuarios(con) == [seed.EMAIL_MORADOR, seed.EMAIL_AGENTE]
        assert seed.criar_usuarios(con) == []
        assert seed.criar_situacoes_exemplo(con) == 3  # a estação que já tinha dado real fica como está
        assert seed.criar_alerta_exemplo(con) is True
        assert seed.criar_alerta_exemplo(con) is False
        situacoes = banco.listar_situacoes(con)
        assert len(banco.listar_sms(con)) == 1
    finally:
        con.close()
    assert situacoes["EST-ARI-01"]["origem"] is None and situacoes["EST-IPI-01"]["origem"] == "exemplo"
    assert "dados de exemplo" in cliente.get("/").text
