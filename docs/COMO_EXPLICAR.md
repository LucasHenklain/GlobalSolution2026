# Guia de estudo do código, área por área

Leitura de 15 minutos, para a equipe revisar e entender o que está sendo entregue. Para cada área: a ideia em uma frase,
onde está no código, o que rodar para ver funcionando e perguntas para testar o entendimento.
Quem for apresentar uma área deve abrir os arquivos citados e rodar o comando.

## A história em 30 segundos

Uma estação barata (ESP32) mede o nível do córrego e a chuva. As leituras viajam por MQTT, são validadas e
organizadas em camadas (bronze, silver, gold). Um modelo de machine learning lê o gold e calcula a chance de o
córrego transbordar na próxima hora. Um agente de regras transforma essa chance em um alerta com linguagem simples,
manda para o app do morador, enfileira o SMS e liga a sirene. O morador também relata problemas (bueiro entupido),
que voltam para o data lake. A Defesa Civil vê tudo num painel e decide onde agir primeiro.

---

## Área 1 — IA e automação (`ia/`)

**Em uma frase:** a IA prevê o transbordo antes de o nível subir, olhando principalmente a chuva; o agente decide o alerta.

| Arquivo | O que faz |
|---|---|
| `dataset.py` | lê o gold, cria as variáveis de entrada e o alvo ("vai transbordar em 60 min?"), separa treino/validação/teste **por tempo** |
| `treinar.py` | treina o `HistGradientBoostingClassifier`, escolhe o limiar na validação, mede no teste, grava modelo e métricas |
| `avaliacao.py` | a régua: antecedência por evento, alarmes falsos, precisão/recall/F1 — aplicada igual à regra fixa e à IA |
| `modelo.py` | carrega o modelo e devolve a probabilidade |
| `agente.py` | regras R1–R10: nível de risco, quando emitir, lembrete, sem repetição, normalização, sirene |
| `mensagens.py` | textos fixos por nível (título, mensagem, orientações, SMS ≤ 160 caracteres, "por quê") |
| `servico.py` | laço em tempo real: lê o gold → modelo → agente → entrega ao app e à sirene; modo `retroativo` para o dashboard |
| `demonstrar.py` | entrada e saída no terminal |

**Mostrar:** `python -m ia.demonstrar` (nível 38 cm, que a regra fixa chama de "normal", vira alerta vermelho com 95%).

**Perguntas e respostas**
- *Por que gradient boosting?* Porque a relação é não linear (chuva forte com solo encharcado escoa muito mais) e
  árvores lidam com isso sem normalizar dados. É conteúdo de scikit-learn; treina em menos de 1 minuto.
- *Qual é o "antes"?* A regra de limiar fixo: alertar quando o nível passa da cota de alerta. É o que um sensor sem IA faz
  (e é a regra que roda na estação). Ela só avisa quando a água já subiu: mediana de 10 min de antecedência.
- *Como evitaram "colar"?* Separação por tempo: treino 2019–2022, limiar escolhido em 2023, números reportados em
  2024–2025. O modelo nunca viu o teste.
- *Como escolheram o limiar 0,20?* Na validação: o limiar mais sensível que **não gera mais alarmes falsos do que a regra
  fixa**. Assim a IA só pode ganhar em antecedência sem custar mais alarme à toa.
- *Os dados são reais?* A chuva é (INMET). O nível é simulado por um modelo chuva-vazão declarado, com incertezas que a
  IA não enxerga (a chuva na bacia é diferente da chuva no ponto). Os números valem para esse cenário.
- *E se a IA errar ou cair?* A regra de nível continua valendo como rede de segurança (R2 e R5) e a estação toca a
  sirene sozinha. A IA nunca avisa menos do que a regra.
- *Por que não usar um LLM para escrever o alerta?* Aviso de emergência precisa ser previsível, revisável pela Defesa
  Civil e funcionar sem internet. Texto fixo cumpre isso.

**Números principais (modelo sozinho contra a regra sozinha):** 23,7% → 78,9% dos eventos avisados com 30+ min · mediana 10 → 40 min ·
alarmes falsos 61 → 41 · F1 0,28 → 0,57. **Política implantada (IA + regra):** 84,2% · 40 min · 78 alarmes falsos · F1 0,41 —
a rede de segurança avisa 100% dos eventos, ao custo de mais alarmes.

---

## Área 2 — Big data e visualização (`dados/`)

**Em uma frase:** o dado entra bruto, é validado por um contrato e vira tabelas prontas para decidir.

| Camada | O que guarda | Código |
|---|---|---|
| landing | micro-lotes JSONL que o gateway MQTT grava | `ingestao/gateway_mqtt.py` |
| bronze | o bruto imutável (CSV do INMET, JSONL dos sensores) + manifesto com hash | `processamento/bronze.py` |
| silver | dado limpo: tipos, faixas, sem duplicata; o que reprova vai para a **quarentena** com o motivo | `processamento/silver.py` + `contratos/leitura_sensor.v1.yaml` |
| gold | features de 10 min, eventos de transbordo, risco, alertas, ocorrências, agregado diário | `processamento/features.py`, `gold.py` |

**Mostrar:** `python -m dados.pipeline status` e o dashboard (`python -m streamlit run dados/dashboard/app.py`):
trocar o período para "Temporal de 24/01/2025", desmarcar estações, mudar o nível de risco — os 6 indicadores mudam.

**Perguntas e respostas**
- *Por que camadas?* Para poder reprocessar: se uma regra mudar, refazemos silver e gold a partir do bronze sem
  perder o dado original.
