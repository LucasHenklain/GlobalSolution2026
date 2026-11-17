"""Emulador das estações: cenários, replay, regra local, sirene e guarda-e-reenvia. Dublê no lugar do cliente MQTT."""

from __future__ import annotations

import json
import random
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from comum.config import RAIZ
from comum.estacoes import carregar_estacoes
from dados.ingestao.gateway_mqtt import validar_leitura
from mvp.iot import emulador
from mvp.iot.emulador import Conexao, EstacaoVirtual, agrupar_por_janela, ler_evento, regra_local, simular

ESTACOES = carregar_estacoes()
ARI = ESTACOES["EST-ARI-01"]
AGORA = datetime(2026, 11, 16, 18, 0, 0, tzinfo=UTC)
EXEMPLO = RAIZ / "dados" / "referencia" / "eventos_demo" / "exemplo_curto.csv"


class ClienteFalso:
    """Dublê do paho: guarda o que seria publicado e deixa o teste 'derrubar' o broker."""

    def __init__(self, conectado: bool = True) -> None:
        self.conectado = conectado
        self.publicadas: list[tuple[str, str]] = []
        self.assinados: list[str] = []
        self.testamento = None

    def will_set(self, topico, payload, qos=0, retain=False):
        self.testamento = (topico, payload, retain)

    def reconnect_delay_set(self, **_):
        pass

    def is_connected(self) -> bool:
        return self.conectado

    def publish(self, topico, payload, qos=0, retain=False):
        self.publicadas.append((topico, payload))
        return SimpleNamespace(rc=0, wait_for_publish=lambda timeout=None: None)

    def subscribe(self, topico, qos=0):
        self.assinados.append(topico)

    def leituras(self) -> list[dict]:
        return [json.loads(p) for t, p in self.publicadas if t.endswith("/leitura")]

    def estados(self) -> list[dict]:
        return [json.loads(p) for t, p in self.publicadas if t.endswith("/sirene/estado")]


def nova_conexao(estacao_id: str = "EST-ARI-01", cenario: str = "calmo", **opcoes) -> Conexao:
    return Conexao(EstacaoVirtual(ESTACOES[estacao_id], cenario), cliente=ClienteFalso(), **opcoes)


# ---------------------------------------------------------------- cenários (funções puras)


@pytest.mark.parametrize("est", ESTACOES.values(), ids=lambda e: e.estacao_id)
def test_temporal_cruza_o_alerta_com_atraso_e_depois_recua(est):
    niveis = [nivel for _, nivel in simular(est, "temporal", emulador.CICLO_PASSOS)]
    passo_alerta = next(i for i, nivel in enumerate(niveis) if nivel >= est.cota_alerta_cm)
    assert passo_alerta > emulador.INICIO_CHUVA + 3  # o nível responde à chuva com atraso, não no mesmo passo
    assert max(niveis) >= est.cota_transbordo_cm
    assert max(niveis) <= est.altura_sensor_cm  # nunca sai da faixa que o gateway aceita
    assert niveis[-1] < est.cota_atencao_cm  # recessão: no fim do ciclo o córrego voltou ao normal


@pytest.mark.parametrize("est", ESTACOES.values(), ids=lambda e: e.estacao_id)
def test_chuva_chega_a_atencao_sem_alerta_e_calmo_fica_normal(est):
    pico_chuva = max(nivel for _, nivel in simular(est, "chuva", emulador.CICLO_PASSOS))
    pico_calmo = max(nivel for _, nivel in simular(est, "calmo", emulador.CICLO_PASSOS))
    assert est.cota_atencao_cm <= pico_chuva < est.cota_alerta_cm
    assert pico_calmo < est.cota_atencao_cm


def test_chuva_so_no_trecho_de_chuva_e_em_multiplos_da_basculada():
    rng = random.Random(1)  # noqa: S311 - simulação, não é criptografia
    chuvas = [emulador.chuva_do_passo("temporal", passo, rng) for passo in range(emulador.CICLO_PASSOS * 2)]
    assert all(c == 0 for c in chuvas[: emulador.INICIO_CHUVA])
    assert all(c == 0 for c in chuvas[emulador.FIM_CHUVA : emulador.CICLO_PASSOS])
    assert all(c > 0 and c % emulador.BASCULADA_MM == 0 for c in chuvas[emulador.INICIO_CHUVA : emulador.FIM_CHUVA])
    assert chuvas[emulador.CICLO_PASSOS + emulador.INICIO_CHUVA] > 0  # o cenário se repete


def test_mesma_semente_gera_a_mesma_serie():
    assert simular(ARI, "temporal", 60, semente=7) == simular(ARI, "temporal", 60, semente=7)
    assert simular(ARI, "temporal", 60, semente=7) != simular(ARI, "temporal", 60, semente=8)


