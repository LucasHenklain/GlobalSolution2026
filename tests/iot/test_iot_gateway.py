"""Gateway MQTT: validação na porta (contrato 3.1) e gravação dos micro-lotes. Sem rede e sem broker."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import yaml

from comum.config import RAIZ
from dados.ingestao import gateway_mqtt
from dados.ingestao.gateway_mqtt import Gateway, chaves_desconhecidas, validar_leitura

AGORA = datetime(2026, 11, 16, 18, 0, 30, 123000, tzinfo=UTC)
TOPICO = "vigia/sensores/EST-ARI-01/leitura"


def leitura_ok(**trocas) -> dict:
    """O exemplo do contrato; cada teste troca só o campo que quer estragar."""
    base = {
        "estacao_id": "EST-ARI-01",
        "medido_em": "2026-11-16T18:00:00Z",
        "nivel_cm": 142.5,
        "chuva_mm": 1.25,
        "bateria_pct": 87,
        "seq": 123,
        "fw": "1.0.0",
        "origem": "emulador",
    }
    base.update(trocas)
    return base


def sem(campo: str) -> dict:
    leitura = leitura_ok()
    del leitura[campo]
    return leitura


# ---------------------------------------------------------------- validar_leitura (função pura)


def test_leitura_valida_passa_inteira():
    leitura, motivo = validar_leitura(leitura_ok(), "EST-ARI-01", AGORA)
    assert motivo is None
    assert leitura == leitura_ok()


def test_medido_em_com_outro_fuso_e_normalizado_para_utc():
    leitura, _ = validar_leitura(leitura_ok(medido_em="2026-11-16T15:00:00-03:00"), "EST-ARI-01", AGORA)
    assert leitura["medido_em"] == "2026-11-16T18:00:00Z"


@pytest.mark.parametrize(
    ("bruto", "motivo_esperado"),
    [
        (sem("estacao_id"), "LEI-01"),
        (sem("medido_em"), "LEI-01"),
        (sem("nivel_cm"), "LEI-01"),
        (sem("chuva_mm"), "LEI-01"),
        (leitura_ok(nivel_cm=None), "LEI-01"),
        (leitura_ok(nivel_cm="142.5"), "LEI-01"),  # texto não é número
        (leitura_ok(chuva_mm=True), "LEI-01"),  # bool não é número
        (leitura_ok(nivel_cm=float("nan")), "LEI-01"),
        (leitura_ok(medido_em="ontem à tarde"), "LEI-01"),
        (leitura_ok(medido_em="2026-11-16T18:00:00"), "LEI-01"),  # sem fuso não dá para confiar
        (leitura_ok(medido_em=1763316000), "LEI-01"),
        (leitura_ok(estacao_id="EST-XXX-99"), "LEI-02"),
        (leitura_ok(estacao_id=["EST-ARI-01"]), "LEI-02"),
        (leitura_ok(nivel_cm=-0.5), "LEI-03"),
        (leitura_ok(nivel_cm=400.5), "LEI-03"),  # acima da altura do sensor
        (leitura_ok(chuva_mm=-0.25), "LEI-04"),
        (leitura_ok(chuva_mm=60.25), "LEI-04"),
        (leitura_ok(medido_em="2026-11-16T18:05:31Z"), "LEI-05"),  # 5 min e 1 s no futuro
        (["não", "é", "objeto"], "GTW-01"),
    ],
)
def test_cada_tipo_de_rejeicao(bruto, motivo_esperado):
    leitura, motivo = validar_leitura(bruto, "EST-ARI-01", AGORA)
    assert leitura is None
    assert motivo.startswith(motivo_esperado)


def test_limites_das_faixas_sao_aceitos():
    for trocas in ({"nivel_cm": 0}, {"nivel_cm": 400}, {"chuva_mm": 0}, {"chuva_mm": 60}):
        assert validar_leitura(leitura_ok(**trocas), "EST-ARI-01", AGORA)[1] is None
    no_limite = (AGORA + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert validar_leitura(leitura_ok(medido_em=no_limite), "EST-ARI-01", AGORA)[1] is None


def test_estacao_diferente_da_do_topico_e_rejeitada():
    leitura, motivo = validar_leitura(leitura_ok(), "EST-PIR-01", AGORA)
    assert leitura is None
    assert motivo.startswith("GTW-02")


def test_chave_desconhecida_e_descartada_e_listada():
    bruto = leitura_ok(luminosidade_lux=800, senha="x")
    leitura, motivo = validar_leitura(bruto, "EST-ARI-01", AGORA)
    assert motivo is None
    assert "luminosidade_lux" not in leitura and "senha" not in leitura
    assert chaves_desconhecidas(bruto) == ["luminosidade_lux", "senha"]


def test_opcional_invalido_e_descartado_sem_invalidar_a_leitura():
    bruto = leitura_ok(bateria_pct=140, seq="7", fw=100, origem="satelite")
    leitura, motivo = validar_leitura(bruto, "EST-ARI-01", AGORA)
    assert motivo is None
    assert set(leitura) == {"estacao_id", "medido_em", "nivel_cm", "chuva_mm"}


def test_faixas_do_gateway_iguais_as_do_contrato_de_dados():
    contrato = RAIZ / "dados" / "contratos" / "leitura_sensor.v1.yaml"
    campos = yaml.safe_load(contrato.read_text(encoding="utf-8"))["campos"]
    assert campos["chuva_mm"]["maximo"] == gateway_mqtt.CHUVA_MAX_MM
    assert campos["nivel_cm"]["maximo"] == 400  # no gateway o teto é a altura do sensor de cada estação
    obrigatorios = {nome for nome, regra in campos.items() if regra["obrigatorio"]}
    assert obrigatorios == set(gateway_mqtt.OBRIGATORIOS)


# ---------------------------------------------------------------- micro-lotes na landing


def novo_gateway(tmp_path, **opcoes) -> Gateway:
    return Gateway(landing=tmp_path, relogio=lambda: AGORA, **opcoes)


def linhas(arquivo) -> list[dict]:
    return [json.loads(linha) for linha in arquivo.read_text(encoding="utf-8").splitlines()]


def test_micro_lote_e_quarentena_gravados_no_layout_do_contrato(tmp_path):
    gateway = novo_gateway(tmp_path)
    assert gateway.processar(TOPICO, json.dumps(leitura_ok(extra=1)).encode()) is None
    assert gateway.processar(TOPICO, json.dumps(leitura_ok(nivel_cm=999)).encode()).startswith("LEI-03")
    assert gateway.processar(TOPICO, b"{isto nao e json").startswith("GTW-01")
    arquivos = gateway.descarregar()

    lote = tmp_path / "sensores" / "20261116" / "leituras_20261116T180030Z.jsonl"
    quarentena = tmp_path / "quarentena_gateway" / "20261116" / "rejeitadas_20261116T180030Z.jsonl"
    assert arquivos == [lote, quarentena]
    assert linhas(lote) == [{**leitura_ok(), "recebido_em": "2026-11-16T18:00:30.123Z"}]
    rejeitadas = linhas(quarentena)
    assert [r["motivo"][:6] for r in rejeitadas] == ["LEI-03", "GTW-01"]
    assert rejeitadas[0]["bruto"]["nivel_cm"] == 999
    assert rejeitadas[1]["bruto"] == "{isto nao e json"
    assert all(r["recebido_em"] == "2026-11-16T18:00:30.123Z" for r in rejeitadas)
    assert not list(tmp_path.rglob("*.tmp"))  # a troca atômica não deixa resto


def test_batimento_traz_os_contadores(tmp_path):
    gateway = novo_gateway(tmp_path)
    gateway.processar(TOPICO, json.dumps(leitura_ok(extra=1)).encode())
    gateway.processar(TOPICO, b"lixo")
    gateway.descarregar()
    batimento = json.loads((tmp_path / "_gateway_batimento.json").read_text(encoding="utf-8"))
    assert batimento["atualizado_em"] == "2026-11-16T18:00:30Z"
    assert batimento["ultimo_lote_em"] == "2026-11-16T18:00:30Z"
    assert (batimento["recebidas"], batimento["validas"], batimento["rejeitadas"], batimento["lotes"]) == (2, 1, 1, 1)
    assert batimento["chaves_desconhecidas"] == 1
    assert batimento["motivos_rejeicao"] == {"GTW-01 payload não é JSON": 1}


def test_janela_vazia_nao_cria_lote_mas_atualiza_o_batimento(tmp_path):
    gateway = novo_gateway(tmp_path)
    assert gateway.descarregar() == []
    assert not (tmp_path / "sensores").exists()
    assert (tmp_path / "_gateway_batimento.json").exists()


def test_dois_lotes_no_mesmo_segundo_tem_nomes_diferentes(tmp_path):
    gateway = novo_gateway(tmp_path)
    nomes = []
    for seq in (1, 2, 3):
        gateway.processar(TOPICO, json.dumps(leitura_ok(seq=seq)).encode())
        (lote,) = gateway.descarregar()
        nomes.append(lote.name)
        lote.unlink()  # o pipeline move o lote para o bronze; o nome não pode ser reaproveitado mesmo assim
    assert nomes == [
        "leituras_20261116T180030Z.jsonl",
        "leituras_20261116T180030Z_2.jsonl",
        "leituras_20261116T180030Z_3.jsonl",
    ]


def test_lote_cheio_e_gravado_sem_esperar_a_janela(tmp_path):
    gateway = novo_gateway(tmp_path, max_lote=3)
    for seq in range(7):
        gateway.processar(TOPICO, json.dumps(leitura_ok(seq=seq)).encode())
    lotes = sorted((tmp_path / "sensores" / "20261116").glob("*.jsonl"))
    assert [len(linhas(lote)) for lote in lotes] == [3, 3]
    assert gateway.contadores["lotes"] == 2


def test_payload_gigante_vai_para_a_quarentena_truncado(tmp_path):
    gateway = novo_gateway(tmp_path)
    assert gateway.processar(TOPICO, b"x" * 5000).startswith("GTW-03")
    (quarentena,) = gateway.descarregar()
    assert len(linhas(quarentena)[0]["bruto"]) == 200


def test_callbacks_mqtt_com_cliente_duble(tmp_path):
    gateway = novo_gateway(tmp_path)
    cliente = gateway_mqtt.criar_cliente(gateway, "vigia/sensores/+/leitura")  # só cria o objeto; não conecta
    assinaturas = []
    duble = SimpleNamespace(subscribe=lambda topico, qos: assinaturas.append((topico, qos)))

    cliente.on_connect(duble, None, None, SimpleNamespace(is_failure=False), None)
    assert assinaturas == [("vigia/sensores/+/leitura", 1)] and gateway.conectado

    cliente.on_message(duble, None, SimpleNamespace(topic=TOPICO, payload=json.dumps(leitura_ok()).encode()))
    cliente.on_message(duble, None, SimpleNamespace(topic=TOPICO, payload=None))  # mensagem hostil não derruba
    assert gateway.contadores["validas"] == 1

    cliente.on_disconnect(duble, None, None, "caiu", None)
    assert not gateway.conectado
