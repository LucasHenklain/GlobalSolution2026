"""Seções do PDF de entregáveis, na ordem da rubrica. Cada função devolve HTML."""

from __future__ import annotations

import re

from docs.pdf.gerar_pdf import bloco, br, esc, figura, git, ler, markdown_simples, metricas, rubrica, tabela

EQUIPE = [
    ("Lucas Dalmas Batista e Souza", "RM551178"),
    ("Lucas Emanuel de Mélo Silva", "RM97881"),
    ("Kayque Moraes Dias", "RM97592"),
    ("Lucas Moraes Henklain da Silva", "RM99350"),
    ("Vinicius Pinheiro", "RM99198"),
]
P = "docs/evidencias/prints/"
CI = "docs/evidencias/ci_local/"


def _powerbi() -> str:
    """Prints do Power BI, se a equipe os tiver feito (kit em dados/powerbi). Sem os prints, o PDF diz o que existe."""
    from docs.pdf.gerar_pdf import RAIZ

    painel, medida = P + "40_powerbi_painel.png", P + "41_powerbi_medida.png"
    if not (RAIZ / painel).exists():
        return (
            '<p class="pequeno">O painel oficial é o Streamlit, que roda com um comando e lê o mesmo gold. O arquivo <code>.dax</code> e o kit '
            "<code>python -m dados.powerbi.exportar_kit</code> permitem montar o mesmo painel no Power BI.</p>"
        )
    figuras = figura(painel, "As mesmas medidas no Power BI, sobre os Parquet do gold, com filtros de estação e de data (temporal de 24/01/2025).")
    if (RAIZ / medida).exists():
        figuras += figura(medida, "Fórmula DAX de uma das medidas na barra de fórmulas do Power BI.")
    return (
        "<p><b>No Power BI.</b> As medidas de <code>dados/powerbi/medidas.dax</code> foram montadas no Power BI Desktop sobre os Parquet do gold "
        "(kit gerado por <code>python -m dados.powerbi.exportar_kit</code>); os valores conferem com os calculados em Python.</p>" + figuras
    )


def _link_do_video() -> str:
    m = re.search(r"\*\*Vídeo pitch \(3 min\):\*\*\s*(.+)", ler("README.md"))
    return m.group(1).strip() if m else "[A PREENCHER]"


def capa() -> str:
    linhas = "".join(f"<tr><td>{nome}</td><td>{rm}</td></tr>" for nome, rm in EQUIPE)
    return f"""
<section class="capa">
  <div class="faixa">
    <div class="marca">Vig<span>IA</span></div>
    <div class="sub">Alerta comunitário de enchentes</div>
    <div class="frase">Quem mora perto de córrego só descobre que vai alagar quando a água já está na porta.
    O VigIA mede o córrego e a chuva, prevê o transbordo com até uma hora de antecedência e avisa em linguagem simples —
    no celular, por SMS e pela sirene, mesmo com internet ruim.</div>
  </div>
  <div>
    <p class="meta"><b>Global Solution 2026/2 · CitizenTech</b><br>FIAP · Engenharia de Software · 4º ano · Turma 4ESOA · <b>Grupo 14</b></p>
    <table><tr><th>Integrante</th><th>RM</th></tr>{linhas}</table>
    <p class="meta">Vídeo pitch: {esc(_link_do_video())}</p>
    <p class="pequeno">Entregáveis de cada área: solução, arquitetura, prints, dashboards e evidências. Novembro de 2026.</p>
  </div>
</section>"""


def resumo() -> str:
    m = metricas().get("teste", {})
    a, d = m.get("antes_regra_limiar_fixo", {}), m.get("depois_ia", {})
    i = m.get("implantado_ia_mais_regra", {})
    return f"""
<section>
<h1>1. Resumo: o que estamos entregando</h1>
<p><b>Problema.</b> Enchentes-relâmpago em córregos urbanos. O morador de área de risco só percebe o perigo quando a água já subiu.
<b>Solução.</b> Estações de baixo custo (ESP32) medem nível e chuva; um pipeline organiza os dados em camadas; uma IA prevê o
transbordo na próxima hora; um agente de regras decide o alerta e o envia ao app, por SMS e à sirene; o morador relata
ocorrências; a Defesa Civil prioriza pelo painel.</p>
<div class="kpis">
  <div class="kpi"><div class="a">Eventos avisados com 30 min ou mais</div><div class="v">{br(d.get("avisados_30min_pct", "?"))}%</div><div class="r">antes: {br(a.get("avisados_30min_pct", "?"))}%</div></div>
  <div class="kpi"><div class="a">Antecedência mediana do alerta</div><div class="v">{d.get("antecedencia_mediana_min", 0):.0f} min</div><div class="r">antes: {a.get("antecedencia_mediana_min", 0):.0f} min</div></div>
  <div class="kpi"><div class="a">Alarmes falsos no teste</div><div class="v">{d.get("alarmes_falsos", "?")}</div><div class="r">antes: {a.get("alarmes_falsos", "?")}</div></div>
  <div class="kpi"><div class="a">F1 por janela de 10 min</div><div class="v">{br(round(d.get("f1", 0), 2))}</div><div class="r">antes: {br(round(a.get("f1", 0), 2))}</div></div>
</div>
<p class="pequeno"><b>Política implantada no protótipo (IA + regra de nível como rede de segurança):</b>
{br(i.get("avisados_30min_pct", "?"))}% dos eventos avisados com 30 min ou mais, mediana de {i.get("antecedencia_mediana_min", 0):.0f} min,
100% dos eventos avisados antes — ao custo de {i.get("alarmes_falsos", "?")} alarmes falsos no período (a regra sozinha gera {a.get("alarmes_falsos", "?")}).</p>
<p class="pequeno">"Antes" = regra de limiar fixo (alerta quando o nível passa da cota). "Depois" = modelo de IA sozinho. Teste com dados de 2024–2025
que o modelo nunca viu ({a.get("eventos", "?")} transbordos). Chuva real do INMET; nível dos córregos simulado.</p>
<h2>Onde está cada item da rubrica</h2>
{tabela(["Área", "Critério", "Onde ver neste PDF", "Onde está no projeto"], [
    ["1 · IA", "IA aplicada (1,5)", "seção 6.1", "<code>ia/treinar.py</code>, <code>ia/modelo.py</code>, <code>ia/servico.py</code>"],
    ["1 · IA", "Regras e agente documentados (1)", "seção 6.2", "<code>ia/agente.py</code>, <code>ia/mensagens.py</code>"],
    ["1 · IA", "Demonstração com entrada e saída (0,5)", "seção 6.3", "<code>python -m ia.demonstrar</code>"],
    ["1 · IA", "Lógica e ganho, antes × depois (1)", "seção 6.4", "<code>ia/avaliacao.py</code>, <code>ia/modelos/metricas.json</code>"],
    ["2 · Dados", "Estrutura em camadas (1)", "seção 7.1", "<code>dados/camadas.py</code>, <code>dados/contratos/</code>"],
    ["2 · Dados", "Ingestão e processamento (1)", "seção 7.2", "<code>dados/ingestao/</code>, <code>dados/processamento/</code>, <code>dados/pipeline.py</code>"],
    ["2 · Dados", "Dashboard com 3+ indicadores e filtros (1,5)", "seção 7.3", "<code>dados/dashboard/app.py</code>"],
    ["2 · Dados", "Funções analíticas estilo DAX (0,5)", "seção 7.4", "<code>dados/medidas.py</code>, <code>dados/powerbi/medidas.dax</code>"],
    ["3 · MVP", "4+ telas funcionais (1)", "seção 8.1", "<code>mvp/web/</code>"],
    ["3 · MVP", "2+ sensores (1)", "seção 8.2", "<code>mvp/iot/firmware/</code>, <code>mvp/iot/emulador.py</code>"],
    ["3 · MVP", "Fluxo completo (1)", "seção 8.3", "<code>python -m devops.demo</code> · <code>docker compose up</code>"],
    ["3 · MVP", "Diagrama de arquitetura (1)", "seção 5", "<code>docs/diagramas/arquitetura.svg</code>"],
    ["4 · DevOps", "Organização por módulos e Git (0,5)", "seção 9.1", "pastas por área; histórico do Git"],
    ["4 · DevOps", "Docker, CI/CD, monitoramento (1)", "seção 9.2", "<code>Dockerfile</code>, <code>docker-compose.yml</code>, <code>.github/workflows/ci.yml</code>, <code>devops/</code>"],
    ["4 · DevOps", "2+ práticas de segurança (0,5)", "seção 9.3", "<code>mvp/web/seguranca.py</code>, <code>validacao.py</code>"],
    ["4 · DevOps", "Plano com 5+ casos e evidência (1)", "seção 9.4", "<code>devops/qualidade/PLANO_DE_TESTES.md</code>, <code>tests/</code>"],
])}
<div class="aviso"><b>Transparência.</b> A chuva é medição real do INMET. O nível dos córregos, as 4 estações e o número de moradores
por área são simulados e isso está dito em cada tela e em cada tabela. A chuva de 10 em 10 minutos é o total horário do INMET
repartido dentro da hora pela simulação. Os números da IA valem para esse cenário simulado.
O pipeline rodou no GitHub Actions e localmente; as duas evidências estão na seção 9.2.</div>
</section>"""


