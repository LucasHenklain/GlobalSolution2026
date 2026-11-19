# VigIA — app web (morador e agente)

App FastAPI + Jinja2, HTML leve e sem JavaScript (funciona em internet ruim), SQLite da biblioteca padrão.
Recebe a situação das estações e os alertas pela API interna (contrato em `docs/contratos-tecnicos.md`, seção 5).

## Como rodar (a partir da raiz do repositório)

```
python -m mvp.web.seed --demo                      # cria os usuários de demonstração e dados de exemplo
python -m uvicorn mvp.web.app:app --port 8000      # abre em http://localhost:8000
python -m pytest tests/web -q                      # testes (sem rede, banco temporário)
```

O banco (`var/vigia.db`, ou o caminho de `VIGIA_DB`) e as tabelas são criados sozinhos na subida do app.
Sem `--demo`, o seed cria só os dois usuários. As situações de exemplo aparecem com a faixa
"Demonstração: dados de exemplo" e nunca passam por cima de dado vindo do pipeline.

## Usuários de demonstração (definidos em `seed.py`; o seed não roda em produção)

| Papel | E-mail | Senha |
|---|---|---|
| Morador (Córrego Aricanduva) | `morador@exemplo.com` | `Morador2026demo` |
| Agente da Defesa Civil | `agente@exemplo.com` | `Agente2026demo` |

## Telas

| Rota | Quem vê | O que mostra |
|---|---|---|
| `/` | todos | situação de cada estação (risco, % da cota, chuva 1 h, hora da leitura) |
| `/cadastro`, `/entrar`, `POST /sair` | todos | conta com consentimento LGPD |
| `/minha-area` | morador | risco da área, por quê, chance de transbordo, gráfico SVG, o que fazer, último alerta |
| `/alertas`, `/alertas/{id}` | logado | alertas da área (agente vê todos) e o detalhe: motivos, orientações, SMS, origem da decisão |
| `/ocorrencias`, `/ocorrencias/nova` | logado | relatar problema e acompanhar o status |
| `/estacoes`, `/estacoes/{id}` | todos | lista e detalhe (gráfico, cotas, bateria) |
| `/perfil` | logado | dados, preferências (SMS, letras grandes, alto contraste), exportar dados, excluir conta |
| `/agente` | agente | sirenes (MQTT), fila de ocorrências, alertas recentes, caixa de saída de SMS simulada |
| `/emergencia` | todos | telefones de emergência com toque para ligar (tela pedida na validação com pessoas reais) |
| `/status.txt` | todos | uma linha por estação em texto puro |
| `/health`, `/metrics` | todos | saúde (JSON) e contadores no formato Prometheus |
| `/api/interno/*` | pipeline e agente de alerta | `POST situacao`, `POST alertas`, `GET ocorrencias` com `X-Token-Interno` |

## Arquivos

| Arquivo | Papel |
|---|---|
| `app.py` | monta o app: sessão, cabeçalhos de segurança, páginas de erro, rotas |
| `apoio.py` | conexão por requisição, usuário da sessão, controle de acesso, CSRF, renderização |
| `banco.py` | tabelas e todo o SQL (sempre parametrizado) |
| `seguranca.py` | bcrypt, Fernet do telefone, máscara, limite de tentativas de login |
| `validacao.py` | validação dos formulários com mensagens simples |
| `modelos.py` | modelos Pydantic da API interna |
| `rotas_publicas.py`, `rotas_conta.py`, `rotas_morador.py`, `rotas_agente.py`, `rotas_interno.py` | as rotas, por público |
| `avisos.py` | recebe o alerta e enfileira o SMS simulado |
| `mqtt_saida.py` | `publicar_sirene(...)`: único ponto que fala com o broker |
| `grafico.py` | gráfico SVG gerado no servidor |
| `apresentacao.py` | textos de risco, orientações, datas em horário de Brasília |
| `metricas.py` | contadores de `/metrics` |
| `seed.py` | dados de demonstração |

