"""Painel da Defesa Civil do VigIA (Streamlit).

Uso (a partir da raiz do repositório):  python -m streamlit run dados/dashboard/app.py

Lê somente o GOLD do data lake. Os filtros da barra lateral (fonte, período, estações, nível de risco) definem o
contexto; os indicadores são as medidas de dados/medidas.py (equivalentes a medidas DAX).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:  # o Streamlit executa este arquivo direto; a raiz precisa estar no caminho de import
    sys.path.insert(0, str(RAIZ))

import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from comum.config import carregar_config  # noqa: E402
from dados import medidas  # noqa: E402
from dados.dashboard import consultas  # noqa: E402

FUSO = "America/Sao_Paulo"
# Cores de status (reservadas para risco) e cores das estações (identidade) — nunca se misturam.
COR_RISCO = {"verde": "#0ca30c", "amarelo": "#fab219", "laranja": "#ec835a", "vermelho": "#d03b3b"}
ROTULO_RISCO = {"verde": "● Normal", "amarelo": "▲ Atenção", "laranja": "◆ Risco alto", "vermelho": "■ Perigo"}
COR_ESTACAO = ["#2a78d6", "#1baf7a", "#6250d6", "#e87ba4"]
TINTA, TINTA_FRACA, GRADE = "#0b0b0b", "#898781", "#e1e0d9"

st.set_page_config(page_title="VigIA · Painel da Defesa Civil", page_icon="🌧️", layout="wide")


# ----------------------------------------------------------------------------- filtros


def filtros() -> dict | None:
    """Barra lateral: tudo o que o painel mostra respeita estas escolhas."""
    st.sidebar.title("VigIA")
    st.sidebar.caption("Alerta comunitário de enchentes · painel da Defesa Civil")
    rotulo = st.sidebar.radio("Fonte dos dados", list(consultas.ORIGENS), help="Histórico: chuva real do INMET e nível simulado. Ao vivo: leituras recebidas por MQTT.")
    origem = consultas.ORIGENS[rotulo]
    disponivel = consultas.periodo_disponivel(origem)
    if disponivel is None:
        st.info(
            "Ainda não há dados desta fonte. "
            + ("Rode `python -m dados.pipeline historico`." if origem == "historico" else "Ligue o emulador ou o Wokwi e o pipeline em tempo real.")
        )
        return None
    primeiro, ultimo = (t.tz_convert(FUSO).date() for t in disponivel)
    atalhos = {"Últimos 90 dias": (max(primeiro, ultimo - timedelta(days=90)), ultimo), "Tudo": (primeiro, ultimo)}
    if origem == "historico":
        atalhos = {
            "Verão 2024/25 (dez–mar)": (datetime(2024, 12, 1).date(), datetime(2025, 3, 31).date()),
            "Temporal de 24/01/2025": (datetime(2025, 1, 24).date(), datetime(2025, 1, 25).date()),
            "Ano de 2025": (datetime(2025, 1, 1).date(), ultimo),
            **atalhos,
        }
    else:
        atalhos = {"Tudo": (primeiro, ultimo)}
    atalho = st.sidebar.selectbox("Período rápido", list(atalhos))
    periodo = st.sidebar.date_input("Período", value=atalhos[atalho], min_value=primeiro, max_value=ultimo, format="DD/MM/YYYY")
    if not isinstance(periodo, tuple) or len(periodo) != 2:
        st.sidebar.warning("Escolha a data inicial e a final.")
        return None
    dim = consultas.dim_estacao()
    nomes = dict(zip(dim["estacao_id"], dim["nome"], strict=True))
    escolhidas = st.sidebar.multiselect("Estações", list(nomes), default=list(nomes), format_func=nomes.get)
    niveis = st.sidebar.multiselect(
        "Nível de risco dos alertas", list(COR_RISCO), default=["amarelo", "laranja", "vermelho"], format_func=lambda n: ROTULO_RISCO[n]
    )
    ao_vivo = origem == "sensor" and st.sidebar.toggle("Atualizar a cada 5 s", value=True)
    de = pd.Timestamp(periodo[0], tz=FUSO).tz_convert("UTC").to_pydatetime()
    ate = (pd.Timestamp(periodo[1], tz=FUSO) + pd.Timedelta(days=1)).tz_convert("UTC").to_pydatetime()
    st.sidebar.divider()
    st.sidebar.caption("Chuva: INMET (A701 Mirante de Santana, A771 Interlagos). Nível dos córregos e moradores por área: simulados.")
    return {"origem": origem, "de": de, "ate": ate, "estacoes": escolhidas, "niveis": niveis, "ao_vivo": ao_vivo, "dim": dim}


@st.cache_data(ttl=4, show_spinner=False)
def carregar(origem: str, de: datetime, ate: datetime, estacoes: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Lê as tabelas do gold para o contexto dos filtros (cache curto: o tempo real muda a cada ciclo)."""
    lista = list(estacoes)
    return {
        "leituras": consultas.leituras(origem, de, ate, lista),
        "risco": consultas.risco(origem, de, ate, lista),
        "eventos": consultas.eventos(origem, de, ate, lista),
        "alertas": consultas.alertas(origem, de, ate, lista),
        "ocorrencias": consultas.ocorrencias(lista),
    }