def problema() -> str:
    return f"""
<section class="secao">
<h1>2. O problema e o cidadão</h1>
<p><b>Cidadão beneficiado.</b> Famílias que moram às margens de córregos urbanos em área de risco — em geral baixa renda,
celular simples, internet pré-paga e instável. <b>Segundo beneficiado:</b> o agente da Defesa Civil e a liderança comunitária,
que precisam decidir onde agir primeiro com poucos recursos.</p>
<p><b>O problema.</b> Em córregos urbanos canalizados, entre a pancada de chuva e o transbordo passam dezenas de minutos.
O aviso que existe hoje, quando existe, é a própria água subindo ou um alerta genérico para a cidade inteira.
Sem antecedência, não dá tempo de levantar móveis, salvar documentos e remédios, tirar idosos e crianças de casa.</p>
{tabela(["Dado real", "Fonte"], [
    ["Mais de <b>8,9 milhões</b> de pessoas vivem em áreas de risco em <b>1.942 municípios</b> (35% dos municípios do país)", "Nota técnica da Casa Civil, divulgada pela Agência Brasil em maio de 2024"],
    ["Entre 1991 e 2022: <b>3.890 mortes</b> e <b>8,2 milhões</b> de desalojados ou desabrigados por inundações, enxurradas e deslizamentos", "Mesma nota técnica (Agência Brasil, 2024)"],
    ["Em 2010, <b>8.270.127</b> pessoas viviam em áreas de risco nos 872 municípios monitorados; 9,2% eram crianças de até 5 anos e 8,5% idosos", "IBGE e Cemaden, População em áreas de risco no Brasil (2018)"],
    ["Aviso com 24 horas de antecedência pode reduzir os danos de um evento em <b>até 30%</b>", "Global Commission on Adaptation, citada pela OMM na iniciativa Early Warnings for All"],
])}
<h2>Por que escolhemos este problema</h2>
<p>Avaliamos os temas do enunciado (enchentes e ondas de calor, pequeno produtor, desperdício de água, zeladoria,
acessibilidade) contra cinco critérios. Enchente em córrego urbano foi o único que atendeu bem a todos:</p>
{tabela(["Critério", "Como o problema atende"], [
    ["IoT plausível com 2+ sensores", "nível do córrego (ultrassom) e chuva (pluviômetro de báscula) cabem num ESP32 de baixo custo"],
    ["Gera dados para pipeline e dashboard com decisão", "série temporal de 10 em 10 minutos por estação; a decisão é para onde mandar equipe primeiro"],
    ["IA com ganho mensurável", "antecedência do alerta, eventos avisados e alarmes falsos, comparados com a regra de limiar fixo"],
    ["Cidadão e ODS evidentes", "morador de área de risco; ODS 11, 13, 3, 10 e 9"],
    ["Funciona com conectividade ruim", "a estação decide e toca a sirene sozinha; SMS de 160 caracteres; página leve sem JavaScript"],
])}
<h1>3. Conexão com os ODS</h1>
{tabela(["ODS", "Meta", "Como o VigIA contribui"], [
    ["<b>11</b> Cidades e comunidades sustentáveis", "11.5 — reduzir mortes e pessoas afetadas por desastres, com foco nos pobres e vulneráveis", "alerta antecipado para áreas de risco; priorização da resposta da Defesa Civil"],
    ["<b>13</b> Ação contra a mudança global do clima", "13.1 — reforçar a resiliência e a capacidade de adaptação a riscos climáticos", "infraestrutura de baixo custo para eventos extremos de chuva, que ficam mais frequentes"],
    ["<b>3</b> Saúde e bem-estar", "3.d — reforçar o alerta precoce e a gestão de riscos à saúde", "menos exposição à água de enchente, afogamentos e doenças; orientação clara do que fazer"],
    ["<b>10</b> Redução das desigualdades", "10.2 — promover a inclusão de todos", "funciona em celular simples (SMS), com linguagem simples, alto contraste e letras grandes"],
    ["<b>9</b> Indústria, inovação e infraestrutura", "9.c — ampliar o acesso às tecnologias de informação", "estação com componentes baratos e software aberto, replicável por prefeituras pequenas"],
])}
</section>"""


def solucao() -> str:
    return f"""
<section class="secao">
<h1>4. A solução</h1>
<h2>Como funciona</h2>
<ol>
  <li><b>Medir.</b> Uma estação ESP32 na margem mede o nível do córrego (ultrassom) e a chuva (pluviômetro) e publica por MQTT.
  Se o nível passa da cota de alerta, ela mesma acende o LED vermelho e toca a sirene — sem depender de internet.</li>
  <li><b>Organizar.</b> O gateway valida cada leitura na porta; o pipeline guarda o bruto (bronze), limpa (silver) e calcula as
  variáveis de 10 em 10 minutos (gold).</li>
  <li><b>Prever.</b> Um modelo de machine learning lê o gold e estima a chance de transbordo nos próximos 60 minutos.</li>
  <li><b>Decidir e avisar.</b> O agente de alerta aplica 10 regras: define o nível (verde, amarelo, laranja, vermelho), escreve a
  mensagem com o motivo e o que fazer, envia ao app, enfileira o SMS e aciona a sirene.</li>
  <li><b>Ouvir.</b> O morador relata bueiro entupido, lixo no córrego ou ponto de alagamento; a ocorrência vai para o data lake.</li>
  <li><b>Agir.</b> A Defesa Civil vê no painel onde agir primeiro e acompanha as ocorrências.</li>
</ol>
<h2>Quem participa do ecossistema</h2>
{tabela(["Participante", "Papel"], [
    ["Moradores de área de risco", "recebem o alerta, relatam ocorrências, validam se o aviso é entendido"],
    ["Defesa Civil municipal e subprefeituras", "definem as cotas, operam o painel, acionam equipes e sirenes"],
    ["Lideranças e associações de bairro, agentes comunitários de saúde", "cadastram vizinhos, cuidam da estação, levam o aviso a quem não tem celular"],
    ["Cemaden, INMET e centros de gerenciamento de emergências", "fontes de chuva e de alertas regionais que complementam os sensores locais"],
    ["Universidades e empresas parceiras", "fabricação e manutenção das estações, operadora de SMS"],
])}
<h2>Simples, segura, inclusiva e útil fora do cenário ideal</h2>
{tabela(["Situação", "O que o VigIA faz"], [
    ["A estação fica sem internet", "decide sozinha pela regra de nível e toca a sirene; guarda 60 leituras e reenvia quando a rede volta"],
    ["O morador tem celular simples ou sem dados", "SMS de até 160 caracteres, sem acento; sirene na rua"],
    ["Internet lenta", "páginas em HTML leve, sem JavaScript; <code>/status.txt</code> em texto puro"],
    ["Baixa visão ou dificuldade de leitura", "cor + ícone + palavra em cada nível; alto contraste e letras grandes no perfil; frases curtas"],
    ["A IA ou o pipeline falham", "a regra de nível continua valendo; o app mostra o último estado conhecido e a hora da leitura"],
    ["Dados pessoais", "só o necessário; telefone cifrado; exportar e excluir conta (LGPD)"],
])}
<h2>Como o impacto será medido e ampliado</h2>
{tabela(["Indicador", "Como medir", "Onde já está no protótipo"], [
    ["Antecedência do alerta (minutos)", "tempo entre o primeiro alerta de risco alto e o início do transbordo", "medida do dashboard e avaliação da IA"],
    ["Eventos avisados com 30+ min (%)", "transbordos com alerta anterior ÷ transbordos", "medida do dashboard"],
    ["Alarmes falsos por estação por ano", "alertas sem transbordo na hora seguinte", "avaliação da IA"],
    ["Moradores cadastrados por área", "contas ativas ÷ moradores estimados", "banco do app"],
    ["Tempo de atendimento das ocorrências", "da abertura ao status resolvida", "painel do agente e gold"],
    ["Compreensão do alerta", "% de pessoas que entendem a tela sem explicação", "roteiro de validação (seção 10)"],
])}
<p><b>Ampliação.</b> (1) piloto em um córrego com a Defesa Civil local, recalibrando o modelo com nível medido de verdade;
(2) cada estação nova entra só com uma linha no catálogo; (3) integração com alertas do Cemaden e com a operadora de SMS;
(4) modelo de negócio: serviço para prefeituras, com custo por estação instalada e mantida por parceiros locais.</p>
</section>"""


