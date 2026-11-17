"""Treina e AVALIA a IA do VigIA: previsão de transbordo nos próximos 60 minutos.

Uso:  python -m ia.treinar        (precisa do gold histórico: python -m dados.pipeline historico)

Saídas em ia/modelos/:
  modelo_transbordo.joblib   modelo + limiares de decisão
  metricas.json              números do "antes" (regra de limiar) e do "depois" (IA) no período de teste
  relatorio_avaliacao.md     os mesmos números em tabela, para o PDF
  avaliacao_antes_depois.png e importancia_variaveis.png
"""

from __future__ import annotations

import json
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score

from comum.log import obter_logger
from dados import camadas
from ia import avaliacao, dataset
from ia.modelo import ARQUIVO_MODELO, PASTA_MODELOS

log = obter_logger("ia.treinar")
LIMIAR_VERMELHO = 0.60  # "muito provável": usado para o nível vermelho antes de a água passar da cota


def treinar_modelo(treino: pd.DataFrame) -> HistGradientBoostingClassifier:
    """Gradient boosting de árvores (scikit-learn): lida bem com relações não lineares entre chuva, nível e ritmo de subida."""
    amostra = dataset.amostra_de_treino(treino)
    modelo = HistGradientBoostingClassifier(
        max_iter=300, learning_rate=0.06, max_leaf_nodes=15, l2_regularization=1.0, random_state=42
    )
    modelo.fit(dataset.preparar_variaveis(amostra), amostra["alvo"])
    return modelo


def escolher_limiar(validacao: pd.DataFrame, prob: pd.Series) -> tuple[float, list[dict]]:
    """Escolhe, na VALIDAÇÃO, o limiar mais sensível que não gera mais alarmes falsos do que a regra fixa.

    Assim a comparação é justa: a IA só pode ganhar em antecedência sem custar mais alarmes à toa.
    """
    teto = avaliacao.avaliar_politica(validacao, avaliacao.alerta_da_regra(validacao))["alarmes_falsos"]
    curva, escolhido = [], 0.5
    for limiar in np.round(np.arange(0.90, 0.04, -0.01), 2):
        m = avaliacao.avaliar_politica(validacao, prob >= limiar)
        curva.append({"limiar": float(limiar), **m})
        if m["alarmes_falsos"] <= teto:
            escolhido = float(
                limiar
            )  # a lista vai do limiar mais alto para o mais baixo: fica o menor que respeita o teto
    return escolhido, curva


def avaliar_no_teste(teste: pd.DataFrame, prob: pd.Series, limiar: float) -> dict:
    """Aplica a mesma régua às três políticas no período que o modelo nunca viu."""
    regra = avaliacao.alerta_da_regra(teste)
    resultado = {
        "antes_regra_limiar_fixo": avaliacao.avaliar_politica(teste, regra),
        "depois_ia": avaliacao.avaliar_politica(teste, prob >= limiar),
        # O que roda em produção: IA + a regra fixa como rede de segurança (a IA nunca avisa menos que a regra).
        "implantado_ia_mais_regra": avaliacao.avaliar_politica(teste, (prob >= limiar) | regra),
    }
    util = teste[~teste["ja_transbordando"]]
    resultado["qualidade_da_probabilidade"] = {
        "auc_roc": round(float(roc_auc_score(util["alvo"], prob[util.index])), 4),
        "auc_pr": round(float(average_precision_score(util["alvo"], prob[util.index])), 4),
        "janelas_avaliadas": int(len(util)),
        "janelas_positivas": int(util["alvo"].sum()),
    }
    por_estacao = {}
    for estacao_id, parte in teste.groupby("estacao_id"):
        por_estacao[estacao_id] = {
            "antes": avaliacao.avaliar_politica(parte, avaliacao.alerta_da_regra(parte)),
            "depois": avaliacao.avaliar_politica(parte, prob[parte.index] >= limiar),
        }
    resultado["por_estacao"] = por_estacao
    return resultado


def importancia_das_variaveis(modelo, validacao: pd.DataFrame) -> dict[str, float]:
    """Quanto a qualidade cai quando embaralhamos cada variável: explica 'no que a IA presta atenção'."""
    amostra = dataset.amostra_de_treino(validacao, semente=7)
    r = permutation_importance(
        modelo,
        dataset.preparar_variaveis(amostra),
        amostra["alvo"],
        scoring="average_precision",
        n_repeats=5,
        random_state=0,
    )
    return dict(
        sorted(zip(dataset.VARIAVEIS, r.importances_mean.round(4).tolist(), strict=True), key=lambda kv: -kv[1])
    )


def _tabela_md(metricas: dict) -> str:
    linhas = [
        ("Eventos de transbordo no teste", "eventos", ""),
        ("Eventos avisados com 30 min ou mais", "avisados_30min_pct", " %"),
        ("Eventos avisados antes (10 min ou mais)", "avisados_pct", " %"),
        ("Antecedência mediana do alerta", "antecedencia_mediana_min", " min"),
        ("Antecedência média do alerta", "antecedencia_media_min", " min"),
        ("Alarmes falsos (total no período)", "alarmes_falsos", ""),
        ("Alarmes falsos por estação por ano", "alarmes_falsos_por_estacao_ano", ""),
        ("Precisão (por janela de 10 min)", "precisao", ""),
        ("Recall (por janela de 10 min)", "recall", ""),
        ("F1", "f1", ""),
    ]
    a, d, i = metricas["antes_regra_limiar_fixo"], metricas["depois_ia"], metricas["implantado_ia_mais_regra"]
    texto = "| Indicador | Antes: regra de limiar fixo | Depois: IA | Implantado: IA + regra |\n|---|---:|---:|---:|\n"
    for rotulo, chave, unidade in linhas:
        texto += f"| {rotulo} | {a[chave]}{unidade} | {d[chave]}{unidade} | {i[chave]}{unidade} |\n"
    return texto


