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
- [ ] IA aplicada implementada (1,5): modelo de previsão de transbordo em 60 min + agente de alerta
- [ ] Regras/agente documentados no PDF (1)
- [ ] Demonstração com entrada e saída (0,5)
- [ ] Lógica e ganho com métrica antes/depois (1)

### Área 2 · Big data e visualização (4)
- [ ] Estrutura em camadas (data lake bronze/silver/gold + quarentena) (1)
- [ ] Ingestão e processamento da coleta ao dado tratado (1)
- [ ] Dashboard com 3+ indicadores e filtros para decisão (1,5)
- [ ] Funções analíticas / medidas estilo DAX (0,5)

### Área 3 · MVP, IoT e experiência digital (4)
- [ ] 4+ telas funcionais (1)
- [ ] 2+ sensores (Wokwi ESP32: ultrassônico + pluviômetro; emulador) (1)
- [ ] Fluxo completo do início ao fim (1)
- [ ] Diagrama de arquitetura geral (1)

### Área 4 · DevOps, segurança e qualidade (3)
- [ ] Organização por módulos + Git (0,5)
- [ ] Evidência de Docker / CI / monitoramento funcionando (1)
- [ ] 2+ práticas de segurança (0,5)
- [ ] Plano com 5+ casos de teste e evidência de execução (1)

### Vídeo pitch (5) e entrega
- [ ] Vídeo ≤ 2:55 mostrando o protótipo funcionando (MP4 no projeto)
- [ ] Link público do vídeo no `.txt` e no README — **depende da equipe**
- [ ] PDF de entregáveis
- [ ] `.txt` com grupo, RM, nomes e link
- [ ] README de execução + declaração de uso de IA generativa
- [ ] ZIP extraído e validado do zero seguindo só o README
- [ ] Validação com gente real — **depende da equipe** (roteiro pronto)

## 6. Andamento

- 16/11: case lido; problema decidido; ambiente verificado; dados INMET 2019–2025 baixados.