def arquitetura() -> str:
    return f"""
<section class="secao">
<h1>5. Arquitetura geral</h1>
{rubrica("<b>Área 3 · Arquitetura (1 pt):</b> diagrama da arquitetura geral, com as áreas e como se conectam.")}
{figura("docs/diagramas/arquitetura.png", "Arquitetura do VigIA. Setas cheias: dados. Setas tracejadas: comando de volta à estação.")}
<h2>Como as áreas se integram (diferencial)</h2>
{tabela(["Integração", "Como acontece", "Código"], [
    ["Sensores alimentam o dashboard", "leitura MQTT → gateway → bronze → silver → gold → painel ao vivo", "<code>dados/ingestao/gateway_mqtt.py</code> → <code>dados/pipeline.py</code>"],
    ["A IA usa os dados do pipeline", "treina e prevê com as mesmas colunas do gold; uma única função calcula as features nos dois casos", "<code>dados/processamento/features.py</code>, <code>ia/dataset.py</code>"],
    ["A IA devolve dado ao pipeline", "probabilidade, nível de risco e alertas são gravados no gold e aparecem no dashboard", "<code>ia/servico.py</code> (<code>gravar_gold</code>)"],
    ["A IA aciona o app e a estação", "API interna com token (situação e alertas) e comando MQTT da sirene", "<code>ia/servico.py</code> → <code>mvp/web/rotas_interno.py</code>"],
    ["O morador alimenta o data lake", "ocorrências do app são puxadas pelo pipeline, sem dados pessoais", "<code>dados/processamento/bronze.py</code> (<code>ingerir_ocorrencias</code>)"],
    ["DevOps cobre o fluxo inteiro", "o teste de fumaça da CI publica leituras por MQTT e confere o alerta no app", "<code>devops/verificar_pilha.py</code>"],
])}
<p class="pequeno">Tecnologias (todas do conteúdo do curso): Python, FastAPI, Jinja2, SQLite, Streamlit, pandas, DuckDB, Parquet, scikit-learn,
MQTT (Mosquitto, paho-mqtt), ESP32 no Wokwi (C++/Arduino), Docker e Docker Compose, GitHub Actions, pytest, ruff, bandit, pip-audit.</p>
</section>"""