# ----------------------------------------------------------------------------- indicadores


def _delta(atual: float, anterior: float) -> str | None:
    variacao = medidas.variacao_pct(atual, anterior)
    return None if variacao is None else f"{variacao:+.0f}% vs. anterior"


def indicadores(dados: dict, anterior: dict) -> None:
    """Seis medidas no topo. A comparação é com o período imediatamente anterior, de mesmo tamanho."""
    leit, ev, al = dados["leituras"], dados["eventos"], dados["alertas"]
    leit_a, ev_a, al_a = anterior["leituras"], anterior["eventos"], anterior["alertas"]
    c = st.columns(6)
    chuva, chuva_a = medidas.chuva_acumulada_mm(leit), medidas.chuva_acumulada_mm(leit_a)
    c[0].metric("Chuva acumulada", f"{chuva:.0f} mm", _delta(chuva, chuva_a), delta_color="off", help="Média entre as estações selecionadas.")
    c[1].metric("Nível máx. (% da cota)", f"{medidas.nivel_maximo_pct(leit):.0f}%", help="100% = o córrego transborda.")
    n_ev, n_ev_a = medidas.eventos_de_transbordo(ev), medidas.eventos_de_transbordo(ev_a)
    c[2].metric("Transbordos", n_ev, _delta(n_ev, n_ev_a), delta_color="inverse")
    n_al, n_al_a = medidas.alertas_emitidos(al), medidas.alertas_emitidos(al_a)
    c[3].metric("Alertas de risco alto", n_al, _delta(n_al, n_al_a), delta_color="off", help="Níveis laranja (risco alto) e vermelho (perigo).")
    c[4].metric(
        "Antecedência mediana",
        f"{medidas.antecedencia_mediana_min(ev, al):.0f} min" if len(ev) else "—",
        f"{medidas.taxa_eventos_avisados_pct(ev, al):.0f}% com 30+ min" if len(ev) else None,
        delta_color="off",
        help="Tempo entre o primeiro alerta de risco alto/perigo e o início do transbordo.",
    )
    c[5].metric("Sensores no ar", f"{medidas.disponibilidade_sensores_pct(leit):.1f}%", help="Disponibilidade: janelas de 10 min com leitura ÷ janelas esperadas.")


# ----------------------------------------------------------------------------- gráficos


def _estilo(fig: go.Figure, altura: int) -> go.Figure:
    fig.update_layout(
        height=altura, margin={"l": 10, "r": 10, "t": 40, "b": 10}, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#fcfcfb",
        font={"color": TINTA, "size": 13}, hoverlabel={"bgcolor": "white"}, legend={"orientation": "h", "y": 1.12, "x": 0},
    )  # fmt: skip
    fig.update_xaxes(gridcolor=GRADE, linecolor="#c3c2b7", tickfont={"color": TINTA_FRACA})
    fig.update_yaxes(gridcolor=GRADE, linecolor="#c3c2b7", tickfont={"color": TINTA_FRACA}, zeroline=False)
    return fig


