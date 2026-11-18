"""Gera os prints do PDF com o protótipo REAL rodando: sobe os serviços, reproduz o temporal passo a passo e fotografa.

Uso (a partir da raiz):  python docs/ferramentas/capturar_evidencias.py [--porta-app 8021] [--porta-painel 8521]

Nada aqui é montagem: o script alimenta o gateway com as leituras do evento, espera o pipeline e a IA reagirem e só
então captura cada tela no navegador (Edge via Playwright). Saída: docs/evidencias/prints/*.png
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from docs.ferramentas.navegador import abrir  # noqa: E402

EVENTO = RAIZ / "dados" / "referencia" / "eventos_demo" / "temporal_2025-01-24.csv"
SAIDA = RAIZ / "docs" / "evidencias" / "prints"


class Reprodutor:
    """Entrega ao gateway as janelas do evento até um instante e espera o app refletir a leitura."""

    def __init__(self, app_url: str) -> None:
        from dados.ingestao.gateway_mqtt import Gateway

        self.gateway = Gateway()
        self.app_url = app_url
        with open(EVENTO, encoding="utf-8", newline="") as arquivo:
            self.linhas = list(csv.DictReader(arquivo))
        self.enviado_ate = ""

    def avancar_ate(self, instante_utc: str, espera_s: float = 60) -> None:
        novas = [linha for linha in self.linhas if self.enviado_ate < linha["medido_em"] <= instante_utc]
        for linha in novas:
            leitura = {
                "estacao_id": linha["estacao_id"],
                "medido_em": linha["medido_em"],
                "nivel_cm": float(linha["nivel_cm"]),
                "chuva_mm": float(linha["chuva_mm"]),
                "bateria_pct": 90,
                "origem": "replay",
            }
            self.gateway.processar(f"vigia/sensores/{linha['estacao_id']}/leitura", json.dumps(leitura).encode())
        self.gateway.descarregar()
        self.enviado_ate = instante_utc
        # A leitura aparece no /status.txt em horário de Brasília (UTC-3): esperamos por ela.
        hora_local = f"{(int(instante_utc[11:13]) - 3) % 24:02d}:{instante_utc[14:16]}"
        limite = time.time() + espera_s
        while time.time() < limite:
            if all(hora_local in linha for linha in httpx.get(f"{self.app_url}/status.txt").text.splitlines()[1:]):
                time.sleep(3)  # folga para os alertas da mesma rodada chegarem
                return
            time.sleep(1)
        raise TimeoutError(f"o app não refletiu a leitura de {instante_utc}")


def encerrar_arvore(processo: subprocess.Popen) -> None:
    """Encerra o lançador e os serviços que ele abriu (no Windows, terminate() mataria só o processo-pai)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(processo.pid), "/T", "/F"], capture_output=True, check=False)
    else:
        processo.terminate()
    time.sleep(2)


def entrar(pagina, base: str, email: str, senha: str) -> None:
    pagina.goto(f"{base}/entrar")
    pagina.fill("input[name=email]", email)
    pagina.fill("input[name=senha]", senha)
    pagina.click("main button[type=submit]")
    pagina.wait_for_load_state()


def foto(pagina, nome: str, inteira: bool = True) -> None:
    pagina.screenshot(path=str(SAIDA / f"{nome}.png"), full_page=inteira)
    print("print:", nome)