def area_ia() -> str:
    m = metricas()
    t = m.get("teste", {})
    a, d, i = t.get("antes_regra_limiar_fixo", {}), t.get("depois_ia", {}), t.get("implantado_ia_mais_regra", {})
    q = t.get("qualidade_da_probabilidade", {})
    lim = m.get("limiares", {})
    linhas = [
        ("Eventos de transbordo no teste", "eventos", ""),
        ("Eventos avisados com 30 min ou mais", "avisados_30min_pct", " %"),
        ("Eventos avisados antes (10 min ou mais)", "avisados_pct", " %"),
        ("Antecedência mediana do alerta", "antecedencia_mediana_min", " min"),
        ("Antecedência média do alerta", "antecedencia_media_min", " min"),
        ("Alarmes falsos (total no período)", "alarmes_falsos", ""),
        ("Alarmes falsos por estação por ano", "alarmes_falsos_por_estacao_ano", ""),
        ("Precisão (por janela de 10 min)", "precisao", ""),
        ("Recall (por janela de 10 min)", "recall", ""),
        ("F1", "f1", ""),
    ]
    comparacao = tabela(
        ["Indicador", "Antes: regra de limiar fixo", "Depois: IA", "Implantado: IA + regra"],
        [[r, f"{br(a.get(k, '?'))}{u}", f"<b>{br(d.get(k, '?'))}{u}</b>", f"{br(i.get(k, '?'))}{u}"] for r, k, u in linhas],
        numericas=(1, 2, 3),
    )
    por_estacao = tabela(
        ["Estação", "Transbordos", "Avisados 30+ min: antes → depois", "Antecedência mediana: antes → depois", "Alarmes falsos: antes → depois"],
        [
            [e, v["antes"]["eventos"], f"{br(v['antes']['avisados_30min_pct'])}% → <b>{br(v['depois']['avisados_30min_pct'])}%</b>",
             f"{v['antes']['antecedencia_mediana_min']:.0f} → <b>{v['depois']['antecedencia_mediana_min']:.0f} min</b>",
             f"{v['antes']['alarmes_falsos']} → <b>{v['depois']['alarmes_falsos']}</b>"]
            for e, v in t.get("por_estacao", {}).items()
        ],
        numericas=(1, 2, 3, 4),
    )  # fmt: skip
    return f"""
<section class="secao">
<h1>6. Área 1 — IA e automação</h1>
<h2>6.1 IA aplicada</h2>
{rubrica("<b>IA aplicada (1,5 pt):</b> funcionalidade de IA implementada que resolve parte do problema.")}
<p><b>O que a IA faz:</b> a cada janela de 10 minutos, para cada estação, estima a <b>probabilidade de o córrego transbordar nos
próximos 60 minutos</b>. É a parte do problema que a regra de nível não resolve: quando o nível passa da cota, já é tarde.
A IA olha principalmente a chuva que acabou de cair e avisa enquanto o córrego ainda está baixo.</p>
{tabela(["Item", "Descrição"], [
    ["Algoritmo", f"{esc(m.get('algoritmo', ''))} — árvores de decisão em sequência; capta relações não lineares (chuva forte com solo encharcado escoa muito mais)"],
    ["Alvo", "1 se o nível atinge a cota de transbordo em alguma das 6 janelas seguintes; 0 caso contrário"],
    ["Entradas (11)", "nível em % da cota; subida em 10 e 30 min; projeção do nível em 30 min; chuva na janela, em 30 min, 1 h, 3 h, 24 h e 72 h; código da estação"],
    ["Dados", f"gold do pipeline: 1,47 milhão de janelas (4 estações, 2019–2025). Treino {m.get('dados', {}).get('treino', '')}; validação 2023; teste 2024–2025"],
    ["Separação", "por tempo, e não ao acaso: o modelo nunca vê o futuro"],
    ["Desbalanceamento", f"mais de 99% das janelas são de tempo seco; o treino usa todas as janelas com chuva ou nível alto e 3% das demais ({br(m.get('dados', {}).get('linhas_treino_amostradas', '?'))} linhas)"],
    ["Limiares de decisão", f"amarelo ≥ {br(lim.get('amarelo', '?'))} · laranja ≥ {br(lim.get('laranja', '?'))} · vermelho ≥ {br(lim.get('vermelho', '?'))}"],
    ["No protótipo", "<code>ia/servico.py</code> lê o gold a cada 2 s, calcula o risco, grava no gold, envia ao app e aciona a sirene"],
])}
<h2>6.2 Agente de alerta: regras de automação</h2>
{rubrica("<b>Prompts, agentes ou automação (1 pt):</b> as regras de automação usadas, documentadas.")}
<p>O agente (<code>ia/agente.py</code>) transforma probabilidade e leituras em decisão. Não há IA generativa em tempo de execução:
aviso de emergência precisa ser previsível, revisável pela Defesa Civil e igual com ou sem internet.</p>
{tabela(["Regra", "Condição", "Ação"], [
    ["R1", "nível ≥ cota de transbordo <b>ou</b> probabilidade ≥ limiar vermelho", "risco <b>VERMELHO</b> (perigo)"],
    ["R2", "probabilidade ≥ limiar laranja <b>ou</b> nível ≥ cota de alerta", "risco <b>LARANJA</b> (risco alto). A cota de alerta é a rede de segurança: a IA nunca avisa menos que a regra"],
    ["R3", "probabilidade ≥ limiar amarelo <b>ou</b> nível ≥ cota de atenção <b>ou</b> chuva em 1 h ≥ 15 mm", "risco <b>AMARELO</b> (atenção)"],
    ["R4", "nenhuma das anteriores", "risco <b>VERDE</b> (normal)"],
    ["R5", "modelo indisponível", "valem só as regras de nível; o sistema degrada, não para"],
    ["R6", "o risco subiu de nível", "emite alerta"],
    ["R7", "risco laranja ou vermelho há 60 min", "repete o alerta (lembrete)"],
    ["R8", "mesmo nível há menos de 60 min", "não repete (evita cansar o morador)"],
    ["R9", "30 min seguidos em verde depois de um alerta", "avisa que a situação normalizou"],
    ["R10", "alerta laranja ou vermelho", "SMS aos moradores da área + sirene por 15 s (laranja) ou 60 s (vermelho). Amarelo: só no app"],
])}
<h3>Modelos de mensagem (equivalem aos "prompts" do agente)</h3>
{tabela(["Nível", "Título", "SMS (até 160 caracteres, sem acento)"], [
    ["Amarelo", "Atenção: chuva e nível em elevação no &#123;nome&#125;", "VigIA ATENCAO: chuva forte e nivel subindo no &#123;nome&#125;. Fique atento aos proximos avisos."],
    ["Laranja", "Risco alto de enchente no &#123;nome&#125;", "VigIA RISCO ALTO: &#123;nome&#125; pode transbordar em ate 1h. Guarde documentos no alto e prepare-se para sair. Defesa Civil 199"],
    ["Vermelho", "PERIGO: enchente no &#123;nome&#125;", "VigIA PERIGO: enchente no &#123;nome&#125;. SAIA AGORA para lugar alto. Nao atravesse agua. Defesa Civil 199"],
    ["Verde", "Situação normalizada no &#123;nome&#125;", "VigIA: situacao NORMALIZADA no &#123;nome&#125;. Volte so quando a agua baixar."],
])}
<p><b>"Por quê" automático.</b> Cada alerta leva os motivos montados a partir dos próprios dados
(<code>ia/mensagens.py</code>): "choveu 40 mm na última hora", "o nível subiu 44 cm em 30 minutos",
"o córrego está em 89% da altura em que transborda", "o solo já está encharcado (92 mm em 24 horas)",
"a IA estima 95% de chance de transbordo em até 1 hora". Cada nível tem ainda 3 a 4 orientações do que fazer.</p>
<h2>6.3 Demonstração com entrada e saída</h2>
{rubrica("<b>Demonstração (0,5 pt):</b> a funcionalidade inteligente funcionando, com exemplo de entrada e saída.")}
<p>Comando <code>python -m ia.demonstrar</code>. A entrada é a janela das 16h20 (horário de Brasília) de 24/01/2025 no
Córrego Aricanduva: o nível está em 38,5 cm, que a regra fixa chama de <b>normal</b>, mas choveu 40 mm em 30 minutos.</p>
{bloco(ler("docs/evidencias/texto/ia_demonstracao.txt", "(rode python -m ia.demonstrar)"))}
<p>Na simulação, o córrego transborda uma hora depois (17h20). Na mesma tela do app o morador vê esse alerta:</p>
<div class="duas">
{figura(P + "03_minha_area_ia_antecipa.png", "App, tela Minha área às 16h20: córrego em 38 cm e a IA já indica perigo, com o porquê e o que fazer.")}
{figura(P + "06_minha_area_transbordo.png", "Mesma tela às 17h30: na simulação, o transbordo acontece uma hora depois do primeiro aviso.")}
</div>
<p>Exemplo oposto, em tempo calmo (<code>python -m ia.demonstrar --estacao EST-PIR-01 --nivel 60 --chuva-1h 8 --subida-30min 2</code>):</p>
{bloco(ler("docs/evidencias/texto/ia_demonstracao_calmo.txt"), claro=True)}
<h2>6.4 Lógica e ganho: antes × depois</h2>
{rubrica("<b>Lógica e ganho (1 pt):</b> como funciona e o que melhora, com métrica e comparação antes e depois.")}
<p><b>Antes:</b> regra de limiar fixo — alerta quando o nível passa da cota de alerta (o que um sensor sem IA faz, e o que a estação
faz sozinha). <b>Depois:</b> IA — alerta quando a probabilidade passa do limiar. As duas políticas são medidas com a mesma régua
(<code>ia/avaliacao.py</code>), por evento de transbordo: fui avisado antes? com quanto tempo? quantas vezes tocou à toa?</p>
{comparacao}
{figura("ia/modelos/avaliacao_antes_depois.png", "Antes × depois no teste 2024–2025 (dados que o modelo nunca viu).")}
<p><b>Leitura.</b> A regra fixa avisa em cima da hora: metade dos eventos com 10 minutos ou menos. A IA triplica os eventos avisados
com meia hora ou mais e quadruplica a antecedência mediana, com um terço a menos de alarmes falsos — isso é o modelo
sozinho contra a regra sozinha. A política implantada
(IA + regra como rede de segurança) avisa em 100% dos eventos, ao custo de mais alarmes — o agente trata isso com R8 (não repetir).
Qualidade da probabilidade no teste: AUC-ROC {br(q.get("auc_roc", "?"))} e AUC-PR {br(q.get("auc_pr", "?"))}
({br(q.get("janelas_positivas", "?"))} janelas positivas em {br(q.get("janelas_avaliadas", "?"))}).</p>
{por_estacao}
<div class="duas">
{figura("ia/modelos/importancia_variaveis.png", "No que a IA presta atenção: a chuva recente pesa mais do que o nível — por isso ela antecipa.")}
<div>
<h3>Como o limiar foi escolhido</h3>
<p>Na validação (2023), ficamos com o limiar mais sensível que <b>não gera mais alarmes falsos do que a regra fixa</b>.
Assim o modelo, sozinho, só pode ganhar em antecedência sem custar mais alarme à toa. Somar a regra de nível como rede de
segurança aumenta os alarmes falsos (coluna "Implantado"): foi uma escolha consciente por cobertura de 100% dos eventos.
O teste (2024–2025) só foi usado para reportar.</p>
<h3>Limites (honestidade)</h3>
<ul>
<li>O nível dos córregos é simulado; em campo o modelo precisa ser recalibrado com nível medido.</li>
<li>Com 38 eventos no teste, cada evento vale 2,6 pontos percentuais.</li>
<li>Uma variável (projeção do nível em 30 min) foi acrescentada depois da primeira avaliação no teste; o ganho foi pequeno (cerca de 8 pontos percentuais nos eventos avisados).</li>
</ul>
</div>
</div>
</section>"""


