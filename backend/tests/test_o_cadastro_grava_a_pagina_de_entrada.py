# -*- coding: utf-8 -*-
"""O cadastro grava na CONTA a página por onde a pessoa entrou no site.

🆕 26/09/2026 — Pedro, olhando a semana recorde (32 cadastros de 21 a 26/09):
"o que a gente pode melhorar nesses rastreios?". Só 18 dos 32 deixaram rastro
na telemetria (quem aceita cookie). A captura de first-touch
(`aiarq-utils.js`, `_captureSource`) já guardava `landing` — a página de
chegada —, mas o `cadastro.html` mandava pra conta só `src`, `src_ref` e
`src_campaign`. "Entrou pela home ou pelo post do memorial?" ficava sem
resposta justamente pra quem não aceita cookie.

Estes testes RODAM o código da tela no dukpy, não leem o fonte:
- `_origemParaConta`, a função que monta o que vai pra conta;
- o trecho do submit que chama `sbClient.auth.updateUser`, recortado do
  arquivo sem mudar uma vírgula, com `aiArqSource` e `sbClient` encenados.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _jsbancada import (  # noqa: E402
    _do_marcador_ate_fechar, fonte_html, funcao_js, motor, rodar)

_ARQ = "cadastro.html"

# O formato que `_captureSource` grava em `aiarq_src` (aiarq-utils.js).
_TOQUE = {
    "label": "google", "utm_source": "", "utm_medium": "", "utm_campaign": "",
    "ref": "www.google.com",
    "landing": "/blog/posts/memorial-descritivo-de-obra-modelo-pdf-docx.html",
}

# O trecho do submit como era ATÉ 26/09 — só pro controle do fim.
_SUBMIT_DE_ANTES = """try {
        var _srcAttr = window.aiArqSource && window.aiArqSource();
        if (_srcAttr && _srcAttr.label) {
          await sbClient.auth.updateUser({ data: {
            src: _srcAttr.label,
            src_ref: _srcAttr.ref || '',
            src_campaign: _srcAttr.utm_campaign || ''
          } });
        }
      }"""


def _ler(js, expr):
    """🪤 dukpy recusa `undefined` como resultado — tudo sai por JSON."""
    return json.loads(js.evaljs("JSON.stringify(%s)" % expr))


def _motor():
    js = motor()
    js.evaljs(funcao_js("_origemParaConta", _ARQ))
    return js


def _para_conta(toque):
    return _ler(_motor(), "_origemParaConta(%s)" % json.dumps(toque))


# ══════════════════════════════════════════════════════════════════════════
#  A função que monta a origem da conta
# ══════════════════════════════════════════════════════════════════════════
def test_a_conta_recebe_a_pagina_de_entrada():
    assert _para_conta(_TOQUE)["src_landing"] == _TOQUE["landing"]


def test_os_tres_campos_de_antes_saem_iguais():
    """🚨 Consertar o ALCANCE não troca o PADRÃO: a série de origem é lida
    desde 07/07 por `src`, `src_ref` e `src_campaign`. Eles têm que sair
    exatamente como saíam — e nenhum campo a mais além da página."""
    o = _para_conta(dict(_TOQUE, utm_campaign="bio"))
    assert (o["src"], o["src_ref"], o["src_campaign"]) == (
        "google", "www.google.com", "bio")
    assert sorted(o) == ["src", "src_campaign", "src_landing", "src_ref"]


def test_sem_origem_nao_grava_nada():
    js = _motor()
    for vazio in ("null", "undefined", "{}", json.dumps(dict(_TOQUE, label=""))):
        assert _ler(js, "_origemParaConta(%s)" % vazio) is None, vazio


def test_first_touch_sem_pagina_grava_vazio():
    """Quem tem um `aiarq_src` sem `landing` continua com a origem gravada."""
    toque = {k: v for k, v in _TOQUE.items() if k != "landing"}
    assert _para_conta(toque)["src_landing"] == ""


def test_a_pagina_e_cortada_em_80():
    """O `aiarq_src` mora no localStorage do visitante: o corte feito em
    `_captureSource` não é garantia do que chega aqui."""
    o = _para_conta(dict(_TOQUE, landing="/" + "a" * 300))
    assert len(o["src_landing"]) == 80


# ══════════════════════════════════════════════════════════════════════════
#  O submit de verdade: o que chega no updateUser
# ══════════════════════════════════════════════════════════════════════════
def _trecho_do_submit():
    src = fonte_html(_ARQ)
    i = src.find("_origemParaConta(window.aiArqSource")
    assert i > 0, "o submit parou de montar a origem por _origemParaConta"
    t = src.rfind("try {", 0, i)
    assert t > 0, "não achei o try da origem no submit"
    return _do_marcador_ate_fechar(src, t, "try da origem (%s)" % _ARQ)


def _chamadas_do_updateUser(toque, trecho=None):
    """Roda o trecho do submit e devolve o que o `updateUser` recebeu.

    O `catch` do arquivo engole erro de propósito (a atribuição nunca bloqueia
    o cadastro); aqui ele relança, pra um erro do trecho não passar calado."""
    js = _motor()
    js.evaljs(
        "var __chamadas = [];"
        "var window = { aiArqSource: function () { return %s; } };"
        "var sbClient = { auth: { updateUser: function (o) {"
        " __chamadas.push(o); return Promise.resolve({ data: {}, error: null }); } } };"
        "async function __atribuir() { %s catch (e) { throw e; } }"
        " null;" % (json.dumps(toque), trecho or _trecho_do_submit()))
    r = rodar(js, "__atribuir()")
    assert "erro" not in r, r
    return _ler(js, "__chamadas")


def test_o_submit_manda_a_pagina_pra_conta():
    """`updateUser({ data })` é o contrato do supabase-js: o que vai em `data`
    vira `user_metadata` da conta — é de lá que a origem é lida."""
    assert _chamadas_do_updateUser(_TOQUE) == [{"data": {
        "src": "google", "src_ref": "www.google.com", "src_campaign": "",
        "src_landing": _TOQUE["landing"],
    }}]


def test_o_submit_sem_origem_nao_chama_o_updateUser():
    assert _chamadas_do_updateUser(None) == []


def test_CONTROLE_o_submit_de_ANTES_nao_mandava_a_pagina():
    """Prova que o teste de cima reprova o código de antes: rodando o trecho
    antigo no mesmo cenário, a conta recebe a origem SEM a página."""
    chamadas = _chamadas_do_updateUser(_TOQUE, trecho=_SUBMIT_DE_ANTES)
    assert len(chamadas) == 1
    dados = chamadas[0]["data"]
    assert dados["src"] == "google", "o controle nem chegou a gravar a origem"
    assert "src_landing" not in dados
    assert chamadas != _chamadas_do_updateUser(_TOQUE)