- *O que é a função mais importante?* `features.py`: o **mesmo código** calcula as variáveis para treinar a IA e para o
  tempo real. Isso evita o modelo receber em produção algo diferente do que viu no treino.
- *Onde estão as "funções DAX"?* `medidas.py`: cada função é uma medida (soma, máximo, mediana, divisão segura,
  período anterior) e traz a fórmula DAX equivalente na docstring; `powerbi/medidas.dax` reúne todas.
- *Que decisão o painel apoia?* "Onde agir primeiro": o índice de prioridade junta probabilidade da IA (60%), nível
  (30%) e ocorrências abertas (10%). Também mostra em que horário os transbordos começam (escala de plantão).
- *Por que DuckDB e Parquet?* Lê 1,47 milhão de linhas com filtro em milissegundos, sem servidor de banco.

---

## Área 3 — MVP, IoT e experiência digital (`mvp/`)

**Em uma frase:** o morador vê o risco da área dele em linguagem simples; a estação funciona mesmo sem internet.

**Web (`mvp/web/`)** — FastAPI + Jinja, HTML leve sem JavaScript.
`app.py` monta tudo; `rotas_publicas.py`, `rotas_conta.py`, `rotas_morador.py`, `rotas_agente.py`, `rotas_interno.py`
são as telas; `banco.py` é o SQLite; `seguranca.py` e `validacao.py` protegem; `grafico.py` desenha o gráfico em SVG no servidor.

**IoT (`mvp/iot/`)** — `firmware/sketch.ino` (ESP32 no Wokwi) e `emulador.py` (4 estações em Python).

**Mostrar o fluxo completo:** `python -m devops.demo` → entrar como morador → "Minha área" muda de verde para vermelho →
abrir o alerta (por quê, o que fazer, SMS) → relatar ocorrência → entrar como agente → ver a ocorrência, a caixa de SMS e o botão da sirene.

**Perguntas e respostas**
- *Quais são os 2 sensores?* Ultrassônico HC-SR04 (distância até a água → nível) e pluviômetro de báscula (cada
  basculada = 0,25 mm, contada por interrupção). Há ainda a bateria. Atuadores: 3 LEDs e a sirene.
- *Por que Wokwi e não TinkerCad?* O TinkerCad não simula ESP32 nem rede; no Wokwi o firmware publica MQTT de verdade.
- *O que acontece sem internet?* A estação decide sozinha (regra local: nível ≥ cota de alerta → LED vermelho e sirene)
  e guarda até 60 leituras para reenviar quando a rede voltar. O morador tem SMS e uma página em texto puro (`/status.txt`).
- *Como o app recebe os dados?* Pela API interna, com token: a IA envia a situação de cada estação e os alertas.
  O app não lê o data lake — se o pipeline cair, ele continua mostrando o último estado conhecido.
- *Acessibilidade?* Cor + ícone + texto em todo nível de risco, alto contraste e letras grandes no perfil, foco visível,
  frases curtas.

---

## Área 4 — DevOps, segurança e qualidade (`devops/`, `tests/`, `.github/`)

**Em uma frase:** um comando sobe tudo, um commit testa tudo, e os dados pessoais ficam protegidos.

- **Docker:** uma imagem, 8 serviços (`docker-compose.yml`): mosquitto, preparo, app, gateway, pipeline, ia, dashboard,
  emulador. Healthchecks, volume para os dados, usuário sem root.
- **CI/CD:** `.github/workflows/ci.yml` — ruff → bandit → pip-audit → pytest → build → sobe a pilha e roda o teste de
  fumaça (`devops/verificar_pilha.py`) → publica a imagem no registro. `python -m devops.ci_local` roda os mesmos
  passos na máquina e guarda a evidência em `docs/evidencias/ci_local/`.
- **Monitoramento:** `/health`, `/metrics`, arquivos de batimento do gateway, do pipeline e da IA, logs em JSON,
  `python -m devops.monitor`.
- **Segurança (onde está):** bcrypt e bloqueio de login (`mvp/web/seguranca.py`), CSRF (`_csrf.html` + `seguranca.py`),
  validação (`mvp/web/validacao.py`, `modelos.py`, gateway e silver), telefone cifrado com Fernet e mascarado,
  papéis morador × agente, token interno, cabeçalhos (CSP), LGPD (exportar e excluir conta).
- **Testes:** `devops/qualidade/PLANO_DE_TESTES.md` (21 casos) e a pasta `tests/`.

**Perguntas e respostas**
- *O CI rodou no GitHub?* Sim: o push de 18/11 disparou o workflow `ci` e os 3 jobs passaram (qualidade → build e
  teste da pilha → publicação da imagem). O print e o endereço da execução estão na seção 9.2 do PDF; os mesmos passos
  também rodaram localmente (`python -m devops.ci_local --com-docker`).
- *Qual a diferença entre autenticação e autorização aqui?* Autenticação: login com senha (bcrypt). Autorização: o
  morador não entra no painel do agente (403) nem vê ocorrência de outro morador.
- *Por que cifrar o telefone?* É dado pessoal (LGPD). Se o banco vazar, o número não aparece. Nas telas ele sai mascarado.
- *O que é teste de ponta a ponta?* O que sobe a pilha inteira no Docker, publica leituras por MQTT e confere se o
  alerta chegou ao app.

---

## O que é real e o que é simulado

- "A chuva é real, do INMET; o nível do córrego é simulado. Os números da IA valem para esse cenário."
- "A IA não substitui a regra de nível: ela antecipa. A regra continua como rede de segurança."
- "Usamos IA generativa como apoio para escrever e revisar código e documentos; está declarado no README."
