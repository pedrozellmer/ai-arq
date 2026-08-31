# -*- coding: utf-8 -*-
"""O guarda de paginas nao pode QUEBRAR a pagina que ele mede (31/08/2026).

O guarda injeta uma sonda `<script>` antes de `</body>` pra ler o resultado.
A 1a versao usava `html.replace("</body>", ...)` — o PRIMEIRO `</body>`. Em
admin.html o primeiro esta DENTRO DE UMA STRING JavaScript:

    testWin.document.write('<!doctype html>… </p></body>');

A sonda entrava no meio da string, quebrava a sintaxe, e o guarda acusava
"Uncaught SyntaxError" num arquivo perfeitamente bom — bloqueando todo push
que tocasse o admin.

🔑 Falso positivo em guarda e PIOR que guarda nenhum: ensina a usar o
AIARQ_DEPLOY_FORCE, e aí o guarda deixa de existir na prática.
"""
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts"))

import guard_paginas_carregam as G  # noqa: E402

SONDA = "<script>window.__sonda=1;</script>"


def test_sonda_entra_no_FIM_e_nao_dentro_de_string_js():
    """O caso real do admin.html, reduzido."""
    html = ("<html><body><script>\n"
            "  w.document.write('<body>oi</p></body>');\n"
            "</script>\n</body></html>")
    saida = G.injeta_sonda(html, SONDA)
    # a sonda tem que estar DEPOIS do bloco <script>, nao dentro dele
    assert saida.index(SONDA) > saida.index("</script>"), (
        "a sonda entrou dentro do <script> — quebra a sintaxe da pagina")
    assert saida.count(SONDA) == 1


def test_pagina_normal_continua_funcionando():
    html = "<html><body><p>oi</p></body></html>"
    saida = G.injeta_sonda(html, SONDA)
    assert saida == "<html><body><p>oi</p>" + SONDA + "</body></html>"


def test_pagina_sem_body_recebe_a_sonda_no_fim():
    html = "<div>sem body</div>"
    assert G.injeta_sonda(html, SONDA) == html + SONDA


def test_CONTROLE_o_jeito_ANTIGO_realmente_quebrava():
    """Prova que o bug era real — sem isto, o teste de cima podia estar
    protegendo contra nada."""
    html = ("<html><body><script>\n"
            "  w.document.write('<body>oi</p></body>');\n"
            "</script>\n</body></html>")
    antigo = html.replace("</body>", SONDA + "</body>")   # o jeito de antes
    primeiro_script_fecha = antigo.index("</script>")
    assert antigo.index(SONDA) < primeiro_script_fecha, (
        "o jeito antigo deveria injetar DENTRO do <script> — se nao injeta, "
        "este teste nao esta reproduzindo o bug de 31/08")
