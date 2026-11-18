### Execução no GitHub Actions (real)

- Repositório: github.com/LucasHenklain/GlobalSolution2026 (público). O push de 18/11/2026 disparou o workflow **ci** sozinho, sem passo manual.
- Execução **#1**, commit 42385bc: **sucesso em 5 min 58 s**, com os três jobs encadeados.
- **Lint, segurança e testes** (1 min 16 s): ruff, bandit, pip-audit e pytest com cobertura.
- **Build da imagem e teste da pilha** (2 min 55 s): docker compose build, pilha no ar, emulador publicando o temporal por MQTT e o teste de fumaça conferindo o alerta da IA no app.
- **Publicar imagem** (1 min 40 s): imagem enviada ao GitHub Container Registry (entrega contínua).
- Endereço da execução: github.com/LucasHenklain/GlobalSolution2026/actions/runs/44342094886
