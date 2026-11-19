"""Fechamento da entrega: link do vídeo e consolidação da validação (com dados de teste, nunca os da entrega)."""

import re

import pytest

from devops import finalizar
from docs.validacao import consolidar

CABECALHO = (
    "data,perfil,bairro_ou_cidade,faixa_etaria,entendeu_a_tela,como_fica_sabendo_hoje,antecedencia_hoje_min,"
    "o_que_faria_com_40_min,confiaria,canal_preferido,sugestao,frase_marcante"
)


def test_so_aceita_link_dos_servicos_do_enunciado():
    assert finalizar.validar_url(" https://youtu.be/abc123 ") == "https://youtu.be/abc123"
    assert finalizar.validar_url("https://www.youtube.com/watch?v=abc")
    assert finalizar.validar_url("https://drive.google.com/file/d/1/view")
    for ruim in ("youtu.be/abc", "http://exemplo.com/video.mp4", "https://youtube.com.exemplo.com/x", "arquivo.mp4"):
        with pytest.raises(ValueError):
            finalizar.validar_url(ruim)


def test_grava_e_troca_o_link_nos_dois_arquivos(tmp_path, monkeypatch):
    readme = tmp_path / "README.md"
    integrantes = tmp_path / "Grupo14_integrantes.txt"
    readme.write_text("# VigIA\n\n**Vídeo pitch (3 min):** [A PREENCHER — link público]\n\nresto\n", encoding="utf-8")
    integrantes.write_text("Grupo: Grupo 14\nLink do video pitch: [A PREENCHER - link]\nfim\n", encoding="utf-8")
    monkeypatch.setattr(
        finalizar,
        "LINHAS_DO_LINK",
        {
            readme: finalizar.LINHAS_DO_LINK[finalizar.README],
            integrantes: finalizar.LINHAS_DO_LINK[finalizar.INTEGRANTES],
        },
    )
    assert finalizar.gravar_link("https://youtu.be/primeiro") == ["README.md", "Grupo14_integrantes.txt"]
    assert "**Vídeo pitch (3 min):** https://youtu.be/primeiro\n" in readme.read_text(encoding="utf-8")
    assert "A PREENCHER" not in integrantes.read_text(encoding="utf-8")
    # Rodar de novo com outro link troca o anterior; com o mesmo link, não mexe em nada.
    finalizar.gravar_link("https://youtu.be/segundo")
    assert "segundo" in integrantes.read_text(encoding="utf-8") and "primeiro" not in readme.read_text(encoding="utf-8")
    assert finalizar.gravar_link("https://youtu.be/segundo") == []


def test_sem_respostas_a_secao_continua_pendente(tmp_path):
    vazio = tmp_path / "respostas.csv"
    vazio.write_text(CABECALHO + "\n,,,,,,,,,,,\n", encoding="utf-8")
    assert consolidar.ler_respostas(vazio) == []
    assert consolidar.montar_secao([]).startswith("> PENDENTE")


def test_consolidacao_so_conta_o_que_esta_no_csv(tmp_path):
    # Dados fictícios de TESTE (não são entrevistas): servem só para conferir as contagens.
    arquivo = tmp_path / "respostas.csv"
    linhas = [
        "18/11;morador;Bairro A;60+;sim;vendo a água subir;5;levantar os móveis;sim;SMS;;frase de teste um",
        "18/11;morador;Bairro A;30-45;parcial;grupo do WhatsApp;15;tirar o carro;depende;WhatsApp;aviso sonoro;",
        "19/11;defesa civil;Cidade B;45-60;sim;radar e telefone;não sei;acionar equipe;sim;SMS;mapa;frase dois",
    ]
    arquivo.write_text(
        CABECALHO.replace(",", ";") + "\n" + "\n".join(linhas) + "\n", encoding="utf-8"
    )  # como o Excel salva
    respostas = consolidar.ler_respostas(arquivo)
    assert len(respostas) == 3
    secao = consolidar.montar_secao(respostas, mudancas="- Trocamos uma palavra na tela.")
    assert "Conversamos com **3 pessoa(s)**" in secao and "PENDENTE" not in secao
    assert "sem explicação:** 2 de 3 (parcialmente: 1; não: 0)" in secao
    assert "(2 resposta(s) com número): 5 min e 15 min." in secao  # "não sei" fica de fora; com 2 números não há mediana
    assert "sms (2), whatsapp (1)" in secao
    assert re.search(r"“frase de teste um”", secao) and "- Trocamos uma palavra na tela." in secao
