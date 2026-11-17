"""Contadores simples em memória, expostos em /metrics no formato de texto do Prometheus."""

from __future__ import annotations

from threading import Lock

DESCRICOES = {
    "vigia_requisicoes_total": "Requisições HTTP atendidas",
    "vigia_respostas_erro_total": "Respostas com erro do servidor (5xx)",
    "vigia_logins_ok_total": "Logins com sucesso",
    "vigia_logins_falhos_total": "Tentativas de login recusadas",
    "vigia_cadastros_total": "Contas criadas",
    "vigia_situacoes_recebidas_total": "Situações de estação recebidas do pipeline",
    "vigia_alertas_recebidos_total": "Alertas novos recebidos do agente de alerta",
    "vigia_sms_enfileirados_total": "SMS simulados colocados na caixa de saída",
    "vigia_ocorrencias_criadas_total": "Ocorrências relatadas pelos moradores",
    "vigia_comandos_sirene_total": "Comandos manuais de sirene enviados pelo agente",
}


class Metricas:
    """Um contador por nome. Zera quando o app reinicia (suficiente para o monitoramento do MVP)."""

    def __init__(self) -> None:
        self._valores = dict.fromkeys(DESCRICOES, 0)
        self._trava = Lock()

    def contar(self, nome: str, quantidade: int = 1) -> None:
        with self._trava:
            self._valores[nome] += quantidade

    def valor(self, nome: str) -> int:
        return self._valores[nome]

    def texto(self) -> str:
        """Monta a saída que o Prometheus lê: HELP, TYPE e o valor de cada contador."""
        linhas = []
        for nome, valor in self._valores.items():
            linhas += [f"# HELP {nome} {DESCRICOES[nome]}", f"# TYPE {nome} counter", f"{nome} {valor}"]
        return "\n".join(linhas) + "\n"
