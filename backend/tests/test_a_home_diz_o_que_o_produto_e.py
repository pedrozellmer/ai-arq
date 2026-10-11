# -*- coding: utf-8 -*-
"""A home diz, no texto que a pessoa lê, o que o produto é.

🔎 11/10/2026 — estudo de SEO. "Levantamento de quantitativos" só existia no <title> da home: zero vez no
corpo. "Software" só no JSON-LD. É a página que mais converte (25 contas, 18 com projeto, contra 1 e 0 do 2º
lugar), e nem buscador nem IA achavam nela a frase que define o produto. Texto escolhido pelo Pedro.

O teste lê o TEXTO VISÍVEL (sem <script>, sem comentário, sem tag) — é o que a pessoa e o rastreador leem.
"""
import html
import io
import os
import re

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _texto_visivel(fonte):
    corpo = fonte[fonte.find("<body"):]
    corpo = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", " ", corpo, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", corpo))).lower()


def _home():
    return io.open(os.path.join(_RAIZ, "index.html"), encoding="utf-8").read()


def test_a_home_define_o_produto_no_texto_visivel():
    t = _texto_visivel(_home())
    assert "software de levantamento de quantitativos de obra" in t
    assert t.count("levantamento de quantitativos") >= 2, "a frase de abertura e o subtítulo do 'como funciona'"


def test_a_definicao_vem_logo_depois_do_titulo_e_o_titulo_nao_mudou():
    fonte = _home()
    h1 = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.search(r"<h1.*?</h1>", fonte, re.S).group(0))).strip()
    assert h1 == "A IA mede sua prancha de verdade — e te mostra no que confiar", h1
    t = _texto_visivel(fonte)
    i_h1 = t.index("te mostra no que confiar")
    i_def = t.index("software de levantamento de quantitativos de obra")
    assert 0 < i_def - i_h1 < 120, "a definição tem que ser a 1ª frase depois do título"


def test_CONTROLE_o_termo_so_no_comentario_ou_no_title_nao_conta():
    """Como estava antes: no <title> e (agora) num comentário — nenhum dos dois é texto que alguém lê."""
    falso = ("<html><head><title>AI.arq — Levantamento de quantitativos</title></head><body>"
             "<!-- software de levantamento de quantitativos de obra --><h1>A IA mede</h1>"
             "<script>var x = 'levantamento de quantitativos';</script></body></html>")
    assert "levantamento de quantitativos" not in _texto_visivel(falso)
