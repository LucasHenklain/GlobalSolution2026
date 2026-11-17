"""Textos e formatos usados nas telas: rótulos de risco, orientações, datas em horário de Brasília."""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime, timedelta, timezone

BRASILIA = timezone(timedelta(hours=-3))  # o Brasil não tem horário de verão desde 2019
MINUTOS_DADO_VELHO = 30  # depois disso a tela avisa que a estação pode estar sem conexão

# Cada nível tem cor, ícone e texto: a informação nunca depende só da cor.
RISCOS = {
    "verde": {"rotulo": "Normal", "frase": "Sem risco de enchente agora."},
    "amarelo": {"rotulo": "Atenção", "frase": "Chuva forte ou córrego subindo. Fique atento."},
    "laranja": {"rotulo": "Risco alto", "frase": "O córrego pode transbordar em até 1 hora. Prepare-se."},
    "vermelho": {"rotulo": "Perigo", "frase": "Enchente agora ou a qualquer momento. Saia para um lugar alto."},
    "sem_dados": {"rotulo": "Sem leitura", "frase": "Ainda não recebemos dados desta estação."},
}

ORIENTACOES = {
    "verde": [
        "Siga sua rotina normalmente.",
        "Mantenha bueiros e calhas livres de lixo.",
        "Viu um bueiro entupido ou lixo no córrego? Relate uma ocorrência.",
    ],
    "amarelo": [
        "Acompanhe os próximos avisos do VigIA.",
        "Evite passar por ruas que costumam alagar.",
        "Veja se bueiros e calhas perto de casa estão livres; se não, relate no app.",
    ],
    "laranja": [
        "Guarde documentos e remédios em um lugar alto ou numa sacola plástica.",
        "Tire da tomada os aparelhos que estão perto do chão.",
        "Avise vizinhos idosos, crianças e pessoas com deficiência.",
        "Combine com a família para onde ir se a água subir.",
    ],
    "vermelho": [
        "Saia agora para um lugar alto. Não espere a água chegar.",
        "Não atravesse ruas alagadas, a pé ou de carro.",
        "Se der tempo, desligue a chave geral de energia.",
        "Emergência: ligue 199 (Defesa Civil) ou 193 (Bombeiros).",
    ],
    "sem_dados": ["Em caso de emergência, ligue 199 (Defesa Civil) ou 193 (Bombeiros)."],
}

TIPOS_OCORRENCIA = {
    "bueiro_entupido": "Bueiro entupido",
    "lixo_no_corrego": "Lixo no córrego",
    "ponto_de_alagamento": "Ponto de alagamento",
    "sirene_com_defeito": "Sirene com defeito",
    "outro": "Outro problema",
}

STATUS_OCORRENCIA = {"aberta": "Aberta", "em_atendimento": "Em atendimento", "resolvida": "Resolvida"}

ORIGENS_DECISAO = {
    "ia": "Previsão da inteligência artificial (chance de transbordo em 60 minutos)",
    "regra_local": "Regra da própria estação (nível passou da cota de alerta)",
}

FAIXAS_DEMONSTRACAO = {
    "replay": "Demonstração: reprodução de um temporal real (chuva medida pelo INMET)",
    "exemplo": "Demonstração: dados de exemplo criados para testar as telas (não são medições)",
}


def _ler_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def data_hora(iso: str | None) -> str:
    """'2026-11-16T18:00:00Z' vira '16/11/2026 15:00' (horário de Brasília)."""
    momento = _ler_iso(iso)
    return momento.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M") if momento else "—"


def hora_curta(iso: str | None) -> str:
    momento = _ler_iso(iso)
    return momento.astimezone(BRASILIA).strftime("%H:%M") if momento else ""


def minutos_desde(iso: str | None) -> int | None:
    momento = _ler_iso(iso)
    if momento is None:
        return None
    return max(0, int((datetime.now(UTC) - momento).total_seconds() // 60))


def ha_quanto(iso: str | None) -> str:
    """Tempo decorrido em linguagem simples: 'agora mesmo', 'há 5 min', 'há 2 h', 'há 3 dias'."""
    minutos = minutos_desde(iso)
    if minutos is None:
        return ""
    if minutos < 1:
        return "agora mesmo"
    if minutos < 60:
        return f"há {minutos} min"
    if minutos < 48 * 60:
        return f"há {minutos // 60} h"
    return f"há {minutos // (24 * 60)} dias"


def dado_velho(situacao: dict | None) -> bool:
    """True quando a última situação chegou há muito tempo (estação ou pipeline sem conexão)."""
    minutos = minutos_desde(situacao["recebido_em"]) if situacao else None
    return minutos is not None and minutos > MINUTOS_DADO_VELHO


def numero(valor: float | None, casas: int = 0) -> str:
    """Número com vírgula decimal, como se escreve no Brasil; traço quando não há valor."""
    if valor is None:
        return "—"
    return f"{valor:.{casas}f}".replace(".", ",")


def porcento(fracao: float | None) -> str:
    return "—" if fracao is None else f"{round(fracao * 100)}%"


def sem_acento(texto: str) -> str:
    """Para o /status.txt: texto puro que qualquer aparelho mostra certo."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def faixa_demonstracao(situacoes: list[dict | None]) -> str | None:
    """Texto da faixa de aviso quando algum dado da tela vem de replay ou do seed de exemplo."""
    origens = {s["origem"] for s in situacoes if s}
    for origem, texto in FAIXAS_DEMONSTRACAO.items():
        if origem in origens:
            return texto
    return None


def motivos_da_situacao(situacao: dict) -> list[str]:
    """Explica o risco com os próprios números da situação, quando não há alerta com a lista de motivos."""
    motivos = [f"O córrego está em {numero(situacao['nivel_pct_cota'])}% da altura em que transborda."]
    motivos.append(f"Choveu {numero(situacao['chuva_1h'], 1)} mm na última hora.")
    delta = situacao.get("delta_nivel_30min")
    if delta is not None and abs(delta) >= 1:
        verbo = "subiu" if delta > 0 else "baixou"
        motivos.append(f"O nível {verbo} {numero(abs(delta))} cm nos últimos 30 minutos.")
    if situacao.get("chuva_24h") is not None:
        motivos.append(f"Choveu {numero(situacao['chuva_24h'], 1)} mm nas últimas 24 horas.")
    return motivos


FILTROS = {
    "data_hora": data_hora,
    "hora_curta": hora_curta,
    "ha_quanto": ha_quanto,
    "numero": numero,
    "porcento": porcento,
}