def painel(
    pagina, base: str, nome: str, fonte: str | None = None, periodo: str | None = None, aba: str | None = None
) -> None:
    """Abre o dashboard, aplica os filtros pedidos e fotografa."""
    pagina.goto(base)
    pagina.get_by_text("Painel da Defesa Civil").first.wait_for(timeout=90000)
    if fonte:
        pagina.get_by_text(fonte, exact=True).click()
        pagina.wait_for_timeout(4000)
    if periodo:
        pagina.get_by_test_id("stSelectbox").first.click()
        pagina.get_by_role("option", name=periodo).click()
        pagina.wait_for_timeout(5000)
    if aba:
        pagina.get_by_role("tab", name=aba).click()
        pagina.wait_for_timeout(3000)
    pagina.wait_for_timeout(4000)
    foto(pagina, nome)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--porta-app", type=int, default=8021)
    parser.add_argument("--porta-painel", type=int, default=8521)
    parser.add_argument(
        "--so-painel", action="store_true", help="refaz só os prints do dashboard (mantém os dados ao vivo)"
    )
    args = parser.parse_args()
    app, dash = f"http://127.0.0.1:{args.porta_app}", f"http://127.0.0.1:{args.porta_painel}"
    SAIDA.mkdir(parents=True, exist_ok=True)
    ambiente = {**os.environ, "PYTHONUTF8": "1"}
    servicos = subprocess.Popen(
        [sys.executable, "-m", "devops.demo", *([] if args.so_painel else ["--limpar"]), "--sem-replay",
         "--porta-app", str(args.porta_app), "--porta-painel", str(args.porta_painel)],
        cwd=RAIZ, env=ambiente,
    )  # fmt: skip
    try:
        for _ in range(120):
            try:
                if httpx.get(f"{app}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        time.sleep(15)
        from mvp.web import seed

        if not args.so_painel:
            evento = Reprodutor(app)

            with abrir(1280, 860) as (_, pg):
                evento.avancar_ate("2025-01-24T18:00:00Z")
                pg.goto(app)
                foto(pg, "01_inicio_tempo_seco")
                pg.goto(f"{app}/cadastro")
                foto(pg, "02_cadastro")

                # 16:20 em Brasília: a chuva desaba, o córrego ainda está baixo e a IA já avisa.
                evento.avancar_ate("2025-01-24T19:20:00Z")
                entrar(pg, app, seed.EMAIL_MORADOR, seed.SENHA_MORADOR)
                pg.goto(f"{app}/minha-area")
                foto(pg, "03_minha_area_ia_antecipa")
                pg.goto(f"{app}/alertas")
                foto(pg, "04_alertas")
                pg.locator("a[href^='/alertas/ALT-']").first.click()
                pg.wait_for_load_state()
                foto(pg, "05_alerta_detalhe")

                # 17:30: o córrego transbordou (uma hora depois do primeiro aviso da IA).
                evento.avancar_ate("2025-01-24T20:30:00Z")
                pg.goto(f"{app}/minha-area")
                foto(pg, "06_minha_area_transbordo")
                pg.goto(app)
                foto(pg, "07_inicio_durante_o_temporal")
                pg.goto(f"{app}/estacoes/EST-ARI-01")
                foto(pg, "08_estacao_detalhe")

                pg.goto(f"{app}/ocorrencias/nova")
                pg.select_option("select[name=tipo]", "bueiro_entupido")
                pg.fill("textarea[name=descricao]", "Bueiro entupido na esquina da rua de baixo, a água não escoa.")
                foto(pg, "09_relatar_ocorrencia")
                pg.click("main button[type=submit]")
                pg.wait_for_load_state()
                foto(pg, "10_minhas_ocorrencias")
                pg.goto(f"{app}/perfil")
                foto(pg, "11_perfil_lgpd")
                pg.goto(f"{app}/status.txt")
                foto(pg, "12_status_txt", inteira=False)

            with abrir(1280, 860) as (_, pg):
                entrar(pg, app, seed.EMAIL_AGENTE, seed.SENHA_AGENTE)
                pg.goto(f"{app}/agente")
                foto(pg, "13_painel_do_agente")

            with abrir(390, 800, escala=2, movel=True) as (_, pg):
                entrar(pg, app, seed.EMAIL_MORADOR, seed.SENHA_MORADOR)
                pg.goto(f"{app}/minha-area")
                foto(pg, "14_celular_minha_area")
                pg.goto(f"{app}/alertas")
                pg.locator("a[href^='/alertas/ALT-']").first.click()
                pg.wait_for_load_state()
                foto(pg, "15_celular_alerta")

        time.sleep(20)  # o pipeline busca as ocorrências do app a cada 15 s
        with abrir(1500, 1900) as (_, pg):
            painel(pg, dash, "20_painel_ao_vivo", fonte="Sensores ao vivo")
            painel(pg, dash, "21_painel_ao_vivo_alertas", fonte="Sensores ao vivo", aba="Alertas e ocorrências")
            painel(pg, dash, "22_painel_historico_verao")
            painel(pg, dash, "23_painel_temporal_24jan", periodo="Temporal de 24/01/2025")
            painel(pg, dash, "24_painel_alertas", aba="Alertas e ocorrências")
            painel(pg, dash, "25_painel_ia_antes_depois", aba="IA: antes × depois")
            painel(pg, dash, "26_painel_dados_monitoramento", aba="Dados e monitoramento")

        if not args.so_painel:
            evento.avancar_ate("2025-01-24T23:50:00Z")
            with abrir(1280, 860) as (_, pg):
                entrar(pg, app, seed.EMAIL_MORADOR, seed.SENHA_MORADOR)
                pg.goto(f"{app}/minha-area")
                foto(pg, "16_minha_area_normalizada")
    finally:
        encerrar_arvore(servicos)


if __name__ == "__main__":
    main()
