# Estação VigIA — ESP32 no Wokwi

Firmware da estação de monitoramento **EST-ARI-01** (Córrego Aricanduva), simulada no
[Wokwi](https://wokwi.com). A estação mede o **nível do córrego** (ultrassom) e a **chuva**
(pluviômetro de báscula), decide sozinha se acende o LED de atenção ou liga a sirene
(**regra local, sem internet**) e publica as leituras por MQTT no formato do contrato
(`docs/contratos-tecnicos.md`, seção 3). O gateway (`dados/ingestao/gateway_mqtt.py`) transforma
essas mensagens nos micro-lotes que o pipeline de dados processa.

## Arquivos

| Arquivo | O que é |
|---|---|
| `sketch.ino` | o firmware: sensores, regra local, guarda-e-reenvia, Wi-Fi, NTP, MQTT, comando da sirene |
| `diagram.json` | o circuito: ESP32 DevKit-C v4, HC-SR04, botão, chave, potenciômetro, 3 LEDs e buzzer |
| `libraries.txt` | bibliotecas usadas: PubSubClient e ArduinoJson |
| `capturar_wokwi.py` | abre o Wokwi no Edge, roda a simulação e salva um PNG (evidência reproduzível) |

## Circuito

| Peça | Pino do ESP32 | Papel |
|---|---|---|
| HC-SR04 (ultrassom) | TRIG 5, ECHO 18 | mede a distância até a água; `nivel_cm = 400 − distância` |
| botão azul | GPIO 27 | pluviômetro de báscula: cada clique = 1 basculada = 0,25 mm (interrupção + debounce) |
| chave deslizante (abaixo do botão) | GPIO 26 | "chuva forte": ligada, soma 8 basculadas (2 mm) a cada publicação |
| potenciômetro | GPIO 34 (ADC1) | simula a bateria (`bateria_pct`) |
| LED verde / amarelo / vermelho | GPIO 21 / 22 / 23 | normal / atenção / alerta |
| buzzer | GPIO 19 | sirene |

## Abrir no wokwi.com (3 minutos)

1. Entre em <https://wokwi.com> → **New Project** → **ESP32** (template "ESP32", Arduino).
2. Na aba `sketch.ino`, apague tudo e cole o `sketch.ino` desta pasta.
3. Na aba `diagram.json`, apague tudo e cole o `diagram.json` desta pasta.
4. Aba **Library Manager** → botão **+** → procure e adicione `PubSubClient` e depois `ArduinoJson`.
5. Clique em **▶ (Start the simulation)**. No monitor serial aparece, nesta ordem:

```
VigIA, estacao EST-ARI-01, firmware 1.0.0
[regra local] NORMAL: nivel 100.0 cm, LED verde
[wifi] ok, IP 10.10.0.2
[ntp] ok, 2026-11-17T13:40:02Z
[mqtt] ok, publicando em vigia/sensores/EST-ARI-01/leitura
[pub] {"estacao_id":"EST-ARI-01","medido_em":"2026-11-17T13:40:05Z","nivel_cm":100,"chuva_mm":0,"bateria_pct":85,"seq":1,"fw":"1.0.0","origem":"wokwi"}
```

Não há senha nem credencial: a rede `Wokwi-GUEST` é aberta e o `broker.hivemq.com:1883` aceita
conexão anônima. Se o HiveMQ estiver instável, troque `MQTT_HOST` por `test.mosquitto.org` no topo do sketch.

## O que mexer para simular cada cenário

Com a simulação rodando, clique na peça para ajustar. A regra local reage em até 1 segundo.

| Cenário | O que mexer | O que acontece |
|---|---|---|
| **Normal** | HC-SR04 com distância **300 cm** (valor inicial) | nível 100 cm · LED **verde** |
| **Atenção** | clique no HC-SR04 e arraste a distância para **230 cm** | nível 170 cm (≥ 150) · LED **amarelo** · `[regra local] ATENCAO` |
| **Alerta** | distância **150 cm** | nível 250 cm (≥ 220) · LED **vermelho** + **sirene** · `[regra local] ALERTA: sirene ligada` |
| **Transbordo** | distância **100 cm** | nível 300 cm (≥ 280) · vermelho + sirene · `[regra local] TRANSBORDO` |
| **Garoa** | clique algumas vezes no **botão azul** | cada clique soma 0,25 mm ao `chuva_mm` da próxima leitura |
| **Chuva forte** | ligue a **chave deslizante** | `chuva_mm` = 2 mm a cada 5 s (a IA do VigIA passa a enxergar risco antes de o nível subir) |
| **Bateria fraca** | gire o **potenciômetro** para a esquerda | `bateria_pct` cai no payload |
| **Sirene por comando** | publique `{"acao":"ligar","nivel":"vermelho","segundos":15}` em `vigia/atuadores/EST-ARI-01/sirene` | a sirene toca por 15 s mesmo com o nível baixo; o estado sai em `…/sirene/estado` |
| **Sem internet** | no topo do sketch, `ATRASO_REDE_DEMO_MS = 30000` e reinicie | por 30 s a estação fica sem rede: a regra local continua e aparecem linhas `[buffer] sem rede…`; depois ela conecta e reenvia tudo (`[reenvio]`, `[pub]` com a hora original) |

Roteiro curto para o vídeo: comece em 300 cm (verde) → ligue a chave de chuva forte → arraste para
230 cm (amarelo) → 150 cm (vermelho + sirene) → volte para 300 cm (a sirene para).

Para publicar o comando da sirene sem instalar nada: <https://www.hivemq.com/demos/websocket-client/>
(Connect em `broker.hivemq.com`) → *Publish* no tópico acima. No fluxo completo quem publica esse
comando é o agente de alerta (`ia/`).

## Ver as leituras chegando no gateway local

Com a simulação rodando no navegador, em um terminal na raiz do repositório:

```bash
python -m dados.ingestao.gateway_mqtt --broker broker.hivemq.com --porta 1883 --duracao-s 120
```

O gateway assina `vigia/sensores/+/leitura` no mesmo broker público, valida cada leitura e grava
micro-lotes em `dados/lake/landing/sensores/<AAAAMMDD>/leituras_<AAAAMMDD>T<HHMMSS>Z.jsonl`
(uma leitura por linha, com `"origem":"wokwi"`). O log mostra `lote gravado` a cada 5 s e os contadores
(recebidas, válidas, rejeitadas); `dados/lake/landing/_gateway_batimento.json` traz o último estado.

Sem Wokwi (ou sem internet), o emulador publica o mesmo payload no broker local:
`python -m mvp.iot.emulador --cenario temporal --intervalo 2`.

## Aviso: o tópico é público

`broker.hivemq.com` é um broker de testes aberto: **qualquer pessoa pode ler e publicar** em `vigia/#`.
Por isso a estação só envia **dado sintético de sensor** (nível, chuva, bateria) — **nenhum dado
pessoal** passa por MQTT. O gateway valida tudo na porta (estação do catálogo, faixas, tamanho) e
manda o que reprova para a quarentena. Em produção o broker seria próprio, com usuário e senha por
estação e TLS (ver `devops/mosquitto/mosquitto.conf`).

## Por que Wokwi e não TinkerCad

O TinkerCad não simula **ESP32** nem **rede**: só Arduino UNO/micro:bit, sem Wi-Fi. O VigIA depende
exatamente disso — Wi-Fi, NTP e MQTT de verdade saindo do microcontrolador. O Wokwi simula o ESP32
com Wi-Fi real (rede `Wokwi-GUEST` com saída para a internet), então a leitura publicada na simulação
chega de fato ao gateway e ao data lake do projeto.

## Captura da simulação (evidência)

```bash
pip install websocket-client          # só para este script
python mvp/iot/firmware/capturar_wokwi.py                                   # cenário normal
python mvp/iot/firmware/capturar_wokwi.py --distancia 150 --saida mvp/iot/firmware/captura-wokwi-alerta.png
```

O script abre o Edge, carrega o sketch e o circuito, instala as bibliotecas, espera 75 s e salva o PNG.
`--distancia N` muda a distância inicial do HC-SR04 só para a captura (150 cm = alerta).
Manual: deixe visíveis o circuito e o monitor serial com pelo menos um `[pub] {...}` e tire o print.

## Como o firmware funciona (para explicar na banca)

* **Regra local primeiro.** A cada 1 s o `loop()` mede o nível e compara com as cotas da estação
  (atenção 150, alerta 220, transbordo 280 cm — as mesmas de `dados/referencia/estacoes.csv`). Essa
  parte não usa Wi-Fi, MQTT nem relógio: se a internet cair, o LED e a sirene continuam funcionando.
* **Sirene = regra local OU comando.** O comando `desligar` só cancela um comando anterior; enquanto o
  nível estiver no alerta a regra local mantém a sirene ligada.
* **Pluviômetro por interrupção.** Cada basculada fecha um contato; a interrupção conta o pulso e o
  debounce (50 ms) ignora o repique do contato. `chuva_mm` é a chuva desde a leitura anterior.
* **Guarda-e-reenvia.** Toda leitura entra num buffer circular de 60 posições e só sai quando é
  publicada. Sem conexão o buffer acumula (com o `medido_em` original); cheio, descarta a mais antiga.
* **Hora certa.** O relógio é acertado por NTP em UTC antes da primeira publicação. Leitura feita antes
  de o NTP responder tem a hora calculada pelo tempo decorrido (`millis()`).
* **Presença.** Ao conectar, a estação publica `online` (retido) e deixa um LWT `offline` no broker.
* **Sem `delay()` longo.** Tudo é controlado por `millis()`; os bipes da sirene também.

## Limitações conhecidas (protótipo)

* A biblioteca PubSubClient só publica em **QoS 0** (o contrato pede QoS 1). O guarda-e-reenvia cobre a
  queda de conexão; o emulador em Python publica em QoS 1.
* Se o Wi-Fi estiver no ar mas o broker não responder, cada tentativa de conexão MQTT pode segurar o
  `loop()` por alguns segundos (uma tentativa a cada 5 s). Em produção a rede iria para uma tarefa
  separada do FreeRTOS.
* No hardware real o ECHO do HC-SR04 sai em 5 V e precisa de divisor de tensão para o ESP32 (3,3 V);
  no Wokwi a ligação direta funciona.
* Na demonstração o tempo é comprimido (publicação a cada 5 s e "chuva forte" de 2 mm por ciclo).
  Em campo: publicação a cada 10 min (`INTERVALO_PUBLICACAO_MS = 600000`) e *deep sleep* entre leituras.