def area_dados() -> str:
    return f"""
<section class="secao">
<h1>7. Área 2 — Big data e visualização</h1>
<h2>7.1 Estrutura dos dados: data lake em camadas</h2>
{rubrica("<b>Estrutura dos dados (1 pt):</b> modelo de dados ou camadas de armazenamento, como um data lake.")}
{tabela(["Camada", "O que guarda", "Formato", "Regra"], [
    ["<b>landing</b>", "micro-lotes do gateway MQTT, um arquivo a cada 2 s", "JSONL", "escrita atômica; o pipeline move para o bronze"],
    ["<b>bronze</b>", "o bruto imutável: CSV originais do INMET, JSONL dos sensores, extrato de ocorrências do app", "CSV, JSONL, Parquet", "nunca é alterado; manifesto com origem, hash SHA-256 e data"],
    ["<b>silver</b>", "dado limpo e tipado: chuva horária do INMET e leituras das estações", "Parquet", "contrato de dados; duplicatas removidas"],
    ["<b>quarentena</b>", "leituras reprovadas, com o motivo", "Parquet, JSONL", "nada é descartado em silêncio"],
    ["<b>gold</b>", "tabelas prontas para decidir (abaixo)", "Parquet + DuckDB", "lidas pelo dashboard e pela IA"],
])}
{tabela(["Tabela do gold", "Grão", "Principais colunas"], [
    ["<code>fato_leitura</code>", "estação × janela de 10 min", "nível, % da cota, chuva na janela, chuva em 30 min/1 h/3 h/24 h/72 h, variação do nível em 10 e 30 min, estado pela regra"],
    ["<code>fato_risco</code>", "estação × janela", "probabilidade de transbordo em 60 min, nível de risco, origem da decisão (saída da IA)"],
    ["<code>fato_alerta</code>", "alerta emitido", "estação, quando, nível, probabilidade, motivo, SMS"],
    ["<code>fato_evento</code>", "evento de transbordo", "estação, início, fim, pico, duração"],
    ["<code>fato_ocorrencia</code>", "ocorrência do morador", "estação, tipo, status, datas (sem dado pessoal e sem o texto livre)"],
    ["<code>agg_diario</code>", "estação × dia", "chuva do dia, nível máximo, minutos em atenção e em transbordo, disponibilidade"],
    ["<code>dim_estacao</code>", "estação", "nome, bairro, cotas, moradores na área, posição"],
])}
<p><b>Contrato de dados</b> (<code>dados/contratos/leitura_sensor.v1.yaml</code>), aplicado no gateway e no silver:</p>
{bloco(chr(10).join(ler("dados/contratos/leitura_sensor.v1.yaml").splitlines()[3:]), claro=True)}
<h2>7.2 Ingestão e processamento: da coleta ao dado tratado</h2>
{rubrica("<b>Ingestão e processamento (1 pt):</b> o caminho dos dados, da coleta ao dado tratado.")}
{tabela(["Etapa", "O que acontece", "Código"], [
    ["1. Coleta", "estação publica JSON por MQTT a cada leitura; arquivos anuais do INMET (dado público)", "<code>mvp/iot/</code>, <code>dados/fontes/inmet/</code>"],
    ["2. Porta de entrada", "gateway confere campos, tipos, faixas, estação e data; reprovadas vão para a quarentena; válidas viram micro-lote", "<code>dados/ingestao/gateway_mqtt.py</code>"],
    ["3. Bronze", "micro-lotes e CSV copiados sem alteração, com manifesto", "<code>dados/processamento/bronze.py</code>"],
    ["4. Silver", "tipos, regras LEI-01 a LEI-07, remoção de duplicatas; −9999 do INMET vira ausente, nunca zero inventado", "<code>dados/processamento/silver.py</code>"],
    ["5. Gold", "grade de 10 min, acumulados de chuva, variação do nível, eventos, agregado diário", "<code>dados/processamento/features.py</code>, <code>gold.py</code>"],
    ["6. Consumo", "dashboard (DuckDB sobre Parquet) e IA", "<code>dados/dashboard/</code>, <code>ia/</code>"],
])}
<p>Saída real de <code>python -m dados.pipeline status</code> depois do histórico e de uma demonstração ao vivo:</p>
{bloco(ler("docs/evidencias/texto/pipeline_status.txt"))}
<p><b>Quarentena funcionando</b> (<code>python docs/ferramentas/exemplo_quarentena.py</code>): uma leitura válida e três inválidas
de propósito passam pelo gateway; as inválidas ficam guardadas com o motivo, nada é descartado em silêncio.</p>
{bloco(chr(10).join(ler("docs/evidencias/texto/quarentena_exemplo.txt").splitlines()[:11]), claro=True)}
<p class="pequeno">Histórico: 14 arquivos do INMET (122.736 horas, 1,15% sem medição) → 1,47 milhão de leituras simuladas de 10 min → gold em cerca de
30 segundos. Tempo real: um ciclo do pipeline leva menos de 1 segundo.</p>
<h2>7.3 Dashboard</h2>
{rubrica("<b>Dashboard (1,5 pt):</b> 3 ou mais indicadores com filtros que ajudam alguém a tomar uma decisão.")}
<p><b>Para quem:</b> agente da Defesa Civil. <b>Decisão:</b> para onde mandar equipe primeiro e quando reforçar o plantão.
<b>Filtros</b> (barra lateral): fonte dos dados (histórico ou sensores ao vivo), período (com atalhos), estações e nível de risco dos alertas.
<b>Indicadores:</b> chuva acumulada, nível máximo em % da cota, transbordos, alertas de risco alto, antecedência mediana e
disponibilidade dos sensores — os três primeiros comparados com o período anterior.</p>
{figura(P + "23_painel_temporal_24jan.png", "Dashboard com o filtro de período no temporal de 24/01/2025: 6 indicadores, tabela Onde agir primeiro (índice de prioridade) e nível × cotas por estação, com os alertas marcados antes do pico.")}
<div class="duas">
{figura(P + "22_painel_historico_verao.png", "Mesmo painel com outro filtro (verão 2024/25): os indicadores mudam com o contexto.", recorte=0.8)}
{figura(P + "20_painel_ao_vivo.png", "Fonte Sensores ao vivo: leituras recebidas por MQTT durante a demonstração; atualiza a cada 5 s.", recorte=0.8)}
</div>
<div class="duas">
{figura(P + "24_painel_alertas.png", "Aba Alertas e ocorrências: alertas por período e nível, horário dos transbordos (escala de plantão), tabela com o motivo e o SMS.", recorte=0.8)}
{figura(P + "26_painel_dados_monitoramento.png", "Aba Dados e monitoramento: volumes por camada, batimento dos serviços e quarentena.", recorte=0.8)}
</div>
<h2>7.4 Funções analíticas (estilo DAX)</h2>
{rubrica("<b>Funções analíticas (0,5 pt):</b> métricas, variáveis ou funções como DAX aplicadas aos indicadores.")}
<p>As medidas estão em <code>dados/medidas.py</code>: cada função recebe as tabelas já filtradas (o contexto de filtro) e devolve
um número. A fórmula DAX equivalente está na docstring e reunida em <code>dados/powerbi/medidas.dax</code>.</p>
{tabela(["Medida", "Fórmula (DAX equivalente)", "Uso"], [
    ["Chuva Acumulada", "<code>AVERAGEX(VALUES(dim_estacao[estacao_id]), CALCULATE(SUM(fato_leitura[chuva_mm])))</code>", "indicador"],
    ["Nível Máximo %", "<code>MAX(fato_leitura[nivel_pct_cota])</code>", "indicador"],
    ["Alertas Emitidos", "<code>CALCULATE(COUNTROWS(fato_alerta), fato_alerta[nivel_risco] IN &#123;&quot;laranja&quot;,&quot;vermelho&quot;&#125;)</code>", "indicador"],
    ["Antecedência Mediana", "<code>MEDIANX(fato_evento, DATEDIFF([primeiro_alerta], fato_evento[inicio], MINUTE))</code>", "indicador"],
    ["% Eventos Avisados", "<code>DIVIDE(COUNTROWS(FILTER(fato_evento, [antecedencia] &gt;= 30)), COUNTROWS(fato_evento))</code>", "indicador"],
    ["Disponibilidade %", "<code>DIVIDE(COUNTROWS(fato_leitura), [Janelas Esperadas])</code>", "indicador"],
    ["Variação %", "<code>DIVIDE([Medida] - [Medida Período Anterior], [Medida Período Anterior])</code> com <code>DATEADD</code>", "comparação com o período anterior"],
    ["Ocorrências Abertas", "<code>CALCULATE(COUNTROWS(fato_ocorrencia), fato_ocorrencia[status] &lt;&gt; &quot;resolvida&quot;)</code>", "prioridade"],
    ["Índice de Prioridade", "<code>60 * [Prob. Máxima IA] + 0.30 * MIN([Nível Máximo %], 100) + 2 * MIN([Ocorrências Abertas], 5)</code>", "tabela Onde agir primeiro"],
])}
{_powerbi()}
</section>"""


