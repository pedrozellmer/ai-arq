# -*- coding: utf-8 -*-
"""Só PDF: o aviso pede CIÊNCIA antes de enviar — e nunca bloqueia.

💡 Ideia do Pedro, 23/09/2026: *"quando o arquivo for PDF o cliente recebe um
aviso na tela antes de rodar — vamos ler seu arquivo, mas funcionamos muito
melhor com dwg ou dxf. E coloca um ticker confirmando que a pessoa leu."*

🩸 O que deu a ideia, no mesmo dia: o cliente do job a62f7ae3 mandou 16 PDFs e
recebeu 537 linhas com ZERO medidas. No dia seguinte mandou os 15 DWG do MESMO
projeto: 753 linhas, 521 medidas.

🔑 A CAIXA DE AVISO JÁ EXISTIA (e foi medida e corrigida em 04/09, quando
dizia "não conseguimos medir nada" — que era falso). O que faltava era a
segunda metade do pedido: a confirmação de que a pessoa leu. Por isso este
diálogo NÃO repete a explicação — ele chama de volta pro aviso e pede a caixa.
Dois textos dizendo o mesmo viram ruído, e o segundo some da vista.

🚨 Guardas que EXECUTAM o JS da tela num motor JS (Duktape), não leem o fonte.

🧪 Controles positivos: envio com CAD não é perguntado; "vou buscar o DWG"
volta pro formulário sem criar projeto; sem o toast a tela NÃO cai no
`confirm()` nativo (trava a aba, 19/09); e o botão só libera com a caixa
marcada — inclusive contra clique programático.
"""
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

from _jsbancada import fonte_html, funcao_js, motor, rodar  # noqa: E402

_SRC = fonte_html("dashboard.html")
NL = chr(10)


def _preludio(nomes, com_toast=True, escolha=True):
    lista = ", ".join("{name: '%s'}" % n for n in nomes)
    partes = [
        "var selectedFiles = [%s];" % lista,
        "var __msg = null, __op = null;",
        "var __confirmou = 0;",
        "var confirm = function (m) { __confirmou++; return true; };",
        "var window = {};",
        # a régua de "isto é PDF?" vive na tela e é compartilhada
        "var _ehPdf = function (f) { return /[.]pdf$/i.test((f && f.name) || ''); };",
    ]
    if com_toast:
        partes.append(
            "window.toast = { confirm: function (msg, op) { __msg = msg; __op = op;"
            " return Promise.resolve(%s); } };" % ("true" if escolha else "false"))
    partes += [funcao_js("_soPdfNoEnvio", "dashboard.html", _SRC),
               funcao_js("_confirmarSoPdf", "dashboard.html", _SRC)]
    return NL.join(partes)


def _resp(nomes, **kw):
    js = motor(_preludio(nomes, **kw))
    return js, rodar(js, "_confirmarSoPdf()")


# ── o caso ─────────────────────────────────────────────────────────────────
def test_envio_so_de_PDF_abre_o_aviso():
    js, r = _resp(["planta.pdf", "cortes.pdf"])
    assert r.get("ok"), r
    assert r["valor"] == "seguir"
    assert "só PDF" in js.evaljs("__msg")


def test_o_aviso_CHAMA_de_volta_pro_que_ja_esta_na_tela():
    """🔑 Não repete a explicação da caixa âmbar — aponta pra ela."""
    js, _ = _resp(["planta.pdf"])
    msg = js.evaljs("__msg")
    assert "aviso acima" in msg, msg
    assert "DWG ou DXF" in msg and "mede de verdade" in msg, msg


def test_a_caixa_de_CIENCIA_esta_no_dialogo():
    js, _ = _resp(["planta.pdf"])
    op = js.evaljs("JSON.stringify(__op)")
    assert "checkbox" in op, "o diálogo saiu sem a caixa de ciência: %s" % op
    assert "Li o aviso" in op, op


def test_as_duas_saidas_existem():
    js, _ = _resp(["planta.pdf"])
    op = js.evaljs("JSON.stringify(__op)")
    assert "Enviar assim mesmo" in op and "Vou buscar o DWG" in op, op


def test_quem_escolhe_BUSCAR_o_DWG_nao_cria_projeto():
    _js, r = _resp(["planta.pdf"], escolha=False)
    assert r["valor"] == "buscar", r


