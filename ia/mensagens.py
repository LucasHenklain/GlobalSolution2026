"""Textos dos alertas em linguagem simples. São modelos fixos (sem IA generativa em tempo de execução):

previsíveis, revisáveis pela Defesa Civil e iguais com ou sem internet. Cada nível tem título, mensagem,
orientações e uma versão SMS de até 160 caracteres sem acento (cabe em qualquer celular).
"""

from __future__ import annotations

import unicodedata

from comum.estacoes import Estacao

LIMITE_SMS = 160
TELEFONE_DEFESA_CIVIL = "199"

TITULOS = {
    "verde": "Situação normalizada no {nome}",
    "amarelo": "Atenção: chuva e nível em elevação no {nome}",
    "laranja": "Risco alto de enchente no {nome}",
    "vermelho": "PERIGO: enchente no {nome}",
}

MENSAGENS = {
    "verde": "O nível do córrego voltou ao normal em {bairro}. Obrigado por acompanhar. Continue atento aos próximos avisos.",
    "amarelo": "Está chovendo forte ou o córrego começou a subir em {bairro}. Ainda não há risco imediato, mas fique atento aos próximos avisos.",
    "laranja": "O córrego pode transbordar em até 1 hora em {bairro}. Prepare-se agora para sair de casa se for preciso.",
    "vermelho": "O córrego está transbordando ou vai transbordar a qualquer momento em {bairro}. Saia agora para um lugar alto e seguro.",
}

ORIENTACOES = {
    "verde": [
        "Volte para casa só quando a água baixar por completo.",
        "Lave e desinfete o que teve contato com a água da enchente.",
    ],
    "amarelo": [
        "Acompanhe os avisos do VigIA.",
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
        f"Emergência: ligue {TELEFONE_DEFESA_CIVIL} (Defesa Civil) ou 193 (Bombeiros).",
    ],
}

SMS = {
    "verde": "VigIA: situacao NORMALIZADA no {nome}. Volte so quando a agua baixar.",
    "amarelo": "VigIA ATENCAO: chuva forte e nivel subindo no {nome}. Fique atento aos proximos avisos.",
    "laranja": "VigIA RISCO ALTO: {nome} pode transbordar em ate 1h. Guarde documentos no alto e prepare-se para sair. Defesa Civil 199",
    "vermelho": "VigIA PERIGO: enchente no {nome}. SAIA AGORA para lugar alto. Nao atravesse agua. Defesa Civil 199",
}


def sem_acento(texto: str) -> str:
    """SMS com acento pode chegar truncado ou ilegível em aparelhos simples."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def explicar_motivos(linha: dict, prob: float | None, est: Estacao, origem_decisao: str, nivel: str) -> list[str]:
    """Explica o alerta com os próprios dados que o geraram — o morador e o agente veem 'por quê'."""
    if nivel == "verde":
        return ["o nível do córrego e a chuva voltaram a valores normais"]
    motivos = []
    if linha["chuva_1h"] >= 10:
        motivos.append(f"choveu {linha['chuva_1h']:.0f} mm na última hora")
    if linha["delta_nivel_30min"] >= 10:
        motivos.append(f"o nível do córrego subiu {linha['delta_nivel_30min']:.0f} cm em 30 minutos")
    if linha["nivel_pct_cota"] >= 50:
        motivos.append(f"o córrego está em {linha['nivel_pct_cota']:.0f}% da altura em que transborda")
    if linha["chuva_24h"] >= 40:
        motivos.append(f"o solo já está encharcado ({linha['chuva_24h']:.0f} mm em 24 horas)")
    if prob is not None and origem_decisao == "ia":
        motivos.append(f"a IA estima {prob * 100:.0f}% de chance de transbordo em até 1 hora")
    if origem_decisao == "regra_local" and linha["nivel_cm"] >= est.cota_alerta_cm:
        motivos.append(f"o nível passou da cota de alerta ({est.cota_alerta_cm:.0f} cm)")
    return motivos or ["chuva e nível acima do normal para o horário"]


def montar_textos(nivel: str, est: Estacao) -> dict:
    """Devolve título, mensagem, orientações e SMS já preenchidos para a estação."""
    nome_sms = sem_acento(est.nome.split(" (")[0])
    sms = SMS[nivel].format(nome=nome_sms)
    return {
        "titulo": TITULOS[nivel].format(nome=est.nome),
        "mensagem": MENSAGENS[nivel].format(bairro=est.bairro),
        "orientacoes": ORIENTACOES[nivel],
        "mensagem_sms": sms[:LIMITE_SMS],
    }
