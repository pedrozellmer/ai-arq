# -*- coding: utf-8 -*-
"""Fontes do rodapé do blog — o buraco silencioso de 29/08/2026.

🩸 O que aconteceu: render_sources agrupava por type e DESCARTAVA CALADO
qualquer tipo fora de {norm, book, link, official}. Em 3 dias diferentes eu
inventei "ref", "law" e "internal" — 11 fontes de 5 posts sumiram do rodapé
sem um aviso, num blog cuja regra nº1 é "fonte em toda afirmação". Quem pegou
foi o cético adversarial lendo o HTML GERADO, não a bancada: nenhum teste
olhava o artefato. Estes olham.
"""
import io
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(RAIZ, "blog")
sys.path.insert(0, BLOG)

TIPOS_DO_RENDER = {"norm", "book", "link", "official", "internal"}


def _posts():
    return json.load(io.open(os.path.join(BLOG, "posts.json"), encoding="utf-8"))["posts"]


def test_todo_tipo_de_fonte_existe_no_renderizador():
    """Tipo novo no posts.json sem balde no render = fonte que some calada."""
    ruins = [(p["slug"], s.get("type"))
             for p in _posts() for s in p.get("sources", [])
             if s.get("type", "link") not in TIPOS_DO_RENDER]
    assert not ruins, (
        "fontes com type que o render_sources NAO conhece (somem do rodapé "
        "sem aviso): %r — ou troque o type, ou ensine o balde novo ao "
        "generate.py E a este teste." % ruins)


def test_fonte_de_link_tem_url():
    """Balde web/official renderiza <a href={url}> — sem url o build QUEBRA
    (KeyError no meio da geração). Melhor reprovar aqui, com nome do post."""
    ruins = [(p["slug"], s.get("title", "")[:50])
             for p in _posts() for s in p.get("sources", [])
             if s.get("type", "link") in ("link", "official") and not s.get("url")]
    assert not ruins, "fonte de link sem url (build vai quebrar): %r" % ruins


def test_CONTROLE_POSITIVO_tipo_desconhecido_explode():
    """🧪 Todo guarda prova que REPROVA: a trava do generate.py tem que
    levantar em tipo inventado — era exatamente o que não acontecia."""
    from generate import render_sources
    with pytest.raises(SystemExit):
        render_sources([{"type": "invencao", "title": "x"}], "2026-01-01")


def test_o_rodape_GERADO_tem_as_fontes():
    """O teste que faltou: olha o ARTEFATO. Pra cada post com fontes, o HTML
    gerado precisa citar pelo menos o título da primeira fonte — um rodapé
    'Fontes & Referências' oco nunca mais."""
    import html as _html
    vazios = []
    for p in _posts():
        fontes = p.get("sources") or []
        if not fontes:
            continue
        caminho = os.path.join(BLOG, "posts", p["slug"] + ".html")
        gerado = io.open(caminho, encoding="utf-8").read()
        titulo = fontes[0].get("title", "")
        if titulo and _html.escape(titulo, quote=False) not in gerado and titulo not in gerado:
            vazios.append((p["slug"], titulo[:50]))
    assert not vazios, "post com rodapé de fontes sem a 1ª fonte dentro: %r" % vazios
