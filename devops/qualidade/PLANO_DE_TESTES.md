# Plano de testes do VigIA

**Objetivo:** provar que cada área funciona sozinha e que o fluxo completo (sensor → pipeline → IA → app → sirene)
funciona de ponta a ponta.

**Como rodar:** `python -m pytest -v` (tudo) ou `python -m devops.ci_local` (testes + lint + segurança, com
registro em `docs/evidencias/ci_local/`).

**Estratégia:** testes automatizados com `pytest`, em três níveis — unidade (regras isoladas), integração
(módulos conversando, com banco e data lake temporários) e ponta a ponta (pilha inteira no Docker).
Nenhum teste depende de internet. Cada teste recebe um data lake e um banco só dele (`tests/conftest.py`).

## Casos de teste

| ID | Área | O que verifica | Entrada | Resultado esperado | Teste automatizado |
|---|---|---|---|---|---|
| CT-01 | Dados | Leitura válida entra no silver | leitura dentro do contrato | 1 válida, 0 em quarentena | `tests/dados/test_silver.py` |
| CT-02 | Dados | Leitura inválida vai para a quarentena com o motivo | nível 900 cm, chuva −3, data futura, estação inexistente | rejeitadas com LEI-02/03/04/05 | `tests/dados/test_silver.py` |
| CT-03 | Dados | Duplicata não conta duas vezes | 2 leituras da mesma estação e instante | fica a recebida por último | `tests/dados/test_silver.py` |
| CT-04 | Dados | Features de 10 min corretas | série conhecida de nível e chuva | acumulados e variações conferem | `tests/dados/test_features.py` |
| CT-05 | Dados | Medidas do dashboard | eventos e alertas conhecidos | antecedência de 50 min; 50% avisados | `tests/dados/test_medidas.py` |
| CT-06 | IoT | Gateway rejeita na porta o que foge do contrato | payloads MQTT inválidos | vão para `quarentena_gateway` com o motivo | `tests/iot/test_iot_gateway.py` |
| CT-07 | IoT | Regra local da estação funciona sem rede | nível acima da cota de alerta | sirene ligada sem depender do MQTT | `tests/iot/test_iot_emulador.py` |
| CT-08 | IoT | Guarda-e-reenvia sem conexão | broker fora do ar | leituras guardadas e reenviadas em ordem | `tests/iot/test_iot_emulador.py` |
| CT-09 | IA | Agente classifica o risco (R1–R5) | probabilidade e nível | verde, amarelo, laranja ou vermelho corretos | `tests/ia/test_agente.py` |
| CT-10 | IA | Agente não repete alerta igual e avisa a normalização (R6–R9) | série com risco subindo e caindo | 1 alerta por subida, lembrete a cada 60 min, aviso de normalização | `tests/ia/test_agente.py` |
| CT-11 | IA | SMS cabe em 160 caracteres, sem acento | todas as estações e níveis | até 160 caracteres, só ASCII | `tests/ia/test_agente.py` |
| CT-12 | IA | Métrica de antecedência e de alarme falso | série sintética com 1 transbordo | antecedência e falsos calculados certo | `tests/ia/test_avaliacao.py` |
| CT-13 | Web | Cadastro, login e saída | dados válidos | sessão criada e encerrada | `tests/web/test_web_conta.py` |
| CT-14 | Segurança | Senha fraca recusada; login errado com mensagem genérica; bloqueio após 5 falhas | tentativas inválidas | recusa, mensagem única, bloqueio | `tests/web/test_web_conta.py` |
| CT-15 | Segurança | Formulário sem token CSRF é recusado | POST sem token | HTTP 403 | `tests/web/test_web_conta.py` |
| CT-16 | Segurança | Morador não acessa o painel do agente nem ocorrência de outro morador | sessão de morador | HTTP 403; não lista | `tests/web/test_web_telas.py` |
| CT-17 | Segurança | Injeção de SQL e XSS não funcionam | aspas e OR 1=1 no login; tag script na descrição | não autentica; texto aparece escapado | `tests/web/test_web_conta.py`, `test_web_telas.py` |
| CT-18 | Segurança | Telefone cifrado no banco e mascarado na tela | cadastro com telefone | número não aparece em claro no SQLite | `tests/web/test_web_conta.py` |
| CT-19 | Web | API interna exige token e é idempotente | mesmo alerta enviado 2 vezes | 401 sem token; 1 alerta e 1 SMS por morador | `tests/web/test_web_interno.py` |
| CT-20 | Integração | Fluxo completo: leituras de um temporal → gold → IA → alerta no app → SMS na fila | replay do evento de demonstração | alerta de risco alto visível ao morador | `tests/integracao/test_fluxo_completo.py` |
| CT-21 | Ponta a ponta | Pilha no Docker: emulador publica por MQTT e o alerta chega ao app | `docker compose up` + replay | `/metrics` do app conta alertas recebidos | `python -m devops.verificar_pilha --esperar-alerta 120` |

## Evidência de execução

- `docs/evidencias/ci_local/04_testes_pytest.txt` — saída completa do `pytest -v` com cobertura.
- `docs/evidencias/ci_local/relatorio-testes.xml` — relatório JUnit.
- `docs/evidencias/ci_local/09_fumaca_ponta_a_ponta.txt` — CT-21 na pilha Docker.
- `docs/evidencias/ci_local/resumo.md` — resultado de cada etapa do pipeline.

## Critério de aceite

Todos os testes passam, `ruff` e `bandit` sem apontamentos, `pip-audit` sem vulnerabilidade conhecida,
e o teste de fumaça recebe ao menos um alerta da IA no app.
