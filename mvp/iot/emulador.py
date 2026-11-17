"""Emulador das estações VigIA: publica por MQTT o mesmo payload do firmware (mvp/iot/firmware/sketch.ino).

Serve para o fluxo completo existir sem hardware: gera leituras, aplica a regra local, obedece ao comando da
sirene e guarda as leituras quando o broker cai (guarda-e-reenvia), exatamente como a estação de verdade.

Uso:  python -m mvp.iot.emulador --cenario temporal --intervalo 2
      python -m mvp.iot.emulador --modo replay --evento dados/referencia/eventos_demo/exemplo_curto.csv --velocidade 2

A primeira metade do arquivo são funções puras (sem rede), testadas em tests/iot; a segunda é o cliente MQTT.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import paho.mqtt.client as mqtt

from comum.config import RAIZ, carregar_config
from comum.estacoes import Estacao, carregar_estacoes
from comum.log import obter_logger

log = obter_logger("mvp.emulador")

FW = "1.0.0"
BASCULADA_MM = 0.25  # cada basculada do pluviômetro vale 0,25 mm (igual ao firmware)
TAMANHO_FILA = 720  # leituras guardadas por estação sem broker (1 h a cada 5 s); o firmware guarda 60
SEGUNDOS_PADRAO_SIRENE = 30

# ---------------------------------------------------------------- cenários (tempo comprimido para a demonstração)
#
# Um "passo" é uma publicação. O cenário se repete a cada CICLO_PASSOS: um trecho seco, a chuva e a recessão.
# Com o intervalo padrão de 5 s o ciclo dura 20 min e, no temporal, o alerta chega em cerca de 2 min.
CICLO_PASSOS = 240
INICIO_CHUVA, FIM_CHUVA = 12, 102
# Basculadas possíveis em cada passo de chuva (sorteadas): quanto mais basculadas, mais forte a chuva.
CENARIOS = {
    "calmo": (0,),  # sem chuva: o nível fica na base
    "chuva": (1, 2),  # média 0,375 mm por passo: o nível passa da atenção, mas não chega ao alerta
    "temporal": (2, 3, 4),  # média 0,75 mm por passo: passa do alerta e transborda
}
# Chuva constante (mm por passo) que, se mantida, leva o nível exatamente à cota de transbordo.
CHUVA_DE_TRANSBORDO_MM = 0.6


@dataclass(frozen=True)
class Resposta:
    """Como o córrego reage à chuva: k1 e k2 são tempos de esvaziamento (em passos); base é o nível sem chuva."""

    k1: float
    k2: float
    base_cm: float


# Córrego pequeno (Ipiranga) responde rápido; a várzea do Tietê (Pantanal) é a mais lenta.
RESPOSTAS = {
    "EST-ARI-01": Resposta(k1=6, k2=10, base_cm=35),
    "EST-PIR-01": Resposta(k1=5, k2=9, base_cm=30),
    "EST-PAN-01": Resposta(k1=10, k2=16, base_cm=70),
    "EST-IPI-01": Resposta(k1=4, k2=7, base_cm=25),
}
RESPOSTA_PADRAO = Resposta(k1=6, k2=10, base_cm=30)


def chuva_do_passo(cenario: str, passo: int, rng: random.Random) -> float:
    """Chuva (mm) de um passo: só chove no trecho de chuva do ciclo, sempre em múltiplos de uma basculada."""
    if not INICIO_CHUVA <= passo % CICLO_PASSOS < FIM_CHUVA:
        return 0.0
    return rng.choice(CENARIOS[cenario]) * BASCULADA_MM


@dataclass
class Bacia:
    """Dois reservatórios em série: o primeiro (ruas e galerias) enche com a chuva e esvazia no segundo (o córrego).

    É o que dá o atraso entre a chuva e a subida do nível, e a descida lenta depois (recessão).
    Mesma ideia de dados/simulacao/hidrologia.py, em versão mínima.
    """

    resposta: Resposta
    ganho: float  # cm de nível por mm/passo de vazão
    s1: float = 0.0
    s2: float = 0.0

    def avancar(self, chuva_mm: float) -> float:
        """Recebe a chuva do passo e devolve o nível do córrego (cm), ainda sem o ruído do sensor."""
        q1 = self.s1 / self.resposta.k1
        q2 = self.s2 / self.resposta.k2
        self.s1 += chuva_mm - q1
        self.s2 += q1 - q2
        return self.resposta.base_cm + self.ganho * q2


def criar_bacia(est: Estacao) -> Bacia:
    resposta = RESPOSTAS.get(est.estacao_id, RESPOSTA_PADRAO)
    return Bacia(resposta, ganho=(est.cota_transbordo_cm - resposta.base_cm) / CHUVA_DE_TRANSBORDO_MM)


def nivel_medido(nivel_cm: float, est: Estacao, rng: random.Random) -> float:
    """O que o ultrassom entregaria: ruído de ~1 cm, resolução de 0,5 cm e o limite físico do sensor."""
    com_ruido = round((nivel_cm + rng.gauss(0, 1.0)) * 2) / 2
    return min(max(com_ruido, 0.0), est.altura_sensor_cm - 5)


def simular(est: Estacao, cenario: str, passos: int, semente: int = 14) -> list[tuple[float, float]]:
    """Série (chuva_mm, nivel_cm) de um cenário, sem MQTT: usada nos testes e para entender o modelo."""
    rng = random.Random(f"{semente}-{est.estacao_id}")  # noqa: S311 - simulação, não é criptografia # nosec B311
    bacia = criar_bacia(est)
    serie = []
    for passo in range(passos):
        chuva = chuva_do_passo(cenario, passo, rng)
        serie.append((chuva, nivel_medido(bacia.avancar(chuva), est, rng)))
    return serie


# ---------------------------------------------------------------- payload, regra local e sirene

LED_POR_ESTADO = {"normal": "verde", "atencao": "amarelo", "alerta": "vermelho", "transbordo": "vermelho"}


def iso_utc(instante: datetime) -> str:
    return instante.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def montar_leitura(estacao_id: str, medido_em: str, nivel_cm: float, chuva_mm: float, seq: int, origem: str) -> dict:
    """O payload do contrato 3.1, com as mesmas chaves e na mesma ordem que o firmware publica."""
    return {
        "estacao_id": estacao_id,
        "medido_em": medido_em,
        "nivel_cm": round(nivel_cm, 1),
        "chuva_mm": round(chuva_mm, 2),
        "bateria_pct": max(20, 96 - seq // 50),  # descarga lenta, só para o campo variar
        "seq": seq,
        "fw": FW,
        "origem": origem,
    }


def regra_local(est: Estacao, nivel_cm: float) -> tuple[str, bool]:
    """A decisão que a estação toma sozinha, sem internet: (cor do LED, sirene ligada?).

    Verde abaixo da atenção, amarelo a partir da atenção, vermelho + sirene a partir do alerta.
    """
    estado = est.estado_regra(nivel_cm)
    return LED_POR_ESTADO[estado], estado in ("alerta", "transbordo")


@dataclass
class Sirene:
    """A sirene toca se a regra local mandar OU se houver um comando ainda dentro do prazo.

    Um comando 'desligar' só cancela o comando anterior: enquanto o nível estiver no alerta, a regra local
    mantém a sirene ligada (a segurança do morador não depende de quem está do outro lado da rede).
    """

    por_regra: bool = False
    comando_ate: datetime | None = None

    def ligada(self, agora: datetime) -> bool:
        return self.por_regra or (self.comando_ate is not None and agora < self.comando_ate)


class EstacaoVirtual:
    """Uma estação sem rede: gera leituras, aplica a regra local e obedece ao comando da sirene."""

    def __init__(self, est: Estacao, cenario: str = "calmo", semente: int = 14) -> None:
        self.est = est
        self.cenario = cenario
        self.rng = random.Random(f"{semente}-{est.estacao_id}")  # noqa: S311 - simulação, não é criptografia # nosec B311
        self.bacia = criar_bacia(est)
        self.seq = 0
        self.led = "verde"
        self.sirene = Sirene()
        self.tocando = False  # último estado da sirene já informado

    # --- leituras

    def medir(self, passo: int, agora: datetime) -> dict:
        """Modo tempo-real: avança o modelo um passo e devolve a leitura com medido_em = agora."""
        chuva = chuva_do_passo(self.cenario, passo, self.rng)
        nivel = nivel_medido(self.bacia.avancar(chuva), self.est, self.rng)
        return self._leitura(iso_utc(agora), nivel, chuva, "emulador")

    def reproduzir(self, linha: dict) -> dict:
        """Modo replay: a leitura sai com o medido_em, o nível e a chuva do arquivo de evento."""
        return self._leitura(linha["medido_em"], linha["nivel_cm"], linha["chuva_mm"], "replay")

    def _leitura(self, medido_em: str, nivel_cm: float, chuva_mm: float, origem: str) -> dict:
        self.seq += 1
        return montar_leitura(self.est.estacao_id, medido_em, nivel_cm, chuva_mm, self.seq, origem)

    # --- atuadores (LEDs e sirene)

    def atualizar_atuadores(self, nivel_cm: float, agora: datetime) -> list[dict]:
        """Aplica a regra local e vence o prazo do comando. Devolve os estados da sirene a publicar (0, 1 ou 2)."""
        estados = []
        if self.sirene.comando_ate is not None and agora >= self.sirene.comando_ate:
            self.sirene.comando_ate = None
            estados.append(self._se_mudou(agora, "comando"))
        led, self.sirene.por_regra = regra_local(self.est, nivel_cm)
        if led != self.led:
            self.led = led
            self._registrar("regra local", nivel_cm=nivel_cm, estado=self.est.estado_regra(nivel_cm), led=led)
        estados.append(self._se_mudou(agora, "regra_local"))
        return [e for e in estados if e is not None]

    def receber_comando(self, payload: bytes | str, agora: datetime) -> dict | None:
        """Trata o comando do contrato 3.2. Devolve o estado da sirene (a resposta), ou None se o comando é inválido."""
        try:
            comando = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            comando = None
        acao = comando.get("acao") if isinstance(comando, dict) else None
        if acao == "ligar":
            segundos = comando.get("segundos")
            valido = isinstance(segundos, int | float) and not isinstance(segundos, bool) and 0 < segundos <= 600
            self.sirene.comando_ate = agora + timedelta(seconds=segundos if valido else SEGUNDOS_PADRAO_SIRENE)
        elif acao == "desligar":
            self.sirene.comando_ate = None
        else:
            self._registrar("comando da sirene ignorado (inválido)")
            return None
        # "nivel_alerta" e não "nivel": no log JSON a chave "nivel" já é a severidade (INFO, WARNING...).
        self._registrar(
            "comando da sirene", acao=acao, nivel_alerta=comando.get("nivel"), alerta_id=comando.get("alerta_id")
        )
        return self._se_mudou(agora, "comando") or self._estado(agora, "comando")

    def _se_mudou(self, agora: datetime, gatilho: str) -> dict | None:
        """Só há estado novo a publicar quando a sirene de fato liga ou desliga."""
        tocando = self.sirene.ligada(agora)
        if tocando == self.tocando:
            return None
        self.tocando = tocando
        self._registrar("sirene TOCARIA agora" if tocando else "sirene silenciada", gatilho=gatilho)
        return self._estado(agora, gatilho)

    def _estado(self, agora: datetime, gatilho: str) -> dict:
        """Payload de estado do contrato 3.2. Se a regra local segura a sirene ligada, o motivo é ela."""
        motivo = "regra_local" if self.sirene.por_regra else gatilho
        return {"sirene": "ligada" if self.tocando else "desligada", "motivo": motivo, "em": iso_utc(agora)}

    def _registrar(self, mensagem: str, **dados) -> None:
        log.info(mensagem, extra={"dados": {"estacao_id": self.est.estacao_id, **dados}})


# ---------------------------------------------------------------- replay de um arquivo de evento


def _instante(texto: str) -> datetime:
    """Aceita '2026-01-15T18:00:00Z' e também o formato do pandas ('2026-01-15 18:00:00+00:00'); sem fuso = UTC."""
    instante = datetime.fromisoformat(texto.strip())
    return instante.astimezone(UTC) if instante.tzinfo else instante.replace(tzinfo=UTC)


def ler_evento(caminho: Path, estacoes: set[str] | None = None) -> list[dict]:
    """Lê o CSV do contrato (seção 7) e devolve as linhas em ordem de medido_em, com nível e chuva numéricos."""
    with open(caminho, encoding="utf-8", newline="") as f:
        linhas = [
            {
                "estacao_id": bruta["estacao_id"],
                "medido_em": iso_utc(_instante(bruta["medido_em"])),
                "nivel_cm": float(bruta["nivel_cm"]),
                "chuva_mm": float(bruta["chuva_mm"]),
            }
            for bruta in csv.DictReader(f)
        ]
    if estacoes is not None:
        linhas = [linha for linha in linhas if linha["estacao_id"] in estacoes]
    return sorted(linhas, key=lambda linha: (linha["medido_em"], linha["estacao_id"]))


def agrupar_por_janela(linhas: list[dict]) -> list[list[dict]]:
    """Junta as linhas de mesmo medido_em: no replay, as estações de uma janela são publicadas juntas."""
    janelas: list[list[dict]] = []
    for linha in linhas:
        if janelas and janelas[-1][0]["medido_em"] == linha["medido_em"]:
            janelas[-1].append(linha)
        else:
            janelas.append([linha])
    return janelas


# ---------------------------------------------------------------- cliente MQTT (um por estação, como no firmware)


class Conexao:
    """Liga uma EstacaoVirtual ao broker: presença (LWT), comando da sirene e guarda-e-reenvia."""

    def __init__(self, estacao: EstacaoVirtual, prefixo: str = "vigia", cliente=None, tamanho_fila: int = TAMANHO_FILA):
        self.estacao = estacao
        estacao_id = estacao.est.estacao_id
        self.topico_leitura = f"{prefixo}/sensores/{estacao_id}/leitura"
        self.topico_status = f"{prefixo}/sensores/{estacao_id}/status"
        self.topico_comando = f"{prefixo}/atuadores/{estacao_id}/sirene"
        self.topico_estado = f"{self.topico_comando}/estado"
        # Fila circular: sem broker as leituras ficam aqui com o medido_em original; cheia, a mais antiga é descartada.
        self.fila: deque[str] = deque(maxlen=tamanho_fila)
        self.trava = threading.Lock()  # o comando chega na thread do MQTT; as leituras saem da principal
        self.enviadas = 0
        self._ultimo_envio = None
        self.cliente = cliente or mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=f"vigia-emulador-{estacao_id}-{uuid.uuid4().hex[:6]}"
        )
        # LWT: se a estação sumir sem se despedir, o próprio broker publica "offline" por ela.
        self.cliente.will_set(self.topico_status, "offline", qos=1, retain=True)
        self.cliente.on_connect = self._ao_conectar
        self.cliente.on_message = self._ao_receber
        self.cliente.reconnect_delay_set(min_delay=1, max_delay=10)

    def iniciar(self, broker: str, porta: int) -> None:
        """connect_async + loop_start: o paho reconecta sozinho em segundo plano, inclusive na primeira tentativa."""
        self.cliente.connect_async(broker, porta, keepalive=30)
        self.cliente.loop_start()

    def _ao_conectar(self, cliente, _dados, _flags, codigo, _props) -> None:
        if codigo.is_failure:
            return
        cliente.subscribe(self.topico_comando, qos=1)
        cliente.publish(self.topico_status, "online", qos=1, retain=True)
        dados = {"estacao_id": self.estacao.est.estacao_id, "na_fila": len(self.fila)}
        log.info("estação conectada", extra={"dados": dados})

    def _ao_receber(self, cliente, _dados, mensagem) -> None:
        with self.trava:
            estado = self.estacao.receber_comando(mensagem.payload, datetime.now(UTC))
        if estado is not None:
            cliente.publish(self.topico_estado, json.dumps(estado), qos=1)

    def ciclo(self, leitura: dict, agora: datetime) -> int:
        """Um ciclo da estação: regra local, estado da sirene e a leitura. Devolve quantas leituras foram enviadas."""
        with self.trava:
            estados = self.estacao.atualizar_atuadores(leitura["nivel_cm"], agora)
        for estado in estados:
            self.cliente.publish(self.topico_estado, json.dumps(estado), qos=1)
        self.fila.append(json.dumps(leitura, separators=(",", ":")))
        return self.reenviar()

    def reenviar(self) -> int:
        """Esvazia a fila na ordem em que as leituras foram medidas; para na primeira falha e tenta no próximo ciclo."""
        enviadas = 0
        while self.fila and self.cliente.is_connected():
            envio = self.cliente.publish(self.topico_leitura, self.fila[0], qos=1)
            if envio.rc != mqtt.MQTT_ERR_SUCCESS:
                break
            self.fila.popleft()
            self._ultimo_envio = envio
            enviadas += 1
        self.enviadas += enviadas
        return enviadas

    def encerrar(self) -> None:
        """Última tentativa de esvaziar a fila, espera a confirmação (QoS 1), despede-se com 'offline' e desconecta."""
        try:
            self.reenviar()
            if self._ultimo_envio is not None:
                self._ultimo_envio.wait_for_publish(timeout=3)
            if self.cliente.is_connected():
                self.cliente.publish(self.topico_status, "offline", qos=1, retain=True).wait_for_publish(timeout=3)
        except (ValueError, RuntimeError):
            pass  # a conexão caiu no meio da despedida: o LWT do broker cobre esse caso
        self.cliente.disconnect()
        self.cliente.loop_stop()


def aguardar_conexao(conexoes: list[Conexao], limite_s: float = 10.0) -> bool:
    """Dá um tempo para o broker responder; se não responder, o emulador segue e guarda as leituras."""
    fim = time.monotonic() + limite_s
    while time.monotonic() < fim:
        if all(c.cliente.is_connected() for c in conexoes):
            return True
        time.sleep(0.1)
    log.warning("broker fora do ar: as leituras ficam guardadas e serão reenviadas quando ele voltar")
    return False


def _registrar_ciclo(conexao: Conexao, leitura: dict, enviadas: int) -> None:
    dados = {
        "estacao_id": leitura["estacao_id"],
        "medido_em": leitura["medido_em"],
        "nivel_cm": leitura["nivel_cm"],
        "chuva_mm": leitura["chuva_mm"],
        "led": conexao.estacao.led,
        "sirene": conexao.estacao.tocando,
        "enviadas": enviadas,
        "na_fila": len(conexao.fila),
    }
    log.info("leitura publicada" if enviadas else "sem broker: leitura guardada", extra={"dados": dados})


def rodar_tempo_real(
    conexoes: list[Conexao],
    intervalo_s: float,
    max_mensagens: int | None = None,
    dormir: Callable[[float], None] = time.sleep,
    relogio: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """A cada intervalo, uma leitura por estação com medido_em = agora. Devolve o total enviado ao broker."""
    total, passo = 0, 0
    while True:
        agora = relogio()
        for conexao in conexoes:
            leitura = conexao.estacao.medir(passo, agora)
            enviadas = conexao.ciclo(leitura, agora)
            _registrar_ciclo(conexao, leitura, enviadas)
            total += enviadas
            if max_mensagens is not None and total >= max_mensagens:
                return total
        passo += 1
        dormir(intervalo_s)


def rodar_replay(
    conexoes: list[Conexao],
    janelas: list[list[dict]],
    velocidade: float,
    repetir: bool = False,
    max_mensagens: int | None = None,
    dormir: Callable[[float], None] = time.sleep,
    relogio: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    """Publica o evento janela a janela (`velocidade` janelas por segundo), mantendo o medido_em do arquivo."""
    por_estacao = {c.estacao.est.estacao_id: c for c in conexoes}
    total = 0
    while True:
        for janela in janelas:
            for linha in janela:
                conexao = por_estacao.get(linha["estacao_id"])
                if conexao is None:
                    continue  # estação do arquivo que não está no catálogo ou ficou fora do filtro --estacoes
                leitura = conexao.estacao.reproduzir(linha)
                enviadas = conexao.ciclo(leitura, relogio())
                _registrar_ciclo(conexao, leitura, enviadas)
                total += enviadas
                if max_mensagens is not None and total >= max_mensagens:
                    return total
            dormir(1 / velocidade)
        if not repetir:
            return total


# ---------------------------------------------------------------- linha de comando


def _argumentos() -> argparse.Namespace:
    cfg = carregar_config()
    ap = argparse.ArgumentParser(description="Emulador das estações VigIA (mesmo payload do firmware ESP32).")
    ap.add_argument("--modo", choices=("tempo-real", "replay"), default="tempo-real")
    ap.add_argument("--cenario", choices=tuple(CENARIOS), default="calmo", help="só no modo tempo-real")
    ap.add_argument("--intervalo", type=float, default=5.0, help="segundos entre publicações (tempo-real)")
    ap.add_argument("--estacoes", default="", help="lista separada por vírgula; vazio = todas do catálogo")
    ap.add_argument("--evento", type=Path, help="CSV de evento (modo replay)")
    ap.add_argument("--velocidade", type=float, default=1.0, help="janelas do evento por segundo (replay)")
    ap.add_argument("--repetir", action="store_true", help="recomeça o evento quando ele acaba (replay)")
    ap.add_argument("--max-mensagens", type=int, default=None, help="encerra depois de N leituras enviadas")
    ap.add_argument("--semente", type=int, default=14, help="mesma semente = mesma série (demonstração reproduzível)")
    ap.add_argument("--broker", default=cfg.mqtt_host)
    ap.add_argument("--porta", type=int, default=cfg.mqtt_port)
    args = ap.parse_args()
    if args.modo == "replay" and args.evento is None:
        ap.error("--modo replay exige --evento <arquivo.csv>")
    if args.intervalo <= 0 or args.velocidade <= 0:
        ap.error("--intervalo e --velocidade precisam ser maiores que zero")
    args.estacoes = [e.strip() for e in args.estacoes.split(",") if e.strip()]
    desconhecidas = [e for e in args.estacoes if e not in carregar_estacoes()]
    if desconhecidas:
        ap.error(f"estação fora do catálogo: {', '.join(desconhecidas)}")
    return args


def main() -> None:
    args = _argumentos()
    cfg = carregar_config()
    catalogo = carregar_estacoes()
    escolhidas = [catalogo[e] for e in (args.estacoes or catalogo)]
    conexoes = [Conexao(EstacaoVirtual(est, args.cenario, args.semente), cfg.mqtt_prefixo) for est in escolhidas]
    ids = [est.estacao_id for est in escolhidas]
    inicio = {"modo": args.modo, "broker": f"{args.broker}:{args.porta}", "estacoes": ids}
    log.info("emulador iniciando", extra={"dados": inicio})
    for conexao in conexoes:
        conexao.iniciar(args.broker, args.porta)
    aguardar_conexao(conexoes)
    try:
        if args.modo == "replay":
            evento = args.evento if args.evento.is_absolute() or args.evento.exists() else RAIZ / args.evento
            janelas = agrupar_por_janela(ler_evento(evento, {e.estacao_id for e in escolhidas}))
            rodar_replay(conexoes, janelas, args.velocidade, args.repetir, args.max_mensagens)
        else:
            rodar_tempo_real(conexoes, args.intervalo, args.max_mensagens)
    except KeyboardInterrupt:
        log.info("encerrando a pedido")
    finally:
        for conexao in conexoes:
            conexao.encerrar()
        totais = {"enviadas": sum(c.enviadas for c in conexoes), "ficaram_na_fila": sum(len(c.fila) for c in conexoes)}
        log.info("emulador encerrado", extra={"dados": totais})


if __name__ == "__main__":
    main()