def area_mvp() -> str:
    return f"""
<section class="secao">
<h1>8. Área 3 — MVP, IoT e experiência digital</h1>
<h2>8.1 Protótipo: telas funcionais</h2>
{rubrica("<b>Protótipo (1 pt):</b> 4 ou mais telas funcionais, web ou mobile.")}
<p>App web em FastAPI + Jinja2 (<code>mvp/web/</code>), HTML leve sem JavaScript, pensado primeiro para celular. Treze telas funcionais e uma saída em texto puro;
todos os prints abaixo são do protótipo rodando, capturados por <code>docs/ferramentas/capturar_evidencias.py</code>.</p>
{tabela(["Tela", "Rota", "Quem usa", "O que faz"], [
    ["Início", "<code>/</code>", "todos", "situação de cada estação, sem login"],
    ["Cadastro e login", "<code>/cadastro</code>, <code>/entrar</code>", "todos", "conta com consentimento LGPD"],
    ["Minha área", "<code>/minha-area</code>", "morador", "risco da área, por quê, chance de transbordo, gráfico, o que fazer"],
    ["Alertas e detalhe", "<code>/alertas</code>, <code>/alertas/&#123;id&#125;</code>", "morador, agente", "histórico; motivos, orientações, SMS, quem decidiu"],
    ["Estações e detalhe", "<code>/estacoes</code>, <code>/estacoes/&#123;id&#125;</code>", "todos", "nível, cotas, chuva, bateria"],
    ["Relatar e acompanhar ocorrência", "<code>/ocorrencias/nova</code>, <code>/ocorrencias</code>", "morador", "bueiro entupido, lixo no córrego, alagamento, sirene com defeito"],
    ["Perfil", "<code>/perfil</code>", "morador", "preferências (SMS, letras grandes, alto contraste), exportar e excluir dados"],
    ["Painel do agente", "<code>/agente</code>", "agente", "sirenes, fila de ocorrências, alertas, caixa de SMS"],
    ["Telefones de emergência", "<code>/emergencia</code>", "todos", "199, 193, 192, 190 e 156 com toque para ligar (tela criada a partir da validação)"],
    ["Texto puro", "<code>/status.txt</code>", "todos", "uma linha por estação, para conexão muito ruim"],
])}
<div class="duas">
{figura(P + "01_inicio_tempo_seco.png", "Início público em tempo seco.")}
{figura(P + "07_inicio_durante_o_temporal.png", "Início durante o temporal: cada nível com cor, ícone e palavra.")}
</div>
<div class="duas">
{figura(P + "05_alerta_detalhe.png", "Detalhe do alerta: mensagem, por quê, o que fazer, texto do SMS e quem decidiu (IA).")}
{figura(P + "08_estacao_detalhe.png", "Detalhe da estação: nível contra as cotas e chuva.")}
</div>
<div class="duas">
{figura(P + "02_cadastro.png", "Cadastro com consentimento LGPD.")}
{figura(P + "11_perfil_lgpd.png", "Perfil: acessibilidade, SMS, exportar e excluir os dados.")}
</div>
<div class="tres celular">
{figura(P + "14_celular_minha_area.png", "No celular (390 px): Minha área.", recorte=2.1)}
{figura(P + "15_celular_alerta.png", "No celular: alerta.", recorte=2.1)}
{figura(P + "12_status_txt.png", "/status.txt: texto puro.")}
</div>
<h2>8.2 IoT: sensores</h2>
{rubrica("<b>IoT (1 pt):</b> 2 ou mais sensores com Arduino, TinkerCad, sensores reais ou mock.")}
{tabela(["Componente", "Tipo", "Pino", "Função"], [
    ["HC-SR04 (ultrassônico)", "<b>sensor</b>", "TRIG 5, ECHO 18", "distância até a água; nível = 400 cm − distância"],
    ["Pluviômetro de báscula (botão)", "<b>sensor</b>", "GPIO 27, interrupção", "cada basculada = 0,25 mm de chuva"],
    ["Chave chuva forte", "apoio à demonstração", "GPIO 26", "soma 8 basculadas por leitura (2 mm)"],
    ["Potenciômetro", "<b>sensor</b>", "GPIO 34 (ADC1)", "nível da bateria"],
    ["LED verde, amarelo, vermelho", "atuadores", "21, 22, 23", "estado local: normal, atenção, alerta"],
    ["Buzzer", "atuador", "GPIO 19", "sirene"],
])}
<p>Firmware em <code>mvp/iot/firmware/sketch.ino</code> (ESP32, C++/Arduino), simulado no <b>Wokwi</b> — o TinkerCad não simula ESP32 nem rede.
O firmware compila e roda no Wokwi, conecta no Wi-Fi, sincroniza o relógio, publica por MQTT num broker público e as leituras
chegam ao nosso gateway. <b>Regra local:</b> nível ≥ cota de alerta acende o LED vermelho e toca a sirene sem depender de rede.
<b>Guarda-e-reenvia:</b> sem conexão, guarda até 60 leituras com a hora original e publica quando a rede volta.</p>
{figura("mvp/iot/firmware/captura-wokwi.png", "Simulação no Wokwi (captura automática por capturar_wokwi.py): circuito à direita; no monitor serial, a estação guardando leituras enquanto o MQTT não conecta (guarda-e-reenvia) — depois elas são publicadas.")}
{figura("mvp/iot/firmware/captura-wokwi-alerta.png", "Mesmo circuito com o ultrassônico a 150 cm da água (nível 250 cm, acima da cota de alerta): a regra local acende o LED vermelho e liga a sirene, sem depender da rede.")}
<p>Leitura publicada pela estação simulada no Wokwi e recebida pelo gateway (arquivo da landing):</p>
{bloco('{"estacao_id":"EST-ARI-01","medido_em":"2026-11-17T16:16:20Z","nivel_cm":97.5,"chuva_mm":0.0,"bateria_pct":86.0,"seq":5,"fw":"1.0.0","origem":"wokwi","recebido_em":"2026-11-17T16:16:47.633Z"}', claro=True)}
<p>Além do Wokwi, <code>mvp/iot/emulador.py</code> emula as 4 estações com o mesmo payload (tempo real com cenários, ou replay de um
temporal real), aplica a mesma regra local e obedece ao comando da sirene — é o que alimenta a pilha no Docker.</p>
<h2>8.3 Fluxo funcional completo</h2>
{rubrica("<b>Fluxo funcional (1 pt):</b> um uso completo da solução, do início ao fim.")}
<p>Fluxo demonstrado com <code>docker compose up</code> ou <code>python -m devops.demo</code>, reproduzindo o temporal real de 24/01/2025
(chuva horária medida pelo INMET, repartida em janelas de 10 minutos; nível do córrego simulado). Horários de Brasília:</p>
{tabela(["Hora", "O que acontece", "Onde ver"], [
    ["até 16h00", "tempo seco; estações publicam; app e painel em verde", "Início"],
    ["16h10", "21 mm em 10 minutos; agente emite <b>atenção</b> (amarelo) pela regra de chuva", "Alertas"],
    ["16h20", "40 mm em 30 minutos; córrego ainda em 38 cm; a <b>IA estima 95%</b> → alerta <b>vermelho</b>; SMS enfileirado; comando de sirene por MQTT", "Minha área, detalhe do alerta, caixa de SMS"],
    ["17h20", "na simulação, o Aricanduva transborda — <b>60 minutos depois</b> do aviso da IA; a regra local da estação também dispara", "Minha área, estação"],
    ["17h30", "moradora relata bueiro entupido; a ocorrência entra no data lake e no índice de prioridade", "Relatar ocorrência, painel"],
    ["17h30", "agente vê a ocorrência, os alertas e a caixa de SMS; pode acionar a sirene", "Painel do agente"],
    ["20h20", "30 minutos em verde; agente avisa que a situação normalizou", "Minha área"],
])}
<div class="duas">
{figura(P + "04_alertas.png", "Alertas recebidos pelo morador (vindos da IA pela API interna).")}
{figura(P + "09_relatar_ocorrencia.png", "O morador relata um bueiro entupido.")}
</div>
{figura(P + "13_painel_do_agente.png", "Painel do agente: sirenes por estação, fila de ocorrências, alertas recentes e caixa de saída de SMS (telefone mascarado).")}
<div class="duas">
{figura(P + "21_painel_ao_vivo_alertas.png", "Os mesmos alertas e a ocorrência chegam ao dashboard (fonte Sensores ao vivo).", recorte=0.8)}
{figura(P + "16_minha_area_normalizada.png", "Fim do evento: situação normalizada.")}
</div>
</section>"""


