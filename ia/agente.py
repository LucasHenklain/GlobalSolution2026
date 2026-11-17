"""Agente de alerta do VigIA: transforma a probabilidade da IA e os dados do gold em DECISÕES.

Regras (documentadas no PDF, seção de IA):
  R1  VERMELHO  se nível ≥ cota de transbordo (regra)  OU  probabilidade ≥ limiar vermelho (IA)
  R2  LARANJA   se probabilidade ≥ limiar laranja (IA)  OU  nível ≥ cota de alerta (regra: rede de segurança)
  R3  AMARELO   se probabilidade ≥ limiar amarelo (IA)  OU  nível ≥ cota de atenção  OU  chuva em 1 h ≥ 15 mm
  R4  VERDE     nos demais casos
  R5  Sem modelo disponível, valem só as regras de nível (o sistema degrada, não para)
  R6  Emite alerta quando o risco SOBE de nível
  R7  Repete o alerta de laranja/vermelho a cada 60 min enquanto o risco durar (lembrete)
  R8  Não repete o mesmo nível antes de 60 min (evita cansar o morador com avisos iguais)
  R9  Avisa "situação normalizada" depois de 30 min seguidos em verde
  R10 Laranja e vermelho: SMS aos moradores da área + sirene (15 s e 60 s). Amarelo: só no app
"""

from __future__ import annotations

import pandas as pd

from comum.estacoes import Estacao
from ia import mensagens

ORDEM = {"verde": 0, "amarelo": 1, "laranja": 2, "vermelho": 3}
CHUVA_ATENCAO_1H_MM = 15.0
INTERVALO_LEMBRETE = pd.Timedelta(minutes=60)
JANELAS_PARA_NORMALIZAR = 3  # 30 min em verde
NOVA_SERIE = pd.Timedelta(hours=6)  # buraco maior que isso = outra série (zera a memória do agente)
SIRENE_SEGUNDOS = {"laranja": 15, "vermelho": 60}
SIGLA_NIVEL = {"verde": "NOR", "amarelo": "AMA", "laranja": "LAR", "vermelho": "VRM"}


def classificar_risco(linha: dict, prob: float | None, est: Estacao, limiares: dict | None) -> tuple[str, str]:
    """Aplica R1–R5 a uma janela. Devolve (nível de risco, origem da decisão: 'ia' ou 'regra_local')."""
    nivel = linha["nivel_cm"]
    tem_ia = prob is not None and limiares is not None
    if nivel >= est.cota_transbordo_cm:
        return "vermelho", "regra_local"
    if tem_ia and prob >= limiares["vermelho"]:
        return "vermelho", "ia"
    if tem_ia and prob >= limiares["laranja"]:
        return "laranja", "ia"
    if nivel >= est.cota_alerta_cm:
        return "laranja", "regra_local"
    if tem_ia and prob >= limiares["amarelo"]:
        return "amarelo", "ia"
    if nivel >= est.cota_atencao_cm or linha["chuva_1h"] >= CHUVA_ATENCAO_1H_MM:
        return "amarelo", "regra_local"
    return "verde", "regra_local"


def _montar_alerta(linha: dict, prob: float | None, nivel: str, origem: str, est: Estacao) -> dict:
    """Monta o alerta no formato do contrato da API interna (docs/contratos-tecnicos.md, seção 5)."""
    emitido_em = pd.Timestamp(linha["medido_em"])
    sigla = est.estacao_id.split("-")[1]
    return {
        # Identificador determinístico: reprocessar os mesmos dados não duplica alertas.
        "alerta_id": f"ALT-{sigla}-{emitido_em:%Y%m%d%H%M}-{SIGLA_NIVEL[nivel]}",
        "estacao_id": est.estacao_id,
        "emitido_em": emitido_em.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nivel_risco": nivel,
        "prob": round(float(prob), 3) if prob is not None else None,
        "nivel_cm": round(float(linha["nivel_cm"]), 1),
        "chuva_1h": round(float(linha["chuva_1h"]), 1),
        "motivo": mensagens.explicar_motivos(linha, prob, est, origem, nivel),
        "origem_decisao": origem,
        **mensagens.montar_textos(nivel, est),
    }


def gerar_alertas(serie: pd.DataFrame, est: Estacao, limiares: dict | None) -> tuple[pd.DataFrame, list[dict]]:
    """Percorre as janelas de UMA estação em ordem e aplica R6–R9.

    serie: linhas do gold (fato_leitura) com a coluna 'prob' (NaN quando não há modelo).
    Devolve (a série com 'nivel_risco' e 'origem_decisao', a lista de alertas emitidos).
    Função pura: a mesma lógica serve ao tempo real e à simulação retroativa do dashboard.
    """
    serie = serie.sort_values("medido_em")
    niveis, origens, alertas = [], [], []
    ativo, emitido_em, anterior, verdes_seguidos = "verde", None, None, 0
    for linha in serie.to_dict("records"):
        agora = linha["medido_em"]
        if anterior is not None and agora - anterior > NOVA_SERIE:
            ativo, emitido_em, verdes_seguidos = "verde", None, 0
        anterior = agora
        prob = None if pd.isna(linha.get("prob")) else float(linha["prob"])
        nivel, origem = classificar_risco(linha, prob, est, limiares)
        niveis.append(nivel)
        origens.append(origem)

        subiu = ORDEM[nivel] > ORDEM[ativo]  # R6
        lembrete = (  # R7 e R8
            nivel == ativo and ORDEM[nivel] >= ORDEM["laranja"] and agora - emitido_em >= INTERVALO_LEMBRETE
        )
        verdes_seguidos = verdes_seguidos + 1 if nivel == "verde" else 0
        normalizou = ativo != "verde" and verdes_seguidos >= JANELAS_PARA_NORMALIZAR  # R9
        if subiu or lembrete or normalizou:
            alertas.append(_montar_alerta(linha, prob, nivel, origem, est))
            ativo, emitido_em = nivel, agora
        elif ORDEM[nivel] < ORDEM[ativo] and nivel != "verde" and agora - emitido_em >= INTERVALO_LEMBRETE:
            # O risco caiu um degrau e ficou assim por 1 h: passa a valer o nível menor, sem novo aviso.
            ativo, emitido_em = nivel, agora
    return serie.assign(nivel_risco=niveis, origem_decisao=origens), alertas


def comando_sirene(alerta: dict) -> dict | None:
    """R10: laranja e vermelho acionam a sirene da estação (contrato MQTT 3.2)."""
    segundos = SIRENE_SEGUNDOS.get(alerta["nivel_risco"])
    if segundos is None:
        return None
    return {"acao": "ligar", "nivel": alerta["nivel_risco"], "segundos": segundos, "alerta_id": alerta["alerta_id"]}
