"""Captura reproduzível da simulação no Wokwi: abre o Edge, carrega sketch.ino + diagram.json, instala as
bibliotecas, inicia a simulação do ESP32 e salva um PNG (a evidência dos sensores funcionando).

Uso:  python mvp/iot/firmware/capturar_wokwi.py [--saida captura-wokwi.png] [--espera 75] [--janela]
      python mvp/iot/firmware/capturar_wokwi.py --distancia 150 --saida captura-wokwi-alerta.png
        (--distancia muda a distância inicial do HC-SR04: 150 cm = nível 250 cm = ALERTA, LED vermelho e sirene)

Requer: Microsoft Edge, `pip install websocket-client` e internet (wokwi.com e o broker MQTT público).
Enquanto roda, em outro terminal:  python -m dados.ingestao.gateway_mqtt --broker broker.hivemq.com --duracao-s 90
"""

from __future__ import annotations

import argparse
import atexit
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
URL_NOVO_PROJETO = "https://wokwi.com/projects/new/esp32"
BIBLIOTECAS = ["PubSubClient", "ArduinoJson"]

# Trechos de JavaScript executados na página do Wokwi (clicam nos mesmos botões que uma pessoa clicaria).
JS_EDITOR_PRONTO = (
    "typeof window.monaco === 'object' && monaco.editor.getModels().some(m => m.uri.toString() === 'vfs:sketch.ino')"
)
JS_CARREGAR_SKETCH = (
    "monaco.editor.getModels().find(m => m.uri.toString() === 'vfs:sketch.ino').setValue(window.__vigia.sketch); 1"
)
JS_CARREGAR_DIAGRAMA = """(async () => {
  const aba = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'diagram.json');
  aba && aba.click();
  await new Promise(r => setTimeout(r, 1000));
  const modelo = monaco.editor.getModels().find(m => m.uri.toString() === 'vfs:diagram.json');
  if (modelo) modelo.setValue(window.__vigia.diagrama);
  return !!modelo;
})()"""
JS_INSTALAR_BIBLIOTECA = """(async (nome) => {
  const rotulo = b => b.getAttribute('aria-label') || b.title || '';
  const gerenciador = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Library Manager');
  gerenciador && gerenciador.click();
  await new Promise(r => setTimeout(r, 800));
  const adicionar = [...document.querySelectorAll('button')].find(b => rotulo(b) === 'Add a new library');
  adicionar && adicionar.click();
  await new Promise(r => setTimeout(r, 900));
  const campo = document.querySelector('input[type=text]');
  if (!campo) return 'campo de busca não apareceu';
  campo.focus();
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(campo, nome);
  campo.dispatchEvent(new Event('input', {bubbles: true}));
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 400));
    const item = [...document.querySelectorAll('[role=menuitem]')].find(e => e.textContent.trim() === nome);
    if (item) { item.click(); return 'ok'; }
  }
  return 'não encontrada';
})(%s)"""
JS_INICIAR_SIMULACAO = """(async () => {
  const rotulo = b => b.getAttribute('aria-label') || b.title || '';
  const aba = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Simulation');
  aba && aba.click();
  await new Promise(r => setTimeout(r, 800));
  const iniciar = [...document.querySelectorAll('button')].find(b => rotulo(b) === 'Start the simulation');
  iniciar && iniciar.click();
  return !!iniciar;
})()"""
JS_ERRO_DE_BUILD = (
    "(document.body.innerText.match(/(Build failed|Error during build|fatal error)[^\\n]{0,160}/g) || []).join(' | ')"
)
JS_VOLTAR_AO_CODIGO = """(async () => {
  const aba = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'sketch.ino');
  aba && aba.click();
  await new Promise(r => setTimeout(r, 1500));
  return !!aba;
})()"""
JS_ESTADO_DA_SIMULACAO = (
    "[...document.querySelectorAll('button')].map(b => b.getAttribute('aria-label') || '')"
    ".filter(t => /simulation/i.test(t)).join(', ')"
)


def diagrama_com_distancia(texto: str, distancia: int | None) -> str:
    """Troca a distância inicial do HC-SR04 só em memória (o arquivo não muda), para capturar outro cenário."""
    if distancia is None:
        return texto
    diagrama = json.loads(texto)
    for peca in diagrama["parts"]:
        if peca["type"] == "wokwi-hc-sr04":
            peca.setdefault("attrs", {})["distance"] = str(distancia)
    return json.dumps(diagrama, indent=2, ensure_ascii=False)


class Pagina:
    """Conversa com a aba do Edge pelo DevTools Protocol (CDP): manda um comando e espera a resposta dele."""

    def __init__(self, url_ws: str) -> None:
        import websocket  # websocket-client; importado aqui para o resto do arquivo não depender dele

        self.ws = websocket.create_connection(url_ws, timeout=120, suppress_origin=True)
        self.ultimo_id = 0

    def cdp(self, metodo: str, **parametros) -> dict:
        self.ultimo_id += 1
        self.ws.send(json.dumps({"id": self.ultimo_id, "method": metodo, "params": parametros}))
        while True:
            mensagem = json.loads(self.ws.recv())
            if mensagem.get("id") == self.ultimo_id:
                if "error" in mensagem:
                    raise RuntimeError(mensagem["error"])
                return mensagem.get("result", {})

    def js(self, expressao: str):
        resposta = self.cdp("Runtime.evaluate", expression=expressao, awaitPromise=True, returnByValue=True)
        return resposta.get("result", {}).get("value")

    def fechar(self) -> None:
        self.ws.close()


