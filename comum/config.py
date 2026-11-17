"""Configuração única do VigIA: todo módulo lê as variáveis de ambiente daqui, nunca direto de os.environ."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent  # raiz do repositório

# Segredos que só servem para desenvolvimento: em produção o serviço se recusa a subir com eles.
_TOKEN_DEV = "dev-token-interno"  # noqa: S105 - valor público de desenvolvimento, recusado em prod


def _caminho(valor: str) -> Path:
    """Caminhos relativos são sempre relativos à raiz do repositório, não ao diretório atual."""
    p = Path(valor)
    return p if p.is_absolute() else RAIZ / p


@dataclass(frozen=True)
class Config:
    ambiente: str
    lake: Path
    db: Path
    modelos: Path  # onde ficam o modelo treinado e as métricas da IA
    secret_key: str
    chave_dados: str  # chave Fernet (base64) para cifrar o telefone; vazia = gerar e guardar em var/
    token_interno: str
    app_url: str
    mqtt_host: str
    mqtt_port: int
    mqtt_prefixo: str

    @property
    def referencia(self) -> Path:
        return RAIZ / "dados" / "referencia"


def carregar_config() -> Config:
    """Lê o ambiente a cada chamada (os testes trocam variáveis entre um caso e outro)."""
    ambiente = os.environ.get("VIGIA_AMBIENTE", "dev")
    cfg = Config(
        ambiente=ambiente,
        lake=_caminho(os.environ.get("VIGIA_LAKE", "dados/lake")),
        db=_caminho(os.environ.get("VIGIA_DB", "var/vigia.db")),
        modelos=_caminho(os.environ.get("VIGIA_MODELOS", "ia/modelos")),
        secret_key=os.environ.get("VIGIA_SECRET_KEY", ""),
        chave_dados=os.environ.get("VIGIA_CHAVE_DADOS", ""),
        token_interno=os.environ.get("VIGIA_TOKEN_INTERNO", _TOKEN_DEV),
        app_url=os.environ.get("VIGIA_APP_URL", "http://localhost:8000").rstrip("/"),
        mqtt_host=os.environ.get("MQTT_HOST", "localhost"),
        mqtt_port=int(os.environ.get("MQTT_PORT", "1883")),
        mqtt_prefixo=os.environ.get("MQTT_PREFIXO", "vigia").strip("/"),
    )
    if ambiente == "prod":
        # Em produção não existe segredo padrão: falhar cedo é mais seguro do que subir aberto.
        faltando = [
            n for n, v in (("VIGIA_SECRET_KEY", cfg.secret_key), ("VIGIA_CHAVE_DADOS", cfg.chave_dados)) if not v
        ]
        if cfg.token_interno == _TOKEN_DEV:
            faltando.append("VIGIA_TOKEN_INTERNO")
        if faltando:
            raise RuntimeError(f"Defina as variáveis de ambiente em produção: {', '.join(faltando)}")
    return cfg


def segredo_local(nome: str, gerador=lambda: secrets.token_urlsafe(48)) -> str:
    """Em dev/teste, gera um segredo na primeira execução e guarda ao lado do banco (fora do Git).

    Fica junto do banco de propósito: a chave que cifra os telefones precisa sobreviver junto com eles
    (no Docker, os dois moram no mesmo volume).
    """
    arquivo = carregar_config().db.parent / f"{nome}.key"
    if arquivo.exists():
        return arquivo.read_text(encoding="utf-8").strip()
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    valor = gerador()
    arquivo.write_text(valor, encoding="utf-8")
    return valor
