"""Log estruturado: uma linha JSON por evento no stdout, para o Docker e o monitoramento conseguirem filtrar."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime


class _FormatoJson(logging.Formatter):
    def format(self, registro: logging.LogRecord) -> str:
        evento = {
            "em": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "nivel": registro.levelname,
            "modulo": registro.name,
            "msg": registro.getMessage(),
        }
        # Campos extras passados com logger.info("...", extra={"dados": {...}})
        dados = getattr(registro, "dados", None)
        if dados:
            evento.update(dados)
        if registro.exc_info:
            evento["erro"] = self.formatException(registro.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def obter_logger(nome: str) -> logging.Logger:
    """Devolve um logger que escreve JSON; chamar várias vezes com o mesmo nome não duplica saída."""
    logger = logging.getLogger(nome)
    if not logger.handlers:
        # No Windows, saída redirecionada usa cp1252 e quebra os acentos: forçamos UTF-8.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        saida = logging.StreamHandler(sys.stdout)
        saida.setFormatter(_FormatoJson())
        logger.addHandler(saida)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
