"""Regras de qualidade do contrato de leitura (LEI-01 a LEI-07) aplicadas no silver."""

from datetime import UTC, datetime, timedelta

import pandas as pd

from dados.processamento.silver import validar_leituras

AGORA = datetime(2026, 11, 16, 18, 0, tzinfo=UTC)


def _leitura(**mudancas) -> dict:
    base = {
        "estacao_id": "EST-ARI-01",
        "medido_em": "2026-11-16T17:50:00Z",
        "nivel_cm": 120.0,
        "chuva_mm": 1.5,
        "bateria_pct": 80,
        "origem": "emulador",
        "recebido_em": "2026-11-16T17:50:02Z",
    }
    return {**base, **mudancas}


def _validar(*leituras):
    return validar_leituras(pd.DataFrame(list(leituras)), agora=AGORA)


def test_leitura_valida_passa():
    validas, rejeitadas = _validar(_leitura())
    assert len(validas) == 1 and len(rejeitadas) == 0


def test_estacao_fora_do_catalogo_vai_para_quarentena():
    validas, rejeitadas = _validar(_leitura(estacao_id="EST-XXX-99"))
    assert validas.empty
    assert rejeitadas.iloc[0]["motivo"].startswith("LEI-02")


def test_nivel_e_chuva_fora_da_faixa_sao_rejeitados():
    _, rejeitadas = _validar(_leitura(nivel_cm=900), _leitura(medido_em="2026-11-16T17:40:00Z", chuva_mm=-3))
    assert sorted(m[:6] for m in rejeitadas["motivo"]) == ["LEI-03", "LEI-04"]


def test_leitura_no_futuro_e_rejeitada():
    futuro = (AGORA + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _, rejeitadas = _validar(_leitura(medido_em=futuro))
    assert rejeitadas.iloc[0]["motivo"].startswith("LEI-05")


def test_campo_obrigatorio_ausente_e_rejeitado():
    _, rejeitadas = _validar(_leitura(nivel_cm=None))
    assert rejeitadas.iloc[0]["motivo"].startswith("LEI-01")


def test_duplicata_fica_a_recebida_por_ultimo():
    validas, _ = _validar(
        _leitura(nivel_cm=100, recebido_em="2026-11-16T17:50:02Z"),
        _leitura(nivel_cm=130, recebido_em="2026-11-16T17:50:09Z"),
    )
    assert len(validas) == 1 and validas.iloc[0]["nivel_cm"] == 130


def test_bateria_absurda_vira_nulo_sem_perder_a_leitura():
    validas, rejeitadas = _validar(_leitura(bateria_pct=250))
    assert len(validas) == 1 and rejeitadas.empty
    assert pd.isna(validas.iloc[0]["bateria_pct"])
