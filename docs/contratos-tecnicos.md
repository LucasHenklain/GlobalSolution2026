# Contratos técnicos entre os módulos do VigIA

Fonte única das interfaces. Quem implementa um módulo segue este arquivo; mudança aqui exige ajustar os dois lados.

## 1. Convenções gerais

- Python 3.13. Código, comentários, nomes de variáveis e mensagens em **português** (sem acento em identificadores).
- Executa-se sempre a partir da **raiz do repositório**; os diretórios `comum`, `ia`, `dados`, `mvp`, `devops` são pacotes Python
  (com `__init__.py`). Ex.: `python -m mvp.iot.emulador`, `uvicorn mvp.web.app:app`.
- Datas/horas sempre em **UTC**, ISO 8601 com sufixo `Z` (`2026-11-16T18:00:00Z`). Exibição ao usuário em horário de Brasília (UTC−3).
- Configuração só por variável de ambiente, lida em `comum/config.py` (já existe; não duplicar leitura de env).
- Log: `comum/log.py` → `obter_logger(nome)` (JSON por linha no stdout).
- Dependências permitidas: as de `requirements.txt` (já existe). Não adicionar bibliotecas sem necessidade real.
- Estilo: `ruff` (configurado no `pyproject.toml`, linha de 120). Funções curtas, docstring de uma linha dizendo o porquê,
  comentário só onde a lógica não é óbvia. A equipe precisa conseguir explicar cada arquivo.
- Testes: `pytest` em `tests/<area>/`. Não dependem de rede nem de broker externo (usar dublês).

## 2. Catálogo de estações — `dados/referencia/estacoes.csv`

Lido por `comum.estacoes.carregar_estacoes()` → `dict[str, Estacao]`.

| coluna | exemplo | significado |
|---|---|---|
| estacao_id | EST-ARI-01 | identificador (regex `^EST-[A-Z]{3}-\d{2}$`) |
| nome | Córrego Aricanduva | nome do ponto |
| bairro | Vila Aricanduva | bairro/área atendida |
| zona | Leste | zona da cidade |
| inmet | A701 | estação INMET de onde vem a chuva real do histórico |
| altura_sensor_cm | 400 | altura do sensor ultrassônico acima do leito |
| cota_atencao_cm | 150 | nível de atenção |
| cota_alerta_cm | 220 | nível de alerta (regra local da estação aciona a sirene) |
| cota_transbordo_cm | 280 | nível em que o córrego transborda |
| moradores_area | 1840 | moradores na área de influência (**simulado**) |
| lat, lon | -23.56, -46.51 | posição aproximada |

Estações: `EST-ARI-01` (Aricanduva), `EST-PIR-01` (Pirajuçara), `EST-PAN-01` (Jardim Pantanal), `EST-IPI-01` (Ipiranga).

## 3. MQTT

Broker: `MQTT_HOST`:`MQTT_PORT` (padrão `localhost:1883`; no compose, serviço `mosquitto`). Prefixo de tópico: `MQTT_PREFIXO` (padrão `vigia`).

### 3.1 Leitura — `vigia/sensores/<estacao_id>/leitura` (QoS 1)

```json
{"estacao_id": "EST-ARI-01", "medido_em": "2026-11-16T18:00:00Z", "nivel_cm": 142.5, "chuva_mm": 1.2,
 "bateria_pct": 87, "seq": 123, "fw": "1.0.0", "origem": "emulador"}
```

| campo | tipo | regra |
|---|---|---|
| estacao_id | string | obrigatório; precisa existir no catálogo e ser igual ao do tópico |
| medido_em | string ISO UTC | obrigatório; não pode estar mais de 5 min no futuro |
| nivel_cm | número | obrigatório; 0 ≤ nivel ≤ altura_sensor_cm. Nível da água acima do leito (= altura do sensor − distância medida pelo ultrassom) |
| chuva_mm | número | obrigatório; 0 ≤ chuva ≤ 60. Chuva acumulada **desde a leitura anterior** (pulsos do pluviômetro × 0,25 mm) |
| bateria_pct | número | opcional; 0–100 |
| seq | inteiro | opcional; contador da estação |
| fw | string | opcional |
| origem | string | opcional; `wokwi`, `emulador` ou `replay` |

Chaves desconhecidas são descartadas pelo gateway (e contadas no log). Leitura inválida vai para a quarentena com o motivo.

### 3.2 Comando da sirene — `vigia/atuadores/<estacao_id>/sirene` (QoS 1)

```json
{"acao": "ligar", "nivel": "vermelho", "segundos": 30, "alerta_id": "ALT-20261116-0007"}
```
`acao`: `ligar` | `desligar`. `nivel`: `amarelo` | `laranja` | `vermelho`. A estação responde em
`vigia/atuadores/<estacao_id>/sirene/estado` com `{"sirene": "ligada|desligada", "motivo": "comando|regra_local", "em": "...Z"}`.

### 3.3 Presença — `vigia/sensores/<estacao_id>/status` (retido; LWT) → `online` | `offline`.

## 4. Data lake — `VIGIA_LAKE` (padrão `dados/lake`)

```
landing/sensores/AAAAMMDD/leituras_AAAAMMDDTHHMMSSZ.jsonl      micro-lotes do gateway (1 leitura por linha)
landing/quarentena_gateway/AAAAMMDD/*.jsonl                    rejeitadas na porta: {"motivo": "...", "bruto": {...}}
bronze/  silver/  gold/  quarentena/                           camadas (Parquet), geridas por dados/processamento
```

### Gold (lido pelo dashboard e pela IA)

