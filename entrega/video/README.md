# Vídeo pitch do VigIA

`VigIA_pitch_Grupo14.mp4` — 1920×1080, até 2:55, narração pt-BR e legendas queimadas.
Todas as imagens são do protótipo real rodando (app, painel e simulação do Wokwi); não há tela montada.

## Como regenerar (a partir da raiz do repositório)

1. **Narração** (voz neural `pt-BR-AntonioNeural`, precisa de internet): `python entrega/video/gerar_audio.py`
2. **Simulação do Wokwi** (precisa de internet; ~5 min): `python entrega/video/gravar_wokwi.py --distancia 150`
3. **Telas do protótipo** — use uma CÓPIA do data lake, para não misturar com os seus dados:
   - copie `dados/lake` para uma pasta temporária e apague nela `landing`, `bronze/sensores`,
     `silver/leituras/origem=sensor`, `gold/*/origem=sensor` e `gold/_ia_estado.json`;
   - `python entrega/video/gravar_cenas.py --lake <cópia> --db <pasta temporária>/vigia.db`
     (sobe os serviços nas portas 8031/8531, reproduz o temporal de 24/01/2025 e grava cada cena em `cenas/`).
4. **Montagem**: `python entrega/video/build_video.py` (falha se passar de 175 s).

## Arquivos

| Arquivo | Papel |
|---|---|
| `roteiro.json` | texto da narração, ordem das cenas e qual gravação entra em cada uma |
| `gerar_audio.py` | gera `audio/<cena>.mp3` com edge-tts |
| `gravar_wokwi.py` | grava quadros da simulação real do ESP32 no Wokwi |
| `gravar_cenas.py` | grava as telas reais do app e do painel durante o temporal reproduzido |
| `build_video.py` | ajusta cada cena à narração, concatena e queima as legendas |

## O que cada cena mostra

| Tempo | Cena | Imagem |
|---|---|---|
| 0:00 | Problema e cidadão | tela inicial pública do app (tempo seco), com a fonte do dado no canto |
| 0:25 | Solução | captura real da estação no Wokwi e diagrama de arquitetura |
| 0:42 | Sensor | simulação real no Wokwi: nível acima da cota, LED vermelho e sirene pela regra local, leituras guardadas sem rede |
| 0:59 | IA | "Minha área" às 16h20 do temporal (38 cm, IA em 95%), detalhe do alerta com SMS, transbordo 1 hora depois |
| 1:33 | Números | aba "IA: antes × depois" do painel |
| 1:50 | Painel e ocorrência | filtros do painel, relato de bueiro entupido, painel do agente |
| 2:05 | Impacto e ODS | app no celular e `/status.txt` |
| 2:32 | Fechamento | tela inicial durante o temporal |

O link público (YouTube ou Drive) é publicado pela equipe e vai no `.txt` da entrega e no README do projeto.
