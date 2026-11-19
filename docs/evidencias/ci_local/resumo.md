# Execução local do pipeline de CI

Data: 19/11/2026 16:38 · commit `ea18df8` · mesmos passos de `.github/workflows/ci.yml`.

| Etapa | Resultado | Duração |
|---|---|---:|
| 01_lint_ruff | passou | 1.4 s |
| 02_seguranca_bandit | passou | 2.5 s |
| 03_dependencias_pip_audit | passou | 55.8 s |
| 04_testes_pytest | passou | 81.2 s |
| 05_docker_build | passou | 12.3 s |
| 05b_docker_limpar | passou | 1.2 s |
| 06_docker_up | passou | 65.5 s |
| 07_docker_ps | passou | 4.2 s |
| 08_emulador_replay | passou | 33.9 s |
| 09_fumaca_ponta_a_ponta | passou | 4.5 s |
| 10_monitor | passou | 4.8 s |
| 11_docker_logs | passou | 4.1 s |