`gold/fato_leitura/origem=<historico|sensor>/*.parquet` — uma linha por estação × janela de 10 min:

| coluna | tipo | significado |
|---|---|---|
| estacao_id | str | |
| medido_em | timestamp UTC | início da janela de 10 min |
| nivel_cm | float | último nível da janela |
| chuva_mm | float | chuva somada na janela |
| bateria_pct | float | |
| nivel_pct_cota | float | nivel_cm / cota_transbordo_cm × 100 |
| chuva_30min, chuva_1h, chuva_3h, chuva_24h, chuva_72h | float | acumulados móveis (mm) |
| delta_nivel_10min, delta_nivel_30min | float | variação do nível (cm) |
| estado_regra | str | `normal` / `atencao` / `alerta` / `transbordo` pela regra de limiar fixo |

`gold/fato_risco/origem=<...>/*.parquet` — saída da IA: `estacao_id, medido_em, prob_transbordo_60min, nivel_risco (verde|amarelo|laranja|vermelho)`.

`gold/fato_alerta.parquet` — alertas emitidos pelo agente: `alerta_id, estacao_id, emitido_em, nivel_risco, prob, nivel_cm, chuva_1h, motivo, mensagem_sms, origem_decisao (ia|regra_local)`.

`gold/fato_ocorrencia.parquet` — ocorrências relatadas no app: `ocorrencia_id, estacao_id, tipo, status, criada_em, encerrada_em`.

`gold/dim_estacao.parquet` — o catálogo.

## 5. API interna do app web (FastAPI) — autenticação por cabeçalho `X-Token-Interno: <VIGIA_TOKEN_INTERNO>`

| método e rota | corpo / resposta |
|---|---|
| `POST /api/interno/situacao` | lista de situações por estação (abaixo). Substitui a situação atual. Resposta `{"atualizadas": n}` |
| `POST /api/interno/alertas` | um alerta (abaixo). Idempotente por `alerta_id`. Resposta `{"alerta_id": "...", "novo": true, "sms_enfileirados": n}` |
| `GET /api/interno/ocorrencias?desde=<ISO>` | lista de ocorrências criadas/alteradas desde a data (sem dados pessoais) |
| `GET /health` (público) | `{"status": "ok", "banco": "ok", "ultima_situacao_em": "...Z"}` |
| `GET /metrics` (público) | texto no formato Prometheus (contadores simples) |

Situação:
```json
{"estacao_id": "EST-ARI-01", "atualizado_em": "2026-11-16T18:00:00Z", "nivel_cm": 142.5, "nivel_pct_cota": 50.9,
 "chuva_1h": 12.4, "chuva_24h": 30.2, "delta_nivel_30min": 18.0, "prob_transbordo_60min": 0.07,
 "nivel_risco": "amarelo", "estado_regra": "normal", "bateria_pct": 87,
 "serie": [{"t": "2026-11-16T15:00:00Z", "nivel_cm": 60.0, "chuva_mm": 0.0}]}
```
`serie`: até 36 pontos (últimas 6 h em janelas de 10 min), do mais antigo para o mais novo.

Alerta:
```json
{"alerta_id": "ALT-20261116-0007", "estacao_id": "EST-ARI-01", "emitido_em": "2026-11-16T18:00:00Z",
 "nivel_risco": "laranja", "prob": 0.71, "nivel_cm": 201.0, "chuva_1h": 34.2,
 "titulo": "Risco alto de enchente no Córrego Aricanduva",
 "mensagem": "texto completo em linguagem simples",
 "mensagem_sms": "até 160 caracteres",
 "motivo": ["choveu 34 mm na última hora", "o nível subiu 40 cm em 30 minutos"],
 "orientacoes": ["Guarde documentos e remédios em lugar alto", "..."],
 "origem_decisao": "ia"}
```

Ocorrência (resposta do GET):
```json
{"ocorrencia_id": 12, "estacao_id": "EST-ARI-01", "tipo": "bueiro_entupido", "status": "aberta",
 "descricao": "texto", "criada_em": "...Z", "atualizada_em": "...Z", "encerrada_em": null}
```
`tipo`: `bueiro_entupido` | `lixo_no_corrego` | `ponto_de_alagamento` | `sirene_com_defeito` | `outro`.
`status`: `aberta` | `em_atendimento` | `resolvida`.

## 6. Variáveis de ambiente (`comum/config.py`)

| variável | padrão | uso |
|---|---|---|
| VIGIA_LAKE | dados/lake | raiz do data lake |
| VIGIA_DB | var/vigia.db | SQLite do app |
| VIGIA_SECRET_KEY | (gerada em dev, com aviso) | assinatura do cookie de sessão |
| VIGIA_CHAVE_DADOS | (gerada em dev, com aviso) | chave Fernet que cifra o telefone |
| VIGIA_TOKEN_INTERNO | dev-token-interno | token da API interna |
| VIGIA_APP_URL | http://localhost:8000 | onde o pipeline/agente encontra o app |
| MQTT_HOST / MQTT_PORT / MQTT_PREFIXO | localhost / 1883 / vigia | broker |
| VIGIA_AMBIENTE | dev | `dev` \| `teste` \| `prod` (em `prod`, segredos padrão são recusados) |

## 7. Arquivos de evento para o emulador — `dados/referencia/eventos_demo/<nome>.csv`

Colunas: `estacao_id,medido_em,nivel_cm,chuva_mm` (janelas de 10 min, UTC). O emulador em modo `replay`
publica essas linhas como leituras, com `--velocidade N` (linhas por segundo por estação) e `origem="replay"`.
