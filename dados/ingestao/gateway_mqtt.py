"""Gateway MQTT: a porta de entrada do data lake.

Assina as leituras das estações, valida cada uma pelo contrato (docs/contratos-tecnicos.md, seção 3.1) e grava
micro-lotes JSONL na landing. O que reprova vai para a quarentena do gateway com o motivo, nunca é jogado fora.

Uso:  python -m dados.ingestao.gateway_mqtt [--broker HOST] [--porta 1883] [--janela-s 5] [--duracao-s 60]
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt

from comum.config import carregar_config
from comum.estacoes import Estacao, carregar_estacoes
from comum.log import obter_logger
from dados import camadas

log = obter_logger("dados.gateway")

# Mesmas faixas do contrato dados/contratos/leitura_sensor.v1.yaml (um teste confere que continuam iguais).
CHUVA_MAX_MM = 60.0
TOLERANCIA_FUTURO = timedelta(minutes=5)
OBRIGATORIOS = ("estacao_id", "medido_em", "nivel_cm", "chuva_mm")
OPCIONAIS = ("bateria_pct", "seq", "fw", "origem")
ORIGENS = ("wokwi", "emulador", "replay")
LIMITE_PAYLOAD_BYTES = 2048  # uma leitura tem ~170 bytes; acima disso não é uma estação falando


# ---------------------------------------------------------------- validação (funções puras, sem rede nem disco)


def _numero(valor: object) -> float | None:
    """Aceita int/float finito. bool é subclasse de int em Python, por isso é recusado à parte."""
    if isinstance(valor, bool) or not isinstance(valor, int | float) or not math.isfinite(valor):
        return None
    return float(valor)


def _instante_utc(texto: object) -> datetime | None:
    """Lê um ISO 8601 com fuso explícito (o contrato exige UTC com 'Z'); sem fuso não dá para confiar na hora."""
    if not isinstance(texto, str):
        return None
    try:
        instante = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return instante.astimezone(UTC) if instante.tzinfo else None


def _opcionais_validos(bruto: dict) -> dict:
    """Campo opcional com tipo ou faixa errada é descartado sem invalidar a leitura (regra LEI-07 do contrato)."""
    limpos: dict = {}
    bateria = _numero(bruto.get("bateria_pct"))
    if bateria is not None and 0 <= bateria <= 100:
        limpos["bateria_pct"] = bateria
    seq = bruto.get("seq")
    if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
        limpos["seq"] = seq
    if isinstance(bruto.get("fw"), str):
        limpos["fw"] = bruto["fw"][:20]
    if bruto.get("origem") in ORIGENS:
        limpos["origem"] = bruto["origem"]
    return limpos


def chaves_desconhecidas(bruto: dict) -> list[str]:
    """Chaves fora do contrato: o gateway não as grava, só conta (protege o esquema na porta)."""
    return sorted(str(chave) for chave in bruto if chave not in OBRIGATORIOS + OPCIONAIS)


def validar_leitura(
    bruto: dict, estacao_topico: str, agora: datetime, estacoes: dict[str, Estacao] | None = None
) -> tuple[dict | None, str | None]:
    """Devolve (leitura limpa, None) se passou no contrato, ou (None, motivo) se deve ir para a quarentena."""
    if not isinstance(bruto, dict):
        return None, "GTW-01 payload não é um objeto JSON"
    for campo in OBRIGATORIOS:
        if bruto.get(campo) is None:
            return None, f"LEI-01 campo obrigatório ausente: {campo}"

    estacao_id = bruto["estacao_id"]
    estacao = (estacoes or carregar_estacoes()).get(estacao_id) if isinstance(estacao_id, str) else None
    if estacao is None:
        return None, "LEI-02 estação fora do catálogo"
    if estacao_id != estacao_topico:
        # Uma estação só pode falar por si: impede que um dispositivo publique no lugar de outro.
        return None, "GTW-02 estação diferente da do tópico"

    medido_em = _instante_utc(bruto["medido_em"])
    if medido_em is None:
        return None, "LEI-01 medido_em não é data/hora ISO em UTC"
    if medido_em > agora + TOLERANCIA_FUTURO:
        return None, "LEI-05 leitura no futuro"

    nivel, chuva = _numero(bruto["nivel_cm"]), _numero(bruto["chuva_mm"])
    if nivel is None or chuva is None:
        return None, "LEI-01 nivel_cm e chuva_mm precisam ser números"
    if not 0 <= nivel <= estacao.altura_sensor_cm:
        return None, "LEI-03 nível fora da faixa"
    if not 0 <= chuva <= CHUVA_MAX_MM:
        return None, "LEI-04 chuva fora da faixa"

    leitura = {
        "estacao_id": estacao_id,
        "medido_em": medido_em.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nivel_cm": nivel,
        "chuva_mm": chuva,
    }
    leitura.update(_opcionais_validos(bruto))
    return leitura, None


def estacao_do_topico(topico: str) -> str:
    """vigia/sensores/EST-ARI-01/leitura -> EST-ARI-01."""
    partes = topico.split("/")
    return partes[-2] if len(partes) >= 2 else ""


def iso_ms(instante: datetime) -> str:
    """UTC com milissegundos: o silver usa recebido_em para decidir qual duplicata chegou por último."""
    return instante.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{instante.microsecond // 1000:03d}Z"


# ---------------------------------------------------------------- acumular e gravar os micro-lotes


class Gateway:
    """Valida as mensagens que chegam e as acumula em memória; `descarregar` grava o micro-lote na landing."""

    def __init__(
        self,
        landing: Path | None = None,
        max_lote: int = 200,
        relogio: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.landing = landing or camadas.caminho("landing")
        self.max_lote = max_lote
        self.relogio = relogio
        self.contadores: Counter[str] = Counter(recebidas=0, validas=0, rejeitadas=0, lotes=0, chaves_desconhecidas=0)
        self.motivos: Counter[str] = Counter()
        self.conectado = False
        self.iniciado_em = camadas.agora_iso()
        self.ultimo_lote_em: str | None = None
        self._validas: list[dict] = []
        self._rejeitadas: list[dict] = []
        self._trava = threading.Lock()  # as mensagens chegam na thread do MQTT; a gravação roda na principal
        self._carimbo_atual = ""
        self._nomes_no_carimbo: set[str] = set()

    def processar(self, topico: str, payload: bytes) -> str | None:
        """Trata uma mensagem. Devolve None se a leitura foi aceita, ou o motivo da rejeição."""
        recebido_em = iso_ms(self.relogio())
        with self._trava:
            self.contadores["recebidas"] += 1
            leitura, motivo, bruto = self._validar(topico, payload)
            if leitura is not None:
                leitura["recebido_em"] = recebido_em
                self._validas.append(leitura)
                self.contadores["validas"] += 1
            else:
                rejeitada = {"motivo": motivo, "bruto": bruto, "topico": topico, "recebido_em": recebido_em}
                self._rejeitadas.append(rejeitada)
                self.contadores["rejeitadas"] += 1
                self.motivos[motivo or "?"] += 1
            if len(self._validas) + len(self._rejeitadas) >= self.max_lote:
                self._descarregar()  # rajada: não espera a janela para não acumular memória
            return motivo

    def _validar(self, topico: str, payload: bytes) -> tuple[dict | None, str | None, object]:
        """Do payload cru até (leitura, motivo, bruto que vai para a quarentena se reprovar)."""
        if len(payload) > LIMITE_PAYLOAD_BYTES:
            return None, "GTW-03 payload grande demais", payload[:200].decode("utf-8", "replace")
        try:
            bruto = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return None, "GTW-01 payload não é JSON", payload.decode("utf-8", "replace")
        leitura, motivo = validar_leitura(bruto, estacao_do_topico(topico), self.relogio())
        if leitura is not None:
            self.contadores["chaves_desconhecidas"] += len(chaves_desconhecidas(bruto))
        return leitura, motivo, bruto

    def descarregar(self) -> list[Path]:
        """Grava o que acumulou e atualiza o batimento. Chamado a cada janela e no encerramento."""
        with self._trava:
            return self._descarregar()

    def _descarregar(self) -> list[Path]:
        agora = self.relogio()
        arquivos = []
        if self._validas:
            arquivos.append(self._gravar_lote("sensores", "leituras", self._validas, agora))
            self._validas = []
            self.contadores["lotes"] += 1
            self.ultimo_lote_em = agora.strftime("%Y-%m-%dT%H:%M:%SZ")
        if self._rejeitadas:
            arquivos.append(self._gravar_lote("quarentena_gateway", "rejeitadas", self._rejeitadas, agora))
            self._rejeitadas = []
        self._gravar_batimento(agora)
        return arquivos

    def _gravar_lote(self, pasta: str, prefixo: str, linhas: list[dict], agora: datetime) -> Path:
        """Escreve em .tmp e troca de nome: o pipeline (que lê *.jsonl) nunca enxerga um lote pela metade."""
        carimbo = agora.strftime("%Y%m%dT%H%M%SZ")
        destino = self._nome_unico(self.landing / pasta / carimbo[:8], prefixo, carimbo)
        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(destino.name + ".tmp")
        with open(temporario, "w", encoding="utf-8", newline="\n") as f:
            for linha in linhas:
                f.write(json.dumps(linha, ensure_ascii=False, separators=(",", ":")) + "\n")
        camadas.substituir_atomico(temporario, destino)
        log.info("lote gravado", extra={"dados": {"arquivo": destino.name, "pasta": pasta, "linhas": len(linhas)}})
        return destino

    def _nome_unico(self, pasta: Path, prefixo: str, carimbo: str) -> Path:
        """Dois lotes no mesmo segundo ganham sufixo _2, _3...: nome repetido sobrescreveria o lote anterior.

        A lista em memória é necessária porque o pipeline move os lotes para o bronze: só olhar o disco não basta.
        """
        if carimbo != self._carimbo_atual:
            self._carimbo_atual, self._nomes_no_carimbo = carimbo, set()
        n = 1
        while True:
            nome = f"{prefixo}_{carimbo}.jsonl" if n == 1 else f"{prefixo}_{carimbo}_{n}.jsonl"
            if nome not in self._nomes_no_carimbo and not (pasta / nome).exists():
                self._nomes_no_carimbo.add(nome)
                return pasta / nome
            n += 1

    def resumo(self) -> dict:
        return {**self.contadores, "motivos_rejeicao": dict(self.motivos)}

    def _gravar_batimento(self, agora: datetime) -> None:
        """Sinal de vida para o monitoramento: se `atualizado_em` parar de andar, o gateway caiu."""
        batimento = {
            "atualizado_em": agora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "iniciado_em": self.iniciado_em,
            "conectado": self.conectado,
            "ultimo_lote_em": self.ultimo_lote_em,
            **self.resumo(),
        }
        camadas.escrever_json(batimento, self.landing / "_gateway_batimento.json")


# ---------------------------------------------------------------- cliente MQTT


def criar_cliente(gateway: Gateway, topico: str) -> mqtt.Client:
    """Liga o cliente MQTT ao gateway. Assinar dentro do on_connect faz a assinatura voltar a cada reconexão."""
    cliente = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"vigia-gateway-{uuid.uuid4().hex[:8]}")

    def ao_conectar(cli, _dados, _flags, codigo, _props) -> None:
        if codigo.is_failure:
            log.error("broker recusou a conexão", extra={"dados": {"codigo": str(codigo)}})
            return
        gateway.conectado = True
        cli.subscribe(topico, qos=1)
        log.info("conectado ao broker", extra={"dados": {"topico": topico}})

    def ao_desconectar(_cli, _dados, _flags, codigo, _props) -> None:
        gateway.conectado = False
        if getattr(codigo, "is_failure", True):  # desconexão normal (encerramento) não é motivo de aviso
            log.warning("conexão com o broker caiu; reconectando sozinho", extra={"dados": {"codigo": str(codigo)}})

    def ao_receber(_cli, _dados, mensagem) -> None:
        try:
            gateway.processar(mensagem.topic, mensagem.payload)
        except Exception:  # noqa: BLE001 - uma mensagem hostil ou disco cheio não pode derrubar a thread do MQTT
            log.exception("falha ao tratar mensagem", extra={"dados": {"topico": mensagem.topic}})

    cliente.on_connect = ao_conectar
    cliente.on_disconnect = ao_desconectar
    cliente.on_message = ao_receber
    cliente.reconnect_delay_set(min_delay=1, max_delay=15)
    return cliente


def _encerrar(*_args) -> None:
    """`docker stop` manda SIGTERM: tratar como Ctrl+C garante que o último lote seja gravado."""
    raise KeyboardInterrupt


def executar(broker: str, porta: int, janela_s: float, max_lote: int, duracao_s: float | None, log_s: float) -> Gateway:
    """Roda até `duracao_s` (ou para sempre), descarregando um micro-lote a cada janela."""
    cfg = carregar_config()
    gateway = Gateway(max_lote=max_lote)
    topico = f"{cfg.mqtt_prefixo}/sensores/+/leitura"
    cliente = criar_cliente(gateway, topico)
    signal.signal(signal.SIGTERM, _encerrar)
    inicio = {"broker": f"{broker}:{porta}", "topico": topico, "janela_s": janela_s, "landing": gateway.landing}
    log.info("gateway iniciando", extra={"dados": inicio})
    # connect_async + loop_start: se o broker ainda não subiu (ou cair), o paho fica tentando em segundo plano.
    cliente.connect_async(broker, porta, keepalive=30)
    cliente.loop_start()
    fim = time.monotonic() + duracao_s if duracao_s else None
    proximo_log = time.monotonic() + log_s
    try:
        while fim is None or time.monotonic() < fim:
            time.sleep(janela_s if fim is None else max(0.0, min(janela_s, fim - time.monotonic())))
            try:
                gateway.descarregar()
            except OSError:
                log.exception("falha ao gravar o lote; as leituras ficam em memória para a próxima janela")
            if time.monotonic() >= proximo_log:
                log.info("contadores", extra={"dados": gateway.resumo()})
                proximo_log = time.monotonic() + log_s
    except KeyboardInterrupt:
        log.info("encerrando a pedido")
    finally:
        cliente.disconnect()
        cliente.loop_stop()
        gateway.conectado = False
        gateway.descarregar()
        log.info("gateway encerrado", extra={"dados": gateway.resumo()})
    return gateway


def main() -> None:
    cfg = carregar_config()
    ap = argparse.ArgumentParser(description="Gateway MQTT do VigIA: valida leituras e grava micro-lotes na landing.")
    ap.add_argument("--broker", default=cfg.mqtt_host)
    ap.add_argument("--porta", type=int, default=cfg.mqtt_port)
    ap.add_argument("--janela-s", type=float, default=5.0, help="segundos entre um micro-lote e outro")
    ap.add_argument("--max-lote", type=int, default=200, help="grava antes da janela se acumular N mensagens")
    ap.add_argument("--duracao-s", type=float, default=None, help="encerra sozinho depois de N segundos")
    ap.add_argument("--log-s", type=float, default=30.0, help="segundos entre os logs de contadores")
    args = ap.parse_args()
    executar(args.broker, args.porta, args.janela_s, args.max_lote, args.duracao_s, args.log_s)


if __name__ == "__main__":
    main()
