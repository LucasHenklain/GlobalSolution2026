"""Configuração comum dos testes: cada teste ganha um data lake e um banco temporários (nada toca os dados reais)."""

import pytest


@pytest.fixture(autouse=True)
def ambiente_isolado(tmp_path, monkeypatch):
    monkeypatch.setenv("VIGIA_AMBIENTE", "teste")
    monkeypatch.setenv("VIGIA_LAKE", str(tmp_path / "lake"))
    monkeypatch.setenv("VIGIA_DB", str(tmp_path / "var" / "vigia.db"))
    monkeypatch.setenv("VIGIA_MODELOS", str(tmp_path / "modelos"))
    # Porta fechada de propósito: teste nenhum fala com app ou broker de verdade.
    monkeypatch.setenv("VIGIA_APP_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("MQTT_HOST", "127.0.0.1")
    monkeypatch.setenv("MQTT_PORT", "9")
    yield
