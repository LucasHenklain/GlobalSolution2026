# ruff: noqa: S603, E501
"""Grava as cenas do vídeo pitch com o protótipo REAL rodando (nada de montagem de tela).

Uso (a partir da raiz):  python entrega/video/gravar_cenas.py [--lake PASTA] [--db ARQUIVO] [--so c05,c06a]

O script sobe os serviços (devops.demo, portas 8031/8531) sobre uma CÓPIA do data lake, reproduz o temporal de
24/01/2025 janela a janela (classe Reprodutor das evidências) e, a cada passo, navega no app e no painel com o
Edge (Playwright), salvando os quadros de cada cena. Cada cena vira entrega/video/cenas/<nome>.mp4.

Os quadros são prints sucessivos da página real (rolagem lenta), e não o gravador de vídeo do navegador:
assim o texto fica nítido em 1080p.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ))
CENAS = AQUI / "cenas"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
PORTA_APP, PORTA_PAINEL = 8031, 8531
APP, PAINEL = f"http://127.0.0.1:{PORTA_APP}", f"http://127.0.0.1:{PORTA_PAINEL}"
FPS_ROLAGEM = 15


class Clipe:
    """Junta prints da página com a duração de cada um e, no fim, monta o MP4 da cena."""

    def __init__(self, pagina, nome: str) -> None:
        self.pagina, self.nome = pagina, nome
        self.pasta = CENAS / "_quadros" / nome
        shutil.rmtree(self.pasta, ignore_errors=True)
        self.pasta.mkdir(parents=True)
        self.itens: list[tuple[Path, float]] = []

    def parar(self, segundos: float) -> None:
        """Um print que fica na tela por `segundos`."""
        arquivo = self.pasta / f"q_{len(self.itens) + 1:04d}.jpg"
        self.pagina.screenshot(path=str(arquivo), type="jpeg", quality=93)
        self.itens.append((arquivo, segundos))

    def rolar(self, pixels: float, segundos: float) -> None:
        """Rolagem lenta: um print a cada pequeno passo da roda do mouse."""
        passos = max(int(segundos * FPS_ROLAGEM), 1)
        for _ in range(passos):
            self.pagina.mouse.wheel(0, pixels / passos)
            self.pagina.wait_for_timeout(40)
            self.parar(1 / FPS_ROLAGEM)

    def salvar(self) -> Path:
        lista = self.pasta / "lista.txt"
        linhas = []
        for arquivo, duracao in self.itens:
            linhas += [f"file '{arquivo.as_posix()}'", f"duration {duracao:.4f}"]
        linhas.append(f"file '{self.itens[-1][0].as_posix()}'")  # o concat exige repetir o último quadro
        lista.write_text("\n".join(linhas), encoding="utf-8")
        saida = CENAS / f"{self.nome}.mp4"
        subprocess.run(
            [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(lista), "-vf", "fps=30,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "17", str(saida)],
            check=True, capture_output=True,
        )  # fmt: skip
        total = sum(d for _, d in self.itens)
        print(f"cena {self.nome}: {len(self.itens)} quadros, {total:.1f} s")
        return saida


def esperar_painel(pagina) -> None:
    pagina.get_by_text("Painel da Defesa Civil").first.wait_for(timeout=120000)
    pagina.wait_for_timeout(6000)
    pagina.mouse.move(1000, 500)  # a rolagem do Streamlit acontece dentro da área principal


def gravar(args) -> None:
    from docs.ferramentas.capturar_evidencias import Reprodutor, encerrar_arvore, entrar
    from docs.ferramentas.navegador import abrir
    from mvp.web import seed

    so = set(args.so.split(",")) if args.so else None

    def quero(nome: str) -> bool:
        return so is None or nome in so

    ambiente = {**os.environ, "PYTHONUTF8": "1", "VIGIA_LAKE": args.lake, "VIGIA_DB": args.db}
    os.environ.update({"VIGIA_LAKE": args.lake, "VIGIA_DB": args.db})  # o Reprodutor grava na mesma cópia
    servicos = subprocess.Popen(
        [sys.executable, "-m", "devops.demo", "--sem-replay", "--porta-app", str(PORTA_APP), "--porta-painel", str(PORTA_PAINEL)],
        cwd=RAIZ, env=ambiente,
    )  # fmt: skip
    try:
        import httpx

        for _ in range(240):
            try:
                if httpx.get(f"{APP}/health", timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(1)
        time.sleep(15)
        evento = Reprodutor(APP)
        tela_app = {"largura": 1280, "altura": 720, "escala": 1.5}  # 1920x1080 com a interface maior e nítida

        evento.avancar_ate("2025-01-24T18:00:00Z", espera_s=180)
        if quero("c01"):
            with abrir(**tela_app) as (_, pg):
                pg.goto(APP)
                c = Clipe(pg, "c01_inicio_seco")
                c.parar(5)
                c.rolar(430, 12)
                c.parar(7)
                c.salvar()

        evento.avancar_ate("2025-01-24T19:20:00Z", espera_s=180)
        if quero("c04a") or quero("c04b"):
            with abrir(**tela_app) as (_, pg):
                entrar(pg, APP, seed.EMAIL_MORADOR, seed.SENHA_MORADOR)
                pg.goto(f"{APP}/minha-area")
                c = Clipe(pg, "c04a_minha_area_ia")
                c.parar(9)
                c.rolar(520, 5)
                c.parar(4.5)
                c.salvar()
                pg.goto(f"{APP}/alertas")
                pg.locator("a[href^='/alertas/ALT-']").first.click()
                pg.wait_for_load_state()
                c = Clipe(pg, "c04b_alerta_detalhe")
                c.parar(3)
                c.rolar(520, 4.5)
                c.parar(3)
                c.salvar()

        evento.avancar_ate("2025-01-24T20:30:00Z", espera_s=180)
        with abrir(**tela_app) as (_, pg):
            entrar(pg, APP, seed.EMAIL_MORADOR, seed.SENHA_MORADOR)
            if quero("c04c"):
                pg.goto(f"{APP}/minha-area")
                c = Clipe(pg, "c04c_transbordo")
                c.parar(3)
                c.rolar(520, 3.5)
                c.parar(2)
                c.salvar()
            if quero("c06b"):
                pg.goto(f"{APP}/ocorrencias/nova")
                pg.select_option("select[name=tipo]", "bueiro_entupido")
                pg.fill("textarea[name=descricao]", "Bueiro entupido na esquina da rua de baixo, a água não escoa.")
                c = Clipe(pg, "c06b_ocorrencia")
                c.parar(1.8)
                pg.click("main button[type=submit]")
                pg.wait_for_load_state()
                c.parar(1.8)
                c.salvar()
        if quero("c08"):
            with abrir(**tela_app) as (_, pg):
                pg.goto(APP)
                c = Clipe(pg, "c08_inicio_temporal")
                c.parar(3)
                c.rolar(430, 8)
                c.parar(5)
                c.salvar()
        if quero("c06c"):
            with abrir(**tela_app) as (_, pg):
                entrar(pg, APP, seed.EMAIL_AGENTE, seed.SENHA_AGENTE)
                pg.goto(f"{APP}/agente")
                c = Clipe(pg, "c06c_agente")
                c.parar(1.5)
                c.rolar(900, 2.5)
                c.parar(1)
                c.salvar()
        if quero("c07a"):
            with abrir(390, 844, escala=2, movel=True) as (_, pg):
                entrar(pg, APP, seed.EMAIL_MORADOR, seed.SENHA_MORADOR)
                pg.goto(f"{APP}/minha-area")
                c = Clipe(pg, "c07a_celular")
                c.parar(3.5)
                c.rolar(900, 7)
                pg.goto(f"{APP}/alertas")
                pg.locator("a[href^='/alertas/ALT-']").first.click()
                pg.wait_for_load_state()
                c.parar(2.5)
                c.rolar(700, 6)
                c.parar(1.5)
                c.salvar()
        if quero("c07b"):
            with abrir(960, 540, escala=2) as (_, pg):
                pg.goto(f"{APP}/status.txt")
                c = Clipe(pg, "c07b_status_txt")
                c.parar(7.5)
                c.salvar()

        tela_painel = {"largura": 1440, "altura": 810, "escala": 4 / 3}
        if quero("c06a"):
            time.sleep(20)  # o pipeline busca as ocorrências do app a cada 15 s
            with abrir(**tela_painel) as (_, pg):
                pg.goto(PAINEL)
                esperar_painel(pg)
                pg.get_by_text("Sensores ao vivo", exact=True).click()
                pg.wait_for_timeout(7000)
                c = Clipe(pg, "c06a_painel_filtros")
                c.parar(2)
                pg.get_by_text("Histórico (2019–2025)", exact=True).click()
                pg.wait_for_timeout(7000)
                c.parar(1.5)
                pg.get_by_test_id("stSelectbox").first.click()
                pg.wait_for_timeout(600)
                c.parar(0.8)
                pg.get_by_role("option", name="Temporal de 24/01/2025").click()
                pg.wait_for_timeout(7000)
                pg.mouse.move(1000, 500)
                c.parar(1.7)
                c.rolar(360, 2)
                c.parar(1)
                c.salvar()
        if quero("c05"):
            with abrir(**tela_painel) as (_, pg):
                pg.goto(PAINEL)
                esperar_painel(pg)
                pg.get_by_role("tab", name="IA: antes × depois").click()
                pg.wait_for_timeout(6000)
                pg.mouse.move(1000, 500)
                c = Clipe(pg, "c05_painel_ia")
                c.parar(7)
                c.rolar(260, 4)
                c.parar(6)
                c.salvar()
    finally:
        encerrar_arvore(servicos)


def quadros_do_wokwi() -> None:
    """Monta o clipe da simulação real do Wokwi a partir dos quadros de gravar_wokwi.py (5 quadros por segundo)."""
    pasta = CENAS / "wokwi_alerta"
    if not (pasta / "q_0001.png").exists():
        print("sem quadros do Wokwi: rode entrega/video/gravar_wokwi.py --distancia 150")
        return
    subprocess.run(
        [FFMPEG, "-y", "-framerate", "5", "-i", str(pasta / "q_%04d.png"), "-vf", "fps=30,format=yuv420p",
         "-c:v", "libx264", "-preset", "medium", "-crf", "17", str(CENAS / "wokwi_alerta.mp4")],
        check=True, capture_output=True,
    )  # fmt: skip
    print("cena wokwi_alerta montada")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lake", required=True, help="CÓPIA do data lake (nunca o lake do repositório)")
    ap.add_argument("--db", required=True, help="banco SQLite temporário do app")
    ap.add_argument("--so", default="", help="lista de cenas separadas por vírgula (ex.: c05,c06a); o temporal é reproduzido de novo")
    ap.add_argument("--so-wokwi", action="store_true")
    argumentos = ap.parse_args()
    CENAS.mkdir(exist_ok=True)
    quadros_do_wokwi()
    if not argumentos.so_wokwi:
        gravar(argumentos)
