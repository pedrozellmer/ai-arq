# -*- coding: utf-8 -*-
"""Markdown inline não pode vazar pro leitor — achado da auditoria de 30/08.

🩸 16 blocos de ** LITERAIS apareciam no corpo de 9 posts: o parser montava
<p>/<li>/<h2> mas nunca convertia **negrito**/*itálico*, e intro/cta nem
passavam pelo parser. Guarda no ARTEFATO gerado (a lição: o que importa é o
HTML servido, não o json).
"""
import io
import os
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLOG = os.path.join(RAIZ, "blog")
sys.path.insert(0, BLOG)

# ** ou * pareado dentro de texto visível (fora de <script>/<style>)
_PAR = re.compile(r"\*\*(?=\S)[^*\n]{2,}?\*\*|(?<![\*\w])\*(?=\S)[^*\n]{2,}?\*(?![\*\w])")


def _sem_scripts(html):
    html = re.sub(r"<script\b.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style\b.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    return html


def test_nenhum_post_gerado_tem_markdown_cru():
    posts_dir = os.path.join(BLOG, "posts")
    ruins = []
    for nome in os.listdir(posts_dir):
        if not nome.endswith(".html"):
            continue
        corpo = _sem_scripts(io.open(os.path.join(posts_dir, nome), encoding="utf-8").read())
        for m in _PAR.finditer(corpo):
            ruins.append((nome, m.group(0)[:40]))
    assert not ruins, "markdown inline vazando pro leitor: %r" % ruins[:8]


def test_CONTROLE_o_conversor_reprova_e_converte():
    """🧪 _inline_md tem que converter — senão o guarda acima passa por um
    gerador que não faz nada."""
    from generate import _inline_md
    assert _inline_md("um **negrito** aqui") == "um <strong>negrito</strong> aqui"
    assert _inline_md("um *itálico* aqui") == "um <em>itálico</em> aqui"
    # não estraga <a>/<strong> que já vêm prontos do json
    ja = 'veja <a href="/x">o link</a> e <strong>isto</strong>'
    assert _inline_md(ja) == ja
    # não deixa ** órfão sobreviver como conversão maluca
    assert "**" not in _inline_md("texto **de verdade** limpo")