def _resumo_ci() -> str:
    resumo = ler(CI + "resumo.md")
    if not resumo:
        return '<div class="pendente">Execução local do pipeline ainda não registrada (rode <code>python -m devops.ci_local --com-docker</code>).</div>'
    linhas = [linha.strip("|").split("|") for linha in resumo.splitlines() if linha.startswith("| 0") or linha.startswith("| 1")]
    cabecalho = next((linha for linha in resumo.splitlines() if linha.startswith("Data:")), "")
    cabecalho = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(cabecalho))
    return f"<p>{cabecalho}</p>" + tabela(["Etapa", "Resultado", "Duração"], [[c.strip() for c in linha] for linha in linhas], numericas=(2,))


def _trecho(arquivo: str, padrao: str, antes: int = 0, depois: int = 30) -> str:
    """Recorta de um registro as linhas em torno da primeira ocorrência de um texto."""
    linhas = ler(arquivo).splitlines()
    for i, linha in enumerate(linhas):
        if padrao in linha:
            return "\n".join(linhas[max(0, i - antes) : i + depois])
    return "\n".join(linhas[-depois:])


def area_devops() -> str:
    testes = ler(CI + "04_testes_pytest.txt")
    resultado = re.findall(r"=+ (\d+ passed[^=]*) =+", testes)
    cobertura = re.findall(r"^TOTAL\s+\d+\s+\d+\s+(\d+%)", testes, re.M)
    # Uma linha por arquivo de teste (cada ponto é um caso que passou).
    amostra = "\n".join(linha for linha in testes.splitlines() if linha.startswith("tests"))
    n_commits = git("rev-list", "--count", "HEAD")
    return f"""
<section class="secao">
<h1>9. Área 4 — DevOps, segurança e qualidade</h1>
<h2>9.1 Organização e versionamento</h2>
{rubrica("<b>Organização (0,5 pt):</b> projeto organizado por módulos e versionado com Git.")}
{bloco('''GS2026_CitizenTech/
├── ia/          Área 1  dataset, treinar, avaliacao, modelo, agente, mensagens, servico, demonstrar
├── dados/       Área 2  contratos, fontes/inmet, ingestao, processamento (bronze, silver, features, gold),
│                        simulacao, medidas, dashboard, powerbi, pipeline
├── mvp/         Área 3  web/ (FastAPI: rotas, banco, seguranca, validacao, templates)  iot/ (firmware Wokwi, emulador)
├── devops/      Área 4  preparar, demo, ci_local, verificar_pilha, monitor, finalizar, empacotar, qualidade/PLANO_DE_TESTES.md
├── comum/               config, log, estacoes, http_interno
├── tests/               dados, ia, iot, web, integracao, devops
├── docs/                diagramas, evidencias, validacao, pdf, COMO_EXPLICAR.md, contratos-tecnicos.md
├── .github/workflows/ci.yml   Dockerfile   docker-compose.yml   README.md''', claro=True)}
<p>Git com {n_commits} commits, um por etapa do trabalho. Últimos commits (<code>git log --oneline</code>):</p>
{bloco(git("log", "--oneline", "-n", "12"), claro=True)}
<h2>9.2 DevOps: Docker, CI/CD e monitoramento</h2>
{rubrica("<b>DevOps (1 pt):</b> evidência de Docker, CI/CD ou monitoramento funcionando.")}
<p><b>Docker.</b> Uma imagem (<code>Dockerfile</code>, Python 3.13, usuário sem root) e oito serviços no <code>docker-compose.yml</code>:
<code>mosquitto</code>, <code>preparo</code> (roda uma vez: histórico, treino, usuários), <code>app</code>, <code>gateway</code>,
<code>pipeline</code>, <code>ia</code>, <code>dashboard</code> e <code>emulador</code>, com healthchecks e um volume para os dados.
<code>docker compose up --build</code> sobe tudo (a primeira subida leva alguns minutos, porque o <code>preparo</code> monta o histórico e treina a IA). Serviços no ar (<code>docker compose ps</code>; <code>preparo</code> e <code>emulador</code> rodam e encerram, por isso aparecem seis; as portas 8010, 8511 e 1885 são da máquina de teste, trocadas pelo <code>.env</code>):</p>
{bloco(_trecho(CI + "07_docker_ps.txt", "NAME", 0, 12) or "(execução com Docker ainda não registrada)")}
<p><b>CI/CD.</b> O workflow <code>.github/workflows/ci.yml</code> encadeia, a cada push, sem passo manual:
lint (ruff) → segurança do código (bandit) → vulnerabilidades em dependências (pip-audit) → testes com cobertura (pytest) →
build da imagem → pilha no ar e teste de fumaça de ponta a ponta → publicação da imagem no GitHub Container Registry (só na <code>main</code>).</p>
<div class="aviso"><b>O que rodou onde.</b> O pipeline rodou em dois lugares: no <b>GitHub Actions</b>, disparado pelo push
(evidência abaixo), e nesta máquina, com os mesmos passos, por <code>python -m devops.ci_local --com-docker</code>
(registros completos em <code>docs/evidencias/ci_local/</code>).</div>
{markdown_simples(ler("docs/pdf/conteudo/ci_github.md", "Execução no GitHub Actions: ainda não realizada (repositório não publicado até a geração deste PDF)."))}
{figura(P + "30_github_actions_run.png", "GitHub Actions, execução #1 do workflow ci: um push disparou lint, segurança e testes → build da imagem e teste da pilha → publicação da imagem, tudo com sucesso.")}
<h3>Execução local do pipeline</h3>
{_resumo_ci()}
<p class="pequeno">No GitHub Actions o pipeline inteiro leva cerca de 6 minutos.</p>
<p><b>Teste de fumaça de ponta a ponta na pilha Docker</b> (o emulador publica o temporal por MQTT; o script confere a saúde dos serviços e
espera o alerta da IA chegar ao app):</p>
{bloco(_trecho(CI + "09_fumaca_ponta_a_ponta.txt", "[", 0, 10) or "(não registrado)")}
<p><b>Monitoramento.</b> <code>/health</code> e <code>/metrics</code> (formato Prometheus) no app; arquivos de batimento gravados pelo gateway,
pelo pipeline e pela IA a cada ciclo; logs em JSON por linha; <code>python -m devops.monitor</code> junta tudo e sai com erro se algo parar.
A aba Dados e monitoramento do dashboard mostra os mesmos sinais.</p>
{bloco(_trecho(CI + "10_monitor.txt", "saudavel", 0, 3) or "(não registrado)")}
{bloco(_trecho(CI + "11_docker_logs.txt", "alertas emitidos", 2, 6), max_linhas=10)}
<h2>9.3 Segurança</h2>
{rubrica("<b>Segurança (0,5 pt):</b> 2 ou mais práticas, como autenticação, validação de entrada ou proteção de dados.")}
{tabela(["Prática", "Como foi feita", "Código", "Teste"], [
    ["<b>Autenticação</b>", "senha com bcrypt; sessão em cookie assinado, <code>HttpOnly</code> e <code>SameSite=Lax</code>; sessão regenerada no login; bloqueio após 5 tentativas; mensagem genérica de erro", "<code>mvp/web/seguranca.py</code>, <code>rotas_conta.py</code>", "CT-13, CT-14"],
    ["<b>Autorização</b>", "papéis morador × agente; morador só vê as próprias ocorrências", "<code>mvp/web/apoio.py</code>, <code>rotas_agente.py</code>", "CT-16"],
    ["<b>Validação de entrada</b>", "todo formulário validado no servidor; API interna com modelos Pydantic (faixas, enumerações, tamanhos); gateway e silver validam leituras pelo contrato; SQL sempre parametrizado; Jinja com escape automático", "<code>mvp/web/validacao.py</code>, <code>modelos.py</code>, <code>dados/ingestao/</code>", "CT-02, CT-06, CT-17"],
    ["<b>Proteção contra CSRF</b>", "token por sessão em todo formulário POST", "<code>mvp/web/seguranca.py</code>, <code>_csrf.html</code>", "CT-15"],
    ["<b>Proteção de dados (LGPD)</b>", "telefone cifrado em repouso (Fernet) e mascarado nas telas; consentimento no cadastro; exportar e excluir a conta; API interna e data lake sem dado pessoal; logs sem dado pessoal", "<code>mvp/web/seguranca.py</code>, <code>rotas_conta.py</code>", "CT-18"],
    ["<b>Segredos e serviços</b>", "segredos por variável de ambiente; em produção o serviço não sobe com segredo padrão; token na API interna comparado em tempo constante; container sem root", "<code>comum/config.py</code>, <code>Dockerfile</code>", "CT-19"],
    ["<b>Cabeçalhos</b>", "Content-Security-Policy sem script, <code>X-Frame-Options</code>, <code>X-Content-Type-Options</code>, <code>Referrer-Policy</code>", "<code>mvp/web/app.py</code>", "testes web"],
    ["<b>Cadeia de software</b>", "bandit e pip-audit no pipeline; dependências com versão fixa", "<code>.github/workflows/ci.yml</code>", "etapas 02 e 03"],
])}
{bloco(_trecho(CI + "03_dependencias_pip_audit.txt", "$", 0, 8), claro=True, max_linhas=8)}
<h2>9.4 Testes</h2>
{rubrica("<b>Testes (1 pt):</b> plano com 5 ou mais casos e evidências da execução.")}
<p>Plano completo em <code>devops/qualidade/PLANO_DE_TESTES.md</code>: <b>21 casos</b> em três níveis (unidade, integração, ponta a ponta),
todos automatizados. Resumo:</p>
{tabela(["ID", "Área", "O que verifica", "Resultado esperado"], [
    ["CT-02", "Dados", "leitura inválida (nível 900 cm, chuva negativa, data futura, estação inexistente)", "quarentena com o motivo LEI-02 a LEI-05"],
    ["CT-04", "Dados", "features de 10 min sobre série conhecida", "acumulados e variações conferem"],
    ["CT-06", "IoT", "gateway rejeita na porta o que foge do contrato", "vai para a quarentena do gateway"],
    ["CT-07", "IoT", "regra local sem rede", "sirene ligada sem MQTT"],
    ["CT-08", "IoT", "guarda-e-reenvia", "leituras reenviadas em ordem"],
    ["CT-09", "IA", "classificação de risco R1 a R5", "nível correto em cada combinação"],
    ["CT-10", "IA", "emissão R6 a R9", "1 alerta por subida, lembrete em 60 min, normalização"],
    ["CT-11", "IA", "SMS de todas as estações e níveis", "até 160 caracteres, sem acento"],
    ["CT-12", "IA", "métrica de antecedência e alarme falso", "valores calculados à mão conferem"],
    ["CT-14", "Segurança", "senha fraca, login errado, 5 falhas", "recusa, mensagem genérica, bloqueio"],
    ["CT-15", "Segurança", "POST sem token CSRF", "HTTP 403"],
    ["CT-16", "Segurança", "morador no painel do agente", "HTTP 403"],
    ["CT-17", "Segurança", "injeção de SQL e XSS", "não autentica; texto escapado"],
    ["CT-18", "Segurança", "telefone no banco", "cifrado; mascarado na tela"],
    ["CT-19", "Web", "API interna sem token; alerta repetido", "401; 1 alerta e 1 SMS"],
    ["CT-20", "Integração", "temporal → gateway → gold → IA → app", "alerta visível ao morador; SMS na fila"],
    ["CT-21", "Ponta a ponta", "pilha Docker com MQTT", "alerta da IA contado no /metrics do app"],
])}
<p><b>Evidência de execução</b> (<code>docs/evidencias/ci_local/04_testes_pytest.txt</code>):
<b>{esc(resultado[-1] if resultado else "ver registro")}</b>{" · cobertura total " + cobertura[-1] if cobertura else ""}.</p>
{bloco(amostra or "(execução ainda não registrada)", max_linhas=30)}
{bloco(_trecho(CI + "04_testes_pytest.txt", "Name ", 0, 60), claro=True, max_linhas=42)}
</section>"""