def test_leitura_do_emulador_passa_no_contrato_do_gateway():
    estacao = EstacaoVirtual(ARI, "temporal")
    for passo in range(emulador.CICLO_PASSOS):
        leitura = estacao.medir(passo, AGORA)
        validada, motivo = validar_leitura(leitura, "EST-ARI-01", AGORA)
        assert motivo is None, motivo
        assert validada == leitura  # nenhuma chave descartada, nenhum valor alterado
    assert leitura["seq"] == emulador.CICLO_PASSOS and leitura["origem"] == "emulador"


# ---------------------------------------------------------------- regra local e sirene


def test_regra_local_muda_exatamente_nas_cotas():
    assert regra_local(ARI, 149.5) == ("verde", False)
    assert regra_local(ARI, 150) == ("amarelo", False)
    assert regra_local(ARI, 219.5) == ("amarelo", False)
    assert regra_local(ARI, 220) == ("vermelho", True)
    assert regra_local(ARI, 280) == ("vermelho", True)


def test_regra_local_liga_e_desliga_a_sirene_publicando_so_na_mudanca():
    estacao = EstacaoVirtual(ARI)
    assert estacao.atualizar_atuadores(100, AGORA) == []
    assert estacao.atualizar_atuadores(230, AGORA) == [
        {"sirene": "ligada", "motivo": "regra_local", "em": "2026-11-16T18:00:00Z"}
    ]
    assert estacao.atualizar_atuadores(240, AGORA) == []  # continua ligada: nada novo a dizer
    assert estacao.led == "vermelho"
    (estado,) = estacao.atualizar_atuadores(160, AGORA)
    assert (estado["sirene"], estado["motivo"], estacao.led) == ("desligada", "regra_local", "amarelo")


def test_comando_liga_a_sirene_e_o_prazo_desliga():
    estacao = EstacaoVirtual(ARI)
    comando = json.dumps({"acao": "ligar", "nivel": "vermelho", "segundos": 30, "alerta_id": "ALT-20261116-0007"})
    assert estacao.receber_comando(comando, AGORA) == {
        "sirene": "ligada",
        "motivo": "comando",
        "em": "2026-11-16T18:00:00Z",
    }
    assert estacao.atualizar_atuadores(100, AGORA + timedelta(seconds=29)) == []
    (estado,) = estacao.atualizar_atuadores(100, AGORA + timedelta(seconds=30))
    assert (estado["sirene"], estado["motivo"]) == ("desligada", "comando")


def test_desligar_nao_cala_a_sirene_enquanto_a_regra_local_mandar():
    estacao = EstacaoVirtual(ARI)
    estacao.atualizar_atuadores(250, AGORA)
    resposta = estacao.receber_comando(b'{"acao": "desligar"}', AGORA)
    assert resposta == {"sirene": "ligada", "motivo": "regra_local", "em": "2026-11-16T18:00:00Z"}


@pytest.mark.parametrize("payload", [b"nao e json", b"[1, 2]", b'{"acao": "explodir"}', b"\xff\xfe"])
def test_comando_invalido_e_ignorado(payload):
    estacao = EstacaoVirtual(ARI)
    assert estacao.receber_comando(payload, AGORA) is None
    assert not estacao.tocando


# ---------------------------------------------------------------- replay


def test_ler_evento_ordena_por_medido_em_e_aceita_formato_do_pandas(tmp_path):
    arquivo = tmp_path / "evento.csv"
    arquivo.write_text(
        "estacao_id,medido_em,nivel_cm,chuva_mm\n"
        "EST-PIR-01,2026-01-15T18:10:00Z,31.0,0.25\n"
        "EST-ARI-01,2026-01-15 18:10:00+00:00,36.0,0.5\n"
        "EST-ARI-01,2026-01-15T18:00:00Z,35.0,0\n",
        encoding="utf-8",
    )
    linhas = ler_evento(arquivo)
    assert [(linha["medido_em"], linha["estacao_id"]) for linha in linhas] == [
        ("2026-01-15T18:00:00Z", "EST-ARI-01"),
        ("2026-01-15T18:10:00Z", "EST-ARI-01"),
        ("2026-01-15T18:10:00Z", "EST-PIR-01"),
    ]
    assert [len(janela) for janela in agrupar_por_janela(linhas)] == [1, 2]
    assert len(ler_evento(arquivo, {"EST-PIR-01"})) == 1


