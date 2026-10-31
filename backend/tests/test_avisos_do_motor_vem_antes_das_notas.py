# -*- coding: utf-8 -*-
"""Os avisos que pedem ação vêm antes das notas de cada prancha.

🩸 31/10/2026 (f9bf23b4): 405 avisos, 401 deles notas da leitura, e os 4 do motor
perdidos na lista. 📏 60 dias: 31 de 242 projetos com 30+ avisos, mediana 4.
🔑 Nada some: o que não é reconhecido fica recolhido. Com poucas notas, nada muda.
Os textos são os do banco (cortados).
"""
import json
import os
import sys

import pytest

_AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_AQUI))
sys.path.insert(0, _AQUI)

import main  # noqa: E402
from _jsbancada import fonte_html, funcao_js, motor  # noqa: E402

NL = chr(10)
_SRC = fonte_html("projeto.html")
_i = _SRC.index("const _AVISOS_ABERTOS_ATE")
_CONST = _SRC[_i:_SRC.index("function separarAvisos", _i)].replace("const ", "var ")
_JS = NL.join([_CONST, funcao_js("separarAvisos", "projeto.html", _SRC), "1;"])

_DO_MOTOR = [
    "⚠ 12 item(ns) em METRO ficaram sem quantidade.",
    "📐 Nenhuma linha deste projeto foi MEDIDA do desenho.",
    "📄 Das páginas dos PDFs deste projeto, 3 são memoriais.",
    "ℹ 89 pranchas foram lidas e não geraram nenhum item nesta planilha.",
    "✅ Escala conferida pelo próprio desenho.",
    "11 esquadria(s) ficaram sem especificação.",
    "8 linha(s) que parecem ser mobiliário.",
    "Área total de 1400 m² informada por você no upload.",
    "A área que você informou NÃO foi usada nos itens.",
    "A leitura da prancha 'A.pdf' ficou INCOMPLETA: ela tem itens demais.",
    "Tipologia salva como 'residential'.",
    "'Memorial - Composicoes.pdf' tem 59 páginas — lemos as primeiras 40.",
]
_NOTAS = ["Nota %d da leitura: a altura dos pilares não está cotada." % i for i in range(6)]


def _sep(avisos):
    r = motor(_JS).evaljs("JSON.stringify(separarAvisos(%s))" % json.dumps(avisos))
    return json.loads(r)


@pytest.mark.parametrize("aviso", _DO_MOTOR)
def test_aviso_do_motor_fica_aberto(aviso):
    r = _sep(_NOTAS + [aviso])
    assert r["abertos"] == [aviso] and r["notas"] == _NOTAS


def test_a_ordem_de_cada_grupo_nao_muda():
    r = _sep([_DO_MOTOR[1], _NOTAS[0], _DO_MOTOR[0]] + _NOTAS[1:])
    assert r["abertos"] == [_DO_MOTOR[1], _DO_MOTOR[0]] and r["notas"] == _NOTAS


def test_nada_some():
    avisos = _NOTAS + _DO_MOTOR
    r = _sep(avisos)
    assert sorted(r["abertos"] + r["notas"]) == sorted(avisos)


def test_ate_5_notas_a_caixa_segue_como_sempre():
    avisos = _NOTAS[:5] + _DO_MOTOR[:2]
    assert _sep(avisos) == {"abertos": avisos, "notas": []}


def test_a_6a_nota_recolhe():
    r = _sep(_NOTAS[:6] + _DO_MOTOR[:2])
    assert len(r["notas"]) == 6 and len(r["abertos"]) == 2


def test_so_notas_ficam_recolhidas():
    assert _sep(_NOTAS) == {"abertos": [], "notas": _NOTAS}


def test_marca_no_meio_da_frase_nao_e_do_motor():
    nota = "Prancha sem cota ⚠ conferir."
    assert nota in _sep(_NOTAS + [nota])["notas"]


def test_CONTROLE_nota_que_comeca_com_numero_nao_e_do_motor():
    nota = "12 portas identificadas na planta."
    assert nota in _sep(_NOTAS + [nota])["notas"]


def test_aviso_nulo_nao_quebra():
    assert None in _sep(_NOTAS + [None])["notas"]


def _js_tela(avisos):
    return motor(NL.join([
        "var jobId = 'j1'; var __ev = [];",
        "var window = {trackEvent: function (n, m) { __ev.push(n + '|' + m.job_id); }};",
        "var trackEvent = window.trackEvent;",
        "function esc(s) { return s; } function _contarAvisoDoTopo() {}",
        "var __el = {}; function __e(id) { return __el[id] || (__el[id] = {id: id, innerHTML: '',"
        " textContent: '', open: false, oculto: true, ouvinte: null,"
        " classList: {remove: function () { __el[id].oculto = false; }},"
        " addEventListener: function (n, f) { __el[id].ouvinte = [n, f]; }}); }",
        "var document = {getElementById: __e};",
        _CONST,
        funcao_js("separarAvisos", "projeto.html", _SRC),
        funcao_js("_linhaDeAviso", "projeto.html", _SRC),
        funcao_js("renderWarnings", "projeto.html", _SRC),
        "renderWarnings(%s); 1;" % json.dumps(avisos),
    ]))


def test_a_caixa_desenha_os_dois_grupos():
    js = _js_tela(_NOTAS + _DO_MOTOR[:2])
    lista = js.evaljs("__el['proj-warnings-list'].innerHTML")
    assert "METRO" in lista and "Nota 0" not in lista
    assert "Nota 5" in js.evaljs("__el['proj-notas-lista'].innerHTML")
    assert js.evaljs("__el['proj-notas-titulo'].textContent") == \
        "Ver as 6 observações da leitura, prancha por prancha"
    assert js.evaljs("__el['proj-notas'].oculto") is False


def test_CONTROLE_com_poucas_notas_nao_aparece_o_recolhido():
    js = _js_tela(_NOTAS[:2] + _DO_MOTOR[:1])
    assert "Nota 1" in js.evaljs("__el['proj-warnings-list'].innerHTML")
    assert js.evaljs("__el['proj-notas'] === undefined") is True


def test_abrir_as_notas_fica_registrado():
    js = _js_tela(_NOTAS)
    assert js.evaljs("__el['proj-notas'].ouvinte[0]") == "toggle"
    js.evaljs("__el['proj-notas'].open = true; __el['proj-notas'].ouvinte[1](); 1;")
    assert js.evaljs("__ev[0]") == "clique:ver-notas-da-leitura|j1"


def test_fechar_nao_conta():
    js = _js_tela(_NOTAS)
    js.evaljs("__el['proj-notas'].ouvinte[1](); 1;")
    assert js.evaljs("__ev.length") == 0


def test_os_alvos_existem_na_pagina():
    for alvo in ("proj-notas", "proj-notas-titulo", "proj-notas-lista", "proj-warnings-list"):
        assert 'id="%s"' % alvo in _SRC, alvo


def test_o_recolhido_comeca_escondido():
    assert '<details id="proj-notas" class="hidden' in _SRC


def test_o_evento_e_aceito_no_track():
    assert main._track_evento_aceito("clique:ver-notas-da-leitura")
