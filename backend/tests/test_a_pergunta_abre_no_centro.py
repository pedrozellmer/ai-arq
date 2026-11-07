# -*- coding: utf-8 -*-
"""A pergunta de sim ou não abre no CENTRO, com a tela escurecida atrás.

🩸 07/11/2026. O `toast.confirm` punha a pergunta na mesma região dos avisos,
no canto de cima à direita, com 420 px no máximo. Quem não via clicava
"Processar" de novo e levava o "seu envio já começou": em 30 dias, 10 pessoas,
e uma desistiu sem enviar. Um cliente de 06/11 ficou 4,5 min parado nela.
Maquete aprovada pelo Pedro em 07/11: centro, fundo escurecido, botões
grandes, em todas as perguntas do site; os avisos simples continuam no canto.

Este guarda roda o `confirmToast` REAL num DOM mínimo de mentira, só com o que
ele toca. Ele confere onde a pergunta vai parar e como ela fecha.
"""
import json
import os
import re
import sys

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _AQUI)

from _jsbancada import fonte_html, motor  # noqa: E402

_DOM = r"""
var window = this; window.window = window;
function _el(tag) {
  var e = { tag: tag, className: '', attrs: {}, children: [], parentNode: null,
            ouvintes: {}, hidden: false, disabled: false, textContent: '',
            _sub: {}, style: {}, focado: false };
  e.setAttribute = function (k, v) { e.attrs[k] = String(v); };
  e.appendChild = function (c) { c.parentNode = e; e.children.push(c); return c; };
  e.removeChild = function (c) {
    e.children = e.children.filter(function (x) { return x !== c; });
    c.parentNode = null; return c; };
  e.addEventListener = function (ev, fn) { (e.ouvintes[ev] = e.ouvintes[ev] || []).push(fn); };
  e.dispara = function (ev, dado) { (e.ouvintes[ev] || []).forEach(function (fn) { fn(dado || {}); }); };
  e.focus = function () { e.focado = true; };
  e.querySelector = function (s) {
    if (!e._sub[s]) { var x = _el(s); e._sub[s] = x;
      if (s === '.toast-check') { x.hidden = true; } }
    if (s === 'input' || s === 'span') { return e._sub[s]; }
    return e._sub[s];
  };
  e.querySelectorAll = function (s) {
    if (!e._sub[s]) { e._sub[s] = [_el('ok'), _el('cancel')]; }
    return e._sub[s];
  };
  return e;
}
var __body = _el('body'), __head = _el('head');
var document = { readyState: 'complete', addEventListener: function () {},
  body: __body, head: __head, createElement: _el,
  getElementById: function () { return null; } };
null;
"""


def _js():
    js = motor(_DOM)
    js.evaljs(fonte_html("toast.js") + "\n;null;")
    js.evaljs("var __r = 'pendente';"
              "window.toast.confirm('Excluir projeto?', {ok: 'Excluir', cancel: 'Não'})"
              ".then(function (v) { __r = v; }); null;")
    return js


def _estado(js):
    return json.loads(js.evaljs(r"""JSON.stringify((function () {
      var ov = __body.children.filter(function (c) { return c.className === 'toast-overlay'; })[0];
      var item = ov && ov.children[0];
      var bts = item ? item.querySelectorAll('.toast-actions button') : [];
      return { overlay: !!ov, no_body: __body.children.length,
               classe: item ? item.className : null,
               modal: item ? item.attrs['aria-modal'] : null,
               papel: item ? item.attrs['role'] : null,
               ok_focado: bts.length ? bts[0].focado : false,
               resposta: __r };
    })())"""))


def test_a_pergunta_vai_pro_centro_sobre_o_fundo_escuro():
    e = _estado(_js())
    assert e["overlay"], "a pergunta não abriu sobre o fundo escurecido: %r" % e
    assert "toast-dialog" in e["classe"], e
    assert e["modal"] == "true" and e["papel"] == "alertdialog", e
    assert e["ok_focado"], "o foco não foi pro botão principal: %r" % e


def test_o_botao_principal_responde_sim_e_fecha_tudo():
    js = _js()
    js.evaljs("var _ov = __body.children.filter(function (c) {"
              " return c.className === 'toast-overlay'; })[0];"
              "_ov.children[0].querySelectorAll('.toast-actions button')[0].dispara('click'); null;")
    e = _estado(js)
    assert e["resposta"] is True, e
    assert not e["overlay"], "o fundo escuro ficou na tela depois da resposta: %r" % e


def test_esc_vale_como_recusa():
    js = _js()
    js.evaljs("__body.children[__body.children.length - 1].dispara('keydown', {key: 'Escape'}); null;")
    e = _estado(js)
    assert e["resposta"] is False and not e["overlay"], e


def test_clique_no_fundo_nao_fecha_a_pergunta():
    """A pergunta só fecha num dos botões (ou no Esc), como antes: um clique
    fora não pode decidir pela pessoa."""
    js = _js()
    js.evaljs("__body.children[__body.children.length - 1].dispara('click'); null;")
    e = _estado(js)
    assert e["resposta"] == "pendente" and e["overlay"], e


def test_os_avisos_simples_continuam_no_canto():
    src = fonte_html("toast.js")
    show = src[src.index("function show("):src.index("function confirmToast(")]
    assert "region.appendChild(item);" in show and "toast-overlay" not in show


def test_o_css_do_fundo_existe_e_cobre_a_tela():
    css = re.sub(r"/\*.*?\*/", "", fonte_html("toast.js"), flags=re.S)
    regra = re.search(r"\.toast-overlay\s*\{([^}]*)\}", css)
    assert regra, "sem a regra do fundo, a pergunta não fica no centro"
    assert "position: fixed" in regra.group(1) and "inset: 0" in regra.group(1)
    assert "justify-content: center" in regra.group(1)
