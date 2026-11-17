# Avaliação da IA — previsão de transbordo em 60 min

Treino 2019–2022 · validação 2023 · **teste 2024–2025** (dados que o modelo nunca viu). Limiar de alerta escolhido na validação: **0.20**.

| Indicador | Antes: regra de limiar fixo | Depois: IA | Implantado: IA + regra |
|---|---:|---:|---:|
| Eventos de transbordo no teste | 38 | 38 | 38 |
| Eventos avisados com 30 min ou mais | 23.7 % | 78.9 % | 84.2 % |
| Eventos avisados antes (10 min ou mais) | 89.5 % | 97.4 % | 100.0 % |
| Antecedência mediana do alerta | 10.0 min | 40.0 min | 40.0 min |
| Antecedência média do alerta | 20.3 min | 40.5 min | 42.6 min |
| Alarmes falsos (total no período) | 61 | 41 | 78 |
| Alarmes falsos por estação por ano | 7.6 | 5.1 | 9.8 |
| Precisão (por janela de 10 min) | 0.226 | 0.566 | 0.302 |
| Recall (por janela de 10 min) | 0.35 | 0.582 | 0.646 |
| F1 | 0.275 | 0.574 | 0.411 |

Qualidade da probabilidade no teste: AUC-ROC 0.9748 · AUC-PR 0.5562 (237 janelas positivas em 420712).

Chuva: medição real do INMET. Nível do córrego: simulação declarada (dados/simulacao/hidrologia.py).