def test_replay_respeita_a_ordem_e_o_medido_em_do_arquivo():
    linhas = ler_evento(EXEMPLO)
    conexoes = [nova_conexao("EST-ARI-01"), nova_conexao("EST-PIR-01")]
    pausas = []
    total = emulador.rodar_replay(conexoes, agrupar_por_janela(linhas), velocidade=4, dormir=pausas.append)

    assert total == len(linhas) == 60
    assert pausas == [0.25] * 30  # uma pausa por janela: as duas estações da janela saem juntas
    for conexao in conexoes:
        estacao_id = conexao.estacao.est.estacao_id
        publicadas = conexao.cliente.leituras()
        esperadas = [linha for linha in linhas if linha["estacao_id"] == estacao_id]
        assert [p["medido_em"] for p in publicadas] == [e["medido_em"] for e in esperadas]
        assert [p["nivel_cm"] for p in publicadas] == [e["nivel_cm"] for e in esperadas]
        assert all(p["origem"] == "replay" and p["estacao_id"] == estacao_id for p in publicadas)
        assert [p["seq"] for p in publicadas] == list(range(1, 31))


def test_replay_do_exemplo_dispara_a_regra_local_e_passa_no_gateway():
    linhas = ler_evento(EXEMPLO)
    assert {linha["estacao_id"] for linha in linhas} == {"EST-ARI-01", "EST-PIR-01"}
    assert max(linha["nivel_cm"] for linha in linhas if linha["estacao_id"] == "EST-ARI-01") >= ARI.cota_transbordo_cm
    conexao = nova_conexao("EST-ARI-01")
    emulador.rodar_replay([conexao], agrupar_por_janela(linhas), velocidade=100, dormir=lambda _: None)

    assert [e["sirene"] for e in conexao.cliente.estados()] == ["ligada", "desligada"]
    for leitura in conexao.cliente.leituras():
        assert validar_leitura(leitura, "EST-ARI-01", AGORA)[1] is None


def test_replay_para_em_max_mensagens_e_pode_repetir():
    janelas = agrupar_por_janela(ler_evento(EXEMPLO))
    conexoes = [nova_conexao("EST-ARI-01"), nova_conexao("EST-PIR-01")]
    total = emulador.rodar_replay(conexoes, janelas, 100, repetir=True, max_mensagens=75, dormir=lambda _: None)
    assert total == 75  # passou das 60 linhas do arquivo: recomeçou


# ---------------------------------------------------------------- tempo real e guarda-e-reenvia


def test_tempo_real_publica_uma_leitura_por_estacao_a_cada_intervalo():
    conexoes = [nova_conexao("EST-ARI-01"), nova_conexao("EST-IPI-01")]
    pausas = []
    total = emulador.rodar_tempo_real(conexoes, 5, max_mensagens=6, dormir=pausas.append, relogio=lambda: AGORA)
    assert total == 6 and pausas == [5, 5]
    assert [leitura["seq"] for leitura in conexoes[0].cliente.leituras()] == [1, 2, 3]
    assert all(leitura["medido_em"] == "2026-11-16T18:00:00Z" for leitura in conexoes[1].cliente.leituras())
    assert conexoes[0].topico_leitura == "vigia/sensores/EST-ARI-01/leitura"


def test_sem_broker_guarda_e_reenvia_na_ordem_com_o_medido_em_original():
    conexao = nova_conexao()
    conexao.cliente.conectado = False
    for minuto in range(3):
        momento = AGORA + timedelta(minutes=minuto)
        assert conexao.ciclo(conexao.estacao.medir(minuto, momento), momento) == 0
    assert len(conexao.fila) == 3 and conexao.cliente.leituras() == []

    conexao.cliente.conectado = True  # o broker voltou: o próximo ciclo leva a fila inteira
    momento = AGORA + timedelta(minutes=3)
    assert conexao.ciclo(conexao.estacao.medir(3, momento), momento) == 4
    assert [leitura["medido_em"][14:16] for leitura in conexao.cliente.leituras()] == ["00", "01", "02", "03"]
    assert len(conexao.fila) == 0 and conexao.enviadas == 4


def test_fila_cheia_descarta_a_leitura_mais_antiga():
    conexao = nova_conexao(tamanho_fila=2)
    conexao.cliente.conectado = False
    for passo in range(5):
        conexao.ciclo(conexao.estacao.medir(passo, AGORA), AGORA)
    assert [json.loads(item)["seq"] for item in conexao.fila] == [4, 5]


def test_conexao_declara_presenca_assina_comando_e_responde_o_estado():
    conexao = nova_conexao()
    cliente = conexao.cliente
    assert cliente.testamento == ("vigia/sensores/EST-ARI-01/status", "offline", True)  # LWT

    conexao._ao_conectar(cliente, None, None, SimpleNamespace(is_failure=False), None)
    assert cliente.assinados == ["vigia/atuadores/EST-ARI-01/sirene"]
    assert ("vigia/sensores/EST-ARI-01/status", "online") in cliente.publicadas

    comando = SimpleNamespace(topic="vigia/atuadores/EST-ARI-01/sirene", payload=b'{"acao": "ligar", "segundos": 10}')
    conexao._ao_receber(cliente, None, comando)
    assert cliente.estados()[-1]["sirene"] == "ligada"
    assert conexao.estacao.tocando
