# -*- coding: utf-8 -*-
"""A copy pública não chama o selo de "conferido", não fala "motor" e não promete o que a base não mostra.

🩸 27/09/2026 — O estudo de posicionamento listou frases que o produto não sustenta, espalhadas pela home,
FAQ, /dados, /sobre, preços, llms.txt e posts do blog:
  • "o que você pode usar SEM CONFERIR", "já vem conferida", "certificada", "usar sem reconferir" — o selo
    diz de onde veio o número, não que ele foi conferido (nunca foi comparado com gabarito);
  • "o motor mede / o motor lê" — palavra de dentro de casa;
  • "os melhores / mais avançados modelos de IA do mundo" — o estudo acadêmico mediu os modelos que TESTOU;
  • "suas correções afinam o motor / seus próximos quantitativos saem medindo melhor" — a base de
    comparação por tipo de obra tem 2 projetos, de um tipo só.
Pedro liberou a limpeza em todos esses lugares. O guarda cobra o texto de cada página pública e das fontes
que geram texto público (blog/posts.json → blog/posts/*.html; blog/gerar_llms.py → llms.txt).
Fora do escopo, de propósito: a área logada (dashboard, projeto, revisão), que não é copy de aquisição.
"""
import glob
import html
import io
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAGINAS = ["index.html", "faq.html", "dados.html", "sobre.html", "precos.html", "exemplo.html", "llms.txt",
           "blog/index.html", "blog/posts.json", "blog/gerar_llms.py"]

PROIBIDAS = [
    (r"usar\s+sem\s+(re)?conferir", "selo não é conferência"),
    (r"vem\s+conferid", "selo não é conferência"),
    (r"certificad[ao]\s+como\s+medid|sai\s+certificad", "selo não é certificado"),
    (r"\bo\s+motor\s+(mede|l[êe])\b", "jargão da casa"),
    (r"afina[m]?\s+(o\s+motor|a\s+IA|a\s+calibra)", "promessa que a base não sustenta"),
    (r"saem\s+medindo\s+melhor", "promessa que a base não sustenta"),
    (r"(melhores|mais\s+avan[çc]ados)\s+(modelos\s+de\s+IA\s+)?do\s+mundo", "o estudo mediu os modelos testados"),
]


def _texto(caminho):
    t = io.open(caminho, encoding="utf-8").read()
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.S)
    return html.unescape(t)


def problemas(textos):
    """textos: {nome: texto}. Devolve a lista do que está proibido (vazia = certo)."""
    achados = []
    for nome, t in textos.items():
        for pad, porque in PROIBIDAS:
            for m in re.finditer(pad, t, re.I):
                achados.append("%s: %r (%s)" % (nome, t[max(0, m.start() - 30):m.end() + 20], porque))
    return achados


def _todas():
    nomes = PAGINAS + [os.path.relpath(p, RAIZ) for p in glob.glob(os.path.join(RAIZ, "blog", "posts", "*.html"))]
    return {n: _texto(os.path.join(RAIZ, n)) for n in nomes}


def test_a_copy_publica_nao_promete_mais_que_a_base():
    achados = problemas(_todas())
    assert not achados, "a copy pública voltou a prometer demais:\n  " + "\n  ".join(achados[:15])


def test_CONTROLE_o_guarda_REPROVA_as_frases_que_estavam_no_ar():
    """🧪 Uma frase de cada, como estava no ar até 27/09."""
    velhas = {
        "faq": "A diferença maior está no que você pode usar SEM CONFERIR: em CAD, 25,0%",
        "home": "Em CAD, 1 em cada 4 linhas já vem conferida",
        "post": "contagem sai certificada em 41,7% dos casos; “linha certificada como medida”",
        "dados": "PDF vetorial também é lido — o motor mede a geometria quando dá",
        "faq2": "O motor lê o CAD de qualquer lugar",
        "precos": "Planilha revisada e cotações de fornecedor afinam o motor — seus próximos quantitativos saem medindo melhor.",
        "faq3": "Mesmo os modelos de IA mais avançados do mundo, quando contam itens",
    }
    achados = problemas(velhas)
    for nome in velhas:
        assert any(a.startswith(nome + ":") for a in achados), (nome, achados)


def test_CONTROLE_o_guarda_nao_morde_uso_legitimo():
    """"sem conferir" é português comum — só a promessa de usar o número sem conferir é proibida."""
    ok = {"post-manual": "tratar estimativa como medição é como assinar um cheque sem conferir o saldo",
          "post-duto": "Supor a mais fina sem conferir erra o peso",
          "cert": "PDF assinado com certificado digital ICP-Brasil",
          "motor": "persiana motorizada"}
    assert problemas(ok) == []


def test_CONTROLE_o_guarda_le_as_paginas_de_verdade():
    textos = _todas()
    assert len([n for n in textos if n.startswith(os.path.join("blog", "posts"))]) >= 20, "não achei os posts"
    for n in ("index.html", "faq.html", "llms.txt"):
        assert len(textos[n]) > 2000, "%s veio vazio — o guarda não está lendo" % n
