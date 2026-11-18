# PLANO — Global Solution 2026/2 · CitizenTech · Grupo 14 (4ESOA)

> Documento vivo. Atualizado a cada etapa. Prazo: **19/11/2026 23h55** (plataforma FIAP).

## 1. Problema escolhido

**Enchentes-relâmpago em córregos urbanos: o morador de área de risco só descobre que a água vai subir quando ela já está na porta.**

- **Cidadão beneficiado:** famílias que moram às margens de córregos urbanos em áreas de risco
  (persona: moradora de 62 anos, celular simples, internet pré-paga instável). Segundo beneficiado:
  o agente da Defesa Civil / liderança comunitária, que precisa decidir onde agir primeiro.
- **Dados reais (com fonte):**
  - 8.270.127 pessoas viviam em áreas de risco em 872 municípios monitorados (IBGE/Cemaden, 2018, base Censo 2010).
  - 1.942 municípios com áreas de risco e mais de 8,9 milhões de pessoas nelas; de 1991 a 2022: 3.890 mortes
    e 8,2 milhões de desalojados/desabrigados por inundações, enxurradas e deslizamentos
    (nota técnica da Casa Civil, divulgada pela Agência Brasil em maio/2024).
  - 24 horas de aviso antecipado podem reduzir os danos de um evento em até 30%
    (Global Commission on Adaptation, citada pela OMM na iniciativa *Early Warnings for All*).
- **Por que este problema (critérios do enunciado):**
  (a) IoT plausível e barato: sensor ultrassônico de nível + pluviômetro de báscula num ESP32;
  (b) gera série temporal para pipeline em camadas e dashboard de decisão (onde agir primeiro);
  (c) a IA tem ganho **mensurável**: antecedência do alerta, eventos detectados e alarmes falsos contra a regra de limiar fixo;
  (d) cidadão e ODS evidentes (11.5, 13.1, 3.d, 10.2, 9.c);
  (e) funciona com conectividade ruim: a estação decide e toca a sirene sozinha (regra local),
  guarda leituras quando fica sem rede, e o alerta chega por SMS de 160 caracteres e por página de poucos KB.

## 2. Produto: **VigIA — alerta comunitário de enchentes**

Estações de baixo custo (ESP32) medem o nível do córrego e a chuva; o pipeline trata os dados em camadas;
um modelo de IA prevê transbordo nos próximos 60 minutos; um agente de regras decide o nível do alerta,
escreve a mensagem em linguagem simples e aciona a sirene da estação; o morador recebe o aviso no app/SMS e
relata ocorrências (bueiro entupido, ponto de alagamento); a Defesa Civil prioriza pelo dashboard.

Recorte do MVP: 4 pontos de monitoramento **simulados** em córregos reais de São Paulo
(Aricanduva, Pirajuçara, Jardim Pantanal/Tietê, Ipiranga). **Chuva real** (INMET, estações A701 Mirante de Santana e
A771 Interlagos, 2019–2025, dado horário); **nível do córrego simulado** por modelo hidrológico simples (declarado).

## 3. Arquitetura (resumo)

```
ESP32 (Wokwi) / emulador ──MQTT──> gateway ──> landing ──> BRONZE ──> SILVER ──> GOLD ──┬─> dashboard (Streamlit, filtros + medidas)
   ^  sirene + LEDs (regra local)                    (quarentena)                        ├─> IA: modelo (prob. transbordo 60 min)
   └──────────── MQTT comando sirene <── agente de alerta (regras) <──────────────────────┘        │
                                              │ POST /api/interno/alertas + /situacao              │
                                              v                                                    │
                           app web FastAPI (morador + agente) ── ocorrências ──> bronze ───────────┘
```

Pastas (uma por área do enunciado):

| Pasta | Área | Conteúdo |
|---|---|---|
| `ia/` | 1 · IA e automação | features → modelo scikit-learn, avaliação antes/depois, agente de alerta (regras), mensagens |
| `dados/` | 2 · Big data e visualização | contratos, ingestão (gateway MQTT, INMET), data lake bronze/silver/gold, medidas (estilo DAX), dashboard Streamlit |
| `mvp/` | 3 · MVP, IoT e experiência | `web/` (FastAPI + Jinja, 8+ telas), `iot/` (firmware ESP32 Wokwi, emulador de estações) |
| `devops/` | 4 · DevOps, segurança e qualidade | Docker, compose, CI (GitHub Actions + execução local), monitoramento, plano de testes |
| `comum/` | compartilhado | configuração, log estruturado, catálogo de estações |
| `tests/` | qualidade | testes automatizados por área |
| `docs/` | entregáveis | PDF, diagramas, evidências, guia "como explicar cada área" |
| `entrega/` | entrega | ZIP, `.txt` dos integrantes, vídeo |

Contratos técnicos entre os módulos: [docs/contratos-tecnicos.md](docs/contratos-tecnicos.md).

## 4. Decisões

