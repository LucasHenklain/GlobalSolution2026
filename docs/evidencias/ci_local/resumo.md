# Execução local do pipeline de CI

Data: 18/11/2026 12:43 · commit `7af78d6` · mesmos passos de `.github/workflows/ci.yml`.

| Etapa | Resultado | Duração |
|---|---|---:|
| 01_lint_ruff | passou | 4.2 s |
| 02_seguranca_bandit | passou | 5.2 s |
| 03_dependencias_pip_audit | passou | 130.6 s |
| 04_testes_pytest | passou | 155.2 s |
| 05_docker_build | passou | 24.9 s |
| 05b_docker_limpar | passou | 5.2 s |
| 06_docker_up | passou | 433.9 s |
| 07_docker_ps | passou | 6.1 s |
| 08_emulador_replay | passou | 71.8 s |
| 09_fumaca_ponta_a_ponta | passou | 11.0 s |
| 10_monitor | passou | 9.9 s |
| 11_docker_logs | passou | 6.5 s |
