"""Transforma as respostas reais da validação (docs/validacao/respostas.csv) na seção 10 do PDF.

Uso (a partir da raiz):  python docs/validacao/consolidar.py
Lê:    docs/validacao/respostas.csv      (uma linha por pessoa, preenchida pela equipe)
       docs/validacao/o_que_mudou.md     (opcional: o que a equipe mudou no produto por causa das conversas)
Grava: docs/pdf/conteudo/validacao.md    (texto que o gerador do PDF usa)

Só conta e transcreve o que está no CSV: não inventa número nem frase. Sem nenhuma linha, a seção continua PENDENTE.
"""

from __future__ import annotations

import csv
import statistics
import sys
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
RESPOSTAS = RAIZ / "docs" / "validacao" / "respostas.csv"
MUDANCAS = RAIZ / "docs" / "validacao" / "o_que_mudou.md"
SAIDA = RAIZ / "docs" / "pdf" / "conteudo" / "validacao.md"

PENDENTE = """> PENDENTE — esta seção é preenchida pela equipe com conversas reais. Até a geração deste PDF, nenhuma entrevista havia sido registrada em docs/validacao/respostas.csv. Nada aqui foi inventado.

### O que está pronto para validar

- Roteiro de 5 minutos por pessoa, com 5 perguntas, em docs/validacao/ROTEIRO_VALIDACAO.md.
- Material para mostrar: tela Minha área em risco alto, texto do SMS e painel da Defesa Civil.
- Planilha de registro (docs/validacao/respostas.csv), sem dados pessoais.

### Hipóteses que queremos testar com moradores e com a Defesa Civil

- A tela de alerta é entendida em 5 segundos, sem explicação.
- Quarenta minutos de antecedência dão tempo de fazer algo útil (levantar móveis, salvar documentos, tirar idosos e crianças).
- SMS e sirene são canais mais confiáveis do que aplicativo para quem tem celular simples.
- O índice de prioridade ajuda a decidir para onde mandar equipe primeiro.
"""


def ler_respostas(arquivo: Path = RESPOSTAS) -> list[dict]:
    """Linhas do CSV que têm ao menos um campo preenchido (o Excel costuma deixar linhas vazias no fim)."""
    if not arquivo.exists():
        return []
    with open(arquivo, encoding="utf-8-sig", newline="") as f:
        amostra = f.read(2048)
        f.seek(0)
        separador = ";" if amostra.count(";") > amostra.count(",") else ","  # o Excel em português salva com ';'
        linhas = [
            {k.strip(): (v or "").strip() for k, v in linha.items() if k}
            for linha in csv.DictReader(f, delimiter=separador)
        ]
    return [linha for linha in linhas if any(linha.values())]


def _contagem(respostas: list[dict], campo: str) -> list[tuple[str, int]]:
    valores = [r.get(campo, "").lower() for r in respostas if r.get(campo)]
    return Counter(valores).most_common()


def _como_escrito(respostas: list[dict], campo: str) -> str:
    """Valores de um campo descritivo (perfil, lugar, idade) com a grafia original e quantas vezes aparecem."""
    return _lista(Counter(r[campo] for r in respostas if r.get(campo)).most_common())


def _lista(pares: list[tuple[str, int]]) -> str:
    return ", ".join(f"{valor} ({n})" for valor, n in pares) or "não informado"


def _minutos(respostas: list[dict]) -> list[float]:
    numeros = []
    for r in respostas:
        try:
            numeros.append(float(r.get("antecedencia_hoje_min", "").replace(",", ".")))
        except ValueError:
            continue  # campo vazio ou texto livre ("não sei"): fica de fora da mediana
    return numeros


def montar_secao(respostas: list[dict], mudancas: str = "") -> str:
    """Texto da seção 10 a partir das respostas. Cada número sai de uma contagem do CSV."""
    if not respostas:
        return PENDENTE
    n = len(respostas)
    entendeu = dict(_contagem(respostas, "entendeu_a_tela"))
    minutos = _minutos(respostas)
    partes = [
        f"Conversamos com **{n} pessoa(s)** seguindo o roteiro de 5 perguntas (docs/validacao/ROTEIRO_VALIDACAO.md). "
        "As respostas brutas, sem dados pessoais, estão em docs/validacao/respostas.csv. Os números abaixo são contagens diretas dessas respostas.",
        "",
        "### Quem ouvimos",
        "",
        f"- Perfis: {_como_escrito(respostas, 'perfil')}.",
        f"- Onde moram ou moraram: {_como_escrito(respostas, 'bairro_ou_cidade')}.",
        f"- Faixa etária: {_como_escrito(respostas, 'faixa_etaria')}.",
        "",
        "### O que as respostas mostram",
        "",
        f"- **Entenderam a tela de alerta sem explicação:** {entendeu.get('sim', 0)} de {n} "
        f"(parcialmente: {entendeu.get('parcial', 0)}; não: {entendeu.get('nao', 0) + entendeu.get('não', 0)}).",
    ]
    if len(minutos) >= 3:
        partes.append(
            f"- **Antecedência com que ficam sabendo hoje** ({len(minutos)} resposta(s) com número): mediana de "
            f"{statistics.median(minutos):.0f} min (de {min(minutos):.0f} a {max(minutos):.0f} min)."
        )
    elif minutos:  # com uma ou duas respostas, mediana não diz nada: mostramos os valores
        valores = " e ".join(f"{m:.0f} min" for m in sorted(minutos))
        partes.append(f"- **Antecedência com que ficam sabendo hoje** ({len(minutos)} resposta(s) com número): {valores}.")
    partes += [
        f"- **Confiariam no aviso:** {_lista(_contagem(respostas, 'confiaria'))}.",
        f"- **Canal preferido:** {_lista(_contagem(respostas, 'canal_preferido'))}.",
    ]
    for titulo, campo in (
        ("Como ficam sabendo hoje", "como_fica_sabendo_hoje"),
        ("O que fariam com 40 minutos de antecedência", "o_que_faria_com_40_min"),
        ("Sugestões recebidas", "sugestao"),
    ):
        itens = [r[campo] for r in respostas if r.get(campo)]
        if itens:
            partes += ["", f"### {titulo}", ""] + [f"- {item}" for item in itens]
    frases = [r["frase_marcante"] for r in respostas if r.get("frase_marcante")]
    if frases:
        partes += ["", "### Frases de quem ouvimos (transcritas, sem identificação)", ""] + [f"- “{f}”" for f in frases]
    partes += ["", "### O que mudou no produto por causa das conversas", ""]
    partes.append(
        mudancas.strip() or "- A equipe ainda não registrou mudanças (arquivo docs/validacao/o_que_mudou.md)."
    )
    return "\n".join(partes) + "\n"


def main() -> int:
    respostas = ler_respostas()
    mudancas = MUDANCAS.read_text(encoding="utf-8") if MUDANCAS.exists() else ""
    SAIDA.write_text(montar_secao(respostas, mudancas), encoding="utf-8")
    print(
        f"{len(respostas)} resposta(s) → {SAIDA.relative_to(RAIZ)}"
        + ("" if respostas else " (seção continua PENDENTE)")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
