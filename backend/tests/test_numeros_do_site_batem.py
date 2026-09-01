# -*- coding: utf-8 -*-
"""Os números de cobertura têm que ser O MESMO nas páginas públicas.

🩸 31/08/2026 — CINCO LEITORES CEGOS ACHARAM ISSO. Pedi a 5 agentes que lessem
só o ai.arq.br e dissessem o que o produto faz. Três dos cinco apontaram a mesma
coisa como A ambiguidade que atrapalha decidir: o site dava TRÊS números de
cobertura em três páginas —
    home     21,6% em CAD contra 4,7% em PDF  ("~4,6× mais")
    FAQ      25,5% em CAD contra 2,0% em PDF  (~13×, outra amostra)
    exemplo  72% medido
🪤 E ao remedir, nenhum dos dois primeiros pares foi reproduzível: os 4,7%/2,0%
de PDF vinham de um bug do selo, que carimbava como MEDIDO item sem medição de
geometria (628 itens entre abril e julho, zerado em agosto).

🔑 O conserto separou duas perguntas que estavam misturadas:
  • quanto da planilha volta PREENCHIDA  → 73,8% CAD · 70,0% PDF
  • quanto volta CARIMBADO COMO MEDIDO   → 23,9% CAD · 0% PDF
O zero do PDF é a regra dura nº1 funcionando (carimbo é declaração, não prova),
não falha de leitura — e a copy tem que dizer isso, senão vira "não lemos PDF".

Este guarda não julga se o número está certo: ele exige que as páginas contem
A MESMA história. Ao remedir, atualize os quatro valores AQUI e o teste aponta
toda página que ficou pra trás.
"""
import io
import os
import re

# .../<repo>/backend/tests/este_arquivo.py -> tres niveis acima e a raiz do repo,
# que e onde moram index.html, faq.html e exemplo.html.
SITE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# medido em 31/08/2026, projetos concluídos em agosto: 79 em CAD, 11 só PDF
PREENCHIDO_CAD = "73,8%"
PREENCHIDO_PDF = "70,0%"
MEDIDO_CAD = "23,9%"

# páginas que falam de cobertura → o que cada uma TEM que dizer
ESPERADO = {
    "index.html":   [PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD],
    "faq.html":     [PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD],
    "exemplo.html": [PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD],
}

# números que a gente APOSENTOU — não podem reaparecer em copy viva
APOSENTADOS = ("21,6%", "4,7%", "25,5%", "2,0%", "4,6&times;", "4,6×")


def _texto(nome):
    return io.open(os.path.join(SITE, nome), encoding="utf-8").read()


def test_as_tres_paginas_dao_o_MESMO_numero():
    faltando = []
    for pagina, numeros in ESPERADO.items():
        t = _texto(pagina)
        for n in numeros:
            if n not in t:
                faltando.append("%s não diz %s" % (pagina, n))
    assert not faltando, (
        "as páginas voltaram a contar histórias diferentes: " + " | ".join(faltando))


def test_numero_APOSENTADO_nao_volta_na_copy_viva():
    """🪤 O post do blog é EXCEÇÃO de propósito: post datado não é erro, e a
    apuração antiga fica lá como histórico com nota de atualização em cima."""
    problemas = []
    for pagina in ESPERADO:
        t = _texto(pagina)
        for velho in APOSENTADOS:
            if velho in t:
                problemas.append("%s ainda tem %s" % (pagina, velho))
    assert not problemas, (
        "número aposentado voltou pra copy viva: " + " | ".join(problemas))


def test_o_ZERO_do_PDF_nunca_aparece_sozinho():
    """🚨 O mais importante daqui. "0% medido em PDF" é verdade sobre o SELO e
    mentira sobre o produto: o motor lê o PDF e devolve 70% da planilha
    preenchida. Se a página disser o zero sem dizer que ele é por REGRA e sem o
    número de preenchimento do lado, ela passa a ideia de que não lemos PDF."""
    for pagina in ESPERADO:
        t = _texto(pagina).lower()
        if "nenhuma" in t or "nenhum" in t or "0%" in t:
            assert ("carimbo" in t and "declara" in t), (
                "%s fala do zero do PDF sem explicar que é a regra do carimbo "
                "(declaração, não prova) — vira 'não lemos PDF'" % pagina)
            assert PREENCHIDO_PDF in t.replace("&nbsp;", " "), (
                "%s fala do zero do PDF sem dizer que a planilha volta %s "
                "preenchida — falta a metade que evita o mal-entendido"
                % (pagina, PREENCHIDO_PDF))


def test_CONTROLE_o_guarda_enxerga_as_paginas():
    """Guarda que lê arquivo vazio passa verde guardando nada."""
    for pagina in ESPERADO:
        t = _texto(pagina)
        assert len(t) > 5000, "%s tem só %d bytes — o guarda não está lendo a página" % (
            pagina, len(t))


def test_CONTROLE_o_guarda_REPROVA_numero_divergente():
    """🧪 Prova que morde, sem tocar em arquivo nenhum."""
    falso = "a home diz 21,6% em CAD"
    assert any(v in falso for v in APOSENTADOS), (
        "a lista de aposentados não pega o número que causou o problema")
