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

# 🔄 REMEDIDO EM 18/09/2026 sobre TODOS os projetos de cliente concluídos:
#     CAD  101 projetos · 5.682 linhas · 68,4% preenchidas · 25,0% medidas
#     PDF   53 projetos · 5.222 linhas · 52,3% preenchidas ·     3 medidas
#
# 🩸 O que estava publicado era de 31/08, sobre agosto, e o lado do PDF se
# apoiava em **387 linhas de 11 projetos**. Em 18 dias o PDF foi a 5.222 linhas
# de 53 projetos e o preenchimento caiu de 70,0% para 52,3% — a copy pública
# prometia uma planilha 18 pontos mais cheia do que a que chega hoje.
# Conferido em 5 janelas (120/90/60/30/14 dias): a queda aparece em todas, e
# nos últimos 30 dias é 47,0% contra 77,2% do CAD. Não é ruído de recorte.
#
# ⏭️ ESTES NÚMEROS ENVELHECEM. Remedir junto com o post de 18/10.
PREENCHIDO_CAD = "68,4%"
PREENCHIDO_PDF = "52,3%"
MEDIDO_CAD = "25,0%"

# páginas que falam de cobertura → o que cada uma TEM que dizer
ESPERADO = {
    "index.html":   [PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD],
    "faq.html":     [PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD],
    "exemplo.html": [PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD],
}

# 🚨 04/09/2026 — a regra "o zero do PDF nunca aparece sozinho" cobria só as
# páginas públicas, e o DASHBOARD escapava dela — justo a tela onde a pessoa
# decide se sobe ou desiste. A caixa de "só PDF" dizia "não conseguimos medir
# nada" E "os itens saem sem quantidade". Medido nos projetos reais de cliente:
#
#                       só PDF      só CAD
#     linhas             1.756        3.938
#     COM QUANTIDADE     71,0%        69,6%      <- praticamente igual
#     com selo             3          1.039
#
# A 1ª frase é verdade; a 2ª é FALSA. E era a falsa que assustava.
_TELA_DE_DECISAO = "dashboard.html"

# números que a gente APOSENTOU — não podem reaparecer em copy viva
APOSENTADOS = ("21,6%", "4,7%", "25,5%", "2,0%", "4,6&times;", "4,6×",
               # aposentados em 18/09/2026 — eram a medição de agosto
               "73,8%", "70,0%", "23,9%")


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


def test_o_FAQ_diz_a_MESMA_coisa_no_schema_e_na_tela():
    """🪤 Achado pela sabotagem de 18/09: a resposta do FAQ vive em DOIS
    lugares — o JSON-LD do schema.org e o texto visível — e nenhum guarda
    cobrava os dois divergirem.

    Isso importa mais do que parece: o JSON-LD é o que o Google lê e mostra no
    resultado da busca. Atualizar só o visível deixaria a busca anunciando um
    número que a página não diz mais, sem nada ficar vermelho.
    """
    t = _texto("faq.html")
    for numero in (PREENCHIDO_CAD, PREENCHIDO_PDF, MEDIDO_CAD):
        n = t.count(numero)
        assert n >= 2, (
            "o faq.html cita %s só %d vez — o schema.org e a resposta visível "
            "têm que dizer o mesmo, senão a busca anuncia outro número"
            % (numero, n))


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


def test_a_caixa_do_SO_PDF_no_dashboard_nao_diz_sem_quantidade():
    """🚨 A tela onde a pessoa decide, e que escapava da regra de cima.

    A afirmação "os itens saem sem quantidade" é FALSA: metade das linhas do
    só-PDF vem preenchida. O que falta é o SELO, não o número. Dizer o
    contrário empurra pra fora quem só tem PDF, com base numa frase que os
    nossos próprios dados desmentem.

    🩸 18/09/2026 — A 1ª VERSÃO DESTE GUARDA PINAVA O VALOR: cobrava
    literalmente `"71%" in caixa`. Quando a realidade se moveu (o PDF caiu de
    71% para 52% e deixou de ser "igual ao CAD"), o guarda seguiu VERDE
    segurando a frase falsa no ar — ele estava defendendo o número, não a
    afirmação. Guarda que fixa um valor que não consegue conferir congela a
    copy no dia em que foi escrito.

    Agora ele cobra a FORMA da afirmação: que a caixa diga um percentual de
    preenchimento do PDF e o compare com o do CAD. O valor certo é
    responsabilidade de quem remede — e mora nas constantes do topo, com data.
    """
    t = _texto(_TELA_DE_DECISAO)
    i = t.index("S&oacute; PDF")
    caixa = t[i:i + 900]
    assert "sem quantidade" not in caixa.lower(), (
        "a caixa do só-PDF voltou a dizer que os itens saem SEM QUANTIDADE — "
        "medido: metade das linhas vem com quantidade")
    pcts = re.findall(r"(\d{1,3})%", caixa)
    assert len(pcts) >= 2, (
        "a caixa precisa de DOIS percentuais — o do PDF e o do CAD pra "
        "comparar. Achei %r" % pcts)
    assert "cad" in caixa.lower(), (
        "a caixa dá um número de preenchimento sem dizer contra o quê — "
        "sozinho ele não informa nada")
    assert "igual ao cad" not in caixa.lower(), (
        "a caixa voltou a dizer que o PDF preenche IGUAL ao CAD. Medido em "
        "18/09: 52,3%% contra 68,4%%, e nos últimos 30 dias 47%% contra 77%%")
    assert "selo" in caixa.lower(), (
        "sumiu a explicação do que REALMENTE muda (o selo, não a quantidade)")


def test_a_caixa_do_SO_PDF_nao_e_vermelha():
    """🪤 Vermelho diz "não faça isso". O dado não sustenta: a planilha de PDF
    volta tão preenchida quanto a de CAD. É ressalva, não impedimento."""
    t = _texto(_TELA_DE_DECISAO)
    i = t.index("S&oacute; PDF")
    assert "bg-red-50" not in t[max(0, i - 400):i], (
        "a caixa do só-PDF voltou a ser vermelha — ela é uma ressalva sobre o "
        "selo, não um aviso para não subir")
