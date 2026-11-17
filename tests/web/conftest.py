"""Preparação dos testes do app web: cada teste roda com um banco SQLite novo em pasta temporária, sem rede."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

RAIZ = Path(__file__).resolve().parents[2]
for pasta in (str(RAIZ), str(Path(__file__).resolve().parent)):
    if pasta not in sys.path:  # permite `import mvp...` e `import ajudas_web` de qualquer diretório
        sys.path.insert(0, pasta)

TOKEN_INTERNO = "token-interno-de-teste"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """App novo apontando para um banco temporário (VIGIA_DB) e com segredos só de teste."""
    monkeypatch.setenv("VIGIA_DB", str(tmp_path / "vigia_teste.db"))
    monkeypatch.setenv("VIGIA_AMBIENTE", "teste")
    monkeypatch.setenv("VIGIA_SECRET_KEY", "chave-de-sessao-so-para-os-testes-0123456789")
    monkeypatch.setenv("VIGIA_CHAVE_DADOS", Fernet.generate_key().decode())
    monkeypatch.setenv("VIGIA_TOKEN_INTERNO", TOKEN_INTERNO)
    from mvp.web.app import criar_app

    return criar_app()


@pytest.fixture
def cliente(app):
    """Navegador de mentira: guarda cookies entre as requisições, como um navegador de verdade."""
    with TestClient(app) as navegador:  # o "with" reaproveita a mesma thread em todas as requisições (mais rápido)
        yield navegador


@pytest.fixture
def outro_cliente(app):
    """Um segundo navegador (outra pessoa) no mesmo app."""
    with TestClient(app) as navegador:
        yield navegador


@pytest.fixture
def interno():
    """Cabeçalho de autenticação da API interna."""
    return {"X-Token-Interno": TOKEN_INTERNO}


@pytest.fixture
def sirene_falsa(monkeypatch):
    """Dublê do MQTT: guarda os comandos em vez de falar com um broker."""
    from mvp.web import mqtt_saida

    enviados = []

    def publicar(cfg, estacao_id, comando):
        enviados.append((estacao_id, comando))
        return True

    monkeypatch.setattr(mqtt_saida, "publicar_sirene", publicar)
    return enviados