## Práticas de segurança (e onde estão)

| Prática | Onde | Teste |
|---|---|---|
| Senha com bcrypt; mínimo de 8 caracteres com letra e número | `seguranca.py` (`gerar_hash_senha`, `problemas_da_senha`) | `test_senha_fraca_e_recusada`, `test_senha_guardada_com_bcrypt` |
| Sessão em cookie assinado, `HttpOnly`, `SameSite=Lax` (`Secure` em produção); sessão nova no login; sair invalida os cookies antigos | `app.py` (`SessionMiddleware`), `apoio.py` (`iniciar_sessao`, `usuario_da_sessao`) | `test_sessao_regenerada_no_login_e_invalida_apos_sair` |
| CSRF: token por sessão em todo formulário, conferido no servidor (403) | `apoio.py` (`verificar_csrf`), `templates/_csrf.html` | `test_post_sem_csrf_da_403` |
| Limite de login: 5 falhas por e-mail+IP bloqueiam por 15 min; mensagem sempre genérica | `seguranca.py` (`LimiteLogin`), `rotas_conta.py` (`entrar`) | `test_bloqueio_apos_cinco_falhas`, `test_login_errado_tem_mensagem_generica` |
| Validação de entrada no servidor, com erro na própria tela | `validacao.py`, `modelos.py` | `test_cadastro_exige_consentimento_e_dados_validos`, `test_payload_invalido_da_422` |
| SQL sempre parametrizado | `banco.py` | `test_injecao_sql_no_login_nao_autentica` |
| XSS: Jinja com autoescape, sem `\|safe` em dado de usuário; CSP sem script | `apoio.py`, `app.py` (`CSP`) | `test_xss_na_descricao_aparece_escapado` |
| Telefone cifrado em repouso (Fernet) e mascarado na tela | `seguranca.py` (`cifrar_telefone`, `mascarar_telefone`) | `test_telefone_cifrado_no_banco_e_mascarado_na_tela` |
| Controle de acesso por papel e por dono | `apoio.py` (`exigir_login`, `exigir_agente`), `banco.py` (`ocorrencias_do_usuario`) | `test_morador_nao_acessa_painel_do_agente`, `test_morador_nao_ve_ocorrencia_de_outro` |
| LGPD: consentimento, exportar dados, excluir conta com senha | `rotas_conta.py`, `banco.py` (`excluir_usuario`) | `test_exportar_meus_dados`, `test_excluir_conta_remove_dados_pessoais` |
| API interna com token comparado em tempo constante e sem dado pessoal na resposta | `rotas_interno.py`, `seguranca.py` (`iguais`) | `test_api_interna_sem_token_da_401`, `test_ocorrencias_para_o_pipeline_sem_dados_pessoais` |
| Cabeçalhos: CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; `Cache-Control: no-store` nas telas | `app.py` (`CABECALHOS_SEGURANCA`) | `test_cookie_de_sessao_e_cabecalhos_de_seguranca` |
| Logs sem dados pessoais (só ids) | `rotas_conta.py`, `rotas_morador.py` | `test_logs_nao_tem_dados_pessoais` |

## Limites conhecidos (protótipo)

- O SMS é simulado: fica na tabela `sms_saida` só com o telefone mascarado.
- O limite de login e as métricas ficam em memória: zeram ao reiniciar e valem para um processo só.
- O cadastro avisa quando o e-mail não pode ser usado (sem confirmação por e-mail, não há como esconder isso).
- A descrição da ocorrência é texto livre e segue para o pipeline como o contrato pede; a tela orienta a não escrever dados pessoais.
- Segredos: em dev/teste as chaves são geradas ao lado do banco; em produção `VIGIA_SECRET_KEY`, `VIGIA_CHAVE_DADOS` e `VIGIA_TOKEN_INTERNO` são obrigatórias.
