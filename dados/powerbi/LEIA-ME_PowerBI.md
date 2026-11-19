# VigIA no Power BI — 20 minutos, sem Docker e sem Python

Objetivo: mostrar as medidas DAX funcionando sobre o **gold** do data lake e tirar **um print** para o PDF (Área 2, funções analíticas).
Os dados são os mesmos do painel Streamlit, recortados em 2024–2025 (período de teste da IA). Datas já em horário de Brasília.

## 1. Importar (5 min)

1. Power BI Desktop → **Obter dados** → **Parquet** → cole o caminho completo do arquivo (ex.: `C:\...\VigIA_kit_powerbi\fato_leitura.parquet`) → **Carregar**.
2. Repita para: `fato_evento.parquet`, `fato_alerta.parquet`, `fato_risco.parquet`, `dim_estacao.parquet`, `dim_data.parquet`.
3. Aba **Modelo**: confira (ou crie, arrastando) as relações, todas de um para muitos saindo das dimensões:
   - `dim_estacao[estacao_id]` → `estacao_id` de `fato_leitura`, `fato_evento`, `fato_alerta`, `fato_risco`
   - `dim_data[data]` → `data` de `fato_leitura`, `fato_evento`, `fato_alerta`, `fato_risco`
4. Clique na tabela `dim_data` → **Ferramentas da tabela** → **Marcar como tabela de datas** → coluna `data`.

## 2. Criar as medidas (5 min)

**Página Inicial → Nova medida**, uma por vez, colando do arquivo `medidas.dax`. As cinco primeiras bastam para o print:

- `Chuva Acumulada (mm)`
- `Nível Máximo (% da cota)`
- `Horas em Alerta`
- `Eventos de Transbordo`
- `Alertas Emitidos`

Se sobrar tempo: `Prob. Máxima da IA` e `Variação da Chuva (%)` (esta usa a `dim_data`).
As medidas de antecedência usam uma coluna calculada em `fato_evento` e são opcionais.

## 3. Montar a página (5 min)

- 5 **cartões**, um para cada medida.
- 2 **segmentações de dados** (filtros): `dim_estacao[nome]` e `dim_data[data]` (estilo "Entre").
- 1 **gráfico de linhas**: eixo `fato_leitura[medido_em]`, valores `Nível Máximo (% da cota)`, legenda `dim_estacao[nome]`.
- 1 **tabela**: `dim_estacao[nome]`, `Chuva Acumulada (mm)`, `Nível Máximo (% da cota)`, `Eventos de Transbordo`, `Alertas Emitidos`.

## 4. Conferir e tirar o print (5 min)

1. No filtro de data, escolha **24/01/2025 a 25/01/2025** (o temporal da demonstração), com todas as estações.
2. Compare os cartões com `valores_para_conferir.txt` (calculados em Python sobre os mesmos dados). Têm de bater.
3. Tire **dois prints**: a página inteira com os filtros aplicados, e a tela com a fórmula de uma medida aberta
   (clique na medida `Alertas Emitidos` para a barra de fórmulas aparecer).
4. Mande os prints no grupo com os nomes `40_powerbi_painel.png` e `41_powerbi_medida.png`.
   Se quiser, mande também o `.pbix`.

Se algum número não bater ou uma medida der erro, mande o print do erro: é informação útil, não escondam.
