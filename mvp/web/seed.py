"""Dados de demonstração. Uso (da raiz do repositório): python -m mvp.web.seed [--demo]

Sem opção: cria um morador e um agente de demonstração (pode rodar várias vezes, não duplica).
Com --demo: cria também uma situação de exemplo por estação e um alerta (telas preenchidas mesmo sem o pipeline).
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta

from comum.config import carregar_config
from comum.estacoes import Estacao, carregar_estacoes
from mvp.web import avisos, banco, seguranca
from mvp.web.modelos import para_iso

# Contas só para demonstração local (documentadas no README). O seed se recusa a rodar em produção.
EMAIL_MORADOR = "morador@exemplo.com"
SENHA_MORADOR = "Morador2026demo"  # noqa: S105
EMAIL_AGENTE = "agente@exemplo.com"
SENHA_AGENTE = "Agente2026demo"  # noqa: S105
TELEFONE_MORADOR = "11900001234"  # número fictício
ESTACAO_MORADOR = "EST-ARI-01"
ALERTA_EXEMPLO = "ALT-EXEMPLO-0001"

# Um cenário por estação, para aparecerem os quatro níveis de risco nas telas:
# (nível final como fração da cota de transbordo, pico de chuva em mm por 10 min, probabilidade, risco)
CENARIOS = {
    "EST-ARI-01": (0.78, 7.0, 0.71, "laranja"),
    "EST-PIR-01": (0.55, 3.0, 0.18, "amarelo"),
    "EST-PAN-01": (0.22, 0.0, 0.02, "verde"),
    "EST-IPI-01": (1.02, 9.5, 0.96, "vermelho"),
}


def criar_usuarios(con: sqlite3.Connection) -> list[str]:
    """Cria o morador e o agente se ainda não existem; devolve os e-mails criados agora."""
    contas = (
        ("Maria (demonstração)", EMAIL_MORADOR, SENHA_MORADOR, TELEFONE_MORADOR, ESTACAO_MORADOR, "morador"),
        ("Agente da Defesa Civil (demonstração)", EMAIL_AGENTE, SENHA_AGENTE, None, None, "agente"),
    )
    criados = []
    for nome, email, senha, telefone, estacao_id, papel in contas:
        if banco.usuario_por_email(con, email):
            continue
        cifrado = seguranca.cifrar_telefone(telefone) if telefone else None
        banco.criar_usuario(con, nome, email, seguranca.gerar_hash_senha(senha), cifrado, estacao_id, papel)
        criados.append(email)
    return criados


def _serie_exemplo(fim: datetime, nivel_inicial: float, nivel_final: float, chuva_pico: float) -> list[dict]:
    """36 pontos de 10 em 10 minutos: a chuva vem primeiro e o nível sobe cada vez mais rápido depois dela."""
    pontos = []
    for i in range(36):
        avanco = i / 35
        nivel = nivel_inicial + (nivel_final - nivel_inicial) * avanco**2
        chuva = chuva_pico * max(0.0, 1 - abs(avanco - 0.8) / 0.3)  # triângulo com pico perto do fim
        momento = fim - timedelta(minutes=10 * (35 - i))
        pontos.append({"t": para_iso(momento), "nivel_cm": round(nivel, 1), "chuva_mm": round(chuva, 1)})
    return pontos


def _situacao_exemplo(estacao: Estacao, agora: datetime) -> dict:
    fracao, chuva_pico, prob, risco = CENARIOS.get(estacao.estacao_id, (0.2, 0.0, 0.02, "verde"))
    serie = _serie_exemplo(agora, estacao.cota_transbordo_cm * 0.15, estacao.cota_transbordo_cm * fracao, chuva_pico)
    nivel = serie[-1]["nivel_cm"]
    return {
        "estacao_id": estacao.estacao_id,
        "atualizado_em": para_iso(agora),
        "nivel_cm": nivel,
        "nivel_pct_cota": round(nivel / estacao.cota_transbordo_cm * 100, 1),
        "chuva_1h": round(sum(p["chuva_mm"] for p in serie[-6:]), 1),
        "chuva_24h": round(sum(p["chuva_mm"] for p in serie), 1),
        "delta_nivel_30min": round(nivel - serie[-4]["nivel_cm"], 1),
        "prob_transbordo_60min": prob,
        "nivel_risco": risco,
        "estado_regra": estacao.estado_regra(nivel),
        "bateria_pct": 87,
        "origem": "exemplo",  # as telas mostram a faixa "dados de exemplo"
        "serie": serie,
    }


def criar_situacoes_exemplo(con: sqlite3.Connection) -> int:
    """Só preenche estação sem dado (ou com exemplo antigo): nunca passa por cima de dado vindo do pipeline."""
    agora = datetime.now(UTC).replace(second=0, microsecond=0)
    agora -= timedelta(minutes=agora.minute % 10)
    atuais = banco.listar_situacoes(con)
    novas = [
        _situacao_exemplo(estacao, agora)
        for estacao in carregar_estacoes().values()
        if estacao.estacao_id not in atuais or atuais[estacao.estacao_id]["origem"] == "exemplo"
    ]
    return banco.salvar_situacoes(con, novas)


def criar_alerta_exemplo(con: sqlite3.Connection) -> bool:
    """Um alerta laranja na área do morador de demonstração (gera também o SMS simulado dele)."""
    estacao = carregar_estacoes()[ESTACAO_MORADOR]
    situacao = banco.buscar_situacao(con, ESTACAO_MORADOR) or {}
    alerta = {
        "alerta_id": ALERTA_EXEMPLO,
        "estacao_id": ESTACAO_MORADOR,
        "emitido_em": banco.agora_iso(),
        "nivel_risco": "laranja",
        "prob": 0.71,
        "nivel_cm": situacao.get("nivel_cm"),
        "chuva_1h": situacao.get("chuva_1h"),
        "titulo": f"Risco alto de enchente no {estacao.nome}",
        "mensagem": f"O córrego pode transbordar em até 1 hora em {estacao.bairro}. "
        "Prepare-se agora para sair de casa se for preciso.",
        "mensagem_sms": "VigIA RISCO ALTO: Corrego Aricanduva pode transbordar em ate 1h. Guarde documentos no alto e "
        "prepare-se para sair. Defesa Civil 199",
        "motivo": [
            "choveu forte na última hora",
            "o nível do córrego subiu rápido nos últimos 30 minutos",
            "a IA estima 71% de chance de transbordo em até 1 hora",
        ],
        "orientacoes": [
            "Guarde documentos e remédios em um lugar alto ou numa sacola plástica.",
            "Tire da tomada os aparelhos que estão perto do chão.",
            "Avise vizinhos idosos, crianças e pessoas com deficiência.",
            "Combine com a família para onde ir se a água subir.",
        ],
        "origem_decisao": "ia",
    }
    novo, _ = avisos.receber_alerta(con, alerta)
    return novo


def main() -> None:
    argumentos = argparse.ArgumentParser(description="Cria os dados de demonstração do app web do VigIA.")
    argumentos.add_argument("--demo", action="store_true", help="cria também situações e um alerta de exemplo")
    opcoes = argumentos.parse_args()
    cfg = carregar_config()
    if cfg.ambiente == "prod":
        raise SystemExit("O seed cria contas com senha pública de demonstração: não rode em produção.")
    banco.criar_tabelas(cfg.db)
    con = banco.conectar(cfg.db)
    try:
        criados = criar_usuarios(con)
        print(f"Usuários de demonstração criados agora: {', '.join(criados) or 'nenhum (já existiam)'}")
        if opcoes.demo:
            print(f"Situações de exemplo gravadas: {criar_situacoes_exemplo(con)}")
            print(f"Alerta de exemplo criado agora: {'sim' if criar_alerta_exemplo(con) else 'não (já existia)'}")
    finally:
        con.close()
    print(f"Banco: {cfg.db}")


if __name__ == "__main__":
    main()
