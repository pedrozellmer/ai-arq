# -*- coding: utf-8 -*-
"""O exemplo público fala a língua de quem chega nele: sem jargão da casa e sem o tamanho da base.

🩸 27/09/2026 — A revisão do plano de outubro do Instagram (workflow adversarial, achados COPY-04
e COPY-10) achou na letra miúda do raio-x do exemplo.html: "Não é que o motor não leia o PDF" e
"(Base de set/2026: 154 projetos, 101 em CAD e 53 só PDF.)". Em outubro a página é o 1º link da
bio o mês inteiro e o destino de 7 chamadas dos posts — quem chegava do Instagram lia "motor",
palavra de dentro de casa, e quantos projetos a gente tem.

A frase do "motor" tinha função — evitar o mal-entendido "não lemos PDF" — e ficou, na voz da
própria página ("A IA leu o CAD…"): "Não é que a IA não leia o PDF: ela lê e mede". A contagem
de projetos saiu. Os números de cobertura continuam: quem cobra que eles batam com a home e a FAQ
é o test_numeros_do_site_batem.py.
"""
import io
import os
import re

# .../<repo>/backend/tests/este_arquivo.py -> três níveis acima é a raiz do repo
SITE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# palavra de dentro de casa. O ".match(" do JavaScript não conta: é código, não aparece na tela.
JARGAO = re.compile(r"\bmotor\b|(?<![.\w])match(es)?\b", re.I)
# o tamanho da base: "154 projetos", "101 em CAD"
CONTAGEM_DA_BASE = re.compile(r"\b\d+\s+projetos\b|\b\d+\s+em\s+CAD\b", re.I)


def _texto_da_pagina():
    """O que o visitante lê: a página sem comentário HTML e sem linha de comentário do JS.
    Os DADOS da tabela ficam — eles moram no <script>, mas aparecem na tela."""
    html = io.open(os.path.join(SITE, "exemplo.html"), encoding="utf-8").read()
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", " ", html)


def test_o_exemplo_nao_fala_motor_nem_match():
    achados = sorted(set(m.group(0) for m in JARGAO.finditer(_texto_da_pagina())))
    assert not achados, (
        "o exemplo público voltou a falar jargão da casa: %r — quem chega do Instagram não "
        "sabe o que é; diga 'a IA'" % achados)


def test_o_exemplo_nao_expoe_o_tamanho_da_base():
    achados = sorted(set(m.group(0) for m in CONTAGEM_DA_BASE.finditer(_texto_da_pagina())))
    assert not achados, (
        "o exemplo público voltou a dizer quantos projetos a base tem: %r" % achados)


def test_CONTROLE_o_guarda_le_a_pagina_inteira():
    """Guarda que lê arquivo vazio passa verde guardando nada — e tirar comentário não pode
    levar junto a tabela, que é justamente o que o visitante vê."""
    t = _texto_da_pagina()
    assert len(t) > 5000, "o exemplo.html tem só %d bytes — o guarda não está lendo a página" % len(t)
    for pedaco in ("Raio-X da leitura", "Contrapiso", "Porta de vidro temperado"):
        assert pedaco in t, "sumiu %r do texto que o guarda confere" % pedaco


def test_CONTROLE_o_guarda_REPROVA_o_texto_antigo():
    """🧪 Prova que morde, sem tocar em arquivo nenhum: a frase que estava no ar em 27/09."""
    velho = ("Não é que o motor não leia o PDF: ele lê e mede. "
             "(Base de set/2026: 154 projetos, 101 em CAD e 53 só PDF.)")
    assert JARGAO.search(velho), "o guarda não pega o 'motor' que estava no ar"
    assert CONTAGEM_DA_BASE.search(velho), "o guarda não pega a contagem que estava no ar"
    assert JARGAO.search("MATCH %"), "o guarda não pega o 'MATCH' da planilha antiga"


def test_CONTROLE_o_guarda_nao_morde_codigo_nem_texto_honesto():
    assert not JARGAO.search("const m = s.match(/x/);"), "o guarda confundiu código com texto"
    assert not CONTAGEM_DA_BASE.search("quantos projetos quiser, sem cartão")
    assert not CONTAGEM_DA_BASE.search("68,4% das linhas em CAD")
