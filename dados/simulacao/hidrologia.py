"""Simulação do nível dos córregos a partir da chuva REAL do INMET.

Por que simular: não existe série pública aberta de nível de córrego em janelas de 10 minutos para estes pontos.
A chuva horária é medida (INMET); o nível é produzido por um modelo chuva-vazão simples e conhecido
(dois reservatórios lineares em série), com ruídos que a IA NÃO enxerga, para a previsão não ficar trivial.
Tudo aqui é parâmetro de simulação declarado, não medição.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from comum.estacoes import Estacao

PASSOS_POR_HORA = 6  # janelas de 10 minutos
BASCULADA_MM = 0.25  # resolução do pluviômetro de báscula (igual ao firmware)


@dataclass(frozen=True)
class Bacia:
    """Parâmetros hidrológicos de um ponto. k1 e k2 são tempos de esvaziamento em janelas de 10 min."""

    k1: float
    k2: float
    nivel_base_cm: float
    transbordos_por_ano: float  # alvo de calibração do ganho (frequência plausível para córrego urbano)
    semente: int


# Tempos de resposta coerentes com o tamanho das bacias: Aricanduva e Pirajuçara (dezenas de km²) levam
# cerca de 1 a 1,5 h entre a chuva e o pico; o Ipiranga, menor, menos de 1 h; a várzea do Tietê, várias horas.
BACIAS = {
    "EST-ARI-01": Bacia(k1=3.0, k2=5.0, nivel_base_cm=35, transbordos_por_ano=5, semente=101),
    "EST-PIR-01": Bacia(k1=2.5, k2=4.5, nivel_base_cm=30, transbordos_por_ano=6, semente=202),
    "EST-PAN-01": Bacia(k1=8.0, k2=16.0, nivel_base_cm=70, transbordos_por_ano=3, semente=303),
    "EST-IPI-01": Bacia(k1=2.0, k2=3.5, nivel_base_cm=25, transbordos_por_ano=5, semente=404),
}


def desagregar_chuva_horaria(chuva_h: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Divide cada total horário em 6 janelas de 10 min, com pesos aleatórios (chuva de verão vem em pancadas)."""
    pesos = rng.gamma(shape=1.0, scale=1.0, size=(len(chuva_h), PASSOS_POR_HORA))
    pesos /= pesos.sum(axis=1, keepdims=True)
    return (pesos * chuva_h[:, None]).reshape(-1)


def _fator_por_dia(n_passos: int, desvio: float, rng: np.random.Generator) -> np.ndarray:
    """Um fator multiplicativo por dia (dia começando às 6h de Brasília, quando quase não há temporal em curso)."""
    passos_dia = 24 * PASSOS_POR_HORA
    deslocamento = 9 * PASSOS_POR_HORA  # 09:00 UTC = 06:00 em Brasília
    dia = (np.arange(n_passos) + passos_dia - deslocamento) // passos_dia
    fatores = rng.lognormal(mean=0.0, sigma=desvio, size=dia.max() + 1)
    return fatores[dia]


def resposta_da_bacia(chuva_efetiva: np.ndarray, bacia: Bacia) -> np.ndarray:
    """Chuva → escoamento: solo encharcado escoa mais; dois reservatórios em série dão o atraso e a recessão."""
    saida = np.zeros(len(chuva_efetiva))
    umidade_antecedente = 0.0  # "memória" de chuva dos últimos dias (meia-vida ~1 dia)
    s1 = s2 = 0.0
    for i, chuva in enumerate(chuva_efetiva):
        umidade_antecedente = umidade_antecedente * 0.995 + chuva
        saturacao = 1.0 - np.exp(-umidade_antecedente / 40.0)
        coef_escoamento = 0.30 + 0.60 * saturacao  # área urbana: 30% a 90% da chuva vira escoamento
        q1 = s1 / bacia.k1
        q2 = s2 / bacia.k2
        s1 += coef_escoamento * chuva - q1
        s2 += q1 - q2
        saida[i] = q2
    return saida


def calibrar_ganho(resposta: np.ndarray, est: Estacao, bacia: Bacia, anos: float) -> float:
    """Escolhe o ganho para que o número de dias com transbordo bata com a frequência-alvo da bacia."""
    passos_dia = 24 * PASSOS_POR_HORA
    n_dias = len(resposta) // passos_dia
    pico_diario = np.sort(resposta[: n_dias * passos_dia].reshape(n_dias, passos_dia).max(axis=1))[::-1]
    alvo = max(int(round(bacia.transbordos_por_ano * anos)), 1)
    return (est.cota_transbordo_cm - bacia.nivel_base_cm) / pico_diario[alvo - 1]


def simular_estacao(chuva_horaria: pd.Series, est: Estacao, bacia: Bacia | None = None) -> pd.DataFrame:
    """Gera as leituras de 10 min de uma estação (nível, chuva, bateria) a partir da chuva horária real.

    chuva_horaria: série indexada por hora (UTC), em mm; valores faltantes são tratados como zero.
    """
    bacia = bacia or BACIAS[est.estacao_id]
    rng = np.random.default_rng(bacia.semente)
    horas = chuva_horaria.fillna(0.0).to_numpy(dtype=float)
    n = len(horas) * PASSOS_POR_HORA

    # 1) Chuva no ponto (o que o pluviômetro da estação mede): varia em relação ao INMET, a alguns km dali.
    chuva_local = desagregar_chuva_horaria(horas, rng) * _fator_por_dia(n, 0.35, rng)
    chuva_medida = np.round(chuva_local / BASCULADA_MM) * BASCULADA_MM

    # 2) Chuva média na bacia a montante: difere do ponto e NÃO é observada (fonte real de incerteza).
    chuva_bacia = chuva_local * _fator_por_dia(n, 0.25, rng)

    # 3) Resposta do córrego e conversão em nível, com ganho calibrado pela frequência de transbordo.
    resposta = resposta_da_bacia(chuva_bacia, bacia) ** 0.85
    ganho = calibrar_ganho(resposta, est, bacia, anos=len(horas) / 8766)
    nivel = bacia.nivel_base_cm + ganho * resposta
    # Acima da cota a água se espalha pela várzea/rua: o nível sobe mais devagar.
    excesso = np.clip(nivel - est.cota_transbordo_cm, 0, None)
    nivel = np.where(excesso > 0, est.cota_transbordo_cm + 0.35 * excesso, nivel)

    # 4) Imperfeições do sensor: ruído do ultrassom, resolução de 0,5 cm, limite físico.
    nivel = nivel + rng.normal(0, 1.2, n)
    nivel = np.clip(np.round(nivel * 2) / 2, 0, est.altura_sensor_cm - 5)

    indice = pd.date_range(chuva_horaria.index[0], periods=n, freq="10min", tz="UTC")
    hora_local = (indice.hour + indice.minute / 60 - 3) % 24
    # Bateria com painel solar: cai à noite, recupera de dia.
    bateria = np.clip(82 + 14 * np.sin((hora_local - 9) / 24 * 2 * np.pi) + rng.normal(0, 1.5, n), 5, 100).round(0)

    leituras = pd.DataFrame(
        {
            "estacao_id": est.estacao_id,
            "medido_em": indice,
            "nivel_cm": nivel,
            "chuva_mm": chuva_medida,
            "bateria_pct": bateria,
        }
    )
    # 5) Falhas de comunicação: ~0,3% das leituras nunca chegam (o pipeline precisa lidar com buracos).
    return leituras[rng.random(n) > 0.003].reset_index(drop=True)
