"""Gráfico SVG montado no servidor (sem JavaScript): nível do córrego contra as cotas e, embaixo, a chuva.

São dois painéis com o mesmo eixo de tempo, cada um com a sua escala (nível em cm, chuva em mm).
As cores vêm do CSS (classes g-*), então o alto contraste também vale para o gráfico.
"""

from __future__ import annotations

from markupsafe import Markup, escape

from comum.estacoes import Estacao
from mvp.web.apresentacao import hora_curta, numero

LARGURA, ALTURA = 480, 280  # medidas internas do desenho; na tela ele estica até a largura disponível
X0, X1 = 40, 470  # área útil na horizontal
NIVEL_TOPO, NIVEL_BASE = 22, 176  # painel do nível
CHUVA_TOPO, CHUVA_BASE = 212, 250  # painel da chuva
CHUVA_MINIMA_ESCALA = 5.0  # mm: evita que um chuvisco pareça temporal


def _y(valor: float, maximo: float, topo: float, base: float) -> float:
    """Converte um valor (0..maximo) na posição vertical dentro do painel."""
    return base - (min(valor, maximo) / maximo) * (base - topo)


def _xs(quantidade: int) -> list[float]:
    passo = (X1 - X0) / max(quantidade - 1, 1)
    return [X0 + i * passo for i in range(quantidade)]


def _cotas(estacao: Estacao, maximo: float) -> str:
    """Linhas tracejadas das três cotas, cada uma com o nome escrito (não depende só da cor)."""
    partes = []
    cotas = (
        ("atencao", "atenção", estacao.cota_atencao_cm),
        ("alerta", "alerta", estacao.cota_alerta_cm),
        ("transbordo", "transbordo", estacao.cota_transbordo_cm),
    )
    for classe, nome, cota in cotas:
        y = _y(cota, maximo, NIVEL_TOPO, NIVEL_BASE)
        partes.append(f'<line class="g-cota g-cota-{classe}" x1="{X0}" y1="{y:.1f}" x2="{X1}" y2="{y:.1f}"/>')
        partes.append(f'<text class="g-eixo" x="{X0 - 6}" y="{y + 4:.1f}" text-anchor="end">{cota:.0f}</text>')
        partes.append(f'<text class="g-rotulo" x="{X0 + 6}" y="{y - 5:.1f}">{nome}</text>')
    return "".join(partes)


def _linha_do_nivel(xs: list[float], niveis: list[float], maximo: float) -> str:
    ys = [_y(n, maximo, NIVEL_TOPO, NIVEL_BASE) for n in niveis]
    pontos = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    area = f"{X0},{NIVEL_BASE} {pontos} {xs[-1]:.1f},{NIVEL_BASE}"
    # O rótulo do último ponto fica à esquerda dele e nunca sai do painel.
    y_rotulo = max(ys[-1] - 10, NIVEL_TOPO + 4)
    return (
        f'<polygon class="g-area" points="{area}"/>'
        f'<polyline class="g-linha" points="{pontos}"/>'
        f'<circle class="g-agora" cx="{xs[-1]:.1f}" cy="{ys[-1]:.1f}" r="5"/>'
        f'<text class="g-valor" x="{xs[-1] - 9:.1f}" y="{y_rotulo:.1f}" text-anchor="end">'
        f"agora: {niveis[-1]:.0f} cm</text>"
    )


def _barras_de_chuva(xs: list[float], chuvas: list[float]) -> str:
    maximo = max(max(chuvas), CHUVA_MINIMA_ESCALA)
    largura = max((X1 - X0) / max(len(xs) - 1, 1) * 0.6, 2)
    partes = [
        f'<line class="g-base" x1="{X0}" y1="{CHUVA_BASE}" x2="{X1}" y2="{CHUVA_BASE}"/>',
        f'<text class="g-rotulo" x="{X0 + 6}" y="{CHUVA_TOPO - 6}">chuva a cada 10 min (mm)</text>',
        f'<text class="g-eixo" x="{X0 - 6}" y="{CHUVA_TOPO + 4}" text-anchor="end">{numero(maximo)}</text>',
        f'<text class="g-eixo" x="{X0 - 6}" y="{CHUVA_BASE + 4}" text-anchor="end">0</text>',
    ]
    for x, chuva in zip(xs, chuvas, strict=True):
        if chuva > 0:
            y = _y(chuva, maximo, CHUVA_TOPO, CHUVA_BASE)
            altura = max(CHUVA_BASE - y, 1.5)
            esquerda = min(max(x - largura / 2, X0), X1 - largura)
            partes.append(
                f'<rect class="g-chuva" x="{esquerda:.1f}" y="{CHUVA_BASE - altura:.1f}" width="{largura:.1f}"'
                f' height="{altura:.1f}" rx="1.5"/>'
            )
    return "".join(partes)


