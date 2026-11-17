/*
 * VigIA · alerta comunitário de enchentes · estação de monitoramento (ESP32 no Wokwi)
 * ---------------------------------------------------------------------------------
 * Estação EST-ARI-01 (Córrego Aricanduva). Mede o nível do córrego e a chuva e:
 *
 *  1. REGRA LOCAL (funciona SEM internet): compara o nível com as cotas da estação e
 *     acende o LED verde / amarelo / vermelho; a partir da cota de alerta liga a sirene.
 *  2. Publica a leitura por MQTT a cada 5 s (contrato 3.1 de docs/contratos-tecnicos.md):
 *       vigia/sensores/EST-ARI-01/leitura
 *       {"estacao_id":"EST-ARI-01","medido_em":"2026-11-16T18:00:00Z","nivel_cm":142.5,
 *        "chuva_mm":1.25,"bateria_pct":87,"seq":123,"fw":"1.0.0","origem":"wokwi"}
 *  3. GUARDA-E-REENVIA: sem Wi-Fi/MQTT as leituras ficam num buffer circular (60) com a
 *     hora original e são publicadas, em ordem, quando a conexão volta.
 *  4. Obedece ao comando da sirene (contrato 3.2) e informa o estado:
 *       vigia/atuadores/EST-ARI-01/sirene          {"acao":"ligar","nivel":"vermelho","segundos":30}
 *       vigia/atuadores/EST-ARI-01/sirene/estado   {"sirene":"ligada","motivo":"comando","em":"...Z"}
 *  5. Presença (contrato 3.3): vigia/sensores/EST-ARI-01/status = online | offline (retido, LWT).
 *
 * Sensores e atuadores (o circuito está em diagram.json):
 *   HC-SR04 (ultrassom)   TRIG 5, ECHO 18   distância até a água -> nivel_cm = 400 - distância
 *   botão (pluviômetro)   GPIO 27           cada clique = 1 basculada = 0,25 mm (interrupção)
 *   chave "chuva forte"   GPIO 26           ligada: +8 basculadas por publicação (2 mm)
 *   potenciômetro         GPIO 34 (ADC1)    bateria_pct (o ADC2 não funciona com Wi-Fi ligado)
 *   LED verde / amarelo / vermelho   GPIO 21 / 22 / 23
 *   buzzer (sirene)       GPIO 19
 *
 * Bibliotecas (libraries.txt): PubSubClient e ArduinoJson (v7).
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <math.h>

// ---------------------------------------------------------------------------
// Configuração — tudo que se ajusta está aqui no topo
// ---------------------------------------------------------------------------
const char* ESTACAO_ID = "EST-ARI-01";  // precisa existir em dados/referencia/estacoes.csv
const char* FW_VERSAO  = "1.0.0";
const char* ORIGEM     = "wokwi";

// Cotas da estação EST-ARI-01 (mesmos valores do catálogo de estações).
const float ALTURA_SENSOR_CM   = 400.0f;  // altura do ultrassom acima do leito do córrego
const float COTA_ATENCAO_CM    = 150.0f;  // LED amarelo
const float COTA_ALERTA_CM     = 220.0f;  // LED vermelho + sirene
const float COTA_TRANSBORDO_CM = 280.0f;  // o córrego transborda

const float MM_POR_BASCULADA = 0.25f;                 // resolução do pluviômetro de báscula
const unsigned long BASCULADAS_CHUVA_FORTE = 8;       // somadas a cada publicação com a chave ligada (2 mm)

const char* WIFI_SSID  = "Wokwi-GUEST";  // rede simulada do Wokwi, sem senha
const char* WIFI_SENHA = "";
const char* MQTT_HOST  = "broker.hivemq.com";  // broker público, sem credencial (só dado sintético)
const uint16_t MQTT_PORTA = 1883;
const char* MQTT_PREFIXO  = "vigia";
const char* NTP_SERVIDOR_1 = "pool.ntp.org";
const char* NTP_SERVIDOR_2 = "time.google.com";

const unsigned long INTERVALO_REGRA_MS      = 1000;   // mede o nível e aplica a regra local
const unsigned long INTERVALO_PUBLICACAO_MS = 5000;   // 5 s na demonstração; 600000 (10 min) em campo
const unsigned long INTERVALO_RECONEXAO_MS  = 5000;   // entre tentativas de conectar ao broker
const unsigned long DEBOUNCE_MS             = 50;     // repique do contato do pluviômetro
const unsigned long TIMEOUT_ECO_US          = 30000;  // 400 cm de ida e volta levam ~23 ms
const unsigned long BIPE_MS                 = 300;    // a sirene toca em bipes de 300 ms
const unsigned int  FREQUENCIA_SIRENE_HZ    = 2200;
const int SEGUNDOS_PADRAO_SIRENE = 30;
const int SEGUNDOS_MAXIMO_SIRENE = 600;

// Demonstração do guarda-e-reenvia: com 30000 a estação passa os primeiros 30 s SEM rede
// (regra local funcionando, leituras no buffer) e depois conecta e reenvia tudo. 0 = desligado.
const unsigned long ATRASO_REDE_DEMO_MS = 0;

const int TAMANHO_BUFFER     = 60;  // leituras guardadas sem rede (5 min a cada 5 s)
const int REENVIOS_POR_VOLTA = 5;   // esvazia o buffer aos poucos para não travar o loop

// Pinos
const int PINO_TRIG         = 5;
const int PINO_ECHO         = 18;
const int PINO_PLUVIOMETRO  = 27;
const int PINO_CHUVA_FORTE  = 26;
const int PINO_BATERIA      = 34;
const int PINO_LED_VERDE    = 21;
const int PINO_LED_AMARELO  = 22;
const int PINO_LED_VERMELHO = 23;
const int PINO_BUZZER       = 19;

// ---------------------------------------------------------------------------
// Tipos (declarados antes de qualquer função: exigência do pré-processador do Arduino)
// ---------------------------------------------------------------------------
// Em ordem crescente de gravidade (a regra local usa ">= ESTADO_ALERTA").
enum Estado { ESTADO_DESCONHECIDO, ESTADO_NORMAL, ESTADO_ATENCAO, ESTADO_ALERTA, ESTADO_TRANSBORDO };

struct Leitura {
  time_t        epoch;       // instante UTC da medição; 0 = o relógio ainda não estava certo
  unsigned long medidoMs;    // millis() da medição: permite calcular a hora depois que o NTP responder
  float         nivelCm;
  float         chuvaMm;
  int           bateriaPct;
  unsigned long seq;
};

// ---------------------------------------------------------------------------
// Estado
// ---------------------------------------------------------------------------
WiFiClient rede;
PubSubClient mqtt(rede);

char topicoLeitura[64];
char topicoStatus[64];
char topicoComando[64];
char topicoEstado[72];

// Pluviômetro: alterado dentro da interrupção, por isso volatile + seção crítica.
volatile unsigned long basculadas = 0;
volatile unsigned long ultimaBordaMs = 0;
portMUX_TYPE travaPluviometro = portMUX_INITIALIZER_UNLOCKED;

float nivelCm = 0.0f;
Estado estadoAtual = ESTADO_DESCONHECIDO;
unsigned long falhasDoSensor = 0;

bool sirenePorRegra = false;      // a regra local mandou ligar
bool sirenePorComando = false;    // um comando MQTT mandou ligar (com prazo)
unsigned long comandoAteMs = 0;
bool sireneTocando = false;       // último estado informado
bool bipeLigado = false;

Leitura pendentes[TAMANHO_BUFFER];  // buffer circular
int inicioBuffer = 0;               // posição da leitura mais antiga
int qtdBuffer = 0;
unsigned long perdidas = 0;
unsigned long sequencia = 0;

bool redeIniciada = false;
bool wifiOk = false;
bool mqttOk = false;
bool relogioAnunciado = false;
unsigned long ultimaTentativaMqttMs = 0;
unsigned long ultimaRegraMs = 0;
unsigned long ultimaPublicacaoMs = 0;

// ---------------------------------------------------------------------------
// Relógio
// ---------------------------------------------------------------------------
bool relogioCerto() {
  return time(nullptr) > 1700000000;  // antes de nov/2023 = o NTP ainda não respondeu
}

void formatarIso(time_t instante, char* saida, size_t tamanho) {
  struct tm utc;
  gmtime_r(&instante, &utc);  // o contrato exige UTC com sufixo Z
  strftime(saida, tamanho, "%Y-%m-%dT%H:%M:%SZ", &utc);
}

// ---------------------------------------------------------------------------
// Sensores
// ---------------------------------------------------------------------------

// Interrupção do pluviômetro (qualquer borda). Debounce: ignora bordas a menos de DEBOUNCE_MS
// da anterior e só conta quando o contato está fechado (LOW), ou seja, uma vez por basculada.
void IRAM_ATTR aoBascular() {
  unsigned long agora = millis();
  bool repique = (agora - ultimaBordaMs) < DEBOUNCE_MS;
  ultimaBordaMs = agora;
  if (repique) return;
  if (digitalRead(PINO_PLUVIOMETRO) == LOW) {
    portENTER_CRITICAL_ISR(&travaPluviometro);
    basculadas++;
    portEXIT_CRITICAL_ISR(&travaPluviometro);
  }
}

// Lê e zera o contador: chuva_mm é a chuva DESDE A LEITURA ANTERIOR.
unsigned long coletarBasculadas() {
  portENTER_CRITICAL(&travaPluviometro);
  unsigned long n = basculadas;
  basculadas = 0;
  portEXIT_CRITICAL(&travaPluviometro);
  return n;
}

// Distância até a água em cm; NAN se o eco não voltou.
float lerDistanciaCm() {
  digitalWrite(PINO_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PINO_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PINO_TRIG, LOW);
  unsigned long ecoUs = pulseIn(PINO_ECHO, HIGH, TIMEOUT_ECO_US);
  if (ecoUs == 0) return NAN;
  return ecoUs * 0.0343f / 2.0f;  // som a 343 m/s, ida e volta
}

// nivel_cm = altura do sensor - distância medida. Sem eco, mantém o último nível válido.
void atualizarNivel() {
  float distancia = lerDistanciaCm();
  if (isnan(distancia)) {
    falhasDoSensor++;
    if (falhasDoSensor % 10 == 1) Serial.println("[sensor] ultrassom sem eco: mantendo o ultimo nivel");
    return;
  }
  nivelCm = constrain(ALTURA_SENSOR_CM - distancia, 0.0f, ALTURA_SENSOR_CM);
}

int lerBateriaPct() {
  // Em campo: divisor de tensão da bateria. Aqui o potenciômetro entrega 0-100 % direto.
  return (int)(analogRead(PINO_BATERIA) * 100L / 4095L);
}

// ---------------------------------------------------------------------------
// Sirene (regra local OU comando) e estado publicado
// ---------------------------------------------------------------------------
void publicarEstadoSirene(const char* gatilho) {
  if (!mqtt.connected() || !relogioCerto()) return;  // sem rede só a sirene importa; o estado vai na reconexão
  char iso[25];
  formatarIso(time(nullptr), iso, sizeof(iso));
  JsonDocument doc;
  doc["sirene"] = sireneTocando ? "ligada" : "desligada";
  doc["motivo"] = sirenePorRegra ? "regra_local" : gatilho;  // se a regra local segura a sirene, o motivo é ela
  doc["em"] = iso;
  char saida[128];
  serializeJson(doc, saida, sizeof(saida));
  mqtt.publish(topicoEstado, saida);
  Serial.printf("[sirene] estado publicado %s\n", saida);
}

// Liga/desliga de fato quando o resultado (regra OU comando) muda. Devolve true se mudou.
bool atualizarSirene(const char* gatilho) {
  bool deveTocar = sirenePorRegra || sirenePorComando;
  if (deveTocar == sireneTocando) return false;
  sireneTocando = deveTocar;
  if (!deveTocar) {
    noTone(PINO_BUZZER);
    bipeLigado = false;
  }
  Serial.printf("[sirene] %s (%s)\n", deveTocar ? "LIGADA" : "desligada", gatilho);
  publicarEstadoSirene(gatilho);
  return true;
}

// Bipes sem delay(): a cada BIPE_MS alterna entre som e silêncio.
void tocarSirene() {
  if (!sireneTocando) return;
  bool fase = (millis() / BIPE_MS) % 2 == 0;
  if (fase == bipeLigado) return;
  bipeLigado = fase;
  if (fase) tone(PINO_BUZZER, FREQUENCIA_SIRENE_HZ);
  else noTone(PINO_BUZZER);
}

void vencerComando() {
  if (sirenePorComando && (long)(millis() - comandoAteMs) >= 0) {
    sirenePorComando = false;
    Serial.println("[comando] prazo da sirene acabou");
    atualizarSirene("comando");
  }
}

// ---------------------------------------------------------------------------
// REGRA LOCAL — não usa Wi-Fi, MQTT nem relógio: só o nível e as cotas
// ---------------------------------------------------------------------------
Estado classificar(float nivel) {
  if (nivel >= COTA_TRANSBORDO_CM) return ESTADO_TRANSBORDO;
  if (nivel >= COTA_ALERTA_CM) return ESTADO_ALERTA;
  if (nivel >= COTA_ATENCAO_CM) return ESTADO_ATENCAO;
  return ESTADO_NORMAL;
}

void aplicarRegraLocal() {
  Estado novo = classificar(nivelCm);
  digitalWrite(PINO_LED_VERDE, novo == ESTADO_NORMAL ? HIGH : LOW);
  digitalWrite(PINO_LED_AMARELO, novo == ESTADO_ATENCAO ? HIGH : LOW);
  digitalWrite(PINO_LED_VERMELHO, novo >= ESTADO_ALERTA ? HIGH : LOW);
  sirenePorRegra = (novo >= ESTADO_ALERTA);

  if (novo != estadoAtual) {
    estadoAtual = novo;
    if (novo == ESTADO_NORMAL) Serial.printf("[regra local] NORMAL: nivel %.1f cm, LED verde\n", nivelCm);
    if (novo == ESTADO_ATENCAO) Serial.printf("[regra local] ATENCAO: nivel %.1f cm, LED amarelo\n", nivelCm);
    if (novo == ESTADO_ALERTA) Serial.printf("[regra local] ALERTA: sirene ligada (nivel %.1f cm)\n", nivelCm);
    if (novo == ESTADO_TRANSBORDO) Serial.printf("[regra local] TRANSBORDO: sirene ligada (nivel %.1f cm)\n", nivelCm);
  }
  atualizarSirene("regra_local");
}

// ---------------------------------------------------------------------------
// Comando da sirene (contrato 3.2) — assinatura exigida pelo PubSubClient
// ---------------------------------------------------------------------------
void aoReceberComando(char* topico, byte* payload, unsigned int tamanho) {
  JsonDocument cmd;
  DeserializationError erro = deserializeJson(cmd, payload, tamanho);
  if (erro) {
    Serial.printf("[comando] ignorado: JSON invalido (%s)\n", erro.c_str());
    return;
  }
  const char* acao = cmd["acao"] | "";
  if (strcmp(acao, "ligar") == 0) {
    int segundos = cmd["segundos"] | SEGUNDOS_PADRAO_SIRENE;
    if (segundos < 1 || segundos > SEGUNDOS_MAXIMO_SIRENE) segundos = SEGUNDOS_PADRAO_SIRENE;
    const char* nivelAlerta = cmd["nivel"] | "?";
    const char* alertaId = cmd["alerta_id"] | "-";
    sirenePorComando = true;
    comandoAteMs = millis() + (unsigned long)segundos * 1000UL;
    Serial.printf("[comando] ligar sirene por %d s (nivel %s, alerta %s)\n", segundos, nivelAlerta, alertaId);
  } else if (strcmp(acao, "desligar") == 0) {
    // Só cancela o comando: se o nível estiver no alerta, a regra local mantém a sirene ligada.
    sirenePorComando = false;
    Serial.println("[comando] desligar sirene");
  } else {
    Serial.printf("[comando] ignorado: acao desconhecida '%s'\n", acao);
    return;
  }
  if (!atualizarSirene("comando")) publicarEstadoSirene("comando");  // responde mesmo se nada mudou
}

// ---------------------------------------------------------------------------
// Leituras: buffer circular (guarda-e-reenvia) e publicação
// ---------------------------------------------------------------------------
void guardarLeitura(const Leitura& leitura) {
  int posicao = (inicioBuffer + qtdBuffer) % TAMANHO_BUFFER;
  pendentes[posicao] = leitura;
  if (qtdBuffer < TAMANHO_BUFFER) {
    qtdBuffer++;
  } else {
    // Buffer cheio: a leitura nova ocupou o lugar da mais antiga.
    inicioBuffer = (inicioBuffer + 1) % TAMANHO_BUFFER;
    perdidas++;
    Serial.printf("[buffer] cheio: leitura mais antiga descartada (%lu perdidas)\n", perdidas);
  }
}

bool publicarLeitura(const Leitura& leitura) {
  // Leitura feita antes do NTP: a hora é calculada pelo tempo que passou desde a medição.
  time_t instante = leitura.epoch;
  if (instante == 0) instante = time(nullptr) - (time_t)((millis() - leitura.medidoMs) / 1000UL);
  char iso[25];
  formatarIso(instante, iso, sizeof(iso));

  JsonDocument doc;  // mesmas chaves, na mesma ordem, do contrato 3.1
  doc["estacao_id"] = ESTACAO_ID;
  doc["medido_em"] = iso;
  doc["nivel_cm"] = round((double)leitura.nivelCm * 10.0) / 10.0;  // 1 casa decimal
  doc["chuva_mm"] = (double)leitura.chuvaMm;
  doc["bateria_pct"] = leitura.bateriaPct;
  doc["seq"] = leitura.seq;
  doc["fw"] = FW_VERSAO;
  doc["origem"] = ORIGEM;

  char saida[256];
  serializeJson(doc, saida, sizeof(saida));
  bool ok = mqtt.publish(topicoLeitura, saida);
  if (ok) Serial.printf("[pub] %s\n", saida);
  return ok;
}

// Toda leitura passa pelo buffer: com rede sai na hora; sem rede espera a reconexão.
void reenviarPendentes() {
  if (qtdBuffer == 0 || !mqtt.connected() || !relogioCerto()) return;
  for (int i = 0; i < REENVIOS_POR_VOLTA && qtdBuffer > 0; i++) {
    if (!publicarLeitura(pendentes[inicioBuffer])) return;  // falhou: fica guardada para a próxima volta
    inicioBuffer = (inicioBuffer + 1) % TAMANHO_BUFFER;
    qtdBuffer--;
  }
}

void medirEGuardar() {
  unsigned long n = coletarBasculadas();
  if (digitalRead(PINO_CHUVA_FORTE) == LOW) n += BASCULADAS_CHUVA_FORTE;  // chave ligada = contato no GND

  Leitura leitura;
  leitura.epoch = relogioCerto() ? time(nullptr) : 0;
  leitura.medidoMs = millis();
  leitura.nivelCm = nivelCm;
  leitura.chuvaMm = n * MM_POR_BASCULADA;
  leitura.bateriaPct = lerBateriaPct();
  leitura.seq = ++sequencia;
  guardarLeitura(leitura);

  if (!mqtt.connected() || !relogioCerto()) {
    Serial.printf("[buffer] sem rede: leitura %lu guardada (%d/%d) nivel %.1f cm chuva %.2f mm\n",
                  leitura.seq, qtdBuffer, TAMANHO_BUFFER, leitura.nivelCm, leitura.chuvaMm);
  }
}

// ---------------------------------------------------------------------------
// Rede: Wi-Fi, NTP e MQTT — nada aqui bloqueia a regra local por muito tempo
// ---------------------------------------------------------------------------
void conectarMqtt() {
  // Sufixo aleatório: no broker público, dois simuladores com o mesmo id derrubariam um ao outro.
  char clientId[48];
  snprintf(clientId, sizeof(clientId), "vigia-%s-%08lx", ESTACAO_ID, (unsigned long)random(0x7FFFFFFF));
  Serial.printf("[mqtt] conectando a %s:%u\n", MQTT_HOST, (unsigned int)MQTT_PORTA);
  // LWT: se a estação cair sem avisar, o broker publica "offline" (retido) no tópico de status.
  if (mqtt.connect(clientId, topicoStatus, 1, true, "offline")) {
    mqttOk = true;
    mqtt.publish(topicoStatus, "online", true);
    mqtt.subscribe(topicoComando, 1);
    Serial.printf("[mqtt] ok, publicando em %s\n", topicoLeitura);
    if (qtdBuffer > 0) Serial.printf("[reenvio] %d leitura(s) guardada(s) vao ser publicadas agora\n", qtdBuffer);
    publicarEstadoSirene(sirenePorRegra ? "regra_local" : "comando");
  } else {
    Serial.printf("[mqtt] falhou (rc=%d), nova tentativa em %lu s\n", mqtt.state(), INTERVALO_RECONEXAO_MS / 1000UL);
  }
}

void manterRede() {
  if (!redeIniciada) {
    if (millis() < ATRASO_REDE_DEMO_MS) return;
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.begin(WIFI_SSID, WIFI_SENHA, 6);  // canal 6: conexão imediata no Wokwi
    redeIniciada = true;
    Serial.printf("[wifi] conectando a %s\n", WIFI_SSID);
  }

  bool wifiAgora = (WiFi.status() == WL_CONNECTED);
  if (wifiAgora != wifiOk) {
    wifiOk = wifiAgora;
    if (wifiOk) {
      Serial.printf("[wifi] ok, IP %s\n", WiFi.localIP().toString().c_str());
      configTime(0, 0, NTP_SERVIDOR_1, NTP_SERVIDOR_2);  // fuso 0: medido_em sai em UTC
    } else {
      Serial.println("[wifi] caiu: a regra local continua e as leituras ficam no buffer");
    }
  }
  if (mqttOk && !mqtt.connected()) {
    mqttOk = false;
    Serial.println("[mqtt] caiu: as leituras ficam no buffer ate a reconexao");
  }
  if (!wifiOk) return;

  if (!relogioAnunciado && relogioCerto()) {
    relogioAnunciado = true;
    char iso[25];
    formatarIso(time(nullptr), iso, sizeof(iso));
    Serial.printf("[ntp] ok, %s\n", iso);
  }
  bool horaDeTentar = ultimaTentativaMqttMs == 0 || millis() - ultimaTentativaMqttMs >= INTERVALO_RECONEXAO_MS;
  if (!mqtt.connected() && horaDeTentar) {
    ultimaTentativaMqttMs = millis();
    conectarMqtt();  // pode levar alguns segundos se o broker não responder (ver README, limitações)
  }
}

// ---------------------------------------------------------------------------
// Arduino
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.printf("VigIA, estacao %s, firmware %s\n", ESTACAO_ID, FW_VERSAO);
  Serial.printf("cotas: atencao %.0f cm, alerta %.0f cm, transbordo %.0f cm\n",
                COTA_ATENCAO_CM, COTA_ALERTA_CM, COTA_TRANSBORDO_CM);

  pinMode(PINO_TRIG, OUTPUT);
  pinMode(PINO_ECHO, INPUT);
  pinMode(PINO_PLUVIOMETRO, INPUT_PULLUP);
  pinMode(PINO_CHUVA_FORTE, INPUT_PULLUP);
  pinMode(PINO_LED_VERDE, OUTPUT);
  pinMode(PINO_LED_AMARELO, OUTPUT);
  pinMode(PINO_LED_VERMELHO, OUTPUT);
  pinMode(PINO_BUZZER, OUTPUT);
  analogReadResolution(12);
  attachInterrupt(digitalPinToInterrupt(PINO_PLUVIOMETRO), aoBascular, CHANGE);

  snprintf(topicoLeitura, sizeof(topicoLeitura), "%s/sensores/%s/leitura", MQTT_PREFIXO, ESTACAO_ID);
  snprintf(topicoStatus, sizeof(topicoStatus), "%s/sensores/%s/status", MQTT_PREFIXO, ESTACAO_ID);
  snprintf(topicoComando, sizeof(topicoComando), "%s/atuadores/%s/sirene", MQTT_PREFIXO, ESTACAO_ID);
  snprintf(topicoEstado, sizeof(topicoEstado), "%s/estado", topicoComando);

  mqtt.setServer(MQTT_HOST, MQTT_PORTA);
  mqtt.setCallback(aoReceberComando);
  mqtt.setBufferSize(512);   // o padrão (256) fica justo para tópico + JSON da leitura
  mqtt.setKeepAlive(30);
  mqtt.setSocketTimeout(5);

  // A regra local já vale antes de qualquer tentativa de rede.
  atualizarNivel();
  aplicarRegraLocal();

  Serial.println("Clique no HC-SR04 e mude a distancia: 300 cm = normal, 180 cm = alerta.");
  Serial.println("Botao azul = 1 basculada (0,25 mm). Chave = chuva forte. Potenciometro = bateria.");
}

void loop() {
  unsigned long agora = millis();

  // 1) Regra local primeiro: é o que protege o morador mesmo sem internet.
  if (agora - ultimaRegraMs >= INTERVALO_REGRA_MS) {
    ultimaRegraMs = agora;
    atualizarNivel();
    aplicarRegraLocal();
  }
  vencerComando();
  tocarSirene();

  // 2) Rede, quando houver.
  manterRede();
  mqtt.loop();

  // 3) Leitura periódica: sempre entra no buffer e sai dele quando há conexão e relógio certo.
  if (agora - ultimaPublicacaoMs >= INTERVALO_PUBLICACAO_MS) {
    ultimaPublicacaoMs = agora;
    medirEGuardar();
  }
  reenviarPendentes();
}