# ── controles positivos ────────────────────────────────────────────────────
@pytest.mark.parametrize("nomes, porque", [
    (["planta.dwg"], "só CAD"),
    (["planta.dxf"], "só DXF"),
    (["planta.dwg", "cortes.pdf"], "misto — é a combinação que mede melhor"),
    (["cortes.pdf", "planta.dxf"], "misto na ordem inversa"),
])
def test_CONTROLE_envio_com_CAD_nao_e_perguntado(nomes, porque):
    js, r = _resp(nomes)
    assert r["valor"] == "seguir", porque
    assert js.evaljs("__msg") is None, "abriu o aviso à toa (%s)" % porque


def test_CONTROLE_envio_VAZIO_nao_abre_aviso():
    js, r = _resp([])
    assert r["valor"] == "seguir"
    assert js.evaljs("__msg") is None


def test_CONTROLE_sem_o_toast_NAO_cai_no_confirm_nativo():
    """🪤 19/09: o `confirm()` nativo trava a aba. Avisar não vale um envio
    travado — segue em silêncio."""
    js, r = _resp(["planta.pdf"], com_toast=False)
    assert r.get("ok") and r["valor"] == "seguir", r
    assert js.evaljs("__confirmou") == 0, "caiu no confirm() nativo"


def test_CONTROLE_toast_que_QUEBRA_nao_trava_o_envio():
    pre = _preludio(["planta.pdf"]).replace(
        "return Promise.resolve(true);", "return Promise.reject(new Error('x'));")
    js = motor(pre)
    r = rodar(js, "_confirmarSoPdf()")
    assert r.get("ok") and r["valor"] == "seguir", r


# ══════════════════════════════════════════════════════════════════════════
#  A TRANCA DA CAIXA DE CIÊNCIA (toast.js)
#  🪤 LIMITE DESTE GUARDA, declarado: `confirmToast` monta DOM de verdade
#     (createElement, innerHTML, addEventListener) e o motor JS da bancada não
#     tem DOM. Encenar um DOM inteiro aqui daria um dublê grande e frágil —
#     que é o tipo de teste que passa verde e não guarda nada.
#     Então este confere o FONTE, e a casa sabe que guarda de fonte erra de
#     dois jeitos. O que ele prende é a TRANCA DUPLA: sem ela, o `disabled`
#     sozinho é decorativo (um clique programático passa por cima).
#  📌 O comportamento foi conferido no navegador antes de subir.
# ══════════════════════════════════════════════════════════════════════════
def _toast_js():
    caminho = os.path.join(os.path.dirname(os.path.dirname(_AQUI)), "toast.js")
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def test_o_botao_nasce_TRAVADO_quando_ha_caixa_de_ciencia():
    src = _toast_js()
    assert "okBtn.disabled = true;" in src, (
        "o botão principal não nasce travado — a caixa vira decoração")


def test_marcar_a_caixa_DESTRAVA_o_botao():
    src = _toast_js()
    assert "okBtn.disabled = !box.checked;" in src, (
        "marcar a caixa não solta o botão — o diálogo fica sem saída")


def test_a_TRANCA_segura_ate_clique_programatico():
    """🔑 `disabled` é a porta; isto é a tranca. Sem ela, um `.click()` de
    script (ou um CSS quebrado) passa por cima da ciência da pessoa."""
    src = _toast_js()
    assert "if (checkLabel && !box.checked) return;" in src, (
        "o clique não confere a caixa — só o atributo disabled protege")


def test_CONTROLE_quem_NAO_pede_caixa_continua_com_o_dialogo_de_antes():
    """A opção é aditiva: diálogo sem `checkbox` não ganha caixa nem trava."""
    src = _toast_js()
    assert "const checkLabel = (opts && opts.checkbox) || '';" in src
    assert "if (checkLabel) {" in src, (
        "a caixa passou a aparecer sempre — quebraria os outros diálogos")


def test_o_rotulo_da_caixa_vai_por_textContent_nunca_innerHTML():
    """🔒 O rótulo pode vir de qualquer tela; innerHTML aqui seria XSS."""
    src = _toast_js()
    assert "wrap.querySelector('span').textContent = String(checkLabel);" in src