def _horas(xs: list[float], serie: list[dict]) -> str:
    """Marca as horas cheias no eixo do tempo (horário de Brasília)."""
    partes = []
    for x, ponto in zip(xs, serie, strict=True):
        hora = hora_curta(ponto["t"])
        if hora.endswith(":00") and X0 + 14 <= x <= X1 - 14:
            partes.append(f'<line class="g-grade" x1="{x:.1f}" y1="{NIVEL_TOPO}" x2="{x:.1f}" y2="{CHUVA_BASE}"/>')
            partes.append(f'<text class="g-eixo" x="{x:.1f}" y="{ALTURA - 8}" text-anchor="middle">{hora}</text>')
    return "".join(partes)


def _dicas(xs: list[float], serie: list[dict]) -> str:
    """Faixas invisíveis com <title>: ao passar o dedo ou o mouse, o navegador mostra os números do ponto."""
    largura = (X1 - X0) / max(len(xs) - 1, 1)
    partes = []
    for x, ponto in zip(xs, serie, strict=True):
        texto = f"{hora_curta(ponto['t'])}: nível {ponto['nivel_cm']:.0f} cm, chuva {numero(ponto['chuva_mm'], 1)} mm"
        partes.append(
            f'<rect class="g-dica" x="{x - largura / 2:.1f}" y="{NIVEL_TOPO}" width="{largura:.1f}"'
            f' height="{CHUVA_BASE - NIVEL_TOPO}"><title>{texto}</title></rect>'
        )
    return "".join(partes)


def grafico_nivel(serie: list[dict], estacao: Estacao) -> Markup | None:
    """Devolve o SVG pronto, ou None se ainda não há pontos suficientes para desenhar."""
    if len(serie) < 2:
        return None
    niveis = [float(p["nivel_cm"]) for p in serie]
    chuvas = [float(p["chuva_mm"]) for p in serie]
    maximo = max(estacao.cota_transbordo_cm * 1.25, max(niveis) * 1.1)  # folga no topo para os rótulos
    xs = _xs(len(serie))
    resumo = (
        f"Das {hora_curta(serie[0]['t'])} às {hora_curta(serie[-1]['t'])} o nível foi de {min(niveis):.0f} a "
        f"{max(niveis):.0f} centímetros; agora está em {niveis[-1]:.0f}. O córrego transborda com "
        f"{estacao.cota_transbordo_cm:.0f} centímetros. Choveu {numero(sum(chuvas), 1)} milímetros no período."
    )
    # Só entram no SVG números formatados aqui e textos fixos; o nome da estação vem do catálogo e ainda é escapado.
    svg = (
        f'<svg class="grafico" viewBox="0 0 {LARGURA} {ALTURA}" role="img"'
        ' aria-label="Gráfico do nível do córrego e da chuva">'
        f"<title>Nível e chuva — {escape(estacao.nome)}</title><desc>{resumo}</desc>"
        f'<text class="g-rotulo" x="{X0 + 6}" y="{NIVEL_TOPO - 6}">nível do córrego (cm)</text>'
        f'<line class="g-base" x1="{X0}" y1="{NIVEL_BASE}" x2="{X1}" y2="{NIVEL_BASE}"/>'
        f'<text class="g-eixo" x="{X0 - 6}" y="{NIVEL_BASE + 4}" text-anchor="end">0</text>'
        f"{_horas(xs, serie)}{_cotas(estacao, maximo)}{_linha_do_nivel(xs, niveis, maximo)}"
        f"{_barras_de_chuva(xs, chuvas)}{_dicas(xs, serie)}</svg>"
    )
    # Markup é seguro aqui: o conteúdo foi montado só com números e textos fixos (ver comentário acima).
    return Markup(svg)  # noqa: S704  # nosec B704


def tabela_da_serie(serie: list[dict]) -> list[dict]:
    """Os mesmos dados do gráfico em números, de hora em hora (para leitor de tela e para quem prefere tabela)."""
    linhas = []
    for fim in range(len(serie) - 1, -1, -6):
        janela = serie[max(fim - 5, 0) : fim + 1]
        linhas.append(
            {
                "hora": hora_curta(serie[fim]["t"]),
                "nivel_cm": serie[fim]["nivel_cm"],
                "chuva_mm": sum(p["chuva_mm"] for p in janela),
            }
        )
    return linhas