| # | Decisão | Motivo |
|---|---|---|
| D1 | Enchentes em córregos urbanos (SP) | melhor encaixe nos 5 critérios; dado público real disponível (INMET) |
| D2 | Chuva real do INMET + nível simulado | não há série pública aberta de nível de córrego em 10 min; simulação declarada no README e no PDF |
| D3 | Mesma função de features no treino e no tempo real | evita divergência treino/produção; é o elo "a IA usa os dados do pipeline" |
| D4 | Baseline = regra de limiar fixo (a mesma que roda na estação) | é o "antes" honesto: o que um sensor sem IA faz |
| D5 | Agente de alerta por regras explícitas, sem LLM em tempo de execução | roda offline, explicável, a equipe consegue defender cada regra |
| D6 | App recebe situação/alertas por API interna com token; não lê o lake | desacopla as áreas; o app segue útil com o último estado conhecido |
| D7 | FastAPI + Jinja (HTML leve, quase sem JS) | página de poucos KB para internet ruim; acessível |
| D8 | SQLite no app; Parquet + DuckDB no lake | sem servidor de banco; tudo sobe com `docker compose up` |
| D9 | Sem push/remote: CI preparado + execução local equivalente | regra do processo; evidência honesta |

## 5. Checklist da rubrica

### Área 1 · IA e automação (4)
- [x] IA aplicada implementada (1,5): modelo de previsão de transbordo em 60 min (`ia/treinar.py`) + serviço em tempo real (`ia/servico.py`)
- [x] Regras/agente documentados no PDF (1): R1–R10 e modelos de mensagem (`ia/agente.py`, `ia/mensagens.py`; PDF 6.2)
- [x] Demonstração com entrada e saída (0,5): `python -m ia.demonstrar` (PDF 6.3)
- [x] Lógica e ganho com métrica antes/depois (1): 23,7% → 78,9% avisados com 30+ min; mediana 10 → 40 min; falsos 61 → 41 (PDF 6.4)

### Área 2 · Big data e visualização (4)
- [x] Estrutura em camadas (landing, bronze, silver, quarentena, gold) (1)
- [x] Ingestão e processamento da coleta ao dado tratado (INMET real + MQTT) (1)
- [x] Dashboard com 6 indicadores e 4 filtros para decisão (1,5)
- [x] Funções analíticas / medidas estilo DAX (`dados/medidas.py`, `dados/powerbi/medidas.dax`) (0,5)

### Área 3 · MVP, IoT e experiência digital (4)
- [x] 12 telas funcionais (1)
- [x] 2+ sensores: ESP32 no Wokwi (ultrassônico + pluviômetro + bateria), compilado e publicando MQTT; emulador (1)
- [x] Fluxo completo do início ao fim (`docker compose up` ou `python -m devops.demo`) (1)
- [x] Diagrama de arquitetura geral (`docs/diagramas/arquitetura.svg`) (1)

### Área 4 · DevOps, segurança e qualidade (3)
- [x] Organização por módulos + Git (0,5)
- [x] Docker (8 serviços), CI no GitHub Actions (execução #1, 3 jobs com sucesso) e local, monitoramento (1)
- [x] Segurança: autenticação, autorização, validação, CSRF, cifra do telefone, LGPD (0,5)
- [x] Plano com 21 casos e evidência de execução (154 testes automatizados) (1)

### Vídeo pitch (5) e entrega
- [x] Vídeo de 2:48 mostrando o protótipo funcionando (`entrega/video/VigIA_pitch_Grupo14.mp4`)
- [ ] Link público do vídeo no `.txt` e no README — **depende da equipe**
- [x] PDF de entregáveis (`VigIA_Grupo14_Entregaveis.pdf`, gerado por `docs/pdf/gerar_pdf.py`)
- [x] `.txt` com grupo, RM, nomes e link (`Grupo14_integrantes.txt`; link a preencher)
- [x] README de execução + declaração de uso de IA generativa
- [x] ZIP extraído e validado do zero seguindo só o README (pasta limpa + ambiente virtual; Docker validado na CI do GitHub)
- [ ] Validação com gente real — **depende da equipe** (roteiro em `docs/validacao/`)

## 6. Andamento

- 16/11: case lido; problema decidido; ambiente verificado; dados INMET 2019–2025 baixados.
- 17/11: data lake, simulação hidrológica, IA (treino e avaliação), agente, dashboard, app web, IoT (firmware validado no Wokwi), integração ponta a ponta.
- 18/11: Docker Compose, CI local completo, capturas reais, PDF, README, roteiro de validação, empacotador, vídeo.

## 7. Depois de receber o link do vídeo e as respostas da validação

1. Conferir `docs/validacao/respostas.csv` (uma linha por pessoa) e, se houver, `docs/validacao/o_que_mudou.md`.
2. `python -m devops.finalizar --video LINK` — grava o link, consolida a validação, regera o PDF, faz o commit e monta o ZIP.
3. `git push` e enviar `entrega/GS2026-2_CitizenTech_Grupo14.zip` na plataforma até 19/11 23h55.
