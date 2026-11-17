"""Abre o Edge pelo Playwright para capturar telas reais do protótipo (prints do PDF e cenas do vídeo)."""

from __future__ import annotations

import os
from contextlib import contextmanager

from playwright.sync_api import sync_playwright


def ambiente_limpo() -> dict:
    """O Edge herda variáveis do app desktop que o fazem sair sem renderizar; removemos as que atrapalham."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("CHROME_", "CLAUDE", "ELECTRON_"))}


@contextmanager
def abrir(largura: int = 1440, altura: int = 900, escala: float = 1.0, video_dir: str | None = None, movel: bool = False):
    """Devolve (contexto, página) de um Edge sem interface. Com video_dir, grava a navegação em vídeo."""
    with sync_playwright() as p:
        navegador = p.chromium.launch(channel="msedge", headless=True, env=ambiente_limpo())
        opcoes = {
            "viewport": {"width": largura, "height": altura},
            "device_scale_factor": escala,
            "locale": "pt-BR",
            "timezone_id": "America/Sao_Paulo",
            "is_mobile": movel,
            "has_touch": movel,
        }
        if video_dir:
            opcoes |= {"record_video_dir": video_dir, "record_video_size": {"width": largura, "height": altura}}
        contexto = navegador.new_context(**opcoes)
        pagina = contexto.new_page()
        try:
            yield contexto, pagina
        finally:
            contexto.close()
            navegador.close()