def abrir_edge(caminho: str, porta: int, visivel: bool) -> subprocess.Popen:
    """Abre o Edge com um perfil temporário e a porta de depuração ligada, já na página de novo projeto ESP32."""
    perfil = tempfile.mkdtemp(prefix="edge_wokwi_")
    comando = [
        caminho,
        f"--remote-debugging-port={porta}",
        "--remote-allow-origins=*",
        f"--user-data-dir={perfil}",
        "--window-size=1900,1000",
        "--no-first-run",
        "--disable-extensions",
        "--disable-gpu",
        URL_NOVO_PROJETO,
    ]
    if not visivel:
        comando.insert(1, "--headless=new")
    # Variáveis de quem chamou o script (ex.: um app Electron) confundem o Edge; ele recebe um ambiente limpo.
    ambiente = {k: v for k, v in os.environ.items() if not k.startswith(("CHROME_", "CLAUDE", "ELECTRON_"))}
    edge = subprocess.Popen(comando, env=ambiente, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    atexit.register(lambda: edge.poll() is None and edge.terminate())  # fecha o Edge mesmo se algo falhar no meio
    return edge


def endereco_da_aba(porta: int) -> str:
    """Pergunta ao Edge (só em 127.0.0.1) qual é o WebSocket de depuração da aba do Wokwi."""
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{porta}/json", timeout=2) as resposta:  # noqa: S310
                for aba in json.load(resposta):
                    if aba.get("type") == "page" and "wokwi" in aba.get("url", ""):
                        return aba["webSocketDebuggerUrl"]
        except OSError:
            pass  # o Edge ainda está subindo
        time.sleep(0.5)
    raise SystemExit("o Edge não expôs a página do Wokwi pelo DevTools")


def carregar_projeto(pagina: Pagina, sketch: str, diagrama: str) -> None:
    print("aguardando o editor do Wokwi...")
    for _ in range(120):
        if pagina.js(JS_EDITOR_PRONTO):
            break
        time.sleep(1)
    else:
        raise SystemExit("o editor do Wokwi não carregou")
    pagina.js(f"window.__vigia = {{sketch: {json.dumps(sketch)}, diagrama: {json.dumps(diagrama)}}}; 1")
    pagina.js(JS_CARREGAR_SKETCH)
    if not pagina.js(JS_CARREGAR_DIAGRAMA):
        raise SystemExit("não achei a aba diagram.json no editor")
    print("sketch e diagrama carregados")
    for biblioteca in BIBLIOTECAS:
        print(f"biblioteca {biblioteca}: {pagina.js(JS_INSTALAR_BIBLIOTECA % json.dumps(biblioteca))}")


def simular(pagina: Pagina, espera_s: int) -> None:
    if not pagina.js(JS_INICIAR_SIMULACAO):
        raise SystemExit("não achei o botão de iniciar a simulação")
    print(f"simulação iniciada; aguardando {espera_s} s (compilação + Wi-Fi + NTP + MQTT)...")
    for segundo in range(espera_s):
        time.sleep(1)
        if segundo % 15 == 14:
            erro = pagina.js(JS_ERRO_DE_BUILD)
            if erro:
                raise SystemExit(f"falha de compilação: {erro}")


def capturar(pagina: Pagina, saida: Path) -> None:
    pagina.js(JS_VOLTAR_AO_CODIGO)  # com a aba do código aberta, o monitor serial aparece embaixo do editor
    estado = pagina.js(JS_ESTADO_DA_SIMULACAO)
    png = base64.b64decode(pagina.cdp("Page.captureScreenshot", format="png")["data"])
    saida.write_bytes(png)
    print(f"estado: {estado} · captura salva em {saida} ({len(png) // 1024} KB)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Roda o firmware do VigIA no Wokwi e salva uma captura em PNG.")
    ap.add_argument("--saida", type=Path, default=AQUI / "captura-wokwi.png")
    ap.add_argument("--espera", type=int, default=75, help="segundos de simulação antes da captura")
    ap.add_argument("--distancia", type=int, help="distância inicial do HC-SR04 em cm (2-400); 150 = cenário de alerta")
    ap.add_argument("--janela", action="store_true", help="abre o Edge visível (padrão: sem janela)")
    ap.add_argument("--porta", type=int, default=9333, help="porta local do DevTools")
    ap.add_argument("--navegador", default=EDGE, help="caminho do msedge.exe")
    args = ap.parse_args()
    if args.distancia is not None and not 2 <= args.distancia <= 400:
        ap.error("--distancia precisa estar entre 2 e 400 cm (faixa do HC-SR04)")
    try:
        import websocket  # noqa: F401 - só confere, antes de abrir o navegador, que a dependência existe
    except ImportError:
        sys.exit("instale: python -m pip install websocket-client")

    sketch = (AQUI / "sketch.ino").read_text(encoding="utf-8")
    diagrama = diagrama_com_distancia((AQUI / "diagram.json").read_text(encoding="utf-8"), args.distancia)
    edge = abrir_edge(args.navegador, args.porta, args.janela)
    pagina = Pagina(endereco_da_aba(args.porta))
    try:
        pagina.cdp("Page.enable")
        pagina.cdp("Runtime.enable")
        pagina.cdp("Emulation.setDeviceMetricsOverride", width=1900, height=1000, deviceScaleFactor=1, mobile=False)
        carregar_projeto(pagina, sketch, diagrama)
        simular(pagina, args.espera)
        capturar(pagina, args.saida)
    finally:
        # Browser.close encerra o Edge inteiro (abas e processos filhos). Só terminate() deixava a simulação
        # rodando em segundo plano e consumindo CPU.
        try:
            pagina.cdp("Browser.close")
        except Exception:  # noqa: BLE001, S110 - o navegador fecha a conexão ao obedecer; não há o que tratar
            pass
        pagina.fechar()
        edge.terminate()


if __name__ == "__main__":
    main()
