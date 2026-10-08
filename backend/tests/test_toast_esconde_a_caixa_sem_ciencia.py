# -*- coding: utf-8 -*-
"""O diálogo SEM caixa de ciência não mostra caixinha vazia.

🩸 08/10/2026. Desde 23/09 (a caixa de ciência do aviso de só-PDF), todo
`toast.confirm` sem a opção `checkbox` mostrava uma caixa de marcar vazia, sem
rótulo e sem função: o `<label class="toast-check" hidden>` tinha `display: flex`
no CSS da casa, e display do autor VENCE a regra do navegador pra `[hidden]`.
Visto na prévia da pergunta do tipo antes do envio, conferindo no navegador
(`getComputedStyle` = flex com `hidden` = true).

🪤 E a 1ª versão do conserto DERRUBOU o toast do site inteiro: o CSS mora numa
template string do JS, e uma crase no comentário fechou a string — SyntaxError,
`window.toast` indefinido, nenhum aviso abre. Por isso o 1º guarda COMPILA o
arquivo de verdade.

🪤 O 2º guarda lê o FONTE do CSS: não há motor de CSS na bancada. Ele garante
que a regra existe; a prova de que ela vence foi o navegador (ver acima).
"""
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)

from _jsbancada import fonte_html, motor  # noqa: E402

_SRC = fonte_html("toast.js")


def test_o_toast_COMPILA_e_fica_no_window():
    js = motor(
        "var window = this; window.window = window;"
        "var _no = function () { return {setAttribute: function () {}, appendChild: function () {},"
        " querySelector: function () { return null; }, style: {}, classList: {add: function () {}}}; };"
        "var document = {readyState: 'complete', addEventListener: function () {},"
        " createElement: _no, head: {appendChild: function () {}},"
        " body: {appendChild: function () {}}, getElementById: function () { return null; }};"
        # o motor serializa o valor da última expressão: `null` evita devolver o window
        "null;")
    js.evaljs(_SRC + chr(10) + ";null;")   # SyntaxError aqui = nenhum aviso do site abre
    assert js.evaljs("typeof window.toast.confirm") == "function"


def test_a_caixa_com_hidden_some_mesmo_com_display_flex():
    css = re.sub(r"/\*.*?\*/", "", _SRC, flags=re.S)
    assert re.search(r"\.toast-check\s*\{[^}]*display\s*:\s*flex", css), (
        "a regra da caixa mudou — reveja se o [hidden] ainda precisa de ajuda")
    assert re.search(r"\.toast-check\[hidden\]\s*\{[^}]*display\s*:\s*none", css), (
        "sem a regra, o display: flex vence o hidden e a caixinha vazia volta "
        "em todo diálogo sem ciência")


def test_CONTROLE_o_html_do_dialogo_nasce_com_a_caixa_hidden():
    """A regra só vale se o rótulo nasce `hidden` e só a opção `checkbox` o mostra."""
    assert '<label class="toast-check" hidden>' in _SRC
    assert "wrap.hidden = false" in _SRC