def _reduzir(leituras: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Períodos longos são agregados (máximo do nível, soma da chuva) para o gráfico continuar legível e leve."""
    dias = (leituras["medido_em"].max() - leituras["medido_em"].min()).days
    passo, rotulo = ("10min", "janelas de 10 min") if dias <= 3 else ("1h", "por hora") if dias <= 45 else ("1D", "por dia")
    if passo == "10min":
        return leituras, rotulo
    agrupado = leituras.set_index("local").groupby("estacao_id").resample(passo).agg({"nivel_pct_cota": "max", "chuva_mm": "sum"})
    return agrupado.dropna(subset=["nivel_pct_cota"]).reset_index(), rotulo


def grafico_nivel_e_chuva(leituras: pd.DataFrame, alertas: pd.DataFrame, dim: pd.DataFrame) -> None:
    """Um painel por estação (nível em % da cota) e, embaixo de cada um, a chuva. Eixos separados: nunca eixo duplo."""
    dados, rotulo = _reduzir(leituras)
    estacoes = [e for e in dim["estacao_id"] if e in set(dados["estacao_id"])]
    cotas = dim.set_index("estacao_id")
    titulos = [f"{cotas.loc[e, 'nome']} — nível (% da cota de transbordo)" if i % 2 == 0 else "chuva (mm)" for e in estacoes for i in range(2)]
    fig = make_subplots(
        rows=2 * len(estacoes), cols=1, shared_xaxes=True, vertical_spacing=0.035, subplot_titles=titulos,
        row_heights=[h for _ in estacoes for h in (0.72, 0.28)],
    )  # fmt: skip
    na_legenda: set[str] = set()  # cada nível de alerta aparece uma vez só na legenda
    for i, estacao_id in enumerate(estacoes):
        serie = dados[dados["estacao_id"] == estacao_id]
        cor = COR_ESTACAO[list(dim["estacao_id"]).index(estacao_id) % len(COR_ESTACAO)]
        linha_nivel, linha_chuva = 2 * i + 1, 2 * i + 2
        fig.add_trace(
            go.Scatter(x=serie["local"], y=serie["nivel_pct_cota"], mode="lines", line={"color": cor, "width": 2},
                       name=cotas.loc[estacao_id, "nome"], hovertemplate="%{x|%d/%m %H:%M}<br>nível: %{y:.0f}% da cota<extra></extra>", showlegend=False),
            row=linha_nivel, col=1,
        )  # fmt: skip
        fig.add_trace(
            go.Bar(x=serie["local"], y=serie["chuva_mm"], marker_color=cor, opacity=0.75, showlegend=False,
                   hovertemplate="%{x|%d/%m %H:%M}<br>chuva: %{y:.1f} mm<extra></extra>"),
            row=linha_chuva, col=1,
        )  # fmt: skip
        pct_alerta = cotas.loc[estacao_id, "cota_alerta_cm"] / cotas.loc[estacao_id, "cota_transbordo_cm"] * 100
        for valor, nivel, texto in ((100, "vermelho", "transbordo"), (pct_alerta, "laranja", "cota de alerta")):
            fig.add_hline(y=valor, line={"color": COR_RISCO[nivel], "width": 1.5, "dash": "dash"}, annotation_text=texto,
                          annotation_position="top left", annotation_font={"size": 11, "color": TINTA_FRACA}, row=linha_nivel, col=1)  # fmt: skip
        if len(alertas):
            # Marca o instante de cada alerta de risco alto/perigo sobre a linha do nível.
            avisos = alertas[(alertas["estacao_id"] == estacao_id) & alertas["nivel_risco"].isin(["laranja", "vermelho"])]
            for nivel, grupo in avisos.groupby("nivel_risco"):
                fig.add_trace(
                    go.Scatter(x=grupo["local"], y=grupo["nivel_cm"] / cotas.loc[estacao_id, "cota_transbordo_cm"] * 100, mode="markers",
                               marker={"color": COR_RISCO[nivel], "size": 10, "symbol": "diamond" if nivel == "laranja" else "square",
                                       "line": {"color": "white", "width": 2}},
                               name=f"alerta: {ROTULO_RISCO[nivel]}", legendgroup=nivel, showlegend=nivel not in na_legenda,
                               customdata=grupo[["motivo"]], hovertemplate="%{x|%d/%m %H:%M} · alerta<br>%{customdata[0]}<extra></extra>"),
                    row=linha_nivel, col=1,
                )  # fmt: skip
                na_legenda.add(nivel)
    fig.update_annotations(font_size=12)
    st.plotly_chart(_estilo(fig, 250 * len(estacoes) + 60), width="stretch")
    st.caption(f"Resolução: {rotulo}. Horário de Brasília. Linhas tracejadas: cotas de alerta e de transbordo de cada estação.")


def tabela_prioridade(dados: dict, dim: pd.DataFrame) -> None:
    """A decisão que o painel apoia: para onde mandar equipe primeiro."""
    tabela = medidas.tabela_de_prioridade(dados["leituras"], dados["risco"], dados["ocorrencias"], dim)
    if tabela.empty:
        st.info("Sem leituras no período.")
        return
    tabela["prob_maxima"] = tabela["prob_maxima"] * 100
    st.dataframe(
        tabela[["nome", "bairro", "prioridade", "prob_maxima", "nivel_max_pct", "chuva_mm", "ocorrencias_abertas", "moradores_area"]],
        hide_index=True, width="stretch",
        column_config={
            "nome": "Ponto monitorado", "bairro": "Bairro",
            "prioridade": st.column_config.ProgressColumn("Índice de prioridade", min_value=0, max_value=100, format="%.0f"),
            "prob_maxima": st.column_config.NumberColumn("Prob. máx. da IA", format="%.0f%%"),
            "nivel_max_pct": st.column_config.NumberColumn("Nível máx. (% da cota)", format="%.0f%%"),
            "chuva_mm": st.column_config.NumberColumn("Chuva no período", format="%.0f mm"),
            "ocorrencias_abertas": st.column_config.NumberColumn("Ocorrências abertas", format="%d"),
            "moradores_area": st.column_config.NumberColumn("Moradores na área*", format="%d"),
        },
    )  # fmt: skip
    st.caption("Índice = 60 × probabilidade máxima da IA + 0,30 × nível máximo (até 100%) + 2 × ocorrências abertas (até 5). *Simulado.")


def grafico_alertas_por_periodo(alertas: pd.DataFrame) -> None:
    """Barras empilhadas por nível: quanto o sistema avisou em cada mês (ou dia, em períodos curtos)."""
    dias = (alertas["local"].max() - alertas["local"].min()).days
    periodo = alertas["local"].dt.strftime("%Y-%m" if dias > 62 else "%d/%m")
    contagem = alertas.groupby([periodo, "nivel_risco"]).size().unstack(fill_value=0)
    fig = go.Figure()
    for nivel in ("amarelo", "laranja", "vermelho", "verde"):
        if nivel in contagem:
            fig.add_bar(x=contagem.index, y=contagem[nivel], name=ROTULO_RISCO[nivel], marker={"color": COR_RISCO[nivel], "line": {"color": "white", "width": 2}},
                        hovertemplate="%{x}<br>%{y} alerta(s)<extra>" + ROTULO_RISCO[nivel] + "</extra>")  # fmt: skip
    fig.update_layout(barmode="stack", title="Alertas emitidos por " + ("mês" if dias > 62 else "dia"))
    st.plotly_chart(_estilo(fig, 320), width="stretch")


def grafico_horario_dos_transbordos(eventos: pd.DataFrame) -> None:
    """Em que hora do dia os transbordos começam: apoia a escala de plantão."""
    hora = eventos["inicio"].dt.tz_convert(FUSO).dt.hour
    contagem = hora.value_counts().reindex(range(24), fill_value=0)
    fig = go.Figure(go.Bar(x=[f"{h:02d}h" for h in contagem.index], y=contagem.values, marker_color="#2a78d6",
                           hovertemplate="%{x}: %{y} transbordo(s)<extra></extra>"))  # fmt: skip
    fig.update_layout(title="Hora de início dos transbordos (horário de Brasília)")
    st.plotly_chart(_estilo(fig, 320), width="stretch")


# ----------------------------------------------------------------------------- abas


def aba_visao_geral(dados: dict, f: dict) -> None:
    st.subheader("Onde agir primeiro")
    tabela_prioridade(dados, f["dim"])
    st.subheader("Nível dos córregos e chuva")
    if dados["leituras"].empty:
        st.info("Sem leituras no período e nas estações escolhidas.")
        return
    grafico_nivel_e_chuva(dados["leituras"], dados["alertas"], f["dim"])


def aba_alertas(dados: dict, f: dict) -> None:
    alertas = dados["alertas"]
    alertas = alertas[alertas["nivel_risco"].isin(f["niveis"])] if len(alertas) else alertas
    if alertas.empty:
        st.info("Nenhum alerta com os filtros escolhidos.")
    else:
        esquerda, direita = st.columns(2)
        with esquerda:
            grafico_alertas_por_periodo(alertas)
        with direita:
            if len(dados["eventos"]):
                grafico_horario_dos_transbordos(dados["eventos"])
            else:
                st.info("Nenhum transbordo no período.")
        st.subheader("Alertas emitidos")
        nomes = f["dim"].set_index("estacao_id")["nome"]
        tabela = alertas.sort_values("local", ascending=False).assign(
            quando=lambda d: d["local"].dt.strftime("%d/%m/%Y %H:%M"),
            ponto=lambda d: d["estacao_id"].map(nomes),
            nivel=lambda d: d["nivel_risco"].map(ROTULO_RISCO),
            decisao=lambda d: d["origem_decisao"].map({"ia": "IA", "regra_local": "regra de nível"}),
            prob=lambda d: d["prob"] * 100,
        )
        st.dataframe(
            tabela[["quando", "ponto", "nivel", "decisao", "prob", "nivel_cm", "chuva_1h", "motivo", "mensagem_sms"]].head(500),
            hide_index=True, width="stretch",
            column_config={
                "quando": "Quando", "ponto": "Ponto", "nivel": "Nível", "decisao": "Decidido por",
                "prob": st.column_config.NumberColumn("Prob. IA", format="%.0f%%"),
                "nivel_cm": st.column_config.NumberColumn("Nível (cm)", format="%.0f"),
                "chuva_1h": st.column_config.NumberColumn("Chuva 1 h (mm)", format="%.0f"),
                "motivo": "Por quê", "mensagem_sms": "SMS enviado",
            },
        )  # fmt: skip
    st.subheader("Ocorrências relatadas pelos moradores")
    ocorrencias = dados["ocorrencias"]
    if ocorrencias.empty:
        st.info("Nenhuma ocorrência recebida do app ainda (elas chegam quando o app e o pipeline em tempo real estão no ar).")
    else:
        resumo = ocorrencias.groupby(["tipo", "status"]).size().unstack(fill_value=0)
        st.dataframe(resumo, width="stretch")
        st.caption(f"Ocorrências abertas: {medidas.ocorrencias_abertas(ocorrencias)}")


def aba_ia() -> None:
    arquivo = carregar_config().modelos / "metricas.json"
    if not arquivo.exists():
        st.info("Modelo ainda não treinado. Rode `python -m ia.treinar`.")
        return
    m = json.loads(arquivo.read_text(encoding="utf-8"))
    antes, depois = m["teste"]["antes_regra_limiar_fixo"], m["teste"]["depois_ia"]
    st.markdown(
        f"**Previsão de transbordo em 60 min** · {m['algoritmo']} · treino {m['dados']['treino']}, "
        f"teste {m['dados']['teste']} · limiar de alerta {m['limiares']['laranja']:.2f} (escolhido na validação de 2023)."
    )
    c = st.columns(4)
    c[0].metric("Eventos avisados com 30+ min", f"{depois['avisados_30min_pct']:.0f}%", f"antes: {antes['avisados_30min_pct']:.0f}%", delta_color="off")
    c[1].metric("Antecedência mediana", f"{depois['antecedencia_mediana_min']:.0f} min", f"antes: {antes['antecedencia_mediana_min']:.0f} min", delta_color="off")
    c[2].metric("Alarmes falsos no teste", depois["alarmes_falsos"], f"antes: {antes['alarmes_falsos']}", delta_color="off")
    c[3].metric("F1 (por janela)", f"{depois['f1']:.2f}", f"antes: {antes['f1']:.2f}", delta_color="off")
    esquerda, direita = st.columns(2)
    with esquerda:
        rotulos = {"avisados_30min_pct": "Eventos avisados com 30+ min (%)", "antecedencia_mediana_min": "Antecedência mediana (min)", "alarmes_falsos": "Alarmes falsos (total)"}
        fig = go.Figure()
        fig.add_bar(y=list(rotulos.values()), x=[antes[k] for k in rotulos], name="Antes: regra de limiar fixo", orientation="h", marker_color="#898781",
                    text=[f"{antes[k]:g}" for k in rotulos], textposition="outside")  # fmt: skip
        fig.add_bar(y=list(rotulos.values()), x=[depois[k] for k in rotulos], name="Depois: IA", orientation="h", marker_color="#2a78d6",
                    text=[f"{depois[k]:g}" for k in rotulos], textposition="outside")  # fmt: skip
        fig.update_layout(barmode="group", title="Antes × depois no teste 2024–2025", yaxis={"autorange": "reversed"})
        st.plotly_chart(_estilo(fig, 340), width="stretch")
    with direita:
        imp = pd.Series(m["importancia_variaveis"]).sort_values()
        fig = go.Figure(go.Bar(x=imp.values, y=imp.index, orientation="h", marker_color="#2a78d6", hovertemplate="%{y}: %{x:.3f}<extra></extra>"))
        fig.update_layout(title="No que a IA presta atenção (importância por permutação)")
        st.plotly_chart(_estilo(fig, 340), width="stretch")
    st.caption("Chuva: medição real do INMET. Nível do córrego: simulação declarada. Os números valem para este cenário simulado.")


def aba_dados() -> None:
    st.subheader("Caminho do dado: da coleta ao gold")
    st.dataframe(consultas.volumes_por_camada(), hide_index=True, width="stretch")
    st.subheader("Monitoramento dos serviços")
    agora = datetime.now(UTC)
    colunas = st.columns(3)
    for coluna, (nome, batimento) in zip(colunas, consultas.saude_do_pipeline().items(), strict=True):
        if not batimento:
            coluna.metric(nome, "sem sinal", "nunca rodou nesta máquina", delta_color="off")
            continue
        carimbo = batimento.get("em") or batimento.get("atualizado_em")
        idade = (agora - pd.Timestamp(carimbo).to_pydatetime()).total_seconds()
        coluna.metric(nome, "● no ar" if idade < 60 else "▲ parado", f"último sinal há {idade:.0f} s", delta_color="off")
    st.subheader("Quarentena (leituras reprovadas pelo contrato)")
    rejeitadas = consultas.quarentena()
    if rejeitadas.empty:
        st.success("Nenhuma leitura em quarentena.")
    else:
        st.dataframe(rejeitadas.groupby(["arquivo", "motivo"]).size().rename("leituras").reset_index(), hide_index=True, width="stretch")


# ----------------------------------------------------------------------------- página


def conteudo(f: dict) -> None:
    """Indicadores e abas. No modo ao vivo, só este trecho é refeito a cada 5 s (os filtros ficam parados)."""
    dados = carregar(f["origem"], f["de"], f["ate"], tuple(f["estacoes"]))
    duracao = f["ate"] - f["de"]
    anterior = carregar(f["origem"], f["de"] - duracao, f["de"], tuple(f["estacoes"]))
    for tabela, coluna in (("leituras", "medido_em"), ("alertas", "emitido_em")):
        if len(dados[tabela]):
            dados[tabela] = dados[tabela].assign(local=dados[tabela][coluna].dt.tz_convert(FUSO).dt.tz_localize(None))
    st.caption(
        f"{f['de'].astimezone().strftime('%d/%m/%Y')} a {(f['ate'] - timedelta(seconds=1)).astimezone().strftime('%d/%m/%Y')} · "
        f"{len(f['estacoes'])} estação(ões) · {len(dados['leituras']):,} janelas de 10 min".replace(",", ".")
    )
    indicadores(dados, anterior)
    geral, alertas, ia, tecnica = st.tabs(["Visão geral", "Alertas e ocorrências", "IA: antes × depois", "Dados e monitoramento"])
    with geral:
        aba_visao_geral(dados, f)
    with alertas:
        aba_alertas(dados, f)
    with ia:
        aba_ia()
    with tecnica:
        aba_dados()


def pagina() -> None:
    f = filtros()
    if f is None:
        return
    st.title("Painel da Defesa Civil")
    if not f["estacoes"]:
        st.warning("Escolha ao menos uma estação.")
        return
    # st.fragment com run_every refaz só o conteúdo, sem piscar a página nem perder a aba aberta.
    st.fragment(run_every=5 if f["ao_vivo"] else None)(conteudo)(f)


pagina()