def _tela_da_validacao(texto: str) -> str:
    """Print da tela que nasceu da validação — só aparece quando há conversas registradas."""
    if "PENDENTE" in texto:
        return ""
    return (
        '<div class="duas">'
        + figura(P + "17_emergencia.png", "Mudança feita a partir da validação: tela Telefones de emergência, no menu e no rodapé do app.")
        + figura(P + "18_celular_emergencia.png", "A mesma tela no celular: o número é um botão que liga.", "celular")
        + "</div>"
    )


def validacao() -> str:
    texto = ler("docs/pdf/conteudo/validacao.md")
    return f"""
<section class="secao">
<h1>10. Validação com pessoas reais</h1>
{markdown_simples(texto)}
{_tela_da_validacao(texto)}
<p class="pequeno">Roteiro: <code>docs/validacao/ROTEIRO_VALIDACAO.md</code> (5 perguntas, 5 minutos por pessoa).
Respostas brutas: <code>docs/validacao/respostas.csv</code>.</p>
<h1>11. Uso de IA generativa e reaproveitamento</h1>
{tabela(["Ferramenta", "Para quê"], [
    ["Claude (Anthropic), via Claude Code", "apoio na escolha e pesquisa do problema, geração e revisão de código, testes, documentação, deste PDF e da montagem do vídeo, sob direção e revisão da equipe"],
    ["edge-tts (voz neural do Microsoft Edge)", "narração da versão de rascunho do vídeo pitch; o vídeo entregue é narrado por um integrante da equipe"],
])}
<p>Em tempo de execução <b>não há IA generativa</b>: a previsão é um modelo de machine learning (scikit-learn) e as mensagens dos alertas
são textos fixos. O guia <code>docs/COMO_EXPLICAR.md</code> é o roteiro de revisão da equipe: explica cada área, os arquivos e as
perguntas prováveis.</p>
<p><b>Reaproveitamento interno, com crédito.</b> A ideia de contratos de dados, o gateway MQTT, o firmware ESP32 no Wokwi, o script
de captura da simulação e o montador de vídeo foram adaptados de trabalhos anteriores da própria equipe (AgroSmart e Startup One,
FIAP 2026). O problema, o produto, os dados e o código desta Global Solution são próprios.</p>
<h1>12. Como executar e onde está cada coisa</h1>
{bloco('''pip install -r requirements.txt
python -m devops.preparar            # histórico do data lake, treino da IA, usuários de demonstração (~3 min)
docker compose up --build            # tudo, com broker MQTT        (ou, sem Docker:  python -m devops.demo)
#   app do morador ......... http://localhost:8000
#   painel da Defesa Civil . http://localhost:8501   (fonte: Sensores ao vivo)
python -m ia.demonstrar              # IA: entrada e saída
python -m pytest                     # testes
python -m devops.ci_local            # mesmos passos da CI, com registro em docs/evidencias/ci_local/''', claro=True)}
<p>Passo a passo de cada área, usuários de demonstração e solução de problemas: <code>README.md</code>.
Vídeo pitch: {esc(_link_do_video())}</p>
</section>"""


ORDEM = [capa, resumo, problema, solucao, arquitetura, area_ia, area_dados, area_mvp, area_devops, validacao]
