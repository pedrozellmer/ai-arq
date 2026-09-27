# -*- coding: utf-8 -*-
"""Higiene do blog e das tags (auditoria de aquisição de 26/09, item 5).

Cada guarda fecha um achado MEDIDO no site servido em 26/09:
- SEO-10: o /blog/ levava 8 cards de posts agendados escondidos com
  display:none — título, resumo e link pra página noindex, até 15/11. Robô que
  não aplica CSS lia o calendário editorial inteiro.
- SEO-10: o guarda JS do post (e o filtro do índice) usava 10h de Brasília,
  mas o gerador publica à meia-noite de Brasília (hoje_editorial) e o deploy
  das 06h põe o post no ar — quem abria entre 06h e 10h voltava pro /blog/.
- GEO-09: o reposicionamento de 14/09 (engenharia e orçamento) não chegou às
  tags do Twitter da home, ao índice do blog nem à pergunta "Para quem é" do
  FAQ — que ainda era a lista de 6 públicos do caso Capterra (31/08).
- SEO-09: o logo das páginas públicas apontava pra "index.html", não pra "/".
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_a_landing_fala_com_quem_chega import _PUBLICOS  # noqa: E402

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_RAIZ, "scripts"))
import gerar_faq_jsonld  # noqa: E402


def _ler(rel):
    return io.open(os.path.join(_RAIZ, rel), encoding="utf-8").read()


def _posts():
    d = json.load(io.open(os.path.join(_RAIZ, "blog", "posts.json"), encoding="utf-8"))
    return d if isinstance(d, list) else d["posts"]


def _hoje():
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=3)).date().isoformat()


def _publicos(txt):
    t = txt.lower()
    return [p for p in _PUBLICOS if p in t]


# ── SEO-10: nada de post agendado no índice ────────────────────────────────────

def _agendados_no_indice(html, posts, hoje):
    futuros = {p["slug"] for p in posts if p["publish_date"] > hoje}
    linkados = set(re.findall(r'href="/blog/posts/([a-z0-9-]+)\.html"', html))
    return sorted(futuros & linkados) + (["data-future"] if "data-future" in html else [])


def test_o_indice_do_blog_nao_leva_post_agendado():
    ruins = _agendados_no_indice(_ler("blog/index.html"), _posts(), _hoje())
    assert not ruins, "o /blog/ entrega post agendado no HTML: %s" % ruins


def test_CONTROLE_card_escondido_e_pego():
    html = '<article data-future="true" style="display:none"><a href="/blog/posts/x.html">x</a></article>'
    assert _agendados_no_indice(html, [{"slug": "x", "publish_date": "2999-01-01"}], _hoje()) == ["x", "data-future"]


# ── SEO-10: os guardas JS no relógio do gerador ────────────────────────────────

_GUARDA = re.compile(r"new Date\((?:meta\.content|c\.dataset\.publishDate) \+ '(T[0-9:]+-03:00)'\)")


def _horas_dos_guardas(html):
    return _GUARDA.findall(html)


def test_os_guardas_js_viram_o_dia_a_meia_noite_de_brasilia():
    arquivos = ["blog/index.html"] + ["blog/posts/%s.html" % p["slug"] for p in _posts()]
    ruins = {}
    for a in arquivos:
        horas = _horas_dos_guardas(_ler(a))
        if horas != ["T00:00:00-03:00"]:
            ruins[a] = horas
    assert not ruins, "guarda JS fora da meia-noite de Brasília (o relógio do gerador): %s" % ruins


def test_CONTROLE_guarda_das_10h_e_pego():
    assert _horas_dos_guardas("const pubDate = new Date(meta.content + 'T10:00:00-03:00');") == ["T10:00:00-03:00"]


# ── GEO-09: o público de 14/09 nas superfícies que faltavam ────────────────────

def _tag(src, nome):
    if nome == "title":
        m = re.search(r"<title>(.*?)</title>", src, re.S)
    else:
        m = re.search(r'<meta[^>]*(?:name|property)="%s"[^>]*content="(.*?)"' % re.escape(nome), src, re.S)
    assert m, "tag %r sumiu" % nome
    return m.group(1)


def _confere_publico(rotulo, txt):
    ps = _publicos(txt)
    assert "engenh" in ps and "arquitet" in ps, "%s não nomeia engenharia E arquitetura: %r" % (rotulo, txt[:120])
    assert len(ps) <= 3, "%s virou lista de públicos (%s) — caso Capterra, 31/08" % (rotulo, ps)


def test_as_tags_do_twitter_da_home_falam_com_o_mesmo_publico():
    home = _ler("index.html")
    for n in ("twitter:title", "twitter:description"):
        _confere_publico("home " + n, _tag(home, n))


def test_o_indice_do_blog_fala_com_engenharia_e_arquitetura():
    idx = _ler("blog/index.html")
    for n in ("description", "og:description", "twitter:description"):
        _confere_publico("blog " + n, _tag(idx, n))
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", idx, re.S).group(1)
    _confere_publico("blog H1", h1)
    assert "arquitetos" not in _tag(idx, "title").lower(), "o title do blog voltou a ser 'pra arquitetos'"


def test_a_pergunta_para_quem_e_nao_e_lista_de_profissoes():
    itens = dict(gerar_faq_jsonld.perguntas_visiveis(_ler("faq.html")))
    resposta = itens["Para quem é o AI.arq?"]
    _confere_publico("FAQ 'Para quem é'", resposta)
    assert "orçament" in resposta.lower()


def test_CONTROLE_a_lista_antiga_do_faq_reprovaria():
    antiga = ("Pra quem PROJETA e precisa levantar quantidade a partir do próprio desenho: arquitetos, "
              "projetistas e orçamentistas. Também usam construtoras, incorporadoras e escritórios de engenharia.")
    assert len(_publicos(antiga)) == 6


# ── SEO-09: o logo aponta pra URL canônica ─────────────────────────────────────

def test_paginas_indexaveis_nao_linkam_index_html():
    sitemap = _ler("sitemap.xml")
    raiz = sorted(set(re.findall(r"<loc>https://ai\.arq\.br/([a-z0-9-]+\.html)</loc>", sitemap)))
    assert len(raiz) >= 7, raiz
    ruins = [p for p in raiz if 'href="index.html"' in _ler(p)]
    assert not ruins, "página indexável com link pra index.html (a canônica é /): %s" % ruins
