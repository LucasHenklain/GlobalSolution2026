# Execução local do pipeline de CI

Data: 18/11/2026 15:43 · commit `5673988` · mesmos passos de `.github/workflows/ci.yml`.

| Etapa | Resultado | Duração |
|---|---|---:|
| 01_lint_ruff | passou | 4.8 s |
| 02_seguranca_bandit | passou | 15.5 s |
| 03_dependencias_pip_audit | passou | 708.4 s |
| 04_testes_pytest | passou | 505.1 s |
| 05_docker_build | passou | 89.6 s |
| 05b_docker_limpar | passou | 4.6 s |
| 06_docker_up | passou | 808.1 s |
| 07_docker_ps | passou | 6.2 s |
| 08_emulador_replay | passou | 57.7 s |
| 09_fumaca_ponta_a_ponta | passou | 10.1 s |
| 10_monitor | passou | 11.4 s |
| 11_docker_logs | passou | 6.9 s |
