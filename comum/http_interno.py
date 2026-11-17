"""Cliente HTTP reaproveitado para falar com a API interna do app (pipeline e IA usam o mesmo)."""

from __future__ import annotations

import httpx

from comum.config import carregar_config

_cliente: httpx.Client | None = None
_chave: tuple[str, str] | None = None


def cliente_do_app() -> httpx.Client:
    """Devolve sempre o mesmo cliente: criar um por ciclo custava mais de 1 s (cada cliente monta seu contexto TLS)."""
    global _cliente, _chave
    cfg = carregar_config()
    chave = (cfg.app_url, cfg.token_interno)
    if _cliente is None or chave != _chave:
        if _cliente is not None:
            _cliente.close()
        # trust_env=False: chamada interna nunca deve passar por proxy corporativo configurado na máquina.
        _cliente = httpx.Client(
            base_url=cfg.app_url, headers={"X-Token-Interno": cfg.token_interno}, timeout=5, trust_env=False
        )
        _chave = chave
    return _cliente
