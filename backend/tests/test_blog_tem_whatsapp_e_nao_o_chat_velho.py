# -*- coding: utf-8 -*-
"""O blog tem o mesmo canal de dúvida que o resto do site: o WhatsApp — não o chat que saiu em 21/07.

🩸 27/09/2026 — O chat público saiu de todas as páginas em 21/07 (0 lead) e virou o botão de
WhatsApp. Só sobrou no blog, por herança do modelo (blog/generate.py). Achado PROD-07 da revisão do
plano de outubro do Instagram: os posts dizem "manda no WhatsApp (o botão verde do site)", e quem
chegava pelo blog — o 2º link da bio em três janelas de outubro — não achava o botão: achava o chat
velho.

O guarda olha o que vai pro ar (os HTMLs gerados do blog) e o gerador que os escreve.
"""
import glob
import io
import os

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _paginas_do_blog():
    return sorted(glob.glob(os.path.join(RAIZ, "blog", "*.html"))
                  + glob.glob(os.path.join(RAIZ, "blog", "posts", "*.html")))


def problemas(html):
    probs = []
    if "chat-widget.js" in html:
        probs.append("carrega o chat velho")
    if "whatsapp-button.js" not in html:
        probs.append("não tem o botão de WhatsApp")
    return probs


def test_toda_pagina_do_blog_tem_o_whatsapp_e_nao_o_chat():
    ruins = []
    for caminho in _paginas_do_blog():
        with io.open(caminho, encoding="utf-8") as f:
            probs = problemas(f.read())
        if probs:
            ruins.append("%s: %s" % (os.path.relpath(caminho, RAIZ), ", ".join(probs)))
    assert not ruins, ("página do blog fora do padrão do site (rode `python blog/generate.py` depois de "
                       "mexer no modelo): " + " | ".join(ruins[:10]))


def test_o_gerador_do_blog_escreve_o_whatsapp_nos_dois_modelos():
    with io.open(os.path.join(RAIZ, "blog", "generate.py"), encoding="utf-8") as f:
        gerador = f.read()
    assert "chat-widget.js" not in gerador, "o gerador do blog voltou a carregar o chat velho"
    assert gerador.count("whatsapp-button.js") >= 2, "o post e o índice do blog precisam do botão de WhatsApp"


def test_CONTROLE_o_guarda_REPROVA_a_pagina_de_antes():
    assert problemas('<script src="/chat-widget.js"></script>') == [
        "carrega o chat velho", "não tem o botão de WhatsApp"]


def test_CONTROLE_o_guarda_le_o_blog_inteiro():
    """Guarda que não acha página nenhuma passa verde guardando nada."""
    paginas = _paginas_do_blog()
    assert len(paginas) > 20, "achei só %d páginas do blog" % len(paginas)