def _graficos(metricas: dict, importancia: dict) -> None:
    """Dois gráficos para o PDF. matplotlib só é necessário aqui; se faltar, o treino segue sem as imagens."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    a, d = metricas["antes_regra_limiar_fixo"], metricas["depois_ia"]
    paineis = [
        ("Eventos avisados com\n30 min ou mais (%)", "avisados_30min_pct"),
        ("Antecedência mediana\ndo alerta (min)", "antecedencia_mediana_min"),
        ("Alarmes falsos\npor estação por ano", "alarmes_falsos_por_estacao_ano"),
    ]
    fig, eixos = plt.subplots(1, 3, figsize=(11, 3.6))
    for eixo, (titulo, chave) in zip(eixos, paineis, strict=True):
        barras = eixo.bar(["Antes\n(regra fixa)", "Depois\n(IA)"], [a[chave], d[chave]], color=["#9aa5b1", "#0b6e99"])
        eixo.bar_label(barras, fmt="%g", fontweight="bold")
        eixo.set_title(titulo, fontsize=11)
        eixo.spines[["top", "right"]].set_visible(False)
    fig.suptitle("VigIA — previsão de transbordo: antes × depois (teste 2024–2025, dados nunca vistos)", fontsize=11)
    fig.tight_layout()
    fig.savefig(PASTA_MODELOS / "avaliacao_antes_depois.png", dpi=150)
    plt.close(fig)

    fig, eixo = plt.subplots(figsize=(7, 3.6))
    nomes, valores = list(importancia)[::-1], list(importancia.values())[::-1]
    eixo.barh(nomes, valores, color="#0b6e99")
    eixo.set_title("No que a IA presta atenção (importância por permutação)", fontsize=11)
    eixo.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(PASTA_MODELOS / "importancia_variaveis.png", dpi=150)
    plt.close(fig)


def main() -> dict:
    inicio = time.time()
    fato = dataset.carregar_historico()
    treino, validacao, teste = dataset.separar_por_tempo(fato)
    modelo = treinar_modelo(treino)

    prob_validacao = pd.Series(modelo.predict_proba(dataset.preparar_variaveis(validacao))[:, 1], index=validacao.index)
    limiar, curva = escolher_limiar(validacao, prob_validacao)
    prob_teste = pd.Series(modelo.predict_proba(dataset.preparar_variaveis(teste))[:, 1], index=teste.index)
    metricas = avaliar_no_teste(teste, prob_teste, limiar)
    importancia = importancia_das_variaveis(modelo, validacao)

    limiares = {"amarelo": round(limiar / 3, 3), "laranja": limiar, "vermelho": max(LIMIAR_VERMELHO, limiar)}
    PASTA_MODELOS.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "modelo": modelo,
            "variaveis": dataset.VARIAVEIS,
            "limiares": limiares,
            "treinado_em": camadas.agora_iso(),
            "sklearn": sklearn.__version__,
        },
        ARQUIVO_MODELO,
    )
    relatorio = {
        "treinado_em": camadas.agora_iso(),
        "algoritmo": "HistGradientBoostingClassifier (scikit-learn)",
        "alvo": "transbordo nos próximos 60 minutos",
        "dados": {
            "fonte": "gold/fato_leitura (chuva real INMET A701 e A771; nível simulado)",
            "treino": "2019-2022",
            "validacao": "2023 (escolha do limiar)",
            "teste": "2024-2025 (números reportados)",
            "linhas_treino_amostradas": int(len(dataset.amostra_de_treino(treino))),
            "positivos_treino": int(treino["alvo"].sum()),
        },
        "limiares": limiares,
        "teste": metricas,
        "importancia_variaveis": importancia,
        "curva_validacao": curva,
        "segundos": round(time.time() - inicio, 1),
    }
    (PASTA_MODELOS / "metricas.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    q = metricas["qualidade_da_probabilidade"]
    (PASTA_MODELOS / "relatorio_avaliacao.md").write_text(
        "# Avaliação da IA — previsão de transbordo em 60 min\n\n"
        f"Treino 2019–2022 · validação 2023 · **teste 2024–2025** (dados que o modelo nunca viu). "
        f"Limiar de alerta escolhido na validação: **{limiar:.2f}**.\n\n"
        + _tabela_md(metricas)
        + f"\nQualidade da probabilidade no teste: AUC-ROC {q['auc_roc']} · AUC-PR {q['auc_pr']} "
        f"({q['janelas_positivas']} janelas positivas em {q['janelas_avaliadas']}).\n\n"
        "Chuva: medição real do INMET. Nível do córrego: simulação declarada (dados/simulacao/hidrologia.py).\n",
        encoding="utf-8",
    )
    _graficos(metricas, importancia)
    log.info("modelo treinado", extra={"dados": {"limiar": limiar, "segundos": relatorio["segundos"]}})
    print(_tabela_md(metricas))
    print("limiares:", limiares, "| importância:", importancia)
    return relatorio


if __name__ == "__main__":
    main()
