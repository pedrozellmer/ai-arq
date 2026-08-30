# -*- coding: utf-8 -*-
"""Concorrente não volta a ser citado como fonte no blog (auditoria 30/08).

🔒 A auditoria achou ~13 citações de blog de concorrente (Sienge, OrçaFascio)
como fonte bibliográfica — conflito da regra "fonte em toda afirmação" com
"nunca citar concorrente". Resolvido trocando por primária VERIFICADA (TCU,
CAIXA, Planalto, gov.br, Aldo Mattos) ou dropando quando o post já tinha a
primária. Este guarda impede a recaída, no posts.json E no HTML gerado.
"""
import io
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(RAIZ, "blog")

# domínios de concorrente que não podem aparecer como link (lista da memória
# project_concorrentes_20260625). NÃO inclui nomes citados em texto analítico —
# só o link como FONTE.
_CONC = re.compile(r"(sienge\.com\.br|orcafascio\.com|or[cç]afascio|"
                   r"vobi\.com\.br|levanta\.ai|koreos|i9orcamentos)", re.IGNORECASE)


def test_posts_json_sem_link_de_concorrente():
    d = json.load(io.open(os.path.join(BLOG, "posts.json"), encoding="utf-8"))
    ruins = [(p["slug"], s.get("url"))
             for p in d["posts"] for s in p.get("sources", [])
             if _CONC.search(s.get("url") or "")]
    assert not ruins, "concorrente citado como fonte no posts.json: %r" % ruins


def test_html_gerado_sem_link_de_concorrente():
    posts = os.path.join(BLOG, "posts")
    ruins = []
    for nome in os.listdir(posts):
        if nome.endswith(".html"):
            html = io.open(os.path.join(posts, nome), encoding="utf-8").read()
            for m in re.finditer(r'href="([^"]+)"', html):
                if _CONC.search(m.group(1)):
                    ruins.append((nome, m.group(1)))
    assert not ruins, "link de concorrente no HTML servido: %r" % ruins


def test_CONTROLE_o_detector_pega_concorrente():
    """🧪 Prova que o regex reprova mesmo."""
    assert _CONC.search("https://sienge.com.br/blog/x")
    assert _CONC.search("https://www.orcafascio.com/y")
    assert not _CONC.search("https://portal.tcu.gov.br/z")
    assert not _CONC.search("https://www.planalto.gov.br/lei")
